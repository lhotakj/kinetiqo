"""Mega Stats computation for the infographic page.

Computes summary statistics and calendar heatmap data from a list of
activities filtered by year, period, and activity types.
"""

from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict


# Rainbow month colours (1-indexed month → hex)
MONTH_COLORS: Dict[int, str] = {
    1:  '#FF4136',   # Jan  – Red
    2:  '#FF6D3A',   # Feb  – Orange-Red
    3:  '#FF851B',   # Mar  – Orange
    4:  '#FFDC00',   # Apr  – Yellow
    5:  '#B4D455',   # May  – Yellow-Green
    6:  '#2ECC40',   # Jun  – Green
    7:  '#01A884',   # Jul  – Teal
    8:  '#0074D9',   # Aug  – Blue
    9:  '#4A6CF7',   # Sep  – Indigo
    10: '#7B43CF',   # Oct  – Purple
    11: '#B10DC9',   # Nov  – Magenta
    12: '#FF3F80',   # Dec  – Pink
}

MONTH_SHORT_NAMES: Dict[int, str] = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
    5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
    9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec',
}

# Activity-type groups surfaced in the infographic selector.
ACTIVITY_GROUPS: Dict[str, Dict[str, Any]] = {
    'walking': {
        'name': 'Walking',
        'icon': '🥾',
        'noun': 'walk',
        'types': ['Walk', 'Hike'],
    },
    'cycling': {
        'name': 'Cycling',
        'icon': '🚴',
        'noun': 'ride',
        'types': [
            'Ride', 'VirtualRide', 'EBikeRide', 'EMountainBikeRide',
            'GravelRide', 'MountainBikeRide', 'Velomobile', 'Handcycle',
        ],
    },
    'running': {
        'name': 'Running',
        'icon': '🏃',
        'noun': 'run',
        'types': ['Run', 'VirtualRun', 'TrailRun'],
    },
    'skiing': {
        'name': 'Skiing',
        'icon': '⛷️',
        'noun': 'ski session',
        'types': ['AlpineSki', 'BackcountrySki', 'NordicSki', 'Snowboard'],
    },
    'swimming': {
        'name': 'Swimming',
        'icon': '🏊',
        'noun': 'swim',
        'types': ['Swim'],
    },
}

VALID_PERIODS = ('year', 'q1', 'q2', 'q3', 'q4', 'h1', 'h2')


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_period_range(year: int, period: str) -> Tuple[date, date]:
    """Return ``(start_date, end_date)`` for the given year and period."""
    ranges = {
        'q1': (date(year, 1, 1), date(year, 3, 31)),
        'q2': (date(year, 4, 1), date(year, 6, 30)),
        'q3': (date(year, 7, 1), date(year, 9, 30)),
        'q4': (date(year, 10, 1), date(year, 12, 31)),
        'h1': (date(year, 1, 1), date(year, 6, 30)),
        'h2': (date(year, 7, 1), date(year, 12, 31)),
    }
    return ranges.get(period, (date(year, 1, 1), date(year, 12, 31)))


