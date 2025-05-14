import os
from rich.prompt import Prompt
from rich.text import Text

# Corrected relative import: cli_constants is in the same 'python' package
from .cli_constants import ICONS 
# cli_ui.console will be passed to get_path_from_user_input
# No direct import of cli_ui here unless specific functions from it are needed globally in this module.

def get_path_from_user_input(console_instance, prompt_message="Please provide the full path", default_path=None, is_folder=False):
    path_type = "folder" if is_folder else "file/folder"
    prompt_suffix = f" ([filepath]{path_type}[/filepath])"
    
    # Construct prompt text carefully
    prompt_parts = [Text.from_markup(f"{ICONS.get('confirm', '?')} {prompt_message}{prompt_suffix}")]
    if default_path:
        prompt_parts.append(Text.from_markup(f" [dim_text](default: [filepath]{default_path}[/filepath])[/dim_text]"))
    
    full_prompt_text = Text.assemble(*prompt_parts)

    # Use the passed console_instance for Prompt
    # Allow empty input if no default, which might signify cancellation or skipping
    path_input = Prompt.ask(full_prompt_text, default=default_path if default_path else ..., console=console_instance)
    
    if path_input == ... and default_path is None: # User likely hit Enter on an empty prompt with no default
        return None # Indicate cancellation or skipped input
    
    # If Prompt.ask returns '...' because there was no default and user hit Enter,
    # it means they provided no input. If there was a default, it would return the default.
    # So if path_input is '...' it effectively means empty input when no default was set.
    if path_input is ... : path_input = ""


    stripped_path = path_input.strip().strip("'\"")
    if not stripped_path: # If after stripping, the path is empty
        return None # Treat empty input as cancellation or skipped

    return os.path.abspath(stripped_path)


def resolve_contextual_path(parameter_value_from_llm: str, session_ctx: dict, is_folder_hint: bool = False):
    """
    Resolves special path placeholders like "__FROM_CONTEXT__", "__CURRENT_DIR__".
    Does NOT handle general relative paths here; that's done in _resolve_single_path_parameter.
    """
    # Ensure session_ctx is not None
    if session_ctx is None:
        session_ctx = {} # Default to empty dict if None to avoid NoneType errors

    if parameter_value_from_llm == "__FROM_CONTEXT__":
        # Prioritize based on is_folder_hint and availability
        if is_folder_hint:
            if session_ctx.get("last_folder_listed_path"):
                return session_ctx["last_folder_listed_path"]
            if session_ctx.get("last_referenced_file_path"): # If last ref was a file, its parent might be the context folder
                path_to_check = session_ctx["last_referenced_file_path"]
                if os.path.isfile(path_to_check):
                    return os.path.dirname(path_to_check)
                elif os.path.isdir(path_to_check): # Should not happen if last_ref_file is for files
                    return path_to_check 
            # Fallback to CWD if no specific folder context
            return session_ctx.get("current_directory", os.getcwd())

        # Not specifically a folder hint, can be file or folder
        if session_ctx.get("last_referenced_file_path"):
            return session_ctx["last_referenced_file_path"]
        if session_ctx.get("last_folder_listed_path"): # If no specific file, maybe the last folder is relevant
            return session_ctx["last_folder_listed_path"]
        # Fallback to CWD if no specific file/folder context
        return session_ctx.get("current_directory", os.getcwd())
        
    elif parameter_value_from_llm == "__CURRENT_DIR__":
        return session_ctx.get("current_directory", os.getcwd())
        
    # If not a special placeholder, return the value as is (could be an explicit path or None/empty)
    return parameter_value_from_llm