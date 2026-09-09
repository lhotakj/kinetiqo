"""Regression tests for the Strava reconnect/reauthorize scope list.

Strava's ``/oauth/authorize`` endpoint rejects a ``scope`` query parameter
that contains a duplicate entry with a ``400 Bad Request`` /
``{"errors":[{"resource":"Authorize","field":"scope","code":"invalid"}]}``
response. This module guards against that regression.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("STRAVA_CLIENT_ID", "test-client-id")
os.environ.setdefault("STRAVA_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("STRAVA_REFRESH_TOKEN", "test-refresh-token")

from kinetiqo.web import app as web_app  # noqa: E402


class TestStravaReauthScopeHasNoDuplicates(unittest.TestCase):
    """STRAVA_REAUTH_SCOPES must not list the same scope twice."""

    def test_scope_constant_has_no_duplicate_entries(self):
        scopes = web_app.STRAVA_REAUTH_SCOPES.split(",")
        self.assertEqual(
            len(scopes),
            len(set(scopes)),
            f"Duplicate scope(s) found in STRAVA_REAUTH_SCOPES: {scopes!r}",
        )

    def test_scope_constant_contains_expected_scopes(self):
        scopes = set(web_app.STRAVA_REAUTH_SCOPES.split(","))
        self.assertEqual(
            scopes,
            {"activity:read_all", "profile:read_all", "activity:write"},
        )

    def test_build_authorize_url_has_no_duplicate_scopes(self):
        web_app.config = MagicMock(strava_client_id="test-client-id")
        with web_app.app.test_request_context("/"):
            url = web_app._build_strava_authorize_url("some-state")

        query = parse_qs(urlparse(url).query)
        scope_param = query["scope"][0]
        scopes = scope_param.split(",")
        self.assertEqual(
            len(scopes),
            len(set(scopes)),
            f"Duplicate scope(s) found in built authorize URL: {scopes!r}",
        )


if __name__ == "__main__":
    unittest.main()
