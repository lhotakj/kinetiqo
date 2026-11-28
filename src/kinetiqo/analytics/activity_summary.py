"""Activity analytics summaries for Coggan power zones, HR zones, climbing, and MMP."""

from typing import Any, Dict, List, Optional, Sequence
import math

from kinetiqo.analytics.power import calculate_mmp_curve
from kinetiqo.analytics.zones import calculate_coggan_zones, calculate_hr_zones


def calculate_climb_breakdown(
    distance_stream: Sequence[Optional[float]],
    altitude_stream: Sequence[Optional[float]],
    grade_stream: Sequence[Optional[float]],
) -> Dict[str, Any]:
    """Calculate climbing, flat, and descent distance, duration, and steepest grade."""
    climb_s = 0
    climb_m = 0.0
    flat_s = 0
    flat_m = 0.0
    desc_s = 0
    desc_m = 0.0
    max_grade = 0.0
    min_grade = 0.0

    n = min(len(distance_stream), len(altitude_stream))
    if n < 2:
        return {
            "climb_km": 0.0,
            "climb_seconds": 0,
            "flat_km": 0.0,
            "flat_seconds": 0,
            "desc_km": 0.0,
            "desc_seconds": 0,
            "max_grade": 0.0,
            "min_grade": 0.0,
        }

    for i in range(1, n):
        d_prev = distance_stream[i - 1] or 0.0
        d_curr = distance_stream[i] or 0.0
        delta_dist = max(0.0, d_curr - d_prev)

        grade = grade_stream[i] if i < len(grade_stream) and grade_stream[i] is not None else None
        if grade is None and delta_dist > 0:
            alt_prev = altitude_stream[i - 1] or 0.0
            alt_curr = altitude_stream[i] or 0.0
            grade = ((alt_curr - alt_prev) / delta_dist) * 100.0

        if grade is not None:
            max_grade = max(max_grade, float(grade))
            min_grade = min(min_grade, float(grade))
            if grade > 1.5:
                climb_s += 1
                climb_m += delta_dist
            elif grade < -1.5:
                desc_s += 1
                desc_m += delta_dist
            else:
                flat_s += 1
                flat_m += delta_dist

    return {
        "climb_km": round(climb_m / 1000.0, 2),
        "climb_seconds": climb_s,
        "flat_km": round(flat_m / 1000.0, 2),
        "flat_seconds": flat_s,
        "desc_km": round(desc_m / 1000.0, 2),
        "desc_seconds": desc_s,
        "max_grade": round(max_grade, 1),
        "min_grade": round(min_grade, 1),
    }


def calculate_mmp_summary(
    timestamps: Sequence[int],
    watts_stream: Sequence[Optional[float]],
    ftp: Optional[float],
) -> List[Dict[str, Any]]:
    """Calculate MMP for standard durations: 5s, 30s, 1m, 5m, 20m, 60m with % FTP."""
    durations = (5, 30, 60, 300, 1200, 3600)
    labels = {
        5: "5s",
        30: "30s",
        60: "1m",
        300: "5m",
        1200: "20m",
        3600: "1h",
    }
    raw_mmp = calculate_mmp_curve(timestamps, watts_stream, durations=durations)

    result = []
    for d in durations:
        w = round(raw_mmp.get(d, 0.0))
        pct_ftp = round((w / float(ftp)) * 100.0) if ftp and ftp > 0 and w > 0 else None
        result.append({
            "duration": d,
            "label": labels[d],
            "watts": w,
            "pct_ftp": pct_ftp,
        })
    return result


def build_activity_analytics(
    stream_rows: List[Dict[str, Any]],
    ftp: Optional[float] = None,
    max_hr: Optional[int] = None,
) -> Dict[str, Any]:
    """Assemble all analytical aggregates from raw or downsampled stream rows."""
    if not stream_rows:
        return {
            "coggan_zones": calculate_coggan_zones([], ftp),
            "hr_zones": calculate_hr_zones([], max_hr),
            "mmp_table": calculate_mmp_summary([], [], ftp),
            "climb_stats": calculate_climb_breakdown([], [], []),
        }

    # Extract streams
    ts_list: List[int] = []
    for idx, r in enumerate(stream_rows):
        ts_val = r.get("ts")
        if isinstance(ts_val, (int, float)):
            ts_list.append(int(ts_val))
        else:
            ts_list.append(idx)

    watts = [r.get("watts") for r in stream_rows]
    hrs = [r.get("heartrate") for r in stream_rows]
    distances = [r.get("distance") for r in stream_rows]
    altitudes = [r.get("altitude") for r in stream_rows]
    grades = [r.get("grade_smooth") for r in stream_rows]

    return {
        "coggan_zones": calculate_coggan_zones(watts, ftp),
        "hr_zones": calculate_hr_zones(hrs, max_hr),
        "mmp_table": calculate_mmp_summary(ts_list, watts, ftp),
        "climb_stats": calculate_climb_breakdown(distances, altitudes, grades),
    }

