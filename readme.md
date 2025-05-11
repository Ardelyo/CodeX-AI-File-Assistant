<!--
██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
-->

<div align="center">
  <pre>
  ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝
 ██║     ██║   ██║██║  ██║█████╗   ╚███╔╝ 
 ██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗ 
 ╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗
  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
  </pre>
</div>

<h1 align="center">CodeX AI File Assistant</h1>

<p align="center">
  <em>Transforming File Management with Local AI Intelligence</em>
</p>

<p align="center">
  <a href="#-overview">Overview</a> •
  <a href="#-features">Features</a> •
  <a href="#-concept--workflow">Workflow</a> •
  <a href="#-technology-stack">Tech Stack</a> •
  <a href="#-prerequisites">Prerequisites</a> •
  <a href="#-installation--setup">Installation</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-roadmap">Roadmap</a> •
  <a href="#-contributing">Contributing</a> •
  <a href="#-creator">Creator</a>
</p>

<p align="center">
  <img alt="Python Version" src="https://img.shields.io/badge/python-3.9+-4B8BBE.svg?style=for-the-badge&logo=python&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-22c55e.svg?style=for-the-badge&logo=opensourceinitiative&logoColor=white"> 
  <img alt="Status" src="https://img.shields.io/badge/status-beta%20(v1.8.0)-ff9800.svg?style=for-the-badge&logo=statuspage&logoColor=white">
  <img alt="Built with AI" src="https://img.shields.io/badge/Built%20with-AI-8A2BE2.svg?style=for-the-badge&logo=openai&logoColor=white">
</p>

<div align="center">
  <img src="https://img.shields.io/badge/Ollama-8e44ad?style=flat-square&logo=llama&logoColor=white" alt="Ollama">
  <img src="https://img.shields.io/badge/Local%20AI-00c853?style=flat-square&logo=chip&logoColor=white" alt="LocalAI">
  <img src="https://img.shields.io/badge/Terminal%20UI-2d3748?style=flat-square&logo=windowsterminal&logoColor=white" alt="TerminalUI">
</div>

<div align="center">
  <br/>
  <img src="https://img.shields.io/badge/%F0%9F%94%92%20Privacy%20First-No%20Cloud%20Required-00b0ff" alt="Privacy First">
  <br/><br/>
</div>

<div align="center">
  <pre>╔════════════════════════════ ⊹ ════════════════════════════╗</pre>
</div>

## 🌟 Overview

**CodeX AI File Assistant** is a sophisticated command-line utility engineered to revolutionize your interaction with the local file system. By harnessing the power of locally-run Large Language Models (LLMs) via Ollama, CodeX offers an intuitive, natural language interface for managing, understanding, and organizing your digital assets with unprecedented ease and privacy.

This project represents a dedicated exploration into applied artificial intelligence and system utilities, developed with passion and perseverance by **Ardelyo Satria Anindito** during the 9th grade (2023-2025).

<div align="center">
  <pre>╚════════════════════════════ ⊹ ════════════════════════════╝</pre>
</div>

## ✨ Features

CodeX empowers users with a suite of intelligent capabilities:

*   🗣️ **Natural Language Understanding:** Communicate complex file operations using conversational English.
*   🧠 **Local LLM Intelligence:** Leverages models like `gemma:2b`, `mistral`, etc., for robust understanding, summarization, Q&A, and strategic planning—all processed locally.
*   📄 **Deep File Content Interaction:**
    *   Generate concise summaries for text-rich files (`.txt`, `.py`, `.md`, `.docx`, and more).
    *   Pose questions directly about file contents and receive insightful answers.
*   🗂️ **Advanced File System Operations:**
    *   Effortlessly list directory contents with clear, indexed views.
    *   Perform recursive searches based on name, type, and content criteria (including LLM-assisted content matching).
    *   Securely move files and folders with explicit user confirmation.
*   🪄 **Agentic Organization (Experimental):**
    *   Receive AI-generated organization plans for specified folders based on user-defined goals (e.g., "organize by type," "sort by project name").
    *   Utilizes a Python-based heuristic fallback for common name-based organization if the LLM cannot devise a plan.
    *   Review and execute these plans step-by-step, maintaining full control.
*   💾 **Session Context & Persistence:** CodeX remembers recent interactions (last file/folder, search results) for seamless, contextual follow-up commands, even across application restarts.
*   📜 **Comprehensive Activity Logging:** Maintains a detailed log of all actions for review, auditing, and a "redo" functionality for previous operations.
*   🎨 **Rich Terminal User Interface:** Employs the `rich` library to deliver an enhanced CLI experience with styled text, tables, progress bars, and dynamic spinners.
*   🔒 **Privacy First:** All file processing and AI computations occur entirely on your local machine, ensuring your data remains confidential.

