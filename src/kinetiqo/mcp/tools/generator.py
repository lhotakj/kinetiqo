"""Group E: Visual & Creative Generation Tools."""

from typing import Any, Dict, List, Optional
import base64
import os
from pathlib import Path

from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_CONFIGURED,
    ERROR_NOT_FOUND,
)
from kinetiqo.web.renderers.poster_renderer import render_poster_artifact
from kinetiqo.web.renderers.stats_renderer import render_stats_artifact
from kinetiqo.web.renderers.fondo_renderer import render_fondo_artifact


def _format_generator_error(action: str, exc: Exception) -> Dict[str, Any]:
    err_str = str(exc)
    msg = f"Failed generating {action}: {err_str}"
    lower = err_str.lower()
    error_code = ERROR_INVALID_ARGUMENT
    if "playwright" in lower or "chromium" in lower or "executable" in lower:
        msg += ". Visual rendering requires Chromium and Playwright (available in the 'kinetiqo/web-mcp' Docker image)."
        error_code = ERROR_NOT_CONFIGURED
    return create_error_envelope(error_code, msg)


def kinetiqo_generate_activity_poster(
    repo: Any,
    config: Any,
    activity_id: str,
    ratio: str = "4/3",
    map_provider: str = "carto_dark",
    route_color: str = "#f97316",
    font_family: str = "Inter",
    hide_start_end_km: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate high-resolution PNG activity poster using Playwright rendering."""
    try:
        options = {
            "ratio": ratio,
            "map_provider": map_provider,
            "route_color": route_color,
            "font_family": font_family,
            "hide_start_end_km": hide_start_end_km,
        }
        png_bytes = render_poster_artifact(activity_id=activity_id, options=options, repo=repo, config=config)

        # Artifact formatting (dual stdio: base64 + size)
        b64_str = base64.b64encode(png_bytes).decode("ascii")
        data = {
            "artifact_type": "activity_poster",
            "activity_id": str(activity_id),
            "mime_type": "image/png",
            "byte_size": len(png_bytes),
            "ratio": ratio,
            "base64_data": b64_str[:100] + "... [truncated in metadata]",
            "inline_image_base64": b64_str,
        }
        return create_envelope(data, source="rendered")
    except Exception as e:
        return _format_generator_error("poster", e)


def kinetiqo_generate_mega_stats_infographic(
    repo: Any,
    config: Any,
    year: Any = "all",
    sport_group: str = "cycling",
    font_family: str = "Inter",
) -> Dict[str, Any]:
    """Generate 365-day MEGA Stats calendar heatmap infographic via Playwright."""
    try:
        options = {"font_family": font_family}
        png_bytes = render_stats_artifact(year=year, sport_group=sport_group, options=options, repo=repo, config=config)

        b64_str = base64.b64encode(png_bytes).decode("ascii")
        data = {
            "artifact_type": "mega_stats_infographic",
            "year": year,
            "sport_group": sport_group,
            "mime_type": "image/png",
            "byte_size": len(png_bytes),
            "inline_image_base64": b64_str,
        }
        return create_envelope(data, source="rendered")
    except Exception as e:
        return _format_generator_error("MEGA stats", e)


def kinetiqo_generate_fondo_infographic(
    repo: Any,
    config: Any,
    year: Any = "all",
    sport_group: str = "cycling",
    arc_color: str = "#22c55e",
) -> Dict[str, Any]:
    """Generate concentric rings Fondo-o-meter endurance showcase infographic."""
    try:
        options = {"arc_color": arc_color}
        png_bytes = render_fondo_artifact(year=year, sport_group=sport_group, options=options, repo=repo, config=config)

        b64_str = base64.b64encode(png_bytes).decode("ascii")
        data = {
            "artifact_type": "fondo_infographic",
            "year": year,
            "sport_group": sport_group,
            "mime_type": "image/png",
            "byte_size": len(png_bytes),
            "inline_image_base64": b64_str,
        }
        return create_envelope(data, source="rendered")
    except Exception as e:
        return _format_generator_error("Fondo infographic", e)


def kinetiqo_generate_map_artifact(
    repo: Any,
    config: Any,
    activity_id: str,
    map_provider: str = "osm",
    route_color: str = "#3b82f6",
    hide_start_end_km: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate standalone map rendering for an activity with privacy start/end redaction."""
    return kinetiqo_generate_activity_poster(
        repo=repo,
        config=config,
        activity_id=activity_id,
        ratio="16/9",
        map_provider=map_provider,
        route_color=route_color,
        hide_start_end_km=hide_start_end_km,
    )
