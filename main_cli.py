
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
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "thinking": "🧠",
    "plan": "📝",
    "execute": "🚀",
    "folder": "📁",
    "file": "📄",
    "search": "🔍",
    "question": "❓",
    "answer": "💡",
    "summary": "📋",
    "log": "📜",
    "redo": "🔄",
    "confirm": "🤔",
    "move": "📦",
    "create_folder": "➕📁",
    "app_icon": "🗂️"
}

CUSTOM_THEME = Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "danger": "bold red",
    "success": "green",
    "prompt": "bold #32CD32", # LimeGreen
    "user_input_display": "italic #F0E68C", 
    "filepath": "cyan",
    "highlight": "bold magenta",
    "panel.title": "bold white on #007ACC",
    "panel.border": "#007ACC", # Main panel color
    "panel.title.success": "bold white on green",
    "panel.border.success": "green",
    "panel.title.error": "bold white on red",
    "panel.border.error": "red",
    "panel.title.warning": "bold black on yellow",
    "panel.border.warning": "yellow",
    "panel.title.info": "bold white on #4682B4", # SteelBlue for info
    "panel.border.info": "#4682B4",
    "table.header": "bold #007ACC",
    "table.cell": "default", 
    "spinner_style": "bold #FF69B4", # HotPink spinner
    "progress.bar": "#4169E1", 
    "progress.percentage": "cyan",
    "app_logo_style": "bold #007ACC",
    "separator_style": "dim #007ACC",
    "dim_text": "dim default"
})

APP_LOGO_TEXT = f"""
{ICONS['app_icon']} [app_logo_style]
 ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
        AI File Assistant v1.1[/app_logo_style]
"""

console = Console(theme=CUSTOM_THEME)

SESSION_CONTEXT_FILE = "session_context.json"
MAX_COMMAND_HISTORY = 20

session_context = {
    "last_referenced_file_path": None,
    "last_folder_listed_path": None,
    "last_search_results": [], 
    "command_history": [], 
}

def print_panel_message(title: str, message: str, panel_style_name: str, icon: str = "", box_style=ROUNDED):
    panel_title_style = f"panel.title.{panel_style_name}" if f"panel.title.{panel_style_name}" in CUSTOM_THEME.styles else "panel.title"
    panel_border_style = f"panel.border.{panel_style_name}" if f"panel.border.{panel_style_name}" in CUSTOM_THEME.styles else "panel.border"
    
    panel_title_text = f"{icon} {title}" if icon else title
    console.print(Panel(Text(message, justify="left"),
                        title=f"[{panel_title_style}]{panel_title_text}[/]",
                        border_style=panel_border_style,
                        box=box_style,
                        padding=(1, 2)))

def print_success(message: str, title: str = "Success"):
    print_panel_message(title, message, "success", ICONS["success"])

def print_error(message: str, title: str = "Error"):
    print_panel_message(title, message, "error", ICONS["error"])

def print_warning(message: str, title: str = "Warning"):
    print_panel_message(title, message, "warning", ICONS["warning"])

def print_info(message: str, title: str = "Information"):
    print_panel_message(title, message, "info", ICONS["info"])

def load_session_context():
    global session_context
    if os.path.exists(SESSION_CONTEXT_FILE):
        try:
            with open(SESSION_CONTEXT_FILE, "r", encoding="utf-8") as f:
                loaded_ctx = json.load(f)
                session_context.update(loaded_ctx)
                session_context.setdefault("last_referenced_file_path", None)
                session_context.setdefault("last_folder_listed_path", None)
                session_context.setdefault("last_search_results", [])
                session_context.setdefault("command_history", [])
                console.print(f"[dim_text]{ICONS['info']} Session context loaded from {SESSION_CONTEXT_FILE}[/dim_text]")
        except (json.JSONDecodeError, IOError) as e:
            print_warning(f"Could not load session context: {e}. Starting fresh.", "Session Warning")
            session_context = {
                "last_referenced_file_path": None, "last_folder_listed_path": None,
                "last_search_results": [], "command_history": []
            }

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
    if key == "last_search_results" and value is not None:
        session_context["last_referenced_file_path"] = None
    elif key == "last_referenced_file_path" and value:
        session_context["last_folder_listed_path"] = os.path.dirname(value) if os.path.isfile(value) else None
    elif key == "last_folder_listed_path" and value:
        session_context["last_referenced_file_path"] = None

def add_to_command_history(action: str, parameters: dict, nlu_notes: str = None):
    global session_context
    if "command_history" not in session_context or not isinstance(session_context["command_history"], list):
        session_context["command_history"] = []
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "parameters": parameters if parameters else {}
    }
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

def resolve_contextual_path(parameter_value, is_folder_hint=False):
    if parameter_value == "__FROM_CONTEXT__":
        if is_folder_hint and session_context.get("last_folder_listed_path"):
            return session_context["last_folder_listed_path"]
        if session_context.get("last_referenced_file_path"):
            path_to_check = session_context["last_referenced_file_path"]
            return os.path.dirname(path_to_check) if (is_folder_hint and os.path.isfile(path_to_check)) else path_to_check
        if session_context.get("last_folder_listed_path"):
             return session_context["last_folder_listed_path"]
    return None

