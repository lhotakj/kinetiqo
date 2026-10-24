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

    def test_get_activity_totals_normalizes_cycling_sport_types(self):
        self.mock_repo.get_activities_totals.return_value = {
            "total_distance": 11122550.0,
            "total_elevation": 91245.9,
            "total_moving_time": 1529063,
        }
        self.mock_repo.count_activities.return_value = 250

        # When AI passes ['Ride'], it is normalized to include all cycling types (VirtualRide, GravelRide, etc.)
        res = activities.kinetiqo_get_activity_totals(self.mock_repo, sport_types=["Ride"], start_date="2026-01-01", end_date="2026-12-31")
        self.assertEqual(res["data_status"], "complete")
        self.assertEqual(res["data"]["distance_km"], 11122.55)
        self.assertEqual(res["data"]["elevation_m"], 91245.9)
        call_types = self.mock_repo.get_activities_totals.call_args.kwargs["types"]
        self.assertIn("VirtualRide", call_types)
        self.assertIn("GravelRide", call_types)
        self.assertIn("Ride", call_types)

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

    def test_calculate_power_curve_cross_activity(self):
        self.mock_repo.get_profile.return_value = {"weight": 70.0}
        self.mock_repo.get_activity_ids_by_types.return_value = [
            {"id": "101", "name": "Crit", "start_date": "2026-05-10T10:00:00Z"},
            {"id": "102", "name": "TT", "start_date": "2026-05-12T10:00:00Z"},
        ]
        def mock_best_power(ids, duration):
            return {"101": 300.0, "102": 320.0}
        self.mock_repo.get_best_power_per_activity.side_effect = mock_best_power

        res = telemetry.kinetiqo_calculate_power_curve(self.mock_repo, activity_id=None, days=30, durations=[5, 60])
        self.assertEqual(res["data_status"], "complete")
        self.assertEqual(res["data"]["mmp_curve"]["5"]["watts"], 320.0)
        self.assertEqual(res["data"]["mmp_curve"]["5"]["source_activity_id"], "102")
        self.assertAlmostEqual(res["data"]["mmp_curve"]["5"]["w_per_kg"], 4.57, places=2)

    def test_get_personal_records(self):
        self.mock_repo.get_profile.return_value = {"weight": 70.0}
        self.mock_repo.get_activity_ids_by_types.return_value = [
            {"id": "101", "name": "Morning Ride", "start_date": "2026-05-10T10:00:00Z"},
            {"id": "102", "name": "Evening Ride", "start_date": "2026-05-12T10:00:00Z"},
        ]
        def mock_best_power(ids, duration):
            if duration == 5:
                return {"101": 800.0, "102": 750.0}
            if duration == 300:
                return {"101": 350.0, "102": 380.0}
            return {}
        self.mock_repo.get_best_power_per_activity.side_effect = mock_best_power

        res = telemetry.kinetiqo_get_personal_records(
            self.mock_repo,
            athlete_id=1,
            durations=[5, 300],
            start_date="2026-05-01",
            end_date="2026-05-31",
        )
        self.assertEqual(res["data_status"], "complete")
        records = res["data"]["records"]
        self.assertEqual(records["5"]["watts"], 800.0)
        self.assertEqual(records["5"]["activity_id"], "101")
        self.assertEqual(records["5"]["activity_name"], "Morning Ride")
        self.assertEqual(records["300"]["watts"], 380.0)
        self.assertEqual(records["300"]["activity_id"], "102")
        self.assertEqual(records["300"]["activity_name"], "Evening Ride")

    # --- Group C: Physiology ---
    def test_get_ftp_history(self):
        self.mock_repo.get_profile.return_value = {"weight": 70.0, "ftp": 280.0}
        self.mock_repo.get_activity_ids_by_types.return_value = [
            {"id": "201", "name": "20m Test", "start_date": "2026-05-10T10:00:00Z"},
            {"id": "202", "name": "Zwift Race", "start_date": "2026-05-12T10:00:00Z"},
        ]
        def mock_best_power(ids, duration):
            if duration == 1200:
                return {"201": 300.0, "202": 320.0}
            return {}
        self.mock_repo.get_best_power_per_activity.side_effect = mock_best_power

        res = physiology.kinetiqo_get_ftp_history(self.mock_repo, athlete_id=1)
        self.assertEqual(res["data_status"], "complete")
        self.assertEqual(res["data"]["configured_ftp_watts"], 280.0)
        self.assertEqual(res["data"]["athlete_weight_kg"], 70.0)
        breakthroughs = res["data"]["historical_20m_breakthroughs"]
        self.assertEqual(len(breakthroughs), 2)
        self.assertEqual(breakthroughs[0]["activity_id"], "202")
        self.assertEqual(breakthroughs[0]["best_20m_watts"], 320.0)
        self.assertEqual(breakthroughs[0]["estimated_ftp_watts"], 304.0)
        self.assertAlmostEqual(breakthroughs[0]["w_per_kg"], 4.34, places=2)

    def test_get_power_skills(self):
        self.mock_repo.get_profile.return_value = {"weight": 70.0, "ftp": 280.0}
        self.mock_repo.get_activity_ids_by_types.return_value = [
            {"id": "301", "name": "Sprint Workout", "start_date": "2026-05-10T10:00:00Z"},
            {"id": "302", "name": "Threshold Intervals", "start_date": "2026-05-12T10:00:00Z"},
        ]
        def mock_best_power(ids, duration):
            if duration == 5:
                return {"301": 1000.0, "302": 700.0}
            if duration == 1200:
                return {"301": 250.0, "302": 320.0}
            return {}
        self.mock_repo.get_best_power_per_activity.side_effect = mock_best_power

        res = physiology.kinetiqo_get_power_skills(self.mock_repo, athlete_id=1)
        self.assertEqual(res["data_status"], "complete")
        benchmarks = res["data"]["benchmarks"]
        self.assertEqual(benchmarks["5"]["watts"], 1000.0)
        self.assertEqual(benchmarks["5"]["activity_id"], "301")
        self.assertEqual(benchmarks["1200"]["watts"], 320.0)
        self.assertEqual(benchmarks["1200"]["activity_id"], "302")

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

    def test_get_training_goals_db_schema(self):
        # DatabaseRepository returns rows with activity_type_id and goal columns
        self.mock_repo.get_goals.return_value = [
            {
                "activity_type_id": 1,
                "weekly_distance_goal": 200.0,
                "monthly_distance_goal": 800.0,
                "yearly_distance_goal": 10000.0,
                "weekly_elevation_goal": 2000.0,
                "monthly_elevation_goal": None,
                "yearly_elevation_goal": None,
            }
        ]
        self.mock_repo.get_activities_totals.return_value = {
            "total_distance": 150000.0,
            "total_elevation": 1800.0,
            "total_moving_time": 18000,
        }

        res = achievements.kinetiqo_get_training_goals(self.mock_repo, athlete_id=1)
        self.assertEqual(res["data_status"], "complete")
        goals = res["data"]["goals"]
        self.assertEqual(len(goals), 4)  # 3 distance goals + 1 elevation goal
        weekly_dist = next(g for g in goals if g["period"] == "weekly" and g["metric"] == "distance")
        self.assertEqual(weekly_dist["target"], 200.0)
        self.assertEqual(weekly_dist["actual"], 150.0)
        self.assertEqual(weekly_dist["remaining"], 50.0)
        self.assertEqual(weekly_dist["percent_completed"], 75.0)
        self.assertFalse(weekly_dist["is_completed"])

    def test_update_training_goals_upsert_goal(self):
        # DatabaseRepository uses upsert_goal
        mock_repo = MagicMock(spec=["get_goals", "upsert_goal"])
        mock_repo.get_goals.return_value = [
            {
                "activity_type_id": 1,
                "weekly_distance_goal": 150.0,
                "monthly_distance_goal": 600.0,
                "yearly_distance_goal": None,
                "weekly_elevation_goal": None,
                "monthly_elevation_goal": None,
                "yearly_elevation_goal": None,
            }
        ]

        res = achievements.kinetiqo_update_training_goals(
            mock_repo,
            athlete_id=1,
            period="weekly",
            goal_type="cycling",
            target=250.0,
            metric="distance",
            allow_write=True,
        )
        self.assertEqual(res["data_status"], "complete")
        self.assertTrue(res["data"]["success"])
        mock_repo.upsert_goal.assert_called_once_with(
            athlete_id=1,
            activity_type_id=1,
            weekly_distance_goal=250.0,
            monthly_distance_goal=600.0,
            yearly_distance_goal=None,
            weekly_elevation_goal=None,
            monthly_elevation_goal=None,
            yearly_elevation_goal=None,
        )

    def test_update_athlete_profile_upsert_profile(self):
        mock_repo = MagicMock(spec=["get_profile", "upsert_profile"])
        mock_repo.get_profile.return_value = {
            "athlete_id": 1,
            "first_name": "Test",
            "last_name": "Rider",
            "weight": 70.0,
            "ftp": 280.0,
            "refresh_token": "tok123",
            "gps_simplification": 1,
            "update_strava_cycling_indoor": "indoor template",
        }

        res = operations.kinetiqo_update_athlete_profile(
            mock_repo,
            weight_kg=72.5,
            ftp_watts=295.0,
            allow_write=True,
        )
        self.assertEqual(res["data_status"], "complete")
        self.assertTrue(res["data"]["success"])
        mock_repo.upsert_profile.assert_called_once()
        call_kwargs = mock_repo.upsert_profile.call_args[1]
        self.assertEqual(call_kwargs["weight"], 72.5)
        self.assertEqual(call_kwargs["ftp"], 295.0)
        self.assertEqual(call_kwargs["refresh_token"], "tok123")

    def test_tools_with_zero_argument_get_profile(self):
        # DatabaseRepository.get_profile() takes 0 arguments. Calling with 1 arg raises TypeError.
        class RealSignatureRepo:
            def get_profile(self):
                return {"athlete_id": 1, "weight": 70.0, "ftp": 280.0}

            def get_activity_ids_by_types(self, types, since_date=None, watts_only=False):
                return [{"id": "99", "name": "Solo TT", "start_date": "2026-05-15T09:00:00Z"}]

            def get_best_power_per_activity(self, activity_ids, duration_seconds, min_total_samples=0):
                return {"99": 350.0}

        repo = RealSignatureRepo()
        ftp_res = physiology.kinetiqo_get_ftp_history(repo, athlete_id=1)
        self.assertEqual(ftp_res["data_status"], "complete")
        self.assertEqual(ftp_res["data"]["configured_ftp_watts"], 280.0)

        skills_res = physiology.kinetiqo_get_power_skills(repo, athlete_id=1)
        self.assertEqual(skills_res["data_status"], "complete")
        self.assertIsNotNone(skills_res["data"]["benchmarks"]["1200"])

        pr_res = telemetry.kinetiqo_get_personal_records(repo, athlete_id=1, durations=[1200])
        self.assertEqual(pr_res["data_status"], "complete")
        self.assertIsNotNone(pr_res["data"]["records"]["1200"])


if __name__ == "__main__":
    unittest.main()
