"""Fast GPS track decimation for map visualization.

Implements an O(N) distance-based sampling algorithm. For map display
at typical zoom levels, sub-15-metre precision is invisible to the
user, so dropping intermediate points that lie within a small threshold
dramatically reduces payload size and browser rendering time.
"""

import math
from typing import Dict, List

# Scale 0–10 mapping to distance thresholds in metres.
# Level 0 = 0.0m (no decimation, raw GPS stream retained).
GPS_SIMPLIFICATION_THRESHOLDS: Dict[int, float] = {
    0: 0.0,       # Level 0: No simplification (original raw track data)
    1: 3.0,       # Level 1: 3 m threshold
    2: 6.0,       # Level 2: 6 m threshold
    3: 10.0,      # Level 3: 10 m threshold
    4: 15.0,      # Level 4: 15 m threshold
    5: 20.0,      # Level 5: 20 m threshold
    6: 30.0,      # Level 6: 30 m threshold
    7: 45.0,      # Level 7: 45 m threshold
    8: 60.0,      # Level 8: 60 m threshold
    9: 80.0,      # Level 9: 80 m threshold
    10: 100.0,    # Level 10: 100 m threshold (max simplification)
}


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def simplify_track(coords: List[List[float]], threshold_meters: float = 15.0) -> List[List[float]]:
    """Distance-based GPS track decimation.

    Keeps the first and last point, and any intermediate point whose
    straight-line distance from the last *kept* point exceeds the
    threshold. This is O(N) and ~100x faster than Douglas-Peucker
    for the visual quality needed on a web map.

    :param coords: List of ``[lat, lng]`` pairs ordered by time.
    :param threshold_meters: Minimum distance (in metres) between kept
        points. 10-20 m is ideal for cycling/running map overlays.
    :return: Decimated list of ``[lat, lng]`` pairs.
    """
    if len(coords) <= 2:
        return coords

    simplified: List[List[float]] = [coords[0]]
    last_kept = coords[0]

    for point in coords[1:-1]:
        if _haversine_m(last_kept[0], last_kept[1], point[0], point[1]) >= threshold_meters:
            simplified.append(point)
            last_kept = point

    simplified.append(coords[-1])  # always preserve terminus
    return simplified