def handle_summarize_file(connector: OllamaConnector, parameters: dict):
    filepath_param = parameters.get("file_path")
    filepath = resolve_contextual_path(filepath_param)
    
    if not filepath or filepath_param == "__MISSING__":
        filepath = get_path_from_user_input("Which file to summarize?", default_path=session_context.get("last_referenced_file_path"))
    
    abs_filepath = os.path.abspath(filepath)
    if not os.path.isfile(abs_filepath):
        print_error(f"Path '{abs_filepath}' is not a valid file.")
        log_action("summarize_file", {"file_path": filepath, **parameters}, "failure", f"Invalid file path: {abs_filepath}")
        return

    console.print(f"{ICONS['file']} Attempting to summarize: [filepath]{abs_filepath}[/filepath]")
    update_session_context("last_referenced_file_path", abs_filepath)
    
    content = get_file_content(abs_filepath, console)
    if content:
        if "PDF parsing not yet fully implemented" in content:
            print_warning(content, "PDF Parsing Status")
            log_action("summarize_file", {"file_path": abs_filepath, **parameters}, "partial_success", "PDF not fully parsed")
            return
            
        llm_prompt = "Summarize the following text comprehensively and concisely, focusing on key information and main points:"
        summary = ""
        spinner_text = f"{ICONS['thinking']} [spinner_style]Asking LLM for summarization of '{os.path.basename(abs_filepath)}'[/spinner_style]"
        with Live(Spinner("bouncingBar", text=spinner_text), console=console, refresh_per_second=10, transient=True):
            summary = connector.invoke_llm_for_content(main_instruction=llm_prompt, context_text=content)
        
        if "Error: LLM content generation failed." in summary:
            print_error(summary, "LLM Summarization Failed")
        else:
            print_panel_message("LLM Summary", summary, "info", ICONS["summary"])
        log_action("summarize_file", {"file_path": abs_filepath, **parameters}, "success", f"Summary generated (length: {len(summary)})")
    else:
        log_action("summarize_file", {"file_path": abs_filepath, **parameters}, "failure", "Could not read file content (get_file_content likely printed error)")

def handle_ask_question(connector: OllamaConnector, parameters: dict):
    filepath_param = parameters.get("file_path")
    question = parameters.get("question_text", "")
    filepath = resolve_contextual_path(filepath_param)

    if not filepath or filepath_param == "__MISSING__":
        default_path = session_context.get("last_folder_listed_path") or session_context.get("last_referenced_file_path")
        filepath = get_path_from_user_input("Which file or folder are you asking about?", default_path=default_path)
    
    abs_filepath = os.path.abspath(filepath)
    
    if os.path.isdir(abs_filepath):
        update_session_context("last_folder_listed_path", abs_filepath)
        item_name_display = os.path.basename(abs_filepath)
        
        if not question:
            question = Prompt.ask(Text.from_markup(f"{ICONS['question']} What would you like to know about folder [filepath]{item_name_display}[/filepath]?")).strip()
        if not question:
            print_warning("No question provided for folder analysis.")
            log_action("ask_question_about_folder", {"folder_path": abs_filepath, **parameters}, "failure", "No question")
            return

        console.print(f"{ICONS['folder']} Analyzing folder: [filepath]{abs_filepath}[/filepath]")
        console.print(f"{ICONS['question']} Question: [italic white]{question}[/italic white]")

        items_for_analysis = list_folder_contents(abs_filepath, console) or []
        
        context_for_llm = f"The folder '{item_name_display}' "
        if not items_for_analysis:
            context_for_llm += "is empty."
        else:
            context_for_llm += "contains the following items (name, type):\n"
            for item in items_for_analysis[:15]:
                context_for_llm += f"- {item.get('name', 'N/A')} ({item.get('type', 'N/A')})\n"
            if len(items_for_analysis) > 15:
                context_for_llm += f"...and {len(items_for_analysis) - 15} more items.\n"

        effective_question = question
        if question.lower() in ["what do you think about it?", "tell me about it", "analyze this", "what do you see?", "your thoughts?"]:
            effective_question = f"Analyze the contents and structure of the folder '{item_name_display}'. What patterns or interesting aspects do you observe? Are there opportunities for better organization?"

        llm_prompt = f"Based on the provided folder contents, answer the following question: {effective_question}"
        answer = ""
        spinner_text = f"{ICONS['thinking']} [spinner_style]Analyzing folder structure for '{item_name_display}'[/spinner_style]"
        with Live(Spinner("bouncingBar", text=spinner_text), console=console, transient=True):
            answer = connector.invoke_llm_for_content(main_instruction=llm_prompt, context_text=context_for_llm)
        
        if "Error: LLM content generation failed." in answer:
            print_error(answer, "LLM Folder Analysis Failed")
        else:
            print_panel_message("Folder Analysis", answer, "info", ICONS["answer"])
        log_action("ask_question_about_folder", {"folder_path": abs_filepath, "question_text": question, **parameters}, "success", f"Analysis length: {len(answer)}")
        return

    if not os.path.isfile(abs_filepath):
        print_error(f"Path '{abs_filepath}' is not a valid file or folder.")
        log_action("ask_question_about_file", {"file_path": filepath, **parameters}, "failure", f"Invalid path: {abs_filepath}")
        return

    update_session_context("last_referenced_file_path", abs_filepath)
    item_name_display = os.path.basename(abs_filepath)

    if not question:
        question = Prompt.ask(Text.from_markup(f"{ICONS['question']} What is your question about [filepath]{item_name_display}[/filepath]?")).strip()
    if not question:
        print_warning("No question provided for file.")
        log_action("ask_question_about_file", {"file_path": abs_filepath, **parameters}, "failure", "No question")
        return

    console.print(f"{ICONS['file']} Asking about file: [filepath]{abs_filepath}[/filepath]")
    console.print(f"{ICONS['question']} Question: [italic white]{question}[/italic white]")
    
    content = get_file_content(abs_filepath, console)
    if content:
        if "PDF parsing not yet fully implemented" in content:
            print_warning(content, "PDF Parsing Status")
            log_action("ask_question_about_file", {"file_path": abs_filepath, **parameters}, "partial_success", "PDF not parsed")
            return
        
        llm_prompt = f"Based on the provided file content, answer the following question: {question}"
        answer = ""
        spinner_text = f"{ICONS['thinking']} [spinner_style]Consulting LLM for answer about '{item_name_display}'[/spinner_style]"
        with Live(Spinner("bouncingBar", text=spinner_text), console=console, transient=True):
            answer = connector.invoke_llm_for_content(main_instruction=llm_prompt, context_text=content)

        if "Error: LLM content generation failed." in answer:
            print_error(answer, "LLM Answer Failed")
        else:
            print_panel_message("LLM Answer", answer, "info", ICONS["answer"])
        log_action("ask_question_about_file", {"file_path": abs_filepath, **parameters}, "success", f"Answer length: {len(answer)}")
    else:
        log_action("ask_question_about_file", {"file_path": abs_filepath, **parameters}, "failure", "Could not read file content")

