import os
import time
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
import re

# Target URL
TARGET_URL = "https://coda.io/d/DLC-link-Wiki_d0eJEEjA-GU/Second-CL-Grant-preso-10-19-21_suEaKOeB"

def setup_driver():
    """Setup Chrome driver with appropriate options"""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        return None

def wait_for_page_load(driver, timeout=10):
    """Wait for page to load completely"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        time.sleep(2)  # Additional wait for dynamic content
        return True
    except TimeoutException:
        return False

def clean_html(html_content):
    """Clean and structure HTML content for better formatting"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Convert Coda's list structure to proper HTML lists
    for div in soup.find_all('div', class_='kr-ulist'):
        # If this is a list item
        if 'kr-listitem' in div.get('class', []):
            # If there's no parent ul, create one
            if not div.parent.name == 'ul':
                ul = soup.new_tag('ul')
                div.wrap(ul)
            
            # Convert div to li
            li = soup.new_tag('li')
            # Move the text content
            span = div.find('span')
            if span:
                li.string = span.get_text()
            # Replace the div with li
            div.replace_with(li)
    
    # Handle nested lists
    for ul in soup.find_all('ul'):
        # Find all li elements
        items = ul.find_all('li', recursive=False)
        for i, item in enumerate(items):
            # Check if next item is more indented
            if i < len(items) - 1:
                current_indent = len(item.get('class', []))
                next_indent = len(items[i + 1].get('class', []))
                if next_indent > current_indent:
                    # Create nested ul if it doesn't exist
                    if not item.find('ul'):
                        nested_ul = soup.new_tag('ul')
                        item.append(nested_ul)
    
    # Convert headings
    for div in soup.find_all('div', class_=True):
        classes = div.get('class', [])
        if any('heading' in cls.lower() for cls in classes):
            level = 1  # Default to h1
            for cls in classes:
                if 'heading' in cls.lower():
                    try:
                        level = int(cls[-1])  # Try to get heading level from class
                    except:
                        pass
            h_tag = soup.new_tag(f'h{level}')
            h_tag.string = div.get_text()
            div.replace_with(h_tag)
    
    # Convert other formatting
    format_map = {
        'bold': 'strong',
        'italic': 'em',
        'underline': 'u',
        'strike': 'strike',
        'code': 'code',
        'quote': 'blockquote'
    }
    
    for div in soup.find_all(['div', 'span']):
        if not div.get('class'):
            continue
        
        classes = div.get('class', [])
        for cls in classes:
            for fmt_class, fmt_tag in format_map.items():
                if fmt_class in cls.lower():
                    new_tag = soup.new_tag(fmt_tag)
                    new_tag.string = div.get_text()
                    div.replace_with(new_tag)
                    break
    
    # Clean up empty elements
    for tag in soup.find_all():
        # Remove empty tags except br
        if not tag.contents and not tag.string and tag.name != 'br':
            tag.decompose()
        # Remove all data attributes and classes
        for attr in list(tag.attrs):
            if attr.startswith('data-') or attr == 'class':
                del tag[attr]
    
    # Final structure cleanup
    html = str(soup)
    
    # Remove multiple consecutive line breaks
    html = re.sub(r'\n\s*\n', '\n\n', html)
    
    return html

