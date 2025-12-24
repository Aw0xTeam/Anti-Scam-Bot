import time
import asyncio
import re
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import html

import config
import db

# ChromeDriver Path
CHROMEDRIVER_PATH = r"C:\Users\Administrator\Downloads\chromedriver.exe"

# init db
db.init_db()

# aiogram bot
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Selenium driver
driver = None

# worker control
_worker_task = None
_worker_running = False

# Navigation tracking
current_page = "live_sms"  # live_sms, add_range, return_numbers

def init_driver():
    """Initialize Selenium WebDriver - VISIBLE BROWSER"""
    global driver
    try:
        options = webdriver.ChromeOptions()
        
        # MAKE BROWSER VISIBLE - NOT HEADLESS
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        
        # ADDITIONAL OPTIONS:
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set user agent to look like normal browser
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.implicitly_wait(10)
        print("✅ ChromeDriver started successfully - Browser is VISIBLE!")
        return True
    except Exception as e:
        db.save_error(f"Failed to start ChromeDriver: {e}")
        print(f"❌ Failed to start ChromeDriver: {e}")
        return False

def close_driver():
    """Close Selenium WebDriver"""
    global driver
    if driver:
        try:
            driver.quit()
            driver = None
            print("✅ ChromeDriver closed")
        except Exception as e:
            print(f"❌ Failed to close ChromeDriver: {e}")

# =========================================================
# Navigation Functions
# =========================================================

def navigate_to_live_sms(force_return=False):
    """Navigate to Live SMS page"""
    global current_page
    
    if current_page == "live_sms" and not force_return:
        try:
            if "portal/live/my_sms" in driver.current_url:
                return True
        except:
            pass
    
    try:
        if not driver:
            return False
        
        print("🌐 Navigating to Live SMS page...")
        driver.get("https://www.ivasms.com/portal/live/my_sms")
        time.sleep(3)
        
        # Check if we need to login
        if "login" in driver.current_url:
            print("⚠️ Redirected to login page, trying to login...")
            return login_and_fetch_token()
        
        if "portal/live/my_sms" not in driver.current_url:
            print("🔄 Trying alternative URL...")
            driver.get("https://www.ivasms.com/portal/live")
            time.sleep(3)
        
        # Verify we're on the right page
        try:
            page_title = driver.title
            page_source = driver.page_source
            if "Live SMS" in page_title or "Live SMS" in page_source:
                print("✅ Live SMS page verified")
            else:
                print(f"⚠️ Page title doesn't contain 'Live SMS': {page_title}")
        except:
            pass
        
        current_page = "live_sms"
        print("✅ Successfully navigated to Live SMS page")
        return True
        
    except Exception as e:
        print(f"❌ Error navigating to Live SMS page: {e}")
        return False

def navigate_to_add_range_page():
    """Navigate to terminations page (add range)"""
    global current_page
    try:
        if not driver:
            return False
        
        print("🌐 Navigating to terminations page...")
        driver.get("https://www.ivasms.com/portal/numbers/test")
        time.sleep(3)
        
        # Check if we need to login
        if "login" in driver.current_url:
            print("⚠️ Redirected to login page, trying to login...")
            return login_and_fetch_token()
        
        if "portal/numbers/test" not in driver.current_url:
            print("❌ Failed to navigate to terminations page")
            return False
        
        current_page = "add_range"
        print("✅ Successfully navigated to terminations (add range) page")
        return True
        
    except Exception as e:
        print(f"❌ Error navigating to terminations page: {e}")
        return False

def navigate_to_return_numbers_page():
    """Navigate to numbers page (maida numbers)"""
    global current_page
    try:
        if not driver:
            return False
        
        print("🌐 Navigating to numbers page...")
        driver.get("https://www.ivasms.com/portal/numbers")
        time.sleep(3)
        
        # Check if we need to login
        if "login" in driver.current_url:
            print("⚠️ Redirected to login page, trying to login...")
            return login_and_fetch_token()
        
        if "portal/numbers" not in driver.current_url:
            print("❌ Failed to navigate to numbers page")
            return False
        
        current_page = "return_numbers"
        print("✅ Successfully navigated to numbers (maida numbers) page")
        return True
        
    except Exception as e:
        print(f"❌ Error navigating to numbers page: {e}")
        return False

# =========================================================
# Login Function
# =========================================================
def login_and_fetch_token():
    print("🔄 Attempting to login and fetch new session/token...")
    
    global driver
    
    if not driver:
        if not init_driver():
            return False
    
    try:
        driver.get("https://www.ivasms.com/login")
        
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "input"))
        )
        
        print("✅ Login page loaded!")
        
        # Wait for manual login (60 seconds)
        print("⏳ Waiting for manual login (60 seconds)...")
        time.sleep(60)
        
        token_input = driver.find_element(By.NAME, "_token")
        initial_csrf_token = token_input.get_attribute("value")
        
        if not initial_csrf_token:
            db.save_error("Login failed: CSRF token is empty.")
            print("❌ Login failed: CSRF token is empty.")
            return False

        print("✅ Got CSRF token")
        
        email_input = driver.find_element(By.NAME, "email")
        password_input = driver.find_element(By.NAME, "password")
        
        email_input.clear()
        email_input.send_keys(config.LOGIN_EMAIL)
        
        password_input.clear()
        password_input.send_keys(config.LOGIN_PASSWORD)
        
        print("✅ Credentials filled - clicking login button...")
        
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        
        print("⏳ Waiting for login...")
        
        try:
            WebDriverWait(driver, 15).until(
                lambda driver: "portal" in driver.current_url
            )
            print("✅ Login successful! URL changed to portal.")
            
        except TimeoutException:
            try:
                error_element = driver.find_element(By.CLASS_NAME, "alert-danger")
                error_text = error_element.text
                print(f"❌ Login error: {error_text}")
                db.save_error(f"Login error: {error_text}")
                return False
            except NoSuchElementException:
                if "login" in driver.current_url:
                    print("❌ Login failed - still on login page")
                    db.save_error("Login failed - still on login page")
                    return False
        
        if "portal" not in driver.current_url:
            print(f"❌ Not logged in - Currently on: {driver.current_url}")
            db.save_error(f"Not logged in - Currently on: {driver.current_url}")
            return False
        
        print("✅ Logged in successfully!")
        
        return navigate_to_live_sms()

    except TimeoutException:
        db.save_error("Login failed: Wait time expired.")
        print("❌ Login failed: Wait time expired.")
        return False
    except NoSuchElementException as e:
        db.save_error(f"Login failed: Could not find element: {e}")
        print(f"❌ Login failed: Could not find element: {e}")
        return False
    except Exception as e:
        db.save_error(f"Login process failed with error: {e}")
        print(f"❌ Login process failed with error: {e}")
        return False

# =========================================================
# Range Management Functions - SEARCH BY TEST NUMBER
# =========================================================

