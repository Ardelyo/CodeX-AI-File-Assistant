# python/nlu_processor.py

import os
import re

# Corrected relative imports for modules within the 'python' package
from .path_resolver import get_path_from_user_input, resolve_contextual_path
from .cli_constants import ICONS, KNOWN_BAD_EXAMPLE_PATHS
from . import cli_ui
from . import session_manager


def _resolve_single_path_parameter(param_key: str, param_value: str, current_session_ctx: dict, is_folder_hint: bool = False, prompt_if_missing: bool = True, check_exists_for_source: bool = False, ui_console_instance=None):
    """
    Resolves a single path parameter.
    Handles __FROM_CONTEXT__, __MISSING__, __CURRENT_DIR__, etc., and relative paths.
    Prompts user if necessary and prompt_if_missing is True.
    If check_exists_for_source is True, it will verify the path exists after resolution.
    """
    original_param_value_for_debug = param_value 

    # 1. Handle explicit non-placeholder paths first if they are absolute
    if isinstance(param_value, str) and os.path.isabs(param_value) and not param_value.startswith("__"):
        # If it's an absolute path and not a placeholder, use it directly.
        # Further validation (isfile, isdir) will happen in process_nlu_result or handler.
        resolved_path = param_value
        if check_exists_for_source and not os.path.exists(resolved_path):
            if ui_console_instance:
                cli_ui.print_error(f"Path Error: Explicitly provided source path '{resolved_path}' for '{param_key}' does not exist.", "Path Validation Error")
            return None # Path doesn't exist
        return resolved_path

    # 2. Handle chaining placeholders (like __PREVIOUS_ACTION_RESULT_PATH__)
    last_action_res = current_session_ctx.get("last_action_result")
    resolved_from_chain = False
    path_after_chaining_or_placeholder_resolution = param_value

    if param_value == "__PREVIOUS_ACTION_RESULT_PATH__":
        # ... (keep existing chaining logic, ensure it returns an absolute path or None)
        if isinstance(last_action_res, str) and os.path.isabs(last_action_res) and (os.path.isfile(last_action_res) or os.path.isdir(last_action_res)):
            path_after_chaining_or_placeholder_resolution = last_action_res
            resolved_from_chain = True
        elif isinstance(last_action_res, dict) and 'path' in last_action_res and isinstance(last_action_res['path'], str) and os.path.isabs(last_action_res['path']):
            path_after_chaining_or_placeholder_resolution = last_action_res['path']
            resolved_from_chain = True
        else:
            if ui_console_instance:
                cli_ui.print_warning(f"Could not resolve '{original_param_value_for_debug}' for '{param_key}'. Previous action result was not a suitable absolute path.", "Chaining Error")
            path_after_chaining_or_placeholder_resolution = "__MISSING__" # Fallback to missing

    elif param_value == "__PREVIOUS_ACTION_RESULT_FIRST_PATH__":
        # ... (keep existing chaining logic, ensure it returns an absolute path or None)
        if isinstance(last_action_res, list) and len(last_action_res) > 0:
            first_item = last_action_res[0]
            if isinstance(first_item, dict) and 'path' in first_item and isinstance(first_item['path'], str) and os.path.isabs(first_item['path']):
                path_after_chaining_or_placeholder_resolution = first_item['path']
                resolved_from_chain = True
            elif isinstance(first_item, str) and os.path.isabs(first_item) and (os.path.isfile(first_item) or os.path.isdir(first_item)):
                path_after_chaining_or_placeholder_resolution = first_item
                resolved_from_chain = True
            else:
                if ui_console_instance:
                     cli_ui.print_warning(f"Could not resolve '{original_param_value_for_debug}' for '{param_key}'. First item of previous list result was not a suitable absolute path object.", "Chaining Error")
                path_after_chaining_or_placeholder_resolution = "__MISSING__"
        else:
            if ui_console_instance:
                 cli_ui.print_warning(f"Could not resolve '{original_param_value_for_debug}' for '{param_key}'. Previous action result was not a list or was empty.", "Chaining Error")
            path_after_chaining_or_placeholder_resolution = "__MISSING__"

    # 3. If not resolved by chaining, try contextual placeholder resolution (e.g., __FROM_CONTEXT__, __CURRENT_DIR__)
    #    or if it was an explicit relative path.
    if not resolved_from_chain:
        # `resolve_contextual_path` should return an absolute path if it resolves a placeholder,
        # or the original value if it's not a known placeholder (e.g. a relative path string or __MISSING__)
        path_after_chaining_or_placeholder_resolution = resolve_contextual_path(param_value, current_session_ctx, is_folder_hint)


    # 4. Handle __MISSING__ or prompt if necessary
    if path_after_chaining_or_placeholder_resolution == "__MISSING__":
        if prompt_if_missing and ui_console_instance:
            if ui_console_instance: # Ensure cli_ui is available
                 cli_ui.print_warning(f"Parameter '{param_key}' is missing or could not be resolved from context.", "Missing Information")
            user_provided_path = get_path_from_user_input(ui_console_instance, f"Enter path for '{param_key}'", is_folder=is_folder_hint)
            if not user_provided_path:  # User cancelled
                return None
            # User input might be relative, make it absolute based on current_directory
            base_dir = current_session_ctx.get("current_directory", os.getcwd())
            path_after_chaining_or_placeholder_resolution = os.path.abspath(os.path.join(base_dir, user_provided_path))
        else: # Not prompting or no UI
            return None

    # 5. Ensure the path is absolute if it's a string by now
    #    (Contextual placeholders from resolve_contextual_path should already be absolute)
    #    This primarily handles user-provided relative paths or LLM-provided relative paths.
    if isinstance(path_after_chaining_or_placeholder_resolution, str) and not os.path.isabs(path_after_chaining_or_placeholder_resolution):
        base_dir = current_session_ctx.get("current_directory", os.getcwd())
        resolved_path = os.path.abspath(os.path.join(base_dir, path_after_chaining_or_placeholder_resolution))
    elif isinstance(path_after_chaining_or_placeholder_resolution, str): # Already absolute
        resolved_path = path_after_chaining_or_placeholder_resolution
    else: # Could be None if __MISSING__ and not prompted, or user cancelled prompt
        resolved_path = None

    # 6. Final existence check if requested (typically for source paths)
    if resolved_path and check_exists_for_source and not os.path.exists(resolved_path):
        if ui_console_instance:
            cli_ui.print_error(f"Path Error: Resolved source path '{resolved_path}' for '{param_key}' does not exist.", "Path Validation Error")
        return None

    # 7. If it's a folder hint and the resolved path is a file, take its parent.
    if resolved_path and is_folder_hint and os.path.isfile(resolved_path):
        if ui_console_instance:
            cli_ui.print_info(f"Context for '{param_key}' resolved to file '{os.path.basename(resolved_path)}'. Using its parent directory.", "Context Adjustment")
        return os.path.dirname(resolved_path)
        
    return resolved_path


