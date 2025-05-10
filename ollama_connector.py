import os
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
            return {"error_type": "timeout", "message": f"Ollama request timed out. Prompt: {prompt_text[:100]}..."}
        except requests.exceptions.HTTPError as e:
            error_body = "N/A"
            if response is not None:
                try: error_body = response.json()
                except json.JSONDecodeError: error_body = response.text[:200]
            return {"error_type": "http_error", "message": f"Ollama HTTP Error: {e}. Response: {error_body}"}
        except requests.exceptions.RequestException as e:
            return {"error_type": "request_error", "message": f"Ollama Request Error: {e}."}

    def invoke_llm_for_content(self, main_instruction: str, context_text: str = "") -> str:
        full_prompt = f"{context_text}\n\n---\n\nUser Command: {main_instruction}" if context_text else main_instruction
        response_data = self._send_request_to_ollama(full_prompt)
        if response_data and "error_type" in response_data:
            return f"Error: LLM content generation failed. {response_data.get('message', 'Unknown Ollama error')}"
        return response_data.get("response", "").strip() if response_data else "Error: LLM content generation failed (no response)."

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
                context_hint_str = f"Contextual Information: {'; '.join(hints)}."
        
        meta_prompt = f"""
You are an expert AI assistant for file management, information retrieval, and task planning.
Your primary goal is to identify a SINGLE main action the user wants to perform and extract its necessary parameters.
Respond ONLY with a valid JSON object.

Available actions and their EXCLUSIVE parameters:
- "summarize_file": User wants a summary of a specific file.
  Parameters: "file_path" (string, path to the file).
- "ask_question_about_file": User is asking about a file or folder.
  Parameters: "file_path" (string, path to file/folder), "question_text" (string).
- "list_folder_contents": User wants to list folder contents.
  Parameters: "folder_path" (string, path to the folder).
- "move_item": User wants to move a file or folder.
  Parameters: "source_path" (string), "destination_path" (string).
- "search_files": User wants to find files/folders. This is the action if keywords like "search", "find", "look for" are prominent and a search subject (e.g., "images", "files containing 'budget'") is mentioned.
  Parameters: "search_criteria" (string, what to search for), "search_path" (string, where to search, optional).
- "propose_and_execute_organization": User wants to organize a folder.
  Parameters: "target_path_or_context" (string, the folder to organize), "organization_goal" (string, e.g., "by type", "by project", optional).
- "show_activity_log": User wants to see recent activity/log/history.
  Parameters: "count" (integer, optional, e.g., "last 5 activities").
- "redo_activity": User wants to redo a previously logged action.
  Parameters: "activity_identifier" (string, e.g., "last", index, or timestamp).
- "general_chat": For general conversation or requests not matching other actions.
  Parameters: "original_request" (string).
- "unknown": If the request is unclear or cannot be mapped to an action.
  Parameters: "original_request" (string), "error" (string, optional explanation).

Path Handling:
- Use "__FROM_CONTEXT__" if the path is implied (e.g., "this file", "it", "here") and should be resolved from session context.
- Use "__MISSING__" if a path is needed but not provided and not clearly contextual.

CRITICAL RULES:
1.  Strictly one primary action per request.
2.  "search_files" is for *finding* items. "search_criteria" is MANDATORY. Do NOT confuse with "summarize_file" or "ask_question_about_file" even if a path is mentioned alongside search terms. If user says "search for python files in /dev", action is "search_files", criteria is "python files", path is "/dev".
3.  "propose_and_execute_organization": "target_path_or_context" is *what* to organize (the folder). "organization_goal" is *how* (e.g., "by file type", "by date"). Do not mix these. Example: "organize C:/Downloads by type" -> target_path_or_context="C:/Downloads", organization_goal="by type". If goal is missing, it's general.

{context_hint_str}
User Request: "{user_prompt}"

Examples of correct JSON output:
- "summarize /tmp/report.txt": {{"action": "summarize_file", "parameters": {{"file_path": "/tmp/report.txt"}}}}
- "find images in my pictures folder": {{"action": "search_files", "parameters": {{"search_criteria": "images", "search_path": "__FROM_CONTEXT__"}}}}
- "organize ./downloads_folder by extension": {{"action": "propose_and_execute_organization", "parameters": {{"target_path_or_context": "./downloads_folder", "organization_goal": "by extension"}}}}
- "organize this folder": {{"action": "propose_and_execute_organization", "parameters": {{"target_path_or_context": "__FROM_CONTEXT__", "organization_goal": null}}}}
- "show my last 3 activities": {{"action": "show_activity_log", "parameters": {{"count": 3}}}}
- "move old.log to archive/": {{"action": "move_item", "parameters": {{"source_path": "old.log", "destination_path": "archive/"}}}}

Your JSON response:
"""
        response_data = self._send_request_to_ollama(meta_prompt, is_json_mode=True)

        if response_data and "error_type" in response_data: 
            return {"action": "unknown", "parameters": {"original_request": user_prompt, "error": response_data.get("message", "LLM NLU request failed")}, "nlu_method": "llm_request_error"}
        
        if response_data:
            json_string = response_data.get("response", "{}").strip()
            try:
                if json_string.startswith("```json"): json_string = json_string.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                elif json_string.startswith("```"): json_string = json_string.strip("` \n")
                json_string = "\n".join(line for line in json_string.splitlines() if not line.strip().startswith("//"))
                
                parsed_json = json.loads(json_string)
                parsed_json["nlu_method"] = "llm_parsed" # Add method note
                
                action = parsed_json.get("action")
                params = parsed_json.get("parameters", {})
                user_prompt_lower = user_prompt.lower()

                # L1 NLU Correction: Check for misattributed 'search_criteria' by LLM
                if action in ["summarize_file", "ask_question_about_file"] and "search_criteria" in params:
                    new_search_params = {"search_criteria": params["search_criteria"]}
                    if "search_path" in params: new_search_params["search_path"] = params["search_path"]
                    elif action == "ask_question_about_file" and params.get("file_path") and params["file_path"] not in ["__MISSING__", "__FROM_CONTEXT__"]:
                        new_search_params["search_path"] = params["file_path"]
                    else: new_search_params["search_path"] = "__MISSING__"
                    
                    correction_note = (f"NLU L1 Correction (Ollama): LLM chose '{action}' but included 'search_criteria'. "
                                       f"Re-interpreting as 'search_files'. Original LLM params: {params}. ")
                    return {"action": "search_files", "parameters": new_search_params, "nlu_correction_note": correction_note, "nlu_method": "llm_corrected_l1"}

                # L2 NLU Correction: If LLM chose summarize/ask, but user_prompt strongly implies search
                search_trigger_keywords = ["search for", "find files", "look for", "locate files", "search ", "find "]
                original_prompt_is_searchy = any(keyword in user_prompt_lower for keyword in search_trigger_keywords)
                if not original_prompt_is_searchy: # Check explicit start if not in general keywords
                    if user_prompt_lower.startswith("search ") or user_prompt_lower.startswith("find "):
                        original_prompt_is_searchy = True
                
                if action in ["summarize_file", "ask_question_about_file"] and original_prompt_is_searchy:
                    extracted_criteria = None; extracted_path = None
                    
                    match_in = re.search(r"^(?:search|find)\s+(?:for\s+)?(.+?)\s+in\s+(['\"]?)(.+?)\2?$", user_prompt, re.IGNORECASE)
                    if match_in:
                        extracted_criteria = match_in.group(1).strip().rstrip("'\" "); extracted_path = match_in.group(3).strip().rstrip("'\" ")
                    else:
                        path_pattern_for_no_in = r"""
                            (?P<path> 
                                (?:['"])(?P<quoted_path_content>.+?)(?:['"])| 
                                (?:[a-zA-Z]:\\(?:[^<>:"/\\|?*\s\x00-\x1f]+\\)*[^<>:"/\\|?*\s\x00-\x1f]*?)| 
                                (?:/(?:[^<>:"/\\|?*\s\x00-\x1f]+/)*[^<>:"/\\|?*\s\x00-\x1f]*?)| 
                                (?:(?:~|\.|[^<>:"/\\|?*\s\x00-\x1f./\\'"\s][^<>:"/\\|?*\s\x00-\x1f./\\']*)) 
                            )
                        """
                        match_no_in_str = r"^(?:search|find)\s+(?:for\s+)?(?P<criteria>.+?)\s+" + path_pattern_for_no_in.strip().replace("\n", "").replace(" ", "") + r"$"
                        match_no_in = re.search(match_no_in_str, user_prompt, re.IGNORECASE | re.VERBOSE)

                        if match_no_in:
                            extracted_criteria = match_no_in.group("criteria").strip().rstrip("'\" ")
                            if match_no_in.group("quoted_path_content"): extracted_path = match_no_in.group("quoted_path_content").strip()
                            else: extracted_path = match_no_in.group("path").strip().rstrip("'\" ")
                        else: 
                             match_simple = re.search(r"^(?:search|find)\s+(?:for\s+)?(.+)$", user_prompt, re.IGNORECASE)
                             if match_simple: extracted_criteria = match_simple.group(1).strip().rstrip("'\" ")

                    final_search_params = {}; correction_prefix = f"NLU L2 Correction (Ollama): LLM chose '{action}' but user prompt ('{user_prompt_lower[:30]}...') implies search."
                    if extracted_criteria:
                        final_search_params["search_criteria"] = extracted_criteria
                        if extracted_path: final_search_params["search_path"] = extracted_path
                        elif params.get("file_path") and params["file_path"] not in ["__MISSING__", "__FROM_CONTEXT__"]:
                            final_search_params["search_path"] = params["file_path"]
                            correction_prefix += f" Used LLM's file_path ('{params['file_path']}') as search_path."
                        else: final_search_params["search_path"] = "__MISSING__"
                        
                        correction_note = f"{correction_prefix} Overriding to 'search_files'. Original LLM params: {params}."
                        return {"action": "search_files", "parameters": final_search_params, "nlu_correction_note": correction_note, "nlu_method": "llm_corrected_l2_criteria"}
                    
                    fallback_search_path = params.get("file_path") if params.get("file_path") not in ["__MISSING__", "__FROM_CONTEXT__"] else "__MISSING__"
                    correction_note = (f"NLU L2 Fallback (Ollama): {correction_prefix} Regex extraction weak. "
                                       f"Forcing 'search_files', using LLM's file_path ('{fallback_search_path}') as search_path, and prompting for criteria. Original LLM params: {params}.")
                    return {
                        "action": "search_files",
                        "parameters": {"search_criteria": "__MISSING__", "search_path": fallback_search_path},
                        "nlu_correction_note": correction_note, "nlu_method": "llm_corrected_l2_fallback"
                    }
                return parsed_json
            except json.JSONDecodeError:
                return {"action": "unknown", "parameters": {"original_request": user_prompt, "error": f"LLM NLU JSON error. Raw: {json_string[:100]}"}, "nlu_method": "llm_json_decode_error"}
        return {"action": "unknown", "parameters": {"original_request": user_prompt, "error": "No LLM NLU response."}, "nlu_method": "llm_no_response"}

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
        if response_data and "error_type" in response_data:
            return False 
        if response_data: return "YES" in response_data.get("response", "").strip().upper()
        return False

    def generate_organization_plan_llm(self, items_list_str: str, user_goal_str: str, base_path_for_plan: str) -> (list | None):
        example_images_folder = os.path.join(base_path_for_plan, "Images_Organized")
        example_photo_source = os.path.join(base_path_for_plan, "holiday_photo.jpg")
        example_photo_dest = os.path.join(example_images_folder, "holiday_photo.jpg")
        
        example_alpha_folder_A_name = "A_files" 
        example_alpha_folder_A = os.path.join(base_path_for_plan, example_alpha_folder_A_name)
        example_alpha_source_apple = os.path.join(base_path_for_plan, "apple.txt")
        example_alpha_dest_apple = os.path.join(example_alpha_folder_A, "apple.txt")

        example_by_the_names_folder_R_name = "R_files" 
        example_by_the_names_folder_A_name = "A_files"
        example_by_the_names_folder_R = os.path.join(base_path_for_plan, example_by_the_names_folder_R_name)
        example_by_the_names_folder_A = os.path.join(base_path_for_plan, example_by_the_names_folder_A_name)
        example_by_the_names_source_report = os.path.join(base_path_for_plan, "report.docx") 
        example_by_the_names_dest_report = os.path.join(example_by_the_names_folder_R, "report.docx")
        example_by_the_names_source_alpha = os.path.join(base_path_for_plan, "alpha_notes.txt") 
        example_by_the_names_dest_alpha = os.path.join(example_by_the_names_folder_A, "alpha_notes.txt")

        planning_meta_prompt = f"""
You are an AI expert in file organization. Given a list of items in a base path, and a user's goal, 
generate a precise JSON list of actions to organize them.

CRITICAL: Your output MUST BE a valid JSON array. Each element of the array MUST be a JSON object representing a single action.
If no actions are needed or you cannot determine a valid plan, return an empty JSON array: [].

The base path for all operations and context is: "{base_path_for_plan}"
All "path", "source", and "destination" values in your JSON output MUST be ABSOLUTE paths.
All generated paths MUST be derived from or located within the `base_path_for_plan`. Do NOT generate paths outside this directory.

Items to organize (paths are relative to the base path if not already absolute):
{items_list_str}

User's organization goal: "{user_goal_str if user_goal_str else 'general organization'}"

Available actions for the plan (use absolute paths for all path parameters):
- {{"action_type": "CREATE_FOLDER", "path": "string (absolute path of folder to create)"}}
- {{"action_type": "MOVE_ITEM", "source": "string (absolute current path of item)", "destination": "string (absolute new path of item)"}}

Interpreting Common Goals:
- If goal is "by type" or "by file extension": Create subfolders like "{os.path.join(base_path_for_plan, "Documents")}", "{os.path.join(base_path_for_plan, "Images")}", etc., and move files accordingly.
- User Goal Mapping for Names: If the user's goal contains keywords like "name", "names", "first letter", or "alphabetical", you MUST apply the 'first_letter_folder_organization' strategy. This strategy involves:
    1. Identifying the first alphanumeric character of each item's filename (using the relative path name).
    2. Creating a destination subfolder based on this character (e.g., for 'apple.txt', the folder would be '{example_alpha_folder_A_name}'; for '123report.doc', '0-9_files'). Ensure folder names are simple, like "A_files", "B_files", "0-9_files", "Symbols_files".
    3. Moving the item into its corresponding first-letter subfolder. All paths MUST be absolute.
- If goal involves project names: Try to group items into project-specific subfolders like "{os.path.join(base_path_for_plan, "ProjectAlpha")}".

Rules for the plan:
1.  Convert all relative item paths from `items_list_str` to absolute paths using `base_path_for_plan` for the "source" in MOVE_ITEM actions.
2.  Create necessary folders (using CREATE_FOLDER) before moving items into them (using MOVE_ITEM).
3.  Ensure source and destination for MOVE_ITEM are different.
4.  Do not propose moving a folder into itself or one of its own subfolders.
5.  Be conservative: if an item's organization is unclear, or it already seems well-organized according to the goal, it's okay to not include an action for it.
6.  If the goal is unclear even after consulting 'User Goal Mapping for Names' for relevant name-based goals, or if applying the 'first_letter_folder_organization' strategy would be trivial (e.g., all items already start with 'S', or there are very few items like 1 or 2), return an empty JSON array: [].

Example for "by type" (organizing items into an "Images_Organized" subfolder):
[
  {{"action_type": "CREATE_FOLDER", "path": "{example_images_folder}"}},
  {{"action_type": "MOVE_ITEM", "source": "{example_photo_source}", "destination": "{example_photo_dest}"}}
]
Example for user_goal_str: "the names" (using 'first_letter_folder_organization' strategy for hypothetical items "report.docx", "alpha_notes.txt" in base path):
[
  {{"action_type": "CREATE_FOLDER", "path": "{example_by_the_names_folder_R}"}},
  {{"action_type": "CREATE_FOLDER", "path": "{example_by_the_names_folder_A}"}},
  {{"action_type": "MOVE_ITEM", "source": "{example_by_the_names_source_report}", "destination": "{example_by_the_names_dest_report}"}},
  {{"action_type": "MOVE_ITEM", "source": "{example_by_the_names_source_alpha}", "destination": "{example_by_the_names_dest_alpha}"}}
]

Your JSON plan (must be an array):
"""
        response_data = self._send_request_to_ollama(planning_meta_prompt, is_json_mode=True)
        
        if response_data and "error_type" in response_data:
            return None
        
        if response_data:
            json_string = response_data.get("response", "[]").strip()
            try:
                if json_string.startswith("```json"):
                    json_string = json_string.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                elif json_string.startswith("```"):
                    json_string = json_string.strip("` \n")
                json_string = "\n".join(line for line in json_string.splitlines() if not line.strip().startswith("//"))
                
                if not json_string.strip().startswith("[") or not json_string.strip().endswith("]"):
                    parsed_plan = []
                else:
                    parsed_plan = json.loads(json_string)

                if isinstance(parsed_plan, list):
                    return parsed_plan
                else:
                    return [] 
            except json.JSONDecodeError:
                return None 
        
        return None
