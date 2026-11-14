"""Unit tests for decoupled headless renderers (poster, stats, fondo)."""

import asyncio
import threading
import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.web.renderers.poster_renderer import (
    render_poster_artifact,
    find_chromium_executable,
    run_in_clean_thread,
)
from kinetiqo.web.renderers.stats_renderer import render_stats_artifact
from kinetiqo.web.renderers.fondo_renderer import render_fondo_artifact


class TestRenderers(unittest.TestCase):
    """Test suite for decoupled Playwright visual renderers."""

    @patch("playwright.sync_api.sync_playwright")
    def test_render_poster_artifact_mocked_playwright(self, mock_sync_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"\x89PNG\r\n\x1a\nfake_poster_png"

        png_bytes = render_poster_artifact(
            activity_id=12345,
            options={"poster_size": 1280, "ratio": "4/3"},
            html_content="<html><body>Poster</body></html>",
        )

        self.assertEqual(png_bytes, b"\x89PNG\r\n\x1a\nfake_poster_png")
        mock_page.set_content.assert_called_once_with("<html><body>Poster</body></html>", wait_until="networkidle")
        mock_page.screenshot.assert_called_once_with(type="png")
        mock_browser.close.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_render_stats_artifact_png(self, mock_sync_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"\x89PNG\r\n\x1a\nfake_stats_png"

        png_bytes = render_stats_artifact(
            year=2026,
            sport_group="cycling",
            options={"width": 1200, "height": 1400, "format": "png"},
        )

        self.assertEqual(png_bytes, b"\x89PNG\r\n\x1a\nfake_stats_png")
        mock_page.screenshot.assert_called_once_with(type="png")

    @patch("playwright.sync_api.sync_playwright")
    def test_render_fondo_artifact_pdf(self, mock_sync_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_browser.new_page.return_value = mock_page
        mock_page.pdf.return_value = b"%PDF-1.4 fake_fondo_pdf"

        pdf_bytes = render_fondo_artifact(
            year="all",
            sport_group="cycling",
            options={"width": 1200, "height": 1200, "format": "pdf"},
        )

        self.assertEqual(pdf_bytes, b"%PDF-1.4 fake_fondo_pdf")
        mock_page.pdf.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_render_inside_asyncio_event_loop(self, mock_sync_playwright):
        """Verify renderers succeed when called from within an active asyncio event loop."""
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_browser.new_page.return_value = mock_page
        mock_page.screenshot.return_value = b"\x89PNG\r\n\x1a\nasync_loop_png"
        mock_page.pdf.return_value = b"%PDF-1.4 async_loop_pdf"

        async def run_renders():
            stats = render_stats_artifact(year=2026, sport_group="cycling")
            poster = render_poster_artifact(activity_id=999)
            fondo = render_fondo_artifact(year=2026, options={"format": "pdf"})
            return stats, poster, fondo

        stats_res, poster_res, fondo_res = asyncio.run(run_renders())
        self.assertEqual(stats_res, b"\x89PNG\r\n\x1a\nasync_loop_png")
        self.assertEqual(poster_res, b"\x89PNG\r\n\x1a\nasync_loop_png")
        self.assertEqual(fondo_res, b"%PDF-1.4 async_loop_pdf")

    def test_run_in_clean_thread_execution_contexts(self):
        """Verify clean thread dispatching logic across sync and async contexts."""
        main_thread_id = threading.get_ident()

        def probe():
            return threading.get_ident(), asyncio.get_event_loop_policy().get_event_loop() if False else None

        # Outside asyncio loop: runs on current thread
        run_thread_id, _ = run_in_clean_thread(probe)
        self.assertEqual(run_thread_id, main_thread_id)

        # Inside asyncio loop: runs on separate worker thread
        async def async_caller():
            def thread_probe():
                # Inside worker thread, no running loop should exist
                with self.assertRaises(RuntimeError):
                    asyncio.get_running_loop()
                return threading.get_ident()

            return run_in_clean_thread(thread_probe)

        async_thread_id = asyncio.run(async_caller())
        self.assertNotEqual(async_thread_id, main_thread_id)

    def test_find_chromium_executable_returns_string_or_none(self):
        exe = find_chromium_executable()
        self.assertTrue(exe is None or isinstance(exe, str))


if __name__ == "__main__":
    unittest.main()
