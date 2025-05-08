# Project Roadmap: Job Application Agent

This document outlines the development plan for the Job Application Agent, including core functionality, GenAI integration, and future refinements.

## Phase 1: Implement Core Missing Functionality (Non-GenAI)

This phase focuses on building out the foundational pieces described in the architecture that are currently missing.

1.  **Implement Resume Parser:** Create `src/resume_parser.py` to extract structured data from resumes.
2.  **Implement Web Scraper:** Create `src/web_scraper.py` to fetch data from LinkedIn/personal websites.
3.  **Implement Information Consolidator & Conflict Detector:** Develop logic in a new module (e.g., `src/profile_consolidator.py`) to merge parsed data and identify conflicts.
4.  **Implement Conflict Resolution Interface:** Build the UI (e.g., a new template `templates/conflict_resolution.html`) and backend logic in `src/main.py` for users to resolve data conflicts.
5.  **Set up Background Task Execution:** Integrate a task queue (e.g., Celery with Redis or RabbitMQ) for asynchronous job application processing. This will involve:
    *   Adding Celery to `requirements.txt`.
    *   Configuring Celery in `src/main.py` or a new `src/celery_app.py`.
    *   Modifying the `/apply` endpoint to dispatch tasks to Celery workers.
    *   Ensuring `src/automation.py`'s `run_application_task` is Celery-compatible.
6.  **Develop Core Automation Logic for Workday:** Flesh out the placeholder methods in `src/automation.py` with robust Selenium interactions for Workday sites (login, form filling, question handling, document upload, navigating to review page). This will be the most intensive part of this phase.
7.  **Integrate User Profile with Cover Letter Generator:** Update `src/cover_letter.py` to accept and use dynamic user profile data (from the consolidated profile) instead of the `DEFAULT_USER_PROFILE`.
8.  **Implement Job Description Scraping:** Add functionality, likely within `src/automation.py` or a new utility in `src/web_scraper.py`, to extract job descriptions from application URLs when an application process starts.

## Phase 2: GenAI Integration & Batch Submission

1.  **Implement Batch Application Submission:**
    *   Modify the frontend (e.g., `templates/index.html`) to allow users to input multiple job URLs (e.g., in a textarea).
    *   Update the backend `/apply` endpoint in `src/main.py` to parse these multiple URLs. For each URL, it will create an `Application` record and dispatch a separate background task via Celery.
2.  **Create GenAI Handler Module:**
    *   Develop `src/genai_handler.py`.
    *   This module will contain classes/functions to abstract interactions with Google Gemini, Ollama (via its API), and OpenRouter. It will handle API key management, request formatting, and response parsing for each service.
3.  **Implement GenAI Configuration:**
    *   Add UI elements to `templates/config.html` and corresponding backend logic in `src/main.py` for users to:
        *   Select their preferred GenAI provider(s).
        *   Enter API keys securely.
        *   Specify model names (if applicable).
        *   Provide base URLs for local instances like Ollama.
    *   Store these settings, potentially in a new `GenAIConfig` table in the database (`src/models/models.py`) or a secure configuration file.
4.  **Integrate GenAI into Cover Letter Generation:**
    *   Modify `src/cover_letter.py`.
    *   Add logic to check if GenAI is configured and enabled for cover letters.
    *   If so, call the `src/genai_handler.py` with the (scraped) job description and the consolidated user profile to generate cover letter content.
    *   Provide an option for the user to review/edit the GenAI-generated letter or fall back to the template-based one.
5.  **Integrate GenAI into Form Filling (Experimental/Fallback):**
    *   Enhance the form-filling logic in `src/automation.py`.
    *   When the automation encounters an unknown form field or a question not in `StandardAnswers`, it can (if GenAI is enabled for this purpose):
        *   Call the `src/genai_handler.py` with the field label, surrounding context from the page, and user profile to get a suggested answer.
        *   Implement a strategy: either log the suggestion for the user, attempt to fill it and flag for review, or pause and ask the user. This needs careful consideration due to the risk of incorrect information being submitted.

## Phase 3: Expansion and Refinement

1.  **Support for Other ATS Platforms:** Extend automation logic in `src/automation.py` for other platforms like Greenhouse and Lever, based on the patterns established for Workday.
2.  **Frontend Polish & UX Improvements:**
    *   Enhance the dashboard for better visualization of application statuses.
    *   Improve the log viewer with filtering and search.
    *   Implement a more robust notification system as per `system_architecture.md`.
3.  **Advanced Error Handling & Resiliency:**
    *   Improve detection and handling of CAPTCHAs (e.g., notify user, integrate with solving services if ethically appropriate and configured).
    *   Make automation scripts more resilient to minor UI changes on job portals.
4.  **Testing and Documentation:**
    *   Write unit and integration tests for new modules.
    *   Update `system_architecture.md` and add more detailed developer/user documentation.

## Gantt Chart Visualization

```mermaid
gantt
    dateFormat  YYYY-MM-DD
    title Job Application Agent Development Plan
    excludes    weekends

    section Phase 1: Core Functionality
    Resume Parser             :p1_1, 2025-05-09, 7d
    Web Scraper (LinkedIn/Site) :p1_2, after p1_1, 7d
    Info Consolidator/Conflict:p1_3, after p1_2, 5d
    Conflict Resolution UI/UX :p1_4, after p1_3, 5d
    Background Tasks (Celery) :p1_5, 2025-05-09, 10d
    Workday Automation Core   :p1_6, after p1_5, 21d
    Profile in Cover Letter   :p1_7, after p1_3, 3d
    Job Description Scraper   :p1_8, after p1_2, 4d

    section Phase 2: GenAI & Batch Submission
    Batch Application Submit  :p2_1, after p1_6, 7d
    GenAI Handler Module      :p2_2, after p1_8, 10d
    GenAI Configuration UI/DB :p2_3, after p2_2, 7d
    GenAI Cover Letter Integ. :p2_4, after p2_3, 7d
    GenAI Form Filling Integ. :p2_5, after p2_4, 10d

    section Phase 3: Expansion & Refinement
    Other ATS Support         :p3_1, after p2_5, 21d
    Frontend Polish & UX      :p3_2, after p2_1, 14d
    Advanced Error Handling   :p3_3, after p3_1, 10d
    Testing & Documentation   :p3_4, 2025-05-09, 60d