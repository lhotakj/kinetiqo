"""Unit tests for the modular poster image processing filters."""

import unittest
from PIL import Image

from kinetiqo.web.poster_filters import (
    DEFAULT_PHOTO_FILTERS,
    apply_all_poster_filters,
    apply_color_filters,
    apply_detail_filters,
    apply_light_filters,
    normalize_filter_settings,
)


class TestPosterFilters(unittest.TestCase):
    """Test suite verifying poster filter normalization and Pillow operations."""

    def setUp(self):
        # Create a small RGB test canvas
        self.img_rgb = Image.new('RGB', (64, 64), color=(180, 100, 60))
        # Create a small RGBA test canvas
        self.img_rgba = Image.new('RGBA', (64, 64), color=(180, 100, 60, 200))

    def test_normalize_filter_settings_defaults(self):
        """Empty or None input yields complete default schema with 17 keys."""
        normalized = normalize_filter_settings(None)
        self.assertEqual(normalized['color']['vibrance'], 0)
        self.assertEqual(normalized['color']['saturation'], 0)
        self.assertEqual(normalized['color']['temperature'], 0)
        self.assertEqual(normalized['color']['tint'], 0)
        self.assertEqual(normalized['color']['hue'], 0)

        self.assertEqual(normalized['light']['brightness'], 0)
        self.assertEqual(normalized['light']['exposure'], 0)
        self.assertEqual(normalized['light']['contrast'], 0)
        self.assertEqual(normalized['light']['black'], 0)
        self.assertEqual(normalized['light']['white'], 0)
        self.assertEqual(normalized['light']['highlights'], 0)
        self.assertEqual(normalized['light']['shadows'], 0)

        self.assertEqual(normalized['details']['sharpen'], 0)
        self.assertEqual(normalized['details']['clarity'], 0)
        self.assertEqual(normalized['details']['smooth'], 0)
        self.assertEqual(normalized['details']['blur'], 0)
        self.assertEqual(normalized['details']['grain'], 0)

    def test_normalize_clamps_bounds(self):
        """Values outside permissible ranges are clamped safely."""
        raw = {
            'color': {'vibrance': 500, 'saturation': -999},
            'light': {'brightness': 250},
            'details': {'sharpen': -50, 'blur': 999}
        }
        normalized = normalize_filter_settings(raw)
        self.assertEqual(normalized['color']['vibrance'], 100)
        self.assertEqual(normalized['color']['saturation'], -100)
        self.assertEqual(normalized['light']['brightness'], 100)
        # Sharpen is unipolar 0..100
        self.assertEqual(normalized['details']['sharpen'], 0)
        self.assertEqual(normalized['details']['blur'], 100)

    def test_no_op_when_all_zero(self):
        """When all settings are zero, image is returned untouched."""
        res = apply_all_poster_filters(self.img_rgb, DEFAULT_PHOTO_FILTERS)
        self.assertEqual(res.size, self.img_rgb.size)
        self.assertEqual(res.mode, 'RGB')

    def test_color_filters_rgb_and_rgba(self):
        """Color adjustments run without errors on RGB and RGBA buffers."""
        settings = {'vibrance': 25, 'saturation': 30, 'temperature': 15, 'tint': -10, 'hue': 20}
        out_rgb = apply_color_filters(self.img_rgb, settings)
        self.assertEqual(out_rgb.size, (64, 64))
        self.assertEqual(out_rgb.mode, 'RGB')

        out_rgba = apply_color_filters(self.img_rgba, settings)
        self.assertEqual(out_rgba.size, (64, 64))
        self.assertEqual(out_rgba.mode, 'RGBA')
        # Alpha channel preserved
        self.assertEqual(out_rgba.getchannel('A').getpixel((0, 0)), 200)

    def test_light_filters_rgb_and_rgba(self):
        """Light adjustments run without errors on RGB and RGBA buffers."""
        settings = {
            'brightness': 10,
            'exposure': 15,
            'contrast': 20,
            'black': -5,
            'white': 10,
            'highlights': -15,
            'shadows': 20
        }
        out_rgb = apply_light_filters(self.img_rgb, settings)
        self.assertEqual(out_rgb.size, (64, 64))
        self.assertEqual(out_rgb.mode, 'RGB')

        out_rgba = apply_light_filters(self.img_rgba, settings)
        self.assertEqual(out_rgba.size, (64, 64))
        self.assertEqual(out_rgba.mode, 'RGBA')

    def test_detail_filters_rgb_and_rgba(self):
        """Detail adjustments run without errors on RGB and RGBA buffers."""
        settings = {'sharpen': 30, 'clarity': 25, 'smooth': 10, 'blur': 15, 'grain': 20}
        out_rgb = apply_detail_filters(self.img_rgb, settings)
        self.assertEqual(out_rgb.size, (64, 64))
        self.assertEqual(out_rgb.mode, 'RGB')

        out_rgba = apply_detail_filters(self.img_rgba, settings)
        self.assertEqual(out_rgba.size, (64, 64))
        self.assertEqual(out_rgba.mode, 'RGBA')

    def test_full_pipeline(self):
        """Applying full pipeline processes all three categories consecutively."""
        full_settings = {
            'color': {'temperature': 20, 'saturation': 15},
            'light': {'exposure': 10, 'contrast': 10},
            'details': {'sharpen': 25, 'grain': 15}
        }
        out = apply_all_poster_filters(self.img_rgb, full_settings)
        self.assertEqual(out.size, (64, 64))
        # Pixel values should have changed from input
        self.assertNotEqual(out.getpixel((32, 32)), self.img_rgb.getpixel((32, 32)))


if __name__ == '__main__':
    unittest.main()
