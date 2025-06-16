import requests
import json
import unicodedata
from bs4 import BeautifulSoup
import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Configuration
CODA_API_TOKEN = '3c10b406-488c-49ac-a483-4b912be6fc23'
CODA_DOC_ID = '0eJEEjA-GU'
MAX_TEST_PAGES = 2  # Limit to 2 test pages for now

# Headers
coda_headers = {'Authorization': f'Bearer {CODA_API_TOKEN}'}

NOTION_API_TOKEN = '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'
NOTION_PARENT_PAGE_ID = '1dc636dd0ba580a6b3cbe3074911045f'
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
            print(f"[DEBUG] Fetching pages with params: {params}")
            resp = requests.get(base_url, headers=coda_headers, params=params)
            
            if resp.status_code != 200:
                print(f"[ERROR] Failed to fetch pages. Status: {resp.status_code}")
                print(f"[ERROR] Response: {resp.text}")
                sys.exit(1)

            data = resp.json()
            items = data.get('items', [])
            
            # Debug first page details
            if len(all_pages) == 0 and items:
                print("\n[DEBUG] First page details:")
                print(json.dumps(items[0], indent=2))
                print()
            
            all_pages.extend(items)
            print(f"[INFO] Fetched {len(items)} pages...")

            next_token = data.get('nextPageToken')
            if not next_token or len(all_pages) >= MAX_TEST_PAGES:
                break

        except Exception as e:
            print(f"[ERROR] Exception while fetching pages: {str(e)}")
            sys.exit(1)

    print(f"[INFO] Total pages fetched: {len(all_pages)}")
    return all_pages

def setup_driver():
    """Setup Chrome driver with appropriate options"""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--user-data-dir=/Users/akibalogh/selenium-profile")
    options.add_argument("--profile-directory=Default")
    return webdriver.Chrome(options=options)

def postprocess_coda_lists(html_content):
    """Convert lines starting with '*' or '-' in kr-line divs into nested <ul><li> HTML lists. Also preserve the first non-list, bolded line as a bold paragraph, and skip header/title lines."""
    from bs4 import BeautifulSoup, Tag
    print('[DEBUG] Entering postprocess_coda_lists')
    print(f'[DEBUG] html_content type: {type(html_content)}')
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove Coda header and page title if present
    header = soup.find('div', class_='kr-canvas-header')
    if header:
        header.decompose()

    # Find all kr-line divs in order
    lines = soup.find_all('div', class_=lambda c: c and 'kr-line' in c)
    print(f'[DEBUG] Found {len(lines)} kr-line divs')
    new_blocks = []
    i = 0
    first_bolded_done = False
    while i < len(lines):
        div = lines[i]
        text = div.get_text(strip=True)
        if text is None:
            text = ''
        # If this is the first non-list, bolded line, preserve as bold paragraph
        if not first_bolded_done and not text.startswith('*') and not text.startswith('-'):
            # Check for bold class in any span
            bold_span = div.find('span', class_=lambda c: c and 'kr-bold' in c)
            if bold_span:
                p = soup.new_tag('p')
                strong = soup.new_tag('strong')
                strong.string = text
                p.append(strong)
                new_blocks.append(p)
                first_bolded_done = True
                i += 1
                continue
        # Detect bullet lines
        if text.startswith('*') or text.startswith('-'):
            list_stack = []
            while i < len(lines):
                div2 = lines[i]
                text2 = div2.get_text(strip=True)
                if text2 is None:
                    text2 = ''
                if text2.startswith('*'):
                    level = 0
                    content = text2.lstrip('*').strip()
                elif text2.startswith('-'):
                    level = 1
                    content = text2.lstrip('-').strip()
                else:
                    break
                if content is None:
                    content = ''
                while list_stack and list_stack[-1][1] >= level:
                    list_stack.pop()
                if not list_stack or list_stack[-1][1] < level:
                    ul = soup.new_tag('ul')
                    if list_stack:
                        parent_ul, _ = list_stack[-1]
                        if parent_ul.contents and hasattr(parent_ul.contents[-1], 'name') and parent_ul.contents[-1].name == 'li':
                            parent_ul.contents[-1].append(ul)
                        else:
                            li = soup.new_tag('li')
                            li.string = ''
                            parent_ul.append(li)
                            li.append(ul)
                    else:
                        new_blocks.append(ul)
                    list_stack.append((ul, level))
                li = soup.new_tag('li')
                li.string = content if content is not None else ''
                list_stack[-1][0].append(li)
                i += 1
            continue
        else:
            # For other non-list lines, add as normal paragraph
            p = soup.new_tag('p')
            p.string = text
            new_blocks.append(p)
            i += 1
    for div in lines:
        try:
            div.decompose()
        except Exception as e:
            print(f"[DEBUG] Failed to decompose div: {e}")
    main_container = soup
    # Filter out any tags with name=None or non-Tag objects
    filtered_blocks = []
    for block in new_blocks:
        if not isinstance(block, Tag):
            print(f"[DEBUG] Skipping non-Tag block: type={type(block)}, id={id(block)}")
            continue
        if block.name is None:
            print(f"[DEBUG] Skipping block with name=None: type={type(block)}, id={id(block)}")
            continue
        filtered_blocks.append(block)
    for block in filtered_blocks:
        try:
            main_container.append(block)
        except Exception as e:
            print(f"[DEBUG] Failed to append block: {e}")
    print('[DEBUG] Leaving postprocess_coda_lists')
    return str(soup)

