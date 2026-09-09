"""Unit tests for Config environment variable parsing, validation, and coercions."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.config import Config, DEFAULT_UPDATE_STRAVA_PLACEMENT


class TestConfigEnvironmentParsing(unittest.TestCase):
    """Comprehensive unit test suite for Config env var reading and coercions."""

    @patch.dict(os.environ, {
        "UPDATE_STRAVA_CYCLING_INDOOR": "{{indoor-template}}",
        "UPDATE_STRAVA_CYCLING_OUTDOOR": "{{outdoor-template}}",
        "UPDATE_STRAVA_RUNNING_INDOOR": "{{run-indoor}}",
        "UPDATE_STRAVA_RUNNING_OUTDOOR": "{{run-outdoor}}",
        "UPDATE_STRAVA_WALKING": "{{walk-template}}",
        "UPDATE_STRAVA_SWIMMING": "{{swim-template}}",
        "UPDATE_STRAVA_PLACEMENT": "begin",
    }, clear=True)
    def test_update_strava_env_vars_parsed(self):
        """All 6 UPDATE_STRAVA_* environment variables and placement are parsed correctly."""
        config = Config()
        self.assertEqual(config.update_strava_cycling_indoor, "{{indoor-template}}")
        self.assertEqual(config.update_strava_cycling_outdoor, "{{outdoor-template}}")
        self.assertEqual(config.update_strava_running_indoor, "{{run-indoor}}")
        self.assertEqual(config.update_strava_running_outdoor, "{{run-outdoor}}")
        self.assertEqual(config.update_strava_walking, "{{walk-template}}")
        self.assertEqual(config.update_strava_swimming, "{{swim-template}}")
        self.assertEqual(config.update_strava_placement, "begin")

    @patch.dict(os.environ, {"UPDATE_STRAVA_PLACEMENT": "INVALID_PLACEMENT"}, clear=True)
    def test_update_strava_placement_invalid_fallback(self):
        """Invalid UPDATE_STRAVA_PLACEMENT falls back to default ('end')."""
        config = Config()
        self.assertEqual(config.update_strava_placement, DEFAULT_UPDATE_STRAVA_PLACEMENT)

    @patch.dict(os.environ, {"GPS_SIMPLIFICATION": "4"}, clear=True)
    def test_gps_simplification_valid_level(self):
        """GPS_SIMPLIFICATION env var level 0-10 is coerced to integer and marks env set."""
        config = Config()
        self.assertTrue(config.is_gps_simplification_env_set)
        self.assertEqual(config.gps_simplification, 4)

    @patch.dict(os.environ, {"GPS_SIMPLIFICATION_LEVEL": "7"}, clear=True)
    def test_gps_simplification_level_alias(self):
        """GPS_SIMPLIFICATION_LEVEL environment alias is recognized."""
        config = Config()
        self.assertTrue(config.is_gps_simplification_env_set)
        self.assertEqual(config.gps_simplification, 7)

    @patch.dict(os.environ, {"GPS_SIMPLIFICATION": "15"}, clear=True)
    def test_gps_simplification_out_of_bounds_fallback(self):
        """Out of bounds GPS_SIMPLIFICATION level (>10) defaults to 0."""
        config = Config()
        self.assertTrue(config.is_gps_simplification_env_set)
        self.assertEqual(config.gps_simplification, 0)

    @patch.dict(os.environ, {"ATHLETE_WEIGHT": "81.5"}, clear=True)
    def test_athlete_weight_parsed(self):
        """ATHLETE_WEIGHT env var is coerced to float."""
        config = Config()
        self.assertEqual(config.athlete_weight, 81.5)

    @patch.dict(os.environ, {
        "POSTGRESQL_HOST": "pg.local",
        "POSTGRESQL_PORT": "5433",
        "POSTGRESQL_USER": "pg_user",
        "POSTGRESQL_PASSWORD": "pg_pass",
        "POSTGRESQL_DATABASE": "pg_db",
    }, clear=True)
    def test_postgresql_env_vars_parsed(self):
        """PostgreSQL environment variables are parsed correctly."""
        config = Config()
        self.assertEqual(config.postgresql_host, "pg.local")
        self.assertEqual(config.postgresql_port, 5433)
        self.assertEqual(config.postgresql_user, "pg_user")
        self.assertEqual(config.postgresql_password, "pg_pass")
        self.assertEqual(config.postgresql_database, "pg_db")

    @patch.dict(os.environ, {
        "MYSQL_HOST": "mysql.local",
        "MYSQL_PORT": "3307",
        "MYSQL_USER": "my_user",
        "MYSQL_PASSWORD": "my_pass",
        "MYSQL_DATABASE": "my_db",
        "MYSQL_SSL_MODE": "DISABLED",
    }, clear=True)
    def test_mysql_env_vars_parsed(self):
        """MySQL environment variables are parsed correctly."""
        config = Config()
        self.assertEqual(config.mysql_host, "mysql.local")
        self.assertEqual(config.mysql_port, 3307)
        self.assertEqual(config.mysql_user, "my_user")
        self.assertEqual(config.mysql_password, "my_pass")
        self.assertEqual(config.mysql_database, "my_db")
        self.assertEqual(config.mysql_ssl_mode, "DISABLED")

    @patch.dict(os.environ, {
        "FIREBIRD_HOST": "firebird.local",
        "FIREBIRD_PORT": "3051",
        "FIREBIRD_USER": "fb_user",
        "FIREBIRD_PASSWORD": "fb_pass",
        "FIREBIRD_DATABASE": "fb_db",
    }, clear=True)
    def test_firebird_env_vars_parsed(self):
        """Firebird environment variables are parsed correctly."""
        config = Config()
        self.assertEqual(config.firebird_host, "firebird.local")
        self.assertEqual(config.firebird_port, 3051)
        self.assertEqual(config.firebird_user, "fb_user")
        self.assertEqual(config.firebird_password, "fb_pass")
        self.assertEqual(config.firebird_database, "fb_db")

    @patch.dict(os.environ, {
        "MAPY_API_KEY": "mapy_key",
        "THUNDERFOREST_API_KEY": "tf_key",
        "MAPTILER_API_KEY": "mt_key",
        "GEOAPIFY_API_KEY": "geo_key",
        "DATE_FORMAT": "%d/%m/%Y",
    }, clear=True)
    def test_map_and_misc_env_vars_parsed(self):
        """Map API key and date format environment variables are parsed correctly."""
        config = Config()
        self.assertEqual(config.mapy_api_key, "mapy_key")
        self.assertEqual(config.thunderforest_api_key, "tf_key")
        self.assertEqual(config.maptiler_api_key, "mt_key")
        self.assertEqual(config.geoapify_api_key, "geo_key")
        self.assertEqual(config.date_format, "%d/%m/%Y")


if __name__ == '__main__':
    unittest.main()
