import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.web.app import app, mark_startup_sync_done


class TestActivitiesAPI(unittest.TestCase):
    """Test suite for /api/activities endpoints (querying and single/bulk deletion)."""

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
    def test_get_activities_api_client_side_mode(self, mock_get_db):
        """GET /api/activities returns formatted rows and totals for DataTables."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        mock_repo.get_activities_web.return_value = [
            {
                'id': 1001,
                'name': 'Afternoon Gravel Ride',
                'type': 'Ride',
                'start_date': '2026-06-10T14:30:00Z',
                'distance': 35400.0,
                'total_elevation_gain': 450.0,
                'moving_time': 5400,
                'average_speed': 6.55,
                'average_heartrate': 142,
                'average_watts': 195.0,
                'max_watts': 520.0,
                'weighted_average_watts': 210.0,
                'device_watts': 1,
                'calories': 850.0,
                'kilojoules': 1050.0,
                'achievement_count': 3,
                'pr_count': 1,
                'suffer_score': 65,
                'average_temp': 22.0,
                'elev_high': 350.0,
                'elev_low': 120.0,
                'gear_id': 'g123',
                'has_heartrate': 1,
                'workout_type': 10,
            }
        ]
        mock_repo.get_activities_totals.return_value = {
            'total_distance': 35.4,
            'total_elevation': 450.0,
            'total_time': 5400,
            'total_count': 1,
        }

        resp = self.client.get('/api/activities')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertIn('data', data)
        self.assertIn('totals', data)
        self.assertEqual(len(data['data']), 1)

        row = data['data'][0]
        self.assertEqual(row['id'], 1001)
        self.assertEqual(row['name'], 'Afternoon Gravel Ride')
        self.assertEqual(row['distance'], 35400.0)
        self.assertIn('display', row['date'])
        self.assertIn('timestamp', row['date'])

    @patch('kinetiqo.web.app.get_db')
    def test_get_activities_api_server_side_pagination(self, mock_get_db):
        """GET /api/activities with pagination and sorting params queries repo accordingly."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_activities_web.return_value = []
        mock_repo.get_activities_totals.return_value = {}

        resp = self.client.get('/api/activities?page=3&per_page=25&sortColumn=distance&sortDir=ASC&types[]=Ride&startDate=2026-01-01&endDate=2026-12-31')
        self.assertEqual(resp.status_code, 200)

        mock_repo.get_activities_web.assert_called_once_with(
            limit=25,
            offset=50,
            sort_by='distance',
            sort_order='ASC',
            types=['Ride'],
            start_date='2026-01-01',
            end_date='2026-12-31',
        )

    @patch('kinetiqo.web.app.get_db')
    def test_delete_single_activity_api(self, mock_get_db):
        """DELETE /api/activities/<activity_id> removes activity and logs sync deletion."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'admin'

        resp = self.client.delete('/api/activities/1001')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

        mock_repo.delete_activity.assert_called_once_with('1001')
        mock_repo.log_sync.assert_called_once()

    @patch('kinetiqo.web.app.get_db')
    def test_delete_bulk_activities_api_success(self, mock_get_db):
        """DELETE /api/activities with activity_ids array deletes all specified activities."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'admin'

        resp = self.client.delete('/api/activities', json={'activity_ids': ['1001', '1002', '1003']})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

        mock_repo.delete_activities.assert_called_once_with(['1001', '1002', '1003'])
        mock_repo.log_sync.assert_called_once()

    @patch('kinetiqo.web.app.get_db')
    def test_delete_bulk_activities_api_empty_ids(self, mock_get_db):
        """DELETE /api/activities with missing or empty activity_ids returns 400."""
        resp = self.client.delete('/api/activities', json={'activity_ids': []})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])

    @patch('kinetiqo.web.app.get_db')
    def test_activities_page_loading_indicator(self, mock_get_db):
        """Activities page renders DataTable with kinetiqo-loading-32x32.webp processing icon."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_distinct_activity_types.return_value = ['Ride', 'Run']

        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'admin'

        resp = self.client.get('/activities')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # DataTable processing config must use the unified WebP loading asset
        self.assertIn('/static/img/kinetiqo-loading-32x32.webp', html)
        self.assertIn('"processing": true', html)
        self.assertIn('"loadingRecords": \'&nbsp;\'', html)


if __name__ == '__main__':
    unittest.main()