def extract_content(driver, url):
    """Extract formatted content from a Coda page using robust selectors and JS."""
    try:
        print(f"[DEBUG] Navigating to URL: {url}")
        driver.get(url)
        print("[DEBUG] Waiting for Coda main content...")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]'))
        )
        time.sleep(2)
        js = '''
        let contentElements = document.querySelectorAll('[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]');
        for (let element of contentElements) {
            if (element.offsetWidth > 0 && element.offsetHeight > 0) {
                return element.innerHTML;
            }
        }
        return null;
        '''
        html_content = driver.execute_script(js)
        print(f"[DEBUG] html_content type: {type(html_content)}")
        if not html_content:
            print("[ERROR] Could not find visible Coda content container.")
            return None, None
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        clean_html = str(soup)
        print(f"[DEBUG] clean_html type: {type(clean_html)}")
        # Post-process for nested lists
        clean_html = postprocess_coda_lists(clean_html)
        print(f"[DEBUG] postprocessed clean_html type: {type(clean_html)}")
        clean_text = soup.get_text(separator='\n', strip=True)
        print(f"[DEBUG] clean_text type: {type(clean_text)}")
        return clean_html, clean_text
    except Exception as e:
        print(f"[ERROR] Failed to extract content: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, None

def save_content(html_content, text_content, page_name):
    """Save extracted content to files"""
    if not os.path.exists('output'):
        os.makedirs('output')
    clean_name = "".join(c for c in page_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    if html_content:
        html_path = f'output/{clean_name}.html'
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[INFO] Saved HTML content to {html_path}")
    if text_content:
        text_path = f'output/{clean_name}.txt'
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        print(f"[INFO] Saved text content to {text_path}")

def html_to_notion_blocks(html):
    from bs4 import BeautifulSoup, NavigableString, Tag
    soup = BeautifulSoup(html, 'html.parser')
    blocks = []

    # If the soup has a single top-level tag (like <div>), process its children
    elements = soup.contents
    if len(elements) == 1 and isinstance(elements[0], Tag):
        elements = elements[0].contents

    def parse_rich_text(el, parent_annotations=None):
        if parent_annotations is None:
            parent_annotations = {"bold": False, "italic": False, "underline": False, "strikethrough": False, "code": False, "color": "default"}
        rich_text = []
        for child in el.children if hasattr(el, 'children') else []:
            annotations = parent_annotations.copy()
            if isinstance(child, NavigableString):
                text = str(child)
                if text.strip():
                    rich_text.append({
                        "type": "text",
                        "text": {"content": text},
                        "annotations": annotations
                    })
            elif isinstance(child, Tag):
                tag = child.name.lower()
                if tag in ["strong", "b"]:
                    annotations["bold"] = True
                if tag in ["em", "i"]:
                    annotations["italic"] = True
                if tag == "u":
                    annotations["underline"] = True
                if tag in ["s", "strike"]:
                    annotations["strikethrough"] = True
                if tag == "code":
                    annotations["code"] = True
                rich_text.extend(parse_rich_text(child, annotations))
        return rich_text

    def parse_list(ul):
        items = []
        for li in ul.find_all('li', recursive=False):
            rich_text = parse_rich_text(li)
            if not rich_text:
                text = li.get_text(strip=True)
                if text:
                    rich_text = [{
                        "type": "text",
                        "text": {"content": text},
                        "annotations": {"bold": False, "italic": False, "underline": False, "strikethrough": False, "code": False, "color": "default"}
                    }]
            block = {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": rich_text
                }
            }
            nested_uls = li.find_all('ul', recursive=False)
            if nested_uls:
                block["bulleted_list_item"]["children"] = []
                for nested_ul in nested_uls:
                    block["bulleted_list_item"]["children"].extend(parse_list(nested_ul))
            items.append(block)
        return items

    for el in elements:
        if isinstance(el, NavigableString):
            if str(el).strip() == '':
                # Empty line
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": []}
                })
            continue
        if not isinstance(el, Tag):
            continue
        tag = el.name.lower()
        if tag in ["h1", "h2", "h3"]:
            level = int(tag[1])
            rich_text = parse_rich_text(el)
            if not rich_text:
                text = el.get_text(strip=True)
                if text:
                    rich_text = [{
                        "type": "text",
                        "text": {"content": text},
                        "annotations": {"bold": False, "italic": False, "underline": False, "strikethrough": False, "code": False, "color": "default"}
                    }]
            blocks.append({
                "object": "block",
                "type": f"heading_{level}",
                f"heading_{level}": {"rich_text": rich_text}
            })
        elif tag == 'ul':
            blocks += parse_list(el)
        elif tag in ['p', 'div']:
            rich_text = parse_rich_text(el)
            if not rich_text:
                text = el.get_text(strip=True)
                if text:
                    rich_text = [{
                        "type": "text",
                        "text": {"content": text},
                        "annotations": {"bold": False, "italic": False, "underline": False, "strikethrough": False, "code": False, "color": "default"}
                    }]
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text}
            })
        elif tag == 'br':
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": []}
            })

    # Remove leading empty/whitespace-only paragraph blocks
    while blocks and blocks[0]["type"] == "paragraph" and (not blocks[0]["paragraph"]["rich_text"] or all(rt["type"] == "text" and not rt["text"]["content"].strip() for rt in blocks[0]["paragraph"]["rich_text"])):
        blocks.pop(0)

    return blocks

