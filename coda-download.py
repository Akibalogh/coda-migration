import requests
import json
import unicodedata
from bs4 import BeautifulSoup
import time
import sys

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

# --- CANVAS ENDPOINT DEBUG BLOCK ---
'''
if not CODA_API_TOKEN:
    print("[ERROR] CODA_API_TOKEN environment variable is not set!")
    sys.exit(1)

canvas_url = f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/canvases"
print(f"[DEBUG] Fetching canvases from: {canvas_url}")
try:
    resp = requests.get(canvas_url, headers=coda_headers)
    print(f"[DEBUG] Response status: {resp.status_code}")
    print(f"[DEBUG] Raw response text: {resp.text}")
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch canvases. Status: {resp.status_code}")
        sys.exit(1)
    data = resp.json()
    print(f"[DEBUG] Canvases response: {json.dumps(data, indent=2)}")
    print("[DEBUG] Canvas IDs:")
    for item in data.get("items", []):
        print(f"- id: {item.get('id')} | name: {item.get('name')}")
except Exception as e:
    print(f"[ERROR] Exception in fetch_coda_canvases: {e}")
    sys.exit(1)
'''
# --- END CANVAS ENDPOINT DEBUG BLOCK ---

# --- PAGES CONTENT ENDPOINT DEBUG BLOCK ---
canvas_page_id = "canvas-A5HjEaKOeB"  # Example canvas page ID
pages_content_url = f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/{canvas_page_id}/content"
print(f"[DEBUG] Fetching page content from: {pages_content_url}")
try:
    resp = requests.get(pages_content_url, headers=coda_headers)
    print(f"[DEBUG] Response status: {resp.status_code}")
    print(f"[DEBUG] Raw response text: {resp.text}")
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch page content. Status: {resp.status_code}")
        sys.exit(1)
    data = resp.json()
    print(f"[DEBUG] Page content response: {json.dumps(data, indent=2)}")
    print("[INFO] Page content endpoint check complete. Exiting for debug.")
    sys.exit(0)
except Exception as e:
    print(f"[ERROR] Exception while fetching page content: {str(e)}")
    sys.exit(1)
