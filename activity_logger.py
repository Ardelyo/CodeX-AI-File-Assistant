import json
import datetime
import os

LOG_FILE_PATH = "activity_log.jsonl"
MAX_LOG_SIZE_MB = 5
MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL = 50

# Modified log_action function
def log_action(
    action: str,
    parameters: dict,
    status: str = "success",
    details: str = None,
    chain_of_thought: str = None,
    nlu_method: str = None, # Added
    is_multi_step_parent: bool = False # Added
):
    """
    Logs an action to the activity log.

    Args:
        action (str): The name of the action being logged.
        parameters (dict): The parameters passed to the action.
        status (str, optional): The status of the action. Defaults to "success".
        details (str, optional): Any additional details about the action's execution. Defaults to None.
        chain_of_thought (str, optional): The chain of thought from the NLU for this action. Defaults to None.
        nlu_method (str, optional): The NLU method used to determine the action. Defaults to None.
        is_multi_step_parent (bool, optional): True if this is the first action in a multi-step sequence. Defaults to False.
    """
    log_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "parameters": parameters if parameters else {},
        "status": status,
        "details": details if details else ""
    }
    if chain_of_thought is not None:
        log_entry["chain_of_thought"] = chain_of_thought
    if nlu_method is not None: # Added
        log_entry["nlu_method"] = nlu_method
    # Always include is_multi_step_parent, even if False, for consistency
    log_entry["is_multi_step_parent"] = is_multi_step_parent # Added

    try:
        if os.path.exists(LOG_FILE_PATH) and os.path.getsize(LOG_FILE_PATH) > MAX_LOG_SIZE_MB * 1024 * 1024:
            os.rename(LOG_FILE_PATH, f"{LOG_FILE_PATH}.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.old")

        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Return the timestamp as a unique ID for this log entry
        return log_entry["timestamp"] 
    except Exception as e:
        print(f"[ActivityLogger] Error writing to log: {e}")
        return None


def update_last_activity_status(new_status: str, new_details: str = None, result_data: dict = None): # Unchanged
    if not os.path.exists(LOG_FILE_PATH):
        return

    all_lines = []
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
    except Exception as e:
        print(f"[ActivityLogger] Error reading log for update: {e}")
        return

    if not all_lines:
        return

    try:
        last_log_entry = json.loads(all_lines[-1].strip())
        last_log_entry["status"] = new_status
        if new_details is not None:
            last_log_entry["details"] = new_details
        if result_data is not None:
            last_log_entry.setdefault("result_data", {}).update(result_data) # Ensure result_data is initialized if not present
        
        all_lines[-1] = json.dumps(last_log_entry) + "\n"

        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.writelines(all_lines)
            
    except json.JSONDecodeError:
        print(f"[ActivityLogger] Error decoding last log entry for update.")
    except Exception as e:
        print(f"[ActivityLogger] Error updating last log entry: {e}")

def get_recent_activities(count: int = 10) -> list: # Unchanged
    activities = []
    if not os.path.exists(LOG_FILE_PATH):
        return activities
    
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            
        for line in reversed(all_lines): 
            if len(activities) >= count:
                break
            try:
                activities.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
        return list(reversed(activities)) 
    except Exception as e:
        print(f"[ActivityLogger] Error reading log: {e}")
        return []

def get_activity_by_partial_id_or_index(identifier: str, console) -> (dict | None): # Unchanged
    if not os.path.exists(LOG_FILE_PATH):
        if console: console.print("[yellow]Activity log is empty.[/yellow]")
        return None

    activities_to_search = get_recent_activities(MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL) 
    if not activities_to_search:
        if console: console.print("[yellow]No activities found in the log to match.[/yellow]")
        return None

    # Handle "last" or direct index from end (e.g., "1" means the most recent)
    if identifier.lower() == "last" or identifier == "1": # Assuming "1" refers to the most recent
        return activities_to_search[-1] if activities_to_search else None
    
    try: 
        # Convert to 0-based index from the end for user convenience (1-based from most recent)
        index = int(identifier)
        if 1 <= index <= len(activities_to_search):
            # activities_to_search is already [oldest_retrieved, ..., newest_retrieved]
            # So, user index 1 = activities_to_search[-1]
            # User index N = activities_to_search[-N]
            return activities_to_search[-index] 
        else:
            if console: console.print(f"[yellow]Invalid activity index '{identifier}'. Max index is {len(activities_to_search)}.[/yellow]")
            return None
    except ValueError: 
        # Not an integer, so treat as partial ID (timestamp)
        pass

    # Search by partial timestamp (ID)
    for activity in reversed(activities_to_search): # Search from newest to oldest for timestamp match
        if identifier in activity.get("timestamp", ""):
            return activity
    
    if console: console.print(f"[yellow]No activity found matching identifier '{identifier}'.[/yellow]")
    return None

if __name__ == "__main__": # Updated example call
    # Example of logging with the new parameters
    log_action(
        action="test_action_1",
        parameters={"param1": "value1"},
        status="success",
        details="Test successful",
        chain_of_thought="CoT for test 1",
        nlu_method="direct_parser_test",
        is_multi_step_parent=False
    )
    log_action(
        action="test_action_2_parent",
        parameters={"file": "/path/to/file.txt", "mode": "read"},
        status="pending_execution",
        details="File not found yet",
        chain_of_thought="CoT for test 2 - will fail - parent",
        nlu_method="llm_test",
        is_multi_step_parent=True
    )
    update_last_activity_status("failure", "File was indeed not found after trying.")

    print("\nRecent Activities:")
    recent = get_recent_activities(5)
    if recent:
        for activity in recent:
            print(f"- TS: {activity['timestamp']} | Action: {activity['action']} | Status: {activity['status']} | CoT: {activity.get('chain_of_thought','N/A')} | NLU: {activity.get('nlu_method','N/A')} | Parent: {activity.get('is_multi_step_parent', 'N/A')}")
    else:
        print("No activities logged or error reading log.")