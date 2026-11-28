"""Canonical sport taxonomy and activity grouping definitions for Kinetiqo."""

from typing import Any, Dict, List, Optional

# Core sport classifications
CYCLING_OUTDOOR_TYPES = (
    "Ride",
    "EBikeRide",
    "EMountainBikeRide",
    "GravelRide",
    "MountainBikeRide",
    "Velomobile",
    "Handcycle",
)
CYCLING_INDOOR_TYPES = (
    "VirtualRide",
    "IndoorRide",
)
CYCLING_TYPES = CYCLING_OUTDOOR_TYPES + CYCLING_INDOOR_TYPES

RUNNING_OUTDOOR_TYPES = (
    "Run",
    "TrailRun",
)
RUNNING_INDOOR_TYPES = (
    "VirtualRun",
)
RUNNING_TYPES = RUNNING_OUTDOOR_TYPES + RUNNING_INDOOR_TYPES

WALKING_TYPES = (
    "Walk",
    "Hike",
)

SKIING_TYPES = (
    "AlpineSki",
    "BackcountrySki",
    "NordicSki",
    "Snowboard",
)

SWIMMING_TYPES = (
    "Swim",
)

# Infographic and UI grouping metadata
ACTIVITY_GROUPS: Dict[str, Dict[str, Any]] = {
    "walking": {
        "name": "Walking",
        "icon": "🥾",
        "noun": "walk",
        "types": list(WALKING_TYPES),
    },
    "cycling": {
        "name": "Cycling",
        "icon": "🚴",
        "noun": "ride",
        "types": list(CYCLING_TYPES),
    },
    "cycling_indoor": {
        "name": "Cycling (indoor)",
        "icon": "🚴",
        "noun": "ride",
        "types": list(CYCLING_INDOOR_TYPES),
    },
    "cycling_outdoor": {
        "name": "Cycling (outdoor)",
        "icon": "🚴",
        "noun": "ride",
        "types": list(CYCLING_OUTDOOR_TYPES),
    },
    "running": {
        "name": "Running",
        "icon": "🏃",
        "noun": "run",
        "types": ["Run", "VirtualRun", "TrailRun"],
    },
    "skiing": {
        "name": "Skiing",
        "icon": "⛷️",
        "noun": "ski session",
        "types": list(SKIING_TYPES),
    },
    "swimming": {
        "name": "Swimming",
        "icon": "🏊",
        "noun": "swim",
        "types": list(SWIMMING_TYPES),
    },
}

# Aliases for backward compatibility
CYCLING_ACTIVITY_TYPES = list(CYCLING_TYPES)
CYCLING_INDOOR_ACTIVITY_TYPES = list(CYCLING_INDOOR_TYPES)
CYCLING_OUTDOOR_ACTIVITY_TYPES = list(CYCLING_OUTDOOR_TYPES)
OUTDOOR_CYCLING_SPORT_TYPES = CYCLING_OUTDOOR_TYPES
INDOOR_CYCLING_SPORT_TYPES = ("VirtualRide",)
CYCLING_SPORT_TYPES = CYCLING_TYPES
OUTDOOR_RUNNING_SPORT_TYPES = RUNNING_OUTDOOR_TYPES
INDOOR_RUNNING_SPORT_TYPES = RUNNING_INDOOR_TYPES
RUNNING_SPORT_TYPES = RUNNING_TYPES
WALKING_SPORT_TYPES = WALKING_TYPES
SWIMMING_SPORT_TYPES = SWIMMING_TYPES


def normalize_sport_group(group: str) -> str:
    """Normalize user or model sport descriptions into exact ACTIVITY_GROUPS keys."""
    g = (group or "").lower().strip().replace("-", " ").replace("_", " ")
    if "outdoor" in g and any(k in g for k in ("cycl", "bike", "ride")):
        return "cycling_outdoor"
    if any(k in g for k in ("indoor", "virtual", "trainer", "zwift")) and any(k in g for k in ("cycl", "bike", "ride")):
        return "cycling_indoor"
    if any(k in g for k in ("cycl", "bike", "ride")):
        return "cycling"
    if "outdoor" in g and "run" in g:
        return "running_outdoor"
    if ("indoor" in g and "run" in g) or "treadmill" in g or "virtual run" in g:
        return "running_indoor"
    if "run" in g:
        return "running"
    if "walk" in g or "hik" in g:
        return "walking"
    if "ski" in g or "snowboard" in g:
        return "skiing"
    if "swim" in g:
        return "swimming"
    return "cycling"


