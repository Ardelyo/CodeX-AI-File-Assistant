import os
import time
import re
import json
import datetime
from ollama_connector import OllamaConnector
from file_utils import get_file_content, move_item, list_folder_contents, search_files_recursive
from activity_logger import log_action, get_recent_activities, get_activity_by_partial_id_or_index, MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL
from config import OLLAMA_MODEL

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.progress import Progress
from rich.style import Style
from rich.theme import Theme
from rich.markdown import Markdown
from rich.padding import Padding
from rich.align import Align
from rich.box import ROUNDED, HEAVY
from rich.rule import Rule

ICONS = {
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️",
    "thinking": "🧠", "plan": "📝", "execute": "🚀", "folder": "📁",
    "file": "📄", "search": "🔍", "question": "❓", "answer": "💡",
    "summary": "📋", "log": "📜", "redo": "🔄", "confirm": "🤔",
    "move": "📦", "create_folder": "➕📁", "app_icon": "🗂️", "organize": "🪄"
}

CUSTOM_THEME = Theme({
    "info": "dim cyan", "warning": "yellow", "danger": "bold red", "success": "green",
    "prompt": "bold #32CD32", "user_input_display": "italic #F0E68C",
    "filepath": "cyan", "highlight": "bold magenta",
    "panel.title": "bold white on #007ACC", "panel.border": "#007ACC",
    "panel.title.success": "bold white on green", "panel.border.success": "green",
    "panel.title.error": "bold white on red", "panel.border.error": "red",
    "panel.title.warning": "bold black on yellow", "panel.border.warning": "yellow",
    "panel.title.info": "bold white on #4682B4", "panel.border.info": "#4682B4",
    "table.header": "bold #007ACC", "table.cell": "default",
    "spinner_style": "bold #FF69B4", "progress.bar": "#4169E1",
    "progress.percentage": "cyan", "app_logo_style": "bold #007ACC",
    "separator_style": "dim #007ACC", "dim_text": "dim default"
})

APP_LOGO_TEXT = f"""
{ICONS['app_icon']} [app_logo_style]
 ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
        AI File Assistant v1.8.0[/app_logo_style] 
""" # Updated version

console = Console(theme=CUSTOM_THEME)
SESSION_CONTEXT_FILE = "session_context.json"
MAX_COMMAND_HISTORY = 20
session_context = {
    "last_referenced_file_path": None, "last_folder_listed_path": None,
    "last_search_results": [], "command_history": [],
}

# --- UI Helper Functions ---
def print_panel_message(title: str, message: str, panel_style_name: str, icon: str = "", box_style=ROUNDED):
    panel_title_style = f"panel.title.{panel_style_name}" if f"panel.title.{panel_style_name}" in CUSTOM_THEME.styles else "panel.title"
    panel_border_style = f"panel.border.{panel_style_name}" if f"panel.border.{panel_style_name}" in CUSTOM_THEME.styles else "panel.border"
    panel_title_text = f"{icon} {title}" if icon else title
    console.print(Panel(Text(message, justify="left"), title=f"[{panel_title_style}]{panel_title_text}[/]", border_style=panel_border_style, box=box_style, padding=(1, 2)))
def print_success(message: str, title: str = "Success"): print_panel_message(title, message, "success", ICONS["success"])
def print_error(message: str, title: str = "Error"): print_panel_message(title, message, "error", ICONS["error"])
def print_warning(message: str, title: str = "Warning"): print_panel_message(title, message, "warning", ICONS["warning"])
def print_info(message: str, title: str = "Information"): print_panel_message(title, message, "info", ICONS["info"])

# --- Session and Context Management ---
def load_session_context():
    global session_context
    if os.path.exists(SESSION_CONTEXT_FILE):
        try:
            with open(SESSION_CONTEXT_FILE, "r", encoding="utf-8") as f:
                loaded_ctx = json.load(f)
                session_context.update(loaded_ctx)
            for key in ["last_referenced_file_path", "last_folder_listed_path", "last_search_results", "command_history"]:
                session_context.setdefault(key, None if "path" in key else [])
        except (json.JSONDecodeError, IOError) as e:
            print_warning(f"Could not load session context: {e}. Starting fresh.", "Session Warning")
            session_context = {"last_referenced_file_path": None, "last_folder_listed_path": None, "last_search_results": [], "command_history": []}
def save_session_context():
    global session_context
    try:
        with open(SESSION_CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(session_context, f, indent=2)
    except IOError as e:
        print_error(f"Error saving session context: {e}", "Session Save Error")
def update_session_context(key, value):
    global session_context
    session_context[key] = value
    if key == "last_search_results" and value is not None: # If new search results, clear specific file ref
        session_context["last_referenced_file_path"] = None
    elif key == "last_referenced_file_path" and value: # If specific file, update its folder as last listed
        session_context["last_folder_listed_path"] = os.path.dirname(value) if os.path.isfile(value) else value if os.path.isdir(value) else None
    elif key == "last_folder_listed_path" and value: # If specific folder, clear specific file ref
        session_context["last_referenced_file_path"] = None

def add_to_command_history(action: str, parameters: dict, nlu_notes: str = None):
    global session_context
    if "command_history" not in session_context or not isinstance(session_context["command_history"], list):
        session_context["command_history"] = []
    entry = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "action": action, "parameters": parameters if parameters else {}}
    if nlu_notes:
        entry["nlu_notes"] = nlu_notes
    session_context["command_history"].append(entry)
    session_context["command_history"] = session_context["command_history"][-MAX_COMMAND_HISTORY:]
def get_path_from_user_input(prompt_message="Please provide the full path", default_path=None, is_folder=False):
    path_type = "folder" if is_folder else "file/folder"
    prompt_suffix = f" ([filepath]{path_type}[/filepath])"
    styled_prompt = Text.from_markup(f"{ICONS['confirm']} {prompt_message}{prompt_suffix}")
    if default_path:
        styled_prompt.append(f" [dim_text](default: [filepath]{default_path}[/filepath])[/dim_text]")
    path = Prompt.ask(styled_prompt, default=default_path if default_path else ...)
    return os.path.abspath(path.strip().strip("'\""))
def resolve_contextual_path(parameter_value, session_ctx, is_folder_hint=False):
    if parameter_value == "__FROM_CONTEXT__":
        if is_folder_hint and session_ctx.get("last_folder_listed_path"):
            return session_ctx["last_folder_listed_path"]
        if session_ctx.get("last_referenced_file_path"): # Check this first for non-folder hints
            path_to_check = session_ctx["last_referenced_file_path"]
            return os.path.dirname(path_to_check) if (is_folder_hint and os.path.isfile(path_to_check)) else path_to_check
        if session_ctx.get("last_folder_listed_path"): # Fallback to last folder if file not specific
            return session_ctx["last_folder_listed_path"]
        return None
    return parameter_value

# --- Direct Parsers (Pre-LLM) ---
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

def parse_direct_list(user_input: str, session_ctx: dict) -> dict | None:
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

def parse_direct_summarize(user_input: str, session_ctx: dict) -> dict | None:
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

def parse_direct_organize(user_input: str, session_ctx: dict) -> dict | None:
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
        # Search from the end of the string for context keywords to avoid matching parts of filenames like "notes.txt"
        # This requires a more complex regex or iterating backwards. For simplicity, let's stick to a basic match
        # and assume that if an explicit path wasn't found, context keywords are more likely targets.
        context_matches = list(re.finditer(context_keyword_pattern, text_for_goal_processing, re.IGNORECASE))
        if context_matches:
            # Prefer last match as context is often at the end if no explicit path follows
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

    # Regex to capture "move <source_part> to <destination_part>"
    # Source and destination parts can be quoted or unquoted.
    # This regex is simplified; assumes " to " is the primary delimiter.
    # More complex scenarios might need iterative parsing or LLM.
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

