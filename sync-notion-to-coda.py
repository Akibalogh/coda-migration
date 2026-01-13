#!/usr/bin/env python3
"""
Sync Notion pages to match current Coda pages.

This script will:
1. Fetch all current pages from Coda
2. Fetch all pages from Notion
3. Delete pages from Notion that don't exist in Coda
4. Handle renames (pages that exist in both but with different names)
5. Report what was deleted and renamed
"""
import requests
import os
from dotenv import load_dotenv
import unicodedata
import time

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
    """Fetch all current pages from Coda"""
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

def archive_notion_page(page_id):
    """Archive (delete) a Notion page"""
    try:
        url = f'https://api.notion.com/v1/pages/{page_id}'
        data = {"archived": True}
        r = requests.patch(url, headers=notion_headers, json=data)
        return r.ok
    except Exception as e:
        print(f"[WARNING] Error archiving page {page_id}: {e}")
        return False

def main():
    print("=" * 60)
    print("SYNC NOTION TO CODA")
    print("=" * 60)
    print()
    print("This will:")
    print("  1. Delete pages from Notion that don't exist in Coda")
    print("  2. Report any potential renames")
    print()
    
    # Confirm before proceeding
    response = input("Continue? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Cancelled.")
        return
    
    print()
    print("[INFO] Fetching all current Coda pages...")
    coda_pages = get_all_coda_pages()
    print(f"[INFO] Found {len(coda_pages)} pages in Coda")
    print()
    
    print("[INFO] Fetching all Notion pages...")
    notion_pages = get_all_notion_pages()
    print(f"[INFO] Found {len(notion_pages)} pages in Notion")
    print()
    
    # Create normalized title maps
    coda_titles = {normalize(p.get('name', '')): p.get('name', '') for p in coda_pages}
    notion_pages_map = {normalize(p['title']): p for p in notion_pages}
    
    # Find pages to delete (in Notion but not in Coda)
    pages_to_delete = []
    for notion_title_norm, notion_page in notion_pages_map.items():
        if notion_title_norm not in coda_titles:
            pages_to_delete.append(notion_page)
    
    # Find potential renames (same normalized name but different actual name)
    # This is tricky - we'll just note pages that exist in both
    pages_in_both = []
    for coda_title_norm, coda_title in coda_titles.items():
        if coda_title_norm in notion_pages_map:
            notion_title = notion_pages_map[coda_title_norm]['title']
            if coda_title != notion_title:
                pages_in_both.append({
                    'coda': coda_title,
                    'notion': notion_title,
                    'notion_id': notion_pages_map[coda_title_norm]['id']
                })
    
    # Report findings
    print("=" * 60)
    print("SYNC ANALYSIS")
    print("=" * 60)
    print()
    print(f"📊 Current Coda pages: {len(coda_pages)}")
    print(f"📊 Current Notion pages: {len(notion_pages)}")
    print()
    
    if pages_to_delete:
        print(f"🗑️  Pages to delete from Notion: {len(pages_to_delete)}")
        for i, page in enumerate(pages_to_delete[:20], 1):
            print(f"   {i}. {page['title']}")
        if len(pages_to_delete) > 20:
            print(f"   ... and {len(pages_to_delete) - 20} more")
        print()
    else:
        print("✅ No pages to delete")
        print()
    
    if pages_in_both:
        print(f"📝 Potential renames detected: {len(pages_in_both)}")
        print("   (These pages exist in both but with different casing/spacing)")
        for item in pages_in_both[:10]:
            print(f"   Coda: '{item['coda']}' → Notion: '{item['notion']}'")
        if len(pages_in_both) > 10:
            print(f"   ... and {len(pages_in_both) - 10} more")
        print()
    
    # Confirm deletion
    if pages_to_delete:
        print("=" * 60)
        print(f"⚠️  WARNING: About to delete {len(pages_to_delete)} pages from Notion")
        print("=" * 60)
        response = input("Proceed with deletion? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Cancelled.")
            return
        
        print()
        print("[INFO] Archiving pages in Notion...")
        deleted_count = 0
        failed_count = 0
        
        for i, page in enumerate(pages_to_delete, 1):
            print(f"   [{i}/{len(pages_to_delete)}] Archiving: {page['title']}")
            if archive_notion_page(page['id']):
                deleted_count += 1
            else:
                failed_count += 1
                print(f"      ❌ Failed to archive")
            time.sleep(0.5)  # Rate limiting
        
        print()
        print("=" * 60)
        print("DELETION COMPLETE")
        print("=" * 60)
        print()
        print(f"✅ Successfully archived: {deleted_count} pages")
        if failed_count > 0:
            print(f"❌ Failed to archive: {failed_count} pages")
        print()
    else:
        print("✅ No pages to delete - Notion is already in sync")
        print()
    
    print("=" * 60)
    print("SYNC COMPLETE")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Run the migration script to ensure all current Coda pages are in Notion")
    print("  2. Verify completeness with verify-migration-complete.py")
    print()

if __name__ == "__main__":
    main()
