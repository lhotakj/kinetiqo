"""Mocked unit tests for MistralChatProvider."""

import json
import unittest
from unittest.mock import MagicMock

import httpx

from kinetiqo.chat.errors import (
    ChatAuthenticationError,
    ChatProviderResponseError,
    ChatProviderUnavailableError,
    ChatRateLimitError,
    ChatTimeoutError,
)
from kinetiqo.chat.models import StreamEvent
from kinetiqo.chat.providers.mistral import MistralChatProvider


class TestMistralChatProvider(unittest.TestCase):
    def test_headers_include_bearer_and_kinetiqo_ua(self):
        provider = MistralChatProvider("test-mistral-key")
        headers = provider._headers()
        self.assertEqual(headers["Authorization"], "Bearer test-mistral-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["User-Agent"], "Kinetiqo-Fitness-AI")

    def test_list_models_discovers_chat_models_and_filters_non_chat(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "object": "list",
            "data": [
                {
                    "id": "mistral-embed",
                    "name": "Mistral Embed",
                    "capabilities": {"completion_chat": False},
                },
                {
                    "id": "mistral-moderation-latest",
                    "name": "Mistral Moderation",
                    "capabilities": {"completion_chat": False},
                },
                {
                    "id": "mistral-tiny",
                    "name": "Mistral Tiny (Deprecated)",
                    "capabilities": {"completion_chat": True},
                },
                {
                    "id": "mistral-large-latest",
                    "name": "Mistral Large",
                    "description": "Top-tier flagship reasoning model.",
                    "max_context_length": 128000,
                    "capabilities": {
                        "completion_chat": True,
                        "function_calling": True,
                        "vision": False,
                    },
                },
                {
                    "id": "pixtral-large-latest",
                    "name": "Pixtral Large",
                    "description": "Frontier multimodal vision model.",
                    "max_context_length": 128000,
                    "capabilities": {
                        "completion_chat": True,
                        "function_calling": True,
                        "vision": True,
                    },
                },
                {
                    "id": "mistral-small-latest",
                    "name": "Mistral Small",
                    "description": "Fast and lightweight model.",
                    "max_context_length": 128000,
                    "capabilities": {
                        "completion_chat": True,
                        "function_calling": True,
                        "vision": False,
                    },
                },
            ],
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client

        provider = MistralChatProvider("key", client_factory=lambda timeout=None: client)
        models = provider.list_models()

        # Should exclude mistral-embed, mistral-moderation-latest, and deprecated mistral-tiny
        model_ids = [m.id for m in models]
        self.assertNotIn("mistral-embed", model_ids)
        self.assertNotIn("mistral-moderation-latest", model_ids)
        self.assertNotIn("mistral-tiny", model_ids)

        self.assertIn("mistral-small-latest", model_ids)
        self.assertIn("mistral-large-latest", model_ids)
        self.assertIn("pixtral-large-latest", model_ids)

        # mistral-small-latest should rank ahead of pixtral-large-latest based on PREFERRED_MODELS
        small_idx = model_ids.index("mistral-small-latest")
        large_idx = model_ids.index("mistral-large-latest")
        self.assertLess(small_idx, large_idx)

        # Check capabilities extraction
        pixtral = next(m for m in models if m.id == "pixtral-large-latest")
        self.assertTrue(pixtral.supports_vision)
        self.assertTrue(pixtral.supports_tools)
        self.assertEqual(pixtral.context_length, 128000)
        self.assertEqual(pixtral.description, "Frontier multimodal vision model.")

    def test_raise_for_status_mappings(self):
        provider = MistralChatProvider("key")

        # 401 -> ChatAuthenticationError
        resp_401 = MagicMock(status_code=401, is_success=False)
        resp_401.read.return_value = b'{"error": {"message": "Unauthorized"}}'
        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(resp_401)

        # 403 -> ChatAuthenticationError
        resp_403 = MagicMock(status_code=403, is_success=False)
        resp_403.read.return_value = b'{"error": {"message": "Forbidden"}}'
        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(resp_403)

        # 402 -> ChatRateLimitError
        resp_402 = MagicMock(status_code=402, is_success=False)
        resp_402.read.return_value = b'{"error": {"message": "Payment required"}}'
        with self.assertRaises(ChatRateLimitError):
            provider._raise_for_status(resp_402)

        # 429 -> ChatRateLimitError
        resp_429 = MagicMock(status_code=429, is_success=False)
        resp_429.read.return_value = b'{"error": {"message": "Rate limit exceeded"}}'
        with self.assertRaises(ChatRateLimitError):
            provider._raise_for_status(resp_429)

        # 500 -> ChatProviderUnavailableError
        resp_500 = MagicMock(status_code=500, is_success=False)
        resp_500.read.return_value = b'Internal Server Error'
        with self.assertRaises(ChatProviderUnavailableError):
            provider._raise_for_status(resp_500)

        # 400 -> ChatProviderResponseError
        resp_400 = MagicMock(status_code=400, is_success=False)
        resp_400.read.return_value = b'{"error": {"message": "Bad request"}}'
        with self.assertRaises(ChatProviderResponseError):
            provider._raise_for_status(resp_400)

    def test_validate_model_success_and_failures(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "mistral-small-latest",
                    "name": "Mistral Small",
                    "max_context_length": 128000,
                    "capabilities": {"completion_chat": True, "function_calling": True},
                },
                {
                    "id": "mistral-embed",
                    "name": "Mistral Embed",
                    "capabilities": {"completion_chat": False},
                },
            ]
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client

        provider = MistralChatProvider("key", client_factory=lambda timeout=None: client)

        # Valid model
        info = provider.validate_model("mistral-small-latest")
        self.assertEqual(info["id"], "mistral-small-latest")
        self.assertTrue(info["supports_tools"])

        # Empty model ID
        with self.assertRaises(ValueError):
            provider.validate_model("   ")

        # Embedding model rejection
        with self.assertRaises(ValueError):
            provider.validate_model("mistral-embed")

        # Unknown model ID
        with self.assertRaises(LookupError):
            provider.validate_model("nonexistent-model")

    def test_stream_text_deltas(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.iter_lines.return_value = [
            "data: " + json.dumps({
                "choices": [{"delta": {"content": "Hello"}}],
            }),
            "data: " + json.dumps({
                "choices": [{"delta": {"content": " from Mistral!"}}],
            }),
            "data: " + json.dumps({
                "choices": [{"delta": {}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }),
            "data: [DONE]",
        ]
        client.stream.return_value.__enter__.return_value = mock_resp
        client.__enter__.return_value = client

        provider = MistralChatProvider("key", client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="mistral-small-latest",
            system_instruction="You are an assistant.",
            history=[],
            prompt="Hi",
        ))

        texts = [ev.text for ev in events if ev.type == "text_delta"]
        self.assertEqual("".join(texts), "Hello from Mistral!")

        usage_events = [ev for ev in events if ev.type == "usage"]
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0].input_tokens, 12)
        self.assertEqual(usage_events[0].output_tokens, 5)

    def test_stream_tool_calling_loop(self):
        client = MagicMock()

        # Turn 1: model yields a tool call for kinetiqo_get_activity_totals
        turn1_resp = MagicMock(status_code=200, is_success=True)
        turn1_resp.iter_lines.return_value = [
            "data: " + json.dumps({
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "kinetiqo_get_activity_totals",
                                "arguments": '{"sport_types": ["Ride"]}',
                            },
                        }]
                    }
                }],
            }),
            "data: [DONE]",
        ]

        # Turn 2: model synthesizes final answer after receiving tool response
        turn2_resp = MagicMock(status_code=200, is_success=True)
        turn2_resp.iter_lines.return_value = [
            "data: " + json.dumps({
                "choices": [{"delta": {"content": "You rode 150 km this month."}}],
            }),
            "data: [DONE]",
        ]

        client.stream.return_value.__enter__.side_effect = [turn1_resp, turn2_resp]
        client.__enter__.return_value = client

        executed_calls = []

        def mock_executor(tool_name, tool_args):
            executed_calls.append((tool_name, tool_args))
            return {"distance_km": 150.0}, 0

        provider = MistralChatProvider("key", client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="mistral-small-latest",
            system_instruction="Analyze athlete data.",
            history=[],
            prompt="What is my riding distance?",
            tools=[{"type": "function", "function": {"name": "kinetiqo_get_activity_totals"}}],
            tool_executor=mock_executor,
        ))

        self.assertEqual(len(executed_calls), 1)
        self.assertEqual(executed_calls[0][0], "kinetiqo_get_activity_totals")
        self.assertEqual(executed_calls[0][1], {"sport_types": ["Ride"]})

        text_events = [ev.text for ev in events if ev.type == "text_delta"]
        self.assertEqual("".join(text_events), "You rode 150 km this month.")

    def test_stream_timeout_and_network_error(self):
        client = MagicMock()
        client.stream.side_effect = httpx.TimeoutException("Read timed out")
        client.__enter__.return_value = client

        provider = MistralChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatTimeoutError):
            list(provider.stream("mistral-small-latest", "sys", [], "prompt"))

        client.stream.side_effect = httpx.ConnectError("Connection refused")
        with self.assertRaises(ChatProviderUnavailableError):
            list(provider.stream("mistral-small-latest", "sys", [], "prompt"))


if __name__ == "__main__":
    unittest.main()

