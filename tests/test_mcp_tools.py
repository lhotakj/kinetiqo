"""Unit tests for Kinetiqo MCP tool implementations."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.mcp.tools import activities, telemetry, physiology, achievements, generator, operations


class TestMCPTools(unittest.TestCase):
    """Test all MCP tools with isolated mocked database repository."""

    def setUp(self):
        self.mock_repo = MagicMock()
        self.mock_config = MagicMock()
        self.mock_config.athlete_id = 1

    # --- Group A: Discovery ---
    def test_search_activities(self):
        self.mock_repo.search_activities.return_value = (
            [
                {
                    "activity_id": 12345,
                    "name": "Tempo Ride",
                    "start_date": "2026-05-12T08:00:00Z",
                    "sport_type": "Ride",
                    "distance": 54200.0,
                    "moving_time": 5400,
                    "total_elevation_gain": 450.0,
                    "average_watts": 215.0,
                    "suffer_score": 65,
                }
            ],
            "cursor_abc",
            True,
        )

        res = activities.kinetiqo_search_activities(self.mock_repo, athlete_id=1, query="Tempo", min_distance_km=50.0)
        self.assertEqual(res["data_status"], "complete")
        acts = res["data"]["activities"]
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["distance_km"], 54.2)
        self.assertEqual(res["data"]["pagination"]["next_cursor"], "cursor_abc")

    def test_get_activity_details(self):
        self.mock_repo.get_activities_by_ids.return_value = [
            {
                "activity_id": 12345,
                "name": "Hill Repeats",
                "sport_type": "Ride",
                "distance": 32000.0,
                "moving_time": 3600,
                "total_elevation_gain": 800.0,
                "average_watts": 240.0,
            }
        ]
        self.mock_repo.get_stream_coverage.return_value = {
            "watts": {"status": "present", "rows": 3600},
            "heartrate": {"status": "absent", "rows": 0},
        }

        res = activities.kinetiqo_get_activity_details(self.mock_repo, "12345")
        self.assertEqual(res["data"]["name"], "Hill Repeats")
        self.assertEqual(res["data"]["distance_km"], 32.0)
        self.assertIn("watts", res["data"]["sensor_coverage"])

    def test_compare_activities_bounds(self):
        # Less than 2 activities
        res = activities.kinetiqo_compare_activities(self.mock_repo, ["123"])
        self.assertEqual(res["data_status"], "unavailable")

    def test_compare_periods(self):
        self.mock_repo.get_activities_totals.side_effect = [
            {"distance": 100000.0, "elevation": 1000.0, "moving_time": 10800},
            {"distance": 120000.0, "elevation": 1200.0, "moving_time": 12600},
        ]
        self.mock_repo.count_activities.side_effect = [5, 6]

        res = activities.kinetiqo_compare_periods(
            self.mock_repo,
            period_a={"start_date": "2026-05-01", "end_date": "2026-05-31"},
            period_b={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )
        self.assertEqual(res["data"]["deltas"]["distance_km"], 20.0)
        self.assertEqual(res["data"]["deltas"]["distance_pct"], 20.0)

    # --- Group B: Telemetry ---
    def test_get_activity_streams(self):
        self.mock_repo.get_activity_stream_window.return_value = [
            {"ts": i, "watts": 220.0, "heartrate": 150} for i in range(100)
        ]
        res = telemetry.kinetiqo_get_activity_streams(self.mock_repo, "12345", resolution="auto")
        self.assertEqual(res["data"]["original_samples_count"], 100)
        self.assertIn("samples", res["data"])

    def test_calculate_power_curve_activity(self):
        self.mock_repo.get_activity_stream_window.return_value = [
            {"ts": i, "watts": 250.0} for i in range(100)
        ]
        res = telemetry.kinetiqo_calculate_power_curve(self.mock_repo, activity_id="12345", durations=[5, 10, 30])
        mmp = res["data"]["mmp_curve"]
        self.assertEqual(mmp["5"]["watts"], 250.0)

    def test_analyze_workout_structure(self):
        self.mock_repo.get_activities_by_ids.return_value = [{"activity_id": "123", "name": "Crit", "moving_time": 3600}]
        self.mock_repo.get_profile.return_value = {"ftp": 250.0}
        self.mock_repo.get_activity_stream_window.return_value = [{"ts": i, "watts": 250.0} for i in range(120)]

        res = telemetry.kinetiqo_analyze_workout_structure(self.mock_repo, "123")
        self.assertEqual(res["data"]["normalized_power_w"], 250.0)
        self.assertEqual(res["data"]["intensity_factor"], 1.0)

    # --- Group C: Physiology ---
    def test_get_fitness_and_freshness(self):
        self.mock_repo.get_activities_web.return_value = [
            {"start_date": "2026-05-10T10:00:00Z", "suffer_score": 80},
            {"start_date": "2026-05-12T10:00:00Z", "suffer_score": 60},
        ]
        res = physiology.kinetiqo_get_fitness_and_freshness(self.mock_repo, period_days=14, warmup_days=7)
        self.assertIn("fitness_ctl", res["data"]["current_status"])
        self.assertIn("training_status", res["data"]["current_status"])

    def test_get_vo2max_trend(self):
        self.mock_repo.get_profile.return_value = {"weight": 70.0, "ftp": 280.0}
        self.mock_repo.get_activity_ids_by_types.return_value = ["101"]
        self.mock_repo.get_best_power_per_activity.return_value = {"101": {300: 350.0}}
        self.mock_repo.get_activities_by_ids.return_value = [{"activity_id": "101", "name": "5m MAP test"}]

        res = physiology.kinetiqo_get_vo2max_trend(self.mock_repo, days=30)
        self.assertEqual(res["data"]["athlete_weight_kg"], 70.0)
        self.assertIsNotNone(res["data"]["coggan_ftp_vo2max"])
        self.assertEqual(len(res["data"]["recent_storer_davis_efforts"]), 1)

    def test_get_weekly_training_profile(self):
        self.mock_repo.get_activities_web.return_value = [
            {
                "activity_id": 101,
                "name": "Tuesday Intervals",
                "start_date": "2026-05-12T08:00:00Z",
                "distance": 45000.0,
                "moving_time": 4500,
                "total_elevation_gain": 400.0,
                "average_watts": 220.0,
                "weighted_average_watts": 235.0,
                "kilojoules": 990.0,
            },
            {
                "activity_id": 102,
                "name": "Saturday Long Ride",
                "start_date": "2026-05-16T09:00:00Z",
                "distance": 110000.0,
                "moving_time": 12600,
                "total_elevation_gain": 1200.0,
                "average_watts": 195.0,
                "weighted_average_watts": 210.0,
                "kilojoules": 2450.0,
            },
        ]

        res = physiology.kinetiqo_get_weekly_training_profile(self.mock_repo, athlete_id=1, year=2026)
        self.assertEqual(res["data_status"], "complete")
        self.assertEqual(res["data"]["period"]["total_activities"], 2)
        history = res["data"]["weekly_history"]
        self.assertEqual(len(history), 1)
        w = history[0]
        self.assertEqual(w["activity_count"], 2)
        self.assertEqual(w["distance_km"], 155.0)
        self.assertEqual(w["elevation_m"], 1600.0)
        self.assertAlmostEqual(w["kilojoules"], 3440.0)
        self.assertIsNotNone(w["average_watts"])
        self.assertIsNotNone(res["data"]["peak_weeks"]["best_power_week"])
        self.assertIn("day_of_week_distribution", res["data"]["typical_week_profile"])

    def test_analyze_recovery_turnaround(self):
        self.mock_repo.get_activities_web.return_value = [
            {
                "activity_id": 201,
                "name": "Gran Fondo 120k",
                "start_date": "2026-05-01T08:00:00Z",
                "distance": 120000.0,
                "moving_time": 14400,
                "total_elevation_gain": 1500.0,
                "suffer_score": 180,
            },
            {
                "activity_id": 202,
                "name": "Easy Recovery Spin",
                "start_date": "2026-05-03T10:00:00Z",
                "distance": 30000.0,
                "moving_time": 3600,
                "total_elevation_gain": 150.0,
                "suffer_score": 25,
            },
            {
                "activity_id": 203,
                "name": "Threshold Repeats",
                "start_date": "2026-05-05T08:00:00Z",
                "distance": 55000.0,
                "moving_time": 5500,
                "total_elevation_gain": 600.0,
                "suffer_score": 85,
            },
        ]

        res = physiology.kinetiqo_analyze_recovery_turnaround(self.mock_repo, min_distance_km=100.0)
        self.assertEqual(res["data_status"], "complete")
        self.assertEqual(res["data"]["qualifying_milestone_count"], 1)
        summary = res["data"]["turnaround_summary"]
        self.assertEqual(summary["median_rest_days_until_next_activity"], 2.0)
        self.assertEqual(summary["median_days_until_next_hard_workout"], 4.0)
        self.assertIn("guidance", summary)

    # --- Group D: Achievements ---
    @patch("kinetiqo.mcp.tools.achievements.load_verified_koms")
    def test_get_verified_koms(self, mock_load_koms):
        mock_load_koms.return_value = {"12345": 2}
        self.mock_repo.get_activities_by_ids.return_value = [{"activity_id": "12345", "name": "Passo Ride"}]

        res = achievements.kinetiqo_get_verified_koms(self.mock_repo, athlete_id=1)
        self.assertEqual(res["data"]["total_verified_koms"], 2)
        self.assertEqual(len(res["data"]["activities"]), 1)

    def test_update_training_goals_gating(self):
        # Denied when allow_write is False
        res = achievements.kinetiqo_update_training_goals(self.mock_repo, athlete_id=1, period="weekly", goal_type="cycling", target=200.0, allow_write=False)
        self.assertEqual(res["data_status"], "unavailable")

        # Allowed when allow_write is True
        res_ok = achievements.kinetiqo_update_training_goals(self.mock_repo, athlete_id=1, period="weekly", goal_type="cycling", target=200.0, allow_write=True)
        self.assertTrue(res_ok["data"]["success"])

    # --- Group E: Generator ---
    @patch("kinetiqo.mcp.tools.generator.render_poster_artifact")
    def test_generate_activity_poster(self, mock_render):
        mock_render.return_value = b"\x89PNG\r\n\x1a\nfake_poster_bytes"
        res = generator.kinetiqo_generate_activity_poster(self.mock_repo, self.mock_config, activity_id="12345")
        self.assertEqual(res["source"], "rendered")
        self.assertEqual(res["data"]["artifact_type"], "activity_poster")
        self.assertIn("inline_image_base64", res["data"])

    @patch("kinetiqo.mcp.tools.generator.render_poster_artifact")
    def test_generate_activity_poster_missing_playwright(self, mock_render):
        mock_render.side_effect = RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium")
        res = generator.kinetiqo_generate_activity_poster(self.mock_repo, self.mock_config, activity_id="12345")
        self.assertEqual(res["data_status"], "unavailable")
        self.assertIn("Playwright", res["data"]["message"])
        self.assertIn("kinetiqo/web-mcp", res["data"]["message"])

    # --- Group F: Operations ---
    def test_operations_gating(self):
        # Sync denied by default
        sync_denied = operations.kinetiqo_trigger_sync(self.mock_repo, self.mock_config, allow_sync=False)
        self.assertEqual(sync_denied["data_status"], "unavailable")

        # Sync allowed when flag enabled
        sync_ok = operations.kinetiqo_trigger_sync(self.mock_repo, self.mock_config, allow_sync=True)
        self.assertEqual(sync_ok["data"]["status"], "queued")

        # Strava write denied by default
        strava_denied = operations.kinetiqo_update_strava_description(self.mock_repo, self.mock_config, "123", "prev_1", allow_write=False)
        self.assertEqual(strava_denied["data_status"], "unavailable")

        # Profile write denied by default
        prof_denied = operations.kinetiqo_update_athlete_profile(self.mock_repo, weight_kg=72.0, allow_write=False)
        self.assertEqual(prof_denied["data_status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
