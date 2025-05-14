
import os
import re
import json # Though not directly used now, might be for future complex param processing
from rich.prompt import Prompt, Confirm
from rich.text import Text

from ollama_connector import OllamaConnector # For type hinting
from path_resolver import get_path_from_user_input, resolve_contextual_path
from cli_ui import print_warning, print_info, print_error, console as global_console # Use the global console
from cli_constants import ICONS, KNOWN_BAD_EXAMPLE_PATHS


def process_nlu_result(parsed_command: dict, user_input: str, session_ctx: dict, connector: OllamaConnector) -> tuple[str | None, dict, str | None]:
    action = parsed_command.get("action")
    parameters = parsed_command.get("parameters", {})
    nlu_notes = parsed_command.get("nlu_method") or parsed_command.get("nlu_correction_note")

    if not action or action == "unknown":
        llm_error = parameters.get("error", "Could not understand request.")
        return "unknown", {"original_request": user_input, "error": llm_error}, nlu_notes

    final_params = {}
    
    if action == "summarize_file":
        raw_path = parameters.get("file_path")
        if raw_path and isinstance(raw_path, str) and raw_path.lower() in [p.lower() for p in KNOWN_BAD_EXAMPLE_PATHS]:
            path_in_user_input_match = re.search(r"summarize\s+(['\"]?)(.+?)\1(?:$|\s)", user_input, re.IGNORECASE)
            if path_in_user_input_match:
                user_provided_path = path_in_user_input_match.group(2).strip()
                if user_provided_path.lower() != raw_path.lower():
                    raw_path = user_provided_path
                    nlu_notes = (nlu_notes + "; PathOverriddenFromUserInput(AntiHallucination)") if nlu_notes else "PathOverriddenFromUserInput(AntiHallucination)"
        
        resolved_path = resolve_contextual_path(raw_path, session_ctx, is_folder_hint=False)
        if not resolved_path or raw_path == "__MISSING__":
            resolved_path = get_path_from_user_input(global_console, "Which file to summarize?", default_path=session_ctx.get("last_referenced_file_path"))
        final_params["file_path"] = os.path.abspath(resolved_path) if resolved_path else None
    
    elif action == "ask_question_about_file":
        raw_path = parameters.get("file_path")
        resolved_path = resolve_contextual_path(raw_path, session_ctx)
        if not resolved_path or raw_path == "__MISSING__":
            default_ask_path = session_ctx.get("last_referenced_file_path") or session_ctx.get("last_folder_listed_path")
            resolved_path = get_path_from_user_input(global_console, "Which file or folder are you asking about?", default_path=default_ask_path)
        final_params["file_path"] = os.path.abspath(resolved_path) if resolved_path else None
        final_params["question_text"] = parameters.get("question_text", "")
        if not final_params["question_text"] and final_params.get("file_path"):
            item_name_q = os.path.basename(final_params["file_path"])
            final_params["question_text"] = Prompt.ask(f"What is your question about [filepath]{item_name_q}[/filepath]?", console=global_console)

    elif action == "list_folder_contents":
        raw_path = parameters.get("folder_path")
        resolved_path = resolve_contextual_path(raw_path, session_ctx, is_folder_hint=True)
        if not resolved_path or raw_path == "__MISSING__":
            default_list_path = session_ctx.get("last_folder_listed_path") or \
                                (os.path.dirname(session_ctx["last_referenced_file_path"]) if session_ctx.get("last_referenced_file_path") and os.path.isfile(session_ctx.get("last_referenced_file_path")) else None) or \
                                os.getcwd()
            resolved_path = get_path_from_user_input(global_console, "Which folder to list?", default_path=default_list_path, is_folder=True)
        final_params["folder_path"] = os.path.abspath(resolved_path) if resolved_path else None

    elif action == "search_files":
        final_params["search_criteria"] = parameters.get("search_criteria")
        if not final_params["search_criteria"] or final_params["search_criteria"] == "__MISSING__":
            final_params["search_criteria"] = Prompt.ask("What are you searching for?", console=global_console)
        
        raw_path = parameters.get("search_path")
        resolved_path = None
        if raw_path and raw_path not in ["__MISSING__", "__FROM_CONTEXT__"]:
            if raw_path.lower() in [".", "here", "current folder", "this folder"]: resolved_path = os.getcwd()
            else: resolved_path = os.path.abspath(raw_path)
        elif raw_path == "__FROM_CONTEXT__":
            resolved_path = resolve_contextual_path(raw_path, session_ctx, is_folder_hint=True)
        
        if not resolved_path or not (isinstance(resolved_path, str) and os.path.isdir(resolved_path)):
            default_search_dir = session_ctx.get("last_folder_listed_path") or os.getcwd()
            if resolved_path and not (isinstance(resolved_path, str) and os.path.isdir(resolved_path)):
                print_warning(f"Search path '[filepath]{resolved_path}[/filepath]' from NLU is invalid. Prompting.")
            resolved_path = get_path_from_user_input(global_console, "Where should I search?", default_path=default_search_dir, is_folder=True)
        final_params["search_path"] = os.path.abspath(resolved_path) if resolved_path else None

    elif action == "move_item":
        raw_source_path = parameters.get("source_path")
        resolved_source_path = None
        if raw_source_path and raw_source_path not in ["__MISSING__", "__FROM_CONTEXT__"]:
            resolved_source_path = os.path.abspath(raw_source_path)
        elif raw_source_path == "__FROM_CONTEXT__":
            resolved_source_path = resolve_contextual_path(raw_source_path, session_ctx)
        
        if not resolved_source_path:
            default_move_src = session_ctx.get("last_referenced_file_path") or session_ctx.get("last_folder_listed_path")
            resolved_source_path = get_path_from_user_input(global_console, "What item to move (source)?", default_path=default_move_src)
        final_params["source_path"] = os.path.abspath(resolved_source_path) if resolved_source_path else None
        
        raw_dest_path = parameters.get("destination_path")
        resolved_dest_path = None
        if raw_dest_path and raw_dest_path not in ["__MISSING__", "__FROM_CONTEXT__"]:
             resolved_dest_path = os.path.abspath(raw_dest_path)
        elif raw_dest_path == "__FROM_CONTEXT__":
             resolved_dest_path = resolve_contextual_path(raw_dest_path, session_ctx, is_folder_hint=True)

        if not resolved_dest_path:
            item_name_m = os.path.basename(final_params["source_path"]) if final_params.get("source_path") else "the item"
            default_move_dest = session_ctx.get("last_folder_listed_path")
            resolved_dest_path = get_path_from_user_input(global_console, f"Where to move '{item_name_m}' (destination)?", default_path=default_move_dest)
        final_params["destination_path"] = os.path.abspath(resolved_dest_path) if resolved_dest_path else None
        
    elif action == "propose_and_execute_organization":
        raw_path = parameters.get("target_path_or_context")
        resolved_path = None
        
        current_nlu_method = parsed_command.get("nlu_method", "")
        if current_nlu_method.startswith("llm") and raw_path and isinstance(raw_path, str) and raw_path.lower() in [p.lower() for p in KNOWN_BAD_EXAMPLE_PATHS]:
            path_match_in_user_input = re.search(r"(?:organize|sort|clean\s*up)\s+(['\"]?)(.+?)\1(?:\s+by|\s+based\s+on|$)", user_input, re.IGNORECASE)
            if path_match_in_user_input:
                user_provided_path = path_match_in_user_input.group(2).strip()
                if user_provided_path and user_provided_path.lower() != raw_path.lower():
                    raw_path = user_provided_path
                    nlu_notes = (nlu_notes + "; OrgPathOverriddenFromUserInput(AntiHallucination)") if nlu_notes else "OrgPathOverriddenFromUserInput(AntiHallucination)"

        if raw_path == "__FROM_CONTEXT__":
            resolved_path = session_ctx.get("last_folder_listed_path")
            if not resolved_path or not (isinstance(resolved_path, str) and os.path.isdir(resolved_path)):
                print_warning("No valid folder context for 'organize it/this'. Please list a folder first, or specify a folder path.", "Organization Context")
                return "unknown", {"original_request": user_input, "error": "Missing folder context for organization"}, nlu_notes
        elif raw_path and raw_path != "__MISSING__":
            path_to_check_org = raw_path
            if path_to_check_org.startswith('~'): path_to_check_org = os.path.expanduser(path_to_check_org)
            resolved_path_candidate = os.path.abspath(path_to_check_org)
            if os.path.exists(resolved_path_candidate) and os.path.isdir(resolved_path_candidate):
                resolved_path = resolved_path_candidate
            else:
                print_warning(f"Organization target '[filepath]{raw_path}[/filepath]' (resolved to '[filepath]{resolved_path_candidate}[/filepath]') is invalid or not a directory. Prompting.")
                resolved_path = get_path_from_user_input(global_console, "Which folder to organize?", default_path=session_ctx.get("last_folder_listed_path") or os.getcwd(), is_folder=True)
        else: 
            resolved_path = get_path_from_user_input(global_console, "Which folder to organize?", default_path=session_ctx.get("last_folder_listed_path") or os.getcwd(), is_folder=True)
        
        final_params["target_path_or_context"] = os.path.abspath(resolved_path) if resolved_path else None
        final_params["organization_goal"] = parameters.get("organization_goal")
        
        if final_params.get("target_path_or_context") and os.path.isdir(final_params["target_path_or_context"]):
            org_target_display = os.path.basename(final_params["target_path_or_context"])
            org_goal_display = final_params.get("organization_goal") or "general organization"
            confirm_msg = (f"I will attempt to organize the folder "
                           f"'[filepath]{org_target_display}[/filepath]' "
                           f"based on the goal: '[highlight]{org_goal_display}[/highlight]'.\n"
                           f"Full path: [dim_text]{final_params['target_path_or_context']}[/dim_text]\n"
                           f"Is this correct?")
            if not Confirm.ask(Text.from_markup(f"{ICONS['confirm']} {confirm_msg}"), default=True, console=global_console):
                print_info("Organization attempt cancelled by user.")
                return "user_cancelled_organization", {"target": final_params["target_path_or_context"], "goal": final_params.get("organization_goal")}, (nlu_notes + "; UserCancelledPrePlan") if nlu_notes else "UserCancelledPrePlan"
        elif not final_params.get("target_path_or_context"):
             print_error("Organization target folder is missing. Cannot proceed.", "Organization Error")
             return "unknown", {"original_request": user_input, "error": "Missing target folder for organization after processing"}, nlu_notes

    elif action == "show_activity_log": final_params["count"] = parameters.get("count")
    elif action == "redo_activity":
        final_params["activity_identifier"] = parameters.get("activity_identifier")
        if not final_params["activity_identifier"]: final_params["activity_identifier"] = Prompt.ask("Which activity to redo ('last', index, or partial timestamp)?", console=global_console)
    elif action == "general_chat": final_params["original_request"] = parameters.get("original_request", user_input)
    else: final_params = parameters # Pass through if no specific processing

    return action, final_params, nlu_notes


