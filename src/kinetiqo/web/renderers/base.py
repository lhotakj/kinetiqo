"""Base Playwright rendering infrastructure and browser lifecycle helpers."""

import asyncio
import concurrent.futures
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, Generator, Optional, Tuple

logger = logging.getLogger("kinetiqo.renderers")

CHROMIUM_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--font-render-hinting=none",
]


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


def extract_flask_cookies_and_port(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract cookies and port from active Flask request context if present."""
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
    return opts


@contextmanager
def playwright_page(
    viewport: Dict[str, int],
    cookies: Optional[list[Dict[str, Any]]] = None,
    device_scale_factor: int = 1,
) -> Generator[Tuple[Any, Any, Any], None, None]:
    """Context manager setting up a Playwright browser, context, and page with standardized flags."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from e

    chromium_exe = find_chromium_executable()
    launch_kwargs: Dict[str, Any] = {
        "headless": True,
        "args": CHROMIUM_LAUNCH_ARGS,
    }
    if chromium_exe:
        launch_kwargs["executable_path"] = chromium_exe

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(
                viewport=viewport,
                device_scale_factor=device_scale_factor,
                ignore_https_errors=True,
            )
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception:
                    pass
            page = context.new_page()
            yield page, browser, context
        finally:
            try:
                browser.close()
            except Exception:
                pass
