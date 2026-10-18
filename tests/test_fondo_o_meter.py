"""Mocked unit tests for the Fondo-o-meter feature.

Follows the canonical pattern: isolated, fast, no external calls.
"""

import io
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from kinetiqo.web.app import app
from kinetiqo.web.fondo_o_meter import (
    compute_fondo_o_meter,
    compute_fondo_circles,
    get_sport_threshold,
    SPORT_DISTANCE_THRESHOLDS,
)


def _make_activity(activity_id, name, sport, start_date, distance_km,
                   achievement_count=0, pr_count=0, koms_count=None):
    """Helper to create mock activity dict matching get_activities_web shape."""
    act = {
        'id': activity_id,
        'activity_id': activity_id,
        'name': name,
        'type': sport,
        'sport': sport,
        'start_date': start_date,
        'distance': distance_km * 1000.0,
        'achievement_count': achievement_count,
        'pr_count': pr_count,
    }
    if koms_count is not None:
        act['koms_count'] = koms_count
    return act


class TestFondoOMeterComputation(unittest.TestCase):
    """Test suite for Fondo-o-meter backend computation."""

    def test_empty_activities(self):
        result = compute_fondo_o_meter([], 2026, 'cycling')
        self.assertEqual(result['year'], 2026)
        self.assertEqual(result['total_activities'], 0)
        self.assertEqual(result['koms_count'], 0)
        self.assertEqual(result['prs_count'], 0)
        self.assertIsNone(result['longest_ride'])
        self.assertEqual(result['fondo']['total_qualifying'], 0)
        self.assertEqual(len(result['fondo']['circles']), 0)
        self.assertEqual(result['trophies_count'], 0)
        self.assertEqual(result['trophies']['total'], 0)

    def test_year_and_group_filtering(self):
        activities = [
            _make_activity(1, '2025 Ride', 'Ride', '2025-06-01T10:00:00Z', 120.0, 5, 2, koms_count=2),
            _make_activity(2, '2026 Ride', 'Ride', '2026-06-01T10:00:00Z', 150.0, 8, 3, koms_count=1),
            _make_activity(3, '2026 Run',  'Run',  '2026-06-02T10:00:00Z', 45.0,  4, 4),
        ]
        res_cycling_2026 = compute_fondo_o_meter(activities, 2026, 'cycling')
        self.assertEqual(res_cycling_2026['total_activities'], 1)
        self.assertEqual(res_cycling_2026['longest_ride']['name'], '2026 Ride')
        self.assertEqual(res_cycling_2026['koms_count'], 1)
        self.assertEqual(res_cycling_2026['prs_count'], 3)

        res_running_2026 = compute_fondo_o_meter(activities, 2026, 'running')
        self.assertEqual(res_running_2026['total_activities'], 1)
        self.assertEqual(res_running_2026['longest_ride']['name'], '2026 Run')
        self.assertEqual(res_running_2026['koms_count'], 0)
        self.assertEqual(res_running_2026['prs_count'], 4)

    def test_koms_and_prs_aggregation_with_verified_cache(self):
        """Verified KOMs cache correctly attributes KOMs; rides without verified KOMs contribute 0."""
        activities = [
            _make_activity(1, 'Ride 1', 'Ride', '2026-04-10T08:00:00Z', 50.0, achievement_count=10, pr_count=3),
            _make_activity(2, 'Ride 2', 'Ride', '2026-05-15T08:00:00Z', 80.0, achievement_count=2,  pr_count=2),
            _make_activity(3, 'Ride 3', 'Ride', '2026-07-20T08:00:00Z', 60.0, achievement_count=0,  pr_count=0),
        ]
        # Activity 1 has 1 true verified KOM in cache; Activity 2 & 3 have 0
        res = compute_fondo_o_meter(activities, 2026, 'cycling', verified_koms={'1': 1, '2': 0, '3': 0})
        self.assertEqual(res['koms_count'], 1)
        self.assertEqual(res['prs_count'], 5)  # 3 + 2 + 0

    def test_unverified_candidate_rides_do_not_inflate_koms(self):
        """Unverified rides (ach > pr) must NOT inflate KOM count by guessing ach - pr."""
        activities = [
            _make_activity(100, 'Ride without KOM', 'Ride', '2026-05-01T08:00:00Z', 50.0, achievement_count=15, pr_count=2),
        ]
        res = compute_fondo_o_meter(activities, 2026, 'cycling', verified_koms={})
        self.assertEqual(res['koms_count'], 0)  # Must be 0, not 13!

    def test_koms_excludes_course_records_on_non_cycling(self):
        """Only cycling activities should contribute to KOMs; non-cycling CRs are excluded."""
        activities = [
            _make_activity(1, 'Epic Ride', 'Ride', '2026-06-01T08:00:00Z', 100.0, achievement_count=8, pr_count=3, koms_count=2),
            _make_activity(2, 'Marathon',  'Run',  '2026-06-02T08:00:00Z', 42.2,  achievement_count=10, pr_count=2),
        ]
        # In cycling group: only the Ride is included -> 2 KOMs, 3 PRs
        res_cycling = compute_fondo_o_meter(activities, 2026, 'cycling')
        self.assertEqual(res_cycling['koms_count'], 2)
        self.assertEqual(res_cycling['prs_count'], 3)

        # In running group: only the Run is included -> 0 KOMs, 2 PRs
        res_running = compute_fondo_o_meter(activities, 2026, 'running')
        self.assertEqual(res_running['koms_count'], 0)
        self.assertEqual(res_running['prs_count'], 2)

    def test_koms_module_helpers(self):
        """Test kinetiqo.koms helper functions for extracting KOMs and detecting candidates."""
        from kinetiqo.koms import (
            extract_koms_from_activity_detail,
            count_koms_in_activity_detail,
            is_kom_candidate_activity,
        )

        mock_detail = {
            'segment_efforts': [
                {'name': 'Segment 1 (PR only)', 'pr_rank': 1, 'kom_rank': None, 'achievements': [{'type': 'pr', 'rank': 1}]},
                {'name': 'Segment 2 (2nd PR)', 'pr_rank': 2, 'kom_rank': None, 'achievements': [{'type': 'pr', 'rank': 2}]},
                {'name': 'Segment 3 (Top 10)', 'pr_rank': None, 'kom_rank': 5, 'achievements': [{'type': 'overall', 'rank': 5}]},
                {'name': 'Segment 4 (True KOM)', 'pr_rank': 1, 'kom_rank': 1, 'achievements': [{'type': 'overall', 'rank': 1}, {'type': 'kom', 'rank': 1}]},
                {'name': 'Segment 5 (Another KOM)', 'pr_rank': None, 'kom_rank': None, 'achievements': [{'type': 'cr', 'rank': 1}]},
            ]
        }
        koms = extract_koms_from_activity_detail(mock_detail)
        self.assertEqual(len(koms), 2)
        self.assertEqual(count_koms_in_activity_detail(mock_detail), 2)
        self.assertEqual(koms[0]['name'], 'Segment 4 (True KOM)')
        self.assertEqual(koms[1]['name'], 'Segment 5 (Another KOM)')

        # Candidate detection
        self.assertTrue(is_kom_candidate_activity({'sport': 'Ride', 'achievement_count': 5, 'pr_count': 2}))
        self.assertFalse(is_kom_candidate_activity({'sport': 'Ride', 'achievement_count': 2, 'pr_count': 2}))
        self.assertFalse(is_kom_candidate_activity({'sport': 'Run', 'achievement_count': 5, 'pr_count': 2}))

    def test_trophies_computation_ranks_1_to_10(self):
        """Test trophies computation with ranks 1 to 10 from segment efforts and verified caches."""
        from kinetiqo.koms import extract_trophies_from_segment_efforts

        efforts_sample = [
            {'name': 'Effort 1 (Gold)', 'kom_rank': 1},
            {'name': 'Effort 2 (Silver)', 'pr_rank': None, 'achievements': [{'type': 'overall', 'rank': 2}]},
            {'name': 'Effort 3 (Bronze)', 'achievements': [{'type': 'overall', 'rank': 3}]},
            {'name': 'Effort 4 (Gray 4th)', 'achievements': [{'type': 'overall', 'rank': 4}]},
            {'name': 'Effort 5 (Gray 10th)', 'achievements': [{'type': 'overall', 'rank': 10}]},
            {'name': 'Effort 6 (11th place - ignored)', 'achievements': [{'type': 'overall', 'rank': 11}]},
        ]
        extracted = extract_trophies_from_segment_efforts(efforts_sample)
        self.assertEqual(extracted[1], 1)
        self.assertEqual(extracted[2], 1)
        self.assertEqual(extracted[3], 1)
        self.assertEqual(extracted[4], 1)
        self.assertEqual(extracted[10], 1)
        self.assertEqual(extracted[5], 0)
        self.assertEqual(sum(extracted.values()), 5)

        act1 = _make_activity(1, 'Ride with segment efforts', 'Ride', '2026-05-01T08:00:00Z', 50.0)
        act1['segment_efforts'] = efforts_sample

        act2 = _make_activity(2, 'Ride with explicit ranks', 'Ride', '2026-06-01T08:00:00Z', 60.0)
        act2['trophies_ranks'] = {1: 2, 5: 3}

        act3 = _make_activity(3, 'Ride with cache', 'Ride', '2026-07-01T08:00:00Z', 70.0)
        verified_trophies = {'3': {1: 1, 2: 2, 7: 1}}

        res = compute_fondo_o_meter([act1, act2, act3], 2026, 'cycling', verified_trophies=verified_trophies)
        tr = res['trophies']
        self.assertEqual(tr['ranks']['1'], 4)
        self.assertEqual(tr['ranks']['2'], 3)
        self.assertEqual(tr['ranks']['3'], 1)
        self.assertEqual(tr['ranks']['4'], 1)
        self.assertEqual(tr['ranks']['5'], 3)
        self.assertEqual(tr['ranks']['7'], 1)
        self.assertEqual(tr['ranks']['10'], 1)
        self.assertEqual(tr['total'], 14)
        self.assertEqual(res['trophies_count'], 14)

    def test_trophies_computation_from_database_column(self):
        """Test reading trophies stored as JSON strings and dicts from database rows."""
        import json
        act1 = _make_activity(101, 'Ride with DB JSON string', 'Ride', '2026-05-10T08:00:00Z', 55.0)
        act1['trophies'] = json.dumps({'1': 1, '2': 3, '3': 2, '4': 1})

        act2 = _make_activity(102, 'Ride with DB dict', 'Ride', '2026-06-12T08:00:00Z', 65.0)
        act2['trophies'] = {'2': 1, '3': 4, '8': 2}

        res = compute_fondo_o_meter([act1, act2], 2026, 'cycling')
        tr = res['trophies']
        self.assertEqual(tr['ranks']['1'], 1)  # 1 from act1
        self.assertEqual(tr['ranks']['2'], 4)  # 3 from act1 + 1 from act2
        self.assertEqual(tr['ranks']['3'], 6)  # 2 from act1 + 4 from act2
        self.assertEqual(tr['ranks']['4'], 1)  # 1 from act1
        self.assertEqual(tr['ranks']['8'], 2)  # 2 from act2
        self.assertEqual(tr['total'], 14)
        self.assertEqual(res['trophies_count'], 14)

    def test_all_time_computation(self):
        """Passing year='all' aggregates activities across multiple years."""
        activities = [
            _make_activity(1, '2024 Ride', 'Ride', '2024-05-10T10:00:00Z', 120.0, achievement_count=5, pr_count=2, koms_count=2),
            _make_activity(2, '2025 Ride', 'Ride', '2025-06-15T10:00:00Z', 140.0, achievement_count=8, pr_count=3, koms_count=1),
            _make_activity(3, '2026 Ride', 'Ride', '2026-07-20T10:00:00Z', 180.0, achievement_count=10, pr_count=4, koms_count=1),
        ]
        res = compute_fondo_o_meter(activities, 'all', 'cycling')
        self.assertEqual(res['year'], 'all')
        self.assertEqual(res['total_activities'], 3)
        self.assertEqual(res['koms_count'], 4)  # 2 + 1 + 1
        self.assertEqual(res['prs_count'], 9)   # 2 + 3 + 4
        self.assertEqual(res['fondos_count'], 3)
        self.assertEqual(res['longest_ride']['name'], '2026 Ride')
        self.assertEqual(res['longest_ride']['distance_km'], 180.0)

    def test_trophies_unverified_achievements_do_not_inflate_podium(self):
        """Activities with non-PR achievements (ach > pr) do not inflate 2nd place without verified efforts."""
        # Activity 1: 1 verified KOM (rank 1), achievement_count=5, pr_count=2
        act1 = _make_activity(1, 'Ride A', 'Ride', '2026-05-01T08:00:00Z', 50.0, achievement_count=5, pr_count=2, koms_count=1)
        # Activity 2: 0 KOMs, achievement_count=4, pr_count=2 (candidate with 2nd PRs)
        act2 = _make_activity(2, 'Ride B', 'Ride', '2026-05-02T08:00:00Z', 60.0, achievement_count=4, pr_count=2, koms_count=0)
        res = compute_fondo_o_meter([act1, act2], 2026, 'cycling')
        tr = res['trophies']
        # Rank 1 gets the 1 verified KOM; ranks 2..10 are not falsely inflated
        self.assertEqual(tr['ranks']['1'], 1)  # 1st place gold / KOM
        self.assertEqual(tr['ranks']['2'], 0)  # No false 2nd place inflation!
        self.assertEqual(tr['ranks']['3'], 0)
        self.assertEqual(tr['total'], 1)
        self.assertEqual(res['trophies_count'], 1)

    def test_fondo_no_qualifying_rides(self):
        activities = [
            _make_activity(1, 'Short Ride 1', 'Ride', '2026-04-10T08:00:00Z', 45.0),
            _make_activity(2, 'Short Ride 2', 'Ride', '2026-05-15T08:00:00Z', 95.0),
        ]
        res = compute_fondo_o_meter(activities, 2026, 'cycling')
        self.assertEqual(res['total_activities'], 2)
        self.assertEqual(res['fondo']['total_qualifying'], 0)
        self.assertEqual(len(res['fondo']['circles']), 0)
        self.assertIsNotNone(res['longest_ride'])
        self.assertEqual(res['longest_ride']['distance_km'], 95.0)

    def test_fondo_single_qualifying_ride(self):
        activities = [
            _make_activity(1, 'Gran Fondo Epic', 'Ride', '2026-06-15T08:00:00Z', 135.5),
        ]
        res = compute_fondo_o_meter(activities, 2026, 'cycling')
        self.assertEqual(res['fondo']['total_qualifying'], 1)
        circles = res['fondo']['circles']
        self.assertEqual(len(circles), 1)
        self.assertTrue(circles[0]['is_longest'])
        self.assertEqual(circles[0]['distance_km'], 135.5)
        self.assertEqual(circles[0]['arc_pct'], 50.0)

    def test_fondo_smart_binning_user_scenario(self):
        # Scenario: Max ride 215 km, 5 rides between 150-200 km, rides 100-150 km
        activities = [
            _make_activity(1, 'Mt Ventoux 215k', 'Ride', '2026-07-01T08:00:00Z', 215.0),
            _make_activity(2, 'Long 195k', 'Ride', '2026-06-01T08:00:00Z', 195.0),
            _make_activity(3, 'Long 180k', 'Ride', '2026-06-10T08:00:00Z', 180.0),
            _make_activity(4, 'Long 175k', 'Ride', '2026-06-20T08:00:00Z', 175.0),
            _make_activity(5, 'Long 160k', 'Ride', '2026-07-10T08:00:00Z', 160.0),
            _make_activity(6, 'Long 155k', 'Ride', '2026-07-20T08:00:00Z', 155.0),
            _make_activity(7, 'Fondo 120k', 'Ride', '2026-05-01T08:00:00Z', 120.0),
            _make_activity(8, 'Fondo 110k', 'Ride', '2026-05-15T08:00:00Z', 110.0),
        ]
        res = compute_fondo_o_meter(activities, 2026, 'cycling')
        circles = res['fondo']['circles']

        # Total circles must never exceed 8
        self.assertLessEqual(len(circles), 8)
        self.assertGreaterEqual(len(circles), 2)

        # Outermost circle must be the longest ride
        outer = circles[-1]
        self.assertTrue(outer['is_longest'])
        self.assertEqual(outer['distance_km'], 215.0)
        self.assertEqual(outer['label'], '215.0 km')
        self.assertEqual(outer['name'], 'Mt Ventoux 215k')

        # Inverse color gradient: outermost ring is brightest lime (#F7FBE2), innermost is darker
        self.assertEqual(outer['color'], '#F7FBE2')
        self.assertNotEqual(circles[0]['color'], outer['color'])

        # Inner circles must have arc_pct <= 50.0 and correct label format (low–high km)
        for c in circles[:-1]:
            self.assertFalse(c['is_longest'])
            self.assertLessEqual(c['arc_pct'], 50.0)
            self.assertGreater(c['arc_pct'], 0)
            self.assertIn('km:', c['label'])
            self.assertIn('ride', c['label'])
            self.assertLessEqual(c['low_km'], c['high_km'])

    def test_sport_threshold_adaptation(self):
        self.assertEqual(get_sport_threshold('cycling'), 100.0)
        self.assertEqual(get_sport_threshold('cycling_outdoor'), 100.0)
        self.assertEqual(get_sport_threshold('running'), 42.195)
        self.assertEqual(get_sport_threshold('swimming'), 10.0)
        self.assertEqual(get_sport_threshold('walking'), 42.195)
        self.assertEqual(get_sport_threshold('unknown_sport'), 100.0)


