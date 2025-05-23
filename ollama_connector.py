

import os
import requests
import json
from ai_provider import AIProvider # Import AIProvider
# Removed: from config import OLLAMA_API_BASE_URL, OLLAMA_MODEL

class OllamaConnector(AIProvider): # Inherit from AIProvider
    def __init__(self, config: dict): # Modified __init__ signature
        self.base_url = config.get("BASE_URL", "http://localhost:11434") # Extract from config
        self.model = config.get("MODEL", "gemma3:1b") # Extract from config
        self.api_generate_url = f"{self.base_url}/api/generate"
        self.api_tags_url = f"{self.base_url}/api/tags" # For checking model availability

    def check_connection_and_model(self) -> tuple[bool, bool, list]: # Added type hints
        """
        Checks connection to Ollama and if the configured model is available.
        Returns: (connection_ok, model_found, list_of_available_models_details)
        """
        try:
            # Check base connection
            response = requests.get(self.base_url, timeout=5)
            response.raise_for_status() # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
            
            # Check model availability
            models_response = requests.get(self.api_tags_url, timeout=5)
            models_response.raise_for_status()
            
            available_models_data = models_response.json()
            if not isinstance(available_models_data, dict) or "models" not in available_models_data:
                # Unexpected response format from /api/tags
                return True, False, [] 

            available_models_list = available_models_data.get("models", [])
            if not isinstance(available_models_list, list):
                 return True, False, [] # Models field is not a list

            model_found = any(
                (m.get("name") == self.model or m.get("name", "").startswith(self.model + ":"))
                for m in available_models_list if isinstance(m, dict)
            )
            return True, model_found, available_models_list

        except requests.exceptions.RequestException as e:
            # Covers connection errors, timeouts, etc. for both requests
            # print(f"Debug: Ollama connection/model check failed: {e}") # Optional debug print
            return False, False, []
        except json.JSONDecodeError as e:
            # print(f"Debug: Ollama /api/tags response was not valid JSON: {e}") # Optional debug print
            return True, False, [] # Connection was okay, but model list parsing failed


    def _send_request_to_ollama(self, prompt_text: str, is_json_mode: bool = False) -> (dict | None): # Retained type hint as it's an internal method
        """
        Sends a request to the Ollama /api/generate endpoint.
        Handles JSON mode and basic error scenarios.
        Returns a dictionary (parsed JSON from LLM or error dict) or None on critical failure.
        """
        payload = {"model": self.model, "prompt": prompt_text, "stream": False}
        if is_json_mode:
            payload["format"] = "json"
        
        headers = {"Content-Type": "application/json"}
        response_obj = None 

        try:
            response_obj = requests.post(self.api_generate_url, data=json.dumps(payload), headers=headers, timeout=300) # 5 min timeout
            response_obj.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            
            ollama_api_response = response_obj.json() # Parse the successful response

            if is_json_mode:
                # In JSON mode, Ollama wraps the LLM's JSON output as a string within the 'response' field.
                if "response" in ollama_api_response and isinstance(ollama_api_response['response'], str):
                    try:
                        # Attempt to parse the stringified JSON from the LLM
                        parsed_llm_json = json.loads(ollama_api_response['response'])
                        return parsed_llm_json
                    except json.JSONDecodeError as e:
                        # LLM produced a string, but it wasn't valid JSON
                        return {
                            "error_type": "json_decode_error_llm",
                            "message": f"Ollama LLM returned a string that is not valid JSON. Error: {e}. Raw response (truncated): {ollama_api_response['response'][:300]}"
                        }
                else:
                    # This case implies Ollama didn't return the expected 'response' field as a string in JSON mode.
                    return {
                        "error_type": "json_mode_unexpected_response_field",
                        "message": f"Ollama in JSON mode, but the 'response' field is missing or not a string. Full API response (truncated): {str(ollama_api_response)[:500]}"
                    }
            else: # Not JSON mode, return the full Ollama API response dictionary
                return ollama_api_response

        except requests.exceptions.Timeout:
            return {"error_type": "timeout", "message": f"Ollama request timed out after 300 seconds. Prompt start: {prompt_text[:150]}..."}
        except requests.exceptions.HTTPError as e:
            error_body_str = "Could not retrieve error body."
            if response_obj is not None:
                try:
                    error_body_json = response_obj.json()
                    error_body_str = json.dumps(error_body_json, indent=2)
                except json.JSONDecodeError:
                    error_body_str = response_obj.text[:500] # Show first 500 chars if not JSON
            return {"error_type": "http_error", "message": f"Ollama HTTP Error: {e}. Response body: {error_body_str}"}
        except requests.exceptions.RequestException as e: # Catch other request-related errors (e.g., connection refused)
            return {"error_type": "request_error", "message": f"Ollama Request Error: {e}."}
        except json.JSONDecodeError as e: # If the initial response_obj.json() fails
             return {"error_type": "json_decode_error_api", "message": f"Failed to decode Ollama's main API response (not the LLM's JSON output). Error: {e}. Raw response: {response_obj.text[:300] if response_obj else 'N/A'}"}


    def invoke_llm_for_content(self, main_instruction: str, context_text: str = "") -> str:
        """
        Generic LLM invocation for tasks like summarization, Q&A, where a text response is expected.
        """
        full_prompt = f"{context_text}\n\n---\n\nUser Command: {main_instruction}" if context_text else main_instruction
        
        response_data = self._send_request_to_ollama(full_prompt, is_json_mode=False) 
        
        if response_data and "error_type" in response_data:
            return f"Error: LLM content generation failed. {response_data.get('message', 'Unknown Ollama error')}"
        
        return response_data.get("response", "").strip() if response_data else "Error: LLM content generation failed (no response or unexpected format)."

    def get_intent_and_entities(self, user_input: str, session_context: dict) -> dict:
        """
        Uses LLM to understand user intent and extract entities for file operations.
        Returns a structured dictionary based on the defined JSON output format.
        """
        context_summary_parts = []
        if session_context.get('current_directory'): 
            context_summary_parts.append(f"- Current working directory: {session_context['current_directory']}")
        if session_context.get('last_referenced_file_path'):
            context_summary_parts.append(f"- Last referenced file: {session_context['last_referenced_file_path']}")
        if session_context.get('last_folder_listed_path'):
            context_summary_parts.append(f"- Last listed folder: {session_context['last_folder_listed_path']}")
        if session_context.get('last_search_results'):
            context_summary_parts.append(f"- Last search produced {len(session_context['last_search_results'])} items.")
        if session_context.get('last_action_result'): # Keep this, useful for __PREVIOUS_ACTION_RESULT...
            # Truncate potentially long results
            result_str = str(session_context['last_action_result'])
            if len(result_str) > 200:
                result_str = result_str[:197] + "..."
            context_summary_parts.append(f"- Output of the immediate previous action step: {result_str}")

        context_summary = "No specific session context available."
        if context_summary_parts:
            context_summary = "Current session context:\n" + "\n".join(context_summary_parts)

        system_prompt = f"""
You are CodeX AI File Assistant, an expert in understanding user requests for file system operations.
Your task is to analyze the user's input, considering the provided session context, and provide a structured JSON output.
The output should be a list of actions to be performed sequentially.

**Core Rules for Path Handling & Parameters:**
1.  **Explicit Paths First:** If the user provides an explicit, absolute, or clearly defined relative path for an operation (e.g., "C:\\Users\\X\\Downloads", "./my_folder", "archive/reports"), you MUST use that exact path string as the value for the relevant path parameter.
2.  **Contextual Placeholders Second:** Only use placeholders like `__CURRENT_DIR__`, `__LAST_REFERENCED_FILE__`, `__LAST_LISTED_FOLDER__`, or chaining placeholders (`__PREVIOUS_ACTION_...`) if the user's command *explicitly relies on context* (e.g., "summarize it", "search here", "organize this folder", "list contents then search that folder").
3.  **Parameter Names are Strict:** You MUST use the exact parameter names specified for each action below (e.g., `search_path` for `search_files`, `target_path_or_context` for `propose_and_execute_organization`).
4.  **Output Placeholders as Strings:** When using a placeholder, output the placeholder string itself (e.g., `"search_path": "__CURRENT_DIR__"`). The system will resolve it.
5.  **Relative Paths from User:** If the user provides a relative path string (e.g., "my_project/docs"), pass that relative path string as the parameter value. The system will resolve it.

Always perform the following steps in your reasoning (which you will articulate in 'chain_of_thought'):
1.  **Deconstruct User's Goal:** Break down the user's request into a sequence of one or more discrete file system operations or queries.
2.  **For each operation in the sequence:**
    a.  **Identify Key Entities:** Extract file paths, folder paths, search terms, questions, etc., relevant to this specific operation. Adhere to "Explicit Paths First" rule.
    b.  **Contextual Resolution:** Explicitly state how you are using (or not using) the provided session context to resolve ambiguities or infer missing information for this operation, following the "Contextual Placeholders Second" rule. Consider 'current_directory', 'last_referenced_file_path', 'last_folder_listed_path', and 'last_action_result' (if chaining).
    c.  **Path Inference/Assumption:** If a full path is not given by user and context is used, explain how you are deriving it. Use placeholders:
        - `__CURRENT_DIR__`: For the current working directory if contextually appropriate (e.g., "here", "this folder").
        - `__LAST_REFERENCED_FILE__`: For the last file explicitly mentioned or acted upon.
        - `__LAST_LISTED_FOLDER__`: For the last folder whose contents were listed.
        - `__PREVIOUS_ACTION_RESULT_PATH__`: If the current action depends on a single file/folder path output from the *immediately preceding* action in THIS sequence.
        - `__PREVIOUS_ACTION_RESULT_FIRST_PATH__`: If the current action needs a single file/folder path from a list of items output by the *immediately preceding* action in THIS sequence.
        - `__MISSING__`: If a path is needed but genuinely not inferable from user input, context, or previous steps.
    d.  **Action Determination:** Determine the most appropriate single action from the list below for this operation.
    e.  **Parameter Finalization:** List the parameters required for that action. **Path parameters MUST use the specific names defined for the action.** Values will be explicit paths from user, or placeholders, or relative path strings.
    f.  **Step Description:** Briefly explain the purpose of this specific action step.
3.  **Overall Ambiguity Check:** If, after deconstruction, critical information for *any step* is missing or highly ambiguous (and not resolved by chaining or context), set 'clarification_needed' to true and formulate a specific question.

Available actions and their **strict parameter names**:
- "summarize_file": Parameters: **"file_path"** (string).
- "ask_question_about_file": Parameters: **"file_path"** (string, can be file or folder), **"question_text"** (string).
- "list_folder_contents": Parameters: **"folder_path"** (string, e.g., user path, `__CURRENT_DIR__`, `__LAST_LISTED_FOLDER__`, or `__PREVIOUS_ACTION_RESULT_PATH__`).
- "move_item": Parameters: **"source_path"** (string), **"destination_path"** (string).
- "search_files": Parameters: **"search_criteria"** (string), **"search_path"** (string, the directory to search within; optional, e.g., user path, `__CURRENT_DIR__`, `__PREVIOUS_ACTION_RESULT_PATH__`).
- "propose_and_execute_organization": Parameters: **"target_path_or_context"** (string, the folder to organize), **"organization_goal"** (string, optional). This action is for organizing contents *within* a folder.
- "show_activity_log": Parameters: **"count"** (integer, optional).
- "redo_activity": Parameters: **"activity_identifier"** (string).
- "general_chat": Parameters: **"original_request"** (string).
- "unknown": Parameters: **"original_request"** (string), **"error_reason"** (string). (Use this as a single action if the entire request is un-interpretable)

**OUTPUT FORMAT (Strict JSON):**
You MUST output a single JSON object with the following fields:
-   `chain_of_thought`: (string) Your detailed overall reasoning process. Use newline characters (\\n) for readability.
-   `actions`: (array of objects) A list of action objects. Each action object MUST contain:
    -   `action_name`: (string) The action identified for this step.
    -   `parameters`: (object) A JSON object containing parameters for this action, **using the strict parameter names defined above.**
    -   `step_description`: (string) Brief explanation of this step's purpose.
-   `clarification_needed`: (boolean) true if critical information is missing for any step, otherwise false.
-   `suggested_question`: (string) If 'clarification_needed' is true, provide a concise, targeted question. Otherwise, an empty string or null.
-   `nlu_method`: (string) Set this to "llm_multi_action_nlu".

**FEW-SHOT EXAMPLES:**
---
Example 1 (Single Action, Contextual):
User Input: "summarize the report I just looked at"
Session Context:
- Current working directory: /user/projects
- Last referenced file: /user/docs/Q3_financial_report.docx

Assistant JSON Output:
```json
{{
  "chain_of_thought": "User's Goal: Summarize a recently accessed file.\\nDecomposition: Single action - summarize.\\nStep 1 Reasoning: User said 'just looked at', so using 'Last referenced file' from context for the 'file_path' parameter. Action is 'summarize_file'. Parameters: file_path is __LAST_REFERENCED_FILE__. No ambiguity.",
  "actions": [
    {{
      "action_name": "summarize_file",
      "parameters": {{ "file_path": "__LAST_REFERENCED_FILE__" }},
      "step_description": "Summarize the last referenced financial report."
    }}
  ],
  "clarification_needed": false,
  "suggested_question": "",
  "nlu_method": "llm_multi_action_nlu"
}}
```
---
Example 2 (Multi-Action with Chaining and Explicit Path):
User Input: "list my C:\\Users\\Me\\Downloads folder and then find any pdfs in there"
Session Context:
- Current working directory: /user/home

Assistant JSON Output:
```json
{{
  "chain_of_thought": "User's Goal: First list C:\\Users\\Me\\Downloads, then search for PDFs within that folder.\\nDecomposition: Two actions - list, then search.\\nStep 1 (List): User provided an explicit path 'C:\\Users\\Me\\Downloads' for the 'folder_path' parameter. Action: 'list_folder_contents'.\\nStep 2 (Search): Search for 'pdfs'. The 'search_path' parameter should be the folder path listed in Step 1, so using '__PREVIOUS_ACTION_RESULT_PATH__'. Action: 'search_files'.\\nNo major ambiguity.",
  "actions": [
    {{
      "action_name": "list_folder_contents",
      "parameters": {{ "folder_path": "C:\\Users\\Me\\Downloads" }},
      "step_description": "List the contents of C:\\Users\\Me\\Downloads. The output of this action (the path listed) will be used by the next step."
    }},
    {{
      "action_name": "search_files",
      "parameters": {{ "search_criteria": "pdfs", "search_path": "__PREVIOUS_ACTION_RESULT_PATH__" }},
      "step_description": "Search for PDF files within the previously listed C:\\Users\\Me\\Downloads folder."
    }}
  ],
  "clarification_needed": false,
  "suggested_question": "",
  "nlu_method": "llm_multi_action_nlu"
}}
```
---
Example 3 (Multi-Action, Search then Summarize Chained, Relative Path):
User Input: "search for 'latest_earnings.docx' in my_docs and then summarize it"
Session Context:
- Current working directory: /user/home

Assistant JSON Output:
```json
{{
  "chain_of_thought": "User's Goal: Search for a specific document in a relative path, then summarize the found document.\\nDecomposition: Two actions - search, then summarize.\\nStep 1 (Search): Search for 'latest_earnings.docx' in 'my_docs'. User provided a relative path 'my_docs' for the 'search_path' parameter. Action: 'search_files'.\\nStep 2 (Summarize): Summarize the file found in Step 1. Using '__PREVIOUS_ACTION_RESULT_FIRST_PATH__' for the 'file_path' parameter to get the path of the (hopefully single) search result. Action: 'summarize_file'.\\nNo major ambiguity.",
  "actions": [
    {{
      "action_name": "search_files",
      "parameters": {{ "search_criteria": "latest_earnings.docx", "search_path": "my_docs" }},
      "step_description": "Search for the file 'latest_earnings.docx' in the 'my_docs' folder (system will resolve relative to CWD). The first result's path will be used by the next step."
    }},
    {{
      "action_name": "summarize_file",
      "parameters": {{ "file_path": "__PREVIOUS_ACTION_RESULT_FIRST_PATH__" }},
      "step_description": "Summarize the 'latest_earnings.docx' file found in the previous search step."
    }}
  ],
  "clarification_needed": false,
  "suggested_question": "",
  "nlu_method": "llm_multi_action_nlu"
}}
```
---
Example 4 (Ambiguity requiring clarification):
User Input: "organize them by date and then move project X files"
Session Context:
- Current working directory: /user/projects/project_alpha

Assistant JSON Output:
```json
{{
  "chain_of_thought": "User's Goal: Organize some items by date, then move specific project files.\\nDecomposition: Two actions - organize, then move.\\nStep 1 (Organize): 'them' is ambiguous. Context suggests current directory for 'target_path_or_context'. Goal: 'by date'. Action: 'propose_and_execute_organization'.\\nStep 2 (Move): 'project X files' is ambiguous for 'source_path'. 'destination_path' also unspecified. Action: 'move_item'.\\nOverall Ambiguity: Yes, Step 2 needs more info.",
  "actions": [
    {{
      "action_name": "propose_and_execute_organization",
      "parameters": {{ "target_path_or_context": "__CURRENT_DIR__", "organization_goal": "by date" }},
      "step_description": "Organize items in the current directory by date."
    }},
    {{
      "action_name": "move_item",
      "parameters": {{ "source_path": "__MISSING__", "destination_path": "__MISSING__" }},
      "step_description": "Move 'project X files'. Source and destination are unclear."
    }}
  ],
  "clarification_needed": true,
  "suggested_question": "For moving 'project X files': which files/folder are you referring to as the source for 'project X files', and where would you like to move them (destination path)?",
  "nlu_method": "llm_multi_action_nlu"
}}
```
---
Example 5 (Search with explicit path and criteria):
User Input: "search for images in C:\\Users\\MyUser\\Pictures"
Session Context:
- Current working directory: /user/home

Assistant JSON Output:
```json
{{
  "chain_of_thought": "User's Goal: Search for images in an explicit directory.\\nDecomposition: Single action - search.\\nStep 1 Reasoning: User provided explicit path 'C:\\Users\\MyUser\\Pictures' for 'search_path'. Search criteria is 'images'. Action is 'search_files'.\\nNo ambiguity.",
  "actions": [
    {{
      "action_name": "search_files",
      "parameters": {{ "search_criteria": "images", "search_path": "C:\\Users\\MyUser\\Pictures" }},
      "step_description": "Search for images in the C:\\Users\\MyUser\\Pictures directory."
    }}
  ],
  "clarification_needed": false,
  "suggested_question": "",
  "nlu_method": "llm_multi_action_nlu"
}}
```
---
END OF EXAMPLES.
"""
        prompt_for_llm = f"{system_prompt}\nUser Input: \"{user_input}\"\n{context_summary}\nAssistant JSON Output:"

        response_data = self._send_request_to_ollama(prompt_for_llm, is_json_mode=True)

        # Default error structure, ensuring all expected keys are present
        default_error_response = {
            "chain_of_thought": "Error: Could not process NLU request.",
            "actions": [{
                "action_name": "unknown",
                "parameters": {"original_request": user_input, "error_reason": "NLU processing failed."},
                "step_description": "Failed to understand the request."
            }],
            "clarification_needed": False,
            "suggested_question": "",
            "nlu_method": "llm_error_default" 
        }

        if not response_data: # Handles if _send_request_to_ollama returns None
            default_error_response["chain_of_thought"] = "Error: No response received from LLM NLU endpoint."
            default_error_response["actions"][0]["parameters"]["error_reason"] = "No response from LLM."
            default_error_response["nlu_method"] = "llm_no_response"
            return default_error_response

        if "error_type" in response_data: # Error dictionary returned by _send_request_to_ollama
            error_message = response_data.get("message", "LLM NLU request failed due to an unspecified error.")
            default_error_response["chain_of_thought"] = f"Error during NLU processing: {error_message}"
            default_error_response["actions"][0]["parameters"]["error_reason"] = error_message
            default_error_response["nlu_method"] = f"llm_{response_data.get('error_type', 'request_error')}"
            return default_error_response
        
        # At this point, response_data should be the successfully parsed JSON from the LLM
        parsed_llm_json = response_data
        
        # Validate the structure of the parsed_llm_json
        required_top_level_keys = ["chain_of_thought", "actions", "clarification_needed", "suggested_question", "nlu_method"]
        missing_top_level_keys = [key for key in required_top_level_keys if key not in parsed_llm_json]

        if missing_top_level_keys:
            error_detail = f"LLM NLU response is missing required top-level keys: {', '.join(missing_top_level_keys)}. Response (truncated): {str(parsed_llm_json)[:300]}"
            default_error_response["chain_of_thought"] = f"Error: {error_detail}"
            default_error_response["actions"][0]["parameters"]["error_reason"] = error_detail
            default_error_response["nlu_method"] = "llm_incomplete_response_top_level"
            return default_error_response

        if not isinstance(parsed_llm_json.get("actions"), list) or not parsed_llm_json.get("actions"):
            # LLM must provide at least one action, even if it's 'unknown'
            error_detail = f"LLM NLU 'actions' field is not a list or is empty. Response (truncated): {str(parsed_llm_json)[:300]}"
            default_error_response["chain_of_thought"] = f"Error: {error_detail}"
            default_error_response["actions"][0]["parameters"]["error_reason"] = error_detail
            default_error_response["nlu_method"] = "llm_invalid_actions_field"
            return default_error_response

        required_action_keys = ["action_name", "parameters", "step_description"]
        for i, action_item in enumerate(parsed_llm_json["actions"]):
            if not isinstance(action_item, dict):
                error_detail = f"Action item at index {i} is not a dictionary. Response (truncated): {str(parsed_llm_json)[:300]}"
                default_error_response["chain_of_thought"] = f"Error: {error_detail}"
                default_error_response["actions"][0]["parameters"]["error_reason"] = error_detail
                default_error_response["nlu_method"] = "llm_invalid_action_item_type"
                return default_error_response
            
            missing_action_keys = [key for key in required_action_keys if key not in action_item]
            if missing_action_keys:
                error_detail = f"Action item at index {i} is missing required keys: {', '.join(missing_action_keys)}. Response (truncated): {str(parsed_llm_json)[:300]}"
                default_error_response["chain_of_thought"] = f"Error: {error_detail}"
                default_error_response["actions"][0]["parameters"]["error_reason"] = error_detail
                default_error_response["nlu_method"] = "llm_incomplete_action_item"
                return default_error_response

            if not isinstance(action_item.get("parameters"), dict):
                error_detail = f"Action item at index {i} has a 'parameters' field that is not a dictionary. Response (truncated): {str(parsed_llm_json)[:300]}"
                default_error_response["chain_of_thought"] = f"Error: {error_detail}"
                default_error_response["actions"][0]["parameters"]["error_reason"] = error_detail
                default_error_response["nlu_method"] = "llm_invalid_action_parameters_type"
                return default_error_response

        return parsed_llm_json # Return the validated JSON from LLM

    def generate_organization_plan(self, target_folder_path: str, organization_goal: str, current_contents_summary: str) -> dict:
        """
        Asks LLM to generate an organization plan.
        Returns a dictionary with 'plan_steps' and 'explanation', or 'error'.
        """
        items_list_str = current_contents_summary 
        base_path_for_plan = target_folder_path
        user_goal_str = organization_goal

        plan_steps_list = self._generate_actual_organization_plan_with_detailed_prompt(
            items_list_str, user_goal_str, base_path_for_plan
        )

        if plan_steps_list is None: # Error occurred during plan generation
            return {"error": "LLM failed to generate a valid organization plan JSON."}
        
        return {
            "plan_steps": plan_steps_list,
            "explanation": "Plan generated by LLM." # LLM could provide a better explanation
        }

    def _generate_actual_organization_plan_with_detailed_prompt(self, items_list_str: str, user_goal_str: str, base_path_for_plan: str) -> (list | None):
        """
        This internal helper would contain the full, detailed prompt for organization planning.
        It calls _send_request_to_ollama in JSON mode.
        Returns a list of plan steps (dictionaries) or None on error.
        """
        example_images_folder = os.path.join(base_path_for_plan, "Images_Organized")
        example_photo_source = os.path.join(base_path_for_plan, "holiday_photo.jpg") 
        example_photo_dest = os.path.join(example_images_folder, "holiday_photo.jpg")
        
        example_alpha_folder_A_name = "A_files" 
        example_alpha_folder_A = os.path.join(base_path_for_plan, example_alpha_folder_A_name)
        example_alpha_source_apple = os.path.join(base_path_for_plan, "apple.txt")
        example_alpha_dest_apple = os.path.join(example_alpha_folder_A, "apple.txt")

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
    1. Identifying the first alphanumeric character of each item's filename.
    2. Creating a destination subfolder based on this character (e.g., for 'apple.txt', the folder would be '{example_alpha_folder_A_name}'; for '123report.doc', '0-9_files'). Ensure folder names are simple, like "A_files", "B_files", "0-9_files", "Symbols_files". Paths to these folders must be absolute.
    3. Moving the item into its corresponding first-letter subfolder. All paths MUST be absolute.
