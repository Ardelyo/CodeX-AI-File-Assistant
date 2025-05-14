import os
import re

# Corrected relative imports for modules within the 'python' package
from .path_resolver import get_path_from_user_input, resolve_contextual_path
from .cli_constants import ICONS, KNOWN_BAD_EXAMPLE_PATHS # Assuming ICONS are needed here
# cli_ui and session_manager are typically passed in or their specific functions are called by main_cli
# For direct use here (e.g. for printing warnings not handled by main_cli), import them:
from . import cli_ui
from . import session_manager


def _resolve_single_path_parameter(param_key: str, param_value: str, current_session_ctx: dict, is_folder_hint: bool = False, prompt_if_missing: bool = True, ui_console_instance=None):
    """
    Resolves a single path parameter.
    Handles __FROM_CONTEXT__, __MISSING__, __CURRENT_DIR__ and relative paths.
    Prompts user if necessary and prompt_if_missing is True.
    `ui_console_instance` is the Rich Console object from cli_ui.
    """
    resolved_from_placeholder = resolve_contextual_path(param_value, current_session_ctx, is_folder_hint)

    if resolved_from_placeholder == param_value and param_value == "__MISSING__": # Placeholder was __MISSING__ and it wasn't resolved by resolve_contextual_path
        if prompt_if_missing and ui_console_instance:
            # Use cli_ui for consistency if available
            cli_ui.print_warning(f"Parameter '{param_key}' is missing.", "Missing Information")
            return get_path_from_user_input(ui_console_instance, f"Enter path for '{param_key}'", is_folder=is_folder_hint)
        return None # Indicate still missing if not prompting
    
    # If resolve_contextual_path returned a path (not the original placeholder or None)
    # or if the original param_value was not a placeholder.
    path_to_make_absolute = resolved_from_placeholder if resolved_from_placeholder != param_value else param_value

    if path_to_make_absolute and isinstance(path_to_make_absolute, str) and not os.path.isabs(path_to_make_absolute):
        # If relative, resolve against current_directory from session context
        base_dir = current_session_ctx.get("current_directory", os.getcwd())
        return os.path.abspath(os.path.join(base_dir, path_to_make_absolute))
    
    # If it was resolved from a placeholder to an absolute path, or was already absolute, or was None/empty initially
    return path_to_make_absolute 