class TestFondoOMeterWebRoutes(unittest.TestCase):
    """Test suite for Fondo-o-meter web routes and API endpoints."""

    def setUp(self):
        self._orig_testing = app.config.get('TESTING')
        self._orig_login_disabled = app.config.get('LOGIN_DISABLED')
        self._orig_csrf = app.config.get('WTF_CSRF_ENABLED')
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = app.test_client()

    def tearDown(self):
        app.config['TESTING'] = self._orig_testing
        app.config['LOGIN_DISABLED'] = self._orig_login_disabled
        app.config['WTF_CSRF_ENABLED'] = self._orig_csrf

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_fondo_o_meter_page_renders_with_controls(self, mock_get_db, mock_get_user):
        """Page should render with 200 OK and include all requested control labels and options."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activities_web.return_value = [
            {'id': 1, 'start_date': '2024-05-01T08:00:00Z', 'distance': 50000}
        ]
        mock_repo.get_profile.return_value = {
            'first_name': 'Test',
            'last_name': 'Cyclist',
        }
        mock_get_db.return_value = mock_repo

        response = self.client.get('/fondo-o-meter')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn('Fondo-o-meter', html)
        self.assertIn('Fondo-o-meter Size', html)
        self.assertIn('Fondo Analysis', html)
        self.assertIn('Number of KOMs', html)
        self.assertIn('Number of PRs', html)
        self.assertIn('fondo-year', html)
        self.assertIn('col-fondo', html)
        self.assertIn('col-koms', html)
        self.assertIn('col-prs', html)
        self.assertIn('col-thropies', html)
        self.assertIn('toggle-thropies', html)
        self.assertIn('Thropies', html)
        self.assertIn('id="fondos-count"', html)
        self.assertIn('id="fondo-hero-logo"', html)
        self.assertIn('fondo-o-meter-gf.png', html)
        self.assertIn('fondo-o-meter-kom.png', html)
        self.assertIn('fondo-o-meter-pr.png', html)
        self.assertIn('fondo-o-meter-thropies.png', html)
        self.assertIn('id="thropies-total-count"', html)
        self.assertIn('id="trophy-count-1"', html)
        self.assertIn('id="trophy-count-10"', html)
        self.assertIn('id="fondo-crown-type"', html)
        self.assertIn('id="fondos-label"', html)
        self.assertIn('id="koms-header-title">KOMs</span>', html)
        self.assertIn('King of the Mountains verified across cycling activities', html)
        self.assertNotIn('koms-header-icon', html)
        self.assertNotIn('fondo-col-header-img', html)

        # Verify action buttons from _infographic_action_buttons.html
        self.assertIn('id="btn-download-png"', html)
        self.assertIn('id="btn-download-pdf"', html)

        # Verify size box from _infographic_size_box.html
        self.assertIn('data-box-id="fondoOMeterSize"', html)
        self.assertIn('id="fondo-size"', html)
        self.assertIn('id="fondo-dimensions"', html)
        self.assertIn('1280', html)
        self.assertIn('2048', html)

        # Verify period box from _control_year_select.html & _control_box_header.html
        self.assertIn('data-box-id="fondoOMeterPeriod"', html)
        self.assertIn('id="fondo-year"', html)

        # Verify appearance box from _infographic_appearance_box.html
        self.assertIn('data-box-id="fondoOMeterAppearance"', html)
        self.assertIn('id="fondo-bg"', html)
        self.assertIn('id="fondo-group"', html)
        self.assertIn('id="fondo-tint"', html)
        self.assertIn('id="fondo-tint-clear-btn"', html)
        self.assertIn('id="fondo-opacity"', html)
        self.assertIn('id="fondo-font"', html)
        self.assertIn('id="fondo-upload-input"', html)
        self.assertIn('id="fondo-clear-image-btn"', html)

        # Verify options box from _control_box_header.html & _control_range.html
        self.assertIn('data-box-id="fondoOMeterOptions"', html)
        self.assertIn('id="fondo-title-font-size"', html)
        self.assertIn('id="fondo-title-font-size-val"', html)
        self.assertIn('id="fondo-font-size"', html)
        self.assertIn('id="fondo-font-size-val"', html)
        self.assertIn('id="fondo-arc-color"', html)
        self.assertIn('id="fondo-arc-color-reset"', html)
        self.assertIn('id="fondo-arc-width"', html)
        self.assertIn('id="fondo-arc-width-val"', html)
        self.assertIn('max="160"', html)
        self.assertIn('id="fondo-arc-size"', html)
        self.assertIn('id="fondo-arc-size-val"', html)
        self.assertNotIn('id="fondo-arch-size"', html)
        self.assertIn('id="fondo-vignette"', html)
        self.assertIn('id="fondo-vignette-val"', html)
        self.assertIn('id="ig-bg-vignette"', html)
        self.assertIn('id="fondo-logo-color"', html)
        self.assertIn('id="fondo-logo-color-reset"', html)
        self.assertIn('id="fondo-logo-size"', html)
        self.assertIn('id="fondo-logo-size-val"', html)
        self.assertIn('id="fondo-logo-opacity"', html)
        self.assertIn('id="fondo-logo-opacity-val"', html)
        self.assertIn('id="fondo-section-blur"', html)
        self.assertIn('id="fondo-section-blur-val"', html)
        self.assertIn('id="logo-colorize"', html)
        self.assertIn('id="logo-flood"', html)
        self.assertTrue('google_fonts_poster_local.css' in html or 'fonts.googleapis.com' in html)

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_legacy_achievements_route_redirects_or_renders(self, mock_get_db, mock_get_user):
        """Legacy /achievements URL should also render the page cleanly."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activities_web.return_value = []
        mock_repo.get_profile.return_value = None
        mock_get_db.return_value = mock_repo

        response = self.client.get('/achievements')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn('Fondo-o-meter', html)

    @patch('kinetiqo.web.fondo_o_meter.load_verified_koms')
    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_fondo_o_meter_api_returns_data(self, mock_get_db, mock_get_user, mock_load_koms):
        """API should return computed fondo-o-meter data with verified KOMs matching selected year and group."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_load_koms.return_value = {'1': 1, '2': 0}

        mock_repo = MagicMock()
        mock_repo.get_activities_web.return_value = [
            _make_activity(1, 'Long Epic', 'Ride', '2026-06-01T08:00:00Z', 160.0, achievement_count=5, pr_count=2),
            _make_activity(2, 'Short Blast', 'Ride', '2026-06-02T08:00:00Z', 40.0, achievement_count=2, pr_count=1),
        ]
        mock_repo.get_profile.return_value = {
            'first_name': 'Jarda',
            'last_name': 'Rider',
        }
        mock_get_db.return_value = mock_repo

        response = self.client.get('/api/fondo_o_meter_data?year=2026&group=cycling')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['year'], 2026)
        self.assertEqual(data['group'], 'cycling')
        self.assertEqual(data['athlete_name'], 'Jarda Rider')
        self.assertEqual(data['koms_count'], 1)  # Verified 1 KOM from cache
        self.assertEqual(data['prs_count'], 3)   # 2 + 1 = 3
        self.assertEqual(data['total_activities'], 2)
        self.assertEqual(data['fondos_count'], 1)
        self.assertEqual(data['fondo']['total_qualifying'], 1)
        self.assertEqual(len(data['fondo']['circles']), 1)
        self.assertEqual(data['fondo']['circles'][0]['distance_km'], 160.0)
        self.assertEqual(data['fondo']['circles'][0]['label'], '160.0 km')
        self.assertIn('trophies_count', data)
        self.assertIn('trophies', data)
        self.assertIn('ranks', data['trophies'])
        self.assertEqual(len(data['trophies']['ranks']), 10)

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_fondo_o_meter_api_all_time(self, mock_get_user, mock_get_db):
        """API with year=all queries without date boundaries and aggregates all time data."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activities_web.return_value = [
            _make_activity(1, '2024 Ride', 'Ride', '2024-05-10T10:00:00Z', 120.0, achievement_count=5, pr_count=2, koms_count=2),
            _make_activity(2, '2026 Ride', 'Ride', '2026-06-15T10:00:00Z', 150.0, achievement_count=8, pr_count=3, koms_count=1),
        ]
        mock_repo.get_profile.return_value = {'first_name': 'Athlete', 'last_name': 'Champ'}
        mock_get_db.return_value = mock_repo

        response = self.client.get('/api/fondo_o_meter_data?year=all&group=cycling')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['year'], 'all')
        self.assertEqual(data['koms_count'], 3)
        self.assertEqual(data['prs_count'], 5)
        self.assertEqual(data['total_activities'], 2)
        # Verify get_activities_web was called with start_date=None, end_date=None
        mock_repo.get_activities_web.assert_called_once()
        _, kwargs = mock_repo.get_activities_web.call_args
        self.assertIsNone(kwargs['start_date'])
        self.assertIsNone(kwargs['end_date'])

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_fondo_o_meter_api_rejects_unknown_group(self, mock_get_user, mock_get_db):
        """Unknown activity group should return HTTP 400."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        response = self.client.get('/api/fondo_o_meter_data?group=non_existent_group')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unknown activity group', response.get_json()['error'])

    @patch('kinetiqo.web.app.get_db')
    @patch('flask_login.utils._get_user')
    def test_fondo_o_meter_photo_reset(self, mock_get_user, mock_get_db):
        """Reset endpoint should return cleared status."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        response = self.client.post('/api/fondo_o_meter/image/reset')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'status': 'cleared'})


if __name__ == '__main__':
    unittest.main()