def handle_list_folder(parameters: dict):
    folder_path_param = parameters.get("folder_path")
    folder_path = resolve_contextual_path(folder_path_param, is_folder_hint=True)

    if not folder_path or folder_path_param == "__MISSING__":
        default_path = session_context.get("last_folder_listed_path") or \
                       (os.path.dirname(session_context["last_referenced_file_path"]) if session_context.get("last_referenced_file_path") and os.path.isfile(session_context.get("last_referenced_file_path")) else None) or \
                       os.getcwd()
        folder_path = get_path_from_user_input("Which folder to list?", default_path=default_path, is_folder=True)
    
    abs_folder_path = os.path.abspath(folder_path)
    if not os.path.isdir(abs_folder_path):
        # Improved error handling with suggestions as in original code
        # For brevity in this update, direct error. Original complex suggestion logic can be re-integrated.
        print_error(f"Path '{abs_folder_path}' is not a valid directory.")
        log_action("list_folder_contents", {"folder_path": folder_path, **parameters}, "failure", f"Invalid folder path: {abs_folder_path}")
        return

    console.print(f"{ICONS['folder']} Listing contents of folder: [filepath]{abs_folder_path}[/filepath]")
    update_session_context("last_folder_listed_path", abs_folder_path)
    
    contents = list_folder_contents(abs_folder_path, console)
    if contents is not None:
        if not contents:
            print_info(f"Folder [filepath]'{os.path.basename(abs_folder_path)}'[/filepath] is empty.", "Folder Empty")
            update_session_context("last_search_results", []) 
            log_action("list_folder_contents", {"folder_path": abs_folder_path, **parameters}, "success", "Folder empty")
        else:
            table = Table(title=f"{ICONS['folder']} Contents of {os.path.basename(abs_folder_path)} ({len(contents)} items)",
                          show_header=True, header_style="table.header", box=ROUNDED, expand=True)
            table.add_column("Icon", width=4, justify="center")
            table.add_column("Index", width=5, justify="right")
            table.add_column("Name", style="filepath", no_wrap=False, overflow="fold")
            table.add_column("Type", width=10)
            
            for i, item in enumerate(contents):
                item_icon = ICONS["folder"] if item['type'] == "folder" else ICONS["file"]
                table.add_row(item_icon, str(i + 1), item['name'], item['type'])
            console.print(table)
            update_session_context("last_search_results", contents)
            log_action("list_folder_contents", {"folder_path": abs_folder_path, **parameters}, "success", f"Listed {len(contents)} items")
    else:
        log_action("list_folder_contents", {"folder_path": abs_folder_path, **parameters}, "failure", "Error during listing")

def handle_move_item(parameters: dict):
    source_path_param = parameters.get("source_path")
    destination_path_param = parameters.get("destination_path")

    source_path = resolve_contextual_path(source_path_param)
    if not source_path or source_path_param == "__MISSING__":
        default_src = session_context.get("last_referenced_file_path") or session_context.get("last_folder_listed_path")
        source_path = get_path_from_user_input("What item to move? (Source path)", default_path=default_src)
    
    abs_source_path = os.path.abspath(source_path)
    if not os.path.exists(abs_source_path):
        print_error(f"Source path '{abs_source_path}' does not exist.")
        log_action("move_item", {"source_path": source_path, **parameters}, "failure", f"Invalid source: {abs_source_path}")
        return
    
    if not destination_path_param or destination_path_param == "__MISSING__":
        destination_path = get_path_from_user_input(f"Where to move '{os.path.basename(abs_source_path)}'? (Destination path/folder)")
    else:
        destination_path = destination_path_param

    abs_destination_path = os.path.abspath(destination_path)

    confirm_panel_text = (f"  FROM: [filepath]{abs_source_path}[/filepath]\n"
                          f"  TO:   [filepath]{abs_destination_path}[/filepath]")
    print_panel_message("Confirm Move", confirm_panel_text, "warning", ICONS["confirm"])
    
    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Proceed with move operation?"), default=False):
        if move_item(abs_source_path, abs_destination_path, console): # console passed for move_item's internal errors
            print_success(f"Successfully moved '{os.path.basename(abs_source_path)}' to '{abs_destination_path}'.")
            log_action("move_item", {"source_path": abs_source_path, "destination_path": abs_destination_path, **parameters}, "success")
            update_session_context("last_referenced_file_path", None) # Invalidate context
            update_session_context("last_folder_listed_path", None)
            update_session_context("last_search_results", [])
        else:
            # Error already printed by move_item or print_error here if move_item doesn't print
            log_action("move_item", {"source_path": abs_source_path, "destination_path": abs_destination_path, **parameters}, "failure", "Move failed")
    else:
        print_info("Move operation cancelled.", "Cancelled")
        log_action("move_item", {"source_path": source_path, "destination_path": destination_path, **parameters}, "cancelled")

