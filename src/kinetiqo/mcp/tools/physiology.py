"""Group C: Physiology & Fitness Modeling Tools."""

from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
import math

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
)
from kinetiqo.analytics.fitness import calculate_ctl_atl_tsb
from kinetiqo.web.vo2max import estimate_vo2max, estimate_vo2max_coggan, classify_vo2max


def kinetiqo_get_fitness_and_freshness(
    repo: Any,
    period_days: int = 90,
    warmup_days: int = 42,
) -> Dict[str, Any]:
    """Retrieve CTL (Fitness), ATL (Fatigue), and TSB (Form) trends calculated from Suffer Score history."""
    try:
        total_days = period_days + warmup_days
        start_date = (date.today() - timedelta(days=total_days)).isoformat()
        end_date = date.today().isoformat()

        activities = repo.get_activities_web(
            limit=2000,
            offset=0,
            start_date=start_date,
            end_date=end_date,
            sort_by="start_date",
            sort_order="ASC",
        )

        # Map to format expected by calculate_ctl_atl_tsb
        act_feed = []
        for a in activities:
            suffer = a.get("suffer_score")
            d_raw = a.get("start_date")
            d_str = d_raw.isoformat() if hasattr(d_raw, "isoformat") else str(d_raw or "")
            if suffer is not None:
                act_feed.append({"start_date": d_str, "suffer_score": suffer})

        calc_res = calculate_ctl_atl_tsb(act_feed, period_days=period_days, warmup_days=warmup_days)

        ctl = round(float(calc_res.get("current_ctl") or 0.0), 1)
        atl = round(float(calc_res.get("current_atl") or 0.0), 1)
        tsb = round(float(calc_res.get("current_tsb") or 0.0), 1)

        # Form interpretation (cautious, descriptive)
        if tsb > 25.0:
            form_label = "Transition / Low Training Load"
        elif 10.0 <= tsb <= 25.0:
            form_label = "Fresh / Peak Performance Zone"
        elif -10.0 <= tsb < 10.0:
            form_label = "Neutral / Optimal Training Maintenance"
        elif -30.0 <= tsb < -10.0:
            form_label = "Productive Overload / Fatigue"
        else:
            form_label = "High Fatigue / Rest Strongly Recommended"

        data = {
            "current_status": {
                "as_of_date": end_date,
                "fitness_ctl": ctl,
                "fatigue_atl": atl,
                "form_tsb": tsb,
                "training_status": form_label,
            },
            "period_days": period_days,
            "warmup_days": warmup_days,
            "history": {
                "dates": calc_res.get("dates", []),
                "fitness": calc_res.get("fitness", []),
                "fatigue": calc_res.get("fatigue", []),
                "form": calc_res.get("form", []),
            },
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed calculating fitness and freshness: {e}")


def kinetiqo_get_ftp_history(repo: Any, athlete_id: int = 1) -> Dict[str, Any]:
    """Retrieve configured athlete FTP and historical 95% of 20-min power breakthroughs."""
    try:
        profile = repo.get_profile(athlete_id) or {}
        configured_ftp = float(profile.get("ftp") or 0.0)
        weight_kg = float(profile.get("weight") or 0.0)

        act_ids = repo.get_activity_ids_by_types(
            types=["Ride", "VirtualRide", "GravelRide"],
            watts_only=True,
        )

        breakthroughs = []
        if act_ids:
            bests_20m = repo.get_best_power_per_activity(act_ids[:150], [1200])
            act_details = {str(a.get("activity_id") or a.get("id")): a for a in repo.get_activities_by_ids(act_ids[:150])}

            for aid, d_map in bests_20m.items():
                p20 = float(d_map.get(1200) or 0.0)
                if p20 > 0:
                    est_ftp = round(p20 * 0.95, 1)
                    act = act_details.get(str(aid), {})
                    breakthroughs.append({
                        "activity_id": str(aid),
                        "activity_name": act.get("name"),
                        "date": str(act.get("start_date") or ""),
                        "best_20m_watts": round(p20, 1),
                        "estimated_ftp_watts": est_ftp,
                        "w_per_kg": round(est_ftp / weight_kg, 2) if weight_kg > 0 else None,
                    })

            breakthroughs.sort(key=lambda x: x["date"], reverse=True)

        data = {
            "configured_ftp_watts": configured_ftp if configured_ftp > 0 else None,
            "athlete_weight_kg": weight_kg if weight_kg > 0 else None,
            "historical_20m_breakthroughs": breakthroughs[:20],
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving FTP history: {e}")


def kinetiqo_get_vo2max_trend(repo: Any, days: int = 90) -> Dict[str, Any]:
    """Compute Storer-Davis (5m MAP) and Coggan (FTP) estimated VO2max trends."""
    try:
        profile = repo.get_profile() or {}
        weight_kg = float(profile.get("weight") or 0.0)
        ftp = float(profile.get("ftp") or 0.0)

        if weight_kg <= 0:
            return create_envelope(
                {"estimates": [], "message": "Athlete weight not configured; cannot calculate ml/kg/min"},
                source="calculated",
                warnings=["Valid athlete weight required for VO2max calculations"],
            )

        coggan_vo2max = estimate_vo2max_coggan(ftp, weight_kg) if ftp > 0 else None

        act_ids = repo.get_activity_ids_by_types(types=["Ride", "VirtualRide", "GravelRide"], watts_only=True)
        estimates = []
        if act_ids:
            bests_5m = repo.get_best_power_per_activity(act_ids[:100], [300])
            act_details = {str(a.get("activity_id") or a.get("id")): a for a in repo.get_activities_by_ids(act_ids[:100])}

            for aid, d_map in bests_5m.items():
                p5 = float(d_map.get(300) or 0.0)
                if p5 >= 150.0:  # Minimum meaningful effort
                    raw_sd = estimate_vo2max(p5, weight_kg)
                    act = act_details.get(str(aid), {})
                    estimates.append({
                        "activity_id": str(aid),
                        "name": act.get("name"),
                        "date": str(act.get("start_date") or ""),
                        "best_5m_watts": round(p5, 1),
                        "storer_davis_vo2max": round(raw_sd, 1),
                        "fitness_tier": classify_vo2max(raw_sd),
                    })

            estimates.sort(key=lambda x: x["date"], reverse=True)

        data = {
            "athlete_weight_kg": weight_kg,
            "coggan_ftp_vo2max": coggan_vo2max,
            "recent_storer_davis_efforts": estimates[:15],
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed calculating VO2max trend: {e}")


def kinetiqo_get_power_skills(repo: Any, athlete_id: int = 1) -> Dict[str, Any]:
    """Benchmark power skills across durations: 5s, 30s, 1m, 5m, 10m, 20m, 1h."""
    durations = [5, 30, 60, 300, 600, 1200, 3600]
    dur_labels = {
        5: "5s (Sprint Neuromuscular)",
        30: "30s (Anaerobic Capacity)",
        60: "1m (Anaerobic Power)",
        300: "5m (VO2max Aerobic Power)",
        600: "10m (FTP Threshold)",
        1200: "20m (Sub-Threshold / FTP)",
        3600: "1h (Aerobic Endurance)",
    }

    try:
        profile = repo.get_profile(athlete_id) or {}
        weight_kg = float(profile.get("weight") or 0.0)

        act_ids = repo.get_activity_ids_by_types(types=["Ride", "VirtualRide", "GravelRide"], watts_only=True)
        if not act_ids:
            return create_envelope(
                {"benchmarks": {str(d): None for d in durations}},
                source="calculated",
                warnings=["No power activities available for benchmark calculations"],
            )

        activity_bests = repo.get_best_power_per_activity(act_ids[:150], durations)
        act_details = {str(a.get("activity_id") or a.get("id")): a for a in repo.get_activities_by_ids(act_ids[:150])}

        benchmarks = {}
        for d in durations:
            best_w = 0.0
            best_aid = None
            for aid, d_map in activity_bests.items():
                val = float(d_map.get(d) or 0.0)
                if val > best_w:
                    best_w = val
                    best_aid = str(aid)

            if best_w > 0 and best_aid and best_aid in act_details:
                act = act_details[best_aid]
                benchmarks[str(d)] = {
                    "duration_seconds": d,
                    "label": dur_labels.get(d, f"{d}s"),
                    "watts": round(best_w, 1),
                    "w_per_kg": round(best_w / weight_kg, 2) if weight_kg > 0 else None,
                    "activity_id": best_aid,
                    "activity_name": act.get("name"),
                    "date": str(act.get("start_date") or ""),
                }
            else:
                benchmarks[str(d)] = None

        return create_envelope({"benchmarks": benchmarks}, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed calculating power skills: {e}")


def kinetiqo_get_training_load_trends(repo: Any, weeks: int = 12) -> Dict[str, Any]:
    """Retrieve rolling 7-day and 28-day training volumes and Acute:Chronic Workload Ratio."""
    try:
        total_days = weeks * 7
        start_date = (date.today() - timedelta(days=total_days)).isoformat()
        end_date = date.today().isoformat()

        activities = repo.get_activities_web(
            limit=2000,
            offset=0,
            start_date=start_date,
            end_date=end_date,
            sort_by="start_date",
            sort_order="ASC",
        )

        # Aggregate daily volumes
        daily_vol: Dict[str, Dict[str, float]] = {}
        curr = date.today() - timedelta(days=total_days)
        while curr <= date.today():
            daily_vol[curr.isoformat()] = {"distance_km": 0.0, "elevation_m": 0.0, "moving_time_s": 0.0, "suffer": 0.0}
            curr += timedelta(days=1)

        for a in activities:
            d_raw = a.get("start_date")
            d_str = d_raw.isoformat()[:10] if hasattr(d_raw, "isoformat") else str(d_raw or "")[:10]
            if d_str in daily_vol:
                daily_vol[d_str]["distance_km"] += float(a.get("distance") or 0.0) / 1000.0
                daily_vol[d_str]["elevation_m"] += float(a.get("total_elevation_gain") or 0.0)
                daily_vol[d_str]["moving_time_s"] += float(a.get("moving_time") or 0.0)
                daily_vol[d_str]["suffer"] += float(a.get("suffer_score") or 0.0)

        # Rolling 7d vs 28d
        sorted_dates = sorted(daily_vol.keys())
        last_7_days = sorted_dates[-7:]
        last_28_days = sorted_dates[-28:]

        acute_7d_dist = sum(daily_vol[d]["distance_km"] for d in last_7_days)
        chronic_28d_dist = sum(daily_vol[d]["distance_km"] for d in last_28_days) / 4.0

        acute_7d_mov = sum(daily_vol[d]["moving_time_s"] for d in last_7_days) / 3600.0
        chronic_28d_mov = (sum(daily_vol[d]["moving_time_s"] for d in last_28_days) / 3600.0) / 4.0

        acwr_distance = round(acute_7d_dist / chronic_28d_dist, 2) if chronic_28d_dist > 0 else None
        acwr_time = round(acute_7d_mov / chronic_28d_mov, 2) if chronic_28d_mov > 0 else None

        data = {
            "acute_7d": {
                "distance_km": round(acute_7d_dist, 1),
                "moving_time_hours": round(acute_7d_mov, 1),
            },
            "chronic_weekly_avg_28d": {
                "distance_km": round(chronic_28d_dist, 1),
                "moving_time_hours": round(chronic_28d_mov, 1),
            },
            "acute_to_chronic_workload_ratio": {
                "by_distance": acwr_distance,
                "by_time": acwr_time,
                "interpretation": "Sweet spot (0.8–1.3)" if (acwr_time and 0.8 <= acwr_time <= 1.3) else "Attention: workload shift",
            },
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed calculating training load trends: {e}")
