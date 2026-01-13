# Product Requirements Document (PRD)
## Coda to Notion Migration System

### Document Information
- **Version**: 2.0
- **Date**: January 2025
- **Author**: Aki Balogh
- **Status**: Active

---

## 1. Executive Summary

### 1.1 Purpose
Migrate client meeting notes from Coda documents to Notion by extracting page content and creating corresponding Notion pages with preserved formatting, structure, and links.

### 1.2 Problem Statement
- Client meeting notes are stored in Coda documents with rich formatting, lists, and links
- Need to migrate these notes to Notion while preserving structure and content
- Manual copy-paste is time-consuming and loses formatting
- Need automated migration that handles nested lists, links, headings, and dates

### 1.3 Solution Overview
Automated system that:
1. Fetches all pages from a Coda document via API
2. Extracts formatted HTML content from each page using Selenium
3. Converts HTML to Notion block format
4. Creates Notion pages with preserved formatting, lists, and links

---

## 2. Product Overview

### 2.1 Target Users
- Sales team members
- Account managers
- System administrators

### 2.2 Key Features
- **Coda API Integration**: Fetch pages and metadata from Coda documents
- **Content Extraction**: Extract formatted HTML content using Selenium browser automation
- **HTML to Notion Conversion**: Convert HTML elements to Notion block format
- **Format Preservation**: Preserve headings, lists (bulleted and numbered), links, and text formatting
- **Nested List Support**: Handle nested lists with proper hierarchy
- **Date Extraction**: Extract and format dates from page titles
- **Batch Processing**: Process multiple pages in sequence

---

## 3. Functional Requirements

### 3.1 Coda Integration
- **API Authentication**: Authenticate with Coda using API token
- **Page Listing**: Fetch all pages from a Coda document
- **Page Filtering**: Support starting from a specific page (e.g., "Client Meeting Notes")
- **Page Metadata**: Extract page names, IDs, and browser links

### 3.2 Content Extraction
- **Selenium Automation**: Use headless Chrome to extract rendered HTML
- **Content Selectors**: Robust selectors for canvas/content elements
- **Formatting Detection**: JavaScript-based detection of text formatting using browser computed styles (font-weight, font-style, text-decoration)
- **HTML Processing**: Clean and process HTML to extract structured content
- **List Conversion**: Convert Coda list structures to proper HTML `<ul>`/`<ol>` elements
- **Link Preservation**: Preserve all anchor tags and href attributes
- **Rich Text Wrapping**: Automatically wrap formatted text with semantic HTML tags (`<strong>`, `<em>`, `<u>`, `<s>`) based on computed styles
- **Note**: PDF extraction is not used. The system uses Selenium to extract rendered HTML directly from Coda pages, which preserves formatting, links, and structure better than PDF conversion.

### 3.3 Notion Integration
- **API Authentication**: Authenticate with Notion using integration token
- **Block Conversion**: Convert HTML elements to Notion block format
- **Rich Text Support**: Support bold, italic, underline, strikethrough, code formatting
- **List Support**: Support bulleted and numbered lists with nesting
- **Heading Support**: Support H1, H2, H3 headings
- **Link Support**: Preserve links in rich text
- **Page Creation**: Create Notion pages with title and content blocks
- **Chunked Upload**: Handle large content by splitting into chunks (100 blocks per request)

### 3.4 User Interface
- **Command Line Interface**: Easy-to-use CLI with clear progress output
- **Progress Tracking**: Real-time feedback during processing
- **Error Reporting**: Clear error messages and suggestions
- **Selective Processing**: Support filtering pages to process (e.g., specific account names)

---

## 4. Technical Requirements

### 4.1 System Architecture
```
Coda Document → API Fetch → Selenium Extraction → HTML Processing → Notion Block Conversion → Notion API Upload
```

### 4.2 Technology Stack
- **Language**: Python 3.9+
- **Coda API**: REST API with bearer token authentication
- **Selenium**: Chrome WebDriver for content extraction
- **Notion API**: REST API v1 (2022-06-28)
- **HTML Processing**: BeautifulSoup4 for HTML parsing and manipulation
- **Text Processing**: Regular expressions for date extraction and text normalization
- **File Management**: Pathlib for cross-platform file handling

### 4.3 HTML to Notion Block Conversion

**Supported Block Types**:
- **Paragraph**: Basic text blocks with rich text formatting
- **Heading 1/2/3**: Headings with rich text
- **Bulleted List**: Nested bulleted lists
- **Numbered List**: Nested numbered lists

