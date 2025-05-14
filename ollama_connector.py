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
            response = requests.post(self.api_generate_url, data=json.dumps(payload), headers=headers, timeout=300)
            response.raise_for_status()
            # Ollama with format="json" returns the JSON directly in the 'response' field,
            # but the field itself is a string containing JSON.
            # The top-level response from requests.post().json() is the Ollama API response structure.
            ollama_api_response = response.json()
            if is_json_mode:
                if "response" in ollama_api_response:
                    try:
                        # The actual JSON content from the LLM is a string in ollama_api_response['response']
                        parsed_llm_json = json.loads(ollama_api_response['response'])
                        # We return the parsed JSON from the LLM, not the whole Ollama API response envelope
                        return parsed_llm_json
                    except json.JSONDecodeError as e:
                        return {"error_type": "json_decode_error_llm", "message": f"Ollama LLM returned invalid JSON string: {e}. Raw: {ollama_api_response['response'][:200]}"}
                else:
                    return {"error_type": "json_mode_no_response_field", "message": "Ollama in JSON mode but 'response' field missing."}
            return ollama_api_response # For non-JSON mode, return the whole API response
        except requests.exceptions.Timeout:
            return {"error_type": "timeout", "message": f"Ollama request timed out. Prompt: {prompt_text[:100]}..."}
        except requests.exceptions.HTTPError as e:
            error_body = "N/A"
            # response object might not be available if the error is severe (e.g., connection refused before request object is fully formed)
            if 'response' in locals() and response is not None:
                try: error_body = response.json()
                except json.JSONDecodeError: error_body = response.text[:200]
            return {"error_type": "http_error", "message": f"Ollama HTTP Error: {e}. Response: {error_body}"}
        except requests.exceptions.RequestException as e:
            return {"error_type": "request_error", "message": f"Ollama Request Error: {e}."}

    def invoke_llm_for_content(self, main_instruction: str, context_text: str = "") -> str:
        full_prompt = f"{context_text}\n\n---\n\nUser Command: {main_instruction}" if context_text else main_instruction
        response_data = self._send_request_to_ollama(full_prompt, is_json_mode=False) # Not JSON mode for general content
        if response_data and "error_type" in response_data:
            return f"Error: LLM content generation failed. {response_data.get('message', 'Unknown Ollama error')}"
        return response_data.get("response", "").strip() if response_data else "Error: LLM content generation failed (no response)."

    def get_intent_and_entities(self, user_input: str, session_context: dict) -> dict:
        context_summary_parts = []
        if session_context.get('current_directory'): # Added current_directory
            context_summary_parts.append(f"- Current working directory: {session_context['current_directory']}")
        if session_context.get('last_referenced_file_path'):
            context_summary_parts.append(f"- Last referenced file: {session_context['last_referenced_file_path']}")
        if session_context.get('last_folder_listed_path'):
            context_summary_parts.append(f"- Last listed folder: {session_context['last_folder_listed_path']}")
        if session_context.get('last_search_results'):
            context_summary_parts.append(f"- Last search produced {len(session_context['last_search_results'])} items.")
        
        context_summary = "No specific session context available."
        if context_summary_parts:
            context_summary = "Current session context:\n" + "\n".join(context_summary_parts)

        system_prompt = f"""
You are CodeX AI File Assistant, an expert in understanding user requests for file system operations.
Your task is to analyze the user's input, considering the provided session context, and provide a structured JSON output.

Always perform the following steps in your reasoning (which you will articulate in 'chain_of_thought'):
1.  **Rephrase User's Goal:** Briefly state what you believe the user is trying to achieve.
2.  **Identify Key Entities:** Extract potential file paths, folder paths, search terms, organizational goals, etc.
3.  **Contextual Resolution:** Explicitly state how you are using (or not using) the provided session context to resolve ambiguities or infer missing information. For example, if the user says "this file," check 'last_referenced_file_path' or 'current_directory'.
4.  **Path Inference/Assumption:** If a full path is not given, explain how you are deriving it (e.g., from current directory, context, or a common location like 'Downloads'). If a path is clearly relative (e.g. "./docs", "file.txt"), state that it should be resolved against the current working directory.
5.  **Action Determination:** Based on the above, determine the most appropriate single action from the list below.
6.  **Parameter Finalization:** List the parameters required for that action. Path parameters should be the string provided by the user if explicit, or a placeholder like "__FROM_CONTEXT__" or "__CURRENT_DIR__" if inferred.
7.  **Ambiguity Check:** If, after all reasoning, a critical piece of information (especially a path for an action like move or summarize) is still missing or highly ambiguous, set 'clarification_needed' to true and formulate a specific question. Do NOT guess if confidence is low on critical items.

Available actions and their parameters:
- "summarize_file": Parameters: "file_path" (string).
- "ask_question_about_file": Parameters: "file_path" (string), "question_text" (string).
- "list_folder_contents": Parameters: "folder_path" (string, can be "__CURRENT_DIR__" or "__FROM_CONTEXT__").
- "move_item": Parameters: "source_path" (string), "destination_path" (string).
- "search_files": Parameters: "search_criteria" (string), "search_path" (string, optional, can be "__CURRENT_DIR__" or "__FROM_CONTEXT__").
- "propose_and_execute_organization": Parameters: "target_path_or_context" (string), "organization_goal" (string, optional).
- "show_activity_log": Parameters: "count" (integer, optional).
- "redo_activity": Parameters: "activity_identifier" (string).
- "general_chat": Parameters: "original_request" (string).
- "unknown": Parameters: "original_request" (string), "error_reason" (string).

**OUTPUT FORMAT (Strict JSON):**
You MUST output a single JSON object with the following fields:
-   `chain_of_thought`: (string) Your detailed step-by-step reasoning process. Use newline characters (\\n) for readability if needed.
-   `action`: (string) The single, most appropriate action identified.
-   `parameters`: (object) A JSON object containing parameters for the identified 'action'.
-   `clarification_needed`: (boolean) true if critical information is missing or highly ambiguous, otherwise false.
-   `suggested_question`: (string) If 'clarification_needed' is true, provide a concise, targeted question. Otherwise, an empty string or null.
-   `nlu_method`: (string) Set this to "llm_direct_nlu".

**FEW-SHOT EXAMPLES:**
---
Example 1:
User Input: "summarize the report I just looked at"
Session Context:
- Current working directory: /user/projects
- Last referenced file: /user/docs/Q3_financial_report.docx

Assistant JSON Output:
```json
{{
  "chain_of_thought": "1. User's Goal: Summarize a recently accessed file implicitly referred to as 'the report I just looked at'.\\n2. Key Entities: 'report', 'summarize', implicit reference.\\n3. Contextual Resolution: User said 'just looked at', so I will use 'Last referenced file' from context: /user/docs/Q3_financial_report.docx.\\n4. Path Inference: The path is directly from context.\\n5. Action Determination: The action is 'summarize_file'.\\n6. Parameter Finalization: file_path is /user/docs/Q3_financial_report.docx.\\n7. Ambiguity Check: No major ambiguity, path seems clear from context.",
  "action": "summarize_file",
  "parameters": {{
    "file_path": "/user/docs/Q3_financial_report.docx"
  }},
  "clarification_needed": false,
  "suggested_question": "",
  "nlu_method": "llm_direct_nlu"
}}
```
---
Example 2:
User Input: "find text files about 'project alpha' in my main dev folder"
Session Context:
- Current working directory: /user/projects/project_beta

Assistant JSON Output:
```json

{{
  "chain_of_thought": "1. User's Goal: Search for text files containing 'project alpha' within a specific 'main dev folder'.\\n2. Key Entities: 'text files', 'project alpha', 'main dev folder'.\\n3. Contextual Resolution: 'main dev folder' is not explicitly in context. Current directory is '/user/projects/project_beta', which might not be the 'main dev folder'.\\n4. Path Inference: The path for 'main dev folder' is ambiguous. I cannot reliably guess it.\\n5. Action Determination: The core action seems to be 'search_files'.\\n6. Parameter Finalization: search_term is 'project alpha', file_type could be 'txt' (implied by 'text files'). However, 'search_path' for 'main dev folder' is missing.\\n7. Ambiguity Check: The location of 'main dev folder' is critical and ambiguous. Clarification is needed.",
  "action": "search_files",
  "parameters": {{
    "search_criteria": "text files about 'project alpha'"
  }},
  "clarification_needed": true,
  "suggested_question": "Which folder do you consider your 'main dev folder' for this search?",
  "nlu_method": "llm_direct_nlu"
}}
```
---
Example 3:
User Input: "list this directory"
Session Context:
- Current working directory: /user/documents/reports

Assistant JSON Output:
```json
{{
  "chain_of_thought": "1. User's Goal: List contents of the current directory.\\n2. Key Entities: 'this directory'.\\n3. Contextual Resolution: 'this directory' refers to the 'Current working directory' from context: /user/documents/reports.\\n4. Path Inference: Path is directly from context, can use '__CURRENT_DIR__'.\\n5. Action Determination: Action is 'list_folder_contents'.\\n6. Parameter Finalization: folder_path is '__CURRENT_DIR__'.\\n7. Ambiguity Check: No major ambiguity.",
  "action": "list_folder_contents",
  "parameters": {{
    "folder_path": "__CURRENT_DIR__"
  }},
  "clarification_needed": false,
  "suggested_question": "",
  "nlu_method": "llm_direct_nlu"
}}
```
---
END OF EXAMPLES.
"""
        # This prompt_content structure is crucial for Ollama when format: "json" is used.
        # The user input part should be minimal to let the system prompt dominate.
        prompt_for_llm = f"{system_prompt}\nUser Input: \"{user_input}\"\n{context_summary}\nAssistant JSON Output:"

        response_data = self._send_request_to_ollama(prompt_for_llm, is_json_mode=True)

        if not response_data:
            return {
                "chain_of_thought": "Error: No response from LLM.",
                "action": "unknown",
                "parameters": {"original_request": user_input, "error_reason": "No LLM NLU response."},
                "clarification_needed": False,
                "suggested_question": "",
                "nlu_method": "llm_no_response"
            }

        if "error_type" in response_data:
            error_message = response_data.get("message", "LLM NLU request failed due to an error.")
            return {
                "chain_of_thought": f"Error during NLU: {error_message}",
                "action": "unknown",
                "parameters": {"original_request": user_input, "error_reason": error_message},
                "clarification_needed": False,
                "suggested_question": "",
                "nlu_method": f"llm_{response_data.get('error_type', 'request_error')}"
            }
        
        # At this point, response_data should be the parsed JSON from the LLM
        parsed_llm_json = response_data

        # Validate required fields
        required_keys = ["chain_of_thought", "action", "parameters", "clarification_needed", "suggested_question", "nlu_method"]
        missing_keys = [key for key in required_keys if key not in parsed_llm_json]

        if missing_keys:
            error_detail = f"LLM NLU response missing required keys: {', '.join(missing_keys)}. Response: {str(parsed_llm_json)[:200]}"
            return {
                "chain_of_thought": f"Error: {error_detail}",
                "action": "unknown",
                "parameters": {"original_request": user_input, "error_reason": error_detail},
                "clarification_needed": False,
                "suggested_question": "",
                "nlu_method": "llm_incomplete_response"
            }
        
        # Add original user input to parameters for logging/debugging if not already there
        if "original_request" not in parsed_llm_json["parameters"]:
            parsed_llm_json["parameters"]["original_request_for_action"] = user_input

        return parsed_llm_json


    def check_content_match(self, file_content: str, criteria_description: str) -> bool:
        if not file_content: return False
        MAX_CONTENT_FOR_CHECK = 3500 # Consider making this configurable
        prompt = f"""
        File content (potentially truncated):
        --- FILE CONTENT START ---
        {file_content[:MAX_CONTENT_FOR_CHECK]} 
        --- FILE CONTENT END ---
        Does this content match: "{criteria_description}"? Respond ONLY with YES or NO.
        """
        response_data = self._send_request_to_ollama(prompt, is_json_mode=False)
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
        # This is a JSON request to the LLM.
        response_data = self._send_request_to_ollama(planning_meta_prompt, is_json_mode=True)
        
        if not response_data or "error_type" in response_data:
            return None # Error occurred or no response
        
        # response_data here is already the parsed JSON list from the LLM
        # due to the changes in _send_request_to_ollama for is_json_mode=True
        if isinstance(response_data, list):
            return response_data
        else:
            # If it's not a list, it's an unexpected format from the LLM (e.g. LLM returned an error object as JSON)
            # Or if the LLM failed to adhere to the "return an array" instruction.
            return None

