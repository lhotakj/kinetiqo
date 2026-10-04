"""Fondo-o-meter computation for the Fondo-o-meter infographic page.

Computes Fondo Analysis concentric circles, KOM counts, PR counts,
and summary metrics from activities filtered by year and activity group.
"""

from datetime import datetime, date
from typing import List, Dict, Any, Optional
import math

from kinetiqo.web.stats import (
    ACTIVITY_GROUPS,
    parse_activity_date,
)

# Baseline distance threshold in kilometers for Fondo Analysis by sport group
SPORT_DISTANCE_THRESHOLDS: Dict[str, float] = {
    'cycling': 100.0,
    'cycling_outdoor': 100.0,
    'cycling_indoor': 100.0,
    'running': 42.195,  # Marathon
    'walking': 42.195,
    'swimming': 10.0,
    'skiing': 50.0,
}

DEFAULT_DISTANCE_THRESHOLD_KM = 100.0

# Harmonic colors for up to 8 concentric rings (innermost to outermost / highest km in brightest color)
FONDO_RING_COLORS: List[str] = [
    '#2E4A14',  # Ring 1 (innermost / deepest olive)
    '#4D6A28',  # Ring 2
    '#709930',  # Ring 3
    '#94C03B',  # Ring 4
    '#B3D45A',  # Ring 5
    '#CDE57A',  # Ring 6
    '#E2F19D',  # Ring 7
    '#F7FBE2',  # Ring 8 (outermost / brightest lime)
]


def get_sport_threshold(group_key: str) -> float:
    """Return the threshold in kilometers for the given activity group."""
    return SPORT_DISTANCE_THRESHOLDS.get(group_key, DEFAULT_DISTANCE_THRESHOLD_KM)


def _pick_step_size(span: float, max_bins: int = 7) -> float:
    """Pick a clean round step size so that span / step <= max_bins."""
    candidates = [5.0, 10.0, 20.0, 25.0, 50.0, 100.0, 200.0, 250.0, 500.0]
    for step in candidates:
        if span / step <= max_bins:
            return step
    return candidates[-1]


