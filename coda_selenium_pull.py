import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Read credentials from environment variables
CODA_EMAIL = os.environ.get("CODA_EMAIL")
CODA_PASSWORD = os.environ.get("CODA_PASSWORD")

if not CODA_EMAIL or not CODA_PASSWORD:
    raise ValueError("Please set CODA_EMAIL and CODA_PASSWORD environment variables.")

# Target Coda page URL
TARGET_URL = "https://coda.io/d/DLC-link-Wiki_d0eJEEjA-GU/Second-CL-Grant-preso-10-19-21_suEaKOeB"

def setup_driver():
    """Setup Chrome driver with appropriate options"""
    options = Options()
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
        return True
    except TimeoutException:
        return False

def try_navigation(driver, url, max_attempts=3):
    """Try to navigate to a URL multiple times with proper waits"""
    for attempt in range(max_attempts):
        try:
            print(f"\nNavigation attempt {attempt + 1}/{max_attempts}")
            
            # Navigate to the page
            driver.get(url)
            
            # Wait for page load
            if not wait_for_page_load(driver, timeout=10):
                print("Page load timeout, will retry...")
                continue
                
            print("Page loaded, waiting for content...")
            time.sleep(5)  # Give extra time for dynamic content
            
            # Verify we reached the correct page
            if TARGET_URL in driver.current_url:
                print("Successfully navigated to target URL!")
                return True
            else:
                print("Navigation didn't reach target. Current URL:", driver.current_url)
            
        except WebDriverException as e:
            print(f"Navigation error on attempt {attempt + 1}: {e}")
        except Exception as e:
            print(f"Unexpected error on attempt {attempt + 1}: {e}")
            
        if attempt < max_attempts - 1:
            print("Waiting before next attempt...")
            time.sleep(3)
    
    return False

def extract_content(driver):
    """Extract content using multiple selectors and approaches"""
    print("\nTrying to extract content...")
    
    target_text = "Keeper is doing CheckUpkeep function"
    content_found = []
    
    # Wait for any dynamic content
    time.sleep(5)
    
    try:
        # Try to scroll the page to ensure all content is loaded
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # First try to find elements containing our target text
        print("\nSearching for elements containing target text...")
        elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{target_text}')]")
        
        if elements:
            print(f"Found {len(elements)} elements containing target text!")
            for element in elements:
                # Try to get the parent container that might have the full text block
                try:
                    # Look for parent elements that might contain the full text block
                    parent = element
                    for _ in range(3):  # Try up to 3 levels up
                        parent_text = parent.text.strip()
                        if len(parent_text) > len(element.text) and target_text in parent_text:
                            print("\nFound text block:")
                            print("=" * 50)
                            print(parent_text)
                            print("=" * 50)
                            content_found.append(parent_text)
                            break
                        parent = parent.find_element(By.XPATH, "..")
                except:
                    # If we can't get parent, just use the element itself
                    text = element.text.strip()
                    if text:
                        print("\nFound text:")
                        print("=" * 50)
                        print(text)
                        print("=" * 50)
                        content_found.append(text)
        
        if not content_found:
            print("\nTrying alternative selectors...")
            selectors = [
                "[data-coda-ui-id='doc-body']",
                "[data-coda-ui-id='canvas-content']",
                "[data-coda-ui-id='page-content']",
                "[data-coda-ui-id='rich-text']",
                "[data-coda-ui-id='text-block']",
                "article",
                "main"
            ]
            
            for selector in selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if target_text in text:
                        print(f"\nFound text in {selector}:")
                        print("=" * 50)
                        print(text)
                        print("=" * 50)
                        content_found.append(text)
        
        # Take a screenshot for debugging if needed
        if not content_found:
            screenshot_path = "coda_page_debug.png"
            driver.save_screenshot(screenshot_path)
            print(f"\nNo content found. Saved debug screenshot to {screenshot_path}")
            
            # Try one last time with full body text
            body_text = driver.find_element(By.TAG_NAME, "body").text
            if target_text in body_text:
                paragraphs = body_text.split('\n\n')
                for para in paragraphs:
                    if target_text in para:
                        print("\nFound text in body:")
                        print("=" * 50)
                        print(para)
                        print("=" * 50)
                        content_found.append(para)
    
    except Exception as e:
        print(f"Error during content extraction: {e}")
    
    return content_found

def main():
    driver = None
    try:
        print("\n=== Starting browser ===")
        driver = setup_driver()
        if not driver:
            print("Failed to initialize Chrome driver")
            return
        
        print("\n=== Navigating to target page ===")
        if not try_navigation(driver, TARGET_URL):
            print("Failed to navigate to target page")
            return
        
        print("\n=== Extracting content ===")
        content = extract_content(driver)
        
        if content:
            print("\n=== Extracted Text Blocks ===")
            for i, text_block in enumerate(content, 1):
                print(f"\nText Block {i}:")
                print("=" * 50)
                print(text_block)
                print("=" * 50)
        else:
            print("\nNo content was extracted!")
        
        print("\nScript complete. Press Enter to close the browser...")
        input()
        
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