import io
import os
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.web.app import app, mark_startup_sync_done


class TestPosterPhoto(unittest.TestCase):
    """Test suite for poster photo retrieval, reload, and custom upload."""

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
        self.test_activity_id = 'test_activity_99999'
        self.cached_file = self.cache_dir / f"{self.test_activity_id}.png"

    def tearDown(self):
        app.config['TESTING'] = self._orig_testing
        app.config['LOGIN_DISABLED'] = self._orig_login_disabled
        app.config['WTF_CSRF_ENABLED'] = self._orig_csrf
        if self.cached_file.exists():
            try:
                self.cached_file.unlink()
            except Exception:
                pass

    def test_poster_photo_get_cached(self):
        """GET /api/poster/photo/<activity_id> serves cached PNG directly."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Create a tiny 10x10 PNG
        img = Image.new('RGB', (10, 10), color='red')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        png_bytes = buf.getvalue()
        self.cached_file.write_bytes(png_bytes)

        resp = self.client.get(f'/api/poster/photo/{self.test_activity_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'image/png')
        self.assertEqual(resp.data, png_bytes)

    @patch('kinetiqo.web.app._fetch_strava_activity_photo')
    @patch('kinetiqo.web.app._download_and_convert_to_png')
    def test_poster_photo_get_from_strava(self, mock_download, mock_fetch):
        """GET /api/poster/photo/<activity_id> fetches from Strava when not cached."""
        mock_fetch.return_value = 'https://strava.com/photos/123.jpg'
        img = Image.new('RGB', (10, 10), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        png_bytes = buf.getvalue()
        mock_download.return_value = png_bytes

        resp = self.client.get(f'/api/poster/photo/{self.test_activity_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'image/png')
        self.assertEqual(resp.data, png_bytes)
        self.assertTrue(self.cached_file.exists())

    def test_poster_photo_upload_valid_image(self):
        """POST /api/poster/upload/<activity_id> uploads and converts image to cached PNG."""
        img = Image.new('RGB', (50, 50), color='green')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        jpeg_bytes = buf.getvalue()

        data = {
            'file': (io.BytesIO(jpeg_bytes), 'my_photo.jpg')
        }

        resp = self.client.post(
            f'/api/poster/upload/{self.test_activity_id}',
            data=data,
            content_type='multipart/form-data'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'image/png')
        self.assertTrue(self.cached_file.exists())

    def test_poster_photo_upload_no_file(self):
        """POST /api/poster/upload/<activity_id> with no file returns 400 error."""
        resp = self.client.post(
            f'/api/poster/upload/{self.test_activity_id}',
            data={},
            content_type='multipart/form-data'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_poster_photo_upload_invalid_extension(self):
        """POST /api/poster/upload/<activity_id> with unsupported file extension returns 400."""
        data = {
            'file': (io.BytesIO(b'not an image'), 'document.pdf')
        }
        resp = self.client.post(
            f'/api/poster/upload/{self.test_activity_id}',
            data=data,
            content_type='multipart/form-data'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('Invalid file type', data['error'])


if __name__ == '__main__':
    unittest.main()
