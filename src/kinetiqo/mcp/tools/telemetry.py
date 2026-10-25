"""Group B: High-Resolution Telemetry & Power Analytics Tools."""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
import math

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
)
from kinetiqo.mcp.utils import (
    downsample_stream_window,
    detect_stream_gaps,
    extract_activity_summaries,
    get_best_powers_for_durations,
    normalize_sport_types,
    CYCLING_SPORT_TYPES,
)
from kinetiqo.analytics.power import (
    calculate_normalized_power,
    calculate_intensity_factor,
    calculate_tss,
    calculate_mmp_curve,
)
from kinetiqo.analytics.pacing import calculate_pacing_splits


def kinetiqo_get_activity_streams(
    repo: Any,
    activity_id: str,
    stream_types: Optional[List[str]] = None,
    resolution: str = "auto",
) -> Dict[str, Any]:
    """Retrieve raw or downsampled telemetry time-series for an activity."""
    try:
        int_id = int(str(activity_id).strip())
    except ValueError:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Invalid activity ID format: {activity_id}")

    columns = stream_types or ["time", "watts", "heartrate", "cadence", "altitude"]
    max_raw = 20000 if (resolution or "").lower() == "high" else 5000

    try:
        raw_rows = repo.get_activity_stream_window(
            activity_id=int_id,
            columns=columns,
            start_ts=None,
            end_ts=None,
            max_rows=max_raw,
        )
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving stream window: {e}")

    if not raw_rows:
        return create_envelope(
            {"samples": [], "count": 0, "resolution": resolution},
            source="local_db",
            data_status="unavailable",
            warnings=[f"No stream telemetry recorded for activity {activity_id}"],
        )

    downsampled, method = downsample_stream_window(raw_rows, resolution=resolution)
    gaps = detect_stream_gaps(downsampled)

    payload = {
        "activity_id": str(activity_id),
        "resolution": resolution,
        "downsampling_method": method,
        "original_samples_count": len(raw_rows),
        "returned_samples_count": len(downsampled),
        "gaps_detected": gaps["total_gaps"],
        "max_gap_s": gaps["max_gap_seconds"],
        "samples": downsampled,
    }
    return create_envelope(payload, source="local_db")


def kinetiqo_get_data_coverage(repo: Any, activity_id: str) -> Dict[str, Any]:
    """Fast pre-flight check returning sensor presence, sample counts, timestamp ranges, and gaps."""
    try:
        int_id = int(str(activity_id).strip())
    except ValueError:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Invalid activity ID format: {activity_id}")

    try:
        coverage = repo.get_stream_coverage(int_id)
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed querying stream coverage: {e}")

    has_any = any(v.get("status") == "present" for v in coverage.values())
    return create_envelope(
        {"activity_id": str(activity_id), "channels": coverage},
        source="local_db",
        data_status="complete" if has_any else "unavailable",
        warnings=[] if has_any else [f"No sensor data recorded in streams for activity {activity_id}"],
    )