**Rich Text Annotations**:
- Bold (`<strong>`, `<b>`)
- Italic (`<em>`, `<i>`)
- Underline (`<u>`)
- Strikethrough (`<s>`, `<strike>`)
- Code (`<code>`)
- Links (`<a href="...">`)

**List Nesting**:
- Supports nested lists within list items
- Maintains proper hierarchy using children blocks
- Handles mixed nested lists (bulleted within numbered, etc.)

### 4.4 Content Processing Pipeline

**Note**: PDF extraction is not used. The system extracts content directly from rendered Coda pages using Selenium, which provides superior format preservation compared to PDF conversion.

**Step 1: Coda API Fetch**
- Fetch all pages from Coda document
- Filter pages starting from a specific page name
- Extract page metadata (name, ID, browser link)

**Step 2: Selenium Extraction**
- Load each page in headless Chrome
- Wait for content to render
- Extract HTML from canvas/content elements
- Clean HTML (remove scripts, styles)

**Step 3: HTML Processing**
- Convert Coda list structures to proper HTML lists
- Process nested lists using block-level classes
- Preserve links and formatting
- Extract and format dates from page titles

**Step 4: Notion Block Conversion**
- Parse HTML elements
- Convert to Notion block format
- Handle rich text annotations
- Build nested list structures

**Step 5: Notion API Upload**
- Create Notion page with title
- Upload blocks in chunks of 100
- Handle API rate limits and errors

### 4.5 Dependencies
- Coda API access with token
- Notion workspace with integration token
- Chrome browser for Selenium
- Python environment with required packages

---

## 5. User Stories

### 5.1 Primary User Stories

**As a sales team member, I want to:**
- Run a single command to migrate all my Coda meeting notes to Notion
- Preserve all formatting, lists, and links in the migration
- See progress as pages are migrated
- Have dates automatically extracted and formatted

**As a system administrator, I want to:**
- Configure which pages to migrate (starting point)
- Monitor the migration process and handle errors
- Maintain the system with minimal manual intervention

### 5.2 Acceptance Criteria

**Coda Integration:**
- ✅ System fetches all pages from Coda document
- ✅ Supports filtering pages from a starting point
- ✅ Extracts page metadata correctly

**Content Extraction:**
- ✅ Extracts formatted HTML content from Coda pages
- ✅ Preserves links and formatting
- ✅ Converts Coda lists to proper HTML lists
- ✅ Handles nested lists correctly

**Notion Integration:**
- ✅ Creates Notion pages with correct titles
- ✅ Preserves formatting (bold, italic, links, etc.)
- ✅ Supports nested lists
- ✅ Handles large content with chunked uploads

---

## 6. Data Models

### 6.1 Coda Page Structure
```json
{
  "id": "page-id",
  "name": "Page Title",
  "browserLink": "https://coda.io/d/...",
  "href": "https://coda.io/d/..."
}
```

### 6.2 Notion Block Structure
```json
{
  "object": "block",
  "type": "paragraph",
  "paragraph": {
    "rich_text": [
      {
        "type": "text",
        "text": {
          "content": "Text content",
          "link": {"url": "https://example.com"}
        },
        "annotations": {
          "bold": true,
          "italic": false,
          "underline": false,
          "strikethrough": false,
          "code": false,
          "color": "default"
        }
      }
    ]
  }
}
```

### 6.3 Configuration
```bash
# .env file
CODA_API_TOKEN=your_coda_token
CODA_DOC_ID=your_doc_id
NOTION_API_TOKEN=your_notion_token
NOTION_PARENT_PAGE_ID=your_parent_page_id
```

**Testing Configuration:**
- Test Notion page: https://www.notion.so/Coda-migrations-test-2c3636dd0ba5807eb374c07a0134e636
- Test parent page ID: `2c3636dd-0ba5-807e-b374-c07a0134e636` (with hyphens for API)
- This test page is used for development and testing of the migration system
- **Note**: The page must be shared with your Notion integration for API access

---

## 7. Implementation Plan

### 7.1 Phase 1: Core Coda Integration (Completed)
- [x] Coda API authentication
- [x] Page listing and filtering
- [x] Page metadata extraction

### 7.2 Phase 2: Content Extraction (Completed)
- [x] Selenium setup and configuration
- [x] HTML content extraction
- [x] List structure conversion
- [x] Link preservation

### 7.3 Phase 3: Notion Integration (Completed)
- [x] Notion API authentication
- [x] HTML to Notion block conversion
- [x] Rich text formatting support
- [x] Nested list support
- [x] Page creation with chunked uploads

### 7.4 Phase 4: Testing & Documentation (In Progress)
- [x] Basic functionality testing
- [x] Error handling
- [ ] Comprehensive documentation
- [ ] Troubleshooting guide