def resolve_indexed_reference(user_input_lower: str, action_name: str, parameters: dict, session_ctx: dict):
    # This function modifies `parameters` and can change `action_name`.
    # It returns the potentially new action_name and a boolean indicating if resolution occurred.
    
    path_keys_to_check = ["file_path", "folder_path", "target_path_or_context", "source_path"]
    is_explicit_path_present = False
    for pk in path_keys_to_check:
        val = parameters.get(pk)
        if val and val not in ["__MISSING__", "__FROM_CONTEXT__"]:
            is_explicit_path_present = True
            break
    
    if is_explicit_path_present and not re.fullmatch(r"(?:item\s*|number\s*|file\s*|#\s*)?(\d+)(?:st|nd|rd|th)?(?:\s*one)?", user_input_lower.strip()):
         return action_name, False # Explicit path from NLU takes precedence

    match = re.search(r"(?:item\s*|number\s*|file\s*|#\s*)?(\d+)(?:st|nd|rd|th)?(?:\s*one)?", user_input_lower)
    if match and session_ctx.get("last_search_results"):
        try:
            idx = int(match.group(1)) - 1
            is_likely_direct_index_ref = (user_input_lower.strip() == match.group(0).strip()) or \
                                         (action_name in ["summarize_file", "list_folder_contents", "ask_question_about_file"] and \
                                          (match.group(0).strip() in user_input_lower))

            if is_likely_direct_index_ref and 0 <= idx < len(session_ctx["last_search_results"]):
                item = session_ctx["last_search_results"][idx]
                
                for p_key in ["file_path", "folder_path", "target_path_or_context", "source_path", "destination_path"]:
                    if p_key in parameters:
                        del parameters[p_key]

                new_action_name = action_name
                if item["type"] == "file":
                    parameters["file_path"] = item["path"]
                    ask = ("ask" in action_name.lower() or any(k in user_input_lower for k in ["ask ","tell me","what is","explain","question"]))
                    summ = ("summarize" in action_name.lower() or "summarize" in user_input_lower)
                    
                    if ask:
                        new_action_name="ask_question_about_file"
                        q_part = user_input_lower.replace(match.group(0).strip(),"",1)
                        for verb in ["ask","tell me","what is","explain","question about", "summarize", "summary of", "list"]:
                             q_part = re.sub(r'\b'+re.escape(verb)+r'\b','',q_part,flags=re.I).strip()
                        parameters["question_text"]= q_part if q_part else f"Tell me more about {os.path.basename(item['name'])}"
                    elif summ or not action_name or action_name=="unknown":
                        new_action_name="summarize_file"
                
                elif item["type"] == "folder":
                    parameters["folder_path"]=item["path"]
                    org = ("organize" in action_name.lower() or "organize" in user_input_lower or "sort" in user_input_lower)
                    list_cmd = ("list" in action_name.lower() or "ls" in user_input_lower or "contents" in user_input_lower)

                    if org:
                        new_action_name="propose_and_execute_organization"
                        parameters["target_path_or_context"]=item["path"]
                        g_part_text = user_input_lower.replace(match.group(0).strip(),"",1)
                        for verb in ["organize","sort","list","ls"]: g_part_text = re.sub(r'\b'+re.escape(verb)+r'\b','',g_part_text,flags=re.I).strip()
                        g_part_match = re.search(r"(?:by|based\s+on)\s+(['\"]?)(.+?)\1?$", g_part_text, re.IGNORECASE)
                        if g_part_match:
                             parameters["organization_goal"] = g_part_match.group(2).strip().rstrip("'\" ")
                        elif parameters.get("organization_goal"): pass
                        else: parameters["organization_goal"] = None
                    elif list_cmd or not action_name or action_name=="unknown":
                        new_action_name="list_folder_contents"
                
                # Update action in parameters dict if it changed, so main loop can use it.
                # This is a bit of a hack; ideally resolve_indexed_reference returns new action separately.
                parameters["action"] = new_action_name 
                return new_action_name, True
        except (ValueError,TypeError,AttributeError):
            pass
    return action_name, False