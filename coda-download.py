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
    """Convert kr-line divs into properly nested <ul>/<ol> HTML lists using block-level-X for nesting, and robustly preserve anchor tags and all inline content. Do not change heading handling."""
    from bs4 import BeautifulSoup, Tag, NavigableString
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove Coda header and page title if present
    header = soup.find('div', class_='kr-canvas-header')
    if header:
        header.decompose()

    lines = soup.find_all('div', class_=lambda c: c and 'kr-line' in c)
    new_blocks = []
    stack = []  # Stack of (list_tag, level, list_obj, li_obj)

    def extract_content_with_links(tag):
        result = []
        for child in tag.children:
            if isinstance(child, NavigableString):
                if child.strip():
                    result.append(child)
            elif isinstance(child, Tag):
                # If it's a kr-object-e, look for <a>
                if 'kr-object-e' in child.get('class', []):
                    a = child.find('a', href=True)
                    if a:
                        result.append(a)
                        continue
                # If it's an <a>, preserve it
                if child.name == 'a' and child.has_attr('href'):
                    result.append(child)
                    continue
                # Otherwise, recurse
                result.extend(extract_content_with_links(child))
        return result

    for div in lines:
        classes = div.get('class', [])
        # Determine nesting level
        level = 0
        for c in classes:
            if c.startswith('block-level-'):
                try:
                    level = int(c.split('-')[-1])
                except Exception:
                    level = 0
        is_bullet = 'kr-ulist' in classes and 'kr-listitem' in classes
        is_numbered = 'kr-olist' in classes and 'kr-listitem' in classes
        list_tag = 'ul' if is_bullet else ('ol' if is_numbered else None)

        if is_bullet or is_numbered:
            # Pop stack to the parent level
            while stack and (stack[-1][1] >= level):
                stack.pop()
            # If we need a new list at this level
            if not stack or stack[-1][0] != list_tag or stack[-1][1] != level:
                new_list = soup.new_tag(list_tag)
                if stack:
                    # Attach to parent li
                    parent_li = stack[-1][3]
                    if parent_li is not None:
                        parent_li.append(new_list)
                    else:
                        new_blocks.append(new_list)
                else:
                    new_blocks.append(new_list)
                stack.append((list_tag, level, new_list, None))
            # Create list item
            li = soup.new_tag('li')
            for content in extract_content_with_links(div):
                li.append(content)
            # Attach li to current list
            stack[-1][2].append(li)
            # Update stack to point to this li for possible nested lists
            stack[-1] = (stack[-1][0], stack[-1][1], stack[-1][2], li)
        else:
            # Not a list item: close all open lists
            stack = []
            p = soup.new_tag('p')
            for content in extract_content_with_links(div):
                p.append(content)
            new_blocks.append(p)

    # Remove all original kr-line divs
    for div in lines:
        try:
            div.decompose()
        except Exception:
            pass
    # Remove empty <ul>, <ol>, <li>
    for tag in soup.find_all(['ul', 'ol', 'li']):
        if not tag.contents or all(isinstance(c, NavigableString) and not c.strip() for c in tag.contents):
            tag.decompose()
    # Append new blocks to soup
    for block in new_blocks:
        soup.append(block)
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

def safe_filename(name):
    # Only allow alphanumeric, space, dash, and underscore
    return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()

def save_content(html_content, text_content, page_name):
    """Save extracted content to files"""
    if not os.path.exists('output'):
        os.makedirs('output')
    clean_name = safe_filename(page_name)
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

    # Remove empty <ul> and <li> elements
    for ul in soup.find_all('ul'):
        if not ul.find('li'):
            ul.decompose()
    for li in soup.find_all('li'):
        if not li.get_text(strip=True) and not li.find(['ul', 'ol']):
            li.decompose()

    blocks = []

    # Always process all top-level elements, including <ul> and <ol>
    elements = [el for el in soup.contents if not (isinstance(el, NavigableString) and not el.strip())]

    # DEBUG: Print first 5 top-level elements for any HTML processed
    print("\n[DEBUG] Top-level elements in html_to_notion_blocks:")
    for i, el in enumerate(elements[:5]):
        if isinstance(el, Tag):
            print(f"  [{i}] <{el.name}>: {str(el)[:80]}...")
        elif isinstance(el, NavigableString):
            print(f"  [{i}] NavigableString: {repr(str(el)[:80])}")

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
                if tag == "a" and child.has_attr('href'):
                    text = child.get_text()
                    if text:
                        rich_text.append({
                            "type": "text",
                            "text": {"content": text, "link": {"url": child['href']}},
                            "annotations": annotations
                        })
                else:
                    # Recursively parse all children (including nested <a> tags)
                    rich_text.extend(parse_rich_text(child, annotations))
        return rich_text

    def parse_list(ul):
        items = []
        for li in ul.find_all('li', recursive=False):
            if not li.get_text(strip=True) and not li.find(['ul', 'ol']):
                continue
            main_content = []
            nested_lists = []
            for child in li.contents:
                if isinstance(child, Tag) and child.name in ['ul', 'ol']:
                    nested_lists.append(child)
                else:
                    main_content.append(child)
            li_for_rich = Tag(name='span')
            for c in main_content:
                li_for_rich.append(c)
            rich_text = parse_rich_text(li_for_rich)
            if not rich_text:
                text = li_for_rich.get_text(strip=True)
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
            children = []
            for nested in nested_lists:
                if nested.name == 'ul':
                    children.extend(parse_list(nested))
                elif nested.name == 'ol':
                    children.extend(parse_ordered_list(nested))
            if children:
                block["bulleted_list_item"]["children"] = children
            items.append(block)
        return items

    def parse_ordered_list(ol):
        items = []
        for li in ol.find_all('li', recursive=False):
            if not li.get_text(strip=True) and not li.find(['ul', 'ol']):
                continue
            main_content = []
            nested_lists = []
            for child in li.contents:
                if isinstance(child, Tag) and child.name in ['ul', 'ol']:
                    nested_lists.append(child)
                else:
                    main_content.append(child)
            li_for_rich = Tag(name='span')
            for c in main_content:
                li_for_rich.append(c)
            rich_text = parse_rich_text(li_for_rich)
            if not rich_text:
                text = li_for_rich.get_text(strip=True)
                if text:
                    rich_text = [{
                        "type": "text",
                        "text": {"content": text},
                        "annotations": {"bold": False, "italic": False, "underline": False, "strikethrough": False, "code": False, "color": "default"}
                    }]
            block = {
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": rich_text
                }
            }
            children = []
            for nested in nested_lists:
                if nested.name == 'ul':
                    children.extend(parse_list(nested))
                elif nested.name == 'ol':
                    children.extend(parse_ordered_list(nested))
            if children:
                block["numbered_list_item"]["children"] = children
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
        elif tag == 'ol':
            blocks += parse_ordered_list(el)
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

    while blocks and blocks[0]["type"] == "paragraph" and (not blocks[0]["paragraph"]["rich_text"] or all(rt["type"] == "text" and not rt["text"]["content"].strip() for rt in blocks[0]["paragraph"]["rich_text"])):
        blocks.pop(0)

    return blocks

