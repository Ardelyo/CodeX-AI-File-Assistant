import os
import json
import datetime

# Assuming cli_ui.py is in the same directory or Python path
from .cli_ui import print_warning, print_error # For load/save errors

SESSION_CONTEXT_FILE = "session_context.json"
MAX_COMMAND_HISTORY = 20 # Max entries for the brief command history in session

_session_context = {
    "current_directory": os.getcwd(), # Added current_directory
    "last_referenced_file_path": None, 
    "last_folder_listed_path": None,
    "last_search_results": [], 
    "command_history": [], # For brief nlu_notes, not full CoT
    "last_command_status": None,
    "last_action": None,
    "last_parameters": None
}

def get_session_context():
    # Ensure current directory is always up-to-date if it can change outside this manager
    _session_context["current_directory"] = os.getcwd() 
    return _session_context

def load_session_context():
    global _session_context
    _session_context["current_directory"] = os.getcwd() # Initialize/update on load

    if os.path.exists(SESSION_CONTEXT_FILE):
        try:
            with open(SESSION_CONTEXT_FILE, "r", encoding="utf-8") as f:
                loaded_ctx = json.load(f)
                # Selectively update to preserve current_directory managed by os.getcwd()
                # and ensure new keys are present
                for key, default_val in _session_context.items():
                    if key != "current_directory": # Don't override live CWD with stale CWD
                        _session_context[key] = loaded_ctx.get(key, default_val)
            
            # Ensure essential keys have their default types if missing from file
            if not isinstance(_session_context.get("last_search_results"), list):
                 _session_context["last_search_results"] = []
            if not isinstance(_session_context.get("command_history"), list):
                 _session_context["command_history"] = []

        except (json.JSONDecodeError, IOError) as e:
            print_warning(f"Could not load session context: {e}. Starting fresh.", "Session Warning")
            # Reset to defaults, but keep current_directory
            cwd = _session_context["current_directory"]
            _session_context = {
                "current_directory": cwd,
                "last_referenced_file_path": None, "last_folder_listed_path": None,
                "last_search_results": [], "command_history": [],
                "last_command_status": None, "last_action": None, "last_parameters": None
            }
    else:
        # If file doesn't exist, _session_context is already initialized with CWD and defaults
        pass


def save_session_context():
    global _session_context
    _session_context["current_directory"] = os.getcwd() # Ensure CWD is current before saving
    try:
        with open(SESSION_CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(_session_context, f, indent=2)
    except IOError as e:
        print_error(f"Error saving session context: {e}", "Session Save Error")

def update_session_context(key, value):
    global _session_context
    _session_context[key] = value
    
    # Keep related context items consistent
    if key == "last_search_results" and value is not None:
        _session_context["last_referenced_file_path"] = None # Clear last file if new search results
    elif key == "last_referenced_file_path" and value:
        # If it's a file, set last_folder to its directory. If it's a dir, set last_folder.
        if os.path.isfile(value):
            _session_context["last_folder_listed_path"] = os.path.dirname(value)
        elif os.path.isdir(value):
             _session_context["last_folder_listed_path"] = value
        else: # Path doesn't exist or is not file/dir
            _session_context["last_folder_listed_path"] = None
    elif key == "last_folder_listed_path" and value:
        _session_context["last_referenced_file_path"] = None # Listing a folder clears specific last file

def add_to_command_history(action: str, parameters: dict, nlu_notes: str = None):
    """Adds to the short-term command history stored in session_context.json.
       This is for brief NLU notes, not the full Chain of Thought which goes to activity_log.jsonl.
    """
    global _session_context
    if "command_history" not in _session_context or not isinstance(_session_context["command_history"], list):
        _session_context["command_history"] = []
    
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), 
        "action": action, 
        "parameters": parameters if parameters else {} # Ensure it's a dict
    }
    if nlu_notes: # nlu_notes are brief, like "direct_parsed", "llm_corrected"
        entry["nlu_notes"] = nlu_notes
        
    _session_context["command_history"].append(entry)
    _session_context["command_history"] = _session_context["command_history"][-MAX_COMMAND_HISTORY:]