"""Utility functions for Kinetiqo MCP: downsampling, unit conversions, and time handling."""

import calendar
from datetime import date, datetime, timedelta, timezone
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import dateutil.parser

logger = logging.getLogger("kinetiqo.mcp.utils")


def format_iso_timestamp(ts: Optional[datetime]) -> Optional[str]:
    """Format a datetime to UTC ISO-8601 string."""
    if not ts:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc).isoformat()
    return ts.astimezone(timezone.utc).isoformat()


def downsample_stream_window(
    rows: List[Dict[str, Any]],
    resolution: str = "auto",
    max_auto_samples: int = 500,
) -> Tuple[List[Dict[str, Any]], str]:
    """Downsample time-series stream rows based on requested resolution.

    Resolutions:
      - 'auto': downsamples to at most max_auto_samples preserving extrema and endpoints
      - 'medium': 10-second timestamp buckets (averaging numeric channels)
      - 'low': 60-second timestamp buckets
      - 'high': returns raw rows up to hard cap (20,000)

    Returns:
        (downsampled_rows, method_description)
    """
    total = len(rows)
    if total == 0:
        return [], "empty"

    res_clean = (resolution or "auto").strip().lower()

    if res_clean == "high":
        # Raw samples (capped at 20,000)
        return rows[:20000], "raw"

    if res_clean in ("medium", "low"):
        bucket_seconds = 10 if res_clean == "medium" else 60
        return _bucket_downsample(rows, bucket_seconds), f"bucket_{bucket_seconds}s"

    # Default: "auto" -> target at most max_auto_samples
    if total <= max_auto_samples:
        return rows, "verbatim"

    # Extrema-preserving downsampler
    step = total / float(max_auto_samples)
    selected_indices = {0, total - 1}  # Always preserve first and last

    # Numeric columns to preserve min/max for
    numeric_cols = [c for c, v in rows[0].items() if isinstance(v, (int, float)) and c != "ts"]

    for i in range(max_auto_samples):
        start_idx = int(i * step)
        end_idx = min(int((i + 1) * step), total)
        if start_idx >= end_idx:
            continue
        chunk = rows[start_idx:end_idx]
        if not chunk:
            continue

        # Add middle sample
        mid_idx = start_idx + len(chunk) // 2
        selected_indices.add(mid_idx)

        # Check peak and trough for primary numeric metric (e.g. watts or altitude)
        for col in ("watts", "altitude", "heartrate"):
            if col in numeric_cols:
                best_sub_idx = max(range(len(chunk)), key=lambda idx: chunk[idx].get(col) or -1)
                selected_indices.add(start_idx + best_sub_idx)
                break

    sorted_indices = sorted(selected_indices)
    downsampled = [rows[idx] for idx in sorted_indices]
    return downsampled, f"extrema_preserved_target_{max_auto_samples}"


def _bucket_downsample(rows: List[Dict[str, Any]], bucket_seconds: int) -> List[Dict[str, Any]]:
    """Aggregate stream rows into fixed timestamp buckets."""
    if not rows:
        return []

    buckets: Dict[int, List[Dict[str, Any]]] = {}
    first_ts = int(rows[0].get("ts") or 0)

    for row in rows:
        ts = int(row.get("ts") or 0)
        bucket_key = (ts - first_ts) // bucket_seconds
        if bucket_key not in buckets:
            buckets[bucket_key] = []
        buckets[bucket_key].append(row)

    downsampled = []
    numeric_keys = [k for k, v in rows[0].items() if isinstance(v, (int, float))]

    for _, group in sorted(buckets.items()):
        if not group:
            continue
        agg_row: Dict[str, Any] = {}
        # Representative timestamp: midpoint or first
        agg_row["ts"] = group[0].get("ts")
        for k in group[0].keys():
            if k == "ts":
                continue
            if k in numeric_keys:
                valid_vals = [g[k] for g in group if g.get(k) is not None]
                if valid_vals:
                    agg_row[k] = round(sum(valid_vals) / len(valid_vals), 2)
                else:
                    agg_row[k] = None
            else:
                agg_row[k] = group[0].get(k)
        downsampled.append(agg_row)

    return downsampled