def extract_formatted_content(driver):
    """Extract content while preserving formatting"""
    content_found = []
    
    try:
        # Wait for Coda's content to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-coda-ui-id]'))
        )
        
        # Try to scroll the page to ensure all content is loaded
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # JavaScript to get Coda's formatted content
        js_get_content = """
        function getCodaContent() {
            // Helper function to get computed styles
            function getStyle(element, property) {
                return window.getComputedStyle(element)[property];
            }
            
            // Helper function to check if element is visible
            function isVisible(element) {
                return element.offsetWidth > 0 && element.offsetHeight > 0;
            }
            
            // Find Coda's main content container
            let contentElements = document.querySelectorAll('[data-coda-ui-id="canvas"], [data-coda-ui-id="canvas-content"], [data-coda-ui-id="page-content"]');
            let mainContent = null;
            
            for (let element of contentElements) {
                if (isVisible(element)) {
                    mainContent = element;
                    break;
                }
            }
            
            if (!mainContent) {
                return null;
            }
            
            // Get all content blocks
            let blocks = Array.from(mainContent.querySelectorAll('[data-canvas-placement-block="true"]'));
            
            // Initialize HTML structure
            let html = '<div class="coda-content">';
            let currentList = null;
            let currentListLevel = 0;
            
            blocks.forEach((block, index) => {
                let text = block.textContent.trim();
                if (!text) {
                    if (block.querySelector('br')) {
                        html += '<br/>';
                    }
                    return;
                }
                
                // Get block's computed styles
                let styles = {
                    fontWeight: getStyle(block, 'fontWeight'),
                    fontStyle: getStyle(block, 'fontStyle'),
                    textDecoration: getStyle(block, 'textDecoration'),
                    marginLeft: parseInt(getStyle(block, 'marginLeft')),
                    display: getStyle(block, 'display')
                };
                
                // Determine if this is a list item
                let isList = block.classList.contains('kr-listitem') || 
                           block.classList.contains('kr-ulist') ||
                           block.querySelector('.kr-listitem, .kr-ulist');
                
                // Calculate indentation level
                let level = Math.floor(styles.marginLeft / 20);
                
                // Handle list structure
                if (isList) {
                    // If we're not in a list or at a different level, handle list transitions
                    if (!currentList || level !== currentListLevel) {
                        // Close deeper lists if needed
                        while (currentList && currentListLevel > level) {
                            html += '</ul>';
                            currentListLevel--;
                        }
                        // Open new list if needed
                        if (!currentList || currentListLevel < level) {
                            html += '<ul>';
                            currentListLevel = level;
                        }
                        currentList = true;
                    }
                    html += '<li>';
                } else {
                    // Close any open lists
                    while (currentList && currentListLevel >= 0) {
                        html += '</ul>';
                        currentListLevel--;
                    }
                    currentList = null;
                    
                    // Check for headings
                    if (block.classList.contains('kr-heading')) {
                        html += '<h2>';
                    } else {
                        html += '<p>';
                    }
                }
                
                // Apply text formatting
                if (parseInt(styles.fontWeight) >= 600) text = `<strong>${text}</strong>`;
                if (styles.fontStyle === 'italic') text = `<em>${text}</em>`;
                if (styles.textDecoration.includes('underline')) text = `<u>${text}</u>`;
                if (styles.textDecoration.includes('line-through')) text = `<strike>${text}</strike>`;
                
                // Add the text
                html += text;
                
                // Close the tag
                if (isList) {
                    html += '</li>';
                } else {
                    if (block.classList.contains('kr-heading')) {
                        html += '</h2>';
                    } else {
                        html += '</p>';
                    }
                }
                
                // Add spacing after certain blocks
                if (!isList && index < blocks.length - 1) {
                    let nextBlock = blocks[index + 1];
                    if (nextBlock && !nextBlock.classList.contains('kr-listitem')) {
                        html += '<br/>';
                    }
                }
            });
            
            // Close any remaining lists
            while (currentList && currentListLevel >= 0) {
                html += '</ul>';
                currentListLevel--;
            }
            
            html += '</div>';
            return html;
        }
        return getCodaContent();
        """
        
        try:
            # Try to get content from main document
            html_content = driver.execute_script(js_get_content)
            if html_content and len(html_content) > 100:
                cleaned_html = clean_html(html_content)
                text_content = driver.execute_script("return document.body.innerText;")
                content_found.append({
                    'selector': 'coda-content',
                    'html': cleaned_html,
                    'text': text_content
                })
                print("Successfully extracted content from main document")
        except Exception as e:
            print(f"Error extracting main content: {e}")
        
        # If no content found, try iframe
        if not content_found:
            try:
                print("\nTrying iframe content...")
                # Wait for iframe
                iframe = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "iframe"))
                )
                
                # Switch to iframe
                driver.switch_to.frame(iframe)
                
                # Wait for Coda content in iframe
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-coda-ui-id]'))
                )
                
                # Try to get content from iframe
                html_content = driver.execute_script(js_get_content)
                if html_content and len(html_content) > 100:
                    cleaned_html = clean_html(html_content)
                    text_content = driver.execute_script("return document.body.innerText;")
                    content_found.append({
                        'selector': 'iframe-content',
                        'html': cleaned_html,
                        'text': text_content
                    })
                    print("Successfully extracted content from iframe")
                
                driver.switch_to.default_content()
            except Exception as e:
                print(f"Error extracting iframe content: {e}")
                try:
                    driver.switch_to.default_content()
                except:
                    pass
    
    except Exception as e:
        print(f"Error during content extraction: {e}")
    
    return content_found

def save_content(content_blocks, output_dir="extracted_content"):
    """Save extracted content to files"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    for i, content in enumerate(content_blocks, 1):
        # Save HTML version
        html_file = os.path.join(output_dir, f"content_block_{i}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(content['html'])
        
        # Save text version
        text_file = os.path.join(output_dir, f"content_block_{i}.txt")
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(content['text'])
            
        print(f"\nSaved content block {i}:")
        print(f"- HTML: {html_file}")
        print(f"- Text: {text_file}")

def main():
    driver = None
    try:
        print("\n=== Starting browser ===")
        driver = setup_driver()
        if not driver:
            print("Failed to initialize Chrome driver")
            return
        
        print(f"\nNavigating to: {TARGET_URL}")
        driver.get(TARGET_URL)
        
        if wait_for_page_load(driver):
            print("Page loaded successfully")
            
            print("\n=== Extracting formatted content ===")
            content_blocks = extract_formatted_content(driver)
            
            if content_blocks:
                print("\n=== Content Blocks Found ===")
                for i, content in enumerate(content_blocks, 1):
                    print(f"\nContent Block {i} (found with {content['selector']}):")
                    print("=" * 80)
                    # Print first part of HTML to show structure
                    html_preview = content['html'][:500] + "..." if len(content['html']) > 500 else content['html']
                    print("HTML Structure Preview:")
                    print(html_preview)
                    print("\nText Content Preview (first 200 chars):")
                    print(content['text'][:200] + "..." if len(content['text']) > 200 else content['text'])
                    print("=" * 80)
                
                # Save content to files
                save_content(content_blocks)
            else:
                print("\nNo content blocks found")
    
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    main() 