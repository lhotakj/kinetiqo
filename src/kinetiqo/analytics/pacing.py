"""Pure pacing analysis and aerobic decoupling calculations."""

from typing import Any, Dict, List, Optional


def calculate_pacing_splits(
    stream_data: List[Dict[str, Any]],
    split_basis: str = "moving_time",
    num_splits: int = 2,
) -> Dict[str, Any]:
    """Calculate pacing splits and aerobic decoupling across an activity.

    :param stream_data: List of sample dicts containing 'watts', 'heartrate', 'distance', 'altitude'.
    :param split_basis: Basis for splits: 'moving_time' (samples count) or 'distance'.
    :param num_splits: Number of equal splits (default 2 for halves).
    :return: Dict containing 'splits' list and 'aerobic_decoupling_pct'.
    """
    if not stream_data or num_splits < 2:
        return {"splits": [], "aerobic_decoupling_pct": None}

    n = len(stream_data)
    chunk_size = n // num_splits
    if chunk_size == 0:
        return {"splits": [], "aerobic_decoupling_pct": None}

    splits = []
    for s_idx in range(num_splits):
        start_i = s_idx * chunk_size
        end_i = (s_idx + 1) * chunk_size if s_idx < num_splits - 1 else n
        sub_samples = stream_data[start_i:end_i]

        watts_list = [float(r["watts"]) for r in sub_samples if r.get("watts") is not None]
        hr_list = [float(r["heartrate"]) for r in sub_samples if r.get("heartrate") is not None]

        dist_start = float(sub_samples[0].get("distance") or 0.0)
        dist_end = float(sub_samples[-1].get("distance") or 0.0)
        split_distance = max(0.0, dist_end - dist_start)

        elev_gain = 0.0
        prev_alt = None
        for r in sub_samples:
            alt = r.get("altitude")
            if alt is not None:
                alt = float(alt)
                if prev_alt is not None and alt > prev_alt:
                    elev_gain += alt - prev_alt
                prev_alt = alt

        avg_watts = round(sum(watts_list) / len(watts_list), 1) if watts_list else None
        avg_hr = round(sum(hr_list) / len(hr_list), 1) if hr_list else None

        splits.append({
            "split_index": s_idx + 1,
            "sample_count": len(sub_samples),
            "distance_m": round(split_distance, 1),
            "elevation_gain_m": round(elev_gain, 1),
            "average_watts": avg_watts,
            "average_heartrate": avg_hr,
        })

    # Aerobic decoupling across split 1 vs split 2
    decoupling_pct = None
    if len(splits) >= 2:
        s1 = splits[0]
        s2 = splits[1]
        w1, hr1 = s1.get("average_watts"), s1.get("average_heartrate")
        w2, hr2 = s2.get("average_watts"), s2.get("average_heartrate")

        if w1 and hr1 and w2 and hr2 and hr1 > 0 and hr2 > 0 and w2 > 0:
            ef1 = w1 / hr1
            ef2 = w2 / hr2
            if ef2 > 0:
                # Decoupling is typically defined as (EF1 / EF2 - 1) * 100
                decoupling_pct = round(((ef1 / ef2) - 1.0) * 100.0, 2)

    return {
        "splits": splits,
        "aerobic_decoupling_pct": decoupling_pct,
    }
