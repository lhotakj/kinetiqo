"""Pure functions for power modeling, Normalized Power, Intensity Factor, TSS, and MMP curves."""

import math
from typing import Dict, List, Optional, Sequence


def calculate_normalized_power(watts_stream: Sequence[Optional[float]]) -> float:
    """Calculate Normalized Power (NP) from a 1-second watts stream.

    NP uses a 30-second rolling average P_30s, raised to the 4th power:
        NP = ( mean(P_30s^4) ) ^ (1/4)

    :param watts_stream: Sequence of per-second watts (None is treated as 0.0).
    :return: Normalized Power in Watts (float).
    """
    cleaned = [float(w) if w is not None else 0.0 for w in watts_stream]
    if not cleaned:
        return 0.0

    if len(cleaned) < 30:
        return float(sum(cleaned) / len(cleaned))

    # 30-second rolling average
    window_size = 30
    cumsum = [0.0]
    for w in cleaned:
        cumsum.append(cumsum[-1] + w)

    p30_pow4_sum = 0.0
    count = 0
    for i in range(window_size, len(cleaned) + 1):
        avg_30s = (cumsum[i] - cumsum[i - window_size]) / window_size
        p30_pow4_sum += avg_30s ** 4
        count += 1

    if count == 0:
        return 0.0

    mean_pow4 = p30_pow4_sum / count
    return float(mean_pow4 ** 0.25)


def calculate_intensity_factor(np_w: float, ftp: float) -> Optional[float]:
    """Calculate Intensity Factor (IF = NP / FTP).

    :param np_w: Normalized Power in Watts.
    :param ftp: Functional Threshold Power in Watts (must be > 0).
    :return: Intensity Factor as float rounded to 4 decimals, or None if invalid.
    """
    if not ftp or ftp <= 0 or not np_w or np_w <= 0:
        return None
    return round(float(np_w) / float(ftp), 4)


def calculate_tss(duration_seconds: float, np_w: float, if_val: float, ftp: float) -> Optional[float]:
    """Calculate Training Stress Score (TSS).

    Formula:
        TSS = (duration_seconds * NP * IF) / (FTP * 3600) * 100

    :param duration_seconds: Duration in seconds.
    :param np_w: Normalized Power in Watts.
    :param if_val: Intensity Factor.
    :param ftp: Functional Threshold Power in Watts.
    :return: Training Stress Score as float rounded to 1 decimal, or None if invalid.
    """
    if not ftp or ftp <= 0 or not duration_seconds or duration_seconds <= 0 or not np_w or not if_val:
        return None
    tss = (duration_seconds * np_w * if_val) / (ftp * 3600.0) * 100.0
    return round(float(tss), 1)


def calculate_mmp_curve(
    timestamps: Sequence[int],
    watts: Sequence[Optional[float]],
    durations: Sequence[int] = (5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600),
) -> Dict[int, float]:
    """Calculate Mean Maximal Power (MMP) curve over continuous elapsed-time windows.

    Enforces true continuous elapsed-time semantics based on timestamps, preventing
    distorted rolling-window duration averages across pause or dropped-sample gaps.

    :param timestamps: Monotonically increasing epoch seconds for each sample.
    :param watts: Watts recorded at each timestamp (None treated as 0.0).
    :param durations: List of target window durations in seconds.
    :return: Dict mapping duration_seconds -> peak average watts.
    """
    if not timestamps or not watts or len(timestamps) != len(watts):
        return {d: 0.0 for d in durations}

    clean_watts = [float(w) if w is not None else 0.0 for w in watts]
    n = len(timestamps)
    result: Dict[int, float] = {}

    for target_dur in durations:
        if target_dur <= 0:
            result[target_dur] = 0.0
            continue

        best_avg = 0.0
        left = 0
        window_sum = 0.0

        for right in range(n):
            window_sum += clean_watts[right]
            
            # Shrink left side if elapsed time between timestamps exceeds target duration
            while left <= right and (timestamps[right] - timestamps[left] + 1) > target_dur:
                window_sum -= clean_watts[left]
                left += 1

            # Only qualify if the window covers the full target duration
            elapsed = timestamps[right] - timestamps[left] + 1
            if elapsed == target_dur:
                avg = window_sum / float(target_dur)
                if avg > best_avg:
                    best_avg = avg

        result[target_dur] = round(best_avg, 1)

    return result
