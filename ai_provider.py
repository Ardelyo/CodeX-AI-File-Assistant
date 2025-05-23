from abc import ABC, abstractmethod

class AIProvider(ABC):
    @abstractmethod
    def __init__(self, config: dict):
        pass

    @abstractmethod
    def check_connection_and_model(self) -> tuple[bool, bool, list]:
        pass

    @abstractmethod
    def get_intent_and_entities(self, user_input: str, session_context: dict) -> dict:
        pass

    @abstractmethod
    def invoke_llm_for_content(self, main_instruction: str, context_text: str = "") -> str:
        pass

    @abstractmethod
    def generate_organization_plan(self, target_folder_path: str, organization_goal: str, current_contents_summary: str) -> dict:
        pass

    @abstractmethod
    def get_summary(self, file_content: str, file_path_for_context: str) -> dict:
        pass

    @abstractmethod
    def ask_question_about_text(self, text_content: str, question: str, file_path_for_context: str) -> dict:
        pass

    @abstractmethod
    def general_chat_completion(self, user_query: str) -> dict:
        pass
