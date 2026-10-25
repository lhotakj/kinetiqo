"""Group C: Physiology & Fitness Modeling Tools."""

from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
import math
import statistics

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
)
from kinetiqo.mcp.utils import (
    extract_activity_summaries,
    get_best_power_for_single_duration,
    get_best_powers_for_durations,
    normalize_sport_types,
    CYCLING_SPORT_TYPES,
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


def compute_coggan_zones(ftp: float, weight_kg: float = 0.0) -> List[Dict[str, Any]]:
    """Compute Coggan 7-Zone power model boundaries, percentages, and W/kg from athlete FTP."""
    zones_def = [
        ("Z1", "Active Recovery", 0, 55, "< 55% FTP", "Easy recovery spinning, post-interval recovery, promotes circulation with minimal fatigue."),
        ("Z2", "Endurance", 56, 75, "56% - 75% FTP", "All-day aerobic base pace, builds mitochondrial density and lipid oxidation capacity."),
        ("Z3", "Tempo", 76, 90, "76% - 90% FTP", "Rhythmic aerobic endurance, sustainable for 1-3 hours, conversation in broken sentences."),
        ("Sweet Spot", "Sweet Spot Sub-Zone", 88, 94, "88% - 94% FTP", "High aerobic stimulus with manageable neuro-muscular strain; optimal base training efficiency."),
        ("Z4", "Lactate Threshold", 91, 105, "91% - 105% FTP", "FTP maintenance and raising, 10-30 min intervals, onset of blood lactate accumulation."),
        ("Z5", "VO2max", 106, 120, "106% - 120% FTP", "Maximal aerobic ceiling expansion, 3-8 min intervals or 30/30s micro-intervals, high cadence (>95 RPM)."),
        ("Z6", "Anaerobic Capacity", 121, 150, "121% - 150% FTP", "Short intense efforts (30s to 2 min), severe glycolytic acidosis."),
        ("Z7", "Neuromuscular Power", 151, None, "> 150% FTP", "Maximal sprint efforts (< 15-20 seconds), maximum motor unit recruitment, non-aerobic."),
    ]
    res = []
    for code, name, min_pct, max_pct, pct_range, desc in zones_def:
        min_w = round(ftp * (min_pct / 100.0), 1) if min_pct > 0 else 0.0
        max_w = round(ftp * (max_pct / 100.0), 1) if max_pct is not None else None
        min_w_kg = round(min_w / weight_kg, 2) if (weight_kg > 0 and min_w > 0) else (0.0 if weight_kg > 0 else None)
        max_w_kg = round(max_w / weight_kg, 2) if (weight_kg > 0 and max_w is not None) else None
        range_str = f"{min_w:.0f}W - {max_w:.0f}W" if max_w is not None else f">{min_w:.0f}W"
        w_kg_str = f"{min_w_kg:.2f} - {max_w_kg:.2f} W/kg" if (min_w_kg is not None and max_w_kg is not None) else (f">{min_w_kg:.2f} W/kg" if min_w_kg is not None else None)
        res.append({
            "zone": code,
            "name": name,
            "pct_ftp_range": pct_range,
            "min_watts": min_w,
            "max_watts": max_w,
            "watts_range": range_str,
            "min_w_per_kg": min_w_kg,
            "max_w_per_kg": max_w_kg,
            "w_per_kg_range": w_kg_str,
            "description": desc,
        })
    return res


def kinetiqo_get_ftp_history(repo: Any, athlete_id: int = 1) -> Dict[str, Any]:
    """Retrieve configured athlete FTP, Coggan 7-Zone boundaries, heart rate zones, and historical 20-min power breakthroughs."""
    try:
        try:
            profile = repo.get_profile() or {}
        except TypeError:
            profile = repo.get_profile(athlete_id) or {}
        configured_ftp = float(profile.get("ftp") or 0.0)
        weight_kg = float(profile.get("weight") or 0.0)

        raw_acts = repo.get_activity_ids_by_types(
            types=list(CYCLING_SPORT_TYPES),
            watts_only=True,
        ) or []

        summaries = extract_activity_summaries(raw_acts)
        str_ids = [s["id"] for s in summaries]

        breakthroughs = []
        if str_ids:
            bests_20m = get_best_power_for_single_duration(repo, str_ids[:150], 1200)

            act_details = {s["id"]: s for s in summaries if s.get("name")}
            missing = [aid for aid in bests_20m.keys() if aid not in act_details]
            if missing and hasattr(repo, "get_activities_by_ids"):
                try:
                    for a in repo.get_activities_by_ids(missing):
                        aid_key = str(a.get("id") or a.get("activity_id"))
                        act_details[aid_key] = {
                            "id": aid_key,
                            "name": a.get("name"),
                            "start_date": str(a.get("start_date") or ""),
                        }
                except Exception:
                    pass

            for aid, p20 in bests_20m.items():
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

        effective_ftp = configured_ftp if configured_ftp > 0 else (breakthroughs[0]["estimated_ftp_watts"] if breakthroughs else 0.0)
        coggan_zones = compute_coggan_zones(effective_ftp, weight_kg) if effective_ftp > 0 else []

        vo2max_target = None
        if effective_ftp > 0:
            z5_min = round(effective_ftp * 1.06, 1)
            z5_max = round(effective_ftp * 1.20, 1)
            vo2max_target = {
                "zone": "Z5",
                "name": "VO2max",
                "pct_ftp_range": "106% - 120% FTP",
                "min_watts": z5_min,
                "max_watts": z5_max,
                "watts_range": f"{z5_min:.0f}W - {z5_max:.0f}W",
                "w_per_kg_range": f"{round(z5_min / weight_kg, 2)} - {round(z5_max / weight_kg, 2)} W/kg" if weight_kg > 0 else None,
                "cadence_recommendation": "High cadence (95-105+ RPM) to maximize cardiac stroke volume while sparing peripheral muscular torque.",
                "evidence_based_protocols": [
                    "Long intervals: 4-5 x 4-5 min @ 108-115% FTP with 3-4 min active recovery in Z1 (1:1 or 2:1 ratio)",
                    "Micro-bursts: 30s ON @ 115-125% FTP / 30s OFF @ 50% FTP (2-3 sets of 8-10 reps)",
                    "Target accumulated time in Zone 5: 15-25 minutes per session",
                    "Weekly frequency: 1-2 sessions weekly within a polarized 80/20 distribution with 48-72h recovery between sessions",
                ],
            }

        # Check observed max heart rate across activities for 5-zone HR
        max_hr = 0
        try:
            if hasattr(repo, "get_activities_web"):
                acts_hr = repo.get_activities_web(limit=50, sort_by="max_heartrate", sort_order="DESC") or []
                for a in acts_hr:
                    mhr = int(a.get("max_heartrate") or 0)
                    if 100 <= mhr <= 230:
                        max_hr = max(max_hr, mhr)
        except Exception:
            pass

        hr_zones = []
        if max_hr > 0:
            hr_zones = [
                {"zone": "Z1", "name": "Active Recovery", "pct_max_hr": "< 60%", "min_bpm": 0, "max_bpm": round(max_hr * 0.60), "description": "Very light aerobic, promotes recovery and blood flow."},
                {"zone": "Z2", "name": "Aerobic / Endurance", "pct_max_hr": "60% - 70%", "min_bpm": round(max_hr * 0.60) + 1, "max_bpm": round(max_hr * 0.70), "description": "All-day endurance base, burns fat, conversation pace."},
                {"zone": "Z3", "name": "Tempo", "pct_max_hr": "70% - 80%", "min_bpm": round(max_hr * 0.70) + 1, "max_bpm": round(max_hr * 0.80), "description": "Aerobic fitness, brisk pace, speaking in short sentences."},
                {"zone": "Z4", "name": "Lactate Threshold", "pct_max_hr": "80% - 90%", "min_bpm": round(max_hr * 0.80) + 1, "max_bpm": round(max_hr * 0.90), "description": "Hard sustained effort, heavy breathing, lactate accumulation threshold."},
                {"zone": "Z5", "name": "VO2max / Maximum", "pct_max_hr": "90% - 100%", "min_bpm": round(max_hr * 0.90) + 1, "max_bpm": max_hr, "description": "Maximal cardiovascular capacity, panting, sustained for only a few minutes."},
            ]

        data = {
            "configured_ftp_watts": configured_ftp if configured_ftp > 0 else None,
            "athlete_weight_kg": weight_kg if weight_kg > 0 else None,
            "effective_ftp_watts": effective_ftp if effective_ftp > 0 else None,
            "is_ftp_estimated": configured_ftp <= 0 and effective_ftp > 0,
            "power_zones_coggan": coggan_zones,
            "vo2max_target": vo2max_target,
            "heart_rate_zones": hr_zones,
            "observed_max_heartrate": max_hr if max_hr > 0 else None,
            "historical_20m_breakthroughs": breakthroughs[:20],
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving FTP history: {e}")


def kinetiqo_get_vo2max_trend(repo: Any, days: int = 90) -> Dict[str, Any]:
    """Compute Storer-Davis (5m MAP) and Coggan (FTP) estimated VO2max trends and actionable interval targets."""
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

        since_date = (date.today() - timedelta(days=days)).isoformat() if days else None
        raw_acts = repo.get_activity_ids_by_types(types=["Ride", "VirtualRide", "GravelRide"], since_date=since_date, watts_only=True) or []
        summaries = extract_activity_summaries(raw_acts)
        str_ids = [s["id"] for s in summaries]

        estimates = []
        if str_ids:
            bests_5m = get_best_power_for_single_duration(repo, str_ids[:100], 300)
            act_details = {s["id"]: s for s in summaries if s.get("name")}
            missing = [aid for aid in bests_5m.keys() if aid not in act_details]
            if missing and hasattr(repo, "get_activities_by_ids"):
                try:
                    for a in repo.get_activities_by_ids(missing):
                        aid_key = str(a.get("id") or a.get("activity_id"))
                        act_details[aid_key] = {
                            "id": aid_key,
                            "name": a.get("name"),
                            "start_date": str(a.get("start_date") or ""),
                        }
                except Exception:
                    pass

            for aid, p5 in bests_5m.items():
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

        vo2_min_w = round(ftp * 1.06, 1) if ftp > 0 else None
        vo2_max_w = round(ftp * 1.20, 1) if ftp > 0 else None
        vo2_min_wkg = round(vo2_min_w / weight_kg, 2) if (vo2_min_w and weight_kg > 0) else None
        vo2_max_wkg = round(vo2_max_w / weight_kg, 2) if (vo2_max_w and weight_kg > 0) else None

        data = {
            "athlete_weight_kg": weight_kg,
            "coggan_ftp_vo2max": coggan_vo2max,
            "vo2max_target_power": {
                "ftp_watts": ftp if ftp > 0 else None,
                "zone_5_min_watts": vo2_min_w,
                "zone_5_max_watts": vo2_max_w,
                "watts_range": f"{vo2_min_w:.0f}W - {vo2_max_w:.0f}W" if (vo2_min_w and vo2_max_w) else None,
                "w_per_kg_range": f"{vo2_min_wkg:.2f} - {vo2_max_wkg:.2f} W/kg" if (vo2_min_wkg and vo2_max_wkg) else None,
            },
            "training_guidance": {
                "what_vo2max_means": "VO2max represents your physiological aerobic ceiling—the maximal volume of oxygen your cardiovascular system can transport to working muscles per minute (ml/kg/min). Training at VO2max expands cardiac stroke volume, blood plasma volume, capillary density, and mitochondrial aerobic enzymes.",
                "target_zone": "Zone 5 (106% - 120% of FTP)",
                "cadence_recommendation": "High cadence (95-105+ RPM) to minimize muscular torque fatigue and maximize cardiac output.",
                "evidence_based_protocols": [
                    "Long intervals: 4-5 x 4-5 min @ 108-115% FTP with 3-4 min active recovery in Z1 (1:1 or 2:1 ratio)",
                    "Micro-bursts: 30s ON @ 115-125% FTP / 30s OFF @ 50% FTP (2-3 sets of 8-10 repetitions)",
                    "Accumulated time in Zone 5: Target 15-25 minutes total per session",
                    "Weekly frequency: 1-2 sessions weekly within a polarized 80/20 distribution (80% Zone 2 endurance base, 20% high intensity) with 48-72h recovery between sessions",
                ],
            },
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
        try:
            profile = repo.get_profile() or {}
        except TypeError:
            profile = repo.get_profile(athlete_id) or {}
        weight_kg = float(profile.get("weight") or 0.0)

        raw_acts = repo.get_activity_ids_by_types(types=list(CYCLING_SPORT_TYPES), watts_only=True) or []
        summaries = extract_activity_summaries(raw_acts)
        str_ids = [s["id"] for s in summaries]

        if not str_ids:
            return create_envelope(
                {"benchmarks": {str(d): None for d in durations}},
                source="calculated",
                warnings=["No power activities available for benchmark calculations"],
            )

        multi_bests = get_best_powers_for_durations(repo, str_ids[:150], durations)

        act_details = {s["id"]: s for s in summaries if s.get("name")}
        winner_aids = set()
        for d in durations:
            for aid, val in multi_bests.get(d, {}).items():
                if val > 0:
                    winner_aids.add(aid)
        missing = [aid for aid in winner_aids if aid not in act_details]
        if missing and hasattr(repo, "get_activities_by_ids"):
            try:
                for a in repo.get_activities_by_ids(missing):
                    aid_key = str(a.get("id") or a.get("activity_id"))
                    act_details[aid_key] = {
                        "id": aid_key,
                        "name": a.get("name"),
                        "start_date": str(a.get("start_date") or ""),
                    }
            except Exception:
                pass

        benchmarks = {}
        for d in durations:
            dur_bests = multi_bests.get(d, {})
            best_w = 0.0
            best_aid = None
            for aid, val in dur_bests.items():
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


def _parse_activity_date(d_raw: Any) -> Optional[date]:
    """Helper to parse activity date whether it is a datetime, date, or string."""
    if isinstance(d_raw, datetime):
        return d_raw.date()
    if isinstance(d_raw, date):
        return d_raw
    if isinstance(d_raw, str) and len(d_raw) >= 10:
        try:
            return date.fromisoformat(d_raw[:10])
        except Exception:
            return None
    return None


def kinetiqo_get_weekly_training_profile(
    repo: Any,
    athlete_id: int = 1,
    year: Optional[int] = None,
    weeks: int = 12,
    sport_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute multi-week training load profiles grouped by ISO calendar weeks, surfacing power, volume, and habits."""
    try:
        types = normalize_sport_types(sport_types) or list(CYCLING_SPORT_TYPES)
        if year is not None:
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"
        else:
            lookback = max(1, min(weeks, 52))
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=lookback * 7)).isoformat()

        activities = repo.get_activities_web(
            limit=5000,
            offset=0,
            types=types,
            start_date=start_date,
            end_date=end_date,
            sort_by="start_date",
            sort_order="ASC",
        ) or []

        weeks_map: Dict[str, Dict[str, Any]] = {}
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_counts = {day: 0 for day in day_names}

        for a in activities:
            d = _parse_activity_date(a.get("start_date"))
            if not d:
                continue

            day_counts[day_names[d.weekday()]] += 1
            iso_year, iso_week, _ = d.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"

            if week_key not in weeks_map:
                try:
                    w_mon = date.fromisocalendar(iso_year, iso_week, 1).isoformat()
                    w_sun = date.fromisocalendar(iso_year, iso_week, 7).isoformat()
                except Exception:
                    w_mon = d.isoformat()
                    w_sun = d.isoformat()

                weeks_map[week_key] = {
                    "week_key": week_key,
                    "iso_year": iso_year,
                    "iso_week": iso_week,
                    "start_date": w_mon,
                    "end_date": w_sun,
                    "activity_count": 0,
                    "distance_km": 0.0,
                    "elevation_m": 0.0,
                    "moving_time_s": 0.0,
                    "moving_time_hours": 0.0,
                    "kilojoules": 0.0,
                    "power_time_s": 0.0,
                    "power_work_sum": 0.0,
                    "weighted_work_sum": 0.0,
                    "average_watts": None,
                    "weighted_average_watts": None,
                }

            w = weeks_map[week_key]
            dist_m = float(a.get("distance") or 0.0)
            elev_m = float(a.get("total_elevation_gain") or a.get("elevation_gain") or 0.0)
            mov_s = float(a.get("moving_time") or 0.0)
            avg_w = float(a["average_watts"]) if a.get("average_watts") is not None else None
            weighted_w = float(a["weighted_average_watts"]) if a.get("weighted_average_watts") is not None else None
            kj = float(a["kilojoules"]) if a.get("kilojoules") is not None else ((avg_w * mov_s / 1000.0) if avg_w and mov_s else 0.0)

            w["activity_count"] += 1
            w["distance_km"] += dist_m / 1000.0
            w["elevation_m"] += elev_m
            w["moving_time_s"] += mov_s
            w["kilojoules"] += kj

            if avg_w is not None and mov_s > 0:
                w["power_time_s"] += mov_s
                w["power_work_sum"] += avg_w * mov_s

            if weighted_w is not None and mov_s > 0:
                w["weighted_work_sum"] += weighted_w * mov_s

        weekly_history = []
        for w_key in sorted(weeks_map.keys()):
            w = weeks_map[w_key]
            w["distance_km"] = round(w["distance_km"], 1)
            w["elevation_m"] = round(w["elevation_m"], 1)
            w["moving_time_hours"] = round(w["moving_time_s"] / 3600.0, 2)
            w["kilojoules"] = round(w["kilojoules"], 1)

            if w["power_time_s"] > 0:
                w["average_watts"] = round(w["power_work_sum"] / w["power_time_s"], 1)
            if w["power_time_s"] > 0 and w["weighted_work_sum"] > 0:
                w["weighted_average_watts"] = round(w["weighted_work_sum"] / w["power_time_s"], 1)

            del w["moving_time_s"]
            del w["power_time_s"]
            del w["power_work_sum"]
            del w["weighted_work_sum"]
            weekly_history.append(w)

        best_power_week = None
        best_distance_week = None
        best_elevation_week = None

        if weekly_history:
            power_candidates = [w for w in weekly_history if (w.get("kilojoules") or 0.0) > 0.0 or w.get("average_watts")]
            if power_candidates:
                best_power_week = max(power_candidates, key=lambda x: (x.get("kilojoules") or 0.0, x.get("average_watts") or 0.0))
            best_distance_week = max(weekly_history, key=lambda x: x["distance_km"])
            best_elevation_week = max(weekly_history, key=lambda x: x["elevation_m"])

        total_activities = len(activities)
        num_weeks = max(len(weekly_history), 1)

        distances = [w["distance_km"] for w in weekly_history if w["distance_km"] > 0]
        elevations = [w["elevation_m"] for w in weekly_history if w["elevation_m"] > 0]

        median_dist = round(statistics.median(distances), 1) if distances else 0.0
        mean_dist = round(sum(w["distance_km"] for w in weekly_history) / num_weeks, 1) if weekly_history else 0.0

        median_elev = round(statistics.median(elevations), 1) if elevations else 0.0
        mean_elev = round(sum(w["elevation_m"] for w in weekly_history) / num_weeks, 1) if weekly_history else 0.0

        mean_hours = round(sum(w["moving_time_hours"] for w in weekly_history) / num_weeks, 2) if weekly_history else 0.0

        day_pcts = {
            day: {
                "count": count,
                "percentage": round((count / total_activities * 100.0), 1) if total_activities > 0 else 0.0,
            }
            for day, count in day_counts.items()
        }

        data = {
            "period": {
                "year": year,
                "weeks_requested": weeks if year is None else len(weekly_history),
                "evaluated_weeks_count": len(weekly_history),
                "total_activities": total_activities,
            },
            "peak_weeks": {
                "best_power_week": best_power_week,
                "best_distance_week": best_distance_week,
                "best_elevation_week": best_elevation_week,
            },
            "typical_week_profile": {
                "median_weekly_distance_km": median_dist,
                "mean_weekly_distance_km": mean_dist,
                "median_weekly_elevation_m": median_elev,
                "mean_weekly_elevation_m": mean_elev,
                "mean_weekly_moving_time_hours": mean_hours,
                "typical_rides_per_week": round(total_activities / num_weeks, 1),
                "day_of_week_distribution": day_pcts,
            },
            "weekly_history": weekly_history,
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed calculating weekly training profile: {e}")


def kinetiqo_analyze_recovery_turnaround(
    repo: Any,
    min_distance_km: float = 100.0,
    sport_group: str = "cycling",
    lookback_days: int = 365,
) -> Dict[str, Any]:
    """Analyze athlete recovery turnaround time and TSB fatigue dissipation following endurance milestones."""
    try:
        types = ["Ride", "VirtualRide", "GravelRide"] if sport_group.lower().startswith("cycl") else ["Run", "Walk"]
        start_date = (date.today() - timedelta(days=lookback_days)).isoformat()
        end_date = date.today().isoformat()

        activities = repo.get_activities_web(
            limit=5000,
            offset=0,
            types=types,
            start_date=start_date,
            end_date=end_date,
            sort_by="start_date",
            sort_order="ASC",
        ) or []

        act_feed = []
        for a in activities:
            suffer = a.get("suffer_score")
            d_raw = a.get("start_date")
            d_str = d_raw.isoformat() if hasattr(d_raw, "isoformat") else str(d_raw or "")
            if suffer is not None:
                act_feed.append({"start_date": d_str, "suffer_score": suffer})

        tsb_dates = []
        tsb_form = []
        try:
            tsb_calc = calculate_ctl_atl_tsb(act_feed, period_days=lookback_days, warmup_days=42)
            tsb_dates = tsb_calc.get("dates", [])
            tsb_form = tsb_calc.get("form", [])
        except Exception:
            pass

        date_to_tsb = {d: f for d, f in zip(tsb_dates, tsb_form)}

        threshold_m = min_distance_km * 1000.0
        milestones = []
        all_act_by_date = []
        for a in activities:
            d = _parse_activity_date(a.get("start_date"))
            if d:
                all_act_by_date.append((d, a))

        all_act_by_date.sort(key=lambda x: x[0])

        rest_days_list = []
        hard_days_list = []
        tsb_rebound_list = []

        for idx, (m_date, act) in enumerate(all_act_by_date):
            dist_m = float(act.get("distance") or 0.0)
            if dist_m < threshold_m:
                continue

            aid = str(act.get("activity_id") or act.get("id"))
            mov_s = float(act.get("moving_time") or 0.0)
            elev_m = float(act.get("total_elevation_gain") or act.get("elevation_gain") or 0.0)
            suffer = int(act["suffer_score"]) if act.get("suffer_score") is not None else None

            subsequent = [pair for pair in all_act_by_date[idx + 1:] if pair[0] > m_date]

            days_to_next = None
            next_act_name = None
            if subsequent:
                next_d, next_act = subsequent[0]
                days_to_next = (next_d - m_date).days
                next_act_name = next_act.get("name")
                rest_days_list.append(days_to_next)

            days_to_next_hard = None
            subsequent_hard = [
                pair for pair in subsequent
                if (pair[1].get("suffer_score") or 0) >= 50
                or (float(pair[1].get("distance") or 0.0) >= 50000.0)
                or (float(pair[1].get("moving_time") or 0.0) >= 5400.0)
            ]
            if subsequent_hard:
                hard_d, _ = subsequent_hard[0]
                days_to_next_hard = (hard_d - m_date).days
                hard_days_list.append(days_to_next_hard)

            tsb_rebound = None
            if date_to_tsb:
                for check_day_offset in range(1, 21):
                    check_d = (m_date + timedelta(days=check_day_offset)).isoformat()
                    val = date_to_tsb.get(check_d)
                    if val is not None and val >= 0.0:
                        tsb_rebound = check_day_offset
                        tsb_rebound_list.append(tsb_rebound)
                        break

            milestones.append({
                "activity_id": aid,
                "name": act.get("name") or "Endurance Milestone",
                "date": m_date.isoformat(),
                "distance_km": round(dist_m / 1000.0, 1),
                "elevation_m": round(elev_m, 1),
                "moving_time_hours": round(mov_s / 3600.0, 2),
                "suffer_score": suffer,
                "rest_days_until_next_activity": days_to_next,
                "next_activity_name": next_act_name,
                "days_until_next_hard_workout": days_to_next_hard,
                "tsb_rebound_days": tsb_rebound,
            })

        med_rest = round(statistics.median(rest_days_list), 1) if rest_days_list else None
        avg_rest = round(sum(rest_days_list) / len(rest_days_list), 1) if rest_days_list else None
        med_hard = round(statistics.median(hard_days_list), 1) if hard_days_list else None
        avg_tsb_rebound = round(sum(tsb_rebound_list) / len(tsb_rebound_list), 1) if tsb_rebound_list else None

        if med_rest is not None:
            guidance = f"Following a {min_distance_km:.0f}km+ ride, the athlete typically takes {med_rest} day(s) before training again"
            if med_hard is not None:
                guidance += f", and {med_hard} day(s) before attempting another hard or long workout."
            else:
                guidance += "."
            if avg_tsb_rebound is not None:
                guidance += f" Training Stress Balance (TSB Form) typically rebounds back to fresh within ~{avg_tsb_rebound:.0f} days."
        else:
            guidance = f"No subsequent activities found after qualifying {min_distance_km:.0f}km+ rides in the evaluated period."

        data = {
            "sport_group": sport_group,
            "min_distance_km": min_distance_km,
            "lookback_days": lookback_days,
            "qualifying_milestone_count": len(milestones),
            "turnaround_summary": {
                "median_rest_days_until_next_activity": med_rest,
                "average_rest_days_until_next_activity": avg_rest,
                "median_days_until_next_hard_workout": med_hard,
                "average_tsb_rebound_days": avg_tsb_rebound,
                "guidance": guidance,
            },
            "milestones": milestones,
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed analyzing recovery turnaround: {e}")