<div align="center">
  <pre>╔════════════════════════════ ⊹ ════════════════════════════╗</pre>
</div>

## 💡 Concept & Workflow

CodeX operates through a streamlined, intelligent workflow visually represented below:

<div align="center">
<pre>
                 ╭──────────────────────────╮
                 │      User Typed Input     │
                 │ (e.g., "summarize doc.txt")│
                 ╰────────────┬─────────────╯
                              ↓
                 ╭──────────────────────────╮
                 │   Direct Parser Attempt   │
                 │ (Regex for common commands)│
                 ╰────────────┬─────────────╯
                              │
                No Match /    │ Matched
                Complex Query │
                              ↓
     ╭──────────────────────────╮     ╭────────────────────╮
     │    LLM NLU & Intent       │ ──→ │   Session Context   │
     │ (Ollama: gemma3:1b etc.)  │ ←── │ (Last file, folder) │
     ╰────────────┬─────────────╯     ╰────────────────────╯
                  │
                  ↓
     ╭──────────────────────────╮
     │   Action Dispatcher       │
     │ (Identified Action & Params)│
     ╰────────────┬─────────────╯
                  │
     ┌────────────┼────────────┐
     │            │            │
     ↓            ↓            ↓
╭─────────────╮ ╭─────────────╮ ╭───────────────────╮
│File System  │ │ LLM Content │ │LLM Org. Plan Gen. │
│(Read, List) │ │(Summarize)  │ │(Python Heuristic) │
╰──────┬──────╯ ╰──────┬──────╯ ╰─────────┬─────────╯
       │               │                  │
     ┌─┴───────────────┴──────────────────┘
     │
     ↓
╭─────────────────────────╮
│   Execute & Display     │
│ (Rich CLI Output)       │
╰────────────┬────────────╯
             │
             ↓
╭─────────────────────────╮     ╭────────────────────╮
│      Activity Logger     │ ──→ │ activity_log.jsonl │
╰─────────────────────────╯     ╰────────────────────╯
</pre>
</div>

1.  ⌨️ **User Input:** You articulate your file management needs in natural language.
2.  🤖 **NLU & Intent Parsing:** Input is first processed by direct regex-based parsers. If no match, it's dispatched to the local LLM to discern *intent* and extract *parameters*.
3.  🔗 **Contextual Awareness:** CodeX utilizes session history to resolve contextual references.
4.  ⚙️ **Action Dispatch & Tooling:** Based on the intent, appropriate tools are engaged (file system APIs, LLM for content processing or organization planning).
5.  🖥️ **Output & Logging:** Results are displayed; actions are logged, and session context is updated.

<div align="center">
  <pre>╚════════════════════════════ ⊹ ════════════════════════════╝</pre>
</div>

## 🛠️ Technology Stack

CodeX is built upon a foundation of modern and powerful technologies:

<div align="center">
  <table>
    <tr>
      <td align="center"><img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white"/></td>
      <td align="center"><img src="https://img.shields.io/badge/Ollama-Local%20LLMs-674EA7?style=for-the-badge&logo=llama&logoColor=white"/></td>
    </tr>
    <tr>
      <td align="center"><img src="https://img.shields.io/badge/Rich-CLI%20Enhancement-00875F?style=for-the-badge&logo=windowsterminal&logoColor=white"/></td>
      <td align="center"><img src="https://img.shields.io/badge/JSON-Data%20Storage-000000?style=for-the-badge&logo=json&logoColor=white"/></td>
    </tr>
  </table>
</div>