# --- Central NLU Result Processing ---
def process_nlu_result(parsed_command: dict, user_input: str, session_ctx: dict, connector: OllamaConnector) -> tuple[str | None, dict, str | None]:
    action = parsed_command.get("action")
    parameters = parsed_command.get("parameters", {})
    nlu_notes = parsed_command.get("nlu_method") or parsed_command.get("nlu_correction_note")

    if not action or action == "unknown":
        llm_error = parameters.get("error", "Could not understand request.")
        return "unknown", {"original_request": user_input, "error": llm_error}, nlu_notes

    final_params = {} # Store fully resolved parameters here
    known_bad_example_paths = ["c:/reports/annual.docx"] # LLM might hallucinate these

    # Priority: Use paths from current NLU if they are explicit.
    # Fallback to context or prompt only if NLU indicates path is MISSING or FROM_CONTEXT.
    
    if action == "summarize_file":
        raw_path = parameters.get("file_path")
        # LLM hallucination check
        if raw_path and isinstance(raw_path, str) and raw_path.lower() in [p.lower() for p in known_bad_example_paths]:
            path_in_user_input_match = re.search(r"summarize\s+(['\"]?)(.+?)\1(?:$|\s)", user_input, re.IGNORECASE)
            if path_in_user_input_match:
                user_provided_path = path_in_user_input_match.group(2).strip()
                if user_provided_path.lower() != raw_path.lower(): # User input differs from LLM hallucination
                    raw_path = user_provided_path
                    nlu_notes = (nlu_notes + "; PathOverriddenFromUserInput(AntiHallucination)") if nlu_notes else "PathOverriddenFromUserInput(AntiHallucination)"
        
        resolved_path = resolve_contextual_path(raw_path, session_ctx, is_folder_hint=False)
        if not resolved_path or raw_path == "__MISSING__":
            resolved_path = get_path_from_user_input("Which file to summarize?", default_path=session_ctx.get("last_referenced_file_path"))
        final_params["file_path"] = os.path.abspath(resolved_path) if resolved_path else None
    
    elif action == "ask_question_about_file":
        raw_path = parameters.get("file_path")
        resolved_path = resolve_contextual_path(raw_path, session_ctx) # No specific folder hint, can be file or folder
        if not resolved_path or raw_path == "__MISSING__":
            default_ask_path = session_ctx.get("last_referenced_file_path") or session_ctx.get("last_folder_listed_path")
            resolved_path = get_path_from_user_input("Which file or folder are you asking about?", default_path=default_ask_path)
        final_params["file_path"] = os.path.abspath(resolved_path) if resolved_path else None
        final_params["question_text"] = parameters.get("question_text", "")
        if not final_params["question_text"] and final_params.get("file_path"): # If Q is empty but path is known
            item_name_q = os.path.basename(final_params["file_path"])
            final_params["question_text"] = Prompt.ask(f"What is your question about [filepath]{item_name_q}[/filepath]?")

    elif action == "list_folder_contents":
        raw_path = parameters.get("folder_path")
        resolved_path = resolve_contextual_path(raw_path, session_ctx, is_folder_hint=True)
        if not resolved_path or raw_path == "__MISSING__":
            default_list_path = session_ctx.get("last_folder_listed_path") or \
                                (os.path.dirname(session_ctx["last_referenced_file_path"]) if session_ctx.get("last_referenced_file_path") and os.path.isfile(session_ctx.get("last_referenced_file_path")) else None) or \
                                os.getcwd()
            resolved_path = get_path_from_user_input("Which folder to list?", default_path=default_list_path, is_folder=True)
        final_params["folder_path"] = os.path.abspath(resolved_path) if resolved_path else None

    elif action == "search_files":
        final_params["search_criteria"] = parameters.get("search_criteria")
        if not final_params["search_criteria"] or final_params["search_criteria"] == "__MISSING__":
            final_params["search_criteria"] = Prompt.ask("What are you searching for?")
        
        raw_path = parameters.get("search_path") # Path from NLU
        resolved_path = None
        if raw_path and raw_path not in ["__MISSING__", "__FROM_CONTEXT__"]: # Explicit path given by NLU
            # Normalize if it's a context-like keyword that NLU passed as explicit
            if raw_path.lower() in [".", "here", "current folder", "this folder"]: resolved_path = os.getcwd()
            else: resolved_path = os.path.abspath(raw_path)
        elif raw_path == "__FROM_CONTEXT__": # NLU says use context
            resolved_path = resolve_contextual_path(raw_path, session_ctx, is_folder_hint=True)
        
        # If, after the above, path is still not valid/resolved, then prompt
        if not resolved_path or not (isinstance(resolved_path, str) and os.path.isdir(resolved_path)):
            default_search_dir = session_ctx.get("last_folder_listed_path") or os.getcwd()
            if resolved_path and not (isinstance(resolved_path, str) and os.path.isdir(resolved_path)): # If NLU gave bad explicit path
                print_warning(f"Search path '[filepath]{resolved_path}[/filepath]' from NLU is invalid. Prompting.")
            resolved_path = get_path_from_user_input("Where should I search?", default_path=default_search_dir, is_folder=True)
        final_params["search_path"] = os.path.abspath(resolved_path) if resolved_path else None

    elif action == "move_item":
        raw_source_path = parameters.get("source_path")
        resolved_source_path = None
        if raw_source_path and raw_source_path not in ["__MISSING__", "__FROM_CONTEXT__"]:
            resolved_source_path = os.path.abspath(raw_source_path)
        elif raw_source_path == "__FROM_CONTEXT__":
            resolved_source_path = resolve_contextual_path(raw_source_path, session_ctx) # General context
        
        if not resolved_source_path: # Includes __MISSING__ or invalid context
            default_move_src = session_ctx.get("last_referenced_file_path") or session_ctx.get("last_folder_listed_path")
            resolved_source_path = get_path_from_user_input("What item to move (source)?", default_path=default_move_src)
        final_params["source_path"] = os.path.abspath(resolved_source_path) if resolved_source_path else None
        
        raw_dest_path = parameters.get("destination_path")
        resolved_dest_path = None
        if raw_dest_path and raw_dest_path not in ["__MISSING__", "__FROM_CONTEXT__"]: # NLU provided explicit dest
             resolved_dest_path = os.path.abspath(raw_dest_path)
        # Destination usually isn't __FROM_CONTEXT__ from LLM, but if it were:
        elif raw_dest_path == "__FROM_CONTEXT__":
             resolved_dest_path = resolve_contextual_path(raw_dest_path, session_ctx, is_folder_hint=True) # Assume dest context is folder

        if not resolved_dest_path: # Includes __MISSING__ or invalid context
            item_name_m = os.path.basename(final_params["source_path"]) if final_params.get("source_path") else "the item"
            default_move_dest = session_ctx.get("last_folder_listed_path") # Common to move to last viewed folder
            resolved_dest_path = get_path_from_user_input(f"Where to move '{item_name_m}' (destination)?", default_path=default_move_dest)
        final_params["destination_path"] = os.path.abspath(resolved_dest_path) if resolved_dest_path else None
        
    elif action == "propose_and_execute_organization":
        raw_path = parameters.get("target_path_or_context")
        resolved_path = None
        
        current_nlu_method = parsed_command.get("nlu_method", "")
        if current_nlu_method.startswith("llm") and raw_path and isinstance(raw_path, str) and raw_path.lower() in [p.lower() for p in known_bad_example_paths]:
            path_match_in_user_input = re.search(r"(?:organize|sort|clean\s*up)\s+(['\"]?)(.+?)\1(?:\s+by|\s+based\s+on|$)", user_input, re.IGNORECASE)
            if path_match_in_user_input:
                user_provided_path = path_match_in_user_input.group(2).strip()
                if user_provided_path and user_provided_path.lower() != raw_path.lower():
                    raw_path = user_provided_path
                    nlu_notes = (nlu_notes + "; OrgPathOverriddenFromUserInput(AntiHallucination)") if nlu_notes else "OrgPathOverriddenFromUserInput(AntiHallucination)"

        if raw_path == "__FROM_CONTEXT__":
            resolved_path = session_ctx.get("last_folder_listed_path")
            if not resolved_path or not (isinstance(resolved_path, str) and os.path.isdir(resolved_path)):
                print_warning("No valid folder context for 'organize it/this'. Please list a folder first, or specify a folder path.", "Organization Context")
                return "unknown", {"original_request": user_input, "error": "Missing folder context for organization"}, nlu_notes
        elif raw_path and raw_path != "__MISSING__":
            path_to_check_org = raw_path
            if path_to_check_org.startswith('~'): path_to_check_org = os.path.expanduser(path_to_check_org)
            resolved_path_candidate = os.path.abspath(path_to_check_org)
            if os.path.exists(resolved_path_candidate) and os.path.isdir(resolved_path_candidate):
                resolved_path = resolved_path_candidate
            else:
                print_warning(f"Organization target '[filepath]{raw_path}[/filepath]' (resolved to '[filepath]{resolved_path_candidate}[/filepath]') is invalid or not a directory. Prompting.")
                resolved_path = get_path_from_user_input("Which folder to organize?", default_path=session_ctx.get("last_folder_listed_path") or os.getcwd(), is_folder=True)
        else: 
            resolved_path = get_path_from_user_input("Which folder to organize?", default_path=session_ctx.get("last_folder_listed_path") or os.getcwd(), is_folder=True)
        
        final_params["target_path_or_context"] = os.path.abspath(resolved_path) if resolved_path else None
        final_params["organization_goal"] = parameters.get("organization_goal")
        
        if final_params.get("target_path_or_context") and os.path.isdir(final_params["target_path_or_context"]):
            org_target_display = os.path.basename(final_params["target_path_or_context"])
            org_goal_display = final_params.get("organization_goal") or "general organization"
            confirm_msg = (f"I will attempt to organize the folder "
                           f"'[filepath]{org_target_display}[/filepath]' "
                           f"based on the goal: '[highlight]{org_goal_display}[/highlight]'.\n"
                           f"Full path: [dim_text]{final_params['target_path_or_context']}[/dim_text]\n"
                           f"Is this correct?")
            if not Confirm.ask(Text.from_markup(f"{ICONS['confirm']} {confirm_msg}"), default=True):
                print_info("Organization attempt cancelled by user.")
                return "user_cancelled_organization", {"target": final_params["target_path_or_context"], "goal": final_params.get("organization_goal")}, (nlu_notes + "; UserCancelledPrePlan") if nlu_notes else "UserCancelledPrePlan"
        elif not final_params.get("target_path_or_context"):
             print_error("Organization target folder is missing. Cannot proceed.", "Organization Error")
             return "unknown", {"original_request": user_input, "error": "Missing target folder for organization after processing"}, nlu_notes

    elif action == "show_activity_log": final_params["count"] = parameters.get("count")
    elif action == "redo_activity":
        final_params["activity_identifier"] = parameters.get("activity_identifier")
        if not final_params["activity_identifier"]: final_params["activity_identifier"] = Prompt.ask("Which activity to redo ('last', index, or partial timestamp)?")
    elif action == "general_chat": final_params["original_request"] = parameters.get("original_request", user_input)
    else: final_params = parameters

    return action, final_params, nlu_notes


