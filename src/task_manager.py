# src/task_manager.py
import multiprocessing
import time
import datetime
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure the app's context can be found by child processes
# This is a common way to ensure imports work in subprocesses
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import logger # Import the configured logger

# Late imports to avoid circular dependencies and allow app context in workers
_db = None
_Application = None
_Profile = None
_StandardAnswer = None
_Log = None
_JobAutomator = None
_log_event_util = None
_flask_app = None

def initialize_worker_imports():
    """Initializes imports needed by worker processes."""
    global _db, _Application, _Profile, _StandardAnswer, _Log, _JobAutomator, _log_event_util, _flask_app
    
    # Import Flask app and db instance
    # This assumes 'app' and 'db' are accessible from 'src.main'
    # In a robust setup, you might pass db_uri and create engine/session per process
    from src.main import app as flask_app_instance, db as main_db
    from src.models.models import Application, Profile, StandardAnswer, Log
    from src.automation import JobAutomator
    from src.utils import log_event as log_event_func

    _flask_app = flask_app_instance
    _db = main_db
    _Application = Application
    _Profile = Profile
    _StandardAnswer = StandardAnswer
    _Log = Log
    _JobAutomator = JobAutomator
    _log_event_util = log_event_func

MAX_WORKERS = 4  # Number of worker processes
TASK_QUEUE_MAX_SIZE = MAX_WORKERS * 2 # Max items in the in-memory queue
POLL_INTERVAL = 5  # Seconds to wait before polling the DB for new tasks
DB_URI = None # Will be set when starting the manager

def create_new_db_session(db_uri):
    """Creates a new SQLAlchemy session for a worker process."""
    engine = create_engine(db_uri)
    Session = sessionmaker(bind=engine)
    return Session()

