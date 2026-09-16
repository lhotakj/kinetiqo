import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.db.repository import compute_best_average_power
from kinetiqo.web.app import app, mark_startup_sync_done, POWER_SKILLS_DURATIONS


class TestPowerSkills(unittest.TestCase):
    """Test suite for /powerskills endpoint and sliding-window power calculation."""

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

    def _mock_authenticated_user(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

    def test_compute_best_average_power_algorithm(self):
        """Verify compute_best_average_power returns correct sliding-window maximum."""
        # Empty or too short
        self.assertEqual(compute_best_average_power([], 5), 0.0)
        self.assertEqual(compute_best_average_power([100, 200], 5), 0.0)

        # Exact length
        self.assertEqual(compute_best_average_power([100, 200, 300], 3), 200.0)

        # Sliding window finds highest peak
        samples = [100, 100, 500, 500, 500, 100, 100]
        # 3-second window should be (500 + 500 + 500) / 3 = 500.0
        self.assertEqual(compute_best_average_power(samples, 3), 500.0)
        # 5-second window: max is [100, 500, 500, 500, 100] -> 1700 / 5 = 340.0
        self.assertEqual(compute_best_average_power(samples, 5), 340.0)

    @patch('kinetiqo.web.app.get_db')
    def test_powerskills_no_activities_redirects(self, mock_get_db):
        """GET or POST /powerskills with empty activity IDs redirects with a flash warning."""
        # GET with no ids
        resp = self.client.get('/powerskills')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/activities', resp.headers['Location'])

        # POST with empty activity_ids[]
        resp = self.client.post('/powerskills', data={})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/activities', resp.headers['Location'])

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_powerskills_get_with_ids_computes_radar_data(self, mock_get_db, mock_get_user):
        """GET /powerskills?ids=101,102 fetches metadata and streams to compute radar data."""
        self._mock_authenticated_user(mock_get_user)
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        mock_repo.get_activities_by_ids.return_value = [
            {'id': '101', 'name': 'Morning Sprint', 'start_date': '2026-06-01T08:00:00Z'},
            {'id': '102', 'name': 'Endurance Ride', 'start_date': '2026-06-02T08:00:00Z'},
        ]

        # Activity 101 has high short-duration power (5s = 600W)
        # Activity 102 has high sustained power (60s = 350W)
        stream_101 = [600] * 10 + [200] * 50
        stream_102 = [350] * 60

        mock_repo.get_watts_streams_for_activities.return_value = {
            '101': stream_101,
            '102': stream_102,
        }

        resp = self.client.get('/powerskills?ids=101,102')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        mock_repo.get_activities_by_ids.assert_called_once_with(['101', '102'])
        mock_repo.get_watts_streams_for_activities.assert_called_once_with(['101', '102'])

        self.assertIn('Power Skills', html)
        self.assertIn('Morning Sprint', html)
        self.assertIn('Endurance Ride', html)

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_powerskills_post_with_activity_ids(self, mock_get_db, mock_get_user):
        """POST /powerskills with activity_ids[] calculates power curve for all standard durations."""
        self._mock_authenticated_user(mock_get_user)
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        mock_repo.get_activities_by_ids.return_value = [
            {'id': '201', 'name': 'Century Ride', 'start_date': '2026-07-04T07:00:00Z'},
        ]
        mock_repo.get_watts_streams_for_activities.return_value = {
            '201': [250] * 3600,
        }

        resp = self.client.post('/powerskills', data={'activity_ids[]': ['201']})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # All duration labels should be present
        for d in POWER_SKILLS_DURATIONS:
            self.assertIn(d["label"], html)

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_powerskills_handles_db_exception_gracefully(self, mock_get_db, mock_get_user):
        """If repository throws, /powerskills handles the exception and renders fallback zeros."""
        self._mock_authenticated_user(mock_get_user)
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_activities_by_ids.side_effect = RuntimeError("Database connection lost")

        resp = self.client.get('/powerskills?ids=999')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Power Skills', html)


if __name__ == '__main__':
    unittest.main()