def handle_search_files(connector: OllamaConnector, parameters: dict):
    search_criteria = parameters.get("search_criteria")
    search_path_from_llm = parameters.get("search_path")

    if not search_criteria:
        search_criteria = Prompt.ask(Text.from_markup(f"{ICONS['search']} What are you searching for? (e.g., 'images', 'PDFs about finance')")).strip()
    if not search_criteria:
        print_warning("No search criteria provided.")
        log_action("search_files", parameters, "failure", "No search criteria")
        return

    resolved_search_path = None
    if search_path_from_llm and search_path_from_llm not in ["__MISSING__", "__FROM_CONTEXT__"]:
        # Handle special keywords like ".", "here" etc.
        if search_path_from_llm.lower() in [".", "here", "current folder", "this folder"]:
            resolved_search_path = os.path.abspath(os.getcwd())
        else:
            candidate_path = os.path.abspath(search_path_from_llm)
            if os.path.isdir(candidate_path): resolved_search_path = candidate_path
    
    if not resolved_search_path:
        if search_path_from_llm == "__FROM_CONTEXT__":
            context_folder = session_context.get("last_folder_listed_path")
            context_file_dir = os.path.dirname(session_context.get("last_referenced_file_path","")) if session_context.get("last_referenced_file_path") and os.path.isfile(session_context.get("last_referenced_file_path","")) else None
            resolved_search_path = context_folder or context_file_dir
        
        if not resolved_search_path: 
            default_prompt_path = session_context.get("last_folder_listed_path", os.getcwd())
            if search_path_from_llm and search_path_from_llm not in ["__MISSING__", "__FROM_CONTEXT__", ".", "here", "current folder", "this folder"]:
                 print_warning(f"Could not use '[filepath]{search_path_from_llm}[/filepath]' as search location. It may be invalid.")
            resolved_search_path = get_path_from_user_input("Where should I search?", default_path=default_prompt_path, is_folder=True)
            
    abs_search_path = os.path.abspath(resolved_search_path)
    if not os.path.isdir(abs_search_path):
        print_error(f"Search directory '[filepath]{abs_search_path}[/filepath]' is invalid or does not exist.")
        log_action("search_files", {"search_path": resolved_search_path, **parameters}, "failure", "Invalid search directory")
        return

    console.print(f"{ICONS['search']} Searching in [filepath]{abs_search_path}[/filepath] for: [highlight]'{search_criteria}'[/highlight]")
    
    # search_files_recursive uses Rich Progress internally
    found_files = search_files_recursive(abs_search_path, search_criteria, connector, console)
    
    if not found_files:
        print_info(f"No files found matching criteria: [highlight]'{search_criteria}'[/highlight]", "Search Results")
    else:
        print_success(f"Found {len(found_files)} item(s) matching [highlight]'{search_criteria}'[/highlight]:", "Search Results")
        table = Table(title=f"{ICONS['search']} Search Results", show_header=True, header_style="table.header", box=ROUNDED, expand=True)
        table.add_column("Icon", width=4, justify="center")
        table.add_column("Index", width=5, justify="right")
        table.add_column("Name", style="filepath", no_wrap=False, overflow="fold")
        table.add_column("Path", style="dim_text", no_wrap=False, overflow="fold") # Dim path to highlight name
        for i, item in enumerate(found_files):
            item_icon = ICONS["folder"] if item['type'] == "folder" else ICONS["file"]
            table.add_row(item_icon, str(i + 1), item['name'], item['path'])
        console.print(table)
    
    update_session_context("last_search_results", found_files)
    update_session_context("last_folder_listed_path", abs_search_path)
    log_action("search_files", {"search_criteria": search_criteria, "search_path": abs_search_path, **parameters}, "success", f"Found {len(found_files)} items")

def handle_general_chat(connector: OllamaConnector, parameters: dict):
    original_request = parameters.get("original_request", "...")
    response = ""
    spinner_text = f"{ICONS['thinking']} [spinner_style]Thinking about: '{original_request[:30]}...'[/spinner_style]"
    with Live(Spinner("bouncingBar", text=spinner_text), console=console, transient=True):
        response = connector.invoke_llm_for_content(main_instruction=original_request)
    
    if "Error: LLM content generation failed." in response:
        print_error(response, "LLM Chat Failed")
    else:
        print_panel_message("CodeX Response", response, "info", ICONS['answer'])
    log_action("general_chat", {"request": original_request, **parameters}, "success", f"Response length: {len(response)}")

