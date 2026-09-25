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



    def test_generate_workout_summary_highlights_single_peak(self):
        """A sustained 2-min surge well above the threshold is highlighted."""
        activity = {"moving_time": 3600, "average_watts": 180.0}
        watts_stream = [180.0] * 3600
        for i in range(600, 720):
            watts_stream[i] = 380.0
        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("Endurance", res)
        self.assertIn("+ peak 2min @380W", res)

    def test_generate_workout_summary_highlights_multiple_peaks(self):
        """Several surges above the threshold are highlighted as 'Nx surges'."""
        activity = {"moving_time": 5400, "average_watts": 180.0}
        watts_stream = [180.0] * 5400
        for start, watts in ((600, 360.0), (1800, 380.0), (3000, 400.0)):
            for i in range(start, start + 90):
                watts_stream[i] = watts
        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("3x surges", res)
        self.assertIn("@360-400W", res)

    def test_generate_workout_summary_no_peaks_below_threshold_or_too_short(self):
        """Sub-threshold or sub-minute efforts are not highlighted."""
        activity = {"moving_time": 3600, "average_watts": 180.0}
        watts_stream = [180.0] * 3600
        for i in range(600, 645):   # 45s — too short
            watts_stream[i] = 380.0
        for i in range(1200, 1320):  # below the 300W floor / 110% FTP
            watts_stream[i] = 280.0
        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertNotIn("peak", res)
        self.assertNotIn("surges", res)

    def test_generate_workout_summary_surges_use_average_watts_not_sample_spikes(self):
        """Surges with 0W dropouts or high single-sample spikes use average power, not min/max sample range."""
        activity = {"moving_time": 3480, "average_watts": 180.0}
        watts_stream = [180.0] * 3480
        # Surge 1 (70s): avg ~ 350W, but contains 0W dropout and 663W spike
        for i in range(600, 670):
            watts_stream[i] = 350.0
        watts_stream[610] = 0.0
        watts_stream[620] = 663.0

        # Surge 2 (70s): avg ~ 370W
        for i in range(1800, 1870):
            watts_stream[i] = 370.0

        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("2x surges", res)
        self.assertNotIn("0-", res)
        self.assertNotIn("663", res)
        self.assertIn("@349-370W", res)

    def test_sprint_peak_highlight_1000w_tier(self):
        """A sprint peak over 1000W (e.g. 1050W) uses 1000W tier adjectives (impressive, striking, respectable)."""
        activity = {"moving_time": 3600, "average_watts": 180.0}
        watts_stream = [180.0] * 3600
        for i in range(600, 605):
            watts_stream[i] = 1050.0

        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("5 sec peak 1050W", res)
        self.assertTrue(any(word in res for word in ["impressive", "striking", "respectable"]))

    def test_sprint_peak_highlight_1500w_tier(self):
        """A sprint peak over 1500W (e.g. 1580W) uses 1500W tier adjectives (remarkable, mind-blowing, extraordinary)."""
        activity = {"moving_time": 3600, "average_watts": 180.0}
        watts_stream = [180.0] * 3600
        for i in range(600, 603):
            watts_stream[i] = 1580.0

        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("3 sec peak 1580W", res)
        self.assertTrue(any(word in res for word in ["remarkable", "mind-blowing", "extraordinary"]))

    def test_sprint_peak_highlight_1700w_tier(self):
        """A sprint peak over 1700W (e.g. 1750W) uses 1700W tier adjectives (monumental, breathtaking, jaw-dropping, extraordinary)."""
        activity = {"moving_time": 3600, "average_watts": 180.0}
        watts_stream = [180.0] * 3600
        for i in range(600, 605):
            watts_stream[i] = 1750.0

        res = generate_workout_summary(activity, watts_stream=watts_stream, ftp=280.0)
        self.assertIn("5 sec peak 1750W", res)
        self.assertTrue(any(word in res for word in ["monumental", "breathtaking", "jaw-dropping", "extraordinary"]))

    def test_sprint_peak_metadata_fallback(self):
        """When watts_stream is not available, max_watts >= 1000 in activity metadata highlights 1 sec peak."""
        activity = {"moving_time": 3600, "average_watts": 180.0, "max_watts": 1100.0}
        res = generate_workout_summary(activity, watts_stream=None, ftp=280.0)
        self.assertIn("1 sec peak 1100W", res)

    def test_sprint_peak_grammar_article(self):
        """Article selection matches vowel ('an') vs consonant ('a') initial adjectives."""
        from kinetiqo.workout_summary import format_sprint_peak_highlight
        peak_extraordinary = {"duration_s": 5, "avg_w": 1550.0, "max_w": 1550.0, "tier_w": 1550.0}

        # Test multiple random samples, checking that 'an extraordinary' or 'a mind-blowing' or 'a remarkable' is valid
        for _ in range(30):
            formatted = format_sprint_peak_highlight(peak_extraordinary)
            if "extraordinary" in formatted:
                self.assertIn("with an extraordinary", formatted)
            elif "mind-blowing" in formatted:
                self.assertIn("with a mind-blowing", formatted)
            elif "remarkable" in formatted:
                self.assertIn("with a remarkable", formatted)


if __name__ == "__main__":
    unittest.main()
