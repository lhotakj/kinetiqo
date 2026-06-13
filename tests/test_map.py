"""Mocked unit tests for the map page shell and control defaults."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.web.app import app


class TestMapPage(unittest.TestCase):
    """Map page should render the new shared controls with sane defaults."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        self.client = app.test_client()

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
