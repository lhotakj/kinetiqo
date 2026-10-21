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
