"""Poster export renderer using in-process HTML synthesis or Playwright rendering."""

import logging
from typing import Any, Dict, Optional

from kinetiqo.web.renderers.base import (
    extract_flask_cookies_and_port,
    find_chromium_executable,
    playwright_page,
    run_in_clean_thread,
)

logger = logging.getLogger("kinetiqo")


def _render_poster_sync(
    activity_id: Any,
    options: Optional[Dict[str, Any]] = None,
    repo: Any = None,
    config: Any = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Internal synchronous implementation of poster rendering via Playwright."""
    options = options or {}
    width = int(options.get("poster_size") or options.get("posterSize") or 1280)
    ratio = str(options.get("ratio") or "4/3")

    if ratio == "16/9":
        height = int(round(width * 9 / 16))
    elif ratio == "1/1":
        height = width
    else:  # default 4/3
        height = int(round(width * 3 / 4))

    cookies = options.get("cookies") or []
    with playwright_page(
        viewport={"width": width, "height": height},
        cookies=cookies,
        device_scale_factor=1,
    ) as (page, browser, context):
        if html_content:
            page.set_content(html_content, wait_until="networkidle")
            return page.screenshot(type="png")

        port = str(options.get("port") or 4444)
        internal_url = f"http://127.0.0.1:{port}/poster/{activity_id}"
        rendered_via_server = False

        try:
            page.goto(internal_url, wait_until="networkidle", timeout=30_000)
            page.wait_for_function("document.fonts.ready", timeout=10_000)
            page.wait_for_selector("#posterContainer", state="visible", timeout=10_000)
            page.wait_for_timeout(600)
            png_bytes = page.screenshot(type="png")
            rendered_via_server = True
            return png_bytes
        except Exception as nav_err:
            logger.warning("Failed to render Poster via internal URL %s: %s — using fallback HTML", internal_url, nav_err)

        if not rendered_via_server:
            fallback_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ margin: 0; background: #0f172a; color: #f8fafc; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; }}
                    .poster {{ text-align: center; }}
                    h1 {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
                    p {{ color: #94a3b8; font-size: 1.25rem; }}
                </style>
            </head>
            <body>
                <div class="poster">
                    <h1>Activity {activity_id}</h1>
                    <p>Kinetiqo Activity Poster</p>
                </div>
            </body>
            </html>
            """
            page.set_content(fallback_html, wait_until="networkidle")

        return page.screenshot(type="png")


def render_poster_artifact(
    activity_id: Any,
    options: Optional[Dict[str, Any]] = None,
    repo: Any = None,
    config: Any = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Renders an activity poster to PNG bytes using headless Playwright.

    :param activity_id: Target activity ID.
    :param options: Dict of rendering options (ratio, poster_size, route_color, etc.).
    :param repo: Database repository instance (optional).
    :param config: Application configuration instance (optional).
    :param html_content: Synthesized HTML content (optional).
    :return: PNG bytes.
    """
    opts = extract_flask_cookies_and_port(options)
    return run_in_clean_thread(
        _render_poster_sync,
        activity_id=activity_id,
        options=opts,
        repo=repo,
        config=config,
        html_content=html_content,
    )
