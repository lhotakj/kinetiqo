"""Utility functions for Kinetiqo MCP: downsampling, unit conversions, and time handling."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import math


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
