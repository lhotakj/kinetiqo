"""Tests for the shared Google Fonts catalog."""

import unittest

from kinetiqo.web.fonts import (
    BASE_GOOGLE_FONTS_URL,
    GOOGLE_FONT_CATALOG,
    LOGIN_GOOGLE_FONTS_URL,
    POSTER_GOOGLE_FONTS_URL,
    POSTER_GOOGLE_FONT_NAMES,
    BASE_GOOGLE_FONT_NAMES,
    LOGIN_GOOGLE_FONT_NAMES,
    build_google_fonts_stylesheet_url,
)


class TestGoogleFontsCatalog(unittest.TestCase):
    """Unit tests for the shared Google Fonts helper module."""

    def test_catalog_includes_new_fonts(self):
        """The shared catalog should expose the added poster fonts."""

        for font_name in ("Oswald", "Ubuntu", "Bebas Neue"):
            with self.subTest(font_name=font_name):
                self.assertIn(font_name, GOOGLE_FONT_CATALOG)

    def test_font_groups_include_expected_fonts(self):
        """The context-facing font groups should stay aligned with the catalog."""

        self.assertEqual(BASE_GOOGLE_FONT_NAMES, ("Inter", "Italiana"))
        self.assertEqual(LOGIN_GOOGLE_FONT_NAMES, ("Inter", "Italiana", "Merriweather"))
        for font_name in ("Oswald", "Ubuntu", "Bebas Neue"):
            with self.subTest(font_name=font_name):
                self.assertIn(font_name, POSTER_GOOGLE_FONT_NAMES)

    def test_precomputed_urls_are_stable_strings(self):
        """The pre-computed URL constants must be plain strings, not callables."""

        for name, url in (
            ("base", BASE_GOOGLE_FONTS_URL),
            ("login", LOGIN_GOOGLE_FONTS_URL),
            ("poster", POSTER_GOOGLE_FONTS_URL),
        ):
            with self.subTest(url_name=name):
                self.assertIsInstance(url, str)
                self.assertTrue(url.startswith("https://fonts.googleapis.com/css2?"))
                self.assertTrue(url.endswith("&display=swap"))

    def test_precomputed_urls_match_builder_output(self):
        """Pre-computed constants must equal the output of the URL builder."""

        self.assertEqual(
            BASE_GOOGLE_FONTS_URL,
            build_google_fonts_stylesheet_url(BASE_GOOGLE_FONT_NAMES),
        )
        self.assertEqual(
            POSTER_GOOGLE_FONTS_URL,
            build_google_fonts_stylesheet_url(POSTER_GOOGLE_FONT_NAMES),
        )

    def test_stylesheet_url_contains_poster_fonts(self):
        """The poster URL must reference each new font's stylesheet fragment."""

        self.assertIn("family=Oswald:wght@400;700", POSTER_GOOGLE_FONTS_URL)
        self.assertIn("family=Ubuntu:wght@400;700", POSTER_GOOGLE_FONTS_URL)
        self.assertIn("family=Bebas+Neue:wght@400", POSTER_GOOGLE_FONTS_URL)
