# src/utils.py
import datetime
from src.main import db
from src.models.models import Log, Application

def log_event(application_id, level, message, screenshot_path=None):
    """Logs an event for a specific application run."""
    try:
        log_entry = Log(
            application_id=application_id,
            level=level,
            message=message,
            screenshot_path=screenshot_path,
            timestamp=datetime.datetime.utcnow()
        )
        db.session.add(log_entry)

        # Also update the last log message on the Application record
        application = Application.query.get(application_id)
        if application:
            application.last_log_message = f"[{level}] {message}"
            # Potentially update application status based on log level
            if level == "ERROR" or level == "FAILED":
                application.status = "failed"
                application.timestamp_ended = datetime.datetime.utcnow()
            elif level == "PENDING": # Used for pending review
                 application.status = "pending_review"
            # Add other status updates as needed

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error logging event: {e}")
        # Consider logging this error to a file or system log

# Example usage (will be called from other parts of the app):
# log_event(app_id, "INFO", "Starting application process...")
# log_event(app_id, "ERROR", "Failed to find login button.", screenshot_path="/path/to/error.png")