def worker_function(application_id, db_uri_for_worker):
    """
    The function executed by each worker process.
    Processes a single application.
    """
    if _Application is None: # Ensure imports are done if not already (checking one is enough)
        initialize_worker_imports()

    worker_pid = os.getpid()
    worker_name = multiprocessing.current_process().name
    logger.info(f"[{worker_name} PID-{worker_pid}] Picked up application_id: {application_id}. Starting processing.")
    
    session = None # Initialize session to None for the finally block
    try:
        session = create_new_db_session(db_uri_for_worker)
        
        application = session.query(_Application).get(application_id)
        if not application:
            if not application:
                # Log this to a central file or stderr if session is not available or app_id is unknown
                logger.error(f"[Worker-{worker_pid}] Error: Application ID {application_id} not found in DB. Cannot log to application.")
                # Attempt to log this critical issue if log_event_util is available
                if _log_event_util:
                    try:
                        # We don't have an application_id context here in the DB, so log without it or use a placeholder if necessary
                        # For now, just print, as logging to DB without app context is tricky.
                        pass
                    except Exception:
                        pass # Avoid error in error handling
                return
            
            logger.info(f"[{worker_name} PID-{worker_pid}] WorkerFunction START for app_id: {application_id}, current_retry_count: {application.retry_count}, status: {application.status}")
            _log_event_util(application_id, "DEBUG", f"WorkerFunction START. PID: {worker_pid}. Retry: {application.retry_count}. Status: {application.status}", session=session)
            # Re-check status in case it was changed by another process (though manager should prevent this for 'processing')
            if application.status != "processing":
                logger.warning(f"[Worker-{worker_pid}] Application ID {application_id} status is '{application.status}', not 'processing'. Skipping.")
                _log_event_util(application_id, "WARN", f"Worker-{worker_pid} picked up task but status was '{application.status}'. Skipping.", session=session)
                # No commit needed here as we are not changing the application state based on this warning.
                return
        profile = session.query(_Profile).first()
        if not profile:
            error_msg = "User profile not found. Cannot proceed."
            _log_event_util(application_id, "ERROR", error_msg, session=session)
            application.status = "failed_final" # No retry if profile is missing
            application.error_details = error_msg
            application.last_log_message = f"[ERROR] {error_msg}"
            application.timestamp_ended = datetime.datetime.utcnow()
            session.commit()
            return

        answers = session.query(_StandardAnswer).all()
        standard_answers_dict = {qa.question.lower().strip(): qa.answer for qa in answers}
        
        config_settings = {"auto_attach_cover_letter": True} # Placeholder for actual config loading

        automator = _JobAutomator(
            application_id=application.id,
            job_url=application.job_url,
            user_profile=profile,
            standard_answers=standard_answers_dict,
            config=config_settings,
            db_session=session # Pass the dedicated session to JobAutomator
        )

        _log_event_util(application_id, "INFO", f"[{worker_name} PID-{worker_pid}] Initialized. About to call run_automation() for app_id: {application_id}.", session=session)
        logger.info(f"[{worker_name} PID-{worker_pid}] Calling run_automation() for app_id: {application_id}...")
        _log_event_util(application_id, "DEBUG", f"WorkerFunction BEFORE run_automation. PID: {worker_pid}.", session=session)
        
        automation_result = automator.run_automation() # This now returns a dict
        
        _log_event_util(application_id, "DEBUG", f"WorkerFunction AFTER run_automation. PID: {worker_pid}. Result: {automation_result.get('status')}", session=session)
        logger.info(f"[{worker_name} PID-{worker_pid}] run_automation() completed for app_id: {application_id}. Result: {automation_result}")

        # Re-fetch application to ensure we have the latest version before updating
        # This is good practice if JobAutomator made any intermediate commits (e.g. via log_event)
        # though log_event now uses the passed session, so it's part of the same transaction.
        # However, fetching again ensures we're not working with stale data if other parts change.
        application = session.query(_Application).get(application_id) # Get fresh instance
        if not application: # Should not happen if it existed before
             logger.critical(f"[Worker-{worker_pid}] Application ID {application_id} disappeared during processing.")
             _log_event_util(application_id, "CRITICAL", f"Worker-{worker_pid} - Application disappeared during processing.", session=session)
             session.commit() # Commit the log at least
             return


        # Process automation_result
        result_status = automation_result.get("status", "unknown_completion")
        application.status = result_status
        application.error_details = automation_result.get("error_message") or automation_result.get("details")
        application.last_log_message = f"[INFO] Worker-{worker_pid} finished. Result: {result_status}. Msg: {automation_result.get('message', '')}"
        
        if "screenshot_path" in automation_result and automation_result["screenshot_path"]:
            application.review_screenshot_path = automation_result["screenshot_path"]

        application.timestamp_ended = datetime.datetime.utcnow()

        if result_status == "failed" and application.retry_count < application.max_retries:
            application.status = "queued" # Re-queue for retry
            application.retry_count += 1
            application.last_log_message = f"[INFO] Task failed, queued for retry ({application.retry_count}/{application.max_retries}). Error: {application.error_details}"
            _log_event_util(application_id, "WARN", f"Task failed, requeuing for retry {application.retry_count}/{application.max_retries}. Error: {application.error_details}. New status: {application.status}", session=session)
            logger.warning(f"[{worker_name} PID-{worker_pid}] app_id: {application_id} FAILED, requeuing for retry {application.retry_count}/{application.max_retries}. New status: {application.status}")
        elif result_status == "failed": # Failed and max_retries met or exceeded
            application.status = "failed_final" # A terminal failed state
            application.last_log_message = f"[ERROR] Task failed permanently after {application.retry_count} retries. Error: {application.error_details}"
            _log_event_util(application_id, "ERROR", f"Task failed permanently after {application.retry_count} retries. Error: {application.error_details}. New status: {application.status}", session=session)
            logger.error(f"[{worker_name} PID-{worker_pid}] app_id: {application_id} FAILED permanently after {application.retry_count} retries. New status: {application.status}")
        else:
            _log_event_util(application_id, "INFO", f"Task completed with status: {result_status}. Details: {application.error_details}", session=session)
            logger.info(f"[{worker_name} PID-{worker_pid}] app_id: {application_id} processed. Final status: {application.status}")


        session.commit()
        logger.info(f"[{worker_name} PID-{worker_pid}] Successfully processed application_id: {application_id}. Final status committed to DB: {application.status}")
        _log_event_util(application_id, "DEBUG", f"WorkerFunction END. PID: {worker_pid}. Final DB status: {application.status}", session=session)

    except Exception as e:
        logger.critical(f"[{worker_name} PID-{worker_pid}] CRITICAL ERROR processing application_id {application_id}: {e}", exc_info=True)
        if session:
            session.rollback()
            try:
                # Try to fetch app again to log error status, even if original app object is problematic
                app_for_error = session.query(_Application).get(application_id) # Use existing session for this attempt
                if app_for_error:
                    app_for_error.status = "failed_worker_exception"
                    err_details = f"[{worker_name} PID-{worker_pid}] uncaught exception: {str(e)}"
                    app_for_error.error_details = err_details
                    app_for_error.last_log_message = f"[CRITICAL ERROR] {err_details}"
                    app_for_error.timestamp_ended = datetime.datetime.utcnow()
                    
                    _log_event_util(application_id, "CRITICAL", err_details, session=session) # Log the critical error itself

                    if app_for_error.retry_count < app_for_error.max_retries:
                        app_for_error.status = "queued" # Re-queue
                        app_for_error.retry_count += 1
                        app_for_error.retry_count += 1
                        _log_event_util(application_id, "ERROR", f"Worker exception, requeuing for retry {app_for_error.retry_count}/{app_for_error.max_retries}: {e}. New status: {app_for_error.status}", session=session)
                        logger.error(f"[{worker_name} PID-{worker_pid}] app_id: {application_id} EXCEPTION, requeuing for retry {app_for_error.retry_count}/{app_for_error.max_retries}. New status: {app_for_error.status}")
                    else:
                        app_for_error.status = "failed_final" # Terminal failure after exception and retries
                        _log_event_util(application_id, "ERROR", f"Worker exception, max retries reached, failing permanently: {e}. New status: {app_for_error.status}", session=session)
                        logger.error(f"[{worker_name} PID-{worker_pid}] app_id: {application_id} EXCEPTION, FAILED permanently after {app_for_error.retry_count} retries. New status: {app_for_error.status}")
                    session.commit()
                    _log_event_util(application_id, "DEBUG", f"WorkerFunction EXCEPTION HANDLED. PID: {worker_pid}. Final DB status: {app_for_error.status}", session=session)
            except Exception as db_err: # This except corresponds to the try starting on line 178
                logger.critical(f"[{worker_name} PID-{worker_pid}] FATAL: Could not update application status after error: {db_err}", exc_info=True)
            if _log_event_util: # Attempt to log this secondary critical error
                _log_event_util(application_id, "CRITICAL", f"Worker-{worker_pid} FATAL: Could not update application status after error: {db_err}. Original error: {e}", session=session) # session might be compromised
                try:
                    session.commit() # Try to commit the log
                except:
                    pass # Best effort
        if session:
            session.close()
            logger.debug(f"[{worker_name} PID-{worker_pid}] DB session closed for application_id: {application_id}")
        logger.info(f"[{worker_name} PID-{worker_pid}] Finished attempt for application_id: {application_id}")

