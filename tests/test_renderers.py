"""Unit tests for decoupled headless renderers (poster, stats, fondo)."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.web.renderers.poster_renderer import render_poster_artifact, find_chromium_executable
from kinetiqo.web.renderers.stats_renderer import render_stats_artifact
from kinetiqo.web.renderers.fondo_renderer import render_fondo_artifact


class TestRenderers(unittest.TestCase):
    """Test suite for decoupled Playwright visual renderers."""

    @patch("playwright.sync_api.sync_playwright")
    def test_render_poster_artifact_mocked_playwright(self, mock_sync_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
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
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
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
        mock_page = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.pdf.return_value = b"%PDF-1.4 fake_fondo_pdf"

        pdf_bytes = render_fondo_artifact(
            year="all",
            sport_group="cycling",
            options={"width": 1200, "height": 1200, "format": "pdf"},
        )

        self.assertEqual(pdf_bytes, b"%PDF-1.4 fake_fondo_pdf")
        mock_page.pdf.assert_called_once()

    def test_find_chromium_executable_returns_string_or_none(self):
        exe = find_chromium_executable()
        self.assertTrue(exe is None or isinstance(exe, str))


if __name__ == "__main__":
    unittest.main()
