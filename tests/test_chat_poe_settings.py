"""Mocked tests for Poe provider settings endpoints."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestPoeSettingsEndpoints(unittest.TestCase):
    def setUp(self):
        self.original_testing = app.config.get("TESTING")
        self.original_csrf = app.config.get("WTF_CSRF_ENABLED")
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        username = next(iter(users))
        with self.client.session_transaction() as session:
            session["_user_id"] = username
            session["_fresh"] = True

    def tearDown(self):
        if self.original_testing is not None:
            app.config["TESTING"] = self.original_testing
        if self.original_csrf is not None:
            app.config["WTF_CSRF_ENABLED"] = self.original_csrf

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_save_and_read_poe_key_and_configured_bot(self, service_factory, user_id):
        repository = MagicMock()
        repository.get_provider_config.return_value = {"models": [{"id": "AssistantBot"}]}
        service_factory.return_value = MagicMock(repository=repository)

        response = self.client.post("/api/settings/ai/poe", json={"api_key": "poe-key"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["configured"])
        repository.save_provider_key.assert_called_once()
        self.assertEqual(repository.save_provider_key.call_args.args[1], "poe")

        response = self.client.get("/api/settings/ai/poe")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["models"][0]["id"], "AssistantBot")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.PoeChatProvider")
    def test_add_and_remove_validated_bot(self, provider_factory, service_factory, user_id):
        repository = MagicMock()
        repository.get_provider_key.return_value = encrypt_api_key("poe-key", app.secret_key)
        repository.get_provider_config.return_value = {"models": []}
        service_factory.return_value = MagicMock(repository=repository)
        provider_factory.return_value.validate_model.return_value = {
            "id": "AssistantBot",
            "name": "Assistant",
            "supports_tools": True,
            "supports_vision": False,
        }

        response = self.client.post(
            "/api/settings/ai/poe/models",
            json={"model_id": "AssistantBot"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["models"][0]["id"], "AssistantBot")
        repository.save_provider_config.assert_called_once()

        repository.get_provider_config.return_value = {"models": [{"id": "AssistantBot"}]}
        response = self.client.delete(
            "/api/settings/ai/poe/models",
            json={"model_id": "AssistantBot"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["models"], [])

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_chat_models_includes_poe_provider(self, service_factory, user_id):
        service = MagicMock()
        service.models.return_value = [{
            "provider": "poe",
            "display_name": "Poe",
            "models": [{"id": "AssistantBot"}],
        }]
        service_factory.return_value = service

        response = self.client.get("/api/chat/models?provider=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["providers"][0]["provider"], "poe")


if __name__ == "__main__":
    unittest.main()