def worker_manager_process(task_queue, stop_event, db_uri_for_manager):
    """
    Polls the database for new tasks and puts them into the in-memory queue.
    """
    if _Application is None: # Ensure imports are done if not already
        initialize_worker_imports()
    
    manager_pid = os.getpid()
    logger.info(f"[Manager-{manager_pid}] Worker Manager process starting.")
    
    session = None
    while not stop_event.is_set():
        try:
            session = create_new_db_session(db_uri_for_manager)
            # logger.debug(f"[Manager-{manager_pid}] DB session created for polling.")

            # Back-pressure: Don't query for more tasks if the queue is full
            # or if too many tasks are already 'processing'
            active_processing_count = session.query(_Application).filter_by(status="processing").count()
            
            if task_queue.qsize() < TASK_QUEUE_MAX_SIZE and active_processing_count < MAX_WORKERS * 1.5:
                # Fetch tasks: status='queued', order by priority (lower is higher), then by creation time
                tasks_to_queue = session.query(_Application).\
                    filter(_Application.status == "queued").\
                    order_by(_Application.priority.asc(), _Application.timestamp_started.asc()).\
                    limit(MAX_WORKERS - task_queue.qsize()).all()

                if tasks_to_queue:
                    logger.info(f"[Manager-{manager_pid}] Found {len(tasks_to_queue)} tasks to queue.")
                    for task in tasks_to_queue:
                        if task_queue.full():
                            logger.warning(f"[Manager-{manager_pid}] In-memory task queue is full. Waiting.")
                            break
                        
                        logger.debug(f"[Manager-{manager_pid}] Fetching task from DB: app_id={task.id}, status={task.status}, priority={task.priority}, retries={task.retry_count}")
                        _log_event_util(task.id, "DEBUG", f"Manager: Fetched task from DB. Status: {task.status}, Priority: {task.priority}, Retries: {task.retry_count}", session=session)

                        task.status = "processing" # Mark as processing BEFORE putting in queue
                        task.last_attempted_at = datetime.datetime.utcnow()
                        task.last_log_message = "[INFO] Task picked up by manager, moving to in-memory queue."
                        # session.add(task) # Task is already part of the session from the query
                        
                        task_queue.put(task.id) # Put application_id into the queue
                        logger.info(f"[Manager-{manager_pid}] Queued application_id: {task.id}. New status 'processing'. Queue size: {task_queue.qsize()}")
                        _log_event_util(task.id, "INFO", f"Manager: Task moved to in-memory queue. New status 'processing'. Queue size: {task_queue.qsize()}", session=session)
                    session.commit()
                else:
                    # logger.debug(f"[Manager-{manager_pid}] No new 'queued' tasks found in DB. Queue size: {task_queue.qsize()}, Processing: {active_processing_count}")
                    pass
            else:
                # logger.debug(f"[Manager-{manager_pid}] Queue full (size: {task_queue.qsize()}) or too many processing ({active_processing_count}). Waiting.")
                pass
            
            session.close() # Close session after each polling loop
            session = None # Ensure it's reset for the next iteration's try/finally
            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"[Manager-{manager_pid}] Error in worker manager loop: {e}", exc_info=True)
            if session:
                session.rollback()
                session.close()
                session = None
            time.sleep(POLL_INTERVAL * 2) # Wait longer after an error
        finally:
            if session: # Should be None if closed properly, but as a safeguard
                session.close()
                session = None
                # logger.debug(f"[Manager-{manager_pid}] DB session closed in finally block.")


    logger.info(f"[Manager-{manager_pid}] Worker Manager process stopping.")

