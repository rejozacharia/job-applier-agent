# Job Application Agent

## Overview

The Job Application Agent is a project designed to automate or significantly assist with the process of applying for jobs online. It features a web-based user interface for managing profiles, configurations, and tracking application progress. Currently, the agent primarily focuses on automating applications through Workday-based portals, with ongoing exploration into more advanced AI-driven automation capabilities for broader platform support and enhanced efficiency.

## Current Features

### User Profile Management
-   Upload resumes in PDF or DOCX format.
-   Store LinkedIn profile and personal website URLs.
-   Set a default email address for applications.

### Configuration
-   Manage a list of standard questions and their corresponding answers to expedite form filling.

### Application Submission
-   Submit single job application URLs.
-   Submit multiple job application URLs in a batch.
-   Applications are queued and processed asynchronously in the background.

### Background Task Management
-   Utilizes Python's `multiprocessing` module for robust background task execution.
-   User-controlled start and stop functionality for the task manager via the web UI.
-   Real-time status display for the task manager and individual worker processes.

### Core Automation (Workday)
-   Implemented using Selenium, primarily within [`src/automation.py`](src/automation.py:0).
-   **Platform Detection:** Basic capability to identify the target platform (currently focused on Workday).
-   **Navigation:** Opens and navigates to the provided job application URL.
-   **Login/Account Creation:** Attempts to log in or create an account on Workday, with enhanced handling for common scenarios.
-   **Form Filling:**
    -   Personal Information (name, contact details).
    -   Address (including handling for type-ahead/dropdown fields for State, Zip Code, and Country).
    -   Work Experience (supports multiple entries).
    -   Education (supports multiple entries).
-   **Standard Question Handling:** Matches questions found on application forms against the user's pre-set answers. If an unknown question is encountered, the process for that application may pause or stop, awaiting user input or a pre-defined strategy.
-   **Document Upload:** Uploads the user's resume and, if configured, a cover letter.

### Data Handling
-   **Resume Parsing:** Extracts text content from uploaded PDF and DOCX resumes using [`src/resume_parser.py`](src/resume_parser.py:0).
-   **Web Scraping:** Basic capabilities for scraping text from websites, including job descriptions, using [`src/web_scraper.py`](src/web_scraper.py:0).
-   **Profile Consolidation:** Rudimentary merging of user data from various sources (e.g., resume, manual input) managed by [`src/profile_consolidator.py`](src/profile_consolidator.py:0).
-   **Conflict Resolution Interface:** A UI to review and select primary data points (e.g., preferred email address) when conflicts arise from different data sources.

### Cover Letter Generation
-   Template-based cover letter generation using dynamic data from the user's profile, handled by [`src/cover_letter.py`](src/cover_letter.py:0).
-   Includes placeholders for future integration with Generative AI for more sophisticated cover letter creation.

### GenAI Foundation
-   **GenAI Handler Module:** A foundational module ([`src/genai_handler.py`](src/genai_handler.py:0)) designed with placeholders to integrate various Generative AI providers.
-   **GenAI Configuration:** UI and backend components to manage GenAI provider settings, such as API keys and preferred models.

### Logging
-   Comprehensive file-based logging to [`job_agent.log`](job_agent.log:0) for diagnostics and tracking.

### Database
-   Uses SQLite ([`src/job_agent.db`](src/job_agent.db:0)) for storing user profiles, application details, logs, and configurations.

## Project Structure

The project is organized into several key directories:

-   `src/`: Contains the core application logic.
    -   `models/`: Defines database models (e.g., [`src/models/models.py`](src/models/models.py:0)).
    -   `templates/`: HTML templates for the web interface (e.g., [`src/templates/index.html`](src/templates/index.html:0)).
    -   `static/`: Static assets like CSS and JavaScript files (e.g., [`src/static/css/style.css`](src/static/css/style.css:0)).
-   Key files:
    -   [`src/main.py`](src/main.py:0): The main Flask application file, handling routing and core app setup.
    -   [`src/automation.py`](src/automation.py:0): Contains the Selenium-based browser automation logic.
    -   [`src/task_manager.py`](src/task_manager.py:0): Manages the background task processing system.

## Technology Stack

-   **Backend:** Python, Flask, SQLAlchemy
-   **Frontend:** HTML, CSS, JavaScript
-   **Browser Automation:** Selenium
-   **Background Tasks:** `multiprocessing` (Python standard library)
-   **Database:** SQLite
-   **Key Python Libraries:** (as found in [`requirements.txt`](requirements.txt:0))
    -   `PyPDF2` (for PDF parsing)
    -   `python-docx` (for DOCX parsing)
    -   `BeautifulSoup4` (for web scraping)
    -   And others for various functionalities.

## Setup and Installation

1.  **Prerequisites:**
    *   Python 3.x (preferably 3.9 or newer).
    *   A web browser compatible with Selenium (e.g., Chrome, Firefox) and its corresponding WebDriver.

2.  **Clone the Repository (if applicable):**
    ```bash
    git clone <repository-url>
    cd job-application-agent
    ```
    (Assuming you have the project files locally if not cloning)

3.  **Create and Activate a Virtual Environment:**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Initialize the Database:**
    ```bash
    flask --app src/main:app init-db
    ```

## How to Run

1.  **Start the Task Manager:**
    *   Navigate to the "Configuration" page in the web UI.
    *   Click the "Start Task Manager" button.

2.  **Start the Flask Web Server:**
    ```bash
    flask --app src/main:app run --debug --port 5001
    ```

3.  **Access the UI:**
    *   Open your web browser and go to: `http://127.0.0.1:5001/`

## Current Development Status

-   **Phase 1:** Completed. This included core profile management, single application submission, basic Workday automation, and the initial background task system.
-   **Phase 2:** In progress. Key achievements include:
    -   Batch URL submission for job applications.
    -   Implementation of the GenAI Handler module structure.
    -   Development of the GenAI Configuration UI and backend.
    -   Significant refactoring and stabilization of the `multiprocessing`-based background task system.

## Future Work / Roadmap Highlights

-   **Complete GenAI Integration:**
    -   Enhance cover letter generation using GenAI.
    -   Develop GenAI-assisted form filling to handle a wider variety of questions and improve accuracy.
-   **Advanced AI-Driven Agentic Automation:**
    -   Research and implement more resilient and platform-agnostic web interaction capabilities. This includes exploring frameworks like OpenManus or similar technologies to create agents that can adapt to different website structures with less explicit programming.
-   **Support for Other Applicant Tracking Systems (ATS):**
    -   Expand automation capabilities beyond Workday to include other popular ATS platforms (e.g., Taleo, Greenhouse, Lever).
-   **UI/UX Enhancements:**
    -   Continuously improve the user interface and user experience based on feedback and evolving features.
-   **Enhanced Error Handling and Recovery:**
    -   Improve the robustness of the automation scripts to better handle unexpected website changes or errors.
-   **More Sophisticated Profile Management:**
    -   Allow for multiple resume versions and more granular control over profile data.