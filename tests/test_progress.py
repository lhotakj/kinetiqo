import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.web.app import app, mark_startup_sync_done
from kinetiqo.web.progress import _aggregate_activity


class TestProgress(unittest.TestCase):
    """Test suite for /progress page and /api/progress_data aggregation."""

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

    def test_aggregate_activity_helper(self):
        """Verify _aggregate_activity correctly converts distance (km) and elevation (m)."""
        day_map = {
            '2026-06-15': {'dist': 0.0, 'elev': 0.0},
        }

        # Valid activity matching date in day_map
        activity = {
            'start_date': '2026-06-15T10:00:00Z',
            'distance': 45000.0,  # 45 km
            'total_elevation_gain': 650.0,  # 650 m
        }
        _aggregate_activity(activity, day_map)
        self.assertEqual(day_map['2026-06-15']['dist'], 45.0)
        self.assertEqual(day_map['2026-06-15']['elev'], 650.0)

        # Missing or invalid date should be ignored without exception
        _aggregate_activity({'start_date': None, 'distance': 1000}, day_map)
        _aggregate_activity({'start_date': '2026-01-01T00:00:00Z', 'distance': 1000}, day_map)
        self.assertEqual(day_map['2026-06-15']['dist'], 45.0)

    @patch('flask_login.utils._get_user')
    def test_progress_page_get(self, mock_get_user):
        """GET /progress renders the progress page shell."""
        self._mock_authenticated_user(mock_get_user)
        resp = self.client.get('/progress')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Progress', html)

    @patch('kinetiqo.web.app.get_db')
    def test_progress_data_api_sentinel_no_match(self, mock_get_db):
        """GET /api/progress_data with types[]=_NO_MATCH_ immediately returns empty structures."""
        resp = self.client.get('/api/progress_data?types[]=_NO_MATCH_')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['week'], {'dates': [], 'distance': [], 'elevation': []})
        self.assertEqual(data['month'], {'dates': [], 'distance': [], 'elevation': []})
        self.assertEqual(data['year'], {'dates': [], 'distance': [], 'elevation': []})

    @patch('kinetiqo.web.app.get_db')
    def test_progress_data_api_aggregates_ranges(self, mock_get_db):
        """GET /api/progress_data queries repository and aggregates week/month/year data."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        today_str = datetime.now().strftime('%Y-%m-%d')
        mock_repo.get_activities_web.return_value = [
            {
                'id': 1,
                'start_date': f'{today_str}T09:00:00Z',
                'distance': 25000.0,
                'total_elevation_gain': 300.0,
            }
        ]

        resp = self.client.get('/api/progress_data?types[]=Ride&types[]=Run')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertIn('week', data)
        self.assertIn('month', data)
        self.assertIn('year', data)

        # Dates array contains today_str
        self.assertIn(today_str, data['week']['dates'])
        self.assertIn(today_str, data['month']['dates'])
        self.assertIn(today_str, data['year']['dates'])

        # Check aggregated distance
        today_idx = data['week']['dates'].index(today_str)
        self.assertEqual(data['week']['distance'][today_idx], 25.0)
        self.assertEqual(data['week']['elevation'][today_idx], 300.0)


if __name__ == '__main__':
    unittest.main()
