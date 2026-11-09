"""Mocked unit tests for PayPerQChatProvider."""

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
from kinetiqo.chat.providers.payperq import PayPerQChatProvider


class TestPayPerQChatProvider(unittest.TestCase):
    def test_headers_include_bearer_and_user_agent(self):
        provider = PayPerQChatProvider("test-payperq-key")
        headers = provider._headers()
        self.assertEqual(headers["Authorization"], "Bearer test-payperq-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("User-Agent", headers)

    def test_list_models_discovers_from_endpoint_and_falls_back_on_error(self):
        # 1. Success from endpoint
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "data": [
                {"id": "openai/gpt-4o", "name": "GPT-4o", "context_length": 128000},
                {"id": "auto", "name": "Smart Router (Auto)", "context_length": 128000},
                {"id": "text-embedding-3-small", "name": "Embedding", "type": "embedding"},
            ]
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = PayPerQChatProvider("test-key", client_factory=lambda timeout=None: client)

        models = provider.list_models()
        self.assertEqual(len(models), 2)
        # Verify auto is sorted first and embedding is excluded
        self.assertEqual(models[0].id, "auto")
        self.assertEqual(models[1].id, "openai/gpt-4o")

        # 2. Network error falls back to curated defaults
        fail_client = MagicMock()
        fail_client.get.side_effect = httpx.ConnectError("Network unreachable")
        fail_client.__enter__.return_value = fail_client
        fallback_provider = PayPerQChatProvider("test-key", client_factory=lambda timeout=None: fail_client)

        fallback_models = fallback_provider.list_models()
        self.assertTrue(len(fallback_models) >= 2)
        self.assertEqual(fallback_models[0].id, "auto")

        # 3. 401 raises ChatAuthenticationError
        auth_client = MagicMock()
        auth_resp = MagicMock(status_code=401, is_success=False)
        auth_client.get.return_value = auth_resp
        auth_client.__enter__.return_value = auth_client
        auth_provider = PayPerQChatProvider("bad-key", client_factory=lambda timeout=None: auth_client)
        with self.assertRaises(ChatAuthenticationError):
            auth_provider.list_models()

    def test_raise_for_status_mappings(self):
        provider = PayPerQChatProvider("key")

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

    def test_validate_credentials_calls_models_endpoint(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = PayPerQChatProvider("key", client_factory=lambda timeout=None: client)

        provider.validate_credentials()
        client.get.assert_called_once()
        call_url = client.get.call_args[0][0]
        self.assertIn("/models", call_url)

    def test_validate_model_direct_endpoint_success(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "id": "auto",
            "name": "Smart Router (Auto)",
            "context_window": 128000,
            "tags": ["tool-use", "vision", "router"],
            "supported_parameters": ["tools", "tool_choice"],
            "modalities": {"input": ["text", "image"], "output": ["text"]},
            "type": "language",
            "description": "Smart Router auto model",
            "pricing": {"input": "0.000001", "output": "0.000002"},
            "max_output_tokens": 8192,
            "rate_limits": {"requests_per_minute": 60},
            "request_limits": {"max_input_tokens": 128000},
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = PayPerQChatProvider("key", client_factory=lambda timeout=None: client)

        result = provider.validate_model("auto")
        self.assertEqual(result["id"], "auto")
        self.assertEqual(result["display_name"], "Smart Router (Auto)")
        self.assertEqual(result["context_length"], 128000)
        self.assertTrue(result["supports_tools"])
        self.assertTrue(result["supports_vision"])

    def test_validate_model_catalog_fallback_success(self):
        client = MagicMock()
        # Direct lookup fails with 404
        direct_resp = MagicMock(status_code=404, is_success=False)
        direct_resp.json.return_value = {"error": "Not found"}

        # Catalog query returns list with matching model
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {
            "data": [
                {
                    "id": "deepseek/deepseek-r1",
                    "name": "DeepSeek R1",
                    "context_length": 64000,
                    "supported_parameters": ["tools"],
                }
            ]
        }
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client
        provider = PayPerQChatProvider("key", client_factory=lambda timeout=None: client)

        result = provider.validate_model("deepseek/deepseek-r1")
        self.assertEqual(result["id"], "deepseek/deepseek-r1")
        self.assertEqual(result["context_length"], 64000)

    def test_validate_model_embedding_rejected(self):
        provider = PayPerQChatProvider("key")
        with self.assertRaises(ValueError) as ctx:
            provider.validate_model("text-embedding-3-small")
        self.assertIn("embedding", str(ctx.exception).lower())

    def test_validate_model_not_found_raises_lookup_error(self):
        client = MagicMock()
        direct_resp = MagicMock(status_code=404, is_success=False)
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {"data": [{"id": "auto"}, {"id": "deepseek/deepseek-r1"}]}
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client
        provider = PayPerQChatProvider("key", client_factory=lambda timeout=None: client)

        with self.assertRaises(LookupError):
            provider.validate_model("nonexistent-model-xyz")

    def test_stream_text_deltas(self):
        client = MagicMock()
        stream_resp = MagicMock(is_success=True)
        stream_resp.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " athlete!"}}]}',
            'data: {"usage": {"prompt_tokens": 12, "completion_tokens": 4}}',
            "data: [DONE]",
        ]
        client.stream.return_value.__enter__.return_value = stream_resp
        client.__enter__.return_value = client

        provider = PayPerQChatProvider("key", client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="auto",
            system_instruction="You are a coach.",
            history=[],
            prompt="Hi",
        ))

        text_events = [e for e in events if e.type == "text_delta"]
        usage_events = [e for e in events if e.type == "usage"]

        self.assertEqual(len(text_events), 2)
        self.assertEqual(text_events[0].text, "Hello")
        self.assertEqual(text_events[1].text, " athlete!")
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0].input_tokens, 12)
        self.assertEqual(usage_events[0].output_tokens, 4)

    def test_stream_multi_turn_tool_calling(self):
        client = MagicMock()

        # Turn 1: Model calls a tool
        stream_resp_1 = MagicMock(is_success=True)
        stream_resp_1.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "kinetiqo_get_ftp_history", "arguments": "{}"}}]}}]}',
            "data: [DONE]",
        ]

        # Turn 2: Model answers after tool execution
        stream_resp_2 = MagicMock(is_success=True)
        stream_resp_2.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"content": "Your FTP is 280W."}}]}',
            'data: {"usage": {"prompt_tokens": 50, "completion_tokens": 10}}',
            "data: [DONE]",
        ]

        client.stream.return_value.__enter__.side_effect = [stream_resp_1, stream_resp_2]
        client.__enter__.return_value = client

        def dummy_executor(name, args):
            return ({"current_ftp": 280}, 200)

        provider = PayPerQChatProvider("key", client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="auto",
            system_instruction="System",
            history=[],
            prompt="What is my FTP?",
            tools=[{"type": "function", "function": {"name": "kinetiqo_get_ftp_history"}}],
            tool_executor=dummy_executor,
        ))

        event_types = [e.type for e in events]
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("text_delta", event_types)
        self.assertIn("usage", event_types)

        text_content = "".join(e.text for e in events if e.type == "text_delta")
        self.assertEqual(text_content, "Your FTP is 280W.")

    def test_stream_timeout_and_network_errors(self):
        # Timeout error
        client_timeout = MagicMock()
        client_timeout.stream.side_effect = httpx.TimeoutException("Timed out")
        client_timeout.__enter__.return_value = client_timeout
        provider = PayPerQChatProvider("key", client_factory=lambda timeout=None: client_timeout)

        with self.assertRaises(ChatTimeoutError):
            list(provider.stream(
                model_id="auto",
                system_instruction="Sys",
                history=[],
                prompt="Test",
            ))

        # Network error
        client_net = MagicMock()
        client_net.stream.side_effect = httpx.ConnectError("Network fail")
        client_net.__enter__.return_value = client_net
        provider_net = PayPerQChatProvider("key", client_factory=lambda timeout=None: client_net)

        with self.assertRaises(ChatProviderUnavailableError):
            list(provider_net.stream(
                model_id="auto",
                system_instruction="Sys",
                history=[],
                prompt="Test",
            ))


if __name__ == "__main__":
    unittest.main()

