# python/cli_ui.py

import time
from rich.console import Console # Keep this import at the top
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.align import Align
from rich.box import ROUNDED
from rich.markdown import Markdown
from rich.padding import Padding
from rich.theme import Theme

print("DEBUG: cli_ui.py: Top of file reached, Rich imports done.")

INITIAL_THEMED_CONSOLE_ID = None # Stores the ID of our themed console
_CODEX_THEME_INSTANCE = None # To store the theme instance

from .cli_constants import CUSTOM_THEME_DICT, ICONS, APP_LOGO_TEXT, APP_VERSION
print("DEBUG: cli_ui.py: Imported from .cli_constants.")

import sys
import os

# --- Start of config.py import block ---
OLLAMA_MODEL_IMPORTED_SUCCESSFULLY = False
OLLAMA_MODEL_VALUE = "config_not_loaded_or_error" # Fallback
try:
    print(f"DEBUG: cli_ui.py: About to modify sys.path. Current sys.path[0]: {sys.path[0] if sys.path else 'EMPTY'}")
    original_sys_path = list(sys.path)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    if sys.path[0] != project_root:
        if project_root in sys.path:
            sys.path.remove(project_root)
        sys.path.insert(0, project_root)
        print(f"DEBUG: cli_ui.py: sys.path adjusted. New sys.path[0]: {sys.path[0]}. Project root: {project_root}")
    else:
        print(f"DEBUG: cli_ui.py: Project root '{project_root}' is already at sys.path[0].")

    print(f"DEBUG: cli_ui.py: Attempting to import OLLAMA_MODEL from config.py (expected at: {os.path.join(project_root, 'config.py')})")
    
    config_file_path = os.path.join(project_root, 'config.py')
    if not os.path.exists(config_file_path):
        print(f"DEBUG: cli_ui.py: !!! CRITICAL ERROR - config.py NOT FOUND at {config_file_path}")
    else:
        print(f"DEBUG: cli_ui.py: config.py FOUND at {config_file_path}. Proceeding with import.")
        from config import OLLAMA_MODEL 
        OLLAMA_MODEL_VALUE = OLLAMA_MODEL
        OLLAMA_MODEL_IMPORTED_SUCCESSFULLY = True
        print(f"DEBUG: cli_ui.py: OLLAMA_MODEL imported successfully: {OLLAMA_MODEL_VALUE}")

    if sys.path[0] == project_root and (len(original_sys_path) == 0 or original_sys_path[0] != project_root):
        sys.path.pop(0) 
        print("DEBUG: cli_ui.py: sys.path restored by popping the project_root added by this block.")
    elif sys.path != original_sys_path : 
        print("DEBUG: cli_ui.py: sys.path differs from original_sys_path after config import. Manual review of sys.path changes might be needed.")

except ImportError as e_import:
    print(f"DEBUG: cli_ui.py: !!! CRITICAL IMPORT ERROR - Failed to import OLLAMA_MODEL from config.py: {e_import}")
    print(f"DEBUG: cli_ui.py: Project root was calculated as: {project_root}")
    print(f"DEBUG: cli_ui.py: Please ensure config.py exists at this location and defines OLLAMA_MODEL.")
except Exception as e_general:
    print(f"DEBUG: cli_ui.py: !!! UNEXPECTED ERROR during OLLAMA_MODEL import block: {e_general}")
    import traceback
    traceback.print_exc() 
finally:
    OLLAMA_MODEL = OLLAMA_MODEL_VALUE 
    print(f"DEBUG: cli_ui.py: Final OLLAMA_MODEL value being used: {OLLAMA_MODEL}. Imported successfully: {OLLAMA_MODEL_IMPORTED_SUCCESSFULLY}")
# --- End of config.py import block ---


print("DEBUG: cli_ui.py: About to create codex_theme from CUSTOM_THEME_DICT.")
try:
    _CODEX_THEME_INSTANCE = Theme(CUSTOM_THEME_DICT) # Store the theme instance
    print(f"DEBUG: cli_ui.py: _CODEX_THEME_INSTANCE created. Type: {type(_CODEX_THEME_INSTANCE)}")
    if hasattr(_CODEX_THEME_INSTANCE, 'styles'):
        print(f"DEBUG: cli_ui.py: _CODEX_THEME_INSTANCE HAS 'styles' attribute. Number of styles: {len(_CODEX_THEME_INSTANCE.styles)}")
    else:
        print("DEBUG: cli_ui.py: !!! CRITICAL - _CODEX_THEME_INSTANCE instance MISSING 'styles' attribute AFTER Theme() call.")
