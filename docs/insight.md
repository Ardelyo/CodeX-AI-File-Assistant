# SAM-Open (Sistem Asisten Mandiri) File Assistant: Internal Design & Development Plan

## 1. Concept and Vision

**Core Idea:** To create a locally-run, AI-powered command-line assistant that deeply understands and interacts with a user's file system using natural language. The assistant should not just execute simple commands but also exhibit basic reasoning, planning (for organization), and contextual awareness.

**Key Principles:**
*   **Local First & Privacy:** All core processing (LLM, file access) happens locally.
*   **Natural Interaction:** Prioritize natural language over rigid command syntax.
*   **Agentic Behavior (Emerging):** Move towards an AI that can understand goals, propose plans, and execute them with confirmation.
*   **Extensibility:** Design with future enhancements in mind.
*   **User Safety:** For file modification operations, prioritize clarity, confirmation, and safeguards.

## 2. System Architecture & Structure

The system is composed of several Python modules:

*   **`main_cli.py` (Orchestrator & UI):**
    *   Handles the main application loop.
    *   Manages the Rich CLI (prompts, output formatting, spinners).
    *   Loads and saves session context.
    *   Receives user input and passes it to the NLU.
    *   Dispatches tasks to appropriate handler functions based on NLU output.
    *   Contains handler functions for each defined action (e.g., `handle_summarize_file`, `handle_propose_and_execute_organization`).
*   **`ollama_connector.py` (LLM Interaction & NLU):**
    *   Manages all communication with the local Ollama API.
    *   `get_intent_and_entities()`: Takes user input and session context, constructs a meta-prompt, and queries the LLM to parse the user's intent and extract relevant parameters/entities. Returns a structured JSON-like dictionary.
    *   `invoke_llm_for_content()`: Sends text (e.g., file content + instruction) to the LLM for tasks like summarization or answering questions.
    *   `check_content_match()`: Asks LLM if a file's content matches a textual criterion (for search).
    *   `generate_organization_plan_llm()`: Takes a list of items, a goal, and a base path, and prompts the LLM to generate a JSON list of file operations for organization.
*   **`file_utils.py` (File System Toolkit):**
    *   Contains functions for all direct file system interactions:
        *   Reading various file types (`.txt`, `.docx`; PDF is placeholder).
        *   Listing folder contents.
        *   Moving files/folders (`move_item`).
        *   Searching files recursively (`search_files_recursive`) with name, type, and basic content filtering.
    *   Designed to be OS-agnostic where possible (`os.path`).
*   **`activity_logger.py` (Logging):**
    *   Provides functions to log actions (`log_action`) to a `activity_log.jsonl` file.
    *   Retrieves recent activities (`get_recent_activities`, `get_activity_by_partial_id_or_index`).
*   **`config.py` (Configuration):**
    *   Stores settings like Ollama API URL and the target LLM model name.
*   **`session_context.json` (Data File):**
    *   Persists session state (last file/folder, search results, command history) across application runs.
*   **`activity_log.jsonl` (Data File):**
    *   Stores a history of actions performed by the assistant.

## 3. Detailed Workflow (Example: "Organize this folder by type")

1.  **Startup:**
    *   `main_cli.py` loads `session_context.json`.
    *   `ollama_connector` checks connection to Ollama and model availability.
2.  **User Input:** User types "organize this folder by type".
3.  **NLU Call 1 (Intent Parsing - `main_cli.py` -> `ollama_connector.get_intent_and_entities`):**
    *   `user_input` and current `session_context` (which might contain `last_folder_listed_path`) are sent to `get_intent_and_entities`.
    *   The LLM, guided by its meta-prompt, should return:
        ```json
        {
          "action": "propose_and_execute_organization",
          "parameters": {
            "target_path_or_context": "__FROM_CONTEXT__", // or the specific folder if mentioned
            "organization_goal": "by file type"
          }
        }
        ```
