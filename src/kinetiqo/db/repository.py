from abc import ABC, abstractmethod
from typing import Optional, Set, List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Activity-type constants used for the activity_goals table.
# New sport categories can be added here — the database stores the integer ID.
# ---------------------------------------------------------------------------
GOAL_TYPE_CYCLING = 1   # Ride, VirtualRide, EBikeRide, GravelRide, …
GOAL_TYPE_WALKING = 2   # Walk, Hike


def compute_best_average_power(watts_series: List[float], duration_seconds: int) -> float:
    """O(N) sliding-window maximum average power for a single activity.

    This is the canonical, backend-agnostic implementation used by MySQL and
    Firebird (where SQL window functions are O(N×K) and unusable for large K).
    PostgreSQL uses its own O(N) SQL window-function path instead.

    :param watts_series: List of watts values ordered by timestamp (1 sample/sec).
    :param duration_seconds: Window size in seconds.
    :return: Best average power as float, or 0.0 if insufficient data.
    """
    n = len(watts_series)
    if n < duration_seconds:
        return 0.0

    window_sum = sum(watts_series[:duration_seconds])
    max_sum = window_sum

    for i in range(1, n - duration_seconds + 1):
        window_sum += watts_series[i + duration_seconds - 1] - watts_series[i - 1]
        if window_sum > max_sum:
            max_sum = window_sum

    return max_sum / duration_seconds


def compute_best_power_per_activity(
    watts_data: Dict[str, List[float]],
    duration_seconds: int,
    min_total_samples: int = 0,
) -> Dict[str, float]:
    """Compute best rolling-average power for each activity from raw watts data.

    Wraps :func:`compute_best_average_power` with the ``min_total_samples``
    filter so that MySQL and Firebird repositories can delegate to this after
    fetching raw watts via ``get_watts_streams_for_activities``.

    :param watts_data: Dict mapping activity_id → list of watts values.
    :param duration_seconds: Rolling-window size in seconds.
    :param min_total_samples: Minimum total non-NULL watts samples required
        per activity.  Activities with fewer samples are omitted.  Defaults to
        ``duration_seconds`` when ≤ 0.
    :return: Dict mapping activity_id → best average watts (float).
    """
    min_total = min_total_samples if min_total_samples > 0 else duration_seconds
    result: Dict[str, float] = {}

    for aid, watts_list in watts_data.items():
        if len(watts_list) < min_total:
            continue
        best = compute_best_average_power(watts_list, duration_seconds)
        if best > 0:
            result[aid] = best

    return result

# Mapping from Strava sport-type strings to GOAL_TYPE_* IDs
STRAVA_TYPE_TO_GOAL_TYPE: Dict[str, int] = {
    "Ride": GOAL_TYPE_CYCLING,
    "VirtualRide": GOAL_TYPE_CYCLING,
    "EBikeRide": GOAL_TYPE_CYCLING,
    "EMountainBikeRide": GOAL_TYPE_CYCLING,
    "GravelRide": GOAL_TYPE_CYCLING,
    "MountainBikeRide": GOAL_TYPE_CYCLING,
    "Velomobile": GOAL_TYPE_CYCLING,
    "Handcycle": GOAL_TYPE_CYCLING,
    "Walk": GOAL_TYPE_WALKING,
    "Hike": GOAL_TYPE_WALKING,
}


