
import os
import json
import datetime
import re # For handle_propose_and_execute_organization's fallback logic
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.progress import Progress
from rich.text import Text
from rich.padding import Padding
from rich.box import ROUNDED
from rich.prompt import Confirm # For move_item and redo_activity, propose_organization

# Local/project imports
from ollama_connector import OllamaConnector
from file_utils import get_file_content, move_item as fu_move_item, list_folder_contents as fu_list_folder_contents, search_files_recursive as fu_search_files_recursive
from activity_logger import log_action, get_recent_activities, get_activity_by_partial_id_or_index, MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL
from .fs_utils import is_path_within_base
from . import session_manager # To update session context
from .cli_ui import console, ICONS, print_error, print_success, print_warning, print_info, print_panel_message
from . import nlu_processor # For handle_redo_activity -> process_nlu_result

# This map will be populated at the end of the file
_ACTION_HANDLERS_MAP = {}

# --- Action Handlers ---
def handle_summarize_file(connector: OllamaConnector, parameters: dict):
    abs_filepath = parameters.get("file_path")
    if not abs_filepath or not os.path.isfile(abs_filepath):
        print_error(f"Cannot summarize: Path '[filepath]{abs_filepath}[/filepath]' is not a valid file.", "Summarize Error")
        log_action("summarize_file", parameters, "failure", f"Invalid or missing file path: {abs_filepath}")
        return
    console.print(f"{ICONS['file']} Attempting to summarize: [filepath]{abs_filepath}[/filepath]")
    session_manager.update_session_context("last_referenced_file_path", abs_filepath)
    content = get_file_content(abs_filepath, console)
    if content:
        if content.startswith("Error extracting text from PDF"):
            print_warning(content, "PDF Summarization Issue")
            log_action("summarize_file", parameters, "partial_success", f"PDF extraction error: {content.split(':', 1)[-1].strip()}")
            return
        summary = connector.invoke_llm_for_content("Summarize this file content comprehensively and concisely, focusing on key information and main points:", content)
        if summary.startswith("Error: LLM content generation failed"): print_error(summary, "LLM Summarization Failed")
        else: print_panel_message("LLM Summary", summary, "info", ICONS["summary"])
        log_action("summarize_file", parameters, "success", f"Summary length: {len(summary)}")
    else: log_action("summarize_file", parameters, "failure", "Could not read file")

def handle_ask_question(connector: OllamaConnector, parameters: dict):
    abs_filepath = parameters.get("file_path")
    question = parameters.get("question_text", "")
    if not abs_filepath or not os.path.exists(abs_filepath):
        print_error(f"Q&A Error: Path '[filepath]{abs_filepath}[/filepath]' does not exist.")
        log_action("ask_question", parameters, "failure", f"Path missing for Q&A: {abs_filepath}")
        return
    if not question:
        print_warning("No question for Q&A.") # Should be caught by nlu_processor ideally
        log_action("ask_question", parameters, "failure", "No question text")
        return
    
    item_name_display = os.path.basename(abs_filepath)
    log_action_name = "ask_question_about_folder" if os.path.isdir(abs_filepath) else "ask_question_about_file"

    if os.path.isdir(abs_filepath):
        session_manager.update_session_context("last_folder_listed_path", abs_filepath)
        session_manager.update_session_context("last_referenced_file_path", None)
        console.print(f"{ICONS['folder']} Analyzing folder: [filepath]{abs_filepath}[/filepath]\n{ICONS['question']} Question: [italic white]{question}[/italic white]")
        items = fu_list_folder_contents(abs_filepath, console) or []
        ctx = f"Folder '{item_name_display}' "
        if not items: ctx += "is empty."
        else: ctx += "contains:\n" + "\n".join([f"- {i.get('name','N/A')} ({i.get('type','N/A')})" for i in items[:15]])
        if len(items)>15: ctx+=f"\n...and {len(items)-15} more."
        
        eff_q = question
        if question.lower() in ["what about it?","analyze this", "tell me about it", "what do you think about it?", "your thoughts?"]:
            eff_q = f"Analyze folder '{item_name_display}'. What patterns or interesting aspects do you observe? Any organization opportunities?"
        
        ans = connector.invoke_llm_for_content(f"Answer based on folder info: {eff_q}", ctx)
        if ans.startswith("Error: LLM content generation failed"): print_error(ans,"LLM Folder Analysis Failed")
        else: print_panel_message("Folder Analysis",ans,"info",ICONS["answer"])
        log_action(log_action_name,parameters,"success",f"Analysis len:{len(ans)}")

    elif os.path.isfile(abs_filepath):
        session_manager.update_session_context("last_referenced_file_path",abs_filepath)
        console.print(f"{ICONS['file']} Asking about file: [filepath]{abs_filepath}[/filepath]\n{ICONS['question']} Question: [italic white]{question}[/italic white]")
        content = get_file_content(abs_filepath,console)
        if content:
            if content.startswith("Error extracting text from PDF"):
                print_warning(content, "PDF Q&A Issue")
                log_action(log_action_name, parameters, "partial_success", f"PDF extraction error: {content.split(':', 1)[-1].strip()}")
                return
            ans = connector.invoke_llm_for_content(f"Answer based on file content: {question}",content)
            if ans.startswith("Error: LLM content generation failed"): print_error(ans,"LLM Answer Failed")
            else: print_panel_message("LLM Answer",ans,"info",ICONS["answer"])
            log_action(log_action_name,parameters,"success",f"Ans len:{len(ans)}")
        else: log_action(log_action_name,parameters,"failure","Cannot read file")
    else: print_error(f"Path '[filepath]{abs_filepath}[/filepath]' is neither a file nor a directory.", "Q&A Path Error")


