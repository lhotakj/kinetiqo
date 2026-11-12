"""Mocked tests for internal read-only chat data context and MCP tool execution."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.tools import (
    CHAT_TOOL_ALLOWLIST,
    MUTATING_TOOL_NAMES,
    _bound_tool_payload,
    build_training_context,
    execute_chat_tool,
    get_chat_tools,
    normalize_tool_call_arguments,
    to_gemini_schema,
    to_openai_schema,
)


class TestChatTools(unittest.TestCase):
    def test_allowlist_contains_only_read_tools(self):
        self.assertNotIn("kinetiqo_trigger_sync", CHAT_TOOL_ALLOWLIST)
        self.assertNotIn("kinetiqo_update_athlete_profile", CHAT_TOOL_ALLOWLIST)
        self.assertIn("kinetiqo_get_activity_totals", CHAT_TOOL_ALLOWLIST)
        self.assertIn("kinetiqo_get_fitness_and_freshness", CHAT_TOOL_ALLOWLIST)
        self.assertIn("kinetiqo_get_activity_weather", CHAT_TOOL_ALLOWLIST)

    @patch("kinetiqo.chat.tools.physiology.kinetiqo_get_fitness_and_freshness")
    @patch("kinetiqo.chat.tools.activities.kinetiqo_get_activity_totals")
    def test_summary_and_freshness_use_local_tool_functions(self, totals, freshness):
        totals.return_value = {"data": {"count": 4, "distance_km": 123.4}}
        freshness.return_value = {"data": {"current_status": {"form_tsb": 7.5}}}
        repo = MagicMock()
        context = build_training_context(repo, "Summarize my last four weeks of training and how fresh am I?")
        totals.assert_called_once()
        freshness.assert_called_once_with(repo=repo, period_days=90)
        self.assertIn("kinetiqo_get_activity_totals", context)
        self.assertIn("123.4", context)
        self.assertIn("form_tsb", context)

    @patch("kinetiqo.chat.tools.activities.kinetiqo_get_activity_totals")
    def test_general_prompt_does_not_query_local_data(self, totals):
        self.assertEqual(build_training_context(MagicMock(), "What is FTP?"), "")
        totals.assert_not_called()

    def test_activity_totals_correctly_maps_total_distance_from_repository(self):
        from kinetiqo.mcp.tools.activities import kinetiqo_get_activity_totals
        repo = MagicMock()
        repo.get_activities_totals.return_value = {
            "total_distance": 54200.0,
            "total_elevation": 650.0,
            "total_moving_time": 7200.0,
        }
        repo.count_activities.return_value = 3
        res = kinetiqo_get_activity_totals(repo, start_date="2024-05-01", end_date="2024-05-31")
        self.assertEqual(res["data"]["distance_km"], 54.2)
        self.assertEqual(res["data"]["elevation_m"], 650.0)
        self.assertEqual(res["data"]["moving_time_hours"], 2.0)
        self.assertEqual(res["data"]["count"], 3)

    def test_get_chat_tools_discovers_read_only_tools_and_excludes_mutating(self):
        tools = get_chat_tools(force_refresh=True)
        self.assertGreater(len(tools), 20)
        tool_names = {t["name"] for t in tools}
        self.assertIn("kinetiqo_search_activities", tool_names)
        self.assertIn("kinetiqo_get_activity_totals", tool_names)
        self.assertIn("kinetiqo_get_fitness_and_freshness", tool_names)
        self.assertIn("kinetiqo_get_activity_weather", tool_names)
        self.assertIn("kinetiqo_get_power_skills", tool_names)
        for mutating in MUTATING_TOOL_NAMES:
            self.assertNotIn(mutating, tool_names)
        for name in tool_names:
            self.assertFalse(name.startswith(("kinetiqo_update_", "kinetiqo_trigger_")))

    def test_to_gemini_schema_converts_pydantic_schema_cleanly(self):
        input_schema = {
            "type": "object",
            "title": "SearchArgs",
            "properties": {
                "query": {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Query", "default": None},
                "limit": {"type": "integer", "title": "Limit", "default": 20},
                "sport_types": {"anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}]},
            },
            "required": ["limit"],
        }
        gemini_schema = to_gemini_schema(input_schema)
        self.assertEqual(gemini_schema["type"], "OBJECT")
        self.assertNotIn("title", gemini_schema)
        self.assertEqual(gemini_schema["properties"]["query"]["type"], "STRING")
        self.assertEqual(gemini_schema["properties"]["limit"]["type"], "INTEGER")
        self.assertEqual(gemini_schema["properties"]["sport_types"]["type"], "ARRAY")
        self.assertEqual(gemini_schema["properties"]["sport_types"]["items"]["type"], "STRING")
        self.assertEqual(gemini_schema["required"], ["limit"])

    def test_get_chat_tools_supports_openai_and_mistral_schema_formatting(self):
        openai_tools = get_chat_tools(provider="openai", force_refresh=True)
        self.assertGreater(len(openai_tools), 20)
        first_tool = openai_tools[0]
        self.assertEqual(first_tool["type"], "function")
        self.assertIn("name", first_tool["function"])
        self.assertIn("description", first_tool["function"])
        self.assertEqual(first_tool["function"]["parameters"]["type"], "object")

        vercel_tools = get_chat_tools(provider="vercel", force_refresh=True)
        self.assertGreater(len(vercel_tools), 20)
        self.assertEqual(vercel_tools[0]["type"], "function")

        kilo_tools = get_chat_tools(provider="kilo", force_refresh=True)
        self.assertGreater(len(kilo_tools), 20)
        self.assertEqual(kilo_tools[0]["type"], "function")

        magnetapi_tools = get_chat_tools(provider="magnetapi", force_refresh=True)
        self.assertGreater(len(magnetapi_tools), 20)
        self.assertEqual(magnetapi_tools[0]["type"], "function")
        self.assertIn("name", magnetapi_tools[0]["function"])
        self.assertEqual(magnetapi_tools[0]["function"]["parameters"]["type"], "object")

        anthropic_tools = get_chat_tools(provider="anthropic", force_refresh=True)
        self.assertGreater(len(anthropic_tools), 20)
        first_ant = anthropic_tools[0]
        self.assertIn("name", first_ant)
        self.assertIn("description", first_ant)
        self.assertIn("input_schema", first_ant)
        self.assertEqual(first_ant["input_schema"]["type"], "object")

    def test_execute_chat_tool_blocks_mutating_tools(self):
        repo = MagicMock()
        payload, elapsed = execute_chat_tool(repo, "kinetiqo_trigger_sync", {"sync_type": "full"})
        self.assertEqual(payload.get("status"), "forbidden")
        self.assertIn("not permitted", payload.get("error", ""))

    def test_execute_chat_tool_runs_read_only_tool_in_process(self):
        repo = MagicMock()
        repo.get_training_goals.return_value = []
        payload, elapsed = execute_chat_tool(repo, "kinetiqo_get_training_goals", {})
        self.assertIsInstance(payload, dict)
        self.assertIn("data", payload)
        self.assertGreaterEqual(elapsed, 0)

    def test_execute_chat_tool_power_and_ftp_tools(self):
        repo = MagicMock()
        repo.get_profile.return_value = {"ftp": 275.0, "weight": 71.0}
        repo.get_activity_ids_by_types.return_value = [
            {"id": "501", "name": "Crit Race", "start_date": "2026-06-01T10:00:00Z"},
            {"id": "502", "name": "FTP Test", "start_date": "2026-06-05T10:00:00Z"},
        ]
        def mock_best_power(ids, duration):
            if duration == 1200:
                return {"501": 260.0, "502": 310.0}
            if duration == 5:
                return {"501": 950.0, "502": 600.0}
            return {}
        repo.get_best_power_per_activity.side_effect = mock_best_power

        # Test kinetiqo_get_personal_records
        res_pr, _ = execute_chat_tool(repo, "kinetiqo_get_personal_records", {"durations": [5, 1200]})
        self.assertNotIn("error", res_pr)
        self.assertIn("data", res_pr)
        self.assertEqual(res_pr["data"]["records"]["5"]["watts"], 950.0)

        # Test kinetiqo_get_power_skills
        res_ps, _ = execute_chat_tool(repo, "kinetiqo_get_power_skills", {})
        self.assertNotIn("error", res_ps)
        self.assertIn("data", res_ps)
        self.assertEqual(res_ps["data"]["benchmarks"]["1200"]["watts"], 310.0)

        # Test kinetiqo_get_ftp_history
        res_ftp, _ = execute_chat_tool(repo, "kinetiqo_get_ftp_history", {})
        self.assertNotIn("error", res_ftp)
        self.assertIn("data", res_ftp)
        self.assertEqual(res_ftp["data"]["configured_ftp_watts"], 275.0)
        self.assertEqual(res_ftp["data"]["historical_20m_breakthroughs"][0]["estimated_ftp_watts"], round(310.0 * 0.95, 1))

    def test_bound_tool_payload_truncates_large_lists(self):
        large_list = list(range(50))
        bounded = _bound_tool_payload({"items": large_list}, max_items=10)
        self.assertEqual(len(bounded["items"]), 11)  # 10 items + truncation notice
        self.assertEqual(bounded["items"][-1]["_truncated_count"], 40)

    def test_normalize_tool_call_arguments(self):
        # Integer activity_id coerced to string
        norm = normalize_tool_call_arguments({"activity_id": 20749829518, "other": 123})
        self.assertEqual(norm["activity_id"], "20749829518")
        self.assertEqual(norm["other"], 123)

        # List of integer activity_ids coerced to strings
        norm_list = normalize_tool_call_arguments({"activity_ids": [20713760854, 20749829518]})
        self.assertEqual(norm_list["activity_ids"], ["20713760854", "20749829518"])

        # Accidental single int for activity_ids wrapped in list of string
        norm_single = normalize_tool_call_arguments({"activity_ids": 20749829518})
        self.assertEqual(norm_single["activity_ids"], ["20749829518"])

        # Prune empty string parameters
        norm_empty = normalize_tool_call_arguments({"query": "  ", "start_date": "", "valid": "hello"})
        self.assertEqual(norm_empty, {"valid": "hello"})

        # Prune dummy zero bounds emitted when models populate all schema arguments
        full_dummy_args = {
            "query": "#vo2max",
            "sport_types": ["Ride"],
            "start_date": "",
            "end_date": "",
            "date_preset": "this_year",
            "min_distance_km": 0,
            "max_distance_km": 0,
            "min_elevation_m": 0,
            "max_elevation_m": 0,
            "min_moving_time_min": 0,
            "max_moving_time_min": 0,
            "min_watts": 0,
            "max_watts": 0,
            "min_max_watts": 0,
            "max_max_watts": 0,
            "min_heartrate": 0,
            "max_heartrate": 0,
            "has_heartrate": True,
            "has_power": True,
            "min_speed_kmh": 0,
            "max_speed_kmh": 0,
            "min_suffer_score": 0,
            "max_suffer_score": 0,
            "min_pr_count": 0,
            "gear_id": "",
            "workout_type": 0,
            "has_trophies": False,
            "koms_only": False,
            "weather_condition": "",
            "min_temp_c": 0,
            "max_temp_c": 0,
            "min_wind_speed_kmh": 0,
            "max_wind_speed_kmh": 0,
            "min_wind_speed_ms": 0,
            "max_wind_speed_ms": 0,
            "min_wind_gust_kmh": 0,
            "max_wind_gust_kmh": 0,
            "min_wind_gust_ms": 0,
            "max_wind_gust_ms": 0,
            "has_weather": False,
            "cursor": "",
            "limit": 100,
            "sort_by": "start_date",
            "sort_order": "asc",
        }
        cleaned = normalize_tool_call_arguments(full_dummy_args)
        self.assertEqual(cleaned["query"], "#vo2max")
        self.assertEqual(cleaned["sport_types"], ["Ride"])
        self.assertEqual(cleaned["date_preset"], "this_year")
        self.assertTrue(cleaned["has_heartrate"])
        self.assertTrue(cleaned["has_power"])
        self.assertEqual(cleaned["limit"], 100)
        self.assertEqual(cleaned["sort_by"], "start_date")
        self.assertEqual(cleaned["sort_order"], "asc")
        # Ensure dummy zero bounds that would zero out queries are stripped
        for poisoned in (
            "max_distance_km", "max_watts", "max_heartrate", "max_moving_time_min",
            "max_elevation_m", "min_distance_km", "min_watts", "workout_type",
            "start_date", "end_date", "has_weather", "has_trophies", "koms_only",
        ):
            self.assertNotIn(poisoned, cleaned)

    def test_to_gemini_and_openai_schema_prefers_string_for_unions(self):
        union_prop = {
            "anyOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}],
            "title": "Activity Id",
        }
        gemini = to_gemini_schema(union_prop)
        self.assertEqual(gemini["type"], "STRING")

        openai = to_openai_schema(union_prop)
        self.assertEqual(openai["type"], "string")

    def test_execute_chat_tool_with_integer_activity_id(self):
        repo = MagicMock()
        repo.get_activities_by_ids.return_value = [{
            "activity_id": "20749829518",
            "name": "Morning Ride",
            "distance": 50000.0,
            "moving_time": 5400,
        }]
        repo.get_stream_coverage.return_value = {}

        # Passing integer activity_id should not fail Pydantic validation
        payload, elapsed = execute_chat_tool(repo, "kinetiqo_get_activity_details", {"activity_id": 20749829518})
        self.assertNotIn("error", payload)
        self.assertEqual(payload.get("data_status"), "complete")
        self.assertEqual(payload.get("data", {}).get("activity_id"), "20749829518")
        self.assertGreaterEqual(elapsed, 0)

