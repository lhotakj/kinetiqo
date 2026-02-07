from abc import ABC, abstractmethod
from typing import Optional, Set, List, Dict, Any

class DatabaseRepository(ABC):
    """Abstract base class for database operations."""

    @abstractmethod
    def initialize_schema(self):
        """Initialize or update the database schema."""
        pass

    @abstractmethod
    def get_latest_activity_time(self) -> Optional[int]:
        """Get the start timestamp of the activity with the highest ID."""
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
    def get_activities_web(self, limit=10, offset=0, sort_by='start_date', sort_order='DESC', types=None, start_date=None, end_date=None):
        """Get a list of activities for display."""
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
    def close(self):
        """Close database connection."""
        pass
