"""Mocked unit tests for OllamaChatProvider."""

import json
import unittest
from unittest.mock import MagicMock

import httpx

from kinetiqo.chat.errors import (
    ChatAuthenticationError,
    ChatProviderResponseError,
    ChatProviderUnavailableError,
    ChatRateLimitError,
)
from kinetiqo.chat.models import StreamEvent
from kinetiqo.chat.providers.ollama import OllamaChatProvider


class TestOllamaChatProvider(unittest.TestCase):
    def test_headers_and_base_url_resolution(self):
        # Default without key
        provider = OllamaChatProvider()
        self.assertEqual(provider.base_url, "http://localhost:11434")
        headers = provider._headers()
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("Authorization", headers)

        # Custom LAN host with trailing slash and optional token
        provider_lan = OllamaChatProvider(
            api_key="lan-secret-token",
            base_url="http://192.168.1.150:11434/",
        )
        self.assertEqual(provider_lan.base_url, "http://192.168.1.150:11434")
        lan_headers = provider_lan._headers()
        self.assertEqual(lan_headers["Authorization"], "Bearer lan-secret-token")

    def test_list_models_from_native_api_tags(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "qwen3:1.7b",
                    "model": "qwen3:1.7b",
                    "details": {"parameter_size": "1.7B", "family": "qwen3"},
                },
                {
                    "name": "llama3.1:8b",
                    "model": "llama3.1:8b",
                    "details": {"parameter_size": "8.0B", "family": "llama"},
                },
            ]
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client

        provider = OllamaChatProvider(client_factory=lambda timeout=None: client)
        models = provider.list_models()
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0].id, "qwen3:1.7b")
        self.assertEqual(models[0].display_name, "qwen3:1.7b (1.7B)")
        self.assertEqual(models[1].id, "llama3.1:8b")
        self.assertEqual(models[1].display_name, "llama3.1:8b (8.0B)")

    def test_list_models_fallback_to_v1_models_if_tags_fails(self):
        client = MagicMock()

        def mock_get(url, headers=None):
            if url.endswith("/api/tags"):
                return MagicMock(status_code=404, is_success=False)
            if url.endswith("/v1/models"):
                resp = MagicMock(status_code=200, is_success=True)
                resp.json.return_value = {
                    "data": [
                        {"id": "mistral-nemo:12b"},
                    ]
                }
                return resp
            return MagicMock(status_code=500, is_success=False)

        client.get.side_effect = mock_get
        client.__enter__.return_value = client

        provider = OllamaChatProvider(client_factory=lambda timeout=None: client)
        models = provider.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].id, "mistral-nemo:12b")

    def test_test_connection_success(self):
        client = MagicMock()
        mock_resp = MagicMock(status_code=200, is_success=True)
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "qwen3:1.7b",
                    "details": {"parameter_size": "1.7B"},
                }
            ]
        }
        client.get.return_value = mock_resp
        client.__enter__.return_value = client

        result = OllamaChatProvider.test_connection(
            "http://192.168.1.150:11434",
            client_factory=lambda timeout=None: client,
        )
        self.assertTrue(result["connected"])
        self.assertEqual(result["base_url"], "http://192.168.1.150:11434")
        self.assertEqual(len(result["models"]), 1)
        self.assertEqual(result["models"][0]["id"], "qwen3:1.7b")

    def test_test_connection_network_errors(self):
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__enter__.return_value = client

        with self.assertRaises(ConnectionError) as ctx:
            OllamaChatProvider.test_connection(
                "http://10.0.0.5:11434",
                client_factory=lambda timeout=None: client,
            )
        self.assertIn("OLLAMA_HOST=0.0.0.0:11434", str(ctx.exception))

    def test_raise_for_status_mappings(self):
        provider = OllamaChatProvider()

        # 401 / 403 -> ChatAuthenticationError
        resp_401 = MagicMock(status_code=401, is_success=False)
        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(resp_401)

        resp_403 = MagicMock(status_code=403, is_success=False)
        with self.assertRaises(ChatAuthenticationError):
            provider._raise_for_status(resp_403)

        # 429 -> ChatRateLimitError
        resp_429 = MagicMock(status_code=429, is_success=False)
        with self.assertRaises(ChatRateLimitError):
            provider._raise_for_status(resp_429)

        # 500+ -> ChatProviderUnavailableError
        resp_503 = MagicMock(status_code=503, is_success=False)
        with self.assertRaises(ChatProviderUnavailableError):
            provider._raise_for_status(resp_503)

        # 404 / 400 -> ChatProviderResponseError
        resp_404 = MagicMock(status_code=404, is_success=False)
        with self.assertRaises(ChatProviderResponseError):
            provider._raise_for_status(resp_404)

    def test_stream_single_turn_text(self):
        chunks = [
            "data: " + json.dumps({
                "choices": [{"delta": {"content": "Hello "}, "finish_reason": None}]
            }) + "\n\n",
            "data: " + json.dumps({
                "choices": [{"delta": {"content": "athlete!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }) + "\n\n",
            "data: [DONE]\n\n",
        ]

        client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.iter_lines.return_value = [line.strip() for line in chunks if line.strip()]
        client.stream.return_value.__enter__.return_value = mock_response
        client.__enter__.return_value = client

        provider = OllamaChatProvider(client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="qwen3:1.7b",
            system_instruction="You are an endurance coach.",
            history=[],
            prompt="Hello!",
        ))

        text_events = [e for e in events if e.type == "text_delta"]
        usage_events = [e for e in events if e.type == "usage"]

        self.assertEqual("".join(e.text for e in text_events), "Hello athlete!")
        self.assertEqual(len(usage_events), 1)
        self.assertEqual(usage_events[0].input_tokens, 12)
        self.assertEqual(usage_events[0].output_tokens, 5)

    def test_stream_multi_turn_tool_execution(self):
        # Turn 1: Ollama requests a tool call
        turn1_chunks = [
            "data: " + json.dumps({
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_123",
                            "function": {
                                "name": "kinetiqo_get_weekly_training_profile",
                                "arguments": '{"weeks": 4}',
                            },
                        }]
                    },
                    "finish_reason": "tool_calls",
                }]
            }) + "\n\n",
            "data: [DONE]\n\n",
        ]

        # Turn 2: Final synthesized answer
        turn2_chunks = [
            "data: " + json.dumps({
                "choices": [{
                    "delta": {"content": "You trained 6.5 hours this week."},
                    "finish_reason": "stop",
                }]
            }) + "\n\n",
            "data: [DONE]\n\n",
        ]

        client = MagicMock()
        mock_resp1 = MagicMock(status_code=200, is_success=True)
        mock_resp1.iter_lines.return_value = [l.strip() for l in turn1_chunks if l.strip()]

        mock_resp2 = MagicMock(status_code=200, is_success=True)
        mock_resp2.iter_lines.return_value = [l.strip() for l in turn2_chunks if l.strip()]

        # Stream context manager returns turn 1 first, then turn 2
        stream_ctx1 = MagicMock()
        stream_ctx1.__enter__.return_value = mock_resp1
        stream_ctx2 = MagicMock()
        stream_ctx2.__enter__.return_value = mock_resp2
        client.stream.side_effect = [stream_ctx1, stream_ctx2]
        client.__enter__.return_value = client

        mock_executor = MagicMock(return_value=({"total_hours": 6.5}, 45))

        provider = OllamaChatProvider(client_factory=lambda timeout=None: client)
        events = list(provider.stream(
            model_id="qwen2.5:7b-instruct",
            system_instruction="Coach",
            history=[],
            prompt="What is my weekly volume?",
            tools=[{"type": "function", "function": {"name": "kinetiqo_get_weekly_training_profile"}}],
            tool_executor=mock_executor,
        ))

        mock_executor.assert_called_once_with("kinetiqo_get_weekly_training_profile", {"weeks": 4})
        text_events = [e for e in events if e.type == "text_delta"]
        tool_call_events = [e for e in events if e.type == "tool_call"]
        tool_result_events = [e for e in events if e.type == "tool_result"]

        self.assertEqual(len(tool_call_events), 1)
        self.assertEqual(tool_call_events[0].tool, "kinetiqo_get_weekly_training_profile")
        self.assertEqual(len(tool_result_events), 1)
        self.assertEqual("".join(e.text for e in text_events), "You trained 6.5 hours this week.")


if __name__ == "__main__":
    unittest.main()