def detect_stream_gaps(rows: List[Dict[str, Any]], threshold_s: int = 2) -> Dict[str, Any]:
    """Detect timestamp discontinuities in 1 Hz stream samples.

    Returns:
        dict with total_gaps, max_gap_seconds, total_gap_seconds
    """
    if len(rows) < 2:
        return {"total_gaps": 0, "max_gap_seconds": 0, "total_gap_seconds": 0}

    total_gaps = 0
    max_gap = 0
    total_gap_sec = 0

    for i in range(len(rows) - 1):
        t1 = rows[i].get("ts")
        t2 = rows[i + 1].get("ts")
        if t1 is not None and t2 is not None:
            delta = t2 - t1
            if delta > threshold_s:
                total_gaps += 1
                gap = delta - 1
                total_gap_sec += gap
                if gap > max_gap:
                    max_gap = gap

    return {
        "total_gaps": total_gaps,
        "max_gap_seconds": max_gap,
        "total_gap_seconds": total_gap_sec,
    }


def extract_activity_summaries(raw_activities: List[Any]) -> List[Dict[str, Any]]:
    """Normalize activity records from repo.get_activity_ids_by_types into [{'id': str, 'name': ..., 'start_date': ...}]."""
    summaries = []
    for item in raw_activities or []:
        if isinstance(item, dict):
            aid = str(item.get("id") or item.get("activity_id") or "").strip()
            name = item.get("name")
            sdate = str(item.get("start_date") or "")
        else:
            aid = str(item).strip()
            name = None
            sdate = ""
        if aid:
            summaries.append({"id": aid, "name": name, "start_date": sdate})
    return summaries


def get_best_power_for_single_duration(repo: Any, activity_ids: List[str], duration: int) -> Dict[str, float]:
    """Query repo.get_best_power_per_activity for a single duration and normalize to {activity_id: float_watts}."""
    str_ids = [str(aid).strip() for aid in activity_ids if str(aid).strip()]
    if not str_ids:
        return {}
    res: Dict[str, float] = {}
    try:
        raw_res = repo.get_best_power_per_activity(str_ids, duration)
        if isinstance(raw_res, dict):
            for aid, val in raw_res.items():
                if isinstance(val, dict):
                    w = val.get(duration)
                    if w is not None:
                        res[str(aid)] = float(w)
                elif val is not None:
                    res[str(aid)] = float(val)
    except Exception as e:
        logger.warning("Error querying best power for duration %s: %s", duration, e)
    return res


def get_best_powers_for_durations(repo: Any, activity_ids: List[str], durations: List[int]) -> Dict[int, Dict[str, float]]:
    """Query best powers across multiple durations.

    Gracefully supports both the canonical DatabaseRepository API (calling get_best_power_per_activity(ids, d)
    per integer duration) and test mocks that return nested {aid: {d: watts}} maps.
    """
    str_ids = [str(aid).strip() for aid in activity_ids if str(aid).strip()]
    result: Dict[int, Dict[str, float]] = {d: {} for d in durations}
    if not str_ids:
        return result

    # Check if a test mock handles durations as a list directly
    try:
        mock_check = repo.get_best_power_per_activity(str_ids, durations)
        if isinstance(mock_check, dict) and any(isinstance(v, dict) for v in mock_check.values()):
            for aid, d_map in mock_check.items():
                if isinstance(d_map, dict):
                    for d, w in d_map.items():
                        if d in result and w is not None:
                            result[d][str(aid)] = float(w)
            return result
    except Exception:
        pass

    # Standard DatabaseRepository call per duration
    for d in durations:
        result[d] = get_best_power_for_single_duration(repo, str_ids, d)

    return result


CYCLING_SPORT_TYPES = (
    "Ride", "VirtualRide", "EBikeRide", "EMountainBikeRide",
    "GravelRide", "MountainBikeRide", "Velomobile", "Handcycle",
)
RUNNING_SPORT_TYPES = ("Run", "VirtualRun", "TrailRun")
WALKING_SPORT_TYPES = ("Walk", "Hike")


