#!/usr/bin/env python3
"""
Verify that all current Coda pages have been migrated to Notion.

Note: Extra pages in Notion (not in current Coda) are expected and not
reported as errors, since some pages may have been deleted from Coda.
"""
import requests
import os
from dotenv import load_dotenv
import unicodedata

load_dotenv()

CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
CODA_DOC_ID = '0eJEEjA-GU'
NOTION_API_TOKEN = os.getenv('NOTION_API_TOKEN')
NOTION_PARENT_PAGE_ID = '2c3636dd-0ba5-807e-b374-c07a0134e636'

coda_headers = {'Authorization': f'Bearer {CODA_API_TOKEN}'}
notion_headers = {
    'Authorization': f'Bearer {NOTION_API_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

def normalize(text):
    return unicodedata.normalize("NFKC", text.strip().lower())

def get_all_coda_pages():
    """Fetch all pages from Coda"""
    url = f'https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages'
    all_pages = []
    next_token = None
    
    while True:
        params = {'limit': 100}
        if next_token:
            params['pageToken'] = next_token
        
        resp = requests.get(url, headers=coda_headers, params=params)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to fetch Coda pages: {resp.status_code}")
            break
        
        data = resp.json()
        items = data.get('items', [])
        all_pages.extend(items)
        
        next_token = data.get('nextPageToken')
        if not next_token:
            break
    
    return all_pages

def get_all_notion_pages():
    """Fetch all child pages from Notion parent"""
    url = f'https://api.notion.com/v1/blocks/{NOTION_PARENT_PAGE_ID}/children'
    all_pages = []
    next_cursor = None
    
    while True:
        params = {}
        if next_cursor:
            params['start_cursor'] = next_cursor
        
        resp = requests.get(url, headers=notion_headers, params=params)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to fetch Notion pages: {resp.status_code}")
            break
        
        data = resp.json()
        results = data.get('results', [])
        
        # Get full page details for child_page blocks
        for result in results:
            if result.get('type') == 'child_page':
                page_id = result.get('id')
                page_url = f'https://api.notion.com/v1/pages/{page_id}'
                page_resp = requests.get(page_url, headers=notion_headers)
                if page_resp.ok:
                    page_data = page_resp.json()
                    page_title_prop = page_data.get('properties', {}).get('title', {})
                    if page_title_prop.get('title'):
                        page_title = page_title_prop['title'][0].get('plain_text', '')
                        all_pages.append({
                            'id': page_id,
                            'title': page_title
                        })
        
        next_cursor = data.get('next_cursor')
        if not next_cursor:
            break
    
    return all_pages

def main():
    print("=" * 60)
    print("MIGRATION COMPLETENESS VERIFICATION")
    print("=" * 60)
    print()
    
    print("[INFO] Fetching all Coda pages...")
    coda_pages = get_all_coda_pages()
    print(f"[INFO] Found {len(coda_pages)} pages in Coda")
    print()
    
    print("[INFO] Fetching all Notion pages...")
    notion_pages = get_all_notion_pages()
    print(f"[INFO] Found {len(notion_pages)} pages in Notion")
    print()
    
    # Create normalized title maps
    coda_titles = {normalize(p.get('name', '')): p.get('name', '') for p in coda_pages}
    notion_titles = {normalize(p['title']): p['title'] for p in notion_pages}
    
    # Find missing pages
    missing_in_notion = []
    for coda_title_norm, coda_title in coda_titles.items():
        if coda_title_norm not in notion_titles:
            missing_in_notion.append(coda_title)
    
    # Find extra pages in Notion (not in Coda)
    extra_in_notion = []
    for notion_title_norm, notion_title in notion_titles.items():
        if notion_title_norm not in coda_titles:
            extra_in_notion.append(notion_title)
    
    # Report results
    print("=" * 60)
    print("VERIFICATION RESULTS")
    print("=" * 60)
    print()
    print(f"📊 Current Coda pages: {len(coda_pages)}")
    print(f"📊 Total Notion pages: {len(notion_pages)}")
    print()
    print("ℹ️  Note: Extra pages in Notion (not in current Coda) are expected")
    print("   since some pages may have been deleted from Coda.")
    print()
    
    if not missing_in_notion:
        print("✅ SUCCESS: All current Coda pages have been migrated to Notion!")
    else:
        print(f"❌ WARNING: {len(missing_in_notion)} current Coda pages are missing in Notion:")
        for i, title in enumerate(missing_in_notion[:20], 1):
            print(f"   {i}. {title}")
        if len(missing_in_notion) > 20:
            print(f"   ... and {len(missing_in_notion) - 20} more")
        print()
    
    if extra_in_notion:
        print(f"ℹ️  INFO: {len(extra_in_notion)} pages in Notion are not in current Coda")
        print("   (These are expected - likely from deleted Coda pages)")
        if len(extra_in_notion) <= 10:
            for i, title in enumerate(extra_in_notion, 1):
                print(f"   {i}. {title}")
        print()
    
    # Calculate migration percentage (only for current Coda pages)
    if coda_pages:
        migrated_count = len(coda_pages) - len(missing_in_notion)
        migration_percentage = (migrated_count / len(coda_pages)) * 100
        print(f"📈 Migration Coverage: {migrated_count}/{len(coda_pages)} current Coda pages ({migration_percentage:.1f}%)")
        print()
    
    print("=" * 60)
    
    return len(missing_in_notion) == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
