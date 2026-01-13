#!/usr/bin/env python3
"""
Script to find problematic pages that failed during migration
and need manual handling.
"""

import glob
import os
import re
import sys

def find_problematic_pages(log_file):
    """Analyze migration log to find problematic pages"""
    
    with open(log_file, 'r') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Track processed vs created pages
    processed_pages = set()
    created_pages = set()
    updated_pages = set()
    skipped_pages = set()
    
    # Track errors
    problematic_pages = {}
    
    current_page = None
    
    for i, line in enumerate(lines):
        # Track processed pages
        match = re.search(r'\[INFO\] Processing page: (.+)', line)
        if match:
            current_page = match.group(1)
            processed_pages.add(current_page)
        
        # Track created pages
        match = re.search(r'\[✓\] Notion page created: (.+)', line)
        if match:
            page_name = match.group(1)
            created_pages.add(page_name)
            updated_pages.add(page_name)  # Updated pages are also "created"
        
        # Track updated pages
        match = re.search(r'\[UPDATE\].*Page \'(.+)\' exists but content has changed', line)
        if match:
            updated_pages.add(match.group(1))
        
        # Track skipped pages
        match = re.search(r'\[SKIP\].*already exists', line)
        if match and current_page:
            skipped_pages.add(current_page)
        
        # Track errors
        if '[ERROR]' in line and current_page:
            if current_page not in problematic_pages:
                problematic_pages[current_page] = {
                    'errors': [],
                    'line': i
                }
            problematic_pages[current_page]['errors'].append(line.strip())
        
        # Track exceptions/tracebacks
        if ('Traceback' in line or 'Exception:' in line) and current_page:
            if current_page not in problematic_pages:
                problematic_pages[current_page] = {
                    'errors': [],
                    'line': i
                }
    
    # Pages that were processed but not created/updated/skipped
    failed_pages = processed_pages - created_pages - updated_pages - skipped_pages
    
    return {
        'processed': processed_pages,
        'created': created_pages,
        'updated': updated_pages,
        'skipped': skipped_pages,
        'failed': failed_pages,
        'with_errors': problematic_pages
    }

def main():
    print("=" * 60)
    print("PROBLEMATIC PAGES ANALYSIS")
    print("=" * 60)
    print()
    
    # Find latest migration log
    migration_logs = sorted(glob.glob("migration-*.log"), key=os.path.getmtime, reverse=True)
    if not migration_logs:
        print("⚠️  No migration logs found")
        sys.exit(1)
    
    latest = migration_logs[0]
    print(f"📝 Analyzing log: {latest}")
    print()
    
    results = find_problematic_pages(latest)
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()
    print(f"📊 Pages processed: {len(results['processed'])}")
    print(f"✅ Pages created: {len(results['created'])}")
    print(f"🔄 Pages updated: {len(results['updated'])}")
    print(f"⏭️  Pages skipped: {len(results['skipped'])}")
    print(f"❌ Pages failed: {len(results['failed'])}")
    print(f"⚠️  Pages with errors: {len(results['with_errors'])}")
    print()
    
    # Failed pages
    if results['failed']:
        print("=" * 60)
        print("FAILED PAGES (processed but not created/updated/skipped)")
        print("=" * 60)
        print()
        print("These pages were processed but failed to create in Notion:")
        print()
        for page in sorted(results['failed']):
            print(f"   - {page}")
        print()
        print(f"Total: {len(results['failed'])} pages need manual handling")
        print()
    else:
        print("✅ No failed pages found")
        print()
    
    # Pages with errors
    if results['with_errors']:
        print("=" * 60)
        print("PAGES WITH ERRORS")
        print("=" * 60)
        print()
        print("These pages encountered errors during processing:")
        print()
        for page, error_info in sorted(results['with_errors'].items()):
            print(f"   - {page}")
            for error in error_info['errors'][:3]:  # Show first 3 errors
                print(f"     {error[:100]}")
            if len(error_info['errors']) > 3:
                print(f"     ... and {len(error_info['errors']) - 3} more errors")
            print()
        print()
    
    # All problematic pages (failed OR with errors)
    all_problematic = results['failed'] | set(results['with_errors'].keys())
    
    if all_problematic:
        print("=" * 60)
        print("ALL PROBLEMATIC PAGES (FOR MANUAL HANDLING)")
        print("=" * 60)
        print()
        print("The following pages need manual handling:")
        print()
        for page in sorted(all_problematic):
            issues = []
            if page in results['failed']:
                issues.append("failed to create")
            if page in results['with_errors']:
                issues.append("has errors")
            print(f"   - {page} ({', '.join(issues)})")
        print()
        print(f"Total: {len(all_problematic)} pages need manual handling")
        print()
    else:
        print("✅ No problematic pages found!")
        print("   All pages migrated successfully!")
        print()
    
    print("=" * 60)
    
    return len(all_problematic)

if __name__ == "__main__":
    sys.exit(main())