def search_for_range_by_test_number(test_number):
    """Search for a specific test number in terminations page"""
    try:
        print(f"🔍 Searching for test number: {test_number}")
        
        if current_page != "add_range":
            if not navigate_to_add_range_page():
                return None
        
        time.sleep(3)
        
        # Clear search input COMPLETELY before new search
        print("🧹 Clearing previous search completely...")
        
        # Method 1: Try to find and click the clear button (X) first
        try:
            clear_buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='reset'], .clear-search, .search-clear, .fa-times, .close, [aria-label='Clear']")
            for btn in clear_buttons:
                try:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        print("✅ Clicked clear button (X)")
                        time.sleep(1)
                        break
                except:
                    continue
        except:
            pass
        
        # Method 2: Find search input and clear it manually
        search_input = None
        search_selectors = [
            "input[placeholder*='Search']",
            "input[type='search']",
            "input.form-control[type='text']",
            ".dataTables_filter input",
            "#searchInput",
            "input[name='search']",
            "input[type='text']",
        ]
        
        for selector in search_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        search_input = element
                        print(f"✅ Found search input: {selector}")
                        
                        # Clear the input thoroughly
                        search_input.clear()
                        
                        # Also use JavaScript to ensure it's empty
                        driver.execute_script("arguments[0].value = '';", search_input)
                        
                        # Send Ctrl+A then Delete for complete clear
                        search_input.send_keys(Keys.CONTROL + "a")
                        search_input.send_keys(Keys.DELETE)
                        
                        print("✅ Completely cleared search input")
                        break
                if search_input:
                    break
            except:
                continue
        
        if not search_input:
            print("❌ Could not find search input")
            return None
        
        # Wait a bit after clearing
        time.sleep(1)
        
        # Now type the test number (full phone number)
        print(f"📝 Typing test number: {test_number}")
        
        # Type character by character to mimic human typing
        for char in test_number:
            search_input.send_keys(char)
            time.sleep(0.05)
        
        print(f"✅ Typed test number: {test_number}")
        
        # Press Enter to search
        search_input.send_keys(Keys.RETURN)
        print("✅ Pressed Enter to search")
        
        # Wait for search results to load
        time.sleep(4)
        
        # Wait for search results with timeout
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "tbody tr")) > 0 or 
                         "searching" not in d.page_source.lower() or
                         "processing" not in d.page_source.lower()
            )
        except TimeoutException:
            print("⚠️ Timeout waiting for search results")
        
        # Get all rows
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
        print(f"📊 Found {len(rows)} rows after search")
        
        if len(rows) == 0:
            print("❌ No rows found in search results")
            return None
        
        # Check each row for the EXACT test number match
        for i, row in enumerate(rows):
            try:
                row_text = row.text.strip()
                if not row_text or len(row_text) < 5:
                    continue
                
                # Display row for debugging
                print(f"  Row {i+1}: {row_text[:80]}...")
                
                # Check if test number is in the row text
                # Remove any spaces or special characters from test number for comparison
                clean_test_number = re.sub(r'[^\d]', '', test_number)
                
                # Extract all numbers from row
                row_numbers = re.findall(r'\d{10,15}', row_text)
                
                for row_num in row_numbers:
                    if row_num == clean_test_number:
                        print(f"✅ Found EXACT test number '{clean_test_number}' in row {i+1}")
                        print(f"   📋 Row data: {row_text[:100]}...")
                        return row
                        
                # Also check if test number appears anywhere in the text
                if clean_test_number in row_text:
                    print(f"✅ Found test number '{clean_test_number}' in row {i+1}")
                    return row
                        
            except Exception as e:
                print(f"   ❌ Error checking row {i+1}: {e}")
                continue
        
        print(f"❌ Test number '{test_number}' not found in search results")
        
        # Show first few rows for debugging
        print(f"📋 First 3 rows full content:")
        for i in range(min(3, len(rows))):
            try:
                row_text = rows[i].text
                print(f"  Row {i+1}: {row_text}")
            except:
                pass
        
        return None
        
    except Exception as e:
        print(f"❌ Error searching for test number: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_range_id_from_row(row):
    """Extract range ID from table row HTML"""
    try:
        row_html = row.get_attribute('outerHTML')
        
        # Try multiple patterns
        patterns = [
            r"TerminationDetials\('(\d+)'\)",
            r"showDetails\('(\d+)'\)",
            r"openModal\('(\d+)'\)",
            r"id=['\"](\d+)['\"]",
            r"data-id=['\"](\d+)['\"]",
            r"range['\"]?\s*[:=]\s*['\"]?(\d+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, row_html)
            if match:
                range_id = match.group(1)
                print(f"📊 Extracted range ID using pattern '{pattern}': {range_id}")
                return range_id
        
        print("❌ Could not extract range ID from row")
        
        # Try to find any number that might be ID
        numbers = re.findall(r'\b\d{4,7}\b', row_html)
        if numbers:
            print(f"📋 Found potential IDs: {numbers}")
            # Usually the first larger number is the ID
            for num in numbers:
                if len(num) >= 4:
                    print(f"   Using as ID: {num}")
                    return num
        
        return None
            
    except Exception as e:
        print(f"❌ Error extracting range ID: {e}")
        return None

def get_csrf_token():
    """Get CSRF token from page"""
    try:
        # Try to get token from meta tag first
        try:
            meta_token = driver.find_element(By.CSS_SELECTOR, "meta[name='csrf-token']")
            csrf_token = meta_token.get_attribute("content")
            if csrf_token:
                print(f"🔐 CSRF Token from meta: {csrf_token[:20]}...")
                return csrf_token
        except:
            pass
        
        # Try hidden input
        try:
            token_element = driver.find_element(By.NAME, "_token")
            csrf_token = token_element.get_attribute("value")
            if csrf_token:
                print(f"🔐 CSRF Token from input: {csrf_token[:20]}...")
                return csrf_token
        except:
            pass
        
        # Try to find in page source
        try:
            page_source = driver.page_source
            match = re.search(r'csrf-token["\']\s*content=["\']([^"\']+)["\']', page_source)
            if match:
                csrf_token = match.group(1)
                print(f"🔐 CSRF Token from regex: {csrf_token[:20]}...")
                return csrf_token
        except:
            pass
        
        print("❌ CSRF token not found")
        return None
            
    except Exception as e:
        print(f"❌ Error getting CSRF token: {e}")
        return None

async def add_range_via_js(range_id, csrf_token, test_number, range_name="Unknown"):
    """Add range using JavaScript - IMPROVED VERSION"""
    try:
        print(f"🔄 Adding range via JavaScript: {range_name} (Test: {test_number}, ID: {range_id})")
        
        # JavaScript to click "Add Number" button
        js_code = f"""
        console.log('🔄 Opening range details for {range_name}...');
        
        // First, open range details modal
        try {{
            TerminationDetials('{range_id}');
            console.log('✅ Called TerminationDetials for ID: {range_id}');
        }} catch (error) {{
            console.log('❌ Error calling TerminationDetials:', error);
            
            // Try alternative function name
            try {{
                showDetails('{range_id}');
                console.log('✅ Called showDetails instead');
            }} catch (error2) {{
                console.log('❌ Error calling showDetails:', error2);
                return false;
            }}
        }}
        
        // Wait for modal to load
        setTimeout(function() {{
            console.log('🔍 Looking for Add Number button...');
            
            // Method 1: Find by onclick attribute
            var addButtons = document.querySelectorAll('button[onclick*="AddNumbers"]');
            
            if (addButtons.length > 0) {{
                console.log('✅ Found Add Number button by onclick');
                addButtons[0].click();
                console.log('✅ Clicked Add Number button for range ' + '{range_name}');
                return true;
            }} 
            
            // Method 2: Find by text content
            var buttons = document.getElementsByTagName('button');
            for (var i = 0; i < buttons.length; i++) {{
                if (buttons[i].textContent.includes('Add Number') || 
                    buttons[i].textContent.includes('Add Range') ||
                    buttons[i].textContent.includes('Add')) {{
                    console.log('✅ Found Add Number button by text: ' + buttons[i].textContent);
                    buttons[i].click();
                    console.log('✅ Clicked Add Number button (by text)');
                    return true;
                }}
            }}
            
            // Method 3: Find in modal
            var modal = document.querySelector('.modal.show, .modal.fade.in');
            if (modal) {{
                var modalButtons = modal.querySelectorAll('button');
                for (var j = 0; j < modalButtons.length; j++) {{
                    if (modalButtons[j].textContent.includes('Add Number') || 
                        modalButtons[j].textContent.includes('Add')) {{
                        console.log('✅ Found Add Number button in modal');
                        modalButtons[j].click();
                        return true;
                    }}
                }}
            }}
            
            console.log('❌ Could not find Add Number button');
            
            // Try to take screenshot of current state
            try {{
                console.log('📸 Debug: Current modal HTML:', modal ? modal.innerHTML.substring(0, 500) : 'No modal found');
            }} catch (e) {{}}
            
            return false;
        }}, 3000);
        """
        
        print("📡 Executing JavaScript to add range...")
        result = driver.execute_script(js_code)
        
        # Wait for success
        time.sleep(5)
        
        # Check for success
        try:
            # Look for success alerts
            success_elements = driver.find_elements(By.CSS_SELECTOR, ".swal2-success, .alert-success, .toast-success, .success-message")
            if success_elements:
                for element in success_elements:
                    if element.is_displayed():
                        success_text = element.text.strip()
                        print(f"✅ Success notification: {success_text}")
                        
                        # Close the success modal if there's a close button
                        try:
                            close_buttons = driver.find_elements(By.CSS_SELECTOR, ".swal2-confirm, .swal2-close, .btn-close, .close")
                            for btn in close_buttons:
                                if btn.is_displayed():
                                    btn.click()
                                    print("✅ Closed success modal")
                                    time.sleep(1)
                                    break
                        except:
                            pass
                        
                        return True
            
            # Check page source
            page_source = driver.page_source.lower()
            success_indicators = ["success", "done add number", "added successfully", "range added", "numbers added"]
            for indicator in success_indicators:
                if indicator in page_source:
                    print(f"✅ Success message found in page: '{indicator}'")
                    
                    # Try to close any modal
                    try:
                        close_buttons = driver.find_elements(By.CSS_SELECTOR, "button:contains('OK'), button:contains('Close'), button:contains('Done')")
                        for btn in close_buttons:
                            if btn.is_displayed():
                                btn.click()
                                print("✅ Closed modal")
                                time.sleep(1)
                                break
                    except:
                        pass
                    
                    return True
            
            # Check for any modal text
            try:
                modals = driver.find_elements(By.CSS_SELECTOR, ".swal2-html-container, .modal-body, .alert")
                for modal in modals:
                    if modal.is_displayed():
                        modal_text = modal.text.lower()
                        if any(indicator in modal_text for indicator in success_indicators):
                            print(f"✅ Success in modal: {modal.text.strip()[:100]}")
                            
                            # Close the modal
                            try:
                                close_btn = modal.find_element(By.CSS_SELECTOR, ".btn-close, .close, [data-dismiss='modal']")
                                if close_btn:
                                    close_btn.click()
                                    print("✅ Closed modal")
                                    time.sleep(1)
                            except:
                                pass
                            
                            return True
            except:
                pass
            
            # Check for error messages
            error_elements = driver.find_elements(By.CSS_SELECTOR, ".alert-danger, .error, .text-danger")
            for error in error_elements:
                if error.is_displayed():
                    print(f"❌ Error message: {error.text.strip()}")
                    
                    # Try to close error modal
                    try:
                        close_buttons = driver.find_elements(By.CSS_SELECTOR, ".swal2-confirm, .btn-close, .close")
                        for btn in close_buttons:
                            if btn.is_displayed():
                                btn.click()
                                print("✅ Closed error modal")
                                time.sleep(1)
                                break
                    except:
                        pass
                    
                    return False
            
            print("⚠️ No success notification detected, but button was clicked")
            
            # Try to close any open modal anyway
            try:
                close_buttons = driver.find_elements(By.CSS_SELECTOR, ".btn-close, .close, [data-dismiss='modal'], [aria-label='Close']")
                for btn in close_buttons:
                    if btn.is_displayed():
                        btn.click()
                        print("✅ Closed any open modal")
                        time.sleep(1)
                        break
            except:
                pass
            
            # Return True because button was clicked and no error found
            return True
            
        except Exception as e:
            print(f"⚠️ Error checking success: {e}")
            return True
            
    except Exception as e:
        print(f"❌ JavaScript error: {str(e)[:200]}")
        return False

# =========================================================
# BULK RETURN - IMPROVED WITH PAGINATION HANDLING
# =========================================================

async def bulk_return_all_numbers():
    """Return all numbers - WITH PAGINATION HANDLING"""
    try:
        print("🔄 Navigating to numbers page for bulk return...")
        
        if not navigate_to_return_numbers_page():
            return False
        
        time.sleep(3)
        
        print("="*60)
        print("🔍 STEP 1: Handling pagination to show ALL numbers...")
        print("="*60)
        
        # FIRST: Change pagination to show ALL numbers (1000)
        try:
            print("🔧 Looking for pagination dropdown (Show entries)...")
            
            # Try multiple selectors for pagination dropdown
            pagination_selectors = [
                "select[name='myTable_length']",
                "select[name='length']",
                ".dataTables_length select",
                "select.form-control",
                "select",
            ]
            
            pagination_select = None
            for selector in pagination_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed() and element.tag_name == "select":
                            pagination_select = element
                            print(f"✅ Found pagination dropdown: {selector}")
                            break
                    if pagination_select:
                        break
                except:
                    continue
            
            if pagination_select:
                # Create Select object
                select = Select(pagination_select)
                
                # Try different methods to select 1000
                try:
                    select.select_by_value("1000")
                    print("✅ Changed pagination to 1000 entries (by value)")
                except:
                    try:
                        select.select_by_visible_text("1000")
                        print("✅ Changed pagination to 1000 entries (by text)")
                    except:
                        try:
                            # Get all options and find 1000
                            options = select.options
                            for i, option in enumerate(options):
                                if "1000" in option.text:
                                    select.select_by_index(i)
                                    print(f"✅ Changed pagination to 1000 entries (index {i})")
                                    break
                        except:
                            try:
                                # Try 500 if 1000 not available
                                select.select_by_value("500")
                                print("✅ Changed pagination to 500 entries")
                            except:
                                try:
                                    select.select_by_visible_text("500")
                                    print("✅ Changed pagination to 500 entries")
                                except:
                                    print("⚠️ Could not change pagination, using default")
                
                # Wait for table to reload with all numbers
                print("⏳ Waiting for all numbers to load (15 seconds)...")
                time.sleep(15)
                
                # Check table size after pagination change
                try:
                    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
                    print(f"📊 After pagination change: {len(rows)} rows visible")
                    
                    if len(rows) == 0:
                        print("⚠️ No rows found after pagination change")
                        # Try refreshing
                        driver.refresh()
                        time.sleep(5)
                except:
                    pass
            else:
                print("⚠️ No pagination dropdown found")
                
        except Exception as e:
            print(f"⚠️ Error handling pagination: {e}")
        
        print("="*60)
        print("🔍 STEP 2: Looking for and selecting ALL checkboxes...")
        print("="*60)
        
        # SECOND: Find and select ALL checkboxes
        checkboxes = []
        
        # Wait a bit for table to fully load
        time.sleep(3)
        
        # Try multiple selectors for checkboxes
        checkbox_selectors = [
            "tbody input[type='checkbox']",
            "td input[type='checkbox']",
            "tr input[type='checkbox']",
            "input[type='checkbox']:not([id*='all']):not([name*='all'])",
            ".select-checkbox",
            ".number-checkbox",
        ]
        
        for selector in checkbox_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, selector)
                if found:
                    # Filter only visible checkboxes
                    checkboxes = [cb for cb in found if cb.is_displayed()]
                    if checkboxes:
                        print(f"✅ Found {len(checkboxes)} visible checkboxes using: {selector}")
                        break
            except:
                continue
        
        # If no checkboxes found, try scanning entire page
        if not checkboxes or len(checkboxes) == 0:
            print("🔍 Scanning entire page for checkboxes...")
            try:
                all_inputs = driver.find_elements(By.TAG_NAME, "input")
                for inp in all_inputs:
                    try:
                        if inp.get_attribute("type") == "checkbox" and inp.is_displayed():
                            # Check if it's in a table row (not header)
                            try:
                                parent_tr = inp.find_element(By.XPATH, "./ancestor::tr")
                                parent_tbody = inp.find_element(By.XPATH, "./ancestor::tbody")
                                if parent_tr and parent_tbody:
                                    checkboxes.append(inp)
                            except:
                                pass
                    except:
                        continue
                
                print(f"📊 Found {len(checkboxes)} checkboxes by scanning")
            except Exception as e:
                print(f"❌ Error scanning for checkboxes: {e}")
        
        # Try to find and use "Select All" checkbox in header if available
        header_select_all = None
        try:
            header_selectors = [
                "thead input[type='checkbox']",
                "th input[type='checkbox']",
                "input.select-all",
                "#selectAll",
                "input[type='checkbox'][id*='all']",
                "input[type='checkbox'][name*='all']",
            ]
            
            for selector in header_selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        header_select_all = element
                        print(f"✅ Found header 'Select All' checkbox: {selector}")
                        break
                except:
                    continue
        except:
            pass
        
        # SELECTION STRATEGY
        if header_select_all:
            # Strategy 1: Use header select all if available
            print("🎯 Using header 'Select All' checkbox")
            try:
                if not header_select_all.is_selected():
                    header_select_all.click()
                    print("✅ Clicked header 'Select All' checkbox")
                    time.sleep(2)
                else:
                    print("✅ Header 'Select All' already checked")
            except Exception as e:
                print(f"❌ Error clicking header select all: {e}")
                header_select_all = None
        
        if not header_select_all and checkboxes and len(checkboxes) > 0:
            # Strategy 2: Select all individual checkboxes
            print(f"🎯 Selecting all {len(checkboxes)} individual checkboxes...")
            
            total_checkboxes = len(checkboxes)
            selected_count = 0
            
            for i, checkbox in enumerate(checkboxes):
                try:
                    if checkbox.is_displayed() and checkbox.is_enabled():
                        # Scroll to checkbox
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkbox)
                        time.sleep(0.05)
                        
                        # Check if already selected
                        if not checkbox.is_selected():
                            # Use JavaScript click
                            driver.execute_script("arguments[0].click();", checkbox)
                            selected_count += 1
                            
                            # Show progress
                            if selected_count % 50 == 0:
                                print(f"   ✅ Selected {selected_count}/{total_checkboxes} checkboxes")
                            
                            # Small delay to avoid overwhelming
                            if selected_count % 100 == 0:
                                time.sleep(0.5)
                except Exception as e:
                    print(f"   ❌ Error with checkbox {i+1}: {e}")
                    continue
            
            print(f"📊 Successfully selected {selected_count}/{total_checkboxes} checkboxes")
        
        # Verify selection
        time.sleep(2)
        try:
            if checkboxes:
                selected_count = len([cb for cb in checkboxes if cb.is_selected()])
                print(f"📋 Verification: {selected_count} checkboxes are selected")
                
                if selected_count == 0:
                    print("❌ No checkboxes selected, cannot proceed")
                    return False
        except:
            pass
        
        print("="*60)
        print("🔍 STEP 3: Looking for bulk return button...")
        print("="*60)
        
        # THIRD: Find and click bulk return button
        bulk_button = None
        bulk_button_selectors = [
            ("#BluckButton", "ID BluckButton"),
            ("button[onclick*='bulkReturn']", "onclick attribute"),
            ("button:contains('Bulk return')", "text 'Bulk return'"),
            ("button:contains('Bulk Return')", "text 'Bulk Return'"),
            (".btn-warning", "warning button class"),
            (".btn-danger", "danger button class"),
            ("button.btn-primary", "primary button"),
        ]
        
        for selector, desc in bulk_button_selectors:
            try:
                if "contains" in selector:
                    # XPath for text contains (case insensitive)
                    bulk_button = driver.find_element(By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bulk return')]")
                else:
                    bulk_button = driver.find_element(By.CSS_SELECTOR, selector)
                
                if bulk_button and bulk_button.is_displayed():
                    print(f"✅ Found bulk button: {desc}")
                    print(f"   Text: {bulk_button.text.strip()}")
                    print(f"   Enabled: {bulk_button.is_enabled()}")
                    break
            except:
                continue
        
        if not bulk_button:
            print("❌ Could not find bulk return button")
            return False
        
        # Check if button is enabled
        if not bulk_button.is_enabled():
            print("⚠️ Bulk button is disabled")
            
            # Check selection status
            try:
                if checkboxes:
                    selected = len([cb for cb in checkboxes if cb.is_selected()])
                    print(f"📋 {selected} checkboxes are selected")
                    
                    if selected == 0:
                        print("❌ No checkboxes selected")
                        
                        # Try to select a few checkboxes manually
                        print("🔄 Trying to select some checkboxes...")
                        for i in range(min(5, len(checkboxes))):
                            try:
                                if not checkboxes[i].is_selected():
                                    checkboxes[i].click()
                                    print(f"   ✅ Selected checkbox {i+1}")
                                    time.sleep(0.5)
                            except:
                                pass
                        
                        time.sleep(2)
                        
                        # Check button again
                        if bulk_button.is_enabled():
                            print("✅ Bulk button now enabled!")
                        else:
                            return False
            except:
                pass
            
            if not bulk_button.is_enabled():
                print("❌ Bulk button still disabled after selection")
                return False
        
        print("✅ Clicking bulk return button...")
        
        # Click the button
        try:
            # Scroll to button
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", bulk_button)
            time.sleep(1)
            
            # Use JavaScript click for reliability
            driver.execute_script("arguments[0].click();", bulk_button)
            print("✅ Clicked bulk button via JavaScript")
        except Exception as e:
            print(f"❌ Failed to click bulk button: {e}")
            return False
        
        time.sleep(3)
        
        print("="*60)
        print("🔍 STEP 4: Looking for confirmation modal...")
        print("="*60)
        
        # FOURTH: Handle confirmation modal
        confirm_button = None
        
        # Wait for modal to appear
        for attempt in range(15):
            try:
                # Look for "Yes, Return" button (exact text from screenshot)
                confirm_button = driver.find_element(By.XPATH, "//button[contains(., 'Yes, Return') or contains(., 'Yes,Return')]")
                if confirm_button and confirm_button.is_displayed():
                    print(f"✅ Found 'Yes, Return' button on attempt {attempt+1}")
                    break
                
                # Alternative: Look for buttons in modal
                try:
                    # Find any modal
                    modals = driver.find_elements(By.CSS_SELECTOR, ".modal.show, .swal2-show, .modal-dialog")
                    for modal in modals:
                        if modal.is_displayed():
                            buttons = modal.find_elements(By.TAG_NAME, "button")
                            for btn in buttons:
                                if btn.is_displayed():
                                    btn_text = btn.text.strip().lower()
                                    if "yes" in btn_text or "return" in btn_text or "confirm" in btn_text:
                                        confirm_button = btn
                                        print(f"✅ Found confirmation button in modal: {btn_text}")
                                        break
                            if confirm_button:
                                break
                except:
                    pass
                
                if confirm_button:
                    break
                    
            except:
                pass
            
            time.sleep(1)
            if attempt < 10:
                print(f"⏳ Waiting for confirmation modal... (attempt {attempt + 1})")
        
        if not confirm_button:
            print("❌ Could not find confirmation button")
            return False
        
        print(f"✅ Confirmation button text: {confirm_button.text.strip()}")
        
        # Click confirmation button
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", confirm_button)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", confirm_button)
            print("✅ Clicked 'Yes, Return' via JavaScript")
        except:
            try:
                confirm_button.click()
                print("✅ Clicked 'Yes, Return' normally")
            except Exception as e:
                print(f"❌ Failed to click confirmation: {e}")
                return False
        
        time.sleep(5)
        
        print("="*60)
        print("🔍 STEP 5: Looking for success notification...")
        print("="*60)
        
        # FIFTH: Check for success
        success_found = False
        
        for attempt in range(10):
            try:
                # Check for success message
                success_elements = driver.find_elements(By.CSS_SELECTOR, ".alert-success, .swal2-success, .toast-success, .success")
                for element in success_elements:
                    if element.is_displayed():
                        success_text = element.text.strip()
                        print(f"✅ Success message: {success_text}")
                        success_found = True
                        break
                
                if success_found:
                    break
                
                # Check page source
                page_source = driver.page_source.lower()
                success_indicators = ["success", "returned", "done", "completed", "successfully"]
                for indicator in success_indicators:
                    if indicator in page_source:
                        print(f"✅ Found success indicator: '{indicator}'")
                        success_found = True
                        break
                
                if success_found:
                    break
                
                # Look for OK/Close button
                try:
                    close_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'OK') or contains(., 'Ok') or contains(., 'Close') or contains(., 'Done')]")
                    for btn in close_buttons:
                        if btn and btn.is_displayed():
                            print(f"✅ Found close button: {btn.text.strip()}")
                            btn.click()
                            success_found = True
                            time.sleep(1)
                            break
                except:
                    pass
                
            except:
                pass
            
            time.sleep(1)
        
        if not success_found:
            print("⚠️ No explicit success notification found")
            print("ℹ️ Operation may have succeeded silently")
        
        print("✅ Bulk return process completed!")
        
        # Final verification
        time.sleep(3)
        try:
            # Check if table is now empty
            page_text = driver.page_source.lower()
            empty_indicators = [
                "no data", 
                "0 entries", 
                "showing 0 to 0", 
                "no records",
                "empty table"
            ]
            
            for indicator in empty_indicators:
                if indicator in page_text:
                    print(f"✅ Verification: Table is empty ('{indicator}')")
                    break
            else:
                print("⚠️ Verification: Table may still contain numbers")
                
                # Check row count
                try:
                    rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
                    if rows:
                        visible_rows = [r for r in rows if r.is_displayed() and r.text.strip()]
                        print(f"📊 Still showing {len(visible_rows)} rows")
                except:
                    pass
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"❌ Error in bulk_return_all_numbers: {e}")
        import traceback
        traceback.print_exc()
        return False

