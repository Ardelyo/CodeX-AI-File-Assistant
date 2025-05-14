import os
import re

# Corrected relative imports for modules within the 'python' package
from .path_resolver import get_path_from_user_input, resolve_contextual_path
from .cli_constants import ICONS, KNOWN_BAD_EXAMPLE_PATHS 
from . import cli_ui 
from . import session_manager


def _resolve_single_path_parameter(param_key: str, param_value: str, current_session_ctx: dict, is_folder_hint: bool = False, prompt_if_missing: bool = True, ui_console_instance=None):
    """
    Resolves a single path parameter.
    Handles __FROM_CONTEXT__, __MISSING__, __CURRENT_DIR__, __PREVIOUS_ACTION_RESULT_PATH__, 
    __PREVIOUS_ACTION_RESULT_FIRST_PATH__ and relative paths.
    Prompts user if necessary and prompt_if_missing is True.
    `ui_console_instance` is the Rich Console object from cli_ui.
    """
    original_param_value = param_value # Keep original for checks later

    # Handle chaining placeholders first
    last_action_res = current_session_ctx.get("last_action_result")
    resolved_from_chain = False

    if param_value == "__PREVIOUS_ACTION_RESULT_PATH__":
        if isinstance(last_action_res, str) and (os.path.isfile(last_action_res) or os.path.isdir(last_action_res)):
            param_value = last_action_res
            resolved_from_chain = True
        elif isinstance(last_action_res, dict) and 'path' in last_action_res and isinstance(last_action_res['path'], str): # e.g. from list_folder which returns {'path': listed_path}
             param_value = last_action_res['path']
             resolved_from_chain = True
        else:
            cli_ui.print_warning(f"Could not resolve '{original_param_value}' for '{param_key}'. Previous action result was not a suitable path: {str(last_action_res)[:100]}", "Chaining Error")
            param_value = "__MISSING__" # Fallback to missing
    
    elif param_value == "__PREVIOUS_ACTION_RESULT_FIRST_PATH__":
        if isinstance(last_action_res, list) and len(last_action_res) > 0:
            first_item = last_action_res[0]
            if isinstance(first_item, dict) and 'path' in first_item and isinstance(first_item['path'], str):
                param_value = first_item['path']
                resolved_from_chain = True
            elif isinstance(first_item, str) and (os.path.isfile(first_item) or os.path.isdir(first_item)): # List of path strings
                param_value = first_item
                resolved_from_chain = True
            else:
                cli_ui.print_warning(f"Could not resolve '{original_param_value}' for '{param_key}'. First item of previous list result was not a suitable path object: {str(first_item)[:100]}", "Chaining Error")
                param_value = "__MISSING__"
        else:
            cli_ui.print_warning(f"Could not resolve '{original_param_value}' for '{param_key}'. Previous action result was not a list or was empty: {str(last_action_res)[:100]}", "Chaining Error")
            param_value = "__MISSING__"
            
    # If not resolved by chaining, try regular contextual resolution
    if not resolved_from_chain:
        resolved_from_placeholder = resolve_contextual_path(param_value, current_session_ctx, is_folder_hint)
    else: # Already resolved by chaining, use that value
        resolved_from_placeholder = param_value


    if resolved_from_placeholder == param_value and param_value == "__MISSING__":
        if prompt_if_missing and ui_console_instance:
            cli_ui.print_warning(f"Parameter '{param_key}' is missing.", "Missing Information")
            user_provided_path = get_path_from_user_input(ui_console_instance, f"Enter path for '{param_key}'", is_folder=is_folder_hint)
            if not user_provided_path: # User cancelled
                return None 
            return os.path.abspath(user_provided_path) # Make absolute if user provided relative
        return None 
    
    path_to_make_absolute = resolved_from_placeholder

    if path_to_make_absolute and isinstance(path_to_make_absolute, str) and \
       not os.path.isabs(path_to_make_absolute) and \
       param_value not in ["__CURRENT_DIR__", "__LAST_REFERENCED_FILE__", "__LAST_LISTED_FOLDER__"]: # These are already resolved to absolute by resolve_contextual_path usually
        base_dir = current_session_ctx.get("current_directory", os.getcwd())
        return os.path.abspath(os.path.join(base_dir, path_to_make_absolute))
    
    return path_to_make_absolute


