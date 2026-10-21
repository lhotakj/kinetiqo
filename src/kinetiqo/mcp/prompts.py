"""MCP Prompts (Pre-Packaged Coaching and Analysis Workflows)."""

from typing import Any


def register_mcp_prompts(mcp_server: Any) -> None:
    """Register pre-packaged coaching workflows and prompt templates."""

    @mcp_server.prompt("post_ride_debrief")
    def post_ride_debrief(activity_id: str = "") -> str:
        """Deliver an evidence-based post-activity debrief using telemetry and fitness context."""
        act_clause = f"Activity #{activity_id}" if activity_id else "the latest activity"
        return (
            f"You are the Kinetiqo Athlete Assistant. Conduct a structured post-session debrief for {act_clause}:\n\n"
            "Workflow Instructions:\n"
            "1. Fetch activity details using `kinetiqo_get_activity_details` and check sensor telemetry coverage using `kinetiqo_get_data_coverage`.\n"
            "2. If power telemetry is available, analyze the session structure using `kinetiqo_analyze_workout_structure` (NP, IF, TSS, sustained blocks, and sprint surges).\n"
            "3. If multiple splits or pace analysis is needed, run `kinetiqo_analyze_pacing` to inspect pacing deltas and aerobic decoupling.\n"
            "4. Fetch recent fitness and training fatigue trends via `kinetiqo_get_fitness_and_freshness`.\n"
            "5. Synthesize a concise, clear report for the athlete:\n"
            "   - Disclose measured values only (distance, elevation, moving time, average/max power, HR).\n"
            "   - State clearly which sensors were absent or had gaps; never hallucinate missing wattage or cadence.\n"
            "   - Highlight notable achievements (peak surges, sustained power blocks, PRs or KOMs).\n"
            "   - Review training fatigue (TSB Form) with actionable recovery guidance.\n"
            "   - Offer to generate a commemorative poster (`kinetiqo_generate_activity_poster`) or preview description updates."
        )

    @mcp_server.prompt("race_readiness_assessment")
    def race_readiness_assessment(target_date: str, target_event_type: str = "Gran Fondo 150km") -> str:
        """Evaluate athlete readiness, fitness/fatigue balance, and power capabilities for an upcoming event."""
        return (
            f"You are the Kinetiqo Athlete Assistant. Assess athlete readiness for the upcoming '{target_event_type}' on {target_date}:\n\n"
            "Workflow Instructions:\n"
            "1. Retrieve current Fitness (CTL), Fatigue (ATL), and Form (TSB) using `kinetiqo_get_fitness_and_freshness`.\n"
            "2. Retrieve benchmark power skills across critical durations (5s to 1h) using `kinetiqo_get_power_skills`.\n"
            "3. Check configured FTP and recent breakthrough efforts using `kinetiqo_get_ftp_history`.\n"
            "4. Retrieve acute vs. chronic training workload using `kinetiqo_get_training_load_trends`.\n"
            "5. Provide an objective, data-backed assessment:\n"
            "   - Highlight whether current form (TSB) indicates freshness or acute fatigue.\n"
            "   - Compare event demands with the athlete's proven sustained power and longest recent rides (`kinetiqo_get_fondo_milestones`).\n"
            "   - Emphasize that these are historical training indicators, not guaranteed outcome predictions or medical diagnoses."
        )

    @mcp_server.prompt("poster_creative_director")
    def poster_creative_director(activity_id: str = "", style_theme: str = "dark") -> str:
        """Recommend aesthetic configurations (basemaps, color palettes, fonts) and generate posters."""
        act_clause = f"Activity #{activity_id}" if activity_id else "the athlete's latest standout activity"
        return (
            f"You are the Kinetiqo Creative Director. Design an aesthetic art poster for {act_clause} with a '{style_theme}' theme:\n\n"
            "Workflow Instructions:\n"
            "1. Fetch activity metadata using `kinetiqo_get_activity_details` to inspect distance, elevation gain, and sport type.\n"
            "2. Select a harmonious basemap provider:\n"
            "   - 'carto_dark' for sleek, modern dark aesthetics.\n"
            "   - 'thunderforest_outdoors' or 'mapy_cz_outdoor' for mountain passes and high elevation gains.\n"
            "   - 'esri_satellite' for scenic coastal or alpine routes.\n"
            "   - 'carto_light' or 'maptiler_voyager' for clean, minimalist light posters.\n"
            "3. Choose a vibrant contrasting route color (e.g. '#f97316' orange, '#22c55e' emerald, '#3b82f6' sapphire) and a modern typeface ('Outfit', 'Inter', 'Cinzel').\n"
            "4. Invoke `kinetiqo_generate_activity_poster` with the chosen parameters and present the resulting visual artifact to the athlete."
        )