# --- Action Handlers ---
def handle_summarize_file(connector: OllamaConnector, parameters: dict):
    abs_filepath = parameters.get("file_path")
    if not abs_filepath or not os.path.isfile(abs_filepath):
        print_error(f"Cannot summarize: Path '[filepath]{abs_filepath}[/filepath]' is not a valid file.", "Summarize Error")
        log_action("summarize_file", parameters, "failure", f"Invalid or missing file path: {abs_filepath}")
        return
    console.print(f"{ICONS['file']} Attempting to summarize: [filepath]{abs_filepath}[/filepath]")
    update_session_context("last_referenced_file_path", abs_filepath) # Explicitly set for summarize
    content = get_file_content(abs_filepath, console)
    if content:
        if content.startswith("Error extracting text from PDF"):
            print_warning(content, "PDF Summarization Issue")
            log_action("summarize_file", parameters, "partial_success", f"PDF extraction error: {content.split(':', 1)[-1].strip()}")
            return
        summary = connector.invoke_llm_for_content("Summarize this file content comprehensively and concisely, focusing on key information and main points:", content)
        if summary.startswith("Error: LLM content generation failed"): print_error(summary, "LLM Summarization Failed")
        else: print_panel_message("LLM Summary", summary, "info", ICONS["summary"])
        log_action("summarize_file", parameters, "success", f"Summary length: {len(summary)}")
    else: log_action("summarize_file", parameters, "failure", "Could not read file")

def handle_ask_question(connector: OllamaConnector, parameters: dict):
    abs_filepath = parameters.get("file_path")
    question = parameters.get("question_text", "")
    if not abs_filepath or not os.path.exists(abs_filepath):
        print_error(f"Q&A Error: Path '[filepath]{abs_filepath}[/filepath]' does not exist.")
        log_action("ask_question", parameters, "failure", f"Path missing for Q&A: {abs_filepath}")
        return
    if not question:
        print_warning("No question for Q&A.")
        log_action("ask_question", parameters, "failure", "No question text")
        return
    item_name_display = os.path.basename(abs_filepath)
    log_action_name = "ask_question_about_folder" if os.path.isdir(abs_filepath) else "ask_question_about_file"
    if os.path.isdir(abs_filepath):
        update_session_context("last_folder_listed_path", abs_filepath) # Set for folder Q&A
        update_session_context("last_referenced_file_path", None) # Clear specific file
        console.print(f"{ICONS['folder']} Analyzing folder: [filepath]{abs_filepath}[/filepath]\n{ICONS['question']} Question: [italic white]{question}[/italic white]")
        items = list_folder_contents(abs_filepath, console) or []
        ctx = f"Folder '{item_name_display}' "
        if not items: ctx += "is empty."
        else: ctx += "contains:\n" + "\n".join([f"- {i.get('name','N/A')} ({i.get('type','N/A')})" for i in items[:15]])
        if len(items)>15: ctx+=f"\n...and {len(items)-15} more."
        eff_q = question
        if question.lower() in ["what about it?","analyze this", "tell me about it", "what do you think about it?", "your thoughts?"]:
            eff_q = f"Analyze folder '{item_name_display}'. What patterns or interesting aspects do you observe? Any organization opportunities?"
        ans = connector.invoke_llm_for_content(f"Answer based on folder info: {eff_q}", ctx)
        if ans.startswith("Error: LLM content generation failed"): print_error(ans,"LLM Folder Analysis Failed")
        else: print_panel_message("Folder Analysis",ans,"info",ICONS["answer"])
        log_action(log_action_name,parameters,"success",f"Analysis len:{len(ans)}")
    elif os.path.isfile(abs_filepath):
        update_session_context("last_referenced_file_path",abs_filepath) # Set for file Q&A
        console.print(f"{ICONS['file']} Asking about file: [filepath]{abs_filepath}[/filepath]\n{ICONS['question']} Question: [italic white]{question}[/italic white]")
        content = get_file_content(abs_filepath,console)
        if content:
            if content.startswith("Error extracting text from PDF"):
                print_warning(content, "PDF Q&A Issue")
                log_action(log_action_name, parameters, "partial_success", f"PDF extraction error: {content.split(':', 1)[-1].strip()}")
                return
            ans = connector.invoke_llm_for_content(f"Answer based on file content: {question}",content)
            if ans.startswith("Error: LLM content generation failed"): print_error(ans,"LLM Answer Failed")
            else: print_panel_message("LLM Answer",ans,"info",ICONS["answer"])
            log_action(log_action_name,parameters,"success",f"Ans len:{len(ans)}")
        else: log_action(log_action_name,parameters,"failure","Cannot read file")
    else: print_error(f"Path '[filepath]{abs_filepath}[/filepath]' is neither a file nor a directory.", "Q&A Path Error")

