"""Kinetiqo Agent runner for automated Strava activity descriptions.

Extracts structured telemetry from synced activities, formats prompt context,
and executes single-shot LLM completions via ChatService with automatic fallback
cascading.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

from kinetiqo.chat.service import ChatService

logger = logging.getLogger("kinetiqo.agent")

AGENT_SYSTEM_INSTRUCTION = (
    "You are Kinetiqo Agent, an AI fitness assistant. "
    "You generate concise, engaging, and personalized text to be included in an athlete's Strava activity description. "
    "Guidelines:\n"
    "1. Output strictly plain text. Do NOT use markdown bold/italics, quotes, backticks, or code blocks.\n"
    "2. Respect the athlete's requested style, tone, and constraints.\n"
    "3. Keep the output punchy, natural, and directly embeddable into a Strava description.\n"
)


def _format_duration(seconds: int | float | None) -> str:
    if not seconds or seconds <= 0:
        return "0s"
    s = int(seconds)
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def build_activity_telemetry_prompt(activity: Dict[str, Any], athlete_prompt: str) -> Tuple[str, str]:
    """Assemble structured activity facts and athlete instructions.

    :param activity: Dictionary containing raw or summarized activity attributes.
    :param athlete_prompt: User-defined instruction from profile settings.
    :return: A tuple of ``(user_prompt, system_instruction)``.
    """
    sport = (
        activity.get("sport_type")
        or activity.get("sport")
        or activity.get("type")
        or "Workout"
    )
    name = activity.get("name") or "Activity"
    start_date = activity.get("start_date") or ""
    distance_m = float(activity.get("distance", 0.0) or 0.0)
    distance_km = round(distance_m / 1000.0, 2)
    moving_time_s = activity.get("moving_time") or 0
    duration_str = _format_duration(moving_time_s)
    elevation_m = round(float(activity.get("total_elevation_gain", 0.0) or 0.0), 1)

    avg_speed_ms = float(activity.get("average_speed", 0.0) or 0.0)
    avg_speed_kmh = round(avg_speed_ms * 3.6, 1) if avg_speed_ms > 0 else 0.0
    max_speed_ms = float(activity.get("max_speed", 0.0) or 0.0)
    max_speed_kmh = round(max_speed_ms * 3.6, 1) if max_speed_ms > 0 else 0.0

    facts = [
        f"- Sport: {sport}",
        f"- Title: {name}",
        f"- Distance: {distance_km} km",
        f"- Elevation Gain: {elevation_m} m",
        f"- Moving Time: {duration_str}",
    ]

    if start_date:
        facts.append(f"- Date: {start_date}")

    if avg_speed_kmh > 0:
        speed_str = f"- Avg Speed: {avg_speed_kmh} km/h"
        if max_speed_kmh > 0:
            speed_str += f" (Max: {max_speed_kmh} km/h)"
        facts.append(speed_str)

    avg_watts = activity.get("average_watts")
    if avg_watts and float(avg_watts) > 0:
        max_watts = activity.get("max_watts")
        p_str = f"- Avg Power: {round(float(avg_watts))} W"
        if max_watts and float(max_watts) > 0:
            p_str += f" (Max: {round(float(max_watts))} W)"
        weighted_w = activity.get("weighted_average_watts")
        if weighted_w and float(weighted_w) > 0:
            p_str += f", Normalized: {round(float(weighted_w))} W"
        facts.append(p_str)

    avg_hr = activity.get("average_heartrate")
    if avg_hr and float(avg_hr) > 0:
        max_hr = activity.get("max_heartrate")
        hr_str = f"- Avg Heart Rate: {round(float(avg_hr))} bpm"
        if max_hr and float(max_hr) > 0:
            hr_str += f" (Max: {round(float(max_hr))} bpm)"
        facts.append(hr_str)

    cadence = activity.get("average_cadence")
    if cadence and float(cadence) > 0:
        facts.append(f"- Cadence: {round(float(cadence))} rpm")

    calories = activity.get("calories")
    if calories and float(calories) > 0:
        facts.append(f"- Calories: {round(float(calories))} kcal")

    temp = activity.get("average_temp")
    if temp is not None:
        facts.append(f"- Temperature: {round(float(temp), 1)} °C")

    prs = activity.get("pr_count") or 0
    achievements = activity.get("achievement_count") or 0
    trophies = activity.get("trophies")
    achieve_parts = []
    if prs > 0:
        achieve_parts.append(f"{prs} PRs")
    if achievements > 0:
        achieve_parts.append(f"{achievements} total achievements")
    if trophies:
        if isinstance(trophies, dict) and any(trophies.values()):
            achieve_parts.append(f"Leaderboard trophies: {trophies}")
        elif isinstance(trophies, str) and trophies.strip() not in ("", "{}"):
            achieve_parts.append(f"Leaderboard trophies: {trophies}")
    if achieve_parts:
        facts.append(f"- Achievements: {', '.join(achieve_parts)}")

    directive = athlete_prompt.strip() if athlete_prompt and athlete_prompt.strip() else (
        "Write a witty, single-sentence summary of this workout's pace and effort."
    )

    facts_text = "\n".join(facts)
    prompt = f"Activity Telemetry:\n{facts_text}\n\nAthlete Directive:\n{directive}"
    return prompt, AGENT_SYSTEM_INSTRUCTION


def run_agent_prompt(
    chat_service: ChatService,
    athlete_id: str,
    activity: Dict[str, Any],
    athlete_prompt: str,
) -> Tuple[str, str]:
    """Execute single-turn AI prompt for an activity across default and fallback models.

    :param chat_service: Configured ChatService instance.
    :param athlete_id: Athlete identifier string.
    :param activity: Synced activity data dictionary.
    :param athlete_prompt: Athlete's prompt instructions.
    :return: Tuple of ``(response_text, status)`` where status is:
        - ``"generated"``: generated using primary default model
        - ``"fallback <model_id>"``: generated using a fallback model
        - ``"failed"``: all models failed or AI unconfigured
    """
    prompt, system_inst = build_activity_telemetry_prompt(activity, athlete_prompt)
    try:
        response_text, status = chat_service.generate_single_turn(
            athlete_id=athlete_id,
            prompt=prompt,
            system_instruction=system_inst,
        )
        cleaned = response_text.strip().strip('"\'').strip()
        return cleaned, status
    except Exception as exc:
        logger.warning(f"Kinetiqo Agent execution failed: {exc}")
        return "", "failed"

