import unittest
from unittest.mock import patch, MagicMock

from kinetiqo.web.app import app, _compute_best_average_power, FTP_DURATION_SECONDS, FTP_FACTOR, CYCLING_SPORT_TYPES

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

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_returns_95pct_of_best_20min_power(self, mock_get_user, mock_get_db):
        """FTP page should display 95%% of the best 20-min avg power across cycling activities."""
        # Arrange
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = MOCK_CYCLING_ACTIVITIES
        mock_repo.get_watts_streams_for_activities.return_value = {
            '2001': MOCK_WATTS_2001,
            '2002': MOCK_WATTS_2002,
            '2003': MOCK_WATTS_2003,
        }
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
        mock_repo.get_activity_ids_by_types.assert_called_once_with(CYCLING_SPORT_TYPES)

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
        mock_repo.get_watts_streams_for_activities.assert_not_called()

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_ftp_no_streams_long_enough(self, mock_get_user, mock_get_db):
        """FTP should be 0 when no activity has a 20-min watts stream."""
        # Arrange
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activity_ids_by_types.return_value = [
            {"id": 3001, "name": "Quick Ride", "start_date": "2025-09-01T10:00:00+00:00"},
        ]
        # Only 600 seconds of data — too short
        mock_repo.get_watts_streams_for_activities.return_value = {
            '3001': [200.0] * 600,
        }
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


if __name__ == '__main__':
    unittest.main()

