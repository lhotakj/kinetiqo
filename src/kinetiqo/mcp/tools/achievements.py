"""Group D: Achievements & Milestone Tools."""

from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_PERMISSION_DENIED,
)
from kinetiqo.koms import load_verified_koms, load_verified_trophies


def kinetiqo_get_verified_koms(repo: Any, athlete_id: int = 1) -> Dict[str, Any]:
    """Retrieve locally verified King of the Mountains (KOM/QOM) crowns and activities."""
    try:
        koms_map = load_verified_koms()
        total_koms = sum(koms_map.values())

        act_ids = [str(k) for k in koms_map.keys()]
        activities = repo.get_activities_by_ids(act_ids) if act_ids else []
        act_map = {str(a.get("activity_id") or a.get("id")): a for a in activities}

        detailed = []
        for aid, count in koms_map.items():
            if count > 0:
                act = act_map.get(str(aid), {})
                detailed.append({
                    "activity_id": str(aid),
                    "name": act.get("name") or "Unnamed Activity",
                    "date": str(act.get("start_date") or ""),
                    "verified_koms_count": count,
                })

        detailed.sort(key=lambda x: x["date"], reverse=True)

        data = {
            "total_verified_koms": total_koms,
            "activities_with_koms_count": len(detailed),
            "activities": detailed,
        }
        return create_envelope(data, source="local_cache")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving verified KOMs: {e}")


def kinetiqo_get_segment_trophies(repo: Any, athlete_id: int = 1) -> Dict[str, Any]:
    """Retrieve scanned top-10 segment ribbons breakdown (ranks 1st through 10th place)."""
    try:
        trophies_cache = load_verified_trophies()
        total_trophies = {str(r): 0 for r in range(1, 11)}

        for aid, r_map in trophies_cache.items():
            for r in range(1, 11):
                total_trophies[str(r)] += int(r_map.get(str(r), 0))

        podium_count = total_trophies["1"] + total_trophies["2"] + total_trophies["3"]
        top10_count = sum(total_trophies.values())

        data = {
            "total_podium_trophies": podium_count,
            "total_top10_ribbons": top10_count,
            "ranks_breakdown": total_trophies,
            "scanned_activities_count": len(trophies_cache),
        }
        return create_envelope(data, source="local_cache")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving segment trophies: {e}")


