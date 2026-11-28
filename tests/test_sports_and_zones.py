"""Unit tests for unified sports taxonomy and physiology zones."""

import unittest

from kinetiqo.sports import (
    ACTIVITY_GROUPS,
    CYCLING_TYPES,
    normalize_sport_group,
    normalize_sport_types,
)
from kinetiqo.analytics.zones import (
    calculate_coggan_zones,
    calculate_hr_zones,
    compute_coggan_zones,
    get_power_zone_name,
)


class TestSportsAndZones(unittest.TestCase):
    def test_normalize_sport_group(self):
        self.assertEqual(normalize_sport_group("cycling"), "cycling")
        self.assertEqual(normalize_sport_group("indoor cycling"), "cycling_indoor")
        self.assertEqual(normalize_sport_group("outdoor bike"), "cycling_outdoor")
        self.assertEqual(normalize_sport_group("running"), "running")
        self.assertEqual(normalize_sport_group("outdoor run"), "running_outdoor")
        self.assertEqual(normalize_sport_group("treadmill"), "running_indoor")
        self.assertEqual(normalize_sport_group("hiking"), "walking")
        self.assertEqual(normalize_sport_group("swim"), "swimming")
        self.assertEqual(normalize_sport_group("snowboard"), "skiing")
        self.assertEqual(normalize_sport_group("unknown"), "cycling")

    def test_normalize_sport_types(self):
        self.assertIsNone(normalize_sport_types(None))
        self.assertIsNone(normalize_sport_types([]))

        # Outdoor cycling
        out_types = normalize_sport_types("outdoor_cycling")
        self.assertIn("Ride", out_types)
        self.assertIn("GravelRide", out_types)
        self.assertNotIn("VirtualRide", out_types)

        # Indoor cycling
        in_types = normalize_sport_types("zwift")
        self.assertEqual(in_types, ["VirtualRide"])

        # All cycling
        all_types = normalize_sport_types("cycling")
        self.assertIn("Ride", all_types)
        self.assertIn("VirtualRide", all_types)

    def test_get_power_zone_name(self):
        # Percentage scale (0 to 100)
        self.assertEqual(get_power_zone_name(50.0), "Recovery")
        self.assertEqual(get_power_zone_name(70.0), "Endurance")
        self.assertEqual(get_power_zone_name(85.0), "Tempo")
        self.assertEqual(get_power_zone_name(100.0), "Threshold")
        self.assertEqual(get_power_zone_name(115.0), "VO2max")
        self.assertEqual(get_power_zone_name(130.0), "Anaerobic")

        # Decimal scale (0.0 to 1.5)
        self.assertEqual(get_power_zone_name(0.50), "Recovery")
        self.assertEqual(get_power_zone_name(0.70), "Endurance")
        self.assertEqual(get_power_zone_name(1.00), "Threshold")

    def test_compute_coggan_zones(self):
        zones = compute_coggan_zones(ftp=250.0, weight_kg=70.0)
        self.assertEqual(len(zones), 8)  # Z1 to Z7 + Sweet Spot
        z1 = next(z for z in zones if z["zone"] == "Z1")
        self.assertEqual(z1["min_watts"], 0.0)
        self.assertEqual(z1["max_watts"], 137.5)
        self.assertIn("Active Recovery", z1["name"])

        z4 = next(z for z in zones if z["zone"] == "Z4")
        self.assertEqual(z4["min_watts"], 227.5)
        self.assertEqual(z4["max_watts"], 262.5)

    def test_calculate_coggan_zones_distribution(self):
        # 10 samples of 100W (Z1 with FTP 250) and 10 samples of 250W (Z4 with FTP 250)
        watts = [100.0] * 10 + [250.0] * 10
        dist = calculate_coggan_zones(watts, ftp=250.0)
        self.assertEqual(len(dist), 7)
        z1 = next(d for d in dist if d["zone"] == "Z1")
        z4 = next(d for d in dist if d["zone"] == "Z4")
        self.assertEqual(z1["seconds"], 10)
        self.assertEqual(z1["percent"], 50.0)
        self.assertEqual(z4["seconds"], 10)
        self.assertEqual(z4["percent"], 50.0)

    def test_calculate_hr_zones_distribution(self):
        # Max HR 200: 50% is 100 bpm (Z1 min), 60% is 120 bpm (Z1 max)
        hrs = [110] * 10 + [170] * 10
        dist = calculate_hr_zones(hrs, max_hr=200)
        self.assertEqual(len(dist), 5)
        z1 = next(d for d in dist if d["zone"] == "Z1")
        z4 = next(d for d in dist if d["zone"] == "Z4")
        self.assertEqual(z1["seconds"], 10)
        self.assertEqual(z1["percent"], 50.0)
        self.assertEqual(z4["seconds"], 10)
        self.assertEqual(z4["percent"], 50.0)


if __name__ == "__main__":
    unittest.main()
