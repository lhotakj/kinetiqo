"""Mocked unit tests for OpenRouter and AI settings endpoints in web app."""

import json
import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestOpenRouterSettingsEndpoints(unittest.TestCase):
    def setUp(self):
        self._orig_testing = app.config.get("TESTING")
        self._orig_csrf = app.config.get("WTF_CSRF_ENABLED")
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        username = next(iter(users))
        with self.client.session_transaction() as sess:
            sess["_user_id"] = username
            sess["_fresh"] = True

    def tearDown(self):
        if self._orig_testing is not None:
            app.config["TESTING"] = self._orig_testing
        if self._orig_csrf is not None:
            app.config["WTF_CSRF_ENABLED"] = self._orig_csrf

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_get_openrouter_settings_unconfigured(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        resp = self.client.get("/api/settings/ai/openrouter")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["models"], [])

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_save_and_remove_openrouter_key(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_config.return_value = {"models": [{"id": "m1"}]}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        # Save key
        save_resp = self.client.post(
            "/api/settings/ai/openrouter",
            json={"api_key": "sk-or-v1-mytestkey"},
        )
        self.assertEqual(save_resp.status_code, 200)
        data = save_resp.get_json()
        self.assertTrue(data["configured"])
        mock_repo.save_provider_key.assert_called_once()

        # Delete key
        del_resp = self.client.delete("/api/settings/ai/openrouter")
        self.assertEqual(del_resp.status_code, 204)
        mock_repo.remove_provider_key.assert_called_once_with("12345", "openrouter")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.OpenRouterChatProvider")
    def test_validate_openrouter_model_endpoint(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("sk-key", app.secret_key)
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_provider_instance = MagicMock()
        mock_provider_instance.validate_model.return_value = {
            "id": "nvidia/nemotron-3.5-embed-1b:free",
            "name": "Nvidia Nemotron 3.5 Embed",
            "context_length": 4096,
            "supports_tools": True,
        }
        mock_provider_cls.return_value = mock_provider_instance

        resp = self.client.post(
            "/api/settings/ai/openrouter/models/validate",
            json={"model_id": "nvidia/nemotron-3.5-embed-1b:free"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["model"]["id"], "nvidia/nemotron-3.5-embed-1b:free")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.OpenRouterChatProvider")
    def test_add_and_delete_openrouter_model(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("sk-key", app.secret_key)
        mock_repo.get_provider_config.return_value = {"models": []}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_provider_instance = MagicMock()
        mock_provider_instance.validate_model.return_value = {
            "id": "anthropic/claude-3.5-sonnet",
            "name": "Claude 3.5 Sonnet",
            "context_length": 200000,
            "supports_tools": True,
        }
        mock_provider_cls.return_value = mock_provider_instance

        # 1. Add model
        add_resp = self.client.post(
            "/api/settings/ai/openrouter/models",
            json={"model_id": "anthropic/claude-3.5-sonnet"},
        )
        self.assertEqual(add_resp.status_code, 201)
        add_data = add_resp.get_json()
        self.assertEqual(len(add_data["models"]), 1)
        self.assertEqual(add_data["models"][0]["id"], "anthropic/claude-3.5-sonnet")
        mock_repo.save_provider_config.assert_called_once()

        # 2. Delete model
        mock_repo.get_provider_config.return_value = {
            "models": [{"id": "anthropic/claude-3.5-sonnet"}]
        }
        del_resp = self.client.delete(
            "/api/settings/ai/openrouter/models",
            json={"model_id": "anthropic/claude-3.5-sonnet"},
        )
        self.assertEqual(del_resp.status_code, 200)
        del_data = del_resp.get_json()
        self.assertEqual(del_data["models"], [])

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_chat_models_grouped_by_provider(self, mock_service_fn, mock_user_id):
        mock_service = MagicMock()
        mock_service.models.return_value = [
            {"provider": "gemini", "display_name": "Google Gemini", "models": [{"id": "gemini-3.1-flash-lite"}]},
            {"provider": "openrouter", "display_name": "OpenRouter AI", "models": [{"id": "anthropic/claude-3.5-sonnet"}]},
        ]
        mock_service_fn.return_value = mock_service

        resp = self.client.get("/api/chat/models?provider=all")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("providers", data)
        self.assertEqual(len(data["providers"]), 2)
        self.assertEqual(data["providers"][0]["provider"], "gemini")
        self.assertEqual(data["providers"][1]["provider"], "openrouter")


if __name__ == "__main__":
    unittest.main()
