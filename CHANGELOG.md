# Changelog

All notable changes to the Coda to Notion Migration System will be documented in this file.

## [2.0] - 2025-12-12

### Migration Complete
- ✅ Successfully migrated 120 pages from Coda to Notion
- ✅ 110 new pages created, 41 duplicates skipped
- ✅ All formatting preserved (bold, italic, underline, strikethrough)
- ✅ Lists, links, and structure maintained

### Added
- **Rich Text Formatting Support**: Implemented JavaScript-based detection of text formatting using browser computed styles
  - Bold text detection via `font-weight` (>= 600 or 'bold')
  - Italic text detection via `font-style === 'italic'`
  - Underline detection via `text-decoration`
  - Strikethrough detection via `text-decoration`
- **Formatting Preservation**: Automatic wrapping of formatted text with semantic HTML tags (`<strong>`, `<em>`, `<u>`, `<s>`)
- **Enhanced Content Extraction**: Updated `extract_content()` function to use computed style detection instead of simple innerHTML extraction
- **Debug Logging**: Added comprehensive debug logging for formatting detection and processing pipeline

### Fixed
- **Bold Formatting**: Fixed issue where bold text was not being detected or preserved during migration
- **Formatting Loss**: Resolved problem where formatting tags were being stripped during HTML processing
- **Function Integration**: Fixed main migration loop to use `extract_content()` function with formatting detection instead of simple innerHTML extraction

### Changed
- **Content Extraction Method**: Switched from simple `innerHTML` extraction to computed style-based formatting detection
- **Processing Pipeline**: Updated to preserve formatting tags through `postprocess_coda_lists()` function
- **Documentation**: Updated PRD and README to document formatting support and detection methods

### Technical Details
- Formatting detection uses JavaScript `window.getComputedStyle()` to read CSS properties
- Text nodes are wrapped with appropriate HTML tags based on computed styles before HTML processing
- Formatting tags are preserved through the `extract_content_with_links()` function in `postprocess_coda_lists()`
- Notion API receives rich text annotations with `bold: true`, `italic: true`, etc. based on detected formatting

## [1.0] - 2024-XX-XX

### Added
- Initial migration from Salesforce to Notion
- Coda API integration for page listing
- Selenium-based content extraction
- Notion API integration for page creation
- List conversion (bulleted and numbered)
- Link preservation
- Duplicate prevention
- Dry-run mode

