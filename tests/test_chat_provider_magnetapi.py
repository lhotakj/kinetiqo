"""Mocked unit tests for MagnetAPIChatProvider."""

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
from kinetiqo.chat.providers.magnetapi import MagnetAPIChatProvider


class TestMagnetAPIChatProvider(unittest.TestCase):
    def test_headers_include_bearer_and_user_agent(self):
        provider = MagnetAPIChatProvider("test-magnetapi-key")
        headers = provider._headers()
        self.assertEqual(headers["Authorization"], "Bearer test-magnetapi-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("User-Agent", headers)

    def test_list_models_discovers_from_endpoint_and_falls_back_on_error(self):
        # 1. Success from endpoint
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "data": [
                {"id": "deepseek-flash", "name": "DeepSeek Flash", "context_window": 128000},
                {"id": "power-ai", "name": "Power AI", "context_window": 200000},
                {"id": "text-embedding-3-small", "name": "Embedding", "type": "embedding"},
            ]
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = MagnetAPIChatProvider("test-key", client_factory=lambda timeout=None: client)

        models = provider.list_models()
        self.assertEqual(len(models), 2)
        # Verify power-ai is sorted first and embedding is excluded
        self.assertEqual(models[0].id, "power-ai")
        self.assertEqual(models[1].id, "deepseek-flash")

        # 2. Network error falls back to curated defaults
        fail_client = MagicMock()
        fail_client.get.side_effect = httpx.ConnectError("Network unreachable")
        fail_client.__enter__.return_value = fail_client
        fallback_provider = MagnetAPIChatProvider("test-key", client_factory=lambda timeout=None: fail_client)
        fallback = fallback_provider.list_models()
        self.assertTrue(len(fallback) > 0)
        self.assertTrue(any("power-ai" in m.id for m in fallback))
        self.assertTrue(any("gpt-6.1-sol" in m.id for m in fallback))

    def test_raise_for_status_mappings(self):
        provider = MagnetAPIChatProvider("key")

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

    def test_validate_credentials_success(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)

        provider.validate_credentials()
        client.get.assert_called_once_with(
            "https://api.magnetapi.org/v1/models",
            headers=provider._headers(),
        )

    def test_validate_model_direct_endpoint_success(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "id": "power-ai",
            "name": "Power AI",
            "context_window": 200000,
            "tags": ["tool-use", "vision", "reasoning"],
            "supported_parameters": ["tools", "tool_choice"],
            "modalities": {"input": ["text", "image"], "output": ["text"]},
            "type": "language",
            "description": "High-performance auto-managed model",
            "pricing": {"input": "0.000001", "output": "0.000002"},
            "max_output_tokens": 8192,
            "rate_limits": {"requests_per_minute": 60},
            "request_limits": {"max_input_tokens": 128000},
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)

        result = provider.validate_model("power-ai")
        self.assertEqual(result["id"], "power-ai")
        self.assertEqual(result["display_name"], "Power AI")
        self.assertEqual(result["context_length"], 200000)
        self.assertTrue(result["supports_tools"])
        self.assertTrue(result["supports_vision"])
        self.assertFalse(result["is_embedding"])
        self.assertEqual(result["pricing"], {"input": "0.000001", "output": "0.000002"})
        self.assertEqual(result["max_output_tokens"], 8192)
        self.assertEqual(result["rate_limits"], {"requests_per_minute": 60})
        self.assertEqual(result["request_limits"], {"max_input_tokens": 128000})
        self.assertEqual(result["description"], "High-performance auto-managed model")

    def test_validate_model_catalog_fallback_success(self):
        client = MagicMock()
        # Direct lookup returns 404
        direct_resp = MagicMock(status_code=404, is_success=False)
        # Catalog lookup returns 200 with data list
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {
            "data": [
                {
                    "id": "deepseek-flash",
                    "name": "DeepSeek Flash",
                    "context_window": 128000,
                    "supported_parameters": ["tools"],
                    "tags": ["coding"],
                    "modalities": {"input": ["text"], "output": ["text"]},
                }
            ]
        }
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client
        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)

        result = provider.validate_model("deepseek-flash")
        self.assertEqual(result["id"], "deepseek-flash")
        self.assertEqual(result["context_length"], 128000)
        self.assertTrue(result["supports_tools"])
        self.assertFalse(result["supports_vision"])

    def test_validate_model_suggests_canonical_when_prefix_omitted(self):
        client = MagicMock()
        direct_resp = MagicMock(status_code=404, is_success=False)
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {
            "data": [
                {
                    "id": "gpt-6.1-sol",
                    "name": "ChatGPT 6.1 SOL",
                    "context_window": 200000,
                }
            ]
        }
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client
        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)

        with self.assertRaises(LookupError) as ctx:
            provider.validate_model("sol")

        self.assertIn("Did you mean 'gpt-6.1-sol'?", str(ctx.exception))
        self.assertEqual(getattr(ctx.exception, "suggestion", None), "gpt-6.1-sol")

    def test_validate_model_rejects_embedding_model(self):
        provider = MagnetAPIChatProvider("key")
        with self.assertRaises(ValueError) as ctx:
            provider.validate_model("text-embedding-3-small")
        self.assertIn("embedding model", str(ctx.exception))

    def test_validate_empty_model_raises_value_error(self):
        provider = MagnetAPIChatProvider("key")
        with self.assertRaises(ValueError):
            provider.validate_model("   ")

    def test_validate_model_not_found_raises_lookup_error(self):
        client = MagicMock()
        direct_resp = MagicMock(status_code=404, is_success=False)
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {"data": []}
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(LookupError):
            provider.validate_model("nonexistent/model")

    def test_stream_yields_text_deltas_and_usage(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "Training consistency is "}}]}',
            'data: {"choices": [{"delta": {"content": "the key to progressive overload!"}}]}',
            'data: {"usage": {"prompt_tokens": 15, "completion_tokens": 10}}',
            "data: [DONE]",
        ]

        stream_resp = MagicMock(status_code=200, is_success=True)
        stream_resp.iter_lines.return_value = lines

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = stream_resp

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)

        events = list(provider.stream(
            model_id="power-ai",
            system_instruction="You are a coach.",
            history=[],
            prompt="What is the key to training?",
        ))

        text_events = [e for e in events if e.type == "text_delta"]
        usage_events = [e for e in events if e.type == "usage"]

        self.assertEqual(len(text_events), 2)
        self.assertEqual(text_events[0].text, "Training consistency is ")
        self.assertEqual(text_events[1].text, "the key to progressive overload!")
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0].input_tokens, 15)
        self.assertEqual(usage_events[0].output_tokens, 10)

    def test_stream_multi_turn_tool_execution(self):
        # Turn 1: model calls tool 'kinetiqo_get_training_goals'
        turn1_lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_mag_1", "function": {"name": "kinetiqo_get_training_goals", "arguments": "{}"}}]}}]}',
            "data: [DONE]",
        ]
        # Turn 2: model outputs final text based on tool result
        turn2_lines = [
            'data: {"choices": [{"delta": {"content": "Your weekly distance goal is 200km."}}]}',
            'data: {"usage": {"prompt_tokens": 45, "completion_tokens": 11}}',
            "data: [DONE]",
        ]

        resp1 = MagicMock(status_code=200, is_success=True)
        resp1.iter_lines.return_value = turn1_lines

        resp2 = MagicMock(status_code=200, is_success=True)
        resp2.iter_lines.return_value = turn2_lines

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.side_effect = [resp1, resp2]

        tool_executor = MagicMock(return_value=({"goals": [{"type": "Cycling", "distance_km": 200}]}, 20))

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)

        events = list(provider.stream(
            model_id="power-ai",
            system_instruction="Coach",
            history=[],
            prompt="What are my training goals?",
            tools=[{"type": "function", "function": {"name": "kinetiqo_get_training_goals"}}],
            tool_executor=tool_executor,
        ))

        tool_executor.assert_called_once_with("kinetiqo_get_training_goals", {})

        event_types = [e.type for e in events]
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_result", event_types)
        self.assertIn("text_delta", event_types)
        self.assertIn("usage", event_types)

        text_events = [e for e in events if e.type == "text_delta"]
        self.assertEqual(text_events[0].text, "Your weekly distance goal is 200km.")

    def test_stream_network_error_raises_unavailable(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.side_effect = httpx.RequestError("Connection failed")

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatProviderUnavailableError):
            list(provider.stream("power-ai", "sys", [], "hi"))

    def test_stream_timeout_raises_timeout(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.side_effect = httpx.TimeoutException("Read timed out")

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatTimeoutError):
            list(provider.stream("power-ai", "sys", [], "hi"))

    def test_stream_403_forbidden_raises_auth_error_with_body_detail(self):
        err_payload = json.dumps({
            "detail": "Invalid MagnetAPI System Key or User API Key."
        }).encode("utf-8")
        resp = MagicMock(status_code=403, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatAuthenticationError) as ctx:
            list(provider.stream("power-ai", "sys", [], "hi"))

        self.assertIn("Invalid MagnetAPI System Key", str(ctx.exception))
        self.assertIn("HTTP 403", str(ctx.exception))

    def test_stream_402_payment_required_raises_rate_limit_error(self):
        err_payload = json.dumps({"detail": "No usable credit remains in wallet"}).encode("utf-8")
        resp = MagicMock(status_code=402, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatRateLimitError) as ctx:
            list(provider.stream("power-ai", "sys", [], "hi"))

        self.assertIn("No usable credit remains", str(ctx.exception))

    def test_stream_429_rate_limit_raises_rate_limit_error(self):
        err_payload = json.dumps({"detail": "Concurrency limit reached"}).encode("utf-8")
        resp = MagicMock(status_code=429, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatRateLimitError) as ctx:
            list(provider.stream("power-ai", "sys", [], "hi"))

        self.assertIn("Concurrency limit reached", str(ctx.exception))

    def test_stream_500_server_error_raises_unavailable(self):
        resp = MagicMock(status_code=500, is_success=False)
        resp.read.return_value = b"Internal Server Error"

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatProviderUnavailableError):
            list(provider.stream("power-ai", "sys", [], "hi"))

    def test_stream_400_bad_request_raises_response_error(self):
        err_payload = json.dumps({"detail": "Invalid request parameter"}).encode("utf-8")
        resp = MagicMock(status_code=400, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = MagnetAPIChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatProviderResponseError) as ctx:
            list(provider.stream("power-ai", "sys", [], "hi"))

        self.assertIn("Invalid request parameter", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

