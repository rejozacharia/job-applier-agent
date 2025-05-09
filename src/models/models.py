# src/models/models.py
from src.main import db # Import db instance from main app
import datetime

class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resume_path = db.Column(db.String(255), nullable=True)
    linkedin_url = db.Column(db.String(255), nullable=True)
    website_url = db.Column(db.String(255), nullable=True)
    default_email = db.Column(db.String(120), nullable=True)
    password_strategy = db.Column(db.String(50), default="generate") # e.g., "generate", "ask"
    # Add other profile fields as needed

class StandardAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_url = db.Column(db.String(512), nullable=False)
    job_title = db.Column(db.String(255), nullable=True)
    company_name = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default="pending_start") # e.g., pending_start, processing, pending_review, failed, submitted_manual
    detected_platform = db.Column(db.String(50), nullable=True) # e.g., Workday, Greenhouse, Lever, Unknown
    timestamp_started = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    timestamp_ended = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.Integer, default=10)  # Lower numbers are higher priority
    source_site = db.Column(db.String(255), nullable=True)
    search_criteria_used = db.Column(db.Text, nullable=True)
    crawl_timestamp = db.Column(db.DateTime, nullable=True)
    last_attempted_at = db.Column(db.DateTime, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=2) # Default max retries
    error_details = db.Column(db.Text, nullable=True) # For storing detailed error messages/stack traces
    # Foreign key to link logs might be complex if logs are numerous.
    # Storing key info here might be simpler for dashboard view.
    last_log_message = db.Column(db.Text, nullable=True)
    review_screenshot_path = db.Column(db.String(255), nullable=True)
    created_credentials_site = db.Column(db.String(255), nullable=True) # Store site if new creds were made
    created_credentials_password = db.Column(db.String(255), nullable=True) # Store password if generated

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    level = db.Column(db.String(10), nullable=False) # INFO, WARN, ERROR, SUCCESS, PENDING
    message = db.Column(db.Text, nullable=False)
    screenshot_path = db.Column(db.String(255), nullable=True)

    application = db.relationship("Application", backref=db.backref("logs", lazy=True, cascade="all, delete-orphan"))


class GenAIConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_name = db.Column(db.String(50), nullable=False)  # e.g., "gemini", "ollama", "openrouter"
    # api_key is now stored in .env file
    model_name = db.Column(db.String(100), nullable=True)
    base_url = db.Column(db.String(255), nullable=True)  # Primarily for Ollama
    is_enabled = db.Column(db.Boolean, default=False)
    purpose = db.Column(db.String(100), nullable=False)  # e.g., "cover_letter", "form_fill_assist"

    def __repr__(self):
        return f"&lt;GenAIConfig {self.provider_name} ({self.purpose})&gt;"
