"""Group A: Activity Discovery & Query Engine Tools."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import math

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
)
from kinetiqo.mcp.utils import normalize_sport_types, resolve_date_range


def kinetiqo_search_activities(
    repo: Any,
    athlete_id: Optional[int] = None,
    query: Optional[str] = None,
    sport_types: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date_preset: Optional[str] = None,
    min_distance_km: Optional[float] = None,
    max_distance_km: Optional[float] = None,
    min_elevation_m: Optional[float] = None,
    max_elevation_m: Optional[float] = None,
    min_moving_time_min: Optional[float] = None,
    max_moving_time_min: Optional[float] = None,
    min_watts: Optional[float] = None,
    max_watts: Optional[float] = None,
    min_max_watts: Optional[float] = None,
    max_max_watts: Optional[float] = None,
    min_heartrate: Optional[float] = None,
    max_heartrate: Optional[float] = None,
    has_heartrate: Optional[bool] = None,
    has_power: Optional[bool] = None,
    min_speed_kmh: Optional[float] = None,
    max_speed_kmh: Optional[float] = None,
    min_suffer_score: Optional[int] = None,
    max_suffer_score: Optional[int] = None,
    min_pr_count: Optional[int] = None,
    gear_id: Optional[str] = None,
    workout_type: Optional[int] = None,
    has_trophies: Optional[bool] = None,
    koms_only: Optional[bool] = None,
    cursor: Optional[str] = None,
    limit: int = 20,
    sort_by: str = "start_date",
    sort_order: str = "desc",
) -> Dict[str, Any]:
    """Search and filter activities using comprehensive telemetry criteria with deterministic keyset pagination."""
    limit = max(1, min(limit, 100))
    norm_sport_types = normalize_sport_types(sport_types)
    filters: Dict[str, Any] = {"sort_by": sort_by, "sort_order": sort_order}

    if query:
        clean_query = query.strip()
        filters["query"] = clean_query
        filters["keyword"] = clean_query
    if norm_sport_types:
        filters["sport_types"] = norm_sport_types

    resolved_start, resolved_end = resolve_date_range(start_date=start_date, end_date=end_date, preset=date_preset)
    if resolved_start:
        filters["start_date"] = resolved_start
    if resolved_end:
        filters["end_date"] = resolved_end

    if min_distance_km is not None:
        filters["min_distance_km"] = min_distance_km
        filters["min_distance"] = min_distance_km * 1000.0
    if max_distance_km is not None:
        filters["max_distance_km"] = max_distance_km
        filters["max_distance"] = max_distance_km * 1000.0
    if min_elevation_m is not None:
        filters["min_elevation_m"] = min_elevation_m
        filters["min_elevation"] = min_elevation_m
    if max_elevation_m is not None:
        filters["max_elevation_m"] = max_elevation_m
        filters["max_elevation"] = max_elevation_m

    if min_moving_time_min is not None:
        filters["min_moving_time_min"] = min_moving_time_min
    if max_moving_time_min is not None:
        filters["max_moving_time_min"] = max_moving_time_min
    if min_watts is not None:
        filters["min_watts"] = min_watts
    if max_watts is not None:
        filters["max_watts"] = max_watts
    if min_max_watts is not None:
        filters["min_max_watts"] = min_max_watts
    if max_max_watts is not None:
        filters["max_max_watts"] = max_max_watts
    if min_heartrate is not None:
        filters["min_heartrate"] = min_heartrate
    if max_heartrate is not None:
        filters["max_heartrate"] = max_heartrate
    if has_heartrate is not None:
        filters["has_heartrate"] = has_heartrate
    if has_power is not None:
        filters["has_power"] = has_power
    if min_speed_kmh is not None:
        filters["min_speed_kmh"] = min_speed_kmh
    if max_speed_kmh is not None:
        filters["max_speed_kmh"] = max_speed_kmh
    if min_suffer_score is not None:
        filters["min_suffer_score"] = min_suffer_score
    if max_suffer_score is not None:
        filters["max_suffer_score"] = max_suffer_score
    if min_pr_count is not None:
        filters["min_pr_count"] = min_pr_count
    if gear_id:
        filters["gear_id"] = gear_id
    if workout_type is not None:
        filters["workout_type"] = workout_type
    if has_trophies is not None:
        filters["has_trophies"] = has_trophies
    if koms_only is not None:
        filters["koms_only"] = koms_only

    try:
        rows, next_cursor, has_more = repo.search_activities(
            athlete_id=athlete_id,
            filters=filters,
            limit=limit,
            cursor=cursor,
        )
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Activity search failed: {e}")

    activities = []
    for r in rows:
        act_id = str(r.get("activity_id") or r.get("id"))
        dist_m = float(r.get("distance") or 0.0)
        mov_s = int(r.get("moving_time") or 0)
        elev_m = float(r.get("total_elevation_gain") or r.get("elevation_gain") or 0.0)
        watts = float(r["average_watts"]) if r.get("average_watts") is not None else None
        max_w = float(r["max_watts"]) if r.get("max_watts") is not None else None
        avg_hr = float(r["average_heartrate"]) if r.get("average_heartrate") is not None else None
        max_hr = float(r["max_heartrate"]) if r.get("max_heartrate") is not None else None
        avg_cadence = float(r["average_cadence"]) if r.get("average_cadence") is not None else None
        w_watts = float(r["weighted_average_watts"]) if r.get("weighted_average_watts") is not None else None
        calories = float(r["calories"]) if r.get("calories") is not None else None
        suffer = int(r["suffer_score"]) if r.get("suffer_score") is not None else None
        raw_speed = float(r.get("average_speed") or 0.0)
        speed_kmh = round(raw_speed * 3.6, 2) if raw_speed > 0 else (round(dist_m / mov_s * 3.6, 2) if mov_s > 0 else 0.0)

        start_dt = r.get("start_date")
        start_str = start_dt.isoformat() if hasattr(start_dt, "isoformat") else str(start_dt or "")

        act_data = {
            "activity_id": act_id,
            "name": str(r.get("name") or "Unnamed Activity"),
            "start_date": start_str,
            "sport": str(r.get("sport_type") or r.get("sport") or r.get("type") or "Unknown"),
            "distance_km": round(dist_m / 1000.0, 2),
            "moving_time_s": mov_s,
            "elevation_gain_m": round(elev_m, 1),
            "average_speed_kmh": speed_kmh,
            "average_watts": watts,
            "max_watts": max_w,
            "weighted_average_watts": w_watts,
            "average_cadence": avg_cadence,
            "average_heartrate": avg_hr,
            "max_heartrate": max_hr,
            "calories": calories,
            "suffer_score": suffer,
        }
        if r.get("gear_id"):
            act_data["gear_id"] = str(r["gear_id"])
        if r.get("trophies"):
            act_data["trophies"] = r["trophies"]
        if r.get("pr_count"):
            act_data["pr_count"] = int(r["pr_count"])
        activities.append(act_data)

    payload = {
        "activities": activities,
        "pagination": {
            "next_cursor": next_cursor,
            "has_more": has_more,
            "count": len(activities),
        },
    }
    return create_envelope(payload, source="local_db")


def kinetiqo_get_activity_details(repo: Any, activity_id: str) -> Dict[str, Any]:
    """Retrieve comprehensive metadata and sensor coverage for a single activity."""
    act_str = str(activity_id).strip()
    try:
        activities = repo.get_activities_by_ids([act_str])
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Error fetching activity {activity_id}: {e}")

    if not activities:
        return create_error_envelope(ERROR_NOT_FOUND, f"Activity {activity_id} not found in local database")

    act = activities[0]
    dist_m = float(act.get("distance") or 0.0)
    mov_s = int(act.get("moving_time") or 0)
    elap_s = int(act.get("elapsed_time") or mov_s)
    elev_m = float(act.get("total_elevation_gain") or act.get("elevation_gain") or 0.0)

    # Sensor coverage check
    coverage = {}
    try:
        int_id = int(act_str)
        coverage = repo.get_stream_coverage(int_id)
    except Exception:
        pass

    start_dt = act.get("start_date")
    start_str = start_dt.isoformat() if hasattr(start_dt, "isoformat") else str(start_dt or "")

    data = {
        "activity_id": act_str,
        "name": act.get("name") or "Unnamed Activity",
        "sport": act.get("sport_type") or act.get("type") or "Unknown",
        "start_date": start_str,
        "distance_km": round(dist_m / 1000.0, 2),
        "moving_time_s": mov_s,
        "elapsed_time_s": elap_s,
        "elevation_gain_m": round(elev_m, 1),
        "average_speed_kmh": round((dist_m / mov_s * 3.6), 2) if mov_s > 0 else 0.0,
        "max_speed_kmh": round(float(act.get("max_speed") or 0.0) * 3.6, 2),
        "average_watts": float(act["average_watts"]) if act.get("average_watts") is not None else None,
        "max_watts": float(act["max_watts"]) if act.get("max_watts") is not None else None,
        "average_heartrate_bpm": float(act["average_heartrate"]) if act.get("average_heartrate") is not None else None,
        "max_heartrate_bpm": float(act["max_heartrate"]) if act.get("max_heartrate") is not None else None,
        "average_cadence_rpm": float(act["average_cadence"]) if act.get("average_cadence") is not None else None,
        "calories_kcal": float(act["calories"]) if act.get("calories") is not None else None,
        "suffer_score": int(act["suffer_score"]) if act.get("suffer_score") is not None else None,
        "pr_count": int(act.get("pr_count") or 0),
        "koms_count": int(act.get("koms_count") or 0),
        "sensor_coverage": coverage,
    }
    return create_envelope(data, source="local_db")


def kinetiqo_get_activity_totals(
    repo: Any,
    sport_types: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date_preset: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute aggregated distance, elevation, moving time, and count."""
    norm_sports = normalize_sport_types(sport_types)
    resolved_start, resolved_end = resolve_date_range(start_date=start_date, end_date=end_date, preset=date_preset)
    try:
        totals = repo.get_activities_totals(types=norm_sports, start_date=resolved_start, end_date=resolved_end)
        count = repo.count_activities(types=norm_sports, start_date=resolved_start, end_date=resolved_end)
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed calculating activity totals: {e}")

    dist_m = float(totals.get("total_distance") or totals.get("distance") or 0.0)
    elev_m = float(totals.get("total_elevation") or totals.get("elevation") or 0.0)
    mov_s = float(totals.get("total_moving_time") or totals.get("moving_time") or 0.0)

    data = {
        "count": int(count),
        "distance_km": round(dist_m / 1000.0, 2),
        "elevation_m": round(elev_m, 1),
        "moving_time_hours": round(mov_s / 3600.0, 2),
        "moving_time_s": int(mov_s),
        "average_distance_km": round((dist_m / count) / 1000.0, 2) if count > 0 else 0.0,
        "average_elevation_m": round(elev_m / count, 1) if count > 0 else 0.0,
    }
    return create_envelope(data, source="local_db")


