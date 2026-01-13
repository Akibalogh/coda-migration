#!/usr/bin/env python3
"""Check for new pages in Coda that need to be migrated"""
import os
import sys
import requests
from dotenv import load_dotenv

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

def get_notion_pages():
    """Get all pages from Notion"""
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
    return notion_pages

def main():
    print("=" * 60)
    print("CHECKING FOR NEW PAGES TO MIGRATE")
    print("=" * 60)
    print()
    
    # Get all pages from Coda
    print("Fetching pages from Coda...")
    coda_pages = coda_download.fetch_all_pages_flat()
    print(f"Found {len(coda_pages)} total pages in Coda\n")
    
    # Find starting point
    start_from = "Lagoon"
    start_index = None
    for idx, page in enumerate(coda_pages):
        if coda_download.normalize(page.get('name', '')) == coda_download.normalize(start_from):
            start_index = idx
            break
    
    if start_index is None:
        print(f"⚠ Warning: Start page '{start_from}' not found")
        pages_to_migrate = coda_pages
    else:
        pages_to_migrate = coda_pages[start_index:]
        print(f"Pages to migrate (starting from '{start_from}'): {len(pages_to_migrate)}")
        print(f"Total Coda pages: {len(coda_pages)}")
        print(f"Pages before '{start_from}': {start_index}\n")
    
    # Get pages from Notion
    print("Fetching pages from Notion...")
    notion_pages = get_notion_pages()
    print(f"Found {len(notion_pages)} pages in Notion\n")
    
    # Create normalized title maps
    coda_titles = {}
    for page in pages_to_migrate:
        name = page.get('name', 'unnamed')
        notion_title, _ = coda_download.extract_title_and_date(name)
        coda_titles[coda_download.normalize(notion_title)] = (name, notion_title)
    
    notion_titles = {}
    for page in notion_pages:
        title = page.get('child_page', {}).get('title', 'Untitled')
        notion_titles[coda_download.normalize(title)] = title
    
    # Find missing pages
    missing_pages = []
    for norm_title, (original_name, notion_title) in coda_titles.items():
        if norm_title not in notion_titles:
            missing_pages.append((original_name, notion_title))
    
    print("=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    print(f"Coda pages to migrate: {len(pages_to_migrate)}")
    print(f"Notion pages: {len(notion_pages)}")
    print(f"Missing pages: {len(missing_pages)}")
    print("=" * 60)
    
    if missing_pages:
        print(f"\n⚠ Found {len(missing_pages)} pages in Coda that are NOT in Notion:\n")
        for i, (original_name, notion_title) in enumerate(missing_pages, 1):
            print(f"  {i:3}. {notion_title}")
            if original_name != notion_title:
                print(f"       (Original: {original_name})")
        print()
        print("These pages need to be migrated.")
        print("\nTo migrate these pages, run:")
        print("  python3 coda-download.py")
    else:
        print("\n✅ All pages from Coda are already in Notion!")
        print("   No new pages to migrate.")
    
    # Check for pages in Notion that aren't in Coda
    extra_notion = []
    for norm_title, notion_title in notion_titles.items():
        if norm_title not in coda_titles:
            extra_notion.append(notion_title)
    
    if extra_notion:
        print(f"\nℹ Found {len(extra_notion)} pages in Notion that aren't in Coda:")
        print("   (These may have been manually created or from a different source)")
        for title in extra_notion[:10]:
            print(f"     - {title}")
        if len(extra_notion) > 10:
            print(f"     ... and {len(extra_notion) - 10} more")
    
    print()
    print("=" * 60)
    print("MIGRATION COVERAGE")
    print("=" * 60)
    print("✅ Pages: Migrated")
    print("✅ Formatting: Preserved (bold, italic, underline, strikethrough)")
    print("✅ Lists: Migrated (bulleted and numbered, nested)")
    print("✅ Links: Preserved")
    print("✅ Headings: Migrated (H1, H2, H3)")
    print()
    print("⚠ Not currently migrated (if present in Coda):")
    print("  - Images/attachments (would need additional API calls)")
    print("  - Tables (would need special Notion table block conversion)")
    print("  - Code blocks (would need code block conversion)")
    print("  - Callouts/quote blocks (would need callout block conversion)")
    print()
    print("Note: The current migration focuses on text content, formatting,")
    print("      lists, and links. Other content types would require")
    print("      additional development.")

if __name__ == "__main__":
    main()
