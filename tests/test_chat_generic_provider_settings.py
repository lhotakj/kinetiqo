"""Mocked unit tests for the generic parameterized AI provider settings endpoints."""

import json
import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestGenericProviderSettingsEndpoints(unittest.TestCase):
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
    def test_get_generic_provider_unconfigured_with_manifest(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.get("/api/settings/ai/providers/openrouter")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["models"], [])
        self.assertIn("manifest", data)
        self.assertEqual(data["manifest"]["provider"], "openrouter")
        self.assertEqual(data["manifest"]["model_mode"], "curated")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_get_unsupported_provider_returns_404(self, mock_service_fn, mock_user_id):
        mock_service_fn.return_value = MagicMock()
        resp = self.client.get("/api/settings/ai/providers/non_existent_provider_xyz")
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertIn("error", data)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.OpenRouterChatProvider")
    def test_save_and_delete_generic_provider_key(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_config.return_value = {"models": [{"id": "m1"}]}
        mock_service_fn.return_value = MagicMock(repository=mock_repo)
        mock_provider_cls.return_value.validate_credentials.return_value = None

        # POST save key
        resp = self.client.post(
            "/api/settings/ai/providers/openrouter",
            json={"api_key": "sk-or-v1-generic-test"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["configured"])
        mock_repo.save_provider_key.assert_called_once()
        self.assertEqual(mock_repo.save_provider_key.call_args.args[1], "openrouter")

        # DELETE key
        del_resp = self.client.delete("/api/settings/ai/providers/openrouter")
        self.assertEqual(del_resp.status_code, 204)
        mock_repo.remove_provider_key.assert_called_once_with("12345", "openrouter")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.OpenRouterChatProvider")
    def test_validate_and_manage_models_generic_endpoints(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("sk-key", app.secret_key)
        mock_repo.get_provider_config.return_value = {"models": []}
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        mock_instance = MagicMock()
        mock_instance.validate_model.return_value = {
            "id": "meta-llama/llama-3.3-70b-instruct",
            "name": "Meta Llama 3.3 70B",
            "context_length": 131072,
            "supports_tools": True,
        }
        mock_provider_cls.return_value = mock_instance

        # Validate
        val_resp = self.client.post(
            "/api/settings/ai/providers/openrouter/models/validate",
            json={"model_id": "meta-llama/llama-3.3-70b-instruct"},
        )
        self.assertEqual(val_resp.status_code, 200)
        self.assertTrue(val_resp.get_json()["valid"])

        # Add model
        add_resp = self.client.post(
            "/api/settings/ai/providers/openrouter/models",
            json={"model_id": "meta-llama/llama-3.3-70b-instruct"},
        )
        self.assertEqual(add_resp.status_code, 201)
        mock_repo.save_provider_config.assert_called_once()

        # Delete model
        del_resp = self.client.delete(
            "/api/settings/ai/providers/openrouter/models",
            json={"model_id": "meta-llama/llama-3.3-70b-instruct"},
        )
        self.assertEqual(del_resp.status_code, 200)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.OllamaChatProvider.test_connection")
    def test_generic_provider_test_connection_endpoint(self, mock_test_conn, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service_fn.return_value = MagicMock(repository=mock_repo)
        mock_test_conn.return_value = {
            "success": True,
            "version": "0.5.1",
            "models": [{"id": "llama3.2:latest", "name": "Llama 3.2"}],
        }

        resp = self.client.post(
            "/api/settings/ai/providers/ollama/test",
            json={"base_url": "http://localhost:11434"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["models"]), 1)

