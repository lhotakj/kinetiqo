"""MCP Resource Handlers for Kinetiqo."""

import json
from typing import Any, Dict


def register_mcp_resources(mcp_server: Any, get_repo: Any) -> None:
    """Register read-only MCP resources on the FastMCP server instance."""

    @mcp_server.resource("kinetiqo://profile")
    def get_athlete_profile_resource() -> str:
        """Sanitized athlete profile: weight, FTP, timezone, and units."""
        repo = get_repo()
        try:
            profile = repo.get_profile() or {}
            athlete_id = profile.get("athlete_id") or profile.get("id")
            first_name = profile.get("first_name", "") or ""
            last_name = profile.get("last_name", "") or ""
            full_name = f"{first_name} {last_name}".strip()
            sanitized = {
                "athlete_id": athlete_id,
                "name": full_name or profile.get("username") or profile.get("firstname") or "Athlete",
                "weight_kg": profile.get("weight"),
                "ftp_watts": profile.get("ftp"),
                "timezone": profile.get("timezone") or "UTC",
            }
            return json.dumps(sanitized, indent=2)
        finally:
            if hasattr(repo, "close"):
                repo.close()

    @mcp_server.resource("kinetiqo://goals")
    def get_training_goals_resource() -> str:
        """Active training goals and current progress for cycling and walking."""
        from kinetiqo.mcp.tools.achievements import kinetiqo_get_training_goals
        repo = get_repo()
        try:
            res = kinetiqo_get_training_goals(repo)
            return json.dumps(res.get("data", {}), indent=2)
        finally:
            if hasattr(repo, "close"):
                repo.close()

    @mcp_server.resource("kinetiqo://activities/latest")
    def get_latest_activity_resource() -> str:
        """Summary and sensor telemetry coverage of the most recent activity."""
        repo = get_repo()
        try:
            acts = repo.get_activities_web(limit=1, offset=0, sort_by="start_date", sort_order="DESC")
            if not acts:
                return json.dumps({"message": "No activities found in database"}, indent=2)
            act = acts[0]
            act_id = str(act.get("activity_id") or act.get("id"))
            from kinetiqo.mcp.tools.activities import kinetiqo_get_activity_details
            details = kinetiqo_get_activity_details(repo, act_id)
            return json.dumps(details.get("data", {}), indent=2)
        finally:
            if hasattr(repo, "close"):
                repo.close()

    @mcp_server.resource("kinetiqo://analytics/fitness-freshness")
    def get_fitness_freshness_resource() -> str:
        """Current suffer-score CTL/ATL/TSB and 90-day training workload trend."""
        from kinetiqo.mcp.tools.physiology import kinetiqo_get_fitness_and_freshness
        repo = get_repo()
        try:
            res = kinetiqo_get_fitness_and_freshness(repo, period_days=90)
            return json.dumps(res.get("data", {}), indent=2)
        finally:
            if hasattr(repo, "close"):
                repo.close()

    @mcp_server.resource("kinetiqo://analytics/power-skills")
    def get_power_skills_resource() -> str:
        """Power-duration benchmark skills (5s to 1h) and contributing activities."""
        from kinetiqo.mcp.tools.physiology import kinetiqo_get_power_skills
        repo = get_repo()
        try:
            res = kinetiqo_get_power_skills(repo)
            return json.dumps(res.get("data", {}), indent=2)
        finally:
            if hasattr(repo, "close"):
                repo.close()

    @mcp_server.resource("kinetiqo://analytics/koms")
    def get_koms_resource() -> str:
        """Verified King of the Mountains (KOM/QOM) crowns and cache status."""
        from kinetiqo.mcp.tools.achievements import kinetiqo_get_verified_koms
        repo = get_repo()
        try:
            res = kinetiqo_get_verified_koms(repo)
            return json.dumps(res.get("data", {}), indent=2)
        finally:
            if hasattr(repo, "close"):
                repo.close()