def process_nlu_result(nlu_data_for_step: dict, user_input_original: str, current_session_ctx: dict, connector, ui_module_passed):
    action = nlu_data_for_step.get("action_name") or nlu_data_for_step.get("action")
    params = nlu_data_for_step.get("parameters", {})
    nlu_method = nlu_data_for_step.get("nlu_method", "unknown_nlu_processor_step")
    processing_notes = []

    if not action or action == "unknown" or action.startswith("error_"):
        return action, params, f"NLU Error or Unknown Action for step: {action or 'None'}. Method: {nlu_method}"

    final_params = params.copy()
    console_instance = ui_module_passed.console if ui_module_passed else None
    
    # --- Standardize and Resolve Path Parameters ---
    path_to_resolve_val = None
    expected_param_name_for_handler = None
    is_folder_hint_for_resolution = False
    is_source_path = False # For check_exists validation

    if action in ["summarize_file", "ask_question_about_file"]:
        path_to_resolve_val = final_params.get("file_path")
        expected_param_name_for_handler = "file_path"
        # For summarize_file, it must be a file. For ask_question_about_file, it can be file or folder.
        # is_folder_hint here is tricky. Let _resolve_single_path_parameter get the raw path.
        # Validation of file/folder type will happen after resolution.
        is_folder_hint_for_resolution = (action == "ask_question_about_file" and isinstance(path_to_resolve_val, str) and "__DIR__" in path_to_resolve_val.upper()) # Crude hint
        is_source_path = True # The file path must exist

    elif action == "list_folder_contents":
        path_to_resolve_val = final_params.get("folder_path") or final_params.get("file_path") # LLM might use file_path
        expected_param_name_for_handler = "folder_path"
        is_folder_hint_for_resolution = True
        is_source_path = True

    elif action == "search_files":
        # LLM might provide 'file_path' or 'search_path'. Prioritize 'search_path'.
        path_to_resolve_val = final_params.get("search_path") or final_params.get("file_path")
        expected_param_name_for_handler = "search_path"
        is_folder_hint_for_resolution = True
        is_source_path = True # The search directory must exist
        
        # Handle missing search_criteria (as seen in logs)
        if not final_params.get("search_criteria") or final_params.get("search_criteria") == "__MISSING__":
            if ui_module_passed and console_instance:
                # No need for print_warning here as ask_question_prompt itself is a panel
                criteria = ui_module_passed.ask_question_prompt("What would you like to search for?")
                if not criteria: # User cancelled
                    return "user_cancelled_parameter_prompt", final_params, "User cancelled search criteria input."
                final_params["search_criteria"] = criteria
                processing_notes.append("Prompted user for search_criteria.")
            else:
                return "parameter_missing_no_ui", final_params, "Search criteria missing, no UI to prompt."
        # Remove the potentially incorrect 'file_path' if 'search_path' is now populated
        if "file_path" in final_params and expected_param_name_for_handler == "search_path":
            del final_params["file_path"]


    elif action == "move_item":
        # Source Path
        src_path_val = final_params.get("source_path") or final_params.get("file_path") # LLM might use file_path for source
        resolved_src = _resolve_single_path_parameter(
            "source_path", src_path_val, current_session_ctx,
            is_folder_hint=False, prompt_if_missing=True, check_exists_for_source=True,
            ui_console_instance=console_instance
        )
        if resolved_src is None:
            # _resolve_single_path_parameter already prints errors or notes cancellations
            return "path_validation_failed", final_params, f"Source path resolution/validation failed for move. Original: '{src_path_val}'"
        final_params["source_path"] = resolved_src
        if "file_path" in final_params and "source_path" in final_params: # Clean up if LLM used file_path
            del final_params["file_path"]
        
        # Destination Path
        dest_path_val = final_params.get("destination_path")
        resolved_dest = _resolve_single_path_parameter(
            "destination_path", dest_path_val, current_session_ctx,
            is_folder_hint=False, # Destination could be a new filename or existing folder
            prompt_if_missing=True, check_exists_for_source=False, # Dest doesn't have to exist
            ui_console_instance=console_instance
        )
        if resolved_dest is None:
            return "path_validation_failed", final_params, f"Destination path resolution failed for move. Original: '{dest_path_val}'"
        final_params["destination_path"] = resolved_dest
        # No further path processing needed here for move, handler manages final logic

    elif action == "propose_and_execute_organization":
        path_to_resolve_val = final_params.get("target_path_or_context") or final_params.get("target_path") or final_params.get("folder_path") or final_params.get("file_path")
        expected_param_name_for_handler = "target_path" # Handler expects target_path
        is_folder_hint_for_resolution = True
        is_source_path = True

        # Handle missing organization_goal
        if not final_params.get("organization_goal") or final_params.get("organization_goal") == "__MISSING__":
            if ui_module_passed and console_instance:
                user_goal = ui_module_passed.ask_question_prompt("What is your goal for organizing this folder (e.g., 'by type', 'by project')? Press Enter for general.")
                if user_goal: # Empty string is a valid "general" goal
                    final_params["organization_goal"] = user_goal
                else: # User pressed Enter
                    final_params["organization_goal"] = "Organize files logically" # Default for handler
                processing_notes.append("Prompted user for organization_goal.")
            # No error if no UI, handler has a default.
        # Clean up other potential path keys if target_path is now primary
        for k in ["target_path_or_context", "folder_path", "file_path"]:
            if k in final_params and expected_param_name_for_handler == "target_path" and k != "target_path":
                del final_params[k]


    # --- Generic Path Resolution if a path_to_resolve_val was set ---
    if expected_param_name_for_handler and path_to_resolve_val is not None:
        resolved_path = _resolve_single_path_parameter(
            expected_param_name_for_handler, path_to_resolve_val, current_session_ctx,
            is_folder_hint=is_folder_hint_for_resolution,
            prompt_if_missing=True, # Default to prompt if missing after context/placeholder
            check_exists_for_source=is_source_path,
            ui_console_instance=console_instance
        )

        if resolved_path is None:
            # _resolve_single_path_parameter would have printed an error or noted cancellation
            # if path_val was not None/empty/"__MISSING__" initially
            return "path_validation_failed", final_params, f"Path resolution/validation failed for '{expected_param_name_for_handler}'. Original value: '{path_to_resolve_val}'"
        
        # Assign to the correct parameter name for the handler
        final_params[expected_param_name_for_handler] = resolved_path
        
        # Clean up: if LLM provided 'file_path' but we resolved it into 'folder_path' or 'search_path', remove original 'file_path'
        if "file_path" in final_params and expected_param_name_for_handler != "file_path" and final_params.get("file_path") == path_to_resolve_val:
            del final_params["file_path"]
        if "folder_path" in final_params and expected_param_name_for_handler != "folder_path" and final_params.get("folder_path") == path_to_resolve_val:
            del final_params["folder_path"]
        # ... and so on for other generic param names the LLM might use


    # --- Post-resolution validation for specific actions ---
    if action == "summarize_file":
        if not final_params.get("file_path") or not os.path.isfile(final_params["file_path"]):
            msg = f"Summarize Error: Path for 'file_path' ('{final_params.get('file_path')}') is not a valid file."
            if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
            return "path_validation_failed", final_params, msg
    elif action == "ask_question_about_file":
        # Can be file or dir, just needs to exist
        if not final_params.get("file_path") or not os.path.exists(final_params["file_path"]):
            msg = f"Q&A Error: Path for 'file_path' ('{final_params.get('file_path')}') does not exist."
            if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
            return "path_validation_failed", final_params, msg
    elif action in ["list_folder_contents", "search_files", "propose_and_execute_organization"]:
        # Expected param name should be folder_path, search_path, or target_path respectively
        path_key_for_dir_action = "folder_path" if action == "list_folder_contents" else \
                                  "search_path" if action == "search_files" else \
                                  "target_path" # for organization
        
        if not final_params.get(path_key_for_dir_action) or not os.path.isdir(final_params[path_key_for_dir_action]):
            msg = f"{action.replace('_',' ').title()} Error: Path for '{path_key_for_dir_action}' ('{final_params.get(path_key_for_dir_action)}') is not a valid directory."
            if ui_module_passed: ui_module_passed.print_error(msg, "Path Error")
            return "path_validation_failed", final_params, msg

    # Check for KNOWN_BAD_EXAMPLE_PATHS
    if ui_module_passed:
        for key, val_to_check in final_params.items():
            if isinstance(val_to_check, str) and any(bad_path in val_to_check for bad_path in KNOWN_BAD_EXAMPLE_PATHS):
                ui_module_passed.print_warning(
                    f"The path '[filepath]{val_to_check}[/filepath]' for parameter '{key}' looks like an example. Please use real paths.",
                    "Potential Example Path"
                )
                processing_notes.append(f"Warned user about example path for '{key}'.")

    return action, final_params, "; ".join(processing_notes) if processing_notes else "Parameters processed."


