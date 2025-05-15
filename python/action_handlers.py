# python/action_handlers.py

import os
import shutil
import time
import json # For loading activity log if needed for redo
import datetime # Added import for datetime

# PDF and DOCX parsing
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from docx import Document
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False

# Local project imports
from . import cli_ui
from . import cli_constants
# from . import path_resolver # No longer directly called by handlers for resolve_path
from . import fs_utils
import activity_logger # For logging results

from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.panel import Panel
from rich.box import ROUNDED

# --- Configuration for Summarization ---
MAX_CONTENT_LENGTH_FOR_SUMMARY = 20000  # Characters
MAX_ITEMS_TO_DISPLAY_IN_LIST = 50

# === Helper for Content Extraction ===
def _extract_file_content(resolved_path: str, file_extension: str) -> tuple[str, str, str | None]:
    """
    Extracts content from a file based on its extension.
    Assumes resolved_path is an absolute, existing file path.
    """
    file_content = ""
    content_source = "unknown"
    error_message = None

    try:
        if file_extension == ".pdf":
            if not PYMUPDF_AVAILABLE:
                error_message = "PyMuPDF library not found. Cannot parse .pdf files. Please run: pip install pymupdf"
                return "", "pdf_parsing_skipped_dependency", error_message
            content_source = "pdf_parsed"
            doc = fitz.open(resolved_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                file_content += page.get_text("text")
            doc.close()
            if not file_content.strip():
                error_message = f"Extracted no text from PDF: {os.path.basename(resolved_path)}. The PDF might be image-based or protected."
        
        elif file_extension == ".docx":
            if not PYTHON_DOCX_AVAILABLE:
                error_message = "python-docx library not found. Cannot parse .docx files. Please run: pip install python-docx"
                return "", "docx_parsing_skipped_dependency", error_message
            content_source = "docx_parsed"
            doc = Document(resolved_path)
            for para in doc.paragraphs:
                file_content += para.text + "\n"
            if not file_content.strip():
                error_message = f"Extracted no text from DOCX: {os.path.basename(resolved_path)}."

        elif file_extension in [".txt", ".md", ".py", ".json", ".html", ".css", ".js", ".log", ".csv", ".xml", ".yaml", ".yml", ".sh", ".bat", ".ps1", ".c", ".cpp", ".java", ".go", ".rb", ".php"]:
            content_source = f"{file_extension}_text_file_read"
            with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
                file_content = f.read()
            if not file_content.strip():
                error_message = f"File {os.path.basename(resolved_path)} appears to be empty."
        else:
            content_source = "unsupported_type_no_extraction"
            error_message = f"File type '{file_extension}' is not directly supported for content extraction."

    except fitz.fitz.FitxError as e_pdf:
        error_message = f"Error processing PDF file {os.path.basename(resolved_path)}: {e_pdf}. It might be corrupted or password-protected."
        content_source = "pdf_processing_error"
    except Exception as e_extraction:
        error_message = f"An unexpected error occurred during content extraction of {os.path.basename(resolved_path)}: {str(e_extraction)}"
        content_source = "extraction_error"

    if error_message:
        cli_ui.print_warning(error_message, "Content Extraction Issue")
        
    return file_content, content_source, error_message


# === Action Handlers ===
# IMPORTANT ASSUMPTION: All path parameters (file_path, folder_path, search_path, etc.)
# in the 'parameters' dict are ALREADY RESOLVED TO ABSOLUTE PATHS and basic validation
# (e.g., existence for sources, type matching for directory/file) has been performed
# by the nlu_processor.py before these handlers are called.
# Handlers should still check for None and perform their specific logic.

def handle_summarize_file(connector, parameters: dict):
    """Handles the summarization of a file."""
    activity_logger.log_action("summarize_file", parameters, "pending_execution", "Attempting to summarize file.")
    
    # Parameter 'file_path' is expected to be an absolute, validated path from nlu_processor
    resolved_path = parameters.get("file_path")

    if not resolved_path:
        cli_ui.print_error("File path is missing for summarization.", "Summarization Error")
        activity_logger.update_last_activity_status("failure", "Missing resolved file_path parameter.")
        return

    # nlu_processor should have ensured this is a file. Handler can re-verify if critical.
    if not os.path.isfile(resolved_path):
        cli_ui.print_error(f"Provided path is not a file: {resolved_path}", "File Error")
        activity_logger.update_last_activity_status("failure", f"Path is not a file: {resolved_path}")
        return

    file_extension = os.path.splitext(resolved_path)[1].lower()
    cli_ui.console.print(f"{cli_constants.ICONS.get('file','📄')} Attempting to summarize: [filepath]{resolved_path}[/filepath]")

    file_content, content_source, extraction_error = _extract_file_content(resolved_path, file_extension)

    if not file_content.strip() and extraction_error:
        llm_input_content = f"I attempted to summarize the file at path '{resolved_path}'. It is a '{file_extension}' file. However, I encountered an issue extracting its content. The error was: '{extraction_error}'. Can you provide a generic statement or acknowledge this based on the filename and type, or ask the user for more information if needed?"
    elif not file_content.strip():
        llm_input_content = f"The file at path '{resolved_path}' (type: '{file_extension}') appears to be empty or its content could not be read for direct summarization. Please provide a general comment or ask for clarification."
    else:
        llm_input_content = file_content

    if len(llm_input_content) > MAX_CONTENT_LENGTH_FOR_SUMMARY:
        llm_input_content = llm_input_content[:MAX_CONTENT_LENGTH_FOR_SUMMARY] + "\n\n[Content truncated due to length]"
        cli_ui.print_info("Content was truncated for LLM summary due to length.", "Content Truncation")

    summary_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Asking LLM to summarize '{os.path.basename(resolved_path)}' ({content_source})...[/spinner_style]"
    with Live(Spinner("dots", text=summary_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        summary_result = connector.get_summary(llm_input_content, resolved_path)

    if summary_result and summary_result.get("summary_text"):
        cli_ui.print_panel_message("LLM Summary", summary_result["summary_text"], "info", cli_constants.ICONS.get('summary','📝'))
        activity_logger.update_last_activity_status("success", "Summary generated.", result_data={"summary_preview": summary_result["summary_text"][:200]+"..."})
    elif summary_result and summary_result.get("error"):
        cli_ui.print_error(f"LLM could not generate summary: {summary_result['error']}", "Summarization Failed")
        activity_logger.update_last_activity_status("failure", f"LLM error during summary: {summary_result['error']}")
    else:
        cli_ui.print_error("LLM did not return a valid summary or error.", "Summarization Failed")
        activity_logger.update_last_activity_status("failure", "LLM no valid response for summary")


def handle_ask_question_about_file(connector, parameters: dict):
    """Handles asking a question about a file's content."""
    activity_logger.log_action("ask_question_about_file", parameters, "pending_execution", "Attempting to answer question about file.")

    # Parameter 'file_path' is expected to be an absolute, validated path from nlu_processor
    resolved_path = parameters.get("file_path")
    question = parameters.get("question")

    if not resolved_path or not question:
        cli_ui.print_error("File path or question is missing.", "Q&A Error")
        activity_logger.update_last_activity_status("failure", "Missing resolved file_path or question.")
        return

    if not os.path.isfile(resolved_path):
        cli_ui.print_error(f"Provided path is not a file: {resolved_path}", "File Error")
        activity_logger.update_last_activity_status("failure", f"Path for Q&A is not a file: {resolved_path}")
        return

    file_extension = os.path.splitext(resolved_path)[1].lower()
    cli_ui.console.print(f"{cli_constants.ICONS.get('question','❓')} Finding answer for '{question[:50]}...' in [filepath]{resolved_path}[/filepath]")

    file_content, content_source, extraction_error = _extract_file_content(resolved_path, file_extension)
    
    if not file_content.strip() and extraction_error:
        llm_input_content = f"I was asked the question: '{question}' about the file at path '{resolved_path}' (type: '{file_extension}'). I encountered an error trying to read its content: '{extraction_error}'. Please respond appropriately, perhaps indicating you cannot answer without the content."
    elif not file_content.strip():
        llm_input_content = f"I was asked the question: '{question}' about the file at path '{resolved_path}' (type: '{file_extension}'). The file appears to be empty or its content could not be read. Please respond appropriately."
    else:
        llm_input_content = file_content
    
    if len(llm_input_content) > MAX_CONTENT_LENGTH_FOR_SUMMARY:
        llm_input_content = llm_input_content[:MAX_CONTENT_LENGTH_FOR_SUMMARY] + "\n\n[Content truncated due to length]"
        cli_ui.print_info("Content was truncated for LLM Q&A due to length.", "Content Truncation")

    qna_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Asking LLM about '{os.path.basename(resolved_path)}' ({content_source})...[/spinner_style]"
    with Live(Spinner("dots", text=qna_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        answer_result = connector.ask_question_about_text(llm_input_content, question, resolved_path)

    if answer_result and answer_result.get("answer_text"):
        cli_ui.print_panel_message("LLM Answer", answer_result["answer_text"], "info", cli_constants.ICONS.get('answer','💡'))
        activity_logger.update_last_activity_status("success", "Answer generated.", result_data={"answer_preview": answer_result["answer_text"][:200]+"..."})
    elif answer_result and answer_result.get("error"):
        cli_ui.print_error(f"LLM could not provide an answer: {answer_result['error']}", "Q&A Failed")
        activity_logger.update_last_activity_status("failure", f"LLM error during Q&A: {answer_result['error']}")
    else:
        cli_ui.print_error("LLM did not return a valid answer or error.", "Q&A Failed")
        activity_logger.update_last_activity_status("failure", "LLM no valid response for Q&A")


def handle_list_folder_contents(parameters: dict):
    """Lists contents of a specified folder."""
    activity_logger.log_action("list_folder_contents", parameters, "pending_execution", "Attempting to list folder contents.")
    
    # Parameter 'folder_path' is expected to be an absolute, validated path from nlu_processor
    resolved_path = parameters.get("folder_path")

    if not resolved_path:
        cli_ui.print_error("Folder path is missing for listing.", "Directory Error")
        activity_logger.update_last_activity_status("failure", "Missing resolved folder_path for list.")
        return

    if not os.path.isdir(resolved_path):
        cli_ui.print_error(f"Provided path is not a directory: {resolved_path}", "Directory Error")
        activity_logger.update_last_activity_status("failure", f"Path for list is not a directory: {resolved_path}")
        return

    try:
        cli_ui.console.print(f"{cli_constants.ICONS.get('folder','📁')} Contents of [filepath]{resolved_path}[/filepath]:")
        items, error = fs_utils.list_folder_contents_simple(resolved_path)

        if error:
            cli_ui.print_error(f"Error listing folder: {error}", "Listing Error")
            activity_logger.update_last_activity_status("failure", f"Error listing folder: {error}")
            return
        
        if not items:
            cli_ui.print_info("The folder is empty.", "Empty Folder")
            activity_logger.update_last_activity_status("success", "Folder listed (empty).", result_data={"path": resolved_path, "count": 0})
            from . import session_manager
            session_manager.update_session_context("last_folder_listed_path", resolved_path)
            session_manager.update_session_context("last_listed_items", [])
            return

        table = Table(title=None, show_header=True, header_style="table.header", box=ROUNDED)
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Name", style="dim_text", min_width=20, overflow="fold")
        table.add_column("Type", width=10)
        table.add_column("Size", justify="right", width=12)
        table.add_column("Modified", width=20)

        display_count = 0
        for i, item in enumerate(items):
            if display_count >= MAX_ITEMS_TO_DISPLAY_IN_LIST and len(items) > MAX_ITEMS_TO_DISPLAY_IN_LIST + 5 :
                remaining_items = len(items) - display_count
                table.add_row("...", f"... and {remaining_items} more items ...", "", "", "")
                break
            
            item_type_icon = cli_constants.ICONS.get('folder','📁') if item['type'] == 'directory' else cli_constants.ICONS.get('file','📄')
            name_style = "filepath" if item['type'] == 'directory' else "dim_text"
            name_display = Text(f"{item_type_icon} {item['name']}", style=name_style)

            table.add_row(
                str(i + 1),
                name_display,
                item['type'].capitalize(),
                item['size_readable'],
                item['modified_readable']
            )
            display_count += 1
        
        cli_ui.console.print(table)
        activity_logger.update_last_activity_status("success", f"Listed {len(items)} items.", result_data={"path": resolved_path, "count": len(items)})
        
        from . import session_manager
        session_manager.update_session_context("last_folder_listed_path", resolved_path)
        session_manager.update_session_context("last_listed_items", items)

    except Exception as e:
        cli_ui.print_error(f"An unexpected error occurred while listing folder: {e}", "Listing Error")
        cli_ui.console.print_exception(max_frames=2)
        activity_logger.update_last_activity_status("failure", f"Unexpected listing error: {e}")


def handle_search_files(connector, parameters: dict):
    """Searches for files based on criteria."""
    activity_logger.log_action("search_files", parameters, "pending_execution", "Attempting to search files.")
    
    search_criteria = parameters.get("search_criteria", "").strip()
    # Parameter 'search_path' is expected to be an absolute, validated directory path from nlu_processor
    resolved_search_path = parameters.get("search_path")

    if not resolved_search_path:
        cli_ui.print_error("Search path parameter 'search_path' is missing or invalid.", "Search Path Error")
        activity_logger.update_last_activity_status("failure", "Missing or invalid resolved search_path.")
        return

    if not os.path.isdir(resolved_search_path):
        cli_ui.print_error(f"Search path is not a directory: {resolved_search_path}", "Search Path Error")
        activity_logger.update_last_activity_status("failure", f"Search path not a directory: {resolved_search_path}")
        return

    if not search_criteria or search_criteria == "__MISSING__":
        cli_ui.print_error("Search criteria are missing.", "Search Error")
        # This case might also be handled by nlu_processor prompting the user.
        # If it reaches here, it's a fallback.
        activity_logger.update_last_activity_status("failure", "Missing search criteria.")
        return

    cli_ui.console.print(f"{cli_constants.ICONS.get('search','🔍')} Searching in [filepath]{resolved_search_path}[/filepath] for: '[highlight]{search_criteria}[/highlight]'")
    
    found_items = []
    search_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Searching files...[/spinner_style]"

    with Live(Spinner("dots", text=search_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        time.sleep(0.1) 
        # TODO: Replace with a more robust search from fs_utils, potentially using fs_utils.search_files_recursive
        # This current search is very basic (non-recursive name check).
        for entry in os.scandir(resolved_search_path):
            # Allow searching for "image" or "document" types, or specific extensions
            is_match = False
            entry_name_lower = entry.name.lower()
            search_criteria_lower = search_criteria.lower()

            if search_criteria_lower in entry_name_lower: # Basic name matching
                is_match = True
            elif fs_utils.is_file_type_match(entry.path, search_criteria_lower, entry.is_file()): # Type matching
                is_match = True
            
            if is_match:
                stat = entry.stat()
                found_items.append({
                    "name": entry.name,
                    "path": entry.path, # This is already absolute from os.scandir
                    "type": "directory" if entry.is_dir() else "file",
                    "size_bytes": stat.st_size,
                    "size_readable": fs_utils.bytes_to_readable(stat.st_size),
                    "modified_timestamp": stat.st_mtime,
                    "modified_readable": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                })
    
    if not found_items:
        cli_ui.print_info(f"No items found matching '[highlight]{search_criteria}[/highlight]' in [filepath]{resolved_search_path}[/filepath].", "Search Complete")
        activity_logger.update_last_activity_status("success", "Search complete (no results).", result_data={"path": resolved_search_path, "criteria": search_criteria, "count": 0})
        from . import session_manager
        session_manager.update_session_context("last_search_results", [])
        return

    cli_ui.print_success(f"Found {len(found_items)} item(s) matching [highlight]'{search_criteria}'[/highlight]:", "Search Results")
    
    table = Table(title=None, show_header=True, header_style="table.header", box=ROUNDED)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", style="dim_text", min_width=30, overflow="fold")
    table.add_column("Path", style="filepath", min_width=40, overflow="fold")
    table.add_column("Type", width=10)

    display_count = 0
    for i, item in enumerate(found_items):
        if display_count >= MAX_ITEMS_TO_DISPLAY_IN_LIST and len(found_items) > MAX_ITEMS_TO_DISPLAY_IN_LIST + 5:
            remaining_items = len(found_items) - display_count
            table.add_row("...", f"... and {remaining_items} more items ...", "", "")
            break

        item_type_icon = cli_constants.ICONS.get('folder','📁') if item['type'] == 'directory' else cli_constants.ICONS.get('file','📄')
        name_display = Text(f"{item_type_icon} {item['name']}")
        path_display = Text(item['path'], style="filepath")

        table.add_row(
            str(i + 1),
            name_display,
            path_display,
            item['type'].capitalize()
        )
        display_count +=1

    cli_ui.console.print(table)
    activity_logger.update_last_activity_status("success", f"Search found {len(found_items)} items.", result_data={"path": resolved_search_path, "criteria": search_criteria, "count": len(found_items)})
    
    from . import session_manager
    session_manager.update_session_context("last_search_results", found_items)


def handle_move_item(parameters: dict):
    """Moves a file or folder."""
    activity_logger.log_action("move_item", parameters, "pending_execution", "Attempting to move item.")
    
    # 'source_path' and 'destination_path' expected to be resolved by nlu_processor.
    # 'source_path' must exist.
    # 'destination_path' can be an existing directory (move into it) or a full new path.
    resolved_source = parameters.get("source_path")
    final_destination_path = parameters.get("destination_path") # nlu_processor should figure out the final full path

    if not resolved_source or not final_destination_path:
        cli_ui.print_error("Source or destination path is missing or invalid after processing.", "Move Error")
        activity_logger.update_last_activity_status("failure", "Missing resolved source or destination path for move.")
        return

    # nlu_processor should have validated source existence. Re-check for safety.
    if not os.path.exists(resolved_source):
        cli_ui.print_error(f"Source path does not exist: {resolved_source}", "Move Error")
        activity_logger.update_last_activity_status("failure", f"Source path for move not found: {resolved_source}")
        return
        
    # Ensure destination parent directory exists if final_destination_path is a full new path
    dest_parent_dir = os.path.dirname(final_destination_path)
    if not os.path.isdir(dest_parent_dir):
        # This case implies final_destination_path itself was meant to be a directory
        # but it doesn't exist. Or, nlu_processor incorrectly constructed final_destination_path.
        # If final_destination_path *is* the directory, os.path.dirname would be its parent.
        # This logic might need refinement based on how nlu_processor prepares destination_path.
        # For now, assume nlu_processor ensures dest_parent_dir is valid if final_destination_path is a new file name.
        # If final_destination_path is an existing directory to move *into*, this check is fine.
        # If final_destination_path is a new directory path to be created by move, this will fail.
        # shutil.move can create the final component if it's a rename, but not intermediate dirs.
        
        # Simpler: if the target is `somedir/item_name` and `somedir` doesn't exist, error.
        # If target is `existing_dir` (to move into), then `dest_parent_dir` is `existing_dir`'s parent.
        if not os.path.exists(dest_parent_dir):
             try:
                 # Attempt to create the parent directory for the destination
                 os.makedirs(dest_parent_dir, exist_ok=True)
                 cli_ui.print_info(f"Created destination directory: [filepath]{dest_parent_dir}[/filepath]", "Directory Created")
             except Exception as e_mkdir:
                 cli_ui.print_error(f"Destination directory [filepath]{dest_parent_dir}[/filepath] does not exist and could not be created: {e_mkdir}", "Move Error")
                 activity_logger.update_last_activity_status("failure", f"Destination parent directory for move does not exist and couldn't be created: {dest_parent_dir}")
                 return
    
    # Handle overwrite confirmation
    if os.path.exists(final_destination_path):
        overwrite_confirm = cli_ui.ask_question_prompt(
            f"Destination '[filepath]{final_destination_path}[/filepath]' already exists. Overwrite? (yes/no)"
        )
        if overwrite_confirm.lower() not in ["yes", "y"]:
            cli_ui.print_info("Move operation cancelled by user (overwrite denied).", "Move Cancelled")
            activity_logger.update_last_activity_status("user_cancelled", "Move cancelled due to existing destination.")
            return
        # Further checks for directory vs file overwrite
        if os.path.isdir(final_destination_path) and os.path.isfile(resolved_source):
             cli_ui.print_error(f"Cannot overwrite directory '[filepath]{final_destination_path}[/filepath]' with a file.", "Move Error")
             activity_logger.update_last_activity_status("failure", "Cannot overwrite directory with file.")
             return
        if os.path.isfile(final_destination_path) and os.path.isdir(resolved_source):
             cli_ui.print_error(f"Cannot overwrite file '[filepath]{final_destination_path}[/filepath]' with a directory.", "Move Error")
             activity_logger.update_last_activity_status("failure", "Cannot overwrite file with directory.")
             return

    move_confirm_q = f"Confirm moving [filepath]{resolved_source}[/filepath] to [filepath]{final_destination_path}[/filepath]? (yes/no)"
    confirmation = cli_ui.ask_question_prompt(move_confirm_q)

    if confirmation.lower() not in ["yes", "y"]:
        cli_ui.print_info("Move operation cancelled by user.", "Move Cancelled")
        activity_logger.update_last_activity_status("user_cancelled", "User cancelled move confirmation.")
        return

    try:
        cli_ui.console.print(f"{cli_constants.ICONS.get('move','➡️')} Moving [filepath]{resolved_source}[/filepath] to [filepath]{final_destination_path}[/filepath]...")
        shutil.move(resolved_source, final_destination_path)
        cli_ui.print_success(f"Successfully moved item to [filepath]{final_destination_path}[/filepath].", "Move Complete")
        activity_logger.update_last_activity_status("success", "Item moved successfully.", result_data={"source": resolved_source, "destination": final_destination_path})
    except Exception as e:
        cli_ui.print_error(f"Failed to move item: {e}", "Move Error")
        cli_ui.console.print_exception(max_frames=2)
        activity_logger.update_last_activity_status("failure", f"Error during shutil.move: {e}")


def handle_propose_and_execute_organization(connector, parameters: dict):
    """Proposes an organization plan for a folder and allows user to execute it."""
    activity_logger.log_action("propose_and_execute_organization", parameters, "pending_execution", "Attempting to organize folder.")
    
    # 'target_path_or_context' expected to be resolved to an absolute directory path by nlu_processor,
    # and named 'target_path' in the parameters dict.
    resolved_path = parameters.get("target_path") 
    organization_goal = parameters.get("organization_goal", "Organize files logically")

    if not resolved_path:
        cli_ui.print_error("Target folder path is missing for organization.", "Organization Error")
        activity_logger.update_last_activity_status("failure", "Missing resolved target_path for organization.")
        return

    if not os.path.isdir(resolved_path):
        cli_ui.print_error(f"Target path for organization is not a directory: {resolved_path}", "Organization Error")
        activity_logger.update_last_activity_status("failure", f"Target for organization not a directory: {resolved_path}")
        return

    cli_ui.console.print(f"{cli_constants.ICONS.get('plan','📋')} Analyzing folder '[filepath]{resolved_path}[/filepath]' for organization plan...\nGoal: [highlight]{organization_goal}[/highlight]")

    current_items_simple, _ = fs_utils.list_folder_contents_simple(resolved_path, max_depth=0)
    current_contents_summary_parts = [f"{item['name']} ({item['type']})" for item in current_items_simple[:10]]
    if len(current_items_simple) > 10:
        current_contents_summary_parts.append(f"...and {len(current_items_simple)-10} more items.")
    current_contents_summary_text = f"Current folder '{os.path.basename(resolved_path)}' contains: " + ", ".join(current_contents_summary_parts)
    if not current_items_simple:
        current_contents_summary_text = f"Current folder '{os.path.basename(resolved_path)}' is empty."

    plan_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Asking LLM to generate organization plan...[/spinner_style]"
    plan_json = None
    with Live(Spinner("dots", text=plan_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        plan_result = connector.generate_organization_plan(resolved_path, organization_goal, current_contents_summary_text)
        
        if plan_result and plan_result.get("plan_steps"):
            plan_json = plan_result
        elif plan_result and plan_result.get("error"):
            cli_ui.print_error(f"LLM failed to generate a plan: {plan_result['error']}", "Plan Generation Failed")
            activity_logger.update_last_activity_status("failure", f"LLM plan generation error: {plan_result['error']}")
            return
        else:
            cli_ui.print_warning("LLM failed to generate a structured plan. Attempting heuristic organization by type.", "LLM Plan Failed")
            heuristic_plan = fs_utils.generate_heuristic_organization_plan(resolved_path, "by_type") # Ensure this is defined in fs_utils
            if heuristic_plan and heuristic_plan.get("plan_steps"):
                plan_json = heuristic_plan
                cli_ui.print_info("Generated a heuristic plan to organize by file type.", "Heuristic Plan")
            else:
                cli_ui.print_error("LLM and heuristic plan generation both failed.", "Plan Generation Failed")
                activity_logger.update_last_activity_status("failure", "LLM and heuristic plan generation failed.")
                return
    
    if not plan_json or not plan_json.get("plan_steps"):
        cli_ui.print_error("No valid organization plan could be generated.", "Plan Generation Failed")
        activity_logger.update_last_activity_status("failure", "No valid plan steps generated.")
        return

    plan_steps = plan_json.get("plan_steps", [])
    explanation = plan_json.get("explanation", "No detailed explanation provided for this plan.")

    cli_ui.print_info(f"LLM Plan Explanation: {explanation}", "Organization Plan")
    
    cli_ui.console.print("\nProposed Plan Steps:", style="bold")
    if not plan_steps:
        cli_ui.print_info("The proposed plan has no steps.", "Empty Plan")
        activity_logger.update_last_activity_status("success", "Plan generated with no steps.")
        return

    table = Table(title="Organization Steps", box=ROUNDED, show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("Action", style="bold cyan")
    table.add_column("Details")

    for i, step in enumerate(plan_steps):
        action = step.get("action")
        details_parts = []
        if action == "create_folder":
            details_parts.append(f"Folder: [filepath]{step.get('path', 'N/A')}[/filepath]")
        elif action == "move":
            details_parts.append(f"Source: [filepath]{step.get('source', 'N/A')}[/filepath]")
            details_parts.append(f"Destination: [filepath]{step.get('destination', 'N/A')}[/filepath]")
        else:
            details_parts.append(str(step))
        table.add_row(str(i + 1), action.replace("_", " ").title(), "\n".join(details_parts))
    cli_ui.console.print(table)

    confirm_execution = cli_ui.ask_question_prompt(
        f"\n{cli_constants.ICONS.get('confirm','👉')} Do you want to execute this plan for '[filepath]{resolved_path}[/filepath]'? (yes/no)"
    )
    if confirm_execution.lower() not in ["yes", "y"]:
        cli_ui.print_info("Organization plan execution cancelled by user.", "Execution Cancelled")
        activity_logger.update_last_activity_status("user_cancelled", "User cancelled organization plan execution.")
        return
    
    cli_ui.console.print(f"\n{cli_constants.ICONS.get('execute','🚀')} Executing organization plan...")
    executed_successfully = True
    for i, step in enumerate(plan_steps):
        cli_ui.console.print(f"Step {i+1}/{len(plan_steps)}: {step.get('action')}", end=" -> ")
        action_result = False
        try:
            # Ensure paths in steps are relative to the main resolved_path
            if step.get("action") == "create_folder":
                folder_to_create = os.path.join(resolved_path, step.get("path").strip('/\\'))
                if not os.path.exists(folder_to_create):
                    os.makedirs(folder_to_create)
                    cli_ui.console.print(f"[green]Created folder: {folder_to_create}[/green]")
                    action_result = True
                else:
                    cli_ui.console.print(f"[yellow]Folder already exists (skipped): {folder_to_create}[/yellow]")
                    action_result = True
            
            elif step.get("action") == "move":
                source_abs = os.path.join(resolved_path, step.get("source").strip('/\\'))
                dest_abs = os.path.join(resolved_path, step.get("destination").strip('/\\'))

                if not os.path.exists(source_abs):
                    cli_ui.console.print(f"[red]Error: Source file/folder not found: {source_abs}[/red]")
                    action_result = False
                else:
                    dest_dir_abs = os.path.dirname(dest_abs)
                    if not os.path.exists(dest_dir_abs):
                        os.makedirs(dest_dir_abs) 
                        cli_ui.console.print(f"[dim]Ensured destination directory exists: {dest_dir_abs}[/dim]", end=" -> ")
                    
                    shutil.move(source_abs, dest_abs)
                    cli_ui.console.print(f"[green]Moved {step.get('source')} to {step.get('destination')}[/green]")
                    action_result = True
            else:
                cli_ui.console.print(f"[yellow]Unknown action '{step.get('action')}' skipped.[/yellow]")
                action_result = True

            if not action_result:
                executed_successfully = False
                cli_ui.print_error(f"Failed to execute step {i+1}. Aborting plan.", "Execution Error")
                break
        except Exception as e_exec:
            cli_ui.console.print(f"[red]Error executing step {i+1}: {e_exec}[/red]")
            cli_ui.console.print_exception(max_frames=1)
            executed_successfully = False
            break
            
    if executed_successfully:
        cli_ui.print_success("Organization plan executed successfully.", "Organization Complete")
        activity_logger.update_last_activity_status("success", "Organization plan executed.", result_data={"path": resolved_path, "goal": organization_goal, "steps_count": len(plan_steps)})
    else:
        cli_ui.print_error("Organization plan execution failed or was aborted due to errors.", "Organization Failed")
        activity_logger.update_last_activity_status("failure", "Organization plan execution failed or aborted.", result_data={"path": resolved_path, "goal": organization_goal})


def handle_show_activity_log(parameters: dict):
    """Displays recent activity logs."""
    # No 'connector' needed for this specific handler based on main.py dispatch
    activity_logger.log_action("show_activity_log", parameters, "pending_execution", "Attempting to show activity log.")
    count = parameters.get("count", 10) 

    try:
        # Corrected function call
        logs = activity_logger.get_recent_activities(count)
        if not logs:
            cli_ui.print_info("No activities found in the log.", "Activity Log Empty")
            activity_logger.update_last_activity_status("success", "Log viewed (empty).")
            return

        cli_ui.print_success(f"Displaying last {min(count, len(logs))} activities:", "Activity Log")
        
        table = Table(title=None, show_header=True, header_style="table.header", box=ROUNDED)
        table.add_column("Timestamp", style="dim", width=20)
        table.add_column("Action", style="bold cyan", width=25)
        table.add_column("Status", width=15)
        table.add_column("Details/Parameters", min_width=40, overflow="fold")

        for log_entry in logs: # logs are already reversed by get_recent_activities if needed, or handled by it.
            params_str_parts = []
            if log_entry.get("parameters"):
                for k, v in log_entry["parameters"].items():
                    v_str = str(v)
                    if len(v_str) > 70: v_str = v_str[:67] + "..."
                    params_str_parts.append(f"[dim_text]{k}[/dim_text]=[highlight]{v_str}[/highlight]")
            params_display = ", ".join(params_str_parts) if params_str_parts else log_entry.get("details", "N/A")
            
            status = log_entry.get('status', 'N/A')
            status_style = "green" if "success" in status else ("yellow" if "pending" in status or "user_cancelled" in status or "partial" in status else ("red" if "fail" in status or "exception" in status else "dim"))

            # Ensure timestamp_readable exists or fall back
            timestamp_display = log_entry.get("timestamp_readable")
            if not timestamp_display and "timestamp" in log_entry:
                try:
                    dt_obj = datetime.datetime.fromisoformat(log_entry["timestamp"])
                    timestamp_display = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    timestamp_display = log_entry["timestamp"] # fallback to raw ISO if conversion fails

            table.add_row(
                timestamp_display if timestamp_display else "N/A",
                log_entry.get("action_name", log_entry.get("action","N/A")), # Use 'action' if 'action_name' not present
                Text(status.replace("_", " ").title(), style=status_style),
                params_display
            )
        cli_ui.console.print(table)
        activity_logger.update_last_activity_status("success", f"Displayed last {min(count, len(logs))} activities.")

    except AttributeError as e_attr: # Specifically catch if 'get_recent_activities' was wrong
        cli_ui.print_error(f"Failed to display activity log (AttributeError): {e_attr}", "Log Display Error")
        cli_ui.console.print_exception(max_frames=2)
        activity_logger.update_last_activity_status("failure", f"Error displaying log (AttributeError): {e_attr}")
    except Exception as e:
        cli_ui.print_error(f"Failed to display activity log: {e}", "Log Display Error")
        cli_ui.console.print_exception(max_frames=2)
        activity_logger.update_last_activity_status("failure", f"Error displaying log: {e}")


def handle_general_chat(connector, parameters: dict):
    """Handles general chat or commands not fitting other categories."""
    activity_logger.log_action("general_chat", parameters, "pending_execution", "Handling general chat/command.")
    user_query = parameters.get("user_query", "")

    if not user_query:
        cli_ui.print_warning("No query provided for general chat.", "Chat Error")
        activity_logger.update_last_activity_status("failure", "Empty query for general chat.")
        return

    cli_ui.console.print(f"{cli_constants.ICONS.get('thinking','🤔')} Thinking about: \"{user_query[:60]}...\"")
    
    chat_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Processing general query...[/spinner_style]"
    with Live(Spinner("dots", text=chat_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        response = connector.general_chat_completion(user_query)

    if response and response.get("response_text"):
        cli_ui.print_panel_message("LLM Response", response["response_text"], "info", cli_constants.ICONS.get('app_icon','🤖'))
        activity_logger.update_last_activity_status("success", "General chat response provided.")
    elif response and response.get("error"):
        cli_ui.print_error(f"LLM could not process the query: {response['error']}", "Chat Processing Failed")
        activity_logger.update_last_activity_status("failure", f"LLM error during general chat: {response['error']}")
    else:
        cli_ui.print_error("LLM did not return a valid response or error for the general query.", "Chat Processing Failed")
        activity_logger.update_last_activity_status("failure", "LLM no valid response for general chat.")


def handle_redo_activity(connector, parameters: dict):
    """Allows re-doing a previous activity from the log."""
    activity_logger.log_action("redo_activity", parameters, "pending_execution", "Attempting to redo activity.")
    target_activity_ref = parameters.get("activity_reference")

    cli_ui.print_warning(f"Redo functionality for '{target_activity_ref}' is not fully implemented yet. It would require re-dispatching the original command.", "Not Implemented")
    activity_logger.update_last_activity_status("partial_failure", "Redo not fully implemented.")


# === Action Handler Map ===
def get_action_handler_map():
    return {
        "summarize_file": handle_summarize_file,
        "ask_question_about_file": handle_ask_question_about_file,
        "list_folder_contents": handle_list_folder_contents,
        "search_files": handle_search_files,
        "move_item": handle_move_item,
        "propose_and_execute_organization": handle_propose_and_execute_organization,
        "show_activity_log": handle_show_activity_log,
        "general_chat": handle_general_chat,
        "redo_activity": handle_redo_activity,
        # "organize_file": handle_organize_file, # This action was hallucinated by LLM.
                                                # If truly needed, it would be implemented.
                                                # For now, it's not a defined action.
    }