def normalize_sport_types(sport_types: Optional[Any]) -> Optional[List[str]]:
    """Expand generic or shorthand sport types into canonical database taxonomy.

    Supports explicit outdoor vs indoor distinctions:
      - 'outdoor_cycling', 'outdoor_bike', etc. -> all outdoor cycling types (excludes VirtualRide)
      - 'indoor_cycling', 'indoor_bike', 'virtual_cycling', 'zwift', etc. -> VirtualRide
      - 'cycling', 'bike', 'biking' -> all cycling (outdoor + indoor)
      - 'outdoor_running', 'outdoor_run', 'trail' -> Run, TrailRun
      - 'indoor_running', 'indoor_run', 'treadmill' -> VirtualRun
      - 'running', 'run' -> all running (Run, TrailRun, VirtualRun)
      - 'walking', 'hiking', 'walk', 'hike' -> Walk, Hike
      - 'swimming', 'swim' -> Swim
    """
    if not sport_types:
        return None
    if isinstance(sport_types, str):
        sport_types = [x.strip() for x in sport_types.split(",") if x.strip()]
    if not isinstance(sport_types, (list, tuple, set)):
        return None
    if not sport_types:
        return None

    normalized: List[str] = []
    for s in sport_types:
        s_clean = str(s).strip()
        lower = s_clean.lower().replace("-", "_").replace(" ", "_")
        if lower in (
            "outdoor_cycling", "outdoor_bike", "outdoor_biking", "outdoor_ride",
            "outdoor_rides", "outdoor_cycle", "outdoor_bicycle", "road_bike", "gravel", "mtb",
            "mountain_bike", "outdoor_biking_only", "outdoor_cycling_only",
        ):
            normalized.extend(OUTDOOR_CYCLING_SPORT_TYPES)
        elif lower in (
            "indoor_cycling", "indoor_bike", "indoor_biking", "indoor_ride",
            "indoor_rides", "indoor_cycle", "virtual_cycling", "virtual_bike", "virtual_biking",
            "virtual_ride", "virtual_rides", "virtualride", "zwift", "rouvy", "trainer",
            "turbo", "stationary_trainer", "smart_trainer", "indoor_trainer", "indoor",
        ):
            normalized.extend(INDOOR_CYCLING_SPORT_TYPES)
        elif lower in (
            "cycling", "bike", "biking", "all_cycling", "cycle", "ride", "rides",
            "all_rides", "all_bike", "all_bikes", "all_biking", "bicycle", "bicycles", "bicycling",
        ):
            normalized.extend(CYCLING_SPORT_TYPES)
        elif lower in ("outdoor_running", "outdoor_run", "outdoor_runs", "trail_running", "trail"):
            normalized.extend(OUTDOOR_RUNNING_SPORT_TYPES)
        elif lower in (
            "indoor_running", "indoor_run", "indoor_runs", "virtual_running",
            "virtual_run", "treadmill",
        ):
            normalized.extend(INDOOR_RUNNING_SPORT_TYPES)
        elif lower in ("running", "runs", "all_running", "run"):
            normalized.extend(RUNNING_SPORT_TYPES)
        elif lower in ("walking", "hiking", "all_walking", "walk", "hike", "walks", "hikes"):
            normalized.extend(WALKING_SPORT_TYPES)
        elif lower in ("swimming", "swim", "all_swimming", "swims"):
            normalized.extend(SWIMMING_SPORT_TYPES)
        elif lower in ("skiing", "ski", "all_skiing", "snowboard"):
            normalized.extend(SKIING_TYPES)
        else:
            normalized.append(s_clean)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for item in normalized:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped
