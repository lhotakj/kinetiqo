"""Pure functions for Fitness (CTL), Fatigue (ATL), and Form (TSB) calculations."""

from typing import Any, Dict, List, Optional, Union
import pandas as pd


def calculate_ctl_atl_tsb(
    activities: List[Dict[str, Any]],
    period_days: Optional[Union[int, str]] = 90,
    warmup_days: int = 42,
) -> Dict[str, Any]:
    """Calculate daily CTL (42-day EWMA), ATL (7-day EWMA), and TSB (Form).

    :param activities: List of activity dicts containing 'start_date' and 'suffer_score'.
    :param period_days: Number of days to return in the window (int), or 'all' for full history.
    :param warmup_days: Number of historical days prior to period to include for EWMA warm-up.
    :return: Dict containing 'dates', 'fitness', 'fatigue', 'form', 'current_ctl', 'current_atl', 'current_tsb'.
    """
    if not activities:
        return {
            "dates": [],
            "fitness": [],
            "fatigue": [],
            "form": [],
            "current_ctl": 0.0,
            "current_atl": 0.0,
            "current_tsb": 0.0,
            "trend_ctl": 0.0,
        }

    df = pd.DataFrame(activities)
    if "suffer_score" not in df.columns or "start_date" not in df.columns:
        return {
            "dates": [],
            "fitness": [],
            "fatigue": [],
            "form": [],
            "current_ctl": 0.0,
            "current_atl": 0.0,
            "current_tsb": 0.0,
            "trend_ctl": 0.0,
        }

    df["date"] = pd.to_datetime(df["start_date"], utc=True)
    df["suffer_score"] = pd.to_numeric(df["suffer_score"], errors="coerce").fillna(0.0)
    df = df.set_index("date")

    # Resample daily summing suffer score
    daily = df[["suffer_score"]].resample("D").sum().fillna(0.0)

    # Calculate Fitness (CTL) - 42-day EWMA
    daily["fitness"] = daily["suffer_score"].ewm(span=42, adjust=False).mean()

    # Calculate Fatigue (ATL) - 7-day EWMA
    daily["fatigue"] = daily["suffer_score"].ewm(span=7, adjust=False).mean()

    # Calculate Form (TSB)
    daily["form"] = daily["fitness"] - daily["fatigue"]

    # Filter to start from the first non-zero activity date
    first_active = daily[daily["suffer_score"] > 0].index.min()
    if pd.notna(first_active):
        daily = daily[daily.index >= first_active]

    # If period_days is an integer, trim view window while keeping historical warm-up in the calculation
    if period_days is not None and str(period_days).lower() != "all":
        try:
            p_days = int(period_days)
            if p_days > 0 and len(daily) > p_days:
                daily = daily.iloc[-p_days:]
        except ValueError:
            pass

    if daily.empty:
        return {
            "dates": [],
            "fitness": [],
            "fatigue": [],
            "form": [],
            "current_ctl": 0.0,
            "current_atl": 0.0,
            "current_tsb": 0.0,
            "trend_ctl": 0.0,
        }

    last_row = daily.iloc[-1]
    trend_ctl = 0.0
    if len(daily) >= 7:
        trend_ctl = float(last_row["fitness"] - daily.iloc[-7]["fitness"])

    return {
        "dates": daily.index.strftime("%Y-%m-%d").tolist(),
        "fitness": daily["fitness"].round(1).tolist(),
        "fatigue": daily["fatigue"].round(1).tolist(),
        "form": daily["form"].round(1).tolist(),
        "current_ctl": round(float(last_row["fitness"]), 1),
        "current_atl": round(float(last_row["fatigue"]), 1),
        "current_tsb": round(float(last_row["form"]), 1),
        "trend_ctl": round(trend_ctl, 2),
    }
