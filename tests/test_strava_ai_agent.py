"""Mocked unit tests for the Kinetiqo Agent ({{ai-agent}} Strava description integration).

Tests all layers:
1. Special token & template validation for {{ai-agent}}
2. DescriptionContext caching, generation, and fallback behavior
3. Telemetry prompt generation and Agent runner
4. ChatService.generate_single_turn across primary and fallback models
5. DatabaseRepository AI response methods and profile agent_prompt
6. Web API endpoints (/api/activities/purge-ai, /api/profile agent_prompt, /api/activities)
7. Sync single-line logging with AI status suffix
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from kinetiqo.chat.agent_runner import build_activity_telemetry_prompt, run_agent_prompt
from kinetiqo.chat.errors import ChatConfigurationError
from kinetiqo.chat.models import StreamEvent
from kinetiqo.chat.service import ChatService
from kinetiqo.config import Config, UPDATE_STRAVA_PREFIX
from kinetiqo.strava_description import (
    SPECIAL_TOKENS,
    DescriptionContext,
    validate_template,
)
from kinetiqo.web.app import app, mark_startup_sync_done


class TestTemplateValidationAndSpecialTokens(unittest.TestCase):
    """Unit tests for template validation and SPECIAL_TOKENS with {{ai-agent}}."""

    def test_special_tokens_contains_ai_agent(self):
        self.assertIn("ai-agent", SPECIAL_TOKENS)

    def test_validate_template_with_ai_agent_valid(self):
        valid, err = validate_template("Great workout!\n{{ai-agent}}\n{{current-year}}")
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_validate_template_with_unclosed_brace(self):
        valid, err = validate_template("Great workout {{ai-agent")
        self.assertFalse(valid)
        self.assertIsNotNone(err)
        self.assertIn("Mismatched braces", err)

    def test_validate_template_with_invalid_token(self):
        valid, err = validate_template("Great workout {{unknown-placeholder}}")
        self.assertFalse(valid)
        self.assertIsNotNone(err)
        self.assertIn("unknown-placeholder", err)


class TestDescriptionContextAIAgent(unittest.TestCase):
    """Unit tests for DescriptionContext caching and AI handler integration."""

    def setUp(self):
        self.config = MagicMock(spec=Config)
        self.config.update_strava_placement = "end"
        self.repo = MagicMock()
        self.repo.get_goals.return_value = []
        self.repo.get_profile.return_value = {"athlete_id": 1, "agent_prompt": "Analyze workout"}

    def test_cached_ai_response_used_without_calling_handler(self):
        """When activity has existing cached ai_responses, use it directly without calling AI handler."""
        mock_handler = MagicMock()
        ctx = DescriptionContext(config=self.config, repo=self.repo, ai_handler=mock_handler)

        activity = {
            "id": 12345,
            "start_date": "2026-06-10T10:00:00Z",
            "sport_type": "Ride",
            "ai_responses": {"ai-agent": "Cached AI summary from database."},
        }

        template = "Workout info: {{ai-agent}}"
        rendered = ctx.render_for_activity(template, activity["start_date"], "", activity=activity)

        mock_handler.assert_not_called()
        self.assertIn("Cached AI summary from database.", rendered)
        self.assertEqual(ctx.last_ai_status, "cached")

    def test_cached_ai_response_json_string_supported(self):
        """When activity.ai_responses is a serialized JSON string, parse and use it."""
        mock_handler = MagicMock()
        ctx = DescriptionContext(config=self.config, repo=self.repo, ai_handler=mock_handler)

        activity = {
            "id": 12345,
            "start_date": "2026-06-10T10:00:00Z",
            "sport_type": "Ride",
            "ai_responses": json.dumps({"ai-agent": "Parsed string summary."}),
        }

        template = "Summary: {{ai-agent}}"
        rendered = ctx.render_for_activity(template, activity["start_date"], "", activity=activity)

        mock_handler.assert_not_called()
        self.assertIn("Parsed string summary.", rendered)
        self.assertEqual(ctx.last_ai_status, "cached")

    def test_uncached_ai_response_calls_handler_and_persists_to_db(self):
        """When activity has no cached AI response, invoke ai_handler and save to repository."""
        mock_handler = MagicMock(return_value=("Strong sustained tempo effort on climbs.", "generated"))
        ctx = DescriptionContext(config=self.config, repo=self.repo, ai_handler=mock_handler)

        activity = {
            "id": 12345,
            "start_date": "2026-06-10T10:00:00Z",
            "sport_type": "Ride",
            "ai_responses": None,
        }

        template = "AI Feedback: {{ai-agent}}"
        rendered = ctx.render_for_activity(template, activity["start_date"], "", activity=activity)

        mock_handler.assert_called_once_with(activity)
        self.repo.update_activity_ai_responses.assert_called_once_with(
            12345, {"ai-agent": "Strong sustained tempo effort on climbs."}
        )
        self.assertIn("Strong sustained tempo effort on climbs.", rendered)
        self.assertEqual(ctx.last_ai_status, "generated")

    def test_uncached_ai_response_fallback_model_tracked(self):
        """When ai_handler uses a fallback model, track the fallback status."""
        mock_handler = MagicMock(return_value=("Fallback summary.", "fallback gemini-2.5-flash"))
        ctx = DescriptionContext(config=self.config, repo=self.repo, ai_handler=mock_handler)

        activity = {
            "id": 12345,
            "start_date": "2026-06-10T10:00:00Z",
            "sport_type": "Ride",
            "ai_responses": {},
        }

        template = "{{ai-agent}}"
        rendered = ctx.render_for_activity(template, activity["start_date"], "", activity=activity)

        mock_handler.assert_called_once_with(activity)
        self.assertIn("Fallback summary.", rendered)
        self.assertEqual(ctx.last_ai_status, "fallback gemini-2.5-flash")

    def test_ai_handler_failure_leaves_placeholder_empty_and_does_not_crash(self):
        """When ai_handler returns failure or raises, {{ai-agent}} is empty and last_ai_status is failed."""
        mock_handler = MagicMock(side_effect=RuntimeError("AI API quota exhausted"))
        ctx = DescriptionContext(config=self.config, repo=self.repo, ai_handler=mock_handler)

        activity = {
            "id": 12345,
            "start_date": "2026-06-10T10:00:00Z",
            "sport_type": "Ride",
            "ai_responses": None,
        }

        template = "Analysis: [{{ai-agent}}]"
        rendered = ctx.render_for_activity(template, activity["start_date"], "", activity=activity)

        self.assertIn("Analysis: []", rendered)
        self.assertEqual(ctx.last_ai_status, "failed")
        self.repo.update_activity_ai_responses.assert_not_called()

    def test_agent_ai_alias_works_identically(self):
        """{{agent-ai}} alias resolves and outputs with ✨ Kinetiqo AI: prefix."""
        from kinetiqo.config import UPDATE_STRAVA_AI_PREFIX
        mock_handler = MagicMock(return_value=("Great alias run.", "generated"))
        ctx = DescriptionContext(config=self.config, repo=self.repo, ai_handler=mock_handler)
        activity = {"id": 999, "start_date": "2026-06-10T10:00:00Z", "sport_type": "Run"}
        template = "Note: {{agent-ai}}"
        rendered = ctx.render_for_activity(template, activity["start_date"], "", activity=activity)
        self.assertTrue(rendered.startswith(f"{UPDATE_STRAVA_AI_PREFIX} Note: Great alias run."))
        self.assertEqual(ctx.last_ai_status, "generated")


class TestAgentRunnerAndTelemetryPrompt(unittest.TestCase):
    """Unit tests for building telemetry prompt and executing agent runner."""

    def test_build_activity_telemetry_prompt_formats_fields_correctly(self):
        activity = {
            "name": "Morning Alpine Climb",
            "sport_type": "Ride",
            "start_date": "2026-07-15T08:30:00Z",
            "distance": 45200.0,
            "moving_time": 5400,
            "elapsed_time": 6000,
            "total_elevation_gain": 1250.0,
            "elev_high": 1820.0,
            "elev_low": 570.0,
            "average_speed": 8.37,
            "max_speed": 18.2,
            "average_watts": 235.0,
            "max_watts": 780.0,
            "weighted_average_watts": 255.0,
            "average_heartrate": 158.0,
            "max_heartrate": 182.0,
            "calories": 1420.0,
            "kilojoules": 1269.0,
            "suffer_score": 115,
            "average_temp": 19.5,
        }

        prompt, sys_inst = build_activity_telemetry_prompt(activity, athlete_prompt="Summarize my ride")

        self.assertIn("Morning Alpine Climb", prompt)
        self.assertIn("Ride", prompt)
        self.assertIn("45.2 km", prompt)
        self.assertIn("1h 30m 00s", prompt)
        self.assertIn("1250.0 m", prompt)
        self.assertIn("30.1 km/h", prompt)
        self.assertIn("235 W", prompt)
        self.assertIn("780 W", prompt)
        self.assertIn("158 bpm", prompt)
        self.assertIn("1420 kcal", prompt)
        self.assertIn("Summarize my ride", prompt)
        self.assertIn("Kinetiqo Agent", sys_inst)

    def test_run_agent_prompt_success(self):
        mock_chat_service = MagicMock(spec=ChatService)
        mock_chat_service.generate_single_turn.return_value = ("Great pacing throughout the ride!", "generated")

        activity = {"id": 100, "name": "Morning Ride", "sport_type": "Ride"}
        text, status = run_agent_prompt(mock_chat_service, "1", activity, "Summarize ride")

        self.assertEqual(text, "Great pacing throughout the ride!")
        self.assertEqual(status, "generated")
        mock_chat_service.generate_single_turn.assert_called_once()

    def test_run_agent_prompt_exception_handled_gracefully(self):
        mock_chat_service = MagicMock(spec=ChatService)
        mock_chat_service.generate_single_turn.side_effect = RuntimeError("Connection timeout")

        activity = {"id": 100, "name": "Morning Ride", "sport_type": "Ride"}
        text, status = run_agent_prompt(mock_chat_service, "1", activity, "Summarize ride")

        self.assertEqual(text, "")
        self.assertEqual(status, "failed")


class TestChatServiceGenerateSingleTurn(unittest.TestCase):
    """Unit tests for ChatService.generate_single_turn() with primary and fallback cascade."""

    def test_generate_single_turn_primary_success(self):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = {
            "provider": "openrouter",
            "model_id": "anthropic/claude-3.5-sonnet",
        }
        mock_repo.get_fallback_models.return_value = []

        service = ChatService(mock_repo, "x" * 32)

        mock_adapter = MagicMock()
        mock_adapter.stream.return_value = [
            StreamEvent(type="text_delta", text="Awesome "),
            StreamEvent(type="text_delta", text="workout!"),
        ]

        with patch.object(service, "_provider", return_value=mock_adapter):
            text, status = service.generate_single_turn("1", "Give me 2 sentences", "Context")
            self.assertEqual(text, "Awesome workout!")
            self.assertEqual(status, "generated")

    def test_generate_single_turn_cascades_to_fallback(self):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = {
            "provider": "gemini",
            "model_id": "primary-model",
        }
        mock_repo.get_fallback_models.return_value = [
            {"provider": "openrouter", "model_id": "fallback-model-1"}
        ]
        service = ChatService(mock_repo, "x" * 32)

        mock_primary_adapter = MagicMock()
        mock_primary_adapter.stream.side_effect = RuntimeError("Primary 503 Service Unavailable")

        mock_fallback_adapter = MagicMock()
        mock_fallback_adapter.stream.return_value = [
            StreamEvent(type="text_delta", text="Fallback response.")
        ]

        def get_provider(athlete_id, provider):
            if provider == "gemini":
                return mock_primary_adapter
            return mock_fallback_adapter

        with patch.object(service, "_provider", side_effect=get_provider):
            text, status = service.generate_single_turn("1", "Prompt", "Context")
            self.assertEqual(text, "Fallback response.")
            self.assertEqual(status, "fallback fallback-model-1")

    def test_generate_single_turn_no_models_configured(self):
        mock_repo = MagicMock()
        mock_repo.get_default_model.return_value = None
        service = ChatService(mock_repo, "x" * 32)

        with patch.object(service, "configured_providers", return_value=[]):
            with self.assertRaises(ChatConfigurationError):
                service.generate_single_turn("1", "Prompt")

    def test_generate_single_turn_resolves_numeric_strava_id_to_admin(self):
        """When called with numeric Strava athlete ID, resolve_athlete_id bridges to 'admin'."""
        mock_repo = MagicMock()
        mock_repo.resolve_athlete_id.return_value = "admin"
        mock_repo.get_default_model.side_effect = lambda athlete_id: (
            {"provider": "gemini", "model_id": "gemini-2.5-flash"} if athlete_id == "admin" else None
        )
        mock_repo.get_fallback_models.return_value = []

        service = ChatService(mock_repo, "x" * 32)
        mock_adapter = MagicMock()
        mock_adapter.stream.return_value = [
            StreamEvent(type="text_delta", text="Great hike pacing!"),
        ]

        with patch.object(service, "_provider", return_value=mock_adapter):
            text, status = service.generate_single_turn("20729217464", "Summarize hike", "Context")
            self.assertEqual(text, "Great hike pacing!")
            self.assertEqual(status, "generated")
            mock_repo.resolve_athlete_id.assert_called_with("20729217464")


class TestChatRepositoryAthleteResolution(unittest.TestCase):
    """Unit tests for ChatRepository.resolve_athlete_id bridging."""

    def test_resolve_athlete_id_matches_candidate(self):
        from kinetiqo.chat.repository import ChatRepository
        mock_db = MagicMock()
        repo = ChatRepository(mock_db, "postgresql")
        repo._one = MagicMock(return_value=(1,))

        resolved = repo.resolve_athlete_id("admin")
        self.assertEqual(resolved, "admin")

    def test_resolve_athlete_id_bridges_strava_id_to_admin(self):
        from kinetiqo.chat.repository import ChatRepository
        mock_db = MagicMock()
        repo = ChatRepository(mock_db, "postgresql")

        # First call (for candidate 20729217464) returns None; second call (for admin) returns (1,)
        repo._one = MagicMock(side_effect=[None, (1,)])

        resolved = repo.resolve_athlete_id("20729217464")
        self.assertEqual(resolved, "admin")


class TestWebAPIPurgeAndAgentPrompt(unittest.TestCase):
    """Test suite for /api/activities/purge-ai and /api/profile agent_prompt."""

    def setUp(self):
        mark_startup_sync_done()
        self._orig_testing = app.config.get('TESTING')
        self._orig_login_disabled = app.config.get('LOGIN_DISABLED')
        self._orig_csrf = app.config.get('WTF_CSRF_ENABLED')
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def tearDown(self):
        app.config['TESTING'] = self._orig_testing
        app.config['LOGIN_DISABLED'] = self._orig_login_disabled
        app.config['WTF_CSRF_ENABLED'] = self._orig_csrf

    @patch('kinetiqo.web.app.get_db')
    def test_purge_ai_api_empty_list_returns_400(self, mock_get_db):
        resp = self.client.post('/api/activities/purge-ai', json={'activity_ids': []})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    @patch('kinetiqo.web.app.get_db')
    def test_purge_ai_api_success(self, mock_get_db):
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.purge_activities_ai_responses.return_value = 2

        resp = self.client.post('/api/activities/purge-ai', json={'activity_ids': ['1001', '1002']})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['purged_count'], 2)
        mock_repo.purge_activities_ai_responses.assert_called_once_with(['1001', '1002'])

    @patch('kinetiqo.web.app.get_db')
    def test_update_profile_saves_agent_prompt(self, mock_get_db):
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_profile.return_value = {
            "athlete_id": 1,
            "first_name": "Jaroslav",
            "last_name": "Lhotak",
            "ftp": 250,
            "weight": 70.0,
            "agent_prompt": "",
        }

        resp = self.client.post('/api/profile', json={'agent_prompt': 'Short 1-sentence recap'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['agent_prompt'], 'Short 1-sentence recap')
        mock_repo.upsert_profile.assert_called_once()
        _, kwargs = mock_repo.upsert_profile.call_args
        self.assertEqual(kwargs['agent_prompt'], 'Short 1-sentence recap')

    @patch('kinetiqo.web.app.get_db')
    def test_get_activities_api_returns_ai_responses_field(self, mock_get_db):
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_activities_web.return_value = [
            {
                'id': 5001,
                'name': 'Gravel Ride',
                'type': 'Ride',
                'start_date': '2026-06-10T14:30:00Z',
                'distance': 25000.0,
                'total_elevation_gain': 300.0,
                'moving_time': 3600,
                'average_speed': 6.94,
                'average_heartrate': 140,
                'average_watts': 180.0,
                'max_watts': 450.0,
                'weighted_average_watts': 190.0,
                'device_watts': 1,
                'calories': 600.0,
                'kilojoules': 650.0,
                'achievement_count': 1,
                'pr_count': 0,
                'suffer_score': 45,
                'average_temp': 20.0,
                'elev_high': 300.0,
                'elev_low': 100.0,
                'gear_id': 'g1',
                'has_heartrate': 1,
                'workout_type': 0,
                'ai_responses': {'ai-agent': 'Nice tempo effort'},
            }
        ]
        mock_repo.get_activities_totals.return_value = {
            'total_distance': 25000.0,
            'total_elevation': 300.0,
            'total_moving_time': 3600,
        }

        resp = self.client.get('/api/activities')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('data', data)
        self.assertEqual(len(data['data']), 1)
        row = data['data'][0]
        self.assertIn('ai_responses', row)
        self.assertEqual(row['ai_responses'], {'ai-agent': 'Nice tempo effort'})

    @patch('kinetiqo.web.app._chat_user_id', return_value='12345')
    @patch('kinetiqo.web.app._chat_service')
    @patch('kinetiqo.web.app.get_db')
    def test_activities_page_hides_purge_ai_btn_when_ai_not_configured(self, mock_get_db, mock_chat_service, _mock_user):
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_activities.return_value = []
        mock_repo.get_distinct_activity_types.return_value = ['Ride']

        mock_svc = MagicMock()
        mock_svc.configured_providers.return_value = []
        mock_svc.repository.get_default_model.return_value = None
        mock_chat_service.return_value = mock_svc

        resp = self.client.get('/activities')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn('id="purgeAiBtn"', html)

    @patch('kinetiqo.web.app._chat_user_id', return_value='12345')
    @patch('kinetiqo.web.app._chat_service')
    @patch('kinetiqo.web.app.get_db')
    def test_activities_page_shows_purge_ai_btn_when_ai_configured(self, mock_get_db, mock_chat_service, _mock_user):
        mock_repo = MagicMock()
        mock_get_db.return_value = mock_repo
        mock_repo.get_activities.return_value = []
        mock_repo.get_distinct_activity_types.return_value = ['Ride']

        mock_svc = MagicMock()
        mock_svc.configured_providers.return_value = ['gemini']
        mock_svc.repository.get_default_model.return_value = {'provider': 'gemini', 'model_id': 'gemini-3.1-flash-lite'}
        mock_chat_service.return_value = mock_svc

        resp = self.client.get('/activities')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('id="purgeAiBtn"', html)
        self.assertIn('bg-teal-600 hover:bg-teal-700', html)


class TestCliSyncWithAiAgent(unittest.TestCase):
    """Test suite ensuring sync works as expected when triggered via CLI."""

    @patch("kinetiqo.sync.create_repository")
    @patch("kinetiqo.sync.StravaClient")
    @patch("kinetiqo.chat.agent_runner.run_agent_prompt")
    def test_cli_sync_executes_ai_agent_and_updates_description(self, mock_run_agent, mock_strava_cls, mock_create_repo):
        from kinetiqo.sync import SyncService
        from kinetiqo.config import Config, UPDATE_STRAVA_AI_PREFIX

        mock_repo = MagicMock()
        mock_create_repo.return_value = mock_repo
        mock_repo.get_profile.return_value = {
            "athlete_id": "12345",
            "first_name": "Test",
            "last_name": "User",
            "weight": 70.0,
            "agent_prompt": "Summarize run",
            "update_strava_cycling_outdoor": "{{ai-agent}}",
        }
        mock_repo.get_synced_activity_ids.return_value = set()
        mock_repo.get_synced_activity_ids_since.return_value = set()
        mock_repo.get_activities_totals.return_value = {"total_distance": 0, "total_elevation": 0, "total_moving_time": 0}
        mock_repo.get_activity_ai_responses.return_value = None

        mock_strava = MagicMock()
        mock_strava_cls.return_value = mock_strava
        activity = {
            "id": 88888,
            "name": "Morning Ride",
            "sport_type": "Ride",
            "start_date": "2026-10-25T08:00:00Z",
            "distance": 25000,
            "moving_time": 3600,
            "total_elevation_gain": 200,
        }
        mock_strava.get_activities.return_value = iter([[activity]])
        mock_strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}
        mock_strava.get_activity_detail.return_value = {"id": 88888, "description": "Existing strava text"}

        mock_run_agent.return_value = ("Crushed the morning ride!", "generated")

        config = Config()
        config.update_strava_cycling_outdoor = "{{ai-agent}}"
        config.database_type = "postgresql"

        service = SyncService(config)
        with patch.dict(os.environ, {"SECRET_KEY": "0123456789abcdef0123456789abcdef"}), \
             patch("kinetiqo.chat.repository.ChatRepository.resolve_athlete_id", return_value="12345"), \
             patch("kinetiqo.chat.repository.ChatRepository.get_provider_key", return_value="fake_key"), \
             patch("kinetiqo.chat.repository.ChatRepository.get_default_model", return_value={"provider": "gemini", "model_id": "gemini-3.1-flash-lite"}), \
             patch("kinetiqo.chat.repository.ChatRepository.list_configured_providers", return_value=["gemini"]):
            logs = list(service.sync(full_sync=False, trigger="cli", update_strava=True))

        mock_strava.update_activity_description.assert_called_once()
        call_args = mock_strava.update_activity_description.call_args[0]
        self.assertEqual(call_args[0], 88888)
        self.assertIn("Crushed the morning ride!", call_args[1])
        self.assertTrue(call_args[1].endswith(f"{UPDATE_STRAVA_AI_PREFIX} Crushed the morning ride!\n"))
        self.assertIn("Existing strava text", call_args[1])


if __name__ == '__main__':
    unittest.main()
