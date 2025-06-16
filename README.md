# Coda to Notion Migration Tool

This tool automates the migration of content from Coda pages to Notion, preserving formatting such as nested bullet points, bold, italics, and headings.

## Features
- Extracts content from Coda using Selenium (with Chrome in headless mode)
- Preserves nested bullet points and text formatting
- Converts Coda content to Notion blocks using the Notion API
- Creates a new Notion page for each Coda page

## Requirements
- Python 3.8+
- Google Chrome installed
- ChromeDriver installed and in your PATH
- Notion integration token and parent page ID
- Coda API token and document ID

## Setup
1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your Chrome user profile for Selenium authentication (if needed).
4. Edit `coda-download.py` to add your Coda and Notion API tokens and IDs.

## Usage
Run the migration script:
```bash
python coda-download.py
```

- The script will fetch Coda pages, extract and process their content, and create corresponding Notion pages.
- Extracted HTML and text files are saved in the `output/` directory for reference.

## Configuration
- **Coda API Token** and **Document ID**: Set in `coda-download.py`.
- **Notion API Token** and **Parent Page ID**: Set in `coda-download.py`.
- **Chrome Profile Directory**: Update the `--user-data-dir` argument in `setup_driver()` if needed.

## License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Security
**Do not commit or share your API tokens.**

---

For questions or improvements, open an issue or pull request. 