def handle_list_folder(parameters: dict):
    abs_folder_path = parameters.get("folder_path")
    if not abs_folder_path or not os.path.isdir(abs_folder_path):
        print_error(f"List Error: Path '[filepath]{abs_folder_path}[/filepath]' invalid.")
        log_action("list_folder_contents", parameters, "failure", "Invalid folder path for list")
        return
    console.print(f"{ICONS['folder']} Listing: [filepath]{abs_folder_path}[/filepath]")
    update_session_context("last_folder_listed_path", abs_folder_path)
    update_session_context("last_referenced_file_path", None) # Clear specific file after listing
    contents = list_folder_contents(abs_folder_path, console)
    if contents is not None:
        if not contents:
            print_info(f"Folder '[filepath]{os.path.basename(abs_folder_path)}[/filepath]' empty.","Folder Empty")
            update_session_context("last_search_results",[]) # Clear search results as well
        else:
            tbl=Table(title=f"{ICONS['folder']} Contents of {os.path.basename(abs_folder_path)} ({len(contents)})",box=ROUNDED,expand=True, header_style="table.header")
            tbl.add_column("Icon",width=4,justify="center"); tbl.add_column("Idx",width=5,justify="right"); tbl.add_column("Name",style="filepath",overflow="fold"); tbl.add_column("Type",width=10)
            for i,item in enumerate(contents): tbl.add_row(ICONS["folder"] if item['type']=="folder" else ICONS["file"],str(i+1),item['name'],item['type'])
            console.print(tbl)
            update_session_context("last_search_results",contents) # This also clears last_referenced_file_path
        log_action("list_folder_contents",parameters,"success",f"Listed {len(contents) if contents else 0}")
    else: log_action("list_folder_contents",parameters,"failure","file_utils list error")

def handle_move_item(parameters: dict):
    abs_source_path = parameters.get("source_path")
    abs_destination_path = parameters.get("destination_path")
    if not abs_source_path or not os.path.exists(abs_source_path):
        print_error(f"Move Error: Src '[filepath]{abs_source_path}[/filepath]' missing.")
        log_action("move_item", parameters, "failure", "Source missing for move")
        return
    if not abs_destination_path:
        print_error("Move Error: Dest missing.")
        log_action("move_item", parameters, "failure", "Destination missing for move")
        return
    print_panel_message("Confirm Move",f"FROM:[filepath]{abs_source_path}[/filepath]\nTO:  [filepath]{abs_destination_path}[/filepath]","warning",ICONS["confirm"])
    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Proceed?"),default=False):
        if move_item(abs_source_path,abs_destination_path,console):
            print_success(f"Moved '[filepath]{os.path.basename(abs_source_path)}[/filepath]' to '[filepath]{abs_destination_path}[/filepath]'.")
            log_action("move_item",parameters,"success")
            # Clear context after move as paths might have changed
            update_session_context("last_referenced_file_path",None)
            update_session_context("last_folder_listed_path",None)
            update_session_context("last_search_results",[])
        else: log_action("move_item",parameters,"failure","file_utils move error")
    else: print_info("Move cancelled."); log_action("move_item",parameters,"cancelled")

def handle_search_files(connector: OllamaConnector, parameters: dict):
    search_criteria = parameters.get("search_criteria")
    abs_search_path = parameters.get("search_path")
    if not search_criteria:
        print_error("Search Error: No criteria.")
        log_action("search_files", parameters, "failure", "No criteria for search")
        return
    if not abs_search_path or not os.path.isdir(abs_search_path):
        print_error(f"Search Error: Path '[filepath]{abs_search_path}[/filepath]' invalid.")
        log_action("search_files", parameters, "failure", "Invalid search path")
        return
    console.print(f"{ICONS['search']} Searching in [filepath]{abs_search_path}[/filepath] for: [highlight]'{search_criteria}'[/highlight]")
    found = search_files_recursive(abs_search_path,search_criteria,connector,console)
    if not found: print_info(f"No matches for [highlight]'{search_criteria}'[/highlight]","Search Results")
    else:
        print_success(f"Found {len(found)} matching [highlight]'{search_criteria}'[/highlight]:","Search Results")
        tbl=Table(title=f"{ICONS['search']} Results",box=ROUNDED,expand=True, header_style="table.header")
        tbl.add_column("Icon",width=4,justify="center"); tbl.add_column("Idx",width=5,justify="right"); tbl.add_column("Name",style="filepath",overflow="fold"); tbl.add_column("Path",style="dim_text",overflow="fold")
        for i,item in enumerate(found): tbl.add_row(ICONS["folder"] if item['type']=="folder" else ICONS["file"],str(i+1),item['name'],item['path'])
        console.print(tbl)
    update_session_context("last_search_results",found) # This clears last_referenced_file_path
    update_session_context("last_folder_listed_path",abs_search_path) # Set search path as last folder
    log_action("search_files",parameters,"success",f"Found {len(found)}")

def handle_general_chat(connector: OllamaConnector, parameters: dict):
    req = parameters.get("original_request","...")
    spinner=f"{ICONS['thinking']} [spinner_style]Thinking: '{req[:30]}...'[/spinner_style]"
    with Live(Spinner("bouncingBar",text=spinner),console=console,transient=True): resp = connector.invoke_llm_for_content(req)
    if resp.startswith("Error: LLM content generation failed"): print_error(resp,"LLM Chat Failed")
    else: print_panel_message("CodeX Response",resp,"info",ICONS["answer"])
    log_action("general_chat",parameters,"success",f"Resp len:{len(resp)}")

def handle_show_activity_log(parameters: dict):
    count_param = parameters.get("count"); default_log_count = MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL//2
    try:
        count = int(count_param) if count_param is not None else default_log_count
        if not (0<count<=MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL): count = default_log_count
    except (ValueError,TypeError): count = default_log_count
    activities = get_recent_activities(count)
    if not activities: print_info("Activity log empty.","Activity Log"); return
    tbl=Table(title=f"{ICONS['log']} Recent Activity (Last {len(activities)})",box=ROUNDED, header_style="table.header")
    tbl.add_column("TS",style="dim_text",width=22); tbl.add_column("Action",style="bold",width=25); tbl.add_column("Params",style="dim_text",overflow="fold",max_width=40); tbl.add_column("Status",width=12)
    for act in activities:
        ts_str = act.get('timestamp',''); ts = datetime.datetime.fromisoformat(ts_str.replace("Z","+00:00")).strftime('%y-%m-%d %H:%M:%S') if ts_str else 'N/A'
        stat=act.get('status','?'); scolor="green" if stat=="success" else "yellow" if stat in ["partial_success","cancelled","initiated","plan_proposed", "user_cancelled_organization", "python_plan_generated"] else "red"
        pdict=act.get('parameters',{}); pstr=", ".join([f"[highlight]{k}[/highlight]:'{str(v)[:20]}{'...' if len(str(v))>20 else ''}'" for k,v in pdict.items()]) or "N/A"
        tbl.add_row(ts,act.get('action','N/A'),Text.from_markup(pstr),f"[{scolor}]{stat}[/{scolor}]")
    console.print(tbl); log_action("show_activity_log",{"req_c":count_param,"disp_c":len(activities)},"success")

