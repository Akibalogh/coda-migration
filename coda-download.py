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
import re
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Configuration
CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
CODA_DOC_ID = '0eJEEjA-GU'
# MAX_TEST_PAGES = 2  # Remove page limit to process all pages
MAX_TEST_PAGES = None

if not CODA_API_TOKEN:
    print('[ERROR] CODA_API_TOKEN not set in environment or .env file.')
    sys.exit(1)

NOTION_API_TOKEN = os.getenv('NOTION_API_TOKEN')
NOTION_PARENT_PAGE_ID = '1dc636dd0ba580a6b3cbe3074911045f'

if not NOTION_API_TOKEN:
    print('[ERROR] NOTION_API_TOKEN not set in environment or .env file.')
    sys.exit(1)

# Headers
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
            if not next_token or (MAX_TEST_PAGES is not None and len(all_pages) >= MAX_TEST_PAGES):
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
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove Coda header and page title if present
    header = soup.find('div', class_='kr-canvas-header')
    if header:
        header.decompose()

    # Find all kr-line divs in order
    lines = soup.find_all('div', class_=lambda c: c and 'kr-line' in c)
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
        except Exception:
            pass
    main_container = soup
    # Filter out any tags with name=None or non-Tag objects
    from bs4 import Tag
    filtered_blocks = []
    for block in new_blocks:
        if not isinstance(block, Tag):
            continue
        if block.name is None:
            continue
        filtered_blocks.append(block)
    for block in filtered_blocks:
        try:
            main_container.append(block)
        except Exception:
            pass
    return str(soup)

def convert_coda_bullets_to_lists(html):
    from bs4 import BeautifulSoup, Tag
    soup = BeautifulSoup(html, "html.parser")
    lines = soup.find_all("div", class_=lambda c: c and "kr-line" in c)
    new_blocks = []
    i = 0
    while i < len(lines):
        div = lines[i]
        classes = div.get("class", [])
        # Unordered list
        if "kr-ulist" in classes and "kr-listitem" in classes:
            ul = soup.new_tag("ul")
            while i < len(lines):
                div2 = lines[i]
                classes2 = div2.get("class", [])
                if "kr-ulist" in classes2 and "kr-listitem" in classes2:
                    li = soup.new_tag("li")
                    text = div2.get_text(strip=True)
                    li.string = text
                    ul.append(li)
                    i += 1
                else:
                    break
            new_blocks.append(ul)
            continue
        # Ordered list
        elif "kr-olist" in classes and "kr-listitem" in classes:
            ol = soup.new_tag("ol")
            while i < len(lines):
                div2 = lines[i]
                classes2 = div2.get("class", [])
                if "kr-olist" in classes2 and "kr-listitem" in classes2:
                    li = soup.new_tag("li")
                    text = div2.get_text(strip=True)
                    li.string = text
                    ol.append(li)
                    i += 1
                else:
                    break
            new_blocks.append(ol)
            continue
        else:
            # Normal paragraph
            p = soup.new_tag("p")
            p.string = div.get_text(strip=True)
            new_blocks.append(p)
            i += 1
    # Remove all original kr-line divs
    for div in lines:
        div.decompose()
    # Append new blocks to soup
    for block in new_blocks:
        soup.append(block)
    return str(soup)

def extract_content(driver, url):
    """Extract formatted content from a Coda page using robust selectors and JS."""
    try:
        driver.get(url)
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
        if not html_content:
            return None, None
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        clean_html = str(soup)
        clean_html = postprocess_coda_lists(clean_html)
        clean_text = soup.get_text(separator='\n', strip=True)
        return clean_html, clean_text
    except Exception as e:
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
    first_chunk = blocks[:100]
    remaining = blocks[100:]
    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": first_chunk
    }
    url = 'https://api.notion.com/v1/pages'
    r = requests.post(url, headers=notion_headers, json=payload)
    if not r.ok:
        print("[ERROR] Notion API failed:")
        print("Status Code:", r.status_code)
        print("Response:", r.text)
        return
    page_id = r.json().get("id")
    # Append remaining blocks in chunks of 100
    append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    while remaining:
        chunk = remaining[:100]
        remaining = remaining[100:]
        append_payload = {"children": chunk}
        r = requests.patch(append_url, headers=notion_headers, json=append_payload)
        if not r.ok:
            print(f"[ERROR] Notion API failed on chunk append:")
            print("Status Code:", r.status_code)
            print("Response:", r.text)
            return

def extract_title_and_date(page_name):
    # Match patterns like 'Title 10/20/21' or 'Title - 10/20/21'
    match = re.match(r"^(.*?)(?:\s*-)?\s*(\d{1,2}/\d{1,2}/\d{2,4})$", page_name)
    if match:
        title = match.group(1).strip()
        date = match.group(2)
        return title, date
    return page_name, None

def main():
    pages = fetch_all_pages_flat()
    if not pages:
        print("[ERROR] No pages found!")
        sys.exit(1)

    target_name = "Algoz"
    target_page = None
    for page in pages:
        page_name = page.get('name', 'unnamed_page')
        if normalize(page_name) == normalize(target_name):
            target_page = page
            break

    if not target_page:
        print(f"[ERROR] Could not find page: {target_name}")
        sys.exit(1)

    driver = setup_driver()
    try:
        page_name = target_page.get('name', 'unnamed_page')
        page_url = target_page.get('browserLink', '')
        print(f"[INFO] Processing page: {page_name}")
        print(f"[INFO] URL: {page_url}")
        try:
            driver.get(page_url)
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
            raw_html = driver.execute_script(js)
            if not raw_html:
                print(f"[ERROR] No raw HTML extracted for {page_name} at {page_url}")
                return
            # Save raw HTML for inspection
            if not os.path.exists('output'):
                os.makedirs('output')
            with open('output/Algoz_raw.html', 'w', encoding='utf-8') as f:
                f.write(raw_html)
            print(f"[INFO] Saved raw HTML to output/Algoz_raw.html")
            # --- Improved bullet/numbered list detection ---
            soup = BeautifulSoup(raw_html, 'html.parser')
            clean_html = convert_coda_bullets_to_lists(str(soup))
            clean_html = postprocess_coda_lists(clean_html)
            clean_text = soup.get_text(separator='\n', strip=True)
            if clean_html and clean_text:
                save_content(clean_html, clean_text, page_name)
                notion_title, call_date = extract_title_and_date(page_name)
                if call_date:
                    soup2 = BeautifulSoup(clean_html, 'html.parser')
                    first_block = soup2.find(['p', 'div'])
                    if first_block:
                        strong_tag = soup2.new_tag('strong')
                        strong_tag.string = f'Call {call_date} '
                        if first_block.contents:
                            first_block.insert(0, strong_tag)
                            if (len(first_block.contents) > 1 and
                                isinstance(first_block.contents[1], str) and
                                not first_block.contents[1].startswith(' ')):
                                first_block.insert(1, ' ')
                        else:
                            first_block.append(strong_tag)
                        clean_html = str(soup2)
                    else:
                        clean_html = f'<p><strong>Call {call_date}</strong></p>' + clean_html.lstrip('\n').lstrip('\r').lstrip()
                create_notion_page(notion_title, clean_html)
                print(f"[✓] Notion page created: {notion_title}")
            else:
                print(f"[ERROR] No content extracted for {page_name}")
        except Exception as e:
            print(f"[ERROR] Exception during extraction for {page_name} at {page_url}: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
