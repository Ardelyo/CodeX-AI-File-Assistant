
import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.align import Align
from rich.box import ROUNDED, HEAVY # Ensure HEAVY is imported if used by Panel
from rich.markdown import Markdown # For help message
from rich.padding import Padding # For help message and startup message

# Corrected import for cli_constants (assuming cli_constants.py is in the same 'python' directory)
from .cli_constants import CUSTOM_THEME, ICONS, APP_LOGO_TEXT, APP_VERSION
# To import config.py from the parent directory (project root)
import sys
import os
# Add the parent directory (project root) to sys.path to find config.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import OLLAMA_MODEL # Now it should find config.py
sys.path.pop(0) # Clean up sys.path

# Initialize console here to be imported by other modules
console = Console(theme=CUSTOM_THEME)

def print_panel_message(title: str, message: str, panel_style_name: str, icon: str = "", box_style=ROUNDED):
    panel_title_style = f"panel.title.{panel_style_name}" if f"panel.title.{panel_style_name}" in CUSTOM_THEME.styles else "panel.title"
    panel_border_style = f"panel.border.{panel_style_name}" if f"panel.border.{panel_style_name}" in CUSTOM_THEME.styles else "panel.border"
    panel_title_text = f"{icon} {title}" if icon else title
    console.print(Panel(Text(message, justify="left"), title=f"[{panel_title_style}]{panel_title_text}[/]", border_style=panel_border_style, box=box_style, padding=(1, 2)))

def print_success(message: str, title: str = "Success"): print_panel_message(title, message, "success", ICONS["success"])
def print_error(message: str, title: str = "Error"): print_panel_message(title, message, "error", ICONS["error"])
def print_warning(message: str, title: str = "Warning"): print_panel_message(title, message, "warning", ICONS["warning"])
def print_info(message: str, title: str = "Information"): print_panel_message(title, message, "info", ICONS["info"])


def print_startup_message_ui(connector) -> bool: # Renamed to avoid conflict if main_cli still has one
    console.clear(); time.sleep(0.1)
    with Live(Spinner("dots", text=f"{ICONS['thinking']} [spinner_style]Initializing CodeX Assistant...[/spinner_style]"), console=console, transient=True, refresh_per_second=10):
        time.sleep(0.5)
    console.print(Align.center(APP_LOGO_TEXT))
    status_items = []
    conn_ok, model_ok, _ = connector.check_connection_and_model()
    if not conn_ok:
        print_error("Ollama connection failed. Ensure Ollama is running.", "Ollama Error")
        return False
    status_items.append(f"{ICONS['success']} Connected to Ollama ([highlight]{connector.base_url}[/highlight])")
    if not model_ok:
        print_error(f"LLM '[highlight]{OLLAMA_MODEL}[/highlight]' not found. Check `config.py` or pull model with `ollama pull {OLLAMA_MODEL}`.", "Model Error")
        return False
    status_items.append(f"{ICONS['success']} Using LLM: [highlight]{OLLAMA_MODEL}[/highlight]")
    console.print(Panel(Text.from_markup("\n".join(status_items)), title=f"{ICONS['info']} System Status", border_style="panel.border.info", box=ROUNDED, padding=(1,2)))
    console.print(Padding(Text.from_markup(f"\n{ICONS['info']} Type [prompt]help[/prompt] for commands, or [prompt]quit[/prompt] to exit."), (1,0)))
    return True

def display_help():
    console.print(Panel(Markdown(f"""# CodeX AI Assistant Help {ICONS['info']} (v{APP_VERSION})\n\n## Example Commands:\n*   `summarize "path/to/file.txt"` or `summarize "path/to/mydoc.pdf"`\n*   `what is in "doc.docx" about project alpha?`\n*   `list contents of "C:/folder"` OR `list item 3` (after search)\n*   `search for images in .`\n*   `search python scripts containing 'db_utils' in "~/dev/projects/CodeX"`\n*   `search images "C:/Users/Name/Pictures"`\n*   `move "old.txt" to "archive/"` or `move item 1 to "new_folder/"`\n*   `organize this folder by type` (after list/search)\n*   `organize "C:/Downloads" by file extension` or `organize "folder" by name`\n*   `show my last 5 activities` / `view log history`\n*   `redo last search` / `redo task 2`\n\n## Notes:\n*   Use quotes for paths with spaces.\n*   Context is remembered (e.g., `summarize item 1` after a search).\n*   File organization is experimental; always review plans before execution."""),title=f"{ICONS['info']} Help",border_style="panel.border.info",box=ROUNDED,padding=1))