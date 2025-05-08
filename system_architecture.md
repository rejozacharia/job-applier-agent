# Job Application Agent: System Architecture Design

## 1. Overview

This document outlines the proposed system architecture for the Job Application Agent. The agent aims to automate the process of applying for jobs online, focusing primarily on Workday-based application portals while providing a framework for potential expansion to other platforms. The system will feature a web-based user interface for managing user profiles, initiating applications, and tracking progress.

## 2. Goals

*   Automate filling of online job applications using user-provided information (resume, LinkedIn, website).
*   Generate tailored cover letters based on job descriptions and user profiles.
*   Handle common application questions using pre-set user answers.
*   Prioritize robust handling of Workday application forms.
*   Provide clear logging and status updates to the user.
*   Allow user intervention for conflict resolution, unknown questions, and final submission.
*   Deliver the final product as source code.

## 3. Architecture Components

The system will be composed of three main layers: Frontend, Backend, and Database.

### 3.1. Frontend (Web Interface)

*   **Technology:** HTML, CSS, JavaScript. Potentially using Flask's Jinja2 templating for integration with the backend.
*   **Purpose:** Provide a user-friendly interface for interacting with the agent.
*   **Components:**
    *   **Dashboard:** Main entry point. Allows users to input job application URLs and view the status of ongoing and completed applications.
    *   **Profile Management:** Section for users to upload their resume (PDF/DOCX), provide URLs for their LinkedIn profile and personal website, and store default login credentials (username/email, password strategy).
    *   **Configuration Panel:** Interface to define answers to standard questions (e.g., visa status, sponsorship needs). Users can add custom question-answer pairs.
    *   **Application Log Viewer:** Displays detailed logs for each application attempt, including status (success, failure, pending review), detected platform, cover letter used, errors encountered, and any credentials created.
    *   **Conflict Resolution Interface:** Alerts users if conflicting information is detected between the resume, LinkedIn, and website. Provides a way for the user to review and confirm the correct information.
    *   **Notification Area:** Displays alerts for required user actions (e.g., resolve conflicts, answer unknown questions, review application before submission).

### 3.2. Backend (Application Logic)

*   **Technology:** Python 3, using the Flask web framework.
*   **Purpose:** Handle application logic, data processing, automation orchestration, and communication with the frontend and database.
*   **Components:**
    *   **API Server (Flask):** Exposes RESTful endpoints for the frontend to interact with (e.g., `POST /apply`, `GET /profile`, `POST /profile`, `GET /logs`, `POST /resolve_conflict`).
    *   **Resume Parser:** Uses libraries like `python-docx`, `pypdf2`, and potentially `pyresparser` or NLP libraries (like SpaCy) to extract structured data (contact info, experience, education, skills) from uploaded resumes.
    *   **Web Scraper/Parser:** Fetches content from the user's public LinkedIn profile URL and personal website URL using libraries like `requests` and `BeautifulSoup`. Extracts relevant information.
    *   **Information Consolidator & Conflict Detector:** Merges parsed information from resume, LinkedIn, and website into a unified user profile. Identifies discrepancies and flags them for user resolution via the frontend.
    *   **Cover Letter Generator:** Takes job description text (scraped from the application URL) and the consolidated user profile as input. Generates a tailored cover letter. This could initially use templates and keyword matching, potentially integrating with an LLM later. Includes a user setting for automatic attachment.
    *   **Automation Engine Orchestrator:** Manages the lifecycle of a job application task. It receives the job URL, coordinates scraping, cover letter generation, profile data retrieval, and initiates the browser automation module.
    *   **Browser Automation Module:** Uses Selenium or Playwright for browser interaction.
        *   Navigates to the job application URL.
        *   Detects the Application Tracking System (ATS) platform (Workday, Greenhouse, Lever, etc.) using page structure analysis or known URL patterns. Logs the detected platform. Focuses implementation on Workday selectors and flow.
        *   Handles login: Attempts login with default credentials. If password fails, generates a secure random password, uses it to create an account or reset password, and logs the new credentials. If username/email fails (e.g., account already exists with different credentials), it alerts the user.
        *   Fills application forms using data from the consolidated user profile and pre-set standard answers.
        *   Handles standard questions: Matches questions against the user's pre-defined list (allowing for fuzzy matching). If a question is unknown, it pauses the automation and alerts the user via the frontend.
        *   Uploads the resume file.
        *   Attaches the generated cover letter if the automatic attachment option is enabled.
        *   Navigates the application flow to the final review page.
        *   **Crucially, it stops before final submission.** It takes a screenshot of the review page, saves the state/URL, and notifies the user that the application is ready for their manual review and submission.
        *   Handles errors (e.g., CAPTCHAs, unexpected page structure, element not found) by logging the error details (with screenshot if possible), stopping the process for that application, and notifying the user.
    *   **Database Interface:** Module abstracting database operations (CRUD for profiles, logs, configurations).
    *   **Logging Module:** Records detailed information about each step of the process, including timestamps, actions taken, data used, errors, platform detected, credentials used/created, etc., into the database.

### 3.3. Database

*   **Technology:** SQLite (initially, for simplicity and ease of deployment with source code).
*   **Purpose:** Persist user data, application logs, and configuration.
*   **Schema (Conceptual):**
    *   `Users`: Basic user information (if multi-user support is ever needed, otherwise implicit single user).
    *   `Profiles`: Stores path to resume file, LinkedIn URL, website URL, default username/email.
    *   `Credentials`: Stores generated passwords associated with specific job sites/logins.
    *   `StandardAnswers`: Stores user-defined answers to common questions (question text, answer text).
    *   `Applications`: Tracks each application attempt (job URL, job title, status [pending_review, failed, submitted], detected_platform, timestamp_started, timestamp_ended, associated_log_id).
    *   `Logs`: Detailed event log (timestamp, application_id, event_type [info, error, warning], message, screenshot_path [optional]).

## 4. Workflow Summary

1.  **Initialization:** User configures their profile (resume, URLs, credentials) and standard answers via the web UI.
2.  **Application Start:** User submits a job URL via the web UI.
3.  **Backend Processing:**
    *   Flask API receives the request.
    *   Orchestrator fetches job description, generates cover letter (optional auto-attach).
    *   Retrieves user profile data, checking for conflicts (prompts user if needed).
    *   Initiates Browser Automation Module.
4.  **Browser Automation:**
    *   Navigates, logs in (handles credential issues), detects platform.
    *   Fills forms, uploads documents, handles known questions (asks user for unknowns).
    *   Reaches final review page.
5.  **User Review:**
    *   Automation stops, saves state/screenshot, logs status as 'pending_review'.
    *   Backend notifies frontend; UI updates to show application ready for review.
6.  **Manual Submission:** User reviews the application in the browser (potentially guided by the agent or using the saved URL) and submits it manually.
7.  **(Optional) Confirmation:** User marks the application as submitted in the UI, updating its status in the database.

## 5. Technology Stack Summary

*   **Backend:** Python 3, Flask
*   **Frontend:** HTML, CSS, JavaScript (with Jinja2 templating)
*   **Browser Automation:** Selenium or Playwright (Python bindings)
*   **Data Parsing:** python-docx, pypdf2, BeautifulSoup4, (potentially SpaCy, pyresparser)
*   **Database:** SQLite

## 6. Next Steps

*   Confirm this architecture with the user.
*   Begin implementation, starting with backend setup (Flask app, database models), followed by frontend structure, profile management, and then the core automation logic.