# --- Global variables for managing processes ---
_manager_process = None
_worker_pool = []
_task_queue = None
_stop_event = None

def start_task_processing_system(flask_app_instance_for_uri):
    """Starts the worker manager and worker pool."""
    global _manager_process, _worker_pool, _task_queue, _stop_event, DB_URI, _flask_app
    
    if _manager_process and _manager_process.is_alive():
        logger.info("[System] Task processing system already running.")
        return
    logger.info("[System] Initializing task processing system...")

    if _Application is None: # Ensure imports are done if not already
        initialize_worker_imports()
    
    _flask_app = flask_app_instance_for_uri # Store the app instance
    DB_URI = flask_app_instance_for_uri.config["SQLALCHEMY_DATABASE_URI"]
    logger.info(f"[System] DB_URI set to: {DB_URI}")

    _task_queue = multiprocessing.Queue(maxsize=TASK_QUEUE_MAX_SIZE)
    _stop_event = multiprocessing.Event()
    logger.info("[System] Task queue and stop event created.")

    # Start Worker Manager Process
    _manager_process = multiprocessing.Process(
        target=worker_manager_process,
        args=(_task_queue, _stop_event, DB_URI),
        name="WorkerManager"
    )
    _manager_process.start()
    logger.info(f"[System] Worker Manager process ({_manager_process.name} PID: {_manager_process.pid}) initiated.")

    # Start Worker Pool
    _worker_pool = []
    for i in range(MAX_WORKERS):
        worker_name = f"Worker-{i+1}"
        worker = multiprocessing.Process(
            target=worker_process_loop, # Pass function directly
            args=(_task_queue, _stop_event, DB_URI),
            name=worker_name
        )
        _worker_pool.append(worker)
        worker.start()
        logger.info(f"[System] Worker process {worker.name} (PID: {worker.pid}) started.")
    
    logger.info(f"[System] Task processing system started with {MAX_WORKERS} workers.")

