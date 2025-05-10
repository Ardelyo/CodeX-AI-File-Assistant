
import os # <--- THIS IS THE FIX
import re 
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
            response = requests.post(self.api_generate_url, data=json.dumps(payload), headers=headers, timeout=300) 
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            print(f"[OLLAMA TIMEOUT] Prompt: {prompt_text[:100]}...")
            return None
        except requests.exceptions.HTTPError as e:
            error_body = "N/A"
            if response is not None:
                try: error_body = response.json()
                except json.JSONDecodeError: error_body = response.text[:200]
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
                hints.append(f"last file: '{os.path.basename(session_context['last_referenced_file_path'])}'") # Uses os
            if session_context.get("last_folder_listed_path"): 
                hints.append(f"last folder: '{os.path.basename(session_context['last_folder_listed_path'])}'") # Uses os
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
- "summarize_file": User wants a summary of a specific file. Params: "file_path".
- "ask_question_about_file": User is asking about a file/folder. Params: "file_path", "question_text".
- "list_folder_contents": User wants to list folder contents. Params: "folder_path".
- "move_item": User wants to move an item. Params: "source_path", "destination_path".
- "search_files": User wants to find files/folders. Params: "search_criteria", "search_path" (optional).
- "propose_and_execute_organization": User wants to organize. Params: "target_path_or_context", "organization_goal" (optional).
- "show_activity_log": User wants to see activity. Params: "count" (optional).
- "redo_activity": User wants to redo. Params: "activity_identifier".
- "general_chat": General conversation. Params: "original_request".
- "unknown": Request unclear. Params: "original_request", "error" (optional).

Paths like "__FROM_CONTEXT__" or "__MISSING__" should be used if not explicitly stated or if implied by context.

SUPER IMPORTANT RULE:
If the user's request starts with "search" or "find" OR contains phrases like "search for", "find files", "look for files" AND specifies what to look for (e.g., "images", "text files", "documents containing 'report'"), the action MUST be "search_files".
The "search_criteria" parameter is KEY for "search_files".
Do NOT choose "summarize_file" or "ask_question_about_file" if the user clearly indicates a search action, even if a path is mentioned.

IMPORTANT PARAMETER RULES:
1.  Single primary action per request.
2.  "summarize_file" ONLY takes "file_path". NEVER "search_criteria" or "search_path".
3.  "ask_question_about_file" ONLY takes "file_path" and "question_text". NEVER "search_criteria" or "search_path".
4.  "search_files" requires "search_criteria" and optionally "search_path".

{context_hint_str}
User Request: "{user_prompt}"

Respond ONLY with a valid JSON object.