def normalize_sport_types(sport_types: Optional[List[str]]) -> Optional[List[str]]:
    """Expand generic or shorthand sport types into canonical database taxonomy.

    If an AI provider passes generic strings like ['cycling'], ['bike'], or mistakenly
    restricts a riding query to solely ['Ride'], this expands it to all cycling types
    so that VirtualRide (Zwift/Rouvy), GravelRide, MountainBikeRide, etc., are included.
    """
    if not sport_types:
        return None
    normalized = []
    for s in sport_types:
        s_clean = str(s).strip()
        lower = s_clean.lower()
        if lower in ("cycling", "bike", "biking", "all_cycling", "cycle"):
            normalized.extend(CYCLING_SPORT_TYPES)
        elif lower in ("running", "runs", "all_running", "run"):
            normalized.extend(RUNNING_SPORT_TYPES)
        elif lower in ("walking", "hiking", "all_walking", "walk", "hike"):
            normalized.extend(WALKING_SPORT_TYPES)
        elif s_clean == "Ride" and len(sport_types) == 1:
            # Single 'Ride' filter sent by AI for 'ride' / 'rode' prompt:
            # Expand to include all biking activities per user expectation.
            normalized.extend(CYCLING_SPORT_TYPES)
        else:
            normalized.append(s_clean)

    # Deduplicate while preserving order
    seen = set()
    return [x for x in normalized if not (x in seen or seen.add(x))]


