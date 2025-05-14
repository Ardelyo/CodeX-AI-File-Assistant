import json
import datetime
import os

LOG_FILE_PATH = "activity_log.jsonl"
MAX_LOG_SIZE_MB = 5  
MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL = 50 

def log_action(action: str, parameters: dict, status: str = "success", details: str = None, chain_of_thought: str = None):
    """Logs an action to the activity log file, now including chain_of_thought."""
    log_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "parameters": parameters if parameters else {}, 
        "status": status,
        "details": details if details else "" 
    }
    if chain_of_thought is not None: # Add CoT if provided
        log_entry["chain_of_thought"] = chain_of_thought

    try:
        if os.path.exists(LOG_FILE_PATH) and os.path.getsize(LOG_FILE_PATH) > MAX_LOG_SIZE_MB * 1024 * 1024:
            os.rename(LOG_FILE_PATH, f"{LOG_FILE_PATH}.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.old")
            
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        # In a CLI app, printing directly might be okay, but consider a more robust logging for the logger itself
        print(f"[ActivityLogger] Error writing to log: {e}") 

def update_last_activity_status(new_status: str, new_details: str = None, result_data: dict = None):
    """Updates the status and details of the most recent log entry."""
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
            last_log_entry.setdefault("result_data", {}).update(result_data)
        
        all_lines[-1] = json.dumps(last_log_entry) + "\n"

        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.writelines(all_lines)
            
    except json.JSONDecodeError:
        print(f"[ActivityLogger] Error decoding last log entry for update.")
    except Exception as e:
        print(f"[ActivityLogger] Error updating last log entry: {e}")


def get_recent_activities(count: int = 10) -> list:
    """Retrieves the most recent 'count' activities from the log."""
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

def get_activity_by_partial_id_or_index(identifier: str, console) -> (dict | None):
    if not os.path.exists(LOG_FILE_PATH):
        if console: console.print("[yellow]Activity log is empty.[/yellow]")
        return None

    activities_to_search = get_recent_activities(MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL) 
    if not activities_to_search:
        if console: console.print("[yellow]No activities found in the log to match.[/yellow]")
        return None

    if identifier.lower() == "last" or identifier == "1":
        return activities_to_search[-1] if activities_to_search else None
    
    try: 
        index = int(identifier)
        if 1 <= index <= len(activities_to_search):
            return activities_to_search[-index] 
        else:
            if console: console.print(f"[yellow]Invalid activity index '{identifier}'. Max index is {len(activities_to_search)}.[/yellow]")
            return None
    except ValueError: 
        pass

    for activity in reversed(activities_to_search): 
        if identifier in activity.get("timestamp", ""):
            return activity
    
    if console: console.print(f"[yellow]No activity found matching identifier '{identifier}'.[/yellow]")
    return None


if __name__ == "__main__":
    log_action("test_action_1", {"param1": "value1"}, "success", "Test successful", "CoT for test 1")
    log_action("test_action_2", {"file": "/path/to/file.txt", "mode": "read"}, "pending_execution", "File not found", "CoT for test 2 - will fail")
    update_last_activity_status("failure", "File was indeed not found after trying.")

    print("\nRecent Activities:")
    recent = get_recent_activities(5)
    if recent:
        for activity in recent:
            print(f"- TS: {activity['timestamp']} | Action: {activity['action']} | Status: {activity['status']} | CoT: {activity.get('chain_of_thought','N/A')}")
    else:
        print("No activities logged or error reading log.")

    if recent:
        last_activity_ts = recent[-1]['timestamp']
        print(f"\nRetrieving activity by partial TS (first 10 chars of last): {last_activity_ts[:10]}")
        retrieved = get_activity_by_partial_id_or_index(last_activity_ts[:10], None) 
        if retrieved:
            print(f"Found: {retrieved}")
        else:
            print("Not found by partial TS.")
        
        print("\nRetrieving last activity by 'last':")
        retrieved_last = get_activity_by_partial_id_or_index("last", None)
        if retrieved_last:
            print(f"Found: {retrieved_last}")

        print("\nRetrieving 2nd to last activity by index '2':")
        retrieved_idx = get_activity_by_partial_id_or_index("2", None)
        if retrieved_idx:
            print(f"Found: {retrieved_idx}")