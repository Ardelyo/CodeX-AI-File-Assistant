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

from .cli_constants import CUSTOM_THEME_DICT, ICONS, APP_LOGO_TEXT, APP_VERSION


import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import OLLAMA_MODEL 
sys.path.pop(0) 

# Create a Theme object from the dictionary
# CUSTOM_THEME_DICT is the dictionary { "style_name": "style_definition_string", ... }
# The Theme constructor will parse these strings into Style objects.
codex_theme = Theme(CUSTOM_THEME_DICT)

# Initialize console with the Theme object
console = Console(theme=codex_theme) # <--- Pass the Theme object

# ... rest of the cli_ui.py file remains the same as the previous version ...
# (print_panel_message, print_success, etc.)
def print_panel_message(title: str, message: str, panel_style_name: str, icon: str = "", box_style=ROUNDED):
    # Dynamically construct style names, fallback to generic if specific not in theme
    # Accessing console.theme.styles will now work because console.theme is a Theme object
    panel_title_style_key = f"panel.title.{panel_style_name}"
    panel_title_style = panel_title_style_key if panel_title_style_key in console.theme.styles else "panel.title"
    
    panel_border_style_key = f"panel.border.{panel_style_name}"
    panel_border_style = panel_border_style_key if panel_border_style_key in console.theme.styles else "panel.border"
    
    panel_title_text = f"{icon} {title}" if icon else title
    
    message_renderable = Text.from_markup(message) if isinstance(message, str) and "[" in message and "]" in message else Text(str(message)) # Ensure message is string for Text

    console.print(Panel(message_renderable, 
                        title=f"[{panel_title_style}]{panel_title_text}[/]", 
                        border_style=panel_border_style, 
                        box=box_style, 
                        padding=(1, 2)))

def print_success(message: str, title: str = "Success"): print_panel_message(title, message, "success", ICONS.get("success","✅"))
def print_error(message: str, title: str = "Error"): print_panel_message(title, message, "error", ICONS.get("error","❌"))
def print_warning(message: str, title: str = "Warning"): print_panel_message(title, message, "warning", ICONS.get("warning","⚠️"))
def print_info(message: str, title: str = "Information"): print_panel_message(title, message, "info", ICONS.get("info","ℹ️"))


def print_startup_message_ui(connector) -> bool: 
    console.clear(); time.sleep(0.1)
    
    spinner_icon = ICONS.get('thinking', '🤔')
    spinner_renderable_text = Text.assemble(
        (spinner_icon, ""), 
        (" ", ""), 
        (f"Initializing CodeX Assistant...", "spinner_style") 
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
                        title=f"{info_icon} System Status", 
                        border_style="panel.border.info",
                        box=ROUNDED, 
                        padding=(1,2)))
    console.print(Padding(Text.from_markup(f"\n{info_icon} Type [prompt]help[/prompt] for commands, or [prompt]quit[/prompt] to exit."), (1,0)))
    return True

def display_help(): 
    info_icon = ICONS.get('info', 'ℹ️')
    console.print(Panel(Markdown(f"""# CodeX AI Assistant Help {info_icon} (v{APP_VERSION})\n\n## Example Commands:\n*   `summarize "path/to/file.txt"` or `summarize "path/to/mydoc.pdf"`\n*   `what is in "doc.docx" about project alpha?`\n*   `list contents of "C:/folder"` OR `list item 3` (after search)\n*   `search for images in .`\n*   `search python scripts containing 'db_utils' in "~/dev/projects/CodeX"`\n*   `search images "C:/Users/Name/Pictures"`\n*   `move "old.txt" to "archive/"` or `move item 1 to "new_folder/"`\n*   `organize this folder by type` (after list/search)\n*   `organize "C:/Downloads" by file extension` or `organize "folder" by name`\n*   `show my last 5 activities` / `view log history`\n*   `redo last search` / `redo task 2`\n\n## Notes:\n*   Use quotes for paths with spaces.\n*   Context is remembered (e.g., `summarize item 1` after a search).\n*   File organization is experimental; always review plans before execution."""),
                        title=f"{info_icon} Help",
                        border_style="panel.border.info", 
                        box=ROUNDED,padding=1))

def display_chain_of_thought(thought_text: str):
    thinking_icon = ICONS.get('thinking', '🤔')
    if thought_text:
        formatted_thought_text = thought_text.replace("\\n", "\n")
        panel_content = Text(formatted_thought_text, style="italic dim") 
        console.print(Panel(panel_content, title=f"{thinking_icon} My Reasoning", border_style="blue", expand=False, padding=(0,1)))

def ask_question_prompt(question: str) -> str:
    question_icon = ICONS.get('question', '❓')
    input_icon = ICONS.get('input', '>')
    
    question_text_obj = Text.from_markup(question) if "[/]" in question else Text(question, style="bold yellow")
    
    console.print(Panel(question_text_obj, 
                        title=f"{question_icon} Clarification Needed", 
                        border_style="yellow", 
                        expand=False, 
                        padding=(0,1)))
    response = console.input(Text.from_markup(f"{input_icon} [prompt_clarify]Your clarification[/prompt_clarify][prompt]> [/prompt]"))
    return response.strip()