def worker_process_loop(task_queue, stop_event, db_uri_for_worker_loop):
    """Loop for individual worker processes to consume tasks from the queue."""
    # Imports are initialized inside worker_function if needed
    worker_name = multiprocessing.current_process().name
    logger.info(f"[{worker_name}] Worker process loop started (PID: {os.getpid()}).")
    while not stop_event.is_set():
        try:
            # Get task from queue, with a timeout to allow checking stop_event
            application_id = task_queue.get(timeout=1.0)
            if application_id is None: # Sentinel value to stop
                break
            worker_function(application_id, db_uri_for_worker_loop)
        except multiprocessing.queues.Empty:
            # Queue was empty, loop again and check stop_event
            continue
        except Exception as e:
            # Should not happen if worker_function catches its errors
            logger.error(f"[{multiprocessing.current_process().name}] Error in worker loop: {e}", exc_info=True)
            time.sleep(1) # Avoid fast error loops
    logger.info(f"[{multiprocessing.current_process().name}] Worker process loop stopping.")


def stop_task_processing_system():
    """Stops the worker manager and worker pool gracefully."""
    global _manager_process, _worker_pool, _task_queue, _stop_event
    
    if not _stop_event or not _manager_process:
        logger.info("[System] Task processing system not running or already stopped.")
        return

    logger.info("[System] Stopping task processing system...")
    _stop_event.set()

    # Signal workers to stop by putting None into the queue for each
    if _task_queue:
        for _ in range(MAX_WORKERS):
            try:
                _task_queue.put(None, timeout=0.1) # Non-blocking if queue is full
            except multiprocessing.queues.Full:
                pass # Workers will timeout and see stop_event

    # Wait for Worker Manager to finish
    if _manager_process and _manager_process.is_alive():
        logger.info("[System] Waiting for Worker Manager to stop...")
        _manager_process.join(timeout=POLL_INTERVAL + 2)
        if _manager_process.is_alive():
            logger.warning("[System] Worker Manager did not stop in time, terminating.")
            _manager_process.terminate()
            _manager_process.join()

    # Wait for Worker Pool to finish
    for worker in _worker_pool:
        if worker.is_alive():
            logger.info(f"[System] Waiting for {worker.name} to stop...")
            worker.join(timeout=10) # Give workers time to finish current task
            if worker.is_alive():
                logger.warning(f"[System] {worker.name} did not stop in time, terminating.")
                worker.terminate()
                worker.join()
    
    if _task_queue:
        _task_queue.close()
        _task_queue.join_thread()

    _manager_process = None
    _worker_pool = []
    _task_queue = None
    _stop_event = None
    logger.info("[System] Task processing system stopped.")

# Example of how to ensure cleanup on exit (e.g., in Flask app context)
# import atexit
# atexit.register(stop_task_processing_system)
# This should be registered in main.py after app creation