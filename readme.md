# CodeX AI File Assistant

**CodeX is an intelligent command-line file assistant powered by a local Large Language Model (LLM) via Ollama. It helps you manage, understand, and organize your files and folders through natural language interaction.**

CodeX aims to be your personal file system companion, capable of tasks ranging from summarizing documents and answering questions about their content to searching for specific files, listing folder contents, and even proposing and executing file organization plans.

## Features

*   **Natural Language Understanding:** Interact with your files using everyday language.
*   **LLM-Powered Intelligence:** Leverages a local LLM (e.g., `gemma3:1b` or other Ollama-compatible models) for understanding, summarization, Q&A, and planning.
*   **File Content Interaction:**
    *   Summarize text-based files (`.txt`, `.py`, `.js`, `.md`, `.docx`, etc.).
    *   Answer questions about the content of these files.
*   **File System Navigation & Operations:**
    *   List contents of folders.
    *   Search for files based on name, type, and (rudimentary) content criteria.
    *   Move files and folders (with user confirmation).
*   **Agentic Organization (Experimental):**
    *   Propose a file organization plan for a given folder or set of items based on user goals (e.g., "organize by type," "organize by project name").
    *   Execute the proposed plan after explicit user confirmation.
*   **Session Context:** Remembers the last interacted file/folder and search results for more natural follow-up commands.
*   **Activity Logging:** Keeps a log of actions performed for review and potential "redo" operations.
*   **Persistent Sessions:** Remembers context across application restarts.
*   **Rich Terminal UI:** Uses the `rich` library for an enhanced command-line experience with formatted text, tables, spinners, and progress bars.
*   **Local & Private:** Designed to run entirely locally, ensuring your file contents and interactions remain private.

## Concept & Workflow

1.  **User Input:** You type a command in natural language (e.g., "summarize my_report.docx", "search for images in ~/Downloads", "organize this folder by project").
2.  **NLU (Natural Language Understanding):** Your input is sent to the configured local LLM (via Ollama) to determine your *intent* (e.g., summarize, search, list) and extract relevant *parameters* (e.g., file path, search criteria, organization goal).
3.  **Session Context:** The AI considers previous interactions (last file, last folder, last search) to better understand contextual references like "it" or "these files."
4.  **Action Dispatch:** Based on the understood intent, CodeX calls the appropriate internal handler function.
5.  **Tool Usage / File System Interaction:**
    *   For summarization/Q&A, it reads file content and sends it to the LLM.
    *   For listing/searching/moving, it interacts with your file system.
    *   For organization, it first uses the LLM to generate a *plan* (a list of create/move operations), presents this plan for your approval, and then executes it.
6.  **Response & Logging:** The results are displayed in the terminal, and significant actions are logged. Session context is updated.

## Prerequisites

*   **Python:** Version 3.9 or higher.
*   **Ollama:** Installed and running. You can get it from [ollama.ai](https://ollama.ai/).
*   **LLM Model:** A model compatible with Ollama pulled locally (e.g., `gemma:2b`, `mistral`, `llama2`). The default in `config.py` is `gemma3:1b` (ensure you have a model with this exact name or update the config).
    ```bash
    ollama pull gemma:2b # Or your preferred model
    ```
    *(Note: `gemma3:1b` might be a placeholder name; use a valid model name you have pulled.)*

## Installation

1.  **Clone the repository (or download the files):**
    ```bash
    git clone <repository_url>
    cd codex-ai-file-assistant # Or your project directory name
    ```
2.  **Create a Python virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # venv\Scripts\activate    # On Windows
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure:**
    *   Open `config.py`.
    *   Verify `OLLAMA_API_BASE_URL` (default `http://localhost:11434` is usually correct).
    *   **Important:** Change `OLLAMA_MODEL` to the exact name of the model you have pulled in Ollama (e.g., `gemma:2b`).

## Usage

1.  **Ensure Ollama is running** in a separate terminal or as a background service.
2.  **Run the CodeX assistant:**
    ```bash
    python main_cli.py
    ```
3.  You'll see a welcome message. Type your commands at the `You ():` prompt.
4.  Type `help` for a list of example commands.
5.  Type `quit` or `exit` to close the assistant.

**Example Commands:**

*   `summarize "path/to/your/document.docx"`
*   `what is in "config.py" about the API key?`
*   `list contents of "C:/Users/YourName/Projects"` (Use quotes for paths with spaces)
*   `show me files in .` (Lists current directory)
*   `search for python scripts containing 'database_connection' in "~/dev/my_project"`
*   `search for images here`
*   `move "report_draft.txt" to "archive/reports/"`
*   `organize my downloads folder by file type` (Experimental: AI will propose a plan)
*   `organize these items` (After a list or search, refers to the results)
*   `show my last 5 activities`
*   `redo last search` (Attempts to re-execute the last logged search action)

## Troubleshooting

*   **`NameError` or `ImportError`:** Ensure all dependencies from `requirements.txt` are installed in your active virtual environment. Make sure all Python files (`main_cli.py`, `ollama_connector.py`, `file_utils.py`, `activity_logger.py`, `config.py`) are in the same directory.
*   **Connection to Ollama refused:** Make sure the Ollama service is running and accessible at the URL in `config.py`.
*   **Model not found:** Double-check the `OLLAMA_MODEL` name in `config.py` against the output of `ollama list` in your terminal.
*   **LLM NLU is poor / AI doesn't understand:**
    *   Smaller models like `gemma:2b` have limitations. Try to be more explicit in your commands.
    *   Experiment with different models in Ollama if available.
    *   The NLU prompts in `ollama_connector.py` can be tuned for better performance with specific models.
*   **Organization plans are strange or unsafe:** The LLM-generated organization plans are experimental. **Always review the proposed plan carefully before confirming execution.** The safety checks are basic.

## Contributing

Contributions are welcome! If you'd like to contribute, please consider:

*   Improving NLU prompt engineering for different models.
*   Adding support for more file types (e.g., full PDF parsing, OCR for images).
*   Enhancing the agentic planning and execution capabilities.
*   Adding more robust error handling and safety features.
*   Developing a GUI.

(Standard contribution guidelines like forking, branching, PRs would go here).

## License

(Specify your chosen license, e.g., MIT License, Apache 2.0)