def process_nlu_result(nlu_data: dict, user_input_original: str, current_session_ctx: dict, connector, ui_module_passed):
    """
    Processes the NLU result (from direct parser or LLM).
    - Resolves contextual/missing path parameters using path_resolver.
    - Handles user cancellation during path prompts.
    - Finalizes parameters for action handlers.
    Returns: (action_name, finalized_parameters, processing_notes_string)
    `ui_module_passed` is the `cli_ui` module itself, so we can call `cli_ui.print_warning` etc.
    """
    action = nlu_data.get("action")
    params = nlu_data.get("parameters", {})
    nlu_method = nlu_data.get("nlu_method", "unknown_nlu_processor")
    processing_notes = []

    if not action or action == "unknown" or action.startswith("error_"):
        return action, params, f"NLU Error or Unknown Action: {nlu_method}"

    final_params = params.copy() 

    # Central console instance for path prompting
    console_instance = ui_module_passed.console if ui_module_passed else None

    if action == "summarize_file":
        path_val = final_params.get("file_path")
        resolved_path = _resolve_single_path_parameter(
            "file_path", path_val, current_session_ctx, 
            is_folder_hint=False, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_path is None and path_val not in [None, "", "__MISSING__", "__FROM_CONTEXT__", "__CURRENT_DIR__"]: 
            return "user_cancelled_path_prompt", final_params, "User cancelled path input for summarize."
        final_params["file_path"] = resolved_path
        if final_params["file_path"] and not os.path.isfile(final_params["file_path"]):
            if ui_module_passed: ui_module_passed.print_error(f"Summarize Error: Path '[filepath]{final_params['file_path']}[/filepath]' is not a valid file.", "Path Error")
            return "path_validation_failed", final_params, f"Path for summarize is not a file: {final_params['file_path']}"

    elif action == "ask_question_about_file":
        path_val = final_params.get("file_path")
        resolved_path = _resolve_single_path_parameter(
            "file_path", path_val, current_session_ctx,
            is_folder_hint=False, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_path is None and path_val not in [None, "", "__MISSING__", "__FROM_CONTEXT__", "__CURRENT_DIR__"]:
            return "user_cancelled_path_prompt", final_params, "User cancelled path input for ask_question."
        final_params["file_path"] = resolved_path
        if final_params["file_path"] and not os.path.exists(final_params["file_path"]):
            if ui_module_passed: ui_module_passed.print_error(f"Q&A Error: Path '[filepath]{final_params['file_path']}[/filepath]' does not exist.", "Path Error")
            return "path_validation_failed", final_params, f"Path for ask_question does not exist: {final_params['file_path']}"

    elif action == "list_folder_contents":
        path_val = final_params.get("folder_path")
        resolved_path = _resolve_single_path_parameter(
            "folder_path", path_val, current_session_ctx,
            is_folder_hint=True, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_path is None and path_val not in [None, "", "__MISSING__", "__FROM_CONTEXT__", "__CURRENT_DIR__"]:
             return "user_cancelled_path_prompt", final_params, "User cancelled path input for list_folder."
        final_params["folder_path"] = resolved_path
        if final_params["folder_path"] and not os.path.isdir(final_params["folder_path"]):
            if ui_module_passed: ui_module_passed.print_error(f"List Error: Path '[filepath]{final_params['folder_path']}[/filepath]' is not a valid directory.", "Path Error")
            return "path_validation_failed", final_params, f"Path for list_folder is not a directory: {final_params['folder_path']}"

    elif action == "move_item":
        src_path_val = final_params.get("source_path")
        dest_path_val = final_params.get("destination_path")

        resolved_src_path = _resolve_single_path_parameter(
            "source_path", src_path_val, current_session_ctx,
            is_folder_hint=False, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_src_path is None and src_path_val not in [None, "", "__MISSING__", "__FROM_CONTEXT__", "__CURRENT_DIR__"]:
            return "user_cancelled_path_prompt", final_params, "User cancelled source path input for move."
        final_params["source_path"] = resolved_src_path

        if final_params["source_path"] and not os.path.exists(final_params["source_path"]):
            if ui_module_passed: ui_module_passed.print_error(f"Move Error: Source '[filepath]{final_params['source_path']}[/filepath]' does not exist.", "Path Error")
            return "path_validation_failed", final_params, f"Source path for move does not exist: {final_params['source_path']}"

        if dest_path_val and not os.path.isabs(dest_path_val): # If relative, make it absolute
            base_dir = current_session_ctx.get("current_directory", os.getcwd())
            final_params["destination_path"] = os.path.abspath(os.path.join(base_dir, dest_path_val))
        elif dest_path_val: # Already absolute or a placeholder
             final_params["destination_path"] = resolve_contextual_path(dest_path_val, current_session_ctx, is_folder_hint=True) # Dest can be a folder
        
        if not final_params.get("destination_path") or final_params.get("destination_path") == "__MISSING__":
            if ui_module_passed and console_instance:
                ui_module_passed.print_warning("Destination path for move is missing.", "Missing Information")
                resolved_dest_path = get_path_from_user_input(console_instance, "Enter destination path for move")
                if not resolved_dest_path : 
                    return "user_cancelled_path_prompt", final_params, "User cancelled destination path input for move."
                final_params["destination_path"] = resolved_dest_path
            else:
                 return "parameter_missing_no_ui", final_params, "Destination path for move is missing, no UI to prompt."

    elif action == "search_files":
        path_val = final_params.get("search_path")
        if path_val: 
            resolved_path = _resolve_single_path_parameter(
                "search_path", path_val, current_session_ctx,
                is_folder_hint=True, prompt_if_missing=True, ui_console_instance=console_instance
            )
            if resolved_path is None and path_val not in [None, "", "__MISSING__", "__FROM_CONTEXT__", "__CURRENT_DIR__"]:
                 return "user_cancelled_path_prompt", final_params, "User cancelled search path input."
            final_params["search_path"] = resolved_path 
            if final_params["search_path"] and not os.path.isdir(final_params["search_path"]):
                if ui_module_passed: ui_module_passed.print_error(f"Search Error: Path '[filepath]{final_params['search_path']}[/filepath]' is not a valid directory.", "Path Error")
                return "path_validation_failed", final_params, f"Search path is not a directory: {final_params['search_path']}"
        
        if not final_params.get("search_criteria") and ui_module_passed and console_instance:
            ui_module_passed.print_warning("Search criteria is missing.", "Missing Information")
            # Use ui_module_passed.console directly here if ICONS are part of the prompt string
            criteria = console_instance.input(f"{ICONS.get('input', '>')} [prompt]Enter search criteria[/prompt]> ")
            if not criteria:
                return "user_cancelled_parameter_prompt", final_params, "User cancelled search criteria input."
            final_params["search_criteria"] = criteria

    elif action == "propose_and_execute_organization":
        path_val = final_params.get("target_path_or_context")
        resolved_path = _resolve_single_path_parameter(
            "target_path_or_context", path_val, current_session_ctx,
            is_folder_hint=True, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_path is None and path_val not in [None, "", "__MISSING__", "__FROM_CONTEXT__", "__CURRENT_DIR__"]:
             return "user_cancelled_path_prompt", final_params, "User cancelled path input for organization."
        final_params["target_path_or_context"] = resolved_path
        if final_params["target_path_or_context"] and not os.path.isdir(final_params["target_path_or_context"]):
            if ui_module_passed: ui_module_passed.print_error(f"Organization Error: Target '[filepath]{final_params['target_path_or_context']}[/filepath]' is not a valid directory.", "Path Error")
            return "path_validation_failed", final_params, f"Target path for organization is not a directory: {final_params['target_path_or_context']}"

    if ui_module_passed:
        for key, val_to_check in final_params.items():
            if isinstance(val_to_check, str) and any(bad_path in val_to_check for bad_path in KNOWN_BAD_EXAMPLE_PATHS):
                ui_module_passed.print_warning(
                    f"The path '[filepath]{val_to_check}[/filepath]' for parameter '{key}' looks like an example path from documentation. "
                    "Please ensure you provide a real path on your system.",
                    "Potential Example Path"
                )
                processing_notes.append(f"Warned user about example path for '{key}'.")

    return action, final_params, "; ".join(processing_notes) if processing_notes else ""


def resolve_indexed_reference(user_input_lower: str, current_action: str, current_params: dict, session_ctx: dict, ui_module_passed): # Changed from ui_console_instance
    """
    Checks if the user input refers to an item by index.
    Returns: (potentially_updated_action, True_if_resolved_else_False)
    `ui_module_passed` is the `cli_ui` module for printing messages.
    """
    console_instance = ui_module_passed.console if ui_module_passed else None
    match = re.search(r"(?:item|file|number|task|entry)\s+(\d+)|(?:summarize|list|move|organize|view|show|ask|question|delete|copy|rename|search)\s+(\d+)$|^(\d+)$", user_input_lower)
    
    index_str = None
    if match:
        index_str = match.group(1) or match.group(2) or match.group(3)

    if index_str:
        try:
            item_index = int(index_str) - 1 
            last_results = session_ctx.get("last_search_results", [])

            if 0 <= item_index < len(last_results):
                selected_item = last_results[item_index]
                selected_item_path = selected_item.get("path")
                selected_item_type = selected_item.get("type")

                if not selected_item_path:
                    return current_action, False 

                updated_params = current_params.copy()
                action_to_use = current_action

                if current_action in ["summarize_file", "ask_question_about_file"]:
                    if selected_item_type == "file":
                        updated_params["file_path"] = selected_item_path
                    else: 
                        if ui_module_passed:
                             ui_module_passed.print_warning(f"Item {item_index+1} ('{selected_item.get('name')}') is a folder. Summarize/Ask actions are typically for files. Proceeding with folder context for 'ask'.", "Contextual Action")
                        if current_action == "ask_question_about_file":
                             updated_params["file_path"] = selected_item_path
                        else: 
                            if ui_module_passed:
                                ui_module_passed.print_error(f"Cannot summarize folder '{selected_item.get('name')}' directly by index. Please use 'list' or 'ask about' the folder.", "Action Error")
                            return current_action, False 

                elif current_action == "list_folder_contents":
                    if selected_item_type == "folder":
                        updated_params["folder_path"] = selected_item_path
                    else: 
                        if ui_module_passed:
                             ui_module_passed.print_warning(f"Item {item_index+1} ('{selected_item.get('name')}') is a file. To see its parent folder, use 'list {os.path.dirname(selected_item_path)}'. Listing parent folder instead.", "Contextual Action")
                        updated_params["folder_path"] = os.path.dirname(selected_item_path)
                
                elif current_action == "move_item":
                    updated_params["source_path"] = selected_item_path
                    if not updated_params.get("destination_path") or updated_params["destination_path"] == "__MISSING__":
                        if ui_module_passed and console_instance:
                            dest_prompt = f"Enter destination path to move '{selected_item.get('name')}'"
                            dest_path = get_path_from_user_input(console_instance, dest_prompt) # Use console_instance
                            if not dest_path: return "user_cancelled_path_prompt", False 
                            updated_params["destination_path"] = dest_path
                        else: 
                            return current_action, False 

                elif current_action == "propose_and_execute_organization":
                     if selected_item_type == "folder":
                        updated_params["target_path_or_context"] = selected_item_path
                     else:
                        if ui_module_passed:
                             ui_module_passed.print_error(f"Cannot organize file '{selected_item.get('name')}' by index. Organization target must be a folder.", "Action Error")
                        return current_action, False

                if selected_item_type == "file":
                    session_manager.update_session_context("last_referenced_file_path", selected_item_path)
                elif selected_item_type == "folder":
                    session_manager.update_session_context("last_folder_listed_path", selected_item_path)
                    session_manager.update_session_context("last_referenced_file_path", None)

                return action_to_use, True 
            else:
                if ui_module_passed:
                    ui_module_passed.print_warning(f"Index {item_index + 1} is out of range for the last search/list results (1 to {len(last_results)}).", "Index Error")
                return current_action, False
        except ValueError:
            return current_action, False
    
    return current_action, False