def handle_show_activity_log(parameters: dict):
    default_log_count = MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL // 5 
    count_param = parameters.get("count", default_log_count) 
    try:
        count = int(count_param)
        if count <= 0 or count > MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL : count = default_log_count 
    except (ValueError, TypeError):
        count = default_log_count
        print_warning(f"Invalid count '{count_param}', showing last {count} activities.")

    activities = get_recent_activities(count)
    if not activities:
        print_info("Activity log is empty or could not be read.", "Activity Log Status")
        return

    table = Table(title=f"{ICONS['log']} Recent Activity (Last {len(activities)} entries)", 
                  box=ROUNDED, header_style="table.header", show_header=True)
    table.add_column("Timestamp", style="dim_text", width=22)
    table.add_column("Action", style="bold", width=25)
    table.add_column("Parameters", style="dim_text", overflow="fold", max_width=40)
    table.add_column("Status", width=12)
    table.add_column("Details", overflow="fold", max_width=40)

    for activity in activities:
        ts_raw = activity.get('timestamp', 'N/A')
        try:
            ts = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).strftime('%y-%m-%d %H:%M:%S') if ts_raw != 'N/A' else 'N/A'
        except ValueError: ts = ts_raw 
            
        status = activity.get('status', 'unknown')
        status_color = "green" if status == "success" else "yellow" if status in ["partial_success", "cancelled", "initiated", "plan_proposed"] else "red"
        
        details_preview = activity.get('details', '')
        
        param_str_parts = []
        activity_params = activity.get('parameters', {}) if isinstance(activity.get('parameters'), dict) else {}
        for k, v_obj in activity_params.items():
            v_str = str(v_obj)
            param_str_parts.append(f"[highlight]{k}[/highlight]: '{(v_str[:25] + '...' if len(v_str) > 25 else v_str)}'")
        params_str = ", ".join(param_str_parts) if param_str_parts else "N/A"

        table.add_row(ts, activity.get('action', 'N/A'), Text.from_markup(params_str), f"[{status_color}]{status}[/{status_color}]", details_preview)
    
    console.print(table)
    log_action("show_activity_log", {"count": count, **parameters}, "success", f"Displayed {len(activities)} logs")

def handle_redo_activity(connector: OllamaConnector, parameters: dict):
    activity_identifier = parameters.get("activity_identifier")
    if not activity_identifier:
        activity_identifier = Prompt.ask(Text.from_markup(f"{ICONS['redo']} Which activity to redo? ('last', index, or partial timestamp)")).strip()
    if not activity_identifier:
        print_warning("No activity identifier provided for redo.")
        log_action("redo_activity", parameters, "failure", "No identifier")
        return

    activity_to_redo = get_activity_by_partial_id_or_index(activity_identifier, console)
    if not activity_to_redo:
        log_action("redo_activity", {"identifier": activity_identifier, **parameters}, "failure", "Activity not found")
        return 

    action_to_perform = activity_to_redo.get("action")
    params_to_use = activity_to_redo.get("parameters", {})

    redo_confirm_text = (f"Action: [highlight]{action_to_perform}[/highlight]\n"
                         f"Params: [dim_text]{json.dumps(params_to_use, indent=2)}[/dim_text]")
    print_panel_message("Confirm Redo", redo_confirm_text, "warning", ICONS["redo"])

    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Confirm redo?"), default=True):
        console.print(f"{ICONS['execute']} Attempting to redo action: [highlight]{action_to_perform}[/highlight]")
        log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform, **parameters}, "initiated")
        
        handler_func = action_handlers.get(action_to_perform)
        if handler_func:
            try:
                if action_to_perform in ["summarize_file", "ask_question_about_file", "search_files", 
                                         "propose_and_execute_organization", "general_chat", "redo_activity"]:
                    handler_func(connector, params_to_use)
                else:
                    handler_func(params_to_use)
            except Exception as e:
                print_error(f"Error during redo of '{action_to_perform}': {e}", "Redo Execution Error")
                log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform}, "failure", f"Error: {e}")
        else:
            print_error(f"Action '{action_to_perform}' from log is not currently redoable or handler not found.", "Redo Failed")
            log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform}, "failure", "Action not redoable")
    else:
        print_info("Redo operation cancelled.", "Cancelled")
        log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform, **parameters}, "cancelled")

