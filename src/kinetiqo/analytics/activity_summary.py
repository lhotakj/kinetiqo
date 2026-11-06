"""Activity analytics summaries for Coggan power zones, HR zones, climbing, and MMP."""

from typing import Any, Dict, List, Optional, Sequence
import math

from kinetiqo.analytics.power import calculate_mmp_curve


def calculate_coggan_zones(
    watts_stream: Sequence[Optional[float]],
    ftp: Optional[float],
) -> List[Dict[str, Any]]:
    """Calculate time and percentage in Coggan 7 power zones.

    Coggan Zones relative to FTP:
      - Z1 Active Recovery: < 55%
      - Z2 Endurance: 55% - 75%
      - Z3 Tempo: 75% - 90%
      - Z4 Lactate Threshold: 90% - 105%
      - Z5 VO2 Max: 105% - 120%
      - Z6 Anaerobic Capacity: 120% - 150%
      - Z7 Neuromuscular Power: > 150%
    """
    zones_def = [
        {"zone": "Z1", "name": "Active Recovery", "min_pct": 0.0, "max_pct": 0.55, "color": "#94a3b8"},
        {"zone": "Z2", "name": "Endurance", "min_pct": 0.55, "max_pct": 0.75, "color": "#38bdf8"},
        {"zone": "Z3", "name": "Tempo", "min_pct": 0.75, "max_pct": 0.90, "color": "#4ade80"},
        {"zone": "Z4", "name": "Threshold", "min_pct": 0.90, "max_pct": 1.05, "color": "#facc15"},
        {"zone": "Z5", "name": "VO2 Max", "min_pct": 1.05, "max_pct": 1.20, "color": "#fb923c"},
        {"zone": "Z6", "name": "Anaerobic", "min_pct": 1.20, "max_pct": 1.50, "color": "#f87171"},
        {"zone": "Z7", "name": "Neuromuscular", "min_pct": 1.50, "max_pct": 999.0, "color": "#c084fc"},
    ]

    valid_samples = [float(w) for w in watts_stream if w is not None]
    total_seconds = len(valid_samples)
    if not ftp or ftp <= 0 or total_seconds == 0:
        return [
            {
                "zone": z["zone"],
                "name": z["name"],
                "color": z["color"],
                "range_w": f"<{round(ftp * 0.55)}W" if ftp and z["zone"] == "Z1" else "—",
                "seconds": 0,
                "percent": 0.0,
            }
            for z in zones_def
        ]

    counts = [0] * len(zones_def)
    for w in valid_samples:
        pct = w / float(ftp)
        assigned = False
        for idx, z in enumerate(zones_def):
            if pct <= z["max_pct"] or idx == len(zones_def) - 1:
                counts[idx] += 1
                assigned = True
                break
        if not assigned:
            counts[-1] += 1

    result = []
    for idx, z in enumerate(zones_def):
        sec = counts[idx]
        pct_time = round((sec / float(total_seconds)) * 100.0, 1) if total_seconds > 0 else 0.0
        
        # Calculate power range string
        if z["zone"] == "Z1":
            range_w = f"< {round(ftp * 0.55)} W"
        elif z["zone"] == "Z7":
            range_w = f"> {round(ftp * 1.50)} W"
        else:
            range_w = f"{round(ftp * z['min_pct'])}–{round(ftp * z['max_pct'])} W"

        result.append({
            "zone": z["zone"],
            "name": z["name"],
            "color": z["color"],
            "range_w": range_w,
            "seconds": sec,
            "percent": pct_time,
        })
    return result


def calculate_hr_zones(
    hr_stream: Sequence[Optional[int]],
    max_hr: Optional[int],
) -> List[Dict[str, Any]]:
    """Calculate time and percentage in 5 standard Heart Rate zones based on max HR.

    Zones:
      - Z1 Recovery (50% - 60% max HR)
      - Z2 Aerobic / Endurance (60% - 70%)
      - Z3 Tempo (70% - 80%)
      - Z4 Threshold (80% - 90%)
      - Z5 Anaerobic / Redline (90% - 100%+)
    """
    zones_def = [
        {"zone": "Z1", "name": "Recovery", "min_pct": 0.50, "max_pct": 0.60, "color": "#94a3b8"},
        {"zone": "Z2", "name": "Aerobic", "min_pct": 0.60, "max_pct": 0.70, "color": "#38bdf8"},
        {"zone": "Z3", "name": "Tempo", "min_pct": 0.70, "max_pct": 0.80, "color": "#4ade80"},
        {"zone": "Z4", "name": "Threshold", "min_pct": 0.80, "max_pct": 0.90, "color": "#facc15"},
        {"zone": "Z5", "name": "Anaerobic", "min_pct": 0.90, "max_pct": 2.00, "color": "#f87171"},
    ]

    valid_samples = [int(hr) for hr in hr_stream if hr is not None and hr > 30]
    total_seconds = len(valid_samples)
    if not max_hr or max_hr <= 0:
        max_hr = max(valid_samples) if valid_samples else 190

    if total_seconds == 0:
        return [
            {
                "zone": z["zone"],
                "name": z["name"],
                "color": z["color"],
                "range_bpm": "—",
                "seconds": 0,
                "percent": 0.0,
            }
            for z in zones_def
        ]

    counts = [0] * len(zones_def)
    for hr in valid_samples:
        pct = hr / float(max_hr)
        if pct < 0.50:
            counts[0] += 1
            continue
        assigned = False
        for idx, z in enumerate(zones_def):
            if pct <= z["max_pct"] or idx == len(zones_def) - 1:
                counts[idx] += 1
                assigned = True
                break
        if not assigned:
            counts[-1] += 1

    result = []
    for idx, z in enumerate(zones_def):
        sec = counts[idx]
        pct_time = round((sec / float(total_seconds)) * 100.0, 1) if total_seconds > 0 else 0.0
        min_bpm = round(max_hr * z["min_pct"])
        max_bpm = round(max_hr * z["max_pct"])
        range_bpm = f"{min_bpm}–{max_bpm} bpm" if z["zone"] != "Z5" else f"> {min_bpm} bpm"

        result.append({
            "zone": z["zone"],
            "name": z["name"],
            "color": z["color"],
            "range_bpm": range_bpm,
            "seconds": sec,
            "percent": pct_time,
        })
    return result


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