# =========================================================
# Live SMS Monitoring - IMPROVED VERSION
# =========================================================

def monitor_live_sms():
    """Monitor Live SMS for new messages"""
    entries = []
    global driver
    
    if not driver:
        if not init_driver():
            return entries
    
    try:
        print("📡 Monitoring Live SMS for new messages...")
        
        if current_page != "live_sms":
            if not navigate_to_live_sms(force_return=True):
                print("❌ Failed to navigate to Live SMS page")
                return entries
        
        time.sleep(3)
        
        # First, check if we're really on the right page
        try:
            page_url = driver.current_url
            page_title = driver.title
            print(f"🌐 Current URL: {page_url}")
            print(f"📄 Page Title: {page_title}")
            
            # Check if we're logged in
            if "login" in page_url.lower():
                print("⚠️ Redirected to login page, attempting to relogin...")
                if not login_and_fetch_token():
                    return entries
                time.sleep(3)
            
            # Refresh page if needed
            if "live" not in page_url.lower() and "portal" not in page_url.lower():
                print("⚠️ Not on portal page, refreshing...")
                navigate_to_live_sms(force_return=True)
                time.sleep(3)
        except Exception as e:
            print(f"⚠️ Error checking page: {e}")
        
        # Try multiple methods to find the table
        table = None
        table_selectors = [
            "#LiveTestSMS",
            "#liveSmsTable",
            "table.dataTable",
            "table.table",
            "table",
            ".dataTable",
            "[id*='live']",
            "[id*='sms']",
        ]
        
        for selector in table_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed():
                        table = element
                        print(f"✅ Found visible table using selector: {selector}")
                        break
                if table:
                    break
            except:
                continue
        
        if not table:
            print("❌ Could not find Live SMS table")
            return entries
        
        # Try to get rows using different methods
        rows = []
        try:
            # Method 1: Direct table rows
            rows = table.find_elements(By.TAG_NAME, "tr")
            print(f"📊 Found {len(rows)} rows in Live SMS table")
            
            # If no rows or only header, try alternative
            if len(rows) <= 1:
                # Method 2: Look for tbody rows
                try:
                    tbody = table.find_element(By.TAG_NAME, "tbody")
                    tbody_rows = tbody.find_elements(By.TAG_NAME, "tr")
                    if tbody_rows:
                        rows = tbody_rows
                        print(f"📊 Found {len(rows)} rows in tbody")
                except:
                    pass
                
                # Method 3: Check if it's a DataTable with loading
                try:
                    loading = driver.find_element(By.CSS_SELECTOR, ".dataTables_processing")
                    if loading.is_displayed() and "display: none" not in loading.get_attribute("style"):
                        print("⏳ DataTable is loading, waiting...")
                        time.sleep(5)
                        
                        # Try again after waiting
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        print(f"📊 After wait: {len(rows)} rows")
                except:
                    pass
        except Exception as e:
            print(f"❌ Error getting rows: {e}")
            return entries
        
        # Process rows if we have them
        if rows and len(rows) > 0:
            print(f"🔍 Processing {len(rows)} rows...")
            
            for i, row in enumerate(rows):
                try:
                    # Skip if row is empty or is a header
                    row_text = row.text.strip()
                    if not row_text or len(row_text) < 5:
                        continue
                    
                    # Skip "No data" rows
                    if "no data" in row_text.lower() or "no records" in row_text.lower():
                        continue
                    
                    # Skip loading indicators
                    if "loading" in row_text.lower() or "processing" in row_text.lower():
                        continue
                    
                    print(f"\n📊 Row {i+1}: {row_text[:100]}...")
                    
                    # Try to extract columns
                    cols = []
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 2:
                            cols = row.find_elements(By.TAG_NAME, "th")
                    except:
                        continue
                    
                    if len(cols) >= 5:
                        try:
                            # Extract message content
                            message_content = ""
                            if len(cols) > 4:
                                message_content = cols[4].text.strip()
                            elif len(cols) > 3:
                                message_content = cols[3].text.strip()
                            
                            # Extract range/phone info
                            range_info = cols[0].text.strip() if len(cols) > 0 else ""
                            
                            # Extract phone number
                            phone = ""
                            phone_match = re.search(r'\b(?:\+\d{1,4}[-.\s]?)?\d{10,15}\b', range_info)
                            if phone_match:
                                phone = re.sub(r'[^\d]', '', phone_match.group())
                                print(f"   📱 Phone: {phone}")
                            else:
                                # Try to extract from message content
                                phone_match = re.search(r'\b(?:\+\d{1,4}[-.\s]?)?\d{10,15}\b', message_content)
                                if phone_match:
                                    phone = re.sub(r'[^\d]', '', phone_match.group())
                                    print(f"   📱 Phone (from message): {phone}")
                            
                            # Extract OTP if message exists
                            if message_content and message_content.strip():
                                otps = extract_otps(message_content)
                                if otps:
                                    otp = otps[0]
                                    service = detect_service(message_content)
                                    country = detect_country(phone, range_info)
                                    
                                    # Check for duplicates
                                    is_duplicate = False
                                    for entry in entries:
                                        if entry['number'] == phone and entry['otp'] == otp:
                                            is_duplicate = True
                                            break
                                    
                                    if not is_duplicate and phone:
                                        entries.append({
                                            "number": phone,
                                            "otp": otp,
                                            "full_msg": message_content,
                                            "service": service,
                                            "country": country,
                                            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        })
                                        
                                        print(f"   🎉 FOUND OTP: {otp} for {phone} ({service})")
                                else:
                                    print(f"   ❌ No OTP found in message")
                            else:
                                print(f"   ⚠️ No message content")
                                
                        except Exception as col_error:
                            print(f"   ❌ Error processing columns: {col_error}")
                    else:
                        print(f"   ⚠️ Not enough columns ({len(cols)})")
                        
                except Exception as row_error:
                    print(f"   ❌ Error processing row {i+1}: {row_error}")
                    continue
        else:
            print("📭 No data rows found in Live SMS table")
        
        print(f"\n📊 Live SMS monitoring results: {len(entries)} OTPs found")
        
        return entries
        
    except Exception as e:
        print(f"❌ Error monitoring Live SMS: {e}")
        import traceback
        traceback.print_exc()
        return entries

