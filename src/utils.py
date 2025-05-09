# src/utils.py
import datetime
import logging
import os

# --- Logger Setup ---
# Determine the root directory of the project (c:/GitClone/job_agent_app)
# Assuming utils.py is in src/, so two levels up.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = os.path.join(PROJECT_ROOT, "job_agent.log")

# Create logger
logger = logging.getLogger("job_agent_app")
logger.setLevel(logging.DEBUG) # Set to DEBUG to capture all levels of logs

# Create file handler
file_handler = logging.FileHandler(LOG_FILE_PATH)
file_handler.setLevel(logging.DEBUG)

# Create console handler (optional, for also seeing logs in console during dev)
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging.INFO)

# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(processName)s(%(process)d) - %(threadName)s(%(thread)d) - %(message)s')
file_handler.setFormatter(formatter)
# console_handler.setFormatter(formatter)

# Add the handlers to the logger
if not logger.handlers: # Avoid adding multiple handlers if this module is reloaded
    logger.addHandler(file_handler)
    # logger.addHandler(console_handler)

logger.info(f"File logger initialized. Logging to: {LOG_FILE_PATH}")

# Import db for fallback, but prefer passed session
# These imports are delayed to avoid circular dependencies if logger is imported early
_global_db_session_for_main_app_context = None
_Log_model = None
_Application_model = None

def _initialize_db_imports_for_log_event():
    global _global_db_session_for_main_app_context, _Log_model, _Application_model
    if _global_db_session_for_main_app_context is None:
        from src.main import db as global_db_session_for_main_app_context_imported
        from src.models.models import Log as Log_model_imported, Application as Application_model_imported
        _global_db_session_for_main_app_context = global_db_session_for_main_app_context_imported
        _Log_model = Log_model_imported
        _Application_model = Application_model_imported
        logger.debug("DB imports for log_event initialized.")


def log_event(application_id, level, message, screenshot_path=None, session=None):
    """
    Logs an event to both the database and the file logger.
    Uses the provided session if available for DB logging, otherwise falls back to the global db.session.
    """
    _initialize_db_imports_for_log_event() # Ensure DB related imports are done

    # File Logging
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING, # Alias for WARN
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
        "PENDING": logging.INFO, # PENDING is custom, map to INFO for file log
    }
    numeric_level = log_level_map.get(level.upper(), logging.INFO) # Default to INFO if level is unknown
    
    # Include application_id in the log message for context
    log_message_for_file = f"[AppID: {application_id}] {message}"
    if screenshot_path:
        log_message_for_file += f" (Screenshot: {screenshot_path})"
    
    logger.log(numeric_level, log_message_for_file)

    # Database Logging
    active_session = session if session else _global_db_session_for_main_app_context.session
    
    try:
        log_entry = _Log_model(
            application_id=application_id,
            level=level.upper(), # Ensure level is uppercase for DB
            message=message,
            screenshot_path=screenshot_path,
            timestamp=datetime.datetime.utcnow()
        )
        active_session.add(log_entry)

        application = active_session.query(_Application_model).get(application_id)
        if application:
            application.last_log_message = f"[{level.upper()}] {message}"
            # Status updates are handled by worker/automator logic

        active_session.commit()
    except Exception as e:
        active_session.rollback()
        # Log this error to the file logger
        logger.error(f"DB logging failed for AppID {application_id}, Level {level}: {e}. Original message: {message}", exc_info=True)
        # Fallback print if logger itself has issues, though unlikely
        # print(f"CRITICAL: Error logging event to DB (app_id: {application_id}, level: {level}): {e}")


# Example usage (will be called from other parts of the app):
# log_event(app_id, "INFO", "Starting application process...")
# log_event(app_id, "ERROR", "Failed to find login button.", screenshot_path="/path/to/error.png")

