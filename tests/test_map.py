"""Mocked unit tests for the map page shell and control defaults."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.web.app import app, _build_tile_providers, config


class TestMapPage(unittest.TestCase):
    """Map page should render the new shared controls with sane defaults."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        self._csrf_enabled = app.config.get('WTF_CSRF_ENABLED', True)
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def tearDown(self):
        app.config['WTF_CSRF_ENABLED'] = self._csrf_enabled

    @patch('flask_login.utils._get_user')
    def test_map_page_includes_new_controls(self, mock_get_user):
        """The map shell should render the compact map controls and defaults."""

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        response = self.client.post('/map', data={'activity_ids[]': ['123']})
        self.assertEqual(response.status_code, 200)

        html = response.data.decode()

        self.assertIn('id="mapOpacityPicker"', html)
        self.assertIn('id="mapOpacityValue"', html)
        self.assertIn('id="mapTonePicker"', html)
        self.assertIn('id="mapToneClearBtn"', html)
        self.assertIn('id="map-tone-overlay"', html)
        self.assertIn('id="toneOpacityPicker"', html)
        self.assertIn('id="toneOpacityValue"', html)
        self.assertIn('id="opacityValue"', html)
        self.assertIn('value="100"', html)
        self.assertIn('value="50"', html)
        self.assertIn('>None<', html)

    def test_geoapify_layers_are_disabled_without_api_key(self):
        original_key = config.geoapify_api_key
        try:
            config.geoapify_api_key = ""
            providers = _build_tile_providers()
        finally:
            config.geoapify_api_key = original_key

        for key in ("geoapify_osm_bright", "geoapify_osm_carto", "geoapify_dark_matter"):
            with self.subTest(provider=key):
                self.assertIn(key, providers)
                self.assertTrue(providers[key]["disabled"])
                self.assertEqual(providers[key]["url"], "")
                self.assertIn("Geoapify", providers[key]["name"])

    def test_geoapify_layers_use_configured_api_key(self):
        original_key = config.geoapify_api_key
        try:
            config.geoapify_api_key = "test-geoapify-key"
            providers = _build_tile_providers()
        finally:
            config.geoapify_api_key = original_key

        expected_styles = {
            "geoapify_osm_bright": "osm-bright",
            "geoapify_osm_carto": "osm-carto",
            "geoapify_dark_matter": "dark-matter",
        }
        for key, style in expected_styles.items():
            with self.subTest(provider=key):
                self.assertNotIn("disabled", providers[key])
                self.assertEqual(providers[key]["maxZoom"], 20)
                self.assertIn(f"/v1/tile/{style}/{{z}}/{{x}}/{{y}}.png", providers[key]["url"])
                self.assertIn("apiKey=test-geoapify-key", providers[key]["url"])
                self.assertIn("Powered by", providers[key]["attr"])
                self.assertIn("Geoapify", providers[key]["attr"])

    @patch('flask_login.utils._get_user')
    def test_map_page_lists_geoapify_layers(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user

        original_key = config.geoapify_api_key
        try:
            config.geoapify_api_key = ""
            response = self.client.post('/map', data={'activity_ids[]': ['123']})
        finally:
            config.geoapify_api_key = original_key

        self.assertEqual(response.status_code, 200)
        html = response.data.decode()
        self.assertIn('value="geoapify_osm_bright"', html)
        self.assertIn('Geoapify (OSM Bright) (API key required)', html)
        self.assertIn('value="geoapify_osm_carto"', html)
        self.assertIn('Geoapify (OSM Carto) (API key required)', html)
        self.assertIn('value="geoapify_dark_matter"', html)
        self.assertIn('Geoapify (Dark Matter) (API key required)', html)