*   🐍 **Core Language:** Python (3.9+)
*   🧠 **AI Engine:** Local Large Language Models (LLMs)
*   🚀 **LLM Orchestration:** Ollama ([ollama.ai](https://ollama.ai/))
*   📊 **CLI Enhancement:** Rich library
*   📄 **Document Parsing:** `python-docx`
*   ⚙️ **Configuration:** Simple `.py` based configuration (`config.py`).
*   💾 **Data Persistence:** JSON for session context (`session_context.json`) and activity logs (`activity_log.jsonl`).

<div align="center">
  <pre>╔════════════════════════════ ⊹ ════════════════════════════╗</pre>
</div>

## 📋 Prerequisites

Before you begin, ensure your system meets the following requirements:

*   **Python:** Version 3.9 or higher.
*   **Ollama:** Installed and actively running. Download from [ollama.ai](https://ollama.ai/).
*   **LLM Model:** At least one Ollama-compatible model pulled locally.
    *   Examples: `gemma:2b`, `mistral:latest`, `llama3:8b`.
    *   The default configured model is `gemma3:1b` (or as specified in `config.py`). Ensure this model (or your chosen alternative) is available.
    *   Pull a model using: `ollama pull gemma:2b` (replace with your preferred model).

<div align="center">
  <pre>╚════════════════════════════ ⊹ ════════════════════════════╝</pre>
</div>

## 🚀 Installation & Setup

<div align="center">
  <img src="https://img.shields.io/badge/Setup%20Instructions-2d3748?style=flat-square&logo=readthedocs&logoColor=white" alt="Setup">
</div>

Follow these steps to get CodeX up and running:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Ardelyo/CodeX-AI-File-Assistant.git
    cd CodeX-AI-File-Assistant
    ```

2.  **Create a Python Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    ```
    *   Activate on Linux/macOS: `source venv/bin/activate`
    *   Activate on Windows: `venv\Scripts\activate`

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure CodeX:**
    *   Open `config.py`.
    *   Verify `OLLAMA_API_BASE_URL` (default `http://localhost:11434` is typically correct).
    *   **Crucial:** Set `OLLAMA_MODEL` to the exact name of the LLM model you have pulled via Ollama (e.g., `gemma:2b`, `llama3:8b`).

<div align="center">
  <pre>╔════════════════════════════ ⊹ ════════════════════════════╗</pre>
</div>

## 💻 Usage

<div align="center">
  <img src="https://img.shields.io/badge/%F0%9F%96%A5%EF%B8%8F%20Terminal%20Commands-2d3748?style=flat-square&logo=powershell&logoColor=white" alt="Terminal Commands">
</div>

1.  **Ensure Ollama is Running:** Start the Ollama service if it's not already active.
2.  **Launch CodeX AI File Assistant:**
    ```bash
    python main_cli.py
    ```
3.  Upon successful initialization, you will be greeted by the CodeX interface (featuring the CODEX ASCII logo!).
4.  Type `help` to view a list of example commands and interaction patterns.
5.  To exit, type `quit` or `exit`.

<div align="center">
  <table>
    <tr>
      <th>Example Commands</th>
    </tr>
    <tr>
      <td><code>summarize "reports/Q4_FinancialAnalysis.docx"</code></td>
    </tr>
    <tr>
      <td><code>what does "main_cli.py" say about session context?</code></td>
    </tr>
    <tr>
      <td><code>list contents of "/usr/local/bin"</code></td>
    </tr>
    <tr>
      <td><code>search for markdown files containing 'ollama setup'</code></td>
    </tr>
    <tr>
      <td><code>organize "Downloads" by file extension</code></td>
    </tr>
    <tr>
      <td><code>move item 3 to "../archive"</code> (after a list or search)</td>
    </tr>
    <tr>
      <td><code>show my last 10 activities</code></td>
    </tr>
    <tr>
      <td><code>redo last organization task</code></td>
    </tr>
  </table>
</div>

<div align="center">
  <pre>╚════════════════════════════ ⊹ ════════════════════════════╝</pre>
</div>

## 🗺️ Roadmap (Future Enhancements)

<div align="center">
  <img src="https://img.shields.io/badge/Future%20Enhancements-2962ff?style=flat-square&logo=trello&logoColor=white" alt="Future Enhancements">
</div>

CodeX is an evolving project with a vision for continued growth:

*   **Enhanced NLU Contextualization:** Deeper understanding of multi-turn conversations and complex anaphora.
*   **Advanced Search Capabilities:**
    *   Full PDF text extraction and semantic search.
    *   OCR for text search within images.
    *   Sophisticated date-based filtering (modification/creation dates).
*   **Expanded File Operations:** Implement `copy`, `delete` (with robust trash/undo mechanisms), `rename`, and `create new file/folder`.
*   **Interactive Plan Modification:** Allow users to review, modify, or selectively disable steps in AI-proposed organization plans.
*   **Semantic Search Integration:** Utilize vector embeddings for more nuanced topic-based searches.
*   **Plugin Architecture:** Design a modular system for adding new tools and capabilities.
*   **GUI Development:** Explore the creation of a graphical user interface for broader accessibility.

<div align="center">
  <pre>╔════════════════════════════ ⊹ ════════════════════════════╗</pre>
</div>

## 🤝 Contributing

<div align="center">
  <img src="https://img.shields.io/badge/Contributions%20Welcome-0a66c2?style=flat-square&logo=github&logoColor=white" alt="Contributions Welcome">
</div>

Contributions are highly valued and welcomed! If you are passionate about AI, file systems, or CLI tool development, consider contributing to CodeX. Areas for contribution include:

*   Improving NLU prompt engineering for diverse LLMs.
*   Expanding file type support (e.g., advanced PDF, spreadsheets, OCR).
*   Enhancing agentic planning and execution logic.
*   Strengthening error handling, safety protocols, and validation.
*   Bug fixes and performance optimizations.
*   Documentation improvements.

Please create an issue to discuss potential changes or features before submitting a pull request. Standard fork & pull request workflows are encouraged.

<div align="center">
  <pre>╚════════════════════════════ ⊹ ════════════════════════════╝</pre>
</div>

## 👤 Creator

This project, **CodeX AI File Assistant**, was conceived and developed by:

<div align="center">
<pre>
  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
  ┃                                              ┃
  ┃        █▀█ █▀█ █▀▄ █▀▀ █   █▄█ █▀█          ┃
  ┃        █▀█ █▀▄ █ █ █▀▀ █    █  █ █          ┃
  ┃        ▀ ▀ ▀ ▀ ▀▀  ▀▀▀ ▀▀▀  ▀  ▀▀▀          ┃
  ┃                                              ┃
  ┃         █▀ █▀█ ▀█▀ █▀█ █ █▀█                ┃
  ┃         ▄█ █▀█  █  █▀▄ █ █▀█                ┃
  ┃                                              ┃
  ┃       █▀█ █▄ █ █ █▄ █ █▀▄ █ ▀█▀ █▀█         ┃
  ┃       █▀█ █ ▀█ █ █ ▀█ █ █ █  █  █ █         ┃
  ┃                                              ┃
  ┃             (9th Grade Student)              ┃
  ┃               (2023 - 2025)                  ┃
  ┃                                              ┃
  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
</pre>
</div>

This endeavor was undertaken with dedication and a passion for exploring the intersection of artificial intelligence and practical software utilities.

<div align="center">
  <a href="https://github.com/Ardelyo">
    <img src="https://img.shields.io/badge/GitHub-@Ardelyo-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub">
  </a>
</div>

<div align="center">
  <pre>╔════════════════════════════ ⊹ ════════════════════════════╗</pre>
</div>

## 📜 License

<div align="center">
  <img src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square&logo=opensourceinitiative&logoColor=white" alt="License: MIT">
</div>

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

<div align="center">
  <pre>╚════════════════════════════ ⊹ ════════════════════════════╝</pre>
</div>

## 🙏 Acknowledgements

<div align="center">
  <table>
    <tr>
      <td align="center">
        <a href="https://ollama.ai">
          <img src="https://img.shields.io/badge/Ollama-Team-674EA7?style=flat-square&logo=llama&logoColor=white" alt="Ollama Team">
        </a>
      </td>
      <td align="center">
        <a href="https://github.com/Textualize/rich">
          <img src="https://img.shields.io/badge/Rich-Library-00875F?style=flat-square&logo=windowsterminal&logoColor=white" alt="Rich Library">
        </a>
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="https://github.com/open-source-community">
          <img src="https://img.shields.io/badge/Open%20Source-Community-ff9800?style=flat-square&logo=opensourceinitiative&logoColor=white" alt="Open Source Community">
        </a>
      </td>
      <td align="center">
        <a href="https://python.org">
          <img src="https://img.shields.io/badge/Python-Community-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python Community">
        </a>
      </td>
    </tr>
  </table>
</div>

*   The **Ollama** team for making local LLM execution accessible.
*   The developers of the **Rich** library for enabling beautiful terminal applications.
*   The broader open-source community for continuous inspiration and tools.

<div align="center">
  <pre>╔════════════════════════════ ⊹ ════════════════════════════╗</pre>
</div>

<div align="center">
  <img src="https://img.shields.io/badge/%F0%9F%92%BB%20Made%20With%20Passion%20%26%20AI-8A2BE2?style=for-the-badge" alt="Made With Passion & AI">
</div>

<p align="center">
  <b>Thank you for exploring CodeX AI File Assistant!</b><br>
  Your feedback and contributions are appreciated.
</p>

<div align="center">
  <pre>╚════════════════════════════ ⊹ ════════════════════════════╝</pre>
</div>
