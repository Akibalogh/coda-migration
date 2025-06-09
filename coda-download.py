import requests
import json
import unicodedata
from bs4 import BeautifulSoup

# --- Configuration ---
CODA_API_TOKEN = '3c10b406-488c-49ac-a483-4b912be6fc23'
CODA_DOC_ID = '0eJEEjA-GU'
NOTION_API_TOKEN = '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'
NOTION_PARENT_PAGE_ID = '1dc636dd0ba580a6b3cbe3074911045f'
CUTOFF_TITLE = 'Client Meeting Notes'

# --- Headers ---
coda_headers = {'Authorization': f'Bearer {CODA_API_TOKEN}'}
notion_headers = {
    'Authorization': f'Bearer {NOTION_API_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

def normalize(text):
    return unicodedata.normalize("NFKC", text.strip().lower())

def fetch_all_root_pages():
    print("[INFO] Fetching all Coda root pages...")
    base_url = f'https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages'
    all_pages = []
    next_token = None

    while True:
        params = {"pageToken": next_token} if next_token else {}
        resp = requests.get(base_url, headers=coda_headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_pages.extend(items)
        next_token = data.get("nextPageToken")
        if not next_token:
            break

    return all_pages

def fetch_coda_page_html(page_id_or_canvas_id, is_canvas=True):
    if is_canvas:
        browser_url = f'https://coda.io/d/_d{CODA_DOC_ID}/_{page_id_or_canvas_id[7:]}'
    else:
        browser_url = f'https://coda.io/d/_d{CODA_DOC_ID}/_{page_id_or_canvas_id}'

    print(f"[INFO] Fetching Coda browser page: {browser_url}")
    resp = requests.get(browser_url)
    resp.raise_for_status()
    return resp.text

def extract_sections_by_heading(html):
    print("[INFO] Parsing HTML into sections by headings")
    soup = BeautifulSoup(html, 'html.parser')
    sections = {}
    current_heading = None
    current_list_stack = []

    for el in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
        tag = el.name
        text = el.get_text(strip=True)
        if not text:
            continue

        if tag in ['h1', 'h2', 'h3']:
            current_heading = text
            sections[current_heading] = []
            current_list_stack = []
        elif current_heading:
            bullet_type = 'bulleted_list_item' if tag == 'li' else 'paragraph'
            block = {
                "object": "block",
                "type": bullet_type,
                bullet_type: {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": text},
                        "annotations": {
                            "bold": False,
                            "italic": False,
                            "underline": False,
                            "strikethrough": False,
                            "code": False,
                            "color": "default"
                        }
                    }]
                }
            }
            if bullet_type == 'bulleted_list_item' and current_list_stack:
                current_list_stack[-1].setdefault('children', []).append(block)
            else:
                sections[current_heading].append(block)
                if bullet_type == 'bulleted_list_item':
                    current_list_stack = [block]
                else:
                    current_list_stack = []
    return sections

def build_notion_blocks(section_blocks, source_url=None):
    blocks = []
    if source_url:
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": f"Migrated from: {source_url}"}
                }]
            }
        })
    blocks.extend(section_blocks)
    return blocks

def create_notion_page(title, section_blocks, source_url=None):
    print(f"[INFO] Creating Notion page: {title}")
    children_blocks = build_notion_blocks(section_blocks, source_url)
    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": children_blocks
    }
    url = 'https://api.notion.com/v1/pages'
    resp = requests.post(url, headers=notion_headers, json=payload)
    resp.raise_for_status()
    print(f"[DONE] Created Notion page: {title}")

def run():
    print("[INFO] Starting migration run...")
    pages = fetch_all_root_pages()
    cutoff_idx = next((i for i, p in enumerate(pages) if normalize(p.get('name', '')) == normalize(CUTOFF_TITLE)), None)

    if cutoff_idx is None:
        print("Could not find 'Client Meeting Notes'.")
        return

    filtered_pages = pages[cutoff_idx + 1:]
    if not filtered_pages:
        print("No pages found after Client Meeting Notes.")
        return

    first_page = filtered_pages[0]
    title = first_page.get("name", "Untitled")
    browser_url = first_page.get("browserLink")
    page_id = first_page.get("id").replace("canvas-", "")

    print(f"Fetching and sending: {title}")
    html = fetch_coda_page_html(page_id, is_canvas=True)
    sections = extract_sections_by_heading(html)
    print(f"[INFO] Extracted {len(sections)} sections.")
    for heading, blocks in sections.items():
        create_notion_page(heading, blocks, source_url=browser_url)

if __name__ == '__main__':
    run()
