"""Physiology zone models for Coggan 7 power zones and standard 5 heart rate zones."""

from typing import Any, Dict, List, Optional, Sequence


def get_power_zone_name(pct_ftp: float) -> str:
    """Return the Coggan power zone name from percentage of FTP (supports both 0.75 and 75.0)."""
    p = pct_ftp * 100.0 if pct_ftp <= 2.5 else pct_ftp
    if p < 55.0:
        return "Recovery"
    elif p <= 75.0:
        return "Endurance"
    elif p <= 90.0:
        return "Tempo"
    elif p <= 105.0:
        return "Threshold"
    elif p <= 120.0:
        return "VO2max"
    elif p <= 150.0:
        return "Anaerobic"
    return "Neuromuscular"


COGGAN_ZONES_CONFIG = (
    ("Z1", "Active Recovery", 0, 55, "< 55% FTP", "#94a3b8", "Easy recovery spinning, post-interval recovery, promotes circulation with minimal fatigue."),
    ("Z2", "Endurance", 56, 75, "56% - 75% FTP", "#38bdf8", "All-day aerobic base pace, builds mitochondrial density and lipid oxidation capacity."),
    ("Z3", "Tempo", 76, 90, "76% - 90% FTP", "#4ade80", "Rhythmic aerobic endurance, sustainable for 1-3 hours, conversation in broken sentences."),
    ("Sweet Spot", "Sweet Spot Sub-Zone", 88, 94, "88% - 94% FTP", "#22c55e", "High aerobic stimulus with manageable neuro-muscular strain; optimal base training efficiency."),
    ("Z4", "Lactate Threshold", 91, 105, "91% - 105% FTP", "#facc15", "FTP maintenance and raising, 10-30 min intervals, onset of blood lactate accumulation."),
    ("Z5", "VO2max", 106, 120, "106% - 120% FTP", "#fb923c", "Maximal aerobic ceiling expansion, 3-8 min intervals or 30/30s micro-intervals, high cadence (>95 RPM)."),
    ("Z6", "Anaerobic Capacity", 121, 150, "121% - 150% FTP", "#f87171", "Short intense efforts (30s to 2 min), severe glycolytic acidosis."),
    ("Z7", "Neuromuscular Power", 151, None, "> 150% FTP", "#c084fc", "Maximal sprint efforts (< 15-20 seconds), maximum motor unit recruitment, non-aerobic."),
)


def compute_coggan_zones(ftp: float, weight_kg: float = 0.0) -> List[Dict[str, Any]]:
    """Compute Coggan 7-Zone power model boundaries, percentages, and W/kg from athlete FTP."""
    res = []
    for code, name, min_pct, max_pct, pct_range, color, desc in COGGAN_ZONES_CONFIG:
        min_w = round(ftp * (min_pct / 100.0), 1) if min_pct > 0 else 0.0
        max_w = round(ftp * (max_pct / 100.0), 1) if max_pct is not None else None
        min_w_kg = round(min_w / weight_kg, 2) if (weight_kg > 0 and min_w > 0) else (0.0 if weight_kg > 0 else None)
        max_w_kg = round(max_w / weight_kg, 2) if (weight_kg > 0 and max_w is not None) else None
        range_str = f"{min_w:.0f}W - {max_w:.0f}W" if max_w is not None else f">{min_w:.0f}W"
        w_kg_str = (
            f"{min_w_kg:.2f} - {max_w_kg:.2f} W/kg"
            if (min_w_kg is not None and max_w_kg is not None)
            else (f">{min_w_kg:.2f} W/kg" if min_w_kg is not None else None)
        )
        res.append({
            "zone": code,
            "name": name,
            "pct_ftp_range": pct_range,
            "min_watts": min_w,
            "max_watts": max_w,
            "watts_range": range_str,
            "min_w_per_kg": min_w_kg,
            "max_w_per_kg": max_w_kg,
            "w_per_kg_range": w_kg_str,
            "color": color,
            "description": desc,
        })
    return res