def handle_list_folder(parameters: dict): # No connector needed
    abs_folder_path = parameters.get("folder_path")
    if not abs_folder_path or not os.path.isdir(abs_folder_path):
        print_error(f"List Error: Path '[filepath]{abs_folder_path}[/filepath]' invalid.")
        log_action("list_folder_contents", parameters, "failure", "Invalid folder path for list")
        return
    console.print(f"{ICONS['folder']} Listing: [filepath]{abs_folder_path}[/filepath]")
    session_manager.update_session_context("last_folder_listed_path", abs_folder_path)
    session_manager.update_session_context("last_referenced_file_path", None)
    contents = fu_list_folder_contents(abs_folder_path, console)
    if contents is not None:
        if not contents:
            print_info(f"Folder '[filepath]{os.path.basename(abs_folder_path)}[/filepath]' empty.","Folder Empty")
            session_manager.update_session_context("last_search_results",[])
        else:
            tbl=Table(title=f"{ICONS['folder']} Contents of {os.path.basename(abs_folder_path)} ({len(contents)})",box=ROUNDED,expand=True, header_style="table.header")
            tbl.add_column("Icon",width=4,justify="center"); tbl.add_column("Idx",width=5,justify="right"); tbl.add_column("Name",style="filepath",overflow="fold"); tbl.add_column("Type",width=10)
            for i,item in enumerate(contents): tbl.add_row(ICONS["folder"] if item['type']=="folder" else ICONS["file"],str(i+1),item['name'],item['type'])
            console.print(tbl)
            session_manager.update_session_context("last_search_results",contents)
        log_action("list_folder_contents",parameters,"success",f"Listed {len(contents) if contents else 0}")
    else: log_action("list_folder_contents",parameters,"failure","file_utils list error")

def handle_move_item(parameters: dict): # No connector needed
    abs_source_path = parameters.get("source_path")
    abs_destination_path = parameters.get("destination_path")
    if not abs_source_path or not os.path.exists(abs_source_path):
        print_error(f"Move Error: Src '[filepath]{abs_source_path}[/filepath]' missing.")
        log_action("move_item", parameters, "failure", "Source missing for move")
        return
    if not abs_destination_path:
        print_error("Move Error: Dest missing.")
        log_action("move_item", parameters, "failure", "Destination missing for move")
        return
    print_panel_message("Confirm Move",f"FROM:[filepath]{abs_source_path}[/filepath]\nTO:  [filepath]{abs_destination_path}[/filepath]","warning",ICONS["confirm"])
    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Proceed?"),default=False, console=console):
        if fu_move_item(abs_source_path,abs_destination_path,console):
            print_success(f"Moved '[filepath]{os.path.basename(abs_source_path)}[/filepath]' to '[filepath]{abs_destination_path}[/filepath]'.")
            log_action("move_item",parameters,"success")
            session_manager.update_session_context("last_referenced_file_path",None)
            session_manager.update_session_context("last_folder_listed_path",None)
            session_manager.update_session_context("last_search_results",[])
        else: log_action("move_item",parameters,"failure","file_utils move error")
    else: print_info("Move cancelled."); log_action("move_item",parameters,"cancelled")

