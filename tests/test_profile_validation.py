"""Mocked unit tests for /profile page and /api/profile validation.

Ensures that:
- /profile page renders with HTTP 200.
- PUT /api/profile validates FTP between 1 and 1000 W.
- PUT /api/profile validates UPDATE_STRAVA_* templates server-side.
"""

import unittest
from unittest.mock import MagicMock, patch
from kinetiqo.web.app import app
from kinetiqo.web.auth import users


class TestProfileAPIValidation(unittest.TestCase):
    """Unit tests for /profile page and /api/profile endpoint validation."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        username = next(iter(users))
        with self.client.session_transaction() as session:
            session["_user_id"] = username
            session["_fresh"] = True

    def test_profile_page_renders_200(self):
        response = self.client.get('/profile')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Profile', response.data)

    @patch('kinetiqo.web.app.get_db')
    def test_update_profile_valid_template_and_ftp(self, mock_get_db):
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Test',
            'last_name': 'User',
            'weight': 70.0,
            'ftp': 250.0,
            'refresh_token': 'secret'
        }
        mock_get_db.return_value = mock_repo

        response = self.client.put('/api/profile', json={
            'ftp': 310.0,
            'update_strava_cycling_indoor': '{{cycling-distance-total-year}}'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['ftp'], 310.0)
        self.assertEqual(data['update_strava_cycling_indoor'], '{{cycling-distance-total-year}}')
        mock_repo.upsert_profile.assert_called_once()

    @patch('kinetiqo.web.app.get_db')
    def test_update_profile_ftp_out_of_bounds_returns_422(self, mock_get_db):
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Test',
            'last_name': 'User',
            'weight': 70.0,
            'ftp': 250.0,
            'refresh_token': 'secret'
        }
        mock_get_db.return_value = mock_repo

        # FTP <= 0
        response = self.client.put('/api/profile', json={'ftp': 0})
        self.assertEqual(response.status_code, 422)
        self.assertIn('FTP must be between 1 and 1000 W.', response.get_json()['error'])

        # FTP > 1000
        response = self.client.put('/api/profile', json={'ftp': 1001})
        self.assertEqual(response.status_code, 422)
        self.assertIn('FTP must be between 1 and 1000 W.', response.get_json()['error'])
        mock_repo.upsert_profile.assert_not_called()

    @patch('kinetiqo.web.app.get_db')
    def test_update_profile_invalid_brace_template_returns_422(self, mock_get_db):
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Test',
            'last_name': 'User',
            'weight': 70.0,
            'refresh_token': 'secret'
        }
        mock_get_db.return_value = mock_repo

        response = self.client.put('/api/profile', json={
            'update_strava_cycling_outdoor': '{{cycling-distance-total-year'
        })
        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertIn('field', data)
        self.assertEqual(data['field'], 'update_strava_cycling_outdoor')
        self.assertIn('Mismatched braces', data['error'])
        mock_repo.upsert_profile.assert_not_called()

    @patch('kinetiqo.web.app.get_db')
    def test_update_profile_unknown_variable_returns_422(self, mock_get_db):
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Test',
            'last_name': 'User',
            'weight': 70.0,
            'refresh_token': 'secret'
        }
        mock_get_db.return_value = mock_repo

        response = self.client.put('/api/profile', json={
            'update_strava_running_indoor': '{{unknown-var}}'
        })
        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data['field'], 'update_strava_running_indoor')
        self.assertIn('Unknown variable', data['error'])
        mock_repo.upsert_profile.assert_not_called()


if __name__ == '__main__':
    unittest.main()