# =========================================================
# Main Range Adding Function - BY TEST NUMBER
# =========================================================

async def add_multiple_ranges_by_test_number(test_number_list, message):
    """Add multiple ranges using test numbers - WITH TELEGRAM UPDATES"""
    try:
        print(f"🚀 Starting to add {len(test_number_list)} ranges by test number")
        
        # Navigate to add range page
        if not navigate_to_add_range_page():
            print("❌ Failed to navigate to add range page")
            await message.answer("❌ Failed to navigate to add range page")
            return False, []
        
        time.sleep(2)
        
        # Get CSRF token once
        csrf_token = get_csrf_token()
        if not csrf_token:
            print("❌ Cannot proceed without CSRF token")
            await message.answer("❌ Cannot proceed without CSRF token")
            return False, []
        
        added_ranges = []
        failed_ranges = []
        
        for i, test_number in enumerate(test_number_list, 1):
            try:
                print(f"\n{'='*60}")
                print(f"📦 [{i}/{len(test_number_list)}] Processing test number: {test_number}")
                print('='*60)
                
                # Send Telegram update
                await message.answer(f"📝 **Processing {i}/{len(test_number_list)}**\n🔍 Searching for: `{test_number}`")
                
                # Search for this test number
                row = search_for_range_by_test_number(test_number)
                if not row:
                    print(f"❌ Test number '{test_number}' not found")
                    await message.answer(f"❌ **Test number NOT FOUND:** `{test_number}`")
                    failed_ranges.append(test_number)
                    continue
                
                # Extract range ID
                range_id = extract_range_id_from_row(row)
                if not range_id:
                    print(f"❌ Could not extract ID for test number '{test_number}'")
                    await message.answer(f"❌ **Cannot extract ID:** `{test_number}`")
                    failed_ranges.append(test_number)
                    continue
                
                # Extract range name from row for display purposes
                range_name = "Unknown Range"
                try:
                    row_text = row.text
                    if '|' in row_text:
                        columns = [col.strip() for col in row_text.split('|')]
                        if columns:
                            range_name = columns[0]
                    else:
                        words = row_text.split()
                        if len(words) > 1:
                            range_name = ' '.join(words[:2])
                except:
                    pass
                
                print(f"🎯 Test number '{test_number}' found with ID: {range_id}")
                print(f"📋 Range name: {range_name}")
                
                # Send Telegram update
                await message.answer(f"✅ **Found Range!**\n📱 Test: `{test_number}`\n🏷️ Range: {range_name}\n🆔 ID: `{range_id}`\n⏳ Adding...")
                
                # Add the range
                success = await add_range_via_js(range_id, csrf_token, test_number, range_name)
                
                if success:
                    added_ranges.append(f"{range_name} ({test_number})")
                    print(f"✅ Successfully added range via test number: {test_number}")
                    
                    # Send SUCCESS Telegram message
                    await message.answer(f"🎉 **SUCCESSFULLY ADDED!**\n✅ Range: {range_name}\n📱 Test: `{test_number}`\n🆔 ID: `{range_id}`")
                    
                    # REFRESH THE PAGE for next search
                    print("🔄 Refreshing page for next search...")
                    if i < len(test_number_list):
                        time.sleep(2)
                        driver.refresh()
                        time.sleep(3)
                        print("✅ Page refreshed, ready for next search")
                        
                        # Send update
                        await message.answer(f"🔄 Page refreshed, moving to next number...")
                        
                else:
                    failed_ranges.append(test_number)
                    print(f"❌ Failed to add via test number: {test_number}")
                    await message.answer(f"❌ **FAILED to add:** `{test_number}`")
                
                # Wait between ranges
                if i < len(test_number_list):
                    wait_time = 3
                    print(f"⏳ Waiting {wait_time} seconds before next test number...")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                print(f"❌ Error with test number '{test_number}': {e}")
                await message.answer(f"❌ **ERROR:** `{test_number}`\n📝 Error: {str(e)[:100]}")
                failed_ranges.append(test_number)
                continue
        
        print(f"\n{'='*60}")
        print("📊 RANGE ADDING COMPLETE (BY TEST NUMBER)")
        print(f"✅ Successfully added: {len(added_ranges)} ranges")
        print(f"❌ Failed: {len(failed_ranges)} ranges")
        
        # FINAL REPORT TO TELEGRAM
        final_report = f"📊 **RANGE ADDING COMPLETE!**\n\n"
        final_report += f"✅ **Successfully Added:** {len(added_ranges)}\n"
        final_report += f"❌ **Failed:** {len(failed_ranges)}\n\n"
        
        if added_ranges:
            final_report += "📋 **Added Ranges:**\n"
            for i, r in enumerate(added_ranges[:5]):  # Show first 5
                final_report += f"  {i+1}. {r}\n"
            if len(added_ranges) > 5:
                final_report += f"  ... and {len(added_ranges)-5} more\n"
        
        if failed_ranges:
            final_report += "\n❌ **Failed Test Numbers:**\n"
            for i, f in enumerate(failed_ranges[:3]):  # Show first 3
                final_report += f"  {i+1}. `{f}`\n"
            if len(failed_ranges) > 3:
                final_report += f"  ... and {len(failed_ranges)-3} more\n"
        
        await message.answer(final_report)
        
        # AUTOMATICALLY RETURN TO LIVE SMS PAGE
        print("\n🌐 Automatically returning to Live SMS page...")
        await message.answer("🌐 **Returning to Live SMS monitoring...**")
        navigate_to_live_sms()
        
        return len(added_ranges) > 0, added_ranges
        
    except Exception as e:
        print(f"❌ Error in add_multiple_ranges_by_test_number: {e}")
        import traceback
        traceback.print_exc()
        
        await message.answer(f"❌ **CRITICAL ERROR in range adding:**\n{str(e)[:200]}")
        
        # Try to return to Live SMS even if there's an error
        try:
            print("\n🔄 Attempting to return to Live SMS page after error...")
            navigate_to_live_sms()
        except:
            pass
        
        return False, []


