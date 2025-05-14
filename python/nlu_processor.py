import os
import re

# Corrected relative imports for modules within the 'python' package
from .path_resolver import get_path_from_user_input, resolve_contextual_path
from .cli_constants import ICONS, KNOWN_BAD_EXAMPLE_PATHS
from . import cli_ui # Assuming cli_ui is needed for prompting by nlu_processor
from . import session_manager # To get session context if needed directly

# file_utils is at the project root, so nlu_processor should not import it directly.
# If functionality from file_utils is needed here, it should be passed in or refactored.
# For now, assuming it's not directly used here.

# ollama_connector is at the project root.
# nlu_processor typically receives the connector instance from main_cli.py.

def _resolve_single_path_parameter(param_key: str, param_value: str, current_session_ctx: dict, is_folder_hint: bool = False, prompt_if_missing: bool = True, ui_console=None):
    """
    Resolves a single path parameter.
    Handles __FROM_CONTEXT__, __MISSING__, __CURRENT_DIR__ and relative paths.
    Prompts user if necessary and prompt_if_missing is True.
    """
    if param_value == "__FROM_CONTEXT__":
        resolved = resolve_contextual_path(param_value, current_session_ctx, is_folder_hint)
        if not resolved and prompt_if_missing and ui_console:
            cli_ui.print_warning(f"Could not resolve '{param_key}' from context.", "Path Resolution")
            return get_path_from_user_input(ui_console, f"Enter path for '{param_key}'", is_folder=is_folder_hint)
        return resolved
    elif param_value == "__MISSING__":
        if prompt_if_missing and ui_console:
            cli_ui.print_warning(f"Parameter '{param_key}' is missing.", "Missing Information")
            return get_path_from_user_input(ui_console, f"Enter path for '{param_key}'", is_folder=is_folder_hint)
        return None # Indicate still missing if not prompting
    elif param_value == "__CURRENT_DIR__":
        return current_session_ctx.get("current_directory", os.getcwd())
    elif param_value and not os.path.isabs(param_value):
        # If relative, resolve against current_directory from session context
        base_dir = current_session_ctx.get("current_directory", os.getcwd())
        return os.path.abspath(os.path.join(base_dir, param_value))
    return param_value # Already absolute or None/empty