- If goal involves project names: Try to group items into project-specific subfolders like "{os.path.join(base_path_for_plan, "ProjectAlpha")}".

Rules for the plan:
1.  Convert all relative item paths from `items_list_str` to absolute paths using `base_path_for_plan` for the "source" in MOVE_ITEM actions.
2.  Create necessary folders (using CREATE_FOLDER) before moving items into them (using MOVE_ITEM).
3.  Ensure source and destination for MOVE_ITEM are different.
4.  Do not propose moving a folder into itself or one of its own subfolders.
5.  Be conservative: if an item's organization is unclear, or it already seems well-organized according to the goal, it's okay to not include an action for it.
6.  If the goal is unclear even after consulting 'User Goal Mapping for Names' for relevant name-based goals, or if applying the 'first_letter_folder_organization' strategy would be trivial (e.g., all items already start with 'S', or there are very few items like 1 or 2), return an empty JSON array: [].

Example for "by type" (organizing items into an "Images_Organized" subfolder within base_path_for_plan):
[
  {{"action_type": "CREATE_FOLDER", "path": "{example_images_folder}"}},
  {{"action_type": "MOVE_ITEM", "source": "{example_photo_source}", "destination": "{example_photo_dest}"}}
]
Example for user_goal_str: "the names" (using 'first_letter_folder_organization' strategy for hypothetical items "apple.txt" in base path):
[
  {{"action_type": "CREATE_FOLDER", "path": "{example_alpha_folder_A}"}},
  {{"action_type": "MOVE_ITEM", "source": "{example_alpha_source_apple}", "destination": "{example_alpha_dest_apple}"}}
]

