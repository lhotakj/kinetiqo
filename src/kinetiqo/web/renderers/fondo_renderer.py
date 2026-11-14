"""Fondo-o-meter infographic export renderer using Playwright navigation or HTML synthesis."""

import json as _json
import logging
from typing import Any, Dict, Optional

from kinetiqo.web.renderers.base import (
    extract_flask_cookies_and_port,
    find_chromium_executable,
    playwright_page,
    run_in_clean_thread,
)
from kinetiqo.web.renderers.stats_renderer import normalize_stats_sport_group

logger = logging.getLogger("kinetiqo")


def _render_fondo_sync(
    year: Any = "all",
    sport_group: str = "cycling",
    options: Optional[Dict[str, Any]] = None,
    repo: Any = None,
    config: Any = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Internal synchronous implementation of Fondo-o-meter infographic rendering via Playwright."""
    options = options or {}
    width = int(options.get("width") or 1200)
    height = int(options.get("height") or 1200)
    export_format = str(options.get("format") or "png").lower()
    norm_group = normalize_stats_sport_group(sport_group)
    year_str = str(year or "all")
    arc_color = str(options.get("arc_color") or options.get("arcColor") or "#22c55e")
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
        internal_url = f"http://127.0.0.1:{port}/fondo-o-meter"
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
                setVal('fondo-year',  {_json.dumps(year_str)});
                setVal('fondo-group', {_json.dumps(norm_group)});
                setVal('fondo-size',  {_json.dumps(str(width))});
                var arcColor = {_json.dumps(arc_color)};
                var arcColorInput = document.getElementById('fondo-arc-color');
                if (arcColorInput && arcColor) arcColorInput.value = arcColor;

                var sel = document.getElementById('fondo-year');
                if (sel) sel.dispatchEvent(new Event('change'));
            }})();
            """
            page.evaluate(js_code)
            page.wait_for_timeout(800)

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
                        'z-index:99999'
                    ].join(';') + ';';
                }} catch(e) {{ console.error('Fondo export prep failed', e); }}
            }})();
            """)
            page.wait_for_timeout(300)
            rendered_via_server = True
        except Exception as nav_err:
            logger.warning("Failed to render Fondo via internal URL %s: %s — using fallback HTML", internal_url, nav_err)

        if not rendered_via_server:
            fallback_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ margin: 0; background: #030712; color: #f9fafb; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; }}
                    .fondo {{ text-align: center; }}
                    h1 {{ font-size: 2.5rem; color: #f97316; margin-bottom: 0.5rem; }}
                    p {{ color: #9ca3af; font-size: 1.25rem; }}
                </style>
            </head>
            <body>
                <div class="fondo">
                    <h1>Fondo-o-meter — {year_str}</h1>
                    <p>{norm_group.replace('_', ' ').capitalize()} Endurance Milestones</p>
                </div>
            </body>
            </html>
            """
            page.set_content(fallback_html, wait_until="networkidle")

        if export_format == "pdf":
            return page.pdf(width=f"{width}px", height=f"{height}px", print_background=True)
        else:
            return page.screenshot(type="png")


def render_fondo_artifact(
    year: Any = "all",
    sport_group: str = "cycling",
    options: Optional[Dict[str, Any]] = None,
    repo: Any = None,
    config: Any = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Renders a Fondo-o-meter infographic to PNG or PDF bytes using headless Playwright.

    :param year: Target year or 'all'.
    :param sport_group: 'cycling', 'running', etc.
    :param options: Dict of rendering options (format: 'png'|'pdf', width, height).
    :param repo: Database repository instance (optional).
    :param config: Application configuration instance (optional).
    :param html_content: Synthesized HTML content (optional).
    :return: PNG or PDF bytes.
    """
    opts = extract_flask_cookies_and_port(options)
    return run_in_clean_thread(
        _render_fondo_sync,
        year=year,
        sport_group=sport_group,
        options=opts,
        repo=repo,
        config=config,
        html_content=html_content,
    )