except Exception as e_theme:
    print(f"DEBUG: cli_ui.py: !!! CRITICAL ERROR creating _CODEX_THEME_INSTANCE: {e_theme}")
    _CODEX_THEME_INSTANCE = Theme({}) # Fallback


print("DEBUG: cli_ui.py: About to initialize module-level 'console' object.")
try:
    console = Console(theme=_CODEX_THEME_INSTANCE) 
    INITIAL_THEMED_CONSOLE_ID = id(console) 
    print(f"DEBUG: cli_ui.py: Module-level 'console' object initialized. Type: {type(console)}, ID: {id(console)} (This is INITIAL_THEMED_CONSOLE_ID)")

    if hasattr(console, 'theme') and console.theme is not None:
        print(f"DEBUG: cli_ui.py: Initialized 'console' HAS 'theme' attribute. Theme type: {type(console.theme)}, Theme ID: {id(console.theme)}")
        if hasattr(console.theme, 'styles'):
            print(f"DEBUG: cli_ui.py: Initialized 'console.theme' HAS 'styles'. Number of styles: {len(console.theme.styles)}")
        else:
            print("DEBUG: cli_ui.py: !!! CRITICAL - Initialized 'console.theme' MISSING 'styles' attribute.")
    else:
        print("DEBUG: cli_ui.py: !!! CRITICAL - Initialized 'console' MISSING 'theme' attribute or theme is None RIGHT AFTER Console(theme=_CODEX_THEME_INSTANCE) call.")
except Exception as e_console_init:
    print(f"DEBUG: cli_ui.py: !!! CRITICAL ERROR initializing 'console' object: {e_console_init}")
    print("DEBUG: cli_ui.py: Falling back to default Console() for further debugging.")
    console = Console() 
    INITIAL_THEMED_CONSOLE_ID = id(console) 


def print_panel_message(title: str, message: str, panel_style_name: str, icon: str = "", box_style=ROUNDED):
    global console # The module-level console
    global _CODEX_THEME_INSTANCE # The global theme instance
    
    print(f"\nDEBUG: cli_ui.py: ENTERING print_panel_message for title='{title}'")
    current_console_id = id(console)
    print(f"DEBUG: cli_ui.py: In print_panel_message - 'console' object. Type: {type(console)}, Current ID: {current_console_id}")
    print(f"DEBUG: cli_ui.py: Expected initial themed console ID was: {INITIAL_THEMED_CONSOLE_ID}")
    
    if INITIAL_THEMED_CONSOLE_ID is not None and current_console_id != INITIAL_THEMED_CONSOLE_ID:
        print("DEBUG: cli_ui.py: !!! CRITICAL - Console ID MISMATCH! The 'console' object in this function is DIFFERENT from the initially themed one.")
        # This case implies cli_ui.console was reassigned.
        # We could try to re-theme this new console object if it's a Console instance.
        if isinstance(console, Console) and _CODEX_THEME_INSTANCE is not None:
            print("DEBUG: cli_ui.py: Attempting to apply theme to a new console instance.")
            try:
                console.theme = _CODEX_THEME_INSTANCE
                print(f"DEBUG: cli_ui.py: Re-applied theme to NEW console (ID: {id(console)}).")
            except Exception as e_retheme_new:
                 print(f"DEBUG: cli_ui.py: Error re-applying theme to new console: {e_retheme_new}")

    # Check if the theme is missing from the (potentially original) console object
    if not hasattr(console, 'theme') or console.theme is None:
        print("DEBUG: cli_ui.py: In print_panel_message - Console theme is missing or None.")
        if isinstance(console, Console) and _CODEX_THEME_INSTANCE is not None:
            print("DEBUG: cli_ui.py: Attempting to re-apply _CODEX_THEME_INSTANCE to current console.")
            try:
                console.theme = _CODEX_THEME_INSTANCE
                print(f"DEBUG: cli_ui.py: Re-applied theme to console (ID: {id(console)}).")
                if not hasattr(console, 'theme') or console.theme is None:
                     print("DEBUG: cli_ui.py: FAILED to re-apply theme. Still missing after attempt.")
            except Exception as e_retheme:
                print(f"DEBUG: cli_ui.py: Error re-applying theme: {e_retheme}")
    
    effective_theme_styles = {} 
    if hasattr(console, 'theme') and console.theme is not None and hasattr(console.theme, 'styles'):
        print(f"DEBUG: cli_ui.py: In print_panel_message - 'console.theme' HAS 'styles'. First 5 keys: {list(console.theme.styles.keys())[:5]}")
        effective_theme_styles = console.theme.styles
    else:
        print("DEBUG: cli_ui.py: In print_panel_message - Console theme or its styles are still missing. Using fallback empty styles for this panel.")
    
    panel_title_style_key = f"panel.title.{panel_style_name}"
    panel_title_style = panel_title_style_key if panel_title_style_key in effective_theme_styles else "panel.title"

    panel_border_style_key = f"panel.border.{panel_style_name}"
    panel_border_style = panel_border_style_key if panel_border_style_key in effective_theme_styles else "panel.border"

    panel_title_text = f"{icon} {title}" if icon else title
    message_renderable = Text.from_markup(message) if isinstance(message, str) and "[" in message and "]" in message else Text(str(message))

    try:
        console.print(Panel(message_renderable,
                            title=f"[{panel_title_style}]{panel_title_text}[/]",
                            border_style=panel_border_style,
                            box=box_style,
                            padding=(1, 2)))
    except Exception as e_panel_print:
        print(f"DEBUG: cli_ui.py: ERROR during console.print(Panel(...)): {e_panel_print}")

    print(f"DEBUG: cli_ui.py: EXITING print_panel_message for title='{title}'\n")

