"""Unit tests for Playwright base renderer helpers and activity renderer."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.web.renderers.base import (
    CHROMIUM_LAUNCH_ARGS,
    extract_flask_cookies_and_port,
    find_chromium_executable,
    playwright_page,
    run_in_clean_thread,
)
from kinetiqo.web.renderers.activity_renderer import render_activity_artifact


class TestRenderersBase(unittest.TestCase):
    def test_find_chromium_executable(self):
        with patch.dict("os.environ", {"PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH": ""}):
            exe = find_chromium_executable()
            self.assertTrue(exe is None or isinstance(exe, str))

    def test_extract_flask_cookies_and_port_without_context(self):
        opts = {"custom": 123}
        res = extract_flask_cookies_and_port(opts)
        self.assertEqual(res["custom"], 123)
        self.assertNotIn("cookies", res)

    @patch("playwright.sync_api.sync_playwright")
    def test_playwright_page_context_manager(self, mock_sync_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        viewport = {"width": 1280, "height": 960}
        cookies = [{"name": "session", "value": "xyz", "domain": "127.0.0.1", "path": "/"}]

        with playwright_page(viewport=viewport, cookies=cookies, device_scale_factor=2) as (page, browser, context):
            self.assertIs(page, mock_page)
            self.assertIs(browser, mock_browser)
            self.assertIs(context, mock_context)
            mock_context.add_cookies.assert_called_once_with(cookies)

        mock_browser.close.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_render_activity_artifact_png(self, mock_sync_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_element = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_page.locator.return_value = mock_element
        mock_element.screenshot.return_value = b"\x89PNG\r\n\x1a\nfake_activity_png"

        png_bytes = render_activity_artifact(
            activity_id=987,
            options={"width": 1280, "height": 960, "format": "png"},
            html_content="<html><body>Activity Canvas</body></html>",
        )

        self.assertEqual(png_bytes, b"\x89PNG\r\n\x1a\nfake_activity_png")
        mock_page.set_content.assert_called_once_with("<html><body>Activity Canvas</body></html>", wait_until="networkidle")
        mock_element.screenshot.assert_called_once_with(type="png")

    @patch("playwright.sync_api.sync_playwright")
    def test_render_activity_artifact_pdf(self, mock_sync_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_page.pdf.return_value = b"%PDF-1.4 fake_activity_pdf"

        pdf_bytes = render_activity_artifact(
            activity_id=987,
            options={"width": 1280, "height": 960, "format": "pdf"},
            html_content="<html><body>Activity Canvas</body></html>",
        )

        self.assertEqual(pdf_bytes, b"%PDF-1.4 fake_activity_pdf")
        mock_page.pdf.assert_called_once()


if __name__ == "__main__":
    unittest.main()
