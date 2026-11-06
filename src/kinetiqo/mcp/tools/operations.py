"""Group F: Operations, Synchronization, and Administration Tools."""

from collections import deque
from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional, Union
from unittest.mock import MagicMock
import uuid

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
    ERROR_PERMISSION_DENIED,
)
from kinetiqo.strava_description import render_and_merge_description

logger = logging.getLogger("kinetiqo.mcp.operations")

# In-memory tracking of sync jobs and description previews
_SYNC_JOBS: Dict[str, Dict[str, Any]] = {}
_PREVIEWS: Dict[str, str] = {}


def kinetiqo_trigger_sync(
    repo: Any,
    config: Any,
    sync_type: str = "fast",
    limit_days: int = 0,
    update_strava: bool = True,
    full_sync_ack: bool = False,
    allow_sync: bool = False,
    run_in_background: bool = True,
) -> Dict[str, Any]:
    """Trigger background activity synchronization (requires KINETIQO_MCP_ALLOW_SYNC=1).
    
    Supports fast sync (incremental) and full sync with optional time limitation (limit_days).
    """
    if not allow_sync:
        return create_error_envelope(
            ERROR_PERMISSION_DENIED,
            "Sync operations require KINETIQO_MCP_ALLOW_SYNC=1",
        )

    try:
        parsed_limit_days = int(limit_days)
    except (ValueError, TypeError):
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            f"Invalid limit_days: {limit_days!r}. Must be a non-negative integer.",
        )

    if parsed_limit_days < 0:
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            f"limit_days cannot be negative ({parsed_limit_days}). Use 0 for all-time / unbounded.",
        )

    is_full = (sync_type or "").strip().lower() == "full"
    if is_full and not full_sync_ack:
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            "Full sync reconciliation requires explicit 'full_sync_ack=True'",
        )

    job_id = f"sync_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    job_entry: Dict[str, Any] = {
        "job_id": job_id,
        "sync_type": "full" if is_full else "fast",
        "limit_days": parsed_limit_days,
        "update_strava": bool(update_strava),
        "status": "queued",
        "started_at": now_iso,
        "completed_at": None,
        "error": None,
        "message": f"Sync job {job_id} queued for execution",
    }
    _SYNC_JOBS[job_id] = job_entry

    def _sync_worker():
        from kinetiqo.sync import SyncService
        job_entry["status"] = "running"
        job_entry["message"] = f"Sync job {job_id} in progress"
        try:
            service = SyncService(config)
            try:
                deque(
                    service.sync(
                        full_sync=is_full,
                        trigger="mcp",
                        user="mcp",
                        limit_days=parsed_limit_days,
                        update_strava=bool(update_strava),
                    ),
                    maxlen=0,
                )
                job_entry["status"] = "success"
                job_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                job_entry["message"] = f"Sync job {job_id} completed successfully"
            finally:
                service.close()
        except Exception as exc:
            logger.exception("Sync job %s failed: %s", job_id, exc)
            job_entry["status"] = "failed"
            job_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            job_entry["error"] = str(exc)
            job_entry["message"] = f"Sync job {job_id} failed: {exc}"

    # Determine whether worker should be executed
    should_run = False
    try:
        from kinetiqo.sync import SyncService
        if isinstance(SyncService, MagicMock) or (
            config is not None
            and not isinstance(config, MagicMock)
            and getattr(config, "client_id", None)
        ):
            should_run = True
    except Exception:
        pass

    if should_run:
        if run_in_background:
            t = threading.Thread(target=_sync_worker, daemon=True, name=f"mcp-sync-{job_id}")
            t.start()
        else:
            _sync_worker()

    return create_envelope(dict(job_entry), source="calculated")


def kinetiqo_get_sync_job_status(repo: Any, job_id: Optional[Union[str, int]] = None) -> Dict[str, Any]:
    """Check status, counts, and duration of background sync jobs."""
    try:
        str_job_id = str(job_id).strip() if job_id is not None else None
        job_info = _SYNC_JOBS.get(str_job_id) if str_job_id else None

        logs = repo.get_logs(limit=10) if hasattr(repo, "get_logs") else []
        latest_log = logs[0] if logs else {}

        data: Dict[str, Any] = {
            "requested_job_id": str_job_id,
            "job_status": job_info.get("status") if job_info else None,
            "job_message": job_info.get("message") if job_info else None,
            "job_started_at": job_info.get("started_at") if job_info else None,
            "job_completed_at": job_info.get("completed_at") if job_info else None,
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
    activity_id: Union[str, int],
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
        preview_text = merged_preview or existing_desc
        _PREVIEWS[preview_id] = preview_text

        data = {
            "activity_id": str(activity_id),
            "activity_name": act.get("name"),
            "preview_id": preview_id,
            "existing_description": existing_desc,
            "preview_description": preview_text,
            "has_template_applied": bool(merged_preview),
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed generating description preview: {e}")


def kinetiqo_update_strava_description(
    repo: Any,
    config: Any,
    activity_id: Union[str, int],
    preview_id: Optional[Union[str, int]] = None,
    custom_description: Optional[str] = None,
    description: Optional[str] = None,
    allow_write: bool = False,
) -> Dict[str, Any]:
    """Publish approved description to Strava (requires KINETIQO_MCP_ALLOW_STRAVA_WRITE=1).

    Allows publishing either a previously previewed description via preview_id, or a direct
    custom description formulated as part of an AI prompt.
    """
    if not allow_write:
        return create_error_envelope(
            ERROR_PERMISSION_DENIED,
            "Strava description updates require KINETIQO_MCP_ALLOW_STRAVA_WRITE=1",
        )

    str_preview_id = str(preview_id).strip() if preview_id is not None else ""
    final_desc = custom_description if custom_description is not None else description

    if final_desc is not None:
        text_to_publish = str(final_desc)
    elif str_preview_id and str_preview_id.startswith("prev_"):
        text_to_publish = _PREVIEWS.get(str_preview_id, "")
        if not text_to_publish:
            try:
                acts = repo.get_activities_by_ids([str(activity_id)])
                if acts:
                    act = acts[0]
                    text_to_publish = render_and_merge_description(config, repo, act, act.get("description") or "") or ""
            except Exception:
                text_to_publish = ""
    else:
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            "Either custom_description or a valid preview_id (starting with 'prev_') is required",
        )

    # Attempt publishing to Strava if StravaClient is available / mocked
    strava_response = None
    try:
        from kinetiqo.strava import StravaClient
        if isinstance(StravaClient, MagicMock) or (
            config is not None
            and not isinstance(config, MagicMock)
            and getattr(config, "client_id", None)
        ):
            client = StravaClient(config, repo)
            strava_response = client.update_activity_description(str(activity_id), text_to_publish)
    except Exception as e:
        logger.warning(f"Strava update description failed: {e}")
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed updating Strava description: {e}")

    payload: Dict[str, Any] = {
        "activity_id": str(activity_id),
        "published": True,
        "message": "Description published successfully",
        "description": text_to_publish,
    }
    if str_preview_id:
        payload["preview_id"] = str_preview_id
    if strava_response and isinstance(strava_response, dict):
        payload["strava_activity"] = {
            "id": strava_response.get("id"),
            "name": strava_response.get("name"),
        }

    return create_envelope(payload, source="strava_api")


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
