"""VO2max estimation from cycling power data.

Uses the Storer-Davis equation to estimate VO2max from the best 5-minute
average power (a proxy for Maximal Aerobic Power, MAP):

    VO2max (ml/kg/min) ≈ (10.8 × MAP / body_weight_kg) + 7

The per-ride estimates are then smoothed with an **asymmetric EWMA**
inspired by the Firstbeat algorithm used by Garmin:

- Improvements (new > smoothed) are absorbed quickly  (α_up ≈ 0.3).
- Declines    (new < smoothed) are absorbed slowly    (α_down ≈ 0.07).
- Gaps between rides cause a small daily decay         (≈ 0.1 %/day).

This produces a chart that rises promptly with genuine fitness gains
but resists temporary dips from individual bad rides, closely matching
the behaviour athletes see on their Garmin watches.

References:
    Storer, T.W., Davis, J.A., & Caiozzo, V.J. (1990).
    "Accurate prediction of VO2max in cycle ergometry."
    Medicine and Science in Sports and Exercise, 22(5), 704-712.

    Firstbeat Technologies (2014).
    "VO2max Estimation — White Paper."
"""

from datetime import date
from typing import List, Dict
from statistics import median


# --- Smoothing parameters (Firstbeat-inspired) ---
# How quickly the smoothed value rises toward a higher raw estimate.
ALPHA_UP: float = 0.3

# How slowly the smoothed value falls toward a lower raw estimate.
ALPHA_DOWN: float = 0.07

# Multiplicative daily decay applied for each calendar day without a ride.
# 0.999 ≈ −0.1 %/day  →  ~3 % drop after 30 days of complete inactivity.
DAILY_DECAY: float = 0.999

# --- Qualifying-ride filters (Garmin-style) ---
# Minimum seconds of power data for a ride to qualify.  Garmin requires
# sustained effort at a meaningful intensity; 20 minutes of power data is
# a practical proxy when we don't have heart-rate zone information.
MIN_WATTS_SAMPLES: int = 1200  # 20 minutes

# Rides whose VO2max is below this fraction of the running median are
# considered recovery / junk rides and are excluded, just as Garmin
# silently ignores easy efforts.
OUTLIER_FRACTION: float = 0.75


def estimate_vo2max(map_watts: float, body_weight_kg: float) -> float:
    """Estimate VO2max from Maximal Aerobic Power and body weight.

    :param map_watts: Best 5-minute average power in watts.
    :param body_weight_kg: Athlete body weight in kilograms.
    :return: Estimated VO2max in ml/kg/min, or 0.0 if inputs are invalid.
    """
    if body_weight_kg <= 0 or map_watts <= 0:
        return 0.0
    return (10.8 * map_watts / body_weight_kg) + 7.0


def classify_vo2max(vo2max: float, gender: str = "male") -> str:
    """Return a human-readable fitness classification for a VO2max value.

    Categories based on the American College of Sports Medicine (ACSM)
    guidelines for men aged 30-39.  The thresholds are approximate and
    intended for informational purposes only.

    :param vo2max: Estimated VO2max in ml/kg/min.
    :param gender: ``"male"`` or ``"female"`` (currently only male thresholds).
    :return: Classification string.
    """
    if vo2max <= 0:
        return "N/A"
    if vo2max >= 55:
        return "Superior"
    if vo2max >= 49:
        return "Excellent"
    if vo2max >= 43:
        return "Good"
    if vo2max >= 37:
        return "Fair"
    if vo2max >= 30:
        return "Poor"
    return "Very Poor"


def filter_qualifying_rides(
    entries: List[Dict],
    *,
    outlier_fraction: float = OUTLIER_FRACTION,
) -> List[Dict]:
    """Filter a list of per-ride VO2max entries to keep only qualifying efforts.

    Mirrors Garmin/Firstbeat behaviour which silently ignores recovery
    rides and keeps only the best effort per calendar day.

    Steps:
      1. **Best per day** — if multiple rides on the same date, keep only
         the one with the highest VO2max.
      2. **Outlier rejection** — compute the median of the remaining
         values and discard any entry below ``outlier_fraction × median``.
         This removes easy/recovery rides that would drag the EWMA down.

    *entries* must each contain at least ``"date"`` and ``"vo2max"`` keys.
    The returned list preserves the original dict structure and order.

    :param entries: List of ``{"date": ..., "vo2max": ..., ...}`` dicts.
    :param outlier_fraction: Minimum ratio to the median (default 0.75).
    :return: Filtered list of qualifying entries, sorted by date.
    """
    if not entries:
        return []

    # 1. Best per day
    best_by_day: Dict[str, Dict] = {}
    for e in entries:
        d = e["date"]
        if d not in best_by_day or e["vo2max"] > best_by_day[d]["vo2max"]:
            best_by_day[d] = e
    deduped = sorted(best_by_day.values(), key=lambda r: r["date"])

    # 2. Outlier rejection
    if len(deduped) < 3:
        return deduped

    med = median(e["vo2max"] for e in deduped)
    threshold = med * outlier_fraction
    return [e for e in deduped if e["vo2max"] >= threshold]


def smooth_vo2max_history(
    entries: List[Dict],
    *,
    alpha_up: float = ALPHA_UP,
    alpha_down: float = ALPHA_DOWN,
    daily_decay: float = DAILY_DECAY,
) -> List[float]:
    """Apply Firstbeat-style asymmetric EWMA to a VO2max time-series.

    *entries* must be a **chronologically sorted** list of dicts, each
    containing at least ``"date"`` (``"YYYY-MM-DD"`` string) and
    ``"vo2max"`` (float).

    Returns a list of smoothed VO2max values, one per entry, in the
    same order.

    Algorithm per data-point:
      1. Apply daily inactivity decay for every calendar day since the
         previous ride.
      2. Blend the new raw value into the smoothed value using α_up
         (if raw > smoothed) or α_down (if raw ≤ smoothed).

    :param entries: Chronologically sorted list of ``{"date": ..., "vo2max": ...}`` dicts.
    :param alpha_up: EWMA factor for increases (default :data:`ALPHA_UP`).
    :param alpha_down: EWMA factor for decreases (default :data:`ALPHA_DOWN`).
    :param daily_decay: Multiplicative decay per idle day (default :data:`DAILY_DECAY`).
    :return: List of smoothed VO2max floats, same length as *entries*.
    """
    if not entries:
        return []

    smoothed_values: List[float] = []
    smoothed = entries[0]["vo2max"]
    prev_date = date.fromisoformat(entries[0]["date"])
    smoothed_values.append(round(smoothed, 1))

    for entry in entries[1:]:
        raw = entry["vo2max"]
        cur_date = date.fromisoformat(entry["date"])

        # 1. Inactivity decay for idle days between rides
        gap_days = (cur_date - prev_date).days
        if gap_days > 1:
            smoothed *= daily_decay ** (gap_days - 1)

        # 2. Asymmetric EWMA blend
        alpha = alpha_up if raw > smoothed else alpha_down
        smoothed += alpha * (raw - smoothed)

        smoothed_values.append(round(smoothed, 1))
        prev_date = cur_date

    return smoothed_values