def handle_search_files(connector: OllamaConnector, parameters: dict):
    search_criteria = parameters.get("search_criteria")
    abs_search_path = parameters.get("search_path")
    if not search_criteria:
        print_error("Search Error: No criteria.")
        log_action("search_files", parameters, "failure", "No criteria for search")
        return
    if not abs_search_path or not os.path.isdir(abs_search_path):
        print_error(f"Search Error: Path '[filepath]{abs_search_path}[/filepath]' invalid.")
        log_action("search_files", parameters, "failure", "Invalid search path")
        return
    console.print(f"{ICONS['search']} Searching in [filepath]{abs_search_path}[/filepath] for: [highlight]'{search_criteria}'[/highlight]")
    found = fu_search_files_recursive(abs_search_path,search_criteria,connector,console)
    if not found: print_info(f"No matches for [highlight]'{search_criteria}'[/highlight]","Search Results")
    else:
        print_success(f"Found {len(found)} matching [highlight]'{search_criteria}'[/highlight]:","Search Results")
        tbl=Table(title=f"{ICONS['search']} Results",box=ROUNDED,expand=True, header_style="table.header")
        tbl.add_column("Icon",width=4,justify="center"); tbl.add_column("Idx",width=5,justify="right"); tbl.add_column("Name",style="filepath",overflow="fold"); tbl.add_column("Path",style="dim_text",overflow="fold")
        for i,item in enumerate(found): tbl.add_row(ICONS["folder"] if item['type']=="folder" else ICONS["file"],str(i+1),item['name'],item['path'])
        console.print(tbl)
    session_manager.update_session_context("last_search_results",found)
    session_manager.update_session_context("last_folder_listed_path",abs_search_path)
    log_action("search_files",parameters,"success",f"Found {len(found)}")

def handle_general_chat(connector: OllamaConnector, parameters: dict):
    req = parameters.get("original_request","...")
    spinner=f"{ICONS['thinking']} [spinner_style]Thinking: '{req[:30]}...'[/spinner_style]"
    with Live(Spinner("bouncingBar",text=spinner),console=console,transient=True): resp = connector.invoke_llm_for_content(req)
    if resp.startswith("Error: LLM content generation failed"): print_error(resp,"LLM Chat Failed")
    else: print_panel_message("CodeX Response",resp,"info",ICONS["answer"])
    log_action("general_chat",parameters,"success",f"Resp len:{len(resp)}")

def handle_show_activity_log(parameters: dict): # No connector needed
    count_param = parameters.get("count"); default_log_count = MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL//2
    try:
        count = int(count_param) if count_param is not None else default_log_count
        if not (0<count<=MAX_LOG_ENTRIES_SIMPLE_RETRIEVAL): count = default_log_count
    except (ValueError,TypeError): count = default_log_count
    activities = get_recent_activities(count)
    if not activities: print_info("Activity log empty.","Activity Log"); return
    tbl=Table(title=f"{ICONS['log']} Recent Activity (Last {len(activities)})",box=ROUNDED, header_style="table.header")
    tbl.add_column("TS",style="dim_text",width=22); tbl.add_column("Action",style="bold",width=25); tbl.add_column("Params",style="dim_text",overflow="fold",max_width=40); tbl.add_column("Status",width=12)
    for act in activities:
        ts_str = act.get('timestamp',''); ts = datetime.datetime.fromisoformat(ts_str.replace("Z","+00:00")).strftime('%y-%m-%d %H:%M:%S') if ts_str else 'N/A'
        stat=act.get('status','?'); scolor="green" if stat=="success" else "yellow" if stat in ["partial_success","cancelled","initiated","plan_proposed", "user_cancelled_organization", "python_plan_generated"] else "red"
        pdict=act.get('parameters',{}); pstr=", ".join([f"[highlight]{k}[/highlight]:'{str(v)[:20]}{'...' if len(str(v))>20 else ''}'" for k,v in pdict.items()]) or "N/A"
        tbl.add_row(ts,act.get('action','N/A'),Text.from_markup(pstr),f"[{scolor}]{stat}[/{scolor}]")
    console.print(tbl); log_action("show_activity_log",{"req_c":count_param,"disp_c":len(activities)},"success")

