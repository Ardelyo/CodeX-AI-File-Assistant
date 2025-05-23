
# AI Assistant System Context: SAM-Open (Sistem Asisten Mandiri) File Assistant

This document provides the necessary context for an AI assistant to understand and effectively contribute to the "SAM-Open (Sistem Asisten Mandiri) File Assistant" project.

## 1. Project Overview

*   **Project Name:** SAM-Open (Sistem Asisten Mandiri) File Assistant
*   **Version (as of this context):** v1.8.0
*   **Tagline:** Transforming File Management with Local AI Intelligence
*   **Core Purpose:** A sophisticated command-line utility that uses locally-run Large Language Models (LLMs) via Ollama to provide an intuitive, natural language interface for managing, understanding, and organizing files on a local system.
*   **Creator:** Ardellio Satria Anindito (9th Grade Student, 2023-2025)
*   **License:** MIT

### 1.1. Key Features:
    *   Natural Language Understanding for file operations.
    *   Local LLM processing (via Ollama) for privacy and offline capability.
    *   Deep file content interaction: summarization, Q&A for various file types (.txt, .py, .md, .docx).
    *   Advanced file system operations: listing, recursive search (name, type, LLM-assisted content), secure move.
    *   Experimental Agentic Organization: AI-generated (or Python heuristic fallback) plans for folder organization, user-reviewed execution.
    *   Session Context & Persistence: Remembers last interactions (file, folder, search results) across restarts.
    *   Comprehensive Activity Logging: Detailed logs for review, audit, and a "redo" functionality.
    *   Rich Terminal User Interface (via `rich` library).

### 1.2. Technology Stack:
    *   **Core Language:** Python (3.9+)
    *   **AI Engine:** Local LLMs (e.g., `gemma:2b`, `mistral`, `llama3:8b`)
    *   **LLM Orchestration:** Ollama
    *   **CLI Enhancement:** `rich` library
    *   **Document Parsing:** `python-docx`
    *   **Configuration:** `config.py`
    *   **Data Persistence:** JSON for session (`session_context.json`), JSON Lines for activity log (`activity_log.jsonl`).

## 2. Core Application Workflow

1.  **User Input:** User types a command in natural language.
2.  **Direct Parsing:** Input is first attempted by regex-based "direct parsers" for common, simple commands.
3.  **LLM NLU (Fallback):** If no direct match or the query is complex, the input is sent to the local LLM (via Ollama) to determine intent and extract parameters.
4.  **Contextual Resolution:** Session history (last file, folder, search results) is used to resolve contextual references (e.g., "summarize item 1").
5.  **Parameter Finalization:** Paths are resolved, and missing parameters are prompted from the user.
6.  **Action Dispatch:** The identified action and its parameters are sent to the appropriate handler.
7.  **Tooling & Execution:**
    *   File system tools perform operations like read, list, move.
    *   LLM is used for content-related tasks (summarization, Q&A).
    *   LLM (or Python heuristic) generates organization plans for the "organize" command.
8.  **Output & Logging:** Results are displayed in the CLI using `rich`. The action, parameters, and outcome are logged to `activity_log.jsonl`. Session context is updated.

## 3. Directory Structure and File Descriptions

```
.
├── .venv/                         # Python virtual environment (ignore for code changes)
├── python/                        # **Core application logic - Refactored Modules**
│   ├── action_handlers.py         # Defines functions to handle specific user actions (e.g., summarize, list, move). Contains the main action dispatch map.
│   ├── cli_constants.py         # Stores global constants: ICONS, CUSTOM_THEME, APP_LOGO_TEXT, APP_VERSION, KNOWN_BAD_EXAMPLE_PATHS.
│   ├── cli_ui.py                # Manages Rich console, UI printing helpers (panels, success/error messages), startup messages, help display.
│   ├── direct_parsers.py        # Contains regex-based parsers for direct command interpretation (e.g., "list /path", "search X in Y").
│   ├── fs_utils.py              # File system utility functions, e.g., `is_path_within_base` for security checks.
│   ├── main_cli.py              # Main entry point of the application. Orchestrates the command loop, NLU, action dispatching.
│   ├── nlu_processor.py         # Processes NLU results (from direct parsers or LLM), finalizes parameters, resolves indexed references.
│   ├── path_resolver.py         # Handles resolving contextual paths and getting path input from the user via prompts.
│   └── session_manager.py       # Manages loading, saving, and updating the session context (_session_context).
├── __pycache__/                 # Python bytecode cache (ignore)
├── activity_log.jsonl           # Stores a history of all actions performed by the user and system (JSON Lines format).
├── activity_logger.py           # Module for logging actions to `activity_log.jsonl` and retrieving activities.
├── changelog.md                 # Tracks project changes, new features, and bug fixes across versions.
├── config.py                    # Application configuration: OLLAMA_API_BASE_URL, OLLAMA_MODEL.
├── file_utils.py                # Core file system interaction utilities: get_file_content, move_item, list_folder_contents, search_files_recursive.
├── insight.md                   # Potentially developer notes, design decisions, or insights (content not specified in current context).
├── ollama_connector.py          # Handles all communication with the Ollama API (sending requests, receiving LLM responses).
├── readme.md                    # **Primary user and developer documentation.** Describes features, setup, usage. (This is the source for much of this AI context).
├── requirements.txt             # Lists Python package dependencies for the project.
└── session_context.json         # Stores persistent session data like last referenced file/folder and command history.
```