def handle_redo_activity(connector: OllamaConnector, parameters: dict):
    act_id = parameters.get("activity_identifier")
    if not act_id: print_warning("No activity ID for redo."); log_action("redo_activity", parameters, "failure", "No activity ID"); return
    act_to_redo = get_activity_by_partial_id_or_index(act_id, console)
    if not act_to_redo: return
    action_perform = act_to_redo.get("action"); params_use = act_to_redo.get("parameters",{})
    print_panel_message("Confirm Redo",f"Action:[highlight]{action_perform}[/highlight]\nParams:[dim_text]{json.dumps(params_use,indent=1)}[/dim_text]","warning",ICONS["redo"])
    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Confirm?"),default=True):
        console.print(f"{ICONS['execute']} Redoing: [highlight]{action_perform}[/highlight]")
        log_action("redo_activity",{**parameters,"orig_action":action_perform,"orig_params":params_use},"initiated")
        handler = action_handlers.get(action_perform)
        if handler:
            try:
                reproc_action, reproc_params, _ = process_nlu_result(
                    {"action":action_perform,"parameters":params_use},
                    f"Redoing command: {action_perform}",
                    session_context,
                    connector
                )
                if reproc_action == action_perform:
                    if action_perform in ["summarize_file","ask_question_about_file","search_files","propose_and_execute_organization","general_chat","redo_activity"]:
                        handler(connector,reproc_params)
                    else:
                        handler(reproc_params)
                elif reproc_action == "user_cancelled_organization":
                     print_info(f"Organization redo involving '{action_perform}' was pre-cancelled during parameter processing.")
                else:
                    print_error(f"Redo action '{action_perform}' changed to '{reproc_action}' during re-processing. Aborted to prevent unexpected behavior.","Redo Error")
            except Exception as e:
                print_error(f"Error redoing '{action_perform}': {e}","Redo Error")
                console.print_exception(show_locals=False, max_frames=2)
        else:
            print_error(f"Action '{action_perform}' not directly redoable or handler missing.","Redo Error")
    else:
        print_info("Redo cancelled."); log_action("redo_activity",parameters,"cancelled")

def is_path_within_base(path_to_check: str, base_path: str) -> bool:
    try:
        abs_path_to_check = os.path.abspath(path_to_check)
        abs_base_path = os.path.abspath(base_path)
        common_path = os.path.commonpath([abs_path_to_check, abs_base_path])
        return common_path == abs_base_path
    except Exception:
        return False

