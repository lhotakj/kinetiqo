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


if __name__ == "__main__":
    unittest.main()

