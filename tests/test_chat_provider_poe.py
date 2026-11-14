"""Mocked tests for the Poe OpenAI-compatible provider."""

import unittest
from unittest.mock import MagicMock

from kinetiqo.chat.errors import ChatAuthenticationError, ChatConfigurationError, ChatProviderResponseError
from kinetiqo.chat.providers.poe import PoeChatProvider
from kinetiqo.chat.service import ChatService


class TestPoeChatProvider(unittest.TestCase):
    def test_base_url_and_headers(self):
        provider = PoeChatProvider("poe-test-key")

        self.assertEqual(provider.base_url, "https://api.poe.com/v1")
        self.assertEqual(provider._headers()["Authorization"], "Bearer poe-test-key")
        self.assertEqual(provider._headers()["Content-Type"], "application/json")

    def test_list_models_only_returns_configured_bots(self):
        provider = PoeChatProvider("key", configured_models=[
            {"id": "AssistantBot", "display_name": "Assistant", "supports_tools": True},
            {"id": "", "display_name": "Invalid"},
        ])

        models = provider.list_models()

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].id, "AssistantBot")
        self.assertEqual(models[0].display_name, "Assistant")
        self.assertEqual(PoeChatProvider.default_model, "")

    def test_validate_model_uses_bot_api_and_preserves_reported_metadata(self):
        response = MagicMock(status_code=200, is_success=True)
        response.json.return_value = {
            "bot": {
                "handle": "AssistantBot",
                "display_name": "Assistant",
                "description": "A test bot",
                "context_length": 64000,
                "pricing": {"input": "0.01"},
            }
        }
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        provider = PoeChatProvider("key", client_factory=lambda timeout=None: client)

        model = provider.validate_model("AssistantBot")

        self.assertEqual(model["id"], "AssistantBot")
        self.assertEqual(model["display_name"], "Assistant")
        self.assertEqual(model["description"], "A test bot")
        self.assertEqual(model["context_length"], 64000)
        self.assertEqual(model["pricing"], {"input": "0.01"})
        client.get.assert_called_once_with(
            "https://api.poe.com/bots/AssistantBot",
            headers=provider._headers(),
        )

    def test_validate_model_encodes_handle(self):
        response = MagicMock(status_code=200, is_success=True)
        response.json.return_value = {"handle": "bot/name"}
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        provider = PoeChatProvider("key", client_factory=lambda timeout=None: client)

        model = provider.validate_model("bot/name")

        self.assertEqual(model["id"], "bot/name")
        self.assertEqual(client.get.call_args.args[0], "https://api.poe.com/bots/bot%2Fname")

    def test_chat_api_maps_authentication_errors(self):
        provider = PoeChatProvider("key")
        response = MagicMock(status_code=401, is_success=False)

        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(response)

    def test_stream_posts_to_poe_chat_completions_endpoint(self):
        response = MagicMock(status_code=200, is_success=True)
        response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            "data: [DONE]",
        ]
        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = response
        provider = PoeChatProvider("key", client_factory=lambda timeout=None: client)

        events = list(provider.stream("AssistantBot", "system", [], "Hi"))

        self.assertEqual([event.text for event in events if event.type == "text_delta"], ["Hello"])
        self.assertEqual(client.stream.call_args.args[:2], ("POST", "https://api.poe.com/v1/chat/completions"))
        self.assertEqual(client.stream.call_args.kwargs["json"]["model"], "AssistantBot")

    def test_invalid_bot_response_fails_explicitly(self):
        response = MagicMock(status_code=200, is_success=True)
        response.json.return_value = {"bot": []}
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.return_value = response
        provider = PoeChatProvider("key", client_factory=lambda timeout=None: client)

        with self.assertRaises(ChatProviderResponseError):
            provider.validate_model("AssistantBot")


class TestPoeChatSessionDefaults(unittest.TestCase):
    def test_create_session_uses_first_configured_bot_when_default_unspecified(self):
        repository = MagicMock()
        repository.get_provider_key.return_value = "encrypted-key"
        repository.get_provider_config.return_value = {
            "models": [{"id": "AssistantBot", "display_name": "Assistant"}],
        }
        service = ChatService(repository, "test-secret")

        service.create_session("athlete", provider="poe")

        repository.create_session.assert_called_once_with("athlete", "poe", "AssistantBot")

    def test_create_session_rejects_unconfigured_poe_bot(self):
        repository = MagicMock()
        repository.get_provider_key.return_value = "encrypted-key"
        repository.get_provider_config.return_value = {"models": []}
        service = ChatService(repository, "test-secret")

        with self.assertRaises(ChatConfigurationError):
            service.create_session("athlete", provider="poe")


if __name__ == "__main__":
    unittest.main()
