"""Mocked unit tests for VO2max estimation logic and web endpoints."""

import unittest
from unittest.mock import patch, MagicMock

from kinetiqo.web.vo2max import (
    estimate_vo2max,
    classify_vo2max,
    smooth_vo2max_history,
    filter_qualifying_rides,
)
from kinetiqo.db.repository import compute_best_power_per_activity


class TestEstimateVo2max(unittest.TestCase):
    """Unit tests for the Storer-Davis VO2max formula."""

    def test_known_values(self):
        """VO2max for 350 W MAP at 70 kg → (10.8 × 350 / 70) + 7 = 61.0."""
        result = estimate_vo2max(350.0, 70.0)
        self.assertAlmostEqual(result, 61.0, places=1)

    def test_zero_weight_returns_zero(self):
        self.assertEqual(estimate_vo2max(300.0, 0.0), 0.0)

    def test_negative_weight_returns_zero(self):
        self.assertEqual(estimate_vo2max(300.0, -5.0), 0.0)

    def test_zero_power_returns_zero(self):
        self.assertEqual(estimate_vo2max(0.0, 70.0), 0.0)

    def test_lightweight_rider(self):
        """VO2max for 300 W MAP at 55 kg → (10.8 × 300 / 55) + 7 ≈ 65.9."""
        result = estimate_vo2max(300.0, 55.0)
        self.assertAlmostEqual(result, 65.9, places=1)

    def test_heavy_rider(self):
        """VO2max for 300 W MAP at 90 kg → (10.8 × 300 / 90) + 7 = 43.0."""
        result = estimate_vo2max(300.0, 90.0)
        self.assertAlmostEqual(result, 43.0, places=1)


class TestClassifyVo2max(unittest.TestCase):
    """Unit tests for the ACSM-based VO2max classification."""

    def test_classifications(self):
        cases = [
            (0, "N/A"),
            (25, "Very Poor"),
            (30, "Poor"),
            (37, "Fair"),
            (43, "Good"),
            (49, "Excellent"),
            (55, "Superior"),
            (70, "Superior"),
        ]
        for vo2, expected in cases:
            with self.subTest(vo2max=vo2):
                self.assertEqual(classify_vo2max(vo2), expected)


class TestSmoothVo2maxHistory(unittest.TestCase):
    """Unit tests for the Firstbeat-style asymmetric EWMA smoothing."""

    def test_empty_input(self):
        self.assertEqual(smooth_vo2max_history([]), [])

    def test_single_entry(self):
        entries = [{'date': '2025-01-01', 'vo2max': 50.0}]
        result = smooth_vo2max_history(entries)
        self.assertEqual(result, [50.0])

    def test_rise_is_faster_than_fall(self):
        """A large improvement should be absorbed more quickly than a decline."""
        entries = [
            {'date': '2025-01-01', 'vo2max': 40.0},
            {'date': '2025-01-02', 'vo2max': 60.0},  # big jump up
        ]
        result = smooth_vo2max_history(entries)
        rise_delta = result[1] - result[0]  # how much the smoothed value rose

        entries_down = [
            {'date': '2025-01-01', 'vo2max': 60.0},
            {'date': '2025-01-02', 'vo2max': 40.0},  # big drop down
        ]
        result_down = smooth_vo2max_history(entries_down)
        fall_delta = result_down[0] - result_down[1]  # how much the smoothed value fell

        self.assertGreater(rise_delta, fall_delta,
                           "Rise should be absorbed faster than an equivalent fall")

    def test_smoothed_values_are_stable(self):
        """Repeated identical readings should converge toward the raw value."""
        entries = [{'date': f'2025-01-{d:02d}', 'vo2max': 50.0} for d in range(1, 11)]
        result = smooth_vo2max_history(entries)
        # After 10 identical readings the smoothed value should be very close
        self.assertAlmostEqual(result[-1], 50.0, delta=0.5)

    def test_inactivity_decay(self):
        """A large gap between rides should cause the smoothed value to decay."""
        entries = [
            {'date': '2025-01-01', 'vo2max': 55.0},
            {'date': '2025-04-01', 'vo2max': 55.0},  # 90-day gap
        ]
        result = smooth_vo2max_history(entries)
        # The second smoothed value should be lower than 55 because of the gap
        # decay, even though the raw value is the same.
        self.assertLess(result[1], 55.0)

    def test_output_length_matches_input(self):
        entries = [
            {'date': '2025-01-01', 'vo2max': 40.0},
            {'date': '2025-01-03', 'vo2max': 42.0},
            {'date': '2025-01-05', 'vo2max': 41.0},
        ]
        result = smooth_vo2max_history(entries)
        self.assertEqual(len(result), len(entries))


