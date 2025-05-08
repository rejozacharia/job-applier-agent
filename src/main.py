# src/main.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # DON'T CHANGE THIS !!!

import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from celery import Celery

# --- App Initialization ---
app = Flask(__name__,
            template_folder=".", # Use templates from src/
            static_folder="static", # Use static files from src/static
            static_url_path="/static") # URL path for static files

app.config["SECRET_KEY"] = os.urandom(24) # Needed for flashing messages
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.abspath(os.path.dirname(__file__)), "uploads")
app.config["ALLOWED_EXTENSIONS"] = {"pdf", "docx"}

# Create upload folder if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
# --- Celery Configuration ---
# Ensure Redis is running: `redis-server`
# To run Celery worker: `celery -A src.main.celery_app worker -l info` (from project root)
app.config["CELERY_BROKER_URL"] = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
app.config["CELERY_RESULT_BACKEND"] = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# --- Celery Initialization ---
def make_celery(flask_app):
    celery_instance = Celery(
        flask_app.import_name,
        backend=flask_app.config["CELERY_RESULT_BACKEND"],
        broker=flask_app.config["CELERY_BROKER_URL"]
    )
    celery_instance.conf.update(flask_app.config)

    class ContextTask(celery_instance.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

# --- Celery Tasks ---
@celery_app.task(bind=True)
def run_automation_celery_task(self, application_id):
    """
    Celery task to run the job application automation.
    Fetches data and runs the automation for a given application ID.
    """
    # Imports are inside the task to ensure they are loaded in the Celery worker context
    from src.automation import JobAutomator
    # app and db are available via current_app and the ContextTask setup for Celery
    
    # No need for 'with app.app_context():' here due to ContextTask
    application = Application.query.get(application_id)
    profile = Profile.query.first() # Assuming single profile
    answers = StandardAnswer.query.all()
    # config = load_config() # Load other config if needed

    if not application:
        print(f"Error: Celery task - Application ID {application_id} not found.")
        # Optionally, update app status to failed via direct DB access if critical
        return {"status": "error", "message": f"Application ID {application_id} not found."}
    
    if not profile:
        log_event(application_id, "ERROR", "User profile not found. Cannot proceed with automation.")
        # Update app status directly if needed
        application.status = "failed"
        application.last_log_message = "[ERROR] User profile not found. Cannot proceed."
        db.session.commit()
        return {"status": "error", "message": "User profile not found."}

    standard_answers_dict = {qa.question.lower().strip(): qa.answer for qa in answers}
    # TODO: Load actual config settings (e.g., from a DB table or config file)
    config_settings = {"auto_attach_cover_letter": True} # Placeholder

    # Update status to processing
    application.status = "processing"
    application.last_log_message = "[INFO] Automation task started by Celery worker."
    db.session.commit()
    log_event(application_id, "INFO", "Starting browser automation via Celery.")

    automator = JobAutomator(
        application_id=application_id,
        job_url=application.job_url,
        user_profile=profile, 
        standard_answers=standard_answers_dict,
        config=config_settings
    )
    try:
        automator.run_automation()
        # The run_automation method itself should log final status (pending_review, failed)
        # and update the application record in the DB.
        return {"status": "success", "message": f"Automation task completed for app ID {application_id}."}
    except Exception as e:
        # This is a fallback error handler if JobAutomator itself doesn't catch everything
        log_event(application_id, "ERROR", f"Critical error in Celery task run_automation_celery_task: {e}")
        application.status = "failed"
        application.last_log_message = f"[ERROR] Critical error in Celery task: {e}"
        db.session.commit()
        return {"status": "error", "message": f"Critical error during automation: {e}"}
    celery_instance.Task = ContextTask
    return celery_instance

celery_app = make_celery(app)

# --- Database Configuration (SQLite) ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "job_agent.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# --- Database Models (Import after db is initialized) ---
from src.models.models import Profile, StandardAnswer, Application, Log

# --- Utility Functions (Import after db and models) ---
from src.utils import log_event
# Import cover letter generator (will be used later)
# from src.cover_letter import generate_cover_letter
from src.resume_parser import parse_resume
from src.web_scraper import scrape_linkedin_profile, scrape_website_text
from src.profile_consolidator import consolidate_profile_data

# --- Helper Functions ---
def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

# --- Routes ---

@app.route("/")
def index():
    """Dashboard page."""
    try:
        # Query applications sorted by start time descending
        applications = Application.query.order_by(Application.timestamp_started.desc()).limit(20).all()
    except Exception as e:
        flash(f"Error fetching applications: {e}", "danger")
        applications = []
    return render_template("templates/index.html", applications=applications)

@app.route("/profile", methods=["GET"])
def profile():
    """Profile management page."""
    try:
        # Assuming single user profile for now, get the first one or create if none
        profile_data = Profile.query.first()
        if not profile_data:
            profile_data = Profile() # Create an empty one for the template
            # db.session.add(profile_data)
            # db.session.commit() # Don't commit yet, let user save first
        current_resume = os.path.basename(profile_data.resume_path) if profile_data.resume_path else None
    except Exception as e:
        flash(f"Error fetching profile: {e}", "danger")
        profile_data = Profile() # Empty profile on error
        current_resume = None
    return render_template("templates/profile.html", profile_data=profile_data, current_resume=current_resume)

@app.route("/profile", methods=["POST"])
def update_profile():
    """Handle profile form submission."""
    try:
        profile_entry = Profile.query.first()
        if not profile_entry:
            profile_entry = Profile()
            db.session.add(profile_entry)

        profile_entry.linkedin_url = request.form.get("linkedin_url")
        profile_entry.website_url = request.form.get("website_url")
        profile_entry.default_email = request.form.get("default_email")
        profile_entry.password_strategy = request.form.get("password_strategy")

        # Handle file upload
        if "resume_file" in request.files:
            file = request.files["resume_file"]
            if file and file.filename != "" and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(save_path)
                profile_entry.resume_path = save_path
                flash(f"Resume '{filename}' uploaded successfully.", "success")
            elif file.filename != "": # File selected but not allowed type
                 flash(f"Invalid file type for resume. Allowed types: {app.config['ALLOWED_EXTENSIONS']}", "warning")

        db.session.commit()
        flash("Profile updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating profile: {e}", "danger")

    return redirect(url_for("profile"))

@app.route("/config", methods=["GET"])
def config():
    """Configuration page for standard questions."""
    try:
        standard_answers = StandardAnswer.query.all()
        # Placeholder for other config settings
        config_settings = {"auto_attach_cover_letter": True}
    except Exception as e:
        flash(f"Error fetching configuration: {e}", "danger")
        standard_answers = []
        config_settings = {"auto_attach_cover_letter": True}
    return render_template("templates/config.html", standard_answers=standard_answers, config=config_settings)

@app.route("/config", methods=["POST"])
def update_config():
    """Handle configuration form submission for standard answers."""
    try:
        # Clear existing answers for simplicity (could update/delete individually)
        StandardAnswer.query.delete()

        i = 0
        while True:
            question = request.form.get(f"question_{i}")
            answer = request.form.get(f"answer_{i}")
            if question is None or answer is None: # No more questions submitted
                break
            if question.strip() and answer.strip(): # Only save if both have content
                new_qa = StandardAnswer(question=question.strip(), answer=answer.strip())
                db.session.add(new_qa)
            i += 1

        # Handle other config settings later (e.g., auto_attach_cover_letter)

        db.session.commit()
        flash("Configuration saved successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving configuration: {e}", "danger")

    return redirect(url_for("config"))

@app.route("/logs")
def logs():
    """Display application logs."""
    try:
        # Query logs sorted by timestamp descending
        log_entries = Log.query.order_by(Log.timestamp.desc()).limit(100).all()
        # Fetch associated application info efficiently (though model relationship helps)
        # You might want to join Application data here if needed frequently
    except Exception as e:
        flash(f"Error fetching logs: {e}", "danger")
        log_entries = []
    return render_template("templates/logs.html", logs=log_entries)

@app.route("/apply", methods=["POST"])
def start_application():
    """Endpoint to start a new job application process."""
    job_url = request.form.get("job_url")
    if not job_url:
        flash("Job URL is required.", "danger")
        return redirect(url_for("index"))

    try:
        # Create a new application record
        new_app = Application(
            job_url=job_url,
            status="pending_start",
            timestamp_started=datetime.datetime.utcnow()
        )
        db.session.add(new_app)
        db.session.commit() # Commit to get the new_app.id

        # Log the start event
        log_event(new_app.id, "INFO", f"Application process initiated for URL: {job_url}")

        # --- Trigger Background Task via Celery ---
        try:
            run_automation_celery_task.delay(new_app.id)
            log_event(new_app.id, "INFO", f"Automation task for app ID {new_app.id} queued with Celery.")
            # Status will be updated by the Celery task itself (e.g., to 'processing')
            # For immediate feedback, we can set it to 'queued' or similar
            new_app.status = "queued"
            new_app.last_log_message = "[INFO] Automation task queued with Celery."
            db.session.commit()
            flash(f"Application for {job_url} has been queued for processing.", "success")
        except Exception as celery_e:
            log_event(new_app.id, "ERROR", f"Failed to queue Celery task: {celery_e}")
            flash(f"Error queueing application task: {celery_e}", "danger")
            # Rollback status or handle as needed
            new_app.status = "failed_queueing"
            db.session.commit()

        flash(f"Application process started for {job_url}. Check logs for details.", "info")

    except Exception as e:
        db.session.rollback()
        flash(f"Error starting application: {e}", "danger")
        # Log the error if possible (might not have an app_id yet)
        print(f"Error creating application record: {e}")
@app.route("/profile/resolve_conflicts", methods=["GET", "POST"])
def resolve_conflicts():
    """
    Page to display and resolve data conflicts from various profile sources.
    This is a simplified version. In a real scenario, this might be triggered
    when a new resume is uploaded or when starting an application.
    """
    profile_entry = Profile.query.first()
    if not profile_entry:
        flash("Please create a profile first.", "warning")
        return redirect(url_for("profile"))

    # Simulate fetching/parsing data (in a real app, this might be stored or cached)
    resume_data = None
    if profile_entry.resume_path and os.path.exists(profile_entry.resume_path):
        resume_data = parse_resume(profile_entry.resume_path)

    web_profile_data = {}
    # For simplicity, we are not re-scraping live here.
    # In a real app, scraped data might be stored or fetched on demand.
    # web_profile_data["linkedin_text"] = scrape_linkedin_profile(profile_entry.linkedin_url) if profile_entry.linkedin_url else None
    # web_profile_data["website_text"] = scrape_website_text(profile_entry.website_url) if profile_entry.website_url else None
    
    # For now, let's assume web_profile_data is empty or pre-fetched and stored elsewhere
    # to avoid live scraping on every page load of conflict resolution.
    # This part needs more thought on how/when to trigger scraping for consolidation.

    consolidated_data = consolidate_profile_data(resume_data, web_profile_data, profile_entry)

    if request.method == "POST":
        # User has submitted resolved data
        # Update the Profile model with the chosen values
        # Example:
        chosen_email = request.form.get("chosen_email")
        if chosen_email and chosen_email in consolidated_data.get("emails", []):
            profile_entry.default_email = chosen_email
            flash(f"Primary email updated to {chosen_email}.", "info")
        
        # Add logic for other resolvable fields (phone, name, etc.)
        # For fields like skills, experience, education, the resolution might be more complex
        # (e.g., selecting from multiple entries, editing text).

        try:
            db.session.commit()
            flash("Profile conflicts resolved and data updated.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving resolved data: {e}", "danger")
        
        return redirect(url_for("profile")) # Or back to resolve_conflicts if not all resolved

    # For GET request, display the conflicts
    # The template will need to handle the structure of consolidated_data["conflicts"]
    return render_template("templates/conflict_resolution.html",
                           profile_data=profile_entry,
                           consolidated_data=consolidated_data,
                           conflicts=consolidated_data.get("conflicts", []))

    return redirect(url_for("index"))

# --- Database Initialization Command ---
@app.cli.command("init-db")
def init_db_command():
    """Create database tables."""
    with app.app_context():
        db.create_all()
    print("Initialized the database.")

# --- Main Execution ---
if __name__ == "__main__":
    # Note: Use 'flask run' command in terminal, not 'python src/main.py'
    print("To run the app, use the command: flask --app src/main:app run --debug --port 5001")

