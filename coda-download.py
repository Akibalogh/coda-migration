import requests
import json
import unicodedata
from bs4 import BeautifulSoup
import time
import sys
import os
import argparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import re
import hashlib
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from queue import Queue

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
NOTION_PARENT_PAGE_ID = '2c3636dd-0ba5-807e-b374-c07a0134e636'  # Coda migrations test page

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

def setup_driver(max_retries=5):
    """Setup Chrome driver with appropriate options and retry logic"""
    import tempfile
    import shutil
    import random
    from selenium.common.exceptions import SessionNotCreatedException
    
    # Use a random port to avoid conflicts
    debug_port = random.randint(9223, 9999)
    
    for attempt in range(max_retries):
        try:
            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument(f"--remote-debugging-port={debug_port}")
            
            # Use a temporary profile directory to avoid lock conflicts
            temp_profile = tempfile.mkdtemp(prefix="selenium-chrome-")
            options.add_argument(f"--user-data-dir={temp_profile}")
            
            # Use webdriver-manager to automatically handle ChromeDriver version
            try:
                from selenium.webdriver.chrome.service import Service
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            except ImportError:
                # Fallback if webdriver-manager not available
                driver = webdriver.Chrome(options=options)
            
            # Store temp profile path for cleanup
            driver._temp_profile = temp_profile
            return driver
            
        except SessionNotCreatedException as e:
            # Clean up any leftover Chrome processes before retrying
            if attempt < max_retries - 1:
                print(f"[WARNING] Selenium session creation failed (attempt {attempt + 1}/{max_retries}): {str(e)[:100]}")
                print(f"[INFO] Retrying with new port...")
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s, 8s
                debug_port = random.randint(9223, 9999)  # Use a new random port
            else:
                print(f"[ERROR] Failed to create Selenium session after {max_retries} attempts")
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[WARNING] Driver setup failed (attempt {attempt + 1}/{max_retries}): {str(e)[:100]}")
                print(f"[INFO] Retrying...")
                time.sleep(2 ** attempt)
                debug_port = random.randint(9223, 9999)
            else:
                print(f"[ERROR] Failed to setup driver after {max_retries} attempts: {str(e)}")
                raise
    
    raise Exception("Failed to setup driver after all retries")

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
                # Preserve formatting tags: strong, b, em, i, u, s, strike, code
                if child.name in ['strong', 'b', 'em', 'i', 'u', 's', 'strike', 'code']:
                    result.append(child)
                    continue
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
                # Otherwise, recurse to preserve nested formatting
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
                # Append content directly - BeautifulSoup will handle moving tags
                # between soups. Extract first to ensure it's not lost when div
                # is decomposed later.
                if isinstance(content, Tag):
                    # Extract the tag from its current location before appending
                    # This ensures it won't be lost when we decompose the original div
                    extracted = content.extract() if content.parent else content
                    li.append(extracted)
                else:
                    # For NavigableString, append directly
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
    print(f"[DEBUG] extract_content called for URL: {url[:50]}...")
    try:
        driver.get(url)
        print(f"[DEBUG] Page loaded, waiting for content...")
        WebDriverWait(driver, 15).until(  # Reduced from 20 to 15 seconds
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]'))
        )
        time.sleep(1)  # Reduced from 2 to 1 second
        js = '''
        // Function to recursively process elements and add formatting tags
        function processNode(node) {
            if (node.nodeType === Node.TEXT_NODE) {
                if (!node.textContent || !node.textContent.trim()) {
                    return null;
                }
                const parent = node.parentElement;
                if (!parent) return node.cloneNode();
                
                const style = window.getComputedStyle(parent);
                const fontWeight = style.fontWeight;
                const fontStyle = style.fontStyle;
                const textDecoration = style.textDecoration || '';
                
                const fontWeightNum = parseInt(fontWeight) || 400;
                const isBold = fontWeightNum >= 600 || fontWeight === 'bold' || fontWeight === 'bolder';
                const isItalic = fontStyle === 'italic';
                const isUnderline = textDecoration.indexOf('underline') !== -1;
                const isStrikethrough = textDecoration.indexOf('line-through') !== -1;
                
                if (isBold || isItalic || isUnderline || isStrikethrough) {
                    let wrapper = document.createTextNode(node.textContent);
                    
                    if (isStrikethrough) {
                        const s = document.createElement('s');
                        s.appendChild(wrapper);
                        wrapper = s;
                    }
                    if (isUnderline) {
                        const u = document.createElement('u');
                        u.appendChild(wrapper);
                        wrapper = u;
                    }
                    if (isItalic) {
                        const em = document.createElement('em');
                        em.appendChild(wrapper);
                        wrapper = em;
                    }
                    if (isBold) {
                        const strong = document.createElement('strong');
                        strong.appendChild(wrapper);
                        wrapper = strong;
                    }
                    return wrapper;
                }
                return node.cloneNode();
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                // Skip script and style elements
                if (node.tagName === 'SCRIPT' || node.tagName === 'STYLE') {
                    return null;
                }
                
                const clone = node.cloneNode(false); // Shallow clone
                
                // Process all children
                for (let i = 0; i < node.childNodes.length; i++) {
                    const childResult = processNode(node.childNodes[i]);
                    if (childResult) {
                        clone.appendChild(childResult);
                    }
                }
                return clone;
            }
            return node.cloneNode();
        }
        
        let contentElements = document.querySelectorAll('[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]');
        for (let element of contentElements) {
            if (element.offsetWidth > 0 && element.offsetHeight > 0) {
                const processed = processNode(element);
                return processed ? processed.innerHTML : null;
            }
        }
        return null;
        '''
        html_content = driver.execute_script(js)
        if not html_content:
            print("[ERROR] JavaScript returned no HTML content - falling back to innerHTML")
            # Fallback: get innerHTML directly
            html_content = driver.execute_script('''
            let contentElements = document.querySelectorAll('[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]');
            for (let element of contentElements) {
                if (element.offsetWidth > 0 && element.offsetHeight > 0) {
                    return element.innerHTML;
                }
            }
            return null;
            ''')
            if not html_content:
                return None, None
        
        # Debug: Check raw HTML from JavaScript for bold tags
        if html_content:
            test_soup = BeautifulSoup(html_content, 'html.parser')
            test_bold = len(test_soup.find_all(['strong', 'b']))
            print(f"[DEBUG] Raw HTML from JS: {len(html_content)} chars, {test_bold} bold tags")
            if test_bold == 0:
                print("[DEBUG] No bold tags found in raw HTML - JavaScript formatting detection may have failed")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        clean_html = str(soup)
        
        # Check before postprocess
        debug_soup = BeautifulSoup(clean_html, 'html.parser')
        bold_before = len(debug_soup.find_all(['strong', 'b']))
        print(f"[DEBUG] Before postprocess: {bold_before} bold tags")
        
        clean_html = postprocess_coda_lists(clean_html)
        
        # Check after postprocess
        debug_soup2 = BeautifulSoup(clean_html, 'html.parser')
        bold_after = len(debug_soup2.find_all(['strong', 'b']))
        print(f"[DEBUG] After postprocess: {bold_after} bold tags")
        
        if bold_before > 0 and bold_after == 0:
            print(f"[ERROR] postprocess_coda_lists stripped all {bold_before} bold tags!")
        elif bold_after < bold_before:
            print(f"[WARNING] Lost {bold_before - bold_after} bold tags in postprocess")
        clean_text = soup.get_text(separator='\n', strip=True)
        return clean_html, clean_text
    except Exception as e:
        print(f"[ERROR] Exception in extract_content: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
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

def calculate_content_hash(html):
    """Calculate MD5 hash of content for change detection, including formatting"""
    # Normalize HTML by removing whitespace differences
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    # Get text content
    text_content = soup.get_text(separator='\n', strip=True)
    # Include formatting tags (strong, em, u, s, code, a) in structure
    # This ensures formatting changes are detected
    formatting_info = []
    for tag in soup.find_all(['strong', 'b', 'em', 'i', 'u', 's', 'strike', 'code', 'a']):
        tag_info = f"{tag.name}:{tag.get_text(strip=True)}"
        if tag.name == 'a' and tag.get('href'):
            tag_info += f":{tag['href']}"
        formatting_info.append(tag_info)
    # Combine text, structure, and formatting
    structure = ''.join([tag.name for tag in soup.find_all() if tag.name])
    formatting_str = '|'.join(formatting_info)
    combined = f"{text_content}|{structure}|{formatting_str}"
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def get_notion_page_content_hash(page_id):
    """Get content hash from existing Notion page, including formatting annotations"""
    try:
        url = f'https://api.notion.com/v1/blocks/{page_id}/children'
        r = requests.get(url, headers=notion_headers)
        if not r.ok:
            return None
        
        blocks = r.json().get('results', [])
        # Extract text content AND formatting annotations from blocks
        content_parts = []
        for block in blocks[:100]:  # Check first 100 blocks
            block_type = block.get('type')
            if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 
                            'bulleted_list_item', 'numbered_list_item']:
                rich_text = block.get(block_type, {}).get('rich_text', [])
                for text_obj in rich_text:
                    plain_text = text_obj.get('plain_text', '')
                    annotations = text_obj.get('annotations', {})
                    # Include formatting in hash: bold, italic, underline, strikethrough, code
                    formatting = ''.join([
                        'B' if annotations.get('bold') else '',
                        'I' if annotations.get('italic') else '',
                        'U' if annotations.get('underline') else '',
                        'S' if annotations.get('strikethrough') else '',
                        'C' if annotations.get('code') else '',
                    ])
                    # Include link if present
                    link = ''
                    if text_obj.get('text', {}).get('link'):
                        link = text_obj['text']['link'].get('url', '')
                    # Combine text + formatting + link
                    content_parts.append(f"{plain_text}|{formatting}|{link}")
        
        content = '\n'.join(content_parts)
        if content:
            return hashlib.md5(content.encode('utf-8')).hexdigest()
        return None
    except Exception as e:
        print(f"[WARNING] Error getting Notion page content: {e}")
        return None

