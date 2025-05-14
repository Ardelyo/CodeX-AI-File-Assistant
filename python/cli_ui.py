# python/cli_ui.py

import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.align import Align
from rich.box import ROUNDED
from rich.markdown import Markdown
from rich.padding import Padding
from rich.theme import Theme

print("DEBUG: cli_ui.py: Top of file reached, Rich imports done.") # DEBUG Line 1

from .cli_constants import CUSTOM_THEME_DICT, ICONS, APP_LOGO_TEXT, APP_VERSION
print("DEBUG: cli_ui.py: Imported from .cli_constants.") # DEBUG Line 2

import sys
import os

# --- Start of config.py import block ---
OLLAMA_MODEL_IMPORTED_SUCCESSFULLY = False
OLLAMA_MODEL_VALUE = "config_not_loaded_or_error"
try:
    print(f"DEBUG: cli_ui.py: About to modify sys.path. Current sys.path[0]: {sys.path[0] if sys.path else 'EMPTY'}")
    original_sys_path = list(sys.path)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"DEBUG: cli_ui.py: sys.path modified. New sys.path[0]: {sys.path[0]}. Project root: {project_root}")
    else:
        print(f"DEBUG: cli_ui.py: Project root '{project_root}' already in sys.path.")

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

    if project_root == sys.path[0] and project_root not in original_sys_path: 
        sys.path.pop(0)
        print("DEBUG: cli_ui.py: sys.path restored by popping the project_root.")
    elif sys.path != original_sys_path: 
        sys.path = original_sys_path
        print("DEBUG: cli_ui.py: sys.path restored to original_sys_path object.")


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


print("DEBUG: cli_ui.py: About to create codex_theme from CUSTOM_THEME_DICT.") # DEBUG Line 3
try:
    codex_theme = Theme(CUSTOM_THEME_DICT)
    print(f"DEBUG: cli_ui.py: codex_theme created. Type: {type(codex_theme)}") # DEBUG Line 4
    if hasattr(codex_theme, 'styles'):
        print(f"DEBUG: cli_ui.py: codex_theme HAS 'styles' attribute. Number of styles: {len(codex_theme.styles)}")
    else:
        print("DEBUG: cli_ui.py: !!! CRITICAL - codex_theme instance MISSING 'styles' attribute AFTER Theme() call.")
except Exception as e_theme:
    print(f"DEBUG: cli_ui.py: !!! CRITICAL ERROR creating codex_theme: {e_theme}")
    codex_theme = Theme({}) 


print("DEBUG: cli_ui.py: About to initialize module-level 'console' object.") # DEBUG Line 5
try:
    console = Console(theme=codex_theme) 
    print(f"DEBUG: cli_ui.py: Module-level 'console' object initialized. Type: {type(console)}, ID: {id(console)}") # DEBUG Line 6

    if hasattr(console, 'theme'):
        print(f"DEBUG: cli_ui.py: Initialized 'console' HAS 'theme' attribute. Theme type: {type(console.theme)}, Theme ID: {id(console.theme)}")
        if hasattr(console.theme, 'styles'):
            print(f"DEBUG: cli_ui.py: Initialized 'console.theme' HAS 'styles'. Number of styles: {len(console.theme.styles)}")
        else:
            print("DEBUG: cli_ui.py: !!! CRITICAL - Initialized 'console.theme' MISSING 'styles' attribute.")
    else:
        print("DEBUG: cli_ui.py: !!! CRITICAL - Initialized 'console' MISSING 'theme' attribute RIGHT AFTER Console(theme=codex_theme) call.")
except Exception as e_console_init:
    print(f"DEBUG: cli_ui.py: !!! CRITICAL ERROR initializing 'console' object: {e_console_init}")
    print("DEBUG: cli_ui.py: Falling back to default Console() for further debugging.")
    console = Console() 