def compute_fondo_circles(
    qualifying_activities: List[Dict[str, Any]],
    threshold_km: float,
    noun: str = "ride"
) -> List[Dict[str, Any]]:
    """Compute up to 8 concentric rings with smart binning and an inverse gradient.

    Outermost ring (index len-1) is dedicated to the single longest activity.
    Inner rings (indices 0..N-2) represent distance bins from threshold_km up to max_km.

    Returns a list of dicts from innermost (index 0) to outermost (index len-1).
    """
    if not qualifying_activities:
        return []

    # Sort descending by distance
    sorted_acts = sorted(
        qualifying_activities,
        key=lambda a: (a.get('distance') or 0.0),
        reverse=True
    )
    longest = sorted_acts[0]
    max_km = (longest.get('distance') or 0.0) / 1000.0

    if len(sorted_acts) == 1 or max_km <= threshold_km:
        # Only 1 qualifying ride
        label = f"{longest.get('name', 'Longest ' + noun)} ({max_km:.1f} km)"
        return [{
            'ring_index': 0,
            'is_longest': True,
            'name': longest.get('name', 'Longest ' + noun),
            'distance_km': round(max_km, 1),
            'label': label,
            'count': 1,
            'arc_pct': 50.0,
            'color': FONDO_RING_COLORS[-1],
        }]

    span = max_km - threshold_km
    step = _pick_step_size(span, max_bins=7)
    num_bins = min(7, max(1, math.ceil(span / step)))

    bins: List[Dict[str, Any]] = []
    for b in range(num_bins):
        low = threshold_km + b * step
        high = threshold_km + (b + 1) * step
        bins.append({
            'low_km': low,
            'high_km': high,
            'count': 0,
            'activities': []
        })

    # Distribute non-longest qualifying activities into bins
    for act in sorted_acts[1:]:
        d_km = (act.get('distance') or 0.0) / 1000.0
        bin_idx = int((d_km - threshold_km) // step)
        bin_idx = max(0, min(num_bins - 1, bin_idx))
        bins[bin_idx]['count'] += 1
        bins[bin_idx]['activities'].append(act)

    # Filter out empty bins to keep rings meaningful
    active_bins = [b for b in bins if b['count'] > 0]

    # If all non-longest rides ended up in 0 active bins (rare edge case)
    if not active_bins:
        active_bins = [bins[0]]

    # Total rings = active_bins count + 1 (the longest ride)
    total_rings = min(8, len(active_bins) + 1)
    if len(active_bins) > 7:
        active_bins = active_bins[-7:]

    max_count = max([b['count'] for b in active_bins] + [1])

    # Assign harmonic colors using inverse gradient:
    # Outer ring (index total_rings-1) gets the brightest lime (#F7FBE2)
    # Inner rings get proportional deeper shades.
    color_indices = []
    if total_rings == 1:
        color_indices = [len(FONDO_RING_COLORS) - 1]
    else:
        for i in range(total_rings):
            idx = int(round(i * (len(FONDO_RING_COLORS) - 1) / (total_rings - 1)))
            color_indices.append(idx)

    circles: List[Dict[str, Any]] = []

    # 1. Inner rings for bins (innermost first)
    for i, b in enumerate(active_bins):
        # Arc percentage: 10% base + up to 40% proportional to count (max 50% = 180 degrees)
        arc_pct = 12.0 + (b['count'] / max_count) * 38.0
        noun_str = f"{noun}s" if b['count'] > 1 else noun
        low_fmt = f"{int(b['low_km'])}" if b['low_km'].is_integer() else f"{b['low_km']:.1f}"
        high_fmt = f"{int(b['high_km'])}" if b['high_km'].is_integer() else f"{b['high_km']:.1f}"
        label = f"{low_fmt}–{high_fmt} km: {b['count']} {noun_str}"

        circles.append({
            'ring_index': i,
            'is_longest': False,
            'low_km': b['low_km'],
            'high_km': b['high_km'],
            'count': b['count'],
            'label': label,
            'arc_pct': round(arc_pct, 1),
            'color': FONDO_RING_COLORS[color_indices[i]],
        })

    # 2. Outermost ring for the longest activity (sweeps full 180 degrees = 50.0% arc)
    outer_idx = len(circles)
    longest_name = longest.get('name') or f"Longest {noun}"
    outer_label = f"{longest_name} ({max_km:.1f} km)"
    circles.append({
        'ring_index': outer_idx,
        'is_longest': True,
        'name': longest_name,
        'distance_km': round(max_km, 1),
        'label': outer_label,
        'count': 1,
        'arc_pct': 50.0,
        'color': FONDO_RING_COLORS[color_indices[-1]],
    })

    return circles


def compute_fondo_o_meter(
    activities: List[Dict[str, Any]],
    year: int,
    group_key: str = 'cycling'
) -> Dict[str, Any]:
    """Compute summary statistics for the Fondo-o-meter Infographic.

    Filters activities by year and sport group, then calculates:
      - Total activities, total distance (km), total elevation (m)
      - Number of KOMs/CRs (achievement_count - pr_count where > 0)
      - Number of PRs (pr_count)
      - Longest activity details
      - Concentric radial chart circles for qualifying fondo activities

    Returns:
        Dict[str, Any]: Full payload ready for JSON response and rendering.
    """
    group_info = ACTIVITY_GROUPS.get(group_key, ACTIVITY_GROUPS.get('cycling', {}))
    allowed_types = group_info.get('types', [])
    noun = group_info.get('noun', 'ride')
    threshold_km = get_sport_threshold(group_key)

    filtered_activities = []
    koms_count = 0
    prs_count = 0
    longest_act = None
    max_dist_m = 0.0

    for act in activities:
        # Date filter
        d = parse_activity_date(act.get('start_date'))
        if not d or d.year != year:
            continue

        # Sport type filter
        act_type = act.get('type') or act.get('sport_type') or ''
        if allowed_types and act_type not in allowed_types:
            continue

        filtered_activities.append(act)

        # Distance & Longest
        dist_m = float(act.get('distance') or 0.0)
        if dist_m > max_dist_m:
            max_dist_m = dist_m
            longest_act = act

        # KOMs & PRs Aggregation
        ach_count = int(act.get('achievement_count') or 0)
        pr_c = int(act.get('pr_count') or 0)
        prs_count += pr_c
        # KOMs/CRs are achievements beyond PRs
        koms = max(0, ach_count - pr_c)
        koms_count += koms

    # Qualifying Fondo activities (distance >= threshold_km)
    qualifying_acts = [
        a for a in filtered_activities
        if (float(a.get('distance') or 0.0) / 1000.0) >= threshold_km
    ]

    fondo_circles = compute_fondo_circles(qualifying_acts, threshold_km, noun=noun)

    longest_info = None
    if longest_act:
        longest_dist_km = (float(longest_act.get('distance') or 0.0)) / 1000.0
        longest_info = {
            'id': longest_act.get('id') or longest_act.get('activity_id'),
            'name': longest_act.get('name', f'Longest {noun}'),
            'distance_km': round(longest_dist_km, 1),
            'start_date': str(longest_act.get('start_date', '')),
        }

    return {
        'year': year,
        'group': group_key,
        'group_name': group_info.get('name', 'Cycling'),
        'group_icon': group_info.get('icon', '🚴'),
        'group_noun': noun,
        'threshold_km': threshold_km,
        'total_activities': len(filtered_activities),
        'koms_count': koms_count,
        'prs_count': prs_count,
        'longest_ride': longest_info,
        'fondo': {
            'threshold_km': threshold_km,
            'total_qualifying': len(qualifying_acts),
            'circles': fondo_circles,
        }
    }


# Backwards compatibility alias
compute_achievements = compute_fondo_o_meter