def handle_propose_and_execute_organization(connector: OllamaConnector, parameters: dict):
    abs_base_analysis_path = parameters.get("target_path_or_context")
    organization_goal = parameters.get("organization_goal")
    python_generated_plan_used = False

    if not abs_base_analysis_path or not os.path.isdir(abs_base_analysis_path):
        print_error(f"Org Error: Target '[filepath]{abs_base_analysis_path}[/filepath]' invalid or not a directory.")
        log_action("propose_and_execute_organization", parameters, "failure", "Invalid target for org")
        return

    src_desc=f"folder '[filepath]{os.path.basename(abs_base_analysis_path)}[/filepath]'"
    goal_display_text = organization_goal or "general organization"
    console.print(Padding(f"{ICONS['thinking']} Analyzing {src_desc} for organization plan...\nGoal: '[highlight]{goal_display_text}[/highlight]'",(1,0)))
    
    items_in_folder=list_folder_contents(abs_base_analysis_path,console) or []
    if not items_in_folder:
        print_info(f"No items in {src_desc} to organize.","Org Status")
        log_action("propose_and_execute_organization", parameters, "failure", "No items for org")
        return

    item_summary_list_for_llm = []
    for item_data in items_in_folder[:50]:
        relative_item_path = os.path.relpath(item_data['path'], abs_base_analysis_path)
        item_summary_list_for_llm.append(f"- \"{relative_item_path}\" (type: {item_data['type']})")
    
    item_summary_llm_str = "\n".join(item_summary_list_for_llm)
    if len(items_in_folder) > 50:
        item_summary_llm_str += f"\n...and {len(items_in_folder)-50} more items."

    spinner_text=f"{ICONS['thinking']} [spinner_style]LLM generating organization plan...[/spinner_style]"
    with Live(Spinner("bouncingBar",text=spinner_text),console=console,transient=True):
        plan_json_actions = connector.generate_organization_plan_llm(item_summary_llm_str, organization_goal, abs_base_analysis_path)

    if plan_json_actions is None: # LLM communication error or malformed JSON
        print_error("LLM failed to generate a plan or the plan was malformed. Please try rephrasing your goal or check Ollama logs.", "Plan Generation Failed")
        log_action("propose_and_execute_organization", parameters, "failure", "LLM plan generation failed or malformed")
        return
    
    if not isinstance(plan_json_actions, list): # LLM returned something, but not a list
        print_error(f"LLM plan was not a list as expected. Received type: {type(plan_json_actions)}. Cannot proceed.", "Plan Structure Error")
        log_action("propose_and_execute_organization", parameters, "failure", f"LLM plan not a list: {type(plan_json_actions)}")
        return

    # Python Heuristic Fallback for specific name-based goals if LLM returns empty plan
    normalized_goal_for_fallback = (organization_goal or "").lower().strip()
    name_based_heuristic_goals = ["by name", "the names", "by first letter", "alphabetical", "alphabetically by name"]
    if not plan_json_actions and normalized_goal_for_fallback in name_based_heuristic_goals:
        python_generated_plan_used = True
        print_panel_message("AI Plan Fallback", 
                            f"LLM did not propose a specific plan for goal '[highlight]{goal_display_text}[/highlight]'.\nAttempting standard first-letter organization heuristic.", 
                            "info", ICONS["info"])
        
        generated_heuristic_plan = []
        created_folders_for_heuristic_plan = set()
        for item_data in items_in_folder:
            if item_data['type'] == 'file': # Typically only organize files this way
                item_name = item_data['name']
                first_char = item_name[0].upper() if item_name else "_"
                
                subfolder_name = ""
                if first_char.isdigit(): subfolder_name = "0-9_files"
                elif first_char.isalpha(): subfolder_name = f"{first_char}_files"
                else: subfolder_name = "Symbols_files"
                
                abs_subfolder_path = os.path.join(abs_base_analysis_path, subfolder_name)
                
                if abs_subfolder_path not in created_folders_for_heuristic_plan:
                    generated_heuristic_plan.append({"action_type": "CREATE_FOLDER", "path": abs_subfolder_path})
                    created_folders_for_heuristic_plan.add(abs_subfolder_path)
                
                source_path = item_data['path']
                destination_path = os.path.join(abs_subfolder_path, item_name)
                if source_path != destination_path : # Don't move if already in place
                    generated_heuristic_plan.append({"action_type": "MOVE_ITEM", "source": source_path, "destination": destination_path})
        plan_json_actions = generated_heuristic_plan
        log_action("propose_and_execute_organization", {**parameters, "fallback_heuristic_used": True}, "python_plan_generated", f"Python generated {len(plan_json_actions)} actions for '{normalized_goal_for_fallback}'")


    if not plan_json_actions: # Still empty after potential fallback
        empty_plan_message = (
            f"The AI analyzed the folder for the goal '[highlight]{goal_display_text}[/highlight]' "
            f"but did not propose any specific actions.\nThis might be because:\n"
            f"  - The items are already organized according to this goal.\n"
            f"  - The goal was too ambiguous for the AI/heuristic to form a clear plan.\n"
            f"  - There were too few items to apply the chosen organization strategy effectively.\n"
            f"  - The AI determined no changes were beneficial based on its 'be conservative' rule."
        )
        print_info(empty_plan_message, "No Actions Proposed")
        log_action("propose_and_execute_organization", parameters, "success", "No actions proposed (LLM or heuristic)")
        return

    plan_title = f"{ICONS['plan']} Proposed Organization Plan"
    if python_generated_plan_used:
        plan_title += " (Standard Heuristic)"

    tbl=Table(title=plan_title, box=ROUNDED, header_style="table.header", show_lines=True)
    tbl.add_column("Icon",width=4,justify="center"); tbl.add_column("Step",justify="right",width=5); tbl.add_column("Action",width=15); tbl.add_column("Details",overflow="fold"); tbl.add_column("Status", width=15)
    
    valid_actions_to_execute=[]; invalid_actions_found=False
    
    for i, action_data in enumerate(plan_json_actions):
        action_type = action_data.get("action_type")
        details_str = ""; is_action_valid = True; action_status_msg="[green]Valid[/green]"; icon="❓"

        if not isinstance(action_data, dict):
            details_str=f"[danger]Invalid action format (not a dict)[/danger]"; is_action_valid=False; action_status_msg="[danger]Invalid Format[/danger]"
        elif action_type == "CREATE_FOLDER":
            icon=ICONS["create_folder"]
            folder_path = action_data.get("path")
            if not (folder_path and isinstance(folder_path, str) and os.path.isabs(folder_path)):
                details_str=f"Path: [danger]{folder_path or 'MISSING'}[/] (Must be absolute)"; is_action_valid=False; action_status_msg="[danger]Invalid Path[/danger]"
            elif not is_path_within_base(folder_path, abs_base_analysis_path):
                details_str=f"Path: [filepath]{folder_path}[/] [danger](Outside target folder scope)[/danger]"; is_action_valid=False; action_status_msg="[danger]Out of Scope[/danger]"
            else: details_str=f"Path: [filepath]{folder_path}[/filepath]"
        elif action_type == "MOVE_ITEM":
            icon=ICONS["move"]
            source_path = action_data.get("source")
            destination_path = action_data.get("destination")
            
            if not (source_path and isinstance(source_path, str) and os.path.isabs(source_path) and \
                    destination_path and isinstance(destination_path, str) and os.path.isabs(destination_path)):
                details_str=f"Source: [danger]{source_path or 'MISSING'}[/]\nDest:   [danger]{destination_path or 'MISSING'}[/] (Must be absolute)"; is_action_valid=False; action_status_msg="[danger]Invalid Paths[/danger]"
            elif source_path == destination_path: # Item already in place
                details_str=f"From: [filepath]{source_path}[/filepath]\nTo:   [filepath]{destination_path}[/] ([dim_text]Item already in place[/dim_text])"; is_action_valid=False; action_status_msg="[dim_text]No Change[/dim_text]" # Treat as invalid for execution list but not an error
            elif not is_path_within_base(source_path, abs_base_analysis_path) or \
                 not is_path_within_base(destination_path, abs_base_analysis_path):
                s_scope = "[green]OK[/green]" if is_path_within_base(source_path, abs_base_analysis_path) else "[danger]OUT[/danger]"
                d_scope = "[green]OK[/green]" if is_path_within_base(destination_path, abs_base_analysis_path) else "[danger]OUT[/danger]"
                details_str=f"Source ({s_scope}): [filepath]{source_path}[/]\nDest   ({d_scope}): [filepath]{destination_path}[/] [danger](Path(s) out of scope)[/danger]"; is_action_valid=False; action_status_msg="[danger]Out of Scope[/danger]"
            elif not os.path.exists(source_path):
                 details_str=f"Source: [filepath]{source_path}[/] [warning](Does not exist)[/warning]"; is_action_valid=False; action_status_msg="[warning]Src Missing[/warning]"
            else: details_str=f"From: [filepath]{source_path}[/filepath]\nTo:   [filepath]{destination_path}[/filepath]"
        else:
            details_str=f"[danger]Unknown action type: {action_type}[/danger]"; is_action_valid=False; action_status_msg="[danger]Unknown Act[/danger]"
        
        tbl.add_row(icon,str(i+1),action_type if is_action_valid else f"[strike]{action_type}[/strike]",Text.from_markup(details_str), Text.from_markup(action_status_msg))
        if is_action_valid:
            valid_actions_to_execute.append(action_data)
        else:
            if action_status_msg not in ["[dim_text]No Change[/dim_text]"]: # Don't count "No Change" as an invalid action for the warning message
                invalid_actions_found=True
            
    console.print(tbl)

    if invalid_actions_found:
        print_warning("The proposed plan contains invalid or unsafe actions (struck out and marked above). Only valid actions will be considered for execution.","Plan Validation Issues")
    
    if not valid_actions_to_execute:
        print_info("No valid actions remaining in the plan after validation. Nothing to execute.","Plan Empty Post-Validation")
        log_action("propose_and_execute_organization", {**parameters,"initial_plan_c":len(plan_json_actions),"valid_c":0, "python_generated": python_generated_plan_used}, "failure", "No valid actions post-validation")
        return

    log_action("propose_and_execute_organization",{**parameters,"initial_plan_c":len(plan_json_actions),"valid_c":len(valid_actions_to_execute), "python_generated": python_generated_plan_used},"plan_proposed")
    
    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Execute the {len(valid_actions_to_execute)} valid action(s) listed above?"),default=False):
        console.print(Padding(f"{ICONS['execute']} [bold]Executing validated plan...[/bold]",(1,0)))
        success_count, fail_count = 0, 0
        
        with Progress(console=console,expand=True) as prog_bar:
            exec_task = prog_bar.add_task(f"{ICONS['execute']} [spinner_style]Processing...[/spinner_style]",total=len(valid_actions_to_execute))
            for idx, exec_action_data in enumerate(valid_actions_to_execute):
                action_type_exec = exec_action_data["action_type"]
                prog_bar.update(exec_task,description=f"{ICONS['execute']} [spinner_style]Step {idx+1}: {action_type_exec}...[/spinner_style]")
                
                op_successful, log_status, message_detail = False, "failure", ""

                if action_type_exec=="CREATE_FOLDER":
                    path_to_create = exec_action_data["path"]
                    try:
                        if os.path.exists(path_to_create) and os.path.isdir(path_to_create):
                            message_detail=f"  {ICONS['info']} [dim_text]Folder '{os.path.basename(path_to_create)}' already exists. Skipped.[/dim_text]"; op_successful, log_status = True, "skipped"
                        else:
                            os.makedirs(path_to_create,exist_ok=True)
                            message_detail=f"  {ICONS['success']} [green]Created folder:[/] [filepath]{os.path.basename(path_to_create)}[/filepath]"; op_successful, log_status = True, "success"
                    except Exception as e:
                        message_detail=f"  {ICONS['error']} [danger]FAIL CREATE FOLDER '{os.path.basename(path_to_create)}': {e}[/danger]"
                
                elif action_type_exec=="MOVE_ITEM":
                    source_item_path = exec_action_data["source"]
                    destination_item_path = exec_action_data["destination"]
                    if not os.path.exists(source_item_path):
                        message_detail=f"  {ICONS['warning']} [warning]Source '{os.path.basename(source_item_path)}' disappeared before move. Skipped.[/warning]"; log_status="skipped"
                    elif move_item(source_item_path,destination_item_path,console):
                        dest_display_path = os.path.relpath(destination_item_path, os.path.dirname(source_item_path)) if destination_item_path.startswith(os.path.dirname(source_item_path)) else os.path.basename(destination_item_path)
                        message_detail=f"  {ICONS['success']} [green]Moved:[/] [filepath]{os.path.basename(source_item_path)}[/filepath] -> [filepath]{dest_display_path}[/filepath]"; op_successful, log_status = True, "success"
                    else:
                        message_detail=f"  {ICONS['error']} [danger]FAIL MOVE '{os.path.basename(source_item_path)}' (see details above).[/danger]"
                
                console.print(Text.from_markup(message_detail))
                if op_successful: success_count +=1
                else: fail_count +=1
                
                log_action(f"exec_org_{action_type_exec.lower()}",{**exec_action_data,"base_path":abs_base_analysis_path},log_status,message_detail.split(":",1)[-1].strip() if ":" in message_detail else message_detail.strip())
                prog_bar.update(exec_task,advance=1)
            
            prog_bar.update(exec_task,description=f"{ICONS['success']} [green]Execution complete.[/green]")
        
        print_success(f"Organization plan execution finished. Successful: {success_count}, Failed/Skipped: {fail_count}","Organization Summary")
        update_session_context("last_referenced_file_path",None)
        update_session_context("last_folder_listed_path",None)
        update_session_context("last_search_results",[])
        log_action("execute_organization_plan",{**parameters,"executed_c":len(valid_actions_to_execute),"ok_c":success_count,"fail_c":fail_count, "python_generated": python_generated_plan_used},"completed")
    else:
        print_info("Organization plan execution cancelled by user.");
        log_action("execute_organization_plan",{**parameters,"valid_c":len(valid_actions_to_execute), "python_generated": python_generated_plan_used},"cancelled")


