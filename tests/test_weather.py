"""Mocked unit tests for historical weather calculations and provider handling."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from kinetiqo.weather import (
    WeatherProviderError,
    WeatherQuotaExceeded,
    build_activity_weather,
    fetch_visual_crossing_hour,
    format_weather_placeholders,
    hourly_intervals,
    interpolate_route_position,
)


class WeatherCalculationTests(unittest.TestCase):
    def test_hourly_intervals_clip_activity_boundaries(self):
        start = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc)
        self.assertEqual(
            hourly_intervals(start, end),
            [
                (datetime(2026, 1, 1, 10, tzinfo=timezone.utc), 1800),
                (datetime(2026, 1, 1, 11, tzinfo=timezone.utc), 3600),
                (datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 900),
            ],
        )

    def test_route_interpolation_rejects_long_gps_gap(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        points = [
            {"ts": start, "lat": 50.0, "lng": 14.0},
            {"ts": start + timedelta(minutes=16), "lat": 50.01, "lng": 14.01},
        ]
        self.assertIsNone(interpolate_route_position(points, start + timedelta(minutes=8)))

    def test_route_interpolation_returns_position_and_bearing(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        points = [
            {"ts": start, "lat": 50.0, "lng": 14.0},
            {"ts": start + timedelta(minutes=10), "lat": 50.0, "lng": 14.01},
        ]
        position = interpolate_route_position(points, start + timedelta(minutes=5))
        self.assertIsNotNone(position)
        assert position is not None
        self.assertAlmostEqual(position["latitude"], 50.0)
        self.assertAlmostEqual(position["longitude"], 14.005)
        self.assertGreater(position["bearing_deg"], 80)
        self.assertLess(position["bearing_deg"], 100)

    def test_activity_weather_uses_midpoint_of_clipped_first_hour(self):
        start = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
        points = [
            {"ts": start, "lat": 50.0, "lng": 14.0, "distance": 0.0},
            {"ts": start + timedelta(minutes=15), "lat": 50.0, "lng": 14.01, "distance": 1000.0},
            {"ts": start + timedelta(minutes=30), "lat": 50.0, "lng": 14.02, "distance": 2000.0},
        ]
        fetch_hour = Mock(return_value=({"wind_speed_ms": 4.0, "wind_direction_deg": 270.0}, 1))
        payload = build_activity_weather(
            {
                "start_date": start,
                "elapsed_time": 1800,
                "sport_type": "Walk",
            },
            points,
            fetch_hour,
            Mock(return_value=1),
        )

        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["samples"][0]["interval_seconds"], 1800)
        self.assertEqual(payload["samples"][0]["route_distance_m"], 2000.0)
        self.assertEqual(fetch_hour.call_args.args, (50.0, 14.01, datetime(2026, 1, 1, 10, tzinfo=timezone.utc)))

    def test_formatter_omits_absent_precipitation_and_formats_wind(self):
        payload = {
            "status": "complete",
            "activity": {
                "sport_type": "Ride",
                "start_utc": "2026-01-01T10:00:00+00:00",
                "end_utc": "2026-01-01T11:00:00+00:00",
            },
            "samples": [{
                "interval_seconds": 3600,
                "conditions": "Partly cloudy",
                "temperature_c": 12,
                "apparent_temperature_c": 11,
                "precipitation_mm": 0,
                "snowfall_cm": 0,
                "precipitation_types": [],
                "wind_speed_ms": 4,
                "wind_direction_deg": 270,
                "wind_gusts_ms": 11,
                "headwind_component_ms": 4,
            }],
        }
        rendered = format_weather_placeholders(payload)
        self.assertNotIn("rain", rendered["weather-basic"].lower())
        self.assertIn("Partly cloudy", rendered["weather-basic"])
        self.assertIn("m/s", rendered["weather-wind"])
        self.assertIn("gusts", rendered["weather-wind"])

    def test_formatter_preserves_brief_provider_named_severe_condition(self):
        rendered = format_weather_placeholders({
            "status": "complete",
            "activity": {"sport_type": "Hike"},
            "samples": [
                {"interval_seconds": 3500, "conditions": "Overcast"},
                {"interval_seconds": 100, "conditions": "Thunderstorm with hail"},
            ],
        })
        self.assertIn("Thunderstorm with hail", rendered["weather-basic"])

    def test_formatter_respects_gust_threshold_and_circular_wind_direction(self):
        samples = [
            {
                "interval_seconds": 1800,
                "conditions": "Clear",
                "wind_speed_ms": 3.0,
                "wind_direction_deg": 359,
                "wind_gusts_ms": 7.9,
                "headwind_component_ms": 3.0,
            },
            {
                "interval_seconds": 1800,
                "conditions": "Clear",
                "wind_speed_ms": 3.0,
                "wind_direction_deg": 1,
                "wind_gusts_ms": 8.0,
                "headwind_component_ms": 3.0,
            },
        ]
        rendered = format_weather_placeholders({
            "status": "complete",
            "activity": {
                "sport_type": "Ride",
                "start_utc": "2026-01-01T10:00:00+00:00",
                "end_utc": "2026-01-01T11:00:00+00:00",
            },
            "samples": samples,
        })
        self.assertIn("N wind", rendered["weather-basic"])
        self.assertIn("moderate gusts up to 8.0 m/s", rendered["weather-basic"])
        self.assertNotIn("7.9 m/s", rendered["weather-basic"])
        self.assertIn("headwind", rendered["weather-wind"])

    def test_formatter_does_not_infer_rain_from_untyped_precipitation(self):
        rendered = format_weather_placeholders({
            "status": "complete",
            "activity": {"sport_type": "Hike"},
            "samples": [{
                "interval_seconds": 3600,
                "precipitation_mm": 1.2,
                "precipitation_types": [],
            }],
        })
        self.assertIn("precipitation", rendered["weather-precipitation"])
        self.assertNotIn("rain", rendered["weather-precipitation"])

    def test_formatter_reports_cold_and_freezing_minima(self):
        cases = (
            (4.9, 6.0, "cold", "down to 4.9°C"),
            (0.0, 2.0, "freezing", "down to 0.0°C"),
            (6.0, -2.0, "freezing", "feels like as low as -2.0°C"),
        )
        for air, apparent, expected_label, expected_minimum in cases:
            with self.subTest(air=air, apparent=apparent):
                rendered = format_weather_placeholders({
                    "status": "complete",
                    "activity": {"sport_type": "Hike"},
                    "samples": [{
                        "interval_seconds": 3600,
                        "temperature_c": air,
                        "apparent_temperature_c": apparent,
                    }],
                })
                self.assertIn(expected_label, rendered["weather-basic"])
                self.assertIn(expected_minimum, rendered["weather-basic"])

    def test_fetch_reserves_actual_additional_query_cost_and_returns_requested_hour(self):
        hour = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "queryCost": 24,
            "days": [{
                "hours": [{
                    "datetimeEpoch": int(hour.timestamp()),
                    "temp": 12,
                    "feelslike": 10,
                    "conditions": "Clear",
                }],
            }],
        }
        reserve = Mock(side_effect=[1, 24])
        values, cost = fetch_visual_crossing_hour(
            50, 14, hour, api_key="test-key", reserve_quota=reserve,
            get=Mock(return_value=response), sleep=Mock(),
        )
        self.assertEqual(reserve.call_args_list[0].args, (1,))
        self.assertEqual(reserve.call_args_list[1].args, (23,))
        self.assertEqual(cost, 24)
        self.assertEqual(values["temperature_c"], 12)

    def test_fetch_rejects_response_when_actual_cost_cannot_be_reserved(self):
        hour = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"queryCost": 24, "days": []}
        reserve = Mock(side_effect=[1, None])
        with self.assertRaises(WeatherQuotaExceeded):
            fetch_visual_crossing_hour(
                50, 14, hour, api_key="test-key", reserve_quota=reserve,
                get=Mock(return_value=response), sleep=Mock(),
            )
        self.assertEqual(reserve.call_args_list[0].args, (1,))
        self.assertEqual(reserve.call_args_list[1].args, (23,))


class WeatherMCPToolTests(unittest.TestCase):
    def test_weather_tool_is_bounded_and_excludes_coordinates(self):
        from kinetiqo.mcp.tools.weather import kinetiqo_get_activity_weather

        repo = Mock()
        repo.get_activity_weather.return_value = {
            "weather_json": {
                "schema_version": 1,
                "status": "complete",
                "provider": "visual-crossing",
                "latitude": 51.0,
                "samples": [
                    {"time_utc": f"2026-01-01T{hour:02d}:00:00+00:00", "temperature_c": 10}
                    for hour in range(3)
                ],
            },
        }
        result = kinetiqo_get_activity_weather(repo, "123", max_samples=2)
        self.assertEqual(len(result["data"]["samples"]), 2)
        self.assertNotIn("latitude", result["data"])
        self.assertTrue(result["warnings"])


class VisualCrossingClientTests(unittest.TestCase):
    def test_fetch_reserves_quota_and_normalizes_hourly_weather(self):
        hour = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "queryCost": 1,
            "days": [{
                "hours": [{
                    "datetimeEpoch": int(hour.timestamp()),
                    "temp": 12,
                    "feelslike": 10,
                    "precip": 0.2,
                    "snow": 0,
                    "preciptype": ["rain"],
                    "conditions": "Rain, Partially cloudy",
                    "winddir": 270,
                    "windspeed": 18,
                    "windgust": 36,
                    "source": "obs",
                }],
            }],
        }
        request = Mock(return_value=response)
        reservation = Mock(return_value=4)
        values, cost = fetch_visual_crossing_hour(
            50, 14, hour, api_key="test-key", reserve_quota=reservation,
            get=request, sleep=Mock(),
        )
        reservation.assert_called_once_with(1)
        self.assertEqual(cost, 1)
        self.assertEqual(values["wind_speed_ms"], 5)
        self.assertEqual(values["wind_gusts_ms"], 10)
        self.assertEqual(values["source"], "obs")
        self.assertEqual(request.call_args.kwargs["params"]["timezone"], "Z")

    def test_fetch_does_not_dispatch_when_quota_reservation_fails(self):
        request = Mock()
        with self.assertRaises(WeatherQuotaExceeded):
            fetch_visual_crossing_hour(
                50, 14, datetime(2026, 1, 1, tzinfo=timezone.utc),
                api_key="test-key", reserve_quota=Mock(return_value=None),
                get=request, sleep=Mock(),
            )
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