# Cache for Notion pages to avoid repeated API calls
_notion_pages_cache = None

def get_all_notion_pages_cached():
    """Get all Notion pages and cache them. Returns dict of {normalized_title: (page_id, page_data)}"""
    global _notion_pages_cache
    if _notion_pages_cache is not None:
        return _notion_pages_cache
    
    _notion_pages_cache = {}
    try:
        url = f'https://api.notion.com/v1/blocks/{NOTION_PARENT_PAGE_ID}/children'
        while url:
            r = requests.get(url, headers=notion_headers, timeout=10)
            if not r.ok:
                break
            
            data = r.json()
            for result in data.get('results', []):
                if result.get('type') == 'child_page':
                    page_id = result.get('id')
                    page_url = f'https://api.notion.com/v1/pages/{page_id}'
                    page_resp = requests.get(page_url, headers=notion_headers, timeout=10)
                    if page_resp.ok:
                        page_data = page_resp.json()
                        page_title_prop = page_data.get('properties', {}).get('title', {})
                        if page_title_prop.get('title'):
                            page_title = page_title_prop['title'][0].get('plain_text', '')
                            normalized_title = normalize(page_title)
                            _notion_pages_cache[normalized_title] = (page_id, page_data)
            
            # Check pagination
            if data.get('has_more'):
                next_cursor = data.get('next_cursor')
                if next_cursor:
                    url = f'https://api.notion.com/v1/blocks/{NOTION_PARENT_PAGE_ID}/children?start_cursor={next_cursor}'
                else:
                    url = None
            else:
                url = None
    except Exception as e:
        print(f"[WARNING] Error fetching Notion pages cache: {e}")
    
    return _notion_pages_cache

