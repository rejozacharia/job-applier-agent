# src/main.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # DON'T CHANGE THIS !!!

import datetime
from dotenv import load_dotenv # Import dotenv
load_dotenv() # Load environment variables from .env file

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
# --- App Initialization ---
app = Flask(__name__,
            template_folder="templates", # Use templates from src/templates/
            static_folder="static", # Use static files from src/static
            static_url_path="/static") # URL path for static files

app.config["SECRET_KEY"] = os.urandom(24) # Needed for flashing messages
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.abspath(os.path.dirname(__file__)), "uploads")
app.config["ALLOWED_EXTENSIONS"] = {"pdf", "docx"}

# Create upload folder if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
# --- Database Configuration (SQLite) ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "job_agent.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# --- Database Models (Import after db is initialized) ---
from src.models.models import Profile, StandardAnswer, Application, Log, GenAIConfig

# --- Utility Functions (Import after db and models) ---
from src.utils import log_event, logger # Import the configured logger
# Import cover letter generator (will be used later)
# from src.cover_letter import generate_cover_letter
from src.resume_parser import parse_resume
from src.web_scraper import scrape_linkedin_profile, scrape_website_text
from src.profile_consolidator import consolidate_profile_data
from src.task_manager import start_task_processing_system, stop_task_processing_system
import atexit

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
    return render_template("index.html", applications=applications)

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
    return render_template("profile.html", profile_data=profile_data, current_resume=current_resume)

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
    """Configuration page for standard questions and GenAI settings."""
    try:
        standard_answers = StandardAnswer.query.all()
        genai_configs = GenAIConfig.query.order_by(GenAIConfig.provider_name, GenAIConfig.purpose).all()
        # Placeholder for other config settings
        config_settings = {"auto_attach_cover_letter": True} # Example, can be expanded
    except Exception as e:
        flash(f"Error fetching configuration: {e}", "danger")
        standard_answers = []
        genai_configs = []
        config_settings = {"auto_attach_cover_letter": True}
    return render_template("config.html",
                           standard_answers=standard_answers,
                           genai_configs=genai_configs,
                           config=config_settings)

@app.route("/config", methods=["POST"])
def update_config():
    """Handle configuration form submission for standard answers and GenAI settings."""
    try:
        if "submit_genai_config" in request.form:
            # Handling GenAI Configuration
            config_id = request.form.get("genai_config_id") # For future editing
            provider_name = request.form.get("genai_provider_name")
            purpose = request.form.get("genai_purpose")
            # API key is no longer submitted via form, it's read from .env
            model_name = request.form.get("genai_model_name")
            base_url = request.form.get("genai_base_url")
            is_enabled = request.form.get("genai_is_enabled") == "true"

            if not provider_name or not purpose:
                flash("Provider Name and Purpose are required for GenAI configuration.", "warning")
                return redirect(url_for("config"))

            # Simple check for existing config to prevent duplicates (provider + purpose)
            # More robust update logic would be needed for editing
            existing_config = GenAIConfig.query.filter_by(provider_name=provider_name, purpose=purpose).first()
            if existing_config and not config_id: # If adding new and it already exists
                flash(f"A GenAI configuration for {provider_name} with purpose '{purpose}' already exists. Edit not yet implemented.", "warning")
                return redirect(url_for("config"))

            # For now, only adding new. Edit would require loading by config_id.
            new_genai_config = GenAIConfig(
                provider_name=provider_name,
                # api_key is no longer stored in the DB model
                model_name=model_name if model_name else None,
                base_url=base_url if base_url else None,
                is_enabled=is_enabled,
                purpose=purpose
            )
            db.session.add(new_genai_config)
            db.session.commit()
            flash("GenAI configuration saved successfully.", "success")

        elif "delete_genai_config_id" in request.form:
            config_id_to_delete = request.form.get("delete_genai_config_id")
            config_to_delete = GenAIConfig.query.get(config_id_to_delete)
            if config_to_delete:
                db.session.delete(config_to_delete)
                db.session.commit()
                flash("GenAI configuration deleted successfully.", "success")
            else:
                flash("GenAI configuration not found for deletion.", "warning")

        else:
            # Handling Standard Answers Configuration
            StandardAnswer.query.delete() # Clear existing answers for simplicity
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
            db.session.commit()
            flash("Standard Answers configuration saved successfully.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error saving configuration: {e}", "danger")
        logger.error(f"Error in update_config: {e}", exc_info=True)

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
    return render_template("logs.html", logs=log_entries)