def resolve_indexed_reference(user_input_lower: str, current_action: str, current_params: dict, session_ctx: dict, ui_module_passed):
    # This function's logic seems mostly okay for handling explicit "item N" references.
    # Its main role is to translate "item N" into a specific path parameter.
    # The crucial part is that `_resolve_single_path_parameter` and the main `process_nlu_result`
    # should correctly handle path parameters regardless of whether they came from an LLM,
    # direct parser, or this index resolver.
    
    # ... (keep existing logic for resolve_indexed_reference)
    # Minor suggestion: Ensure that when a path is resolved from an index,
    # it's stored in the expected parameter name for the `current_action`.
    # The existing logic seems to try to do this.

    match = re.search(r"\b(?:item|file|number|entry|result)\s+(\d+)\b|^(\d+)$", user_input_lower)
    index_str = None
    if match:
        index_str = match.group(1) or match.group(2)

    if index_str:
        try:
            item_index = int(index_str) - 1 
            last_results = session_ctx.get("last_search_results", []) 

            if not last_results:
                if ui_module_passed:
                    ui_module_passed.print_warning(f"Cannot use item index '{index_str}': no previous results found.", "Index Error")
                return current_action, current_params, False # Note: returning original action/params

            if 0 <= item_index < len(last_results):
                selected_item = last_results[item_index]
                selected_item_path = selected_item.get("path")
                selected_item_type = selected_item.get("type")

                if not selected_item_path:
                    if ui_module_passed:
                        ui_module_passed.print_error(f"Item {item_index+1} has no path.", "Internal Error")
                    return current_action, current_params, False

                updated_params = current_params.copy()
                action_to_use = current_action 
                param_updated = False
                
                # Standardize which parameter gets the path based on action
                # This duplicates some logic from the main processor, but is specific to index resolution
                target_param_for_indexed_path = None
                required_type_for_indexed_path = None # "file", "folder", or None for any

                if current_action in ["summarize_file"]:
                    target_param_for_indexed_path = "file_path"
                    required_type_for_indexed_path = "file"
                elif current_action in ["ask_question_about_file"]:
                    target_param_for_indexed_path = "file_path" # can be file or folder
                elif current_action == "list_folder_contents":
                    target_param_for_indexed_path = "folder_path"
                    required_type_for_indexed_path = "folder"
                elif current_action == "move_item": # Assuming index refers to source
                    if not updated_params.get("source_path") or updated_params["source_path"] == "__MISSING__":
                        target_param_for_indexed_path = "source_path"
                elif current_action == "propose_and_execute_organization":
                    target_param_for_indexed_path = "target_path" # Handler expects this
                    required_type_for_indexed_path = "folder"
                elif current_action == "search_files": # User might say "search images in item 1" (if item 1 is a folder)
                    if selected_item_type == "folder":
                        target_param_for_indexed_path = "search_path"
                        required_type_for_indexed_path = "folder"


                if target_param_for_indexed_path:
                    if required_type_for_indexed_path and selected_item_type != required_type_for_indexed_path:
                        if ui_module_passed:
                            ui_module_passed.print_error(f"Cannot apply '{current_action}' to item {item_index+1} ('{selected_item.get('name')}'). It is a '{selected_item_type}', but action expects a '{required_type_for_indexed_path}'.", "Type Error")
                        return current_action, current_params, False
                    
                    # If item is a file and action expects a folder (e.g. list contents item 1 where item 1 is file)
                    if required_type_for_indexed_path == "folder" and selected_item_type == "file" and current_action == "list_folder_contents":
                        parent_dir = os.path.dirname(selected_item_path)
                        updated_params[target_param_for_indexed_path] = parent_dir
                        param_updated = True
                        if ui_module_passed:
                            ui_module_passed.print_info(f"Item {item_index+1} is a file. Using its parent directory '{parent_dir}' for 'list_folder_contents'.")
                    else:
                        updated_params[target_param_for_indexed_path] = selected_item_path
                        param_updated = True
                
                if param_updated:
                    if selected_item_type == "file":
                        session_manager.update_session_context("last_referenced_file_path", selected_item_path)
                    elif selected_item_type == "folder":
                        # Only update if the action itself isn't listing (to avoid overwriting current list context with parent)
                        if not (current_action == "list_folder_contents" and selected_item_type == "file"):
                             session_manager.update_session_context("last_folder_listed_path", selected_item_path if selected_item_type=="folder" else os.path.dirname(selected_item_path))

                    if ui_module_passed:
                         ui_module_passed.print_info(f"Using item {item_index+1} ('{selected_item.get('name')}') for '{action_to_use}'. Path set to: [filepath]{updated_params.get(target_param_for_indexed_path)}[/filepath]")
                    return action_to_use, updated_params, True
                else:
                    if ui_module_passed:
                        ui_module_passed.print_warning(f"Found item {item_index+1}, but not sure how to apply it to '{current_action}'.", "Context Warning")
                    return current_action, current_params, False
            else:
                if ui_module_passed:
                    ui_module_passed.print_warning(f"Index {item_index + 1} out of range (1 to {len(last_results)}).", "Index Error")
                return current_action, current_params, False
        except ValueError:
            return current_action, current_params, False
    return current_action, current_params, False