def create_notion_page(title, html):
    blocks = html_to_notion_blocks(html)
    # Debug: Print the Notion API payload for Lagoon only
    if title.strip().lower() == 'lagoon':
        import json
        payload = {
            "parent": {"page_id": NOTION_PARENT_PAGE_ID},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": title}}]}
            },
            "children": blocks[:100]
        }
        print("\n[DEBUG] Notion API payload for Lagoon:")
        print(json.dumps(payload, indent=2))
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

    start_from = "Client Meeting Notes"
    start_index = None

    # Debug print: show all page names and indices
    print("\n[DEBUG] List of all pages:")
    for idx, page in enumerate(pages):
        page_name = page.get('name', 'unnamed_page')
        marker = "<-- START HERE" if normalize(page_name) == normalize(start_from) else ""
        print(f"  [{idx}] {page_name} {marker}")
    print()

    # Find the index of the start page
    for idx, page in enumerate(pages):
        page_name = page.get('name', 'unnamed_page')
        if normalize(page_name) == normalize(start_from):
            start_index = idx
            break

    if start_index is None:
        print(f"[ERROR] Start page '{start_from}' not found!")
        sys.exit(1)

    # Process all pages after the start page
    pages_to_process = pages[start_index + 1:]

    driver = setup_driver()
    try:
        output_dir = 'output'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        for page in pages_to_process:
            page_name = page.get('name', 'unnamed_page')
            if normalize(page_name) != normalize('Lagoon'):
                continue  # Only process Lagoon
            safe_name = safe_filename(page_name)
            print(f"[INFO] Processing page: {page_name}")
            page_url = page.get('browserLink', '')
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
                    continue
                # Save raw HTML for inspection
                with open(f'{output_dir}/{safe_name}_raw.html', 'w', encoding='utf-8') as f:
                    f.write(raw_html)
                # --- Improved bullet/numbered list detection ---
                soup = BeautifulSoup(raw_html, 'html.parser')
                clean_html = convert_coda_bullets_to_lists(str(soup))
                clean_html = postprocess_coda_lists(clean_html)
                clean_text = soup.get_text(separator='\n', strip=True)
                if clean_html and clean_text:
                    save_content(clean_html, clean_text, safe_name)
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
    # --- TEST HARNESS FOR postprocess_coda_lists ---
    test_raw_path = 'output/Lagoon_raw.html'
    test_out_path = 'output/Lagoon_test_processed.html'
    import os
    if os.path.exists(test_raw_path):
        with open(test_raw_path, 'r', encoding='utf-8') as f:
            raw_html = f.read()
        processed_html = postprocess_coda_lists(raw_html)
        with open(test_out_path, 'w', encoding='utf-8') as f:
            f.write(processed_html)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(processed_html, 'html.parser')
        kr_lines = soup.find_all('div', class_=lambda c: c and 'kr-line' in c)
        num_kr_lines = len(kr_lines)
        num_ul = len(soup.find_all('ul'))
        num_ol = len(soup.find_all('ol'))
        num_a = len(soup.find_all('a'))
        print(f"[INFO] TEST HARNESS: kr-line divs in processed: {num_kr_lines}, <ul>: {num_ul}, <ol>: {num_ol}, <a>: {num_a}")
        print(f"[INFO] TEST HARNESS: Output written to {test_out_path}")
    # TEST HARNESS: Minimal nested list and link
    test_html = '''<ul><li>Parent item <a href="https://example.com">Example</a><ul><li>Child item <a href="https://child.com">ChildLink</a></li></ul></li></ul>'''
    print("\n[TEST HARNESS] Minimal nested list and link HTML:")
    print(test_html)
    blocks = html_to_notion_blocks(test_html)
    import json
    print("\n[TEST HARNESS] Notion blocks for minimal nested list and link:")
    print(json.dumps(blocks, indent=2))