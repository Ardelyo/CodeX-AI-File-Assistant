import os
import time
import re 
import json 
import datetime 
from ollama_connector import OllamaConnector
from file_utils import get_file_content, move_item, list_folder_contents, search_files_recursive
from activity_logger import log_action, get_recent_activities, get_activity_by_partial_id_or_index, MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL
from config import OLLAMA_MODEL

# Rich components for enhanced UI
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
from rich.box import ROUNDED

# Define custom theme and styles
CUSTOM_THEME = Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "danger": "bold red",
    "success": "green",
    "prompt": "bold green",
    "filepath": "cyan",
    "highlight": "bold magenta",
    "panel.title": "bold white on blue",
    "panel.border": "blue",
    "table.header": "bold blue",
    "table.cell": "cyan",
    "spinner": "bold cyan",
    "progress.bar": "#4169E1",
    "progress.percentage": "cyan",
    "logo": "bold blue"
})

# Visual elements like icons and separators
ICONS = {
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "thinking": "⟳",
    "plan": "☰",
    "execute": "►",
    "folder": "📁",
    "file": "📄",
    "search": "🔍"
}

# ASCII art logo for startup
APP_LOGO = """
 ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
        AI File Assistant v1.0
"""


# Initialize console with custom theme
console = Console(theme=CUSTOM_THEME)

SESSION_CONTEXT_FILE = "session_context.json"
MAX_COMMAND_HISTORY = 20

# --- Session Context Management ---
session_context = {
    "last_referenced_file_path": None,
    "last_folder_listed_path": None,
    "last_search_results": [], 
    "command_history": [], 
}

def load_session_context():
    global session_context
    if os.path.exists(SESSION_CONTEXT_FILE):
        try:
            with open(SESSION_CONTEXT_FILE, "r", encoding="utf-8") as f:
                loaded_ctx = json.load(f)
                session_context.update(loaded_ctx)
                # Ensure default keys exist even if loaded context is minimal
                session_context.setdefault("last_referenced_file_path", None)
                session_context.setdefault("last_folder_listed_path", None)
                session_context.setdefault("last_search_results", [])
                session_context.setdefault("command_history", [])
                console.print(f"[dim]Session context loaded from {SESSION_CONTEXT_FILE}[/dim]")
        except (json.JSONDecodeError, IOError) as e:
            console.print(f"[yellow]Warning: Could not load session context: {e}. Starting fresh.[/yellow]")
            # Re-initialize with defaults to ensure structure
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
        console.print(f"[red]Error saving session context: {e}[/red]")

def update_session_context(key, value):
    global session_context
    session_context[key] = value
    if key == "last_search_results" and value is not None:
        session_context["last_referenced_file_path"] = None
        session_context["last_folder_listed_path"] = None
    elif key == "last_referenced_file_path" and value:
        session_context["last_folder_listed_path"] = None
    elif key == "last_folder_listed_path" and value:
        session_context["last_referenced_file_path"] = None

def add_to_command_history(action: str, parameters: dict):
    global session_context
    if "command_history" not in session_context or not isinstance(session_context["command_history"], list):
        session_context["command_history"] = []
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": action,
        "parameters": parameters if parameters else {}
    }
    session_context["command_history"].append(entry)
    session_context["command_history"] = session_context["command_history"][-MAX_COMMAND_HISTORY:]

def get_path_from_user_input(prompt_message="Please provide the full path", default_path=None, is_folder=False):
    path_type = "folder" if is_folder else "file/folder"
    prompt_suffix = f" ({path_type})"
    if default_path:
        prompt_message = f"{prompt_message}{prompt_suffix} [default: {default_path}]"
    else:
        prompt_message = f"{prompt_message}{prompt_suffix}"
    path = Prompt.ask(prompt_message, default=default_path if default_path else ...)
    return os.path.abspath(path.strip().strip("'\""))

def resolve_contextual_path(parameter_value, is_folder_hint=False):
    if parameter_value == "__FROM_CONTEXT__":
        # Prioritize folder context if hinted and available
        if is_folder_hint and session_context.get("last_folder_listed_path"):
            return session_context["last_folder_listed_path"]
        # Then try file path context
        if session_context.get("last_referenced_file_path"):
            path_to_check = session_context["last_referenced_file_path"]
            # If it's a file and we need a folder, take its parent dir
            return os.path.dirname(path_to_check) if (is_folder_hint and os.path.isfile(path_to_check)) else path_to_check
        # Fallback to folder context if file context was not relevant or empty
        if session_context.get("last_folder_listed_path"):
             return session_context["last_folder_listed_path"]
    return None


# --- Action Handler Functions ---

def handle_summarize_file(connector: OllamaConnector, parameters: dict):
    filepath_param = parameters.get("file_path")
    filepath = resolve_contextual_path(filepath_param)
    
    if not filepath or filepath_param == "__MISSING__":
        filepath = get_path_from_user_input("Which file to summarize?", default_path=session_context.get("last_referenced_file_path"))
    
    abs_filepath = os.path.abspath(filepath) # Ensure absolute path
    if not os.path.isfile(abs_filepath):
        console.print(f"[red]Error: Path '{abs_filepath}' is not a valid file.[/red]")
        log_action("summarize_file", {"file_path": filepath, **parameters}, "failure", f"Invalid file path: {abs_filepath}")
        return

    console.print(f"Attempting to summarize: [cyan]{abs_filepath}[/cyan]")
    update_session_context("last_referenced_file_path", abs_filepath)
    
    content = get_file_content(abs_filepath, console) # get_file_content handles its own error printing
    if content:
        if "PDF parsing not yet fully implemented" in content: # Specific check for placeholder
            console.print(f"[yellow]{content}[/yellow]")
            log_action("summarize_file", {"file_path": abs_filepath, **parameters}, "partial_success", "PDF not fully parsed")
            return
            
        llm_prompt = "Summarize the following text comprehensively and concisely:"
        summary = ""
        with Live(Spinner("bouncingBar", text="Asking LLM for summarization..."), console=console, refresh_per_second=10, transient=True):
            summary = connector.invoke_llm_for_content(main_instruction=llm_prompt, context_text=content)
        
        console.print(Panel(Text(summary, justify="left"), title="[bold green]LLM Summary[/bold green]", border_style="green"))
        log_action("summarize_file", {"file_path": abs_filepath, **parameters}, "success", f"Summary generated (length: {len(summary)})")
    else:
        # get_file_content would have printed an error if content is None
        log_action("summarize_file", {"file_path": abs_filepath, **parameters}, "failure", "Could not read file content")