def handle_redo_activity(connector: OllamaConnector, parameters: dict):
    act_id = parameters.get("activity_identifier")
    if not act_id: print_warning("No activity ID for redo."); log_action("redo_activity", parameters, "failure", "No activity ID"); return
    
    act_to_redo = get_activity_by_partial_id_or_index(act_id, console) # console from cli_ui
    if not act_to_redo: return

    action_perform = act_to_redo.get("action"); params_use = act_to_redo.get("parameters",{})
    print_panel_message("Confirm Redo",f"Action:[highlight]{action_perform}[/highlight]\nParams:[dim_text]{json.dumps(params_use,indent=1)}[/dim_text]","warning",ICONS["redo"])
    
    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Confirm?"),default=True, console=console):
        console.print(f"{ICONS['execute']} Redoing: [highlight]{action_perform}[/highlight]")
        log_action("redo_activity",{**parameters,"orig_action":action_perform,"orig_params":params_use},"initiated")
        
        current_session_ctx = session_manager.get_session_context()
        reproc_action, reproc_params, _ = nlu_processor.process_nlu_result(
            {"action":action_perform,"parameters":params_use},
            f"Redoing command: {action_perform}", # Synthetic user input for processing
            current_session_ctx, # Pass current session context
            connector
        )

        re_handler = _ACTION_HANDLERS_MAP.get(reproc_action) # Use internal map

        if re_handler:
            if reproc_action == "user_cancelled_organization":
                print_info(f"Organization redo involving '{action_perform}' was pre-cancelled during parameter processing.")
                # Log already handled by process_nlu_result if it returns this action
            elif reproc_action == action_perform: # Action remained the same after re-processing
                try:
                    if reproc_action in ["summarize_file","ask_question_about_file","search_files","propose_and_execute_organization","general_chat","redo_activity"]:
                        re_handler(connector,reproc_params)
                    else:
                        re_handler(reproc_params)
                except Exception as e:
                    print_error(f"Error redoing '{reproc_action}': {e}","Redo Error")
                    console.print_exception(show_locals=False, max_frames=2) # Use cli_ui.console
            else: # Action changed during re-processing (e.g. bad path, prompted for new)
                print_error(f"Redo action '{action_perform}' changed to '{reproc_action}' during re-processing. Aborted to prevent unexpected behavior.","Redo Error")
        elif reproc_action == "unknown" and "error" in reproc_params: # nlu_processor returned unknown
             print_error(f"Could not re-process parameters for redo of '{action_perform}': {reproc_params['error']}", "Redo Error")
        else:
            print_error(f"Action '{reproc_action}' not directly redoable or handler missing after re-processing.","Redo Error")
    else:
        print_info("Redo cancelled."); log_action("redo_activity",parameters,"cancelled")


