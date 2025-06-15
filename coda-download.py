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
    # Use a unique user data directory for Selenium
    options.add_argument("--user-data-dir=/Users/akibalogh/selenium-profile")
    options.add_argument("--profile-directory=Default")
    return webdriver.Chrome(options=options)

def extract_content(driver, url):
    """Extract formatted content from a Coda page using robust selectors and JS."""
    try:
        print(f"[DEBUG] Navigating to URL: {url}")
        driver.get(url)
        print("[DEBUG] Waiting for Coda main content...")
        # Wait for any of the main content containers
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]'))
        )
        time.sleep(2)  # Let dynamic content load
        # Find the first visible main content container
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
            print("[ERROR] Could not find visible Coda content container.")
            return None, None
        # Clean and parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        clean_html = str(soup)
        clean_text = soup.get_text(separator='\n', strip=True)
        return clean_html, clean_text
    except Exception as e:
        print(f"[ERROR] Failed to extract content: {str(e)}")
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
            else:
                print(f"[WARN] No content extracted for {page_name}")
            time.sleep(2)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