def process_nlu_result(nlu_data: dict, user_input_original: str, current_session_ctx: dict, connector, ui_module):
    """
    Processes the NLU result (from direct parser or LLM).
    - Resolves contextual/missing path parameters.
    - Handles user cancellation during path prompts.
    - Finalizes parameters for action handlers.
    Returns: (action_name, finalized_parameters, processing_notes)
    """
    action = nlu_data.get("action")
    params = nlu_data.get("parameters", {})
    nlu_method = nlu_data.get("nlu_method", "unknown_nlu_processor")
    processing_notes = []

    if not action or action == "unknown" or action.startswith("error_"):
        return action, params, f"NLU Error or Unknown Action: {nlu_method}"

    # Path parameter resolution logic
    # This needs to be aware of which parameters for which actions are paths
    # and whether they are files or folders.

    final_params = params.copy() # Work on a copy

    if action == "summarize_file":
        path_val = final_params.get("file_path")
        resolved_path = _resolve_single_path_parameter(
            "file_path", path_val, current_session_ctx, 
            is_folder_hint=False, prompt_if_missing=True, ui_console=ui_module.console
        )
        if resolved_path is None and path_val not in [None, ""]: # User cancelled or resolution failed
            return "user_cancelled_path_prompt", final_params, "User cancelled path input for summarize."
        final_params["file_path"] = resolved_path
        if final_params["file_path"] and not os.path.isfile(final_params["file_path"]):
            ui_module.print_error(f"Summarize Error: Path '[filepath]{final_params['file_path']}[/filepath]' is not a valid file.", "Path Error")
            return "path_validation_failed", final_params, f"Path for summarize is not a file: {final_params['file_path']}"


    elif action == "ask_question_about_file":
        path_val = final_params.get("file_path")
        resolved_path = _resolve_single_path_parameter(
            "file_path", path_val, current_session_ctx,
            is_folder_hint=False, prompt_if_missing=True, ui_console=ui_module.console # is_folder_hint=False implies file or folder
        )
        if resolved_path is None and path_val not in [None, ""]:
            return "user_cancelled_path_prompt", final_params, "User cancelled path input for ask_question."
        final_params["file_path"] = resolved_path
        if final_params["file_path"] and not os.path.exists(final_params["file_path"]):
            ui_module.print_error(f"Q&A Error: Path '[filepath]{final_params['file_path']}[/filepath]' does not exist.", "Path Error")
            return "path_validation_failed", final_params, f"Path for ask_question does not exist: {final_params['file_path']}"


    elif action == "list_folder_contents":
        path_val = final_params.get("folder_path")
        resolved_path = _resolve_single_path_parameter(
            "folder_path", path_val, current_session_ctx,
            is_folder_hint=True, prompt_if_missing=True, ui_console=ui_module.console
        )
        if resolved_path is None and path_val not in [None, ""]:
             return "user_cancelled_path_prompt", final_params, "User cancelled path input for list_folder."
        final_params["folder_path"] = resolved_path
        if final_params["folder_path"] and not os.path.isdir(final_params["folder_path"]):
            ui_module.print_error(f"List Error: Path '[filepath]{final_params['folder_path']}[/filepath]' is not a valid directory.", "Path Error")
            return "path_validation_failed", final_params, f"Path for list_folder is not a directory: {final_params['folder_path']}"

    elif action == "move_item":
        src_path_val = final_params.get("source_path")
        dest_path_val = final_params.get("destination_path")

        resolved_src_path = _resolve_single_path_parameter(
            "source_path", src_path_val, current_session_ctx,
            is_folder_hint=False, prompt_if_missing=True, ui_console=ui_module.console
        )
        if resolved_src_path is None and src_path_val not in [None, ""]:
            return "user_cancelled_path_prompt", final_params, "User cancelled source path input for move."
        final_params["source_path"] = resolved_src_path

        if final_params["source_path"] and not os.path.exists(final_params["source_path"]):
            ui_module.print_error(f"Move Error: Source '[filepath]{final_params['source_path']}[/filepath]' does not exist.", "Path Error")
            return "path_validation_failed", final_params, f"Source path for move does not exist: {final_params['source_path']}"

        # For destination, it might not exist yet, so don't check os.path.exists unless it's meant to be an existing folder
        # The LLM prompt now suggests user's input string for paths, so this resolution makes it absolute.
        # If dest_path_val is like "./archive" or "archive", it becomes absolute here.
        if dest_path_val and not os.path.isabs(dest_path_val):
            base_dir = current_session_ctx.get("current_directory", os.getcwd())
            final_params["destination_path"] = os.path.abspath(os.path.join(base_dir, dest_path_val))
        elif dest_path_val: # Already absolute from LLM or direct parser
             final_params["destination_path"] = dest_path_val
        else: # Missing destination
            if ui_module: # Check if ui_module is available for prompting
                ui_module.print_warning("Destination path for move is missing.", "Missing Information")
                resolved_dest_path = get_path_from_user_input(ui_module.console, "Enter destination path for move")
                if not resolved_dest_path : # User cancelled
                    return "user_cancelled_path_prompt", final_params, "User cancelled destination path input for move."
                final_params["destination_path"] = resolved_dest_path
            else: # Cannot prompt
                 return "parameter_missing_no_ui", final_params, "Destination path for move is missing, no UI to prompt."


    elif action == "search_files":
        path_val = final_params.get("search_path")
        # search_path can be optional, if not provided, it means search everywhere or CWD based on file_utils logic
        if path_val: # Only resolve if a path_val is actually given by LLM/direct_parser
            resolved_path = _resolve_single_path_parameter(
                "search_path", path_val, current_session_ctx,
                is_folder_hint=True, prompt_if_missing=True, ui_console=ui_module.console
            )
            if resolved_path is None and path_val not in [None, "", "__MISSING__", "__FROM_CONTEXT__"]: # User cancelled a specific path prompt
                 return "user_cancelled_path_prompt", final_params, "User cancelled search path input."
            final_params["search_path"] = resolved_path # Could be None if optional and not resolved
            if final_params["search_path"] and not os.path.isdir(final_params["search_path"]):
                ui_module.print_error(f"Search Error: Path '[filepath]{final_params['search_path']}[/filepath]' is not a valid directory.", "Path Error")
                return "path_validation_failed", final_params, f"Search path is not a directory: {final_params['search_path']}"
        
        if not final_params.get("search_criteria") and ui_module:
            ui_module.print_warning("Search criteria is missing.", "Missing Information")
            criteria = ui_module.console.input(f"{ICONS['input']} [prompt]Enter search criteria[/prompt]> ")
            if not criteria:
                return "user_cancelled_parameter_prompt", final_params, "User cancelled search criteria input."
            final_params["search_criteria"] = criteria


    elif action == "propose_and_execute_organization":
        path_val = final_params.get("target_path_or_context")
        resolved_path = _resolve_single_path_parameter(
            "target_path_or_context", path_val, current_session_ctx,
            is_folder_hint=True, prompt_if_missing=True, ui_console=ui_module.console
        )
        if resolved_path is None and path_val not in [None, ""]:
             return "user_cancelled_path_prompt", final_params, "User cancelled path input for organization."
        final_params["target_path_or_context"] = resolved_path
        if final_params["target_path_or_context"] and not os.path.isdir(final_params["target_path_or_context"]):
            ui_module.print_error(f"Organization Error: Target '[filepath]{final_params['target_path_or_context']}[/filepath]' is not a valid directory.", "Path Error")
            return "path_validation_failed", final_params, f"Target path for organization is not a directory: {final_params['target_path_or_context']}"

    # Add more actions and their specific parameter processing logic here
    # ...

    # Check for bad example paths and warn user (if ui_module is available)
    if ui_module:
        for key, val_to_check in final_params.items():
            if isinstance(val_to_check, str) and any(bad_path in val_to_check for bad_path in KNOWN_BAD_EXAMPLE_PATHS):
                ui_module.print_warning(
                    f"The path '[filepath]{val_to_check}[/filepath]' for parameter '{key}' looks like an example path from documentation. "
                    "Please ensure you provide a real path on your system.",
                    "Potential Example Path"
                )
                processing_notes.append(f"Warned user about example path for '{key}'.")
                # Optionally, could force re-prompting here or mark action as needing confirmation

    return action, final_params, "; ".join(processing_notes) if processing_notes else ""


