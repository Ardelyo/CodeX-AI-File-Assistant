
import os
from rich.prompt import Prompt
from rich.text import Text
from cli_constants import ICONS # Assuming ICONS are needed for prompts
# cli_ui.console will be passed to get_path_from_user_input

def get_path_from_user_input(console_instance, prompt_message="Please provide the full path", default_path=None, is_folder=False):
    path_type = "folder" if is_folder else "file/folder"
    prompt_suffix = f" ([filepath]{path_type}[/filepath])"
    styled_prompt = Text.from_markup(f"{ICONS['confirm']} {prompt_message}{prompt_suffix}")
    if default_path:
        styled_prompt.append(f" [dim_text](default: [filepath]{default_path}[/filepath])[/dim_text]")
    # Use the passed console_instance for Prompt
    path = Prompt.ask(styled_prompt, default=default_path if default_path else ..., console=console_instance)
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