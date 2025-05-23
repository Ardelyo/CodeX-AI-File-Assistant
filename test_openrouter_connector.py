import unittest
from unittest.mock import patch, Mock
from openrouter_connector import OpenRouterConnector

class TestOpenRouterConnector(unittest.TestCase):

    def test_init_success(self):
        config = {"API_KEY": "test_key_openrouter", "MODEL": "test_model_openrouter"}
        try:
            connector = OpenRouterConnector(config)
            self.assertEqual(connector.api_key, "test_key_openrouter")
            self.assertEqual(connector.model, "test_model_openrouter")
        except ValueError:
            self.fail("OpenRouterConnector raised ValueError unexpectedly on valid config.")

    def test_init_missing_api_key(self):
        config = {"MODEL": "test_model_openrouter"}
        with self.assertRaisesRegex(ValueError, "API_KEY is required"):
            OpenRouterConnector(config)

    @patch('requests.get')
    def test_check_connection_and_model_success_model_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "test_model_openrouter"}, {"id": "another_model"}]}
        mock_get.return_value = mock_response

        config = {"API_KEY": "test_key_openrouter", "MODEL": "test_model_openrouter"}
        connector = OpenRouterConnector(config)
        conn_ok, model_found, models_list = connector.check_connection_and_model()
        
        self.assertTrue(conn_ok)
        self.assertTrue(model_found)
        self.assertIsInstance(models_list, list)
        self.assertEqual(models_list[0]['id'], "test_model_openrouter")
        mock_get.assert_called_once_with(
            f"{connector.base_url}/models", 
            headers={"Authorization": f"Bearer {config['API_KEY']}"}, 
            timeout=10
        )

    @patch('requests.get')
    def test_check_connection_and_model_success_model_not_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "another_model"}]}
        mock_get.return_value = mock_response

        config = {"API_KEY": "test_key_openrouter", "MODEL": "test_model_openrouter"}
        connector = OpenRouterConnector(config)
        conn_ok, model_found, models_list = connector.check_connection_and_model()
        
        self.assertTrue(conn_ok)
        self.assertFalse(model_found)
        self.assertIsInstance(models_list, list)
        mock_get.assert_called_once()
        
    @patch('requests.get')
    def test_check_connection_and_model_api_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 401 
        mock_response.text = "Unauthorized"
        mock_get.return_value = mock_response

        config = {"API_KEY": "test_key_openrouter", "MODEL": "test_model_openrouter"}
        connector = OpenRouterConnector(config)
        conn_ok, model_found, models_list = connector.check_connection_and_model()
        
        self.assertFalse(conn_ok)
        self.assertFalse(model_found)
        self.assertIsInstance(models_list, list)
        self.assertTrue(any("OpenRouter API request failed" in item.get("error", "") for item in models_list if isinstance(item, dict)))
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_check_connection_and_model_request_exception(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Test timeout")

        config = {"API_KEY": "test_key_openrouter", "MODEL": "test_model_openrouter"}
        connector = OpenRouterConnector(config)
        conn_ok, model_found, models_list = connector.check_connection_and_model()
        
        self.assertFalse(conn_ok)
        self.assertFalse(model_found)
        self.assertIsInstance(models_list, list)
        self.assertTrue(any("OpenRouter connection failed" in item.get("error", "") for item in models_list if isinstance(item, dict)))
        mock_get.assert_called_once()

    def test_get_intent_and_entities_placeholder(self):
        config = {"API_KEY": "test_key_openrouter"}
        connector = OpenRouterConnector(config)
        result = connector.get_intent_and_entities("test input", {})
        
        self.assertEqual(result.get("nlu_method"), "openrouter_placeholder_nlu")
        self.assertEqual(result.get("error_type"), "not_implemented")
        self.assertIn("OpenRouter get_intent_and_entities not implemented", result.get("message"))
        self.assertIn("chain_of_thought", result)
        self.assertIn("actions", result)
        self.assertIsInstance(result["actions"], list)
        self.assertEqual(result["actions"][0]["action_name"], "unknown")
        self.assertIn("NLU not implemented for OpenRouter", result["actions"][0]["parameters"]["error_reason"])

    def test_invoke_llm_for_content_placeholder(self):
        config = {"API_KEY": "test_key_openrouter"}
        connector = OpenRouterConnector(config)
        result = connector.invoke_llm_for_content("test instruction")
        self.assertEqual(result, "Error: OpenRouter invoke_llm_for_content not implemented")

    def test_generate_organization_plan_placeholder(self):
        config = {"API_KEY": "test_key_openrouter"}
        connector = OpenRouterConnector(config)
        result = connector.generate_organization_plan("path", "goal", "summary")
        self.assertEqual(result.get("error"), "OpenRouter generate_organization_plan not implemented")

    def test_get_summary_placeholder(self):
        config = {"API_KEY": "test_key_openrouter"}
        connector = OpenRouterConnector(config)
        result = connector.get_summary("content", "path")
        self.assertEqual(result.get("error"), "OpenRouter get_summary not implemented")

    def test_ask_question_about_text_placeholder(self):
        config = {"API_KEY": "test_key_openrouter"}
        connector = OpenRouterConnector(config)
        result = connector.ask_question_about_text("content", "question", "path")
        self.assertEqual(result.get("error"), "OpenRouter ask_question_about_text not implemented")

    def test_general_chat_completion_placeholder(self):
        config = {"API_KEY": "test_key_openrouter"}
        connector = OpenRouterConnector(config)
        result = connector.general_chat_completion("query")
        self.assertEqual(result.get("error"), "OpenRouter general_chat_completion not implemented")

if __name__ == '__main__':
    unittest.main()
