
import os
import time
import re # For keyword matching for direct parsers

from ollama_connector import OllamaConnector
from config import OLLAMA_MODEL # Still needed for startup message context, though not directly used in main logic here
from activity_logger import log_action # For logging unhandled/unknown actions

# New modular imports
# New modular imports
from main import cli_constants
from main import cli_ui
from main import session_manager
from main import direct_parsers
from main import nlu_processor
from main import action_handlers as action_handlers_module # Alias to avoid conflict # Alias to avoid conflict

from rich.prompt import Prompt
from rich.text import Text
from rich.rule import Rule
from rich.live import Live # For LLM spinner
from rich.spinner import Spinner # For LLM spinner


def main():
    session_manager.load_session_context()
    connector = OllamaConnector()

    if not cli_ui.print_startup_message_ui(connector): # Using the UI module's startup message
        session_manager.save_session_context()
        return

    action_handlers_map = action_handlers_module.get_action_handler_map()

    try:
        while True:
            cli_ui.console.print(Rule(style="separator_style"))
            user_input_original = Prompt.ask(Text.from_markup("[prompt]You[/prompt]"), default="", console=cli_ui.console).strip()

            if not user_input_original:
                continue
            if user_input_original.lower() in ['quit','exit','bye','q']:
                cli_ui.console.print(f"{cli_constants.ICONS['app_icon']} [bold app_logo_style]Exiting...[/bold app_logo_style]")
                break
            if user_input_original.lower() == 'help':
                cli_ui.display_help()
                continue

            parsed_cmd=None
            action=None
            params={}
            nlu_notes=None
            nlu_method_note="llm_fallback" # Default if no direct parser matches or if direct fails
            
            current_session_ctx = session_manager.get_session_context()

            direct_parser_functions_map = {
                "search": (direct_parsers.parse_direct_search, False),
                "list": (direct_parsers.parse_direct_list, True),
                "activity": (direct_parsers.parse_direct_activity_log, False),
                "summarize": (direct_parsers.parse_direct_summarize, True),
                "organize": (direct_parsers.parse_direct_organize, True),
                "move": (direct_parsers.parse_direct_move, False)
            }
            
            user_input_first_word = user_input_original.lower().split(" ")[0] if user_input_original else ""
            found_direct_parser = False
            
            relevant_parser_key = None
            if user_input_first_word in ["search", "find"]: relevant_parser_key = "search"
            elif user_input_first_word in ["list", "ls"] or \
                 "contents of" in user_input_original.lower() or \
                 "files in" in user_input_original.lower(): relevant_parser_key = "list"
            elif user_input_first_word in ["show", "view"] and \
                 any(k in user_input_original.lower() for k in ["activity", "log", "history"]): relevant_parser_key = "activity"
            elif user_input_first_word == "summarize": relevant_parser_key = "summarize"
            elif user_input_first_word in ["organize", "organise", "sort", "cleanup"] or \
                 "clean up" in user_input_original.lower(): relevant_parser_key = "organize"
            elif user_input_first_word == "move": relevant_parser_key = "move"

            if relevant_parser_key:
                parser_func, needs_ctx = direct_parser_functions_map[relevant_parser_key]
                if needs_ctx:
                    parsed_cmd = parser_func(user_input_original, current_session_ctx)
                else:
                    parsed_cmd = parser_func(user_input_original)
                
                if parsed_cmd:
                    nlu_method_note = parsed_cmd.pop("nlu_method","direct_unknown")
                    found_direct_parser = True
            
            if not found_direct_parser:
                spinner_text = f"{cli_constants.ICONS['thinking']} [spinner_style]Understanding: '{user_input_original[:35]}...'[/spinner_style]"
                with Live(Spinner("dots",text=spinner_text),console=cli_ui.console,transient=True):
                    parsed_cmd=connector.get_intent_and_entities(user_input_original, current_session_ctx)
                
                if parsed_cmd and parsed_cmd.get("nlu_method"):
                     nlu_method_note = parsed_cmd.pop("nlu_method")
                elif parsed_cmd and parsed_cmd.get("nlu_correction_note"):
                    nlu_method_note = "llm_corrected" # nlu_method_note will be combined later

            if parsed_cmd and "action" in parsed_cmd:
                # Combine nlu_method_note from direct/LLM with potential correction note from LLM
                llm_correction_note = parsed_cmd.get("nlu_correction_note")
                if llm_correction_note and nlu_method_note != "llm_corrected": # Avoid double noting if already set
                    nlu_notes = f"{nlu_method_note}; {llm_correction_note}"
                else:
                    nlu_notes = nlu_method_note # Use the primary note (direct, llm_fallback, or llm_corrected)

                action, params, final_proc_notes = nlu_processor.process_nlu_result(
                    parsed_cmd, user_input_original, current_session_ctx, connector
                )
                if final_proc_notes:
                    nlu_notes = (nlu_notes + "; " + final_proc_notes) if nlu_notes else final_proc_notes
            else:
                action="unknown"
                params={"original_request":user_input_original,"error":"NLU failure (direct & LLM)"}
                nlu_notes="NLU_failed_all"
            
            if not action: # Should not happen if NLU failure path above is taken
                cli_ui.print_error("No action determined after NLU processing.","Critical NLU Error")
                log_action("nlu_critical_failure",{"input":user_input_original},"failure", nlu_notes)
                continue
            
            if action == "user_cancelled_organization": # Special case from nlu_processor
                session_manager.add_to_command_history(action, params, nlu_notes) # Log the cancellation
                continue

            # Resolve indexed references
            # Pass current action, params dict, and session_ctx. It returns new action and flag.
            new_action_from_index, index_resolved = nlu_processor.resolve_indexed_reference(
                user_input_original.lower(), action, params, current_session_ctx
            )
            if index_resolved:
                action = new_action_from_index # Update action if changed by index resolution
                nlu_notes = (nlu_notes + "; IdxRefResolved") if nlu_notes else "IdxRefResolved"

            session_manager.add_to_command_history(action, params, nlu_notes)
            
            handler = action_handlers_map.get(action)
            if handler:
                # Action handlers will use imported cli_ui.console, cli_constants.ICONS, session_manager, etc.
                if action in ["summarize_file","ask_question_about_file","search_files",
                              "propose_and_execute_organization","general_chat","redo_activity"]:
                    handler(connector, params)
                else: # Handlers that don't need the connector instance
                    handler(params)
            elif action=="unknown":
                err_detail = params.get('error','Unrecognized command or parameters.')
                if "Ollama" in err_detail or "LLM" in err_detail: # Crude check
                    cli_ui.print_error(f"Could not understand your request due to an issue with the AI model.\nDetails: {err_detail}\nPlease try again or rephrase.","AI Model Error")
                else:
                    cli_ui.print_warning(f"Cannot handle: '{params.get('original_request',user_input_original)}'.\nDetails: {err_detail}\nTry 'help'.","Unknown Command")
                log_action("unknown_command", params, "failure", err_detail) # Log the original "unknown" action
            else:
                # This case means action was recognized by NLU but no handler is in the map
                cli_ui.print_warning(f"Action '[highlight]{action}[/highlight]' is recognized but not implemented.","Not Implemented")
                log_action("not_implemented", {"action": action, "input": user_input_original, "parsed_params": params}, "pending", nlu_notes)

    except KeyboardInterrupt:
        cli_ui.console.print(f"\n{cli_constants.ICONS['app_icon']} [bold app_logo_style]Exiting...[/bold app_logo_style]")
    except Exception:
        cli_ui.print_error("A critical error occurred in the main application loop!","Critical Error")
        cli_ui.console.print_exception(show_locals=True) # Show more details for debugging main loop errors
    finally:
        session_manager.save_session_context()

if __name__ == '__main__':
    main()