def print_success(message: str, title: str = "Success"): print_panel_message(title, message, "success", ICONS.get("success","✅"))
def print_error(message: str, title: str = "Error"): print_panel_message(title, message, "error", ICONS.get("error","❌"))
def print_warning(message: str, title: str = "Warning"): print_panel_message(title, message, "warning", ICONS.get("warning","⚠️"))
def print_info(message: str, title: str = "Information"): print_panel_message(title, message, "info", ICONS.get("info","ℹ️"))


def print_startup_message_ui(connector) -> bool:
    global console, _CODEX_THEME_INSTANCE # Ensure we use module globals
    print("DEBUG: cli_ui.py: ENTERING print_startup_message_ui")
    
    # Sanity check for console and theme at startup
    if not isinstance(console, Console) or not hasattr(console, 'theme') or console.theme is None:
        print("DEBUG: cli_ui.py: In print_startup_message_ui - Console or theme is invalid. Attempting to fix.")
        if isinstance(console, Console) and _CODEX_THEME_INSTANCE:
            console.theme = _CODEX_THEME_INSTANCE
        else: # Fallback if console itself is not a Console object or _CODEX_THEME_INSTANCE is None
            console = Console(theme=_CODEX_THEME_INSTANCE if _CODEX_THEME_INSTANCE else Theme({}))
            print("DEBUG: cli_ui.py: Re-initialized console in print_startup_message_ui.")

    console.clear(); time.sleep(0.1)
    spinner_icon = ICONS.get('thinking', '🤔')
    spinner_renderable_text = Text.assemble(
        (spinner_icon, ""), (" ", ""), (f"Initializing SAM-Open Assistant...", "spinner_style")
    )
    with Live(Spinner("dots", text=spinner_renderable_text), console=console, transient=True, refresh_per_second=10):
        time.sleep(0.5)
    console.print(Align.center(Text(APP_LOGO_TEXT, style="app_logo_style")))
    status_items = []
    conn_ok, model_ok, _ = connector.check_connection_and_model()
    success_icon = ICONS.get('success', '✅')
    info_icon = ICONS.get('info', 'ℹ️')
    if not conn_ok:
        print_error(f"Ollama connection failed. Ensure Ollama is running at [highlight]{connector.base_url}[/highlight].", "Ollama Error")
        return False
    status_items.append(f"{success_icon} Connected to Ollama ([highlight]{connector.base_url}[/highlight])")
    if not model_ok:
        print_error(f"LLM '[highlight]{OLLAMA_MODEL}[/highlight]' not found. Check `config.py` or pull model with `ollama pull {OLLAMA_MODEL}`.", "Model Error")
        return False
    status_items.append(f"{success_icon} Using LLM: [highlight]{OLLAMA_MODEL}[/highlight]")
    console.print(Panel(Text.from_markup("\n".join(status_items)),
                        title=f"{info_icon} System Status", border_style="panel.border.info",
                        box=ROUNDED, padding=(1,2)))
    console.print(Padding(Text.from_markup(f"\n{info_icon} Type [prompt]help[/prompt] for commands, or [prompt]quit[/prompt] to exit."), (1,0)))
    print("DEBUG: cli_ui.py: EXITING print_startup_message_ui (successfully)")
    return True

