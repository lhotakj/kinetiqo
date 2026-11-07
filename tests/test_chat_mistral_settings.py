"""Mocked tests for Mistral model metadata and settings in AI Settings."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.encryption import encrypt_api_key
from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestMistralSettingsMetadata(unittest.TestCase):
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
    def test_get_mistral_not_configured(self, service_factory, _user_id):
        repository = MagicMock()
        repository.get_provider_key.return_value = None
        repository.get_provider_config.return_value = {}
        repository.get_default_model.return_value = None
        service_factory.return_value = MagicMock(repository=repository)

        response = self.client.get("/api/settings/ai/mistral")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["models"], [])

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MistralChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="mistral-test-key")
    def test_get_mistral_models_returns_discovered_metadata(
        self,
        _decrypt_key,
        provider_cls,
        service_factory,
        _user_id,
    ):
        repository = MagicMock()
        repository.get_provider_key.return_value = encrypt_api_key("mistral-test-key", app.secret_key)
        repository.get_provider_config.return_value = {}
        repository.get_default_model.return_value = {"provider": "mistral", "model_id": "mistral-small-latest"}
        service_factory.return_value = MagicMock(repository=repository)
        provider_cls.return_value.list_models.return_value = [
            ChatProviderModel(
                id="mistral-small-latest",
                display_name="Mistral Small",
                supports_vision=False,
                supports_tools=True,
                context_length=128000,
                max_output_tokens=8192,
                description="Fast and lightweight model.",
            )
        ]

        response = self.client.get("/api/settings/ai/mistral")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        model = data["models"][0]
        self.assertEqual(model["id"], "mistral-small-latest")
        self.assertEqual(model["context_length"], 128000)
        self.assertEqual(model["max_output_tokens"], 8192)
        self.assertTrue(model["supports_tools"])
        self.assertFalse(model["supports_vision"])
        self.assertEqual(model["description"], "Fast and lightweight model.")
        self.assertIsNone(model["pricing"])
        self.assertIsNone(model["rate_limits"])
        repository.save_provider_config.assert_called_once()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MistralChatProvider")
    def test_post_mistral_key_saves_and_discovers_models(
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
                id="mistral-large-latest",
                display_name="Mistral Large",
                supports_vision=False,
                supports_tools=True,
                context_length=128000,
            )
        ]

        response = self.client.post("/api/settings/ai/mistral", json={"api_key": "new-mistral-key"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["id"], "mistral-large-latest")
        repository.save_provider_key.assert_called_once()
        repository.save_provider_config.assert_called_once()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_mistral_key_validation_failure(self, service_factory, _user_id):
        repository = MagicMock()
        service_factory.return_value = MagicMock(repository=repository)

        response = self.client.post("/api/settings/ai/mistral", json={"api_key": "   "})
        self.assertEqual(response.status_code, 422)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_delete_mistral_removes_key_and_clears_defaults(self, service_factory, _user_id):
        repository = MagicMock()
        service_factory.return_value = MagicMock(repository=repository)

        response = self.client.delete("/api/settings/ai/mistral")
        self.assertEqual(response.status_code, 204)
        repository.remove_provider_key.assert_called_once_with("12345", "mistral")
        repository.clear_default_model.assert_called_once_with("12345", provider="mistral")
        repository.clear_fallback_model.assert_called_once_with("12345", provider="mistral")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.MistralChatProvider")
    @patch("kinetiqo.web.app.decrypt_api_key", return_value="mistral-test-key")
    def test_validate_and_manage_mistral_models(
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
            "id": "codestral-latest",
            "name": "Codestral",
            "display_name": "Codestral",
            "context_length": 256000,
            "supports_tools": True,
            "supports_vision": False,
        }

        # Validate endpoint
        val_resp = self.client.post("/api/settings/ai/mistral/models/validate", json={"model_id": "codestral-latest"})
        self.assertEqual(val_resp.status_code, 200)
        self.assertTrue(val_resp.get_json()["valid"])

        # Add model endpoint
        add_resp = self.client.post("/api/settings/ai/mistral/models", json={"model_id": "codestral-latest"})
        self.assertEqual(add_resp.status_code, 201)
        self.assertEqual(len(add_resp.get_json()["models"]), 1)

        # Delete model endpoint
        del_resp = self.client.delete("/api/settings/ai/mistral/models", json={"model_id": "codestral-latest"})
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(len(del_resp.get_json()["models"]), 0)


if __name__ == "__main__":
    unittest.main()