def handle_ask_question(connector: OllamaConnector, parameters: dict):
    filepath_param = parameters.get("file_path")
    question = parameters.get("question_text", "")
    filepath = resolve_contextual_path(filepath_param)

    # If no path specified in parameters
    if not filepath or filepath_param == "__MISSING__":
        default_path = None
        # Try to use last_folder_listed_path if we're likely analyzing a folder structure
        if "structure" in question.lower() or "organize" in question.lower():
            default_path = session_context.get("last_folder_listed_path")
        # Otherwise use last_referenced_file_path
        if not default_path:
            default_path = session_context.get("last_referenced_file_path")
        filepath = get_path_from_user_input("Which file or folder are you asking about?", default_path=default_path)
    
    abs_filepath = os.path.abspath(filepath)
    
    # Support for folder analysis
    if os.path.isdir(abs_filepath):
        update_session_context("last_folder_listed_path", abs_filepath)
        
        if not question:
            question = Prompt.ask(f"What would you like to know about folder [cyan]{os.path.basename(abs_filepath)}[/cyan]?").strip()
        if not question:
            console.print("[yellow]No question provided.[/yellow]")
            log_action("ask_question_about_file", {"file_path": abs_filepath, **parameters}, "failure", "No question provided")
            return

        console.print(f"Analyzing folder: [cyan]{abs_filepath}[/cyan]")
        console.print(f"Question: [italic white]{question}[/italic white]")

        # Get folder contents for context
        items_for_analysis = []
        if session_context.get("last_search_results") and session_context.get("last_folder_listed_path") == abs_filepath:
            items_for_analysis = session_context["last_search_results"]
        
        if not items_for_analysis:
            items_for_analysis = list_folder_contents(abs_filepath, console) or []
        
        if not items_for_analysis:
            context_for_llm = f"The folder '{os.path.basename(abs_filepath)}' is empty."
        else:
            context_for_llm = f"The folder '{os.path.basename(abs_filepath)}' contains the following items:\n"
            for item in items_for_analysis[:15]:  # Limit to avoid token overload
                try:
                    item_abs_path = os.path.abspath(item['path'])
                    relative_path = os.path.relpath(item_abs_path, abs_filepath)
                    context_for_llm += f"- {relative_path} (type: {item['type']})\n"
                except (ValueError, KeyError):
                    context_for_llm += f"- {item.get('name', '???')} (type: {item.get('type', 'unknown')})\n"
            if len(items_for_analysis) > 15:
                context_for_llm += f"...and {len(items_for_analysis) - 15} more items.\n"

        # Ensure question is clear for folder analysis
        effective_question = question
        if question.lower() in ["what do you think about it?", "tell me about it", "analyze this", "what do you see?", "your thoughts?"]:
            effective_question = f"Analyze the contents and structure of the folder '{os.path.basename(abs_filepath)}'. What patterns do you observe? Are there opportunities for better organization?"

        llm_prompt = f"Based on the provided folder contents, answer the following question: {effective_question}"
        answer = ""
        with Live(Spinner("bouncingBar", text="Analyzing folder structure..."), console=console, transient=True):
            answer = connector.invoke_llm_for_content(main_instruction=llm_prompt, context_text=context_for_llm)
        console.print(Panel(Text(answer, justify="left"), title="[bold blue]Folder Analysis[/bold blue]", border_style="blue"))
        log_action("ask_question_about_folder", {"folder_path": abs_filepath, "question_text": question, **parameters}, "success", f"Analysis provided (length: {len(answer)})")
        return

    # Handling for regular files
    if not os.path.isfile(abs_filepath):
        console.print(f"[red]Error: Path '{abs_filepath}' is not a valid file or folder.[/red]")
        log_action("ask_question_about_file", {"file_path": filepath, "question_text": question, **parameters}, "failure", f"Invalid path: {abs_filepath}")
        return

    update_session_context("last_referenced_file_path", abs_filepath)

    if not question:
        question = Prompt.ask(f"What is your question about [cyan]{os.path.basename(abs_filepath)}[/cyan]?").strip()
    if not question:
        console.print("[yellow]No question provided.[/yellow]")
        log_action("ask_question_about_file", {"file_path": abs_filepath, "question_text": question, **parameters}, "failure", "No question provided")
        return

    console.print(f"Asking about file: [cyan]{abs_filepath}[/cyan]")
    console.print(f"Question: [italic white]{question}[/italic white]")
    
    content = get_file_content(abs_filepath, console)
    if content:
        if "PDF parsing not yet fully implemented" in content:
            console.print(f"[yellow]{content}[/yellow]")
            log_action("ask_question_about_file", {"file_path": abs_filepath, "question_text": question, **parameters}, "partial_success", "PDF not fully parsed")
            return
        
        llm_prompt = f"Based on the provided file content, answer the following question: {question}"
        answer = ""
        with Live(Spinner("bouncingBar", text="Consulting LLM for an answer..."), console=console, transient=True):
            answer = connector.invoke_llm_for_content(main_instruction=llm_prompt, context_text=content)
        console.print(Panel(Text(answer, justify="left"), title="[bold blue]LLM Answer[/bold blue]", border_style="blue"))
        log_action("ask_question_about_file", {"file_path": abs_filepath, "question_text": question, **parameters}, "success", f"Answer provided (length: {len(answer)})")
    else:
        log_action("ask_question_about_file", {"file_path": abs_filepath, "question_text": question, **parameters}, "failure", "Could not read file content")

