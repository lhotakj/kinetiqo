"""Isolated unit tests for secure chat foundations."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
from kinetiqo.chat.encryption import ChatEncryptionError, decrypt_api_key, encrypt_api_key
from kinetiqo.chat.errors import ChatAuthenticationError, ChatConfigurationError, ChatProviderResponseError, ChatRateLimitError
from kinetiqo.chat.models import ChatMessage, ChatProviderModel
from kinetiqo.chat.providers.gemini import GeminiChatProvider
from kinetiqo.chat.repository import ChatRepository
from kinetiqo.chat.service import ChatService, build_system_instruction


class TestChatEncryption(unittest.TestCase):
    def test_round_trip_uses_distinct_nonces_and_rejects_tampering(self):
        secret = "x" * 32
        first = encrypt_api_key("secret-value", secret)
        second = encrypt_api_key("secret-value", secret)
        self.assertNotEqual(first, second)
        self.assertEqual(decrypt_api_key(first, secret), "secret-value")
        with self.assertRaises(ChatEncryptionError):
            decrypt_api_key(first[:-1] + "A", secret)

    def test_short_secret_fails_closed(self):
        with self.assertRaises(ChatEncryptionError):
            encrypt_api_key("secret", "short")


class TestChatService(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.service = ChatService(self.repository, "x" * 32)

    def test_unconfigured_key_is_rejected_before_provider_creation(self):
        self.repository.get_provider_key.return_value = None
        with self.assertRaises(ChatConfigurationError):
            self.service.models("athlete", "gemini")

    @patch("kinetiqo.chat.service.decrypt_api_key", return_value="key")
    @patch("kinetiqo.chat.service.PROVIDER_REGISTRY")
    def test_persists_prompt_before_provider_stream(self, registry, decrypt):
        session = MagicMock(provider="gemini", model_id="gemini-2.5-flash")
        user = ChatMessage("user-id", "session", "athlete", "user", "hello", 1, "complete", datetime.now(timezone.utc))
        assistant = ChatMessage("assistant-id", "session", "athlete", "assistant", "", 2, "interrupted", datetime.now(timezone.utc))
        self.repository.get_session.return_value = session
        self.repository.add_message.side_effect = [user, assistant]
        self.repository.list_messages.return_value = []
        self.repository.get_provider_key.return_value = "ciphertext"
        provider = MagicMock()
        provider.list_models.return_value = [ChatProviderModel("gemini-available", "Available")]
        provider.stream.return_value = iter([])
        registry.__getitem__.return_value.return_value = provider
        _, events = self.service.stream_turn("athlete", "session", "hello")
        list(events)
        self.assertEqual(self.repository.add_message.call_args_list[0].args[2:4], ("user", "hello"))
        provider.stream.assert_called_once()
        self.repository.update_message.assert_called_once()

    @patch("kinetiqo.chat.service.decrypt_api_key", return_value="key")
    @patch("kinetiqo.chat.service.PROVIDER_REGISTRY")
    def test_unavailable_model_is_replaced_with_provider_catalog_model(self, registry, decrypt):
        session = MagicMock(provider="gemini", model_id="retired-model")
        user = ChatMessage("user-id", "session", "athlete", "user", "hello", 1, "complete", datetime.now(timezone.utc))
        assistant = ChatMessage("assistant-id", "session", "athlete", "assistant", "", 2, "interrupted", datetime.now(timezone.utc))
        self.repository.get_session.return_value = session
        self.repository.add_message.side_effect = [user, assistant]
        self.repository.list_messages.return_value = []
        self.repository.get_provider_key.return_value = "ciphertext"
        provider = MagicMock()
        provider.list_models.return_value = [ChatProviderModel("gemini-live", "Live")]
        provider.stream.return_value = iter([])
        registry.__getitem__.return_value.return_value = provider
        _, events = self.service.stream_turn("athlete", "session", "hello")
        list(events)
        self.assertEqual(provider.stream.call_args.args[0], "gemini-live")

    @patch("kinetiqo.chat.service.decrypt_api_key", return_value="key")
    @patch("kinetiqo.chat.service.PROVIDER_REGISTRY")
    def test_deprecated_model_is_upgraded_to_default_in_stream_turn(self, registry, decrypt):
        session = MagicMock(provider="gemini", model_id="gemini-2.5-flash")
        user = ChatMessage("user-id", "session", "athlete", "user", "hello", 1, "complete", datetime.now(timezone.utc))
        assistant = ChatMessage("assistant-id", "session", "athlete", "assistant", "", 2, "interrupted", datetime.now(timezone.utc))
        self.repository.get_session.return_value = session
        self.repository.add_message.side_effect = [user, assistant]
        self.repository.list_messages.return_value = []
        self.repository.get_provider_key.return_value = "ciphertext"
        provider = MagicMock()
        provider.list_models.return_value = [ChatProviderModel("gemini-3.1-flash-lite", "Flash Lite")]
        provider.stream.return_value = iter([])
        registry.__getitem__.return_value.return_value = provider
        _, events = self.service.stream_turn("athlete", "session", "hello", model_id="gemini-2.5-flash")
        list(events)
        self.assertEqual(provider.stream.call_args.args[0], "gemini-3.1-flash-lite")
        self.repository.update_session.assert_called_with("athlete", "session", model_id="gemini-3.1-flash-lite")

    def test_create_session_uses_provider_default_model(self):
        self.service.create_session("athlete", provider="vercel")
        self.repository.create_session.assert_called_with("athlete", "vercel", "moonshotai/kimi-k2.6")

    @patch("kinetiqo.chat.service.decrypt_api_key", return_value="key")
    @patch("kinetiqo.chat.service.PROVIDER_REGISTRY")
    def test_stream_turn_switches_provider_when_explicitly_requested(self, registry, decrypt):
        session = MagicMock(provider="openrouter", model_id="meta-llama/llama-3.3-70b-instruct")
        user = ChatMessage("user-id", "session", "athlete", "user", "hello", 1, "complete", datetime.now(timezone.utc))
        assistant = ChatMessage("assistant-id", "session", "athlete", "assistant", "", 2, "interrupted", datetime.now(timezone.utc))
        self.repository.get_session.return_value = session
        self.repository.add_message.side_effect = [user, assistant]
        self.repository.list_messages.return_value = []
        self.repository.list_configured_providers.return_value = ["openrouter", "gemini"]
        self.repository.get_provider_key.return_value = "ciphertext"
        self.repository.get_provider_config.return_value = {}

        gemini_provider = MagicMock()
        gemini_provider.list_models.return_value = [ChatProviderModel("gemini-3.1-flash-lite", "Flash Lite")]
        gemini_provider.stream.return_value = iter([])

        registry.__getitem__.side_effect = lambda key: MagicMock(return_value=gemini_provider) if key == "gemini" else MagicMock()

        _, events = self.service.stream_turn(
            "athlete", "session", "hello", model_id="gemini-3.1-flash-lite", provider="gemini"
        )
        list(events)

        gemini_provider.stream.assert_called_once()
        self.assertEqual(gemini_provider.stream.call_args.args[0], "gemini-3.1-flash-lite")
        self.repository.update_session.assert_called_with("athlete", "session", provider="gemini", model_id="gemini-3.1-flash-lite")
        self.assertEqual(self.repository.add_message.call_args_list[1].args[5], "gemini")

    @patch("kinetiqo.chat.service.decrypt_api_key", return_value="key")
    @patch("kinetiqo.chat.service.PROVIDER_REGISTRY")
    def test_stream_turn_switches_provider_automatically_when_model_belongs_to_different_provider(self, registry, decrypt):
        session = MagicMock(provider="openrouter", model_id="meta-llama/llama-3.3-70b-instruct")
        user = ChatMessage("user-id", "session", "athlete", "user", "hello", 1, "complete", datetime.now(timezone.utc))
        assistant = ChatMessage("assistant-id", "session", "athlete", "assistant", "", 2, "interrupted", datetime.now(timezone.utc))
        self.repository.get_session.return_value = session
        self.repository.add_message.side_effect = [user, assistant]
        self.repository.list_messages.return_value = []
        self.repository.list_configured_providers.return_value = ["openrouter", "gemini"]
        self.repository.get_provider_key.return_value = "ciphertext"
        self.repository.get_provider_config.return_value = {}

        openrouter_provider = MagicMock()
        openrouter_provider.list_models.return_value = [ChatProviderModel("meta-llama/llama-3.3-70b-instruct", "Llama 3.3")]

        gemini_provider = MagicMock()
        gemini_provider.list_models.return_value = [ChatProviderModel("gemini-3.1-flash-lite", "Flash Lite")]
        gemini_provider.stream.return_value = iter([])

        def get_prov(name):
            if name == "gemini":
                return MagicMock(return_value=gemini_provider)
            return MagicMock(return_value=openrouter_provider)

        registry.__getitem__.side_effect = get_prov

        # Notice: provider is NOT passed; only model_id is passed
        _, events = self.service.stream_turn(
            "athlete", "session", "hello", model_id="gemini-3.1-flash-lite"
        )
        list(events)

        gemini_provider.stream.assert_called_once()
        self.assertEqual(gemini_provider.stream.call_args.args[0], "gemini-3.1-flash-lite")
        self.repository.update_session.assert_called_with("athlete", "session", provider="gemini", model_id="gemini-3.1-flash-lite")
        self.assertEqual(self.repository.add_message.call_args_list[1].args[5], "gemini")

    def test_message_limit_is_enforced(self):
        with self.assertRaises(ValueError):
            self.service.stream_turn("athlete", "session", "x" * (32 * 1024 + 1))

    @patch("kinetiqo.chat.service.execute_chat_tool", return_value=({"distance_km": 100}, 25))
    @patch("kinetiqo.chat.service.decrypt_api_key", return_value="key")
    @patch("kinetiqo.chat.service.PROVIDER_REGISTRY")
    def test_turn_with_tool_execution_persists_provenance(self, registry, decrypt, mock_exec):
        session = MagicMock(provider="gemini", model_id="gemini-live")
        user = ChatMessage("user-id", "session", "athlete", "user", "hello", 1, "complete", datetime.now(timezone.utc))
        assistant = ChatMessage("assistant-id", "session", "athlete", "assistant", "", 2, "interrupted", datetime.now(timezone.utc))
        self.repository.get_session.return_value = session
        self.repository.add_message.side_effect = [user, assistant]
        self.repository.list_messages.return_value = []
        self.repository.get_provider_key.return_value = "ciphertext"

        def fake_stream(model_id, system_instruction, history, prompt, **kwargs):
            tool_exec = kwargs.get("tool_executor")
            if tool_exec:
                tool_exec("kinetiqo_get_activity_totals", {"sport_types": ["Ride"]})
            from kinetiqo.chat.models import StreamEvent
            yield StreamEvent("text_delta", text="Totals summary")

        provider = MagicMock()
        provider.list_models.return_value = [ChatProviderModel("gemini-live", "Live")]
        provider.stream.side_effect = fake_stream
        registry.__getitem__.return_value.return_value = provider

        _, events = self.service.stream_turn("athlete", "session", "hello")
        list(events)

        self.repository.update_message.assert_called_once()
        update_kwargs = self.repository.update_message.call_args.kwargs
        provenance = update_kwargs.get("tool_provenance")
        self.assertIsNotNone(provenance)
        self.assertIn("kinetiqo_get_activity_totals", provenance)
        self.assertIn('"duration_ms": 25', provenance)

    @patch("kinetiqo.chat.service.decrypt_api_key", return_value="key")
    @patch("kinetiqo.chat.service.PROVIDER_REGISTRY")
    def test_stream_turn_handles_generator_exit_as_cancelled(self, registry, decrypt):
        session = MagicMock(provider="gemini", model_id="gemini-live")
        user = ChatMessage("user-id", "session", "athlete", "user", "hello", 1, "complete", datetime.now(timezone.utc))
        assistant = ChatMessage("assistant-id", "session", "athlete", "assistant", "", 2, "interrupted", datetime.now(timezone.utc))
        self.repository.get_session.return_value = session
        self.repository.add_message.side_effect = [user, assistant]
        self.repository.list_messages.return_value = []
        self.repository.get_provider_key.return_value = "ciphertext"

        provider = MagicMock()
        provider.list_models.return_value = [ChatProviderModel("gemini-live", "Live")]

        def infinite_events():
            from kinetiqo.chat.models import StreamEvent
            yield StreamEvent("text_delta", text="Partial ")
            yield StreamEvent("text_delta", text="content ")

        provider.stream.return_value = infinite_events()
        registry.__getitem__.return_value.return_value = provider

        _, events = self.service.stream_turn("athlete", "session", "hello")
        first_event = next(events)
        self.assertEqual(first_event.text, "Partial ")

        # Simulate client aborting the HTTP request/connection
        events.close()

        self.repository.update_message.assert_called_once()
        call_args = self.repository.update_message.call_args[0]
        self.assertEqual(call_args[0], "athlete")
        self.assertEqual(call_args[1], "assistant-id")
        self.assertEqual(call_args[2], "Partial ")
        self.assertEqual(call_args[3], "cancelled")
        self.assertEqual(call_args[4], "cancelled")

    def test_system_instruction_contains_taxonomy_and_indoor_outdoor_mandate(self):
        instruction = build_system_instruction()
        self.assertIn("SPORT TAXONOMY MANDATE", instruction)
        self.assertIn("OUTDOOR vs INDOOR DISTINCTION", instruction)
        self.assertIn("VirtualRide", instruction)
        self.assertIn("VirtualRun", instruction)



class TestChatRepository(unittest.TestCase):
    def test_save_provider_key_binds_dialect_appropriate_boolean(self):
        for dialect, expected in (("postgresql", True), ("mysql", True), ("firebird", 1)):
            with self.subTest(dialect=dialect):
                backend = MagicMock()
                cursor = backend.conn.cursor.return_value
                cursor.fetchone.return_value = None
                repository = ChatRepository(backend, dialect)
                repository.save_provider_key("athlete", "gemini", "encrypted", config={})
                insert_calls = [call for call in cursor.execute.call_args_list if "INSERT INTO chat_provider_keys" in call.args[0]]
                self.assertTrue(len(insert_calls) > 0)
                insert_parameters = insert_calls[0].args[1]
                self.assertEqual(insert_parameters[4], expected)
                backend.conn.commit.assert_called_once()

    def test_clear_history_deletes_messages_and_sessions_for_athlete(self):
        backend = MagicMock()
        cursor = backend.conn.cursor.return_value
        repository = ChatRepository(backend, "postgresql")
        repository.clear_history("athlete-123")
        executed_queries = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any("DELETE FROM chat_messages" in q for q in executed_queries))
        self.assertTrue(any("DELETE FROM chat_sessions" in q for q in executed_queries))
        backend.conn.commit.assert_called_once()

    def test_list_recent_prompts_deduplicates_and_preserves_recency(self):
        backend = MagicMock()
        cursor = backend.conn.cursor.return_value
        cursor.fetchall.return_value = [
            ("Summarize training",),
            ("Compare month",),
            ("Summarize training",),
            ("What is my FTP?",),
        ]
        repository = ChatRepository(backend, "postgresql")
        prompts = repository.list_recent_prompts("athlete-123", limit=10)
        self.assertEqual(prompts, ["Summarize training", "Compare month", "What is my FTP?"])
        executed_query = cursor.execute.call_args[0][0]
        self.assertIn("SELECT content FROM chat_messages", executed_query)
        self.assertIn("role = 'user'", executed_query)
        self.assertIn("ORDER BY created_at DESC", executed_query)


class TestGeminiDiagnostics(unittest.TestCase):
    def test_model_discovery_filters_non_generation_models(self):
        provider = GeminiChatProvider("key")
        provider._request_json = MagicMock(return_value={"models": [
            {
                "name": "models/gemini-available",
                "displayName": "Available",
                "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
                "inputTokenLimit": 1048576,
                "outputTokenLimit": 8192,
                "description": "A Gemini test model.",
            },
            {"name": "models/gemini-non-stream", "displayName": "No Stream", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-flash", "displayName": "Deprecated Flash", "supportedGenerationMethods": ["generateContent", "streamGenerateContent"]},
            {"name": "models/embedding-only", "supportedGenerationMethods": ["embedContent"]},
        ]})
        models = provider.list_models()
        self.assertEqual([(model.id, model.display_name) for model in models], [("gemini-available", "Available")])
        self.assertEqual(models[0].context_length, 1048576)
        self.assertEqual(models[0].max_output_tokens, 8192)
        self.assertEqual(models[0].description, "A Gemini test model.")
        self.assertIsNone(models[0].pricing)
        self.assertIsNone(models[0].rate_limits)
        self.assertNotIn("gemini-non-stream", [m.id for m in models])
        self.assertNotIn("gemini-2.5-flash", [m.id for m in models])

    def test_invalid_request_logs_status_without_response_body(self):
        response = httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": "private upstream message"}}, headers={"x-request-id": "request-123"})
        with self.assertLogs("kinetiqo.chat.gemini", "WARNING") as logs:
            with self.assertRaises(ChatProviderResponseError):
                GeminiChatProvider._raise_for_status(response)
        output = "\n".join(logs.output)
        self.assertIn("http_status=400", output)
        self.assertIn("provider_status=INVALID_ARGUMENT", output)
        self.assertIn("request-123", output)
        self.assertNotIn("private upstream message", output)

    def test_unread_streaming_error_response_is_read_before_status_parsing(self):
        response = httpx.Response(
            400,
            stream=httpx.ByteStream(b'{"error":{"status":"INVALID_ARGUMENT"}}'),
        )
        with self.assertRaises(ChatProviderResponseError):
            GeminiChatProvider._raise_for_status(response)
        self.assertTrue(response.is_stream_consumed)

    def test_unauthorized_response_maps_to_authentication_error(self):
        response = httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})
        with self.assertRaises(ChatAuthenticationError):
            GeminiChatProvider._raise_for_status(response)

    def test_quota_exceeded_maps_to_transparent_rate_limit_error(self):
        response = httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded for model"}})
        with self.assertRaises(ChatRateLimitError) as ctx:
            GeminiChatProvider._raise_for_status(response)
        self.assertIn("quota", ctx.exception.user_message.lower())

    def test_stream_uses_gemini_camel_case_system_instruction(self):
        client = MagicMock()
        response = client.stream.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_lines.return_value = []
        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        provider = GeminiChatProvider("key", client_factory=factory)
        list(provider.stream("gemini-2.5-flash", "system rules", [], "hello"))
        payload = client.stream.call_args.kwargs["json"]
        self.assertIn("systemInstruction", payload)
        self.assertNotIn("system_instruction", payload)

    def test_stream_handles_function_call_and_invokes_tool_executor(self):
        client = MagicMock()
        resp1 = MagicMock(status_code=200)
        resp1.iter_lines.return_value = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"thoughtSignature": "sig_xyz789", "functionCall": {"name": "kinetiqo_get_activity_totals", "args": {"sport_types": ["Ride"]}, "id": "call_abc123"}}]}}]}'
        ]
        resp2 = MagicMock(status_code=200)
        resp2.iter_lines.return_value = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "You rode 120km."}]}}]}'
        ]
        context1 = MagicMock(__enter__=MagicMock(return_value=resp1), __exit__=MagicMock())
        context2 = MagicMock(__enter__=MagicMock(return_value=resp2), __exit__=MagicMock())
        client.stream.side_effect = [context1, context2]

        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        provider = GeminiChatProvider("key", client_factory=factory)

        tool_executor = MagicMock(return_value=({"distance_km": 120}, 35))
        events = list(provider.stream(
            "gemini-2.5-flash",
            "system rules",
            [{"role": "user", "content": "Previous prompt"}, {"role": "user", "content": "Duplicate user turn"}],
            "Show ride totals",
            tools=[{"name": "kinetiqo_get_activity_totals", "description": "Totals", "parameters": {}}],
            tool_executor=tool_executor,
        ))

        tool_executor.assert_called_once_with("kinetiqo_get_activity_totals", {"sport_types": ["Ride"]})
        event_types = [e.type for e in events]
        self.assertEqual(event_types, ["tool_call", "tool_result", "text_delta", "completed"])
        self.assertEqual(events[0].tool, "kinetiqo_get_activity_totals")
        self.assertEqual(events[2].text, "You rode 120km.")

        # Verify second call included the function response in contents with matching id
        second_call_body = client.stream.call_args_list[1].kwargs["json"]
        last_turn = second_call_body["contents"][-1]
        self.assertEqual(last_turn["role"], "user")
        self.assertEqual(last_turn["parts"][0]["functionResponse"]["name"], "kinetiqo_get_activity_totals")
        self.assertEqual(last_turn["parts"][0]["functionResponse"]["id"], "call_abc123")

        # Verify model turn has functionCall with matching id and preserved thoughtSignature
        model_turn = second_call_body["contents"][-2]
        self.assertEqual(model_turn["role"], "model")
        self.assertEqual(model_turn["parts"][0]["functionCall"]["id"], "call_abc123")
        self.assertEqual(model_turn["parts"][0]["thoughtSignature"], "sig_xyz789")

    def test_stream_forces_synthesis_after_consecutive_tool_calls(self):
        client = MagicMock()
        # Simulate 2 consecutive tool call rounds followed by text
        resp1 = MagicMock(status_code=200)
        resp1.iter_lines.return_value = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "kinetiqo_get_activity_totals", "args": {"year": 2024}}}]}}]}'
        ]
        resp2 = MagicMock(status_code=200)
        resp2.iter_lines.return_value = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "kinetiqo_get_activity_totals", "args": {"year": 2025}}}]}}]}'
        ]
        resp3 = MagicMock(status_code=200)
        resp3.iter_lines.return_value = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "Your best year was 2025."}]}}]}'
        ]
        c1 = MagicMock(__enter__=MagicMock(return_value=resp1), __exit__=MagicMock())
        c2 = MagicMock(__enter__=MagicMock(return_value=resp2), __exit__=MagicMock())
        c3 = MagicMock(__enter__=MagicMock(return_value=resp3), __exit__=MagicMock())
        client.stream.side_effect = [c1, c2, c3]

        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        provider = GeminiChatProvider("key", client_factory=factory)

        tool_executor = MagicMock(return_value=({"distance_km": 5000}, 20))
        events = list(provider.stream(
            "gemini-2.5-flash",
            "system rules",
            [],
            "Compare 2024 and 2025",
            tools=[{"name": "kinetiqo_get_activity_totals", "description": "Totals", "parameters": {}}],
            tool_executor=tool_executor,
        ))

        self.assertEqual(tool_executor.call_count, 2)
        text_events = [e for e in events if e.type == "text_delta"]
        self.assertEqual(len(text_events), 1)
        self.assertEqual(text_events[0].text, "Your best year was 2025.")

    def test_build_system_instruction_calendar_anchoring(self):
        instruction = build_system_instruction()
        self.assertIn("DATE & TIME RECKONING", instruction)
        self.assertIn("'This Week' (current ISO calendar week", instruction)
        self.assertIn("Monday", instruction)
        self.assertIn("Sunday", instruction)
        self.assertIn("TOOL DATE SIMPLIFICATION:", instruction)
        self.assertIn("date_preset='this_week'", instruction)



