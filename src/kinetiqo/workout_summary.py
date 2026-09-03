"""RestOrTrain-style workout summary classification & structure generator.

Analyzes activity stream data (watts, heart rate, time) and athlete FTP to
generate human-readable workout summaries (e.g. "Endurance | 120min @ 191W",
"Tempo | 120min @ 224W", "Endurance | 4h @ 209W normalized (74% FTP), with 10-15min blocks @ 220-243W (78-86%)",
or HR fallback "Endurance | About 2h30m aerobic riding @ 125bpm average HR").

Significant high-watt peaks (at least 1 minute at or above the peak
threshold) are highlighted as best moments, e.g.
"Endurance | 49min @ 150W + peak 2min @360-400W" or
"Endurance | 90min @ 180W + 3x surges 1-2min @360-400W".
"""

import math
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Peak highlight constants. A "peak" is a sustained high-watt effort worth
# calling out as one of the ride's best moments (see format_peaks_highlight).
# The effective threshold is the higher of DEFAULT_PEAK_THRESHOLD_W (an
# absolute watt floor, env-configurable via WORKOUT_SUMMARY_PEAK_THRESHOLD_W)
# and 110% of the athlete's FTP, so peaks are always relative to the
# athlete's own fitness, not just a fixed number.
# ---------------------------------------------------------------------------
DEFAULT_PEAK_THRESHOLD_W = 300.0
PEAK_MIN_DURATION_S = 60  # a peak must last at least 1 minute
PEAK_MERGE_GAP_S = 20  # sub-threshold drops shorter than this don't split a peak
PEAK_MAX_SHOWN = 3  # at most this many peaks are highlighted


def calculate_normalized_power(watts_stream: List[float]) -> float:
    """Calculate Normalized Power (NP) from a 1-second watts stream.

    NP uses a 30-second rolling average P_30s, raised to the 4th power:
        NP = ( mean(P_30s^4) ) ^ (1/4)
    """
    if not watts_stream or len(watts_stream) < 30:
        return float(sum(watts_stream) / len(watts_stream)) if watts_stream else 0.0

    # 30-second rolling average
    window_size = 30
    cumsum = [0.0]
    for w in watts_stream:
        cumsum.append(cumsum[-1] + (w or 0.0))

    p30_pow4_sum = 0.0
    count = 0
    for i in range(window_size, len(watts_stream) + 1):
        avg_30s = (cumsum[i] - cumsum[i - window_size]) / window_size
        p30_pow4_sum += avg_30s ** 4
        count += 1

    if count == 0:
        return 0.0

    mean_pow4 = p30_pow4_sum / count
    return mean_pow4 ** 0.25


def format_duration(seconds: float, use_minutes: bool = True) -> str:
    """Format duration in seconds.

    If use_minutes is True and seconds <= 10800 (3 hours), formats as 'Xmin' (e.g. 120min).
    Otherwise formats as 'Xh' or 'XhYm' (e.g. 4h, 2h30m).
    """
    total_sec = max(0, int(round(seconds)))
    total_min = total_sec // 60
    hours = total_min // 60
    mins = total_min % 60

    if use_minutes and total_sec <= 10800:
        return f"{total_min}min"

    if mins == 0:
        return f"{hours}h"
    return f"{hours}h{mins:02d}m" if hours > 0 else f"{mins}min"


def get_power_zone_name(pct_ftp: float) -> str:
    """Return the Coggan 7-Zone power zone name from percentage of FTP."""
    if pct_ftp < 55.0:
        return "Recovery"
    elif pct_ftp <= 75.0:
        return "Endurance"
    elif pct_ftp <= 90.0:
        return "Tempo"
    elif pct_ftp <= 105.0:
        return "Threshold"
    elif pct_ftp <= 120.0:
        return "VO2max"
    else:
        return "Anaerobic"


