"""Unit tests for profile_sync and gps_simplification database persistence."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.config import Config
from kinetiqo.profile_sync import sync_gps_simplification_from_env
from kinetiqo.web.app import app


class TestGpsSimplificationProfileSync(unittest.TestCase):
    """Test sync_gps_simplification_from_env precedence & DB sync rules."""

    def test_env_var_provided_updates_different_db(self):
        """If env var is set and differs from DB, env var overrides and updates DB on startup."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'weight': 65.0,
            'gps_simplification': 2,
            'refresh_token': 'token123',
        }
        config = Config()
        config.is_gps_simplification_env_set = True
        config.gps_simplification = 6

        sync_gps_simplification_from_env(config, mock_repo)

        mock_repo.upsert_profile.assert_called_once()
        _, kwargs = mock_repo.upsert_profile.call_args
        self.assertEqual(kwargs.get('gps_simplification'), 6)
        self.assertEqual(config.gps_simplification, 6)

    def test_env_var_not_provided_preserves_db_value(self):
        """If env var is NOT set, the stored DB value is preserved."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'weight': 65.0,
            'gps_simplification': 5,
            'refresh_token': 'token123',
        }
        config = Config()
        config.is_gps_simplification_env_set = False
        config.gps_simplification = 0  # default

        sync_gps_simplification_from_env(config, mock_repo)

        # Should NOT update DB since DB already has a value
        mock_repo.upsert_profile.assert_not_called()
        self.assertEqual(config.gps_simplification, 5)

    def test_env_var_not_provided_db_unset_defaults_to_zero(self):
        """If env var is NOT set and DB has no value yet, initializes DB with 0."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'weight': 65.0,
            'gps_simplification': None,
            'refresh_token': 'token123',
        }
        config = Config()
        config.is_gps_simplification_env_set = False
        config.gps_simplification = 0

        sync_gps_simplification_from_env(config, mock_repo)

        mock_repo.upsert_profile.assert_called_once()
        _, kwargs = mock_repo.upsert_profile.call_args
        self.assertEqual(kwargs.get('gps_simplification'), 0)
        self.assertEqual(config.gps_simplification, 0)


class TestGpsSimplificationWebAPI(unittest.TestCase):
    """Test PUT /api/profile updating gps_simplification."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        self._csrf_enabled = app.config.get('WTF_CSRF_ENABLED', True)
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def tearDown(self):
        app.config['WTF_CSRF_ENABLED'] = self._csrf_enabled

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.create_repository')
    def test_update_profile_gps_simplification_valid(self, mock_create_repo, mock_get_user):
        """Valid gps_simplification (0-10) is saved to DB and returned in response."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'John',
            'last_name': 'Doe',
            'weight': 70.0,
            'ftp': 250,
            'gps_simplification': 0,
        }
        mock_create_repo.return_value = mock_repo

        resp = self.client.put('/api/profile', json={'gps_simplification': 4})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('gps_simplification'), 4)
        mock_repo.upsert_profile.assert_called_once()

    @patch('flask_login.utils._get_user')
    @patch('kinetiqo.web.app.create_repository')
    def test_update_profile_gps_simplification_invalid(self, mock_create_repo, mock_get_user):
        """Out-of-range or invalid gps_simplification returns HTTP 422."""
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_get_user.return_value = mock_user

        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'John',
            'last_name': 'Doe',
            'weight': 70.0,
        }
        mock_create_repo.return_value = mock_repo

        resp = self.client.put('/api/profile', json={'gps_simplification': 15})
        self.assertEqual(resp.status_code, 422)
        data = resp.get_json()
        self.assertIn('error', data)


from kinetiqo.profile_sync import (
    sync_gps_simplification_from_env,
    sync_update_strava_from_env,
    sync_athlete_weight_from_env,
)


