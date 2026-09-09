import sys, os
# Ensure src/ is on sys.path when running tests directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.web.app import app
from kinetiqo.web.auth import users

class TestCSRFMeta(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_csrf_meta_present_on_login(self):
        rv = self.client.get('/login')
        self.assertEqual(rv.status_code, 200)
        data = rv.get_data(as_text=True)
        self.assertIn('meta name="csrf-token"', data)
        # Verify HTMX config listener is present
        self.assertIn('htmx:configRequest', data)
        self.assertIn('window.fetch = function(input, init)', data)
        self.assertIn('XMLHttpRequest', data)
        self.assertIn('HTMLFormElement', data)
        self.assertIn('window.kinetiqoAddCsrfField', data)

    def test_activities_dynamic_forms_add_csrf_before_submit(self):
        username = next(iter(users))
        with self.client.session_transaction() as session:
            session['_user_id'] = username
            session['_fresh'] = True

        repo = MagicMock()
        repo.get_activities.return_value = []
        with patch('kinetiqo.web.app.get_db', return_value=repo):
            rv = self.client.get('/activities')

        self.assertEqual(rv.status_code, 200)
        data = rv.get_data(as_text=True)
        self.assertIn('vendor/htmx/htmx-2.0.10.min.js', data)
        self.assertIn("window.kinetiqoAddCsrfField(form[0]);", data)
        self.assertIn("action: '/map'", data)
        self.assertIn("action: '/powerskills'", data)
        self.assertIn('action="/logout"', data)
        self.assertIn('name="csrf_token"', data)
        self.assertIn('id="columnSelectModal"', data)
        self.assertIn('background-color: rgba(0, 0, 0, 0.3);', data)
        self.assertNotIn('bg-opacity-30', data)
        self.assertIn('id="selectAllOnAllPagesBtn"', data)
        self.assertIn('id="clearSelectionBtn"', data)
        self.assertIn('for="selectAllOnPage"', data)
        self.assertIn('Select all activities on this page', data)
        self.assertIn('aria-label="Select activity ${data}"', data)
        self.assertIn("table.rows({filter: 'applied'}).count() > 0", data)
        self.assertIn('setButtonState(', data)
        self.assertIn('updateSelectionButtons();', data)

    def test_logout_does_not_allow_get(self):
        rv = self.client.get('/logout')
        self.assertEqual(rv.status_code, 405)

    def test_map_export_includes_watermark(self):
        get = self.client.get('/login')
        html = get.get_data(as_text=True)
        token_match = re.search(r'name="csrf_token" value="([^"]*)"', html)

        username = next(iter(users))
        with self.client.session_transaction() as session:
            session['_user_id'] = username
            session['_fresh'] = True

        data = {'activity_ids[]': ['1']}
        if token_match:
            data['csrf_token'] = token_match.group(1)

        rv = self.client.post('/map', data=data)
        self.assertEqual(rv.status_code, 200)
        page = rv.get_data(as_text=True)
        self.assertIn('const MAP_WATERMARK_SIZE_PCT = 0.05;', page)
        self.assertIn('const MAP_WATERMARK_OPACITY = 0.8;', page)
        self.assertIn('kinetiqo_logo.png', page)
        self.assertIn('await drawMapWatermark(ctx, finalCanvas);', page)

    def test_stop_sync_creates_stop_signal(self):
        get = self.client.get('/login')
        html = get.get_data(as_text=True)
        token_match = re.search(r'name="csrf_token" value="([^"]*)"', html)
        self.assertIsNotNone(token_match)

        username = next(iter(users))
        with self.client.session_transaction() as session:
            session['_user_id'] = username
            session['_fresh'] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            stop_signal = os.path.join(tmpdir, '.sync_stop')
            with patch('kinetiqo.web.app.STOP_SIGNAL_FILE', stop_signal):
                rv = self.client.post(
                    '/api/sync/stop',
                    headers={'X-CSRFToken': token_match.group(1)},
                )

            self.assertEqual(rv.status_code, 204)
            self.assertTrue(os.path.exists(stop_signal))

    def test_post_without_csrf_is_blocked(self):
        # Skip if CSRF not enabled in this environment
        import importlib
        webmod = importlib.import_module('kinetiqo.web.app')
        if getattr(webmod, 'csrf', None) is None:
            self.skipTest('Flask-WTF/CSRF not available in test environment')
        # POSTing without a CSRF token should be rejected
        username, user = next(iter(users.items()))
        rv = self.client.post('/login', data={'username': username, 'password': user['password']})
        self.assertEqual(rv.status_code, 400)
        self.assertIn('CSRF', rv.get_data(as_text=True))

    def test_post_with_csrf_succeeds(self):
        import importlib
        webmod = importlib.import_module('kinetiqo.web.app')
        if getattr(webmod, 'csrf', None) is None:
            self.skipTest('Flask-WTF/CSRF not available in test environment')
        # First GET the login page to obtain a token
        get = self.client.get('/login')
        self.assertEqual(get.status_code, 200)
        html = get.get_data(as_text=True)
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        self.assertIsNotNone(m, 'csrf hidden input not found')
        token = m.group(1)
        # Now POST with token
        username, user = next(iter(users.items()))
        rv = self.client.post(
            '/login',
            data={'username': username, 'password': user['password'], 'csrf_token': token},
            follow_redirects=False,
        )
        # On successful login the app redirects to /activities (302)
        self.assertIn(rv.status_code, (302, 303))

if __name__ == '__main__':
    unittest.main()
