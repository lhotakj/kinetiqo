"""Fondo-o-meter computation for the Fondo-o-meter infographic page.

Computes Fondo Analysis concentric circles, KOM counts, PR counts,
and summary metrics from activities filtered by year and activity group.
"""

from datetime import datetime, date
from typing import List, Dict, Any, Optional
import json
import math

from kinetiqo.web.stats import (
    ACTIVITY_GROUPS,
    CYCLING_ACTIVITY_TYPES,
    parse_activity_date,
)
from kinetiqo.koms import (
    load_verified_koms,
    load_verified_trophies,
    extract_trophies_from_segment_efforts,
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
        label = f"{max_km:.1f} km"
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
    outer_label = f"{max_km:.1f} km"
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
    year: Any,
    group_key: str = 'cycling',
    verified_koms: Optional[Dict[str, int]] = None,
    verified_trophies: Optional[Dict[str, Dict[str, int]]] = None,
) -> Dict[str, Any]:
    """Compute summary statistics for the Fondo-o-meter Infographic.

    Filters activities by year (or all time) and sport group, then calculates:
      - Total activities, total distance (km), total elevation (m)
      - Number of true verified KOMs (from verified_koms cache)
      - Number of PRs (pr_count)
      - Number of Thropies (placements 1st through 10th place)
      - Longest activity details
      - Concentric radial chart circles for qualifying fondo activities

    Returns:
        Dict[str, Any]: Full payload ready for JSON response and rendering.
    """
    group_info = ACTIVITY_GROUPS.get(group_key, ACTIVITY_GROUPS.get('cycling', {}))
    allowed_types = group_info.get('types', [])
    noun = group_info.get('noun', 'ride')
    threshold_km = get_sport_threshold(group_key)

    # Load verified KOMs cache if not explicitly provided
    if verified_koms is None:
        verified_koms_map = load_verified_koms()
    else:
        verified_koms_map = {str(k): int(v) for k, v in verified_koms.items()}

    # Load verified trophies cache if not explicitly provided
    if verified_trophies is None:
        verified_trophies_map = load_verified_trophies()
    else:
        verified_trophies_map = {
            str(k): {str(rk): int(rv) for rk, rv in v.items()}
            for k, v in verified_trophies.items()
        }

    is_all_time = str(year).strip().lower() in ('all', 'all_time', '0')
    target_year: Optional[int] = None
    if not is_all_time:
        try:
            target_year = int(year)
        except (ValueError, TypeError):
            is_all_time = True

    filtered_activities = []
    koms_count = 0
    prs_count = 0
    trophies_ranks: Dict[int, int] = {r: 0 for r in range(1, 11)}
    longest_act = None
    max_dist_m = 0.0

    for act in activities:
        # Date filter
        if not is_all_time:
            d = parse_activity_date(act.get('start_date'))
            if not d or d.year != target_year:
                continue

        # Sport type filter
        act_type = act.get('type') or act.get('sport_type') or act.get('sport') or ''
        if allowed_types and act_type not in allowed_types:
            continue

        filtered_activities.append(act)

        # Distance & Longest
        dist_m = float(act.get('distance') or 0.0)
        if dist_m > max_dist_m:
            max_dist_m = dist_m
            longest_act = act

        # PRs Aggregation
        pr_c = int(act.get('pr_count') or 0)
        if pr_c == 0 and act.get('segment_efforts'):
            pr_c = sum(1 for eff in act['segment_efforts'] if isinstance(eff, dict) and eff.get('pr_rank') in (1, 2, 3, '1', '2', '3'))
        prs_count += pr_c

        # KOMs Aggregation (strictly on cycling activities, using synced verified KOMs)
        act_koms = 0
        if act_type in CYCLING_ACTIVITY_TYPES:
            explicit_koms = act.get('koms_count') if act.get('koms_count') is not None else act.get('koms')
            if explicit_koms is not None:
                act_koms = max(0, int(explicit_koms))
            else:
                act_id_str = str(act.get('id') or act.get('activity_id') or '')
                if act_id_str and act_id_str in verified_koms_map:
                    act_koms = max(0, verified_koms_map[act_id_str])

        # Thropies Aggregation (placements 1st through 10th place)
        act_id_str = str(act.get('id') or act.get('activity_id') or '')
        explicit_trophies = act.get('trophies_ranks') or act.get('trophies')

        if isinstance(explicit_trophies, str):
            try:
                explicit_trophies = json.loads(explicit_trophies)
            except Exception:
                explicit_trophies = None

        act_ranks = {r: 0 for r in range(1, 11)}
        has_act_trophies = False

        if isinstance(explicit_trophies, dict):
            for r in range(1, 11):
                val = explicit_trophies.get(r, explicit_trophies.get(str(r), 0))
                try:
                    act_ranks[r] = max(act_ranks[r], int(val))
                    if act_ranks[r] > 0:
                        has_act_trophies = True
                except (ValueError, TypeError):
                    pass

        if act.get('segment_efforts'):
            eff_trophies = extract_trophies_from_segment_efforts(act['segment_efforts'])
            for r in range(1, 11):
                act_ranks[r] = max(act_ranks[r], eff_trophies[r])
                if act_ranks[r] > 0:
                    has_act_trophies = True

        if act_id_str and act_id_str in verified_trophies_map:
            act_tr = verified_trophies_map[act_id_str]
            if isinstance(act_tr, dict):
                for r in range(1, 11):
                    val = act_tr.get(r, act_tr.get(str(r), 0))
                    try:
                        act_ranks[r] = max(act_ranks[r], int(val))
                        if act_ranks[r] > 0:
                            has_act_trophies = True
                    except (ValueError, TypeError):
                        pass

        # Harmonize with verified KOM count on rank 1
        if act_koms > 0:
            act_ranks[1] = max(act_ranks[1], act_koms)
            has_act_trophies = True
        elif act_type in CYCLING_ACTIVITY_TYPES and act_ranks[1] > 0:
            act_koms = act_ranks[1]

        koms_count += act_koms

        if has_act_trophies:
            for r in range(1, 11):
                trophies_ranks[r] += act_ranks[r]

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

    total_trophies = sum(trophies_ranks.values())

    return {
        'year': 'all' if is_all_time else target_year,
        'group': group_key,
        'group_name': group_info.get('name', 'Cycling'),
        'group_icon': group_info.get('icon', '🚴'),
        'group_noun': noun,
        'threshold_km': threshold_km,
        'total_activities': len(filtered_activities),
        'koms_count': koms_count,
        'prs_count': prs_count,
        'fondos_count': len(qualifying_acts),
        'trophies_count': total_trophies,
        'trophies': {
            'total': total_trophies,
            'ranks': {str(r): trophies_ranks[r] for r in range(1, 11)},
        },
        'longest_ride': longest_info,
        'fondo': {
            'threshold_km': threshold_km,
            'total_qualifying': len(qualifying_acts),
            'circles': fondo_circles,
        }
    }


# Backwards compatibility alias
compute_achievements = compute_fondo_o_meter