def resolve_indexed_reference(user_input_lower: str, current_action: str, current_params: dict, session_ctx: dict, ui_console_instance):
    """
    Checks if the user input refers to an item by index (e.g., "item 3", "number 2")
    from the last search/list results and updates action/params if so.
    Returns: (potentially_updated_action, True_if_resolved_else_False)
    """
    # Regex to find "item X", "number X", "X" (if X is only thing after a verb like "summarize")
    # This regex is quite broad and might need refinement.
    # It tries to capture "item 1", "file 2", "3rd item", "summarize 1" (where 1 is the index)
    match = re.search(r"(?:item|file|number|task|entry)\s+(\d+)|(?:summarize|list|move|organize|view|show|ask|question|delete|copy|rename|search)\s+(\d+)$|^(\d+)$", user_input_lower)
    
    index_str = None
    if match:
        index_str = match.group(1) or match.group(2) or match.group(3)

    if index_str:
        try:
            item_index = int(index_str) - 1 # Convert to 0-based index
            last_results = session_ctx.get("last_search_results", [])

            if 0 <= item_index < len(last_results):
                selected_item = last_results[item_index]
                selected_item_path = selected_item.get("path")
                selected_item_type = selected_item.get("type")

                if not selected_item_path:
                    return current_action, False # No path in selected item

                # Update parameters based on the current_action and selected_item
                # This is a simplified logic, more sophisticated mapping might be needed.
                updated_params = current_params.copy()
                action_to_use = current_action

                if current_action in ["summarize_file", "ask_question_about_file"]:
                    if selected_item_type == "file":
                        updated_params["file_path"] = selected_item_path
                    else: # Trying to summarize/ask about a folder from index
                        if ui_console_instance:
                             cli_ui.print_warning(f"Item {item_index+1} ('{selected_item.get('name')}') is a folder. Summarize/Ask actions are typically for files. Proceeding with folder context.", "Contextual Action")
                        # For ask_question, file_path can be a folder. For summarize, it's tricky.
                        # Let's allow ask_question to proceed with folder path.
                        if current_action == "ask_question_about_file":
                             updated_params["file_path"] = selected_item_path
                        else: # summarize_file on a folder
                            if ui_console_instance:
                                cli_ui.print_error(f"Cannot summarize folder '{selected_item.get('name')}' directly by index. Please use 'list' or 'ask about' the folder.", "Action Error")
                            return current_action, False # Don't change, let it fail if not a file

                elif current_action == "list_folder_contents":
                    if selected_item_type == "folder":
                        updated_params["folder_path"] = selected_item_path
                    else: # Trying to list a file by index
                        if ui_console_instance:
                             cli_ui.print_warning(f"Item {item_index+1} ('{selected_item.get('name')}') is a file. To see its parent folder, use 'list {os.path.dirname(selected_item_path)}'. Listing parent folder instead.", "Contextual Action")
                        updated_params["folder_path"] = os.path.dirname(selected_item_path)
                
                elif current_action == "move_item":
                    updated_params["source_path"] = selected_item_path
                    # Destination path would still need to be from original command or prompted
                    if not updated_params.get("destination_path") or updated_params["destination_path"] == "__MISSING__":
                        if ui_console_instance: # Check if ui_console_instance is available
                            dest_prompt = f"Enter destination path to move '{selected_item.get('name')}'"
                            dest_path = get_path_from_user_input(ui_console_instance, dest_prompt)
                            if not dest_path: return "user_cancelled_path_prompt", False # User cancelled
                            updated_params["destination_path"] = dest_path
                        else: # Cannot prompt
                            return current_action, False # Destination still missing

                elif current_action == "propose_and_execute_organization":
                     if selected_item_type == "folder":
                        updated_params["target_path_or_context"] = selected_item_path
                     else:
                        if ui_console_instance:
                             cli_ui.print_error(f"Cannot organize file '{selected_item.get('name')}' by index. Organization target must be a folder.", "Action Error")
                        return current_action, False

                # Update session context to reflect this indexed reference as the "last referenced"
                if selected_item_type == "file":
                    session_manager.update_session_context("last_referenced_file_path", selected_item_path)
                elif selected_item_type == "folder":
                    session_manager.update_session_context("last_folder_listed_path", selected_item_path)
                    session_manager.update_session_context("last_referenced_file_path", None)

                return action_to_use, True # Parameters updated
            else:
                # Index out of bounds for last_search_results
                if ui_console_instance:
                    cli_ui.print_warning(f"Index {item_index + 1} is out of range for the last search/list results (1 to {len(last_results)}).", "Index Error")
                return current_action, False
        except ValueError:
            # Not a valid integer index
            return current_action, False
    
    return current_action, False # No indexed reference found or resolved