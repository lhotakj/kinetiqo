"""Mocked tests for Anthropic Claude model metadata and settings in AI Settings."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestAnthropicSettingsMetadata(unittest.TestCase):
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
    def test_get_anthropic_not_configured(self, service_factory, _user_id):
        repository = MagicMock()
        repository.get_provider_key.return_value = None
        repository.get_provider_config.return_value = {}
        repository.get_default_model.return_value = None
        service_factory.return_value = MagicMock(repository=repository)

        response = self.client.get("/api/settings/ai/anthropic")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["models"], [])
        self.assertEqual(data["manifest"]["provider"], "anthropic")
        self.assertEqual(data["manifest"]["model_mode"], "discovered")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.AnthropicChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="anthropic-test-key")
    def test_get_anthropic_models_returns_discovered_metadata(
        self,
        _decrypt_key,
        provider_cls,
        service_factory,
        _user_id,
    ):
        repository = MagicMock()
        repository.get_provider_key.return_value = encrypt_api_key("anthropic-test-key", app.secret_key)
        repository.get_provider_config.return_value = {}
        repository.get_default_model.return_value = {"provider": "anthropic", "model_id": "claude-3-5-sonnet-20241022"}
        service_factory.return_value = MagicMock(repository=repository)
        provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(
                id="claude-3-5-sonnet-20241022",
                display_name="Claude 3.5 Sonnet",
                supports_vision=True,
                supports_tools=True,
                context_length=200000,
                max_output_tokens=8192,
                description="High-intelligence flagship model with exceptional reasoning, coding, and vision",
            )
        ]

        response = self.client.get("/api/settings/ai/anthropic")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        model = data["models"][0]
        self.assertEqual(model["id"], "claude-3-5-sonnet-20241022")
        self.assertEqual(model["context_length"], 200000)
        self.assertEqual(model["max_output_tokens"], 8192)
        self.assertTrue(model["supports_tools"])
        self.assertTrue(model["supports_vision"])
        self.assertIn("High-intelligence flagship model", model["description"])
        self.assertIsNone(model["pricing"])
        self.assertIsNone(model["rate_limits"])
        repository.save_provider_config.assert_called_once()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.AnthropicChatProvider")
    def test_post_anthropic_key_saves_and_discovers_models(
        self,
        provider_cls,
        service_factory,
        _user_id,
    ):
        repository = MagicMock()
        repository.get_provider_config.return_value = {}
        repository.get_default_model.return_value = None
        service_factory.return_value = MagicMock(repository=repository)
        provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(
                id="claude-3-7-sonnet-20250219",
                display_name="Claude 3.7 Sonnet",
                supports_vision=True,
                supports_tools=True,
                context_length=200000,
                max_output_tokens=8192,
            )
        ]

        response = self.client.post("/api/settings/ai/anthropic", json={"api_key": "sk-ant-test-key"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["id"], "claude-3-7-sonnet-20250219")
        repository.save_provider_key.assert_called_once()
        repository.save_provider_config.assert_called_once()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_anthropic_key_validation_failure(self, service_factory, _user_id):
        repository = MagicMock()
        service_factory.return_value = MagicMock(repository=repository)

        response = self.client.post("/api/settings/ai/anthropic", json={"api_key": "   "})
        self.assertEqual(response.status_code, 422)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.AnthropicChatProvider")
    def test_post_anthropic_invalid_key_returns_401_and_does_not_save(
        self,
        provider_cls,
        service_factory,
        _user_id,
    ):
        from kinetiqo.chat.errors import ChatAuthenticationError
        repository = MagicMock()
        service_factory.return_value = MagicMock(repository=repository)
        provider_cls.return_value.list_models.side_effect = ChatAuthenticationError("Anthropic access rejected (HTTP 401): invalid x-api-key")

        response = self.client.post("/api/settings/ai/anthropic", json={"api_key": "sk-ant-invalid-token"})
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("invalid x-api-key", data["error"]["message"])
        repository.save_provider_key.assert_not_called()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.AnthropicChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="anthropic-bad-stored-key")
    def test_get_anthropic_reports_auth_error_when_stored_key_rejected(
        self,
        _decrypt_key,
        provider_cls,
        service_factory,
        _user_id,
    ):
        from kinetiqo.chat.errors import ChatAuthenticationError
        repository = MagicMock()
        repository.get_provider_key.return_value = encrypt_api_key("anthropic-bad-stored-key", app.secret_key)
        repository.get_provider_config.return_value = {}
        service_factory.return_value = MagicMock(repository=repository)
        provider_cls.return_value.list_models.side_effect = ChatAuthenticationError("Anthropic access rejected (HTTP 401): invalid x-api-key")

        response = self.client.get("/api/settings/ai/anthropic")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["configured"])
        self.assertIn("invalid x-api-key", data.get("auth_error", ""))

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_delete_anthropic_removes_key_and_clears_defaults(self, service_factory, _user_id):
        repository = MagicMock()
        service_factory.return_value = MagicMock(repository=repository)

        response = self.client.delete("/api/settings/ai/anthropic")
        self.assertEqual(response.status_code, 204)
        repository.remove_provider_key.assert_called_once_with("12345", "anthropic")
        repository.clear_default_model.assert_called_once_with("12345", provider="anthropic")
        repository.clear_fallback_model.assert_called_once_with("12345", provider="anthropic")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.AnthropicChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="anthropic-test-key")
    def test_validate_and_manage_anthropic_models(
        self,
        _decrypt_key,
        provider_cls,
        service_factory,
        _user_id,
    ):
        repository = MagicMock()
        repository.get_provider_key.return_value = "enc_key"
        repository.get_provider_config.return_value = {"models": []}
        repository.get_default_model.return_value = None
        service_factory.return_value = MagicMock(repository=repository)
        provider_cls.return_value.validate_model.return_value = {
            "id": "claude-3-5-haiku-20241022",
            "name": "Claude 3.5 Haiku",
            "display_name": "Claude 3.5 Haiku",
            "context_length": 200000,
            "supports_tools": True,
            "supports_vision": True,
        }

        # Validate endpoint
        val_resp = self.client.post("/api/settings/ai/anthropic/models/validate", json={"model_id": "claude-3-5-haiku-20241022"})
        self.assertEqual(val_resp.status_code, 200)
        self.assertTrue(val_resp.get_json()["valid"])

        # Add model endpoint
        add_resp = self.client.post("/api/settings/ai/anthropic/models", json={"model_id": "claude-3-5-haiku-20241022"})
        self.assertEqual(add_resp.status_code, 201)
        self.assertEqual(len(add_resp.get_json()["models"]), 1)

        # Delete model endpoint
        del_resp = self.client.delete("/api/settings/ai/anthropic/models", json={"model_id": "claude-3-5-haiku-20241022"})
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(len(del_resp.get_json()["models"]), 0)


if __name__ == "__main__":
    unittest.main()