---

## 8. Success Metrics

### 8.1 Technical Metrics
- **Processing Speed**: Process pages at reasonable speed (target: < 10 seconds per page)
- **Format Preservation**: 100% preservation of links and basic formatting
- **List Accuracy**: Correct nesting and structure for nested lists
- **Error Rate**: < 1% failed page migrations

### 8.2 User Metrics
- **Time Savings**: 90% reduction in manual work
- **Format Quality**: > 95% of formatting preserved correctly
- **User Satisfaction**: > 4.5/5 rating

---

## 9. Risk Assessment

### 9.1 Technical Risks
- **Coda API Changes**: Mitigated by using stable API endpoints
- **Notion API Limits**: Handled with chunked uploads and rate limiting
- **Selenium Reliability**: Mitigated by robust selectors and error handling
- **HTML Parsing Complexity**: Addressed with BeautifulSoup and careful processing

### 9.2 Business Risks
- **Data Loss**: Mitigated by processing one page at a time with error handling
- **Security Concerns**: Addressed with secure credential storage (.env file)
- **User Adoption**: Mitigated by intuitive CLI and comprehensive documentation

---

## 10. Future Enhancements

### 10.1 Short Term (3 months)
- Support for more Notion block types (tables, callouts, etc.)
- Enhanced date formatting options
- Batch processing improvements
- Better error recovery

### 10.2 Long Term (6+ months)
- Web-based interface
- Real-time sync capabilities
- Advanced formatting options
- Integration with other document sources

---

## 11. Appendices

### 11.1 Configuration Examples
See `.env` file for configuration examples.

### 11.2 API Documentation
- Coda API: https://coda.io/developers/apis/v1
- Notion API: https://developers.notion.com/reference

### 11.3 Troubleshooting Guide
See `README.md` for common issues and solutions.

---

**Document Status**: ✅ Complete and Active
**Last Updated**: January 2025
**Next Review**: April 2025

## 12. Current Status Summary

### 12.1 Major Achievements
- ✅ **Coda API Integration**: Successfully fetches pages from Coda documents
- ✅ **Content Extraction**: Robust HTML extraction using Selenium with computed style detection
- ✅ **Notion Integration**: Complete Notion API integration with block conversion
- ✅ **Format Preservation**: Preserves links, formatting, and nested lists
- ✅ **Rich Text Formatting**: Detects and preserves bold, italic, underline, and strikethrough text via computed CSS styles
- ✅ **List Processing**: Handles nested bulleted and numbered lists correctly
- ✅ **Formatting Detection**: JavaScript-based detection of text formatting using browser computed styles

### 12.2 Key Files
- `coda-download.py` - Main migration script
- `.env` - Configuration file for API tokens

### 12.3 Testing
- **Test Notion Page**: https://www.notion.so/Coda-migrations-test-2c3636dd0ba5807eb374c07a0134e636
- All migrated pages are created as children of this test page during development
- Use `--dry-run` flag to preview migrations without creating pages

### 12.4 Duplicate Prevention
- **Automatic Duplicate Detection**: The system checks for existing pages with the same title before creating new ones
- **Skip Logic**: If a page with the same title already exists, the migration skips it to avoid duplicates
- **Content Verification**: Duplicate detection compares both title and initial content to ensure pages are truly duplicates
- **Cleanup Tools**: Scripts available to identify and remove duplicate pages if they occur

### 12.5 Formatting Support (Implemented January 2025)
- ✅ **Bold Text**: Detected via computed `font-weight` (>= 600 or 'bold') and wrapped with `<strong>` tags
- ✅ **Italic Text**: Detected via computed `font-style === 'italic'` and wrapped with `<em>` tags
- ✅ **Underline**: Detected via computed `text-decoration` and wrapped with `<u>` tags
- ✅ **Strikethrough**: Detected via computed `text-decoration` and wrapped with `<s>` tags
- ✅ **Bulleted Lists**: Converted from Coda `kr-ulist` classes to HTML `<ul>` and Notion `bulleted_list_item`
- ✅ **Numbered Lists**: Converted from Coda `kr-olist` classes to HTML `<ol>` and Notion `numbered_list_item`
- ✅ **Nested Lists**: Supports multi-level nested lists with proper hierarchy
- ✅ **Links**: Preserved with href attributes and converted to Notion link annotations

### 12.6 Next Steps
- Complete comprehensive testing across all page types
- Add support for additional Notion block types (tables, callouts, code blocks)
- Improve error handling and recovery
- Performance optimization for large migrations
