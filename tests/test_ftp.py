import json
import unittest
from unittest.mock import patch, MagicMock

from kinetiqo.web.app import app, _compute_best_average_power, FTP_DURATION_SECONDS, FTP_FACTOR, CYCLING_SPORT_TYPES
from kinetiqo.web.app import _power_cache
from kinetiqo.db.repository import compute_best_power_per_activity

# --- Mock Data ---
MOCK_CYCLING_ACTIVITIES = [
    {"id": 2001, "name": "Morning Ride", "start_date": "2025-06-15T07:00:00+00:00"},
    {"id": 2002, "name": "Evening Ride", "start_date": "2025-07-20T17:30:00+00:00"},
    {"id": 2003, "name": "Short Spin", "start_date": "2025-08-01T08:00:00+00:00"},
]

# A watts stream long enough for a 20-min window (1200 samples at 1 Hz)
# Activity 2001: 1200 seconds at 250 W → best 20-min avg = 250 → FTP = 238
MOCK_WATTS_2001 = [250.0] * 1200

# Activity 2002: 1200 seconds at 280 W → best 20-min avg = 280 → FTP = 266 (the winner)
MOCK_WATTS_2002 = [280.0] * 1200

# Activity 2003: only 600 seconds → too short for a 20-min window
MOCK_WATTS_2003 = [300.0] * 600


