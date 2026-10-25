"""Mocked unit tests for OpenRouterChatProvider."""

import json
import unittest
from unittest.mock import MagicMock

import httpx

from kinetiqo.chat.errors import (
    ChatAuthenticationError,
    ChatConfigurationError,
    ChatProviderResponseError,
    ChatProviderUnavailableError,
    ChatRateLimitError,
)
from kinetiqo.chat.models import StreamEvent
from kinetiqo.chat.providers.openrouter import OpenRouterChatProvider


class TestOpenRouterChatProvider(unittest.TestCase):
    def test_headers_include_bearer_and_kinetiqo_title(self):
        provider = OpenRouterChatProvider("test-openrouter-key")
        headers = provider._headers()
        self.assertEqual(headers["Authorization"], "Bearer test-openrouter-key")
        self.assertEqual(headers["HTTP-Referer"], "https://github.com/lhotakj/kinetiqo")
        self.assertEqual(headers["X-Title"], "Kinetiqo")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_list_models_returns_configured_models_or_fallback(self):
        # Empty configured models -> fallback
        provider = OpenRouterChatProvider("key", configured_models=[])
        fallback = provider.list_models()
        self.assertTrue(len(fallback) > 0)
        self.assertTrue(any("nemotron" in m.id or "llama" in m.id for m in fallback))

        # Explicit configured models
        cfg = [
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 Free", "context_length": 131072},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "context_length": 200000},
        ]
        provider = OpenRouterChatProvider("key", configured_models=cfg)
        models = provider.list_models()
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0].id, "meta-llama/llama-3.3-70b-instruct:free")
        self.assertEqual(models[0].display_name, "Llama 3.3 Free")
        self.assertEqual(models[1].id, "anthropic/claude-3.5-sonnet")

    def test_raise_for_status_mappings(self):
        provider = OpenRouterChatProvider("key")

        # 401 -> ChatAuthenticationError
        resp_401 = MagicMock(status_code=401, is_success=False)
        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(resp_401)

        # 402 -> ChatRateLimitError (insufficient credits)
        resp_402 = MagicMock(status_code=402, is_success=False)
        with self.assertRaises(ChatRateLimitError):
            provider._raise_for_status(resp_402)

        # 429 -> ChatRateLimitError
        resp_429 = MagicMock(status_code=429, is_success=False)
        with self.assertRaises(ChatRateLimitError):
            provider._raise_for_status(resp_429)

        # 500 -> ChatProviderUnavailableError
        resp_500 = MagicMock(status_code=500, is_success=False)
        with self.assertRaises(ChatProviderUnavailableError):
            provider._raise_for_status(resp_500)

        # 400 -> ChatProviderResponseError
        resp_400 = MagicMock(status_code=400, is_success=False)
        with self.assertRaises(ChatProviderResponseError):
            provider._raise_for_status(resp_400)

    def test_validate_model_catalog_success(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "meta-llama/llama-3.3-70b-instruct",
                    "name": "Meta Llama 3.3 70B",
                    "context_length": 131072,
                    "supported_parameters": ["tools"],
                    "architecture": {"modality": "text"},
                }
            ]
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = OpenRouterChatProvider("key", client_factory=lambda timeout=None: client)

        result = provider.validate_model("meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(result["id"], "meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(result["display_name"], "Meta Llama 3.3 70B")
        self.assertEqual(result["context_length"], 131072)
        self.assertTrue(result["supports_tools"])

    def test_validate_model_suggests_base_model_when_free_suffix_not_offered(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "meta-llama/llama-3.3-70b-instruct",
                    "name": "Meta Llama 3.3 70B",
                    "context_length": 131072,
                    "supported_parameters": ["tools"],
                    "architecture": {"modality": "text"},
                }
            ]
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = OpenRouterChatProvider("key", client_factory=lambda timeout=None: client)

        with self.assertRaises(LookupError) as ctx:
            provider.validate_model("meta-llama/llama-3.3-70b-instruct:free")

        self.assertIn("does not currently offer a free tier (:free)", str(ctx.exception))
        self.assertEqual(getattr(ctx.exception, "suggestion", None), "meta-llama/llama-3.3-70b-instruct")

    def test_validate_model_rejects_embedding_model(self):
        provider = OpenRouterChatProvider("key")
        with self.assertRaises(ValueError) as ctx:
            provider.validate_model("nvidia/nemotron-3.5-embed-1b:free")
        self.assertIn("embedding model", str(ctx.exception))

    def test_validate_model_not_found_raises_lookup_error(self):
        client = MagicMock()
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {"data": []}
        client.get.return_value = cat_resp
        client.__enter__.return_value = client

        provider = OpenRouterChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(LookupError):
            provider.validate_model("nonexistent/model")

    def test_stream_yields_text_deltas_and_usage(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "Hello "}}]}',
            'data: {"choices": [{"delta": {"content": "world!"}}]}',
            'data: {"usage": {"prompt_tokens": 15, "completion_tokens": 4}}',
            "data: [DONE]",
        ]

        stream_resp = MagicMock(status_code=200, is_success=True)
        stream_resp.iter_lines.return_value = lines

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = stream_resp

        provider = OpenRouterChatProvider("key", client_factory=lambda timeout=None: client)

        events = list(provider.stream(
            model_id="anthropic/claude-3.5-sonnet",
            system_instruction="You are a coach.",
            history=[],
            prompt="Hi",
        ))

        text_events = [e for e in events if e.type == "text_delta"]
        usage_events = [e for e in events if e.type == "usage"]

        self.assertEqual(len(text_events), 2)
        self.assertEqual(text_events[0].text, "Hello ")
        self.assertEqual(text_events[1].text, "world!")
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0].input_tokens, 15)
        self.assertEqual(usage_events[0].output_tokens, 4)

    def test_stream_multi_turn_tool_execution(self):
        # Turn 1: model calls tool 'kinetiqo_get_training_goals'
        turn1_lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_123", "function": {"name": "kinetiqo_get_training_goals", "arguments": "{}"}}]}}]}',
            "data: [DONE]",
        ]
        # Turn 2: model outputs final text based on tool result
        turn2_lines = [
            'data: {"choices": [{"delta": {"content": "Your goal is 100km per week."}}]}',
            'data: {"usage": {"prompt_tokens": 50, "completion_tokens": 10}}',
            "data: [DONE]",
        ]

        resp1 = MagicMock(status_code=200, is_success=True)
        resp1.iter_lines.return_value = turn1_lines

        resp2 = MagicMock(status_code=200, is_success=True)
        resp2.iter_lines.return_value = turn2_lines

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.side_effect = [resp1, resp2]

        tool_executor = MagicMock(return_value=({"goals": [{"type": "Ride", "distance_km": 100}]}, 42))

        provider = OpenRouterChatProvider("key", client_factory=lambda timeout=None: client)

        events = list(provider.stream(
            model_id="anthropic/claude-3.5-sonnet",
            system_instruction="Coach",
            history=[],
            prompt="What is my goal?",
            tools=[{"type": "function", "function": {"name": "kinetiqo_get_training_goals"}}],
            tool_executor=tool_executor,
        ))

        # Verify tool was called
        tool_executor.assert_called_once_with("kinetiqo_get_training_goals", {})

        # Verify tool call, tool result, text delta, and usage events
        event_types = [e.type for e in events]
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("text_delta", event_types)
        self.assertIn("usage", event_types)

        text_events = [e for e in events if e.type == "text_delta"]
        self.assertEqual(text_events[0].text, "Your goal is 100km per week.")


if __name__ == "__main__":
    unittest.main()
