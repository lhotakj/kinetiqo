"""Mocked unit tests for Ollama settings endpoints in Kinetiqo web app."""

import json
import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestOllamaSettingsEndpoints(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        username = next(iter(users))
        with self.client.session_transaction() as sess:
            sess["_user_id"] = username
            sess["_fresh"] = True

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    def test_get_ollama_settings_unconfigured(self, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.has_provider.return_value = False
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        resp = self.client.get("/api/settings/ai/ollama")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["configured"])
        self.assertEqual(data["base_url"], "http://localhost:11434")
        self.assertFalse(data["has_api_key"])
        self.assertEqual(data["models"], [])

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.OllamaChatProvider.test_connection")
    def test_save_ollama_configuration_and_remove(self, mock_test_conn, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_test_conn.return_value = {
            "connected": True,
            "models": [{"id": "qwen3:1.7b", "name": "qwen3:1.7b (1.7B)"}],
        }

        # Save config
        resp = self.client.post(
            "/api/settings/ai/ollama",
            json={"base_url": "http://192.168.1.150:11434"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["configured"])
        self.assertEqual(data["base_url"], "http://192.168.1.150:11434")
        self.assertEqual(len(data["models"]), 1)
        mock_repo.save_provider_key.assert_called_once()

        # Delete config
        del_resp = self.client.delete("/api/settings/ai/ollama")
        self.assertEqual(del_resp.status_code, 204)
        mock_repo.remove_provider_key.assert_called_once_with("12345", "ollama")

    @patch("kinetiqo.web.app._chat_user_id", return_value="12345")
    @patch("kinetiqo.web.app._chat_service")
    @patch("kinetiqo.web.app.OllamaChatProvider.test_connection")
    def test_test_ollama_endpoint(self, mock_test_conn, mock_service_fn, mock_user_id):
        mock_repo = MagicMock()
        mock_repo.get_provider_key.return_value = None
        mock_repo.get_provider_config.return_value = {}
        mock_service = MagicMock(repository=mock_repo)
        mock_service_fn.return_value = mock_service

        mock_test_conn.return_value = {
            "connected": True,
            "base_url": "http://192.168.1.150:11434",
            "models": [{"id": "qwen3:1.7b", "name": "qwen3:1.7b"}],
        }

        resp = self.client.post(
            "/api/settings/ai/ollama/test",
            json={"base_url": "http://192.168.1.150:11434"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["connected"])
        self.assertEqual(len(data["models"]), 1)


if __name__ == "__main__":
    unittest.main()