class TestFTPRoute(unittest.TestCase):
    """Mocked unit tests for the /ftp route."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        # Disable login_required for testing
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        # Clear the power cache between tests so cached results from one test
        # don't leak into another.
        _power_cache.invalidate()

    @staticmethod
    def _make_power_side_effect(watts_map):
        """Return a side_effect callable for ``get_best_power_per_activity``
        that delegates to the real Python sliding-window helper using the
        given *watts_map* as the underlying watts data."""
        def _side_effect(activity_ids, duration_seconds, min_total_samples=0):
            subset = {aid: watts_map[aid] for aid in activity_ids if aid in watts_map}
            return compute_best_power_per_activity(subset, duration_seconds, min_total_samples)
        return _side_effect

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_returns_95pct_of_best_20min_power(self, mock_get_user, mock_get_db):
        """FTP page should display 95%% of the best 20-min avg power across cycling activities."""
        # Arrange
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        watts_map = {
            '2001': MOCK_WATTS_2001,
            '2002': MOCK_WATTS_2002,
            '2003': MOCK_WATTS_2003,
        }

        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = MOCK_CYCLING_ACTIVITIES
        mock_repo.get_best_power_per_activity.side_effect = self._make_power_side_effect(watts_map)
        mock_get_db.return_value = mock_repo

        # Act
        response = self.client.get('/ftp')

        # Assert
        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        # The best 20-min power is 280 W from activity 2002 → FTP = 280 * 0.95 = 266
        self.assertIn('266', html)
        self.assertIn('Evening Ride', html)
        # Verify the repository was called with cycling sport types
        mock_repo.get_activity_ids_by_types.assert_called_once()

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_no_cycling_activities(self, mock_get_user, mock_get_db):
        """FTP page should show a warning when no cycling activities exist."""
        # Arrange
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = []
        mock_get_db.return_value = mock_repo

        # Act
        response = self.client.get('/ftp')

        # Assert
        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn('No Power Data', html)
        mock_repo.get_best_power_per_activity.assert_not_called()

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_no_streams_long_enough(self, mock_get_user, mock_get_db):
        """FTP should be 0 when no activity has a 20-min watts stream."""
        # Arrange
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        watts_map = {
            '3001': [200.0] * 600,  # Only 600 seconds of data — too short
        }

        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = [
            {"id": 3001, "name": "Quick Ride", "start_date": "2025-09-01T10:00:00+00:00"},
        ]
        mock_repo.get_best_power_per_activity.side_effect = self._make_power_side_effect(watts_map)
        mock_get_db.return_value = mock_repo

        # Act
        response = self.client.get('/ftp')

        # Assert
        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn('No Power Data', html)


class TestComputeBestAveragePower(unittest.TestCase):
    """Unit tests for the _compute_best_average_power helper used by FTP."""

    def test_exact_window_size(self):
        """When the stream length equals the window, the result is the average."""
        watts = [200.0, 300.0, 250.0]
        result = _compute_best_average_power(watts, 3)
        self.assertAlmostEqual(result, 250.0)

    def test_sliding_window_finds_best(self):
        """The function should find the best window in a longer stream."""
        # 5 samples, window=3: windows are [100,100,100]=100, [100,100,400]=200, [100,400,400]=300
        watts = [100.0, 100.0, 100.0, 400.0, 400.0]
        result = _compute_best_average_power(watts, 3)
        self.assertAlmostEqual(result, 300.0)

    def test_insufficient_data(self):
        """Should return 0.0 when stream is shorter than the window."""
        watts = [250.0] * 10
        result = _compute_best_average_power(watts, 1800)
        self.assertEqual(result, 0.0)

    def test_empty_stream(self):
        """Should return 0.0 for an empty stream."""
        result = _compute_best_average_power([], 1800)
        self.assertEqual(result, 0.0)


class TestFTPHistoryAPI(unittest.TestCase):
    """Mocked unit tests for the /api/ftp_history endpoint."""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        _power_cache.invalidate()

    @staticmethod
    def _make_power_side_effect(watts_map):
        def _side_effect(activity_ids, duration_seconds, min_total_samples=0):
            subset = {aid: watts_map[aid] for aid in activity_ids if aid in watts_map}
            return compute_best_power_per_activity(subset, duration_seconds, min_total_samples)
        return _side_effect

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_history_returns_per_ride_values(self, mock_get_user, mock_get_db):
        """The API should return an FTP value for each ride with sufficient data."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        watts_map = {
            '2001': MOCK_WATTS_2001,
            '2002': MOCK_WATTS_2002,
            '2003': MOCK_WATTS_2003,  # too short — should be excluded
        }

        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = MOCK_CYCLING_ACTIVITIES
        mock_repo.get_best_power_per_activity.side_effect = self._make_power_side_effect(watts_map)
        mock_get_db.return_value = mock_repo

        response = self.client.get('/api/ftp_history?period=all')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        # Only 2001 and 2002 have ≥1200 samples
        self.assertEqual(len(data['dates']), 2)
        self.assertEqual(len(data['ftp_values']), 2)
        self.assertEqual(len(data['activity_names']), 2)
        # Sorted chronologically: 2001 (Jun 15) before 2002 (Jul 20)
        self.assertEqual(data['dates'][0], '2025-06-15')
        self.assertEqual(data['dates'][1], '2025-07-20')
        # 250 * 0.95 = 237.5 and 280 * 0.95 = 266.0
        self.assertAlmostEqual(data['ftp_values'][0], 237.5, places=1)
        self.assertAlmostEqual(data['ftp_values'][1], 266.0, places=1)

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_history_no_activities(self, mock_get_user, mock_get_db):
        """The API should return empty arrays when no cycling activities exist."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = []
        mock_get_db.return_value = mock_repo

        response = self.client.get('/api/ftp_history?period=all')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertEqual(data['dates'], [])
        self.assertEqual(data['ftp_values'], [])

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_history_period_filter(self, mock_get_user, mock_get_db):
        """The API should exclude activities outside the requested period."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        # One recent activity and one old one
        activities = [
            {"id": 4001, "name": "Old Ride", "start_date": "2020-01-01T08:00:00+00:00"},
            {"id": 4002, "name": "Recent Ride", "start_date": "2026-03-10T08:00:00+00:00"},
        ]
        watts_map = {
            '4002': [260.0] * 1200,
        }
        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = activities
        mock_repo.get_best_power_per_activity.side_effect = self._make_power_side_effect(watts_map)
        mock_get_db.return_value = mock_repo

        # Last 30 days should only include the recent ride
        response = self.client.get('/api/ftp_history?period=30')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        # Only the recent ride should produce an FTP value
        called_ids = mock_repo.get_best_power_per_activity.call_args[0][0]
        self.assertNotIn('4001', called_ids)
        self.assertIn('4002', called_ids)


if __name__ == '__main__':
    unittest.main()

