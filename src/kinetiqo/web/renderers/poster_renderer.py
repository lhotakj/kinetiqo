"""Poster export renderer using in-process HTML synthesis or Playwright rendering."""

import asyncio
import concurrent.futures
import json as _json
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("kinetiqo")


def run_in_clean_thread(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Execute a function in a clean worker thread if the current thread has an active asyncio loop.

    Playwright's Sync API uses greenlets and explicitly prohibits being called inside
    an active asyncio event loop thread. When invoked from asynchronous frameworks
    (such as FastMCP or in-process asyncio event loops), running in a separate worker
    thread ensures no asyncio event loop is active on the executing thread.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            return future.result()

    return func(*args, **kwargs)


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

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium") from e

    chromium_exe = find_chromium_executable()
    launch_kwargs: Dict[str, Any] = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--font-render-hinting=none",
        ],
    }
    if chromium_exe:
        launch_kwargs["executable_path"] = chromium_exe

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
                ignore_https_errors=True,
            )
            cookies = options.get("cookies") or []
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception:
                    pass

            page = context.new_page()

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

            png_bytes = page.screenshot(type="png")
            return png_bytes
        finally:
            browser.close()


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
    opts = dict(options or {})
    try:
        import flask
        if flask.has_request_context():
            if "cookies" not in opts:
                c_list = []
                for n, v in flask.request.cookies.items():
                    c_list.append({"name": n, "value": v, "domain": "127.0.0.1", "path": "/"})
                    c_list.append({"name": n, "value": v, "domain": "localhost", "path": "/"})
                opts["cookies"] = c_list
            if "port" not in opts:
                host = flask.request.host
                opts["port"] = host.split(":")[1] if ":" in host else "4444"
    except Exception:
        pass

    return run_in_clean_thread(
        _render_poster_sync,
        activity_id=activity_id,
        options=opts,
        repo=repo,
        config=config,
        html_content=html_content,
    )
