import io
import os
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.web.app import app, mark_startup_sync_done


class TestStatsImageAndUI(unittest.TestCase):
    """Test suite for Mega Stats background image upload, reset, and UI elements."""

    def setUp(self):
        mark_startup_sync_done()
        self._orig_testing = app.config.get('TESTING')
        self._orig_login_disabled = app.config.get('LOGIN_DISABLED')
        self._orig_csrf = app.config.get('WTF_CSRF_ENABLED')
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        self.cache_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / '..' / 'src' / 'kinetiqo' / 'web' / 'posters-cache'
        self.cached_file = self.cache_dir / "stats_bg.png"

        self.mock_repo = MagicMock()
        self.mock_repo.get_activities_web.return_value = [{'start_date': '2025-01-01T00:00:00Z'}]
        self.mock_repo.get_profile.return_value = {'first_name': 'Test', 'last_name': 'Athlete'}
        self.mock_repo.get_activities_by_ids.return_value = [{
            'id': 1,
            'name': 'Morning Ride',
            'type': 'Ride',
            'distance': 25000,
            'total_elevation_gain': 300,
            'moving_time': 3600,
            'start_date_local': '2025-06-01T08:00:00',
            'summary_polyline': ''
        }]

    def tearDown(self):
        app.config['TESTING'] = self._orig_testing
        app.config['LOGIN_DISABLED'] = self._orig_login_disabled
        app.config['WTF_CSRF_ENABLED'] = self._orig_csrf
        if self.cached_file.exists():
            try:
                self.cached_file.unlink()
            except Exception:
                pass

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_stats_page_contains_new_elements(self, mock_get_db, mock_get_user):
        """GET /stats renders Stats Options box, Font dropdown, and Image upload controls."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user
        mock_get_db.return_value = self.mock_repo

        resp = self.client.get('/stats')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Unified "Stats Options" box
        self.assertIn('Stats Options', html)
        self.assertIn('stats-title-font-size', html)
        self.assertIn('stats-column-width', html)
        self.assertIn('data-layout="stacked"', html)
        self.assertIn('class="ig-stat-row"', html)

        # Appearance box contains font dropdown, image upload/reset, tint and opacity
        self.assertIn('stats-font', html)
        self.assertIn('stats-upload-input', html)
        self.assertIn('stats-clear-image-btn', html)
        self.assertIn('stats-tint', html)
        self.assertIn('stats-tint-clear-btn', html)
        self.assertIn('stats-opacity', html)

        # Collapsible boxes with data-box-id
        self.assertIn('data-box-id="statsSize"', html)
        self.assertIn('data-box-id="statsPeriod"', html)
        self.assertIn('data-box-id="statsAppearance"', html)
        self.assertIn('data-box-id="statsOptions"', html)

        # Infographic contains background image and overlay elements
        self.assertIn('id="ig-bg-image"', html)
        self.assertIn('id="ig-bg-overlay"', html)

        # Poster Google fonts CSS is linked in head
        self.assertIn('google_fonts_poster', html)

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.get_db')
    def test_poster_page_contains_reused_elements(self, mock_get_db, mock_get_user):
        """GET /poster/<activity_id> renders successfully using extracted reusable partials."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 'admin'
        mock_get_user.return_value = mock_user
        mock_get_db.return_value = self.mock_repo

        resp = self.client.get('/poster/1')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('uploadInput', html)
        self.assertIn('clearImageBtn', html)
        self.assertIn('titleFont', html)
        self.assertIn('statsFont', html)
        self.assertIn('mapToneColor', html)
        self.assertIn('mapToneClearBtn', html)
        self.assertIn('mapOpacity', html)
        self.assertIn('toneOpacity', html)

    def test_stats_photo_upload_valid_image(self):
        """POST /api/stats/upload uploads and converts image to cached PNG."""
        img = Image.new('RGB', (40, 40), color='purple')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        jpeg_bytes = buf.getvalue()

        data = {
            'file': (io.BytesIO(jpeg_bytes), 'bg_photo.jpg')
        }

        resp = self.client.post(
            '/api/stats/upload',
            data=data,
            content_type='multipart/form-data'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'image/png')
        self.assertTrue(self.cached_file.exists())

    def test_stats_photo_upload_no_file(self):
        """POST /api/stats/upload with no file returns 400 error."""
        resp = self.client.post(
            '/api/stats/upload',
            data={},
            content_type='multipart/form-data'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_stats_photo_upload_invalid_extension(self):
        """POST /api/stats/upload with unsupported file extension returns 400."""
        data = {
            'file': (io.BytesIO(b'not an image'), 'document.pdf')
        }
        resp = self.client.post(
            '/api/stats/upload',
            data=data,
            content_type='multipart/form-data'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('Invalid file type', data['error'])

    def test_stats_photo_get_when_cached(self):
        """GET /api/stats/image returns cached PNG if present."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGB', (20, 20), color='cyan')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        png_bytes = buf.getvalue()
        self.cached_file.write_bytes(png_bytes)

        resp = self.client.get('/api/stats/image')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'image/png')
        self.assertEqual(resp.data, png_bytes)

    def test_stats_photo_get_when_not_cached(self):
        """GET /api/stats/image returns 404 when no image is cached."""
        if self.cached_file.exists():
            self.cached_file.unlink()

        resp = self.client.get('/api/stats/image')
        self.assertEqual(resp.status_code, 404)

    def test_stats_photo_reset_post(self):
        """POST /api/stats/image/reset removes cached image."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cached_file.write_bytes(b'fake png data')
        self.assertTrue(self.cached_file.exists())

        resp = self.client.post('/api/stats/image/reset')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {'status': 'cleared'})
        self.assertFalse(self.cached_file.exists())

    def test_stats_photo_reset_delete(self):
        """DELETE /api/stats/image removes cached image."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cached_file.write_bytes(b'fake png data')
        self.assertTrue(self.cached_file.exists())

        resp = self.client.delete('/api/stats/image')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {'status': 'cleared'})
        self.assertFalse(self.cached_file.exists())


if __name__ == '__main__':
    unittest.main()