def handle_propose_and_execute_organization(connector: OllamaConnector, parameters: dict):
    abs_base_analysis_path = parameters.get("target_path_or_context")
    organization_goal = parameters.get("organization_goal")
    python_generated_plan_used = False

    if not abs_base_analysis_path or not os.path.isdir(abs_base_analysis_path):
        print_error(f"Org Error: Target '[filepath]{abs_base_analysis_path}[/filepath]' invalid or not a directory.")
        log_action("propose_and_execute_organization", parameters, "failure", "Invalid target for org")
        return

    src_desc=f"folder '[filepath]{os.path.basename(abs_base_analysis_path)}[/filepath]'"
    goal_display_text = organization_goal or "general organization"
    console.print(Padding(f"{ICONS['thinking']} Analyzing {src_desc} for organization plan...\nGoal: '[highlight]{goal_display_text}[/highlight]'",(1,0)))
    
    items_in_folder=fu_list_folder_contents(abs_base_analysis_path,console) or []
    if not items_in_folder:
        print_info(f"No items in {src_desc} to organize.","Org Status")
        log_action("propose_and_execute_organization", parameters, "failure", "No items for org")
        return

    item_summary_list_for_llm = []
    for item_data in items_in_folder[:50]: # Limit for LLM context
        relative_item_path = os.path.relpath(item_data['path'], abs_base_analysis_path)
        item_summary_list_for_llm.append(f"- \"{relative_item_path}\" (type: {item_data['type']})")
    
    item_summary_llm_str = "\n".join(item_summary_list_for_llm)
    if len(items_in_folder) > 50:
        item_summary_llm_str += f"\n...and {len(items_in_folder)-50} more items."

    spinner_text=f"{ICONS['thinking']} [spinner_style]LLM generating organization plan...[/spinner_style]"
    with Live(Spinner("bouncingBar",text=spinner_text),console=console,transient=True):
        plan_json_actions = connector.generate_organization_plan_llm(item_summary_llm_str, organization_goal, abs_base_analysis_path)

    if plan_json_actions is None:
        print_error("LLM failed to generate a plan or the plan was malformed. Please try rephrasing your goal or check Ollama logs.", "Plan Generation Failed")
        log_action("propose_and_execute_organization", parameters, "failure", "LLM plan generation failed or malformed")
        return
    
    if not isinstance(plan_json_actions, list):
        print_error(f"LLM plan was not a list as expected. Received type: {type(plan_json_actions)}. Cannot proceed.", "Plan Structure Error")
        log_action("propose_and_execute_organization", parameters, "failure", f"LLM plan not a list: {type(plan_json_actions)}")
        return

    normalized_goal_for_fallback = (organization_goal or "").lower().strip()
    name_based_heuristic_goals = ["by name", "the names", "by first letter", "alphabetical", "alphabetically by name"]
    if not plan_json_actions and normalized_goal_for_fallback in name_based_heuristic_goals:
        python_generated_plan_used = True
        print_panel_message("AI Plan Fallback", 
                            f"LLM did not propose a specific plan for goal '[highlight]{goal_display_text}[/highlight]'.\nAttempting standard first-letter organization heuristic.", 
                            "info", ICONS["info"])
        
        generated_heuristic_plan = []
        created_folders_for_heuristic_plan = set()
        for item_data in items_in_folder:
            if item_data['type'] == 'file':
                item_name = item_data['name']
                first_char = item_name[0].upper() if item_name else "_"
                subfolder_name = "0-9_files" if first_char.isdigit() else f"{first_char}_files" if first_char.isalpha() else "Symbols_files"
                abs_subfolder_path = os.path.join(abs_base_analysis_path, subfolder_name)
                
                if abs_subfolder_path not in created_folders_for_heuristic_plan:
                    generated_heuristic_plan.append({"action_type": "CREATE_FOLDER", "path": abs_subfolder_path})
                    created_folders_for_heuristic_plan.add(abs_subfolder_path)
                
                source_path = item_data['path']
                destination_path = os.path.join(abs_subfolder_path, item_name)
                if source_path != destination_path :
                    generated_heuristic_plan.append({"action_type": "MOVE_ITEM", "source": source_path, "destination": destination_path})
        plan_json_actions = generated_heuristic_plan
        log_action("propose_and_execute_organization", {**parameters, "fallback_heuristic_used": True}, "python_plan_generated", f"Python generated {len(plan_json_actions)} actions for '{normalized_goal_for_fallback}'")

    if not plan_json_actions:
        empty_plan_message = (f"The AI analyzed the folder for the goal '[highlight]{goal_display_text}[/highlight]' "
                              f"but did not propose any specific actions.\nThis might be because:\n"
                              f"  - The items are already organized according to this goal.\n"
                              f"  - The goal was too ambiguous for the AI/heuristic to form a clear plan.\n"
                              f"  - There were too few items to apply the chosen organization strategy effectively.\n"
                              f"  - The AI determined no changes were beneficial based on its 'be conservative' rule.")
        print_info(empty_plan_message, "No Actions Proposed")
        log_action("propose_and_execute_organization", parameters, "success", "No actions proposed (LLM or heuristic)")
        return

    plan_title = f"{ICONS['plan']} Proposed Organization Plan" + (" (Standard Heuristic)" if python_generated_plan_used else "")
    tbl=Table(title=plan_title, box=ROUNDED, header_style="table.header", show_lines=True)
    tbl.add_column("Icon",width=4,justify="center"); tbl.add_column("Step",justify="right",width=5); tbl.add_column("Action",width=15); tbl.add_column("Details",overflow="fold"); tbl.add_column("Status", width=15)
    
    valid_actions_to_execute=[]; invalid_actions_found=False
    for i, action_data in enumerate(plan_json_actions):
        action_type = action_data.get("action_type")
        details_str = ""; is_action_valid = True; action_status_msg="[green]Valid[/green]"; icon="❓"

        if not isinstance(action_data, dict):
            details_str=f"[danger]Invalid action format (not a dict)[/danger]"; is_action_valid=False; action_status_msg="[danger]Invalid Format[/danger]"
        elif action_type == "CREATE_FOLDER":
            icon=ICONS["create_folder"]
            folder_path = action_data.get("path")
            if not (folder_path and isinstance(folder_path, str) and os.path.isabs(folder_path)):
                details_str=f"Path: [danger]{folder_path or 'MISSING'}[/] (Must be absolute)"; is_action_valid=False; action_status_msg="[danger]Invalid Path[/danger]"
            elif not is_path_within_base(folder_path, abs_base_analysis_path): # fs_utils.is_path_within_base
                details_str=f"Path: [filepath]{folder_path}[/] [danger](Outside target folder scope)[/danger]"; is_action_valid=False; action_status_msg="[danger]Out of Scope[/danger]"
            else: details_str=f"Path: [filepath]{folder_path}[/filepath]"
        elif action_type == "MOVE_ITEM":
            icon=ICONS["move"]
            source_path = action_data.get("source")
            destination_path = action_data.get("destination")
            if not (source_path and isinstance(source_path, str) and os.path.isabs(source_path) and \
                    destination_path and isinstance(destination_path, str) and os.path.isabs(destination_path)):
                details_str=f"Source: [danger]{source_path or 'MISSING'}[/]\nDest:   [danger]{destination_path or 'MISSING'}[/] (Must be absolute)"; is_action_valid=False; action_status_msg="[danger]Invalid Paths[/danger]"
            elif source_path == destination_path:
                details_str=f"From: [filepath]{source_path}[/filepath]\nTo:   [filepath]{destination_path}[/] ([dim_text]Item already in place[/dim_text])"; is_action_valid=False; action_status_msg="[dim_text]No Change[/dim_text]"
            elif not is_path_within_base(source_path, abs_base_analysis_path) or \
                 not is_path_within_base(destination_path, abs_base_analysis_path):
                s_scope = "[green]OK[/green]" if is_path_within_base(source_path, abs_base_analysis_path) else "[danger]OUT[/danger]"
                d_scope = "[green]OK[/green]" if is_path_within_base(destination_path, abs_base_analysis_path) else "[danger]OUT[/danger]"
                details_str=f"Source ({s_scope}): [filepath]{source_path}[/]\nDest   ({d_scope}): [filepath]{destination_path}[/] [danger](Path(s) out of scope)[/danger]"; is_action_valid=False; action_status_msg="[danger]Out of Scope[/danger]"
            elif not os.path.exists(source_path):
                 details_str=f"Source: [filepath]{source_path}[/] [warning](Does not exist)[/warning]"; is_action_valid=False; action_status_msg="[warning]Src Missing[/warning]"
            else: details_str=f"From: [filepath]{source_path}[/filepath]\nTo:   [filepath]{destination_path}[/filepath]"
        else:
            details_str=f"[danger]Unknown action type: {action_type}[/danger]"; is_action_valid=False; action_status_msg="[danger]Unknown Act[/danger]"
        
        tbl.add_row(icon,str(i+1),action_type if is_action_valid else f"[strike]{action_type}[/strike]",Text.from_markup(details_str), Text.from_markup(action_status_msg))
        if is_action_valid: valid_actions_to_execute.append(action_data)
        else:
            if action_status_msg not in ["[dim_text]No Change[/dim_text]"]: invalid_actions_found=True
    console.print(tbl)

    if invalid_actions_found: print_warning("The proposed plan contains invalid or unsafe actions (struck out and marked above). Only valid actions will be considered for execution.","Plan Validation Issues")
    if not valid_actions_to_execute:
        print_info("No valid actions remaining in the plan after validation. Nothing to execute.","Plan Empty Post-Validation")
        log_action("propose_and_execute_organization", {**parameters,"initial_plan_c":len(plan_json_actions),"valid_c":0, "python_generated": python_generated_plan_used}, "failure", "No valid actions post-validation")
        return

    log_action("propose_and_execute_organization",{**parameters,"initial_plan_c":len(plan_json_actions),"valid_c":len(valid_actions_to_execute), "python_generated": python_generated_plan_used},"plan_proposed")
    
    if Confirm.ask(Text.from_markup(f"{ICONS['confirm']} Execute the {len(valid_actions_to_execute)} valid action(s) listed above?"),default=False, console=console):
        console.print(Padding(f"{ICONS['execute']} [bold]Executing validated plan...[/bold]",(1,0)))
        success_count, fail_count = 0, 0
        with Progress(console=console,expand=True) as prog_bar:
            exec_task = prog_bar.add_task(f"{ICONS['execute']} [spinner_style]Processing...[/spinner_style]",total=len(valid_actions_to_execute))
            for idx, exec_action_data in enumerate(valid_actions_to_execute):
                action_type_exec = exec_action_data["action_type"]
                prog_bar.update(exec_task,description=f"{ICONS['execute']} [spinner_style]Step {idx+1}: {action_type_exec}...[/spinner_style]")
                op_successful, log_status, message_detail = False, "failure", ""
                if action_type_exec=="CREATE_FOLDER":
                    path_to_create = exec_action_data["path"]
                    try:
                        if os.path.exists(path_to_create) and os.path.isdir(path_to_create):
                            message_detail=f"  {ICONS['info']} [dim_text]Folder '{os.path.basename(path_to_create)}' already exists. Skipped.[/dim_text]"; op_successful, log_status = True, "skipped"
                        else:
                            os.makedirs(path_to_create,exist_ok=True)
                            message_detail=f"  {ICONS['success']} [green]Created folder:[/] [filepath]{os.path.basename(path_to_create)}[/filepath]"; op_successful, log_status = True, "success"
                    except Exception as e: message_detail=f"  {ICONS['error']} [danger]FAIL CREATE FOLDER '{os.path.basename(path_to_create)}': {e}[/danger]"
                elif action_type_exec=="MOVE_ITEM":
                    source_item_path = exec_action_data["source"]
                    destination_item_path = exec_action_data["destination"]
                    if not os.path.exists(source_item_path):
                        message_detail=f"  {ICONS['warning']} [warning]Source '{os.path.basename(source_item_path)}' disappeared before move. Skipped.[/warning]"; log_status="skipped"
                    elif fu_move_item(source_item_path,destination_item_path,console): # Use fu_move_item
                        dest_display_path = os.path.relpath(destination_item_path, os.path.dirname(source_item_path)) if destination_item_path.startswith(os.path.dirname(source_item_path)) else os.path.basename(destination_item_path)
                        message_detail=f"  {ICONS['success']} [green]Moved:[/] [filepath]{os.path.basename(source_item_path)}[/filepath] -> [filepath]{dest_display_path}[/filepath]"; op_successful, log_status = True, "success"
                    else: message_detail=f"  {ICONS['error']} [danger]FAIL MOVE '{os.path.basename(source_item_path)}' (see details above).[/danger]"
                
                console.print(Text.from_markup(message_detail))
                if op_successful: success_count +=1
                else: fail_count +=1
                log_action(f"exec_org_{action_type_exec.lower()}",{**exec_action_data,"base_path":abs_base_analysis_path},log_status,message_detail.split(":",1)[-1].strip() if ":" in message_detail else message_detail.strip())
                prog_bar.update(exec_task,advance=1)
            prog_bar.update(exec_task,description=f"{ICONS['success']} [green]Execution complete.[/green]")
        
        print_success(f"Organization plan execution finished. Successful: {success_count}, Failed/Skipped: {fail_count}","Organization Summary")
        session_manager.update_session_context("last_referenced_file_path",None)
        session_manager.update_session_context("last_folder_listed_path",None)
        session_manager.update_session_context("last_search_results",[])
        log_action("execute_organization_plan",{**parameters,"executed_c":len(valid_actions_to_execute),"ok_c":success_count,"fail_c":fail_count, "python_generated": python_generated_plan_used},"completed")
    else:
        print_info("Organization plan execution cancelled by user.");
        log_action("execute_organization_plan",{**parameters,"valid_c":len(valid_actions_to_execute), "python_generated": python_generated_plan_used},"cancelled")


# Populate the map
_ACTION_HANDLERS_MAP.update({
    "summarize_file": handle_summarize_file,
    "ask_question_about_file": handle_ask_question,
    "list_folder_contents": handle_list_folder,
    "move_item": handle_move_item,
    "search_files": handle_search_files,
    "propose_and_execute_organization": handle_propose_and_execute_organization,
    "show_activity_log": handle_show_activity_log,
    "redo_activity": handle_redo_activity,
    "general_chat": handle_general_chat
})

def get_action_handler_map():
    return _ACTION_HANDLERS_MAP