action_handlers = {
    "summarize_file": handle_summarize_file,
    "ask_question_about_file": handle_ask_question,
    "list_folder_contents": handle_list_folder,
    "move_item": handle_move_item,
    "search_files": handle_search_files,
    "propose_and_execute_organization": handle_propose_and_execute_organization,
    "show_activity_log": handle_show_activity_log,
    "redo_activity": handle_redo_activity,
    "general_chat": handle_general_chat
}

def resolve_indexed_reference(user_input_lower: str, parameters: dict, session_ctx: dict):
    # If paths are already explicitly set by NLU for the current command, don't override with index.
    # This check is a bit broad; ideally, we'd know if the NLU *intended* for this specific action
    # to use an indexed reference vs. it just being a number in the query.
    # For now, if any primary path parameter is set by NLU, assume NLU has handled it.
    if parameters.get("file_path") or \
       parameters.get("folder_path") or \
       parameters.get("target_path_or_context") or \
       parameters.get("source_path"): # For move
        # Check if the value is NOT a placeholder that would trigger index resolution
        # e.g. if file_path = "/explicit/path.txt", don't try to resolve index.
        # If file_path = "__MISSING__", then index resolution might be valid.
        # This logic is getting complex. Let's simplify: if a path param is present and not a "magic string", assume it's explicit.
        
        path_keys_to_check = ["file_path", "folder_path", "target_path_or_context", "source_path"]
        is_explicit_path_present = False
        for pk in path_keys_to_check:
            val = parameters.get(pk)
            if val and val not in ["__MISSING__", "__FROM_CONTEXT__"]:
                is_explicit_path_present = True
                break
        
        if is_explicit_path_present and not re.fullmatch(r"(?:item\s*|number\s*|file\s*|#\s*)?(\d+)(?:st|nd|rd|th)?(?:\s*one)?", user_input_lower.strip()):
             return False # Explicit path from NLU takes precedence over trying to parse an index from a general query.

    match = re.search(r"(?:item\s*|number\s*|file\s*|#\s*)?(\d+)(?:st|nd|rd|th)?(?:\s*one)?", user_input_lower)
    if match and session_ctx.get("last_search_results"):
        try:
            idx = int(match.group(1)) - 1
            # More robust check: is the *entire user input* essentially just this index reference?
            # Or is the index reference a clear, standalone part of the command?
            # E.g., "summarize item 1" vs "tell me about item 1 in the list of 100 items"
            # Simple check for now:
            is_likely_direct_index_ref = (user_input_lower.strip() == match.group(0).strip()) or \
                                         (parameters.get("action") in ["summarize_file", "list_folder_contents", "ask_question_about_file"] and # Actions that commonly use index
                                          (match.group(0).strip() in user_input_lower)) # and the index is part of the input

            if is_likely_direct_index_ref and 0 <= idx < len(session_ctx["last_search_results"]):
                item = session_ctx["last_search_results"][idx]
                current_llm_action = parameters.get("action","")
                
                # Clear any prior path parameters from NLU if we are now resolving by index
                for p_key in ["file_path", "folder_path", "target_path_or_context", "source_path", "destination_path"]:
                    if p_key in parameters:
                        del parameters[p_key]

                if item["type"] == "file":
                    parameters["file_path"] = item["path"]
                    # Determine action based on keywords or default to summarize
                    ask = ("ask" in current_llm_action.lower() or any(k in user_input_lower for k in ["ask ","tell me","what is","explain","question"]))
                    summ = ("summarize" in current_llm_action.lower() or "summarize" in user_input_lower)
                    
                    if ask:
                        parameters["action"]="ask_question_about_file"
                        # Try to extract question part, removing the index reference and action verb
                        q_part = user_input_lower.replace(match.group(0).strip(),"",1)
                        for verb in ["ask","tell me","what is","explain","question about", "summarize", "summary of", "list"]: # also remove summarize if it was there
                             q_part = re.sub(r'\b'+re.escape(verb)+r'\b','',q_part,flags=re.I).strip()
                        parameters["question_text"]= q_part if q_part else f"Tell me more about {os.path.basename(item['name'])}"
                    elif summ or not current_llm_action or current_llm_action=="unknown":
                        parameters["action"]="summarize_file"
                
                elif item["type"] == "folder":
                    parameters["folder_path"]=item["path"]
                    org = ("organize" in current_llm_action.lower() or "organize" in user_input_lower or "sort" in user_input_lower)
                    list_cmd = ("list" in current_llm_action.lower() or "ls" in user_input_lower or "contents" in user_input_lower)

                    if org:
                        parameters["action"]="propose_and_execute_organization"
                        parameters["target_path_or_context"]=item["path"]
                        # Extract goal if present
                        g_part_text = user_input_lower.replace(match.group(0).strip(),"",1)
                        for verb in ["organize","sort","list","ls"]: g_part_text = re.sub(r'\b'+re.escape(verb)+r'\b','',g_part_text,flags=re.I).strip()
                        g_part_match = re.search(r"(?:by|based\s+on)\s+(['\"]?)(.+?)\1?$", g_part_text, re.IGNORECASE)
                        if g_part_match:
                             parameters["organization_goal"] = g_part_match.group(2).strip().rstrip("'\" ")
                        elif parameters.get("organization_goal"): pass # Keep if NLU already had one
                        else: parameters["organization_goal"] = None
                    elif list_cmd or not current_llm_action or current_llm_action=="unknown":
                        parameters["action"]="list_folder_contents"
                return True
        except (ValueError,TypeError,AttributeError):
            pass
    return False

# --- Main Application Logic ---
def print_startup_message(connector):
    console.clear(); time.sleep(0.1)
    with Live(Spinner("dots", text=f"{ICONS['thinking']} [spinner_style]Initializing CodeX Assistant...[/spinner_style]"), console=console, transient=True, refresh_per_second=10):
        time.sleep(0.5)
    console.print(Align.center(APP_LOGO_TEXT))
    status_items = []
    conn_ok, model_ok, _ = connector.check_connection_and_model()
    if not conn_ok:
        print_error("Ollama connection failed. Ensure Ollama is running.", "Ollama Error")
        return False
    status_items.append(f"{ICONS['success']} Connected to Ollama ([highlight]{connector.base_url}[/highlight])")
    if not model_ok:
        print_error(f"LLM '[highlight]{OLLAMA_MODEL}[/highlight]' not found. Check `config.py` or pull model with `ollama pull {OLLAMA_MODEL}`.", "Model Error")
        return False
    status_items.append(f"{ICONS['success']} Using LLM: [highlight]{OLLAMA_MODEL}[/highlight]")
    console.print(Panel(Text.from_markup("\n".join(status_items)), title=f"{ICONS['info']} System Status", border_style="panel.border.info", box=ROUNDED, padding=(1,2)))
    console.print(Padding(Text.from_markup(f"\n{ICONS['info']} Type [prompt]help[/prompt] for commands, or [prompt]quit[/prompt] to exit."), (1,0)))
    return True

