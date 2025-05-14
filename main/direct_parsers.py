
import os
import re

# No direct Rich UI dependencies here, but they might need session_ctx

def parse_direct_search(user_input: str) -> dict | None:
    user_input_lower = user_input.lower()
    if not (user_input_lower.startswith("search ") or user_input_lower.startswith("find ")):
        return None
    
    match_in = re.search(r"^(?:search|find)\s+(?:for\s+)?(?P<criteria>.+?)\s+in\s+(?P<path>(?:['\"].+?['\"])|(?:[^'\"\s]+(?:[\s][^'\"\s]+)*))$", user_input, re.IGNORECASE)
    if match_in:
        criteria = match_in.group("criteria").strip().rstrip("'\" ")
        path = match_in.group("path").strip().strip("'\" ") 
        if criteria:
            return {"action": "search_files", "parameters": {"search_criteria": criteria, "search_path": path}, "nlu_method": "direct_search_in"}

    path_regex_str = r"""
    (
        (?:['"])(?P<quoted_path_content>.+?)(?:['"])|                                       
        (?P<abs_win_path>[a-zA-Z]:\\(?:[^<>:"/\\|?*\s\x00-\x1f]+\\)*[^<>:"/\\|?*\s\x00-\x1f]*?)| 
        (?P<abs_unix_path>/(?:[^<>:"/\\|?*\s\x00-\x1f]+/)*[^<>:"/\\|?*\s\x00-\x1f]*?)|         
        (?P<rel_path>(?:~[/\\][^<>:"/\\|?*\s\x00-\x1f]*)|                                     
                      (?:\.[/\\]?[^<>:"/\\|?*\s\x00-\x1f]+)|                                  
                      (?:[^<>:"/\\|?*\s\x00-\x1f./\\'"\s][^<>:"/\\|?*\s\x00-\x1f./\\']*(?:[/\\][^<>:"/\\|?*\s\x00-\x1f./\\']+)*) 
        )
    )
    """
    match_no_in_str = r"^(?:search|find)\s+(?:for\s+)?(?P<criteria>.+?)\s+" + path_regex_str + r"$"
    
    try:
        match_no_in = re.search(match_no_in_str, user_input, re.IGNORECASE | re.VERBOSE)
    except re.error:
        match_no_in = None

    if match_no_in:
        criteria = match_no_in.group("criteria").strip().rstrip("'\" ")
        path_candidate = None
        if match_no_in.group("quoted_path_content"): path_candidate = match_no_in.group("quoted_path_content").strip()
        elif match_no_in.group("abs_win_path"): path_candidate = match_no_in.group("abs_win_path").strip()
        elif match_no_in.group("abs_unix_path"): path_candidate = match_no_in.group("abs_unix_path").strip()
        elif match_no_in.group("rel_path"): path_candidate = match_no_in.group("rel_path").strip()
        
        if criteria and path_candidate:
            return {"action": "search_files", "parameters": {"search_criteria": criteria, "search_path": path_candidate}, "nlu_method": "direct_search_path_v2"}

    match_simple_criteria = re.search(r"^(?:search|find)\s+(?:for\s+)?(?P<criteria>.+)$", user_input, re.IGNORECASE)
    if match_simple_criteria:
        criteria_val = match_simple_criteria.group("criteria").strip().rstrip("'\" ")
        potential_path_abs = os.path.abspath(criteria_val)
        if (os.path.sep in criteria_val or criteria_val.startswith(('.', '~')) or os.path.isabs(criteria_val)) and \
           os.path.exists(potential_path_abs) and os.path.isdir(potential_path_abs):
            return {"action": "search_files", "parameters": {"search_criteria": "__MISSING__", "search_path": criteria_val}, "nlu_method": "direct_search_path_as_criteria"}
        
        if criteria_val:
            return {"action": "search_files", "parameters": {"search_criteria": criteria_val, "search_path": "__MISSING__"}, "nlu_method": "direct_search_criteria_only"}
            
    return None

