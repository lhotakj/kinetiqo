"""Mocked unit tests for PayPerQ and AI settings endpoints in web app."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestPayPerQSettingsEndpoints(unittest.TestCase):
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
    def test_get_payperq_settings_unconfigured(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        resp = self.client.get("/api/settings/ai/payperq")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["models"], [])
        self.assertEqual(data["manifest"]["model_mode"], "discovered")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.PayPerQChatProvider")
    def test_save_and_remove_payperq_key(self, mock_provider_cls, mock_service_fn, mock_user_id):
        from kinetiqo.chat.models import ChatProviderModel
        mock_repo = MagicMock()
        mock_repo.get_provider_config.return_value = {}
        mock_repo.get_default_model.return_value = None
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service
        mock_provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(id="auto", display_name="PayPerQ: Smart Router (Auto)")
        ]

        # Save key
        save_resp = self.client.post(
            "/api/settings/ai/payperq",
            json={"api_key": "ppq_testkey123"},
        )
        self.assertEqual(save_resp.status_code, 200)
        data = save_resp.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["id"], "auto")
        mock_repo.save_provider_key.assert_called_once()
        mock_repo.save_provider_config.assert_called_once()

        # Delete key
        del_resp = self.client.delete("/api/settings/ai/payperq")
        self.assertEqual(del_resp.status_code, 204)
        mock_repo.remove_provider_key.assert_called_once_with("12345", "payperq")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.PayPerQChatProvider")
    def test_post_payperq_invalid_key_returns_401(self, mock_provider_cls, mock_service_fn, mock_user_id):
        from kinetiqo.chat.errors import ChatAuthenticationError
        mock_repo = MagicMock()
        mock_service_fn.return_value = MagicMock(repository=mock_repo)
        mock_provider_cls.return_value.list_models.side_effect = ChatAuthenticationError("PayPerQ access rejected (HTTP 401): invalid key")

        save_resp = self.client.post(
            "/api/settings/ai/payperq",
            json={"api_key": "ppq_invalid"},
        )
        self.assertEqual(save_resp.status_code, 401)
        mock_repo.save_provider_key.assert_not_called()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.PayPerQChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="ppq-test-key")
    def test_get_payperq_models_returns_discovered_metadata(
        self,
        _decrypt_key,
        mock_provider_cls,
        mock_service_fn,
        mock_user_id,
    ):
        from kinetiqo.chat.models import ChatProviderModel
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("ppq-test-key", app.secret_key)
        mock_repo.get_provider_config.return_value = {}
        mock_repo.get_default_model.return_value = {"provider": "payperq", "model_id": "auto"}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service
        mock_provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(
                id="auto",
                display_name="PayPerQ: Smart Router (Auto)",
                supports_vision=True,
                supports_tools=True,
                context_length=128000,
                max_output_tokens=8192,
                description="Dynamic auto-router",
            )
        ]

        resp = self.client.get("/api/settings/ai/payperq")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["id"], "auto")
        self.assertEqual(data["models"][0]["context_length"], 128000)
        mock_repo.save_provider_config.assert_called_once()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.PayPerQChatProvider")
    def test_validate_payperq_model_endpoint(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("ppq-key", app.secret_key)
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_provider_instance = MagicMock()
        mock_provider_instance.validate_model.return_value = {
            "id": "auto",
            "name": "Smart Router (Auto)",
            "context_length": 128000,
            "supports_tools": True,
            "max_output_tokens": 8192,
        }
        mock_provider_cls.return_value = mock_provider_instance

        resp = self.client.post(
            "/api/settings/ai/payperq/models/validate",
            json={"model_id": "auto"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["model"]["id"], "auto")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.PayPerQChatProvider")
    def test_add_and_delete_payperq_model(self, mock_provider_cls, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = encrypt_api_key("ppq-key", app.secret_key)
        mock_repo.get_provider_config.return_value = {"models": [{"id": "auto", "name": "Auto"}]}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_provider_instance = MagicMock()
        mock_provider_instance.validate_model.return_value = {
            "id": "autoclaw/eco",
            "name": "AutoClaw Eco",
            "context_length": 128000,
            "supports_tools": True,
        }
        mock_provider_cls.return_value = mock_provider_instance

        # Add model
        add_resp = self.client.post(
            "/api/settings/ai/payperq/models",
            json={"model_id": "autoclaw/eco"},
        )
        self.assertEqual(add_resp.status_code, 201)
        data = add_resp.get_json()
        self.assertEqual(len(data["models"]), 2)
        mock_repo.save_provider_config.assert_called()

        # Delete model
        del_resp = self.client.delete(
            "/api/settings/ai/payperq/models",
            json={"model_id": "autoclaw/eco"},
        )
        self.assertEqual(del_resp.status_code, 200)
        del_data = del_resp.get_json()
        self.assertEqual(len(del_data["models"]), 1)
        self.assertEqual(del_data["models"][0]["id"], "auto")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_payperq_listed_in_all_providers(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.list_configured_providers.return_value = []
        mock_repo.list_enabled_providers.return_value = []
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        resp = self.client.get("/api/settings/ai/providers")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        all_prov_ids = [p["provider"] for p in data["all_providers"]]
        self.assertIn("payperq", all_prov_ids)


if __name__ == "__main__":
    unittest.main()
