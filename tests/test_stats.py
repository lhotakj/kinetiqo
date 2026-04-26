"""Mocked unit tests for the Mega Stats feature.

Follows the canonical pattern from ``tests/test_sync_logic.py``:
class-level patches, subTest for matrix tests, no live database.
"""

import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from kinetiqo.web.app import app
from kinetiqo.web.stats import (
    compute_mega_stats,
    compute_max_streak,
    build_calendar,
    get_period_range,
    parse_activity_date,
    MONTH_COLORS,
    MONTH_SHORT_NAMES,
    ACTIVITY_GROUPS,
    VALID_PERIODS,
)


# ---------------------------------------------------------------------------
# Mock activity data
# ---------------------------------------------------------------------------

def _make_activity(activity_id, name, sport, start_date, distance_m=10000,
                   elevation=100, moving_time=3600, average_speed=2.78,
                   max_speed: float | None = 4.0):
    """Create a mock activity dict matching the shape of ``get_activities_web``."""
    return {
        'id': activity_id,
        'name': name,
        'type': sport,
        'start_date': start_date,
        'distance': distance_m,
        'total_elevation_gain': elevation,
        'moving_time': moving_time,
        'average_speed': average_speed,
        'max_speed': max_speed,
    }


ACTIVITIES_2025 = [
    _make_activity(1, 'Morning Walk',    'Walk', '2025-01-15T08:00:00Z', 5000,  50, 3600,  1.39, 2.0),
    _make_activity(2, 'Afternoon Hike',  'Hike', '2025-01-16T14:00:00Z', 12000, 400, 7200, 1.67, 2.5),
    _make_activity(3, 'Park Stroll',     'Walk', '2025-01-17T10:00:00Z', 3000,  10, 1800,  1.67, 2.0),
    _make_activity(4, 'Long Hike',       'Hike', '2025-03-05T09:00:00Z', 25000, 800, 14400, 1.74, 3.0),
    _make_activity(5, 'City Walk',       'Walk', '2025-06-20T18:00:00Z', 8000,  20, 4800,  1.67, 2.2),
    _make_activity(6, 'Mountain Hike',   'Hike', '2025-06-21T07:00:00Z', 15000, 1200, 10800, 1.39, 2.8),
    _make_activity(7, 'Evening Walk',    'Walk', '2025-06-22T19:00:00Z', 4000,  15, 2400,  1.67, 2.1),
]

CYCLING_ACTIVITIES = [
    _make_activity(10, 'Fast Ride',   'Ride',        '2025-04-10T07:00:00Z', 80000, 500, 10800, 7.41, 15.0),
    _make_activity(11, 'Gravel Loop', 'GravelRide',  '2025-04-12T09:00:00Z', 60000, 700, 9000,  6.67, 12.0),
]


class TestParsing(unittest.TestCase):
    """Test date parsing and period range helpers."""

    def test_parse_iso_date(self):
        d = parse_activity_date('2025-06-15T10:30:00Z')
        self.assertEqual(d, date(2025, 6, 15))

    def test_parse_plain_date(self):
        d = parse_activity_date('2025-06-15')
        self.assertEqual(d, date(2025, 6, 15))

    def test_parse_none(self):
        self.assertIsNone(parse_activity_date(None))
        self.assertIsNone(parse_activity_date(''))

    def test_parse_garbage(self):
        self.assertIsNone(parse_activity_date('not-a-date'))


class TestPeriodRange(unittest.TestCase):
    """Test ``get_period_range`` for all valid periods."""

    def test_full_year(self):
        s, e = get_period_range(2025, 'year')
        self.assertEqual(s, date(2025, 1, 1))
        self.assertEqual(e, date(2025, 12, 31))

    def test_quarters(self):
        cases = {
            'q1': (date(2025, 1, 1), date(2025, 3, 31)),
            'q2': (date(2025, 4, 1), date(2025, 6, 30)),
            'q3': (date(2025, 7, 1), date(2025, 9, 30)),
            'q4': (date(2025, 10, 1), date(2025, 12, 31)),
        }
        for period, expected in cases.items():
            with self.subTest(period=period):
                self.assertEqual(get_period_range(2025, period), expected)

    def test_halves(self):
        s, e = get_period_range(2025, 'h1')
        self.assertEqual(s, date(2025, 1, 1))
        self.assertEqual(e, date(2025, 6, 30))

        s, e = get_period_range(2025, 'h2')
        self.assertEqual(s, date(2025, 7, 1))
        self.assertEqual(e, date(2025, 12, 31))

    def test_unknown_period_defaults_to_year(self):
        s, e = get_period_range(2025, 'bogus')
        self.assertEqual(s, date(2025, 1, 1))
        self.assertEqual(e, date(2025, 12, 31))


class TestMaxStreak(unittest.TestCase):
    """Test the max-streak-of-consecutive-days computation."""

    def test_empty(self):
        self.assertEqual(compute_max_streak(set()), 0)

    def test_single_day(self):
        self.assertEqual(compute_max_streak({date(2025, 1, 1)}), 1)

    def test_consecutive_streak(self):
        dates = {date(2025, 3, 1) + timedelta(days=i) for i in range(5)}
        self.assertEqual(compute_max_streak(dates), 5)

    def test_gap_resets_streak(self):
        dates = {
            date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3),  # 3
            # gap
            date(2025, 1, 5), date(2025, 1, 6),  # 2
        }
        self.assertEqual(compute_max_streak(dates), 3)

    def test_two_equal_streaks(self):
        dates = {
            date(2025, 1, 1), date(2025, 1, 2),  # 2
            date(2025, 1, 10), date(2025, 1, 11),  # 2
        }
        self.assertEqual(compute_max_streak(dates), 2)


class TestBuildCalendar(unittest.TestCase):
    """Test the calendar heatmap builder."""

    def test_full_year_starts_on_monday(self):
        cal = build_calendar(date(2025, 1, 1), date(2025, 12, 31), {})
        # First week's first day must be a Monday
        first_day = date.fromisoformat(cal[0][0]['date'])
        self.assertEqual(first_day.weekday(), 0)  # Monday

    def test_each_week_has_7_days(self):
        cal = build_calendar(date(2025, 1, 1), date(2025, 3, 31), {})
        for week in cal:
            self.assertEqual(len(week), 7)

    def test_active_day_marked(self):
        dist = {date(2025, 2, 15): 10.5}
        cal = build_calendar(date(2025, 1, 1), date(2025, 12, 31), dist)

        found = False
        for week in cal:
            for day in week:
                if day['date'] == '2025-02-15':
                    self.assertTrue(day['has_activity'])
                    self.assertAlmostEqual(day['distance_km'], 10.5, places=1)
                    found = True
        self.assertTrue(found, 'Feb 15 not found in calendar')

    def test_out_of_range_days_have_no_activity(self):
        """Days outside the range should always show as inactive."""
        dist = {date(2024, 12, 30): 5.0}  # outside 2025 range
        cal = build_calendar(date(2025, 1, 1), date(2025, 12, 31), dist)

        for week in cal:
            for day in week:
                if day['date'] == '2024-12-30':
                    self.assertFalse(day['in_range'])
                    self.assertFalse(day['has_activity'])

    def test_quarter_calendar_shorter(self):
        cal_year = build_calendar(date(2025, 1, 1), date(2025, 12, 31), {})
        cal_q1   = build_calendar(date(2025, 1, 1), date(2025, 3, 31), {})
        self.assertGreater(len(cal_year), len(cal_q1))


