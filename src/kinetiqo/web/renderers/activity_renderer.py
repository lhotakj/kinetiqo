"""Activity Detail canvas export renderer using Playwright."""

import json as _json
import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

from kinetiqo.web.renderers.base import (
    extract_flask_cookies_and_port,
    playwright_page,
    run_in_clean_thread,
)

logger = logging.getLogger("kinetiqo.renderers.activity")


def _render_activity_sync(
    activity_id: Any,
    options: Optional[Dict[str, Any]] = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Internal synchronous implementation of Activity Detail canvas rendering via Playwright."""
    payload = options or {}
    export_format = str(payload.get("format", "png")).lower()
    width = max(800, min(int(payload.get("width", 1280)), 2560))
    ratio = str(payload.get("ratio", "auto")).lower()
    height = int(payload.get("height", 960)) if ratio != "auto" else None

    port = str(payload.get("port") or "4444")
    selected_agent = str(payload.get("selectedAgent") or payload.get("agentName") or "").strip()
    agent_param = f"&agent={quote(selected_agent)}" if selected_agent else ""
    internal_url = f"http://127.0.0.1:{port}/activity/{activity_id}?export=1{agent_param}"

    viewport_width = width + 700
    viewport_height = (height or 1400) + 400
    device_scale = 2 if export_format == "png" else 1
    cookies = payload.get("cookies") or []

    with playwright_page(
        viewport={"width": viewport_width, "height": viewport_height},
        cookies=cookies,
        device_scale_factor=device_scale,
    ) as (page, browser, context):
        if html_content:
            page.set_content(html_content, wait_until="networkidle")
            if export_format == "pdf":
                return page.pdf(
                    width=f"{width}px",
                    height=f"{height}px" if height else None,
                    print_background=True,
                    margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
                )
            return page.locator("#activity-canvas").screenshot(type="png")

        page.goto(internal_url, wait_until="networkidle", timeout=30_000)
        page.wait_for_function("document.fonts.ready", timeout=10_000)
        page.wait_for_selector("#activity-canvas", state="visible", timeout=10_000)

        # Ingest settings into localStorage and trigger canvas update
        settings_json = _json.dumps(payload)
        page.evaluate(f"""() => {{
            const s = {settings_json};
            if (window.applyExportSettings) {{
                window.applyExportSettings(s);
            }}
            document.querySelectorAll('.leaflet-control-zoom, .leaflet-control-container').forEach(el => {{
                el.style.setProperty('display', 'none', 'important');
            }});
            const wrapper = document.getElementById('detail-wrapper');
            if (wrapper) {{
                wrapper.style.transform = 'none';
            }}
            const scaler = document.getElementById('detail-preview-scaler');
            if (scaler) {{
                scaler.style.transform = 'none';
            }}
        }}""")

        # Wait for Telemetry Chart to finish rendering
        page.wait_for_function(
            """
(function() {
    var sec = document.getElementById('sec-streams');
    if (!sec || sec.style.display === 'none') return true;
    if (window.telemetryChartReady === true) {
        var c = document.getElementById('telemetry-chart');
        if (!c) return true;
        if (c.width > 0) return true;
        if (typeof Chart !== 'undefined' && Chart.instances && Object.keys(Chart.instances).length > 0) return true;
        try { return (c.getContext && c.getContext('2d')) ? true : false; } catch(e) { return false; }
    }
    return false;
})()
""",
            timeout=30_000,
        )

        # Re-trigger Chart.js resize so the telemetry chart fills the container dimensions
        page.evaluate("""
            (function() {
                var canvas = document.getElementById('telemetry-chart');
                if (canvas && canvas.__chartjs_instance) {
                    canvas.__chartjs_instance.resize();
                }
                if (typeof Chart !== 'undefined' && Chart.instances) {
                    Object.values(Chart.instances).forEach(function(c) { c.resize(); });
                }
                if (window.ensureMapBounds) {
                    window.ensureMapBounds();
                }
                if (typeof window.updateCanvasWatermark === 'function') {
                    window.updateCanvasWatermark();
                }
            })();
        """)

        # Give Leaflet and Chart.js a moment to stabilize
        page.wait_for_timeout(300)

        element = page.locator("#activity-canvas")

        if export_format == "pdf":
            return page.pdf(
                width=f"{width}px",
                height=f"{height}px" if height else None,
                print_background=True,
                margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
            )
        else:
            return element.screenshot(type="png")


def render_activity_artifact(
    activity_id: Any,
    options: Optional[Dict[str, Any]] = None,
    html_content: Optional[str] = None,
) -> bytes:
    """Renders the Activity Detail canvas to PNG or PDF bytes using headless Playwright."""
    opts = extract_flask_cookies_and_port(options)
    return run_in_clean_thread(
        _render_activity_sync,
        activity_id=activity_id,
        options=opts,
        html_content=html_content,
    )