def kinetiqo_calculate_power_curve(
    repo: Any,
    activity_id: Optional[str] = None,
    days: Optional[int] = None,
    durations: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Compute the Mean Maximal Power (MMP) curve for an activity or rolling period."""
    req_durations = durations or [5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600]

    if activity_id:
        try:
            int_id = int(str(activity_id).strip())
            rows = repo.get_activity_stream_window(int_id, ["ts", "watts"], None, None, 20000)
        except Exception as e:
            return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed fetching activity streams: {e}")

        if not rows:
            return create_error_envelope(ERROR_NOT_FOUND, f"No power streams found for activity {activity_id}")

        timestamps = [int(r.get("ts") or 0) for r in rows]
        watts = [float(r.get("watts") or 0.0) for r in rows]
        mmp = calculate_mmp_curve(timestamps, watts, req_durations)

        formatted_mmp = {
            str(d): {
                "duration_s": d,
                "watts": round(val, 1) if val > 0 else None,
            }
            for d, val in mmp.items()
        }

        return create_envelope(
            {"activity_id": str(activity_id), "mmp_curve": formatted_mmp},
            source="calculated",
        )

    # Cross-activity peak powers over rolling window
    lookback_days = days or 90
    try:
        profile = repo.get_profile() or {}
        weight_kg = float(profile.get("weight") or 0.0)
    except Exception:
        weight_kg = 0.0

    since_date = (date.today() - timedelta(days=lookback_days)).isoformat() if lookback_days else None
    try:
        raw_acts = repo.get_activity_ids_by_types(types=list(CYCLING_SPORT_TYPES), since_date=since_date, watts_only=True) or []
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed fetching activity IDs: {e}")

    summaries = extract_activity_summaries(raw_acts)
    str_ids = [s["id"] for s in summaries]

    if not str_ids:
        return create_envelope({"mmp_curve": {str(d): None for d in req_durations}}, source="calculated", warnings=["No power activities found"])

    # Aggregate best power per activity
    best_curve: Dict[str, Any] = {}
    try:
        multi_bests = get_best_powers_for_durations(repo, str_ids[:100], req_durations)
        for d in req_durations:
            dur_bests = multi_bests.get(d, {})
            best_w = 0.0
            best_act = None
            for aid, val in dur_bests.items():
                if val > best_w:
                    best_w = val
                    best_act = aid
            best_curve[str(d)] = {
                "duration_s": d,
                "watts": round(best_w, 1) if best_w > 0 else None,
                "w_per_kg": round(best_w / weight_kg, 2) if (best_w > 0 and weight_kg > 0) else None,
                "source_activity_id": best_act,
            }
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Error calculating power curve: {e}")

    return create_envelope({"days_window": lookback_days, "mmp_curve": best_curve}, source="calculated")


def kinetiqo_get_personal_records(
    repo: Any,
    athlete_id: int,
    durations: Optional[List[int]] = None,
    sport_types: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve verified all-time and period personal power records for benchmark durations."""
    benchmark_durations = durations or [5, 60, 300, 1200, 3600]
    types = normalize_sport_types(sport_types) or ["Ride", "VirtualRide", "GravelRide"]

    try:
        try:
            profile = repo.get_profile() or {}
        except TypeError:
            profile = repo.get_profile(athlete_id) or {}
        weight_kg = float(profile.get("weight") or 0.0)
    except Exception:
        weight_kg = 0.0

    try:
        raw_acts = repo.get_activity_ids_by_types(types=types, since_date=start_date, watts_only=True) or []
        summaries = extract_activity_summaries(raw_acts)
        if start_date or end_date:
            filtered = []
            for s in summaries:
                sdate = str(s.get("start_date") or "")
                if start_date and sdate and sdate[:10] < str(start_date)[:10]:
                    continue
                if end_date and sdate and sdate[:10] > str(end_date)[:10]:
                    continue
                filtered.append(s)
            summaries = filtered

        str_ids = [s["id"] for s in summaries]
        if not str_ids:
            return create_envelope(
                {"records": {str(d): None for d in benchmark_durations}},
                source="calculated",
                warnings=["No power activities matched requested criteria"],
            )

        multi_bests = get_best_powers_for_durations(repo, str_ids[:150], benchmark_durations)

        act_details = {s["id"]: s for s in summaries if s.get("name")}
        winner_aids = set()
        for d in benchmark_durations:
            for aid, val in multi_bests.get(d, {}).items():
                if val > 0:
                    winner_aids.add(aid)
        missing = [aid for aid in winner_aids if aid not in act_details]
        if missing and hasattr(repo, "get_activities_by_ids"):
            try:
                for a in repo.get_activities_by_ids(missing):
                    aid_key = str(a.get("id") or a.get("activity_id"))
                    act_details[aid_key] = {
                        "id": aid_key,
                        "name": a.get("name"),
                        "start_date": str(a.get("start_date") or ""),
                    }
            except Exception:
                pass

        records = {}
        for d in benchmark_durations:
            dur_bests = multi_bests.get(d, {})
            best_w = 0.0
            best_aid = None
            for aid, val in dur_bests.items():
                if val > best_w:
                    best_w = val
                    best_aid = str(aid)

            if best_w > 0 and best_aid and best_aid in act_details:
                act = act_details[best_aid]
                records[str(d)] = {
                    "duration_s": d,
                    "watts": round(best_w, 1),
                    "w_per_kg": round(best_w / weight_kg, 2) if weight_kg > 0 else None,
                    "activity_id": best_aid,
                    "activity_name": act.get("name"),
                    "start_date": str(act.get("start_date") or ""),
                }
            else:
                records[str(d)] = None

        return create_envelope({"records": records}, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed calculating personal records: {e}")


def kinetiqo_analyze_workout_structure(
    repo: Any,
    activity_id: str,
    athlete_ftp: Optional[float] = None,
) -> Dict[str, Any]:
    """Analyze structured workout metrics: NP, IF, TSS, sustained blocks, and sprint surges."""
    try:
        int_id = int(str(activity_id).strip())
        acts = repo.get_activities_by_ids([str(activity_id)])
        if not acts:
            return create_error_envelope(ERROR_NOT_FOUND, f"Activity {activity_id} not found")
        act = acts[0]

        profile = repo.get_profile() or {}
        ftp = athlete_ftp or float(profile.get("ftp") or 0.0)

        rows = repo.get_activity_stream_window(int_id, ["ts", "watts"], None, None, 20000)
        if not rows:
            return create_envelope(
                {"activity_id": str(activity_id), "message": "No power stream available"},
                source="calculated",
                warnings=["Activity lacks power telemetry stream"],
            )

        watts_stream = [float(r.get("watts") or 0.0) for r in rows]
        mov_s = int(act.get("moving_time") or len(watts_stream))

        np_w = calculate_normalized_power(watts_stream)
        if_val = calculate_intensity_factor(np_w, ftp) if (np_w and ftp > 0) else None
        tss_val = calculate_tss(mov_s, np_w, if_val, ftp) if (np_w and if_val and ftp > 0) else None

        # Surge detection (peaks >= 500W for >= 3s)
        surges = []
        surge_start = None
        for i, w in enumerate(watts_stream):
            if w >= 500:
                if surge_start is None:
                    surge_start = i
            else:
                if surge_start is not None:
                    dur = i - surge_start
                    if dur >= 3:
                        peak = max(watts_stream[surge_start:i])
                        surges.append({"start_s": surge_start, "duration_s": dur, "peak_watts": round(peak, 1)})
                    surge_start = None

        max_w = max(watts_stream) if watts_stream else 0.0
        peak_idx = watts_stream.index(max_w) if max_w > 0 else None

        # Coggan 7-Zone power distribution & VO2max workout structure analysis
        zone_dist = {}
        vo2max_analysis = None
        if ftp > 0:
            z_counts = {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0, "Z6": 0, "Z7": 0}
            z_bounds = [
                ("Z1", 0.0, 0.55 * ftp),
                ("Z2", 0.55 * ftp, 0.75 * ftp),
                ("Z3", 0.75 * ftp, 0.90 * ftp),
                ("Z4", 0.90 * ftp, 1.05 * ftp),
                ("Z5", 1.05 * ftp, 1.20 * ftp),
                ("Z6", 1.20 * ftp, 1.50 * ftp),
                ("Z7", 1.50 * ftp, float("inf")),
            ]
            for w in watts_stream:
                for z_name, z_low, z_high in z_bounds:
                    if z_low <= w < z_high:
                        z_counts[z_name] += 1
                        break

            tot_s = max(1, len(watts_stream))
            zone_dist = {
                k: {
                    "time_s": cnt,
                    "time_min": round(cnt / 60.0, 1),
                    "pct": round(cnt / tot_s * 100.0, 1),
                }
                for k, cnt in z_counts.items()
            }

            # Sustained Zone 5 intervals (>= 90s contiguous @ >= 106% FTP, allowing <= 10s dips)
            z5_intervals = []
            z5_low = 1.05 * ftp
            in_z5 = False
            int_start = 0
            dip_count = 0
            for idx, w in enumerate(watts_stream):
                if w >= z5_low:
                    if not in_z5:
                        in_z5 = True
                        int_start = idx
                    dip_count = 0
                else:
                    if in_z5:
                        dip_count += 1
                        if dip_count > 10:
                            dur = (idx - dip_count) - int_start
                            if dur >= 90:
                                chunk = watts_stream[int_start:idx - dip_count]
                                avg_int_w = round(sum(chunk) / max(1, len(chunk)), 1)
                                z5_intervals.append({
                                    "start_s": int_start,
                                    "start_min": round(int_start / 60.0, 1),
                                    "duration_s": dur,
                                    "duration_min": round(dur / 60.0, 1),
                                    "average_watts": avg_int_w,
                                    "pct_ftp": round(avg_int_w / ftp * 100.0, 1),
                                })
                            in_z5 = False
                            dip_count = 0
            if in_z5:
                dur = len(watts_stream) - int_start
                if dur >= 90:
                    chunk = watts_stream[int_start:]
                    avg_int_w = round(sum(chunk) / max(1, len(chunk)), 1)
                    z5_intervals.append({
                        "start_s": int_start,
                        "start_min": round(int_start / 60.0, 1),
                        "duration_s": dur,
                        "duration_min": round(dur / 60.0, 1),
                        "average_watts": avg_int_w,
                        "pct_ftp": round(avg_int_w / ftp * 100.0, 1),
                    })

            z5_time_s = z_counts["Z5"]
            z5_time_min = round(z5_time_s / 60.0, 1)
            is_genuine = (z5_time_min >= 8.0) or (len(z5_intervals) >= 3)

            if is_genuine:
                reason = (
                    f"Genuine VO2max workout: accumulated {z5_time_min} minutes in Zone 5 (106-120% FTP) "
                    f"with {len(z5_intervals)} sustained interval repeats."
                )
            elif z5_time_min >= 3.0:
                reason = (
                    f"Borderline / Mixed effort: {z5_time_min} minutes in Zone 5, but below the standard "
                    f"effective volume (>=8-10 min) for dedicated VO2max ceiling expansion."
                )
            else:
                reason = (
                    f"Not a VO2max workout: only {z5_time_min} minutes in Zone 5. "
                    f"Efforts were predominantly endurance, tempo, threshold, or brief sprint bursts."
                )

            vo2max_analysis = {
                "vo2max_time_s": z5_time_s,
                "vo2max_time_min": z5_time_min,
                "vo2max_pct_time": round(z5_time_s / tot_s * 100.0, 1),
                "sustained_z5_intervals_count": len(z5_intervals),
                "sustained_z5_intervals": z5_intervals[:10],
                "is_genuine_vo2max_workout": is_genuine,
                "classification_reason": reason,
            }

        data = {
            "activity_id": str(activity_id),
            "name": act.get("name"),
            "moving_time_s": mov_s,
            "average_watts": float(act.get("average_watts") or 0.0),
            "max_watts": round(max_w, 1) if max_w > 0 else None,
            "time_to_max_watts_s": peak_idx,
            "time_to_max_watts_min": round(peak_idx / 60.0, 1) if peak_idx is not None else None,
            "normalized_power_w": round(np_w, 1) if np_w else None,
            "ftp_used": ftp if ftp > 0 else None,
            "intensity_factor": round(if_val, 3) if if_val else None,
            "training_stress_score": round(tss_val, 1) if tss_val else None,
            "power_zones_distribution": zone_dist if zone_dist else None,
            "vo2max_analysis": vo2max_analysis,
            "sprint_surges_count": len(surges),
            "sprint_surges": surges[:10],
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Workout structure analysis failed: {e}")


def kinetiqo_analyze_pacing(
    repo: Any,
    activity_id: str,
    split_basis: str = "moving_time",
    num_splits: int = 2,
) -> Dict[str, Any]:
    """Analyze session pacing splits, stops, and aerobic decoupling."""
    try:
        int_id = int(str(activity_id).strip())
        rows = repo.get_activity_stream_window(int_id, ["ts", "distance", "watts", "heartrate", "altitude"], None, None, 20000)
        if not rows or len(rows) < 100:
            return create_envelope(
                {"activity_id": str(activity_id), "message": "Insufficient stream telemetry for pacing analysis"},
                source="calculated",
                warnings=["Activity requires at least 100 stream samples for pacing analysis"],
            )

        splits_data = calculate_pacing_splits(rows, split_basis=split_basis, num_splits=num_splits)
        return create_envelope({"activity_id": str(activity_id), "pacing": splits_data}, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed analyzing pacing: {e}")


def kinetiqo_get_route_highlights(
    repo: Any,
    activity_id: str,
    hide_start_end_km: Optional[float] = None,
) -> Dict[str, Any]:
    """Identify top climbs and peak wattage segments with optional privacy redaction."""
    try:
        int_id = int(str(activity_id).strip())
        rows = repo.get_activity_stream_window(int_id, ["ts", "distance", "altitude", "watts", "lat", "lng"], None, None, 20000)
        if not rows:
            return create_envelope(
                {"climbs": [], "peak_efforts": []},
                source="calculated",
                warnings=["Activity lacks stream telemetry"],
            )

        # GPS start/end privacy redaction
        if hide_start_end_km and hide_start_end_km > 0:
            clip_m = hide_start_end_km * 1000.0
            max_d = float(rows[-1].get("distance") or 0.0)
            rows = [r for r in rows if clip_m <= float(r.get("distance") or 0.0) <= (max_d - clip_m)]

        # Find climbs with elevation gain >= 30m
        climbs = []
        climb_start = None
        for i in range(1, len(rows)):
            alt_prev = float(rows[i - 1].get("altitude") or 0.0)
            alt_curr = float(rows[i].get("altitude") or 0.0)
            if alt_curr > alt_prev:
                if climb_start is None:
                    climb_start = i - 1
            else:
                if climb_start is not None:
                    gain = alt_prev - float(rows[climb_start].get("altitude") or 0.0)
                    dist = float(rows[i - 1].get("distance") or 0.0) - float(rows[climb_start].get("distance") or 0.0)
                    if gain >= 30.0 and dist >= 200.0:
                        climbs.append({
                            "start_km": round(float(rows[climb_start].get("distance") or 0.0) / 1000.0, 2),
                            "elevation_gain_m": round(gain, 1),
                            "distance_m": round(dist, 1),
                            "average_grade_pct": round((gain / dist) * 100.0, 1),
                        })
                    climb_start = None

        climbs.sort(key=lambda c: c["elevation_gain_m"], reverse=True)

        return create_envelope(
            {
                "activity_id": str(activity_id),
                "privacy_redacted_km": hide_start_end_km,
                "climbs": climbs[:5],
            },
            source="calculated",
        )
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed getting route highlights: {e}")