# =========================================================
# Worker Function
# =========================================================

async def worker():
    db.set_status("online")
    await bot.send_message(config.ADMIN_ID, "✅ Live SMS Worker started!")
    global _worker_running
    _worker_running = True
    
    db.cleanup_old_data()
    
    # Verify we're on Live SMS page
    if not navigate_to_live_sms(force_return=True):
        print("❌ FAILED TO REACH LIVE SMS PAGE!")
        await bot.send_message(config.ADMIN_ID, "❌ Failed to access Live SMS page!")
        stop_worker_task()
        return
    
    print("🚀 Starting CONTINUOUS monitoring...")
    
    sent_count = 0
    empty_checks = 0
    max_empty_checks = 5
    
    while _worker_running:
        try:
            print("\n" + "="*60)
            print("🔄 Checking for new Live SMS OTPs...")
            print("="*60)
            
            # Refresh page periodically if getting no data
            if empty_checks >= max_empty_checks:
                print(f"🔄 Refreshing Live SMS page (empty_checks={empty_checks})...")
                navigate_to_live_sms(force_return=True)
                empty_checks = 0
                time.sleep(3)
            
            if current_page != "live_sms":
                print(f"⚠️ Not on Live SMS page (currently on: {current_page}). Returning...")
                navigate_to_live_sms(force_return=True)
                time.sleep(2)
            
            entries = monitor_live_sms()
            
            if entries:
                print(f"📊 Found {len(entries)} new Live SMS OTP entries")
                empty_checks = 0
                
                for e in entries:
                    if not db.otp_exists(e["number"], e["otp"]) and not db.otp_recently_sent(e["number"], e["otp"]):
                        try:
                            db.save_otp(e["number"], e["otp"], e["full_msg"], e["service"], e["country"], "")
                        except Exception as db_error:
                            print(f"⚠️ Error saving Live SMS OTP: {db_error}")
                        
                        print(f"🚀 Sending OTP {e['otp']} immediately...")
                        success = await forward_entry(e)
                        if success:
                            sent_count += 1
                            print(f"✅ OTP {e['otp']} sent immediately!")
                        else:
                            print(f"❌ Failed to send OTP {e['otp']}")
                    else:
                        print(f"⏭️ Live SMS OTP {e['otp']} already exists, skipping")
            else:
                print("📭 No new OTPs found")
                empty_checks += 1
                print(f"📊 Empty checks counter: {empty_checks}/{max_empty_checks}")
            
            wait_time = 3
            print(f"\n⏳ Waiting {wait_time} seconds before next check...")
            print("="*60)
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            print(f"❌ Error in Live SMS worker: {e}")
            import traceback
            traceback.print_exc()
            
            empty_checks += 1
            
            try:
                print("🔄 Attempting to return to Live SMS page after error...")
                navigate_to_live_sms(force_return=True)
            except:
                pass
            
            await asyncio.sleep(5)
    
    db.set_status("offline")
    await bot.send_message(config.ADMIN_ID, f"🛑 Live SMS Worker stopped. Total sent: {sent_count}")

