import os
import json
import datetime

# Corrected relative import: cli_ui is in the same 'python' package
from .cli_ui import print_warning, print_error 

SESSION_CONTEXT_FILE = "session_context.json" # This will be in the project root
MAX_COMMAND_HISTORY = 20 

_session_context = {
    "current_directory": os.getcwd(), 
    "last_referenced_file_path": None, 
    "last_folder_listed_path": None,
    "last_search_results": [], 
    "command_history": [], 
    "last_command_status": None,
    "last_action": None,
    "last_parameters": None
}

def get_session_context(): # Unchanged
    _session_context["current_directory"] = os.getcwd() 
    return _session_context

def load_session_context(): # Unchanged
    global _session_context
    _session_context["current_directory"] = os.getcwd() 

    # SESSION_CONTEXT_FILE should be at the project root, where main_cli.py runs
    session_file_actual_path = os.path.join(os.getcwd(), SESSION_CONTEXT_FILE)
    # However, if main_cli.py changes CWD, this could be an issue.
    # Better to define SESSION_CONTEXT_FILE relative to the script that writes it,
    # or an absolute path, or ensure CWD is stable when this is called.
    # For now, assuming it's in the CWD where main_cli.py starts.

    if os.path.exists(session_file_actual_path): # Use actual path
        try:
            with open(session_file_actual_path, "r", encoding="utf-8") as f: # Use actual path
                loaded_ctx = json.load(f)
                for key, default_val in _session_context.items():
                    if key != "current_directory": 
                        _session_context[key] = loaded_ctx.get(key, default_val)
            
            if not isinstance(_session_context.get("last_search_results"), list):
                 _session_context["last_search_results"] = []
            if not isinstance(_session_context.get("command_history"), list):
                 _session_context["command_history"] = []

        except (json.JSONDecodeError, IOError) as e:
            print_warning(f"Could not load session context from '{session_file_actual_path}': {e}. Starting fresh.", "Session Warning")
            cwd = _session_context["current_directory"]
            _session_context = {
                "current_directory": cwd,
                "last_referenced_file_path": None, "last_folder_listed_path": None,
                "last_search_results": [], "command_history": [],
                "last_command_status": None, "last_action": None, "last_parameters": None
            }
    else:
        pass


def save_session_context(): # Unchanged
    global _session_context
    _session_context["current_directory"] = os.getcwd() 
    session_file_actual_path = os.path.join(os.getcwd(), SESSION_CONTEXT_FILE) # Use actual path
    try:
        with open(session_file_actual_path, "w", encoding="utf-8") as f: # Use actual path
            json.dump(_session_context, f, indent=2)
    except IOError as e:
        print_error(f"Error saving session context to '{session_file_actual_path}': {e}", "Session Save Error")

def update_session_context(key, value): # Unchanged
    global _session_context
    _session_context[key] = value
    
    if key == "last_search_results" and value is not None:
        _session_context["last_referenced_file_path"] = None 
    elif key == "last_referenced_file_path" and value:
        if os.path.isfile(value):
            _session_context["last_folder_listed_path"] = os.path.dirname(value)
        elif os.path.isdir(value):
             _session_context["last_folder_listed_path"] = value
        else: 
            _session_context["last_folder_listed_path"] = None
    elif key == "last_folder_listed_path" and value:
        _session_context["last_referenced_file_path"] = None 

def add_to_command_history(action: str, parameters: dict, nlu_notes: str = None): # Unchanged
    global _session_context
    if "command_history" not in _session_context or not isinstance(_session_context["command_history"], list):
        _session_context["command_history"] = []
    
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), 
        "action": action, 
        "parameters": parameters if parameters else {} 
    }
    if nlu_notes: 
        entry["nlu_notes"] = nlu_notes
        
    _session_context["command_history"].append(entry)
    _session_context["command_history"] = _session_context["command_history"][-MAX_COMMAND_HISTORY:]