#!/usr/bin/env python3
"""
Monitor the Sales Notes migration progress
"""
import os
import time
import sys
import requests
import importlib.util

# Import from coda-download
spec = importlib.util.spec_from_file_location("coda_download", "coda-download.py")
coda_download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coda_download)

# Read .env
coda_token = None
notion_token = None
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.startswith('CODA_API_TOKEN='):
                coda_token = line.split('=', 1)[1].strip()
            elif line.startswith('NOTION_API_TOKEN='):
                notion_token = line.split('=', 1)[1].strip()

CODA_DOC_ID = '0eJEEjA-GU'
NOTION_PARENT_PAGE_ID = '2c3636dd-0ba5-807e-b374-c07a0134e636'

def get_coda_sales_notes_pages():
    """Get all pages in Sales Notes section (Protego to ARKN)"""
    headers = {'Authorization': f'Bearer {coda_token}'}
    base_url = f'https://coda.io/apis/v1/docs/{CODA_DOC_ID}/pages'
    
    all_pages = []
    next_token = None
    
    while True:
        params = {}
        if next_token:
            params['pageToken'] = next_token
        
        resp = requests.get(base_url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            break
        
        data = resp.json()
        items = data.get('items', [])
        all_pages.extend(items)
        
        next_token = data.get('nextPageToken')
        if not next_token:
            break
    
    # Find Protego and ARKN
    protego_idx = None
    arkn_idx = None
    
    for i, page in enumerate(all_pages):
        name = page.get('name', '')
        if coda_download.normalize(name) == coda_download.normalize('Protego'):
            protego_idx = i
        if coda_download.normalize(name) == coda_download.normalize('ARKN'):
            arkn_idx = i
    
    if protego_idx is not None and arkn_idx is not None:
        return all_pages[protego_idx:arkn_idx+1]
    return []

def get_notion_pages():
    """Get all Notion pages"""
    notion_headers = {
        'Authorization': f'Bearer {notion_token}',
        'Notion-Version': '2022-06-28'
    }
    
    notion_pages = {}
    notion_url = f'https://api.notion.com/v1/blocks/{NOTION_PARENT_PAGE_ID}/children'
    
    while notion_url:
        resp = requests.get(notion_url, headers=notion_headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
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
                            notion_pages[coda_download.normalize(page_title)] = page_title
            
            next_cursor = data.get('next_cursor')
            notion_url = f'https://api.notion.com/v1/blocks/{NOTION_PARENT_PAGE_ID}/children?start_cursor={next_cursor}' if next_cursor else None
        else:
            break
    
    return notion_pages

def check_migration_status():
    """Check current migration status"""
    print("=" * 60)
    print("SALES NOTES MIGRATION STATUS")
    print("=" * 60)
    print()
    
    # Get Coda pages
    print("📥 Fetching Coda pages...")
    coda_pages = get_coda_sales_notes_pages()
    print(f"   Found {len(coda_pages)} pages in Sales Notes section")
    print()
    
    # Get Notion pages
    print("📥 Fetching Notion pages...")
    notion_pages = get_notion_pages()
    print(f"   Found {len(notion_pages)} pages in Notion")
    print()
    
    # Compare
    missing = []
    present = []
    
    for page in coda_pages:
        coda_name = page.get('name', '')
        notion_title, _ = coda_download.extract_title_and_date(coda_name)
        norm_title = coda_download.normalize(notion_title)
        
        if norm_title in notion_pages:
            present.append(coda_name)
        else:
            missing.append(coda_name)
    
    print("=" * 60)
    print("PROGRESS")
    print("=" * 60)
    print()
    print(f"✅ Migrated: {len(present)}/{len(coda_pages)} ({len(present)/len(coda_pages)*100:.1f}%)")
    print(f"❌ Remaining: {len(missing)}/{len(coda_pages)} ({len(missing)/len(coda_pages)*100:.1f}%)")
    print()
    
    if missing:
        print(f"📋 Remaining pages to migrate ({len(missing)}):")
        for i, name in enumerate(missing[:20], 1):
            print(f"  {i:3}. {name}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
    else:
        print("🎉 Migration complete! All pages migrated!")
    
    print()
    print("=" * 60)
    
    return len(missing)

def main():
    if not coda_token or not notion_token:
        print("⚠️  Error: Missing API tokens in .env file")
        sys.exit(1)
    
    # Check if migration is running
    if os.path.exists('migration.pid'):
        with open('migration.pid', 'r') as f:
            pid = f.read().strip()
        try:
            os.kill(int(pid), 0)  # Check if process exists
            print(f"✅ Migration process is running (PID: {pid})")
        except OSError:
            print("⚠️  Migration process not found (may have completed)")
    
    print()
    remaining = check_migration_status()
    
    if remaining > 0:
        print()
        print("💡 Tip: Run this script again to check progress")
        print(f"   Command: python3 monitor-sales-notes-migration.py")
    else:
        print()
        print("✅ All pages have been migrated!")

if __name__ == '__main__':
    main()