def handle_list_folder(parameters: dict): # No connector needed
    folder_path_param = parameters.get("folder_path")
    
    # If we have context and the request was unclear (using "it", "there", etc.)
    if folder_path_param == "__FROM_CONTEXT__":
        # Try last_folder_listed_path first
        if session_context.get("last_folder_listed_path"):
            folder_path = session_context["last_folder_listed_path"]
        # If no folder context but we have a file context, try its parent directory
        elif session_context.get("last_referenced_file_path"):
            folder_path = os.path.dirname(session_context["last_referenced_file_path"])
        else:
            folder_path = None
    else:
        folder_path = resolve_contextual_path(folder_path_param, is_folder_hint=True)

    if not folder_path or folder_path_param == "__MISSING__":
        default_path = session_context.get("last_folder_listed_path")
        if not default_path and session_context.get("last_referenced_file_path"):
            default_path = os.path.dirname(session_context["last_referenced_file_path"])
        if not default_path:
            default_path = os.getcwd()
        folder_path = get_path_from_user_input("Which folder to list?", default_path=default_path, is_folder=True)
    
    abs_folder_path = os.path.abspath(folder_path)
    if not os.path.isdir(abs_folder_path):
        # Try to be helpful with suggestions
        if os.path.exists(abs_folder_path):
            console.print(f"[red]Error: '{abs_folder_path}' exists but is not a directory.[/red]")
            if os.path.isfile(abs_folder_path):
                parent_dir = os.path.dirname(abs_folder_path)
                if os.path.isdir(parent_dir):
                    console.print(f"[yellow]Did you mean to list its parent directory? '{parent_dir}'[/yellow]")
                    if Confirm.ask("List the parent directory instead?", default=True):
                        abs_folder_path = parent_dir
                        folder_path = os.path.dirname(folder_path)
                    else:
                        log_action("list_folder_contents", {"folder_path": folder_path, **parameters}, "failure", f"Invalid folder path: {abs_folder_path}")
                        return
        else:
            console.print(f"[red]Error: Path '{abs_folder_path}' does not exist.[/red]")
            # Check for minor typos or case differences
            parent_dir = os.path.dirname(abs_folder_path)
            if os.path.isdir(parent_dir):
                target_name = os.path.basename(abs_folder_path).lower()
                try:
                    siblings = os.listdir(parent_dir)
                    close_matches = [s for s in siblings if s.lower().startswith(target_name[:2]) or target_name.startswith(s.lower()[:2])]
                    if close_matches:
                        console.print("[yellow]Did you mean one of these?[/yellow]")
                        for i, match in enumerate(close_matches[:3], 1):
                            full_path = os.path.join(parent_dir, match)
                            if os.path.isdir(full_path):
                                console.print(f"{i}. [cyan]{match}/[/cyan]")
                            else:
                                console.print(f"{i}. {match}")
                        if Confirm.ask("Would you like to choose one of these?", default=True):
                            choice = IntPrompt.ask("Enter the number", choices=[str(i) for i in range(1, len(close_matches[:3])+1)])
                            abs_folder_path = os.path.join(parent_dir, close_matches[choice-1])
                            if os.path.isdir(abs_folder_path):
                                folder_path = close_matches[choice-1]
                            else:
                                console.print("[red]Selected item is not a directory.[/red]")
                                log_action("list_folder_contents", {"folder_path": folder_path, **parameters}, "failure", "Selected non-directory item")
                                return
                        else:
                            log_action("list_folder_contents", {"folder_path": folder_path, **parameters}, "failure", f"Invalid folder path: {abs_folder_path}")
                            return
                except OSError:
                    pass
            
            if not os.path.isdir(abs_folder_path):
                log_action("list_folder_contents", {"folder_path": folder_path, **parameters}, "failure", f"Invalid folder path: {abs_folder_path}")
                return
        return

    console.print(f"Listing contents of folder: [cyan]{abs_folder_path}[/cyan]")
    update_session_context("last_folder_listed_path", abs_folder_path)
    
    contents = list_folder_contents(abs_folder_path, console) # list_folder_contents prints its own errors
    if contents is not None: # It returns None on error, empty list if folder is empty
        if not contents: # Empty folder
            console.print(f"Folder [cyan]'{abs_folder_path}'[/cyan] is empty.")
            update_session_context("last_search_results", []) 
            log_action("list_folder_contents", {"folder_path": abs_folder_path, **parameters}, "success", "Folder is empty")
        else:
            table = Table(title=f"Contents of {os.path.basename(abs_folder_path)}",show_header=True, header_style="bold magenta", expand=True)
            table.add_column("Index", width=5, justify="right")
            table.add_column("Name", style="dim cyan", no_wrap=False) # Allow wrapping
            table.add_column("Type", width=10)
            
            for i, item in enumerate(contents):
                table.add_row(str(i + 1), item['name'], item['type'])
            console.print(table)
            update_session_context("last_search_results", contents) # Store listed items for context
            log_action("list_folder_contents", {"folder_path": abs_folder_path, **parameters}, "success", f"Listed {len(contents)} items")
    else: # Error occurred in list_folder_contents
        log_action("list_folder_contents", {"folder_path": abs_folder_path, **parameters}, "failure", "Error during listing (see console)")

def handle_move_item(parameters: dict): # No connector needed
    source_path_param = parameters.get("source_path")
    destination_path_param = parameters.get("destination_path")

    source_path = resolve_contextual_path(source_path_param) # Could be file or folder context
    if not source_path or source_path_param == "__MISSING__":
        source_path = get_path_from_user_input("What item to move? (Source path)", default_path=session_context.get("last_referenced_file_path") or session_context.get("last_folder_listed_path"))
    
    abs_source_path = os.path.abspath(source_path) # Ensure absolute
    if not os.path.exists(abs_source_path): # Check existence after resolving
        console.print(f"[red]Source path '{abs_source_path}' is invalid or does not exist.[/red]")
        log_action("move_item", {"source_path": source_path, "destination_path": destination_path_param, **parameters}, "failure", f"Invalid source path: {abs_source_path}")
        return
    
    if not destination_path_param or destination_path_param == "__MISSING__":
        destination_path = get_path_from_user_input(f"Where to move '{os.path.basename(abs_source_path)}'? (Destination path/folder)")
    else:
        destination_path = destination_path_param # Use LLM provided if not missing

    abs_destination_path = os.path.abspath(destination_path) # Ensure absolute

    console.print(Panel(f"Confirm move:\n  FROM: [cyan]{abs_source_path}[/cyan]\n  TO:   [cyan]{abs_destination_path}[/cyan]", title="[bold yellow]Confirm Move[/bold yellow]", border_style="yellow"))
    if Confirm.ask("Proceed with move operation?", default=False):
        if move_item(abs_source_path, abs_destination_path, console): # Pass console for rich error output from move_item
            console.print(f"[green]Successfully moved.[/green]")
            log_action("move_item", {"source_path": abs_source_path, "destination_path": abs_destination_path, **parameters}, "success")
            # Clear context as file structure has changed
            update_session_context("last_referenced_file_path", None)
            update_session_context("last_folder_listed_path", None)
            update_session_context("last_search_results", [])
        else:
            # move_item should have printed the error using the passed console
            log_action("move_item", {"source_path": abs_source_path, "destination_path": abs_destination_path, **parameters}, "failure", "Move operation failed (see console)")
    else:
        console.print("Move operation cancelled.")
        log_action("move_item", {"source_path": source_path, "destination_path": destination_path, **parameters}, "cancelled", "User cancelled move")

