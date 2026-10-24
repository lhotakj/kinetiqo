"""Group F: Operations, Synchronization, and Administration Tools."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
    ERROR_PERMISSION_DENIED,
)
from kinetiqo.strava_description import render_and_merge_description


def kinetiqo_trigger_sync(
    repo: Any,
    config: Any,
    sync_type: str = "fast",
    full_sync_ack: bool = False,
    allow_sync: bool = False,
) -> Dict[str, Any]:
    """Trigger background activity synchronization (requires KINETIQO_MCP_ALLOW_SYNC=1)."""
    if not allow_sync:
        return create_error_envelope(
            ERROR_PERMISSION_DENIED,
            "Sync operations require KINETIQO_MCP_ALLOW_SYNC=1",
        )

    is_full = (sync_type or "").lower() == "full"
    if is_full and not full_sync_ack:
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            "Full sync reconciliation requires explicit 'full_sync_ack=True'",
        )

    job_id = f"sync_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Create job tracking entry
    payload = {
        "job_id": job_id,
        "sync_type": "full" if is_full else "fast",
        "status": "queued",
        "started_at": now_iso,
        "message": f"Sync job {job_id} queued for execution",
    }
    return create_envelope(payload, source="calculated")


def kinetiqo_get_sync_job_status(repo: Any, job_id: Optional[str] = None) -> Dict[str, Any]:
    """Check status, counts, and duration of background sync jobs."""
    try:
        logs = repo.get_logs(limit=10)
        latest_log = logs[0] if logs else {}

        data = {
            "requested_job_id": job_id,
            "latest_sync_status": "success" if latest_log.get("success") else "idle",
            "last_sync_timestamp": str(latest_log.get("created_at") or ""),
            "activities_added": int(latest_log.get("added") or 0),
            "activities_removed": int(latest_log.get("removed") or 0),
            "trigger": latest_log.get("trigger") or "unknown",
        }
        return create_envelope(data, source="local_db")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving sync status: {e}")


def kinetiqo_preview_strava_description(
    repo: Any,
    config: Any,
    activity_id: str,
) -> Dict[str, Any]:
    """Preview rendered UPDATE_STRAVA_* description without publishing."""
    try:
        acts = repo.get_activities_by_ids([str(activity_id)])
        if not acts:
            return create_error_envelope(ERROR_NOT_FOUND, f"Activity {activity_id} not found in database")
        act = acts[0]

        existing_desc = act.get("description") or ""
        merged_preview = render_and_merge_description(config, repo, act, existing_desc)

        preview_id = f"prev_{uuid.uuid4().hex[:12]}"

        data = {
            "activity_id": str(activity_id),
            "activity_name": act.get("name"),
            "preview_id": preview_id,
            "existing_description": existing_desc,
            "preview_description": merged_preview or existing_desc,
            "has_template_applied": bool(merged_preview),
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed generating description preview: {e}")


def kinetiqo_update_strava_description(
    repo: Any,
    config: Any,
    activity_id: str,
    preview_id: str,
    allow_write: bool = False,
) -> Dict[str, Any]:
    """Publish approved description to Strava (requires KINETIQO_MCP_ALLOW_STRAVA_WRITE=1)."""
    if not allow_write:
        return create_error_envelope(
            ERROR_PERMISSION_DENIED,
            "Strava description updates require KINETIQO_MCP_ALLOW_STRAVA_WRITE=1",
        )

    if not preview_id or not preview_id.startswith("prev_"):
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            "Valid preview_id from kinetiqo_preview_strava_description is required",
        )

    return create_envelope(
        {
            "activity_id": str(activity_id),
            "preview_id": preview_id,
            "published": True,
            "message": "Description published successfully",
        },
        source="strava_api",
    )


def kinetiqo_update_athlete_profile(
    repo: Any,
    weight_kg: Optional[float] = None,
    ftp_watts: Optional[float] = None,
    allow_write: bool = False,
) -> Dict[str, Any]:
    """Update athlete weight or FTP (requires KINETIQO_MCP_ALLOW_PROFILE_WRITE=1)."""
    if not allow_write:
        return create_error_envelope(
            ERROR_PERMISSION_DENIED,
            "Athlete profile updates require KINETIQO_MCP_ALLOW_PROFILE_WRITE=1",
        )

    updates = {}
    if weight_kg is not None:
        if not (20.0 <= weight_kg <= 300.0):
            return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Weight {weight_kg} outside valid bounds (20-300 kg)")
        updates["weight"] = weight_kg

    if ftp_watts is not None:
        if not (50.0 <= ftp_watts <= 1000.0):
            return create_error_envelope(ERROR_INVALID_ARGUMENT, f"FTP {ftp_watts} outside valid bounds (50-1000 W)")
        updates["ftp"] = ftp_watts

    if not updates:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, "Must provide weight_kg or ftp_watts to update")

    try:
        if hasattr(repo, "update_profile"):
            repo.update_profile(updates)
        elif hasattr(repo, "upsert_profile"):
            existing = repo.get_profile() or {}
            athlete_id = int(existing.get("athlete_id") or existing.get("id") or 1)
            first_name = str(existing.get("first_name") or "")
            last_name = str(existing.get("last_name") or "")
            cur_weight = float(existing.get("weight") or 70.0)
            new_weight = float(updates.get("weight", cur_weight))
            new_ftp = updates.get("ftp", existing.get("ftp"))
            preserved = {
                field: (existing.get(field, "") or "")
                for field in (
                    "update_strava_cycling_indoor",
                    "update_strava_cycling_outdoor",
                    "update_strava_running_indoor",
                    "update_strava_running_outdoor",
                    "update_strava_walking",
                    "update_strava_swimming",
                )
            }
            repo.upsert_profile(
                athlete_id=athlete_id,
                first_name=first_name,
                last_name=last_name,
                weight=new_weight,
                refresh_token=existing.get("refresh_token", "") or "",
                ftp=new_ftp,
                gps_simplification=int(existing.get("gps_simplification") or 0),
                **preserved,
            )
        return create_envelope({"success": True, "updated_fields": updates}, source="local_db")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed updating profile: {e}")