def kinetiqo_compare_activities(repo: Any, activity_ids: List[str]) -> Dict[str, Any]:
    """Compare 2 to 5 activities side-by-side."""
    if not activity_ids or not (2 <= len(activity_ids) <= 5):
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            f"Must specify between 2 and 5 activity IDs to compare; received {len(activity_ids) if activity_ids else 0}",
        )

    try:
        activities = repo.get_activities_by_ids([str(aid) for aid in activity_ids])
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed fetching activities for comparison: {e}")

    found_map = {str(a.get("activity_id") or a.get("id")): a for a in activities}
    missing = [aid for aid in activity_ids if str(aid) not in found_map]
    warnings = [f"Activity {aid} not found in database" for aid in missing] if missing else []

    compared = []
    for aid in activity_ids:
        act = found_map.get(str(aid))
        if not act:
            continue
        dist_m = float(act.get("distance") or 0.0)
        mov_s = int(act.get("moving_time") or 0)
        elev_m = float(act.get("total_elevation_gain") or act.get("elevation_gain") or 0.0)
        compared.append({
            "activity_id": str(aid),
            "name": act.get("name") or "Unnamed",
            "sport": act.get("sport_type") or act.get("type") or "Unknown",
            "distance_km": round(dist_m / 1000.0, 2),
            "moving_time_s": mov_s,
            "elevation_gain_m": round(elev_m, 1),
            "average_speed_kmh": round((dist_m / mov_s * 3.6), 2) if mov_s > 0 else 0.0,
            "average_watts": float(act["average_watts"]) if act.get("average_watts") is not None else None,
            "average_heartrate_bpm": float(act["average_heartrate"]) if act.get("average_heartrate") is not None else None,
            "suffer_score": int(act["suffer_score"]) if act.get("suffer_score") is not None else None,
        })

    return create_envelope({"compared_activities": compared}, source="local_db", warnings=warnings)


