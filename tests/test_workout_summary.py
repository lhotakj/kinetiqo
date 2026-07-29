"""Unit tests for RestOrTrain-style workout summary generator."""

import unittest
from unittest.mock import MagicMock

from kinetiqo.workout_summary import (
    calculate_normalized_power,
    format_duration,
    generate_workout_summary,
    get_power_zone_name,
)
from kinetiqo.strava_description import DescriptionContext


class TestWorkoutSummary(unittest.TestCase):
    def test_calculate_normalized_power_constant(self):
        """Constant power stream should yield NP equal to constant power."""
        watts = [200.0] * 120
        np = calculate_normalized_power(watts)
        self.assertAlmostEqual(np, 200.0, delta=0.5)

    def test_calculate_normalized_power_empty(self):
        """Empty watts stream yields 0.0 NP."""
        self.assertEqual(calculate_normalized_power([]), 0.0)

    def test_format_duration(self):
        """Test duration formatting logic for minutes and hours."""
        self.assertEqual(format_duration(2700, use_minutes=True), "45min")
        self.assertEqual(format_duration(7200, use_minutes=True), "120min")
        self.assertEqual(format_duration(14400, use_minutes=True), "4h")
        self.assertEqual(format_duration(9000, use_minutes=False), "2h30m")

    def test_get_power_zone_name(self):
        """Test Coggan 7-zone power zone names."""
        self.assertEqual(get_power_zone_name(50.0), "Recovery")
        self.assertEqual(get_power_zone_name(65.0), "Endurance")
        self.assertEqual(get_power_zone_name(82.0), "Tempo")
        self.assertEqual(get_power_zone_name(98.0), "Threshold")
        self.assertEqual(get_power_zone_name(115.0), "VO2max")
        self.assertEqual(get_power_zone_name(130.0), "Anaerobic")

    def test_generate_workout_summary_power_steady(self):
        """Test steady endurance ride summary with power."""
        activity = {"moving_time": 7200, "average_watts": 191.0}
        watts_stream = [191.0] * 7200
        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("Endurance", res)
        self.assertIn("120min @ 191W", res)

    def test_generate_workout_summary_hr_fallback(self):
        """Test HR fallback summary when power is unavailable."""
        activity = {"moving_time": 9000, "average_heartrate": 125.0}
        res = generate_workout_summary(activity, watts_stream=None, ftp=None)
        self.assertEqual(res, "Endurance | About 2h30m aerobic riding @ 125bpm average HR")

    def test_generate_workout_summary_with_blocks(self):
        """Test variable ride with sustained interval blocks."""
        activity = {"moving_time": 14400, "average_watts": 190.0, "weighted_average_watts": 209.0}
        # 4 hours ride with two 12-min tempo blocks @ 230W
        watts_stream = [180.0] * 14400
        for i in range(1800, 2520):
            watts_stream[i] = 230.0
        for i in range(7200, 7920):
            watts_stream[i] = 235.0

        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("Endurance", res)
        self.assertIn("4h", res)
        self.assertIn("blocks @", res)

    def test_description_context_workout_summary_token(self):
        """Test {{workout-summary}} placeholder in DescriptionContext."""
        mock_config = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_profile.return_value = {"ftp": 280.0}
        mock_repo.get_watts_streams_for_activities.return_value = {"12345": [191.0] * 7200}
        mock_repo.get_goals.return_value = {}

        ctx = DescriptionContext(mock_config, mock_repo)
        activity = {"id": "12345", "moving_time": 7200, "average_watts": 191.0}

        rendered = ctx.render_for_activity(
            "{{workout-summary}}",
            "2026-07-29T12:00:00Z",
            "",
            activity=activity,
        )
        self.assertIn("Endurance | 120min @ 191W", rendered)


if __name__ == "__main__":
    unittest.main()
