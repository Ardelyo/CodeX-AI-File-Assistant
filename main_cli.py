
import os
import time

from ollama_connector import OllamaConnector

from python import cli_constants
from python import cli_ui
from python import session_manager
from python import direct_parsers
from python import nlu_processor 
from python import action_handlers as action_handlers_module
from python import path_resolver 

import activity_logger

from rich.prompt import Prompt
from rich.text import Text
from rich.rule import Rule
from rich.live import Live 
from rich.spinner import Spinner 


def main():
    session_manager.load_session_context()
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

            prompt_icon = cli_constants.ICONS.get('prompt', '>') 
            prompt_text = Text.from_markup(f"{prompt_icon} [prompt_path]({current_display_cwd})[/prompt_path] [prompt]You[/prompt][prompt_arrow]> [/prompt_arrow]")
            user_input_original = Prompt.ask(prompt_text, default="", console=cli_ui.console).strip()

            if not user_input_original:
                continue
            if user_input_original.lower() in ['quit','exit','bye','q']:
                cli_ui.console.print(f"{cli_constants.ICONS.get('app_icon', '🤖')} [bold app_logo_style]Exiting...[/bold app_logo_style]")
                break
            if user_input_original.lower() == 'help':
                cli_ui.display_help()
                session_manager.add_to_command_history("help", {}, "user_typed")
                activity_logger.log_action("help", {}, "success", "User viewed help.", chain_of_thought="User requested help command.")
                continue
            
            session_manager.update_session_context("last_action_result", None) # Clear previous action result for a new command

            parsed_nlu_result_from_source = None
            overall_chain_of_thought = ""
            nlu_method_for_log = "unknown_initial"
            actions_to_execute = []
            
            current_session_ctx = session_manager.get_session_context()
            direct_parser_output = direct_parsers.try_all_direct_parsers(user_input_original, current_session_ctx)
            
            if direct_parser_output:
                # Direct parsers currently return a single action, wrap it in the new structure
                actions_to_execute = [{
                    "action_name": direct_parser_output.get("action"),
                    "parameters": direct_parser_output.get("parameters", {}),
                    "step_description": "Directly parsed command."
                }]
                nlu_method_for_log = direct_parser_output.get("nlu_method", "direct_parsed_unknown")
                overall_chain_of_thought = f"Directly parsed as '{actions_to_execute[0]['action_name']}' by '{nlu_method_for_log}'."
                cli_ui.display_chain_of_thought(overall_chain_of_thought)
            else:
                nlu_method_for_log = "llm_fallback_initial" 
                current_input_for_llm = user_input_original

                for attempt in range(MAX_CLARIFICATION_ATTEMPTS + 1): # +1 to allow one attempt without clarification
                    spinner_icon = cli_constants.ICONS.get('thinking', '🤔')
                    spinner_text = f"{spinner_icon} [spinner_style]Understanding: '{current_input_for_llm[:35]}...'[/spinner_style]"
                    
                    # Always get fresh session context for LLM, especially if prior actions in a chain modified it
                    current_session_ctx_for_llm = session_manager.get_session_context()
                    
                    with Live(Spinner("dots",text=spinner_text),console=cli_ui.console,transient=True, refresh_per_second=10):
                        parsed_nlu_result_from_source = connector.get_intent_and_entities(current_input_for_llm, current_session_ctx_for_llm)
                    
                    actions_to_execute = parsed_nlu_result_from_source.get("actions", [])
                    overall_chain_of_thought = parsed_nlu_result_from_source.get("chain_of_thought", "No reasoning provided by LLM.")
                    clarification_needed = parsed_nlu_result_from_source.get("clarification_needed", False)
                    suggested_question = parsed_nlu_result_from_source.get("suggested_question", "")
                    nlu_method_for_log = parsed_nlu_result_from_source.get("nlu_method", "llm_multi_action_nlu_processed")

                    if overall_chain_of_thought:
                        cli_ui.display_chain_of_thought(overall_chain_of_thought)

                    # Check if the primary action (first one, or the only one if 'unknown') indicates an NLU error
                    primary_action_name_for_error_check = actions_to_execute[0].get("action_name") if actions_to_execute else "unknown"
                    primary_params_for_error_check = actions_to_execute[0].get("parameters", {}) if actions_to_execute else {}

                    if primary_action_name_for_error_check == "unknown" or primary_action_name_for_error_check is None or primary_action_name_for_error_check.startswith("error_"):
                        error_reason = primary_params_for_error_check.get("error_reason", overall_chain_of_thought)
                        cli_ui.print_error(f"LLM NLU Error: {error_reason}", "AI Understanding Error")
                        activity_logger.log_action(
                            f"llm_nlu_error_{primary_action_name_for_error_check}", 
                            {"input": current_input_for_llm, "llm_output": parsed_nlu_result_from_source}, 
                            "failure", 
                            error_reason, 
                            overall_chain_of_thought
                        )
                        if not clarification_needed: # If error and no clarification, break from clarification loop
                            actions_to_execute = [] # Clear actions as it's an error state
                            break 
                    
                    if not clarification_needed or attempt >= MAX_CLARIFICATION_ATTEMPTS:
                        if clarification_needed and attempt >= MAX_CLARIFICATION_ATTEMPTS:
                             cli_ui.display_error("Sorry, I'm still having trouble understanding after clarification. Please try rephrasing your original request.")
                             activity_logger.log_action(
                                "clarification_failed_max_attempts",
                                {"original_input": user_input_original, "last_clarification_attempt_input": current_input_for_llm},
                                "failure",
                                "Max clarification attempts reached.",
                                overall_chain_of_thought
                             )
                             actions_to_execute = [] # Clear actions
                        break # Exit clarification loop

                    # If clarification is needed and we have attempts left
                    cli_ui.display_warning("I need a bit more information to proceed.")
                    clarifying_answer = cli_ui.ask_question_prompt(suggested_question or "Could you please clarify?")
                    
                    if not clarifying_answer:
                        cli_ui.display_error("No clarification provided. Please try your command again.")
                        activity_logger.log_action(
                            "user_cancelled_clarification",
                            {"original_input": user_input_original, "suggested_question": suggested_question},
                            "failure",
                            "User did not provide clarification.",
                            overall_chain_of_thought
                        )
                        actions_to_execute = [] # Clear actions
                        break 
                    
                    current_input_for_llm = f"Original request: '{user_input_original}'. My previous question to you: '{suggested_question}'. Your clarifying answer: '{clarifying_answer}'"
                    nlu_method_for_log = "llm_clarifying" # Update log method for this iteration
                    cli_ui.display_info("Thanks! Let me try to understand that again with your clarification...")
            
            if not actions_to_execute:
                session_manager.update_session_context("last_command_status", "nlu_failed_or_empty")
                session_manager.add_to_command_history("unknown_nlu_outcome", {"original_input": user_input_original}, nlu_method_for_log)
                # Error messages are printed inside the loop or by LLM connector if it returns an error structure
                continue

            # --- Sequential Action Execution ---
            final_command_status = "all_steps_completed" 
            processed_successfully_at_least_one_action = False

            for i, action_step in enumerate(actions_to_execute):
                current_action_name = action_step.get("action_name")
                current_parameters = action_step.get("parameters", {})
                step_description = action_step.get("step_description", "No step description.")

                cli_ui.console.print(f"\n[step_style]Step {i+1}/{len(actions_to_execute)}: {current_action_name}[/step_style] - {step_description}")

                # Get fresh context before processing each step, as previous steps might have changed it (e.g. CWD, last_action_result)
                current_session_ctx_for_processing = session_manager.get_session_context()
                
                processed_action_name, processed_parameters, nlu_processing_notes = nlu_processor.process_nlu_result(
                    {"action": current_action_name, "parameters": current_parameters, "nlu_method": nlu_method_for_log}, # Pass nlu_method from overall NLU
                    user_input_original, 
                    current_session_ctx_for_processing, 
                    connector,
                    cli_ui 
                )
                
                current_chain_of_thought_for_log = f"{overall_chain_of_thought}\nStep {i+1} ({processed_action_name}): {step_description}"
                if nlu_processing_notes:
                    current_chain_of_thought_for_log += f"\nNLU Processing Notes: {nlu_processing_notes}"
                
                step_log_status = "pending_execution"
                non_execution_actions_step = [ # Errors/cancellations from nlu_processor for this step
                    "user_cancelled_path_prompt", "path_validation_failed", 
                    "parameter_missing_no_ui", "user_cancelled_parameter_prompt"
                ]
                if not processed_action_name or processed_action_name == "unknown" or processed_action_name.startswith("error_") or processed_action_name in non_execution_actions_step:
                    step_log_status = "step_nlu_failed_or_cancelled"
                    cli_ui.print_error(f"Failed to process step {i+1} ('{current_action_name}'). Reason: {nlu_processing_notes or processed_action_name}", "Step Processing Error")
                    final_command_status = "chain_aborted_step_failure"
                    # Log this failed step attempt
                    activity_logger.log_action(
                        processed_action_name if processed_action_name else f"unknown_step_{i+1}",
                        processed_parameters,
                        step_log_status,
                        f"NLU Method: {nlu_method_for_log}. {nlu_processing_notes}",
                        current_chain_of_thought_for_log
                    )
                    session_manager.add_to_command_history(
                        f"failed_step: {processed_action_name or current_action_name}", 
                        processed_parameters, 
                        nlu_method_for_log
                    )
                    break # Abort the chain of actions

                # Log before execution
                activity_id = activity_logger.log_action(
                    processed_action_name, 
                    processed_parameters, 
                    step_log_status, 
                    f"NLU Method: {nlu_method_for_log}. Step {i+1}/{len(actions_to_execute)}", 
                    current_chain_of_thought_for_log,
                    is_multi_step_parent=(i == 0 and len(actions_to_execute) > 1), # Mark first step of a chain
                    parent_activity_id=None # For sub-steps of a single action, not used here
                )
                # If this is not the first step, it's part of a chain implicitly
                if i > 0: activity_logger.set_current_activity_chained()


                # Resolve indexed references (if any, typically for first action or if context is listable)
                # This might be less relevant if LLM directly uses __PREVIOUS_ACTION_RESULT_FIRST_PATH__
                # For now, keep it, but it might need adjustment for multi-step context.
                # It primarily uses last_search_results which is a global context.
                action_name_before_index_res = processed_action_name
                processed_action_name, index_resolved_flag = nlu_processor.resolve_indexed_reference(
                     user_input_original.lower(), # This might need to be the sub-command part if LLM isolated it
                     processed_action_name, 
                     processed_parameters, 
                     current_session_ctx_for_processing, # Use the most current context
                     cli_ui
                )
                if index_resolved_flag:
                    note = f"Indexed reference resolved for step {i+1}. Original action: {action_name_before_index_res}, New/Confirmed: {processed_action_name}."
                    current_chain_of_thought_for_log += f"\n{note}"
                    nlu_method_for_log += "; IdxRefResolved" # Append to the overall method for this step's log
                    activity_logger.update_last_activity_status( # Updates the 'pending_execution' log for this step
                        "pending_execution_idx_resolved", 
                        f"NLU Method: {nlu_method_for_log}. {note}",
                        result_data={"updated_action": processed_action_name, "updated_parameters": processed_parameters}
                    )
                
                session_manager.add_to_command_history(processed_action_name, processed_parameters, nlu_method_for_log) # Add each processed step

                handler = action_handlers_map.get(processed_action_name)
                if handler:
                    try:
                        handler_result = None
                        if processed_action_name in ["summarize_file", "ask_question_about_file", "search_files",
                                           "propose_and_execute_organization", "general_chat", "redo_activity"]:
                            handler_result = handler(connector, processed_parameters) 
                        else:
                            handler_result = handler(processed_parameters) 
                        
                        activity_logger.update_last_activity_status("success", "Step executed successfully.", result_data=handler_result)
                        session_manager.update_session_context("last_command_status", f"step_{i+1}_success")
                        session_manager.update_session_context("last_action", processed_action_name)
                        session_manager.update_session_context("last_parameters", processed_parameters)
                        session_manager.update_session_context("last_action_result", handler_result) # CRITICAL for chaining
                        processed_successfully_at_least_one_action = True

                    except Exception as e:
                        error_msg = f"Critical error during step {i+1} ('{processed_action_name}') execution: {str(e)}"
                        cli_ui.print_error(error_msg, "Action Execution Error")
                        cli_ui.console.print_exception(show_locals=True, max_frames=1) # Keep concise for CLI
                        activity_logger.update_last_activity_status("execution_exception", error_msg, exception_details=str(e))
                        session_manager.update_session_context("last_command_status", f"step_{i+1}_exception")
                        final_command_status = "chain_aborted_step_exception"
                        break # Abort chain on exception
                else:
                    cli_ui.print_warning(f"Action '[highlight]{processed_action_name}[/highlight]' for step {i+1} is recognized but not implemented.","Not Implemented")
                    activity_logger.update_last_activity_status("not_implemented", f"Handler missing for action: {processed_action_name}")
                    session_manager.update_session_context("last_command_status", f"step_{i+1}_not_implemented")
                    final_command_status = "chain_aborted_step_not_implemented"
                    break # Abort chain if a step is not implemented
            
            # After loop:
            if final_command_status == "all_steps_completed" and not processed_successfully_at_least_one_action and len(actions_to_execute) > 0:
                # This case should ideally not happen if actions_to_execute had items, means loop didn't run or error before first success
                final_command_status = "chain_empty_or_pre_loop_failure"
            elif final_command_status == "all_steps_completed" and not processed_successfully_at_least_one_action and len(actions_to_execute) == 0:
                 final_command_status = "no_actions_to_execute_from_nlu"


            session_manager.update_session_context("last_overall_command_status", final_command_status)
            if final_command_status != "all_steps_completed":
                cli_ui.display_info(f"Command sequence processing ended with status: {final_command_status}")


    except KeyboardInterrupt:
        exit_icon = cli_constants.ICONS.get('app_icon', '🤖')
        cli_ui.console.print(f"\n{exit_icon} [bold app_logo_style]Exiting... (Ctrl+C)[/bold app_logo_style]")
    except Exception as e: 
        cli_ui.print_error(f"A critical error occurred in the main application loop: {str(e)}","Critical Application Error")
        cli_ui.console.print_exception(show_locals=True) 
    finally:
        session_manager.save_session_context()

if __name__ == '__main__':
    main()