def handle_search_files(connector: OllamaConnector, parameters: dict):
    search_criteria = parameters.get("search_criteria")
    search_path_from_llm = parameters.get("search_path")

    if not search_criteria:
        search_criteria = Prompt.ask("What are you searching for? (e.g., 'images', 'PDFs about finance')")
    if not search_criteria: # Still no criteria
        console.print("[yellow]No search criteria provided.[/yellow]")
        log_action("search_files", parameters, "failure", "No search criteria")
        return

    # Path resolution logic from your fix
    resolved_search_path = None
    if search_path_from_llm and search_path_from_llm not in ["__MISSING__", "__FROM_CONTEXT__"]:
        if search_path_from_llm.lower() in [".", "here", "current folder", "this folder"]:
            resolved_search_path = os.path.abspath(os.getcwd())
        else:
            candidate_path = os.path.abspath(search_path_from_llm)
            if os.path.isdir(candidate_path): resolved_search_path = candidate_path
    
    if not resolved_search_path:
        if search_path_from_llm == "__FROM_CONTEXT__":
            context_folder = session_context.get("last_folder_listed_path")
            context_file_dir = os.path.dirname(session_context.get("last_referenced_file_path","")) if session_context.get("last_referenced_file_path") else None
            resolved_search_path = context_folder or context_file_dir 
        
        if not resolved_search_path: 
            default_prompt_path = session_context.get("last_folder_listed_path", os.getcwd())
            if search_path_from_llm and search_path_from_llm not in ["__MISSING__", "__FROM_CONTEXT__", ".", "here", "current folder", "this folder"]:
                 console.print(f"[yellow]Could not use '{search_path_from_llm}' as search location.[/yellow]")
            resolved_search_path = get_path_from_user_input("Where should I search?", default_path=default_prompt_path, is_folder=True)

    abs_search_path = os.path.abspath(resolved_search_path) # Ensure absolute
    if not os.path.isdir(abs_search_path):
        console.print(f"[red]Invalid or non-existent search directory: '{abs_search_path}'[/red]")
        log_action("search_files", {"search_criteria": search_criteria, "search_path": resolved_search_path, **parameters}, "failure", "Invalid search directory")
        return

    console.print(f"Searching in [cyan]{abs_search_path}[/cyan] for: [italic white]'{search_criteria}'[/italic white]")
    
    found_files = search_files_recursive(abs_search_path, search_criteria, connector, console) # Pass console
    
    if not found_files:
        console.print("[yellow]No files found matching your criteria.[/yellow]")
    else:
        console.print(f"[green]Found {len(found_files)} item(s):[/green]")
        table = Table(title="Search Results", show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Index", width=5, justify="right")
        table.add_column("Name", style="dim cyan", no_wrap=False)
        table.add_column("Path", style="green", no_wrap=False)
        for i, item in enumerate(found_files):
            table.add_row(str(i + 1), item['name'], item['path'])
        console.print(table)
    
    update_session_context("last_search_results", found_files)
    update_session_context("last_folder_listed_path", abs_search_path) # Update context to search location
    log_action("search_files", {"search_criteria": search_criteria, "search_path": abs_search_path, **parameters}, "success", f"Found {len(found_files)} items")

def handle_general_chat(connector: OllamaConnector, parameters: dict):
    original_request = parameters.get("original_request", "...")
    response = ""
    with Live(Spinner("bouncingBar", text="Thinking..."), console=console, refresh_per_second=10, transient=True):
        response = connector.invoke_llm_for_content(main_instruction=original_request)
    console.print(f"[bold magenta]CodeX says:[/bold magenta] {response}")
    # Log general chat if desired, perhaps less critical than file ops
    # log_action("general_chat", {"request": original_request, **parameters}, "success", f"LLM response length: {len(response)}")

def handle_show_activity_log(parameters: dict): # No connector    # Use default from activity_logger if not specified by LLM
    default_log_count = MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL // 5 
    count_param = parameters.get("count", default_log_count) 
    try:
        count = int(count_param)
        if count <= 0 or count > MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL : 
            count = default_log_count 
    except (ValueError, TypeError): # Catch TypeError if count_param is not int-convertible
        count = default_log_count
        console.print(f"[yellow]Invalid count '{count_param}', showing last {count} activities.[/yellow]")

    activities = get_recent_activities(count)
    if not activities:
        console.print("[yellow]Activity log is empty or could not be read.[/yellow]")
        return

    console.print(Panel(f"Recent Activity (Last {len(activities)} entries)", title="[bold blue]Activity Log[/bold blue]", border_style="blue", expand=False))
    for activity in activities:
        ts_raw = activity.get('timestamp', 'N/A')
        try:
            ts = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).strftime('%Y-%m-%d %H:%M:%S %Z') if ts_raw != 'N/A' else 'N/A'
        except ValueError:
            ts = ts_raw # Display as is if parsing failed
            
        status = activity.get('status', 'unknown')
        status_color = "green" if status == "success" else \
                       "yellow" if status in ["partial_success", "cancelled", "initiated"] else \
                       "red" # failure or other
        
        details_preview = activity.get('details', '')
        details_preview = (details_preview[:70] + '...') if details_preview and len(details_preview) > 70 else details_preview
        
        param_str_parts = []
        # Ensure parameters is a dict before iterating
        activity_params = activity.get('parameters', {}) if isinstance(activity.get('parameters'), dict) else {}
        for k, v in activity_params.items():
            v_str = str(v)
            param_str_parts.append(f"{k}: '{(v_str[:30] + '...' if len(v_str) > 30 else v_str)}'")
        params_str = ", ".join(param_str_parts)

        console.print(f"[dim]{ts}[/dim] | [bold]{activity.get('action', 'N/A')}[/bold]({params_str if params_str else ''}) | [{status_color}]{status}[/{status_color}]")
        if details_preview:
            console.print(f"  [dim]Details: {details_preview}[/dim]")
    log_action("show_activity_log", {"count": count, **parameters}, "success", f"Displayed {len(activities)} log entries")