def check_page_exists_and_content(title, new_content_hash):
    """Check if page exists and compare content hash. Returns (exists, page_id, content_changed)"""
    try:
        # Use cached page list for much faster lookup
        notion_pages = get_all_notion_pages_cached()
        normalized_title = normalize(title)
        
        if normalized_title in notion_pages:
            page_id, page_data = notion_pages[normalized_title]
            # Found matching page, check content
            existing_hash = get_notion_page_content_hash(page_id)
            if existing_hash and new_content_hash:
                content_changed = (existing_hash != new_content_hash)
                return True, page_id, content_changed
            # If we can't get hash, assume it exists (conservative)
            return True, page_id, False
        
        return False, None, False
    except Exception as e:
        print(f"[WARNING] Error checking for existing page: {e}")
    return False, None, False

def archive_notion_page(page_id):
    """Archive (delete) a Notion page"""
    try:
        url = f'https://api.notion.com/v1/pages/{page_id}'
        data = {"archived": True}
        r = requests.patch(url, headers=notion_headers, json=data)
        return r.ok
    except Exception as e:
        print(f"[WARNING] Error archiving page: {e}")
        return False

def create_notion_page(title, html, dry_run=False):
    blocks = html_to_notion_blocks(html)
    
    # Calculate content hash for change detection
    content_hash = calculate_content_hash(html)
    
    # Check for existing page and content changes
    if not dry_run:
        exists, page_id, content_changed = check_page_exists_and_content(title, content_hash)
        if exists:
            if content_changed:
                print(f"[UPDATE] Page '{title}' exists but content has changed - archiving old version")
                if archive_notion_page(page_id):
                    print(f"[UPDATE] Archived old page, will create updated version")
                else:
                    print(f"[WARNING] Failed to archive old page, skipping update")
                    return None
            else:
                print(f"[SKIP] Page '{title}' already exists with same content, skipping")
                return None
    
    if dry_run:
        print(f"\n[DRY RUN] Would create Notion page: {title}")
        print(f"[DRY RUN] Total blocks: {len(blocks)}")
        print(f"[DRY RUN] Would create page with {len(blocks[:100])} blocks in initial request")
        if len(blocks) > 100:
            print(f"[DRY RUN] Would append {len(blocks) - 100} additional blocks in chunks")
        
        # Show sample of blocks for first page
        if blocks:
            print("\n[DRY RUN] Sample block structure:")
            sample = blocks[0] if blocks else {}
            sample_json = json.dumps(sample, indent=2)
            if len(sample_json) > 500:
                print(sample_json[:500] + "...")
            else:
                print(sample_json)
        return
    
    # Debug: Print the Notion API payload for Lagoon only
    if title.strip().lower() == 'lagoon':
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
        return None
    page_id = r.json().get("id")
    # Append remaining blocks in chunks of 100
    append_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    while remaining:
        chunk = remaining[:100]
        remaining = remaining[100:]
        append_payload = {"children": chunk}
        r = requests.patch(append_url, headers=notion_headers, json=append_payload)
        if not r.ok:
            print("[ERROR] Notion API failed on chunk append:")
            print("Status Code:", r.status_code)
            print("Response:", r.text)
            return None
    
    return page_id

