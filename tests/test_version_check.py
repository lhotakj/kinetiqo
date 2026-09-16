import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.version_check import check_for_new_version, get_latest_version, CACHE_FILE
from kinetiqo.web.app import app, mark_startup_sync_done


class TestVersionCheck(unittest.TestCase):
    """Test suite for version checking, GitHub release querying, and API integration."""

    def setUp(self):
        mark_startup_sync_done()
        self._orig_testing = app.config.get('TESTING')
        self._orig_login_disabled = app.config.get('LOGIN_DISABLED')
        self._orig_csrf = app.config.get('WTF_CSRF_ENABLED')
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def tearDown(self):
        app.config['TESTING'] = self._orig_testing
        app.config['LOGIN_DISABLED'] = self._orig_login_disabled
        app.config['WTF_CSRF_ENABLED'] = self._orig_csrf
        if CACHE_FILE.exists():
            try:
                CACHE_FILE.unlink()
            except Exception:
                pass

    def test_get_latest_version_from_cached_file(self):
        """If CACHE_FILE is recent, get_latest_version reads from cache without network call."""
        CACHE_FILE.write_text("v2.5.0")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ver = loop.run_until_complete(get_latest_version())
            self.assertEqual(ver, "v2.5.0")
        finally:
            loop.close()

    @patch('kinetiqo.version_check.get_latest_version', new_callable=AsyncMock)
    @patch('kinetiqo.version_check.get_version')
    def test_check_for_new_version_available(self, mock_get_version, mock_get_latest):
        """When latest release on GitHub is strictly newer, check_for_new_version returns alert."""
        mock_get_version.return_value = "2.0.0"
        mock_get_latest.return_value = "v2.1.0"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            msg = loop.run_until_complete(check_for_new_version())
            self.assertIsNotNone(msg)
            self.assertIn("v2.1.0", msg)
        finally:
            loop.close()

    @patch('kinetiqo.version_check.get_latest_version', new_callable=AsyncMock)
    @patch('kinetiqo.version_check.get_version')
    def test_check_for_new_version_up_to_date(self, mock_get_version, mock_get_latest):
        """When current version is equal or newer than GitHub release, returns None."""
        mock_get_version.return_value = "2.1.0"
        mock_get_latest.return_value = "v2.1.0"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            msg = loop.run_until_complete(check_for_new_version())
            self.assertIsNone(msg)
        finally:
            loop.close()

    @patch('kinetiqo.version_check.get_latest_version', new_callable=AsyncMock)
    @patch('kinetiqo.version_check.get_version')
    def test_check_for_new_version_dev_mode(self, mock_get_version, mock_get_latest):
        """When running in development mode ('dev'), returns None."""
        mock_get_version.return_value = "dev"
        mock_get_latest.return_value = "v2.2.0"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            msg = loop.run_until_complete(check_for_new_version())
            self.assertIsNone(msg)
        finally:
            loop.close()

    @patch('kinetiqo.version_check.check_for_new_version', new_callable=AsyncMock)
    def test_latest_version_endpoint(self, mock_check):
        """GET /latest-version returns JSON message."""
        mock_check.return_value = "🆕 New version v2.5.0 available"
        resp = self.client.get('/latest-version')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data, {'message': "🆕 New version v2.5.0 available"})


if __name__ == '__main__':
    unittest.main()
