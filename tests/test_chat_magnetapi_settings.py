"""Mocked unit tests for MagnetAPI and AI settings endpoints in web app."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestMagnetAPISettingsEndpoints(unittest.TestCase):
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
    def test_get_magnetapi_settings_unconfigured(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        resp = self.client.get("/api/settings/ai/magnetapi")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["models"], [])
        self.assertEqual(data["manifest"]["model_mode"], "discovered")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MagnetAPIChatProvider")
    def test_save_and_remove_magnetapi_key(self, mock_provider_cls, mock_service_fn, mock_user_id):
        from kinetiqo.chat.models import ChatProviderModel
        mock_repo = MagicMock()
        mock_repo.get_provider_config.return_value = {}
        mock_repo.get_default_model.return_value = None
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service
        mock_provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(id="power-ai", display_name="MagnetAPI: Power AI")
        ]

        # Save key
        save_resp = self.client.post(
            "/api/settings/ai/magnetapi",
            json={"api_key": "mag_testkey123"},
        )
        self.assertEqual(save_resp.status_code, 200)
        data = save_resp.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["id"], "power-ai")
        mock_repo.save_provider_key.assert_called_once()
        mock_repo.save_provider_config.assert_called_once()

        # Delete key
        del_resp = self.client.delete("/api/settings/ai/magnetapi")
        self.assertEqual(del_resp.status_code, 204)
        mock_repo.remove_provider_key.assert_called_once_with("12345", "magnetapi")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MagnetAPIChatProvider")
    def test_post_magnetapi_invalid_key_returns_401(self, mock_provider_cls, mock_service_fn, mock_user_id):
        from kinetiqo.chat.errors import ChatAuthenticationError
        mock_repo = MagicMock()
        mock_service_fn.return_value = MagicMock(repository=mock_repo)
        mock_provider_cls.return_value.list_models.side_effect = ChatAuthenticationError("MagnetAPI access rejected (HTTP 401): invalid key")

        save_resp = self.client.post(
            "/api/settings/ai/magnetapi",
            json={"api_key": "mag_invalid"},
        )
        self.assertEqual(save_resp.status_code, 401)
        mock_repo.save_provider_key.assert_not_called()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MagnetAPIChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="mag-test-key")
    def test_get_magnetapi_models_returns_discovered_metadata(
        self,
        _decrypt_key,
        mock_provider_cls,
        mock_service_fn,
        mock_user_id,
    ):
        from kinetiqo.chat.models import ChatProviderModel
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("mag-test-key", app.secret_key)
        mock_repo.get_provider_config.return_value = {"models": []}
        mock_repo.get_default_model.return_value = None
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service
        mock_provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(
                id="power-ai",
                display_name="Power AI",
                context_length=200000,
                supports_tools=True,
                supports_vision=True,
            )
        ]

        resp = self.client.get("/api/settings/ai/magnetapi")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["id"], "power-ai")
        mock_repo.save_provider_config.assert_called_once()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MagnetAPIChatProvider")
    def test_validate_magnetapi_model_endpoint(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("mag-key", app.secret_key)
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_provider_instance = MagicMock()
        mock_provider_instance.validate_model.return_value = {
            "id": "power-ai",
            "name": "Power AI",
            "context_length": 200000,
            "supports_tools": True,
            "max_output_tokens": 8192,
            "pricing": {"prompt": "varies", "completion": "varies"},
            "description": "High-performance auto-managed destination",
        }
        mock_provider_cls.return_value = mock_provider_instance

        resp = self.client.post(
            "/api/settings/ai/magnetapi/models/validate",
            json={"model_id": "power-ai"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["model"]["id"], "power-ai")
        self.assertEqual(data["model"]["context_length"], 200000)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MagnetAPIChatProvider")
    def test_add_and_delete_magnetapi_model(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("mag-key", app.secret_key)
        mock_repo.get_provider_config.return_value = {"models": []}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_provider_instance = MagicMock()
        mock_provider_instance.validate_model.return_value = {
            "id": "power-ai",
            "name": "Power AI",
            "context_length": 200000,
            "supports_tools": True,
            "pricing": {"prompt": "varies", "completion": "varies"},
        }
        mock_provider_cls.return_value = mock_provider_instance

        # Add model
        add_resp = self.client.post(
            "/api/settings/ai/magnetapi/models",
            json={"model_id": "power-ai"},
        )
        self.assertEqual(add_resp.status_code, 201)
        data = add_resp.get_json()
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["id"], "power-ai")
        mock_repo.save_provider_config.assert_called()

        # Delete model
        del_resp = self.client.delete(
            "/api/settings/ai/magnetapi/models",
            json={"model_id": "power-ai"},
        )
        self.assertEqual(del_resp.status_code, 200)
        del_data = del_resp.get_json()
        self.assertEqual(len(del_data["models"]), 0)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_chat_models_grouped_by_provider_includes_magnetapi(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = None
        mock_repo.get_fallback_models.return_value = []
        mock_service = MagicMock(repository=mock_repo)
        mock_service.models.return_value = [
            {"provider": "gemini", "display_name": "Google Gemini", "models": [{"id": "gemini-2.5-flash"}]},
            {"provider": "openrouter", "display_name": "OpenRouter AI", "models": [{"id": "meta-llama/llama-3.3-70b"}]},
            {"provider": "magnetapi", "display_name": "MagnetAPI", "models": [{"id": "power-ai"}]},
        ]
        mock_service_fn.return_value = mock_service

        resp = self.client.get("/api/chat/models?provider=all")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("providers", data)
        self.assertEqual(data["providers"][2]["provider"], "magnetapi")
        self.assertEqual(data["providers"][2]["display_name"], "MagnetAPI")


if __name__ == "__main__":
    unittest.main()