class TestFilterQualifyingRides(unittest.TestCase):
    """Unit tests for the Garmin-style qualifying-ride filter."""

    def test_empty_input(self):
        self.assertEqual(filter_qualifying_rides([]), [])

    def test_best_per_day(self):
        """When two rides fall on the same date, only the best is kept."""
        entries = [
            {'date': '2025-01-01', 'vo2max': 40.0, 'name': 'Easy'},
            {'date': '2025-01-01', 'vo2max': 50.0, 'name': 'Hard'},
            {'date': '2025-01-02', 'vo2max': 48.0, 'name': 'Solo'},
        ]
        result = filter_qualifying_rides(entries)
        dates = [r['date'] for r in result]
        self.assertEqual(dates.count('2025-01-01'), 1)
        day1 = [r for r in result if r['date'] == '2025-01-01'][0]
        self.assertEqual(day1['vo2max'], 50.0)

    def test_outlier_removal(self):
        """Rides far below the median are rejected."""
        entries = [
            {'date': f'2025-01-{d:02d}', 'vo2max': 50.0} for d in range(1, 11)
        ]
        # Add an outlier ride way below the median
        entries.append({'date': '2025-01-11', 'vo2max': 20.0})
        result = filter_qualifying_rides(entries)
        vo2_values = [r['vo2max'] for r in result]
        self.assertNotIn(20.0, vo2_values)

    def test_clean_data_passes_through(self):
        """Entries that are all within range are kept."""
        entries = [
            {'date': '2025-01-01', 'vo2max': 48.0},
            {'date': '2025-01-02', 'vo2max': 50.0},
            {'date': '2025-01-03', 'vo2max': 49.0},
        ]
        result = filter_qualifying_rides(entries)
        self.assertEqual(len(result), 3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_app(cfg):
    """Import the Flask app, apply *cfg*, and return a logged-in test client."""
    from kinetiqo.web.app import app, set_config, _power_cache
    set_config(cfg)
    app.config['TESTING'] = True
    # Clear the power cache so results from a previous test don't leak.
    _power_cache.invalidate()
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    return client


def _make_config(**overrides):
    """Create a minimal Config with optional overrides."""
    from kinetiqo.config import Config
    cfg = Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


MOCK_PROFILE = {
    'athlete_id': 123,
    'first_name': 'Test',
    'last_name': 'User',
    'weight': 70.0,
}


def _mock_repo_with_rides(profile=None):
    """Return a mock repository with one cycling ride and an optional profile."""
    watts_map = {
        '1001': [250.0] * 600,
    }

    def _power_side_effect(activity_ids, duration_seconds, min_total_samples=0):
        subset = {aid: watts_map[aid] for aid in activity_ids if aid in watts_map}
        return compute_best_power_per_activity(subset, duration_seconds, min_total_samples)

    mock_repo = MagicMock()
    mock_repo.get_activity_ids_by_types.return_value = [
        {'id': '1001', 'name': 'Test Ride', 'start_date': '2025-06-15T10:00:00Z'},
    ]
    mock_repo.get_best_power_per_activity.side_effect = _power_side_effect
    mock_repo.get_profile.return_value = profile
    return mock_repo


# ---------------------------------------------------------------------------
# /vo2max page tests — weight from profile DB table
# ---------------------------------------------------------------------------

class TestVo2maxRouteWithProfileWeight(unittest.TestCase):
    """Tests when weight is read from the profile database table."""

    @patch('kinetiqo.web.app.create_repository')
    def test_vo2max_page_renders_with_profile_weight(self, mock_create_repo):
        """The page renders and shows weight from the profile table."""
        mock_create_repo.return_value = _mock_repo_with_rides(profile=MOCK_PROFILE)

        client = _setup_app(_make_config(athlete_weight=0.0))
        resp = client.get('/vo2max')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'VO', resp.data)
        self.assertIn(b'70.0 kg', resp.data)
        self.assertIn(b'profile', resp.data)

    @patch('kinetiqo.web.app.create_repository')
    def test_profile_weight_takes_precedence_over_env(self, mock_create_repo):
        """Profile weight takes precedence over ATHLETE_WEIGHT env var."""
        profile = {**MOCK_PROFILE, 'weight': 68.0}
        mock_create_repo.return_value = _mock_repo_with_rides(profile=profile)

        client = _setup_app(_make_config(athlete_weight=80.0))
        resp = client.get('/vo2max')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'68.0 kg', resp.data)
        self.assertIn(b'profile', resp.data)


