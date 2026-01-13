#!/usr/bin/env python3
"""Check if a specific Coda page has been modified and needs re-migration"""
import os
import sys
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import hashlib
import time

load_dotenv()

# Import coda-download functions
sys.path.insert(0, '.')
import importlib.util
spec = importlib.util.spec_from_file_location("coda_download", "coda-download.py")
coda_download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coda_download)

NOTION_API_TOKEN = os.getenv('NOTION_API_TOKEN')
NOTION_PARENT_PAGE_ID = '2c3636dd-0ba5-807e-b374-c07a0134e636'

notion_headers = {
    'Authorization': f'Bearer {NOTION_API_TOKEN}',
    'Notion-Version': '2022-06-28',
}

def get_page_content_hash(driver, url):
    """Extract content from Coda page and return hash"""
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]'))
        )
        time.sleep(2)
        
        # Get HTML content
        html_content = driver.execute_script('''
        let contentElements = document.querySelectorAll('[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]');
        for (let element of contentElements) {
            if (element.offsetWidth > 0 && element.offsetHeight > 0) {
                return element.innerText;
            }
        }
        return null;
        ''')
        
        if html_content:
            # Create hash of content
            content_hash = hashlib.md5(html_content.encode('utf-8')).hexdigest()
            return content_hash, html_content[:200]  # Return hash and preview
        return None, None
    except Exception as e:
        print(f"Error extracting content: {e}")
        return None, None

def get_notion_content_hash(page_id):
    """Get content from Notion page and return hash"""
    try:
        url = f'https://api.notion.com/v1/blocks/{page_id}/children'
        response = requests.get(url, headers=notion_headers)
        if not response.ok:
            return None, None
        
        blocks = response.json().get('results', [])
        # Extract text content from blocks
        text_content = []
        for block in blocks[:50]:  # Check first 50 blocks
            block_type = block.get('type')
            if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item']:
                rich_text = block.get(block_type, {}).get('rich_text', [])
                for text in rich_text:
                    text_content.append(text.get('plain_text', ''))
        
        content = '\n'.join(text_content)
        if content:
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            return content_hash, content[:200]  # Return hash and preview
        return None, None
    except Exception as e:
        print(f"Error getting Notion content: {e}")
        return None, None

def main():
    page_name = "FalconX"
    
    print("=" * 60)
    print(f"CHECKING FOR CHANGES IN '{page_name}' PAGE")
    print("=" * 60)
    print()
    
    # Find page in Coda
    print(f"Searching for '{page_name}' in Coda...")
    coda_pages = coda_download.fetch_all_pages_flat()
    
    coda_page = None
    for page in coda_pages:
        if page_name.lower() in page.get('name', '').lower():
            coda_page = page
            break
    
    if not coda_page:
        print(f"❌ Page '{page_name}' not found in Coda")
        return
    
    print(f"✅ Found in Coda: {coda_page.get('name')}")
    print(f"   Updated: {coda_page.get('updatedAt', 'N/A')}")
    print(f"   URL: {coda_page.get('browserLink', 'N/A')}")
    
    # Find page in Notion
    print(f"\nSearching for '{page_name}' in Notion...")
    notion_pages = []
    url = f'https://api.notion.com/v1/blocks/{NOTION_PARENT_PAGE_ID}/children'
    while url:
        response = requests.get(url, headers=notion_headers)
        if not response.ok:
            break
        data = response.json()
        pages = [r for r in data.get('results', []) if r.get('type') == 'child_page']
        notion_pages.extend(pages)
        
        if data.get('has_more'):
            next_cursor = data.get('next_cursor')
            if next_cursor:
                url = f'https://api.notion.com/v1/blocks/{NOTION_PARENT_PAGE_ID}/children?start_cursor={next_cursor}'
            else:
                url = None
        else:
            url = None
    
    notion_page = None
    notion_title, _ = coda_download.extract_title_and_date(coda_page.get('name', ''))
    
    # Search for exact match or variations
    for page in notion_pages:
        title = page.get('child_page', {}).get('title', '')
        if coda_download.normalize(title) == coda_download.normalize(notion_title):
            notion_page = page
            break
    
    # If not found, search for any page with "falcon" in name
    if not notion_page:
        print(f"⚠ Page '{notion_title}' not found with exact match")
        print("   Searching for variations...")
        for page in notion_pages:
            title = page.get('child_page', {}).get('title', '')
            if 'falcon' in title.lower():
                print(f"   Found similar: '{title}'")
                notion_page = page
                break
    
    if not notion_page:
        print(f"❌ Page '{notion_title}' not found in Notion")
        print("   This page needs to be migrated!")
        return
    
    print(f"✅ Found in Notion: {notion_page.get('child_page', {}).get('title', 'Untitled')}")
    print(f"   ID: {notion_page.get('id')}")
    
    # Compare content
    print("\n" + "=" * 60)
    print("COMPARING CONTENT")
    print("=" * 60)
    print("\nExtracting content from Coda...")
    
    # Setup Selenium
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        coda_hash, coda_preview = get_page_content_hash(driver, coda_page.get('browserLink', ''))
        if coda_hash:
            print(f"✅ Coda content hash: {coda_hash[:16]}...")
            print(f"   Preview: {coda_preview[:100]}...")
        else:
            print("❌ Could not extract Coda content")
            return
    finally:
        driver.quit()
    
    print("\nExtracting content from Notion...")
    notion_hash, notion_preview = get_notion_content_hash(notion_page.get('id'))
    if notion_hash:
        print(f"✅ Notion content hash: {notion_hash[:16]}...")
        print(f"   Preview: {notion_preview[:100]}...")
    else:
        print("❌ Could not extract Notion content")
        return
    
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    
    if coda_hash == notion_hash:
        print("✅ Content matches - page is up to date!")
        print("   No changes detected in Coda")
    else:
        print("⚠ CONTENT DIFFERS - page has been modified in Coda!")
        print("   The Coda page needs to be re-migrated to Notion")
        print()
        print("To update the Notion page:")
        print("1. Archive the existing Notion page")
        print("2. Run: python3 coda-download.py")
        print("   (It will recreate the page with updated content)")

if __name__ == "__main__":
    main()

