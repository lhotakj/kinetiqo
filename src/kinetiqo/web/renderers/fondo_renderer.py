"""Fondo-o-meter infographic export renderer using in-process HTML synthesis or Playwright."""

import logging
from typing import Any, Dict, Optional
from kinetiqo.web.renderers.poster_renderer import find_chromium_executable

logger = logging.getLogger("kinetiqo")


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
    options = options or {}
    width = int(options.get("width") or 1200)
    height = int(options.get("height") or 1200)
    export_format = str(options.get("format") or "png").lower()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium") from e

    chromium_exe = find_chromium_executable()
    launch_kwargs: Dict[str, Any] = {"headless": True}
    if chromium_exe:
        launch_kwargs["executable_path"] = chromium_exe
    else:
        launch_kwargs["args"] = ["--no-sandbox", "--disable-setuid-sandbox"]

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            if html_content:
                page.set_content(html_content, wait_until="networkidle")
            else:
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
                        <h1>Fondo-o-meter — {year}</h1>
                        <p>{sport_group.capitalize()} Endurance Milestones</p>
                    </div>
                </body>
                </html>
                """
                page.set_content(fallback_html, wait_until="networkidle")

            if export_format == "pdf":
                pdf_bytes = page.pdf(width=f"{width}px", height=f"{height}px", print_background=True)
                return pdf_bytes
            else:
                png_bytes = page.screenshot(type="png")
                return png_bytes
        finally:
            browser.close()