def process_nlu_result(nlu_data_for_step: dict, user_input_original: str, current_session_ctx: dict, connector, ui_module_passed):
    """
    Processes a single action step from the NLU result (from direct parser or LLM).
    - Resolves contextual/missing path parameters using path_resolver, including chained placeholders.
    - Handles user cancellation during path prompts.
    - Finalizes parameters for the action handler for this step.
    Returns: (action_name, finalized_parameters, processing_notes_string)
    `ui_module_passed` is the `cli_ui` module itself.
    """
    action = nlu_data_for_step.get("action") # This should be action_name from the LLM output structure
    if 'action_name' in nlu_data_for_step: # Adapt to new LLM output if passed directly
        action = nlu_data_for_step.get("action_name")

    params = nlu_data_for_step.get("parameters", {})
    nlu_method = nlu_data_for_step.get("nlu_method", "unknown_nlu_processor_step") # This might come from the parent NLU result
    processing_notes = []

    if not action or action == "unknown" or action.startswith("error_"):
        return action, params, f"NLU Error or Unknown Action for step: {action or 'None'}. Method: {nlu_method}"

    final_params = params.copy() 
    console_instance = ui_module_passed.console if ui_module_passed else None

    # --- Path resolution logic for various actions ---
    if action == "summarize_file" or action == "ask_question_about_file":
        path_key = "file_path"
        path_val = final_params.get(path_key)
        is_folder = False
        resolved_path = _resolve_single_path_parameter(
            path_key, path_val, current_session_ctx, 
            is_folder_hint=is_folder, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_path is None and path_val not in [None, "", "__MISSING__"]: # User might have cancelled prompt for a non-empty placeholder
            return "user_cancelled_path_prompt", final_params, f"User cancelled path input for '{path_key}' in '{action}'."
        final_params[path_key] = resolved_path
        
        if final_params[path_key]: # If path is not None (could be if __MISSING__ and no prompt)
            if action == "summarize_file" and not os.path.isfile(final_params[path_key]):
                msg = f"Summarize Error: Path '[filepath]{final_params[path_key]}[/filepath]' is not a valid file."
                if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
                return "path_validation_failed", final_params, msg
            elif action == "ask_question_about_file" and not os.path.exists(final_params[path_key]): # ask can be about file or folder
                msg = f"Q&A Error: Path '[filepath]{final_params[path_key]}[/filepath]' does not exist."
                if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
                return "path_validation_failed", final_params, msg
        elif not final_params[path_key] and path_val != "__MISSING__": # Path became None due to unresolvable placeholder or cancellation
             msg = f"{action} Error: '{path_key}' ('{path_val}') could not be resolved and no path was provided."
             if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
             return "path_validation_failed", final_params, msg


    elif action == "list_folder_contents":
        path_key = "folder_path"
        path_val = final_params.get(path_key)
        is_folder = True
        resolved_path = _resolve_single_path_parameter(
            path_key, path_val, current_session_ctx,
            is_folder_hint=is_folder, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_path is None and path_val not in [None, "", "__MISSING__"]:
             return "user_cancelled_path_prompt", final_params, f"User cancelled path input for '{path_key}' in '{action}'."
        final_params[path_key] = resolved_path
        if final_params[path_key] and not os.path.isdir(final_params[path_key]):
            msg = f"List Error: Path '[filepath]{final_params[path_key]}[/filepath]' is not a valid directory."
            if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
            return "path_validation_failed", final_params, msg
        elif not final_params[path_key] and path_val != "__MISSING__":
             msg = f"{action} Error: '{path_key}' ('{path_val}') could not be resolved and no path was provided."
             if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
             return "path_validation_failed", final_params, msg

    elif action == "move_item":
        src_path_val = final_params.get("source_path")
        dest_path_val = final_params.get("destination_path")

        resolved_src_path = _resolve_single_path_parameter(
            "source_path", src_path_val, current_session_ctx,
            is_folder_hint=False, prompt_if_missing=True, ui_console_instance=console_instance # Source can be file or folder
        )
        if resolved_src_path is None and src_path_val not in [None, "", "__MISSING__"]:
            return "user_cancelled_path_prompt", final_params, "User cancelled source path input for move."
        final_params["source_path"] = resolved_src_path

        if final_params["source_path"] and not os.path.exists(final_params["source_path"]):
            msg = f"Move Error: Source '[filepath]{final_params['source_path']}[/filepath]' does not exist."
            if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
            return "path_validation_failed", final_params, msg
        elif not final_params["source_path"] and src_path_val != "__MISSING__":
             msg = f"Move Error: Source path ('{src_path_val}') could not be resolved and no path was provided."
             if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
             return "path_validation_failed", final_params, msg


        # Destination path can be relative, absolute, or placeholder (less common for dest unless chained)
        if dest_path_val:
            # Use _resolve_single_path_parameter for destination too, as it might be a chained placeholder
            # Prompt if missing, assuming destination usually needs to be explicit if not chained
            resolved_dest_path = _resolve_single_path_parameter(
                "destination_path", dest_path_val, current_session_ctx,
                is_folder_hint=True, prompt_if_missing=(dest_path_val == "__MISSING__"), # Only prompt if explicitly __MISSING__
                ui_console_instance=console_instance
            )
            if resolved_dest_path is None and dest_path_val not in [None, "", "__MISSING__"]: # User cancelled
                 return "user_cancelled_path_prompt", final_params, "User cancelled destination path input for move."
            final_params["destination_path"] = resolved_dest_path
        
        if not final_params.get("destination_path"): # Still no destination after trying to resolve
            if ui_module_passed and console_instance: # Prompt one last time if truly missing
                ui_module_passed.print_warning("Destination path for move is missing.", "Missing Information")
                user_dest_path = get_path_from_user_input(console_instance, "Enter destination path for move (can be a new folder name in an existing directory, or a full path)")
                if not user_dest_path : 
                    return "user_cancelled_path_prompt", final_params, "User cancelled destination path input for move."
                # Resolve relative to CWD if user gives relative path here
                base_dir = current_session_ctx.get("current_directory", os.getcwd())
                final_params["destination_path"] = os.path.abspath(os.path.join(base_dir, user_dest_path))
            else:
                 return "parameter_missing_no_ui", final_params, "Destination path for move is missing, no UI to prompt."


    elif action == "search_files":
        path_val = final_params.get("search_path")
        if path_val: # search_path is optional, CWD is default if not provided by LLM
            resolved_path = _resolve_single_path_parameter(
                "search_path", path_val, current_session_ctx,
                is_folder_hint=True, prompt_if_missing=True, ui_console_instance=console_instance
            )
            if resolved_path is None and path_val not in [None, "", "__MISSING__"]:
                 return "user_cancelled_path_prompt", final_params, "User cancelled search path input."
            final_params["search_path"] = resolved_path 
            if final_params["search_path"] and not os.path.isdir(final_params["search_path"]):
                msg = f"Search Error: Path '[filepath]{final_params['search_path']}[/filepath]' is not a valid directory."
                if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
                return "path_validation_failed", final_params, msg
            # No error if final_params["search_path"] is None, as it's optional (handler will use CWD)
        
        if not final_params.get("search_criteria") or final_params.get("search_criteria") == "__MISSING__":
            if ui_module_passed and console_instance:
                ui_module_passed.print_warning("Search criteria is missing for 'search_files' action.", "Missing Information")
                criteria = ui_module_passed.ask_question_prompt("What would you like to search for?") # Using Richer prompt
                if not criteria:
                    return "user_cancelled_parameter_prompt", final_params, "User cancelled search criteria input."
                final_params["search_criteria"] = criteria
            else: # No UI to prompt
                 return "parameter_missing_no_ui", final_params, "Search criteria for 'search_files' is missing, no UI to prompt."


    elif action == "propose_and_execute_organization":
        path_key = "target_path_or_context"
        path_val = final_params.get(path_key)
        is_folder = True
        resolved_path = _resolve_single_path_parameter(
            path_key, path_val, current_session_ctx,
            is_folder_hint=is_folder, prompt_if_missing=True, ui_console_instance=console_instance
        )
        if resolved_path is None and path_val not in [None, "", "__MISSING__"]:
             return "user_cancelled_path_prompt", final_params, f"User cancelled path input for '{path_key}' in '{action}'."
        final_params[path_key] = resolved_path
        if final_params[path_key] and not os.path.isdir(final_params[path_key]):
            msg = f"Organization Error: Target '[filepath]{final_params[path_key]}[/filepath]' is not a valid directory."
            if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
            return "path_validation_failed", final_params, msg
        elif not final_params[path_key] and path_val != "__MISSING__":
             msg = f"{action} Error: '{path_key}' ('{path_val}') could not be resolved and no path was provided."
             if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
             return "path_validation_failed", final_params, msg

        if not final_params.get("organization_goal") and ui_module_passed and console_instance:
            # This could be refined to be optional if the LLM thinks general organization is fine
            user_goal = ui_module_passed.ask_question_prompt("What is your goal for organizing this folder (e.g., 'by type', 'by name', or describe your desired structure)? Press Enter for general organization.")
            if user_goal: # Empty string means user wants general organization, which handler can manage
                final_params["organization_goal"] = user_goal
            # No cancellation error if user presses Enter, let handler decide if goal is truly needed

    # Check for KNOWN_BAD_EXAMPLE_PATHS (remains useful)
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


def resolve_indexed_reference(user_input_lower: str, current_action: str, current_params: dict, session_ctx: dict, ui_module_passed):
    """
    Checks if the user input refers to an item by index from 'last_search_results'.
    This function might be less critical if LLM handles chaining well, but kept for direct indexed inputs.
    Returns: (potentially_updated_action, potentially_updated_params, True_if_resolved_else_False)
    `ui_module_passed` is the `cli_ui` module for printing messages.
    """
    console_instance = ui_module_passed.console if ui_module_passed else None
    # Regex to find "item N", "file N", "N", etc., possibly at the end of a command phrase
    # This regex is simplified as LLM should ideally provide specific file paths.
    # It helps if user says "summarize item 1" AFTER a search.
    match = re.search(r"\b(?:item|file|number|entry|result)\s+(\d+)\b|^(\d+)$", user_input_lower)
    
    index_str = None
    if match:
        index_str = match.group(1) or match.group(2) # Group 1 for "item N", Group 2 for standalone N

    if index_str:
        try:
            item_index = int(index_str) - 1 
            last_results = session_ctx.get("last_search_results", []) # This comes from session_manager

            if not last_results:
                if ui_module_passed:
                    ui_module_passed.print_warning(f"Cannot use item index '{index_str}': no previous search results found in current session.", "Index Error")
                return current_action, current_params, False

            if 0 <= item_index < len(last_results):
                selected_item = last_results[item_index] # This is a dict like {'name': ..., 'path': ..., 'type': ...}
                selected_item_path = selected_item.get("path")
                selected_item_type = selected_item.get("type") # "file" or "folder"

                if not selected_item_path:
                    if ui_module_passed:
                        ui_module_passed.print_error(f"Item {item_index+1} from previous results has no path.", "Internal Error")
                    return current_action, current_params, False

                updated_params = current_params.copy()
                action_to_use = current_action # Usually action doesn't change, just its params

                # Determine which parameter of current_action should receive the selected_item_path
                param_updated = False
                if current_action in ["summarize_file", "ask_question_about_file"]:
                    if selected_item_type == "file":
                        updated_params["file_path"] = selected_item_path
                        param_updated = True
                    elif current_action == "ask_question_about_file": # ask can be about folder
                        updated_params["file_path"] = selected_item_path # 'file_path' param used for folder too
                        param_updated = True
                        if ui_module_passed:
                             ui_module_passed.print_info(f"Applying action to folder '{selected_item.get('name')}' (item {item_index+1}).")
                    else: # Cannot summarize a folder by index this way
                        if ui_module_passed:
                            ui_module_passed.print_error(f"Cannot '{current_action}' folder '{selected_item.get('name')}' (item {item_index+1}). Action is for files.", "Action Error")
                        return current_action, current_params, False
                
                elif current_action == "list_folder_contents":
                    if selected_item_type == "folder":
                        updated_params["folder_path"] = selected_item_path
                        param_updated = True
                    else: # Item is a file, list its parent directory
                        parent_dir = os.path.dirname(selected_item_path)
                        updated_params["folder_path"] = parent_dir
                        param_updated = True
                        if ui_module_passed:
                             ui_module_passed.print_info(f"Item {item_index+1} is a file. Listing its parent directory: '{parent_dir}'.")
                
                elif current_action == "move_item": # Assume "item N" refers to source
                    if not updated_params.get("source_path") or updated_params["source_path"] == "__MISSING__":
                        updated_params["source_path"] = selected_item_path
                        param_updated = True
                        if ui_module_passed:
                             ui_module_passed.print_info(f"Setting source for move to item {item_index+1}: '{selected_item.get('name')}'.")
                        # Destination still needs to be prompted if missing (handled by main processing loop)
                    else: # Source path already specified by LLM or user, index might be for something else or redundant
                        if ui_module_passed:
                            ui_module_passed.print_warning(f"Move source already specified as '{updated_params['source_path']}'. Ignoring indexed item {item_index+1} for source.", "Info")


                elif current_action == "propose_and_execute_organization":
                     if selected_item_type == "folder":
                        updated_params["target_path_or_context"] = selected_item_path
                        param_updated = True
                     else:
                        if ui_module_passed:
                             ui_module_passed.print_error(f"Cannot organize file '{selected_item.get('name')}' (item {item_index+1}) directly by index. Organization target must be a folder.", "Action Error")
                        return current_action, current_params, False
                
                if param_updated:
                    if selected_item_type == "file":
                        session_manager.update_session_context("last_referenced_file_path", selected_item_path)
                    elif selected_item_type == "folder":
                        session_manager.update_session_context("last_folder_listed_path", selected_item_path)
                    
                    if ui_module_passed and param_updated:
                         ui_module_passed.print_info(f"Using item {item_index+1} ('{selected_item.get('name')}') for current action '{action_to_use}'.")
                    return action_to_use, updated_params, True
                else: # Indexed item found, but current action doesn't clearly use it
                    if ui_module_passed:
                        ui_module_passed.print_warning(f"Found item {item_index+1} ('{selected_item.get('name')}'), but not sure how to apply it to action '{current_action}'. Parameters remain unchanged.", "Contextual Warning")
                    return current_action, current_params, False


            else: # Index out of range
                if ui_module_passed:
                    ui_module_passed.print_warning(f"Index {item_index + 1} is out of range for the last search/list results (1 to {len(last_results)}).", "Index Error")
                return current_action, current_params, False
        except ValueError: # Not a valid number
            return current_action, current_params, False 
    
    return current_action, current_params, False # No index pattern found