class TestVo2maxRouteWithEnvWeight(unittest.TestCase):
    """Tests when weight falls back to the ATHLETE_WEIGHT env var."""

    @patch('kinetiqo.web.app.create_repository')
    def test_falls_back_to_env_when_profile_has_no_weight(self, mock_create_repo):
        """Falls back to env var when profile weight is 0."""
        profile = {**MOCK_PROFILE, 'weight': 0}
        mock_create_repo.return_value = _mock_repo_with_rides(profile=profile)

        client = _setup_app(_make_config(athlete_weight=75.0))
        resp = client.get('/vo2max')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'75.0 kg', resp.data)
        self.assertIn(b'ATHLETE_WEIGHT env var', resp.data)

    @patch('kinetiqo.web.app.create_repository')
    def test_falls_back_to_env_when_no_profile(self, mock_create_repo):
        """Falls back to env var when no profile row exists at all."""
        mock_create_repo.return_value = _mock_repo_with_rides(profile=None)

        client = _setup_app(_make_config(athlete_weight=72.0))
        resp = client.get('/vo2max')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'72.0 kg', resp.data)
        self.assertIn(b'ATHLETE_WEIGHT env var', resp.data)


class TestVo2maxRouteNoWeight(unittest.TestCase):
    """Tests when no weight source is available."""

    @patch('kinetiqo.web.app.create_repository')
    def test_error_when_no_weight_at_all(self, mock_create_repo):
        """Error page is shown when neither profile nor env var has weight."""
        mock_create_repo.return_value = _mock_repo_with_rides(profile=None)

        client = _setup_app(_make_config(athlete_weight=0.0))
        resp = client.get('/vo2max')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Settings', resp.data)
        self.assertIn(b'ATHLETE_WEIGHT', resp.data)


# ---------------------------------------------------------------------------
# /api/vo2max_history tests
# ---------------------------------------------------------------------------

class TestVo2maxHistoryAPI(unittest.TestCase):
    """Mocked tests for the /api/vo2max_history endpoint."""

    @patch('kinetiqo.web.app.create_repository')
    def test_history_returns_json(self, mock_create_repo):
        """The API returns a valid JSON time-series."""
        watts_map = {
            '2001': [280.0] * 1500,
            '2002': [320.0] * 1500,
        }

        def _power_side_effect(activity_ids, duration_seconds, min_total_samples=0):
            subset = {aid: watts_map[aid] for aid in activity_ids if aid in watts_map}
            return compute_best_power_per_activity(subset, duration_seconds, min_total_samples)

        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {**MOCK_PROFILE, 'weight': 75.0}
        mock_repo.get_activity_ids_by_types.return_value = [
            {'id': '2001', 'name': 'Ride A', 'start_date': '2025-07-01T08:00:00Z'},
            {'id': '2002', 'name': 'Ride B', 'start_date': '2025-07-10T09:00:00Z'},
        ]
        mock_repo.get_best_power_per_activity.side_effect = _power_side_effect
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config(athlete_weight=0.0))
        resp = client.get('/api/vo2max_history?period=all')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('dates', data)
        self.assertIn('vo2max_values', data)
        self.assertIn('vo2max_raw', data)
        self.assertEqual(len(data['dates']), 2)
        for v in data['vo2max_values']:
            self.assertGreater(v, 0)

    @patch('kinetiqo.web.app.create_repository')
    def test_history_error_without_weight(self, mock_create_repo):
        """The API returns 400 when no weight is configured anywhere."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = None
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config(athlete_weight=0.0))
        resp = client.get('/api/vo2max_history')

        self.assertEqual(resp.status_code, 400)

    @patch('kinetiqo.web.app.create_repository')
    def test_history_uses_profile_weight(self, mock_create_repo):
        """The API uses profile weight for VO2max computation."""
        watts_map = {
            '3001': [300.0] * 1500,
        }

        def _power_side_effect(activity_ids, duration_seconds, min_total_samples=0):
            subset = {aid: watts_map[aid] for aid in activity_ids if aid in watts_map}
            return compute_best_power_per_activity(subset, duration_seconds, min_total_samples)

        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {**MOCK_PROFILE, 'weight': 80.0}
        mock_repo.get_activity_ids_by_types.return_value = [
            {'id': '3001', 'name': 'Ride C', 'start_date': '2025-08-01T07:00:00Z'},
        ]
        mock_repo.get_best_power_per_activity.side_effect = _power_side_effect
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config(athlete_weight=0.0))
        resp = client.get('/api/vo2max_history?period=all')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data['dates']), 1)
        # VO2max = (10.8 × 300 / 80) + 7 = 47.5
        self.assertAlmostEqual(data['vo2max_values'][0], 47.5, places=1)


# ---------------------------------------------------------------------------
# /api/profile tests
# ---------------------------------------------------------------------------

class TestProfileAPI(unittest.TestCase):
    """Mocked tests for the profile API endpoints."""

    @patch('kinetiqo.web.app.create_repository')
    def test_get_profile(self, mock_create_repo):
        """GET /api/profile returns the stored profile."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = MOCK_PROFILE
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config())
        resp = client.get('/api/profile')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['first_name'], 'Test')
        self.assertEqual(data['weight'], 70.0)

    @patch('kinetiqo.web.app.create_repository')
    def test_get_profile_empty(self, mock_create_repo):
        """GET /api/profile returns zeroed data when no profile exists."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = None
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config())
        resp = client.get('/api/profile')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['athlete_id'], 0)
        self.assertEqual(data['weight'], 0)

    @patch('kinetiqo.web.app.create_repository')
    def test_update_profile(self, mock_create_repo):
        """PUT /api/profile updates the profile and returns updated data."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = MOCK_PROFILE
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config())
        resp = client.put('/api/profile',
                          json={'first_name': 'Jane', 'weight': 65.5},
                          content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['first_name'], 'Jane')
        self.assertEqual(data['weight'], 65.5)
        mock_repo.upsert_profile.assert_called_once_with(123, 'Jane', 'User', 65.5)

    @patch('kinetiqo.web.app.create_repository')
    def test_update_profile_invalid_weight(self, mock_create_repo):
        """PUT /api/profile rejects non-numeric weight with 422."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = MOCK_PROFILE
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config())
        resp = client.put('/api/profile',
                          json={'weight': 'abc'},
                          content_type='application/json')

        self.assertEqual(resp.status_code, 422)
        mock_repo.upsert_profile.assert_not_called()

    @patch('kinetiqo.web.app.create_repository')
    def test_update_profile_negative_weight(self, mock_create_repo):
        """PUT /api/profile rejects negative weight with 422."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = MOCK_PROFILE
        mock_create_repo.return_value = mock_repo

        client = _setup_app(_make_config())
        resp = client.put('/api/profile',
                          json={'weight': -5},
                          content_type='application/json')

        self.assertEqual(resp.status_code, 422)
        mock_repo.upsert_profile.assert_not_called()