def handle_redo_activity(connector: OllamaConnector, parameters: dict): # Pass connector
    activity_identifier = parameters.get("activity_identifier")
    if not activity_identifier:
        activity_identifier = Prompt.ask("Which activity to redo? (e.g., 'last', an index, or part of a timestamp)")
    if not activity_identifier:
        console.print("[yellow]No activity identifier provided for redo.[/yellow]")
        log_action("redo_activity", parameters, "failure", "No identifier")
        return

    activity_to_redo = get_activity_by_partial_id_or_index(activity_identifier, console)
    if not activity_to_redo:
        log_action("redo_activity", {"identifier": activity_identifier, **parameters}, "failure", "Activity not found by identifier")
        return # get_activity_by_partial_id_or_index prints its own messages

    action_to_perform = activity_to_redo.get("action")
    params_to_use = activity_to_redo.get("parameters", {}) # Ensure it's a dict

    console.print(f"Attempting to redo action: [bold cyan]{action_to_perform}[/bold cyan]")
    console.print(f"With parameters: {params_to_use}")
    if not Confirm.ask("Confirm redo?", default=True):
        console.print("Redo cancelled.")
        log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform, **parameters}, "cancelled")
        return
    
    log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform, "original_params": params_to_use, **parameters}, "initiated")

    # Dispatch to the appropriate handler
    # Need to ensure all parameters are correctly passed, including the connector if needed
    handler_func = action_handlers.get(action_to_perform) # Use the global action_handlers dict
    if handler_func:
        try:
            # Simplistic check if connector is needed based on a known list
            if action_to_perform in ["summarize_file", "ask_question_about_file", "search_files", 
                                     "propose_and_execute_organization", "general_chat", "redo_activity"]: # Redo itself might need connector if it calls LLM
                handler_func(connector, params_to_use)
            else:
                handler_func(params_to_use)
        except Exception as e:
            console.print(f"[red]Error during redo of '{action_to_perform}': {e}[/red]")
            log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform}, "failure", f"Error during execution: {e}")
    else:
        console.print(f"[red]Action '{action_to_perform}' from log is not currently redoable or handler not found.[/red]")
        log_action("redo_activity", {"identifier": activity_identifier, "original_action": action_to_perform}, "failure", "Action not redoable/handler missing")