4.  **Action Dispatch & Context Resolution (`main_cli.py`):**
    *   `main()` identifies the action as `propose_and_execute_organization`.
    *   Calls `handle_propose_and_execute_organization(connector, parameters)`.
    *   The handler resolves `target_path_or_context == "__FROM_CONTEXT__"` to `session_context["last_folder_listed_path"]` (e.g., `C:/Users/User/DemoFolder`). This becomes `base_analysis_path`.
    *   It calls `file_utils.list_folder_contents(base_analysis_path, console)` to get `items_for_analysis`.
5.  **NLU Call 2 (Plan Generation - `handle_propose_and_execute_organization` -> `ollama_connector.generate_organization_plan_llm`):**
    *   A summary of `items_for_analysis` (names, types, relative to `base_analysis_path`), the `organization_goal` ("by file type"), and the `base_analysis_path` are formatted into a new, detailed prompt.
    *   `generate_organization_plan_llm` sends this to the LLM.
    *   The LLM is expected to return a JSON array of actions, e.g.:
        ```json
        [
          {"action_type": "CREATE_FOLDER", "path": "C:/Users/User/DemoFolder/Images"},
          {"action_type": "CREATE_FOLDER", "path": "C:/Users/User/DemoFolder/Documents"},
          {"action_type": "MOVE_ITEM", "source": "C:/Users/User/DemoFolder/photo1.jpg", "destination": "C:/Users/User/DemoFolder/Images/photo1.jpg"},
          {"action_type": "MOVE_ITEM", "source": "C:/Users/User/DemoFolder/report.docx", "destination": "C:/Users/User/DemoFolder/Documents/report.docx"}
        ]
        ```
6.  **Plan Validation & Presentation (`main_cli.py`):**
    *   The handler parses the returned JSON.
    *   It validates each action (e.g., paths are absolute, within `base_analysis_path` scope).
    *   Presents the valid actions to the user in a `rich.Table`.
    *   Logs the proposed plan.
7.  **User Confirmation (`main_cli.py`):**
    *   Prompts "Execute these N valid actions? (yes/no)".
8.  **Plan Execution (`main_cli.py` - if "yes"):**
    *   Iterates through `valid_plan_actions`.
    *   Uses `os.makedirs(..., exist_ok=True)` for `CREATE_FOLDER`.
    *   Uses `file_utils.move_item(..., console)` for `MOVE_ITEM`.
    *   Displays progress using `rich.Progress`.
    *   Logs each individual step's success/failure.
9.  **Feedback & Logging (`main_cli.py`):**
    *   Reports overall success/failure counts.
    *   Logs the completion of the `execute_organization_plan` action.
10. **Session Save (`main_cli.py` - on exit):**
    *   `save_session_context()` writes the updated `session_context` to JSON.

## 4. Programming Plans (High-Level & Future)

*   **Phase 1 (Current):** Basic NLU, file operations (list, read, search, move), session context, activity logging, experimental LLM-based organization plan proposal & execution.
*   **Phase 2 (Near-Term Enhancements):**
    *   **Robust NLU for Context:** Improve meta-prompts for better handling of pronouns ("it", "these") and implicit references to `last_search_results` or `last_folder_listed_path` across all actions.
    *   **Advanced Search:**
        *   Full PDF text extraction and search.
        *   OCR for image text search.
        *   Date-based search (file modification/creation dates).
    *   **More File Operations:** Copy, Delete (with trash/undo confirmation), Rename, Create Folder/File.
    *   **Plan Modification:** Allow users to review and selectively disable/modify steps in a proposed organization plan before execution.
    *   **Improved "Dry Run":** Make dry run more explicit and detailed for organization plans.
*   **Phase 3 (Mid-Term Enhancements):**
    *   **Semantic Search with Embeddings:** Integrate vector embeddings for searching "about <topic>" with higher accuracy.
    *   **Content Modification (Careful):** Allow LLM-assisted textual changes within files, with strict diffing and user review.
    *   **Plugin Architecture:** Design a way to add new "tools" or capabilities more modularly.
    *   **Configuration for Safety:** Allow users to define "sandboxed" directories where write operations are permitted.
