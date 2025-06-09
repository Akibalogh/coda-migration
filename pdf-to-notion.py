import fitz  # PyMuPDF
import requests
import json
import os
from PIL import Image
import pytesseract
import io

# --- Configuration ---
PDF_PATH = "DLC.link Wiki.pdf"
NOTION_API_TOKEN = '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'
NOTION_PARENT_PAGE_ID = '1dc636dd0ba580a6b3cbe3074911045f'
CUTOFF_TITLE = "Client Meeting Notes"
MODE = "single"  # Options: "single", "ten", "all"

notion_headers = {
    'Authorization': f'Bearer {NOTION_API_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

CREATED_TITLES_PATH = "created_titles.txt"
created_titles = set()
if os.path.exists(CREATED_TITLES_PATH):
    with open(CREATED_TITLES_PATH, "r") as f:
        created_titles = set(line.strip() for line in f)


def ocr_pdf_page(pdf_path, page_num, dpi=300):
    doc = fitz.open(pdf_path)
    if page_num < 0 or page_num >= len(doc):
        return ""
    pix = doc[page_num].get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img)


def clean_ocr_text_to_paragraphs(ocr_text):
    lines = ocr_text.splitlines()
    paragraphs = []

    for line in lines:
        text = line.strip()
        if not text:
            continue

        if text.startswith(("e¢", "e", "°", "•", "◦", "-", "→", ">", "*")):
            content = text.lstrip("e¢°•◦→->* ").strip()
            bullet_type = "bulleted_list_item"
        else:
            content = text
            bullet_type = "paragraph"

        paragraphs.append([{
            "text": content,
            "bold": False,
            "italic": False,
            "type": bullet_type
        }])
    return paragraphs


def build_notion_blocks_with_bullets(paragraphs):
    blocks = []
    for para in paragraphs:
        if not para:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": []}
            })
            continue

        rich_text = []
        buffer = ""
        current_style = {"bold": para[0]["bold"], "italic": para[0]["italic"]}

        def flush_buffer():
            nonlocal buffer
            if not buffer:
                return
            for i in range(0, len(buffer), 2000):
                chunk = buffer[i:i+2000]
                rich_text.append({
                    "type": "text",
                    "text": {"content": chunk},
                    "annotations": {
                        "bold": current_style["bold"],
                        "italic": current_style["italic"],
                        "underline": False,
                        "strikethrough": False,
                        "code": False,
                        "color": "default"
                    }
                })
            buffer = ""

        for span in para:
            if span["bold"] == current_style["bold"] and span["italic"] == current_style["italic"]:
                buffer += span["text"] + " "
            else:
                flush_buffer()
                current_style = {"bold": span["bold"], "italic": span["italic"]}
                buffer = span["text"] + " "
        flush_buffer()

        block_type = para[0].get("type", "paragraph")

        blocks.append({
            "object": "block",
            "type": block_type,
            block_type: {"rich_text": rich_text}
        })

    return blocks


def create_notion_page(title, paragraphs):
    search_url = "https://api.notion.com/v1/search"
    search_payload = {
        "query": title,
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        "filter": {"value": "page", "property": "object"}
    }

    search_response = requests.post(search_url, headers=notion_headers, json=search_payload)
    if search_response.ok:
        results = search_response.json().get("results", [])
        for page in results:
            page_title = page.get("properties", {}).get("title", {}).get("title", [])
            if page_title and page_title[0]["text"]["content"] == title:
                page_id = page["id"]
                print(f"[↺] Existing page found: {title} → Deleting")
                delete_url = f"https://api.notion.com/v1/blocks/{page_id}"
                del_res = requests.delete(delete_url, headers=notion_headers)
                if del_res.ok:
                    print(f"[✓] Deleted: {title}")
                else:
                    print(f"[ERROR] Failed to delete page: {title}")
                    print(del_res.status_code, del_res.text)
                break

    children = build_notion_blocks_with_bullets(paragraphs)

    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": children
    }

    print(f"> Creating Notion page: '{title}' under parent ID {NOTION_PARENT_PAGE_ID}")
    url = 'https://api.notion.com/v1/pages'
    r = requests.post(url, headers=notion_headers, json=payload)

    if not r.ok:
        print("[ERROR] Notion API failed:")
        print("Status Code:", r.status_code)
        print("Response:", r.text)
        print("Payload:", json.dumps(payload, indent=2))
        return

    notion_url = r.json().get("url", "(URL missing)")
    print(f"[✓] Created Notion page: {title}")
    print(f"    ↳ {notion_url}")


def run():
    doc = fitz.open(PDF_PATH)
    for i, page in enumerate(doc):
        ocr_text = ocr_pdf_page(PDF_PATH, i)
        if "Second CL Grant preso - 10/19/21" in ocr_text:
            paragraphs = clean_ocr_text_to_paragraphs(ocr_text)
            create_notion_page("Second CL Grant preso - 10/19/21", paragraphs)
            break

if __name__ == "__main__":
    run()