def handle_propose_and_execute_organization(connector: OllamaConnector, parameters: dict):
    target_param = parameters.get("target_path_or_context")
    # Only use a goal if explicitly provided, otherwise leave it generic
    organization_goal = parameters.get("organization_goal")
    if not organization_goal or organization_goal.lower() == "general organization":
        organization_goal = "improve structure and organization based on item names and types"

    items_for_analysis = []
    base_analysis_path = None
    source_description = ""

    # First, handle the case when target_param is __FROM_CONTEXT__
    if target_param == "__FROM_CONTEXT__":
        # If we have a last_folder_listed_path, that's our most reliable context
        # This is often set by list_folder_contents or search_files
        if session_context.get("last_folder_listed_path"):
            base_analysis_path = session_context["last_folder_listed_path"]
            
            # If this last_folder was from a list operation, it will have last_search_results
            # Use those results if they match this folder (are its contents)
            if session_context.get("last_search_results"):
                # Check if the results are children of this folder
                sample_paths = [item['path'] for item in session_context["last_search_results"][:5] if 'path' in item]
                if sample_paths and all(os.path.dirname(p) == base_analysis_path for p in sample_paths):
                    items_for_analysis = session_context["last_search_results"]
                else:
                    # Results are from a different operation, get fresh folder contents
                    items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            else:
                # No results cached, get fresh folder contents
                items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            
            source_description = f"folder '{os.path.basename(base_analysis_path)}' (from context)"

        # If no last_folder_listed_path but we have search results, use those
        elif session_context.get("last_search_results"):
            items_for_analysis = session_context["last_search_results"]
            
            # Try to infer base path from search results
            paths = [item['path'] for item in items_for_analysis if 'path' in item]
            if paths:
                try:
                    # First try to find a common parent directory
                    base_analysis_path = os.path.commonpath(paths)
                    # If that's not a directory (might be a common prefix), use parent of first item
                    if not os.path.isdir(base_analysis_path):
                        base_analysis_path = os.path.dirname(paths[0])
                except ValueError:  # Paths on different drives
                    base_analysis_path = os.path.dirname(paths[0])  # Use first item's parent as base
            
            source_description = "items from your last search/listing"

        # No usable context found, prompt user
        if not base_analysis_path or not items_for_analysis:
            console.print("[yellow]No clear context available. Please specify a folder to organize.[/yellow]")
            base_analysis_path = get_path_from_user_input("Which folder do you want to organize?", 
                                                       default_path=os.getcwd(), 
                                                       is_folder=True)
            items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            source_description = f"folder '{os.path.basename(base_analysis_path)}'"

    # Handle explicit path specified by user/LLM
    elif target_param and target_param != "__MISSING__":
        try:
            candidate_path = os.path.abspath(target_param)
            if os.path.isdir(candidate_path):
                base_analysis_path = candidate_path
                items_for_analysis = list_folder_contents(base_analysis_path, console) or []
                source_description = f"folder '{os.path.basename(base_analysis_path)}'"
            else:
                console.print(f"[red]Error: Path '{target_param}' is not a valid directory.[/red]")
                
                # Try to be helpful by suggesting the parent directory if it exists
                parent_dir = os.path.dirname(candidate_path)
                if os.path.isdir(parent_dir):
                    console.print(f"[yellow]However, its parent directory exists: '{parent_dir}'[/yellow]")
                    if Confirm.ask("Would you like to organize that directory instead?", default=True):
                        base_analysis_path = parent_dir
                        items_for_analysis = list_folder_contents(base_analysis_path, console) or []
                        source_description = f"folder '{os.path.basename(base_analysis_path)}'"
                    else:
                        # User declined, let them specify a different path
                        base_analysis_path = get_path_from_user_input("Which folder do you want to organize?",
                                                                    default_path=os.getcwd(),
                                                                    is_folder=True)
                        items_for_analysis = list_folder_contents(base_analysis_path, console) or []
                        source_description = f"folder '{os.path.basename(base_analysis_path)}'"
                else:
                    # No helpful parent directory exists, ask user
                    console.print("[red]The specified path is invalid and its parent directory doesn't exist.[/red]")
                    base_analysis_path = get_path_from_user_input("Please provide a valid folder path to organize:",
                                                                default_path=os.getcwd(),
                                                                is_folder=True)
                    items_for_analysis = list_folder_contents(base_analysis_path, console) or []
                    source_description = f"folder '{os.path.basename(base_analysis_path)}'"
        except Exception as e:
            console.print(f"[red]Error resolving path '{target_param}': {str(e)}[/red]")
            base_analysis_path = get_path_from_user_input("Please provide a valid folder path to organize:",
                                                        default_path=os.getcwd(),
                                                        is_folder=True)
            items_for_analysis = list_folder_contents(base_analysis_path, console) or []
            source_description = f"folder '{os.path.basename(base_analysis_path)}'"

    # Handle case where no target was specified
    else:
        base_analysis_path = get_path_from_user_input("Which folder do you want to organize?",
                                                    default_path=os.getcwd(),
                                                    is_folder=True)
        items_for_analysis = list_folder_contents(base_analysis_path, console) or []
        source_description = f"folder '{os.path.basename(base_analysis_path)}'"

    # Final validation of path and items
    if not base_analysis_path or not os.path.isdir(base_analysis_path):
        console.print(f"[red]Cannot proceed: No valid directory identified for organization.[/red]")
        log_action("propose_and_execute_organization", parameters, "failure", "No valid directory")
        return

    if not items_for_analysis:
        console.print(f"[yellow]No items found in {source_description} to organize.[/yellow]")
        log_action("propose_and_execute_organization", {**parameters, "resolved_target": base_analysis_path}, 
                  "failure", "No items to organize")
        return

    # Make sure base_analysis_path is absolute for the LLM's planning
    abs_base_analysis_path = os.path.abspath(base_analysis_path)
    console.print(f"Analyzing {source_description} (goal: '{organization_goal}') to propose an organization plan...")

    # Create item summary for LLM, using relative paths where possible for clearer planning
    item_summary_list = []
    for item in items_for_analysis[:50]:  # Limit items for prompt
        try:
            item_abs_path = os.path.abspath(item['path'])
            relative_path = os.path.relpath(item_abs_path, abs_base_analysis_path)
            item_summary_list.append(f"- \"{relative_path}\" (type: {item['type']})")
        except (ValueError, KeyError):
            # Fallback if relative path fails (different drives) or path key missing
            item_summary_list.append(f"- \"{item.get('name', '???')}\" (type: {item.get('type', 'unknown')})")
            
    item_summary_for_llm = "\n".join(item_summary_list)
    if len(items_for_analysis) > 50:
        item_summary_for_llm += f"\n... and {len(items_for_analysis) - 50} more items."

    # Get organization plan from LLM
    proposed_actions_json = None
    with Live(Spinner("bouncingBar", text="Asking LLM to generate organization plan..."), 
             console=console, transient=True):
        proposed_actions_json = connector.generate_organization_plan_llm(
            item_summary_for_llm, organization_goal, abs_base_analysis_path)

    # Handle planning failures
    if proposed_actions_json is None:
        console.print("[red]Failed to generate an organization plan. LLM might have returned invalid data or timed out.[/red]")
        log_action("propose_and_execute_organization", {**parameters, "resolved_target": abs_base_analysis_path},
                  "failure", "LLM plan gen failed/invalid JSON")
        return
    if not proposed_actions_json:  # Empty list []
        console.print("[yellow]LLM proposed no actions. Items might be well-organized or goal unclear.[/yellow]")
        log_action("propose_and_execute_organization", {**parameters, "resolved_target": abs_base_analysis_path},
                  "success", "LLM proposed no actions")
        return

    # Present the plan
    console.print(Panel("[bold blue]Proposed Organization Plan[/bold blue]", expand=False))
    plan_table = Table(title="Actions", show_header=True, header_style="bold magenta")
    plan_table.add_column("Step", justify="right")
    plan_table.add_column("Action")
    plan_table.add_column("Details")
    
    valid_plan_actions = []
    has_invalid_actions = False

    # Validate and process each action
    for i, action_data in enumerate(proposed_actions_json):
        action_type = action_data.get("action_type")
        details_str = ""
        is_valid = True
        
        # Validate CREATE_FOLDER actions
        if action_type == "CREATE_FOLDER":
            path = action_data.get("path")
            if not (path and isinstance(path, str) and os.path.isabs(path)):
                details_str = f"[red]Invalid/Relative path: {path}[/red]"
                is_valid = False
            elif not path.startswith(abs_base_analysis_path):
                details_str = f"[red]Path is outside target directory: {path}[/red]"
                is_valid = False
            else:
                details_str = f"Path: [cyan]{path}[/cyan]"

        # Validate MOVE_ITEM actions
        elif action_type == "MOVE_ITEM":
            source = action_data.get("source")
            dest = action_data.get("destination")
            
            if not (source and isinstance(source, str) and os.path.isabs(source) and
                    dest and isinstance(dest, str) and os.path.isabs(dest)):
                details_str = f"[red]Invalid paths. S: {source}, D: {dest}[/red]"
                is_valid = False
            elif source == dest:
                details_str = f"[red]Source and destination are identical: {source}[/red]"
                is_valid = False
            # Ensure source is within base path
            elif not source.startswith(abs_base_analysis_path):
                details_str = f"[red]Source is outside target directory: {source}[/red]"
                is_valid = False
            # Destination must be within base path or a subfolder
            elif not dest.startswith(abs_base_analysis_path):
                details_str = f"[red]Destination is outside target directory: {dest}[/red]"
                is_valid = False
            else:
                details_str = f"From: [cyan]{source}[/cyan]\nTo:   [cyan]{dest}[/cyan]"

        else:
            details_str = f"[red]Unknown action: {action_type}[/red] - {action_data}"
            is_valid = False

        plan_table.add_row(
            str(i+1),
            action_type if is_valid else f"[red]{action_type}[/red]",
            Text.from_markup(details_str)
        )
        
        if is_valid:
            valid_plan_actions.append(action_data)
        else:
            has_invalid_actions = True

    # Display plan and warnings
    console.print(plan_table)
    if has_invalid_actions:
        console.print("[bold red]Warning: Plan has invalid actions (marked red), they will be skipped.[/bold red]")
    if not valid_plan_actions:
        console.print("[yellow]No valid actions in the proposed plan to execute.[/yellow]")
        log_action("propose_and_execute_organization", {**parameters, "resolved_target": abs_base_analysis_path},
                  "failure", "No valid actions in plan")
        return

    # Log the plan proposal
    log_action("propose_and_execute_organization", {
        "goal": organization_goal,
        "source_desc": source_description,
        "raw_plan_count": len(proposed_actions_json),
        "valid_actions": len(valid_plan_actions),
        **parameters
    }, "plan_proposed")

    # Execute the plan if confirmed
    if Confirm.ask(f"Execute these {len(valid_plan_actions)} valid actions?", default=False):
        console.print(f"\n[bold]Executing {len(valid_plan_actions)} organization actions...[/bold]")
        exec_ok = 0
        exec_fail = 0
        
        with Progress(console=console, transient=False) as progress:
            exec_task = progress.add_task("[cyan]Processing...", total=len(valid_plan_actions))
            
            for i, action_data in enumerate(valid_plan_actions):
                action_type = action_data["action_type"]
                progress.update(
                    exec_task,
                    description=f"[cyan]Step {i+1}/{len(valid_plan_actions)}: {action_type}..."
                )
                success = False
                log_params = action_data.copy()

                # Execute CREATE_FOLDER actions
                if action_type == "CREATE_FOLDER":
                    path = action_data["path"]
                    try:
                        if os.path.exists(path) and os.path.isdir(path):
                            console.print(f"  [dim]Exists: '{path}'. Skipping creation.[/dim]")
                            success = True
                        else:
                            os.makedirs(path, exist_ok=True)
                            console.print(f"  [green]Created:[/green] [cyan]{path}[/cyan]")
                            success = True
                    except Exception as e:
                        console.print(f"  [red]Failed CREATE_FOLDER '{path}': {e}[/red]")

                # Execute MOVE_ITEM actions
                elif action_type == "MOVE_ITEM":
                    source = action_data["source"]
                    dest = action_data["destination"]
                    if not os.path.exists(source):
                        console.print(f"  [red]Source '{source}' gone. Skipping move.[/red]")
                    elif move_item(source, dest, console):  # move_item handles its own error printing
                        console.print(
                            f"  [green]Moved:[/green] [cyan]{os.path.basename(source)}[/cyan] -> [cyan]{dest}[/cyan]")
                        success = True

                # Update progress and log results
                if success:
                    exec_ok += 1
                    log_action(f"exec_org_{action_type.lower()}", log_params, "success")
                else:
                    exec_fail += 1
                    log_action(f"exec_org_{action_type.lower()}", log_params, "failure")
                progress.update(exec_task, advance=1)
            
            progress.update(exec_task, description=f"[green]Execution finished.[/green]")

        # Final summary and cleanup
        console.print(f"\n[bold green]Organization Summary:[/bold green]")
        console.print(f"  Success: {exec_ok}, Failed: {exec_fail}")
        
        # Clear context after organization
        update_session_context("last_referenced_file_path", None)
        update_session_context("last_folder_listed_path", None)
        update_session_context("last_search_results", [])
        
        log_action("execute_organization_plan", {
            "executed": exec_ok,
            "failed": exec_fail,
            **parameters
        }, "completed")

    else:
        console.print("Organization plan execution cancelled.")
        log_action("execute_organization_plan", 
                  {"valid_actions_count": len(valid_plan_actions), **parameters},
                  "cancelled")