**Note on `python/` subdirectory:** This directory contains the primary, refactored Python modules of the application, promoting better organization.

## 4. Key Design Principles & Patterns

*   **Modularity:** Code is broken down into logical modules (as seen in the `python/` directory and other top-level `.py` files). Aim to maintain this separation.
*   **Local First/Privacy:** All AI processing and file operations are local. No data is sent to external services.
*   **Rich CLI:** The `rich` library is used extensively for an enhanced user experience. UI elements should leverage `rich` components.
*   **Ollama Integration:** `ollama_connector.py` is the sole interface to Ollama.
*   **Session Management:** `session_manager.py` and `session_context.json` handle persistent context.
*   **Activity Logging:** `activity_logger.py` and `activity_log.jsonl` provide an audit trail and "redo" capability.
*   **Direct Parsers & LLM Fallback:** A two-stage NLU approach for efficiency and robustness.
*   **Explicit Confirmation:** Critical operations like "move" and "execute organization plan" require user confirmation.
*   **Path Safety:** Efforts are made to ensure file operations are safe (e.g., `is_path_within_base` for organization plans).

## 5. Instructions for the AI Assistant

When assisting with this project, please adhere to the following:

1.  **Understand the Goal:** Always refer to the project's core purpose: an AI-powered CLI file assistant using local LLMs.
2.  **Prioritize Existing Structure:**
    *   When adding new features or fixing bugs, try to fit changes within the existing modular structure described in Section 3.
    *   For example, new UI elements go in `cli_ui.py`, new action logic in `action_handlers.py`, new direct parsers in `direct_parsers.py`.
3.  **Code Style and Patterns:**
    *   Follow Python best practices (PEP 8).
    *   Observe existing coding patterns within the project.
    *   Utilize type hinting where appropriate.
    *   Ensure new code interacting with the user leverages the `rich` library via `cli_ui.py` helpers.
4.  **Documentation:**
    *   The `readme.md` is the primary source of user-facing documentation. If a feature change impacts users, consider how `readme.md` might need updates.
    *   `changelog.md` should be updated for significant changes.
    *   Add code comments and docstrings for clarity.
5.  **Configuration:** All user-configurable settings (like LLM model name) should reside in `config.py`.
6.  **Dependencies:** New Python package dependencies must be added to `requirements.txt`.
7.  **Error Handling:** Implement robust error handling and provide informative messages to the user via `cli_ui.py` error/warning functions.
8.  **Testing (Conceptual):** While no formal test suite is described, ensure that changes are manually tested for common use cases and edge cases.
9.  **Safety and Security:** For file operations, prioritize safety. Avoid destructive actions without confirmation. Use path validation where necessary.
10. **Referring to Context:** You can ask for clarification on specific files or functions if this document is insufficient. My responses will be based on this context.
11. **LLM Interaction:**
    *   Prompts for the Ollama LLM are constructed within `ollama_connector.py` or passed to it.
    *   Be mindful of prompt engineering principles if suggesting changes to LLM interactions.
12. **Data Files:**
    *   `session_context.json` stores runtime user session.
    *   `activity_log.jsonl` stores command history.
    *   Understand their structure if making changes related to session or logging.

By following these guidelines, you can provide accurate, relevant, and high-quality assistance for the "SAM-Open (Sistem Asisten Mandiri) File Assistant" project.

--- END OF FILE forai.md ---