def parse_direct_list(user_input: str, session_ctx: dict) -> dict | None: # Takes session_ctx
    user_input_lower = user_input.lower()
    list_prefix_match = re.match(r"^(?:list|ls|show\s+(?:me\s+)?(?:the\s+)?(?:files\s+in|contents\s+of))\s*(.*)$", user_input_lower)
    if not list_prefix_match:
        if user_input_lower in ["list it", "ls it", "list this folder", "ls this folder", "list here", "ls here"]:
            return {"action": "list_folder_contents", "parameters": {"folder_path": "__FROM_CONTEXT__"}, "nlu_method": "direct_list_context"}
        return None
    path_part = list_prefix_match.group(1).strip()
    folder_path_param = "__MISSING__"
    if path_part:
        if path_part in ["it", "this", "here", "this folder", "current folder", "."]:
            folder_path_param = "__FROM_CONTEXT__"
        else:
            folder_path_param = path_part.strip("'\"")
    elif any(k in user_input_lower for k in ["it", "this folder", "here"]): # If "list" or "ls" was standalone but implies context
        folder_path_param = "__FROM_CONTEXT__"
    return {"action": "list_folder_contents", "parameters": {"folder_path": folder_path_param}, "nlu_method": "direct_list"}

def parse_direct_activity_log(user_input: str) -> dict | None:
    user_input_lower = user_input.lower()
    activity_log_pattern = r"^(?:show|view)\s+(?:me\s+|my\s+)?(?:last\s+|recent\s+)?(\d*)\s*(?:activities|activity|logs?|history)(?:\s+history)?$"
    match = re.match(activity_log_pattern, user_input_lower)
    if match:
        count_str = match.group(1)
        params = {}
        if count_str:
            try: params["count"] = int(count_str)
            except ValueError: pass
        return {"action": "show_activity_log", "parameters": params, "nlu_method": "direct_activity"}
    return None

def parse_direct_summarize(user_input: str, session_ctx: dict) -> dict | None: # Takes session_ctx
    user_input_lower = user_input.lower()
    summarize_match = re.match(r"^summarize\s+(.*)$", user_input_lower)
    if not summarize_match: return None
    path_part = summarize_match.group(1).strip()
    file_path_param = "__MISSING__"
    if path_part:
        if path_part in ["it", "this", "this file"]: file_path_param = "__FROM_CONTEXT__"
        else: file_path_param = path_part.strip("'\"")
    elif any(k in user_input_lower for k in ["it", "this file"]): file_path_param = "__FROM_CONTEXT__"
    if "search" in path_part or "find" in path_part: return None # Avoid conflict with search
    if file_path_param != "__MISSING__":
        return {"action": "summarize_file", "parameters": {"file_path": file_path_param}, "nlu_method": "direct_summarize"}
    return None