def print_panel_message(title: str, message: str, panel_style_name: str, icon: str = "", box_style=ROUNDED):
    print(f"\nDEBUG: cli_ui.py: ENTERING print_panel_message for title='{title}'")
    print(f"DEBUG: cli_ui.py: In print_panel_message - 'console' object. Type: {type(console)}, ID: {id(console)}")

    effective_theme_styles = {} # Default to empty styles

    if not hasattr(console, 'theme'):
        print("DEBUG: cli_ui.py: In print_panel_message - !!! 'console' object MISSING 'theme' attribute. THIS IS THE PROBLEM.")
        print("DEBUG: cli_ui.py: Using fallback empty styles for this panel print due to missing theme on console.")
    else:
        print(f"DEBUG: cli_ui.py: In print_panel_message - 'console' HAS 'theme'. Theme type: {type(console.theme)}, Theme ID: {id(console.theme)}")
        if hasattr(console.theme, 'styles'):
            print(f"DEBUG: cli_ui.py: In print_panel_message - 'console.theme' HAS 'styles'. First 5 keys: {list(console.theme.styles.keys())[:5]}")
            effective_theme_styles = console.theme.styles # Use the actual styles
        else:
            print("DEBUG: cli_ui.py: In print_panel_message - !!! 'console.theme' MISSING 'styles' attribute (but .theme exists).")
            print("DEBUG: cli_ui.py: Using fallback empty styles for this panel print due to missing styles on console.theme.")
    
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
    print("DEBUG: cli_ui.py: ENTERING print_startup_message_ui")
    if not hasattr(console, 'theme'):
         print("DEBUG: cli_ui.py: In print_startup_message_ui - !!! 'console' object MISSING 'theme' attribute AT FUNCTION START.")
    else:
        print(f"DEBUG: cli_ui.py: In print_startup_message_ui - 'console' (ID: {id(console)}) has 'theme' (ID: {id(console.theme)}).")

    console.clear(); time.sleep(0.1)
    spinner_icon = ICONS.get('thinking', '🤔')
    spinner_renderable_text = Text.assemble(
        (spinner_icon, ""), (" ", ""), (f"Initializing CodeX Assistant...", "spinner_style")
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
    print("DEBUG: cli_ui.py: ENTERING display_help")
    info_icon = ICONS.get('info', 'ℹ️')
    console.print(Panel(Markdown(f"""# CodeX AI Assistant Help {info_icon} (v{APP_VERSION})\n\n## Example Commands:\n*   `summarize "path/to/file.txt"` or `summarize "path/to/mydoc.pdf"`\n*   `what is in "doc.docx" about project alpha?`\n*   `list contents of "C:/folder"` OR `list item 3` (after search)\n*   `search for images in .`\n*   `search python scripts containing 'db_utils' in "~/dev/projects/CodeX"`\n*   `search images "C:/Users/Name/Pictures"`\n*   `move "old.txt" to "archive/"` or `move item 1 to "new_folder/"`\n*   `organize this folder by type` (after list/search)\n*   `organize "C:/Downloads" by file extension` or `organize "folder" by name`\n*   `show my last 5 activities` / `view log history`\n*   `redo last search` / `redo task 2`\n\n## Notes:\n*   Use quotes for paths with spaces.\n*   Context is remembered (e.g., `summarize item 1` after a search).\n*   File organization is experimental; always review plans before execution."""),
                        title=f"{info_icon} Help", border_style="panel.border.info",
                        box=ROUNDED,padding=1))
    print("DEBUG: cli_ui.py: EXITING display_help")

def display_chain_of_thought(thought_text: str):
    print("DEBUG: cli_ui.py: ENTERING display_chain_of_thought")
    thinking_icon = ICONS.get('thinking', '🤔')
    if thought_text:
        formatted_thought_text = thought_text.replace("\\n", "\n")
        panel_content = Text(formatted_thought_text, style="italic dim")
        console.print(Panel(panel_content, title=f"{thinking_icon} My Reasoning", border_style="blue", expand=False, padding=(0,1)))
    print("DEBUG: cli_ui.py: EXITING display_chain_of_thought")

def ask_question_prompt(question: str) -> str:
    print("DEBUG: cli_ui.py: ENTERING ask_question_prompt")
    question_icon = ICONS.get('question', '❓')
    input_icon = ICONS.get('input', '>')
    question_text_obj = Text.from_markup(question) if "[/]" in question else Text(question, style="bold yellow")
    console.print(Panel(question_text_obj,
                        title=f"{question_icon} Clarification Needed", border_style="yellow",
                        expand=False, padding=(0,1)))
    response = console.input(Text.from_markup(f"{input_icon} [prompt_clarify]Your clarification[/prompt_clarify][prompt]> [/prompt]"))
    print("DEBUG: cli_ui.py: EXITING ask_question_prompt")
    return response.strip()

print("DEBUG: cli_ui.py: End of file reached, all definitions complete.")