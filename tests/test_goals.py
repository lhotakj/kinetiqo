import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.web.app import app, mark_startup_sync_done


class TestGoalsAPI(unittest.TestCase):
    """Test suite for /api/goals GET and PUT endpoints."""

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

    @patch('kinetiqo.web.app.get_db')
    def test_get_goals_api_with_profile_and_goals(self, mock_get_db):
        """GET /api/goals returns mapped goal configuration for authenticated athlete."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_profile.return_value = {'athlete_id': 12345}
        mock_repo.get_goals.return_value = [
            {
                'activity_type_id': 1,
                'weekly_distance_goal': 150.0,
                'monthly_distance_goal': 600.0,
                'yearly_distance_goal': 7000.0,
                'weekly_elevation_goal': 2000.0,
                'monthly_elevation_goal': 8000.0,
                'yearly_elevation_goal': 90000.0,
            }
        ]

        resp = self.client.get('/api/goals')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertIn('1', data)  # Cycling category id
        self.assertEqual(data['1']['name'], 'Cycling')
        self.assertEqual(data['1']['weekly_distance_goal'], 150.0)
        self.assertEqual(data['1']['yearly_elevation_goal'], 90000.0)

    @patch('kinetiqo.web.app.get_db')
    def test_get_goals_api_no_profile_returns_empty_mapping(self, mock_get_db):
        """GET /api/goals when profile does not exist returns initialized empty goal structure."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_profile.return_value = None

        resp = self.client.get('/api/goals')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('1', data)
        self.assertIsNone(data['1']['weekly_distance_goal'])

    @patch('kinetiqo.web.app.get_db')
    def test_update_goals_api_success(self, mock_get_db):
        """PUT /api/goals upserts athlete goals into the database."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_profile.return_value = {'athlete_id': 12345}

        payload = [
            {
                'activity_type_id': 1,
                'weekly_distance_goal': '200',
                'monthly_distance_goal': '800',
                'yearly_distance_goal': '10000',
                'weekly_elevation_goal': '2500',
                'monthly_elevation_goal': '10000',
                'yearly_elevation_goal': '120000',
            }
        ]

        resp = self.client.put('/api/goals', json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data, {'success': True})

        mock_repo.upsert_goal.assert_called_once_with(
            athlete_id=12345,
            activity_type_id=1,
            weekly_distance_goal=200.0,
            monthly_distance_goal=800.0,
            yearly_distance_goal=10000.0,
            weekly_elevation_goal=2500.0,
            monthly_elevation_goal=10000.0,
            yearly_elevation_goal=120000.0,
        )

    @patch('kinetiqo.web.app.get_db')
    def test_update_goals_api_invalid_payload(self, mock_get_db):
        """PUT /api/goals with non-list body returns 400 error."""
        resp = self.client.put('/api/goals', json={'activity_type_id': 1})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    @patch('kinetiqo.web.app.get_db')
    def test_update_goals_api_no_profile_returns_404(self, mock_get_db):
        """PUT /api/goals when profile does not exist returns 404."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_profile.return_value = None

        resp = self.client.put('/api/goals', json=[{'activity_type_id': 1}])
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertIn('error', data)


if __name__ == '__main__':
    unittest.main()
