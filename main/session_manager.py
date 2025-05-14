
import os
import json
import datetime

# Assuming cli_ui.py is in the same directory or Python path
from .cli_ui import print_warning, print_error # For load/save errors

SESSION_CONTEXT_FILE = "session_context.json"
MAX_COMMAND_HISTORY = 20

_session_context = {
    "last_referenced_file_path": None, "last_folder_listed_path": None,
    "last_search_results": [], "command_history": [],
}

def get_session_context():
    return _session_context

def load_session_context():
    global _session_context
    if os.path.exists(SESSION_CONTEXT_FILE):
        try:
            with open(SESSION_CONTEXT_FILE, "r", encoding="utf-8") as f:
                loaded_ctx = json.load(f)
                _session_context.update(loaded_ctx)
            # Ensure default keys exist if not in loaded context
            for key in ["last_referenced_file_path", "last_folder_listed_path", "last_search_results", "command_history"]:
                _session_context.setdefault(key, None if "path" in key else [])
        except (json.JSONDecodeError, IOError) as e:
            print_warning(f"Could not load session context: {e}. Starting fresh.", "Session Warning")
            _session_context = {"last_referenced_file_path": None, "last_folder_listed_path": None, "last_search_results": [], "command_history": []}
    else:
        _session_context = {"last_referenced_file_path": None, "last_folder_listed_path": None, "last_search_results": [], "command_history": []}


def save_session_context():
    global _session_context
    try:
        with open(SESSION_CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(_session_context, f, indent=2)
    except IOError as e:
        print_error(f"Error saving session context: {e}", "Session Save Error")

def update_session_context(key, value):
    global _session_context
    _session_context[key] = value
    if key == "last_search_results" and value is not None:
        _session_context["last_referenced_file_path"] = None
    elif key == "last_referenced_file_path" and value:
        _session_context["last_folder_listed_path"] = os.path.dirname(value) if os.path.isfile(value) else value if os.path.isdir(value) else None
    elif key == "last_folder_listed_path" and value:
        _session_context["last_referenced_file_path"] = None


def add_to_command_history(action: str, parameters: dict, nlu_notes: str = None):
    global _session_context
    if "command_history" not in _session_context or not isinstance(_session_context["command_history"], list):
        _session_context["command_history"] = []
    entry = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "action": action, "parameters": parameters if parameters else {}}
    if nlu_notes:
        entry["nlu_notes"] = nlu_notes
    _session_context["command_history"].append(entry)
    _session_context["command_history"] = _session_context["command_history"][-MAX_COMMAND_HISTORY:]