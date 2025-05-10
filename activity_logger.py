import json
import datetime
import os

LOG_FILE_PATH = "activity_log.jsonl"
MAX_LOG_SIZE_MB = 5  # Max size in MB before considering rotation (simple check)
MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL = 50 # Max entries to show for simple "show log"

def log_action(action: str, parameters: dict, status: str = "success", details: str = None):
    """Logs an action to the activity log file."""
    log_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "parameters": parameters if parameters else {}, # Ensure parameters is always a dict
        "status": status,
        "details": details if details else "" # Ensure details is always a string
    }
    try:
        # Check log file size (very basic rotation idea, real rotation is more complex)
        if os.path.exists(LOG_FILE_PATH) and os.path.getsize(LOG_FILE_PATH) > MAX_LOG_SIZE_MB * 1024 * 1024:
            # Basic rotation: rename old log, start new. Could be improved (e.g., numbered backups)
            os.rename(LOG_FILE_PATH, f"{LOG_FILE_PATH}.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.old")
            
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[ActivityLogger] Error writing to log: {e}")

def get_recent_activities(count: int = 10) -> list:
    """Retrieves the most recent 'count' activities from the log."""
    activities = []
    if not os.path.exists(LOG_FILE_PATH):
        return activities
    
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            # Read all lines, then take the last 'count'
            # For very large logs, reading all lines might be inefficient.
            # A more robust solution would read from the end or use a database.
            all_lines = f.readlines()
            
        for line in reversed(all_lines): # Start from the most recent
            if len(activities) >= count:
                break
            try:
                activities.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                # Skip malformed lines
                continue
        return list(reversed(activities)) # Return in chronological order
    except Exception as e:
        print(f"[ActivityLogger] Error reading log: {e}")
        return []

def get_activity_by_partial_id_or_index(identifier: str, console) -> (dict | None):
    """
    Retrieves an activity by a partial timestamp ID or a 1-based recency index.
    e.g., "last", "1" (most recent), "2" (second most recent), or a partial ISO timestamp.
    """
    if not os.path.exists(LOG_FILE_PATH):
        if console: console.print("[yellow]Activity log is empty.[/yellow]")
        return None

    activities_to_search = get_recent_activities(MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL) # Search within recent N for performance
    if not activities_to_search:
        if console: console.print("[yellow]No activities found in the log to match.[/yellow]")
        return None

    if identifier.lower() == "last" or identifier == "1":
        return activities_to_search[-1] if activities_to_search else None
    
    try: # Check if it's a 1-based index
        index = int(identifier)
        if 1 <= index <= len(activities_to_search):
            return activities_to_search[-index] # -1 is last, -2 is second last, etc.
        else:
            if console: console.print(f"[yellow]Invalid activity index '{identifier}'. Max index is {len(activities_to_search)}.[/yellow]")
            return None
    except ValueError: # Not an integer, assume it's a partial timestamp
        pass

    # Search by partial timestamp (simple substring match on timestamp string)
    for activity in reversed(activities_to_search): # Search from most recent
        if identifier in activity.get("timestamp", ""):
            return activity
    
    if console: console.print(f"[yellow]No activity found matching identifier '{identifier}'.[/yellow]")
    return None


if __name__ == "__main__":
    # Test logging
    log_action("test_action_1", {"param1": "value1"}, "success", "Test successful")
    log_action("test_action_2", {"file": "/path/to/file.txt", "mode": "read"}, "failure", "File not found")
    log_action("search_files", {"criteria": "images", "path": "."}, "success", "Found 5 images")

    # Test retrieval
    print("\nRecent Activities:")
    recent = get_recent_activities(5)
    if recent:
        for activity in recent:
            print(f"- {activity['timestamp']} | {activity['action']} | {activity['status']}")
    else:
        print("No activities logged or error reading log.")

    if recent:
        last_activity_ts = recent[-1]['timestamp']
        print(f"\nRetrieving activity by partial TS (first 10 chars of last): {last_activity_ts[:10]}")
        retrieved = get_activity_by_partial_id_or_index(last_activity_ts[:10], None) # Pass None for console in direct test
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