def kinetiqo_compare_periods(
    repo: Any,
    period_a: Dict[str, str],
    period_b: Dict[str, str],
    sport_types: Optional[List[str]] = None,
    align: str = "elapsed_days",
) -> Dict[str, Any]:
    """Compare two fair training periods with equal elapsed-day alignment."""
    start_a, end_a = resolve_date_range(start_date=period_a.get("start_date"), end_date=period_a.get("end_date"), preset=period_a.get("preset"))
    start_b, end_b = resolve_date_range(start_date=period_b.get("start_date"), end_date=period_b.get("end_date"), preset=period_b.get("preset"))

    if not (start_a and end_a and start_b and end_b):
        return create_error_envelope(
            ERROR_INVALID_ARGUMENT,
            "Both period_a and period_b must provide valid start and end dates or presets",
        )

    norm_sports = normalize_sport_types(sport_types)
    try:
        totals_a = repo.get_activities_totals(types=norm_sports, start_date=start_a, end_date=end_a)
        count_a = repo.count_activities(types=norm_sports, start_date=start_a, end_date=end_a)
        totals_b = repo.get_activities_totals(types=norm_sports, start_date=start_b, end_date=end_b)
        count_b = repo.count_activities(types=norm_sports, start_date=start_b, end_date=end_b)
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed querying period totals: {e}")

    dist_a_m = float(totals_a.get("total_distance") or totals_a.get("distance") or 0.0)
    dist_b_m = float(totals_b.get("total_distance") or totals_b.get("distance") or 0.0)
    elev_a_m = round(float(totals_a.get("total_elevation") or totals_a.get("elevation") or 0.0), 1)
    elev_b_m = round(float(totals_b.get("total_elevation") or totals_b.get("elevation") or 0.0), 1)
    mov_a_s = int(totals_a.get("total_moving_time") or totals_a.get("moving_time") or 0)
    mov_b_s = int(totals_b.get("total_moving_time") or totals_b.get("moving_time") or 0)

    dist_a_km = round(dist_a_m / 1000.0, 2)
    dist_b_km = round(dist_b_m / 1000.0, 2)

    dist_diff = round(dist_b_km - dist_a_km, 2)
    dist_pct = round((dist_diff / dist_a_km) * 100.0, 1) if dist_a_km > 0 else None

    elev_diff = round(elev_b_m - elev_a_m, 1)
    elev_pct = round((elev_diff / elev_a_m) * 100.0, 1) if elev_a_m > 0 else None

    count_diff = count_b - count_a
    count_pct = round((count_diff / count_a) * 100.0, 1) if count_a > 0 else None

    data = {
        "alignment_mode": align,
        "period_a": {
            "range": [start_a, end_a],
            "count": count_a,
            "distance_km": dist_a_km,
            "elevation_m": elev_a_m,
            "moving_time_s": mov_a_s,
        },
        "period_b": {
            "range": [start_b, end_b],
            "count": count_b,
            "distance_km": dist_b_km,
            "elevation_m": elev_b_m,
            "moving_time_s": mov_b_s,
        },
        "deltas": {
            "distance_km": dist_diff,
            "distance_pct": dist_pct,
            "elevation_m": elev_diff,
            "elevation_pct": elev_pct,
            "count": count_diff,
            "count_pct": count_pct,
        },
    }
    return create_envelope(data, source="calculated")


