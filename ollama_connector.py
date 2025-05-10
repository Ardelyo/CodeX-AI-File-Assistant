import os
import requests
import json
from config import OLLAMA_API_BASE_URL, OLLAMA_MODEL

class OllamaConnector:
    def __init__(self, base_url=OLLAMA_API_BASE_URL, model=OLLAMA_MODEL):
        self.base_url = base_url
        self.model = model
        self.api_generate_url = f"{self.base_url}/api/generate"

    def check_connection_and_model(self):
        try:
            response = requests.get(self.base_url, timeout=5)
            response.raise_for_status()
            models_response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            models_response.raise_for_status()
            available_models = models_response.json().get("models", [])
            model_found = any(m.get("name") == self.model or m.get("name").startswith(self.model + ":") for m in available_models)
            return True, model_found, available_models
        except requests.exceptions.RequestException: return False, False, []

    def _send_request_to_ollama(self, prompt_text: str, is_json_mode: bool = False) -> (dict | None):
        payload = {"model": self.model, "prompt": prompt_text, "stream": False}
        if is_json_mode: payload["format"] = "json"
        headers = {"Content-Type": "application/json"}
        try:
            # Increased timeout for potentially complex NLU or planning
            response = requests.post(self.api_generate_url, data=json.dumps(payload), headers=headers, timeout=300) 
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            print(f"[OLLAMA TIMEOUT] Prompt: {prompt_text[:100]}...")
            return None
        except requests.exceptions.HTTPError as e:
            # Attempt to get more info from response if available
            error_body = "N/A"
            if response is not None:
                try:
                    error_body = response.json() # Or response.text if not JSON
                except json.JSONDecodeError:
                    error_body = response.text[:200]
            print(f"[OLLAMA HTTP ERROR] {e} - Response: {error_body}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[OLLAMA REQUEST ERROR] {e}")
            return None

    def invoke_llm_for_content(self, main_instruction: str, context_text: str = "") -> str:
        full_prompt = f"{context_text}\n\n---\n\nUser Command: {main_instruction}" if context_text else main_instruction
        response_data = self._send_request_to_ollama(full_prompt)
        return response_data.get("response", "").strip() if response_data else "Error: LLM content generation failed."

    def get_intent_and_entities(self, user_prompt: str, session_context: dict = None) -> (dict | None):
        context_hint_str = ""
        if session_context:
            hints = []
            if session_context.get("last_referenced_file_path"): 
                hints.append(f"last file: '{os.path.basename(session_context['last_referenced_file_path'])}'")
            if session_context.get("last_folder_listed_path"): 
                hints.append(f"last folder: '{os.path.basename(session_context['last_folder_listed_path'])}'")
            if session_context.get("last_search_results"): 
                hints.append(f"last search found {len(session_context['last_search_results'])} items")
            if session_context.get("command_history") and session_context["command_history"]:
                last_cmd_info = session_context["command_history"][-1]
                hints.append(f"last command was '{last_cmd_info.get('action', 'unknown')}' with params '{str(last_cmd_info.get('parameters', {}))[:50]}...'")
            if hints: 
                context_hint_str = f"Recent context: {'; '.join(hints)}."
        
        meta_prompt = f"""
You are an expert AI assistant for file management, information retrieval, and task planning.
Your primary goal is to identify a SINGLE main action the user wants to perform and extract its necessary parameters.

Available actions and their EXCLUSIVE parameters:
- "summarize_file": User wants a summary of a specific file.
    Params: "file_path" (string; path to the file, or "__FROM_CONTEXT__" if implied, or "__MISSING__" if not specified).
- "ask_question_about_file": User is asking a question about a specific file or folder.
    Params: "file_path" (string; path to file/folder, or "__FROM_CONTEXT__", or "__MISSING__"), "question_text" (string; the user's question).
- "list_folder_contents": User wants to see the contents of a folder.
    Params: "folder_path" (string; path to the folder, or "__FROM_CONTEXT__", or "__MISSING__").
- "move_item": User wants to move a file or folder.
    Params: "source_path" (string; current path of item, or "__MISSING__"), "destination_path" (string; new path/folder for item, or "__MISSING__").
- "search_files": User wants to find files/folders based on criteria.
    Params: "search_criteria" (string; e.g., "images", "PDFs about finance", "text files containing 'secret'"), "search_path" (string, optional; directory to search in, e.g., ".", "C:/Users/Downloads", or "__MISSING__" to prompt or use context).
- "propose_and_execute_organization": User wants to organize files/folders.
  Params: "target_path_or_context" (string; MUST be "__FROM_CONTEXT__" if referring to current/recent items like "these files", "this folder", or if no path is given after a list/search operation. Otherwise, specify the path like "my downloads folder"), "organization_goal" (string, optional, e.g., "by type", "by project", "general cleanup").
- "show_activity_log": User wants to see recent activity.
    Params: "count" (integer, optional, defaults to a small number like 5-10).
- "redo_activity": User wants to re-run a previous action.
    Params: "activity_identifier" (string; "last", an index number from log, or part of a timestamp).
- "general_chat": For general conversation, greetings, or requests not matching other actions.
    Params: "original_request" (string; the full user prompt).
- "unknown": Request is unclear or unsupported.
    Params: "original_request" (string), "error" (string, optional reason for unknown).

IMPORTANT PARAMETER RULES:
1.  Each user request should map to a SINGLE primary action.
2.  The "summarize_file" action ONLY accepts a "file_path" parameter. It should NEVER have "search_criteria" or "search_path" in its parameters. If a user asks to search for a file and then summarize it, "search_files" is the primary action for this step. Summarizing a specific search result would be a follow-up command.
3.  The "ask_question_about_file" action ONLY accepts "file_path" and "question_text". It should NEVER have "search_criteria" or "search_path" in its parameters.
4.  The "search_files" action requires "search_criteria" and optionally "search_path". It does NOT take "file_path" as a parameter to define the search scope itself.
5.  For "propose_and_execute_organization":
    - Set "target_path_or_context" to "__FROM_CONTEXT__" if the user says "organize these files", "organize this folder", "clean up here", or makes a general organization request immediately after a 'list' or 'search' operation that populated the context.
    - If an explicit path is given (e.g., "organize my Downloads folder"), use that path for "target_path_or_context".
    - If "organization_goal" is not specified, use a generic goal like "general organization based on item names and types".

{context_hint_str}
User Request: "{user_prompt}"

Respond ONLY with a valid JSON object. Do not add any commentary before or after the JSON.

Example for "summarize C:/reports/annual.docx":
{{
  "action": "summarize_file",
  "parameters": {{ "file_path": "C:/reports/annual.docx" }}
}}

Example for "search for pdfs in my documents folder containing 'budget 2024'":
{{
  "action": "search_files",
  "parameters": {{
    "search_criteria": "pdfs containing 'budget 2024'",
    "search_path": "my documents folder"
  }}
}}

Example for "organize these items by date" (after a 'list' or 'search' command):
{{
  "action": "propose_and_execute_organization",
  "parameters": {{
    "target_path_or_context": "__FROM_CONTEXT__",
    "organization_goal": "by date"
  }}
}}

Your JSON response:
"""
        response_data = self._send_request_to_ollama(meta_prompt, is_json_mode=True)
        if response_data:
            json_string = response_data.get("response", "{}").strip()
            try:
                if json_string.startswith("```json"): json_string = json_string.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                elif json_string.startswith("```"): json_string = json_string.strip("` \n")
                json_string = "\n".join(line for line in json_string.splitlines() if not line.strip().startswith("//"))
                
                parsed_json = json.loads(json_string)
                
                # Programmatic validation to catch LLM confusion between summarize/ask and search
                action = parsed_json.get("action")
                params = parsed_json.get("parameters", {})

                if action in ["summarize_file", "ask_question_about_file"]:
                    if "search_criteria" in params:
                        # LLM is confused. It's likely a search request.
                        new_search_params = {"search_criteria": params["search_criteria"]}
                        if "search_path" in params:
                            new_search_params["search_path"] = params["search_path"]
                        else:
                            # Try to infer search_path from file_path if action was ask_question_about_file and file_path was a dir
                            if action == "ask_question_about_file" and params.get("file_path") and params["file_path"] not in ["__MISSING__", "__FROM_CONTEXT__"]:
                                # This is a heuristic; actual path checking would be better but complex here
                                new_search_params["search_path"] = params["file_path"] 
                            else:
                                new_search_params["search_path"] = "__MISSING__"
                        
                        correction_note = (f"LLM initially chose '{action}' but included 'search_criteria'. "
                                           f"Re-interpreting as 'search_files'. Original LLM params: {params}. "
                                           f"User prompt: {user_prompt[:100]}...")
                        
                        # Return the corrected action and parameters
                        # Print to server console for debugging this NLU correction
                        print(f"\n[NLU CORRECTION]\n{correction_note}\n") 
                        return {
                            "action": "search_files",
                            "parameters": new_search_params,
                            "nlu_correction_note": correction_note 
                        }
                return parsed_json
            except json.JSONDecodeError:
                return {"action": "unknown", "parameters": {"original_request": user_prompt, "error": f"LLM NLU JSON error. Raw: {json_string[:100]}"}}
        return {"action": "unknown", "parameters": {"original_request": user_prompt, "error": "No LLM NLU response."}}

    def check_content_match(self, file_content: str, criteria_description: str) -> bool:
        if not file_content: return False
        MAX_CONTENT_FOR_CHECK = 3500 
        prompt = f"""
        File content (potentially truncated):
        --- FILE CONTENT START ---
        {file_content[:MAX_CONTENT_FOR_CHECK]} 
        --- FILE CONTENT END ---
        Does this content match: "{criteria_description}"? Respond ONLY with YES or NO.
        """
        response_data = self._send_request_to_ollama(prompt)
        if response_data: return "YES" in response_data.get("response", "").strip().upper()
        return False

    def generate_organization_plan_llm(self, items_list_str: str, user_goal_str: str, base_path_for_plan: str) -> (list | None):
        planning_meta_prompt = f"""
You are an AI expert in file organization. Given a list of items in a base path, and a user's goal, 
generate a precise JSON list of actions to organize them. Paths in actions should be absolute.
The base path for all operations and context is: "{base_path_for_plan}"

Items to organize (relative to base path if not specified, but your output paths must be absolute):
{items_list_str}

User's organization goal: {user_goal_str}

Available actions for the plan (use absolute paths for all path parameters):
- "CREATE_FOLDER": Create a new folder. Requires "path" (string, absolute path of folder to create).
- "MOVE_ITEM": Move a file or folder. Requires "source" (string, absolute current path of item) and "destination" (string, absolute new path, can be into an existing or newly created folder).

Rules for the plan:
1. Output ONLY a valid JSON array of action objects. No other text.
2. All "path", "source", "destination" values MUST be absolute paths. Use the provided base path to construct them if items are listed relatively.
3. Create necessary folders before moving items into them.
4. If goal is "by type", create folders like "Images", "Documents" etc. (e.g. inside "{base_path_for_plan}/Organized_by_Type" or directly in base_path if appropriate).
5. Be conservative: if an item's organization is unclear or already seems fine, it's okay to not include an action for it.
6. Ensure source and destination for MOVE_ITEM are different.
7. If creating organizational subfolders, make their names descriptive of the organization goal (e.g., "ByType/Images", "Projects/AlphaProj").

Example output format (ensure paths are absolute):
[
  {{"action_type": "CREATE_FOLDER", "path": "{os.path.join(base_path_for_plan, "Images")}"}},
  {{"action_type": "MOVE_ITEM", "source": "{os.path.join(base_path_for_plan, "photo.jpg")}", "destination": "{os.path.join(base_path_for_plan, "Images", "photo.jpg")}"}}
]

Your JSON plan:
"""
        response_data = self._send_request_to_ollama(planning_meta_prompt, is_json_mode=True)
        if response_data:
            json_string = response_data.get("response", "[]").strip()
            try:
                if json_string.startswith("```json"): json_string = json_string.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                elif json_string.startswith("```"): json_string = json_string.strip("` \n")
                json_string = "\n".join(line for line in json_string.splitlines() if not line.strip().startswith("//"))
                parsed_plan = json.loads(json_string)
                if isinstance(parsed_plan, list):
                    return parsed_plan
                else: # LLM returned valid JSON but not a list
                    print(f"[OLLAMA WARNING] Plan generation returned non-list JSON: {json_string[:100]}")
                    return [] 
            except json.JSONDecodeError:
                print(f"[OLLAMA ERROR] Error decoding JSON plan from LLM. Raw: {json_string[:200]}")
                return None 
        return None