def stop_worker_task():
    global _worker_running, _worker_task
    if not _worker_running:
        return
    _worker_running = False
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
    close_driver()

# =========================================================
# Helper Functions
# =========================================================

def mask_number(num: str) -> str:
    s = num.strip()
    if len(s) <= (config.MASK_PREFIX_LEN + config.MASK_SUFFIX_LEN):
        return s
    return s[:config.MASK_PREFIX_LEN] + "****" + s[-config.MASK_SUFFIX_LEN:]

def detect_service(text: str) -> str:
    t = (text or "").lower()
    
    arabic_services = {
        'واتساب': 'WhatsApp',
        'تليجرام': 'Telegram',
        'فيسبوك': 'Facebook',
        'انستغرام': 'Instagram',
        'تويتر': 'Twitter',
        'جوجل': 'Google',
        'بايبال': 'PayPal',
        'امازون': 'Amazon',
        'بنك': 'Bank',
        'بنكي': 'Bank',
        'فيزا': 'Visa',
        'ماستركارد': 'Mastercard',
        'أبل': 'Apple',
        'ابل': 'Apple',
        'مايكروسوفت': 'Microsoft',
        'ياهو': 'Yahoo',
    }
    
    for arabic, english in arabic_services.items():
        if arabic in t:
            return english
    
    for k in sorted(config.SERVICES.keys(), key=len, reverse=True):
        if k in t:
            return config.SERVICES[k]
    
    if "twilio" in t:
        return "Twilio"
    
    if 'whatsapp' in t or 'واتساب' in t or 'code whatsapp' in t:
        return "WhatsApp"
    
    return "Unknown Service"

def detect_country(number: str, extra_text: str = "") -> str:
    s = number.lstrip("+")
    for prefix, flagname in config.COUNTRY_FLAGS.items():
        if s.startswith(prefix):
            return flagname
    txt = (extra_text or "").upper()
    if "PERU" in txt:
        return config.COUNTRY_FLAGS.get("51", "🇵🇪 Peru")
    if "BANGLADESH" in txt or "+880" in number:
        return config.COUNTRY_FLAGS.get("880", "🇧🇩 Bangladesh")
    if "NIGERIA" in txt or "+234" in number:
        return "🇳🇬 Nigeria"
    if "EGYPT" in txt or "+20" in number:
        return "🇪🇬 Egypt"
    if "SAUDI" in txt or "+966" in number:
        return "🇸🇦 Saudi Arabia"
    if "UAE" in txt or "+971" in number:
        return "🇦🇪 UAE"
    if "QATAR" in txt or "+974" in number:
        return "🇶🇦 Qatar"
    if "KUWAIT" in txt or "+965" in number:
        return "🇰🇼 Kuwait"
    return "🌍 Unknown"

