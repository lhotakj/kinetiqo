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


class TestGetAthleteKoms(unittest.TestCase):
    """Unit tests for StravaClient.get_athlete_koms()."""

    def _make_client(self):
        client = StravaClient(_make_config())
        client._access_token = "token"
        return client

    @patch("kinetiqo.strava.requests.get")
    def test_get_athlete_koms_single_page(self, mock_get):
        """Single page response finishes without making extra pagination requests."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"id": 1, "name": "Climb 1", "activity": {"id": 1001}},
            {"id": 2, "name": "Climb 2", "activity": {"id": 1002}},
        ]
        mock_get.return_value = mock_response

        client = self._make_client()
        koms = client.get_athlete_koms(12345, per_page=200)

        self.assertEqual(len(koms), 2)
        self.assertEqual(koms[0]["name"], "Climb 1")
        self.assertEqual(mock_get.call_count, 1)

    @patch("kinetiqo.strava.requests.get")
    def test_get_athlete_koms_multiple_pages(self, mock_get):
        """When a page returns per_page items, it requests the next page."""
        resp1 = MagicMock()
        resp1.raise_for_status.return_value = None
        resp1.json.return_value = [{"id": 1, "activity": {"id": 1001}}, {"id": 2, "activity": {"id": 1002}}]

        resp2 = MagicMock()
        resp2.raise_for_status.return_value = None
        resp2.json.return_value = [{"id": 3, "activity": {"id": 1003}}]

        mock_get.side_effect = [resp1, resp2]

        client = self._make_client()
        koms = client.get_athlete_koms(12345, per_page=2)

        self.assertEqual(len(koms), 3)
        self.assertEqual(mock_get.call_count, 2)

    @patch("kinetiqo.strava.time.sleep")
    @patch("kinetiqo.strava.requests.get")
    def test_get_athlete_koms_retries_transient_error(self, mock_get, mock_sleep):
        """Transient error is retried up to configured limit."""
        fail_resp = _http_error_response(503)
        success_resp = MagicMock()
        success_resp.raise_for_status.return_value = None
        success_resp.json.return_value = [{"id": 1, "activity": {"id": 1001}}]

        mock_get.side_effect = [fail_resp, success_resp]

        client = self._make_client()
        koms = client.get_athlete_koms(12345, per_page=200)

        self.assertEqual(len(koms), 1)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)


class TestTokenExpiryAndAutoRefresh(unittest.TestCase):
    """Unit tests for token expiration detection and automatic refresh."""

    @patch("kinetiqo.strava.requests.post")
    def test_get_access_token_refreshes_when_expired(self, mock_post):
        import time
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "new-token", "expires_at": int(time.time()) + 3600, "refresh_token": "new-ref"}
        )
        client = StravaClient(_make_config())
        client._access_token = "old-token"
        client._expires_at = int(time.time()) - 100  # already expired

        token = client._get_access_token()
        self.assertEqual(token, "new-token")
        mock_post.assert_called_once()

    @patch("kinetiqo.strava.requests.post")
    def test_get_access_token_refreshes_when_nearing_expiration(self, mock_post):
        import time
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "new-token", "expires_at": int(time.time()) + 3600, "refresh_token": "new-ref"}
        )
        client = StravaClient(_make_config())
        client._access_token = "old-token"
        client._expires_at = int(time.time()) + 60  # expires in 60s (< 120s buffer)

        token = client._get_access_token()
        self.assertEqual(token, "new-token")
        mock_post.assert_called_once()

    @patch("kinetiqo.strava.requests.post")
    def test_get_access_token_reuses_valid_token(self, mock_post):
        import time
        client = StravaClient(_make_config())
        client._access_token = "valid-token"
        client._expires_at = int(time.time()) + 3600  # valid for 1h

        token = client._get_access_token()
        self.assertEqual(token, "valid-token")
        mock_post.assert_not_called()


class Test401AutoRefreshAndFailFast(unittest.TestCase):
    """Unit tests for automatic 401 recovery via token refresh and fast failure if unrecoverable."""

    def _make_client(self):
        import time
        client = StravaClient(_make_config())
        client._access_token = "token"
        client._expires_at = int(time.time()) + 3600
        return client

    @patch("kinetiqo.strava.time.sleep")
    @patch("kinetiqo.strava.requests.post")
    @patch("kinetiqo.strava.requests.get")
    def test_get_activity_detail_recovers_from_401_via_refresh(self, mock_get, mock_post, mock_sleep):
        """When detail returns 401, client refreshes token and retries successfully once."""
        import time
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "fresh-token", "expires_at": int(time.time()) + 3600, "refresh_token": "ref"}
        )
        err_401 = _http_error_response(401)
        ok_resp = MagicMock(raise_for_status=lambda: None, json=lambda: {"id": 123, "description": "test"})
        mock_get.side_effect = [err_401, ok_resp]

        client = self._make_client()
        detail = client.get_activity_detail(123)

        self.assertEqual(detail, {"id": 123, "description": "test"})
        self.assertEqual(mock_get.call_count, 2)
        mock_post.assert_called_once()
        mock_sleep.assert_not_called()  # Did NOT wait 2s, 4s, 8s backoff!

    @patch("kinetiqo.strava.time.sleep")
    @patch("kinetiqo.strava.requests.post")
    @patch("kinetiqo.strava.requests.get")
    def test_get_activity_detail_fails_fast_on_persistent_401(self, mock_get, mock_post, mock_sleep):
        """If 401 persists after token refresh, raise StravaAuthError without generic backoff retries."""
        import time
        from kinetiqo.strava import StravaAuthError

        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "fresh-token", "expires_at": int(time.time()) + 3600, "refresh_token": "ref"}
        )
        err_401_first = _http_error_response(401)
        err_401_second = _http_error_response(401)
        mock_get.side_effect = [err_401_first, err_401_second]

        client = self._make_client()
        with self.assertRaises(StravaAuthError):
            client.get_activity_detail(123)

        # 1 initial GET + 1 retried GET after refresh = 2 GET calls, 0 exponential backoff sleeps
        self.assertEqual(mock_get.call_count, 2)
        mock_post.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("kinetiqo.strava.time.sleep")
    @patch("kinetiqo.strava.requests.post")
    @patch("kinetiqo.strava.requests.get")
    def test_get_streams_recovers_from_401(self, mock_get, mock_post, mock_sleep):
        """Streams endpoint also refreshes token on 401."""
        import time
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "fresh-token", "expires_at": int(time.time()) + 3600, "refresh_token": "ref"}
        )
        err_401 = _http_error_response(401)
        ok_resp = MagicMock(raise_for_status=lambda: None, json=lambda: {"time": {"data": [1, 2]}})
        mock_get.side_effect = [err_401, ok_resp]

        client = self._make_client()
        streams = client.get_streams(123)

        self.assertEqual(streams, {"time": {"data": [1, 2]}})
        self.assertEqual(mock_get.call_count, 2)
        mock_post.assert_called_once()

    @patch("kinetiqo.strava.time.sleep")
    @patch("kinetiqo.strava.requests.get")
    def test_rate_limit_429_raises_strava_rate_limit_error(self, mock_get, mock_sleep):
        """HTTP 429 raises StravaRateLimitError to prevent hammering the API."""
        from kinetiqo.strava import StravaRateLimitError

        mock_get.return_value = _http_error_response(429)
        mock_get.return_value.headers = {}

        client = self._make_client()
        with self.assertRaises(StravaRateLimitError):
            client.get_activity_detail(123)


class TestStravaRateLimitMonitoring(unittest.TestCase):
    """Unit tests for Strava API rate limit parsing, 90% warning detection,
    and callback notifications.
    """

    def setUp(self):
        from kinetiqo.strava import reset_rate_limits
        reset_rate_limits()

    def tearDown(self):
        from kinetiqo.strava import reset_rate_limits
        reset_rate_limits()

    def _make_client(self):
        client = StravaClient(_make_config())
        client._access_token = "token"
        return client

    def test_parse_rate_limit_header(self):
        from kinetiqo.strava import parse_rate_limit_header

        self.assertEqual(parse_rate_limit_header("100,1000"), (100, 1000))
        self.assertEqual(parse_rate_limit_header(" 200 , 2000 "), (200, 2000))
        self.assertEqual(parse_rate_limit_header("50"), (50, 50))
        self.assertIsNone(parse_rate_limit_header(None))
        self.assertIsNone(parse_rate_limit_header(""))
        self.assertIsNone(parse_rate_limit_header("invalid,format"))

    def test_tracker_under_90_percent_no_warning(self):
        from kinetiqo.strava import StravaRateLimitTracker
        tracker = StravaRateLimitTracker()

        headers = {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "50,400",
        }
        warning = tracker.observe(headers)
        self.assertIsNone(warning)
        self.assertIsNone(tracker.get_active_warning())

    def test_tracker_15m_reaches_90_percent(self):
        from kinetiqo.strava import StravaRateLimitTracker
        tracker = StravaRateLimitTracker()

        headers = {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "90,400",
        }
        warning = tracker.observe(headers)
        self.assertIsNotNone(warning)
        self.assertIn("90% limit has been reached", warning)
        self.assertIn("15-minute: 90/100 requests used, 10 remaining", warning)
        self.assertEqual(tracker.get_active_warning(), warning)

    def test_tracker_daily_reaches_90_percent(self):
        from kinetiqo.strava import StravaRateLimitTracker
        tracker = StravaRateLimitTracker()

        headers = {
            "X-RateLimit-Limit": "200,2000",
            "X-RateLimit-Usage": "50,1850",
        }
        warning = tracker.observe(headers)
        self.assertIsNotNone(warning)
        self.assertIn("90% limit has been reached", warning)
        self.assertIn("daily: 1850/2000 requests used, 150 remaining", warning)

    def test_tracker_read_headers_reach_90_percent(self):
        from kinetiqo.strava import StravaRateLimitTracker
        tracker = StravaRateLimitTracker()

        headers = {
            "X-RateLimit-Limit": "200,2000",
            "X-RateLimit-Usage": "50,400",
            "X-ReadRateLimit-Limit": "100,1000",
            "X-ReadRateLimit-Usage": "95,400",
        }
        warning = tracker.observe(headers)
        self.assertIsNotNone(warning)
        self.assertIn("90% limit has been reached", warning)
        self.assertIn("15-minute read: 95/100 requests used, 5 remaining", warning)

    def test_tracker_fallback_to_remaining_header(self):
        from kinetiqo.strava import StravaRateLimitTracker
        tracker = StravaRateLimitTracker()

        headers = {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Remaining": "8,500",
        }
        warning = tracker.observe(headers)
        self.assertIsNotNone(warning)
        self.assertIn("90% limit has been reached", warning)
        self.assertIn("15-minute: 92/100 requests used, 8 remaining", warning)

    def test_tracker_expires_at_reset_window(self):
        from kinetiqo.strava import StravaRateLimitTracker
        tracker = StravaRateLimitTracker()

        now_ts = 1731067200.0  # Exactly at a 15m mark
        headers = {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "92,400",
        }
        tracker.observe(headers, now_ts=now_ts)
        self.assertIsNotNone(tracker.get_active_warning(now_ts=now_ts + 60))

        # After 15 minutes (900 seconds), 15m window has reset
        self.assertIsNone(tracker.get_active_warning(now_ts=now_ts + 901))

    @patch("kinetiqo.strava.logger.warning")
    @patch("kinetiqo.strava.requests.get")
    def test_client_observes_headers_and_notifies_callback(self, mock_get, mock_log_warn):
        """StravaClient._request observes rate limit headers, triggers callback, and logs warning."""
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"id": 123, "name": "Test Ride"}
        resp.headers = {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "94,300",
        }
        mock_get.return_value = resp

        client = self._make_client()
        callback_warnings = []
        client.set_rate_limit_warning_callback(lambda msg: callback_warnings.append(msg))

        detail = client.get_activity_detail(123)
        self.assertEqual(detail["id"], 123)

        # Callback was invoked
        self.assertEqual(len(callback_warnings), 1)
        self.assertIn("90% limit has been reached", callback_warnings[0])
        self.assertIn("15-minute: 94/100", callback_warnings[0])

        # Queued on client
        queued = client.pop_rate_limit_warnings()
        self.assertEqual(len(queued), 1)
        self.assertEqual(client.pop_rate_limit_warnings(), [])

        # Logged via logger.warning
        mock_log_warn.assert_called_once()
        self.assertIn("90% limit has been reached", mock_log_warn.call_args[0][0])

    @patch("kinetiqo.strava.requests.get")
    def test_client_observes_rate_limits_on_429(self, mock_get):
        """Even on HTTP 429, headers are parsed and rate limit warning is recorded."""
        from kinetiqo.strava import StravaRateLimitError

        resp = _http_error_response(429)
        resp.headers = {
            "X-RateLimit-Limit": "100,1000",
            "X-RateLimit-Usage": "100,300",
        }
        mock_get.return_value = resp

        client = self._make_client()
        with self.assertRaises(StravaRateLimitError):
            client.get_activity_detail(123)

        active = client.get_active_rate_limit_warning()
        self.assertIsNotNone(active)
        self.assertIn("90% limit has been reached", active)
        self.assertIn("15-minute: 100/100", active)


if __name__ == "__main__":
    unittest.main()