def _detect_blocks(watts_stream: List[float], time_stream: Optional[List[float]], ftp: float, overall_avg_w: float = 0.0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Detect sustained blocks (5-20 min in Z3+) and short surges (1-3 min in Z4+) from watts stream.

    Returns (sustained_blocks, short_surges).
    """
    if not watts_stream or len(watts_stream) < 60 or ftp <= 0:
        return [], []

    total_s = len(watts_stream)

    # Smooth stream with 15s rolling average
    smooth_w = []
    window = 15
    cumsum = [0.0]
    for w in watts_stream:
        cumsum.append(cumsum[-1] + (w or 0.0))
    for i in range(len(watts_stream)):
        start_idx = max(0, i - window + 1)
        cnt = i - start_idx + 1
        smooth_w.append((cumsum[i + 1] - cumsum[start_idx]) / cnt)

    sustained_blocks = []
    short_surges = []

    # Find contiguous segments where smooth power >= 76% FTP (Tempo+)
    i = 0
    n = len(smooth_w)
    while i < n:
        if smooth_w[i] >= 0.76 * ftp:
            start_i = i
            while i < n and smooth_w[i] >= 0.70 * ftp:  # hysteresis threshold
                i += 1
            end_i = i
            duration_s = end_i - start_i
            if duration_s >= 60:
                seg_watts = watts_stream[start_i:end_i]
                avg_w = sum(seg_watts) / len(seg_watts)
                pct_ftp = (avg_w / ftp) * 100.0
                min_w = min(seg_watts)
                max_w = max(seg_watts)

                # Skip single blocks that cover >85% of total ride duration with power ~ overall average
                if duration_s >= 0.85 * total_s and overall_avg_w > 0 and abs(avg_w - overall_avg_w) / overall_avg_w < 0.05:
                    continue

                block_info = {
                    "duration_s": duration_s,
                    "duration_min": round(duration_s / 60.0),
                    "avg_w": round(avg_w),
                    "min_w": round(min_w),
                    "max_w": round(max_w),
                    "pct_ftp": round(pct_ftp),
                    "pct_min": round((min_w / ftp) * 100.0),
                    "pct_max": round((max_w / ftp) * 100.0),
                    "start_i": start_i,
                    "end_i": end_i,
                }

                if duration_s >= 300:  # 5+ minutes
                    sustained_blocks.append(block_info)
                elif duration_s >= 60 and avg_w >= 1.05 * ftp:  # 1-5 min surge
                    short_surges.append(block_info)
        else:
            i += 1

    return sustained_blocks, short_surges


def _detect_high_watt_peaks(
    watts_stream: List[float],
    threshold_w: float,
    min_duration_s: int = PEAK_MIN_DURATION_S,
    merge_gap_s: int = PEAK_MERGE_GAP_S,
) -> List[Dict[str, Any]]:
    """Detect sustained high-watt peaks (>= threshold_w for >= min_duration_s).

    Peaks are located on a noise-tolerant 5-second rolling average, while
    avg/min/max watts are computed from the raw samples of each peak. Brief
    drops below the threshold shorter than *merge_gap_s* seconds do not split
    a peak into two (power meters commonly show 1-5s gaps mid-surge).

    Returns a list of dicts (duration_s, avg_w, min_w, max_w, start_i, end_i)
    sorted by avg_w descending (most intense first).
    """
    if not watts_stream or len(watts_stream) < min_duration_s or threshold_w <= 0:
        return []

    # 5-second rolling average for noise-tolerant threshold crossing
    smooth_w = []
    window = 5
    cumsum = [0.0]
    for w in watts_stream:
        cumsum.append(cumsum[-1] + (w or 0.0))
    for i in range(len(watts_stream)):
        start_idx = max(0, i - window + 1)
        cnt = i - start_idx + 1
        smooth_w.append((cumsum[i + 1] - cumsum[start_idx]) / cnt)

    # Find contiguous segments at or above the threshold
    segments = []
    i = 0
    n = len(smooth_w)
    while i < n:
        if smooth_w[i] >= threshold_w:
            start_i = i
            while i < n and smooth_w[i] >= threshold_w:
                i += 1
            segments.append([start_i, i])
        else:
            i += 1

    # Merge segments separated by short sub-threshold gaps into a single peak
    merged = []
    for seg in segments:
        if merged and seg[0] - merged[-1][1] <= merge_gap_s:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)

    peaks = []
    for seg_start, seg_end in merged:
        # Trim the leading/trailing sub-threshold samples introduced by the
        # smoothing lag, so min/max/avg watts describe the actual effort.
        start_i = seg_start
        while start_i < seg_end and (watts_stream[start_i] or 0.0) < threshold_w:
            start_i += 1
        end_i = seg_end
        while end_i > start_i and (watts_stream[end_i - 1] or 0.0) < threshold_w:
            end_i -= 1
        duration_s = end_i - start_i
        if duration_s < min_duration_s:
            continue
        seg_watts = watts_stream[start_i:end_i]
        peaks.append({
            "duration_s": duration_s,
            "avg_w": sum(seg_watts) / len(seg_watts),
            "min_w": min(seg_watts),
            "max_w": max(seg_watts),
            "start_i": start_i,
            "end_i": end_i,
        })

    # Most intense peaks first
    peaks.sort(key=lambda p: p["avg_w"], reverse=True)
    return peaks


def format_peaks_highlight(peaks: List[Dict[str, Any]], max_shown: int = PEAK_MAX_SHOWN) -> str:
    """Format the best high-watt peaks as a highlight suffix for the workout summary.

    With a single peak:   " + peak 2min @360-400W"
    With several peaks:   " + 3x surges 1-2min @360-400W"
                          " + 3+ surges 1-2min @360-400W"  (more than max_shown peaks)

    The duration range and watt range are computed from the best *max_shown*
    peaks (by avg watts). Returns an empty string when there are no peaks.
    """
    if not peaks:
        return ""

    def _fmt_peak_min(seconds: float) -> str:
        return f"{max(1, int(round(seconds / 60)))}min"

    shown = peaks[:max_shown]
    min_w = round(min(p["min_w"] for p in shown))
    max_w = round(max(p["max_w"] for p in shown))
    w_str = f"{min_w}W" if min_w == max_w else f"{min_w}-{max_w}W"
    if len(peaks) == 1:
        return f" + peak {_fmt_peak_min(shown[0]['duration_s'])} @{w_str}"

    min_d = int(round(min(p["duration_s"] for p in shown) / 60))
    max_d = int(round(max(p["duration_s"] for p in shown) / 60))
    dur_str = f"{min_d}min" if min_d == max_d else f"{min_d}-{max_d}min"
    count_str = f"{max_shown}+" if len(peaks) > max_shown else f"{len(peaks)}x"
    return f" + {count_str} surges {dur_str} @{w_str}"


def generate_workout_summary(
    activity: Dict[str, Any],
    watts_stream: Optional[List[float]] = None,
    time_stream: Optional[List[float]] = None,
    hr_stream: Optional[List[float]] = None,
    ftp: Optional[float] = None,
    peak_threshold_w: Optional[float] = None
) -> str:
    """Generate RestOrTrain-style workout summary text.

    If power data is available (via watts_stream or activity['average_watts']),
    calculates zone category, NP, % FTP, and interval structure. Significant
    high-watt peaks are highlighted as best moments, e.g.
    "Endurance | 49min @ 150W + peak 2min @360-400W" (see
    :func:`format_peaks_highlight`); the effective peak threshold is the
    higher of *peak_threshold_w* (default :data:`DEFAULT_PEAK_THRESHOLD_W`)
    and 110% of FTP.

    If power data is NOT available, falls back to HR & moving_time summary:
        "Endurance | About 2h30m aerobic riding @ 125bpm average HR"
    """
    moving_time = float(activity.get("moving_time") or 0)
    avg_watts = float(activity.get("average_watts") or 0)
    weighted_watts = float(activity.get("weighted_average_watts") or 0)
    avg_hr = float(activity.get("average_heartrate") or 0)

    # 1. Power-based classification
    has_power = (watts_stream and any(w > 0 for w in watts_stream)) or (avg_watts > 0)
    if has_power:
        ftp_val = float(ftp) if ftp and ftp > 0 else 250.0  # default fallback if unconfigured

        if watts_stream and len(watts_stream) >= 30:
            np_watts = calculate_normalized_power(watts_stream)
        elif weighted_watts > 0:
            np_watts = weighted_watts
        else:
            np_watts = avg_watts

        # Calculate % FTP
        effective_power = np_watts if np_watts > 0 else avg_watts
        pct_ftp = round((effective_power / ftp_val) * 100.0)
        category = get_power_zone_name(pct_ftp)

        # Detect blocks & surges
        sustained_blocks, short_surges = _detect_blocks(watts_stream or [], time_stream, ftp_val, overall_avg_w=avg_watts)

        # Detect significant high-watt peaks (best moments). The threshold is
        # the higher of the configured absolute floor and 110% of FTP, so
        # peaks are always relative to the athlete's own fitness.
        effective_peak_threshold = float(peak_threshold_w or DEFAULT_PEAK_THRESHOLD_W)
        if ftp_val > 0:
            effective_peak_threshold = max(effective_peak_threshold, 1.10 * ftp_val)
        peaks = _detect_high_watt_peaks(watts_stream or [], effective_peak_threshold)
        if sustained_blocks and peaks:
            # A peak fully inside an already-reported sustained block adds no
            # information — keep only peaks that stand on their own.
            peaks = [p for p in peaks if not any(
                b["start_i"] <= p["start_i"] and p["end_i"] <= b["end_i"]
                for b in sustained_blocks
            )]
        peaks_part = format_peaks_highlight(peaks)

        # If short explosive surges (>120% FTP) dominate intervals, promote to
        # Anaerobic or VO2max. When high-watt peaks were detected they already
        # highlight the intensity as best moments, so the ride category is
        # left alone (an endurance ride with a few surges stays "Endurance").
        if short_surges and not sustained_blocks and not peaks:
            max_surge_pct = max(s["pct_ftp"] for s in short_surges)
            if max_surge_pct > 120 and category in ("Recovery", "Endurance"):
                category = "Anaerobic"

        use_min = moving_time <= 10800  # <= 3h -> min
        main_duration_str = format_duration(moving_time, use_minutes=use_min)

        # Check if NP is significantly higher than average (variable ride)
        is_variable = (np_watts > avg_watts * 1.08) and (moving_time >= 3600)

        if is_variable:
            base_part = f"{main_duration_str} @ {round(np_watts)}W normalized ({pct_ftp}% FTP)"
        else:
            p_show = round(avg_watts) if avg_watts > 0 else round(np_watts)
            base_part = f"{main_duration_str} @ {p_show}W"

        # Format blocks, peaks or short surges
        if sustained_blocks:
            min_dur = min(b["duration_min"] for b in sustained_blocks)
            max_dur = max(b["duration_min"] for b in sustained_blocks)
            dur_range_str = f"{min_dur}min" if min_dur == max_dur else f"{min_dur}-{max_dur}min"

            min_w = min(b["avg_w"] for b in sustained_blocks)
            max_w = max(b["avg_w"] for b in sustained_blocks)
            w_range_str = f"{min_w}W" if min_w == max_w else f"{min_w}-{max_w}W"

            min_pct = min(b["pct_ftp"] for b in sustained_blocks)
            max_pct = max(b["pct_ftp"] for b in sustained_blocks)
            pct_range_str = f"{min_pct}%" if min_pct == max_pct else f"{min_pct}-{max_pct}%"

            structure_part = f", with {dur_range_str} blocks @ {w_range_str} ({pct_range_str})"
            return f"{category} | {base_part}{structure_part}{peaks_part}"
        elif peaks:
            return f"{category} | {base_part}{peaks_part}"
        elif short_surges:
            surge = short_surges[0]
            surge_str = f" + {surge['duration_min']}min @ {surge['avg_w']}W"
            return f"{category} | {base_part}{surge_str}"
        else:
            return f"{category} | {base_part}"

    # 2. Heart Rate fallback (Garmin HR Zone & EPOC methodology)
    if avg_hr > 0 or moving_time > 0:
        if avg_hr <= 135:
            category = "Endurance"
            intensity_text = "aerobic riding"
        elif avg_hr <= 155:
            category = "Tempo"
            intensity_text = "tempo riding"
        elif avg_hr <= 170:
            category = "Threshold"
            intensity_text = "threshold riding"
        else:
            category = "VO2max"
            intensity_text = "high intensity riding"

        total_min = int(round(moving_time / 60.0))
        hours = total_min // 60
        mins = total_min % 60
        if hours > 0 and mins > 0:
            dur_str = f"{hours}h{mins:02d}m"
        elif hours > 0:
            dur_str = f"{hours}h"
        else:
            dur_str = f"{total_min}min"

        hr_str = f" @ {int(round(avg_hr))}bpm average HR" if avg_hr > 0 else ""
        return f"{category} | About {dur_str} {intensity_text}{hr_str}"

    return ""
