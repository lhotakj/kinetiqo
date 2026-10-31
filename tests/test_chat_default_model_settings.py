"""Mocked unit tests for AI provider index and global default-model settings endpoints."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestChatDefaultModelSettingsEndpoints(unittest.TestCase):
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
    def test_get_default_model(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = {"provider": "gemini", "model_id": "gemini-3.1-flash-lite"}
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.get("/api/settings/ai/default-model")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["default_model"]["provider"], "gemini")
        self.assertEqual(data["default_model"]["model_id"], "gemini-3.1-flash-lite")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_default_model(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = {"provider": "openrouter", "model_id": "meta-llama/llama-3.3-70b-instruct"}
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.post(
            "/api/settings/ai/default-model",
            json={"provider": "openrouter", "model_id": "meta-llama/llama-3.3-70b-instruct"},
        )
        self.assertEqual(resp.status_code, 200)
        mock_repo.set_default_model.assert_called_once_with("12345", "openrouter", "meta-llama/llama-3.3-70b-instruct")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_default_model_rejects_unknown_provider(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.post(
            "/api/settings/ai/default-model",
            json={"provider": "unknown", "model_id": "x"},
        )
        self.assertEqual(resp.status_code, 422)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_add_provider_creates_empty_config(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_config.return_value = {}
        mock_repo.list_configured_providers.return_value = ["gemini"]
        mock_repo.list_enabled_providers.return_value = ["gemini", "openrouter"]
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.post("/api/settings/ai/providers", json={"provider": "openrouter"})
        self.assertEqual(resp.status_code, 200)
        mock_repo.save_provider_config.assert_called_once_with("12345", "openrouter", {})
        payload = resp.get_json()
        self.assertIn("all_providers", payload)
        self.assertIn("enabled_providers", payload)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_get_providers_includes_kilo(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_repo.list_configured_providers.return_value = ["gemini"]
        mock_repo.list_enabled_providers.return_value = ["gemini", "kilo"]
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.get("/api/settings/ai/providers")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        provider_ids = [p["provider"] for p in payload["all_providers"]]
        self.assertIn("kilo", provider_ids)
        self.assertIn("vercel", provider_ids)

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_get_fallback_models(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_fallback_models.return_value = [
            {"provider": "openrouter", "model_id": "anthropic/claude-3.5-sonnet"},
            {"provider": "gemini", "model_id": "gemini-2.5-flash"},
        ]
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.get("/api/settings/ai/fallback-models")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["fallback_models"]), 2)
        self.assertEqual(data["fallback_models"][0]["model_id"], "anthropic/claude-3.5-sonnet")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_fallback_models_up_to_three(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = {"provider": "gemini", "model_id": "gemini-3.1-flash-lite"}
        mock_repo.set_fallback_models.return_value = [
            {"provider": "openrouter", "model_id": "model-1"},
            {"provider": "vercel", "model_id": "model-2"},
            {"provider": "kilo", "model_id": "model-3"},
        ]
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.post(
            "/api/settings/ai/fallback-models",
            json={
                "fallback_models": [
                    {"provider": "openrouter", "model_id": "model-1"},
                    {"provider": "vercel", "model_id": "model-2"},
                    {"provider": "kilo", "model_id": "model-3"},
                ]
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["fallback_models"]), 3)
        mock_repo.set_fallback_models.assert_called_once()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_fallback_models_rejects_more_than_three(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.post(
            "/api/settings/ai/fallback-models",
            json={
                "fallback_models": [
                    {"provider": "openrouter", "model_id": "model-1"},
                    {"provider": "openrouter", "model_id": "model-2"},
                    {"provider": "openrouter", "model_id": "model-3"},
                    {"provider": "openrouter", "model_id": "model-4"},
                ]
            },
        )
        self.assertEqual(resp.status_code, 422)
        mock_repo.set_fallback_models.assert_not_called()

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_post_fallback_models_rejects_default_model_as_fallback(self, mock_service_fn, _mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = {"provider": "gemini", "model_id": "gemini-2.5-flash"}
        mock_service_fn.return_value = MagicMock(repository=mock_repo)

        resp = self.client.post(
            "/api/settings/ai/fallback-models",
            json={
                "fallback_models": [
                    {"provider": "gemini", "model_id": "gemini-2.5-flash"},
                ]
            },
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("default model", resp.get_json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()

