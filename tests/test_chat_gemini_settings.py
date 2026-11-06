"""Mocked tests for Gemini model metadata in AI Settings."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestGeminiSettingsMetadata(unittest.TestCase):
    def setUp(self):
        self._orig_testing = app.config.get("TESTING")
        self._orig_csrf = app.config.get("WTF_CSRF_ENABLED")
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        username = next(iter(users))
        with self.client.session_transaction() as session:
            session["_user_id"] = username
            session["_fresh"] = True

    def tearDown(self):
        if self._orig_testing is not None:
            app.config["TESTING"] = self._orig_testing
        if self._orig_csrf is not None:
            app.config["WTF_CSRF_ENABLED"] = self._orig_csrf

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.GeminiChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="gemini-test-key")
    def test_get_gemini_models_returns_published_metadata(
        self,
        _decrypt_key,
        provider_cls,
        service_factory,
        _user_id,
    ):
        repository = MagicMock()
        repository.get_provider_key.return_value = encrypt_api_key("gemini-test-key", app.secret_key)
        repository.get_provider_config.return_value = {}
        service_factory.return_value = MagicMock(repository=repository)
        provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(
                id="gemini-example",
                display_name="Gemini Example",
                supports_vision=True,
                supports_tools=True,
                context_length=1048576,
                max_output_tokens=8192,
                description="Example model description.",
            )
        ]

        response = self.client.get("/api/settings/ai/gemini")

        self.assertEqual(response.status_code, 200)
        model = response.get_json()["models"][0]
        self.assertEqual(model["context_length"], 1048576)
        self.assertEqual(model["max_output_tokens"], 8192)
        self.assertEqual(model["description"], "Example model description.")
        self.assertIsNone(model["pricing"])
        self.assertIsNone(model["rate_limits"])
        self.assertTrue(model["supports_vision"])
        repository.save_provider_config.assert_called_once()


if __name__ == "__main__":
    unittest.main()
