# src/automation.py
import os
import time
import random
import string

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Import necessary components from the main app
# Need to handle imports carefully if running this standalone vs. via Flask app context
# For now, assume it might be called from a background task runner that has app context
# Or pass necessary data (profile, config, db session) as arguments
from src.utils import log_event
from src.models.models import Profile, StandardAnswer, Application
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
    def __init__(self, application_id, job_url, user_profile, standard_answers, config):
        self.application_id = application_id
        self.job_url = job_url
        self.user_profile = user_profile # Pass profile data (dict or Profile object)
        self.standard_answers = standard_answers # Pass list of QA pairs
        self.config = config # Pass config settings (e.g., auto_attach_cl)
        self.driver = None
        self.wait = None
        self.platform = "Unknown"

    def _init_driver(self):
        """Initializes the Selenium WebDriver."""
        try:
            log_event(self.application_id, "INFO", "Initializing WebDriver...")
            options = webdriver.ChromeOptions()
            # Add options like headless, incognito, user-agent if needed
            # options.add_argument("--headless")
            options.add_argument("--no-sandbox") # Often needed in containerized environments
            options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.maximize_window()
            self.wait = WebDriverWait(self.driver, 15) # Default wait time of 15 seconds
            log_event(self.application_id, "SUCCESS", "WebDriver initialized successfully.")
            return True
        except Exception as e:
            log_event(self.application_id, "ERROR", f"Failed to initialize WebDriver: {e}")
            return False

    def _take_screenshot(self, stage_name):
        """Takes a screenshot and saves it."""
        try:
            filename = f"app_{self.application_id}_{stage_name}_{int(time.time())}.png"
            filepath = os.path.join(SCREENSHOT_DIR, filename)
            self.driver.save_screenshot(filepath)
            log_event(self.application_id, "INFO", f"Screenshot saved: {filename}")
            return filepath
        except Exception as e:
            log_event(self.application_id, "WARN", f"Failed to take screenshot: {e}")
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

        log_event(self.application_id, "INFO", f"Detected platform: {self.platform}")
        # Update Application record in DB (requires db session or separate update mechanism)
        # Example: Application.query.get(self.application_id).detected_platform = self.platform
        # db.session.commit()

    def _navigate_to_job(self):
        """Navigates to the job application URL."""
        try:
            log_event(self.application_id, "INFO", f"Navigating to job URL: {self.job_url}")
            self.driver.get(self.job_url)
            time.sleep(2) # Allow initial page load
            # Check for immediate errors (e.g., 404)
            if "page not found" in self.driver.title.lower() or "404" in self.driver.title:
                 log_event(self.application_id, "ERROR", f"Job URL led to 'Page Not Found' or 404.")
                 return False
            log_event(self.application_id, "SUCCESS", "Successfully navigated to job page.")
            self._detect_platform() # Detect platform after navigation
            return True
        except Exception as e:
            log_event(self.application_id, "ERROR", f"Failed to navigate to job URL: {e}")
            self._take_screenshot("navigation_error")
            return False

    def _handle_login(self):
        """Handles login or account creation (Placeholder)."""
        log_event(self.application_id, "INFO", "Attempting login/account creation (Placeholder)...")
        # This requires platform-specific logic (Workday, Greenhouse, etc.)
        # 1. Find login/apply button
        # 2. Check if login form is present
        # 3. Try default credentials (self.user_profile.default_email)
        # 4. If fails, check for 'create account' option
        # 5. If creating account, use default email and generated password (if strategy allows)
        # 6. Log generated password and site if created
        # 7. If email exists / login fails / unknown state -> Log error and potentially stop/ask user

        if self.platform == "Workday":
            log_event(self.application_id, "INFO", "Attempting Workday login/account creation flow.")
            
            # Step 1: Click an "Apply" or "Apply with Workday" button on the job board page
            # This might need to be more robust, checking for multiple common XPaths/texts
            apply_button_xpaths = [
                "//a[contains(@data-automation-id, 'applyButton')]",
                "//button[contains(text(), 'Apply') or contains(text(), 'Apply Now') or contains(text(), 'Apply with Workday')]",
                "//a[contains(text(), 'Apply') or contains(text(), 'Apply Now') or contains(text(), 'Apply with Workday')]"
            ]
            apply_button_found = False
            for xpath in apply_button_xpaths:
                try:
                    apply_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", apply_button) # Scroll into view
                    time.sleep(0.5) # Brief pause after scroll
                    apply_button.click()
                    log_event(self.application_id, "INFO", f"Clicked 'Apply' button using XPath: {xpath}")
                    apply_button_found = True
                    time.sleep(5) # Wait for potential page transition or iframe load
                    break
                except (NoSuchElementException, TimeoutException):
                    log_event(self.application_id, "DEBUG", f"Apply button not found with XPath: {xpath}")
                    continue
            
            if not apply_button_found:
                log_event(self.application_id, "WARN", "Could not find a primary 'Apply' button on the job page.")
                self._take_screenshot("apply_button_not_found")
                # Depending on the site, the application might already be on a Workday page.
                # We can proceed to check for Workday specific elements directly.
                # return False # Or try to continue if already on Workday page

            # Step 2: Check if we are in a Workday iframe and switch to it if necessary
            # Workday often loads in an iframe.
            try:
                workday_iframe_xpath = "//iframe[contains(@src, 'myworkdayjobs.com') or contains(@title, 'Workday')]"
                self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.XPATH, workday_iframe_xpath)))
                log_event(self.application_id, "INFO", "Switched to Workday iframe.")
                time.sleep(1)
            except TimeoutException:
                log_event(self.application_id, "INFO", "No Workday iframe detected, or already on main Workday page. Proceeding.")
                # If no iframe, assume we are on the main page or the content is directly embedded.

            # Step 3: Look for email input field and "Create Account" or "Next"
            if not self.user_profile or not self.user_profile.default_email:
                log_event(self.application_id, "ERROR", "User profile email not set. Cannot proceed with Workday login.")
                self._take_screenshot("workday_email_missing_in_profile")
                return False

            try:
                # Common Workday email field
                email_input_xpath = "//input[@data-automation-id='email' or @data-automation-id='username' or @type='email']"
                email_input = self.wait.until(EC.visibility_of_element_located((By.XPATH, email_input_xpath)))
                email_input.send_keys(self.user_profile.default_email)
                log_event(self.application_id, "INFO", f"Entered email: {self.user_profile.default_email}")
                self._take_screenshot("workday_email_entered")

                # Click "Next", "Continue", or "Verify" button
                # These buttons can vary.
                next_button_xpaths = [
                    "//button[@data-automation-id='verifyIdentifier']", # Common for "Next" after email
                    "//button[@data-automation-id='submit']",
                    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next')]",
                    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]"
                ]
                next_button_clicked = False
                for xpath in next_button_xpaths:
                    try:
                        next_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                        next_button.click()
                        log_event(self.application_id, "INFO", f"Clicked 'Next/Continue' button after email using XPath: {xpath}")
                        next_button_clicked = True
                        time.sleep(3) # Wait for next page (password or create account details)
                        self._take_screenshot("workday_after_email_next")
                        break
                    except (NoSuchElementException, TimeoutException):
                        log_event(self.application_id, "DEBUG", f"Next/Continue button not found with XPath: {xpath}")
                        continue
                
                if not next_button_clicked:
                    log_event(self.application_id, "WARN", "Could not find 'Next/Continue' button after entering email.")
                    self._take_screenshot("workday_next_button_fail")
                    # At this point, we might be on a page that requires immediate password or account creation.
                    # Further logic will be needed here.
                    return False # For now, consider it a point where we need more logic

                # TODO: Add logic to check if it's a password page (existing user)
                # or a create account page (new user).
                # Look for password field: //input[@data-automation-id='password']
                # Look for "Create Account" specific fields like first name, last name, new password.
                log_event(self.application_id, "INFO", "Successfully entered email and clicked next. Further login/creation steps needed.")
                return True # Placeholder, more steps needed

            except TimeoutException:
                log_event(self.application_id, "WARN", "Could not find Workday email input field or timed out.")
                self._take_screenshot("workday_email_field_fail")
                # Check for "Create Account" link directly if email field isn't obvious
                try:
                    create_account_link_xpath = "//a[@data-automation-id='createAccountLink' or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create account')]"
                    create_account_link = self.wait.until(EC.element_to_be_clickable((By.XPATH, create_account_link_xpath)))
                    create_account_link.click()
                    log_event(self.application_id, "INFO", "Clicked 'Create Account' link.")
                    time.sleep(3)
                    self._take_screenshot("workday_create_account_clicked")
                    # Now, we should be on a page to enter details.
                    # TODO: Implement form filling for account creation.
                    log_event(self.application_id, "INFO", "Navigated to create account page. Further steps needed.")
                    return True # Placeholder
                except (NoSuchElementException, TimeoutException):
                    log_event(self.application_id, "ERROR", "Failed to find email input and also failed to find 'Create Account' link.")
                    self._take_screenshot("workday_login_create_options_fail")
                    return False
            except Exception as e:
                log_event(self.application_id, "ERROR", f"An error occurred during Workday login attempt: {e}")
                self._take_screenshot("workday_login_generic_error")
                return False
            finally:
                # Switch back to default content if we were in an iframe
                try:
                    self.driver.switch_to.default_content()
                    log_event(self.application_id, "INFO", "Switched back to default content from iframe (if applicable).")
                except Exception as e_iframe_switch:
                    log_event(self.application_id, "DEBUG", f"Error switching back from iframe (or was not in one): {e_iframe_switch}")


        else: # Other platforms
            log_event(self.application_id, "WARN", f"Login logic not implemented for platform: {self.platform}")
            return False # Explicitly return False if not Workday and not implemented

        # If we reached here for Workday and didn't return False, it implies partial success or next steps.
        # For now, the function will return based on the specific paths taken above.

    def _fill_forms(self):
        """Fills application forms based on user profile (Placeholder)."""
        log_event(self.application_id, "INFO", "Filling application forms (Placeholder)...")
        # Requires platform-specific logic
        # Use self.user_profile data (parsed resume, etc.)
        # Find form fields (e.g., by label, name, id, data-automation-id for Workday)
        # Handle different field types (text, dropdown, radio, checkbox)
        # Example for Workday:
        # self.driver.find_element(By.XPATH, "//input[@data-automation-id=\'firstName\']").send_keys(self.user_profile.get("first_name"))
        return True

    def _handle_standard_questions(self):
        """Answers standard questions using pre-set answers (Placeholder)."""
        log_event(self.application_id, "INFO", "Handling standard questions (Placeholder)...")
        # Requires platform-specific logic
        # 1. Find question elements on the page
        # 2. Extract question text
        # 3. Match question text (exact or fuzzy) against self.standard_answers
        # 4. If match found, input the answer
        # 5. If no match found, log PENDING/WARN and stop, notifying user
        return True

    def _upload_documents(self):
        """Uploads resume and potentially cover letter (Placeholder)."""
        log_event(self.application_id, "INFO", "Uploading documents (Placeholder)...")
        # Requires platform-specific logic
        # Find file input elements
        # Use self.user_profile.resume_path
        # Generate cover letter if needed (using src.cover_letter) and save temporarily
        # Upload files using .send_keys() on the file input element
        if not self.user_profile or not self.user_profile.resume_path or not os.path.exists(self.user_profile.resume_path):
             log_event(self.application_id, "WARN", "Resume path not found or invalid in profile. Skipping upload.")
             return False # Or True depending on whether it's critical

        log_event(self.application_id, "INFO", f"Attempting to upload resume: {self.user_profile.resume_path}")
        # Example:
        # try:
        #    resume_input = self.driver.find_element(By.XPATH, "//input[@type='file' and contains(@aria-label, 'resume')]")
        #    resume_input.send_keys(self.user_profile.resume_path)
        #    log_event(self.application_id, "SUCCESS", "Resume uploaded.")
        # except Exception as e:
        #    log_event(self.application_id, "ERROR", f"Failed to upload resume: {e}")
        #    return False
        return True

    def run_automation(self):
        """Main method to run the full automation process."""
        if not self._init_driver():
            return # Stop if driver fails

        try:
            if not self._navigate_to_job():
                return

            # --- Core Application Flow ---
            # These steps are placeholders and need platform-specific implementation
            if not self._handle_login(): return
            if not self._fill_forms(): return
            if not self._handle_standard_questions(): return # Check return value - stop if questions need user input
            if not self._upload_documents(): return # Check return value

            # --- Final Review Stage ---
            log_event(self.application_id, "INFO", "Reached final review stage (Placeholder). Taking screenshot.")
            screenshot_path = self._take_screenshot("final_review")

            # Update Application status to 'pending_review'
            log_event(self.application_id, "PENDING", "Application ready for manual review and submission.", screenshot_path=screenshot_path)
            # Update DB record (requires db session or other mechanism)
            # Example: app_record = Application.query.get(self.application_id)
            # app_record.status = "pending_review"
            # app_record.review_screenshot_path = screenshot_path
            # db.session.commit()

        except Exception as e:
            log_event(self.application_id, "ERROR", f"An unexpected error occurred during automation: {e}")
            self._take_screenshot("unexpected_error")
        finally:
            if self.driver:
                log_event(self.application_id, "INFO", "Closing WebDriver.")
                self.driver.quit()

# The run_application_task function has been moved to src/main.py as a Celery task.