@app.route("/apply", methods=["POST"])
def apply():
    """Endpoint to start new job application processes, potentially in batch."""
    job_urls_batch_raw = request.form.get("job_urls_batch")
    if not job_urls_batch_raw:
        flash("Job URL(s) are required.", "danger")
        return redirect(url_for("index"))

    urls_input = job_urls_batch_raw.strip().splitlines()
    processed_count = 0
    skipped_count = 0
    skipped_urls = []

    for job_url_raw in urls_input:
        job_url = job_url_raw.strip()
        if not job_url: # Skip empty lines
            skipped_count += 1
            skipped_urls.append("(empty line)")
            continue

        # Basic URL validation (optional, can be enhanced)
        if not (job_url.startswith("http://") or job_url.startswith("https://")):
            logger.warning(f"Skipping invalid URL (no http/https): {job_url}")
            skipped_count += 1
            skipped_urls.append(job_url)
            continue

        try:
            # Create a new application record
            new_app = Application(
                job_url=job_url,
                status="queued", # Directly to queued
                timestamp_started=datetime.datetime.utcnow(),
                priority=10, # Default priority
                last_log_message="[INFO] Application created via batch submission and queued for processing."
            )
            db.session.add(new_app)
            db.session.commit() # Commit to get the new_app.id

            # Log the start event
            log_event(new_app.id, "INFO", f"Batch application process initiated for URL: {job_url}")
            processed_count += 1
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating application record for URL {job_url}: {e}", exc_info=True)
            skipped_count += 1
            skipped_urls.append(f"{job_url} (error: {e})")

    if processed_count > 0:
        flash(f"Successfully queued {processed_count} application(s).", "success")
    if skipped_count > 0:
        flash(f"Skipped {skipped_count} invalid or problematic URL(s): {', '.join(skipped_urls)}", "warning")
    if processed_count == 0 and skipped_count == 0 : # Should not happen if textarea is required
        flash("No URLs were provided or processed.", "info")

    return redirect(url_for("index"))

# --- Task Manager Control Endpoints ---
@app.route("/task-manager/start", methods=["POST"])
def task_manager_start():
    """Endpoint to manually start the task processing system."""
    # Ensure this is only run in the main Werkzeug process, not the reloader's child
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        try:
            logger.info("Attempting to start task processing system via API.")
            # Pass the current app instance to the task manager start function
            # This is crucial for the task manager to access app.config, especially DB_URI
            start_task_processing_system(current_app._get_current_object())
            flash("Task processing system initiated.", "success")
            logger.info("Task processing system start initiated successfully via API.")
        except Exception as e:
            logger.error(f"Error starting task processing system via API: {e}", exc_info=True)
            flash(f"Error starting task system: {e}", "danger")
    else:
        message = "Task manager start request ignored in Werkzeug reloader process or debug non-main process."
        logger.info(message)
        flash(message, "info")
    return redirect(url_for("config")) # Or a dedicated status page

@app.route("/task-manager/stop", methods=["POST"])
def task_manager_stop():
    """Endpoint to manually stop the task processing system."""
    try:
        logger.info("Attempting to stop task processing system via API.")
        stop_task_processing_system()
        flash("Task processing system stop initiated.", "success")
        logger.info("Task processing system stop initiated successfully via API.")
    except Exception as e:
        logger.error(f"Error stopping task processing system via API: {e}", exc_info=True)
        flash(f"Error stopping task system: {e}", "danger")
    return redirect(url_for("config")) # Or a dedicated status page

