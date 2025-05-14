import os
import time

from ollama_connector import OllamaConnector
# config.py is at the root, so cli_ui.py (in python/) will handle its import via sys.path manipulation

# --- Corrected Module Imports ---
# Assuming main_cli.py is at the project root, and these modules are in a 'python' subdirectory.
from python import cli_constants
from python import cli_ui
from python import session_manager
from python import direct_parsers
from python import nlu_processor 
from python import action_handlers as action_handlers_module
from python import path_resolver 

# activity_logger.py is at the project root, same level as main_cli.py
import activity_logger
# --- End of Corrected Module Imports ---

from rich.prompt import Prompt
from rich.text import Text
from rich.rule import Rule
from rich.live import Live 
from rich.spinner import Spinner 


def main():
    session_manager.load_session_context() # Load/initialize session, including CWD
    connector = OllamaConnector()

    if not cli_ui.print_startup_message_ui(connector):
        session_manager.save_session_context()
        return

    action_handlers_map = action_handlers_module.get_action_handler_map()
    MAX_CLARIFICATION_ATTEMPTS = 2

    try:
        while True:
            cli_ui.console.print(Rule(style="separator_style"))
            current_display_cwd = os.getcwd()
            home_dir = os.path.expanduser("~")
            if current_display_cwd.startswith(home_dir):
                current_display_cwd = "~" + current_display_cwd[len(home_dir):]

            prompt_text = Text.from_markup(f"{cli_constants.ICONS['prompt']} [prompt_path]({current_display_cwd})[/prompt_path] [prompt]You[/prompt][prompt_arrow]> [/prompt_arrow]")
            user_input_original = Prompt.ask(prompt_text, default="", console=cli_ui.console).strip()

            if not user_input_original:
                continue
            if user_input_original.lower() in ['quit','exit','bye','q']:
                cli_ui.console.print(f"{cli_constants.ICONS['app_icon']} [bold app_logo_style]Exiting...[/bold app_logo_style]")
                break
            if user_input_original.lower() == 'help':
                cli_ui.display_help()
                session_manager.add_to_command_history("help", {}, "user_typed")
                # Use the correct function signature for activity_logger.log_action
                activity_logger.log_action("help", {}, "success", "User viewed help.", chain_of_thought="User requested help command.")
                continue

            parsed_llm_nlu_result = None
            action_name = None
            parameters = {}
            chain_of_thought = ""
            nlu_method = "unknown_initial"
            
            current_session_ctx = session_manager.get_session_context()

            direct_parser_output = direct_parsers.try_all_direct_parsers(user_input_original, current_session_ctx)
            
            if direct_parser_output:
                action_name = direct_parser_output.get("action")
                parameters = direct_parser_output.get("parameters", {})
                nlu_method = direct_parser_output.get("nlu_method", "direct_parsed_unknown")
                chain_of_thought = f"Directly parsed as '{action_name}' by '{nlu_method}'."
                cli_ui.display_chain_of_thought(chain_of_thought)
            else:
                nlu_method = "llm_fallback_initial" 
                current_input_for_llm = user_input_original

                for attempt in range(MAX_CLARIFICATION_ATTEMPTS):
                    spinner_text = f"{cli_constants.ICONS['thinking']} [spinner_style]Understanding: '{current_input_for_llm[:35]}...'[/spinner_style]"
                    with Live(Spinner("dots",text=spinner_text),console=cli_ui.console,transient=True, refresh_per_second=10):
                        current_session_ctx_for_llm = session_manager.get_session_context()
                        parsed_llm_nlu_result = connector.get_intent_and_entities(current_input_for_llm, current_session_ctx_for_llm)
                    
                    action_name = parsed_llm_nlu_result.get("action")
                    parameters = parsed_llm_nlu_result.get("parameters", {})
                    chain_of_thought = parsed_llm_nlu_result.get("chain_of_thought", "No reasoning provided by LLM.")
                    clarification_needed = parsed_llm_nlu_result.get("clarification_needed", False)
                    suggested_question = parsed_llm_nlu_result.get("suggested_question", "")
                    nlu_method = parsed_llm_nlu_result.get("nlu_method", "llm_fallback_processed")

                    if chain_of_thought:
                        cli_ui.display_chain_of_thought(chain_of_thought)

                    if action_name == "unknown" or action_name is None or action_name.startswith("error_"):
                        error_reason = parameters.get("error_reason", parsed_llm_nlu_result.get("chain_of_thought", "LLM could not determine action."))
                        cli_ui.print_error(f"LLM NLU Error: {error_reason}", "AI Understanding Error")
                        activity_logger.log_action(
                            "llm_nlu_direct_error", 
                            {"input": current_input_for_llm, "llm_output": parsed_llm_nlu_result}, 
                            "failure", 
                            error_reason, 
                            chain_of_thought
                        )
                        if not clarification_needed:
                             action_name = "unknown"
                             break

                    if clarification_needed:
                        cli_ui.display_warning("I need a bit more information to proceed.")
                        clarifying_answer = cli_ui.ask_question_prompt(suggested_question or "Could you please clarify?")
                        
                        if not clarifying_answer:
                            cli_ui.display_error("No clarification provided. Please try your command again.")
                            action_name = "user_cancelled_clarification"
                            parameters = {"original_input": user_input_original}
                            chain_of_thought += "\nUser cancelled clarification."
                            break 
                        
                        current_input_for_llm = f"Original request: '{user_input_original}'. My previous question: '{suggested_question}'. User's clarification: '{clarifying_answer}'"
                        nlu_method = "llm_clarifying"
                        if attempt < MAX_CLARIFICATION_ATTEMPTS - 1:
                            cli_ui.display_info("Thanks! Let me try to understand that again with your clarification...")
                            continue 
                        else:
                            cli_ui.display_error("Sorry, I'm still having trouble understanding after clarification. Please try rephrasing your original request.")
                            action_name = "clarification_failed_max_attempts"
                            parameters = {"original_input": user_input_original, "last_clarification": clarifying_answer}
                            chain_of_thought += "\nClarification failed after max attempts."
                            break
                    else: 
                        break 
            
            if action_name and action_name not in ["unknown", "user_cancelled_clarification", "clarification_failed_max_attempts"] and not action_name.startswith("error_"):
                action_name, parameters, nlu_processing_notes = nlu_processor.process_nlu_result(
                    {"action": action_name, "parameters": parameters, "nlu_method": nlu_method},
                    user_input_original, 
                    current_session_ctx, 
                    connector,
                    cli_ui 
                )
                if nlu_processing_notes:
                    chain_of_thought += f"\nNLU Processing Notes: {nlu_processing_notes}"
                    nlu_method += f"; {nlu_processing_notes.split(':')[0].replace(' ', '_').lower()}"
            
            log_status = "pending_execution"
            if not action_name or action_name in ["unknown", "user_cancelled_clarification", "clarification_failed_max_attempts"] or action_name.startswith("error_") or action_name == "user_cancelled_organization":
                log_status = "nlu_failed_or_cancelled"
            
            activity_logger.log_action(
                action_name if action_name else "unknown_nlu_outcome", 
                parameters, 
                log_status, 
                f"NLU Method: {nlu_method}", 
                chain_of_thought
            )
            session_manager.add_to_command_history(action_name if action_name else "unknown_nlu_outcome", parameters, nlu_method)

            if not action_name or action_name in ["unknown", "user_cancelled_clarification", "clarification_failed_max_attempts"]:
                session_manager.update_session_context("last_command_status", "nlu_failure")
                continue 
            
            if action_name == "user_cancelled_organization":
                cli_ui.print_info("Organization process cancelled by user during path confirmation.")
                session_manager.update_session_context("last_command_status", "user_cancelled")
                # update_last_activity_status should be called by nlu_processor if it sets this state
                activity_logger.update_last_activity_status("user_cancelled", "Organization cancelled during parameter finalization.")
                continue

            action_name_before_index_res = action_name
            action_name, index_resolved_flag = nlu_processor.resolve_indexed_reference(
                 user_input_original.lower(), action_name, parameters, current_session_ctx, cli_ui # Pass cli_ui for its console
            )
            if index_resolved_flag:
                note = f"Indexed reference resolved. Original action: {action_name_before_index_res}, New/Confirmed: {action_name}."
                chain_of_thought += f"\n{note}" # Append to existing CoT
                nlu_method += "; IdxRefResolved"
                activity_logger.update_last_activity_status(
                    "pending_execution_idx_resolved", 
                    f"NLU Method: {nlu_method}. {note}",
                    result_data={"updated_action": action_name, "updated_parameters": parameters}
                )
                session_manager.add_to_command_history(action_name, parameters, nlu_method)

            handler = action_handlers_map.get(action_name)
            if handler:
                try:
                    if action_name in ["summarize_file", "ask_question_about_file", "search_files",
                                       "propose_and_execute_organization", "general_chat", "redo_activity"]:
                        # These handlers now expect (connector, parameters, cli_ui, session_manager, activity_logger)
                        # We need to ensure all action handlers are updated to accept these, or adapt the call here
                        handler(connector, parameters) # Original call, may need to pass more context
                    else:
                        # These handlers now expect (parameters, cli_ui, session_manager, activity_logger)
                        handler(parameters) # Original call, may need to pass more context
                    
                    # It's better if handlers call update_last_activity_status themselves for fine-grained outcome.
                    # If not, a generic update can be done here.
                    # Example: activity_logger.update_last_activity_status("handler_executed_successfully")
                    session_manager.update_session_context("last_command_status", "handler_executed")
                    session_manager.update_session_context("last_action", action_name)
                    session_manager.update_session_context("last_parameters", parameters)

                except Exception as e:
                    error_msg = f"Critical error during '{action_name}' execution: {str(e)}"
                    cli_ui.print_error(error_msg, "Action Execution Error")
                    cli_ui.console.print_exception(show_locals=True, max_frames=3)
                    activity_logger.update_last_activity_status("execution_exception", error_msg)
                    session_manager.update_session_context("last_command_status", "execution_exception")
            
            elif action_name == "unknown": 
                err_detail = parameters.get('error_reason', 'Unrecognized command or NLU failure.')
                cli_ui.print_warning(f"Cannot handle: '{parameters.get('original_request',user_input_original)}'.\nDetails: {err_detail}\nTry 'help'.","Unknown Command")
                session_manager.update_session_context("last_command_status", "unknown_command_at_dispatch")
            else:
                cli_ui.print_warning(f"Action '[highlight]{action_name}[/highlight]' is recognized but not implemented.","Not Implemented")
                activity_logger.update_last_activity_status("not_implemented", f"Handler missing for action: {action_name}")
                session_manager.update_session_context("last_command_status", "not_implemented")

    except KeyboardInterrupt:
        cli_ui.console.print(f"\n{cli_constants.ICONS['app_icon']} [bold app_logo_style]Exiting... (Ctrl+C)[/bold app_logo_style]")
    except Exception as e:
        cli_ui.print_error(f"A critical error occurred in the main application loop: {str(e)}","Critical Application Error")
        cli_ui.console.print_exception(show_locals=True) 
    finally:
        session_manager.save_session_context()

if __name__ == '__main__':
    main()