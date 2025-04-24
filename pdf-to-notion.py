import fitz  # PyMuPDF
import requests
import json

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

            if line_y is not None and last_y is not None and line_y - last_y > 15:
                if current_para:
                    paragraphs.append(current_para.copy())
                    current_para.clear()

            last_y = line_y

            if not block_text:
                if current_para:
                    paragraphs.append(current_para.copy())
                    current_para.clear()
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    is_bold = (span.get("flags", 0) & 2 > 0) or "Bold" in span.get("font", "")
                    is_italic = span.get("flags", 0) & 1 > 0
                    current_para.append({
                        "text": span["text"],
                        "bold": is_bold,
                        "italic": is_italic
                    })

    if current_para:
        paragraphs.append(current_para)
    return paragraphs

def create_notion_page(title, paragraphs):
    children = []

    for para in paragraphs:
        if not para:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": []}
            })
            continue

        buffer = ""
        current_style = {"bold": para[0]["bold"], "italic": para[0]["italic"]}
        blocks = []

        def flush_to_block():
            nonlocal buffer, blocks, current_style
            if buffer == "":
                return
            chunks = [buffer[i:i+2000] for i in range(0, len(buffer), 2000)]
            for chunk in chunks:
                blocks.append({
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
                flush_to_block()
                current_style = {"bold": span["bold"], "italic": span["italic"]}
                buffer = span["text"]

        flush_to_block()
        if blocks:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": blocks}
            })

    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": children
    }

    url = 'https://api.notion.com/v1/pages'
    r = requests.post(url, headers=notion_headers, json=payload)

    if not r.ok:
        print("Notion API error:", r.status_code)
        print("Response:", r.text)
        print("Payload:", json.dumps(payload, indent=2))
    r.raise_for_status()
    print(f"[\u2713] Created Notion page: {title}")

def run():
    titles = extract_titles_after_cutoff(PDF_PATH, CUTOFF_TITLE)
    print(f"Found {len(titles)} client pages\n")

    count = 0
    for title in titles:
        print(f"> Processing: {title}")
        paragraphs = extract_verbatim_blocks(PDF_PATH, title)
        if paragraphs:
            create_notion_page(title, paragraphs)
            count += 1

        if MODE == "single":
            break
        elif MODE == "ten" and count >= 10:
            break

if __name__ == "__main__":
    run()
