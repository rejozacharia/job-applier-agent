# src/automation.py
import os
import time
import random
import string

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Import necessary components from the main app
# Need to handle imports carefully if running this standalone vs. via Flask app context
# For now, assume it might be called from a background task runner that has app context
# Or pass necessary data (profile, config, db session) as arguments
from src.utils import log_event
from src.models.models import Profile, StandardAnswer, Application
from src.cover_letter import generate_cover_letter
# from src.main import db # Avoid direct db import if possible, pass session or data

# --- Constants ---
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# --- Helper Functions ---
def generate_random_password(length=12):
    """Generates a secure random password."""
    characters = string.ascii_letters + string.digits + string.punctuation
    password = "".join(random.choice(characters) for i in range(length))
    # Ensure it meets common complexity requirements (optional)
    # Add checks for uppercase, lowercase, digit, symbol if needed
    return password

# --- Main Automation Class ---
class JobAutomator:
    def __init__(self, application_id, job_url, user_profile, standard_answers, config, db_session=None):
        self.application_id = application_id
        self.job_url = job_url
        self.user_profile = user_profile # Pass profile data (dict or Profile object)
        self.standard_answers = standard_answers # Pass list of QA pairs
        self.config = config # Pass config settings (e.g., auto_attach_cl)
        self.driver = None
        self.wait = None
        self.platform = "Unknown"
        self.db_session = db_session # Store the passed-in session

    def _log_event(self, level, message, screenshot_path=None):
        """Logs an event using the provided db_session."""
        log_event(self.application_id, level, message, screenshot_path=screenshot_path, session=self.db_session)

    def _init_driver(self):
        """Initializes the Selenium WebDriver."""
        try:
            self._log_event("INFO", "Initializing WebDriver...")
            options = webdriver.ChromeOptions()
            # Ensure headless is NOT set for debugging visibility
            # options.add_argument("--headless")
            options.add_argument("--no-sandbox") # Often needed in containerized environments
            options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            options.add_argument("--start-maximized") # Ensure it starts maximized

            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            # self.driver.maximize_window() # --start-maximized option should handle this
            self.wait = WebDriverWait(self.driver, 15) # Default wait time of 15 seconds
            self._log_event("SUCCESS", "WebDriver initialized successfully.")
            print(f"[Automator AppID: {self.application_id}] WebDriver initialized. Pausing for 3s to observe browser.")
            time.sleep(3) # Keep browser open for a moment to confirm it launched
            return True
        except Exception as e:
            self._log_event("ERROR", f"Failed to initialize WebDriver: {e}")
            return False

    def _take_screenshot(self, stage_name):
        """Takes a screenshot and saves it."""
        try:
            filename = f"app_{self.application_id}_{stage_name}_{int(time.time())}.png"
            filepath = os.path.join(SCREENSHOT_DIR, filename)
            self.driver.save_screenshot(filepath)
            self._log_event("INFO", f"Screenshot saved: {filename}")
            return filepath
        except Exception as e:
            self._log_event("WARN", f"Failed to take screenshot: {e}")
            return None

    def _detect_platform(self):
        """Attempts to detect the ATS platform (e.g., Workday)."""
        # Simple detection based on URL or page content
        current_url = self.driver.current_url
        page_source = self.driver.page_source.lower()

        if "workday" in current_url or "myworkdayjobs" in current_url or "wd1.myworkdayjobs.com" in current_url:
            self.platform = "Workday"
        elif "greenhouse.io" in current_url or "boards.greenhouse.io" in current_url:
            self.platform = "Greenhouse"
        elif "lever.co" in current_url or "jobs.lever.co" in current_url:
            self.platform = "Lever"
        # Add more platform detection rules here
        else:
            # Look for clues in page source
            if "data-automation-id" in page_source: # Common in Workday
                 self.platform = "Workday"

        self._log_event("INFO", f"Detected platform: {self.platform}")
        # Update Application record in DB (requires db session or separate update mechanism)
        # Example: app_record = self.db_session.query(Application).get(self.application_id)
        # if app_record: app_record.detected_platform = self.platform
        # self.db_session.commit() # Commits should be handled by the worker

    def _navigate_to_job(self):
        """Navigates to the job application URL."""
        try:
            self._log_event("INFO", f"Navigating to job URL: {self.job_url}")
            print(f"[Automator AppID: {self.application_id}] Navigating to {self.job_url}. Pausing for 5s after page load attempt.")
            self.driver.get(self.job_url)
            time.sleep(5) # Allow initial page load and observation
            # Check for immediate errors (e.g., 404)
            if "page not found" in self.driver.title.lower() or "404" in self.driver.title:
                 self._log_event("ERROR", f"Job URL led to 'Page Not Found' or 404.")
                 return False
            self._log_event("SUCCESS", "Successfully navigated to job page.")
            self._detect_platform() # Detect platform after navigation
            return True
        except Exception as e:
            self._log_event("ERROR", f"Failed to navigate to job URL: {e}")
            self._take_screenshot("navigation_error")
            return False

    def _handle_overlays(self, timeout=5):
        """Attempts to find and close common overlays like cookie banners."""
        self._log_event("DEBUG", "Checking for and attempting to close overlays.")
        overlay_selectors = [
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept all')]",
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow all')]",
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'got it')]",
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'i understand')]",
            "//button[contains(@aria-label, 'close') or contains(@aria-label, 'Close')]",
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'decline') and not(contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'and continue'))]", # Be careful with "decline"
            "//div[contains(@class, 'cookie-banner')]//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//div[contains(@id, 'cookie-consent')]//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//button[@id='onetrust-accept-btn-handler']", # OneTrust cookie consent
        ]
        original_wait_time = self.wait._timeout # type: ignore
        self.wait._timeout = timeout # type: ignore
        closed_overlay = False
        for i, selector in enumerate(overlay_selectors):
            try:
                overlay_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                self.driver.execute_script("arguments[0].scrollIntoView(true);", overlay_button)
                time.sleep(0.2) # Brief pause
                overlay_button.click()
                self._log_event("INFO", f"Clicked a potential overlay button using selector: {selector}")
                closed_overlay = True
                time.sleep(1) # Wait for overlay to disappear
                break # Assume one overlay is enough for now
            except TimeoutException:
                self._log_event("DEBUG", f"Overlay button not found or not clickable with selector ({i+1}/{len(overlay_selectors)}): {selector}")
            except Exception as e:
                self._log_event("WARN", f"Error clicking overlay button with selector {selector}: {e}")
        self.wait._timeout = original_wait_time # type: ignore
        return closed_overlay

    def _click_element_robustly(self, element_finder_tuple, element_name, timeout=10):
        """
        Waits for an element, scrolls to it, and attempts to click it,
        handling potential interceptions.
        element_finder_tuple: A tuple like (By.XPATH, "//button")
        element_name: A descriptive name for logging (e.g., "Apply Button")
        """
        try:
            self._log_event("DEBUG", f"Attempting to click '{element_name}'. Waiting for element to be clickable.")
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable(element_finder_tuple)
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
            time.sleep(0.5) # Pause after scroll

            try:
                element.click()
                self._log_event("INFO", f"Successfully clicked '{element_name}' using standard click.")
                return True
            except Exception as e: # Catches ElementClickInterceptedException and others
                self._log_event("WARN", f"Standard click failed for '{element_name}': {type(e).__name__} - {str(e)}. Attempting workarounds.")
                self._take_screenshot(f"{element_name.replace(' ', '_').lower()}_intercepted")

                # Attempt 1: Handle overlays and retry
                if self._handle_overlays(timeout=3): # Quick check for overlays
                    time.sleep(1) # Wait for overlay to clear
                    try:
                        # Re-fetch element as page might have changed
                        element = WebDriverWait(self.driver, timeout).until(
                            EC.element_to_be_clickable(element_finder_tuple)
                        )
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
                        time.sleep(0.3)
                        element.click()
                        self._log_event("INFO", f"Successfully clicked '{element_name}' using standard click after handling overlays.")
                        return True
                    except Exception as e_retry:
                        self._log_event("WARN", f"Standard click for '{element_name}' still failed after handling overlays: {type(e_retry).__name__} - {str(e_retry)}")

                # Attempt 2: JavaScript click
                try:
                    self._log_event("DEBUG", f"Attempting JavaScript click for '{element_name}'.")
                    # Re-fetch element before JS click as well
                    element = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located(element_finder_tuple) # presence is enough for JS click
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
                    time.sleep(0.3)
                    self.driver.execute_script("arguments[0].click();", element)
                    self._log_event("INFO", f"Successfully clicked '{element_name}' using JavaScript click.")
                    return True
                except Exception as e_js:
                    self._log_event("ERROR", f"JavaScript click also failed for '{element_name}': {type(e_js).__name__} - {str(e_js)}")
                    self._take_screenshot(f"{element_name.replace(' ', '_').lower()}_js_click_failed")
                    return False
        except TimeoutException:
            self._log_event("ERROR", f"Element '{element_name}' not found or not clickable within {timeout}s using locator: {element_finder_tuple}")
            self._take_screenshot(f"{element_name.replace(' ', '_').lower()}_not_found")
            return False
        except Exception as e_outer:
            self._log_event("ERROR", f"An unexpected error occurred while trying to click '{element_name}': {type(e_outer).__name__} - {str(e_outer)}")
            self._take_screenshot(f"{element_name.replace(' ', '_').lower()}_unexpected_error")
            return False


    def _handle_login(self):
        """Handles login or account creation (Placeholder)."""
        self._log_event("INFO", "Attempting login/account creation (Placeholder)...")
        # This requires platform-specific logic (Workday, Greenhouse, etc.)
        # 1. Find login/apply button
        # 2. Check if login form is present
        # 3. Try default credentials (self.user_profile.default_email)
        # 4. If fails, check for 'create account' option
        # 5. If creating account, use default email and generated password (if strategy allows)
        # 6. Log generated password and site if created
        # 7. If email exists / login fails / unknown state -> Log error and potentially stop/ask user

        if self.platform == "Workday":
            self._log_event("INFO", "Attempting Workday login/account creation flow.")
            self._log_event("INFO", "Attempting Workday login/account creation flow.")
            self._handle_overlays() # Attempt to clear any initial overlays

            # Step 1: Click an "Apply" or "Apply with Workday" button
            apply_button_locators = [
                (By.XPATH, "//a[contains(@data-automation-id, 'applyButton')]"),
                (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply') and not(contains(@disabled, 'disabled'))]"),
                (By.XPATH, "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply') and not(contains(@disabled, 'disabled'))]")
            ]
            apply_button_clicked = False
            for locator in apply_button_locators:
                if self._click_element_robustly(locator, "Workday Apply Button"):
                    apply_button_clicked = True
                    time.sleep(5)  # Wait for potential page transition or iframe load
                    self._take_screenshot("workday_after_apply_click")
                    break
            
            if not apply_button_clicked:
                self._log_event("WARN", "Could not find or click a primary 'Apply' button on the job page. Checking if already on Workday login.")
                self._take_screenshot("apply_button_not_found_or_failed")
                # It's possible we are already on a Workday page that directly asks for login.
                # So, we don't necessarily return False here.
            # Step 2: Check if we are in a Workday iframe and switch to it if necessary
            # Step 2: Check if we are in a Workday iframe and switch to it if necessary
            # Workday often loads in an iframe.
            try:
                # More specific iframe locators
                workday_iframe_locators = [
                    (By.XPATH, "//iframe[contains(@src, 'myworkdayjobs.com')]"),
                    (By.XPATH, "//iframe[contains(@title, 'Workday')]"),
                    (By.XPATH, "//iframe[@data-automation-id='workdayApplicationFrame']"),
                    (By.TAG_NAME, "iframe") # Generic fallback, use with caution
                ]
                switched_to_iframe = False
                for i, locator in enumerate(workday_iframe_locators):
                    try:
                        self.wait.until(EC.frame_to_be_available_and_switch_to_it(locator))
                        self._log_event("INFO", f"Switched to Workday iframe using locator: {locator}")
                        switched_to_iframe = True
                        time.sleep(1)
                        break
                    except TimeoutException:
                        self._log_event("DEBUG", f"Workday iframe not found with locator {locator} ({i+1}/{len(workday_iframe_locators)}).")
                
                if not switched_to_iframe:
                     self._log_event("INFO", "No specific Workday iframe detected, or already on main Workday page. Proceeding.")

            except Exception as e_iframe: # Catch any error during iframe search/switch
                self._log_event("WARN", f"Error during iframe handling: {e_iframe}. Proceeding as if no iframe.")
                # If no iframe, assume we are on the main page or the content is directly embedded.
            # Step 3: Look for email input field and "Create Account" or "Next"
            if not self.user_profile or not self.user_profile.default_email:
                self._log_event("ERROR", "User profile email not set. Cannot proceed with Workday login.")
                self._take_screenshot("workday_email_missing_in_profile")
                return False

            try:
                # Common Workday email field
                # Common Workday email field
                email_input_locator = (By.XPATH, "//input[@data-automation-id='email' or @data-automation-id='username' or @type='email']")
                email_input = self.wait.until(EC.visibility_of_element_located(email_input_locator))
                # Clear field first in case of pre-fill
                email_input.clear()
                email_input.send_keys(self.user_profile.default_email)
                self._log_event("INFO", f"Entered email: {self.user_profile.default_email}")
                self._take_screenshot("workday_email_entered")

                # Click "Next", "Continue", or "Verify" button
                next_button_locators = [
                    (By.XPATH, "//button[@data-automation-id='verifyIdentifier']"), # Common for "Next" after email
                    (By.XPATH, "//button[@data-automation-id='submit']"),
                    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next') and not(contains(@disabled, 'disabled'))]"),
                    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue') and not(contains(@disabled, 'disabled'))]")
                ]
                next_button_clicked = False
                for locator in next_button_locators:
                    if self._click_element_robustly(locator, "Workday Email Next/Continue Button"):
                        next_button_clicked = True
                        time.sleep(3) # Wait for next page (password or create account details)
                        self._take_screenshot("workday_after_email_next")
                        break
                
                if not next_button_clicked:
                    self._log_event("WARN", "Could not find or click 'Next/Continue' button after entering email.")
                    self._take_screenshot("workday_next_button_fail")
                    # Consider if we should return False or try to detect password/create account fields directly
                    # For now, let's assume this is a failure point if the button isn't clicked.
                    # However, some Workday flows might directly show password or create account fields
                    # if the email is recognized or not. This needs more advanced state detection.
                    # For now, we will proceed and let the subsequent steps try to find elements.
                    # return False
                # TODO: Add logic to check if it's a password page (existing user)
                # or a create account page (new user).
                # Look for password field: //input[@data-automation-id='password']
                # Look for "Create Account" specific fields like first name, last name, new password.
                # Look for "Create Account" specific fields like first name, last name, new password.
                self._log_event("INFO", "Successfully entered email and clicked next. Further login/creation steps needed.")
                return True # Placeholder, more steps needed

            except TimeoutException:
                self._log_event("WARN", "Could not find Workday email input field or timed out.")
                self._take_screenshot("workday_email_field_fail")
                # Check for "Create Account" link directly if email field isn't obvious
                # Check for "Create Account" link directly if email field isn't obvious or "Next" fails
                # This path is taken if the email input or next button logic above fails.
                create_account_link_locators = [
                    (By.XPATH, "//a[@data-automation-id='createAccountLink']"),
                    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create account')]"),
                    (By.XPATH, "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create account')]")
                ]
                create_account_clicked = False
                for locator in create_account_link_locators:
                    if self._click_element_robustly(locator, "Workday Create Account Link/Button"):
                        create_account_clicked = True
                        time.sleep(3)
                        self._take_screenshot("workday_create_account_clicked")
                        self._log_event("INFO", "Navigated to create account page. Further steps needed for account creation form.")
                        # TODO: Implement form filling for account creation.
                        return True # Placeholder, indicates we are on create account page
                
                if not create_account_clicked:
                    self._log_event("ERROR", "Failed to find email input and also failed to find/click 'Create Account' link/button.")
                    self._take_screenshot("workday_login_create_options_fail")
                    return False # Definite failure if neither login nor create account path works
            except Exception as e:
                self._log_event("ERROR", f"An error occurred during Workday login/email entry attempt: {e}")
                self._take_screenshot("workday_login_generic_error")
            finally:
                # Switch back to default content if we were in an iframe
                try:
                    self.driver.switch_to.default_content()
                    self._log_event("INFO", "Switched back to default content from iframe (if applicable).")
                except Exception as e_iframe_switch:
                    self._log_event("DEBUG", f"Error switching back from iframe (or was not in one): {e_iframe_switch}")


        else: # Other platforms
            self._log_event("WARN", f"Login logic not implemented for platform: {self.platform}")
            return False # Explicitly return False if not Workday and not implemented

        # If we reached here for Workday and didn't return False, it implies partial success or next steps.
        # For now, the function will return based on the specific paths taken above.

    def _fill_forms(self):
        """Fills application forms based on user profile (Placeholder)."""
        self._log_event("INFO", "Filling application forms (Placeholder)...")
        # Requires platform-specific logic
        # Find form fields (e.g., by label, name, id, data-automation-id for Workday)
        # Handle different field types (text, dropdown, radio, checkbox)
        if self.platform == "Workday":
            self._log_event("INFO", "Starting to fill Workday forms (e.g., My Information).")
            self._handle_overlays() # Handle any overlays that might appear before form filling

            # Switch to iframe if necessary (common for Workday forms)
            # This logic is similar to _handle_login, might be refactored later
            try:
                workday_iframe_locators = [
                    (By.XPATH, "//iframe[contains(@src, 'myworkdayjobs.com')]"),
                    (By.XPATH, "//iframe[contains(@title, 'Workday')]"),
                    (By.XPATH, "//iframe[@data-automation-id='workdayApplicationFrame']")
                ]
                switched_to_iframe = False
                for locator in workday_iframe_locators:
                    try:
                        WebDriverWait(self.driver, 5).until(EC.frame_to_be_available_and_switch_to_it(locator))
                        self._log_event("INFO", f"Switched to Workday iframe for form filling using: {locator}")
                        switched_to_iframe = True
                        time.sleep(0.5)
                        break
                    except TimeoutException:
                        self._log_event("DEBUG", f"Workday iframe not found with {locator} for form filling.")
                if not switched_to_iframe:
                    self._log_event("INFO", "No specific Workday iframe found for forms, assuming main content.")
            except Exception as e_iframe_form:
                self._log_event("WARN", f"Error switching to iframe for forms: {e_iframe_form}")

            # Example: Fill First Name
            try:
                first_name_locator = (By.XPATH, "//input[@data-automation-id='legalNameSection_firstName' or @data-automation-id='firstName']")
                fn_element = self.wait.until(EC.visibility_of_element_located(first_name_locator))
                fn_element.clear()
                fn_element.send_keys(self.user_profile.first_name if self.user_profile else "TestFirstName")
                self._log_event("INFO", f"Filled First Name: {self.user_profile.first_name if self.user_profile else 'TestFirstName'}")
                self._take_screenshot("workday_filled_firstname")
            except TimeoutException:
                self._log_event("WARN", "First Name field not found on Workday form.")
                self._take_screenshot("workday_firstname_not_found")
            except Exception as e:
                self._log_event("ERROR", f"Error filling First Name: {e}")

            # Example: Fill Last Name
            try:
                last_name_locator = (By.XPATH, "//input[@data-automation-id='legalNameSection_lastName' or @data-automation-id='lastName']")
                ln_element = self.wait.until(EC.visibility_of_element_located(last_name_locator))
                ln_element.clear()
                ln_element.send_keys(self.user_profile.last_name if self.user_profile else "TestLastName")
                self._log_event("INFO", f"Filled Last Name: {self.user_profile.last_name if self.user_profile else 'TestLastName'}")
                self._take_screenshot("workday_filled_lastname")
            except TimeoutException:
                self._log_event("WARN", "Last Name field not found on Workday form.")
                self._take_screenshot("workday_lastname_not_found")
            except Exception as e:
                self._log_event("ERROR", f"Error filling Last Name: {e}")
            
            # Fill Phone Number
            try:
                # Workday often has a primary phone section.
                # We'll try to find a general phone input first, then a more specific one.
                # Common data-automation-ids: 'phoneNumber', 'phoneGridSection_phoneNumber'
                # Sometimes there's a type dropdown like 'phoneDeviceType'
                phone_input_locator = (By.XPATH, "//input[@data-automation-id='phoneNumber' or contains(@data-automation-id, 'phoneNumber')]")
                phone_element = self.wait.until(EC.visibility_of_element_located(phone_input_locator))
                
                # Assuming user_profile.primary_phone exists
                phone_number_to_fill = self.user_profile.primary_phone if self.user_profile and hasattr(self.user_profile, 'primary_phone') else "1234567890" # Default if not found
                
                phone_element.clear()
                phone_element.send_keys(phone_number_to_fill)
                self._log_event("INFO", f"Filled Phone Number: {phone_number_to_fill}")
                self._take_screenshot("workday_filled_phone")
            except TimeoutException:
                self._log_event("WARN", "Phone Number field not found on Workday form.")
                self._take_screenshot("workday_phone_not_found")
            except Exception as e:
                self._log_event("ERROR", f"Error filling Phone Number: {e}")
                self._take_screenshot("workday_phone_fill_error")

            # Fill Address Line 1
            try:
                # Common data-automation-ids: 'addressLine1', 'addressSection_addressLine1'
                address1_locator = (By.XPATH, "//input[@data-automation-id='addressLine1' or @data-automation-id='addressSection_addressLine1']")
                address1_element = self.wait.until(EC.visibility_of_element_located(address1_locator))
                
                # Assuming user_profile.address_street exists
                address_street_to_fill = self.user_profile.address_street if self.user_profile and hasattr(self.user_profile, 'address_street') else "123 Main St"
                
                address1_element.clear()
                address1_element.send_keys(address_street_to_fill)
                self._log_event("INFO", f"Filled Address Line 1: {address_street_to_fill}")
                self._take_screenshot("workday_filled_address1")
            except TimeoutException:
                self._log_event("WARN", "Address Line 1 field not found on Workday form.")
                self._take_screenshot("workday_address1_not_found")
            except Exception as e:
                self._log_event("ERROR", f"Error filling Address Line 1: {e}")
                self._take_screenshot("workday_address1_fill_error")

            # Fill City
            try:
                # Common data-automation-ids: 'city', 'addressSection_city'
                city_locator = (By.XPATH, "//input[@data-automation-id='city' or @data-automation-id='addressSection_city']")
                city_element = self.wait.until(EC.visibility_of_element_located(city_locator))

                # Assuming user_profile.address_city exists
                address_city_to_fill = self.user_profile.address_city if self.user_profile and hasattr(self.user_profile, 'address_city') else "Anytown"

                city_element.clear()
                city_element.send_keys(address_city_to_fill)
                self._log_event("INFO", f"Filled City: {address_city_to_fill}")
                self._take_screenshot("workday_filled_city")
            except TimeoutException:
                self._log_event("WARN", "City field not found on Workday form.")
                self._take_screenshot("workday_city_not_found")
            except Exception as e:
                self._log_event("ERROR", f"Error filling City: {e}")
                self._take_screenshot("workday_city_fill_error")

            # Fill Country
            try:
                country_to_fill = self.user_profile.address_country if self.user_profile and hasattr(self.user_profile, 'address_country') else "United States"
                self._log_event("INFO", f"Attempting to fill Country: {country_to_fill}")

                # Workday often uses a button to open a dropdown list for country, then a search input, then a list item to click.
                # Locator for the button that opens the country selection dialog/dropdown
                country_dropdown_button_locator = (By.XPATH, "//button[@data-automation-id='countryDropdown']")
                # Locator for the search input within the dropdown/dialog
                country_search_input_locator = (By.XPATH, "//input[@data-automation-id='searchBox']")
                # Locator for the country option in the list (will be formatted with the country name)
                country_option_locator_template = "//div[@data-automation-id='promptOption' and contains(text(),'{country_name}')]"

                try:
                    # Try clicking the main dropdown button first
                    country_button = self.wait.until(EC.element_to_be_clickable(country_dropdown_button_locator))
                    country_button.click()
                    self._log_event("INFO", "Clicked country dropdown button.")
                    time.sleep(0.5) # Wait for dropdown to appear

                    # Search for the country
                    country_search_input = self.wait.until(EC.visibility_of_element_located(country_search_input_locator))
                    country_search_input.clear()
                    country_search_input.send_keys(country_to_fill)
                    self._log_event("INFO", f"Typed '{country_to_fill}' into country search.")
                    time.sleep(1) # Wait for list to filter

                    # Click the specific country option
                    country_option_locator = (By.XPATH, country_option_locator_template.format(country_name=country_to_fill))
                    country_option = self.wait.until(EC.element_to_be_clickable(country_option_locator))
                    country_option.click()
                    self._log_event("SUCCESS", f"Selected Country: {country_to_fill} from dropdown list.")
                    self._take_screenshot("workday_selected_country")

                except TimeoutException:
                    self._log_event("WARN", "Complex country dropdown interaction failed. Trying simpler input if available.")
                    # Fallback: If the above fails, try to find a simpler input or a standard select
                    # This could be a direct input field or a <select> tag
                    country_input_locator_fallback = (By.XPATH, "//input[@data-automation-id='country' or contains(@aria-label, 'Country')]") # General input
                    country_select_locator_fallback = (By.XPATH, "//select[@data-automation-id='country' or contains(@aria-label, 'Country')]") # Select tag

                    try:
                        country_element = self.driver.find_element(*country_input_locator_fallback)
                        country_element.clear()
                        country_element.send_keys(country_to_fill)
                        self._log_event("INFO", f"Filled Country using fallback input: {country_to_fill}")
                        self._take_screenshot("workday_filled_country_fallback_input")
                    except NoSuchElementException:
                        try:
                            select_element = Select(self.wait.until(EC.visibility_of_element_located(country_select_locator_fallback)))
                            select_element.select_by_visible_text(country_to_fill)
                            self._log_event("INFO", f"Selected Country using fallback select: {country_to_fill}")
                            self._take_screenshot("workday_selected_country_fallback_select")
                        except (NoSuchElementException, TimeoutException):
                            self._log_event("WARN", "Country field (input or select) not found with fallback locators.")
                            self._take_screenshot("workday_country_not_found")
                        except Exception as e_select:
                            self._log_event("ERROR", f"Error selecting Country with fallback select: {e_select}")
                            self._take_screenshot("workday_country_select_error")
                    except Exception as e_input:
                        self._log_event("ERROR", f"Error filling Country with fallback input: {e_input}")
                        self._take_screenshot("workday_country_input_error")

            except Exception as e:
                self._log_event("ERROR", f"Overall error processing Country field: {e}")
                self._take_screenshot("workday_country_overall_error")

            # Fill State/Province
            # This often depends on the country selected. The options might dynamically load.
            try:
                state_to_fill = self.user_profile.address_state if self.user_profile and hasattr(self.user_profile, 'address_state') else "California" # Default for example
                self._log_event("INFO", f"Attempting to fill State/Province: {state_to_fill}")
                time.sleep(1) # Give a brief moment for state field to update after country selection

                # Similar to country, Workday might use a button, search, and list item for state.
                # Locator for the button that opens the state selection dialog/dropdown
                state_dropdown_button_locator = (By.XPATH, "//button[@data-automation-id='stateDropdown' or @data-automation-id='provinceDropdown' or @data-automation-id='locationLevel2']") # Common IDs
                # Locator for the search input within the dropdown/dialog
                state_search_input_locator = (By.XPATH, "//input[@data-automation-id='searchBox']") # Often reused ID
                # Locator for the state option in the list
                state_option_locator_template = "//div[@data-automation-id='promptOption' and contains(text(),'{state_name}')]"

                try:
                    state_button = self.wait.until(EC.element_to_be_clickable(state_dropdown_button_locator))
                    state_button.click()
                    self._log_event("INFO", "Clicked state/province dropdown button.")
                    time.sleep(0.5)

                    state_search_input = self.wait.until(EC.visibility_of_element_located(state_search_input_locator))
                    state_search_input.clear()
                    state_search_input.send_keys(state_to_fill)
                    self._log_event("INFO", f"Typed '{state_to_fill}' into state/province search.")
                    time.sleep(1)

                    state_option_locator = (By.XPATH, state_option_locator_template.format(state_name=state_to_fill))
                    # Sometimes the text match needs to be exact or handle abbreviations
                    # For robustness, one might try variations or a more complex XPath if direct text match fails.
                    state_option = self.wait.until(EC.element_to_be_clickable(state_option_locator))
                    state_option.click()
                    self._log_event("SUCCESS", f"Selected State/Province: {state_to_fill} from dropdown list.")
                    self._take_screenshot("workday_selected_state")

                except TimeoutException:
                    self._log_event("WARN", "Complex state/province dropdown interaction failed. Trying simpler input/select.")
                    state_input_locator_fallback = (By.XPATH, "//input[@data-automation-id='state' or @data-automation-id='province' or contains(@aria-label, 'State') or contains(@aria-label, 'Province')]")
                    state_select_locator_fallback = (By.XPATH, "//select[@data-automation-id='state' or @data-automation-id='province' or contains(@aria-label, 'State') or contains(@aria-label, 'Province')]")

                    try:
                        state_element = self.driver.find_element(*state_input_locator_fallback)
                        state_element.clear()
                        state_element.send_keys(state_to_fill)
                        self._log_event("INFO", f"Filled State/Province using fallback input: {state_to_fill}")
                        self._take_screenshot("workday_filled_state_fallback_input")
                    except NoSuchElementException:
                        try:
                            select_element = Select(self.wait.until(EC.visibility_of_element_located(state_select_locator_fallback)))
                            # Try by visible text first, then by value (e.g., 'CA' for California)
                            try:
                                select_element.select_by_visible_text(state_to_fill)
                            except NoSuchElementException:
                                self._log_event("WARN", f"Could not select state '{state_to_fill}' by visible text, trying by value (abbreviation).")
                                # This assumes state_to_fill might be an abbreviation if full name fails.
                                # A more robust solution would have mapping or check profile for abbreviation.
                                select_element.select_by_value(state_to_fill)
                            self._log_event("INFO", f"Selected State/Province using fallback select: {state_to_fill}")
                            self._take_screenshot("workday_selected_state_fallback_select")
                        except (NoSuchElementException, TimeoutException):
                            self._log_event("WARN", "State/Province field (input or select) not found with fallback locators.")
                            self._take_screenshot("workday_state_not_found")
                        except Exception as e_select_state:
                            self._log_event("ERROR", f"Error selecting State/Province with fallback select: {e_select_state}")
                            self._take_screenshot("workday_state_select_error")
                    except Exception as e_input_state:
                        self._log_event("ERROR", f"Error filling State/Province with fallback input: {e_input_state}")
                        self._take_screenshot("workday_state_input_error")

            except Exception as e:
                self._log_event("ERROR", f"Overall error processing State/Province field: {e}")
                self._take_screenshot("workday_state_overall_error")

            # Fill Zip/Postal Code
            try:
                zip_to_fill = self.user_profile.address_zip if self.user_profile and hasattr(self.user_profile, 'address_zip') else "90210" # Default
                self._log_event("INFO", f"Attempting to fill Zip/Postal Code: {zip_to_fill}")
                # Common data-automation-ids: 'postalCode', 'zipCode', 'addressSection_postalCode'
                zip_locator = (By.XPATH, "//input[@data-automation-id='postalCode' or @data-automation-id='zipCode' or @data-automation-id='addressSection_postalCode' or contains(@aria-label, 'Zip') or contains(@aria-label, 'Postal Code')]")
                zip_element = self.wait.until(EC.visibility_of_element_located(zip_locator))
                
                zip_element.clear()
                zip_element.send_keys(zip_to_fill)
                self._log_event("INFO", f"Filled Zip/Postal Code: {zip_to_fill}")
                self._take_screenshot("workday_filled_zip")
            except TimeoutException:
                self._log_event("WARN", "Zip/Postal Code field not found on Workday form.")
                self._take_screenshot("workday_zip_not_found")
            except Exception as e:
                self._log_event("ERROR", f"Error filling Zip/Postal Code: {e}")
                self._take_screenshot("workday_zip_fill_error")

            # --- WORK EXPERIENCE SECTION ---
            self._log_event("INFO", "Attempting to add work experience section.")
            try:
                experiences = self.user_profile.get("experience", [])
                if not experiences:
                    self._log_event("INFO", "No work experience found in profile to add.")
                else:
                    self._log_event("INFO", f"Found {len(experiences)} work experience entries to process.")

                # Locators for "Add Experience" or "Add Another Experience" buttons
                add_experience_button_locators = [
                    (By.XPATH, "//button[@data-automation-id='addExperience']"), # Typically for the first entry
                    (By.XPATH, "//button[@data-automation-id='addAnotherExperience']"), # For subsequent entries
                    (By.XPATH, "//button[contains(@aria-label, 'Add Work Experience') or contains(normalize-space(.), 'Add Work Experience')]"),
                    (By.XPATH, "//button[contains(@aria-label, 'Add Experience') or contains(normalize-space(.), 'Add Experience')]")
                ]
                
                for i, exp in enumerate(experiences):
                    self._log_event("INFO", f"Adding experience {i+1}/{len(experiences)}: {exp.get('title', 'N/A')} at {exp.get('company', 'N/A')}")
                    
                    # Attempt to click an "Add" button to reveal the form for the current experience.
                    # This logic assumes that for each new experience item from the profile,
                    # an "Add" or "Add Another" button needs to be clicked to open a new form.
                    clicked_add_button = False
                    current_add_locators = add_experience_button_locators # Start with general locators
                    
                    # More specific logic could be added here to differentiate between initial "Add" and "Add Another" if needed
                    # For example, if i == 0, prioritize "addExperience", if i > 0, prioritize "addAnotherExperience".
                    # For now, we iterate through all common locators.

                    for locator in current_add_locators:
                        # Short timeout for add button, as it might not always be needed if form auto-appears
                        if self._click_element_robustly(locator, f"Add Experience Button (Entry {i+1})", timeout=5):
                            self._log_event("INFO", f"Clicked 'Add Experience' button for entry {i+1} using {locator}.")
                            clicked_add_button = True
                            time.sleep(2.5) # Wait for form to appear/update
                            self._take_screenshot(f"workday_exp_add_clicked_{i+1}")
                            break
                    
                    if not clicked_add_button:
                        self._log_event("WARN", f"Could not click an 'Add Experience' button for entry {i+1}. Will attempt to fill fields, assuming form is already present or became available.")
                        self._take_screenshot(f"workday_exp_add_btn_fail_or_not_needed_{i+1}")

                    # --- Fill Experience Details for the current entry ---
                    try:
                        # Job Title
                        title = exp.get("title")
                        if title:
                            # Using [last()] to target the most recently added/opened form block
                            title_locator = (By.XPATH, "(//input[@data-automation-id='jobTitle' or @data-automation-id='title'])[last()]")
                            title_el = self.wait.until(EC.visibility_of_element_located(title_locator))
                            title_el.clear()
                            title_el.send_keys(title)
                            self._log_event("INFO", f"Filled Job Title for experience {i+1}: {title}")
                        else:
                            self._log_event("WARN", f"No Job Title provided for experience {i+1}.")

                        # Company
                        company = exp.get("company")
                        if company:
                            company_locator = (By.XPATH, "(//input[@data-automation-id='company'])[last()]")
                            company_el = self.wait.until(EC.visibility_of_element_located(company_locator))
                            company_el.clear()
                            company_el.send_keys(company)
                            self._log_event("INFO", f"Filled Company for experience {i+1}: {company}")
                        else:
                            self._log_event("WARN", f"No Company provided for experience {i+1}.")

                        # Location
                        location = exp.get("location")
                        if location:
                            location_locator = (By.XPATH, "(//input[@data-automation-id='location'])[last()]")
                            location_el = self.wait.until(EC.visibility_of_element_located(location_locator))
                            location_el.clear()
                            location_el.send_keys(location)
                            self._log_event("INFO", f"Filled Location for experience {i+1}: {location}")

                        # Start Date (MM/YYYY or text)
                        start_date = exp.get("start_date")
                        if start_date:
                            start_date_locators = [
                                (By.XPATH, "(//input[@data-automation-id='startDate' or contains(@data-automation-id, 'startDate') or @data-automation-id='fromDate'])[last()]")
                                # Add more specific selectors for month/year dropdowns if text input fails
                            ]
                            filled_start_date = False
                            for sd_locator in start_date_locators:
                                try:
                                    start_date_el = self.wait.until(EC.visibility_of_element_located(sd_locator))
                                    start_date_el.clear()
                                    start_date_el.send_keys(start_date)
                                    self._log_event("INFO", f"Filled Start Date for experience {i+1}: {start_date}")
                                    filled_start_date = True
                                    break
                                except TimeoutException:
                                    self._log_event("DEBUG", f"Start Date field not found with {sd_locator} for exp {i+1}.")
                                except Exception as e_sd:
                                    self._log_event("WARN", f"Error filling Start Date with {sd_locator} for exp {i+1}: {e_sd}")
                                    break
                            if not filled_start_date:
                                 self._log_event("WARN", f"Could not fill Start Date for experience {i+1}.")
                        else:
                            self._log_event("WARN", f"No Start Date provided for experience {i+1}.")

                        # End Date (MM/YYYY, "Present", or text)
                        end_date = exp.get("end_date")
                        if end_date:
                            currently_work_here_checkbox_locator = (By.XPATH, "(//input[@data-automation-id='currentlyWorkHere' and @type='checkbox'])[last()]")
                            
                            if end_date.lower() == "present":
                                try:
                                    checkbox = self.wait.until(EC.element_to_be_clickable(currently_work_here_checkbox_locator))
                                    if not checkbox.is_selected(): # Click only if not already selected
                                        self.driver.execute_script("arguments[0].click();", checkbox) # JS click for reliability
                                    self._log_event("INFO", f"Checked 'I currently work here' for experience {i+1}.")
                                except TimeoutException:
                                    self._log_event("WARN", f"'I currently work here' checkbox not found for exp {i+1}. Attempting to write 'Present' in date field if available.")
                                    # Fallback: try to write "Present" into the end date field
                                    end_date_locators_fallback = [(By.XPATH, "(//input[@data-automation-id='endDate' or contains(@data-automation-id, 'endDate') or @data-automation-id='toDate'])[last()]")]
                                    filled_end_date_text_fallback = False
                                    for ed_locator_fb in end_date_locators_fallback:
                                        try:
                                            end_date_el_fb = self.wait.until(EC.visibility_of_element_located(ed_locator_fb))
                                            end_date_el_fb.clear()
                                            end_date_el_fb.send_keys(end_date) # Send "Present"
                                            self._log_event("INFO", f"Filled End Date for experience {i+1} with text (fallback): {end_date}")
                                            filled_end_date_text_fallback = True
                                            break
                                        except TimeoutException: self._log_event("DEBUG", f"End Date field (text fallback) not found with {ed_locator_fb} for exp {i+1}.")
                                        except Exception as e_ed_fb_fill: self._log_event("WARN", f"Error filling End Date (text fallback) with {ed_locator_fb} for exp {i+1}: {e_ed_fb_fill}"); break
                                    if not filled_end_date_text_fallback: self._log_event("WARN", f"Could not fill End Date as text 'Present' (fallback) for experience {i+1}.")
                                except Exception as e_checkbox: # Catch other errors related to checkbox interaction
                                    self._log_event("ERROR", f"Error handling 'I currently work here' checkbox for exp {i+1}: {e_checkbox}")
                            else: # Specific end date provided
                                end_date_locators = [(By.XPATH, "(//input[@data-automation-id='endDate' or contains(@data-automation-id, 'endDate') or @data-automation-id='toDate'])[last()]")]
                                filled_end_date = False
                                for ed_locator in end_date_locators:
                                    try:
                                        # Ensure "I currently work here" is unchecked if providing a specific end date
                                        try:
                                            checkbox = self.wait.until(EC.presence_of_element_located(currently_work_here_checkbox_locator))
                                            if checkbox.is_selected():
                                                self.driver.execute_script("arguments[0].click();", checkbox)
                                                self._log_event("INFO", f"Unchecked 'I currently work here' as specific end date is provided for exp {i+1}.")
                                                time.sleep(0.3) # Allow UI to update
                                        except TimeoutException: pass # Checkbox not found, proceed
                                        except Exception as e_uncheck_cb: self._log_event("WARN", f"Could not uncheck 'I currently work here' for exp {i+1}: {e_uncheck_cb}")

                                        end_date_el = self.wait.until(EC.visibility_of_element_located(ed_locator))
                                        end_date_el.clear()
                                        end_date_el.send_keys(end_date)
                                        self._log_event("INFO", f"Filled End Date for experience {i+1}: {end_date}")
                                        filled_end_date = True
                                        break
                                    except TimeoutException: self._log_event("DEBUG", f"End Date field not found with {ed_locator} for exp {i+1}.")
                                    except Exception as e_ed_fill: self._log_event("WARN", f"Error filling End Date with {ed_locator} for exp {i+1}: {e_ed_fill}"); break
                                if not filled_end_date: self._log_event("WARN", f"Could not fill End Date for experience {i+1}.")
                        else:
                            self._log_event("WARN", f"No End Date provided for experience {i+1}.")

                        # Description/Summary
                        description = exp.get("description") or exp.get("summary")
                        if description:
                            # Common IDs: 'description', 'jobDescription', 'summary', 'roleDescription'
                            desc_locator = (By.XPATH, "(//textarea[@data-automation-id='description' or @data-automation-id='jobDescription' or @data-automation-id='summary' or @data-automation-id='roleDescription'])[last()]")
                            desc_el = self.wait.until(EC.visibility_of_element_located(desc_locator))
                            desc_el.clear()
                            desc_el.send_keys(description)
                            self._log_event("INFO", f"Filled Description for experience {i+1}.")
                        
                        self._take_screenshot(f"workday_exp_filled_fields_{i+1}")

                        # Click "Save" for this experience entry
                        # Workday might have "Save", "Done", or "Save and Add Another"
                        save_experience_locators = [
                            (By.XPATH, "(//button[@data-automation-id='saveButton' and not(contains(@title, 'Save and Continue')) and not(contains(@title, 'Save & Continue'))])[last()]"), # Contextual save for this block
                            (By.XPATH, "(//button[@data-automation-id='saveAndAddAnotherButton'])[last()]"),
                            (By.XPATH, "//button[@data-automation-id='saveButton']"), # More general save
                            (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save') and not(contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')) and not(contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'exit'))]"),
                            (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'done') and not(contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'all done'))]")
                        ]
                        saved_this_entry = False
                        for save_locator in save_experience_locators:
                            if self._click_element_robustly(save_locator, f"Save Experience Entry {i+1} Button", timeout=7):
                                self._log_event("INFO", f"Clicked 'Save' (or similar) for experience entry {i+1} using {save_locator}.")
                                saved_this_entry = True
                                time.sleep(3.0) # Wait for save operation and potential UI update (e.g., form closes, "Add Another" appears)
                                self._take_screenshot(f"workday_exp_saved_{i+1}")
                                break # Assume one save click is enough
                        
                        if not saved_this_entry:
                            self._log_event("WARN", f"Could not click 'Save' (or similar) for experience entry {i+1}. It might auto-save, or the button was not found/interactable.")
                            self._take_screenshot(f"workday_exp_save_fail_{i+1}")

                    except Exception as e_exp_fill_details:
                        self._log_event("ERROR", f"Error filling details for experience {i+1} ({exp.get('title', 'N/A')} at {exp.get('company', 'N/A')}): {e_exp_fill_details}")
                        self._take_screenshot(f"workday_exp_fill_detail_error_{i+1}")
                        # Continue to the next experience entry in the loop, as per requirements
                
                self._log_event("INFO", "Finished processing all Workday work experience entries from profile.")

            except Exception as e_work_exp_main_section:
                self._log_event("ERROR", f"A general error occurred in the Workday work experience section: {e_work_exp_main_section}")
                self._take_screenshot("workday_work_experience_section_general_error")
            # --- END OF WORK EXPERIENCE SECTION ---

            # --- EDUCATION SECTION ---
            self._log_event("INFO", "Attempting to add education section.")
            try:
                education_entries = self.user_profile.get("education", [])
                if not education_entries:
                    self._log_event("INFO", "No education entries found in profile to add.")
                else:
                    self._log_event("INFO", f"Found {len(education_entries)} education entries to process.")

                add_education_button_locators = [
                    (By.XPATH, "//button[@data-automation-id='addEducation']"),
                    (By.XPATH, "//button[@data-automation-id='addAnotherEducation']"),
                    (By.XPATH, "//button[contains(@aria-label, 'Add Education') or contains(normalize-space(.), 'Add Education')]")
                ]

                for i, edu in enumerate(education_entries):
                    self._log_event("INFO", f"Adding education {i+1}/{len(education_entries)}: {edu.get('degree', 'N/A')} from {edu.get('university', 'N/A')}")
                    
                    clicked_add_edu_button = False
                    for locator in add_education_button_locators:
                        if self._click_element_robustly(locator, f"Add Education Button (Entry {i+1})", timeout=5):
                            self._log_event("INFO", f"Clicked 'Add Education' button for entry {i+1} using {locator}.")
                            clicked_add_edu_button = True
                            time.sleep(2.5) # Wait for form to appear/update
                            self._take_screenshot(f"workday_edu_add_clicked_{i+1}")
                            break
                    
                    if not clicked_add_edu_button:
                        self._log_event("WARN", f"Could not click an 'Add Education' button for entry {i+1}. Assuming form is already present or became available.")
                        self._take_screenshot(f"workday_edu_add_btn_fail_or_not_needed_{i+1}")

                    try:
                        # School/University Name
                        university = edu.get("university")
                        if university:
                            uni_locator = (By.XPATH, "(//input[@data-automation-id='school' or @data-automation-id='institution'])[last()]")
                            uni_el = self.wait.until(EC.visibility_of_element_located(uni_locator))
                            uni_el.clear()
                            uni_el.send_keys(university)
                            self._log_event("INFO", f"Filled University/School for education {i+1}: {university}")
                        else:
                            self._log_event("WARN", f"No University/School provided for education {i+1}.")

                        # Degree
                        degree = edu.get("degree")
                        if degree:
                            degree_locator = (By.XPATH, "(//input[@data-automation-id='degree'])[last()]") # Common, but might need dropdown handling
                            # TODO: Handle if degree is a dropdown (common in Workday)
                            # For now, assuming text input. If it's a button opening a list:
                            # 1. Click degree field (which might be a button).
                            # 2. Wait for dropdown/search box.
                            # 3. Type degree into search box.
                            # 4. Click matching item from list.
                            degree_el = self.wait.until(EC.visibility_of_element_located(degree_locator))
                            degree_el.clear()
                            degree_el.send_keys(degree)
                            self._log_event("INFO", f"Filled Degree for education {i+1}: {degree}")
                        else:
                            self._log_event("WARN", f"No Degree provided for education {i+1}.")

                        # Major/Field of Study
                        major = edu.get("major")
                        if major:
                            major_locator = (By.XPATH, "(//input[@data-automation-id='fieldOfStudy' or @data-automation-id='major'])[last()]") # Common
                            # TODO: Similar to degree, this could be a dropdown/searchable list.
                            major_el = self.wait.until(EC.visibility_of_element_located(major_locator))
                            major_el.clear()
                            major_el.send_keys(major)
                            self._log_event("INFO", f"Filled Major/Field of Study for education {i+1}: {major}")
                        else:
                            self._log_event("WARN", f"No Major/Field of Study provided for education {i+1}.")
                        
                        # Graduation Date (MM/YYYY or text)
                        grad_date = edu.get("graduation_date")
                        if grad_date:
                            # Workday often has separate month/year dropdowns or a text field that expects MM/YYYY
                            # For simplicity, trying direct input first.
                            # More robust: handle date pickers or separate month/year fields.
                            grad_date_locator = (By.XPATH, "(//input[@data-automation-id='graduationDate' or @data-automation-id='endDate'])[last()]")
                            try:
                                grad_date_el = self.wait.until(EC.visibility_of_element_located(grad_date_locator))
                                grad_date_el.clear()
                                grad_date_el.send_keys(grad_date)
                                self._log_event("INFO", f"Filled Graduation Date for education {i+1}: {grad_date}")
                            except TimeoutException:
                                self._log_event("WARN", f"Graduation Date text input field not found with {grad_date_locator} for edu {i+1}. Date might require dropdowns.")
                                # TODO: Add logic for month/year dropdowns if text input fails
                            except Exception as e_grad_date:
                                self._log_event("ERROR", f"Error filling Graduation Date for education {i+1}: {e_grad_date}")
                        else:
                            self._log_event("WARN", f"No Graduation Date provided for education {i+1}.")

                        # GPA (if applicable)
                        gpa = edu.get("gpa")
                        if gpa:
                            gpa_locator = (By.XPATH, "(//input[@data-automation-id='gpaOverall' or @data-automation-id='gpa'])[last()]")
                            try:
                                gpa_el = self.wait.until(EC.visibility_of_element_located(gpa_locator))
                                gpa_el.clear()
                                gpa_el.send_keys(gpa)
                                self._log_event("INFO", f"Filled GPA for education {i+1}: {gpa}")
                            except TimeoutException:
                                self._log_event("WARN", f"GPA field not found for education {i+1}.")
                            except Exception as e_gpa:
                                self._log_event("ERROR", f"Error filling GPA for education {i+1}: {e_gpa}")
                        
                        self._take_screenshot(f"workday_edu_filled_fields_{i+1}")

                        # Click "Save" for this education entry
                        save_education_locators = [
                            (By.XPATH, "(//button[@data-automation-id='saveButton' and not(contains(@title, 'Save and Continue'))])[last()]"),
                            (By.XPATH, "(//button[@data-automation-id='saveAndAddAnotherButton'])[last()]"), # If adding multiple
                            (By.XPATH, "//button[@data-automation-id='saveEducationButton']"), # Specific to education section
                            (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save') and not(contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue'))]"),
                            (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'done')]")
                        ]
                        saved_this_edu_entry = False
                        for save_locator in save_education_locators:
                            if self._click_element_robustly(save_locator, f"Save Education Entry {i+1} Button", timeout=7):
                                self._log_event("INFO", f"Clicked 'Save' (or similar) for education entry {i+1} using {save_locator}.")
                                saved_this_edu_entry = True
                                time.sleep(3.0) # Wait for save and UI update
                                self._take_screenshot(f"workday_edu_saved_{i+1}")
                                break
                        
                        if not saved_this_edu_entry:
                            self._log_event("WARN", f"Could not click 'Save' (or similar) for education entry {i+1}.")
                            self._take_screenshot(f"workday_edu_save_fail_{i+1}")

                    except Exception as e_edu_fill_details:
                        self._log_event("ERROR", f"Error filling details for education {i+1} ({edu.get('degree', 'N/A')}): {e_edu_fill_details}")
                        self._take_screenshot(f"workday_edu_fill_detail_error_{i+1}")
                        # Continue to the next education entry
                
                self._log_event("INFO", "Finished processing all Workday education entries from profile.")

            except Exception as e_education_main_section:
                self._log_event("ERROR", f"A general error occurred in the Workday education section: {e_education_main_section}")
                self._take_screenshot("workday_education_section_general_error")
            # --- END OF EDUCATION SECTION ---

            # Remember to switch back from iframe if one was entered
            try:
                self.driver.switch_to.default_content()
                self._log_event("INFO", "Switched back to default content after form filling (if applicable).")
            except Exception:
                pass # May not have been in an iframe

        else:
            self._log_event("WARN", f"Form filling not implemented for platform: {self.platform}")
        return True # Placeholder, actual success depends on fields filled

    def _handle_standard_questions(self):
        """
        Answers standard screening questions using pre-configured answers.
        Identifies questions on the page, matches them against self.standard_answers,
        and attempts to select the corresponding answer.
        Stops automation and returns False if an unmatched question is found.
        """
        self._log_event("INFO", "Scanning for standard questions...")
        if self.platform != "Workday":
            self._log_event("WARN", f"Standard question handling not implemented for platform: {self.platform}")
            return True # Or False, depending on desired behavior for non-Workday

        # Ensure standard_answers is a dict and not empty
        if not isinstance(self.standard_answers, dict) or not self.standard_answers:
            self._log_event("INFO", "No standard answers configured or provided. Skipping question handling.")
            return True

        # Switch to iframe if necessary (common for Workday forms)
        # This logic is similar to _fill_forms and _handle_login, might be refactored.
        iframe_switched_for_questions = False
        try:
            workday_iframe_locators = [
                (By.XPATH, "//iframe[contains(@src, 'myworkdayjobs.com')]"),
                (By.XPATH, "//iframe[contains(@title, 'Workday')]"),
                (By.XPATH, "//iframe[@data-automation-id='workdayApplicationFrame']")
            ]
            for locator in workday_iframe_locators:
                try:
                    WebDriverWait(self.driver, 3).until(EC.frame_to_be_available_and_switch_to_it(locator)) # Short wait
                    self._log_event("INFO", f"Switched to Workday iframe for question handling using: {locator}")
                    iframe_switched_for_questions = True
                    time.sleep(0.5)
                    break
                except TimeoutException:
                    self._log_event("DEBUG", f"Workday iframe not found with {locator} for question handling.")
            if not iframe_switched_for_questions:
                self._log_event("INFO", "No specific Workday iframe found for questions, assuming main content or already switched.")
        except Exception as e_iframe_form:
            self._log_event("WARN", f"Error switching to iframe for questions: {e_iframe_form}")


        # Common XPaths for question text elements in Workday.
        # These might need refinement based on actual Workday structures.
        # Look for elements that typically contain question text.
        question_text_locators = [
            "//label[contains(@class, 'gwt-Label') and string-length(normalize-space(.)) > 15 and not(ancestor::*[@data-automation-id='formField-fileUploaderDropZone'])]", # General labels, not file uploaders
            "//div[contains(@class, 'gwt-Label') and string-length(normalize-space(.)) > 15]",
            "//span[contains(@data-automation-id, 'formLabel') and string-length(normalize-space(.)) > 15]",
            "//p[contains(@data-automation-id, 'richText') and string-length(normalize-space(.)) > 15]", # Sometimes questions are in rich text
            "//div[contains(@class, 'inputField')]/label[string-length(normalize-space(.)) > 15]", # Label directly associated with an input field group
        ]

        # Find all potential question elements on the page
        # This is a broad approach; specific sections might be targeted in a more advanced version.
        all_potential_question_elements = []
        for q_xpath in question_text_locators:
            try:
                elements = self.driver.find_elements(By.XPATH, q_xpath)
                for el in elements:
                    if el.is_displayed(): # Only consider visible elements
                        all_potential_question_elements.append(el)
            except NoSuchElementException:
                pass # It's okay if some locators don't find anything

        if not all_potential_question_elements:
            self._log_event("INFO", "No potential question text elements found on the page using current locators.")
            # Before returning True, switch back from iframe if one was entered
            if iframe_switched_for_questions:
                try:
                    self.driver.switch_to.default_content()
                    self._log_event("INFO", "Switched back to default content after question handling (no questions found).")
                except Exception: pass
            return True

        self._log_event("INFO", f"Found {len(all_potential_question_elements)} potential question elements. Processing them.")
        
        processed_questions_texts = set() # To avoid processing the same question text multiple times if found by different locators

        for question_element in all_potential_question_elements:
            try:
                question_text_raw = question_element.text
                if not question_text_raw or len(question_text_raw.strip()) < 10: # Skip very short texts
                    continue

                question_text = question_text_raw.strip().lower().replace('*', '').replace(':', '') # Normalize
                question_text = ' '.join(question_text.split()) # Normalize whitespace

                if not question_text or question_text in processed_questions_texts:
                    continue # Skip empty or already processed questions
                
                processed_questions_texts.add(question_text)
                self._log_event("INFO", f"Found question: '{question_text_raw}' (Normalized: '{question_text}')")
                self._take_screenshot(f"found_question_{question_text[:30].replace(' ', '_')}")

                matched_answer = None
                # Simple exact match first (after normalizing keys in standard_answers as well)
                normalized_standard_answers = {k.strip().lower().replace('*', '').replace(':', ''): v for k, v in self.standard_answers.items()}
                
                if question_text in normalized_standard_answers:
                    matched_answer = normalized_standard_answers[question_text]
                else:
                    # Basic partial match (e.g. if question_text is a substring of a key or vice-versa)
                    for key_sa, val_sa in normalized_standard_answers.items():
                        if question_text in key_sa or key_sa in question_text:
                            # This could be too broad, needs careful testing.
                            # For now, prefer more exact matches.
                            # Let's stick to closer matches for now.
                            # A more robust solution would be fuzzy matching.
                            pass # Placeholder for more advanced matching

                if matched_answer:
                    self._log_event("SUCCESS", f"Matched question '{question_text_raw}' to configured answer '{matched_answer}'.")
                    
                    # Now, attempt to find and select the answer element(s)
                    # This is highly dependent on Workday's structure for Q&A
                    # We need to find the input associated with this question_element
                    # The input might be a sibling, child of parent, or identified by aria-labelledby

                    # Attempt 1: Radio buttons or checkboxes near the question label
                    # Common pattern: label followed by a div containing inputs, or inputs as siblings
                    # Try to find inputs within a reasonable proximity or common parent.
                    # This needs to be robust.
                    
                    # Scenario 1: Radio buttons by label text or value
                    # Workday often uses data-automation-id for radio button groups or individual radios
                    # Example: <div data-automation-id="radioGroup"> <label><input type="radio">Yes</label> </div>
                    # Or: <input type="radio" value="Yes" name="question123"> <label>Yes</label>
                    
                    answer_found_and_clicked = False
                    try:
                        # Look for radio buttons first
                        # Try to find radio buttons whose label text matches the answer
                        radio_options_xpath = f".//ancestor::div[contains(@class, 'FieldSet') or contains(@class, 'gwt-DisclosurePanel') or contains(@class, 'StandardQuestion') or contains(@class, 'questionItem') or count(./descendant::input[@type='radio' or @type='checkbox']) > 0][1]//label[normalize-space(.)='{matched_answer}']//input[@type='radio']"
                        # Fallback: radio buttons whose value attribute matches the answer
                        radio_options_value_xpath = f".//ancestor::div[contains(@class, 'FieldSet') or contains(@class, 'gwt-DisclosurePanel') or contains(@class, 'StandardQuestion') or contains(@class, 'questionItem') or count(./descendant::input[@type='radio' or @type='checkbox']) > 0][1]//input[@type='radio' and @value='{matched_answer}']"
                        
                        # Try to find checkboxes whose label text matches the answer
                        checkbox_options_xpath = f".//ancestor::div[contains(@class, 'FieldSet') or contains(@class, 'gwt-DisclosurePanel') or contains(@class, 'StandardQuestion') or contains(@class, 'questionItem') or count(./descendant::input[@type='radio' or @type='checkbox']) > 0][1]//label[normalize-space(.)='{matched_answer}']//input[@type='checkbox']"


                        possible_answer_elements = []
                        try:
                            # Search relative to the question_element
                            possible_answer_elements.extend(question_element.find_elements(By.XPATH, radio_options_xpath))
                        except NoSuchElementException: pass
                        if not possible_answer_elements:
                             try: possible_answer_elements.extend(question_element.find_elements(By.XPATH, radio_options_value_xpath))
                             except NoSuchElementException: pass
                        if not possible_answer_elements:
                             try: possible_answer_elements.extend(question_element.find_elements(By.XPATH, checkbox_options_xpath))
                             except NoSuchElementException: pass

                        # If not found relative to question_element, try searching globally (less ideal but a fallback)
                        if not possible_answer_elements:
                            self._log_event("DEBUG", f"Could not find answer '{matched_answer}' relative to question. Trying global search for radio/checkbox.")
                            global_radio_xpath = f"//label[normalize-space(.)='{matched_answer}']//input[@type='radio' and not(@disabled)]"
                            global_radio_value_xpath = f"//input[@type='radio' and @value='{matched_answer}' and not(@disabled)]"
                            global_checkbox_xpath = f"//label[normalize-space(.)='{matched_answer}']//input[@type='checkbox' and not(@disabled)]"
                            try: possible_answer_elements.extend(self.driver.find_elements(By.XPATH, global_radio_xpath))
                            except NoSuchElementException: pass
                            if not possible_answer_elements:
                                try: possible_answer_elements.extend(self.driver.find_elements(By.XPATH, global_radio_value_xpath))
                                except NoSuchElementException: pass
                            if not possible_answer_elements:
                                try: possible_answer_elements.extend(self.driver.find_elements(By.XPATH, global_checkbox_xpath))
                                except NoSuchElementException: pass
                        
                        for ans_element in possible_answer_elements:
                            if ans_element.is_displayed() and ans_element.is_enabled():
                                self._log_event("INFO", f"Attempting to select answer '{matched_answer}' for question '{question_text_raw}'.")
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", ans_element)
                                time.sleep(0.3) # Brief pause after scroll

                                try:
                                    ans_element.click()
                                    self._log_event("SUCCESS", f"Successfully clicked answer '{matched_answer}' for question '{question_text_raw}' using standard click.")
                                    self._take_screenshot(f"answered_{question_text[:30].replace(' ', '_')}")
                                    answer_found_and_clicked = True
                                    time.sleep(0.5) # Brief pause after clicking
                                    break # Move to next question
                                except Exception as e_click: # Catches ElementClickInterceptedException and others
                                    self._log_event("WARN", f"Standard click failed for answer '{matched_answer}': {type(e_click).__name__}. Attempting JavaScript click.")
                                    self._take_screenshot(f"click_intercepted_{question_text[:30].replace(' ', '_')}")
                                    try:
                                        self.driver.execute_script("arguments[0].click();", ans_element)
                                        self._log_event("SUCCESS", f"Successfully clicked answer '{matched_answer}' for question '{question_text_raw}' using JavaScript click.")
                                        self._take_screenshot(f"answered_js_click_{question_text[:30].replace(' ', '_')}")
                                        answer_found_and_clicked = True
                                        time.sleep(0.5)
                                        break # Move to next question
                                    except Exception as e_js_click:
                                        self._log_event("ERROR", f"JavaScript click also failed for answer '{matched_answer}': {type(e_js_click).__name__}")
                                        self._take_screenshot(f"js_click_failed_{question_text[:30].replace(' ', '_')}")
                        
                        if not answer_found_and_clicked:
                             # Scenario 2: Dropdowns (simple select tags or Workday's custom ones)
                            self._log_event("DEBUG", f"Radio/checkbox for '{matched_answer}' not directly found or clicked. Checking for dropdowns.")
                            # Workday dropdowns often use data-automation-id like 'selectWidget', 'comboBoxInput'
                            # The question_element itself might be a label for a dropdown, or the dropdown is nearby.
                            # This is a simplified approach for select tags. Custom Workday dropdowns are more complex.
                            try:
                                # Find a select element near the question label
                                # This XPath tries to find a select whose preceding label (or label of parent div) matches question_text_raw
                                # Or a select that is a sibling or child of a common ancestor.
                                # This is very generic and might need specific data-automation-ids for reliability.
                                dropdown_xpath = f".//ancestor::div[contains(@class, 'FieldSet') or contains(@class, 'gwt-DisclosurePanel') or contains(@class, 'StandardQuestion') or contains(@class, 'questionItem')][1]//select"
                                # More specific: dropdown associated by data-automation-id of a parent or self
                                dropdown_data_auto_id_xpath = f"//div[@data-automation-id='formField-{question_text_raw.replace(' ','')}']//select" # Heuristic
                                
                                potential_dropdowns = []
                                try: potential_dropdowns.extend(question_element.find_elements(By.XPATH, dropdown_xpath))
                                except NoSuchElementException: pass
                                
                                # If not found relative, try a more global search if question text is very specific
                                # This is risky, better to associate with question_element
                                # For now, let's assume dropdown is near question_element

                                for dropdown_element in potential_dropdowns:
                                    if dropdown_element.is_displayed() and dropdown_element.is_enabled():
                                        self._log_event("INFO", f"Attempting to select '{matched_answer}' in a dropdown for question '{question_text_raw}'.")
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_element)
                                        time.sleep(0.3)
                                        select = Select(dropdown_element)
                                        select.select_by_visible_text(matched_answer)
                                        self._log_event("SUCCESS", f"Successfully selected '{matched_answer}' in dropdown for '{question_text_raw}'.")
                                        self._take_screenshot(f"dropdown_answered_{question_text[:30].replace(' ', '_')}")
                                        answer_found_and_clicked = True
                                        time.sleep(0.5)
                                        break
                                if answer_found_and_clicked:
                                    break # From the loop of potential dropdowns

                            except NoSuchElementException:
                                self._log_event("WARN", f"Could not find a standard select dropdown for answer '{matched_answer}' for question '{question_text_raw}'. Custom Workday dropdowns might need specific handling.")
                            except Exception as e_dropdown:
                                self._log_event("ERROR", f"Error selecting '{matched_answer}' in dropdown for '{question_text_raw}': {e_dropdown}")
                                self._take_screenshot(f"dropdown_error_{question_text[:30].replace(' ', '_')}")
                        
                        if not answer_found_and_clicked:
                            self._log_event("WARN", f"Could not find or interact with an input for answer '{matched_answer}' for question '{question_text_raw}'.")
                            # This specific answer could not be processed. Depending on strictness, this could be a failure.
                            # For now, we continue to other questions, but if ANY question is matched but not answerable, it's an issue.
                            # However, the main failure is an UNMATCHED question.
                            # If a question is matched but its answer input isn't found, that's a configuration/selector issue.
                            # Let's consider this a point where user intervention might be needed for this specific question.
                            # For now, we'll let it pass and rely on the "unmatched question" logic to stop if needed.

                    except Exception as e_ans:
                        self._log_event("ERROR", f"Error while trying to answer question '{question_text_raw}' with '{matched_answer}': {e_ans}")
                        self._take_screenshot(f"error_answering_{question_text[:30].replace(' ', '_')}")
                        # This is an error during answering, might not be an "unmatched" question.
                        # Depending on policy, this could also be a reason to stop.
                        # For now, we'll log and continue to see if other questions can be handled.
                        # A robust system might retry or flag this specific question.

                else: # No match found in self.standard_answers
                    self._log_event("PENDING", f"Unmatched question found: '{question_text_raw}'. Stopping automation for user review.")
                    self._take_screenshot("unmatched_question_found")
                    # Update application status in DB if possible (e.g., to 'pending_user_input')
                    # Example: app_record = self.db_session.query(Application).get(self.application_id)
                    # if app_record: app_record.status = "pending_user_input"
                    # self.db_session.commit()
                    if iframe_switched_for_questions:
                        try:
                            self.driver.switch_to.default_content()
                            self._log_event("INFO", "Switched back to default content after unmatched question.")
                        except Exception: pass
                    return False # Critical: Stop automation

            except StaleElementReferenceException:
                self._log_event("WARN", "Stale element reference encountered while processing questions. Page might have changed. Re-evaluating.")
                # Optionally, re-fetch elements or break/return False
                # For now, just log and continue with the next potential element if any, or let it fail if it's critical.
                # This might require a re-scan. For simplicity, we'll let this iteration skip.
                continue
            except Exception as e_outer_loop:
                self._log_event("ERROR", f"Unexpected error processing a question element: {e_outer_loop}")
                # Continue to the next question element if possible
                continue
        
        self._log_event("INFO", "Finished scanning all identified potential questions.")
        if iframe_switched_for_questions:
            try:
                self.driver.switch_to.default_content()
                self._log_event("INFO", "Switched back to default content after question handling.")
            except Exception: pass
        return True # All found questions were either matched and attempted, or no questions triggered a stop

    def _upload_documents(self):
        """Uploads resume and potentially a cover letter to the application platform."""
        self._log_event("INFO", f"Starting document upload process for platform: {self.platform}")
        if self.platform != "Workday":
            self._log_event("WARN", f"Document upload logic not implemented for platform: {self.platform}")
            return False

        # --- Resume Upload ---
        resume_uploaded = False
        if not self.user_profile or not hasattr(self.user_profile, 'resume_path') or not self.user_profile.resume_path:
            self._log_event("WARN", "User profile resume path not found or not set. Skipping resume upload.")
        elif not os.path.exists(self.user_profile.resume_path):
            self._log_event("WARN", f"Resume file not found at path: {self.user_profile.resume_path}. Skipping resume upload.")
        else:
            self._log_event("INFO", f"Attempting to upload resume from: {self.user_profile.resume_path}")
            try:
                # Common Workday resume input selectors
                resume_input_locators = [
                    (By.XPATH, "//input[@type='file' and contains(@data-automation-id, 'resume')]"),
                    (By.XPATH, "//button[@data-automation-id='resumeUpload']"), # Sometimes it's a button that opens a dialog
                    (By.XPATH, "//input[@data-automation-id='fileInput']") # Generic fallback if specific not found
                ]
                resume_input_element = None
                for locator_type, locator_value in resume_input_locators:
                    try:
                        # For file inputs, they might be hidden. We need presence.
                        # If it's a button, it needs to be clickable.
                        if "button" in locator_value:
                             # This case is more complex as send_keys won't work on a button.
                             # It would require clicking the button and then handling the OS file dialog,
                             # which is beyond typical Selenium capabilities without tools like AutoIt or PyAutoGUI.
                             # For now, we'll assume direct file input or a scenario where send_keys works on a styled button.
                             # A more robust solution might involve finding the *actual* hidden file input associated with the button.
                            self._log_event("DEBUG", f"Locator {locator_value} is a button, direct send_keys might not work. Looking for associated input.")
                            # Try to find a nearby input type=file
                            associated_input = self.driver.find_element(locator_type, locator_value + "/ancestor::div[1]//input[@type='file']")
                            if associated_input:
                                resume_input_element = associated_input
                                self._log_event("INFO", f"Located associated resume file input for button using: {locator_value} -> associated input")
                                break
                            else: # If no associated input, we might try sending keys to the button if it's a special component
                                resume_input_element = self.wait.until(EC.presence_of_element_located((locator_type, locator_value)))
                                self._log_event("INFO", f"Located resume upload button (will attempt send_keys): {locator_value}")
                                break
                        else:
                            resume_input_element = self.wait.until(EC.presence_of_element_located((locator_type, locator_value)))
                            self._log_event("INFO", f"Located resume upload input using: {locator_value}")
                            break
                    except TimeoutException:
                        self._log_event("DEBUG", f"Resume input/button not found with locator: {locator_value}")
                
                if not resume_input_element:
                    self._log_event("ERROR", "Could not locate the resume upload input element on the page.")
                    self._take_screenshot("resume_upload_input_not_found")
                    # return False # Decide if this is a hard fail

                if resume_input_element:
                    # Ensure element is visible if it's an input, though send_keys can work on hidden inputs
                    # self.driver.execute_script("arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';", resume_input_element)
                    resume_input_element.send_keys(self.user_profile.resume_path)
                    self._log_event("SUCCESS", "Resume file sent to input element.")
                    self._take_screenshot("resume_uploaded")
                    time.sleep(random.uniform(2, 4)) # Wait for upload to register
                    resume_uploaded = True

            except NoSuchElementException:
                self._log_event("ERROR", "Resume upload input element not found (NoSuchElementException).")
                self._take_screenshot("resume_upload_no_such_element")
            except TimeoutException:
                self._log_event("ERROR", "Timeout waiting for resume upload input element.")
                self._take_screenshot("resume_upload_timeout")
            except Exception as e:
                self._log_event("ERROR", f"An error occurred during resume upload: {e}")
                self._take_screenshot("resume_upload_error")
        
        # --- Cover Letter Upload (Conditional) ---
        cover_letter_uploaded = False
        # Ensure self.config is a dictionary and get the value safely
        auto_attach_cl = isinstance(self.config, dict) and self.config.get("auto_attach_cover_letter", False)

        if auto_attach_cl:
            self._log_event("INFO", "Attempting to generate and upload cover letter.")
            if not hasattr(self, 'job_details') or not self.job_details:
                self._log_event("WARN", "Job details (title, company, description) not available. Cannot generate cover letter.")
            else:
                job_title = self.job_details.get("title", "the job")
                company_name = self.job_details.get("company", "your company")
                job_description = self.job_details.get("description", "")

                if not job_description:
                    self._log_event("WARN", "Job description is empty. Cover letter quality may be affected or generation skipped.")
                
                try:
                    # Ensure user_profile is in the expected dict format for generate_cover_letter if it's an object
                    profile_data_for_cl = self.user_profile.__dict__ if hasattr(self.user_profile, '__dict__') else self.user_profile

                    cover_letter_content = generate_cover_letter(
                        job_title=job_title,
                        company_name=company_name,
                        job_description=job_description,
                        user_profile_data=profile_data_for_cl
                    )
                    
                    temp_cl_file = None
                    if cover_letter_content:
                        # Save to a temporary file
                        import tempfile # Import here to keep it local if not used elsewhere frequently
                        fd, temp_cl_path = tempfile.mkstemp(suffix=".txt", prefix="cover_letter_")
                        with os.fdopen(fd, 'w', encoding='utf-8') as tmp:
                            tmp.write(cover_letter_content)
                        temp_cl_file = temp_cl_path
                        self._log_event("INFO", f"Cover letter generated and saved to temporary file: {temp_cl_file}")

                        # Locate cover letter input element
                        # Common Workday cover letter input selectors
                        cl_input_locators = [
                            (By.XPATH, "//input[@type='file' and contains(@data-automation-id, 'coverLetter')]"),
                            (By.XPATH, "//button[@data-automation-id='coverLetterUpload']"),
                            (By.XPATH, "//input[@data-automation-id='fileInput']") # Generic fallback
                        ]
                        cl_input_element = None
                        for locator_type, locator_value in cl_input_locators:
                            try:
                                if "button" in locator_value:
                                    self._log_event("DEBUG", f"Locator {locator_value} is a button for CL, direct send_keys might not work.")
                                    associated_input = self.driver.find_element(locator_type, locator_value + "/ancestor::div[1]//input[@type='file']")
                                    if associated_input:
                                        cl_input_element = associated_input
                                        self._log_event("INFO", f"Located associated cover letter file input for button using: {locator_value} -> associated input")
                                        break
                                    else:
                                        cl_input_element = self.wait.until(EC.presence_of_element_located((locator_type, locator_value)))
                                        self._log_event("INFO", f"Located cover letter upload button (will attempt send_keys): {locator_value}")
                                        break
                                else:
                                    cl_input_element = self.wait.until(EC.presence_of_element_located((locator_type, locator_value)))
                                    self._log_event("INFO", f"Located cover letter upload input using: {locator_value}")
                                    break
                            except TimeoutException:
                                self._log_event("DEBUG", f"Cover letter input/button not found with locator: {locator_value}")
                        
                        if not cl_input_element:
                            self._log_event("WARN", "Could not locate the cover letter upload input element. Skipping cover letter upload.")
                            self._take_screenshot("cover_letter_input_not_found")
                        
                        if cl_input_element:
                            cl_input_element.send_keys(temp_cl_file)
                            self._log_event("SUCCESS", "Cover letter file sent to input element.")
                            self._take_screenshot("cover_letter_uploaded")
                            time.sleep(random.uniform(2, 4)) # Wait for upload
                            cover_letter_uploaded = True
                    else:
                        self._log_event("WARN", "Cover letter generation returned empty content.")

                except Exception as e_cl:
                    self._log_event("ERROR", f"An error occurred during cover letter generation or upload: {e_cl}")
                    self._take_screenshot("cover_letter_error")
                finally:
                    if temp_cl_file and os.path.exists(temp_cl_file):
                        try:
                            os.remove(temp_cl_file)
                            self._log_event("INFO", f"Temporary cover letter file {temp_cl_file} deleted.")
                        except Exception as e_del:
                            self._log_event("WARN", f"Failed to delete temporary cover letter file {temp_cl_file}: {e_del}")
        else:
            self._log_event("INFO", "Cover letter attachment is disabled in config or config not available.")

        # Return True if resume (usually mandatory) was uploaded, or if only CL failed but resume was ok.
        # If resume upload failed, this method should probably indicate a more significant failure.
        if not resume_uploaded and (hasattr(self.user_profile, 'resume_path') and self.user_profile.resume_path and os.path.exists(self.user_profile.resume_path)):
             self._log_event("ERROR", "Resume upload failed or was skipped due to an error, and a resume was expected.")
             return False # Resume is critical

        self._log_event("SUCCESS", f"Document upload step completed. Resume uploaded: {resume_uploaded}, Cover Letter uploaded: {cover_letter_uploaded}")
        return True

    def run_automation(self):
        """
        Main method to run the full automation process.
        Returns a dictionary with status and relevant details.
        e.g., {"status": "pending_review", "screenshot_path": "path/to/img.png", "message": "Ready for review."}
              {"status": "failed", "error_message": "Failed at login.", "details": "..."}
              {"status": "success", "message": "Application submitted successfully."} (if full auto-submit is implemented)
        """
        if not self._init_driver():
            return {"status": "failed", "error_message": "WebDriver initialization failed."}
        
        # self._log_event("DEBUG", "Pausing for 5 seconds after driver init to observe browser.")
        # time.sleep(5) # Keep browser open for a moment

        try:
            if not self._navigate_to_job():
                return {"status": "failed", "error_message": "Failed to navigate to job URL."}
            
            # self._log_event("DEBUG", "Pausing for 3 seconds after navigation to observe page.")
            # time.sleep(3) # Keep browser open after navigation

            # --- Core Application Flow ---
            # These steps are placeholders and need platform-specific implementation
            if not self._handle_login():
                # _handle_login logs specifics, this is a general failure point
                return {"status": "failed", "error_message": "Login/Account creation step failed or incomplete."}
            
            if not self._fill_forms():
                return {"status": "failed", "error_message": "Form filling step failed or incomplete."}
            
            if not self._handle_standard_questions():
                # This might mean it's pending user input for a question
                # For now, treat as failure to proceed automatically
                return {"status": "failed", "error_message": "Standard questions step failed or requires manual input."}
            
            if not self._upload_documents():
                return {"status": "failed", "error_message": "Document upload step failed."}

            # --- Final Review Stage ---
            self._log_event("INFO", "Reached final review stage (Placeholder). Taking screenshot.")
            screenshot_path = self._take_screenshot("final_review")
            
            # This log indicates the automation reached the point of manual review.
            self._log_event("PENDING", "Application ready for manual review and submission.", screenshot_path=screenshot_path)
            
            return {
                "status": "pending_review",
                "message": "Application automation reached the review stage.",
                "screenshot_path": screenshot_path
            }

        except Exception as e:
            error_message = f"An unexpected error occurred during automation: {str(e)}"
            self._log_event("ERROR", error_message)
            screenshot = self._take_screenshot("unexpected_error")
            return {"status": "failed", "error_message": error_message, "details": str(e), "screenshot_path": screenshot}
        finally:
            if self.driver:
                self._log_event("INFO", "Closing WebDriver.")
                self.driver.quit()

# The run_application_task function has been moved to src/main.py as a Celery task.
# And now, even that is replaced by the multiprocessing system.