def kinetiqo_get_fondo_milestones(
    repo: Any,
    sport_group: str = "cycling",
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Retrieve Gran Fondo and distance milestone achievements (e.g. 100k+, double metrics)."""
    threshold_km = 100.0 if sport_group.startswith("cycling") else 42.195
    threshold_m = threshold_km * 1000.0

    try:
        start_d = f"{year}-01-01" if year else None
        end_d = f"{year}-12-31" if year else None

        types = ["Ride", "VirtualRide", "GravelRide"] if sport_group.startswith("cycling") else ["Run", "Walk"]
        activities = repo.get_activities_web(
            limit=2000,
            offset=0,
            types=types,
            start_date=start_d,
            end_date=end_d,
            sort_by="distance",
            sort_order="DESC",
        )

        qualifying = [a for a in activities if float(a.get("distance") or 0.0) >= threshold_m]

        fondos = []
        for a in qualifying:
            dist_km = round(float(a.get("distance") or 0.0) / 1000.0, 1)
            elev_m = round(float(a.get("total_elevation_gain") or 0.0), 1)
            mov_h = round(float(a.get("moving_time") or 0.0) / 3600.0, 2)
            fondos.append({
                "activity_id": str(a.get("activity_id") or a.get("id")),
                "name": a.get("name"),
                "date": str(a.get("start_date") or ""),
                "distance_km": dist_km,
                "elevation_m": elev_m,
                "moving_time_hours": mov_h,
            })

        data = {
            "sport_group": sport_group,
            "year": year or "all_time",
            "threshold_km": threshold_km,
            "total_qualifying_milestones": len(fondos),
            "longest_activity": fondos[0] if fondos else None,
            "activities": fondos,
        }
        return create_envelope(data, source="calculated")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving fondo milestones: {e}")


def kinetiqo_get_training_goals(repo: Any, athlete_id: int = 1) -> Dict[str, Any]:
    """Retrieve active training goals, current progress, and remaining required pace."""
    try:
        goals = repo.get_goals(athlete_id) or []
        today = date.today()

        # Date boundaries for week, month, year
        start_week = today - timedelta(days=today.weekday())
        start_month = date(today.year, today.month, 1)
        start_year = date(today.year, 1, 1)

        parsed_goals = []
        for g in goals:
            if "activity_type_id" in g:
                type_id = int(g.get("activity_type_id") or 1)
                sport_name = "cycling" if type_id == 1 else "walking"
                field_mappings = [
                    ("weekly", "distance", g.get("weekly_distance_goal")),
                    ("monthly", "distance", g.get("monthly_distance_goal")),
                    ("yearly", "distance", g.get("yearly_distance_goal")),
                    ("weekly", "elevation", g.get("weekly_elevation_goal")),
                    ("monthly", "elevation", g.get("monthly_elevation_goal")),
                    ("yearly", "elevation", g.get("yearly_elevation_goal")),
                ]
                for p, m, val in field_mappings:
                    if val is not None and float(val) > 0:
                        parsed_goals.append({
                            "period": p,
                            "metric": m,
                            "goal_type": sport_name,
                            "target": float(val),
                        })
            else:
                period = str(g.get("period") or "").lower()
                metric = str(g.get("metric") or "distance").lower()
                sport = str(g.get("goal_type") or "cycling").lower()
                target = float(g.get("target") or 0.0)
                if target > 0 and period:
                    parsed_goals.append({
                        "period": period,
                        "metric": metric,
                        "goal_type": sport,
                        "target": target,
                    })

        summary = []
        for item in parsed_goals:
            period = item["period"]
            metric = item["metric"]
            sport = item["goal_type"]
            target = item["target"]

            if period == "weekly":
                start_d = start_week.isoformat()
            elif period == "monthly":
                start_d = start_month.isoformat()
            else:
                start_d = start_year.isoformat()

            types = ["Ride", "VirtualRide", "GravelRide"] if "cycling" in sport else ["Walk", "Hike"]
            totals = repo.get_activities_totals(types=types, start_date=start_d, end_date=today.isoformat()) or {}

            if metric == "elevation":
                actual = float(totals.get("total_elevation") or totals.get("elevation") or 0.0)
            else:
                dist_m = float(totals.get("total_distance") or totals.get("distance") or 0.0)
                actual = dist_m / 1000.0

            remaining = max(0.0, target - actual)
            percent = round((actual / target) * 100.0, 1)

            summary.append({
                "period": period,
                "sport": sport,
                "metric": metric,
                "target": target,
                "actual": round(actual, 1),
                "remaining": round(remaining, 1),
                "percent_completed": percent,
                "is_completed": actual >= target,
            })

        return create_envelope({"goals": summary}, source="local_db")
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed retrieving training goals: {e}")


def kinetiqo_update_training_goals(
    repo: Any,
    athlete_id: int,
    period: str,
    goal_type: str,
    target: float,
    metric: str = "distance",
    allow_write: bool = False,
) -> Dict[str, Any]:
    """Update athlete distance or elevation goal (requires KINETIQO_MCP_ALLOW_PROFILE_WRITE=1)."""
    if not allow_write:
        return create_error_envelope(
            ERROR_PERMISSION_DENIED,
            "Updating training goals requires KINETIQO_MCP_ALLOW_PROFILE_WRITE=1",
        )

    try:
        norm_period = (period or "").lower()
        norm_metric = (metric or "distance").lower()
        norm_sport = (goal_type or "cycling").lower()
        act_type_id = 2 if ("walk" in norm_sport or "hike" in norm_sport) else 1

        if hasattr(repo, "upsert_goal"):
            existing_goals = repo.get_goals(athlete_id) if hasattr(repo, "get_goals") else []
            existing_row = next((r for r in (existing_goals or []) if int(r.get("activity_type_id", 0)) == act_type_id), {})

            w_dist = existing_row.get("weekly_distance_goal")
            m_dist = existing_row.get("monthly_distance_goal")
            y_dist = existing_row.get("yearly_distance_goal")
            w_elev = existing_row.get("weekly_elevation_goal")
            m_elev = existing_row.get("monthly_elevation_goal")
            y_elev = existing_row.get("yearly_elevation_goal")

            target_val = float(target) if target > 0 else None
            if norm_metric == "elevation":
                if norm_period == "weekly":
                    w_elev = target_val
                elif norm_period == "monthly":
                    m_elev = target_val
                else:
                    y_elev = target_val
            else:
                if norm_period == "weekly":
                    w_dist = target_val
                elif norm_period == "monthly":
                    m_dist = target_val
                else:
                    y_dist = target_val

            repo.upsert_goal(
                athlete_id=athlete_id,
                activity_type_id=act_type_id,
                weekly_distance_goal=w_dist,
                monthly_distance_goal=m_dist,
                yearly_distance_goal=y_dist,
                weekly_elevation_goal=w_elev,
                monthly_elevation_goal=m_elev,
                yearly_elevation_goal=y_elev,
            )
        elif hasattr(repo, "set_goal"):
            repo.set_goal(
                athlete_id=athlete_id,
                period=norm_period,
                metric=norm_metric,
                goal_type=norm_sport,
                target=target,
            )
        return create_envelope(
            {
                "success": True,
                "updated_goal": {
                    "athlete_id": athlete_id,
                    "period": period,
                    "goal_type": goal_type,
                    "metric": metric,
                    "target": target,
                },
            },
            source="local_db",
        )
    except Exception as e:
        return create_error_envelope(ERROR_INVALID_ARGUMENT, f"Failed updating goal: {e}")
