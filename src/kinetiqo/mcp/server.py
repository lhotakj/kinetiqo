"""FastMCP Server factory for Kinetiqo."""

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, List, Optional
from mcp.server.fastmcp import FastMCP

from kinetiqo.db.factory import create_repository
from kinetiqo.mcp.resources import register_mcp_resources
from kinetiqo.mcp.prompts import register_mcp_prompts
from kinetiqo.mcp.tools import activities, telemetry, physiology, achievements, generator, operations

logger = logging.getLogger("kinetiqo.mcp")


def create_mcp_server(
    config: Any,
    repo_factory: Optional[Callable[[], Any]] = None,
    host: str = "0.0.0.0",
    port: int = 8000,
) -> FastMCP:
    """Create and configure the Kinetiqo FastMCP server with dynamic tool gating."""
    server = FastMCP(
        "kinetiqo",
        host=host,
        port=port,
        instructions=(
            "Kinetiqo is a self-hosted private fitness and telemetry platform. "
            "You have access to evidence-based athlete data, telemetry streams, "
            "power curves, fitness/freshness tracking, and visual artifact generation. "
            "Always state measured values versus estimates and disclose missing sensors."
        ),
    )

    # Repository access helper ensuring clean connection lifecycle
    @contextmanager
    def get_repo() -> Generator[Any, None, None]:
        if repo_factory:
            repo = repo_factory()
            try:
                yield repo
            finally:
                pass
        else:
            repo = create_repository(config)
            try:
                yield repo
            finally:
                if hasattr(repo, "close"):
                    repo.close()

    # Mutation gating flags
    allow_profile_write = os.environ.get("KINETIQO_MCP_ALLOW_PROFILE_WRITE", "0").strip() == "1"
    allow_sync = os.environ.get("KINETIQO_MCP_ALLOW_SYNC", "0").strip() == "1"
    allow_strava_write = os.environ.get("KINETIQO_MCP_ALLOW_STRAVA_WRITE", "0").strip() == "1"

    # ==========================================
    # Group A: Activity Discovery & Query Engine
    # ==========================================
    @server.tool(
        name="kinetiqo_search_activities",
        description=(
            "Search and filter activities with comprehensive telemetry criteria and deterministic keyset pagination. "
            "Supports flexible dates (e.g. '2026', '2026-08', '24.10.2026', 'yesterday', 'this_week', 'this_month', 'this_year', '7_days', '30_days', 'all_time'), "
            "name keywords, sport types (e.g. ['cycling'], ['running']), distance, elevation, moving time, watts, heartrate, speed, suffer score, gear, PRs, and trophies."
        ),
    )
    def search_activities(
        query: Optional[str] = None,
        sport_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        date_preset: Optional[str] = None,
        min_distance_km: Optional[float] = None,
        max_distance_km: Optional[float] = None,
        min_elevation_m: Optional[float] = None,
        max_elevation_m: Optional[float] = None,
        min_moving_time_min: Optional[float] = None,
        max_moving_time_min: Optional[float] = None,
        min_watts: Optional[float] = None,
        max_watts: Optional[float] = None,
        min_max_watts: Optional[float] = None,
        max_max_watts: Optional[float] = None,
        min_heartrate: Optional[float] = None,
        max_heartrate: Optional[float] = None,
        has_heartrate: Optional[bool] = None,
        has_power: Optional[bool] = None,
        min_speed_kmh: Optional[float] = None,
        max_speed_kmh: Optional[float] = None,
        min_suffer_score: Optional[int] = None,
        max_suffer_score: Optional[int] = None,
        min_pr_count: Optional[int] = None,
        gear_id: Optional[str] = None,
        workout_type: Optional[int] = None,
        has_trophies: Optional[bool] = None,
        koms_only: Optional[bool] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        sort_by: str = "start_date",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return activities.kinetiqo_search_activities(
                repo=r,
                athlete_id=athlete_id,
                query=query,
                sport_types=sport_types,
                start_date=start_date,
                end_date=end_date,
                date_preset=date_preset,
                min_distance_km=min_distance_km,
                max_distance_km=max_distance_km,
                min_elevation_m=min_elevation_m,
                max_elevation_m=max_elevation_m,
                min_moving_time_min=min_moving_time_min,
                max_moving_time_min=max_moving_time_min,
                min_watts=min_watts,
                max_watts=max_watts,
                min_max_watts=min_max_watts,
                max_max_watts=max_max_watts,
                min_heartrate=min_heartrate,
                max_heartrate=max_heartrate,
                has_heartrate=has_heartrate,
                has_power=has_power,
                min_speed_kmh=min_speed_kmh,
                max_speed_kmh=max_speed_kmh,
                min_suffer_score=min_suffer_score,
                max_suffer_score=max_suffer_score,
                min_pr_count=min_pr_count,
                gear_id=gear_id,
                workout_type=workout_type,
                has_trophies=has_trophies,
                koms_only=koms_only,
                cursor=cursor,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
            )

    @server.tool(name="kinetiqo_get_activity_details", description="Retrieve comprehensive activity metadata and sensor coverage.")
    def get_activity_details(activity_id: str) -> Dict[str, Any]:
        with get_repo() as r:
            return activities.kinetiqo_get_activity_details(repo=r, activity_id=activity_id)

    @server.tool(
        name="kinetiqo_get_activity_totals",
        description="Compute aggregated distance, elevation, moving time, and count. Supports flexible dates and presets (e.g. 'this_year', 'last_month', '2026'). For riding/cycling, specify all biking types or ['cycling']. Omit for all sports.",
    )
    def get_activity_totals(
        sport_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        date_preset: Optional[str] = None,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return activities.kinetiqo_get_activity_totals(
                repo=r,
                sport_types=sport_types,
                start_date=start_date,
                end_date=end_date,
                date_preset=date_preset,
            )

    @server.tool(name="kinetiqo_compare_activities", description="Compare 2 to 5 activities side-by-side.")
    def compare_activities(activity_ids: List[str]) -> Dict[str, Any]:
        with get_repo() as r:
            return activities.kinetiqo_compare_activities(repo=r, activity_ids=activity_ids)

    @server.tool(name="kinetiqo_compare_periods", description="Compare two training periods with equal elapsed-day alignment.")
    def compare_periods(
        period_a: Dict[str, str],
        period_b: Dict[str, str],
        sport_types: Optional[List[str]] = None,
        align: str = "elapsed_days",
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return activities.kinetiqo_compare_periods(
                repo=r,
                period_a=period_a,
                period_b=period_b,
                sport_types=sport_types,
                align=align,
            )

    @server.tool(name="kinetiqo_find_similar_routes", description="Find past activities matching an activity's GPS route.")
    def find_similar_routes(
        activity_id: str,
        sport_types: Optional[List[str]] = None,
        max_candidates: int = 10,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return activities.kinetiqo_find_similar_routes(
                repo=r,
                activity_id=activity_id,
                sport_types=sport_types,
                max_candidates=max_candidates,
            )

    @server.tool(name="kinetiqo_compare_route_attempts", description="Compare matched section performance across two sessions on the same route.")
    def compare_route_attempts(source_activity_id: str, target_activity_id: str) -> Dict[str, Any]:
        with get_repo() as r:
            return activities.kinetiqo_compare_route_attempts(
                repo=r,
                source_activity_id=source_activity_id,
                target_activity_id=target_activity_id,
            )

    # ==========================================
    # Group B: Telemetry & Power Analytics
    # ==========================================
    @server.tool(name="kinetiqo_get_activity_streams", description="Retrieve raw or downsampled telemetry time-series.")
    def get_activity_streams(
        activity_id: str,
        stream_types: Optional[List[str]] = None,
        resolution: str = "auto",
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return telemetry.kinetiqo_get_activity_streams(
                repo=r,
                activity_id=activity_id,
                stream_types=stream_types,
                resolution=resolution,
            )

    @server.tool(name="kinetiqo_get_data_coverage", description="Check sensor presence, row counts, and sampling gaps.")
    def get_data_coverage(activity_id: str) -> Dict[str, Any]:
        with get_repo() as r:
            return telemetry.kinetiqo_get_data_coverage(repo=r, activity_id=activity_id)

    @server.tool(name="kinetiqo_calculate_power_curve", description="Compute Mean Maximal Power (MMP) curve.")
    def calculate_power_curve(
        activity_id: Optional[str] = None,
        days: Optional[int] = None,
        durations: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return telemetry.kinetiqo_calculate_power_curve(
                repo=r,
                activity_id=activity_id,
                days=days,
                durations=durations,
            )

    @server.tool(name="kinetiqo_get_personal_records", description="Retrieve peak power records for benchmark durations.")
    def get_personal_records(
        durations: Optional[List[int]] = None,
        sport_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return telemetry.kinetiqo_get_personal_records(
                repo=r,
                athlete_id=athlete_id,
                durations=durations,
                sport_types=sport_types,
                start_date=start_date,
                end_date=end_date,
            )

    @server.tool(name="kinetiqo_analyze_workout_structure", description="Analyze NP, IF, TSS, sustained blocks, and sprint surges.")
    def analyze_workout_structure(activity_id: str, athlete_ftp: Optional[float] = None) -> Dict[str, Any]:
        with get_repo() as r:
            return telemetry.kinetiqo_analyze_workout_structure(
                repo=r,
                activity_id=activity_id,
                athlete_ftp=athlete_ftp,
            )

    @server.tool(name="kinetiqo_analyze_pacing", description="Analyze split pacing, stops, and aerobic decoupling.")
    def analyze_pacing(
        activity_id: str,
        split_basis: str = "moving_time",
        num_splits: int = 2,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return telemetry.kinetiqo_analyze_pacing(
                repo=r,
                activity_id=activity_id,
                split_basis=split_basis,
                num_splits=num_splits,
            )

    @server.tool(name="kinetiqo_get_route_highlights", description="Identify top climbs and peak wattage segments with optional privacy redaction.")
    def get_route_highlights(activity_id: str, hide_start_end_km: Optional[float] = None) -> Dict[str, Any]:
        with get_repo() as r:
            return telemetry.kinetiqo_get_route_highlights(
                repo=r,
                activity_id=activity_id,
                hide_start_end_km=hide_start_end_km,
            )

    # ==========================================
    # Group C: Physiology & Fitness Modeling
    # ==========================================
    @server.tool(name="kinetiqo_get_fitness_and_freshness", description="Retrieve CTL (Fitness), ATL (Fatigue), and TSB (Form) trends.")
    def get_fitness_and_freshness(period_days: int = 90) -> Dict[str, Any]:
        with get_repo() as r:
            return physiology.kinetiqo_get_fitness_and_freshness(repo=r, period_days=period_days)

    @server.tool(name="kinetiqo_get_ftp_history", description="Retrieve configured FTP and historical 20-min breakthrough efforts.")
    def get_ftp_history() -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return physiology.kinetiqo_get_ftp_history(repo=r, athlete_id=athlete_id)

    @server.tool(name="kinetiqo_get_vo2max_trend", description="Estimate VO2max trends via Storer-Davis 5m MAP and Coggan FTP.")
    def get_vo2max_trend(days: int = 90) -> Dict[str, Any]:
        with get_repo() as r:
            return physiology.kinetiqo_get_vo2max_trend(repo=r, days=days)

    @server.tool(name="kinetiqo_get_power_skills", description="Benchmark power skills across durations (5s, 30s, 1m, 5m, 10m, 20m, 1h).")
    def get_power_skills() -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return physiology.kinetiqo_get_power_skills(repo=r, athlete_id=athlete_id)

    @server.tool(name="kinetiqo_get_training_load_trends", description="Retrieve rolling 7d/28d training load and Acute:Chronic Workload Ratio.")
    def get_training_load_trends(weeks: int = 12) -> Dict[str, Any]:
        with get_repo() as r:
            return physiology.kinetiqo_get_training_load_trends(repo=r, weeks=weeks)

    @server.tool(name="kinetiqo_get_weekly_training_profile", description="Retrieve weekly training profile, volume, power (watts/kJ), best power weeks, and day-of-week habits.")
    def get_weekly_training_profile(
        year: Optional[int] = None,
        weeks: int = 12,
        sport_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return physiology.kinetiqo_get_weekly_training_profile(
                repo=r,
                athlete_id=athlete_id,
                year=year,
                weeks=weeks,
                sport_types=sport_types,
            )

    @server.tool(name="kinetiqo_analyze_recovery_turnaround", description="Analyze recovery turnaround time and TSB fatigue dissipation following endurance milestones.")
    def analyze_recovery_turnaround(
        min_distance_km: float = 100.0,
        sport_group: str = "cycling",
        lookback_days: int = 365,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return physiology.kinetiqo_analyze_recovery_turnaround(
                repo=r,
                min_distance_km=min_distance_km,
                sport_group=sport_group,
                lookback_days=lookback_days,
            )

    # ==========================================
    # Group D: Achievements & Milestones
    # ==========================================
    @server.tool(name="kinetiqo_get_verified_koms", description="Retrieve verified King of the Mountains (KOM/QOM) crowns.")
    def get_verified_koms() -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return achievements.kinetiqo_get_verified_koms(repo=r, athlete_id=athlete_id)

    @server.tool(name="kinetiqo_get_segment_trophies", description="Retrieve top-10 segment ribbons breakdown.")
    def get_segment_trophies() -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return achievements.kinetiqo_get_segment_trophies(repo=r, athlete_id=athlete_id)

    @server.tool(name="kinetiqo_get_fondo_milestones", description="Retrieve Gran Fondo and endurance distance milestones.")
    def get_fondo_milestones(sport_group: str = "cycling", year: Optional[int] = None) -> Dict[str, Any]:
        with get_repo() as r:
            return achievements.kinetiqo_get_fondo_milestones(repo=r, sport_group=sport_group, year=year)

    @server.tool(name="kinetiqo_get_training_goals", description="Retrieve active distance and elevation goals and current progress.")
    def get_training_goals() -> Dict[str, Any]:
        with get_repo() as r:
            athlete_id = int(getattr(config, "athlete_id", 1) or 1)
            return achievements.kinetiqo_get_training_goals(repo=r, athlete_id=athlete_id)

    if allow_profile_write:
        @server.tool(name="kinetiqo_update_training_goals", description="Update athlete distance/elevation goal (requires KINETIQO_MCP_ALLOW_PROFILE_WRITE=1).")
        def update_training_goals(period: str, goal_type: str, target: float, metric: str = "distance") -> Dict[str, Any]:
            with get_repo() as r:
                athlete_id = int(getattr(config, "athlete_id", 1) or 1)
                return achievements.kinetiqo_update_training_goals(
                    repo=r,
                    athlete_id=athlete_id,
                    period=period,
                    goal_type=goal_type,
                    target=target,
                    metric=metric,
                    allow_write=True,
                )

    # ==========================================
    # Group E: Visual Generation
    # ==========================================
    @server.tool(name="kinetiqo_generate_activity_poster", description="Generate high-resolution PNG activity poster.")
    def generate_activity_poster(
        activity_id: str,
        ratio: str = "4/3",
        map_provider: str = "carto_dark",
        route_color: str = "#f97316",
        font_family: str = "Inter",
        hide_start_end_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return generator.kinetiqo_generate_activity_poster(
                repo=r,
                config=config,
                activity_id=activity_id,
                ratio=ratio,
                map_provider=map_provider,
                route_color=route_color,
                font_family=font_family,
                hide_start_end_km=hide_start_end_km,
            )

    @server.tool(name="kinetiqo_generate_mega_stats_infographic", description="Generate 365-day MEGA Stats calendar heatmap.")
    def generate_mega_stats(
        year: Any = "all",
        sport_group: str = "cycling",
        font_family: str = "Inter",
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return generator.kinetiqo_generate_mega_stats_infographic(
                repo=r,
                config=config,
                year=year,
                sport_group=sport_group,
                font_family=font_family,
            )

    @server.tool(name="kinetiqo_generate_fondo_infographic", description="Generate Fondo-o-meter concentric rings infographic.")
    def generate_fondo_infographic(
        year: Any = "all",
        sport_group: str = "cycling",
        arc_color: str = "#22c55e",
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return generator.kinetiqo_generate_fondo_infographic(
                repo=r,
                config=config,
                year=year,
                sport_group=sport_group,
                arc_color=arc_color,
            )

    @server.tool(name="kinetiqo_generate_map_artifact", description="Generate standalone map artifact with route line.")
    def generate_map_artifact(
        activity_id: str,
        map_provider: str = "osm",
        route_color: str = "#3b82f6",
        hide_start_end_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        with get_repo() as r:
            return generator.kinetiqo_generate_map_artifact(
                repo=r,
                config=config,
                activity_id=activity_id,
                map_provider=map_provider,
                route_color=route_color,
                hide_start_end_km=hide_start_end_km,
            )

    # ==========================================
    # Group F: Operations & Sync
    # ==========================================
    @server.tool(name="kinetiqo_get_sync_job_status", description="Check status and duration of background sync jobs.")
    def get_sync_job_status(job_id: Optional[str] = None) -> Dict[str, Any]:
        with get_repo() as r:
            return operations.kinetiqo_get_sync_job_status(repo=r, job_id=job_id)

    @server.tool(name="kinetiqo_preview_strava_description", description="Preview UPDATE_STRAVA_* description merge without writing.")
    def preview_strava_description(activity_id: str) -> Dict[str, Any]:
        with get_repo() as r:
            return operations.kinetiqo_preview_strava_description(repo=r, config=config, activity_id=activity_id)

    if allow_sync:
        @server.tool(name="kinetiqo_trigger_sync", description="Trigger background activity sync (requires KINETIQO_MCP_ALLOW_SYNC=1).")
        def trigger_sync(sync_type: str = "fast", full_sync_ack: bool = False) -> Dict[str, Any]:
            with get_repo() as r:
                return operations.kinetiqo_trigger_sync(
                    repo=r,
                    config=config,
                    sync_type=sync_type,
                    full_sync_ack=full_sync_ack,
                    allow_sync=True,
                )

    if allow_strava_write:
        @server.tool(name="kinetiqo_update_strava_description", description="Publish approved description to Strava (requires KINETIQO_MCP_ALLOW_STRAVA_WRITE=1).")
        def update_strava_description(activity_id: str, preview_id: str) -> Dict[str, Any]:
            with get_repo() as r:
                return operations.kinetiqo_update_strava_description(
                    repo=r,
                    config=config,
                    activity_id=activity_id,
                    preview_id=preview_id,
                    allow_write=True,
                )

    if allow_profile_write:
        @server.tool(name="kinetiqo_update_athlete_profile", description="Update athlete weight or FTP (requires KINETIQO_MCP_ALLOW_PROFILE_WRITE=1).")
        def update_athlete_profile(weight_kg: Optional[float] = None, ftp_watts: Optional[float] = None) -> Dict[str, Any]:
            with get_repo() as r:
                return operations.kinetiqo_update_athlete_profile(
                    repo=r,
                    weight_kg=weight_kg,
                    ftp_watts=ftp_watts,
                    allow_write=True,
                )

    # Register Resources & Prompts
    def direct_repo_factory():
        if repo_factory:
            return repo_factory()
        return create_repository(config)

    register_mcp_resources(server, direct_repo_factory)
    register_mcp_prompts(server)

    # Attach unified request/response logging across tools, resources, and prompts (like HTTP access logs in web)
    if hasattr(server, "_tool_manager") and hasattr(server._tool_manager, "call_tool"):
        orig_call_tool = server._tool_manager.call_tool

        async def logged_call_tool(name: str, arguments: dict, context=None, convert_result=False):
            safe_args = {}
            for k, v in (arguments or {}).items():
                if k.lower() in ("password", "secret", "token", "key"):
                    safe_args[k] = "***"
                elif isinstance(v, str) and len(v) > 60:
                    safe_args[k] = v[:57] + "..."
                else:
                    safe_args[k] = v
            args_str = ", ".join(f"{k}={v!r}" for k, v in safe_args.items()) if safe_args else "no args"

            logger.info("MCP Request: %s(%s)", name, args_str)
            start_time = time.perf_counter()
            try:
                result = await orig_call_tool(name, arguments, context=context, convert_result=convert_result)
                elapsed = time.perf_counter() - start_time

                # Extract status summary if result is JSON envelope
                status_desc = "complete"
                if isinstance(result, tuple) and len(result) > 0 and hasattr(result[0], "__iter__"):
                    for item in result[0]:
                        if hasattr(item, "text"):
                            try:
                                parsed = json.loads(item.text)
                                if isinstance(parsed, dict):
                                    status_desc = parsed.get("data_status") or "complete"
                                    if "error_code" in parsed.get("data", {}):
                                        status_desc = f"error: [{parsed['data']['error_code']}]"
                            except Exception:
                                pass
                            break

                logger.info("MCP Response: %s -> %s (elapsed %.3fs)", name, status_desc, elapsed)
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                logger.error("MCP Exception: %s failed: %s (elapsed %.3fs)", name, e, elapsed)
                raise

        server._tool_manager.call_tool = logged_call_tool

    if hasattr(server, "read_resource"):
        orig_read_resource = server.read_resource

        async def logged_read_resource(uri):
            logger.info("MCP Resource Request: %s", uri)
            start_time = time.perf_counter()
            try:
                res = await orig_read_resource(uri)
                elapsed = time.perf_counter() - start_time
                logger.info("MCP Resource Response: %s -> complete (elapsed %.3fs)", uri, elapsed)
                return res
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                logger.error("MCP Resource Exception: %s failed: %s (elapsed %.3fs)", uri, e, elapsed)
                raise

        server.read_resource = logged_read_resource

    if hasattr(server, "get_prompt"):
        orig_get_prompt = server.get_prompt

        async def logged_get_prompt(name, arguments=None):
            args_str = str(arguments) if arguments else "no args"
            logger.info("MCP Prompt Request: %s(%s)", name, args_str)
            start_time = time.perf_counter()
            try:
                res = await orig_get_prompt(name, arguments=arguments)
                elapsed = time.perf_counter() - start_time
                logger.info("MCP Prompt Response: %s -> complete (elapsed %.3fs)", name, elapsed)
                return res
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                logger.error("MCP Prompt Exception: %s failed: %s (elapsed %.3fs)", name, e, elapsed)
                raise

        server.get_prompt = logged_get_prompt

    return server
