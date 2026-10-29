"""Mocked unit tests for settings helpers and endpoints."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from kinetiqo.web.app import app, describe_cron
from kinetiqo.web.auth import users


class TestDescribeCron(unittest.TestCase):
    """Unit tests for the settings page cron description helper."""

    def test_empty_schedule_is_not_scheduled(self):
        self.assertEqual(describe_cron(""), "Not scheduled")

    def test_interval_schedule(self):
        self.assertEqual(describe_cron("*/1 * * * *"), "Every 1 minute")
        self.assertEqual(describe_cron("*/15 * * * *"), "Every 15 minutes")

    def test_daily_schedule(self):
        self.assertEqual(describe_cron("0 12 * * *"), "Daily at noon")
        self.assertEqual(describe_cron("30 8 * * *"), "Daily at 08:30")

    def test_weekly_schedule(self):
        self.assertEqual(describe_cron("0 0 * * 0"), "Every Sunday at midnight")
        self.assertEqual(describe_cron("15 6 * * 1,3,5"), "Every Monday, Wednesday and Friday at 06:15")

    def test_monthly_and_yearly_schedules(self):
        self.assertEqual(describe_cron("0 3 1 * *"), "Monthly on the 1st at 03:00")
        self.assertEqual(describe_cron("0 3 31 12 *"), "Yearly on December 31st at 03:00")

    def test_unknown_or_invalid_schedule_is_returned_unchanged(self):
        self.assertEqual(describe_cron("0 0 * *"), "0 0 * *")
        self.assertEqual(describe_cron("0 24 * * *"), "0 24 * * *")
        self.assertEqual(describe_cron("0 0 1 * 0"), "0 0 1 * 0")


class TestSettingsApi(unittest.TestCase):
    """Unit tests for settings JSON exposed to the UI."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        username = next(iter(users))
        with self.client.session_transaction() as session:
            session["_user_id"] = username
            session["_fresh"] = True

    def test_settings_api_describes_weekly_full_sync(self):
        repo = MagicMock()
        repo.config = MagicMock()
        repo.config.mysql_host = "localhost"
        repo.config.mysql_port = "3306"
        repo.config.postgresql_host = "localhost"
        repo.config.postgresql_port = "5432"
        repo.config.firebird_host = "localhost"
        repo.config.firebird_port = "3050"
        repo.get_table_record_counts.return_value = {}

        with patch.dict(os.environ, {"FULL_SYNC": "0 0 * * 0", "FAST_SYNC": "*/15 * * * *"}), \
                patch("kinetiqo.web.app.get_db", return_value=repo):
            response = self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["full_sync"]["description"], "Every Sunday at midnight")
        self.assertEqual(data["fast_sync"]["description"], "Every 15 minutes")

    def test_settings_page_renders_template_variables_info_box(self):
        repo = MagicMock()
        repo.get_profile.return_value = None
        with patch("kinetiqo.web.app.get_db", return_value=repo):
            response = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        content = response.get_data(as_text=True)
        self.assertIn("Supported Template Variables", content)
        self.assertIn("strava-var-dropdown", content)
        self.assertIn("bg-orange-500 hover:bg-orange-600", content)
        self.assertIn("Add Agent", content)
        self.assertNotIn('"token": "{{agent-ai}}"', content)
        for heading in ("Model Name &amp; ID", "Context", "Capabilities", "Pricing &amp; Limits", "Default", "Actions"):
            self.assertEqual(content.count(f">{heading}</th>"), 5, heading)

    def test_settings_page_contains_section_anchors(self):
        repo = MagicMock()
        repo.get_profile.return_value = None
        with patch("kinetiqo.web.app.get_db", return_value=repo):
            response = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        content = response.get_data(as_text=True)
        for anchor_id in ('id="templates"', 'id="profile"', 'id="gps"', 'id="ai"', 'id="sync"'):
            self.assertIn(anchor_id, content)

    def test_chat_page_contains_ai_settings_link_and_suggestions(self):
        repo = MagicMock()
        repo.get_profile.return_value = None
        repo.list_recent_prompts.return_value = []
        with patch("kinetiqo.web.app.get_db", return_value=repo):
            response = self.client.get("/chat")

        self.assertEqual(response.status_code, 200)
        content = response.get_data(as_text=True)
        self.assertIn('/settings#ai', content)
        self.assertIn('AI Settings', content)
        self.assertIn('id="chat-suggestions-grid"', content)
        self.assertNotIn('chat-hero-icon', content)

    def test_chat_page_and_api_contains_disclaimer_modal(self):
        repo = MagicMock()
        repo.get_profile.return_value = None
        repo.list_recent_prompts.return_value = []
        with patch("kinetiqo.web.app.get_db", return_value=repo):
            response = self.client.get("/chat")

        self.assertEqual(response.status_code, 200)
        content = response.get_data(as_text=True)
        self.assertIn('id="open-disclaimer-btn"', content)
        self.assertIn('id="ai-disclaimer-modal"', content)
        self.assertIn('id="disclaimer-acknowledge-btn"', content)
        self.assertIn('I acknowledge', content)
        self.assertIn('background-color: rgba(0, 0, 0, 0.65);', content)
        self.assertIn('w-[80vw]', content)
        self.assertIn('h-[80vh]', content)
        self.assertIn('chat-disclaimer-modal-body', content)
        self.assertIn('Training advice is informational.', content)

        # Test GET /api/chat/disclaimer endpoint
        api_response = self.client.get("/api/chat/disclaimer")
        self.assertEqual(api_response.status_code, 200)
        api_data = api_response.get_json()
        self.assertIn('disclaimer', api_data)
        self.assertIn('Kinetiqo AI Disclaimer', api_data['disclaimer'])



class TestDatabaseEnvConfig(unittest.TestCase):
    """Unit tests for database environment variable fallback."""

    def test_default_database_type_is_postgresql(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            self.assertEqual(config.database_type, "postgresql")

    def test_database_type_fallback_to_database_env(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {"DATABASE": "firebird"}, clear=True):
            config = Config()
            self.assertEqual(config.database_type, "firebird")

    def test_database_type_env_takes_precedence(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {"DATABASE_TYPE": "mysql", "DATABASE": "firebird"}, clear=True):
            config = Config()
            self.assertEqual(config.database_type, "mysql")

    def test_invalid_database_type_falls_back_to_postgresql(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {"DATABASE_TYPE": "invalid_db"}, clear=True):
            config = Config()
            self.assertEqual(config.database_type, "postgresql")


class TestGpsSimplificationConfig(unittest.TestCase):
    """Unit tests for GPS_SIMPLIFICATION environment variable parsing."""

    def test_default_gps_simplification_is_zero(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            self.assertEqual(config.gps_simplification, 0)

    def test_valid_gps_simplification_level(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {"GPS_SIMPLIFICATION": "5"}, clear=True):
            config = Config()
            self.assertEqual(config.gps_simplification, 5)

    def test_invalid_gps_simplification_out_of_range(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {"GPS_SIMPLIFICATION": "15"}, clear=True):
            config = Config()
            self.assertEqual(config.gps_simplification, 0)

    def test_invalid_gps_simplification_non_numeric(self):
        from kinetiqo.config import Config
        with patch.dict(os.environ, {"GPS_SIMPLIFICATION": "invalid"}, clear=True):
            config = Config()
            self.assertEqual(config.gps_simplification, 0)


if __name__ == "__main__":
    unittest.main()
