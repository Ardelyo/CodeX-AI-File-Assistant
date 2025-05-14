import os
import re

# No direct Rich UI dependencies here, but they might need session_ctx

def parse_direct_search(user_input: str) -> dict | None:
    # This function will be removed as per the new strategy.
    # Keeping it here as a placeholder to indicate it's targeted for removal.
    return None

def parse_direct_list(user_input: str, session_ctx: dict) -> dict | None: # Takes session_ctx
    # This function will be removed as per the new strategy.
    return None

def parse_direct_activity_log(user_input: str) -> dict | None:
    user_input_lower = user_input.lower()
    # Pattern: show [me/my] [last/recent] [N] activities/activity/log/logs/history [history]
    activity_log_pattern = r"^(?:show|view|display)\s+(?:me\s+|my\s+)?(?:last\s+|recent\s+)?(\d*)\s*(?:activities|activity|logs?|history)(?:\s+history)?$"
    match = re.match(activity_log_pattern, user_input_lower)
    if match:
        count_str = match.group(1) # Capture the optional number
        params = {}
        if count_str: # If a number was provided for count
            try: params["count"] = int(count_str)
            except ValueError: pass # Ignore if not a valid int, will use default count
        return {"action": "show_activity_log", "parameters": params, "nlu_method": "direct_activity_log"}
    
    # Simpler pattern for "activity log" or "show log"
    if user_input_lower in ["activity log", "show log", "show history", "view history", "logs", "history"]:
        return {"action": "show_activity_log", "parameters": {}, "nlu_method": "direct_activity_log_simple"}
        
    return None

def parse_direct_summarize(user_input: str, session_ctx: dict) -> dict | None: # Takes session_ctx
    # This function will be removed as per the new strategy.
    return None


def parse_direct_organize(user_input: str, session_ctx: dict) -> dict | None: # Takes session_ctx
    # This function will be removed as per the new strategy.
    return None


def parse_direct_move(user_input: str) -> dict | None:
    # This function will be removed as per the new strategy.
    return None

# --- UPDATED FUNCTION ---
def try_all_direct_parsers(user_input: str, session_ctx: dict) -> dict | None:
    """
    Tries all available direct parsers in a predefined order.
    Returns the result of the first successful parser, or None if none match.
    Most parsers are removed to rely more on LLM.
    """
    # Order matters: more specific or common patterns first.
    parsers_to_try = [
        # Specific utility commands
        {"name": "activity_log", "func": parse_direct_activity_log, "needs_ctx": False},
        # Removed: move, summarize, organize, search, list
        # 'help' and 'exit' are handled directly in main_cli.py loop
    ]

    for parser_info in parsers_to_try:
        try:
            if parser_info["needs_ctx"]: # parse_direct_activity_log does not need ctx currently
                result = parser_info["func"](user_input, session_ctx)
            else:
                result = parser_info["func"](user_input)
            
            if result:
                return result
        except Exception:
            # Optionally log or print if a specific parser fails unexpectedly
            # print(f"DEBUG: Error in direct parser '{parser_info['name']}': {e}")
            pass # Continue to the next parser
            
    return None