def extract_whatsapp_code(text: str):
    if not text:
        return None
    
    text = text.strip()
    
    patterns = [
        r'(?:رمز واتساب|كود واتساب|واتساب)[\s:]*[:؛]?[\s]*(\d{3}[-.\s]\d{3})',
        r'(?:Code WhatsApp|WhatsApp code|WhatsApp)[\s:]*[:؛]?[\s]*(\d{3}[-.\s]\d{3})',
        r'(?:لا تشارك|لا تشارك رمز)[\s:]+(?:واتساب)?[\s:]*(\d{3}[-.\s]\d{3})',
        r'(?:Do not share|Don\'t share)[\s:]+(?:WhatsApp)?[\s:]*(\d{3}[-.\s]\d{3})',
        r'\b(\d{3}[-.\s]\d{3})\b',
        r'(?:whatsapp|واتساب)[\s:]*(\d{6})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
        if match:
            code = match.group(1)
            clean_code = re.sub(r'[^\d]', '', code)
            if len(clean_code) == 6:
                print(f"📱 Found WhatsApp code: {clean_code}")
                return clean_code
    
    return None

def extract_otps(text: str):
    if not text:
        return []
    
    text = text.strip()
    text = html.unescape(text)
    
    print(f"🔍 Raw text for OTP extraction: {text[:200]}...")
    
    whatsapp_code = extract_whatsapp_code(text)
    if whatsapp_code:
        print(f"🎯 PRIORITY 1: Found WhatsApp code: {whatsapp_code}")
        return [whatsapp_code]
    
    has_arabic = bool(re.search(r'[\u0600-\u06FF]', text))
    if has_arabic:
        print("🔤 Text contains Arabic characters")
    
    clean_text = re.sub(r'\+\d{10,15}', '', text)
    clean_text = re.sub(r'\b\d{10,15}\b', '', text)
    
    if has_arabic:
        arabic_patterns = [
            r'(?:رمز|كود|الرمز|الكود)[\s:]*[:؛]?[\s]*(\d{6})\b',
            r'(?:رمز|كود)[\s]+(?:التحقق|التفعيل)[\s:]*[:؛]?[\s]*(\d{6})\b',
            r'(\d{6})[\s]+(?:هو|هي)[\s]+(?:الرمز|الكود|رمز|код)',
        ]
        
        for pattern in arabic_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE | re.UNICODE)
            if match:
                otp = match.group(1)
                otp = re.sub(r'[^\d]', '', otp)
                
                if len(otp) == 6:
                    if len(set(otp)) == 1:
                        continue
                    if otp in ['123456', '111111', '222222', '333333', '444444', '555555']:
                        continue
                    
                    print(f"📘 PRIORITY 2: Found Arabic OTP: {otp}")
                    return [otp]
    
    six_digit_pattern = r'\b\d{6}\b'
    six_digit_matches = re.findall(six_digit_pattern, clean_text)
    
    valid_6_digit_otps = []
    for otp in six_digit_matches:
        if len(set(otp)) == 1:
            continue
        
        common_fake_otps = ['123456', '111111', '222222', '333333', '444444', '555555',
                          '666666', '777777', '888888', '999999', '000000',
                          '654321', '012345', '543210']
        if otp in common_fake_otps:
            continue
        
        sequences = ['123456', '234567', '345678', '456789', '567890',
                    '098765', '987654', '876543', '765432', '654321']
        if otp in sequences:
            continue
        
        valid_6_digit_otps.append(otp)
    
    if valid_6_digit_otps:
        print(f"📗 PRIORITY 3: Found 6-digit OTP: {valid_6_digit_otps[0]}")
        return [valid_6_digit_otps[0]]
    
    universal_patterns = [
        r'\b(?:code|otp|verification|رمز|كود)[\s:]*[:؛]?[\s]*(\d{4,6})\b',
        r'\b(\d{4,6})\b[\s]+(?:is|are|رمز|код|code|otp|verification)',
        r'[\[\(\{]\s*(\d{4,6})\s*[\]\)\}]',
        r'[:؛]\s*(\d{4,6})\b',
    ]
    
    for pattern in universal_patterns:
        matches = re.findall(pattern, clean_text, re.IGNORECASE | re.UNICODE)
        for otp in matches:
            otp = re.sub(r'[^\d]', '', otp)
            
            if 4 <= len(otp) <= 6:
                if len(set(otp)) == 1:
                    continue
                
                if len(otp) == 6:
                    print(f"📓 PRIORITY 4: Found 6-digit OTP via pattern: {otp}")
                    return [otp]
                elif len(otp) >= 4:
                    print(f"📓 PRIORITY 4: Found {len(otp)}-digit OTP via pattern: {otp}")
                    return [otp]
    
    print(f"❌ No valid OTP found in text")
    return []

async def forward_entry(e):
    if db.otp_recently_sent(e["number"], e["otp"]):
        print(f"⏭️ OTP {e['otp']} was already sent recently, skipping")
        return False
    
    num_display = mask_number(e["number"])
    
    full_msg_text = e.get('full_msg', '')
    full_msg_text = html.unescape(full_msg_text)
    
    if '<' in full_msg_text and '>' in full_msg_text:
        soup = BeautifulSoup(full_msg_text, 'html.parser')
        full_msg_text = soup.get_text(strip=True)
    
    full_msg_text = full_msg_text.strip()
    
    if len(full_msg_text) < 5:
        full_msg_text = "No full message received"
    
    if len(full_msg_text) > 500:
        full_msg_text = full_msg_text[:500] + "..."
    
    escaped_full_msg = html.escape(full_msg_text)
    otp_to_display = e.get('otp', '')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    text = (
        f"🔔 <b> NEW LIVE SMS OTP DETECTED </b>\n\n"
        f"🕰 <b>Time:</b> {now}\n"
        f"🌍 <b>Country:</b> {e.get('country', 'Unknown')}\n"
        f"⚙️ <b>Service:</b> {e.get('service', 'Unknown')}\n"
        f"📱 <b>Number:</b> {num_display}\n"
        f"🔑 <b>OTP:</b> <code>{otp_to_display}</code>\n\n"
        f"📩 <b>Full Message:</b>\n"
        f"<pre>{escaped_full_msg}</pre>"
    )
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="👑 ×°𝓞𝔀𝓷𝓮𝓻°× 👑", url=config.OWNER_LINK),
         types.InlineKeyboardButton(text="༄ 𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐫 𒆜", url="https://t.me/BashOnChain")],
        [types.InlineKeyboardButton(text="★彡[ᴀʟʟ ɴᴜᴍʙᴇʀꜱ]彡★", url="https://t.me/oxfreebackup")]
    ])
    
    try:
        await bot.send_message(config.GROUP_ID, text, reply_markup=kb)
        print(f"✅ Sent Live SMS OTP message to group: {otp_to_display}")
        
        db.mark_otp_sent(e["number"], e["otp"])
        return True
        
    except Exception as exc:
        db.save_error(f"Failed to forward Live SMS message to group: {exc}")
        print(f"❌ Error forwarding Live SMS message to group: {exc}")
        try:
            await bot.send_message(config.ADMIN_ID, f"Failed to forward Live SMS message: {exc}")
        except Exception:
            pass
        return False

# =========================================================
# Bot Commands - UPDATED
# =========================================================

@dp.message(F.text.startswith("/addnumbers"))
async def cmd_addnumbers(m: types.Message):
    """Handle /addnumbers command - add ranges by test number"""
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    
    try:
        # Parse command
        lines = m.text.strip().split('\n')
        if len(lines) < 2:
            await m.answer("⚠️ Format: /addnumbers\\nTestNumber1\\nTestNumber2\\n...")
            await m.answer("📋 Example:\\n/addnumbers\\n994507647922\\n995123456789\\n994701234567")
            return
        
        # Get test numbers (all lines except first)
        test_numbers = []
        for i in range(1, len(lines)):
            test_number = lines[i].strip()
            # Clean the number (remove spaces, dashes, etc.)
            clean_number = re.sub(r'[^\d]', '', test_number)
            if clean_number and len(clean_number) >= 10:
                test_numbers.append(clean_number)
            elif test_number:
                # Try to see if it's a range name format (contains letters)
                if re.search(r'[a-zA-Z]', test_number):
                    # It's a range name, not test number
                    await m.answer(f"⚠️ '{test_number}' looks like a range name, not test number!")
                    await m.answer("ℹ️ Use /addrangers for range names, /addnumbers for test numbers")
                    return
        
        if not test_numbers:
            await m.answer("⚠️ No valid test numbers specified")
            await m.answer("ℹ️ Test numbers should be 10-15 digits (e.g., 994507647922)")
            return
        
        # Check if too many test numbers (max 10)
        if len(test_numbers) > 10:
            await m.answer(f"⚠️ Maximum 10 test numbers allowed. You specified {len(test_numbers)}.")
            await m.answer("📝 Using first 10 test numbers only.")
            test_numbers = test_numbers[:10]
        
        # Start process
        await m.answer(f"🚀 **Starting range adding by TEST NUMBER**\\n📊 Test numbers to process: {len(test_numbers)}\\n⏳ Please wait...")
        
        # DIRECTLY ADD NEW RANGES USING TEST NUMBERS
        success, added_ranges = await add_multiple_ranges_by_test_number(test_numbers, m)
        
        # Final summary
        if success:
            summary = f"✅ **PROCESS COMPLETED!**\\n📊 Total added: {len(added_ranges)} ranges"
            await m.answer(summary)
        else:
            await m.answer("❌ Process completed with errors.")
        
    except Exception as e:
        await m.answer(f"❌ Error in /addnumbers command: {e}")
        print(f"❌ Error in /addnumbers: {e}")
        import traceback
        traceback.print_exc()

@dp.message(F.text.startswith("/addrangers"))
async def cmd_addrangers(m: types.Message):
    """Handle /addrangers command - add ranges by range name"""
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    
    try:
        # Parse command
        lines = m.text.strip().split('\n')
        if len(lines) < 2:
            await m.answer("⚠️ Format: /addrangers\\nRangeName1\\nRangeName2\\n...")
            await m.answer("📋 Example:\\n/addrangers\\nAZERBAIJAN 9866\\nPERU 5384\\nNIGERIA 12844")
            return
        
        # Get range names (all lines except first)
        range_names = []
        for i in range(1, len(lines)):
            range_name = lines[i].strip()
            if range_name:
                range_names.append(range_name)
        
        if not range_names:
            await m.answer("⚠️ No range names specified")
            return
        
        # Check if too many ranges (max 10)
        if len(range_names) > 10:
            await m.answer(f"⚠️ Maximum 10 ranges allowed. You specified {len(range_names)}.")
            await m.answer("📝 Using first 10 ranges only.")
            range_names = range_names[:10]
        
        # Start process
        await m.answer(f"🚀 Starting range adding by NAME...\\n📊 Ranges to add: {len(range_names)}\\n⏳ Please wait...")
        
        # Convert range names to search (for compatibility)
        # Note: You'll need to update the old add_multiple_ranges function
        # to work with the new system or use test numbers instead
        await m.answer("⚠️ **NOTE:** /addrangers uses range names. Consider using /addnumbers with test numbers instead.")
        await m.answer("📱 Use /addnumbers with actual test numbers for more accurate results.")
        
        # For now, we'll just inform the user
        range_list_text = "\\n".join([f"  • {r}" for r in range_names])
        await m.answer(f"📋 Range names received:\\n{range_list_text}\\n\\n❌ This feature needs update. Use /addnumbers instead.")
        
    except Exception as e:
        await m.answer(f"❌ Error in /addrangers command: {e}")
        print(f"❌ Error in /addrangers: {e}")