def handle_propose_and_execute_organization(connector: OllamaConnector, parameters: dict):
    target_param = parameters.get("target_path_or_context")
    organization_goal = parameters.get("organization_goal")
    if not organization_goal or organization_goal.lower() == "general organization":
        organization_goal = "improve structure and organization based on item names and types"

    items_for_analysis = []
    base_analysis_path = None
    source_description = ""

    if target_param == "__FROM_CONTEXT__":
        if session_context.get("last_folder_listed_path"):
            base_analysis_path = session_context["last_folder_listed_path"]
            # Use last_search_results if they are contents of this folder
            if session_context.get("last_search_results"):
                sample_paths = [item['path'] for item in session_context["last_search_results"][:5] if 'path' in item]
                # Simple check: if any path is not a child, refresh. More robust check is complex.
                is_content_of_folder = all(p.startswith(base_analysis_path + os.sep) for p in sample_paths)
                if is_content_of_folder:
                    items_for_analysis = session_context["last_search_results"]
                else:
                    items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            else:
                items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            source_description = f"folder '[filepath]{os.path.basename(base_analysis_path)}[/filepath]' (from context)"
        elif session_context.get("last_search_results"):
            items_for_analysis = session_context["last_search_results"]
            paths = [item['path'] for item in items_for_analysis if 'path' in item]
            if paths:
                try: base_analysis_path = os.path.commonpath(paths)
                except ValueError: base_analysis_path = os.path.dirname(paths[0])
                if not os.path.isdir(base_analysis_path): base_analysis_path = os.path.dirname(paths[0])
            source_description = "items from your last search/listing"
        else: # No usable context
            print_warning("No clear context for organization. Please specify a folder.")
            base_analysis_path = get_path_from_user_input("Which folder to organize?", default_path=os.getcwd(), is_folder=True)
            items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            source_description = f"folder '[filepath]{os.path.basename(base_analysis_path)}[/filepath]'"
    elif target_param and target_param != "__MISSING__":
        candidate_path = os.path.abspath(target_param)
        if os.path.isdir(candidate_path):
            base_analysis_path = candidate_path
            items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            source_description = f"folder '[filepath]{os.path.basename(base_analysis_path)}[/filepath]'"
        else:
            print_error(f"Path '{target_param}' is not a valid directory for organization.")
            # Simplified logic here for brevity, original error handling was more detailed.
            return
    else: # No target specified or missing
        base_analysis_path = get_path_from_user_input("Which folder do you want to organize?", default_path=os.getcwd(), is_folder=True)
        items_for_analysis = list_folder_contents(base_analysis_path, console) or []
        source_description = f"folder '[filepath]{os.path.basename(base_analysis_path)}[/filepath]'"

    if not base_analysis_path or not os.path.isdir(base_analysis_path):
        print_error("Cannot proceed: No valid directory identified for organization.")
        log_action("propose_and_execute_organization", parameters, "failure", "No valid directory")
        return
    if not items_for_analysis:
        print_info(f"No items found in {source_description} to organize.", "Organization Status")
        log_action("propose_and_execute_organization", {**parameters, "resolved_target": base_analysis_path}, "failure", "No items to organize")
        return

    abs_base_analysis_path = os.path.abspath(base_analysis_path)
    console.print(Padding(f"{ICONS['thinking']} Analyzing {source_description} (goal: '[highlight]{organization_goal}[/highlight]') to propose an organization plan...", (1,0)))

    item_summary_list = [f"- \"{os.path.relpath(item['path'], abs_base_analysis_path) if item['path'].startswith(abs_base_analysis_path) else item.get('name', 'N/A')}\" (type: {item['type']})" 
                         for item in items_for_analysis[:50]]
    item_summary_for_llm = "\n".join(item_summary_list)
    if len(items_for_analysis) > 50: item_summary_for_llm += f"\n... and {len(items_for_analysis) - 50} more items."

    proposed_actions_json = None
    spinner_text = f"{ICONS['thinking']} [spinner_style]Asking LLM to generate organization plan...[/spinner_style]"
    with Live(Spinner("bouncingBar", text=spinner_text), console=console, transient=True):
        proposed_actions_json = connector.generate_organization_plan_llm(item_summary_for_llm, organization_goal, abs_base_analysis_path)

    if proposed_actions_json is None:
        print_error("Failed to generate an organization plan. LLM might have returned invalid data or timed out.", "Planning Failed")
        log_action("propose_and_execute_organization", {**parameters, "base_path": abs_base_analysis_path}, "failure", "LLM plan gen failed")
        return
    if not proposed_actions_json:
        print_info("LLM proposed no actions. Items might be well-organized or the goal was unclear.", "Planning Result")
        log_action("propose_and_execute_organization", {**parameters, "base_path": abs_base_analysis_path}, "success", "LLM proposed no actions")
        return

    plan_table = Table(title=f"{ICONS['plan']} Proposed Organization Plan", show_header=True, header_style="table.header", box=ROUNDED)
    plan_table.add_column("Icon", width=4, justify="center")
    plan_table.add_column("Step", justify="right", width=5)
    plan_table.add_column("Action", width=15)
    plan_table.add_column("Details", overflow="fold")
    
    valid_plan_actions = []
    has_invalid_actions = False

    for i, action_data in enumerate(proposed_actions_json):
        action_type = action_data.get("action_type")
        details_str = ""
        is_valid = True
        action_icon = "❓"

        if action_type == "CREATE_FOLDER":
            action_icon = ICONS["create_folder"]
            path = action_data.get("path")
            if not (path and isinstance(path, str) and os.path.isabs(path)):
                details_str = f"[danger]Invalid/Relative path: {path}[/danger]"
                is_valid = False
            elif not path.startswith(abs_base_analysis_path): # Security check
                details_str = f"[danger]Path is outside target directory: {path}[/danger]"
                is_valid = False
            else: details_str = f"Path: [filepath]{path}[/filepath]"
        elif action_type == "MOVE_ITEM":
            action_icon = ICONS["move"]
            source, dest = action_data.get("source"), action_data.get("destination")
            if not (source and os.path.isabs(source) and dest and os.path.isabs(dest)):
                details_str = f"[danger]Invalid/Relative paths. S: {source}, D: {dest}[/danger]"
                is_valid = False
            elif source == dest: # Usually an error by LLM
                details_str = f"[warning]Source and destination are identical: {source}[/warning]"
                is_valid = False # Typically don't execute this
            elif not source.startswith(abs_base_analysis_path) or not dest.startswith(abs_base_analysis_path): # Security
                details_str = f"[danger]Source or Destination is outside target scope. S: {source}, D: {dest}[/danger]"
                is_valid = False
            else: details_str = f"From: [filepath]{source}[/filepath]\nTo:   [filepath]{dest}[/filepath]"
        else:
            details_str = f"[danger]Unknown action type: {action_type}[/danger]"
            is_valid = False

        plan_table.add_row(action_icon, str(i+1), action_type if is_valid else f"[danger]{action_type}[/danger]", Text.from_markup(details_str))
        if is_valid: valid_plan_actions.append(action_data)
        else: has_invalid_actions = True
    
    console.print(plan_table)
    if has_invalid_actions: print_warning("Plan has invalid actions (marked red/yellow), they will be skipped if you proceed.", "Plan Validation")
    if not valid_plan_actions:
        print_info("No valid actions in the proposed plan to execute.", "Plan Status")
        log_action("propose_and_execute_organization", {**parameters, "base_path": abs_base_analysis_path}, "failure", "No valid actions in plan")
        return

    log_action("propose_and_execute_organization", {**parameters, "base_path": abs_base_analysis_path, "plan_count": len(proposed_actions_json), "valid_count": len(valid_plan_actions)}, "plan_proposed")

    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Execute these {len(valid_plan_actions)} valid actions?"), default=False):
        console.print(Padding(f"{ICONS['execute']} [bold]Executing {len(valid_plan_actions)} organization actions...[/bold]",(1,0)))
        exec_ok, exec_fail = 0, 0
        
        with Progress(console=console, transient=False, expand=True) as progress:
            exec_task = progress.add_task(f"{ICONS['execute']} [spinner_style]Processing...[/spinner_style]", total=len(valid_plan_actions))
            for i, action_data in enumerate(valid_plan_actions):
                action_type = action_data["action_type"]
                progress.update(exec_task, description=f"{ICONS['execute']} [spinner_style]Step {i+1}/{len(valid_plan_actions)}: {action_type}...[/spinner_style]")
                success, log_status, msg = False, "failure", ""

                if action_type == "CREATE_FOLDER":
                    path = action_data["path"]
                    try:
                        if os.path.exists(path) and os.path.isdir(path):
                            msg = f"  {ICONS['info']} [dim_text]Exists: '{os.path.basename(path)}'. Skipping.[/dim_text]"
                            success, log_status = True, "success" # يعتبر ناجح لو موجود
                        else:
                            os.makedirs(path, exist_ok=True)
                            msg = f"  {ICONS['success']} [green]Created:[/green] [filepath]{os.path.basename(path)}[/filepath]"
                            success, log_status = True, "success"
                    except Exception as e: msg = f"  {ICONS['error']} [danger]Failed CREATE_FOLDER '{os.path.basename(path)}': {e}[/danger]"
                elif action_type == "MOVE_ITEM":
                    source, dest = action_data["source"], action_data["destination"]
                    if not os.path.exists(source):
                        msg = f"  {ICONS['warning']} [warning]Source '{os.path.basename(source)}' not found (moved/deleted?). Skipping.[/warning]"
                        log_status = "skipped" # Specific status
                    elif move_item(source, dest, console):
                        msg = f"  {ICONS['success']} [green]Moved:[/green] [filepath]{os.path.basename(source)}[/filepath] -> [filepath]{os.path.relpath(dest, os.path.dirname(source))}[/filepath]"
                        success, log_status = True, "success"
                    else: # move_item prints its own detailed error in red
                        msg = f"  {ICONS['error']} [danger]Failed MOVE_ITEM (see error above): '{os.path.basename(source)}'[/danger]" # Generic if move_item fails silently

                console.print(msg)
                if success: exec_ok += 1
                else: exec_fail += 1
                log_action(f"exec_org_{action_type.lower()}", {**action_data, "base_path": abs_base_analysis_path}, log_status, msg.split(":",1)[-1].strip())
                progress.update(exec_task, advance=1)
            
            progress.update(exec_task, description=f"{ICONS['success']} [green]Execution finished.[/green]")

        summary_msg = f"Successfully executed: {exec_ok}, Failed/Skipped: {exec_fail}"
        print_success(summary_msg, "Organization Summary")
        update_session_context("last_referenced_file_path", None)
        update_session_context("last_folder_listed_path", None)
        update_session_context("last_search_results", [])
        log_action("execute_organization_plan", {**parameters, "base_path": abs_base_analysis_path, "ok": exec_ok, "fail": exec_fail}, "completed")
    else:
        print_info("Organization plan execution cancelled.", "Cancelled")
        log_action("execute_organization_plan", {**parameters, "base_path": abs_base_analysis_path, "valid_actions_count": len(valid_plan_actions)}, "cancelled")


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

