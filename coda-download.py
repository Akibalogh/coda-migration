import requests
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

def fetch_coda_page_html(page_id):
    url = f'https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/{page_id}/content'
    resp = requests.get(url, headers=coda_headers)
    resp.raise_for_status()
    return resp.json().get("body", "")

def extract_text_blocks_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    lines = []
    for el in soup.find_all(['p', 'li']):
        text = el.get_text(strip=True)
        if text:
            lines.append(text)
    return lines

def create_notion_page(title, text_blocks, source_url=None):
    children_blocks = []
    if source_url:
        children_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": f"Migrated from: {source_url}"}
                }]
            }
        })

    for line in text_blocks:
        children_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": line}
                }]
            }
        })

    data = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": children_blocks
    }

    url = 'https://api.notion.com/v1/pages'
    resp = requests.post(url, headers=notion_headers, json=data)
    resp.raise_for_status()
    print(f"[DONE] Created Notion page: {title}")

# --- Main logic ---
def run():
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
    page_id = first_page.get("id")
    url = first_page.get("browserLink")

    print(f"Fetching and sending: {title}")
    html = fetch_coda_page_html(page_id)
    text_blocks = extract_text_blocks_from_html(html)
    create_notion_page(title, text_blocks, source_url=url)

if __name__ == '__main__':
    run()