@dp.message(F.text == "/returnall")
async def cmd_returnall(m: types.Message):
    """Return all numbers/ranges"""
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    
    await m.answer("🔄 Returning all numbers/ranges...")
    
    success = await bulk_return_all_numbers()
    
    if success:
        await m.answer("✅ All numbers/ranges returned successfully!")
    else:
        await m.answer("❌ Failed to return numbers/ranges.")
    
    # Return to Live SMS
    navigate_to_live_sms()
    await m.answer("🌐 Returned to Live SMS monitoring page.")

@dp.message(F.text == "/start")
async def cmd_start(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    st = db.get_status()
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="▶️ Start", callback_data="start_worker"),
         types.InlineKeyboardButton(text="⏸ Stop", callback_data="stop_worker")],
        [types.InlineKeyboardButton(text="🧹 Clear DB", callback_data="clear_db"),
         types.InlineKeyboardButton(text="❗ Errors", callback_data="show_errors")],
        [types.InlineKeyboardButton(text="🔄 Relogin", callback_data="relogin")],
        [types.InlineKeyboardButton(text="📥 Add Ranges", callback_data="add_ranges")]
    ])
    await m.answer(f"⚙️ <b>Live SMS OTP Receiver</b>\nStatus: <b>{st}</b>\nStored OTPs: <b>{db.count_otps()}</b>\nCurrent Page: <b>{current_page}</b>", reply_markup=kb)

@dp.callback_query()
async def cb(q: types.CallbackQuery):
    if q.from_user.id != config.ADMIN_ID:
        await q.answer("⛔ No permission", show_alert=True)
        return
    
    if q.data == "start_worker":
        global _worker_task
        if _worker_task is None or _worker_task.done():
            if driver and navigate_to_live_sms():
                _worker_task = asyncio.create_task(worker())
                await q.message.answer("✅ Live SMS Worker started!")
            else:
                await q.message.answer("❌ Not on Live SMS page! Use '🔄 Relogin' to login.")
        else:
            await q.message.answer("ℹ️ Live SMS Worker is already running.")
        await q.answer()
    
    elif q.data == "stop_worker":
        stop_worker_task()
        await q.message.answer("🛑 Live SMS Worker stopping...")
        await q.answer()
    
    elif q.data == "clear_db":
        db.clear_otps()
        await q.message.answer("🗑 OTP DB cleared.")
        await q.answer()
    
    elif q.data == "show_errors":
        rows = db.get_errors(10)
        if not rows:
            await q.message.answer("✅ No errors recorded.")
        else:
            text = "\n\n".join([f"{r[1]} — {r[0]}" for r in rows])
            await q.message.answer(f"<b>Recent Errors</b>:\n\n{text}")
        await q.answer()
    
    elif q.data == "relogin":
        await q.message.answer("🔄 Relogging in...")
        if login_and_fetch_token():
            await q.message.answer("✅ Manual relogin successful!")
        else:
            await q.message.answer("❌ Manual relogin failed!")
        await q.answer()
    
    elif q.data == "add_ranges":
        await q.message.answer("📋 Use /addnumbers command with TEST NUMBERS:\\n\\n/addnumbers\\n994507647922\\n995123456789\\n...")
        await q.answer()

@dp.message(F.text == "/on")
async def cmd_on(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    global _worker_task
    if _worker_task is None or _worker_task.done():
        if driver and navigate_to_live_sms():
            _worker_task = asyncio.create_task(worker())
            await m.answer("✅ Live SMS Worker started!")
        else:
            await m.answer("❌ Not on Live SMS page! Use /relogin to login.")
    else:
        await m.answer("ℹ️ Live SMS Worker is already running.")

@dp.message(F.text == "/off")
async def cmd_off(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    stop_worker_task()
    await m.answer("🛑 Live SMS Worker stopping...")

@dp.message(F.text == "/status")
async def cmd_status(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    browser_status = "Open" if driver else "Closed"
    current_url = driver.current_url if driver else "No browser"
    login_status = "Logged in" if driver and "portal" in current_url else "Not logged in"
    page_status = current_page
    
    await m.answer(f"📡 Status: <b>{db.get_status()}</b>\n📥 Stored OTPs: <b>{db.count_otps()}</b>\n🖥️ Browser: <b>{browser_status}</b>\n🔐 Login: <b>{login_status}</b>\n📄 Current Page: <b>{page_status}</b>\n🌐 URL: <code>{current_url}</code>")

@dp.message(F.text == "/check")
async def cmd_check(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    await m.answer(f"Stored OTPs: <b>{db.count_otps()}</b>")

@dp.message(F.text == "/clear")
async def cmd_clear(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    db.clear_otps()
    await m.answer("🗑 OTP DB cleared.")

@dp.message(F.text == "/errors")
async def cmd_errors(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    rows = db.get_errors(20)
    if not rows:
        await m.answer("✅ No errors recorded.")
    else:
        text = "\n\n".join([f"{r[1]} — {r[0]}" for r in rows])
        await m.answer(f"<b>Recent Errors</b>:\n\n{text}")

@dp.message(F.text == "/relogin")
async def cmd_relogin(m: types.Message):
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    await m.answer("🔄 Relogging in...")
    if login_and_fetch_token():
        await m.answer("✅ Manual relogin successful!")
    else:
        await m.answer("❌ Manual relogin failed!")

# =========================================================
# NEW COMMAND: /listnumbers
# =========================================================

@dp.message(F.text.startswith("/listnumbers"))
async def cmd_listnumbers(m: types.Message):
    """List termination numbers"""
    if m.from_user.id != config.ADMIN_ID:
        await m.answer("⛔ No permission.")
        return
    
    try:
        parts = m.text.split()
        count = 10
        if len(parts) > 1:
            try:
                count = int(parts[1])
                if count > 20:
                    count = 20
            except:
                pass
        
        await m.answer(f"📋 Getting {count} termination numbers...")
        
        # Navigate to termination page
        if not navigate_to_return_numbers_page():
            await m.answer("❌ Failed to navigate to termination page")
            return
        
        time.sleep(3)
        
        # Extract numbers
        numbers = []
        try:
            # Look for phone numbers in the page
            page_source = driver.page_source
            # Find phone numbers (10-15 digits)
            number_pattern = r'\b\d{10,15}\b'
            all_numbers = re.findall(number_pattern, page_source)
            
            # Remove duplicates and limit
            for num in all_numbers:
                if num not in numbers and len(num) >= 10:
                    numbers.append(num)
                    if len(numbers) >= count:
                        break
        except Exception as e:
            print(f"❌ Error extracting numbers: {e}")
        
        if numbers:
            numbers_text = "\\n".join([f"{i+1}. `{num}`" for i, num in enumerate(numbers)])
            await m.answer(f"📱 **Termination Numbers ({len(numbers)} found):**\\n\\n{numbers_text}\\n\\n**To add these:**\\nUse `/addnumbers` then paste the numbers.")
        else:
            await m.answer("❌ No termination numbers found.")
        
        # Return to Live SMS
        navigate_to_live_sms()
        
    except Exception as e:
        await m.answer(f"❌ Error in /listnumbers: {e}")

# =========================================================
# Startup
# =========================================================

async def on_startup():
    print("🚀 Starting up Live SMS OTP Receiver with range management...")
    close_driver()
    
    if login_and_fetch_token():
        print("✅ Initial login and Live SMS page access successful.")
        
    else:
        print("❌ Initial login failed.")

    if db.get_status() == "online" and driver and navigate_to_live_sms():
        global _worker_task
        if _worker_task and not _worker_task.done():
            _worker_task.cancel()
            time.sleep(1)
        _worker_task = asyncio.create_task(worker())
    else:
        print("⚠️ Not on Live SMS page - Worker not started.")

# =========================================================
# Main
# =========================================================

if __name__ == "__main__":
    try:
        import logging
        logging.basicConfig(level=logging.INFO)
        
        if _worker_task and not _worker_task.done():
            _worker_task.cancel()
        
        dp.startup.register(on_startup)
        print("🤖 Live SMS OTP Bot starting...")
        dp.run_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Exiting...")
        close_driver()
    except Exception as e:
        print(f"❌ Main error: {e}")
        close_driver()