def print_startup_message(connector):
    console.clear()
    with Live(Spinner("dots", text=f"{ICONS['thinking']} [spinner_style]Initializing CodeX Assistant...[/spinner_style]"), console=console, transient=True, refresh_per_second=10):
        time.sleep(1.5) # Simulate loading
    
    console.print(Align.center(APP_LOGO_TEXT))
    
    status_items = []
    conn_ok, model_ok, _ = connector.check_connection_and_model()
    
    if not conn_ok:
        print_error("Could not connect to Ollama. Please ensure Ollama is running.", "Ollama Connection Failed")
        return False
    status_items.append(f"{ICONS['success']} Connected to Ollama ([highlight]{connector.base_url}[/highlight])")
    
    if not model_ok:
        print_error(f"LLM Model '[highlight]{OLLAMA_MODEL}[/highlight]' not found in Ollama. Please pull it or check `config.py`.", "Model Not Found")
        return False
    status_items.append(f"{ICONS['success']} Using LLM Model: [highlight]{OLLAMA_MODEL}[/highlight]")
    
    status_text = "\n".join(status_items)
    console.print(Panel(Text.from_markup(status_text), title=f"{ICONS['info']} System Status", border_style="panel.border.info", box=ROUNDED, padding=(1,2)))
    
    help_text = (f"\n{ICONS['info']} Type [prompt]help[/prompt] for available commands, or just ask your question."
                 f"\n{ICONS['info']} Type [prompt]quit[/prompt] or [prompt]exit[/prompt] to close the assistant.")
    console.print(Padding(Text.from_markup(help_text), (1, 0)))
    return True

