import requests
import json
import unicodedata
from bs4 import BeautifulSoup
import time

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

def fetch_all_pages_flat():
    print("[INFO] Fetching all Coda pages (flat list)...")
    base_url = f'https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages'
    all_pages = []
    next_token = None

    while True:
        params = {}
        if next_token:
            params["pageToken"] = next_token

        try:
            resp = requests.get(base_url, headers=coda_headers, params=params)
            resp.raise_for_status()
        except requests.HTTPError as e:
            print(f"[ERROR] Fetch failed at token: {next_token}")
            print(f"[ERROR] Response: {resp.text}")
            raise e

        data = resp.json()
        all_pages.extend(data.get("items", []))

        next_token = data.get("nextPageToken")
        if not next_token:
            break

    return all_pages

def fetch_coda_page_html(page_id):
    """
    Fetch HTML content for a Coda page.
    page_id should be the full ID including 'canvas-' prefix if present.
    """
    # If page_id already has canvas- prefix, use it directly
    if page_id.startswith('canvas-'):
        urls = [
            f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/{page_id}/content",
            f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/{page_id}"
        ]
    else:
        # If no canvas- prefix, try both with and without
        urls = [
            f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/{page_id}/content",
            f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/canvas-{page_id}/content",
            f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/{page_id}",
            f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/canvas-{page_id}"
        ]

    for url in urls:
        try:
            print(f"[DEBUG] Trying URL: {url}")
            resp = requests.get(url, headers=coda_headers)
            if resp.status_code == 200:
                data = resp.json()
                if 'body' in data:
                    return data['body']
        except Exception as e:
            print(f"[DEBUG] Failed with URL {url}: {e}")
            continue

    raise requests.HTTPError("Failed to fetch Coda page content.")

def extract_sections_by_heading(html):
    soup = BeautifulSoup(html, 'html.parser')
    blocks = []
    for el in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
        text = el.get_text(strip=True)
        if not text:
            continue
        block_type = 'bulleted_list_item' if el.name == 'li' else 'paragraph'
        blocks.append({
            "object": "block",
            "type": block_type,
            block_type: {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": text},
                    "annotations": {
                        "bold": False, "italic": False,
                        "underline": False, "strikethrough": False,
                        "code": False, "color": "default"
                    }
                }]
            }
        })
    return blocks

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
    return blocks + section_blocks

def create_notion_page(title, section_blocks, source_url=None):
    if not section_blocks:
        print(f"[SKIP] No content to migrate for '{title}'")
        return
    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": build_notion_blocks(section_blocks, source_url)
    }
    url = 'https://api.notion.com/v1/pages'
    resp = requests.post(url, headers=notion_headers, json=payload)
    resp.raise_for_status()
    print(f"[DONE] Migrated: {title}")

def fetch_all_pages_with_children(doc_id):
    print("[INFO] Fetching all pages with children...")
    base_url = f'https://coda.io/apis/v1/docs/{doc_id}/pages'
    all_pages = []
    next_token = None

    while True:
        params = {}
        if next_token:
            params["pageToken"] = next_token

        try:
            resp = requests.get(base_url, headers=coda_headers, params=params)
            resp.raise_for_status()
        except requests.HTTPError as e:
            print(f"[ERROR] Fetch failed at token: {next_token}")
            print(f"[ERROR] Response: {resp.text}")
            raise e

        data = resp.json()
        pages = data.get("items", [])
        
        # For each page, fetch its children
        for page in pages:
            page_id = page.get('id')
            if page_id:
                try:
                    children_url = f"{base_url}/{page_id}/children"
                    children_resp = requests.get(children_url, headers=coda_headers)
                    if children_resp.status_code == 200:
                        children_data = children_resp.json()
                        page['children'] = children_data.get('items', [])
                except Exception as e:
                    print(f"[WARN] Failed to fetch children for page {page_id}: {e}")
                    page['children'] = []

        all_pages.extend(pages)
        next_token = data.get("nextPageToken")
        if not next_token:
            break

    return all_pages

def run():
    print("[INFO] Starting migration...")
    all_pages = fetch_all_pages_flat()

    # Locate the 'Client Meeting Notes' page
    cutoff_idx = next((i for i, p in enumerate(all_pages) if normalize(p.get("name", "")) == normalize(CUTOFF_TITLE)), None)
    if cutoff_idx is None:
        print(f"[ERROR] Could not find '{CUTOFF_TITLE}' in pages")
        return
    print(f"[INFO] Found '{CUTOFF_TITLE}' at index {cutoff_idx}")

    # Get all pages that come after the cutoff
    following_pages = all_pages[cutoff_idx + 1:]
    print(f"\n[DEBUG] Pages after cutoff:")
    for p in following_pages[:5]:
        print(f"- {p.get('name')} | id: {p.get('id')} | type: {p.get('type')}")

    # Attempt to migrate the first valid page (regardless of type)
    for page in following_pages:
        title = page.get("name", "Untitled")
        page_id = page.get("id")
        browser_url = page.get("browserLink")

        if not page_id:
            print(f"[SKIP] Page missing ID: {title}")
            continue

        print(f"[INFO] Migrating page: {title} | ID: {page_id} | Type: {page.get('type')}")
        try:
            html = fetch_coda_page_html(page_id)
            if not html or not html.strip():
                print(f"[SKIP] No HTML content in page: {title}")
                continue

            section_blocks = extract_sections_by_heading(html)
            create_notion_page(title, section_blocks, browser_url)
            print(f"[SUCCESS] Migrated: {title}")
            break  # stop after first successful migration

        except Exception as e:
            print(f"[ERROR] Failed to fetch or migrate page '{title}': {e}")
            continue

if __name__ == '__main__':
    run()