def main():
    load_session_context()
    connector = OllamaConnector()
    if not print_startup_message(connector):
        save_session_context()
        return

    try:
        while True:
            console.print(Rule(style="separator_style"))
            user_input_original = Prompt.ask(Text.from_markup("[prompt]You[/prompt]"), default="").strip()
            if not user_input_original:
                continue
            if user_input_original.lower() in ['quit','exit','bye','q']:
                console.print(f"{ICONS['app_icon']} [bold app_logo_style]Exiting...[/bold app_logo_style]")
                break
            if user_input_original.lower() == 'help':
                console.print(Panel(Markdown(f"""# CodeX AI Assistant Help {ICONS['info']}\n\n## Example Commands:\n*   `summarize "path/to/file.txt"` or `summarize "path/to/mydoc.pdf"`\n*   `what is in "doc.docx" about project alpha?`\n*   `list contents of "C:/folder"` OR `list item 3` (after search)\n*   `search for images in .`\n*   `search python scripts containing 'db_utils' in "~/projects"`\n*   `search images "C:/Users/Name/Pictures"`\n*   `move "old.txt" to "archive/"` or `move item 1 to "new_folder/"`\n*   `organize this folder by type` (after list/search)\n*   `organize "C:/Downloads" by file extension` or `organize "folder" by name`\n*   `show my last 5 activities` / `view log history`\n*   `redo last search` / `redo task 2`\n\n## Notes:\n*   Use quotes for paths with spaces.\n*   Context is remembered (e.g., `summarize item 1` after a search).\n*   File organization is experimental; always review plans before execution."""),title=f"{ICONS['info']} Help",border_style="panel.border.info",box=ROUNDED,padding=1))
                continue

            parsed_cmd=None; action=None; params={}; nlu_notes=None;
            nlu_method="llm_fallback" # Default if no direct parser matches or if direct fails
            
            direct_parsers_map = {
                "search": (parse_direct_search, False),
                "list": (parse_direct_list, True),
                "activity": (parse_direct_activity_log, False),
                "summarize": (parse_direct_summarize, True),
                "organize": (parse_direct_organize, True),
                "move": (parse_direct_move, False) # Added move parser
            }
            
            user_input_first_word = user_input_original.lower().split(" ")[0] if user_input_original else ""
            found_direct_parser = False
            
            # Attempt direct parsing if keywords match
            # This logic allows multiple parsers to be relevant (e.g. "show" for list or activity)
            # The first parser that returns a non-None result for a relevant keyword wins.
            relevant_parser_key = None
            if user_input_first_word in ["search", "find"]: relevant_parser_key = "search"
            elif user_input_first_word in ["list", "ls"] or \
                 "contents of" in user_input_original.lower() or \
                 "files in" in user_input_original.lower(): relevant_parser_key = "list"
            elif user_input_first_word in ["show", "view"] and \
                 any(k in user_input_original.lower() for k in ["activity", "log", "history"]): relevant_parser_key = "activity"
            elif user_input_first_word == "summarize": relevant_parser_key = "summarize"
            elif user_input_first_word in ["organize", "organise", "sort", "cleanup"] or \
                 "clean up" in user_input_original.lower(): relevant_parser_key = "organize"
            elif user_input_first_word == "move": relevant_parser_key = "move"

            if relevant_parser_key:
                parser_func, needs_ctx = direct_parsers_map[relevant_parser_key]
                if needs_ctx:
                    parsed_cmd = parser_func(user_input_original, session_context)
                else:
                    parsed_cmd = parser_func(user_input_original)
                
                if parsed_cmd:
                    nlu_method = parsed_cmd.pop("nlu_method","direct_unknown")
                    found_direct_parser = True
            
            # If no direct parser matched or a relevant one returned None, fallback to LLM
            if not found_direct_parser:
                spinner = f"{ICONS['thinking']} [spinner_style]Understanding: '{user_input_original[:35]}...'[/spinner_style]"
                with Live(Spinner("dots",text=spinner),console=console,transient=True):
                    parsed_cmd=connector.get_intent_and_entities(user_input_original,session_context)
                # If LLM parsing, nlu_method will be part of parsed_cmd or default to llm_fallback
                if parsed_cmd and parsed_cmd.get("nlu_method"):
                     nlu_method = parsed_cmd.pop("nlu_method") # Use LLM's own note if present
                elif parsed_cmd and parsed_cmd.get("nlu_correction_note"): # If LLM had correction
                    nlu_method = "llm_corrected"

            if parsed_cmd and "action" in parsed_cmd:
                current_nlu_note_from_parser = nlu_method # This is now set correctly from direct or LLM
                llm_correction_note = parsed_cmd.get("nlu_correction_note") # This is specifically from LLM internal corrections
                
                if llm_correction_note and not nlu_method.startswith("llm_corrected"): # Avoid double noting
                    nlu_notes = f"{current_nlu_note_from_parser}; {llm_correction_note}"
                else:
                    nlu_notes = current_nlu_note_from_parser

                action, params, final_proc_notes = process_nlu_result(
                    parsed_cmd, user_input_original, session_context, connector
                )
                if final_proc_notes:
                    nlu_notes = (nlu_notes + "; " + final_proc_notes) if nlu_notes else final_proc_notes
            else:
                action="unknown"
                params={"original_request":user_input_original,"error":"NLU failure (direct & LLM)"}
                nlu_notes="NLU_failed_all"
            
            if not action:
                print_error("No action determined after NLU processing.","Critical NLU Error")
                log_action("nlu_critical_failure",{"input":user_input_original},"failure")
                continue
            
            if action == "user_cancelled_organization":
                continue

            # Resolve indexed references AFTER primary NLU and path processing,
            # as index usually modifies/clarifies an already understood action.
            if resolve_indexed_reference(user_input_original.lower(), params, session_context):
                action=params.get("action",action) # Action might change due to index (e.g. list folder -> summarize file)
                nlu_notes = (nlu_notes + "; IdxRefResolved") if nlu_notes else "IdxRefResolved"

            add_to_command_history(action, params, nlu_notes)
            handler = action_handlers.get(action)
            if handler:
                if action in ["summarize_file","ask_question_about_file","search_files","propose_and_execute_organization","general_chat","redo_activity"]:
                    handler(connector,params)
                else:
                    handler(params)
            elif action=="unknown":
                err_detail = params.get('error','Unrecognized command or parameters.')
                if "Ollama" in err_detail or "LLM" in err_detail:
                    print_error(f"Could not understand your request due to an issue with the AI model.\nDetails: {err_detail}\nPlease try again or rephrase.","AI Model Error")
                else:
                    print_warning(f"Cannot handle: '{params.get('original_request',user_input_original)}'.\nDetails: {err_detail}\nTry 'help'.","Unknown Command")
                log_action("unknown_command", params, "failure", err_detail)
            else:
                print_warning(f"Action '[highlight]{action}[/highlight]' is recognized but not fully implemented.","Not Implemented")
                log_action("not_implemented", {"action": action, "input": user_input_original, "parsed_params": params}, "pending")

    except KeyboardInterrupt:
        console.print(f"\n{ICONS['app_icon']} [bold app_logo_style]Exiting...[/bold app_logo_style]")
    except Exception:
        print_error("A critical error occurred in the main application loop!","Critical Error")
        console.print_exception(show_locals=True)
    finally:
        save_session_context()

if __name__ == '__main__':
    main()
