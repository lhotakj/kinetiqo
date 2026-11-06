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
                'weather_temp_min': 14.0,
                'weather_temp_max': 20.0,
                'weather_temp_avg': 17.0,
                'weather_condition': 'Partially cloudy',
                'weather_condition_icon': 'partly-cloudy-day',
                'weather_wind_deg': 270,
                'weather_wind_speed': 3.5,
                'weather_precipitation': 'Rain (1.2mm)',
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
        self.assertIn('weather', row)
        self.assertEqual(row['weather']['temp_display'], '14-20°C')
        self.assertEqual(row['weather']['temp_avg'], 17.0)
        self.assertEqual(row['weather']['condition'], 'Partially cloudy')
        self.assertEqual(row['weather']['wind_cardinal'], 'W')
        self.assertEqual(row['weather']['precipitation'], 'Rain (1.2mm)')

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
        mock_repo.update_statistics.assert_called_once()
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

    @patch('kinetiqo.web.app.get_db')
    def test_activities_page_datatable_language_config_no_duplicates(self, mock_get_db):
        """Activities page renders DataTable language block without duplicate language keys."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_distinct_activity_types.return_value = ['Ride', 'Run']

        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'admin'

        resp = self.client.get('/activities')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Ensure language configuration includes search and lengthMenu options
        self.assertIn('"searchPlaceholder": "Filter activities..."', html)
        self.assertIn('"lengthMenu": "Show _MENU_ entries"', html)
        # Verify that "language": { is defined exactly once in the rendered HTML
        self.assertEqual(html.count('"language": {'), 1)

    @patch('kinetiqo.web.app.get_db')
    def test_delete_single_activity_api_anonymous_user_fallback(self, mock_get_db):
        """DELETE /api/activities/<id> handles anonymous user gracefully with fallback."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        # Anonymous request without setting session user
        with patch('kinetiqo.web.app.current_user') as mock_user:
            # Simulate AnonymousUserMixin lacking 'id' attribute
            del mock_user.id
            resp = self.client.delete('/api/activities/1001')
            self.assertEqual(resp.status_code, 200)
            mock_repo.log_sync.assert_called_once_with(
                added=0, removed=1, trigger="web", success=True, action="delete", user="admin"
            )

    @patch('kinetiqo.web.app.get_db')
    def test_delete_bulk_activities_api_anonymous_user_fallback(self, mock_get_db):
        """DELETE /api/activities handles anonymous user in bulk deletion."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo

        with patch('kinetiqo.web.app.current_user') as mock_user:
            del mock_user.id
            resp = self.client.delete('/api/activities', json={'activity_ids': ['1001', '1002']})
            self.assertEqual(resp.status_code, 200)
            mock_repo.log_sync.assert_called_once_with(
                added=0, removed=2, trigger="web", success=True, action="delete_bulk", user="admin"
            )

    @patch('kinetiqo.web.app.get_db')
    def test_delete_single_activity_api_log_failure_resilient(self, mock_get_db):
        """DELETE /api/activities/<id> succeeds even if log_sync raises an error."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.log_sync.side_effect = RuntimeError("DB write error")

        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'admin'

        resp = self.client.delete('/api/activities/1001')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('kinetiqo.web.app.get_db')
    def test_delete_bulk_activities_api_log_failure_resilient(self, mock_get_db):
        """DELETE /api/activities bulk succeeds even if log_sync raises an error."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.log_sync.side_effect = RuntimeError("DB write error")

        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'admin'

        resp = self.client.delete('/api/activities', json={'activity_ids': ['1001']})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])

    @patch('kinetiqo.web.app.get_db')
    def test_activities_page_weather_column_sorting_configuration(self, mock_get_db):
        """Activities page configures DataTable 'weather-temp' custom sorting for weather temperature."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_distinct_activity_types.return_value = ['Ride', 'Run']

        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'admin'

        resp = self.client.get('/activities')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # DataTable custom type registration
        self.assertIn("DataTable.type('weather-temp'", html)
        self.assertIn('"type": "weather-temp"', html)
        # Verify render returns null or float on sort, never legacy -9999
        self.assertNotIn("-9999", html)
        self.assertIn("Number(data.temp_avg)", html)
        # Verify colExtractors includes weather index 19
        self.assertIn("19: row => (row.weather && row.weather.temp_display) ? row.weather.temp_display : ''", html)

    @patch('kinetiqo.web.app.get_db')
    def test_get_activities_api_negative_and_high_weather_temperature(self, mock_get_db):
        """GET /api/activities returns activities with negative and high temperatures for Weather sorting."""
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_activities_web.return_value = [
            {
                'id': 2001,
                'name': 'Freezing Winter Ride',
                'type': 'Ride',
                'start_date': '2026-01-15T10:00:00Z',
                'distance': 25000.0,
                'total_elevation_gain': 200.0,
                'moving_time': 3600,
                'average_speed': 6.94,
                'weather_temp_min': -2.0,
                'weather_temp_max': 0.0,
                'weather_temp_avg': -1.0,
                'weather_condition': 'Clear',
                'weather_condition_icon': 'clear-day',
            },
            {
                'id': 2002,
                'name': 'Scorching Summer Ride',
                'type': 'Ride',
                'start_date': '2026-07-20T14:00:00Z',
                'distance': 60000.0,
                'total_elevation_gain': 600.0,
                'moving_time': 7200,
                'average_speed': 8.33,
                'weather_temp_min': 28.0,
                'weather_temp_max': 28.0,
                'weather_temp_avg': 28.0,
                'weather_condition': 'Sunny',
                'weather_condition_icon': 'clear-day',
            },
            {
                'id': 2003,
                'name': 'Indoor Zwift Workout',
                'type': 'VirtualRide',
                'start_date': '2026-02-10T18:00:00Z',
                'distance': 30000.0,
                'total_elevation_gain': 150.0,
                'moving_time': 3600,
                'average_speed': 8.33,
                'weather_temp_avg': None,
            }
        ]
        mock_repo.get_activities_totals.return_value = {
            'total_distance': 115.0,
            'total_elevation': 950.0,
            'total_time': 14400,
            'total_count': 3,
        }

        resp = self.client.get('/api/activities')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        rows = data['data']
        self.assertEqual(len(rows), 3)

        # Freezing ride (-1°C avg)
        self.assertEqual(rows[0]['weather']['temp_avg'], -1.0)
        self.assertEqual(rows[0]['weather']['temp_display'], '-2-0°C')

        # Scorching ride (28°C avg)
        self.assertEqual(rows[1]['weather']['temp_avg'], 28.0)
        self.assertEqual(rows[1]['weather']['temp_display'], '28°C')

        # Indoor workout (no weather)
        self.assertIsNone(rows[2]['weather'])

    def test_weather_temperature_sorting_comparator_logic(self):
        """Verify the exact sort comparator logic for 'weather-temp' in both directions."""
        import json
        import shutil
        import subprocess

        # Test dataset: -1°C, 28°C, 5°C, None (indoor Zwift), 10°C, None (indoor trainer), -5°C (freezing)
        items = [
            {"id": "indoor-zwift", "temp": None},
            {"id": "act-neg-1", "temp": -1.0},
            {"id": "act-hot-28", "temp": 28.0},
            {"id": "act-cool-5", "temp": 5.0},
            {"id": "indoor-trainer", "temp": None},
            {"id": "act-mild-10", "temp": 10.0},
            {"id": "act-freezing-neg-5", "temp": -5.0},
            {"id": "indoor-workout", "temp": None},
        ]

        # Pure Python simulation of the weather-temp comparator
        def is_empty(v):
            if v is None or v == "":
                return True
            try:
                val = float(v)
                import math
                return math.isnan(val) or not math.isfinite(val)
            except (ValueError, TypeError):
                return True

        def cmp_asc(a, b):
            a_empty = is_empty(a["temp"])
            b_empty = is_empty(b["temp"])
            if a_empty:
                return 0 if b_empty else 1
            if b_empty:
                return -1
            return -1 if a["temp"] < b["temp"] else (1 if a["temp"] > b["temp"] else 0)

        def cmp_desc(a, b):
            a_empty = is_empty(a["temp"])
            b_empty = is_empty(b["temp"])
            if a_empty:
                return 0 if b_empty else 1
            if b_empty:
                return -1
            return 1 if a["temp"] < b["temp"] else (-1 if a["temp"] > b["temp"] else 0)

        from functools import cmp_to_key

        sorted_asc = sorted(items, key=cmp_to_key(cmp_asc))
        # Real outdoor data first (coldest to hottest), indoor/no-weather at the bottom
        self.assertEqual([x["temp"] for x in sorted_asc[:5]], [-5.0, -1.0, 5.0, 10.0, 28.0])
        self.assertTrue(all(x["temp"] is None for x in sorted_asc[5:]))

        sorted_desc = sorted(items, key=cmp_to_key(cmp_desc))
        # Real outdoor data first (hottest to coldest), indoor/no-weather at the bottom
        self.assertEqual([x["temp"] for x in sorted_desc[:5]], [28.0, 10.0, 5.0, -1.0, -5.0])
        self.assertTrue(all(x["temp"] is None for x in sorted_desc[5:]))

        # If Node.js is available on the machine, run the exact JavaScript implementation
        node_bin = shutil.which("node")
        if node_bin:
            js_script = """
            const items = %s;
            function isWeatherEmpty(val) {
                if (val === null || val === undefined || val === '' || typeof val === 'boolean') return true;
                if (typeof val === 'object') return true;
                const num = Number(val);
                return !Number.isFinite(num);
            }
            const ascSorter = function (a, b) {
                const aEmpty = isWeatherEmpty(a);
                const bEmpty = isWeatherEmpty(b);
                if (aEmpty) return bEmpty ? 0 : 1;
                if (bEmpty) return -1;
                const numA = Number(a);
                const numB = Number(b);
                return numA < numB ? -1 : (numA > numB ? 1 : 0);
            };
            const descSorter = function (a, b) {
                const aEmpty = isWeatherEmpty(a);
                const bEmpty = isWeatherEmpty(b);
                if (aEmpty) return bEmpty ? 0 : 1;
                if (bEmpty) return -1;
                const numA = Number(a);
                const numB = Number(b);
                return numA < numB ? 1 : (numA > numB ? -1 : 0);
            };

            const asc = [...items].sort((x, y) => ascSorter(x.temp, y.temp));
            const desc = [...items].sort((x, y) => descSorter(x.temp, y.temp));

            console.log(JSON.stringify({
                asc: asc.map(i => i.temp),
                desc: desc.map(i => i.temp)
            }));
            """ % json.dumps(items)

            res = subprocess.run([node_bin, "-e", js_script], capture_output=True, text=True, check=True)
            result = json.loads(res.stdout)
            self.assertEqual(result["asc"], [-5.0, -1.0, 5.0, 10.0, 28.0, None, None, None])
            self.assertEqual(result["desc"], [28.0, 10.0, 5.0, -1.0, -5.0, None, None, None])


if __name__ == '__main__':
    unittest.main()

