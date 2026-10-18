"""KOM (King of the Mountains) verification and cache management for Kinetiqo.

Strava's athlete-wide KOMs endpoint (``GET /api/v3/athletes/{id}/koms``) provides all
currently held King of the Mountains segment efforts for the athlete. During
synchronization (``SyncService.sync()``), Kinetiqo fetches these verified efforts
in a single paginated query and records the count per activity in ``verified_koms.json``.

This module manages the local cache (``verified_koms.json``) of verified KOM counts
per activity to ensure the UI displays only genuine, verified KOMs directly from
local data without inflating the count with non-PR achievements (2nd/3rd PRs and top-10 ribbons)
and without making any extra on-demand API calls to Strava from web endpoints.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import logging

from kinetiqo.web.stats import CYCLING_ACTIVITY_TYPES

logger = logging.getLogger(__name__)

# Default location for the verified KOMs JSON cache
POSTERS_CACHE_DIR = Path(__file__).resolve().parent / "web" / "posters-cache"
VERIFIED_KOMS_FILE = POSTERS_CACHE_DIR / "verified_koms.json"
VERIFIED_TROPHIES_FILE = POSTERS_CACHE_DIR / "verified_trophies.json"


def get_verified_koms_path() -> Path:
    """Return the absolute Path to the verified KOMs cache file."""
    return VERIFIED_KOMS_FILE


def get_verified_trophies_path() -> Path:
    """Return the absolute Path to the verified trophies cache file."""
    return VERIFIED_TROPHIES_FILE


def load_verified_koms(cache_path: Optional[Path] = None) -> Dict[str, int]:
    """Load verified KOM counts from JSON cache.

    Returns a dict mapping ``activity_id`` (as str) to ``int`` count of verified KOMs.
    Returns an empty dict if the file does not exist or fails to parse.
    """
    path = cache_path or get_verified_koms_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): int(v) for k, v in data.items()}
    except Exception as e:
        logger.warning("Failed to load verified KOMs cache from %s: %e", path, e)
    return {}


def save_verified_koms(data: Dict[str, int], cache_path: Optional[Path] = None) -> None:
    """Save verified KOM counts dictionary to the JSON cache file."""
    path = cache_path or get_verified_koms_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_path.replace(path)
    except Exception as e:
        logger.exception("Failed to save verified KOMs cache to %s: %e", path, e)


def load_verified_trophies(cache_path: Optional[Path] = None) -> Dict[str, Dict[str, int]]:
    """Load verified trophies (ranks 1-10) breakdown from JSON cache.

    Returns a dict mapping ``activity_id`` to a dict of ``{"1": count, ..., "10": count}``.
    """
    path = cache_path or get_verified_trophies_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                res: Dict[str, Dict[str, int]] = {}
                for k, v in data.items():
                    if isinstance(v, dict):
                        res[str(k)] = {str(rk): int(rv) for rk, rv in v.items()}
                return res
    except Exception as e:
        logger.warning("Failed to load verified trophies cache from %s: %e", path, e)
    return {}


def save_verified_trophies(data: Dict[str, Dict[str, int]], cache_path: Optional[Path] = None) -> None:
    """Save verified trophies dictionary to the JSON cache file."""
    path = cache_path or get_verified_trophies_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_path.replace(path)
    except Exception as e:
        logger.exception("Failed to save verified trophies cache to %s: %e", path, e)


def is_kom_candidate_activity(activity: Dict[str, Any]) -> bool:
    """Return True if activity is a cycling activity with achievements beyond PRs.

    Activities with ``achievement_count <= pr_count`` cannot have any KOMs
    and require zero network calls.
    """
    sport = (
        activity.get("sport")
        or activity.get("sport_type")
        or activity.get("type")
        or ""
    )
    if sport not in CYCLING_ACTIVITY_TYPES:
        return False

    ach_count = int(activity.get("achievement_count") or 0)
    pr_count = int(activity.get("pr_count") or 0)
    return ach_count > pr_count


def extract_koms_from_activity_detail(detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract segment efforts representing true King of the Mountain achievements.

    Inspects ``segment_efforts`` for ``kom_rank == 1`` or achievements where
    ``type in ('overall', 'kom', 'cr', ...)`` or ``type_id in (1, 2)`` and ``rank == 1``.
    """
    if not isinstance(detail, dict):
        return []
    efforts = detail.get("segment_efforts", [])
    koms: List[Dict[str, Any]] = []
    for effort in efforts:
        if not isinstance(effort, dict):
            continue
        try:
            kr = int(effort.get("kom_rank") or effort.get("overall_rank") or effort.get("rank") or 0)
            if kr == 1:
                koms.append(effort)
                continue
        except (ValueError, TypeError):
            pass

        for ach in effort.get("achievements", []):
            if isinstance(ach, dict):
                try:
                    r = int(ach.get("rank") or 0)
                except (ValueError, TypeError):
                    r = 0
                if r == 1:
                    ach_type = str(ach.get("type", "")).strip().lower()
                    type_id = ach.get("type_id")
                    if (
                        ach_type in ("overall", "kom", "cr", "top10", "top_10", "segment", "leaderboard", "trophy")
                        or type_id in (1, 2)
                        or (not ach_type and type_id != 3)
                    ) and ach_type not in ("pr", "year_pr"):
                        koms.append(effort)
                        break
    return koms