class TestComputeMegaStats(unittest.TestCase):
    """Test the main ``compute_mega_stats`` computation."""

    def test_empty_activities(self):
        stats = compute_mega_stats([], 2025, 'year')
        self.assertEqual(stats['total_activities'], 0)
        self.assertEqual(stats['total_distance_km'], 0)
        self.assertEqual(stats['active_days'], 0)
        self.assertEqual(stats['max_streak'], 0)
        self.assertIsInstance(stats['calendar'], list)

    def test_basic_totals(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')

        expected_distance_km = sum(
            float(a.get('distance', 0)) for a in ACTIVITIES_2025
        ) / 1000.0
        self.assertAlmostEqual(stats['total_distance_km'], round(expected_distance_km, 1), places=1)
        self.assertEqual(stats['total_activities'], 7)
        self.assertEqual(stats['year'], 2025)
        self.assertEqual(stats['period'], 'year')
        self.assertEqual(stats['period_label'], '2025')

    def test_longest_activity(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')
        # Activity 4 "Long Hike" has 25000m = 25.0 km
        self.assertEqual(stats['longest_activity']['distance_km'], 25.0)
        self.assertEqual(stats['longest_activity']['name'], 'Long Hike')

    def test_highest_elevation_activity(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')
        # Activity 6 "Mountain Hike" has 1200m elevation
        self.assertEqual(stats['highest_elevation_activity']['elevation_m'], 1200)
        self.assertEqual(stats['highest_elevation_activity']['name'], 'Mountain Hike')

    def test_top_speed(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')
        # Highest max_speed is 3.0 m/s = 10.8 km/h
        self.assertAlmostEqual(stats['top_speed_kmh'], 10.8, places=1)

    def test_top_speed_cycling(self):
        stats = compute_mega_stats(CYCLING_ACTIVITIES, 2025, 'year')
        # Highest max_speed is 15.0 m/s = 54.0 km/h
        self.assertAlmostEqual(stats['top_speed_kmh'], 54.0, places=1)

    def test_active_days_and_streak(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')
        # Activities on: Jan 15, 16, 17 (streak 3); Mar 5; Jun 20, 21, 22 (streak 3)
        self.assertEqual(stats['active_days'], 7)
        self.assertEqual(stats['max_streak'], 3)

    def test_most_active_month(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')
        # Jan has 3 activities, Jun has 3 activities — both equal.
        # max() picks last equal element, so the result depends on dict ordering.
        # Both are valid — check that it's one of them.
        self.assertIn(stats['most_active_month']['number'], [1, 6])
        self.assertEqual(stats['most_active_month']['count'], 3)

    def test_quarter_filter(self):
        """Q1 should only include Jan and Mar activities."""
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'q1')
        self.assertEqual(stats['total_activities'], 4)  # Jan 15,16,17 + Mar 5

    def test_half_year_filter(self):
        """H2 should include only Jun activities."""
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'h2')
        self.assertEqual(stats['total_activities'], 0)
        # Wait — Jun 20-22 are in H1 (Jan-Jun), not H2.
        # H2 is Jul-Dec. So 0 activities is correct.

    def test_h1_includes_june(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'h1')
        # H1 = Jan-Jun. All 7 activities are in Jan, Mar, Jun.
        self.assertEqual(stats['total_activities'], 7)

    def test_calendar_is_generated(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')
        self.assertIsInstance(stats['calendar'], list)
        self.assertGreater(len(stats['calendar']), 50)  # ~52-53 weeks
        self.assertEqual(len(stats['calendar'][0]), 7)

    def test_month_colors_present(self):
        stats = compute_mega_stats(ACTIVITIES_2025, 2025, 'year')
        self.assertIn('month_colors', stats)
        self.assertEqual(len(stats['month_colors']), 12)

    def test_fallback_to_average_speed(self):
        """When max_speed is missing, average_speed should be used."""
        activities = [
            _make_activity(99, 'No Max Speed', 'Walk', '2025-05-01T08:00:00Z',
                           distance_m=5000, max_speed=None, average_speed=1.5),
        ]
        # Override max_speed to None
        activities[0]['max_speed'] = None
        stats = compute_mega_stats(activities, 2025, 'year')
        # Should use average_speed 1.5 m/s = 5.4 km/h
        self.assertAlmostEqual(stats['top_speed_kmh'], 5.4, places=1)


class TestActivityGroups(unittest.TestCase):
    """Validate the ACTIVITY_GROUPS structure."""

    def test_all_groups_have_required_keys(self):
        for key, grp in ACTIVITY_GROUPS.items():
            with self.subTest(group=key):
                self.assertIn('name', grp)
                self.assertIn('icon', grp)
                self.assertIn('noun', grp)
                self.assertIn('types', grp)
                self.assertIsInstance(grp['types'], list)
                self.assertGreater(len(grp['types']), 0)

    def test_walking_is_default(self):
        self.assertIn('walking', ACTIVITY_GROUPS)
        self.assertIn('Walk', ACTIVITY_GROUPS['walking']['types'])

    def test_cycling_types(self):
        cycling = ACTIVITY_GROUPS['cycling']
        self.assertIn('Ride', cycling['types'])
        self.assertIn('VirtualRide', cycling['types'])


class TestStatsRoutes(unittest.TestCase):
    """Mocked unit tests for the /stats page and /api/stats_data endpoint."""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_stats_page_uses_earliest_activity_year(self, mock_get_db, mock_get_user):
        """The page should render the year selector starting from the oldest activity year."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activities_web.return_value = [
            {'id': 1, 'start_date': '2023-02-01T08:00:00Z'},
        ]
        mock_repo.get_profile.return_value = {
            'first_name': 'Test',
            'last_name': 'Athlete',
        }
        mock_get_db.return_value = mock_repo

        response = self.client.get('/stats')

        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn('Mega Stats', html)
        self.assertIn('Walking', html)
        self.assertIn('2023', html)
        mock_repo.get_activities_web.assert_called_once_with(
            limit=1,
            sort_by='start_date',
            sort_order='ASC',
        )

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.compute_mega_stats')
    @patch('kinetiqo.web.app.get_db')
    def test_stats_api_returns_augmented_payload(self, mock_get_db, mock_compute_mega_stats, mock_get_user):
        """The API should return computed stats enriched with group and athlete metadata."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_activities_web.return_value = [
            {'id': 10, 'start_date': '2025-01-15T08:00:00Z', 'distance': 5000},
        ]
        mock_repo.get_profile.return_value = {
            'first_name': 'Test',
            'last_name': 'Athlete',
        }
        mock_get_db.return_value = mock_repo
        mock_compute_mega_stats.return_value = {
            'year': 2025,
            'period': 'q1',
            'period_label': 'Q1 2025',
            'start_date': '2025-01-01',
            'end_date': '2025-03-31',
            'total_distance_km': 5.0,
            'total_elevation_m': 0,
            'total_hours': 0,
            'total_activities': 1,
            'active_days': 1,
            'max_streak': 1,
            'longest_activity': {'name': 'Morning Walk', 'distance_km': 5.0, 'date': '2025-01-15'},
            'highest_elevation_activity': {'name': 'Morning Walk', 'elevation_m': 0, 'date': '2025-01-15'},
            'top_speed_kmh': 0,
            'most_active_month': {'number': 1, 'name': 'Jan', 'count': 1, 'distance_km': 5.0, 'color': '#FF4136'},
            'calendar': [],
            'month_colors': MONTH_COLORS,
        }

        response = self.client.get('/api/stats_data?year=2025&period=q1&group=walking')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['group_key'], 'walking')
        self.assertEqual(payload['group_name'], 'Walking')
        self.assertEqual(payload['group_icon'], '🥾')
        self.assertEqual(payload['group_noun'], 'walk')
        self.assertEqual(payload['athlete_name'], 'Test Athlete')
        self.assertEqual(payload['period_label'], 'Q1 2025')
        mock_repo.get_activities_web.assert_called_once_with(
            limit=100000,
            sort_by='start_date',
            sort_order='ASC',
            types=['Walk', 'Hike'],
            start_date='2025-01-01',
            end_date='2025-12-31',
        )
        mock_compute_mega_stats.assert_called_once_with(mock_repo.get_activities_web.return_value, 2025, 'q1')

    @patch('flask_login.utils._get_user')
    def test_stats_api_rejects_unknown_group(self, mock_get_user):
        """An unknown activity group should return a 400 error before touching the database."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        response = self.client.get('/api/stats_data?group=unknown')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unknown activity group', response.get_json()['error'])


class TestConstants(unittest.TestCase):
    """Sanity checks for module-level constants."""

    def test_month_colors_all_12(self):
        self.assertEqual(len(MONTH_COLORS), 12)
        for m in range(1, 13):
            self.assertIn(m, MONTH_COLORS)
            self.assertTrue(MONTH_COLORS[m].startswith('#'))

    def test_month_short_names_all_12(self):
        self.assertEqual(len(MONTH_SHORT_NAMES), 12)

    def test_valid_periods(self):
        self.assertIn('year', VALID_PERIODS)
        self.assertIn('q1', VALID_PERIODS)
        self.assertIn('h2', VALID_PERIODS)


if __name__ == '__main__':
    unittest.main()

