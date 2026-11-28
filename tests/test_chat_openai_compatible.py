"""Unit tests for OpenAICompatibleChatProvider base class."""

import json
import unittest
from unittest.mock import MagicMock, patch

import httpx

from kinetiqo.chat.errors import (
    ChatAuthenticationError,
    ChatProviderResponseError,
    ChatProviderUnavailableError,
    ChatRateLimitError,
    ChatTimeoutError,
)
from kinetiqo.chat.models import StreamEvent
from kinetiqo.chat.providers.openai_compatible import OpenAICompatibleChatProvider


class DummyOpenAIProvider(OpenAICompatibleChatProvider):
    provider_name = "dummy"
    display_name = "Dummy AI"
    base_url = "https://api.dummy.ai/v1"
    default_model = "dummy-v1"
    suggested_models = (
        {"id": "dummy-v1", "label": "Dummy V1"},
    )


class TestOpenAICompatibleChatProvider(unittest.TestCase):
    def setUp(self):
        self.provider = DummyOpenAIProvider("test-key")

    def test_headers_default(self):
        headers = self.provider._headers()
        self.assertEqual(headers["Authorization"], "Bearer test-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("User-Agent", headers)

    def test_raise_for_status_mappings(self):
        # 200 -> no exception
        resp_200 = MagicMock(status_code=200, is_success=True)
        self.provider._raise_for_status(resp_200)

        # 401 / 403 -> ChatAuthenticationError
        resp_401 = MagicMock(status_code=401, is_success=False)
        resp_401.read.return_value = b'{"error": {"message": "Invalid API key"}}'
        with self.assertRaises(ChatAuthenticationError) as ctx:
            self.provider._raise_for_status(resp_401)
        self.assertIn("Invalid API key", str(ctx.exception))

        # 402 -> ChatRateLimitError (Payment required)
        resp_402 = MagicMock(status_code=402, is_success=False)
        resp_402.read.return_value = b'{"error": {"message": "No credits"}}'
        with self.assertRaises(ChatRateLimitError):
            self.provider._raise_for_status(resp_402)

        # 429 -> ChatRateLimitError
        resp_429 = MagicMock(status_code=429, is_success=False)
        resp_429.read.return_value = b'{"error": {"message": "Rate limit exceeded"}}'
        with self.assertRaises(ChatRateLimitError):
            self.provider._raise_for_status(resp_429)

        # 500 / 503 -> ChatProviderUnavailableError
        resp_503 = MagicMock(status_code=503, is_success=False)
        resp_503.read.return_value = b"Service Unavailable"
        with self.assertRaises(ChatProviderUnavailableError):
            self.provider._raise_for_status(resp_503)

        # 400 -> ChatProviderResponseError
        resp_400 = MagicMock(status_code=400, is_success=False)
        resp_400.read.return_value = b'{"error": {"message": "Bad request schema"}}'
        with self.assertRaises(ChatProviderResponseError):
            self.provider._raise_for_status(resp_400)

    def test_parse_model_item(self):
        item = {
            "id": "gpt-4o-mini",
            "name": "GPT 4o Mini",
            "context_length": 128000,
            "supports_tools": True,
            "supports_vision": True,
        }
        parsed = self.provider._parse_model_item(item)
        self.assertEqual(parsed["id"], "gpt-4o-mini")
        self.assertEqual(parsed["name"], "GPT 4o Mini")
        self.assertEqual(parsed["context_length"], 128000)
        self.assertTrue(parsed["supports_tools"])
        self.assertTrue(parsed["supports_vision"])
        self.assertFalse(parsed["is_embedding"])

        # Detect embedding model
        embed_item = {"id": "text-embedding-3-small"}
        parsed_embed = self.provider._parse_model_item(embed_item)
        self.assertTrue(parsed_embed["is_embedding"])

    def test_validate_model_rejects_embedding(self):
        with self.assertRaises(ValueError) as ctx:
            self.provider.validate_model("text-embedding-3-large")
        self.assertIn("embedding model", str(ctx.exception).lower())

        with self.assertRaises(ValueError):
            self.provider.validate_model("")

    def test_validate_model_direct_and_catalog_match(self):
        mock_client = MagicMock()
        self.provider.client_factory = MagicMock(return_value=mock_client)
        mock_client.__enter__.return_value = mock_client

        # Direct model lookup succeeds
        mock_resp_direct = MagicMock(status_code=200, is_success=True)
        mock_resp_direct.json.return_value = {
            "id": "dummy-v1",
            "name": "Dummy V1",
            "context_length": 64000,
            "supports_tools": True,
        }
        mock_client.get.return_value = mock_resp_direct

        res = self.provider.validate_model("dummy-v1")
        self.assertEqual(res["id"], "dummy-v1")
        self.assertEqual(res["context_length"], 64000)

    def test_list_models_configured_vs_fallback(self):
        # 1. Configured models take priority
        cfg_provider = DummyOpenAIProvider("test-key", configured_models=[
            {"id": "m1", "name": "Model 1", "context_length": 32000}
        ])
        models = cfg_provider.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].id, "m1")

        # 2. Fallback to suggested models
        fallback_models = self.provider.list_models()
        self.assertEqual(len(fallback_models), 1)
        self.assertEqual(fallback_models[0].id, "dummy-v1")

    def test_stream_text_and_finish_events(self):
        mock_client = MagicMock()
        self.provider.client_factory = MagicMock(return_value=mock_client)
        mock_client.__enter__.return_value = mock_client

        mock_resp = MagicMock(is_success=True)
        mock_resp.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"content": "Hello "}}]}',
            'data: {"choices": [{"delta": {"content": "world!"}}]}',
            'data: {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}',
            'data: [DONE]',
        ]
        mock_client.stream.return_value.__enter__.return_value = mock_resp

        events = list(self.provider.stream(
            model_id="dummy-v1",
            system_instruction="Be helpful",
            history=[],
            prompt="Hi",
        ))

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].type, "text_delta")
        self.assertEqual(events[0].text, "Hello ")
        self.assertEqual(events[1].type, "text_delta")
        self.assertEqual(events[1].text, "world!")
        self.assertEqual(events[2].type, "usage")
        self.assertEqual(events[2].input_tokens, 10)
        self.assertEqual(events[2].output_tokens, 5)

    def test_stream_tool_calling_multi_turn(self):
        mock_client = MagicMock()
        self.provider.client_factory = MagicMock(return_value=mock_client)
        mock_client.__enter__.return_value = mock_client

        # Turn 1: Model asks to call tool
        turn1_resp = MagicMock(is_success=True)
        turn1_resp.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_123", "function": {"name": "get_weather", "arguments": "{\\"city\\": \\"Prague\\"}"}}]}}]}',
            'data: [DONE]',
        ]
        # Turn 2: Model finishes with answer
        turn2_resp = MagicMock(is_success=True)
        turn2_resp.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"content": "The weather in Prague is sunny."}}]}',
            'data: [DONE]',
        ]

        mock_stream_cm1 = MagicMock()
        mock_stream_cm1.__enter__.return_value = turn1_resp
        mock_stream_cm2 = MagicMock()
        mock_stream_cm2.__enter__.return_value = turn2_resp
        mock_client.stream.side_effect = [mock_stream_cm1, mock_stream_cm2]

        tool_executor = MagicMock(return_value=({"temp": 21, "cond": "sunny"}, 200))

        events = list(self.provider.stream(
            model_id="dummy-v1",
            system_instruction="Be helpful",
            history=[],
            prompt="What is the weather in Prague?",
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
            tool_executor=tool_executor,
        ))

        tool_executor.assert_called_once_with("get_weather", {"city": "Prague"})
        event_types = [e.type for e in events]
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("text_delta", event_types)

    def test_stream_timeout_raises_chat_timeout_error(self):
        mock_client = MagicMock()
        self.provider.client_factory = MagicMock(return_value=mock_client)
        mock_client.__enter__.return_value = mock_client
        mock_client.stream.side_effect = httpx.ReadTimeout("Timeout")

        with self.assertRaises(ChatTimeoutError):
            list(self.provider.stream(
                model_id="dummy-v1",
                system_instruction="sys",
                history=[],
                prompt="hello",
            ))


if __name__ == "__main__":
    unittest.main()
