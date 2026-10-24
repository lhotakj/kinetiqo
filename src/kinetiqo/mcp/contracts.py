"""Data contracts, response envelopes, schemas, and error codes for Kinetiqo MCP."""

from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class MCPResponseEnvelope(BaseModel, Generic[T]):
    """Standard response envelope wrapping all Kinetiqo MCP tool responses."""

    schema_version: int = Field(default=1, description="Protocol envelope schema version")
    generated_at: str = Field(description="UTC ISO-8601 timestamp")
    source: Literal["local_db", "local_cache", "calculated", "strava_api", "rendered"]
    data_status: Literal["complete", "partial", "stale", "unavailable"]
    warnings: List[str] = Field(default_factory=list)
    data: T


class PaginationMetadata(BaseModel):
    """Metadata for cursor-based pagination."""

    next_cursor: Optional[str] = Field(None, description="Opaque URL-safe base64 string for next page")
    has_more: bool = Field(default=False, description="True if more records exist beyond current page")
    total_matched: Optional[int] = Field(None, description="Total matching records count if available")


class ActivitySummaryItem(BaseModel):
    """Summary item for activity search results."""

    activity_id: str
    name: str
    start_date: str
    sport: str
    distance_km: float
    moving_time_s: int
    elevation_gain_m: float
    average_watts: Optional[float] = None
    suffer_score: Optional[int] = None


class ActivitySearchData(BaseModel):
    """Payload for kinetiqo_search_activities."""

    activities: List[Dict[str, Any]]
    pagination: PaginationMetadata


# Error Codes
ERROR_INVALID_ARGUMENT = "INVALID_ARGUMENT"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
ERROR_NOT_CONFIGURED = "NOT_CONFIGURED"
ERROR_PERMISSION_DENIED = "PERMISSION_DENIED"
ERROR_CONFLICT = "CONFLICT"
ERROR_RATE_LIMITED = "RATE_LIMITED"
ERROR_RESOURCE_LIMIT = "RESOURCE_LIMIT"
ERROR_UPSTREAM_ERROR = "UPSTREAM_ERROR"
ERROR_INTERNAL_ERROR = "INTERNAL_ERROR"


def create_envelope(
    data: Any,
    source: Literal["local_db", "local_cache", "calculated", "strava_api", "rendered"] = "local_db",
    data_status: Literal["complete", "partial", "stale", "unavailable"] = "complete",
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a standardized response envelope dictionary."""
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "data_status": data_status,
        "warnings": warnings or [],
        "data": data,
    }


def create_error_envelope(
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a standardized error response envelope dictionary."""
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "calculated",
        "data_status": "unavailable",
        "warnings": [f"[{error_code}] {message}"],
        "data": {
            "error_code": error_code,
            "message": message,
            "details": details or {},
        },
    }
