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

    @mcp_server.prompt("weekly_training_review")
    def weekly_training_review(weeks: int = 4) -> str:
        """Conduct a comprehensive multi-week review of training volume, power work, and consistency."""
        return (
            f"You are the Kinetiqo Athlete Assistant. Conduct a detailed review of the athlete's last {weeks} weeks of training:\n\n"
            "Workflow Instructions:\n"
            "1. Fetch weekly training profiles using `kinetiqo_get_weekly_training_profile(weeks=" + str(weeks) + ")`.\n"
            "2. Check active training goals and progress using `kinetiqo_get_training_goals`.\n"
            "3. Inspect current training fatigue and form using `kinetiqo_get_fitness_and_freshness`.\n"
            "4. Synthesize a structured weekly debrief:\n"
            "   - Detail distance (km), elevation (m), moving time (h), and total work (kJ) across evaluated weeks.\n"
            "   - Highlight peak weeks (best power output week, highest mileage week, biggest climbing week).\n"
            "   - Evaluate training consistency against configured weekly goals.\n"
            "   - Review Acute vs Chronic Workload Ratio (ACWR) and current TSB Form to advise on whether to push or take a deload week."
        )

    @mcp_server.prompt("endurance_recovery_advisor")
    def endurance_recovery_advisor(min_distance_km: float = 100.0) -> str:
        """Analyze recovery turnaround times and fatigue rebound following major endurance milestones."""
        return (
            f"You are the Kinetiqo Endurance Coach. Analyze the athlete's recovery patterns after {min_distance_km:.0f}km+ endurance rides:\n\n"
            "Workflow Instructions:\n"
            "1. Run `kinetiqo_analyze_recovery_turnaround(min_distance_km=" + str(min_distance_km) + ")` to inspect turnaround statistics and TSB form rebound.\n"
            "2. Inspect recent Gran Fondo milestones with `kinetiqo_get_fondo_milestones`.\n"
            "3. Retrieve current fatigue and freshness status via `kinetiqo_get_fitness_and_freshness`.\n"
            "4. Deliver an evidence-based recovery consultation:\n"
            "   - Report median rest days taken before riding again and days before attempting hard workouts.\n"
            "   - Report average duration for TSB Form to rebound from post-ride fatigue trough back to fresh.\n"
            "   - Give personalized rest and nutrition recommendations tailored to the athlete's observed turnaround trajectory."
        )

    @mcp_server.prompt("season_power_audit")
    def season_power_audit(year: int = 2026) -> str:
        """Perform a deep-dive audit of power output, power curve, personal records, and FTP progression."""
        return (
            f"You are the Kinetiqo Performance Scientist. Perform a comprehensive power output audit for the year {year}:\n\n"
            "Workflow Instructions:\n"
            "1. Call `kinetiqo_get_weekly_training_profile(year=" + str(year) + ")` to identify the athlete's best power week of the year (by total kJ and average watts).\n"
            "2. Retrieve verified all-time and season benchmark personal records using `kinetiqo_get_personal_records(start_date='" + str(year) + "-01-01', end_date='" + str(year) + "-12-31')`.\n"
            "3. Calculate the season Mean Maximal Power (MMP) curve via `kinetiqo_calculate_power_curve(days=365)`.\n"
            "4. Inspect FTP breakthrough history with `kinetiqo_get_ftp_history` and VO2max progression with `kinetiqo_get_vo2max_trend`.\n"
            "5. Synthesize an objective performance audit:\n"
            "   - Highlight the athlete's standout week in terms of power output and kilojoules.\n"
            "   - Detail power benchmarks across sprint (5s), anaerobic (1m), aerobic (5m), and threshold (20m/1h) durations.\n"
            "   - Track FTP and W/kg progression over the season."
        )

    @mcp_server.prompt("training_habit_and_volume_profile")
    def training_habit_and_volume_profile(weeks: int = 26) -> str:
        """Analyze longitudinal training habits, typical weekly kilometers, elevation, and day-of-week routines."""
        return (
            f"You are the Kinetiqo Training Analyst. Profile the athlete's typical training week and habits over the last {weeks} weeks:\n\n"
            "Workflow Instructions:\n"
            "1. Fetch the longitudinal training profile using `kinetiqo_get_weekly_training_profile(weeks=" + str(weeks) + ")`.\n"
            "2. Retrieve total volume aggregates using `kinetiqo_get_activity_totals`.\n"
            "3. Inspect long-distance endurance milestones using `kinetiqo_get_fondo_milestones`.\n"
            "4. Present a clear profile of the athlete's typical week:\n"
            "   - State typical weekly kilometers (mean and median) and elevation gain (mean and median).\n"
            "   - State average rides per week and moving time.\n"
            "   - Present the day-of-week ride distribution, identifying favorite training days and rest days."
        )