*   **Phase 4 (Long-Term Vision):**
    *   **GUI:** Develop a graphical user interface.
    *   **Cloud Integration:** Connect to Google Drive, Dropbox, etc.
    *   **Multi-turn Planning:** For very complex goals, the AI might need to break it into sub-goals, perform information gathering, and then plan (e.g., ReAct-style agent loop).
    *   **User Preference Learning:** AI adapts to common organizational patterns or preferred actions of the user.

## 5. Identified Problems & Challenges

1.  **LLM Reliability (Core Challenge):**
    *   **NLU Accuracy:** `gemma3:1b` (or similar small models) can struggle with complex sentence structures, ambiguity, typos, and precise parameter extraction. This leads to misinterpretations or the AI asking for clarification too often.
    *   **JSON Output Consistency:** Forcing the LLM to output perfectly valid JSON for action plans or NLU results is difficult. It might add extra text, miss quotes, or generate malformed structures. Robust parsing and error handling are needed.
    *   **Hallucination of Parameters:** The LLM might invent parameters (like the incorrect "by date" goal) if not strongly guided.
    *   **Planning Capability:** Generating logical, safe, and efficient multi-step file operation plans is a high-level reasoning task that stretches small LLMs. Plans might be suboptimal or contain errors.
2.  **Context Management:**
    *   While basic session context exists, understanding *deep* multi-turn conversational context and resolving complex anaphora ("that file I mentioned three commands ago") is hard.
    *   Determining the *relevance* of past context to the current command.
3.  **File System Safety:**
    *   Preventing accidental data loss due to incorrect moves, deletes (if implemented), or flawed organization plans is critical.
    *   Ensuring the AI doesn't operate outside intended directories.
    *   Implementing a true "undo" or "rollback" for file operations is non-trivial.
4.  **Path Resolution & Ambiguity:**
    *   Users might provide relative paths, vague paths ("my documents"), or paths with typos. Robustly resolving these to absolute, correct paths is challenging.
    *   Cross-platform path differences (Windows vs. Linux/macOS). `os.path` helps but care is needed.
5.  **Performance:**
    *   Multiple LLM calls (NLU, then planning, then content analysis for search) add latency.
    *   Recursive file searches or processing large numbers of files can be slow. `get_file_content_for_search` limits read size, but scanning many files is still intensive.
    *   LLM-based content checking for search (`check_content_match`) is inherently slow per file.
6.  **Unsupported File Types:**
    *   Currently, deep content interaction is limited (text, docx). Full PDF, image (OCR), spreadsheet, and other binary formats require dedicated libraries and more complex parsing logic.
7.  **User Experience for Complex Operations:**
    *   Presenting a complex organization plan clearly and getting intuitive confirmation is vital.
    *   Handling errors during plan execution and communicating them effectively.
8.  **Scalability:**
    *   The current approach of listing all items for an organization plan might not scale to folders with tens of thousands of files due to prompt length limits for the LLM.
    *   Activity log file could grow very large; current rotation is basic.

## 6. Future Development Strategy

*   **Iterative Improvement:** Focus on improving one component or feature at a time.
*   **Prioritize NLU Robustness:** Continuously refine meta-prompts for the LLM based on observed failures and user feedback. Experiment with different prompting techniques.
*   **Safety First:** For any new file modification feature, implement clear confirmations, consider "dry run" modes, and add validation steps.
*   **Modular Design:** Keep components like NLU, file utils, and action handlers as separate as possible to facilitate easier updates and testing.
*   **User Feedback:** (If deployed) Collect feedback on where the AI misunderstands or fails, to guide NLU tuning and feature development.
*   **Consider Hybrid Approaches:** For some tasks (e.g., simple path extraction, keyword search), traditional rule-based logic might be more reliable or efficient than relying solely on a small LLM, which can then be reserved for more complex understanding tasks.