"""Mega Stats infographic export renderer using Playwright navigation or HTML synthesis."""

import json as _json
import logging
from typing import Any, Dict, Optional

from kinetiqo.web.renderers.base import (
    extract_flask_cookies_and_port,
    find_chromium_executable,
    playwright_page,
    run_in_clean_thread,
)
from kinetiqo.sports import normalize_sport_group as normalize_stats_sport_group

logger = logging.getLogger("kinetiqo")

SIZE_WIDTHS = {
    "M": 1280,
    "L": 1440,
    "XL": 1600,
    "XXL": 1920,
    "XXXL": 2048,
}


def normalize_stats_dimensions(options: Dict[str, Any]) -> tuple[int, int]:
    """Resolve width and height from options (e.g. size='XL' -> 1600x1200)."""
    raw_size = str(options.get("size") or options.get("width") or "M").strip().upper()
    if raw_size in SIZE_WIDTHS:
        w = SIZE_WIDTHS[raw_size]
        return w, int(round(w * 3 / 4))
    try:
        w = max(800, min(int(raw_size), 2560))
        h = int(options.get("height") or round(w * 3 / 4))
        return w, h
    except (ValueError, TypeError):
        return 1280, 960


def _render_stats_sync(
    year: Any = "all",
    sport_group: str = "cycling",
    options: Optional[Dict[str, Any]] = None,
    repo: Any = None,
    config: Any = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Internal synchronous implementation of Mega Stats infographic rendering via Playwright."""
    options = options or {}
    width, height = normalize_stats_dimensions(options)
    export_format = str(options.get("format") or "png").lower()
    norm_group = normalize_stats_sport_group(sport_group)
    year_str = str(year or "all")
    period = str(options.get("period") or "year")
    font_family = str(options.get("font_family") or options.get("fontFamily") or "Inter")
    font_size = str(options.get("font_size") or options.get("fontSize") or "24")
    bg = str(options.get("bg") or "#4a4a4a")
    stats_column_width = str(options.get("stats_column_width") or options.get("statsColumnWidth") or "20")
    has_image = bool(options.get("has_image") or options.get("hasImage") or False)
    tint = str(options.get("tint") or "")
    opacity = options.get("opacity", 40)
    cookies = options.get("cookies") or []

    with playwright_page(
        viewport={"width": width, "height": height},
        cookies=cookies,
        device_scale_factor=1,
    ) as (page, browser, context):
        if html_content:
            page.set_content(html_content, wait_until="networkidle")
            if export_format == "pdf":
                return page.pdf(width=f"{width}px", height=f"{height}px", print_background=True)
            return page.screenshot(type="png")

        port = str(options.get("port") or 4444)
        internal_url = f"http://127.0.0.1:{port}/stats"
        rendered_via_server = False

        try:
            page.goto(internal_url, wait_until="networkidle", timeout=30_000)
            page.wait_for_function("document.fonts.ready", timeout=10_000)
            page.wait_for_selector("#infographic-wrapper", state="visible", timeout=10_000)

            js_code = f"""
            (function() {{
                function setVal(id, val) {{
                    var el = document.getElementById(id);
                    if (el) el.value = val;
                }}
                setVal('stats-period', {_json.dumps(period)});
                setVal('stats-size',   {_json.dumps(str(width))});
                var bg = document.getElementById('stats-bg');
                if (bg) bg.value = {_json.dumps(bg)};
                var ig = document.getElementById('infographic');
                if (ig) ig.style.backgroundColor = {_json.dumps(bg)};
                var statsWidthSlider = document.getElementById('stats-column-width');
                if (statsWidthSlider) {{
                    statsWidthSlider.value = {_json.dumps(stats_column_width)};
                    if (typeof window.applyStatsColumnWidth === 'function') {{
                        window.applyStatsColumnWidth(statsWidthSlider.value);
                    }} else {{
                        statsWidthSlider.dispatchEvent(new Event('input'));
                    }}
                }}
                var fontSlider = document.getElementById('stats-title-font-size');
                if (fontSlider) {{
                    fontSlider.value = {_json.dumps(font_size)};
                    if (typeof window.updateStatsFontSize === 'function') {{
                        window.updateStatsFontSize({_json.dumps(font_size)});
                    }}
                }}
                var font = {_json.dumps(font_family)};
                if (font) {{
                    var ig = document.getElementById('infographic');
                    if (ig) ig.style.setProperty('--stats-font-family', '"' + font + '", sans-serif');
                    var fontSel = document.getElementById('stats-font');
                    if (fontSel) fontSel.value = font;
                }}
                var hasImage = {_json.dumps(has_image)};
                var igBg = document.getElementById('ig-bg-image');
                var igOv = document.getElementById('ig-bg-overlay');
                var tint = {_json.dumps(tint)};
                var opacity = {_json.dumps(opacity)};
                var opVal = Number(opacity);
                if (isNaN(opVal)) opVal = 40;

                if (hasImage && igBg) {{
                    igBg.src = '/api/stats/image?t=' + Date.now();
                    igBg.style.display = 'block';
                }} else if (igBg) {{
                    igBg.style.display = 'none';
                }}

                if (igOv) {{
                    if (tint && opVal > 0) {{
                        igOv.style.display = 'block';
                        igOv.style.backgroundColor = tint;
                        igOv.style.opacity = String(opVal / 100.0);
                    }} else if (hasImage && opVal > 0) {{
                        igOv.style.display = 'block';
                        igOv.style.backgroundColor = '#000000';
                        igOv.style.opacity = String(opVal / 100.0);
                    }} else {{
                        igOv.style.display = 'none';
                    }}
                }}
                var grp = document.getElementById('stats-group');
                if (grp) {{
                    grp.value = {_json.dumps(norm_group)};
                    grp.dispatchEvent(new Event('change'));
                }}
                var sel = document.getElementById('stats-year');
                if (sel) {{
                    sel.value = {_json.dumps(year_str)};
                    sel.dispatchEvent(new Event('change'));
                }}
            }})();
            """
            page.evaluate(js_code)

            page.wait_for_function(
                "document.getElementById('ig-body') && "
                "document.getElementById('ig-body').style.display !== 'none'",
                timeout=20_000,
            )
            page.wait_for_timeout(600)

            page.evaluate(f"""
            (function() {{
                try {{
                    var w = document.getElementById('infographic-wrapper');
                    if (!w) return;
                    document.body.appendChild(w);
                    Array.from(document.body.children).forEach(function(el) {{
                        if (el !== w) el.style.visibility = 'hidden';
                    }});
                    document.body.style.cssText = 'margin:0;padding:0;overflow:hidden;background:#000;';
                    w.style.cssText = [
                        'display:block',
                        'position:fixed',
                        'top:0', 'left:0',
                        'width:{width}px',
                        'height:{height}px',
                        'transform:none',
                        'transform-origin:top left',
                        'border-radius:0',
                        'box-shadow:none',
                        'overflow:hidden',
                        'z-index:99999',
                        'background-color:' + {_json.dumps(bg)}
                    ].join(';') + ';';
                    var ig = document.getElementById('infographic');
                    if (ig) {{
                        ig.style.width = '100%';
                        ig.style.height = '100%';
                    }}
                }} catch(e) {{ console.error('Stats export prep failed', e); }}
            }})();
            """)
            page.wait_for_timeout(300)
            rendered_via_server = True
        except Exception as nav_err:
            logger.warning("Failed to render via internal URL %s: %s — using fallback HTML synthesis", internal_url, nav_err)

        if not rendered_via_server:
            fallback_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ margin: 0; background: #09090b; color: #f4f4f5; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; }}
                    .stats {{ text-align: center; }}
                    h1 {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
                    p {{ color: #a1a1aa; font-size: 1.25rem; }}
                </style>
            </head>
            <body>
                <div class="stats">
                    <h1>Mega Stats — {year_str}</h1>
                    <p>{norm_group.replace('_', ' ').capitalize()} Infographic</p>
                </div>
            </body>
            </html>
            """
            page.set_content(fallback_html, wait_until="networkidle")

        if export_format == "pdf":
            return page.pdf(width=f"{width}px", height=f"{height}px", print_background=True)
        else:
            return page.screenshot(type="png")


def render_stats_artifact(
    year: Any = "all",
    sport_group: str = "cycling",
    options: Optional[Dict[str, Any]] = None,
    repo: Any = None,
    config: Any = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Renders a Mega Stats infographic to PNG or PDF bytes using headless Playwright.

    :param year: Target year or 'all'.
    :param sport_group: 'cycling', 'running', etc.
    :param options: Dict of rendering options (format: 'png'|'pdf', width, height, size).
    :param repo: Database repository instance (optional).
    :param config: Application configuration instance (optional).
    :param html_content: Synthesized HTML content (optional).
    :return: PNG or PDF bytes.
    """
    opts = extract_flask_cookies_and_port(options)
    return run_in_clean_thread(
        _render_stats_sync,
        year=year,
        sport_group=sport_group,
        options=opts,
        repo=repo,
        config=config,
        html_content=html_content,
    )