# --- END PAGES CONTENT ENDPOINT DEBUG BLOCK ---

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
            print(f"\n[DEBUG] Fetching pages from: {base_url}")
            if params:
                print(f"[DEBUG] With params: {params}")
            
            resp = requests.get(base_url, headers=coda_headers, params=params)
            print(f"[DEBUG] Response status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"[ERROR] Failed to fetch pages list")
                print(f"[DEBUG] Response: {resp.text}")
                raise requests.HTTPError("Failed to fetch pages list")
                
            data = resp.json()
            
            # Print the raw API response for the first batch
            if not next_token:  # Only print for first batch
                print("\n[DEBUG] Raw API response for first page batch:")
                print(json.dumps(data, indent=2))
            
            # Print details about each page in this batch
            print("\n[DEBUG] Pages in this batch:")
            for page in data.get("items", []):
                print(f"\nPage: {page.get('name')}")
                print(f"- id: {page.get('id')}")
                print(f"- type: {page.get('type')}")
                print(f"- href: {page.get('href')}")
                print(f"- browserLink: {page.get('browserLink')}")
                if page.get('name') == CUTOFF_TITLE:
                    print("\n[DEBUG] Found cutoff page! Full details:")
                    print(json.dumps(page, indent=2))
            
            all_pages.extend(data.get("items", []))
            
            next_token = data.get("nextPageToken")
            if not next_token:
                break

        except Exception as e:
            print(f"[ERROR] Fetch failed at token: {next_token}")
            print(f"[ERROR] Exception: {str(e)}")
            raise e

    return all_pages

def fetch_coda_page_html(page_id, page_type=None):
    """
    Fetch HTML content for a Coda page, handling both regular and canvas pages.
    """
    print(f"\n[DEBUG] Fetching content for page_id: {page_id}, type: {page_type}")
    
    # For canvas pages (check both type and ID format)
    is_canvas = page_id.startswith("canvas-")
    
    if is_canvas:
        # Get the raw canvas ID by stripping the prefix
        raw_id = page_id.replace("canvas-", "")
        # Get the canvas nodes
        url = f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/canvases/{raw_id}/nodes"
        print(f"[DEBUG] Using canvas nodes endpoint: {url}")
        
        try:
            print(f"[DEBUG] Making API request for canvas nodes...")
            resp = requests.get(url, headers=coda_headers)
            print(f"[DEBUG] Response status: {resp.status_code}")
            print(f"[DEBUG] Response headers: {resp.headers}")
            
            if resp.status_code != 200:
                print(f"[ERROR] Failed to fetch canvas nodes. Status: {resp.status_code}")
                print(f"[DEBUG] Error response: {resp.text}")
                return None
                
            data = resp.json()
            print(f"[DEBUG] Canvas nodes response: {json.dumps(data, indent=2)}")
            
            # Extract content from nodes
            content = []
            for node in data.get("items", []):
                node_name = node.get("name", "")
                node_value = node.get("value", "")
                if node_name or node_value:
                    content.append(f"{node_name}: {node_value}")
            
            return "\n".join(content)
            
        except Exception as e:
            print(f"[ERROR] Exception while fetching canvas nodes: {str(e)}")
            return None
            
    else:
        # For regular doc pages
        url = f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages/{page_id}"
        print(f"[DEBUG] Using regular page endpoint: {url}")
        
        try:
            print(f"[DEBUG] Making API request...")
            resp = requests.get(url, headers=coda_headers)
            print(f"[DEBUG] Response status: {resp.status_code}")
            print(f"[DEBUG] Response headers: {resp.headers}")
            
            if resp.status_code != 200:
                print(f"[ERROR] Failed to fetch content. Status: {resp.status_code}")
                print(f"[DEBUG] Error response: {resp.text}")
                return None
                
            data = resp.json()
            return data.get("body", "")
            
        except Exception as e:
            print(f"[ERROR] Exception while fetching content: {str(e)}")
            return None

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

def fetch_coda_canvases():
    print("[DEBUG] fetch_coda_canvases() called!")
    url = f"https://coda.io/apis/v1/docs/{CODA_DOC_ID}/canvases"
    print(f"[DEBUG] Fetching canvases from: {url}")
    try:
        resp = requests.get(url, headers=coda_headers)
        print(f"[DEBUG] Response status: {resp.status_code}")
        print(f"[DEBUG] Raw response text: {resp.text}")
        if resp.status_code != 200:
            print(f"[ERROR] Failed to fetch canvases. Status: {resp.status_code}")
            return
        data = resp.json()
        print(f"[DEBUG] Canvases response: {json.dumps(data, indent=2)}")
        print("[DEBUG] Canvas IDs:")
        for item in data.get("items", []):
            print(f"- id: {item.get('id')} | name: {item.get('name')}")
    except Exception as e:
        print(f"[ERROR] Exception while fetching canvases: {str(e)}")

def run():
    print("[INFO] Starting migration...")
    fetch_coda_canvases()
    all_pages = fetch_all_pages_flat()

    # Locate the 'Client Meeting Notes' page
    cutoff_idx = next((i for i, p in enumerate(all_pages) if normalize(p.get("name", "")) == normalize(CUTOFF_TITLE)), None)
    if cutoff_idx is None:
        print(f"[ERROR] Could not find '{CUTOFF_TITLE}' in pages")
        return
    print(f"[INFO] Found '{CUTOFF_TITLE}' at index {cutoff_idx}")

    # Get all pages that come after the cutoff (limit to first 5 for testing)
    following_pages = all_pages[cutoff_idx + 1:cutoff_idx + 6]  # Only get 5 pages
    print(f"\n[DEBUG] First 5 pages after cutoff:")
    for p in following_pages:
        print(f"- {p.get('name')} | id: {p.get('id')} | type: {p.get('type')}")

    # Attempt to migrate each page
    for page in following_pages:
        title = page.get("name", "Untitled")
        page_id = page.get("id")
        page_type = page.get("type")
        
        if not page_id:
            print(f"[SKIP] No ID for page: {title}")
            continue

        print(f"\n[INFO] Processing: {title} (ID: {page_id}, Type: {page_type})")
        
        try:
            # Fetch page content with type information
            html = fetch_coda_page_html(page_id, page_type)
            
            if html is None:
                print(f"[ERROR] Failed to fetch content for '{title}'")
                continue
                
            # Extract and process content
            section_blocks = extract_sections_by_heading(html)
            
            # Create Notion page
            source_url = f"https://coda.io/d/{CODA_DOC_ID}/_/{page_id}"
            create_notion_page(title, section_blocks, source_url)
            
        except requests.HTTPError as e:
            print(f"[ERROR] HTTP error for '{title}': {str(e)}")
            continue
        except Exception as e:
            print(f"[ERROR] Failed to process '{title}': {str(e)}")
            continue

    print("\n[INFO] Test migration completed")

if __name__ == '__main__':
    fetch_coda_canvases()
    print("\n================ END OF CANVAS LIST ================\n")
    run()
