"""Mocked unit tests for AnthropicChatProvider."""

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
from kinetiqo.chat.providers.anthropic import AnthropicChatProvider


class TestAnthropicChatProvider(unittest.TestCase):
    def test_headers_include_x_api_key_and_anthropic_version(self):
        provider = AnthropicChatProvider("test-anthropic-key")
        headers = provider._headers()
        self.assertEqual(headers["x-api-key"], "test-anthropic-key")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["User-Agent"], "Kinetiqo-Fitness-AI")

    def test_list_models_discovers_chat_models_and_filters_deprecated(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "data": [
                {
                    "type": "model",
                    "id": "claude-2.0",
                    "display_name": "Claude 2.0 (Deprecated)",
                },
                {
                    "type": "model",
                    "id": "claude-instant-1.2",
                    "display_name": "Claude Instant 1.2 (Deprecated)",
                },
                {
                    "type": "model",
                    "id": "claude-3-5-sonnet-20241022",
                    "display_name": "Claude 3.5 Sonnet",
                },
                {
                    "type": "model",
                    "id": "claude-3-7-sonnet-20250219",
                    "display_name": "Claude 3.7 Sonnet",
                },
                {
                    "type": "model",
                    "id": "claude-3-5-haiku-20241022",
                    "display_name": "Claude 3.5 Haiku",
                },
                {
                    "type": "model",
                    "id": "claude-3-opus-20240229",
                    "display_name": "Claude 3 Opus",
                },
            ],
            "has_more": False,
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client

        provider = AnthropicChatProvider("key", client_factory=lambda timeout=None: client)
        models = provider.list_models()

        model_ids = [m.id for m in models]
        self.assertNotIn("claude-2.0", model_ids)
        self.assertNotIn("claude-instant-1.2", model_ids)

        self.assertIn("claude-3-7-sonnet-20250219", model_ids)
        self.assertIn("claude-3-5-sonnet-20241022", model_ids)
        self.assertIn("claude-3-5-haiku-20241022", model_ids)
        self.assertIn("claude-3-opus-20240229", model_ids)

        # Ranked by preferred models: 3-7 Sonnet before 3-5 Sonnet before Haiku
        idx_37 = model_ids.index("claude-3-7-sonnet-20250219")
        idx_35 = model_ids.index("claude-3-5-sonnet-20241022")
        idx_haiku = model_ids.index("claude-3-5-haiku-20241022")
        self.assertLess(idx_37, idx_35)
        self.assertLess(idx_35, idx_haiku)

        # Capabilities and context
        sonnet = next(m for m in models if m.id == "claude-3-5-sonnet-20241022")
        self.assertTrue(sonnet.supports_tools)
        self.assertTrue(sonnet.supports_vision)
        self.assertEqual(sonnet.context_length, 200000)
        self.assertEqual(sonnet.max_output_tokens, 8192)

    def test_list_models_fallback_on_network_error(self):
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__enter__.return_value = client

        provider = AnthropicChatProvider("key", client_factory=lambda timeout=None: client)
        models = provider.list_models()
        self.assertGreater(len(models), 0)
        ids = [m.id for m in models]
        self.assertIn("claude-3-5-sonnet-20241022", ids)

    def test_raise_for_status_mappings(self):
        provider = AnthropicChatProvider("key")

        # 401 -> ChatAuthenticationError
        resp_401 = MagicMock(status_code=401, is_success=False)
        resp_401.read.return_value = b'{"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}'
        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(resp_401)

        # 403 -> ChatAuthenticationError
        resp_403 = MagicMock(status_code=403, is_success=False)
        resp_403.read.return_value = b'{"type": "error", "error": {"type": "permission_error", "message": "Forbidden"}}'
        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(resp_403)

        # 429 -> ChatRateLimitError
        resp_429 = MagicMock(status_code=429, is_success=False)
        resp_429.read.return_value = b'{"type": "error", "error": {"type": "rate_limit_error", "message": "Rate limit exceeded"}}'
        with self.assertRaises(ChatRateLimitError):
            provider._raise_for_status(resp_429)

        # 400 with credit balance -> ChatRateLimitError
        resp_credit = MagicMock(status_code=400, is_success=False)
        resp_credit.read.return_value = b'{"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low"}}'
        with self.assertRaises(ChatRateLimitError):
            provider._raise_for_status(resp_credit)

        # 529 -> ChatProviderUnavailableError (Anthropic Overloaded)
        resp_529 = MagicMock(status_code=529, is_success=False)
        resp_529.read.return_value = b'{"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}'
        with self.assertRaises(ChatProviderUnavailableError):
            provider._raise_for_status(resp_529)

        # 500 -> ChatProviderUnavailableError
        resp_500 = MagicMock(status_code=500, is_success=False)
        resp_500.read.return_value = b'Internal Server Error'
        with self.assertRaises(ChatProviderUnavailableError):
            provider._raise_for_status(resp_500)

        # 400 generic -> ChatProviderResponseError
        resp_400 = MagicMock(status_code=400, is_success=False)
        resp_400.read.return_value = b'{"type": "error", "error": {"message": "Invalid parameter"}}'
        with self.assertRaises(ChatProviderResponseError):
            provider._raise_for_status(resp_400)

    def test_validate_model(self):
        provider = AnthropicChatProvider("key")

        # Empty model
        with self.assertRaises(ValueError):
            provider.validate_model("  ")

        # Deprecated model
        with self.assertRaises(ValueError):
            provider.validate_model("claude-2.0")

        # Known default model
        info = provider.validate_model("claude-3-5-sonnet-20241022")
        self.assertEqual(info["id"], "claude-3-5-sonnet-20241022")
        self.assertTrue(info["supports_tools"])
        self.assertTrue(info["supports_vision"])
        self.assertEqual(info["context_length"], 200000)

        # Custom claude model prefix
        info_custom = provider.validate_model("claude-3-something-future")
        self.assertEqual(info_custom["id"], "claude-3-something-future")

    def test_stream_text_deltas(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.iter_lines.return_value = [
            "event: message_start",
            "data: " + json.dumps({
                "type": "message_start",
                "message": {"id": "msg_1", "usage": {"input_tokens": 15, "output_tokens": 1}},
            }),
            "event: content_block_start",
            "data: " + json.dumps({
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }),
            "event: content_block_delta",
            "data: " + json.dumps({
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hello"},
            }),
            "event: content_block_delta",
            "data: " + json.dumps({
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": " from Claude!"},
            }),
            "event: message_delta",
            "data: " + json.dumps({
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 6},
            }),
            "event: message_stop",
            "data: " + json.dumps({"type": "message_stop"}),
        ]
        client.stream.return_value.__enter__.return_value = mock_resp
        client.__enter__.return_value = client

        provider = AnthropicChatProvider("key", client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="claude-3-5-sonnet-20241022",
            system_instruction="You are a coach.",
            history=[],
            prompt="Hi",
        ))

        texts = [ev.text for ev in events if ev.type == "text_delta"]
        self.assertEqual("".join(texts), "Hello from Claude!")

        usage_events = [ev for ev in events if ev.type == "usage"]
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0].input_tokens, 15)
        self.assertEqual(usage_events[0].output_tokens, 6)

    def test_stream_tool_calling_loop(self):
        client = MagicMock()

        # Turn 1: model calls kinetiqo_get_activity_totals
        turn1_resp = MagicMock(status_code=200, is_success=True)
        turn1_resp.iter_lines.return_value = [
            "event: message_start",
            "data: " + json.dumps({
                "type": "message_start",
                "message": {"id": "msg_turn1", "usage": {"input_tokens": 20, "output_tokens": 1}},
            }),
            "event: content_block_start",
            "data: " + json.dumps({
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_abc123",
                    "name": "kinetiqo_get_activity_totals",
                    "input": {},
                },
            }),
            "event: content_block_delta",
            "data: " + json.dumps({
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"sport_types": ["Ride"]}',
                },
            }),
            "event: content_block_stop",
            "data: " + json.dumps({"type": "content_block_stop", "index": 0}),
            "event: message_delta",
            "data: " + json.dumps({
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 15},
            }),
            "event: message_stop",
            "data: " + json.dumps({"type": "message_stop"}),
        ]

        # Turn 2: model answers with text synthesis
        turn2_resp = MagicMock(status_code=200, is_success=True)
        turn2_resp.iter_lines.return_value = [
            "event: message_start",
            "data: " + json.dumps({
                "type": "message_start",
                "message": {"id": "msg_turn2", "usage": {"input_tokens": 45, "output_tokens": 1}},
            }),
            "event: content_block_start",
            "data: " + json.dumps({
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }),
            "event: content_block_delta",
            "data: " + json.dumps({
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "You rode 150 km this month."},
            }),
            "event: message_delta",
            "data: " + json.dumps({
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 12},
            }),
            "event: message_stop",
            "data: " + json.dumps({"type": "message_stop"}),
        ]

        responses = [turn1_resp, turn2_resp]
        client.stream.side_effect = lambda method, url, **kwargs: MagicMock(
            __enter__=lambda s: responses.pop(0),
            __exit__=lambda s, *args: None,
        )
        client.__enter__.return_value = client

        tool_exec_mock = MagicMock(return_value=({"distance_km": 150.0}, 2))

        provider = AnthropicChatProvider("key", client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="claude-3-5-sonnet-20241022",
            system_instruction="You are a coach.",
            history=[],
            prompt="What are my totals?",
            tools=[{
                "name": "kinetiqo_get_activity_totals",
                "description": "Get totals",
                "input_schema": {"type": "object", "properties": {"sport_types": {"type": "array"}}},
            }],
            tool_executor=tool_exec_mock,
        ))

        tool_calls = [ev for ev in events if ev.type == "tool_call"]
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].tool, "kinetiqo_get_activity_totals")
        self.assertEqual(tool_calls[0].arguments, {"sport_types": ["Ride"]})

        tool_results = [ev for ev in events if ev.type == "tool_result"]
        self.assertEqual(len(tool_results), 1)
        self.assertEqual(tool_results[0].tool_data, {"distance_km": 150.0})

        texts = [ev.text for ev in events if ev.type == "text_delta"]
        self.assertEqual("".join(texts), "You rode 150 km this month.")

    def test_stream_handles_timeout_and_network_error(self):
        client = MagicMock()
        client.stream.side_effect = httpx.TimeoutException("Timed out")
        client.__enter__.return_value = client

        provider = AnthropicChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatTimeoutError):
            list(provider.stream("claude-3-5-sonnet-20241022", "sys", [], "hi"))

        client.stream.side_effect = httpx.ConnectError("Network error")
        with self.assertRaises(ChatProviderUnavailableError):
            list(provider.stream("claude-3-5-sonnet-20241022", "sys", [], "hi"))


if __name__ == "__main__":
    unittest.main()

