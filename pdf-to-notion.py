import fitz  # PyMuPDF
import requests
import json
import os

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

def extract_titles_after_cutoff(pdf_path, cutoff_title):
    doc = fitz.open(pdf_path)
    headings = []
    seen = set()
    passed_cutoff = False
    cutoff_size = None

    for page in doc:
        for block in page.get_text("dict")['blocks']:
            for line in block.get("lines", []):
                if not line.get("spans"):
                    continue
                span = line["spans"][0]
                text = span["text"].strip()
                size = span["size"]
                if size >= 16 and text and text not in seen:
                    if text == cutoff_title:
                        passed_cutoff = True
                        cutoff_size = size
                        continue
                    if passed_cutoff and size == cutoff_size:
                        headings.append(text)
                        seen.add(text)
    return headings

def extract_verbatim_blocks(pdf_path, start_title):
    doc = fitz.open(pdf_path)
    capturing = False
    heading_size = None
    paragraphs = []
    current_para = []
    last_y = None

    for page in doc:
        for block in page.get_text("dict")['blocks']:
            if not block.get("lines"):
                continue

            line_y = block['lines'][0]['bbox'][1] if block['lines'] else None
            block_text = " ".join(
                span["text"] for line in block["lines"] for span in line.get("spans", [])
            ).strip()

            if not capturing and block_text == start_title:
                span = block["lines"][0]["spans"][0]
                heading_size = span["size"]
                capturing = True
                last_y = line_y
                continue

            if capturing:
                span = block["lines"][0]["spans"][0]
                if span["size"] == heading_size and block_text != start_title:
                    if current_para:
                        paragraphs.append(current_para.copy())
                        current_para.clear()
                    return paragraphs

            if not capturing:
                continue

            if line_y is not None and last_y is not None:
                gap = line_y - last_y
                if gap > 40:
                    current_para.append({"text": "\n", "bold": False, "italic": False})
                current_para.append({"text": "\n", "bold": False, "italic": False})

            last_y = line_y

            if not block_text:
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    is_bold = (span.get("flags", 0) & 2 > 0) or "Bold" in span.get("font", "")
                    is_italic = span.get("flags", 0) & 1 > 0
                    text = span["text"]
                    if text.strip():
                        current_para.append({
                            "text": text + " ",
                            "bold": is_bold,
                            "italic": is_italic,
                            "x": span["bbox"][0]
                        })

    if current_para:
        paragraphs.append(current_para)
    return paragraphs

def build_notion_blocks_with_bullets(paragraphs):
    def get_bullet_type(text):
        if text.strip().startswith("→"):
            return "to_do"
        elif text.strip().startswith("◦"):
            return "bulleted_list_item"
        elif text.strip().startswith("•"):
            return "bulleted_list_item"
        return "paragraph"

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
                buffer += span["text"]
            else:
                flush_buffer()
                current_style = {"bold": span["bold"], "italic": span["italic"]}
                buffer = span["text"]
        flush_buffer()

        first_text = para[0]["text"].strip()
        bullet_type = get_bullet_type(first_text)

        if bullet_type != "paragraph" and rich_text:
            rich_text[0]["text"]["content"] = rich_text[0]["text"]["content"].lstrip("•◦→ ").strip()

        blocks.append({
            "object": "block",
            "type": bullet_type,
            bullet_type: {"rich_text": rich_text}
        })

    return blocks

def create_notion_page(title, paragraphs):
    # --- Search for existing page by title ---
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

    # --- Build new content blocks ---
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
    titles = extract_titles_after_cutoff(PDF_PATH, CUTOFF_TITLE)
    print(f"Found {len(titles)} client pages\n")

    count = 0
    for title in titles:
        print(f"> Processing: {title}")
        paragraphs = extract_verbatim_blocks(PDF_PATH, title)
        if paragraphs:
            create_notion_page(title, paragraphs)
            with open(CREATED_TITLES_PATH, "a") as f:
                f.write(title + "\n")
            count += 1

        if MODE == "single":
            break
        elif MODE == "ten" and count >= 10:
            break

if __name__ == "__main__":
    run()