
from rich.theme import Theme
from rich.box import ROUNDED, HEAVY # Used in CUSTOM_THEME, ensure import

APP_VERSION = "1.8.0" # Centralized version

ICONS = {
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️",
    "thinking": "🧠", "plan": "📝", "execute": "🚀", "folder": "📁",
    "file": "📄", "search": "🔍", "question": "❓", "answer": "💡",
    "summary": "📋", "log": "📜", "redo": "🔄", "confirm": "🤔",
    "move": "📦", "create_folder": "➕📁", "app_icon": "🗂️", "organize": "🪄"
}

CUSTOM_THEME = Theme({
    "info": "dim cyan", "warning": "yellow", "danger": "bold red", "success": "green",
    "prompt": "bold #32CD32", "user_input_display": "italic #F0E68C",
    "filepath": "cyan", "highlight": "bold magenta",
    "panel.title": "bold white on #007ACC", "panel.border": "#007ACC",
    "panel.title.success": "bold white on green", "panel.border.success": "green",
    "panel.title.error": "bold white on red", "panel.border.error": "red",
    "panel.title.warning": "bold black on yellow", "panel.border.warning": "yellow",
    "panel.title.info": "bold white on #4682B4", "panel.border.info": "#4682B4",
    "table.header": "bold #007ACC", "table.cell": "default",
    "spinner_style": "bold #FF69B4", "progress.bar": "#4169E1",
    "progress.percentage": "cyan", "app_logo_style": "bold #007ACC",
    "separator_style": "dim #007ACC", "dim_text": "dim default"
})

APP_LOGO_TEXT = f"""
{ICONS['app_icon']} [app_logo_style]
 ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
        AI File Assistant v{APP_VERSION}[/app_logo_style] 
"""

# Paths that LLM might hallucinate, used in NLU processing
KNOWN_BAD_EXAMPLE_PATHS = ["c:/reports/annual.docx"]