def parse_direct_organize(user_input: str, session_ctx: dict) -> dict | None: # Takes session_ctx
    user_input_lower = user_input.lower()
    organize_verb_match = re.match(r"^(organize|sort|clean\s*up)\s*", user_input_lower, re.IGNORECASE)
    if not organize_verb_match:
        return None

    remaining_text_full = user_input[organize_verb_match.end():].strip()
    
    target_path_or_context = "__MISSING__"
    organization_goal = None
    
    path_regex_patterns = {
        "quoted": r"""(?:['"])(?P<path_content>.+?)(?:['"])""",
        "abs_win": r"""(?P<path_content>[a-zA-Z]:\\(?:[^<>:"/\\|?*\s\x00-\x1f]+\\)*[^<>:"/\\|?*\s\x00-\x1f]*?)""",
        "abs_unix": r"""(?P<path_content>/(?:[^<>:"/\\|?*\s\x00-\x1f]+/)*[^<>:"/\\|?*\s\x00-\x1f]*?)""",
        "rel_dots_tilde": r"""(?P<path_content>(?:~|\.\.?)(?:[/\\][^<>:"/\\|?*\s\x00-\x1f]*)*)"""
    }

    potential_paths_with_spans = []
    for key, pattern in path_regex_patterns.items():
        for match_obj in re.finditer(pattern, remaining_text_full, re.IGNORECASE):
            path_str = match_obj.group("path_content")
            if path_str:
                potential_paths_with_spans.append({"path": path_str.strip(), "span": match_obj.span(), "type": key})

    potential_paths_with_spans.sort(key=lambda x: (x["span"][1], (x["span"][1] - x["span"][0])), reverse=True)

    identified_path_abs = None
    text_for_goal_processing = remaining_text_full

    for cand in potential_paths_with_spans:
        try:
            path_to_check = cand["path"]
            if path_to_check.startswith('~'):
                path_to_check = os.path.expanduser(path_to_check)
            
            abs_path = os.path.abspath(path_to_check)
            if os.path.exists(abs_path) and os.path.isdir(abs_path):
                identified_path_abs = abs_path
                target_path_or_context = identified_path_abs
                
                pre_path = remaining_text_full[:cand["span"][0]].rstrip()
                post_path = remaining_text_full[cand["span"][1]:].lstrip()
                text_for_goal_processing = f"{pre_path} {post_path}".strip()
                break
        except Exception:
            continue

    if not identified_path_abs:
        context_keyword_pattern = r"\b(them|this(?:\s+folder)?|it|here|\.)\b"
        context_matches = list(re.finditer(context_keyword_pattern, text_for_goal_processing, re.IGNORECASE))
        if context_matches:
            context_match = context_matches[-1] 
            target_path_or_context = "__FROM_CONTEXT__"
            
            start_idx, end_idx = context_match.span()
            pre_ctx = text_for_goal_processing[:start_idx].rstrip()
            post_ctx = text_for_goal_processing[end_idx:].lstrip()
            text_for_goal_processing = f"{pre_ctx} {post_ctx}".strip()

        elif not text_for_goal_processing.strip() and session_ctx.get("last_folder_listed_path"):
             target_path_or_context = "__FROM_CONTEXT__"

    text_for_goal_processing = text_for_goal_processing.strip()
    goal_prefix_pattern = r"^(?:by|based\s+on|using(?:\s+criteria)?)\s+"
    goal_prefix_match = re.match(goal_prefix_pattern, text_for_goal_processing, re.IGNORECASE)

    if goal_prefix_match:
        organization_goal = text_for_goal_processing[goal_prefix_match.end():].strip().rstrip("'\" ")
    elif text_for_goal_processing:
        organization_goal = text_for_goal_processing.strip().rstrip("'\" ")

    if target_path_or_context == "__MISSING__" and organization_goal:
        try:
            path_to_check_goal = organization_goal
            if path_to_check_goal.startswith('~'):
                path_to_check_goal = os.path.expanduser(path_to_check_goal)
            temp_abs_goal_path = os.path.abspath(path_to_check_goal)
            if os.path.exists(temp_abs_goal_path) and os.path.isdir(temp_abs_goal_path):
                target_path_or_context = temp_abs_goal_path
                organization_goal = None
        except Exception:
            pass

    params = {"target_path_or_context": target_path_or_context}
    if organization_goal:
        params["organization_goal"] = organization_goal
    
    return {"action": "propose_and_execute_organization", "parameters": params, "nlu_method": "direct_organize_v4"}


def parse_direct_move(user_input: str) -> dict | None:
    user_input_lower = user_input.lower()
    if not user_input_lower.startswith("move "):
        return None
    move_match = re.match(r"^move\s+(?P<source_part>.+?)\s+to\s+(?P<dest_part>.+)$", user_input, re.IGNORECASE)
    if move_match:
        source_str = move_match.group("source_part").strip().strip("'\"")
        dest_str = move_match.group("dest_part").strip().strip("'\"")
        if source_str and dest_str:
            return {
                "action": "move_item",
                "parameters": {"source_path": source_str, "destination_path": dest_str},
                "nlu_method": "direct_move_v1"
            }
    return None