# ---------------------------------------------------------------------------
# StravaClient.get_athlete() unit tests (independent of web layer)
# ---------------------------------------------------------------------------

class TestStravaClientGetAthlete(unittest.TestCase):
    """Mocked tests for the StravaClient.get_athlete() method."""

    @patch('kinetiqo.strava.requests.get')
    @patch('kinetiqo.strava.requests.post')
    def test_get_athlete_returns_profile(self, mock_post, mock_get):
        """get_athlete() should return the athlete profile dict with weight."""
        from kinetiqo.strava import StravaClient

        cfg = _make_config(
            strava_client_id='test_id',
            strava_client_secret='test_secret',
            strava_refresh_token='test_token',
        )

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            'access_token': 'mock_access_token',
            'refresh_token': 'test_token',
        }
        mock_post.return_value = mock_token_resp

        mock_athlete_resp = MagicMock()
        mock_athlete_resp.json.return_value = {
            'id': 12345,
            'firstname': 'John',
            'lastname': 'Doe',
            'weight': 72.5,
        }
        mock_athlete_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_athlete_resp

        client = StravaClient(cfg)
        athlete = client.get_athlete()

        self.assertEqual(athlete['weight'], 72.5)
        self.assertEqual(athlete['firstname'], 'John')
        mock_get.assert_called_once()

    @patch('kinetiqo.strava.requests.get')
    @patch('kinetiqo.strava.requests.post')
    def test_get_athlete_uses_cache(self, mock_post, mock_get):
        """get_athlete() should return cached data on the second call."""
        from kinetiqo.strava import StravaClient

        cfg = _make_config(
            strava_client_id='test_id',
            strava_client_secret='test_secret',
            strava_refresh_token='test_token',
        )

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            'access_token': 'mock_access_token',
            'refresh_token': 'test_token',
        }
        mock_post.return_value = mock_token_resp

        athlete_data = {'id': 12345, 'weight': 72.5}
        mock_athlete_resp = MagicMock()
        mock_athlete_resp.json.return_value = athlete_data
        mock_athlete_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_athlete_resp

        client = StravaClient(cfg)

        cache_store = {}
        def fake_cache_get(endpoint, params=None):
            return cache_store.get(endpoint)
        def fake_cache_set(endpoint, data, params=None):
            cache_store[endpoint] = data

        client.cache.get = fake_cache_get
        client.cache.set = fake_cache_set

        athlete1 = client.get_athlete()
        athlete2 = client.get_athlete()

        self.assertEqual(athlete1['weight'], 72.5)
        self.assertEqual(athlete2['weight'], 72.5)
        self.assertEqual(mock_get.call_count, 1)


if __name__ == '__main__':
    unittest.main()