def count_koms_in_activity_detail(detail: Dict[str, Any]) -> int:
    """Return the total number of verified KOMs in an activity's detail payload."""
    return len(extract_koms_from_activity_detail(detail))


def record_activity_koms(
    activity_id: Any,
    koms_count: int,
    cache_path: Optional[Path] = None,
) -> None:
    """Record an activity's verified KOM count into the local cache."""
    cache = load_verified_koms(cache_path)
    cache[str(activity_id)] = max(0, int(koms_count))
    save_verified_koms(cache, cache_path)


def extract_trophies_from_segment_efforts(efforts: List[Dict[str, Any]]) -> Dict[int, int]:
    """Extract placement achievements (1st to 10th place) from a list of segment efforts.

    Returns a dict mapping rank ``1..10`` to the count of times that rank was achieved.
    """
    ranks: Dict[int, int] = {r: 0 for r in range(1, 11)}
    if not isinstance(efforts, list):
        return ranks

    for effort in efforts:
        if not isinstance(effort, dict):
            continue

        placed_rank: Optional[int] = None

        # 1. Check direct rank fields on effort (kom_rank, overall_rank, leaderboard_rank, rank)
        for key in ("kom_rank", "overall_rank", "leaderboard_rank", "rank"):
            val = effort.get(key)
            if val is not None:
                try:
                    r_val = int(val)
                    if 1 <= r_val <= 10:
                        placed_rank = r_val
                        break
                except (ValueError, TypeError):
                    pass

        # 2. Check achievements array if direct rank was not found
        if placed_rank is None:
            achievements = effort.get("achievements")
            if isinstance(achievements, list):
                for ach in achievements:
                    if not isinstance(ach, dict):
                        continue
                    r_raw = ach.get("rank")
                    if r_raw is None:
                        continue
                    try:
                        r = int(r_raw)
                    except (ValueError, TypeError):
                        continue

                    if not (1 <= r <= 10):
                        continue

                    t = str(ach.get("type", "")).strip().lower()
                    type_id = ach.get("type_id")

                    # In Strava API:
                    # type_id 1 is overall rank (top 10), type_id 2 is secondary overall rank
                    # type_id 3 is PR. type "pr" or "year_pr" is personal record.
                    # We match overall / top-10 leaderboard achievements.
                    is_overall = (
                        t in ("overall", "kom", "cr", "top10", "top_10", "segment", "leaderboard", "trophy")
                        or type_id in (1, 2)
                        or (not t and type_id != 3)
                    )

                    if is_overall and t not in ("pr", "year_pr"):
                        placed_rank = r
                        break

        if placed_rank is not None and 1 <= placed_rank <= 10:
            ranks[placed_rank] += 1

    return ranks


def extract_trophies_from_activity_detail(detail: Dict[str, Any]) -> Dict[int, int]:
    """Extract placement achievements (1st to 10th place) from an activity's detail payload."""
    if not isinstance(detail, dict):
        return {r: 0 for r in range(1, 11)}
    return extract_trophies_from_segment_efforts(detail.get("segment_efforts", []))


def record_activity_trophies(
    activity_id: Any,
    trophies: Any,
    cache_path: Optional[Path] = None,
) -> None:
    """Record an activity's verified trophies breakdown into the local cache."""
    if isinstance(trophies, list):
        trophies_dict = extract_trophies_from_segment_efforts(trophies)
    elif isinstance(trophies, dict):
        trophies_dict = trophies
    else:
        trophies_dict = {}

    cache = load_verified_trophies(cache_path)
    entry = {
        str(r): max(0, int(trophies_dict.get(r, trophies_dict.get(str(r), 0))))
        for r in range(1, 11)
    }
    entry["scanned"] = 1
    cache[str(activity_id)] = entry
    save_verified_trophies(cache, cache_path)

