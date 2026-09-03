"""Unit tests for GPS track simplification and Haversine distance calculations."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from unittest.mock import MagicMock, patch
from kinetiqo.gps_simplify import _haversine_m, simplify_track, GPS_SIMPLIFICATION_THRESHOLDS
from kinetiqo.web.app import app


class TestGpsSimplify(unittest.TestCase):
    """Test suite for O(N) Haversine GPS track decimation."""

    def test_threshold_levels_mapping(self):
        """Verify scale 0 to 10 mapped thresholds."""
        self.assertEqual(len(GPS_SIMPLIFICATION_THRESHOLDS), 11)
        self.assertEqual(GPS_SIMPLIFICATION_THRESHOLDS[0], 0.0)
        self.assertEqual(GPS_SIMPLIFICATION_THRESHOLDS[1], 3.0)
        self.assertEqual(GPS_SIMPLIFICATION_THRESHOLDS[4], 15.0)
        self.assertEqual(GPS_SIMPLIFICATION_THRESHOLDS[10], 100.0)

    def test_haversine_zero_distance(self):
        """Identical coordinates return 0.0 metres."""
        dist = _haversine_m(50.0, 14.0, 50.0, 14.0)
        self.assertAlmostEqual(dist, 0.0, places=5)

    def test_haversine_known_distance(self):
        """Distance between Prague (50.0875, 14.4214) and Pilsen (49.7475, 13.3775) is ~78-80 km."""
        dist = _haversine_m(50.0875, 14.4214, 49.7475, 13.3775)
        self.assertGreater(dist, 75_000)
        self.assertLess(dist, 85_000)

    def test_simplify_track_short_or_empty(self):
        """Tracks with 2 or fewer points are returned untouched."""
        self.assertEqual(simplify_track([]), [])
        self.assertEqual(simplify_track([[50.0, 14.0]]), [[50.0, 14.0]])
        self.assertEqual(
            simplify_track([[50.0, 14.0], [50.0001, 14.0001]]),
            [[50.0, 14.0], [50.0001, 14.0001]]
        )

    def test_simplify_track_decimates_dense_points(self):
        """Sub-15m intermediate points are dropped; terminus points are retained."""
        # Generate 100 points, each separated by ~1 metre (~0.000009 degrees latitude)
        dense_coords = [[50.0 + (i * 0.000009), 14.0] for i in range(100)]
        simplified = simplify_track(dense_coords, threshold_meters=15.0)

        # Original list has 100 points
        self.assertEqual(len(dense_coords), 100)

        # Simplified list must preserve start and end
        self.assertEqual(simplified[0], dense_coords[0])
        self.assertEqual(simplified[-1], dense_coords[-1])

        # Decimated count should be drastically reduced (~6 to 10 points)
        self.assertLess(len(simplified), 15)

    def test_simplify_track_retains_widely_spaced_points(self):
        """Points spaced far beyond threshold_meters are all retained."""
        # Generate 5 points spaced by ~11 km (~0.1 degrees latitude)
        sparse_coords = [[50.0 + (i * 0.1), 14.0] for i in range(5)]
        simplified = simplify_track(sparse_coords, threshold_meters=15.0)

        self.assertEqual(simplified, sparse_coords)


class TestMapDataEndpointSimplification(unittest.TestCase):
    """Test /api/map/data endpoint track simplification behavior."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        self._csrf_enabled = app.config.get('WTF_CSRF_ENABLED', True)
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def tearDown(self):
        app.config['WTF_CSRF_ENABLED'] = self._csrf_enabled

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.create_repository')
    def test_map_data_simplifies_response(self, mock_create_repo, mock_get_user):
        """Dense GPS tracks (>200 pts) are decimated when simplification level is enabled."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activities_by_ids.return_value = [{'id': 101, 'name': 'Long Ride'}]

        dense_coords = [[50.0 + (i * 0.000009), 14.0] for i in range(300)]
        mock_repo.get_streams_coords_for_activities.return_value = {'101': dense_coords}
        mock_repo.get_streams_bounds_for_activities.return_value = (50.0, 14.0, 50.0027, 14.0)

        mock_create_repo.return_value = mock_repo

        from kinetiqo.web.app import config
        original_level = config.gps_simplification
        try:
            config.gps_simplification = 4

            resp = self.client.post('/api/map/data', json={'activity_ids': ['101']})
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()

            self.assertIn('activities', data)
            self.assertIn('101', data['activities'])

            point_count = data['point_count']
            self.assertLess(point_count, 30)
            self.assertEqual(len(data['activities']['101']['coords']), point_count)
            self.assertIn('X-Uncompressed-Length', resp.headers)
        finally:
            config.gps_simplification = original_level

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.create_repository')
    def test_map_data_level_0_returns_unsimplified_data(self, mock_create_repo, mock_get_user):
        """GPS_SIMPLIFICATION=0 returns raw track data (300 points) untouched."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activities_by_ids.return_value = [{'id': 101, 'name': 'Long Ride'}]

        dense_coords = [[50.0 + (i * 0.000009), 14.0] for i in range(300)]
        mock_repo.get_streams_coords_for_activities.return_value = {'101': dense_coords}
        mock_repo.get_streams_bounds_for_activities.return_value = (50.0, 14.0, 50.0027, 14.0)
        mock_create_repo.return_value = mock_repo

        from kinetiqo.web.app import config
        original_level = config.gps_simplification
        try:
            config.gps_simplification = 0
            resp = self.client.post('/api/map/data', json={'activity_ids': ['101']})
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()

            self.assertEqual(data['point_count'], 300)
            self.assertEqual(len(data['activities']['101']['coords']), 300)
        finally:
            config.gps_simplification = original_level


if __name__ == '__main__':
    unittest.main()