def extract_title_and_date(page_name):
    # Match patterns like 'Title 10/20/21' or 'Title - 10/20/21'
    match = re.match(r"^(.*?)(?:\s*-)?\s*(\d{1,2}/\d{1,2}/\d{2,4})$", page_name)
    if match:
        title = match.group(1).strip()
        date = match.group(2)
        return title, date
    return page_name, None

def main():
    parser = argparse.ArgumentParser(description='Migrate Coda pages to Notion')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview migration without creating Notion pages')
    args = parser.parse_args()
    
    if args.dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No pages will be created in Notion")
        print("=" * 60)
    
    pages = fetch_all_pages_flat()
    if not pages:
        print("[ERROR] No pages found!")
        sys.exit(1)

    # Find "Protego" page as starting point and "ARKN" as end point
    # These are in the Sales Notes section
    start_from = "Protego"
    end_at = "ARKN"
    start_index = None
    end_index = None

    # Find the indices of start and end pages
    # Note: Coda API may return pages in different order than document view
    # So we search for both by name
    for idx, page in enumerate(pages):
        page_name = page.get('name', 'unnamed_page')
        page_id = page.get('id', '')
        
        # Check by name (normalized)
        if normalize(page_name) == normalize(start_from):
            start_index = idx
            print(f"[INFO] Found start page '{start_from}' at index {idx} (ID: {page_id})")
        
        # Check for ARKN - try exact match first, then partial
        if normalize(page_name) == normalize(end_at):
            end_index = idx
            print(f"[INFO] Found end page '{end_at}' at index {idx} (ID: {page_id})")
        elif 'arkn' in normalize(page_name) and end_index is None:
            # Try to find ARKN by partial match
            end_index = idx
            print(f"[INFO] Found potential end page '{page_name}' at index {idx} (searching for '{end_at}')")

    if start_index is None:
        print(f"[ERROR] Start page '{start_from}' not found!")
        print(f"[INFO] Available pages (first 20):")
        for idx, page in enumerate(pages[:20], 1):
            print(f"  {idx}. {page.get('name', 'unnamed')}")
        sys.exit(1)
    
    if end_index is None:
        print(f"[WARNING] End page '{end_at}' not found!")
        print(f"[INFO] Will process from '{start_from}' to end of list")
        pages_to_process = pages[start_index:]
    elif end_index < start_index:
        print(f"[WARNING] End page '{end_at}' (index {end_index}) comes before start page '{start_from}' (index {start_index})")
        print(f"[INFO] This suggests pages are not in document order. Processing from '{start_from}' to end.")
        pages_to_process = pages[start_index:]
    else:
        # Process pages from Protego to ARKN (inclusive)
        pages_to_process = pages[start_index:end_index+1]
        print(f"[INFO] Processing pages from '{start_from}' to '{end_at}' (inclusive)")
        print(f"[INFO] Found {len(pages_to_process)} pages in Sales Notes section")
    
    print(f"\n[INFO] Will process {len(pages_to_process)} pages:")
    for idx, page in enumerate(pages_to_process[:10], 1):
        print(f"  {idx}. {page.get('name', 'unnamed_page')}")
    if len(pages_to_process) > 10:
        print(f"  ... and {len(pages_to_process) - 10} more")

    # Pre-load Notion pages cache for faster lookups
    print("\n[INFO] Loading Notion pages cache...")
    notion_cache = get_all_notion_pages_cached()
    print(f"[INFO] Cached {len(notion_cache)} existing Notion pages for fast lookup")
    
    # Thread-safe counter and lock
    processed_count = 0
    processed_lock = threading.Lock()
    
    def process_page(page):
        """Process a single page - runs in its own thread with its own driver"""
        nonlocal processed_count
        page_name = page.get('name', 'unnamed_page')
        safe_name = safe_filename(page_name)
        page_url = page.get('browserLink', '')
        
        # Each thread gets its own driver instance
        driver = None
        try:
            print(f"[INFO] Processing page: {page_name}")
            driver = setup_driver()
            
            driver.get(page_url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]'))
            )
            time.sleep(1)
            
            # Use extract_content function which includes formatting detection
            raw_html, clean_text = extract_content(driver, page_url)
            if not raw_html:
                print(f"[ERROR] No HTML extracted for {page_name} at {page_url}")
                return False
            
            # raw_html already processed by extract_content with formatting detection
            clean_html = raw_html
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
                
                create_notion_page(notion_title, clean_html, dry_run=args.dry_run)
                if args.dry_run:
                    print(f"[DRY RUN] ✓ Would create Notion page: {notion_title}")
                else:
                    print(f"[✓] Notion page created: {notion_title}")
                    with processed_lock:
                        processed_count += 1
                return True
            else:
                print(f"[ERROR] No content extracted for {page_name}")
                return False
        except Exception as e:
            print(f"[ERROR] Exception during extraction for {page_name} at {page_url}: {e}")
            return False
        finally:
            if driver:
                driver.quit()
                # Clean up temporary profile directory if it exists
                import shutil
                if hasattr(driver, '_temp_profile'):
                    try:
                        shutil.rmtree(driver._temp_profile, ignore_errors=True)
                    except:
                        pass
    
    # Use concurrent processing with thread pool
    output_dir = 'output'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Determine number of workers (concurrent pages to process)
    # Use 3-5 workers to balance speed vs resource usage
    max_workers = min(5, len(pages_to_process))
    print(f"\n[INFO] Using {max_workers} concurrent workers for faster processing")
    print(f"[INFO] Processing {len(pages_to_process)} pages...\n")
    
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all pages to the thread pool
            future_to_page = {executor.submit(process_page, page): page for page in pages_to_process}
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_page):
                page = future_to_page[future]
                try:
                    result = future.result()
                except Exception as e:
                    page_name = page.get('name', 'unnamed_page')
                    print(f"[ERROR] Page {page_name} generated an exception: {e}")
        
        if not args.dry_run:
            print(f"\n[✓] Migration complete! Processed {processed_count} page(s).")
    except KeyboardInterrupt:
        print("\n[INFO] Migration interrupted by user")
        sys.exit(1)

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