# --- Main Application Logic ---
action_handlers = { # Define this globally or ensure it's in scope for main and redo_activity
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
    
    # Display ASCII logo with padding
    welcome_text = Align.center(APP_LOGO)
    console.print(welcome_text)
    
    # Create status panel
    status_items = []
    conn_ok, model_ok, _ = connector.check_connection_and_model()
    
    if not conn_ok:
        console.print(Panel(f"{ICONS['error']} Could not connect to Ollama", 
                          style="danger", box=ROUNDED))
        return False
    
    status_items.append(f"{ICONS['success']} Connected to Ollama")
    
    if not model_ok:
        console.print(Panel(f"{ICONS['error']} Model '{OLLAMA_MODEL}' not found", 
                          style="danger", box=ROUNDED))
        return False
    
    status_items.append(f"{ICONS['success']} Model: [bold cyan]{OLLAMA_MODEL}[/bold cyan]")
    
    # Status panel with all checks
    status_text = "\n".join(status_items)
    console.print(Panel(status_text, 
                       title="[panel.title]System Status[/panel.title]",
                       border_style="panel.border",
                       box=ROUNDED))
    
    # Help hint
    help_text = (
        f"\n{ICONS['info']} Type [prompt]help[/prompt] for available commands, or just ask your question"
        f"\n{ICONS['info']} Type [prompt]quit[/prompt] to exit"
    )
    console.print(Padding(help_text, (1, 0)))
    console.print(Padding("=" * console.width, (1, 0)))
    return True

def resolve_indexed_reference(user_input_lower: str, parameters: dict):
    if parameters.get("file_path") or parameters.get("folder_path"): return False # Path already found by LLM
    # Try to match "item X", "number X", "file X", "X" (if it's just a number), "Xrd one"
    match = re.search(r"(?:item\s*|number\s*|file\s*|#\s*)?(\d+)(?:st|nd|rd|th)?(?:\s*one)?", user_input_lower)
    
    if match and session_context.get("last_search_results"):
        try:
            item_index_str = match.group(1)
            item_index = int(item_index_str) - 1 # 1-based from user to 0-based
            
            # Heuristic: if the number is the ONLY thing in the input, it's more likely an index.
            # Or if it's preceded/followed by keywords.
            is_likely_index_ref = (user_input_lower.strip() == item_index_str) or \
                                  (match.group(0) in user_input_lower) # Ensure full matched group is part of input

            if is_likely_index_ref and 0 <= item_index < len(session_context["last_search_results"]):
                referenced_item = session_context["last_search_results"][item_index]
                current_action_by_llm = parameters.get("action", "")
                
                # Default action based on item type if no strong action from LLM
                if referenced_item["type"] == "file":
                    parameters["file_path"] = referenced_item["path"]
                    # If LLM suggested a file action, or user mentions it, or no action, assume file action
                    if not current_action_by_llm or any(k in current_action_by_llm for k in ["ask", "summarize"]) or \
                       any(k in user_input_lower for k in ["ask", "tell me about", "summarize", "what is in"]):
                        
                        is_ask_intent = ("ask" in current_action_by_llm or \
                                         any(k in user_input_lower for k in ["ask", "tell me about", "what is in", "question"]))

                        if is_ask_intent and not parameters.get("question_text"):
                            # Try to extract question by removing the matched index part and action words
                            question_part = user_input_lower.replace(match.group(0), "", 1).strip()
                            for aw in ["summarize", "ask", "tell me about", "what is", "explain", "contents of"]:
                                question_part = re.sub(r'\b' + re.escape(aw) + r'\b', '', question_part, flags=re.IGNORECASE).strip()
                            parameters["question_text"] = question_part if question_part else f"Tell me more about {os.path.basename(referenced_item['name'])}"
                        parameters["action"] = "ask_question_about_file" if is_ask_intent else "summarize_file"
                
                elif referenced_item["type"] == "folder":
                    parameters["folder_path"] = referenced_item["path"]
                    parameters["action"] = "list_folder_contents" # Default for folder
                return True # Parameters updated
        except (ValueError, TypeError, AttributeError): # AttributeError if last_search_results is None
            pass 
    return False


def main():
    load_session_context()
    connector = OllamaConnector()
    if not print_startup_message(connector):
        save_session_context(); return

    try:
        while True:
            user_input_original = Prompt.ask("[bold green]You[/bold green]", default="").strip()
            if not user_input_original: continue
            if user_input_original.lower() in ['quit', 'exit', 'bye', 'q']:
                console.print("[bold yellow]Exiting AI Assistant. Goodbye![/bold yellow]"); break
            
            if user_input_original.lower() == 'help':
                console.print("\n[bold]Example Commands:[/bold]\n"
                              "  - summarize \"path/file.txt\"\n"
                              "  - what is in \"doc.docx\" about project alpha?\n"
                              "  - list contents of \"C:/my_folder\" (or 'list item 3' after a search)\n"
                              "  - search for images in . (current dir)\n"
                              "  - search for python scripts containing 'db' in \"~/projects\"\n"
                              "  - move \"old_file.txt\" to \"archive/old_file.txt\"\n"
                              "  - organize this folder by type (after listing a folder)\n"
                              "  - organize \"C:/Downloads\" by file extension\n"
                              "  - show my last 5 activities\n"
                              "  - redo last search\n"
                              "  - redo task 2 (refers to 2nd most recent logged activity)\n" + "-" * console.width)
                continue

            parsed_command = None
            with Live(Spinner("dots", text="Understanding your request..."), console=console, refresh_per_second=10, transient=True):
                parsed_command = connector.get_intent_and_entities(user_input_original, session_context)

            if not parsed_command or "action" not in parsed_command:
                console.print("[yellow]Sorry, I had trouble understanding that. Could you rephrase?[/yellow]")
                log_action("nlu_failure", {"input": user_input_original}, "failure", "LLM could not parse intent")
                continue

            action = parsed_command.get("action")
            parameters = parsed_command.get("parameters", {})
            
            # This updates 'parameters' and potentially 'action' in-place if an index ref is resolved
            resolve_indexed_reference(user_input_original.lower(), parameters)
            action = parameters.get("action", action) # Get updated action

            add_to_command_history(action, parameters)

            handler_func = action_handlers.get(action)
            if handler_func:
                if action in ["summarize_file", "ask_question_about_file", "search_files", 
                              "propose_and_execute_organization", "general_chat", "redo_activity"]:
                    handler_func(connector, parameters)
                else: # For list_folder, move_item, show_activity_log (no connector needed)
                    handler_func(parameters)
            elif action == "unknown":
                original_req = parameters.get("original_request", user_input_original)
                console.print(f"[yellow]I'm not sure how to handle: '{original_req}'. Try 'help'.[/yellow]")
                if parameters.get("error"): console.print(f"[dim]NLU hint: {parameters['error']}[/dim]")
                log_action("unknown_command", {"input": original_req, **parameters}, "failure", parameters.get("error", "Unrecognized"))
            else: # Action recognized by NLU but no handler
                console.print(f"[yellow]Action '[bold]{action}[/bold]' is recognized but not implemented yet.[/yellow]")
                log_action("not_implemented", {"action": action, "input": user_input_original, **parameters}, "pending")

    except KeyboardInterrupt: console.print("\n[bold yellow]Exiting AI Assistant. Goodbye![/bold yellow]")
    except Exception: # Catch-all for unexpected errors
        console.print(f"[bold red]A critical unexpected error occurred in the main loop![/bold red]")
        console.print_exception(show_locals=True, width=console.width) # Show locals for better debugging
    finally: save_session_context()

if __name__ == '__main__':
    main()