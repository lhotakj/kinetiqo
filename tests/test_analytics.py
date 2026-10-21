"""Unit tests for pure analytical services: power, fitness, and pacing."""

import unittest
from kinetiqo.analytics.power import (
    calculate_normalized_power,
    calculate_intensity_factor,
    calculate_tss,
    calculate_mmp_curve,
)
from kinetiqo.analytics.fitness import calculate_ctl_atl_tsb
from kinetiqo.analytics.pacing import calculate_pacing_splits


class TestPowerAnalytics(unittest.TestCase):
    """Test suite for power modeling functions."""

    def test_calculate_normalized_power_constant_power(self):
        # 60 seconds of steady 200W should yield NP == 200.0
        watts = [200.0] * 60
        np_w = calculate_normalized_power(watts)
        self.assertAlmostEqual(np_w, 200.0, places=1)

    def test_calculate_normalized_power_short_series(self):
        watts = [200.0, 220.0, 240.0]
        self.assertEqual(calculate_normalized_power(watts), 220.0)
        self.assertEqual(calculate_normalized_power([]), 0.0)

    def test_calculate_intensity_factor(self):
        self.assertEqual(calculate_intensity_factor(200.0, 250.0), 0.8)
        self.assertIsNone(calculate_intensity_factor(200.0, 0.0))
        self.assertIsNone(calculate_intensity_factor(0.0, 250.0))

    def test_calculate_tss(self):
        # 1 hour at FTP (IF = 1.0) -> TSS = 100.0
        tss = calculate_tss(duration_seconds=3600, np_w=250.0, if_val=1.0, ftp=250.0)
        self.assertEqual(tss, 100.0)

        # 2 hours at 0.707 IF -> 2 * 0.707^2 * 100 = 100 TSS
        tss_2h = calculate_tss(duration_seconds=7200, np_w=176.75, if_val=0.707, ftp=250.0)
        self.assertAlmostEqual(tss_2h, 100.0, delta=1.0)

        self.assertIsNone(calculate_tss(0, 200.0, 0.8, 250.0))
        self.assertIsNone(calculate_tss(3600, 200.0, 0.8, 0.0))

    def test_calculate_mmp_curve_continuous_time(self):
        # 10 continuous seconds with 300W, followed by 5s at 100W
        timestamps = list(range(1000, 1015))
        watts = [300.0] * 10 + [100.0] * 5
        durations = [5, 10, 15]

        mmp = calculate_mmp_curve(timestamps, watts, durations)
        self.assertEqual(mmp[5], 300.0)
        self.assertEqual(mmp[10], 300.0)
        self.assertAlmostEqual(mmp[15], (300.0 * 10 + 100.0 * 5) / 15.0, places=1)

    def test_calculate_mmp_curve_with_pause_gap(self):
        # Pause gap: timestamp jumps from 1004 to 1020 (16-second gap)
        # Total samples = 8, but gap prevents continuous 10s window
        timestamps = [1000, 1001, 1002, 1003, 1004, 1020, 1021, 1022]
        watts = [400.0] * 8
        mmp = calculate_mmp_curve(timestamps, watts, durations=[10])
        # Since no 10-second continuous block exists, peak 10s power must be 0.0
        self.assertEqual(mmp[10], 0.0)


class TestFitnessAnalytics(unittest.TestCase):
    """Test suite for CTL/ATL/TSB calculation."""

    def test_calculate_ctl_atl_tsb_empty(self):
        res = calculate_ctl_atl_tsb([])
        self.assertEqual(res["dates"], [])
        self.assertEqual(res["current_ctl"], 0.0)

    def test_calculate_ctl_atl_tsb_progression(self):
        # 100 on day 1, then 4 rest days
        activities = [
            {"start_date": "2026-05-01T10:00:00Z", "suffer_score": 100},
            {"start_date": "2026-05-05T10:00:00Z", "suffer_score": 0},
        ]
        res = calculate_ctl_atl_tsb(activities, period_days=10)
        self.assertEqual(len(res["dates"]), 5)
        self.assertGreater(res["current_ctl"], 0.0)
        # Because ATL (span=7) decays faster towards 0 during rest days than CTL (span=42),
        # on day 5 CTL will be higher than ATL, resulting in positive Form (freshness)
        self.assertGreater(res["current_ctl"], res["current_atl"])
        self.assertGreater(res["current_tsb"], 0.0)


class TestPacingAnalytics(unittest.TestCase):
    """Test suite for pacing splits and Aerobic Decoupling."""

    def test_calculate_pacing_splits_halves(self):
        # 100 samples total, split into 2 halves of 50
        # First half: 200W, 140 bpm -> EF1 = 200/140 = 1.428
        # Second half: 190W, 145 bpm -> EF2 = 190/145 = 1.310
        stream = []
        for i in range(50):
            stream.append({"watts": 200.0, "heartrate": 140, "distance": i * 10, "altitude": 100.0 + i})
        for i in range(50, 100):
            stream.append({"watts": 190.0, "heartrate": 145, "distance": i * 10, "altitude": 150.0 + i * 0.5})

        res = calculate_pacing_splits(stream, num_splits=2)
        self.assertEqual(len(res["splits"]), 2)
        s1, s2 = res["splits"][0], res["splits"][1]
        self.assertEqual(s1["average_watts"], 200.0)
        self.assertEqual(s1["average_heartrate"], 140.0)
        self.assertEqual(s2["average_watts"], 190.0)
        self.assertEqual(s2["average_heartrate"], 145.0)

        # Decoupling EF1 / EF2 - 1 = (1.42857 / 1.31034) - 1 = +9.02%
        self.assertIsNotNone(res["aerobic_decoupling_pct"])
        self.assertAlmostEqual(res["aerobic_decoupling_pct"], 9.02, delta=0.5)


if __name__ == "__main__":
    unittest.main()