def kinetiqo_find_similar_routes(
    repo: Any,
    activity_id: str,
    sport_types: Optional[List[str]] = None,
    max_candidates: int = 10,
) -> Dict[str, Any]:
    """Find past activities matching a source activity's route via GPS start/end proximity."""
    act_str = str(activity_id).strip()
    try:
        source_acts = repo.get_activities_by_ids([act_str])
        if not source_acts:
            return create_error_envelope(ERROR_NOT_FOUND, f"Source activity {activity_id} not found")
        source = source_acts[0]

        # Retrieve GPS coordinates for source
        source_streams = repo.get_streams_coords_for_activities([act_str])
        coords = source_streams.get(act_str, [])
        if len(coords) < 10:
            return create_envelope(
                {"candidates": [], "message": "Source activity has insufficient GPS points for route matching"},
                source="calculated",
                warnings=["Insufficient GPS coordinates in source activity"],
            )

        src_dist = float(source.get("distance") or 0.0)
        src_start = coords[0]
        src_end = coords[-1]

        # Search candidates with similar distance (+/- 20%)
        min_d = src_dist * 0.80
        max_d = src_dist * 1.20
        src_aid = source.get("athlete_id")
        cands, _, _ = repo.search_activities(
            athlete_id=int(src_aid) if src_aid is not None else None,
            filters={"min_distance": min_d, "max_distance": max_d, "sport_types": norm_sports},
            limit=max_candidates + 5,
        )

        cand_ids = [str(c.get("activity_id") or c.get("id")) for c in cands if str(c.get("activity_id") or c.get("id")) != act_str]
        cand_streams = repo.get_streams_coords_for_activities(cand_ids)

        matches = []
        for c in cands:
            cid = str(c.get("activity_id") or c.get("id"))
            if cid == act_str or cid not in cand_streams:
                continue
            c_coords = cand_streams[cid]
            if len(c_coords) < 10:
                continue

            # Compare endpoints: same direction vs reverse
            start_dist = _haversine_dist(src_start, c_coords[0])
            end_dist = _haversine_dist(src_end, c_coords[-1])
            rev_start_dist = _haversine_dist(src_start, c_coords[-1])
            rev_end_dist = _haversine_dist(src_end, c_coords[0])

            direction = "same"
            endpoint_err = (start_dist + end_dist) / 2.0
            if (rev_start_dist + rev_end_dist) < (start_dist + end_dist):
                direction = "reverse"
                endpoint_err = (rev_start_dist + rev_end_dist) / 2.0

            # Score based on distance difference and endpoint proximity
            dist_ratio = min(src_dist, float(c.get("distance") or 0.0)) / max(src_dist, float(c.get("distance") or 1.0))
            proximity_score = max(0.0, 1.0 - (endpoint_err / 2000.0))  # within 2 km
            similarity = round(0.5 * dist_ratio + 0.5 * proximity_score, 2)

            if similarity >= 0.65:
                matches.append({
                    "activity_id": cid,
                    "name": c.get("name") or "Unnamed",
                    "start_date": str(c.get("start_date") or ""),
                    "distance_km": round(float(c.get("distance") or 0.0) / 1000.0, 2),
                    "similarity_score": similarity,
                    "direction": direction,
                })

        matches.sort(key=lambda x: x["similarity_score"], reverse=True)
        return create_envelope({"candidates": matches[:max_candidates]}, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Route similarity search failed: {e}")


def kinetiqo_compare_route_attempts(
    repo: Any,
    source_activity_id: str,
    target_activity_id: str,
) -> Dict[str, Any]:
    """Compare performance across attempts on the same route."""
    try:
        acts = repo.get_activities_by_ids([str(source_activity_id), str(target_activity_id)])
        if len(acts) < 2:
            return create_error_envelope(ERROR_NOT_FOUND, "One or both activities could not be found")

        act_map = {str(a.get("activity_id") or a.get("id")): a for a in acts}
        src = act_map[str(source_activity_id)]
        tgt = act_map[str(target_activity_id)]

        src_mov = int(src.get("moving_time") or 0)
        tgt_mov = int(tgt.get("moving_time") or 0)
        time_diff = tgt_mov - src_mov

        src_w = float(src.get("average_watts") or 0.0)
        tgt_w = float(tgt.get("average_watts") or 0.0)

        src_hr = float(src.get("average_heartrate") or 0.0)
        tgt_hr = float(tgt.get("average_heartrate") or 0.0)

        data = {
            "source_activity": {
                "activity_id": str(source_activity_id),
                "name": src.get("name"),
                "date": str(src.get("start_date")),
                "moving_time_s": src_mov,
                "average_watts": src_w if src_w > 0 else None,
                "average_heartrate": src_hr if src_hr > 0 else None,
            },
            "target_activity": {
                "activity_id": str(target_activity_id),
                "name": tgt.get("name"),
                "date": str(tgt.get("start_date")),
                "moving_time_s": tgt_mov,
                "average_watts": tgt_w if tgt_w > 0 else None,
                "average_heartrate": tgt_hr if tgt_hr > 0 else None,
            },
            "comparison": {
                "time_delta_s": time_diff,
                "power_delta_w": round(tgt_w - src_w, 1) if (tgt_w > 0 and src_w > 0) else None,
                "heartrate_delta_bpm": round(tgt_hr - src_hr, 1) if (tgt_hr > 0 and src_hr > 0) else None,
            },
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed comparing route attempts: {e}")


def _haversine_dist(p1: List[float], p2: List[float]) -> float:
    """Compute distance in meters between two [lat, lng] coordinates."""
    r = 6371000.0  # Earth radius in meters
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c