Your JSON plan (must be an array):
"""
        response_data = self._send_request_to_ollama(planning_meta_prompt, is_json_mode=True)
        
        if not response_data or "error_type" in response_data:
            return None 
        
        if isinstance(response_data, list):
            valid_plan = True
            for step in response_data:
                if not isinstance(step, dict) or "action_type" not in step:
                    valid_plan = False
                    break
                if step["action_type"] == "CREATE_FOLDER" and "path" not in step:
                    valid_plan = False
                    break
                if step["action_type"] == "MOVE_ITEM" and ("source" not in step or "destination" not in step):
                    valid_plan = False
                    break
            return response_data if valid_plan else None
        else:
            return None


    def get_summary(self, file_content: str, file_path_for_context: str) -> dict:
        """Asks LLM to summarize the given text content."""
        instruction = f"Summarize the following content from the file '{os.path.basename(file_path_for_context)}'. Provide a concise summary."
        summary_text = self.invoke_llm_for_content(instruction, file_content)
        if summary_text.startswith("Error:"):
            return {"error": summary_text}
        return {"summary_text": summary_text}

    def ask_question_about_text(self, text_content: str, question: str, file_path_for_context: str) -> dict:
        """Asks LLM a question about the given text content."""
        instruction = f"Regarding the content of the file '{os.path.basename(file_path_for_context)}', answer the following question: {question}"
        answer_text = self.invoke_llm_for_content(instruction, text_content)
        if answer_text.startswith("Error:"):
            return {"error": answer_text}
        return {"answer_text": answer_text}

    def general_chat_completion(self, user_query: str) -> dict:
        """For general queries not fitting specific actions."""
        response_text = self.invoke_llm_for_content(user_query)
        if response_text.startswith("Error:"):
            return {"error": response_text}
        return {"response_text": response_text}
