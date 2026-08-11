import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.infra.llm.openai_client import OpenAIClient


class TestOpenAIClient(unittest.TestCase):
    def test_chat_api_uses_chat_completions(self):
        fake_client = Mock()
        fake_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="chat-result")
                )
            ]
        )

        with patch("app.infra.llm.openai_client.OpenAI", return_value=fake_client):
            client = OpenAIClient(api_key="sk-test", model="gpt-test", api_type="chat")
            result = client.completions([{"role": "user", "content": "hello"}])

        self.assertEqual(result, "chat-result")
        fake_client.chat.completions.create.assert_called_once()
        fake_client.responses.create.assert_not_called()

    def test_responses_api_uses_responses_create(self):
        fake_client = Mock()
        fake_client.responses.create.return_value = SimpleNamespace(output_text="responses-result")

        with patch("app.infra.llm.openai_client.OpenAI", return_value=fake_client):
            client = OpenAIClient(
                api_key="sk-test",
                model="gpt-test",
                api_type="responses",
                response_options={"store": False},
            )
            result = client.completions([{"role": "user", "content": "hello"}])

        self.assertEqual(result, "responses-result")
        fake_client.responses.create.assert_called_once_with(
            model="gpt-test",
            input=[{"role": "user", "content": "hello"}],
            store=False,
        )
        fake_client.chat.completions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
