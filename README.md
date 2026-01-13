# Coda to Notion Migration Tool

This tool automates the migration of pages from Coda documents to Notion, preserving formatting, lists, links, and structure.

## Features
- **Direct API Integration**: Fetches pages directly from Coda API
- **Rich Text Formatting**: Preserves bold, italic, underline, and strikethrough text formatting
- **Format Preservation**: Preserves headings, lists (bulleted and numbered), links, and text formatting
- **Nested List Support**: Handles nested lists with proper hierarchy
- **Link Preservation**: Maintains all links from original Coda pages
- **Date Extraction**: Automatically extracts and formats dates from page titles
- **Batch Processing**: Processes multiple pages in sequence
- **Selective Processing**: Supports filtering pages to process specific accounts or sections
- **Formatting Detection**: Uses browser computed styles to detect text formatting (works even when Coda doesn't use semantic HTML tags)

## Requirements
- Python 3.9+
- Coda API token
- Notion integration token
- Chrome browser (for Selenium)

## Setup
1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your `.env` file with API credentials:
   ```bash
   CODA_API_TOKEN=your_coda_token
   CODA_DOC_ID=your_coda_doc_id
   NOTION_API_TOKEN=your_notion_token
   NOTION_PARENT_PAGE_ID=your_notion_parent_page_id
   ```
4. Ensure Chrome is installed for Selenium WebDriver

## Usage
Run the migration script:
```bash
python coda-download.py
```

The script will:
- Fetch all pages from your Coda document
- Extract formatted content from each page
- Convert HTML to Notion block format
- Create Notion pages with preserved formatting

## Configuration
- **Coda Credentials**: Set `CODA_API_TOKEN` and `CODA_DOC_ID` in `.env` file
- **Notion Credentials**: Set `NOTION_API_TOKEN` and `NOTION_PARENT_PAGE_ID` in `.env` file
- **Starting Page**: Modify `start_from` variable in script to change which page to start processing from
- **Page Filtering**: Modify the filter condition to process specific pages (e.g., only "Lagoon" pages)

## How It Works

### 1. Coda API Integration
- Uses Coda API to fetch all pages from the document
- Extracts page metadata (name, ID, browser link)

### 2. Content Extraction
- Uses Selenium to load each page in headless Chrome
- Extracts rendered HTML content from the page
- Processes HTML to convert Coda list structures to proper HTML lists
- **Note**: PDF extraction is not used. Content is extracted directly from rendered pages for better format preservation.

### 3. Notion Block Conversion
- Converts HTML elements to Notion block format
- Preserves rich text formatting (bold, italic, links, etc.)
- Handles nested lists with proper hierarchy

### 4. Notion Page Creation
- Creates Notion pages with page title
- Uploads content blocks in chunks (100 blocks per request)
- Preserves all formatting and structure

## Supported Formatting

- **Headings**: H1, H2, H3
- **Lists**: Bulleted and numbered lists with nesting
- **Text Formatting**: 
  - **Bold**: Detected via computed font-weight (>= 600 or 'bold')
  - **Italic**: Detected via computed font-style
  - **Underline**: Detected via computed text-decoration
  - **Strikethrough**: Detected via computed text-decoration
  - **Code**: Supported via `<code>` tags
- **Links**: All anchor tags with href attributes
- **Paragraphs**: Regular text blocks

**Note**: Formatting is detected using browser computed styles, which means it works even when Coda uses CSS classes instead of semantic HTML tags for formatting.

## Troubleshooting

### Authentication Issues
- Verify your Coda API token is valid
- Check that your Notion integration token has access to the target workspace
- Ensure the Notion parent page ID is correct

### Content Extraction Issues
- Ensure Chrome is installed and accessible
- Check that the Coda document is accessible
- Verify Selenium can access the page content

### Notion API Issues
- Check that your Notion integration has the correct permissions
- Verify the parent page ID exists and is accessible
- Ensure you're not hitting API rate limits

## Security
**Do not commit or share your API tokens.**

Keep your `.env` file secure and never commit it to version control.

---

For questions or improvements, open an issue or pull request.
