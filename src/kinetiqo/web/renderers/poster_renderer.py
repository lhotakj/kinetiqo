"""Poster export renderer using in-process HTML synthesis or Playwright rendering."""

import logging
import os
import shutil
from typing import Any, Dict, Optional

logger = logging.getLogger("kinetiqo")


def find_chromium_executable() -> Optional[str]:
    """Finds available Chromium / Chrome binary on the system."""
    exe_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if exe_path and os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
        return exe_path

    executable_names = [
        "chromium",
        "chromium-browser",
        "chromium-headless-shell",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
    ]
    for name in executable_names:
        exe = shutil.which(name)
        if exe:
            return exe

    if os.name == "nt":
        common_paths = [
            r"C:\Program Files\Chromium\Application\chrome.exe",
            r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in common_paths:
            if os.path.isfile(path):
                return path
    else:
        common_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            "/opt/chromium/chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

    return None


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
    options = options or {}
    width = int(options.get("poster_size") or options.get("posterSize") or 1280)
    ratio = str(options.get("ratio") or "4/3")

    if ratio == "16/9":
        height = int(round(width * 9 / 16))
    elif ratio == "1/1":
        height = width
    else:  # default 4/3
        height = int(round(width * 3 / 4))

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

            png_bytes = page.screenshot(type="png")
            return png_bytes
        finally:
            browser.close()