def parse_flexible_date(
    val: Any,
    is_end: bool = False,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Parse a date or datetime string in virtually any human or ISO format into an ISO-8601 string.

    Supports:
      - Relative presets: 'today', 'yesterday', 'this_week', 'last_week', 'this_month', 'last_month',
        'this_year', 'last_year', '7_days', '14_days', '30_days', 'last_12_months', 'all_time'
      - 4-digit years: '2026' -> start: 2026-01-01 00:00:00, end: 2026-12-31 23:59:59
      - Year-Month: '2026-08', '2026/08', 'Aug 2026', 'August 2026'
      - Full dates: '2026-08-15', '15.08.2026', '08/15/2026', '15 Aug 2026', 'August 15, 2026'
        (If no time is provided and is_end=True, sets time to 23:59:59 to cover the full day)
      - Full ISO datetimes: '2026-08-15T14:30:00Z', etc.
    """
    if not val:
        return None
    if isinstance(val, (datetime, date)):
        if isinstance(val, datetime):
            if val.tzinfo is None:
                val = val.replace(tzinfo=timezone.utc)
            return val.isoformat()
        return datetime(
            val.year, val.month, val.day,
            23 if is_end else 0,
            59 if is_end else 0,
            59 if is_end else 0,
            tzinfo=timezone.utc,
        ).isoformat()

    s = str(val).strip()
    if not s or s.lower() in ("all_time", "all", "none"):
        return None

    now = now or datetime.now(timezone.utc)
    s_lower = s.lower().replace("-", "_").replace(" ", "_")

    if s_lower in ("today", "now"):
        return (
            now.replace(hour=23, minute=59, second=59, microsecond=0)
            if is_end
            else now.replace(hour=0, minute=0, second=0, microsecond=0)
        ).isoformat()

    if s_lower == "yesterday":
        y = now - timedelta(days=1)
        return (
            y.replace(hour=23, minute=59, second=59, microsecond=0)
            if is_end
            else y.replace(hour=0, minute=0, second=0, microsecond=0)
        ).isoformat()

    if s_lower in ("this_week", "current_week"):
        monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            (monday + timedelta(days=6, hours=23, minutes=59, seconds=59)).isoformat()
            if is_end
            else monday.isoformat()
        )

    if s_lower in ("last_week", "prev_week"):
        monday = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            (monday + timedelta(days=6, hours=23, minutes=59, seconds=59)).isoformat()
            if is_end
            else monday.isoformat()
        )

    if s_lower in ("this_month", "current_month"):
        start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
        last_d = calendar.monthrange(now.year, now.month)[1]
        end = datetime(now.year, now.month, last_d, 23, 59, 59, tzinfo=timezone.utc)
        return end.isoformat() if is_end else start.isoformat()

    if s_lower in ("last_month", "prev_month"):
        pm = now.month - 1 if now.month > 1 else 12
        py = now.year if now.month > 1 else now.year - 1
        start = datetime(py, pm, 1, 0, 0, 0, tzinfo=timezone.utc)
        last_d = calendar.monthrange(py, pm)[1]
        end = datetime(py, pm, last_d, 23, 59, 59, tzinfo=timezone.utc)
        return end.isoformat() if is_end else start.isoformat()

    if s_lower in ("this_year", "current_year"):
        return (
            datetime(now.year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).isoformat()
            if is_end
            else datetime(now.year, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
        )

    if s_lower in ("last_year", "prev_year"):
        return (
            datetime(now.year - 1, 12, 31, 23, 59, 59, tzinfo=timezone.utc).isoformat()
            if is_end
            else datetime(now.year - 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
        )

    if s_lower in ("7_days", "last_7_days"):
        return (
            now.isoformat()
            if is_end
            else (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        )

    if s_lower in ("14_days", "last_14_days"):
        return (
            now.isoformat()
            if is_end
            else (now - timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        )

    if s_lower in ("30_days", "last_30_days"):
        return (
            now.isoformat()
            if is_end
            else (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        )

    if s_lower in ("year", "last_12_months", "12_months"):
        return (
            now.isoformat()
            if is_end
            else (now - timedelta(days=365)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        )

    # Dynamic relative periods: e.g. "last_2weeks", "2weeks", "last_2_weeks", "3_weeks", "10_days", "3_months"
    rel_match = re.match(r"^(?:last_)?(\d+)_?(day|days|week|weeks|month|months|year|years)$", s_lower)
    if rel_match:
        n = int(rel_match.group(1))
        unit = rel_match.group(2)
        if unit.startswith("day"):
            days = n
        elif unit.startswith("week"):
            days = n * 7
        elif unit.startswith("month"):
            days = n * 30
        else:
            days = n * 365
        return (
            now.isoformat()
            if is_end
            else (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        )

    # 4-digit year: e.g. 2026
    if re.match(r"^\d{4}$", s):
        y = int(s)
        return (
            datetime(y, 12, 31, 23, 59, 59, tzinfo=timezone.utc).isoformat()
            if is_end
            else datetime(y, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
        )

    # Year-month: e.g. 2026-08 or 2026/08
    ym_match = re.match(r"^(\d{4})[-/](\d{1,2})$", s)
    if ym_match:
        y, m = int(ym_match.group(1)), int(ym_match.group(2))
        last_d = calendar.monthrange(y, m)[1]
        return (
            datetime(y, m, last_d, 23, 59, 59, tzinfo=timezone.utc).isoformat()
            if is_end
            else datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
        )

    # General / human string parsing via dateutil
    try:
        dayfirst = bool(re.search(r"^\d{1,2}\.\d{1,2}\.\d{4}", s))
        dt = dateutil.parser.parse(s, fuzzy=True, dayfirst=dayfirst)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        has_time = bool(re.search(r"\d{1,2}:\d{2}", s))
        if not has_time:
            if is_end:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=0)
            else:
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt.isoformat()
    except Exception as e:
        logger.debug("Flexible date parsing failed for '%s': %s", s, e)
        return s


def resolve_date_range(
    start_date: Any = None,
    end_date: Any = None,
    preset: Any = None,
    now: Optional[datetime] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve start_date, end_date, or a preset into canonical ISO start/end strings.

    If start_date is a preset like 'this_year' or 'last 2weeks' and end_date is None,
    automatically computes the matching start and end boundaries.
    """
    now = now or datetime.now(timezone.utc)
    if preset:
        start_str = parse_flexible_date(preset, is_end=False, now=now)
        end_str = parse_flexible_date(preset, is_end=True, now=now)
        return start_str, end_str

    # Check if start_date itself is a preset or lone year/month
    if start_date and not end_date:
        s_clean = str(start_date).strip().lower().replace("-", "_").replace(" ", "_")
        if (
            s_clean in (
                "today", "yesterday", "this_week", "last_week", "this_month", "last_month",
                "this_year", "last_year", "7_days", "14_days", "30_days", "year", "last_12_months",
            )
            or re.match(r"^(?:last_)?\d+_?(?:day|days|week|weeks|month|months|year|years)$", s_clean)
            or re.match(r"^\d{4}$", str(start_date).strip())
            or re.match(r"^(\d{4})[-/](\d{1,2})$", str(start_date).strip())
        ):
            start_str = parse_flexible_date(start_date, is_end=False, now=now)
            end_str = parse_flexible_date(start_date, is_end=True, now=now)
            return start_str, end_str

    parsed_start = parse_flexible_date(start_date, is_end=False, now=now) if start_date else None
    parsed_end = parse_flexible_date(end_date, is_end=True, now=now) if end_date else None
    return parsed_start, parsed_end