def create_notion_page(title, html):
    blocks = html_to_notion_blocks(html)
    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": blocks
    }
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

def main():
    pages = fetch_all_pages_flat()
    if not pages:
        print("[ERROR] No pages found!")
        return
    
    # Find the index of 'Client Meeting Notes'
    start_idx = None
    for i, page in enumerate(pages):
        if normalize(page.get('name', '')) == normalize('Client Meeting Notes'):
            start_idx = i + 1
            break
    if start_idx is None:
        print("[ERROR] Could not find 'Client Meeting Notes' in page list!")
        return
    
    # Process the next 2 pages after 'Client Meeting Notes'
    pages_to_process = pages[start_idx:start_idx+2]
    if not pages_to_process:
        print("[ERROR] No pages found after 'Client Meeting Notes'!")
        return
    
    driver = setup_driver()
    try:
        for page in pages_to_process:
            page_name = page.get('name', 'unnamed_page')
            page_url = page.get('browserLink', '')  # Use browserLink directly
            print(f"\n[INFO] Processing page: {page_name}")
            print(f"[DEBUG] URL: {page_url}")
            html_content, text_content = extract_content(driver, page_url)
            if html_content and text_content:
                save_content(html_content, text_content, page_name)
                create_notion_page(page_name, html_content)
            else:
                print(f"[WARN] No content extracted for {page_name}")
            time.sleep(2)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
