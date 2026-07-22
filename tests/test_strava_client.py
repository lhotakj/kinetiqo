"""Mocked unit tests for kinetiqo.strava.StravaClient.

Follows the style of tests/test_sync_logic.py: no live network is ever
contacted — requests.put/get are patched with unittest.mock.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from kinetiqo.strava import StravaClient


def _make_config(**overrides):
    config = MagicMock()
    config.strava_client_id = "client-id"
    config.strava_client_secret = "client-secret"
    config.strava_refresh_token = "refresh-token"
    config.strava_request_timeout = 15
    config.strava_request_retries = 2
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _http_error_response(status_code):
    response = MagicMock()
    response.status_code = status_code
    error = requests.exceptions.HTTPError(response=response)
    response.raise_for_status.side_effect = error
    return response


class TestUpdateActivityDescription(unittest.TestCase):
    """Unit tests for StravaClient.update_activity_description()."""

    def _make_client(self):
        client = StravaClient(_make_config())
        client._access_token = "token"  # skip the token-exchange POST entirely
        return client

    @patch("kinetiqo.strava.time.sleep")
    @patch("kinetiqo.strava.requests.put")
    def test_401_fails_fast_without_retry(self, mock_put, mock_sleep):
        """A 401 (missing activity:write scope) must not be retried."""
        mock_put.return_value = _http_error_response(401)
        client = self._make_client()

        with self.assertRaises(requests.exceptions.HTTPError):
            client.update_activity_description(123, "new description")

        # Exactly one PUT attempt — no retries burned on a permanent auth error.
        self.assertEqual(mock_put.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("kinetiqo.strava.time.sleep")
    @patch("kinetiqo.strava.requests.put")
    def test_transient_error_is_retried(self, mock_put, mock_sleep):
        """A transient (non-401) error should still be retried up to the configured limit."""
        mock_put.return_value = _http_error_response(503)
        client = self._make_client()

        with self.assertRaises(requests.exceptions.HTTPError):
            client.update_activity_description(123, "new description")

        # request_retries=2 -> 3 total attempts (1 initial + 2 retries) before giving up.
        self.assertEqual(mock_put.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("kinetiqo.strava.requests.put")
    def test_success_returns_json_body(self, mock_put):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"id": 123, "description": "new description"}
        mock_put.return_value = response
        client = self._make_client()

        result = client.update_activity_description(123, "new description")
        self.assertEqual(result, {"id": 123, "description": "new description"})
        mock_put.assert_called_once()


if __name__ == "__main__":
    unittest.main()