Example for "search images in C:/my_pictures":
{{
  "action": "search_files",
  "parameters": {{
    "search_criteria": "images",
    "search_path": "C:/my_pictures"
  }}
}}
Example for "search images C:/my_pictures":
{{
  "action": "search_files",
  "parameters": {{
    "search_criteria": "images",
    "search_path": "C:/my_pictures"
  }}
}}
Example for "find text files about 'budget'":
{{
  "action": "search_files",
  "parameters": {{
    "search_criteria": "text files about 'budget'",
    "search_path": "__MISSING__"
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
                
                action = parsed_json.get("action")
                params = parsed_json.get("parameters", {})
                user_prompt_lower = user_prompt.lower()

                # 1. Check for misattributed 'search_criteria' by LLM (original check)
                if action in ["summarize_file", "ask_question_about_file"] and "search_criteria" in params:
                    new_search_params = {"search_criteria": params["search_criteria"]}
                    if "search_path" in params: new_search_params["search_path"] = params["search_path"]
                    elif action == "ask_question_about_file" and params.get("file_path") and params["file_path"] not in ["__MISSING__", "__FROM_CONTEXT__"]:
                        new_search_params["search_path"] = params["file_path"] 
                    else: new_search_params["search_path"] = "__MISSING__"
                    
                    correction_note = (f"NLU L1 Correction: LLM chose '{action}' but included 'search_criteria'. "
                                       f"Re-interpreting as 'search_files'. Original LLM params: {params}. ")
                    print(f"\n[NLU CORRECTION (L1 - Param Misattribution)]\n{correction_note}\nInput: {user_prompt[:100]}...\n")
                    return {"action": "search_files", "parameters": new_search_params, "nlu_correction_note": correction_note}

                # 2. REVISED CHECK: If LLM chose summarize/ask, but user_prompt strongly implies search
                search_trigger_keywords = ["search for", "find files", "look for", "locate files", "search ", "find "]
                original_prompt_is_searchy = any(keyword in user_prompt_lower for keyword in search_trigger_keywords)
                
                if not original_prompt_is_searchy:
                    if user_prompt_lower.startswith("search ") or user_prompt_lower.startswith("find "):
                        original_prompt_is_searchy = True
                
                if action in ["summarize_file", "ask_question_about_file"] and original_prompt_is_searchy:
                    extracted_criteria = None
                    extracted_path = None
                    
                    match_in = re.search(r"^(?:search|find)\s+(?:for\s+)?(.+?)\s+in\s+(['\"]?)(.+?)\2?$", user_prompt, re.IGNORECASE)
                    if match_in:
                        extracted_criteria = match_in.group(1).strip().rstrip("'\" ")
                        extracted_path = match_in.group(3).strip().rstrip("'\" ")
                    else:
                        match_no_in = re.search(r"^(?:search|find)\s+(?:for\s+)?(.+?)\s+(['\"]?([A-Za-z]:\\(?:[^\"\\/:*?<>|]+\\)*[^\"\\/:*?<>|]*|/(?:[^/]+/)*[^/]*|~\S*|\.\S*)\2|(\S+))$", user_prompt, re.IGNORECASE)
                        if match_no_in:
                            extracted_criteria = match_no_in.group(1).strip().rstrip("'\" ")
                            extracted_path = match_no_in.group(3) if match_no_in.group(3) else match_no_in.group(4)
                            if extracted_path: extracted_path = extracted_path.strip().rstrip("'\" ")
                        else: 
                             match_simple = re.search(r"^(?:search|find)\s+(?:for\s+)?(.+)$", user_prompt, re.IGNORECASE)
                             if match_simple:
                                 extracted_criteria = match_simple.group(1).strip().rstrip("'\" ")

                    final_search_params = {}
                    correction_prefix = f"NLU L2 Correction: LLM chose '{action}' but user prompt ('{user_prompt_lower[:30]}...') implies search."

                    if extracted_criteria:
                        final_search_params["search_criteria"] = extracted_criteria
                        if extracted_path:
                            final_search_params["search_path"] = extracted_path
                        elif params.get("file_path") and params["file_path"] not in ["__MISSING__", "__FROM_CONTEXT__"]:
                            final_search_params["search_path"] = params["file_path"]
                            correction_prefix += f" Used LLM's file_path ('{params['file_path']}') as search_path."
                        else:
                            final_search_params["search_path"] = "__MISSING__"
                        
                        correction_note = f"{correction_prefix} Overriding to 'search_files'. Original LLM params: {params}."
                        print(f"\n[NLU CORRECTION (L2 - Prompt Override, Regex Extracted)]\n{correction_note}\nInput: {user_prompt[:100]}...\nNew Params: {final_search_params}\n")
                        return {"action": "search_files", "parameters": final_search_params, "nlu_correction_note": correction_note}
                    
                    fallback_search_path = params.get("file_path") if params.get("file_path") not in ["__MISSING__", "__FROM_CONTEXT__"] else "__MISSING__"
                    correction_note = (f"NLU L2 Fallback: {correction_prefix} Regex extraction weak. "
                                       f"Forcing 'search_files', using LLM's file_path ('{fallback_search_path}') as search_path, and prompting for criteria. Original LLM params: {params}.")
                    print(f"\n[NLU CORRECTION (L2 - Fallback)]\n{correction_note}\nInput: {user_prompt[:100]}...\n")
                    return {
                        "action": "search_files",
                        "parameters": {"search_criteria": "__MISSING__", "search_path": fallback_search_path},
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
        # The path construction for examples uses os.path.join
        example_images_folder = os.path.join(base_path_for_plan, "Images") # Uses os
        example_photo_source = os.path.join(base_path_for_plan, "photo.jpg") # Uses os
        example_photo_dest = os.path.join(example_images_folder, "photo.jpg") # Uses os

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
4. If goal is "by type", create folders like "Images", "Documents" etc. (e.g. inside "{os.path.join(base_path_for_plan, "Organized_by_Type")}" or directly in base_path if appropriate).
5. Be conservative: if an item's organization is unclear or already seems fine, it's okay to not include an action for it.
6. Ensure source and destination for MOVE_ITEM are different.
7. If creating organizational subfolders, make their names descriptive of the organization goal (e.g., "ByType/Images", "Projects/AlphaProj").

Example output format (ensure paths are absolute):
[
  {{"action_type": "CREATE_FOLDER", "path": "{example_images_folder}"}},
  {{"action_type": "MOVE_ITEM", "source": "{example_photo_source}", "destination": "{example_photo_dest}"}}
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
                else:
                    print(f"[OLLAMA WARNING] Plan generation returned non-list JSON: {json_string[:100]}")
                    return [] 
            except json.JSONDecodeError:
                print(f"[OLLAMA ERROR] Error decoding JSON plan from LLM. Raw: {json_string[:200]}")
                return None 
        return None