def display_help():
    global console # Ensure we use module global
    print("DEBUG: cli_ui.py: ENTERING display_help")
    info_icon = ICONS.get('info', 'ℹ️')
    console.print(Panel(Markdown(f"""# SAM-Open (Sistem Asisten Mandiri) File Assistant Help {info_icon} (v{APP_VERSION})\n\n## Example Commands:\n*   `summarize "path/to/file.txt"` or `summarize "path/to/mydoc.pdf"`\n*   `what is in "doc.docx" about project alpha?`\n*   `list contents of "C:/folder"` OR `list item 3` (after search)\n*   `search for images in .`\n*   `search python scripts containing 'db_utils' in "~/dev/my_project"`\n*   `search images "C:/Users/Name/Pictures"`\n*   `move "old.txt" to "archive/"` or `move item 1 to "new_folder/"`\n*   `organize this folder by type` (after list/search)\n*   `organize "C:/Downloads" by file extension` or `organize "folder" by name`\n*   `show my last 5 activities` / `view log history`\n*   `redo last search` / `redo task 2`\n\n## Notes:\n*   Use quotes for paths with spaces.\n*   Context is remembered (e.g., `summarize item 1` after a search).\n*   File organization is experimental; always review plans before execution."""),
                        title=f"{info_icon} Help", border_style="panel.border.info",
                        box=ROUNDED,padding=1))
    print("DEBUG: cli_ui.py: EXITING display_help")

def display_chain_of_thought(thought_text: str):
    global console # Ensure we use module global
    print("DEBUG: cli_ui.py: ENTERING display_chain_of_thought")
    thinking_icon = ICONS.get('thinking', '🤔')
    if thought_text:
        formatted_thought_text = thought_text.replace("\\n", "\n")
        # Before printing, quickly check and try to restore theme if missing
        if (not hasattr(console, 'theme') or console.theme is None) and _CODEX_THEME_INSTANCE:
            print("DEBUG: cli_ui.py: Theme missing before display_chain_of_thought panel. Attempting restore.")
            console.theme = _CODEX_THEME_INSTANCE

        panel_content = Text(formatted_thought_text, style="italic dim")
        console.print(Panel(panel_content, title=f"{thinking_icon} My Reasoning", border_style="blue", expand=False, padding=(0,1)))
    print("DEBUG: cli_ui.py: EXITING display_chain_of_thought")

def ask_question_prompt(question: str) -> str:
    global console # Ensure we use module global
    print("DEBUG: cli_ui.py: ENTERING ask_question_prompt")
    question_icon = ICONS.get('question', '❓')
    input_icon = ICONS.get('input', '>')
    question_text_obj = Text.from_markup(question) if "[/]" in question else Text(question, style="bold yellow")
    
    # Before printing, quickly check and try to restore theme if missing
    if (not hasattr(console, 'theme') or console.theme is None) and _CODEX_THEME_INSTANCE:
        print("DEBUG: cli_ui.py: Theme missing before ask_question_prompt panel. Attempting restore.")
        console.theme = _CODEX_THEME_INSTANCE

    console.print(Panel(question_text_obj,
                        title=f"{question_icon} Clarification Needed", border_style="yellow",
                        expand=False, padding=(0,1)))
    response = console.input(Text.from_markup(f"{input_icon} [prompt_clarify]Your clarification[/prompt_clarify][prompt]> [/prompt]"))
    print("DEBUG: cli_ui.py: EXITING ask_question_prompt")
    return response.strip()

print("DEBUG: cli_ui.py: End of file reached, all definitions complete.")