"""Unit tests for login page, remember me functionality, and theme support."""

import re
import unittest

from unittest.mock import MagicMock, patch

from kinetiqo.web.app import app, mark_startup_sync_done
from kinetiqo.web.auth import users


class TestLogin(unittest.TestCase):
    """Test suite for authentication, remember me, and theme handling on /login."""

    def setUp(self):
        mark_startup_sync_done()
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.mock_repo = MagicMock()
        self.db_patcher = patch('kinetiqo.web.app.get_db', return_value=self.mock_repo)
        self.db_patcher.start()
        self.client = app.test_client()
        self.username, self.user_info = next(iter(users.items()))
        self.password = self.user_info['password']

    def tearDown(self):
        self.db_patcher.stop()

    def test_login_page_renders_form_and_theme_controls(self):
        """Verify login page includes username, password, remember-me checkbox and theme controls."""
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Form controls
        self.assertIn('id="username"', html)
        self.assertIn('id="password"', html)
        self.assertIn('id="remember"', html)
        self.assertIn('name="remember"', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn('for="remember"', html)
        self.assertIn('Remember me', html)
        self.assertIn('aria-label="Remember me on this device"', html)

        # Theme controls & persistence script
        self.assertIn('id="theme-toggle"', html)
        self.assertIn("localStorage.getItem('theme')", html)
        self.assertIn("themeCookie", html)
        self.assertIn("document.documentElement.classList.add('dark')", html)

    def test_login_without_remember_me_does_not_set_remember_cookie(self):
        """Logging in without remember me should not emit a remember_token cookie."""
        resp = self.client.post('/login', data={
            'username': self.username,
            'password': self.password,
        }, follow_redirects=False)

        self.assertIn(resp.status_code, (302, 303))
        self.assertEqual(resp.headers.get('Location'), '/activities')

        # Check Set-Cookie headers
        set_cookies = resp.headers.getlist('Set-Cookie')
        cookie_text = " ".join(set_cookies)
        self.assertNotIn('remember_token=', cookie_text)

    def test_login_with_remember_me_sets_secure_remember_cookie(self):
        """Logging in with remember=1 sets the remember_token cookie with safe attributes."""
        resp = self.client.post('/login', data={
            'username': self.username,
            'password': self.password,
            'remember': '1',
        }, follow_redirects=False)

        self.assertIn(resp.status_code, (302, 303))
        self.assertEqual(resp.headers.get('Location'), '/activities')

        # Verify remember_token cookie is present in Set-Cookie headers
        set_cookies = resp.headers.getlist('Set-Cookie')
        remember_cookie = next((c for c in set_cookies if 'remember_token=' in c), None)
        self.assertIsNotNone(remember_cookie, "Expected remember_token in Set-Cookie headers")

        # Verify safety flags
        self.assertIn('HttpOnly', remember_cookie)
        self.assertIn('SameSite=Lax', remember_cookie)
        self.assertIn('Path=/', remember_cookie)

    def test_authenticated_user_redirected_away_from_login(self):
        """An already authenticated user visiting /login should be redirected to /activities."""
        with self.client.session_transaction() as sess:
            sess['_user_id'] = self.username
            sess['_fresh'] = True

        resp = self.client.get('/login', follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertEqual(resp.headers.get('Location'), '/activities')

    def test_invalid_login_shows_error(self):
        """Invalid credentials show an error flash message and return 200."""
        resp = self.client.post('/login', data={
            'username': self.username,
            'password': 'wrong-password-xyz',
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Invalid username or password', html)


if __name__ == '__main__':
    unittest.main()