def parse_activity_date(date_str) -> Optional[date]:
    """Parse a date string or datetime to a :class:`date` object."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str).replace('Z', '+00:00')).date()
    except Exception:
        try:
            return datetime.strptime(str(date_str)[:10], '%Y-%m-%d').date()
        except Exception:
            return None


def compute_max_streak(active_dates: set) -> int:
    """Compute the longest run of consecutive active days."""
    if not active_dates:
        return 0
    sorted_dates = sorted(active_dates)
    max_streak = 1
    current = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            current += 1
            if current > max_streak:
                max_streak = current
        else:
            current = 1
    return max_streak


def build_calendar(start_date: date, end_date: date,
                   daily_distance: Dict[date, float]) -> List[List[Dict[str, Any]]]:
    """Build calendar heatmap data as a list of weeks.

    Each week is a list of 7 day-slot dicts (Monday = index 0).
    """
    first_monday = start_date - timedelta(days=start_date.weekday())
    last_sunday = end_date + timedelta(days=(6 - end_date.weekday()))

    weeks: List[List[Dict[str, Any]]] = []
    current = first_monday
    while current <= last_sunday:
        week = []
        for dow in range(7):
            d = current + timedelta(days=dow)
            in_range = start_date <= d <= end_date
            dist = daily_distance.get(d, 0.0) if in_range else 0.0
            week.append({
                'date': d.isoformat(),
                'day': d.day,
                'weekday': dow,
                'month': d.month,
                'distance_km': round(dist, 2),
                'has_activity': dist > 0,
                'in_range': in_range,
                'color': MONTH_COLORS.get(d.month, '#555') if in_range else '#333',
            })
        weeks.append(week)
        current += timedelta(days=7)

    return weeks


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_mega_stats(activities: List[Dict[str, Any]],
                       year: int,
                       period: str) -> Dict[str, Any]:
    """Compute all summary statistics for the Mega Stats infographic.

    :param activities: Activity dicts as returned by ``get_activities_web``.
    :param year: Target year.
    :param period: One of :data:`VALID_PERIODS`.
    :return: Dict with stats, calendar data, and metadata.
    """
    start_date, end_date = get_period_range(year, period)

    # Clamp end date to today when in the future
    today = date.today()
    if end_date > today:
        end_date = today

    # Filter activities within the date range
    filtered: List[Tuple[Dict[str, Any], date]] = []
    for a in activities:
        d = parse_activity_date(a.get('start_date'))
        if d and start_date <= d <= end_date:
            filtered.append((a, d))

    if not filtered:
        return _empty_stats(year, period, start_date, end_date)

    # ---- Basic totals ----
    total_distance_m = sum(float(a.get('distance') or 0) for a, _ in filtered)
    total_elevation_m = sum(float(a.get('total_elevation_gain') or 0) for a, _ in filtered)
    total_moving_time_s = sum(int(a.get('moving_time') or 0) for a, _ in filtered)
    total_activities = len(filtered)

    # ---- Records ----
    longest = max(filtered, key=lambda x: float(x[0].get('distance') or 0))
    longest_activity = {
        'name': longest[0].get('name', ''),
        'distance_km': round(float(longest[0].get('distance') or 0) / 1000.0, 1),
        'date': longest[1].isoformat(),
    }

    highest_elev = max(filtered, key=lambda x: float(x[0].get('total_elevation_gain') or 0))
    highest_elevation_activity = {
        'name': highest_elev[0].get('name', ''),
        'elevation_m': round(float(highest_elev[0].get('total_elevation_gain') or 0)),
        'date': highest_elev[1].isoformat(),
    }

    # Top speed: prefer max_speed (m/s), fall back to average_speed
    max_speed_ms = max(
        (float(a.get('max_speed') or a.get('average_speed') or 0) for a, _ in filtered),
        default=0,
    )
    top_speed_kmh = round(max_speed_ms * 3.6, 1)

    # ---- Active days, streak, monthly aggregates ----
    active_dates: set = set()
    daily_distance: Dict[date, float] = defaultdict(float)
    monthly_distance: Dict[int, float] = defaultdict(float)
    monthly_count: Dict[int, int] = defaultdict(int)

    for a, d in filtered:
        active_dates.add(d)
        dist_km = float(a.get('distance') or 0) / 1000.0
        daily_distance[d] += dist_km
        monthly_distance[d.month] += dist_km
        monthly_count[d.month] += 1

    active_days = len(active_dates)
    max_streak = compute_max_streak(active_dates)

    # Most active month (by activity count)
    if monthly_count:
        best_month = max(monthly_count, key=lambda m: monthly_count[m])
        most_active_month = {
            'number': best_month,
            'name': MONTH_SHORT_NAMES.get(best_month, ''),
            'count': monthly_count[best_month],
            'distance_km': round(monthly_distance[best_month], 1),
            'color': MONTH_COLORS.get(best_month, '#888'),
        }
    else:
        most_active_month = _empty_month()

    # ---- Calendar heatmap ----
    calendar = build_calendar(start_date, end_date, daily_distance)

    return {
        'year': year,
        'period': period,
        'period_label': _period_label(year, period),
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'total_distance_km': round(total_distance_m / 1000.0, 1),
        'total_elevation_m': round(total_elevation_m),
        'total_hours': round(total_moving_time_s / 3600.0, 1),
        'total_activities': total_activities,
        'active_days': active_days,
        'max_streak': max_streak,
        'longest_activity': longest_activity,
        'highest_elevation_activity': highest_elevation_activity,
        'top_speed_kmh': top_speed_kmh,
        'most_active_month': most_active_month,
        'calendar': calendar,
        'month_colors': MONTH_COLORS,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _empty_month() -> Dict[str, Any]:
    return {'number': 0, 'name': '', 'count': 0, 'distance_km': 0, 'color': '#888'}


def _empty_stats(year: int, period: str, start_date: date, end_date: date) -> Dict[str, Any]:
    return {
        'year': year,
        'period': period,
        'period_label': _period_label(year, period),
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'total_distance_km': 0,
        'total_elevation_m': 0,
        'total_hours': 0,
        'total_activities': 0,
        'active_days': 0,
        'max_streak': 0,
        'longest_activity': {'name': '', 'distance_km': 0, 'date': ''},
        'highest_elevation_activity': {'name': '', 'elevation_m': 0, 'date': ''},
        'top_speed_kmh': 0,
        'most_active_month': _empty_month(),
        'calendar': build_calendar(start_date, end_date, {}),
        'month_colors': MONTH_COLORS,
    }


def _period_label(year: int, period: str) -> str:
    labels = {
        'year': str(year),
        'q1': f'Q1 {year}',
        'q2': f'Q2 {year}',
        'q3': f'Q3 {year}',
        'q4': f'Q4 {year}',
        'h1': f'H1 {year}',
        'h2': f'H2 {year}',
    }
    return labels.get(period, str(year))

