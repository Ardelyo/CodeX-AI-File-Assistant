# python/action_handlers.py

import os
import shutil
import time
import json # For loading activity log if needed for redo

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
from . import path_resolver
from . import fs_utils # Assuming you have fs_utils for file operations like list_folder_contents_simple
import activity_logger # For logging results

from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.panel import Panel
from rich.box import ROUNDED

# --- Configuration for Summarization ---
MAX_CONTENT_LENGTH_FOR_SUMMARY = 20000  # Characters, adjust based on your LLM and typical file sizes
MAX_ITEMS_TO_DISPLAY_IN_LIST = 50 # For list_folder_contents

# === Helper for Content Extraction ===
def _extract_file_content(resolved_path: str, file_extension: str) -> tuple[str, str, str | None]:
    """
    Extracts content from a file based on its extension.
    Returns: (content_text, content_source_description, error_message_if_any)
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
                file_content += page.get_text("text") # "text" for plain text
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
            # For unsupported types, content will remain empty. The LLM can be informed.

    except fitz.fitz.FitxError as e_pdf: # More specific PyMuPDF error
        error_message = f"Error processing PDF file {os.path.basename(resolved_path)}: {e_pdf}. It might be corrupted or password-protected."
        content_source = "pdf_processing_error"
    except Exception as e_extraction:
        error_message = f"An unexpected error occurred during content extraction of {os.path.basename(resolved_path)}: {str(e_extraction)}"
        content_source = "extraction_error"

    if error_message:
        cli_ui.print_warning(error_message, "Content Extraction Issue")
        
    return file_content, content_source, error_message


# === Action Handlers ===

def handle_summarize_file(connector, parameters: dict):
    """Handles the summarization of a file."""
    activity_logger.log_action("summarize_file", parameters, "pending_execution", "Attempting to summarize file.")
    
    file_path_param = parameters.get("file_path")
    if not file_path_param:
        cli_ui.print_error("File path is missing for summarization.", "Summarization Error")
        activity_logger.update_last_activity_status("failure", "Missing file_path parameter.")
        return

    resolved_path = path_resolver.resolve_path(file_path_param, cli_ui)
    if not resolved_path or not os.path.isfile(resolved_path):
        cli_ui.print_error(f"File not found or is not a file: {resolved_path or file_path_param}", "File Error")
        activity_logger.update_last_activity_status("failure", f"File not found or not a file: {resolved_path or file_path_param}")
        return

    file_extension = os.path.splitext(resolved_path)[1].lower()
    cli_ui.console.print(f"{cli_constants.ICONS.get('file','📄')} Attempting to summarize: [filepath]{resolved_path}[/filepath]")

    file_content, content_source, extraction_error = _extract_file_content(resolved_path, file_extension)

    if not file_content.strip() and extraction_error: # If extraction failed and produced an error message
        # LLM will be informed about the failure.
        llm_input_content = f"I attempted to summarize the file at path '{resolved_path}'. It is a '{file_extension}' file. However, I encountered an issue extracting its content. The error was: '{extraction_error}'. Can you provide a generic statement or acknowledge this based on the filename and type, or ask the user for more information if needed?"
    elif not file_content.strip(): # If file is empty or unsupported and no specific error was generated by _extract_file_content
        llm_input_content = f"The file at path '{resolved_path}' (type: '{file_extension}') appears to be empty or its content could not be read for direct summarization. Please provide a general comment or ask for clarification."
    else:
        llm_input_content = file_content

    if len(llm_input_content) > MAX_CONTENT_LENGTH_FOR_SUMMARY:
        llm_input_content = llm_input_content[:MAX_CONTENT_LENGTH_FOR_SUMMARY] + "\n\n[Content truncated due to length]"
        cli_ui.print_info("Content was truncated for LLM summary due to length.", "Content Truncation")

    summary_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Asking LLM to summarize '{os.path.basename(resolved_path)}' ({content_source})...[/spinner_style]"
    with Live(Spinner("dots", text=summary_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        summary_result = connector.get_summary(llm_input_content, resolved_path) # Pass resolved_path for context

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

    file_path_param = parameters.get("file_path")
    question = parameters.get("question")

    if not file_path_param or not question:
        cli_ui.print_error("File path or question is missing.", "Q&A Error")
        activity_logger.update_last_activity_status("failure", "Missing file_path or question.")
        return

    resolved_path = path_resolver.resolve_path(file_path_param, cli_ui)
    if not resolved_path or not os.path.isfile(resolved_path):
        cli_ui.print_error(f"File not found or is not a file: {resolved_path or file_path_param}", "File Error")
        activity_logger.update_last_activity_status("failure", f"File not found for Q&A: {resolved_path or file_path_param}")
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
    
    # Content length truncation for Q&A might also be needed, similar to summarization
    if len(llm_input_content) > MAX_CONTENT_LENGTH_FOR_SUMMARY: # Using same constant for now
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
    folder_path_param = parameters.get("folder_path")

    resolved_path = path_resolver.resolve_path(folder_path_param, cli_ui, expect_dir=True)
    if not resolved_path or not os.path.isdir(resolved_path):
        cli_ui.print_error(f"Folder not found or is not a directory: {resolved_path or folder_path_param}", "Directory Error")
        activity_logger.update_last_activity_status("failure", f"Folder not found for list: {resolved_path or folder_path_param}")
        return

    try:
        cli_ui.console.print(f"{cli_constants.ICONS.get('folder','📁')} Contents of [filepath]{resolved_path}[/filepath]:")
        items, error = fs_utils.list_folder_contents_simple(resolved_path) # Assuming fs_utils has this

        if error:
            cli_ui.print_error(f"Error listing folder: {error}", "Listing Error")
            activity_logger.update_last_activity_status("failure", f"Error listing folder: {error}")
            return
        
        if not items:
            cli_ui.print_info("The folder is empty.", "Empty Folder")
            activity_logger.update_last_activity_status("success", "Folder listed (empty).", result_data={"path": resolved_path, "count": 0})
            # Update session context about the listed folder (even if empty)
            from . import session_manager # Local import to avoid circularity if session_manager imports action_handlers
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
            if display_count >= MAX_ITEMS_TO_DISPLAY_IN_LIST and len(items) > MAX_ITEMS_TO_DISPLAY_IN_LIST + 5 : # Show 'more items' message if significantly truncated
                remaining_items = len(items) - display_count
                table.add_row("...", f"... and {remaining_items} more items ...", "", "", "")
                break
            
            item_type_icon = cli_constants.ICONS.get('folder','📁') if item['type'] == 'directory' else cli_constants.ICONS.get('file','📄')
            
            # Apply styling to filename if it's a directory
            name_style = "filepath" if item['type'] == 'directory' else "dim_text" # Example style
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
        
        # Update session context
        from . import session_manager # Local import
        session_manager.update_session_context("last_folder_listed_path", resolved_path)
        session_manager.update_session_context("last_listed_items", items) # Store full list for context

    except Exception as e:
        cli_ui.print_error(f"An unexpected error occurred while listing folder: {e}", "Listing Error")
        cli_ui.console.print_exception(max_frames=2)
        activity_logger.update_last_activity_status("failure", f"Unexpected listing error: {e}")


def handle_search_files(connector, parameters: dict):
    """Searches for files based on criteria (name, type, or LLM-assisted content)."""
    activity_logger.log_action("search_files", parameters, "pending_execution", "Attempting to search files.")
    search_criteria = parameters.get("search_criteria", "").strip()
    search_path_param = parameters.get("search_path")
    # search_type = parameters.get("search_type", "name") # e.g., 'name', 'type', 'content' - NLU should determine this

    resolved_path = path_resolver.resolve_path(search_path_param, cli_ui, expect_dir=True)
    if not resolved_path or not os.path.isdir(resolved_path):
        cli_ui.print_error(f"Search path not found or is not a directory: {resolved_path or search_path_param}", "Search Path Error")
        activity_logger.update_last_activity_status("failure", f"Search path not found: {resolved_path or search_path_param}")
        return

    if not search_criteria or search_criteria == "__MISSING__":
        cli_ui.print_error("Search criteria are missing.", "Search Error")
        activity_logger.update_last_activity_status("failure", "Missing search criteria.")
        return

    cli_ui.console.print(f"{cli_constants.ICONS.get('search','🔍')} Searching in [filepath]{resolved_path}[/filepath] for: '[highlight]{search_criteria}[/highlight]'")
    
    # This is a simplified search. A real implementation would be more complex:
    # - Decide if it's name, type, or content search.
    # - For content search, iterate files, extract text (like in summarize), then ask LLM if text matches criteria.
    # - For now, let's simulate a basic name search.
    
    found_items = []
    search_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Searching files...[/spinner_style]"

    with Live(Spinner("dots", text=search_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        time.sleep(0.1) # Simulate work
        # Actual recursive search logic using os.walk or fs_utils
        # Example: items = fs_utils.search_files_recursive(resolved_path, search_criteria, search_type)
        # For this stub, let's just do a simple name check in the top directory
        for entry in os.scandir(resolved_path):
            if search_criteria.lower() in entry.name.lower():
                stat = entry.stat()
                found_items.append({
                    "name": entry.name,
                    "path": entry.path,
                    "type": "directory" if entry.is_dir() else "file",
                    "size_bytes": stat.st_size,
                    "size_readable": fs_utils.bytes_to_readable(stat.st_size),
                    "modified_timestamp": stat.st_mtime,
                    "modified_readable": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                })
        # This is a very basic search. A proper search would be recursive and might involve LLM for content.
        # For a more advanced search, you'd call a specific function in fs_utils or even involve the LLM.

    if not found_items:
        cli_ui.print_info(f"No items found matching '[highlight]{search_criteria}[/highlight]' in [filepath]{resolved_path}[/filepath].", "Search Complete")
        activity_logger.update_last_activity_status("success", "Search complete (no results).", result_data={"path": resolved_path, "criteria": search_criteria, "count": 0})
        from . import session_manager # Local import
        session_manager.update_session_context("last_search_results", [])
        return

    cli_ui.print_success(f"Found {len(found_items)} item(s) matching [highlight]'{search_criteria}'[/highlight]:", "Search Results")
    
    table = Table(title=None, show_header=True, header_style="table.header", box=ROUNDED)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", style="dim_text", min_width=30, overflow="fold")
    table.add_column("Path", style="filepath", min_width=40, overflow="fold") # Show full path for search results
    table.add_column("Type", width=10)

    display_count = 0
    for i, item in enumerate(found_items):
        if display_count >= MAX_ITEMS_TO_DISPLAY_IN_LIST and len(found_items) > MAX_ITEMS_TO_DISPLAY_IN_LIST + 5:
            remaining_items = len(found_items) - display_count
            table.add_row("...", f"... and {remaining_items} more items ...", "", "")
            break

        item_type_icon = cli_constants.ICONS.get('folder','📁') if item['type'] == 'directory' else cli_constants.ICONS.get('file','📄')
        name_display = Text(f"{item_type_icon} {item['name']}")
        path_display = Text(item['path'], style="filepath") # It's useful to see the full path in search

        table.add_row(
            str(i + 1),
            name_display,
            path_display,
            item['type'].capitalize()
        )
        display_count +=1

    cli_ui.console.print(table)
    activity_logger.update_last_activity_status("success", f"Search found {len(found_items)} items.", result_data={"path": resolved_path, "criteria": search_criteria, "count": len(found_items)})
    
    from . import session_manager # Local import
    session_manager.update_session_context("last_search_results", found_items)


def handle_move_item(parameters: dict):
    """Moves a file or folder."""
    activity_logger.log_action("move_item", parameters, "pending_execution", "Attempting to move item.")
    source_path_param = parameters.get("source_path")
    destination_path_param = parameters.get("destination_path")

    if not source_path_param or not destination_path_param:
        cli_ui.print_error("Source or destination path is missing.", "Move Error")
        activity_logger.update_last_activity_status("failure", "Missing source or destination path for move.")
        return

    resolved_source = path_resolver.resolve_path(source_path_param, cli_ui, check_exists=True) # Source must exist
    if not resolved_source: # resolve_path prints its own error if check_exists fails
        activity_logger.update_last_activity_status("failure", f"Source path for move not found or invalid: {source_path_param}")
        return

    # For destination, we want the absolute path, but it might not exist yet (if it's a new filename within an existing dir)
    # Or it could be just a directory path.
    # path_resolver needs a flag to handle "destination" type paths.
    # For simplicity, let's assume destination_path_param is either an existing dir or a full new path.
    
    # Create a more robust destination resolver if needed.
    # This is a simplified destination logic:
    resolved_dest_parent = os.path.dirname(path_resolver.resolve_path(destination_path_param, cli_ui, check_exists=False))
    if not os.path.exists(resolved_dest_parent) or not os.path.isdir(resolved_dest_parent):
         # Try to see if destination_path_param itself is an existing directory
        potential_dest_dir = path_resolver.resolve_path(destination_path_param, cli_ui, check_exists=False)
        if os.path.isdir(potential_dest_dir):
            # User provided a directory, so we'll move the source *into* it
            final_destination_path = os.path.join(potential_dest_dir, os.path.basename(resolved_source))
        else:
            cli_ui.print_error(f"Destination directory does not exist: {resolved_dest_parent or destination_path_param}", "Move Error")
            activity_logger.update_last_activity_status("failure", f"Destination directory for move does not exist: {resolved_dest_parent or destination_path_param}")
            return
    else:
        # User provided a full path (potentially with a new name for the source)
        final_destination_path = path_resolver.resolve_path(destination_path_param, cli_ui, check_exists=False)


    if os.path.exists(final_destination_path):
        overwrite_confirm = cli_ui.ask_question_prompt(
            f"Destination '[filepath]{final_destination_path}[/filepath]' already exists. Overwrite? (yes/no)"
        )
        if overwrite_confirm.lower() not in ["yes", "y"]:
            cli_ui.print_info("Move operation cancelled by user (overwrite denied).", "Move Cancelled")
            activity_logger.update_last_activity_status("user_cancelled", "Move cancelled due to existing destination.")
            return
        # If overwriting a directory, it's more complex (e.g., shutil.rmtree then move).
        # For simplicity, shutil.move handles file overwrite but might error on dir overwrite.
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
    
    target_path_param = parameters.get("target_path_or_context")
    organization_goal = parameters.get("organization_goal", "Organize files logically") # Default goal

    resolved_path = path_resolver.resolve_path(target_path_param, cli_ui, expect_dir=True)
    if not resolved_path or not os.path.isdir(resolved_path):
        cli_ui.print_error(f"Target folder not found or is not a directory: {resolved_path or target_path_param}", "Organization Error")
        activity_logger.update_last_activity_status("failure", f"Target folder for organization not found: {resolved_path or target_path_param}")
        return

    cli_ui.console.print(f"{cli_constants.ICONS.get('plan','📋')} Analyzing folder '[filepath]{resolved_path}[/filepath]' for organization plan...\nGoal: [highlight]{organization_goal}[/highlight]")

    # Get a summary of current contents (simple list for now, could be more detailed)
    current_items_simple, _ = fs_utils.list_folder_contents_simple(resolved_path, max_depth=0) # Just top level for summary
    current_contents_summary_parts = [f"{item['name']} ({item['type']})" for item in current_items_simple[:10]] # Summary of first 10 items
    if len(current_items_simple) > 10:
        current_contents_summary_parts.append(f"...and {len(current_items_simple)-10} more items.")
    current_contents_summary_text = f"Current folder '{os.path.basename(resolved_path)}' contains: " + ", ".join(current_contents_summary_parts)
    if not current_items_simple:
        current_contents_summary_text = f"Current folder '{os.path.basename(resolved_path)}' is empty."


    plan_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Asking LLM to generate organization plan...[/spinner_style]"
    plan_json = None
    with Live(Spinner("dots", text=plan_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        plan_result = connector.generate_organization_plan(resolved_path, organization_goal, current_contents_summary_text)
        # Expected plan_result: {"plan_steps": [{"action": "create_folder", "path": "subfolder_name"}, {"action": "move", "source": "file.txt", "destination": "subfolder_name/file.txt"}], "explanation": "..."} or {"error": "..."}
        
        if plan_result and plan_result.get("plan_steps"):
            plan_json = plan_result # Use the whole result which might include explanation
        elif plan_result and plan_result.get("error"):
            cli_ui.print_error(f"LLM failed to generate a plan: {plan_result['error']}", "Plan Generation Failed")
            activity_logger.update_last_activity_status("failure", f"LLM plan generation error: {plan_result['error']}")
            return
        else: # Fallback to heuristic if LLM fails or returns unusable plan
            cli_ui.print_warning("LLM failed to generate a structured plan. Attempting heuristic organization by type.", "LLM Plan Failed")
            # Heuristic: organize by file extension into subfolders
            heuristic_plan = fs_utils.generate_heuristic_organization_plan(resolved_path, "by_type")
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
            details_parts.append(str(step)) # Raw details for unknown actions
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
            if step.get("action") == "create_folder":
                folder_to_create = os.path.join(resolved_path, step.get("path"))
                if not os.path.exists(folder_to_create):
                    os.makedirs(folder_to_create)
                    cli_ui.console.print(f"[green]Created folder: {folder_to_create}[/green]")
                    action_result = True
                else:
                    cli_ui.console.print(f"[yellow]Folder already exists (skipped): {folder_to_create}[/yellow]")
                    action_result = True # Skipped is a form of success for the plan
            
            elif step.get("action") == "move":
                source_abs = os.path.join(resolved_path, step.get("source"))
                dest_abs = os.path.join(resolved_path, step.get("destination"))

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
        except Exception as e_exec: # Variable is e_exec
            cli_ui.console.print(f"[red]Error executing step {i+1}: {e_exec}[/red]") # CORRECTED: Use e_exec here
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
    activity_logger.log_action("show_activity_log", parameters, "pending_execution", "Attempting to show activity log.")
    count = parameters.get("count", 10) # Default to last 10 activities

    try:
        logs = activity_logger.get_last_n_activities(count)
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

        for log_entry in logs:
            params_str_parts = []
            if log_entry.get("parameters"):
                for k, v in log_entry["parameters"].items():
                    v_str = str(v)
                    if len(v_str) > 70: v_str = v_str[:67] + "..." # Truncate long param values
                    params_str_parts.append(f"[dim_text]{k}[/dim_text]=[highlight]{v_str}[/highlight]")
            params_display = ", ".join(params_str_parts) if params_str_parts else log_entry.get("details", "N/A")
            
            status = log_entry.get('status', 'N/A')
            status_style = "green" if "success" in status else ("yellow" if "pending" in status or "user_cancelled" in status or "partial" in status else ("red" if "fail" in status or "exception" in status else "dim"))

            table.add_row(
                log_entry.get("timestamp_readable", "N/A"),
                log_entry.get("action_name", "N/A"),
                Text(status.replace("_", " ").title(), style=status_style),
                params_display
            )
        cli_ui.console.print(table)
        activity_logger.update_last_activity_status("success", f"Displayed last {min(count, len(logs))} activities.")

    except Exception as e:
        cli_ui.print_error(f"Failed to display activity log: {e}", "Log Display Error")
        cli_ui.console.print_exception(max_frames=2)
        activity_logger.update_last_activity_status("failure", f"Error displaying log: {e}")


def handle_general_chat(connector, parameters: dict):
    """Handles general chat or commands not fitting other categories."""
    activity_logger.log_action("general_chat", parameters, "pending_execution", "Handling general chat/command.")
    user_query = parameters.get("user_query", "") # This should be the original full input if NLU defaulted here

    if not user_query:
        cli_ui.print_warning("No query provided for general chat.", "Chat Error")
        activity_logger.update_last_activity_status("failure", "Empty query for general chat.")
        return

    cli_ui.console.print(f"{cli_constants.ICONS.get('thinking','🤔')} Thinking about: \"{user_query[:60]}...\"")
    
    chat_spinner_text = f"[spinner_style] {cli_constants.ICONS.get('thinking','🤔')} Processing general query...[/spinner_style]"
    with Live(Spinner("dots", text=chat_spinner_text), console=cli_ui.console, transient=True, refresh_per_second=10):
        response = connector.general_chat_completion(user_query) # Assumes connector has such a method

    if response and response.get("response_text"):
        # For general chat, just print the response directly, maybe in an info panel if it's long.
        # Or use Markdown if the response might contain it.
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
    # This handler is complex. It needs to:
    # 1. Get the 'activity_id' or 'index_in_log' from parameters.
    # 2. Fetch that specific activity from activity_logger.
    # 3. Re-populate action_name and parameters.
    # 4. Get the appropriate handler from the map.
    # 5. Call the handler.
    # This requires main_cli.py to be able to dispatch an action again.
    # A simpler approach might be to have this function return the action_name and params
    # to main_cli.py, which then re-enters its dispatch logic.
    # For now, let's just stub it.
    
    target_activity_ref = parameters.get("activity_reference") # Could be "last", "last search", or an index/ID

    cli_ui.print_warning(f"Redo functionality for '{target_activity_ref}' is not fully implemented yet. It would require re-dispatching the original command.", "Not Implemented")
    activity_logger.update_last_activity_status("partial_failure", "Redo not fully implemented.")
    # In a full implementation:
    # original_action_log = activity_logger.get_activity_by_reference(target_activity_ref)
    # if original_action_log:
    #     action_to_redo = original_action_log.get("action_name")
    #     params_to_redo = original_action_log.get("parameters")
    #     cli_ui.print_info(f"Attempting to redo action: {action_to_redo} with params: {params_to_redo}")
    #     # Here you'd need to call the main dispatch loop or the specific handler again.
    #     # This is tricky as it might create nested calls or state issues.
    # else:
    #     cli_ui.print_error(f"Could not find activity '{target_activity_ref}' to redo.", "Redo Error")


# === Action Handler Map ===
# This map is used by main_cli.py to find the correct handler function.
# It's good practice to define it here so all handlers are in one place.

def get_action_handler_map():
    return {
        "summarize_file": handle_summarize_file,
        "ask_question_about_file": handle_ask_question_about_file,
        "list_folder_contents": handle_list_folder_contents,
        "search_files": handle_search_files,
        "move_item": handle_move_item,
        "propose_and_execute_organization": handle_propose_and_execute_organization,
        "show_activity_log": handle_show_activity_log,
        "general_chat": handle_general_chat, # Fallback for unrecognized but potentially valid LLM actions
        "redo_activity": handle_redo_activity,
        # Add other action handlers here as you create them
        # "unknown": handle_unknown_action, # You might want a specific handler for truly unknown actions
    }