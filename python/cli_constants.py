# python/cli_constants.py

# Theme for Rich console - This is now just a dictionary of style definitions.
# The Theme object will be created in cli_ui.py.
CUSTOM_THEME_DICT = {  # Renamed to make its purpose clear
    "app_logo_style": "bold green",
    "prompt": "bold cyan",
    "prompt_path": "dim blue",
    "prompt_arrow": "bold cyan",
    "prompt_clarify": "yellow",
    "filepath": "bright_blue",
    "highlight": "bold magenta",
    "spinner_style": "bold blue", 
    "dim_text": "dim",
    "danger": "bold red",
    "panel.title": "bold white on blue", # Default panel title
    "panel.title.success": "bold white on green",
    "panel.title.error": "bold white on red",
    "panel.title.warning": "bold black on yellow",
    "panel.title.info": "bold white on blue",
    "panel.border": "dim", # Default panel border
    "panel.border.success": "green",
    "panel.border.error": "red",
    "panel.border.warning": "yellow",
    "panel.border.info": "blue",
    "table.header": "bold cyan",
    "separator_style": "dim cyan"
}

ICONS = {
    "app_icon": "🤖",
    "thinking": "🤔", 
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "question": "❓",
    "confirm": "👉",
    "file": "📄",
    "folder": "📁",
    "search": "🔍",
    "summary": "📝",
    "answer": "💡",
    "log": "📜",
    "redo": "🔄",
    "plan": "📋",
    "create_folder": "➕📁",
    "move": "➡️",
    "execute": "🚀",
    "input": "💬",
    "prompt": "❯",
}

APP_LOGO_TEXT = """
  ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
 ██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
 ██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
 ╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
"""

APP_VERSION = "v1.8.0-phase1.1"

KNOWN_BAD_EXAMPLE_PATHS = [
    "path/to/", 
    "C:/path/to", 
    "/path/to", 
    "example/path",
    "your/file/here",
    "directory/name"
]