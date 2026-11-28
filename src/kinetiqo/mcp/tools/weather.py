"""Read-only activity weather tools."""

import json
from typing import Any

from kinetiqo.mcp.contracts import (
    ERROR_DATA_UNAVAILABLE,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
    create_envelope,
    create_error_envelope,
)


def kinetiqo_get_activity_weather(
    repo: Any,
    activity_id: str,
    max_samples: int = 48,
) -> dict[str, Any]:
    """Return stored hourly weather for an activity without route coordinates."""
    if not activity_id or len(activity_id) > 64:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, "activity_id must be a non-empty ID.")
    if not 1 <= max_samples <= 168:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, "max_samples must be between 1 and 168.")
    try:
        row = repo.get_activity_weather(activity_id)
    except Exception as error:
        return create_error_envelope(ERROR_DATA_UNAVAILABLE, f"Could not read stored activity weather: {error}")
    if not row:
        return create_error_envelope(ERROR_NOT_FOUND, f"No stored weather is available for activity {activity_id}.")
    raw_payload = row.get("weather_json")
    if hasattr(raw_payload, "read"):
        raw_payload = raw_payload.read()
    try:
        payload = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload or "{}")
    except (TypeError, ValueError):
        return create_error_envelope(ERROR_DATA_UNAVAILABLE, "Stored activity weather is invalid JSON.")
    if not isinstance(payload, dict) or payload.get("status") != "complete":
        return create_error_envelope(ERROR_DATA_UNAVAILABLE, "Stored weather is not complete for this activity.")
    safe_payload = {
        key: value for key, value in payload.items()
        if key not in {"coordinates", "route_coordinates", "gps_points", "latitude", "longitude"}
    }
    samples = safe_payload.get("samples")
    if not isinstance(samples, list):
        return create_error_envelope(ERROR_DATA_UNAVAILABLE, "Stored weather samples are unavailable.")
    returned = samples[:max_samples]
    safe_payload["samples"] = returned
    warnings = []
    if len(returned) < len(samples):
        warnings.append(f"Weather samples were limited to the first {max_samples} of {len(samples)} hourly observations.")
    warnings.append("Hourly historical weather is an estimate based on provider data, not a direct on-route measurement.")
    return create_envelope(
        safe_payload,
        source="local_db",
        data_status="complete",
        warnings=warnings,
    )