class DatabaseRepository(ABC):
    """Abstract base class for database operations."""

    @abstractmethod
    def initialize_schema(self):
        """Initialize or update the database schema."""
        pass

    @abstractmethod
    def flightcheck(self) -> bool:
        """Perform a health check on the database."""
        pass

    @abstractmethod
    def get_latest_activity_time(self) -> Optional[int]:
        """Get the start timestamp (epoch) of the most recent activity by date.

        Used by fast sync to determine which activities to fetch from Strava.
        Returns ``None`` when the activities table is empty.
        """
        pass

    @abstractmethod
    def get_synced_activity_ids(self) -> Set[str]:
        """Get all activity IDs already in the database."""
        pass

    @abstractmethod
    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        pass

    @abstractmethod
    def get_activities_web(self, limit=10, offset=0, sort_by='start_date', sort_order='DESC', types=None,
                           start_date=None, end_date=None):
        """Get a list of activities for display."""
        pass

    @abstractmethod
    def get_activities_by_ids(self, activity_ids: List[str]) -> List[Dict[str, Any]]:
        """Get a list of activities by their IDs."""
        pass

    @abstractmethod
    def get_activities_totals(self, types=None, start_date=None, end_date=None) -> Dict[str, float]:
        """Get totals for distance, elevation, and moving_time for the filtered activities."""
        pass

    @abstractmethod
    def count_activities(self, types=None):
        pass

    @abstractmethod
    def write_activity(self, activity: dict):
        """Write activity metadata to the database."""
        pass

    @abstractmethod
    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to the database."""
        pass

    @abstractmethod
    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from the database."""
        pass

    @abstractmethod
    def delete_activities(self, activity_ids: List[str]):
        """Delete multiple activities and their streams from the database."""
        pass

    @abstractmethod
    def log_sync(self, added: int, removed: int, trigger: str, success: bool, action: str, user: str):
        """Log the result of a sync operation."""
        pass

    @abstractmethod
    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest sync logs."""
        pass

    @abstractmethod
    def get_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get GPS streams (lat, lng) for a list of activity IDs.

        Returns a dictionary mapping activity_id to a list of {lat, lng} points.
        """
        pass

    @abstractmethod
    def get_streams_coords_for_activities(self, activity_ids: List[str]) -> Dict[str, List[List[float]]]:
        """Get GPS coordinate arrays for a list of activity IDs.

        Returns a dictionary mapping activity_id to a compact list of [lat, lng] pairs.
        More memory-efficient than get_streams_for_activities() — avoids per-point dict overhead.

        :param activity_ids: List of activity IDs to fetch coordinates for.
        :return: Dict mapping activity_id string to list of [lat, lng] float pairs.
        """
        pass

    @abstractmethod
    def get_streams_bounds_for_activities(self, activity_ids: List[str]) -> Optional[Tuple[float, float, float, float]]:
        """Get GPS bounding box for a list of activity IDs via SQL aggregation.

        Returns (min_lat, min_lng, max_lat, max_lng) or None if no GPS data exists.
        Much faster than computing bounds in Python from all coordinate rows.

        :param activity_ids: List of activity IDs to compute bounds for.
        :return: Tuple of (min_lat, min_lng, max_lat, max_lng) or None.
        """
        pass

    @abstractmethod
    def get_activity_name(self, activity_id: str) -> Optional[str]:
        """Get the name of an activity by its ID."""
        pass

    @abstractmethod
    def close(self):
        """Close database connection."""
        pass

    @abstractmethod
    def get_watts_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[float]]:
        """Get watts time-series for a list of activity IDs.

        Returns a dictionary mapping activity_id to a list of watts values
        ordered by timestamp (1 sample per second).

        :param activity_ids: List of activity IDs to fetch watts for.
        :return: Dict mapping activity_id string to list of float watts values.
        """
        pass

    @abstractmethod
    def get_best_power_per_activity(
        self,
        activity_ids: List[str],
        duration_seconds: int,
        min_total_samples: int = 0,
    ) -> Dict[str, float]:
        """Return the best (maximum) sliding-window average power for each activity.

        **Implementation strategy varies by backend:**

        * **PostgreSQL** — uses SQL ``AVG() OVER (ROWS BETWEEN …)`` window
          functions.  PostgreSQL implements these with an O(N) sliding
          accumulator and the partial covering index
          ``(activity_id, ts) INCLUDE (watts) WHERE watts IS NOT NULL``
          enables index-only scans, making this very fast.

        * **MySQL / Firebird** — fetches raw watts via
          ``get_watts_streams_for_activities`` and computes the sliding-window
          maximum in Python using :func:`compute_best_power_per_activity`.
          MySQL 8.0 and Firebird 4.0 implement ``AVG() OVER (ROWS BETWEEN K
          PRECEDING …)`` with **O(N×K) naive recomputation** (re-summing K
          values for every row), which makes the SQL approach unusable for
          large K (e.g. 1 200 for FTP).  The Python path is O(N) and proven
          fast by the Power Skills spider chart.

        :param activity_ids: Activity IDs to process.
        :param duration_seconds: Rolling-window size in seconds
            (e.g. 300 for VO2max MAP, 1200 for FTP).
        :param min_total_samples: Minimum number of non-NULL watts samples an
            activity must have **in total** to be included.  Defaults to
            ``duration_seconds`` (at least one full window).
        :return: Dict mapping activity_id string to best average watts (float).
            Activities with insufficient data are omitted.
        """
        pass

    @abstractmethod
    def get_activity_ids_by_types(
        self,
        types: List[str],
        since_date: Optional[Any] = None,
        watts_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get lightweight activity records filtered by sport type.

        Returns a list of dicts with ``id``, ``name``, and ``start_date`` keys,
        ordered by ``start_date DESC``.

        :param types: List of sport-type strings to filter on (e.g. ``["Ride", "VirtualRide"]``).
        :param since_date: Optional datetime (aware or naive UTC). When provided, only
            activities whose ``start_date >= since_date`` are returned.  Pushing the
            date cut-off to SQL avoids loading the full activity list into Python just
            to discard old rows — the existing ``idx_activities_sport_start_date``
            index on ``(sport, start_date DESC)`` covers this filter efficiently.
        :param watts_only: When ``True``, only activities with ``average_watts IS NOT NULL``
            are returned.  This pre-filters the activity list to those that actually have
            power-meter data, dramatically reducing the number of stream rows the caller
            must load for VO2max / FTP calculations.  Particularly important for Firebird
            where each extra activity_id in the subsequent IN clause adds a separate
            index range scan on the streams table.
        :return: List of matching activity summary dicts.
        """
        pass

    @abstractmethod
    def get_table_record_counts(self) -> Dict[str, int]:
        """Return a dict of table names and their record counts."""
        pass

    @abstractmethod
    def get_activities_with_suffer_score(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get activities that have a suffer_score > 0, ordered by date.

        :param days: Optional number of days to look back from today. If provided,
            only activities within the last ``days`` days should be returned. If None,
            no date limit must be applied (i.e. return all matching activities for all time).
        :return: List of activity records with a positive suffer_score.
        """
        pass

    @abstractmethod
    def get_profile(self) -> Optional[Dict[str, Any]]:
        """Return the first athlete profile row, or ``None`` if the table is empty.

        :return: Dict with ``athlete_id``, ``first_name``, ``last_name``, ``weight`` keys.
        """
        pass

    @abstractmethod
    def upsert_profile(self, athlete_id: int, first_name: str, last_name: str, weight: float) -> None:
        """Insert or update the athlete profile row.

        :param athlete_id: Strava athlete ID (primary key).
        :param first_name: Athlete first name.
        :param last_name: Athlete last name.
        :param weight: Athlete body weight in kilograms.
        """
        pass

    # ------------------------------------------------------------------
    # Activity goals
    # ------------------------------------------------------------------

    @abstractmethod
    def get_goals(self, athlete_id: int) -> List[Dict[str, Any]]:
        """Return all goal rows for *athlete_id*, ordered by activity_type_id.

        Each dict has the keys:
          activity_type_id, weekly_distance_goal, monthly_distance_goal,
          yearly_distance_goal, weekly_elevation_goal, monthly_elevation_goal,
          yearly_elevation_goal.
        Any unset goal field is ``None``.
        Distance goals are stored in **km**; elevation goals in **metres**.
        """
        pass

    @abstractmethod
    def upsert_goal(
        self,
        athlete_id: int,
        activity_type_id: int,
        weekly_distance_goal: Optional[float],
        monthly_distance_goal: Optional[float],
        yearly_distance_goal: Optional[float],
        weekly_elevation_goal: Optional[float],
        monthly_elevation_goal: Optional[float],
        yearly_elevation_goal: Optional[float],
    ) -> None:
        """Insert or update a single activity-type goal row for *athlete_id*.

        Pass ``None`` for any goal that should be cleared / left unset.
        """
        pass

