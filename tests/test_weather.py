"""Mocked unit tests for historical weather calculations and provider handling."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from kinetiqo.weather import (
    WeatherProviderError,
    WeatherRateLimitState,
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
        fetch_hour = Mock(return_value={"wind_speed_ms": 4.0, "wind_direction_deg": 270.0})
        payload = build_activity_weather(
            {
                "start_date": start,
                "elapsed_time": 1800,
                "sport_type": "Walk",
            },
            points,
            fetch_hour,
        )

        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["samples"][0]["interval_seconds"], 1800)
        self.assertEqual(payload["samples"][0]["route_distance_m"], 2000.0)
        self.assertEqual(fetch_hour.call_args.args, (50.0, 14.01, datetime(2026, 1, 1, 10, tzinfo=timezone.utc)))

    def test_activity_weather_fetches_stationary_short_route_without_headwind(self):
        start = datetime(2026, 10, 27, 17, 13, 32, tzinfo=timezone.utc)
        points = [
            {"ts": start, "lat": 50.038947, "lng": 14.327329, "distance": 0.0},
            {
                "ts": start + timedelta(seconds=27),
                "lat": 50.038947,
                "lng": 14.327329,
                "distance": 0.0,
            },
        ]
        fetch_hour = Mock(return_value={"wind_speed_ms": 4.0, "wind_direction_deg": 270.0})

        payload = build_activity_weather(
            {"start_date": start, "elapsed_time": 27, "sport_type": "Hike"},
            points,
            fetch_hour,
        )

        self.assertEqual(payload["status"], "complete")
        self.assertIsNone(payload["samples"][0]["route_bearing_deg"])
        self.assertIsNone(payload["samples"][0]["headwind_component_ms"])
        self.assertEqual(
            fetch_hour.call_args.args,
            (50.038947, 14.327329, datetime(2026, 10, 27, 17, tzinfo=timezone.utc)),
        )

    def test_activity_weather_uses_nearest_in_hour_gps_point_for_sparse_route(self):
        start = datetime(2026, 10, 27, 17, 13, 32, tzinfo=timezone.utc)
        points = [
            {"ts": start, "lat": 50.038947, "lng": 14.327329, "distance": 0.0},
        ]
        fetch_hour = Mock(return_value={"wind_speed_ms": 4.0, "wind_direction_deg": 270.0})

        payload = build_activity_weather(
            {"start_date": start, "elapsed_time": 27, "sport_type": "Hike"},
            points,
            fetch_hour,
        )

        self.assertEqual(payload["status"], "complete")
        self.assertEqual(
            fetch_hour.call_args.args,
            (50.038947, 14.327329, datetime(2026, 10, 27, 17, tzinfo=timezone.utc)),
        )

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

    def test_activity_weather_discards_partial_samples_when_rate_limit_is_reached(self):
        start = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        points = [
            {"ts": start + timedelta(minutes=25), "lat": 50.0, "lng": 14.0, "distance": 0.0},
            {"ts": start + timedelta(minutes=35), "lat": 50.0, "lng": 14.01, "distance": 100.0},
        ]
        payload = build_activity_weather(
            {"start_date": start, "elapsed_time": 7200, "sport_type": "Ride"},
            points,
            Mock(return_value={"wind_speed_ms": 4.0, "wind_direction_deg": 270.0}),
            rate_limit_reached=Mock(return_value=True),
        )

        self.assertEqual(payload["status"], "deferred_rate_limit")
        self.assertEqual(payload["samples"], [])


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
    def test_fetch_reuses_other_returned_hours_for_same_location_and_day(self):
        hour = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        next_hour = hour + timedelta(hours=1)
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "days": [{
                "hours": [
                    {"datetimeEpoch": int(hour.timestamp()), "temp": 12},
                    {"datetimeEpoch": int(next_hour.timestamp()), "temp": 13},
                ],
            }],
        }
        request = Mock(return_value=response)
        hourly_cache = {}

        first_values = fetch_visual_crossing_hour(
            50, 14, hour, api_key="test-key",
            hourly_cache=hourly_cache, get=request, sleep=Mock(),
        )
        second_values = fetch_visual_crossing_hour(
            50, 14, next_hour, api_key="test-key",
            hourly_cache=hourly_cache, get=request, sleep=Mock(),
        )

        self.assertEqual(first_values["temperature_c"], 12)
        self.assertEqual(second_values["temperature_c"], 13)
        request.assert_called_once()

    def test_fetch_normalizes_hourly_weather(self):
        hour = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
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
        values = fetch_visual_crossing_hour(
            50, 14, hour, api_key="test-key",
            get=request, sleep=Mock(),
        )
        self.assertEqual(values["wind_speed_ms"], 5)
        self.assertEqual(values["wind_gusts_ms"], 10)
        self.assertEqual(values["source"], "obs")
        self.assertEqual(request.call_args.kwargs["params"]["timezone"], "Z")

    def test_zero_remaining_header_stops_future_requests_until_utc_midnight(self):
        hour = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        response = Mock()
        response.status_code = 200
        response.headers = {"X-RateLimit-Remaining": "0"}
        response.json.return_value = {
            "days": [{"hours": [{"datetimeEpoch": int(hour.timestamp()), "temp": 12}]}],
        }
        request = Mock(return_value=response)
        state = WeatherRateLimitState()

        self.assertEqual(
            fetch_visual_crossing_hour(
                50, 14, hour, api_key="test-key", rate_limit_state=state,
                get=request, sleep=Mock(),
            )["temperature_c"],
            12,
        )
        with self.assertRaises(WeatherProviderError) as raised:
            fetch_visual_crossing_hour(
                50, 14, hour + timedelta(hours=1), api_key="test-key",
                rate_limit_state=state, get=request, sleep=Mock(),
            )
        self.assertTrue(raised.exception.stop_run)
        request.assert_called_once()
        self.assertTrue(state.is_exhausted())

    def test_rate_limit_state_expires_at_utc_midnight(self):
        state = WeatherRateLimitState()
        state.mark_exhausted(datetime(2026, 1, 1, 10, tzinfo=timezone.utc))

        self.assertTrue(state.is_exhausted(datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc)))
        self.assertFalse(state.is_exhausted(datetime(2026, 1, 2, tzinfo=timezone.utc)))

    def test_missing_or_invalid_remaining_header_does_not_stop_requests(self):
        hour = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
        state = WeatherRateLimitState()
        request = Mock(side_effect=[
            self._weather_response(hour, headers={}),
            self._weather_response(hour + timedelta(hours=1), headers={"X-RateLimit-Remaining": "unknown"}),
        ])

        fetch_visual_crossing_hour(
            50, 14, hour, api_key="test-key", rate_limit_state=state, get=request, sleep=Mock(),
        )
        fetch_visual_crossing_hour(
            50, 14, hour + timedelta(hours=1), api_key="test-key",
            rate_limit_state=state, get=request, sleep=Mock(),
        )

        self.assertFalse(state.is_exhausted(hour))
        self.assertEqual(request.call_count, 2)

    def test_http_429_marks_rate_limit_state(self):
        response = Mock()
        response.status_code = 429
        response.headers = {"Retry-After": "60"}
        state = WeatherRateLimitState()

        with self.assertRaises(WeatherProviderError) as raised:
            fetch_visual_crossing_hour(
                50, 14, datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
                api_key="test-key", rate_limit_state=state, get=Mock(return_value=response), sleep=Mock(),
            )

        self.assertTrue(raised.exception.stop_run)
        self.assertEqual(raised.exception.retry_after, "60")
        self.assertTrue(state.is_exhausted())

    @staticmethod
    def _weather_response(hour, headers):
        response = Mock()
        response.status_code = 200
        response.headers = headers
        response.json.return_value = {
            "days": [{"hours": [{"datetimeEpoch": int(hour.timestamp()), "temp": 12}]}],
        }
        return response


if __name__ == "__main__":
    unittest.main()