COGGAN_SUMMARY_ZONES = [
    {"zone": "Z1", "name": "Active Recovery", "min_pct": 0.0, "max_pct": 0.55, "color": "#94a3b8"},
    {"zone": "Z2", "name": "Endurance", "min_pct": 0.55, "max_pct": 0.75, "color": "#38bdf8"},
    {"zone": "Z3", "name": "Tempo", "min_pct": 0.75, "max_pct": 0.90, "color": "#4ade80"},
    {"zone": "Z4", "name": "Threshold", "min_pct": 0.90, "max_pct": 1.05, "color": "#facc15"},
    {"zone": "Z5", "name": "VO2 Max", "min_pct": 1.05, "max_pct": 1.20, "color": "#fb923c"},
    {"zone": "Z6", "name": "Anaerobic", "min_pct": 1.20, "max_pct": 1.50, "color": "#f87171"},
    {"zone": "Z7", "name": "Neuromuscular", "min_pct": 1.50, "max_pct": 999.0, "color": "#c084fc"},
]


def _format_coggan_range(ftp: float, z: Dict[str, Any]) -> str:
    """Format the power range string for a Coggan zone."""
    if z["zone"] == "Z1":
        return f"< {round(ftp * 0.55)} W"
    if z["zone"] == "Z7":
        return f"> {round(ftp * 1.50)} W"
    return f"{round(ftp * z['min_pct'])}–{round(ftp * z['max_pct'])} W"


def _assign_coggan_zone(pct: float, zones_def: List[Dict[str, Any]]) -> int:
    """Find the zone index for a given percentage of FTP."""
    for idx, z in enumerate(zones_def):
        if pct <= z["max_pct"] or idx == len(zones_def) - 1:
            return idx
    return len(zones_def) - 1


def calculate_coggan_zones(
    watts_stream: Sequence[Optional[float]],
    ftp: Optional[float],
) -> List[Dict[str, Any]]:
    """Calculate time and percentage in Coggan 7 power zones from a time-series watts stream."""
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
            for z in COGGAN_SUMMARY_ZONES
        ]

    counts = [0] * len(COGGAN_SUMMARY_ZONES)
    for w in valid_samples:
        pct = w / float(ftp)
        counts[_assign_coggan_zone(pct, COGGAN_SUMMARY_ZONES)] += 1

    result = []
    for idx, z in enumerate(COGGAN_SUMMARY_ZONES):
        sec = counts[idx]
        pct_time = round((sec / float(total_seconds)) * 100.0, 1)
        result.append({
            "zone": z["zone"],
            "name": z["name"],
            "color": z["color"],
            "range_w": _format_coggan_range(ftp, z),
            "seconds": sec,
            "percent": pct_time,
        })
    return result


HR_SUMMARY_ZONES = [
    {"zone": "Z1", "name": "Recovery", "min_pct": 0.50, "max_pct": 0.60, "color": "#94a3b8"},
    {"zone": "Z2", "name": "Aerobic", "min_pct": 0.60, "max_pct": 0.70, "color": "#38bdf8"},
    {"zone": "Z3", "name": "Tempo", "min_pct": 0.70, "max_pct": 0.80, "color": "#4ade80"},
    {"zone": "Z4", "name": "Threshold", "min_pct": 0.80, "max_pct": 0.90, "color": "#facc15"},
    {"zone": "Z5", "name": "Anaerobic", "min_pct": 0.90, "max_pct": 2.00, "color": "#f87171"},
]


def calculate_hr_zones(
    hr_stream: Sequence[Optional[int]],
    max_hr: Optional[int],
) -> List[Dict[str, Any]]:
    """Calculate time and percentage in 5 standard Heart Rate zones based on max HR."""
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
            for z in HR_SUMMARY_ZONES
        ]

    counts = [0] * len(HR_SUMMARY_ZONES)
    for hr in valid_samples:
        pct = hr / float(max_hr)
        if pct < 0.50:
            counts[0] += 1
            continue
        assigned = False
        for idx, z in enumerate(HR_SUMMARY_ZONES):
            if pct <= z["max_pct"] or idx == len(HR_SUMMARY_ZONES) - 1:
                counts[idx] += 1
                assigned = True
                break
        if not assigned:
            counts[-1] += 1

    result = []
    for idx, z in enumerate(HR_SUMMARY_ZONES):
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
