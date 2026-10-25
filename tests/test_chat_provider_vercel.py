"""Mocked unit tests for VercelChatProvider."""

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
from kinetiqo.chat.providers.vercel import VercelChatProvider


class TestVercelChatProvider(unittest.TestCase):
    def test_headers_include_bearer_and_user_agent(self):
        provider = VercelChatProvider("test-vercel-key")
        headers = provider._headers()
        self.assertEqual(headers["Authorization"], "Bearer test-vercel-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("User-Agent", headers)

    def test_list_models_returns_configured_models_or_fallback(self):
        # Empty configured models -> fallback to curated defaults
        provider = VercelChatProvider("key", configured_models=[])
        fallback = provider.list_models()
        self.assertTrue(len(fallback) > 0)
        self.assertTrue(any("kimi-k2.6" in m.id for m in fallback))
        self.assertTrue(any("llama-3.3" in m.id for m in fallback))

        # Explicit configured models
        cfg = [
            {"id": "moonshotai/kimi-k2.6", "name": "Kimi K2.6", "context_length": 262000},
            {"id": "meta/llama-3.3-70b", "name": "Llama 3.3 70B", "context_length": 131072},
        ]
        provider = VercelChatProvider("key", configured_models=cfg)
        models = provider.list_models()
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0].id, "moonshotai/kimi-k2.6")
        self.assertEqual(models[0].display_name, "Kimi K2.6")
        self.assertEqual(models[1].id, "meta/llama-3.3-70b")

    def test_raise_for_status_mappings(self):
        provider = VercelChatProvider("key")

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

    def test_validate_model_direct_endpoint_success(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "id": "moonshotai/kimi-k2.6",
            "name": "Kimi K2.6",
            "context_window": 262000,
            "tags": ["tool-use", "vision", "reasoning"],
            "supported_parameters": ["tools", "tool_choice"],
            "modalities": {"input": ["text", "image"], "output": ["text"]},
            "type": "language",
            "description": "Kimi K2.6 model",
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client
        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)

        result = provider.validate_model("moonshotai/kimi-k2.6")
        self.assertEqual(result["id"], "moonshotai/kimi-k2.6")
        self.assertEqual(result["display_name"], "Kimi K2.6")
        self.assertEqual(result["context_length"], 262000)
        self.assertTrue(result["supports_tools"])
        self.assertTrue(result["supports_vision"])
        self.assertFalse(result["is_embedding"])

    def test_validate_model_catalog_fallback_success(self):
        client = MagicMock()
        # Direct lookup returns 404
        direct_resp = MagicMock(status_code=404, is_success=False)
        # Catalog lookup returns 200 with data list
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {
            "data": [
                {
                    "id": "meta/llama-3.3-70b",
                    "name": "Llama 3.3 70B",
                    "context_window": 131072,
                    "supported_parameters": ["tools"],
                    "tags": ["open-weights"],
                    "modalities": {"input": ["text"], "output": ["text"]},
                }
            ]
        }
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client
        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)

        result = provider.validate_model("meta/llama-3.3-70b")
        self.assertEqual(result["id"], "meta/llama-3.3-70b")
        self.assertEqual(result["context_length"], 131072)
        self.assertTrue(result["supports_tools"])
        self.assertFalse(result["supports_vision"])

    def test_validate_model_suggests_canonical_when_prefix_omitted(self):
        client = MagicMock()
        direct_resp = MagicMock(status_code=404, is_success=False)
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {
            "data": [
                {
                    "id": "moonshotai/kimi-k2.6",
                    "name": "Kimi K2.6",
                    "context_window": 262000,
                }
            ]
        }
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client
        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)

        with self.assertRaises(LookupError) as ctx:
            provider.validate_model("kimi-k2.6")

        self.assertIn("Did you mean 'moonshotai/kimi-k2.6'?", str(ctx.exception))
        self.assertEqual(getattr(ctx.exception, "suggestion", None), "moonshotai/kimi-k2.6")

    def test_validate_model_rejects_embedding_model(self):
        provider = VercelChatProvider("key")
        with self.assertRaises(ValueError) as ctx:
            provider.validate_model("openai/text-embedding-3-small")
        self.assertIn("embedding model", str(ctx.exception))

    def test_validate_empty_model_raises_value_error(self):
        provider = VercelChatProvider("key")
        with self.assertRaises(ValueError):
            provider.validate_model("   ")

    def test_validate_model_not_found_raises_lookup_error(self):
        client = MagicMock()
        direct_resp = MagicMock(status_code=404, is_success=False)
        cat_resp = MagicMock(status_code=200, is_success=True)
        cat_resp.json.return_value = {"data": []}
        client.get.side_effect = [direct_resp, cat_resp]
        client.__enter__.return_value = client

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(LookupError):
            provider.validate_model("nonexistent/model")

    def test_stream_yields_text_deltas_and_usage(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "Why is the sky "}}]}',
            'data: {"choices": [{"delta": {"content": "blue? Rayleigh scattering!"}}]}',
            'data: {"usage": {"prompt_tokens": 12, "completion_tokens": 8}}',
            "data: [DONE]",
        ]

        stream_resp = MagicMock(status_code=200, is_success=True)
        stream_resp.iter_lines.return_value = lines

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = stream_resp

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)

        events = list(provider.stream(
            model_id="moonshotai/kimi-k2.6",
            system_instruction="You are a coach.",
            history=[],
            prompt="Why is the sky blue?",
        ))

        text_events = [e for e in events if e.type == "text_delta"]
        usage_events = [e for e in events if e.type == "usage"]

        self.assertEqual(len(text_events), 2)
        self.assertEqual(text_events[0].text, "Why is the sky ")
        self.assertEqual(text_events[1].text, "blue? Rayleigh scattering!")
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0].input_tokens, 12)
        self.assertEqual(usage_events[0].output_tokens, 8)

    def test_stream_multi_turn_tool_execution(self):
        # Turn 1: model calls tool 'kinetiqo_get_training_goals'
        turn1_lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_v1", "function": {"name": "kinetiqo_get_training_goals", "arguments": "{}"}}]}}]}',
            "data: [DONE]",
        ]
        # Turn 2: model outputs final text based on tool result
        turn2_lines = [
            'data: {"choices": [{"delta": {"content": "Your weekly goal is 150km."}}]}',
            'data: {"usage": {"prompt_tokens": 40, "completion_tokens": 9}}',
            "data: [DONE]",
        ]

        resp1 = MagicMock(status_code=200, is_success=True)
        resp1.iter_lines.return_value = turn1_lines

        resp2 = MagicMock(status_code=200, is_success=True)
        resp2.iter_lines.return_value = turn2_lines

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.side_effect = [resp1, resp2]

        tool_executor = MagicMock(return_value=({"goals": [{"type": "Cycling", "distance_km": 150}]}, 20))

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)

        events = list(provider.stream(
            model_id="moonshotai/kimi-k2.6",
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
        self.assertEqual(text_events[0].text, "Your weekly goal is 150km.")

    def test_stream_network_error_raises_unavailable(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.side_effect = httpx.RequestError("Connection failed")

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatProviderUnavailableError):
            list(provider.stream("moonshotai/kimi-k2.6", "sys", [], "hi"))

    def test_stream_timeout_raises_timeout(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.side_effect = httpx.TimeoutException("Read timed out")

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatTimeoutError):
            list(provider.stream("moonshotai/kimi-k2.6", "sys", [], "hi"))

    def test_stream_403_forbidden_raises_auth_error_with_body_detail(self):
        err_payload = json.dumps({
            "error": {
                "code": "customer_verification_required",
                "message": "Payment method required to access Moonshot AI models on Vercel AI Gateway",
            }
        }).encode("utf-8")
        resp = MagicMock(status_code=403, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatAuthenticationError) as ctx:
            list(provider.stream("moonshotai/kimi-k3", "sys", [], "hi"))

        self.assertIn("Payment method required", str(ctx.exception))
        self.assertIn("HTTP 403", str(ctx.exception))

    def test_stream_402_payment_required_raises_rate_limit_error(self):
        err_payload = json.dumps({"error": {"message": "Credit balance exhausted"}}).encode("utf-8")
        resp = MagicMock(status_code=402, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatRateLimitError) as ctx:
            list(provider.stream("moonshotai/kimi-k2.6", "sys", [], "hi"))

        self.assertIn("Credit balance exhausted", str(ctx.exception))

    def test_stream_429_rate_limit_raises_rate_limit_error(self):
        err_payload = json.dumps({"error": {"message": "Concurrency limit reached"}}).encode("utf-8")
        resp = MagicMock(status_code=429, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatRateLimitError) as ctx:
            list(provider.stream("moonshotai/kimi-k2.6", "sys", [], "hi"))

        self.assertIn("Concurrency limit reached", str(ctx.exception))

    def test_stream_500_server_error_raises_unavailable(self):
        resp = MagicMock(status_code=500, is_success=False)
        resp.read.return_value = b"Internal Server Error"

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatProviderUnavailableError):
            list(provider.stream("moonshotai/kimi-k2.6", "sys", [], "hi"))

    def test_stream_400_bad_request_raises_response_error(self):
        err_payload = json.dumps({"error": {"message": "Invalid temperature parameter"}}).encode("utf-8")
        resp = MagicMock(status_code=400, is_success=False)
        resp.read.return_value = err_payload

        client = MagicMock()
        client.__enter__.return_value = client
        client.stream.return_value.__enter__.return_value = resp

        provider = VercelChatProvider("key", client_factory=lambda timeout=None: client)
        with self.assertRaises(ChatProviderResponseError) as ctx:
            list(provider.stream("moonshotai/kimi-k2.6", "sys", [], "hi"))

        self.assertIn("Invalid temperature parameter", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
