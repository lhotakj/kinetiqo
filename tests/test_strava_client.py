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


class TestRefreshTokenRotationCallback(unittest.TestCase):
    """Unit tests for the on_refresh_token_changed callback wiring.

    Strava issues a new refresh_token — invalidating the previous one — on
    every token exchange. StravaClient must notify config.on_refresh_token_changed
    whenever that happens, so the rotated token can be persisted durably (see
    kinetiqo.profile_sync). See tests/test_profile_sync.py for the persistence
    side of this mechanism.
    """

    def _token_response(self, access_token="access-token", refresh_token="refresh-token"):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"access_token": access_token, "refresh_token": refresh_token}
        return response

    @patch("kinetiqo.strava.requests.post")
    def test_get_access_token_triggers_callback_on_rotation(self, mock_post):
        mock_post.return_value = self._token_response(refresh_token="rotated-token")
        callback = MagicMock()
        config = _make_config(strava_refresh_token="old-token", on_refresh_token_changed=callback)
        client = StravaClient(config)

        client._get_access_token()

        self.assertEqual(config.strava_refresh_token, "rotated-token")
        callback.assert_called_once_with("rotated-token")

    @patch("kinetiqo.strava.requests.post")
    def test_get_access_token_no_callback_when_token_unchanged(self, mock_post):
        mock_post.return_value = self._token_response(refresh_token="same-token")
        callback = MagicMock()
        config = _make_config(strava_refresh_token="same-token", on_refresh_token_changed=callback)
        client = StravaClient(config)

        client._get_access_token()

        callback.assert_not_called()

    @patch("kinetiqo.strava.requests.post")
    def test_get_access_token_works_without_callback_configured(self, mock_post):
        mock_post.return_value = self._token_response(refresh_token="rotated-token")
        config = _make_config(strava_refresh_token="old-token", on_refresh_token_changed=None)
        client = StravaClient(config)

        token = client._get_access_token()

        self.assertEqual(token, "access-token")
        self.assertEqual(config.strava_refresh_token, "rotated-token")

    @patch("kinetiqo.strava.requests.post")
    def test_get_access_token_swallows_callback_exception(self, mock_post):
        mock_post.return_value = self._token_response(refresh_token="rotated-token")
        callback = MagicMock(side_effect=RuntimeError("db unreachable"))
        config = _make_config(strava_refresh_token="old-token", on_refresh_token_changed=callback)
        client = StravaClient(config)

        # Must not raise even though the persistence callback failed.
        token = client._get_access_token()

        self.assertEqual(token, "access-token")
        callback.assert_called_once_with("rotated-token")

    @patch("kinetiqo.strava.requests.post")
    def test_exchange_authorization_code_triggers_callback_on_rotation(self, mock_post):
        mock_post.return_value = self._token_response(refresh_token="brand-new-token")
        callback = MagicMock()
        config = _make_config(strava_refresh_token="old-token", on_refresh_token_changed=callback)
        client = StravaClient(config)

        client.exchange_authorization_code("auth-code-123")

        self.assertEqual(config.strava_refresh_token, "brand-new-token")
        callback.assert_called_once_with("brand-new-token")


if __name__ == "__main__":
    unittest.main()
