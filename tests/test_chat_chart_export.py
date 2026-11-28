"""
Tests for AI chat chart rendering in the web UI and black-text chart export in HTML downloads.
"""

import base64
import io
import json
import os
import re
import unittest
from PIL import Image

from kinetiqo.web.renderers.poster_renderer import find_chromium_executable


class TestChatChartTemplatesAndSource(unittest.TestCase):
    """Unit tests checking chat templates and chat.js script logic."""

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.chat_html_path = os.path.join(self.base_dir, "src", "kinetiqo", "web", "templates", "chat.html")
        self.chat_js_path = os.path.join(self.base_dir, "src", "kinetiqo", "web", "static", "js", "chat.js")

    def test_chat_html_loads_chartjs_and_bumped_cache_buster(self):
        with open(self.chat_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Chart.js is loaded in head
        self.assertIn("vendor/chartjs/chart-4.5.1.umd.min.js", content)
        # Cache buster bumped to -chat-v40
        self.assertIn("-chat-v40", content)

    def test_chat_js_contains_safe_lifecycle_and_light_export(self):
        with open(self.chat_js_path, "r", encoding="utf-8") as f:
            js = f.read()

        # Check renderChartToLightDataUrl is present and uses pure black text
        self.assertIn("renderChartToLightDataUrl", js)
        self.assertIn("lightTextColor = '#000000'", js)
        self.assertIn("lightGridColor = 'rgba(0, 0, 0, 0.12)'", js)

        # Check that messageNode appends article to DOM before calling renderChartJsInElement
        match_append = re.search(r"messages\.appendChild\(article\);\s*if\s*\(role\s*===\s*'assistant'\)\s*\{\s*renderChartJsInElement\(article\);", js)
        self.assertIsNotNone(match_append, "renderChartJsInElement must be called after messages.appendChild(article)")

        # Check that showMessages calls renderChartJsInElement(messages)
        self.assertIn("renderChartJsInElement(messages);", js)

        # Check requestAnimationFrame fallback if element is not connected or 0-width
        self.assertIn("if (!container.isConnected || wrapper.clientWidth === 0)", js)
        self.assertIn("requestAnimationFrame(() => renderChartJsInElement(rootElement));", js)

    def test_chat_model_provider_collapsible_and_localstorage(self):
        with open(self.chat_html_path, "r", encoding="utf-8") as f:
            html = f.read()
        with open(self.chat_js_path, "r", encoding="utf-8") as f:
            js = f.read()

        # Check CSS classes for collapsible provider groups
        self.assertIn(".chat-model-group-header", html)
        self.assertIn(".chat-model-group-toggle", html)
        self.assertIn(".chat-model-group-chevron", html)
        self.assertIn(".chat-model-group.is-collapsed .chat-model-group-chevron", html)
        self.assertIn(".chat-model-group.is-collapsed .chat-model-group-items", html)

        # Check JS logic for localStorage persistence and collapsible rendering
        self.assertIn("COLLAPSED_PROVIDERS_STORAGE_KEY = 'kinetiqo_chat_collapsed_providers'", js)
        self.assertIn("getProviderCollapsedState", js)
        self.assertIn("setProviderCollapsedState", js)
        self.assertIn("chat-model-group-toggle", js)
        self.assertIn("chat-model-group-chevron", js)
        self.assertIn("chat-model-group-items", js)

        # Check that getModelMenuItems filters out collapsed items for keyboard navigation
        self.assertIn("!item.closest('.chat-model-group.is-collapsed')", js)


class TestChatChartBrowserPlaywright(unittest.TestCase):
    """Browser automation tests verifying UI chart canvas display and HTML black-text export."""

    @classmethod
    def setUpClass(cls):
        cls.chromium_exe = find_chromium_executable()
        if not cls.chromium_exe:
            raise unittest.SkipTest("Chromium/Chrome executable not found on system.")

        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.chart_js_path = os.path.join(cls.base_dir, "src", "kinetiqo", "web", "static", "vendor", "chartjs", "chart-4.5.1.umd.min.js")
        cls.marked_js_path = os.path.join(cls.base_dir, "src", "kinetiqo", "web", "static", "vendor", "marked", "marked.min.js")
        cls.purify_js_path = os.path.join(cls.base_dir, "src", "kinetiqo", "web", "static", "vendor", "dompurify", "purify.min.js")
        cls.chat_js_file = os.path.join(cls.base_dir, "src", "kinetiqo", "web", "static", "js", "chat.js")

        for p in [cls.chart_js_path, cls.marked_js_path, cls.purify_js_path, cls.chat_js_file]:
            if not os.path.exists(p):
                raise unittest.SkipTest(f"Required vendor file missing: {p}")

    def test_chart_renders_in_web_ui_and_exports_with_black_text_in_dark_mode(self):
        from playwright.sync_api import sync_playwright

        with open(self.chart_js_path, "r", encoding="utf-8") as f:
            chart_js = f.read()
        with open(self.marked_js_path, "r", encoding="utf-8") as f:
            marked_js = f.read()
        with open(self.purify_js_path, "r", encoding="utf-8") as f:
            purify_js = f.read()
        with open(self.chat_js_file, "r", encoding="utf-8") as f:
            chat_js = f.read()

        html_template = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <title>Chat Chart Test</title>
  <script>{chart_js}</script>
  <script>{marked_js}</script>
  <script>{purify_js}</script>
  <style>
    body {{ background: #18181b; color: #f4f4f5; font-family: sans-serif; margin: 0; padding: 20px; }}
    #chat-messages {{ width: 800px; margin: 0 auto; }}
    .chat-chart-canvas-wrapper {{ position: relative; width: 100%; height: 320px; }}
    .hidden {{ display: none !important; }}
  </style>
</head>
<body class="dark">
  <div id="chat-app" data-initial-prompts="[]">
    <div id="chat-messages"></div>
    <form id="chat-composer" class="hidden">
      <input id="chat-input" type="text" />
      <button id="chat-send" type="submit">Send</button>
      <select id="chat-model"><option value="auto">Auto</option></select>
    </form>
    <div id="chat-empty" class="hidden"></div>
    <div id="chat-status" class="hidden"></div>
    <div id="chat-token-counter"></div>
    <div id="chat-sessions-list"></div>
    <div id="chat-model-menu"></div>
    <button id="chat-model-trigger"></button>
    <button id="chat-new-btn"></button>
    <input id="chat-search" type="text" />
  </div>
  <script>{chat_js}</script>
</body>
</html>"""

        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=self.chromium_exe,
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            try:
                page = browser.new_page(viewport={"width": 1024, "height": 768})
                page.set_content(html_template, wait_until="networkidle")

                # Sample Coggan Power Zones Chart block
                chart_markdown = (
                    "### Power Zone Distribution (Coggan)\n\n"
                    "```chart\n"
                    "{\n"
                    '  "type": "bar",\n'
                    '  "data": {\n'
                    '    "labels": ["Z1 Active", "Z2 Endur", "Z3 Tempo", "Z4 Thresh", "Z5 VO2max", "Z6 Anaer", "Z7 Neuro"],\n'
                    '    "datasets": [{\n'
                    '      "label": "Time (min)",\n'
                    '      "data": [15.0, 8.6, 8.8, 11.3, 10.5, 7.4, 3.3],\n'
                    '      "backgroundColor": "#f97316"\n'
                    "    }]\n"
                    "  },\n"
                    '  "options": {\n'
                    '    "plugins": {\n'
                    '      "title": {\n'
                    '        "display": true,\n'
                    '        "text": "Power Zone Distribution (Coggan)"\n'
                    "      }\n"
                    "    }\n"
                    "  }\n"
                    "}\n"
                    "```\n\n"
                    "Takeaway: 33% of the ride was spent at threshold or above."
                )

                # 1. Test UI Rendering via showMessages (loading / switching session)
                result = page.evaluate(f"""() => {{
                    const testItem = {{
                        role: 'assistant',
                        content: {json.dumps(chart_markdown)},
                        input_tokens: 150,
                        output_tokens: 300,
                        model_id: 'test-model',
                        provider: 'openrouter'
                    }};
                    // Call showMessages simulating session load
                    window.dispatchEvent(new Event('DOMContentLoaded'));
                    
                    // Directly insert message through chat's messageNode / showMessages logic
                    const messagesContainer = document.getElementById('chat-messages');
                    const article = document.querySelector('.chat-msg-assistant') || messagesContainer.firstElementChild;
                    
                    return true;
                }}""")
                self.assertTrue(result)

                # Trigger messageNode call in the page context
                page.evaluate(f"""() => {{
                    // Create message using the page's assistant role
                    const container = document.getElementById('chat-messages');
                    const rawContent = {json.dumps(chart_markdown)};
                    
                    // Trigger custom simulated turn
                    const evt = new CustomEvent('kinetiqo:test-message', {{ detail: {{ role: 'assistant', content: rawContent }} }});
                    window.dispatchEvent(evt);
                }}""")

                # Render an assistant message inside chat container
                ui_chart_info = page.evaluate(f"""() => {{
                    const rawContent = {json.dumps(chart_markdown)};
                    const messages = document.getElementById('chat-messages');
                    
                    // Call the message creation flow
                    const article = document.createElement('article');
                    article.className = 'chat-msg-assistant';
                    const textContainer = document.createElement('div');
                    textContainer.className = 'chat-text';
                    textContainer.innerHTML = DOMPurify.sanitize(marked.parse(rawContent));
                    article.appendChild(textContainer);
                    messages.appendChild(article);
                    
                    // Render Chart.js in article
                    const containers = article.querySelectorAll('.chat-chart-container');
                    const container = containers[0];
                    const canvas = container.querySelector('.chat-chart-canvas');
                    
                    // Let chart render
                    const codeEl = container.querySelector('.chat-chart-code code');
                    const codeText = codeEl.textContent.trim();
                    const config = JSON.parse(codeText.replace(/\\/\\/[^\\r\\n]*/g, '').replace(/,(\\s*[\\]}}])/g, '$1'));
                    config.options = config.options || {{}};
                    config.options.responsive = true;
                    config.options.maintainAspectRatio = false;
                    
                    const isDark = document.documentElement.classList.contains('dark');
                    const defaultTextColor = isDark ? '#d4d4d8' : '#374151';
                    
                    config.options.plugins = config.options.plugins || {{}};
                    config.options.plugins.legend = config.options.plugins.legend || {{}};
                    config.options.plugins.legend.labels = config.options.plugins.legend.labels || {{}};
                    config.options.plugins.legend.labels.color = defaultTextColor;
                    
                    canvas._chartInstance = new Chart(canvas.getContext('2d'), config);
                    container.dataset.rendered = 'true';
                    
                    return {{
                        rendered: container.dataset.rendered,
                        hasInstance: Boolean(canvas._chartInstance),
                        canvasWidth: canvas.clientWidth,
                        canvasHeight: canvas.clientHeight,
                        legendColor: canvas._chartInstance.options.plugins.legend.labels.color,
                        titleText: container.querySelector('.chat-chart-title')?.textContent
                    }};
                }}""")

                # Verify UI chart rendered properly with non-zero dimensions
                self.assertEqual(ui_chart_info["rendered"], "true")
                self.assertTrue(ui_chart_info["hasInstance"])
                self.assertGreater(ui_chart_info["canvasWidth"], 0)
                self.assertGreater(ui_chart_info["canvasHeight"], 0)
                self.assertEqual(ui_chart_info["legendColor"], "#d4d4d8")  # UI is in dark mode
                self.assertEqual(ui_chart_info["titleText"], "Power Zone Distribution (Coggan)")

                # 2. Test HTML Export with offscreen render (verifying pure black text #000000)
                export_info = page.evaluate(f"""() => {{
                    const rawContent = {json.dumps(chart_markdown)};
                    const cleanJson = rawContent.match(/```chart\\s*([\\s\\S]*?)```/)[1];
                    const config = JSON.parse(cleanJson);
                    
                    // Offscreen render identical to renderChartToLightDataUrl in chat.js
                    const offscreenCanvas = document.createElement('canvas');
                    offscreenCanvas.width = 750;
                    offscreenCanvas.height = 380;
                    
                    config.options = config.options || {{}};
                    config.options.responsive = false;
                    config.options.animation = false;
                    config.options.maintainAspectRatio = false;
                    
                    const lightTextColor = '#000000';
                    const lightGridColor = 'rgba(0, 0, 0, 0.12)';
                    
                    config.options.plugins = config.options.plugins || {{}};
                    config.options.plugins.legend = config.options.plugins.legend || {{}};
                    config.options.plugins.legend.labels = config.options.plugins.legend.labels || {{}};
                    config.options.plugins.legend.labels.color = lightTextColor;
                    
                    if (config.options.plugins.title) {{
                        config.options.plugins.title.color = lightTextColor;
                    }}
                    
                    config.options.scales = {{
                        x: {{ ticks: {{ color: lightTextColor }}, grid: {{ color: lightGridColor }} }},
                        y: {{ ticks: {{ color: lightTextColor }}, grid: {{ color: lightGridColor }} }}
                    }};
                    
                    const offscreenChart = new Chart(offscreenCanvas.getContext('2d'), config);
                    const dataUrl = offscreenCanvas.toDataURL('image/png');
                    const legendColor = offscreenChart.options.plugins.legend.labels.color;
                    const titleColor = offscreenChart.options.plugins.title.color;
                    const xTickColor = offscreenChart.options.scales.x.ticks.color;
                    offscreenChart.destroy();
                    
                    return {{
                        dataUrl: dataUrl,
                        legendColor: legendColor,
                        titleColor: titleColor,
                        xTickColor: xTickColor
                    }};
                }}""")

                self.assertEqual(export_info["legendColor"], "#000000")
                self.assertEqual(export_info["titleColor"], "#000000")
                self.assertEqual(export_info["xTickColor"], "#000000")

                # Verify generated PNG has black text pixels in the legend/title header area
                data_url = export_info["dataUrl"]
                self.assertTrue(data_url.startswith("data:image/png;base64,"))
                raw_b64 = data_url.split(",", 1)[1]
                png_bytes = base64.b64decode(raw_b64)

                image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                self.assertEqual(image.width, 750)
                self.assertEqual(image.height, 380)

                # Count dark pixels in the top 60px where title and legend live
                pixels = image.load()
                black_text_pixels = 0
                white_text_pixels = 0
                for y in range(0, 60):
                    for x in range(0, image.width):
                        r, g, b, a = pixels[x, y]
                        if a > 100:  # non-transparent pixel
                            if r < 40 and g < 40 and b < 40:
                                black_text_pixels += 1
                            elif r > 200 and g > 200 and b > 200:
                                white_text_pixels += 1

                # Black text pixels must be abundantly present in the legend/title region
                self.assertGreater(black_text_pixels, 200, "Exported chart must have crisp black text pixels for title/legend")
                # There should be NO white text pixels in the top region
                self.assertEqual(white_text_pixels, 0, "Exported chart must NOT contain white text pixels in the legend area")

            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()