def resolve_indexed_reference(user_input_lower: str, parameters: dict):
    if parameters.get("file_path") or parameters.get("folder_path"): return False
    match = re.search(r"(?:item\s*|number\s*|file\s*|#\s*)?(\d+)(?:st|nd|rd|th)?(?:\s*one)?", user_input_lower)
    
    if match and session_context.get("last_search_results"):
        try:
            item_index_str = match.group(1)
            item_index = int(item_index_str) - 1 
            is_likely_index_ref = (user_input_lower.strip() == item_index_str) or (match.group(0) in user_input_lower)

            if is_likely_index_ref and 0 <= item_index < len(session_context["last_search_results"]):
                referenced_item = session_context["last_search_results"][item_index]
                current_action_by_llm = parameters.get("action", "")
                
                if referenced_item["type"] == "file":
                    parameters["file_path"] = referenced_item["path"]
                    is_ask_intent = ("ask" in current_action_by_llm or any(k in user_input_lower for k in ["ask", "tell me about", "what is in", "question", "explain"]))
                    is_summarize_intent = ("summarize" in current_action_by_llm or "summarize" in user_input_lower)

                    if is_ask_intent:
                        parameters["action"] = "ask_question_about_file"
                        if not parameters.get("question_text"): # Extract question if not explicitly parsed by LLM
                            question_part = user_input_lower.replace(match.group(0), "", 1).strip()
                            for aw in ["summarize", "ask", "tell me about", "what is", "explain", "contents of"]:
                                question_part = re.sub(r'\b' + re.escape(aw) + r'\b', '', question_part, flags=re.IGNORECASE).strip()
                            parameters["question_text"] = question_part if question_part else f"Tell me more about {os.path.basename(referenced_item['name'])}"
                    elif is_summarize_intent or not current_action_by_llm: # Default to summarize if file and no other strong intent
                         parameters["action"] = "summarize_file"
                elif referenced_item["type"] == "folder":
                    parameters["folder_path"] = referenced_item["path"]
                    parameters["action"] = "list_folder_contents"
                return True
        except (ValueError, TypeError, AttributeError): pass 
    return False

def main():
    load_session_context()
    connector = OllamaConnector()
    if not print_startup_message(connector):
        save_session_context(); return

    try:
        while True:
            console.print(Rule(style="separator_style"))
            user_input_original = Prompt.ask(Text.from_markup("[prompt]You[/prompt]"), default="").strip()
            
            if not user_input_original: continue
            if user_input_original.lower() in ['quit', 'exit', 'bye', 'q']:
                console.print(f"{ICONS['app_icon']} [bold app_logo_style]Exiting CodeX AI Assistant. Goodbye![/bold app_logo_style]"); break
            
            if user_input_original.lower() == 'help':
                help_content = Markdown(f"""
# CodeX AI Assistant Help {ICONS['info']}

## Example Commands:
*   `summarize "path/to/file.txt"` - Get a summary of a file.
*   `what is in "doc.docx" about project alpha?` - Ask questions about file content.
*   `list contents of "C:/my_folder"` (or `list item 3` after a search that listed folders).
*   `search for images in .` (searches current directory).
*   `search for python scripts containing 'db_utils' in "~/projects"`
*   `move "old_file.txt" to "archive/old_file.txt"`
*   `organize this folder by type` (after listing/searching a folder).
*   `organize "C:/Downloads" by file extension`
*   `show my last 5 activities` - View command history.
*   `redo last search` - Re-run the last executed search.
*   `redo task 2` (refers to 2nd most recent logged activity).
*   Simply chat, e.g., `hello` or `what can you do?`

## Notes:
*   Use quotes for paths with spaces.
*   Context is remembered! You can refer to items from previous listings or searches (e.g., `summarize item 1`).
*   File organization is experimental. Always review proposed plans carefully.
""")
                console.print(Panel(help_content, title=f"{ICONS['info']} Help & Examples", border_style="panel.border.info", box=ROUNDED))
                continue

            parsed_command = None
            spinner_text = f"{ICONS['thinking']} [spinner_style]Understanding: '{user_input_original[:35]}...'[/spinner_style]"
            with Live(Spinner("dots", text=spinner_text), console=console, refresh_per_second=10, transient=True):
                parsed_command = connector.get_intent_and_entities(user_input_original, session_context)

            if not parsed_command or "action" not in parsed_command:
                print_warning("Sorry, I had trouble understanding that. Could you rephrase or try 'help'?", "NLU Error")
                log_action("nlu_failure", {"input": user_input_original}, "failure", "LLM could not parse intent")
                continue

            action = parsed_command.get("action")
            parameters = parsed_command.get("parameters", {})
            nlu_correction_note = parsed_command.get("nlu_correction_note") # Check if NLU was corrected
            
            # resolve_indexed_reference might update 'action' and 'parameters' in-place
            if resolve_indexed_reference(user_input_original.lower(), parameters):
                action = parameters.get("action", action) # Get potentially updated action

            add_to_command_history(action, parameters, nlu_correction_note)

            handler_func = action_handlers.get(action)
            if handler_func:
                if action in ["summarize_file", "ask_question_about_file", "search_files", 
                              "propose_and_execute_organization", "general_chat", "redo_activity"]:
                    handler_func(connector, parameters)
                else:
                    handler_func(parameters)
            elif action == "unknown":
                original_req = parameters.get("original_request", user_input_original)
                error_detail = parameters.get("error", "Unrecognized command structure.")
                print_warning(f"I'm not sure how to handle: '{original_req}'.\nNLU Hint: {error_detail}\nTry 'help' for examples.", "Unknown Command")
                log_action("unknown_command", {"input": original_req, **parameters}, "failure", error_detail)
            else: # Action recognized by NLU but no handler
                print_warning(f"Action '[highlight]{action}[/highlight]' is recognized but not implemented yet.", "Not Implemented")
                log_action("not_implemented", {"action": action, "input": user_input_original, **parameters}, "pending")

    except KeyboardInterrupt: console.print(f"\n{ICONS['app_icon']} [bold app_logo_style]Exiting CodeX AI Assistant. Goodbye![/bold app_logo_style]")
    except Exception:
        print_error("A critical unexpected error occurred in the main loop!", "Critical Error")
        console.print_exception(show_locals=True, width=console.width)
    finally: save_session_context()

if __name__ == '__main__':
    main()