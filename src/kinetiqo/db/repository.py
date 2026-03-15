from abc import ABC, abstractmethod
from typing import Optional, Set, List, Dict, Any, Tuple


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
    def get_activity_ids_by_types(self, types: List[str]) -> List[Dict[str, Any]]:
        """Get lightweight activity records filtered by sport type.

        Returns a list of dicts with ``id``, ``name``, and ``start_date`` keys,
        ordered by ``start_date DESC``.

        :param types: List of sport-type strings to filter on (e.g. ``["Ride", "VirtualRide"]``).
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