@app.route("/task-manager/status", methods=["GET"])
def task_manager_status():
    """Endpoint to get the status of the task manager and workers."""
    # Placeholder implementation.
    # Actual implementation will query status from task_manager module.
    # This will require task_manager to expose status information.
    # For now, check if the global _manager_process exists and is alive as a basic check.
    from src.task_manager import _manager_process as manager_process_global, _worker_pool as worker_pool_global, _stop_event as stop_event_global

    status_data = {
        "manager_status": "unknown",
        "manager_pid": None,
        "worker_count": 0,
        "workers": [] # Later: list of dicts with {pid, status, current_task_id}
    }

    if stop_event_global and manager_process_global: # Indicates it was at least initialized
        if manager_process_global.is_alive():
            status_data["manager_status"] = "running"
            status_data["manager_pid"] = manager_process_global.pid
        elif stop_event_global.is_set():
             status_data["manager_status"] = "stopped"
        else:
            # It was initialized but is not alive and stop event is not set (could be starting or crashed)
            status_data["manager_status"] = "inactive/crashed"
        
        active_workers = []
        for worker in worker_pool_global:
            worker_info = {"pid": worker.pid, "name": worker.name, "is_alive": worker.is_alive()}
            # More detailed status (idle/processing task X) would require IPC or shared status tracking
            active_workers.append(worker_info)
        status_data["workers"] = active_workers
        status_data["worker_count"] = len(active_workers)

    else:
        status_data["manager_status"] = "not_initialized"

    logger.debug(f"Task manager status API called. Current status: {status_data}")
    return jsonify(status_data)

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
    return render_template("conflict_resolution.html",
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

def ensure_db_initialized(flask_app):
    """Checks if DB exists, creates it if not."""
    db_path = flask_app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    if not os.path.exists(db_path):
        with flask_app.app_context():
            # The outer try was causing a syntax error. The inner try/except is sufficient.
            try:
                logger.info(f"Database file not found at {db_path}. Creating database and tables...")
                db.create_all()
                logger.info("Database and tables created successfully.")
            except Exception as e:
                logger.error(f"Error creating database: {e}", exc_info=True)
    else: # This else corresponds to the 'if not os.path.exists(db_path):'
        logger.info(f"Database file found at {db_path}.")

# --- Global flag to ensure task system starts only once ---
# _task_system_initialized = False # Will be managed by new start/stop endpoints

# --- Main Execution ---

# This code runs when 'src.main' is imported (e.g., by 'flask run')
# We check if we are in the main Werkzeug process to avoid running this multiple times
# in development mode with the reloader.
if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    # if not _task_system_initialized: # Logic will move to manual start
    # if not _task_system_initialized: # Logic will move to manual start
    logger.info("Werkzeug main process detected. Task system will NOT start automatically.")
    ensure_db_initialized(app)  # Ensure DB is created if it doesn't exist
    
    # Start the background task processing system - MOVED TO MANUAL CONTROL
    # with app.app_context(): # Needed for start_task_processing_system to access app.config
    #     logger.info("Attempting to start task processing system...")
    #     start_task_processing_system(app)
    #     logger.info("Task processing system start initiated.")
    
    # Register cleanup function for when the app exits - MOVED TO MANUAL CONTROL (or explicit stop)
    # atexit.register(stop_task_processing_system)
    # logger.info("Registered task system shutdown hook.")
    # _task_system_initialized = True
    # else:
    #     logger.info("Werkzeug main process detected, but task system already initialized.") # This state might not be relevant anymore
elif app.debug and not os.environ.get("WERKZEUG_RUN_MAIN"):
    # This is likely the initial process that starts the reloader, or another utility process.
    logger.info("Flask reloader or utility process detected. DB init will occur in the Werkzeug main process. Task system is manually controlled.")
# If not app.debug (i.e., production), this block won't run if WERKZEUG_RUN_MAIN is not set by the prod server.
# Production servers (like Gunicorn) typically import the app once, so the flag helps there too.

if __name__ == "__main__":
    # This block is generally not used when running with 'flask run'.
    # 'flask run' imports the 'app' object and runs it.
    # If you were to run 'python src/main.py' directly (not standard for Flask):
    logger.warning("Running directly with 'python src/main.py' (not recommended for Flask production/standard dev).")
    # Ensure DB is initialized if running this way too, though the above block should cover 'flask run'.
    # if not (os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug):
    #    ensure_db_initialized(app) # Redundant if above works, but safe
    #    with app.app_context():
    #        start_task_processing_system(app)
    #    atexit.register(stop_task_processing_system)
    
    # When running directly, it's better to let Werkzeug handle the reloader and main process detection.
    # The `if os.environ.get("WERKZEUG_RUN_MAIN") == "true":` block above will handle
    # DB initialization and prevent auto-start of task manager in the correct process.
    app.run(debug=True, port=5001, use_reloader=True)
    # The print statement for how to run the app via flask CLI:
    # logger.info("To run the app, use the command: flask --app src/main:app run --debug --port 5001")