class TestUnifiedProfileSync(unittest.TestCase):
    """Test unified env var vs DB persistence logic across all settings."""

    @patch.dict(os.environ, {"UPDATE_STRAVA_CYCLING_OUTDOOR": "New Template"}, clear=True)
    def test_update_strava_env_var_updates_different_db(self):
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'weight': 65.0,
            'update_strava_cycling_outdoor': 'Old Template',
        }
        config = Config()
        sync_update_strava_from_env(config, mock_repo)

        mock_repo.upsert_profile.assert_called_once()
        _, kwargs = mock_repo.upsert_profile.call_args
        self.assertEqual(kwargs.get('update_strava_cycling_outdoor'), 'New Template')

    @patch.dict(os.environ, {}, clear=True)
    def test_update_strava_env_not_set_preserves_db(self):
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'weight': 65.0,
            'update_strava_cycling_outdoor': 'DB Stored Template',
        }
        config = Config()
        sync_update_strava_from_env(config, mock_repo)

        mock_repo.upsert_profile.assert_not_called()
        self.assertEqual(config.update_strava_cycling_outdoor, 'DB Stored Template')

    @patch.dict(os.environ, {"ATHLETE_WEIGHT": "72.5"}, clear=True)
    def test_athlete_weight_env_set_updates_different_db(self):
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'weight': 65.0,
        }
        config = Config()
        sync_athlete_weight_from_env(config, mock_repo)

        mock_repo.upsert_profile.assert_called_once()
        args, _ = mock_repo.upsert_profile.call_args
        self.assertEqual(args[3], 72.5)  # weight argument
        self.assertEqual(config.athlete_weight, 72.5)


    @patch.dict(os.environ, {"UPDATE_STRAVA_CYCLING_OUTDOOR": "Same Template"}, clear=True)
    def test_update_strava_env_same_as_db_does_not_update_db(self):
        """If env var is set but matches DB, upsert_profile is NOT called."""
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {
            'athlete_id': 123,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'weight': 65.0,
            'update_strava_cycling_outdoor': 'Same Template',
        }
        config = Config()
        sync_update_strava_from_env(config, mock_repo)

        mock_repo.upsert_profile.assert_not_called()
        self.assertEqual(config.update_strava_cycling_outdoor, 'Same Template')

    @patch('kinetiqo.profile_sync.sync_update_strava_from_env')
    @patch('kinetiqo.profile_sync.sync_gps_simplification_from_env')
    @patch('kinetiqo.profile_sync.sync_athlete_weight_from_env')
    def test_sync_all_profile_env_vars_delegates(self, mock_weight, mock_gps, mock_strava):
        """sync_all_profile_env_vars delegates to all three individual sync helpers."""
        from kinetiqo.profile_sync import sync_all_profile_env_vars
        config = Config()
        mock_repo = MagicMock()

        sync_all_profile_env_vars(config, mock_repo)

        mock_strava.assert_called_once_with(config, mock_repo)
        mock_gps.assert_called_once_with(config, mock_repo)
        mock_weight.assert_called_once_with(config, mock_repo)

    @patch('kinetiqo.strava.StravaClient')
    def test_seed_profile_from_strava_preserves_newly_synced_env_vars(self, mock_strava_cls):
        """seed_profile_from_strava re-fetches DB state so newly synced env vars are preserved."""
        from kinetiqo.profile_sync import seed_profile_from_strava

        mock_strava_inst = MagicMock()
        mock_strava_inst.get_athlete.return_value = {
            'id': 123,
            'firstname': 'Jaroslav',
            'lastname': 'Lhotak',
            'weight': 81.2,
        }
        mock_strava_cls.return_value = mock_strava_inst

        mock_repo = MagicMock()
        # Initial call before Strava fetch returns old state, second call returns updated DB state
        mock_repo.get_profile.side_effect = [
            {'athlete_id': 123, 'first_name': 'Old', 'last_name': 'Name', 'weight': 80.0, 'gps_simplification': 0, 'update_strava_cycling_outdoor': 'Old'},
            {'athlete_id': 123, 'first_name': 'Old', 'last_name': 'Name', 'weight': 80.0, 'gps_simplification': 4, 'update_strava_cycling_outdoor': 'New Env Template'},
        ]

        config = Config()
        config.strava_refresh_token = 'token'

        seeded = seed_profile_from_strava(config, mock_repo)
        self.assertIsNotNone(seeded)

        mock_repo.upsert_profile.assert_called_once()
        _, kwargs = mock_repo.upsert_profile.call_args
        self.assertEqual(kwargs.get('gps_simplification'), 4)
        self.assertEqual(kwargs.get('update_strava_cycling_outdoor'), 'New Env Template')


if __name__ == '__main__':
    unittest.main()


