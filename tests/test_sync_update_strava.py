"""Mocked unit tests for the UPDATE_STRAVA integration inside SyncService.

Focuses on kinetiqo.sync.SyncService._update_strava_description(), in
particular the "stop trying for the rest of this run after a 401" behavior
(missing activity:write scope). Follows the mocked-unit-test style of
tests/test_sync_logic.py: StravaClient and create_repository are patched so
no live network/database is ever contacted.
"""

import unittest
import os
import tempfile
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import requests

from kinetiqo.config import UPDATE_STRAVA_MAX_ITEMS
from kinetiqo.sync import (
    SyncService,
    STOP_SIGNAL_FILE,
    DESC_NOT_CONFIGURED,
    DESC_UNCHANGED,
    DESC_SKIPPED,
    DESC_UPDATED,
    DESC_FAILED,
    DESC_DEFERRED,
    _description_status_suffix,
)
from kinetiqo.strava_description import DescriptionContext


def _make_config(**overrides):
    config = MagicMock()
    config.update_strava_cycling_indoor = ""
    config.update_strava_cycling_outdoor = "{{current-year}}"
    config.update_strava_running_indoor = ""
    config.update_strava_running_outdoor = ""
    config.update_strava_walking = ""
    config.update_strava_swimming = ""
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _unauthorized_error():
    response = MagicMock()
    response.status_code = 401
    return requests.exceptions.HTTPError(response=response)


class TestSyncServiceUpdateStravaDescription(unittest.TestCase):
    """Unit tests for SyncService._update_strava_description()."""

    @patch("kinetiqo.sync.create_repository")
    @patch("kinetiqo.sync.StravaClient")
    def _make_service(self, mock_strava_client, mock_create_repo):
        service = SyncService(_make_config())
        service.strava = mock_strava_client.return_value
        service.db = mock_create_repo.return_value
        return service

    def test_401_disables_further_updates_for_this_run(self):
        service = self._make_service()
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.update_activity_description.side_effect = _unauthorized_error()

        ctx = DescriptionContext(config=service.config, repo=MagicMock())
        activity = {"id": 1, "sport_type": "Ride", "start_date": "2026-07-22T08:00:00Z"}

        # First call: hits the 401, sets the "unauthorized" flag, doesn't raise,
        # and returns a "failed" status + a warning message describing the
        # missing scope so the caller can surface it in the sync UI.
        status, message = service._update_strava_description(ctx, activity)
        self.assertTrue(service._update_strava_unauthorized)
        service.strava.update_activity_description.assert_called_once()
        self.assertEqual(status, DESC_FAILED)
        self.assertIsNotNone(message)
        self.assertIn("activity:write", message)

        # Second call (any activity): flag is set, so no further API calls at
        # all, status is "skipped" and no (duplicate) warning message.
        service.strava.get_activity_detail.reset_mock()
        service.strava.update_activity_description.reset_mock()
        activity2 = {"id": 2, "sport_type": "Ride", "start_date": "2026-07-22T09:00:00Z"}
        status2, message2 = service._update_strava_description(ctx, activity2)
        service.strava.get_activity_detail.assert_not_called()
        service.strava.update_activity_description.assert_not_called()
        self.assertEqual(status2, DESC_SKIPPED)
        self.assertIsNone(message2)

    def test_non_401_error_does_not_disable_future_updates(self):
        service = self._make_service()
        service.strava.get_activity_detail.return_value = {"description": ""}
        response = MagicMock()
        response.status_code = 503
        service.strava.update_activity_description.side_effect = requests.exceptions.HTTPError(response=response)

        ctx = DescriptionContext(config=service.config, repo=MagicMock())
        activity = {"id": 1, "sport_type": "Ride", "start_date": "2026-07-22T08:00:00Z"}

        status, message = service._update_strava_description(ctx, activity)
        self.assertFalse(service._update_strava_unauthorized)
        self.assertEqual(status, DESC_FAILED)
        self.assertIsNotNone(message)
        self.assertIn("failed to update description for activity 1", message)

    def test_skips_activity_whose_sport_type_has_no_template(self):
        service = self._make_service()
        ctx = DescriptionContext(config=service.config, repo=MagicMock())
        activity = {"id": 1, "sport_type": "WeightTraining", "start_date": "2026-07-22T08:00:00Z"}

        status, message = service._update_strava_description(ctx, activity)
        service.strava.get_activity_detail.assert_not_called()
        service.strava.update_activity_description.assert_not_called()
        self.assertEqual(status, DESC_NOT_CONFIGURED)
        self.assertIsNone(message)

    def test_unchanged_description_returns_unchanged_status(self):
        service = self._make_service()
        service.strava.get_activity_detail.return_value = {"description": "✨ Kinetiqo: Year: 2026\n"}
        ctx = DescriptionContext(config=service.config, repo=MagicMock())
        activity = {"id": 1, "sport_type": "Ride", "start_date": "2026-07-22T08:00:00Z"}
        service.config.update_strava_cycling_outdoor = "Year: {{current-year}}"

        status, message = service._update_strava_description(ctx, activity)
        service.strava.update_activity_description.assert_not_called()
        self.assertEqual(status, DESC_UNCHANGED)
        self.assertIsNone(message)

    def test_successful_update_returns_updated_status(self):
        service = self._make_service()
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.update_activity_description.return_value = None
        ctx = DescriptionContext(config=service.config, repo=MagicMock())
        activity = {"id": 1, "sport_type": "Ride", "start_date": "2026-07-22T08:00:00Z"}

        status, message = service._update_strava_description(ctx, activity)
        service.strava.update_activity_description.assert_called_once()
        self.assertEqual(status, DESC_UPDATED)
        self.assertIsNone(message)

    def test_missing_weather_defers_description_update(self):
        service = self._make_service()
        service.config.update_strava_walking = "{{weather-basic}}"
        service.strava.get_activity_detail.return_value = {"description": "✨ Kinetiqo:\n"}
        service.db.get_activity_weather.return_value = None
        ctx = DescriptionContext(config=service.config, repo=service.db)
        activity = {"id": 1, "sport_type": "Hike", "start_date": "2026-07-22T08:00:00Z"}

        status, message = service._update_strava_description(ctx, activity)

        self.assertEqual(status, DESC_DEFERRED)
        self.assertIsNone(message)
        service.strava.update_activity_description.assert_not_called()

    def test_complete_stored_weather_replaces_legacy_prefixed_line(self):
        service = self._make_service()
        service.config.update_strava_walking = "{{weather-basic}}"
        service.strava.get_activity_detail.return_value = {
            "description": "✨ Kinetiqo:\nRecovery | 1h56min @ 77bpm\n\nvia restortrain.com",
        }
        service.db.get_activity_weather.return_value = {
            "weather_json": json.dumps({
                "status": "complete",
                "activity": {
                    "start_utc": "2026-10-29T11:28:10+00:00",
                    "end_utc": "2026-10-29T13:24:03+00:00",
                    "sport_type": "Hike",
                },
                "samples": [
                    {
                        "time_utc": "2026-10-29T12:00:00+00:00",
                        "interval_seconds": 3600,
                        "temperature_c": 10.2,
                        "apparent_temperature_c": 10.2,
                        "precipitation_mm": 0.0,
                        "snowfall_cm": 0.0,
                        "conditions": "Partially cloudy",
                        "wind_direction_deg": 325.0,
                        "wind_speed_ms": 2.9166666666666665,
                        "wind_gusts_ms": 4.111111111111112,
                        "headwind_component_ms": 2.037306541545804,
                    },
                    {
                        "time_utc": "2026-10-29T13:00:00+00:00",
                        "interval_seconds": 1443,
                        "temperature_c": 11.2,
                        "apparent_temperature_c": 11.2,
                        "precipitation_mm": 0.0,
                        "snowfall_cm": 0.0,
                        "conditions": "Partially cloudy",
                        "wind_direction_deg": 328.0,
                        "wind_speed_ms": 3.611111111111111,
                        "wind_gusts_ms": 3.888888888888889,
                        "headwind_component_ms": 2.5243519683850755,
                    },
                ],
            }),
        }
        ctx = DescriptionContext(config=service.config, repo=service.db)
        activity = {
            "id": 20780336364,
            "sport_type": "Hike",
            "start_date": "2026-10-29T11:28:10Z",
        }

        status, message = service._update_strava_description(ctx, activity)

        self.assertEqual(status, DESC_UPDATED)
        self.assertIsNone(message)
        service.strava.update_activity_description.assert_called_once()
        self.assertEqual(
            service.strava.update_activity_description.call_args.args,
            (
                20780336364,
                "✨ Kinetiqo: Partially cloudy, around 10°C, feels like 10°C, "
                "NW wind 3.1 m/s, up to 4.1 m/s.\n"
                "Recovery | 1h56min @ 77bpm\n\nvia restortrain.com",
            ),
        )


class TestDescriptionStatusSuffix(unittest.TestCase):
    """Unit tests for the brief per-activity log-line status suffix helper."""

    def test_not_configured_has_no_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_NOT_CONFIGURED), "")

    def test_unchanged_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_UNCHANGED), " | Skipping Strava description update")

    def test_skipped_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_SKIPPED), " | Skipping Strava description update")

    def test_updated_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_UPDATED), " | Strava description updated")

    def test_failed_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_FAILED), " | Skipping Strava description update")

    def test_deferred_suffix(self):
        self.assertEqual(
            _description_status_suffix(DESC_DEFERRED),
            " | Strava description deferred: weather unavailable",
        )


class TestSyncSurfacesWarningsInUi(unittest.TestCase):
    """End-to-end tests confirming SyncService.sync() surfaces UPDATE_STRAVA (and
    other) warnings/errors in the SSE stream consumed by the sync UI, instead of
    only logging them server-side.
    """

    @patch("kinetiqo.sync.create_repository")
    @patch("kinetiqo.sync.StravaClient")
    def _make_service(self, mock_strava_client, mock_create_repo):
        service = SyncService(_make_config())
        service.strava = mock_strava_client.return_value
        service.db = mock_create_repo.return_value
        service.db.get_synced_activity_ids.return_value = set()
        service.db.get_synced_activity_ids_since.return_value = set()
        return service

    def test_missing_scope_warning_is_shown_in_final_sync_summary(self):
        service = self._make_service()
        activity = {
            "id": 1, "sport_type": "Ride", "name": "Morning Ride",
            "start_date": "2026-07-22T08:00:00Z",
        }
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.update_activity_description.side_effect = _unauthorized_error()

        events = list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0))
        final_event = events[-1]

        self.assertIn("warning", final_event.lower())
        self.assertIn("activity:write", final_event)
        self.assertIn("1 warning", final_event)

    def test_no_warnings_shown_when_sync_is_clean(self):
        service = self._make_service()
        activity = {
            "id": 1, "sport_type": "Ride", "name": "Morning Ride",
            "start_date": "2026-07-22T08:00:00Z",
        }
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.update_activity_description.return_value = None

        events = list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0))
        stop_button_event = events[0]
        first_log_event = events[1]
        final_event = events[-1]

        self.assertIn('data-sync-stop-button="true"', stop_button_event)
        self.assertIn('kinetiqoRequestSyncStop', stop_button_event)
        self.assertIn('background-color: #dc2626', stop_button_event)
        self.assertIn("Sync in progress...", first_log_event)
        self.assertIn("/static/img/kinetiqo-loading-32x32.webp", first_log_event)
        self.assertIn("sync-progress-text", first_log_event)
        self.assertLess(
            first_log_event.index("/static/img/kinetiqo-loading-32x32.webp"),
            first_log_event.index("Sync in progress..."),
        )
        self.assertIn("Sync completed successfully", final_event)
        self.assertIn('style="height: 500px;"', final_event)
        self.assertIn('<p class="block truncate">', final_event)
        self.assertNotIn('<div class="truncate">', final_event)
        self.assertLess(
            final_event.index("Starting full sync"),
            final_event.index("Found 0 already synced activities"),
        )
        self.assertNotIn("warning", final_event.lower())

    def test_stop_signal_after_fetch_progress_aborts_sync(self):
        service = self._make_service()
        activity = {
            "id": 1, "sport_type": "Ride", "name": "Morning Ride",
            "start_date": "2026-07-22T08:00:00Z",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            stop_signal = os.path.join(tmpdir, os.path.basename(STOP_SIGNAL_FILE))

            def progress_then_stop(_activities, after=None):
                with open(stop_signal, "w", encoding="utf-8") as fh:
                    fh.write("stop")
                yield "Fetched first Strava page"
                yield [activity]

            service.strava.get_activities.side_effect = progress_then_stop
            with patch("kinetiqo.sync.STOP_SIGNAL_FILE", stop_signal):
                events = list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0))

        joined = "".join(events)
        self.assertIn("Fetched first Strava page", joined)
        self.assertIn("Stop signal received during fetch. Aborting...", joined)
        self.assertIn("Sync stopped by user.", joined)
        self.assertNotIn("Morning Ride (Ride)", joined)

    def test_new_activity_log_line_shows_updated_status_inline(self):
        service = self._make_service()
        activity = {
            "id": 1, "sport_type": "Ride", "name": "Morning Ride",
            "start_date": "2026-07-22T08:00:00Z",
        }
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.update_activity_description.return_value = None

        events = list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0))
        synced_line = next(
            event for event in events
            if "[1/1] (100%) Morning Ride (Ride)" in event
        )

        self.assertIn("| Strava description updated", synced_line)

    def test_existing_activity_log_line_shows_status_inline(self):
        service = self._make_service()
        activity = {
            "id": 1, "sport_type": "Ride", "name": "Morning Ride",
            "start_date": "2026-07-22T08:00:00Z",
        }
        service.db.get_synced_activity_ids.return_value = {"1"}
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_activity_detail.return_value = {"description": "✨ Kinetiqo: Year: 2026\n"}
        service.config.update_strava_cycling_outdoor = "Year: {{current-year}}"

        events = list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0))
        updated_line = next(
            event for event in events
            if "[1/1] (100%) Morning Ride (Ride)" in event
        )

        self.assertIn("| Skipping Strava description update", updated_line)
        service.strava.update_activity_description.assert_not_called()

    @patch("kinetiqo.sync.build_activity_weather")
    def test_weather_enabled_sync_persists_weather_before_updating_description(self, mock_build_weather):
        service = self._make_service()
        activity = {
            "id": 1,
            "sport_type": "Hike",
            "name": "Morning Hike",
            "start_date": "2026-07-22T08:00:00Z",
        }
        weather_payload = {
            "status": "complete",
            "activity": {"sport_type": "Hike"},
            "samples": [{
                "interval_seconds": 3600,
                "conditions": "Clear",
                "temperature_c": 18,
                "apparent_temperature_c": 18,
                "precipitation_mm": 0,
                "snowfall_cm": 0,
                "precipitation_types": [],
                "wind_speed_ms": 1,
                "wind_direction_deg": 90,
                "wind_gusts_ms": 1,
                "headwind_component_ms": 0,
            }],
        }
        persisted_weather = {}
        operation_order = []

        service.config.update_strava_cycling_outdoor = ""
        service.config.update_strava_walking = "{{weather-basic}}"
        service.db.get_profile.return_value = {"enable_weather_data": False}
        service.db.get_synced_activity_ids.return_value = {"1"}
        service.db.get_latest_activity_time.return_value = None
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}
        service.db.get_activity_stream_window.return_value = [
            {"ts": 1, "lat": 50.0, "lng": 14.0, "distance": 0.0},
        ]
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.get_athlete.return_value = None
        mock_build_weather.return_value = weather_payload

        def persist_weather(activity_id, payload):
            operation_order.append(("weather", activity_id))
            persisted_weather[activity_id] = {"weather_json": payload}

        def get_weather(activity_id):
            return persisted_weather.get(activity_id)

        def update_description(activity_id, description):
            operation_order.append(("description", activity_id))
            self.assertIn("Clear", description)

        service.db.upsert_activity_weather.side_effect = persist_weather
        service.db.get_activity_weather.side_effect = get_weather
        service.strava.update_activity_description.side_effect = update_description

        with patch("kinetiqo.sync.sync_update_strava_from_env"):
            events = list(service.sync(
                full_sync=False,
                trigger="test",
                user="tester",
                limit_days=0,
                update_weather=True,
            ))

        self.assertEqual(operation_order, [("weather", 1), ("description", 1)])
        self.assertIn(
            "[1/1] (100%) Morning Hike (Hike) | Weather updated | Strava description updated",
            "".join(events),
        )

    @patch("kinetiqo.sync.build_activity_weather")
    def test_weather_placeholder_does_not_fetch_weather_when_weather_is_disabled(self, mock_build_weather):
        service = self._make_service()
        activity = {
            "id": 1,
            "sport_type": "Hike",
            "name": "Morning Hike",
            "start_date": "2026-07-22T08:00:00Z",
        }
        service.config.update_strava_cycling_outdoor = ""
        service.config.update_strava_walking = "{{weather-basic}}"
        service.db.get_profile.return_value = {"enable_weather_data": False}
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.get_athlete.return_value = None
        service.db.get_activity_weather.return_value = None

        with patch("kinetiqo.sync.sync_update_strava_from_env"):
            events = list(service.sync(
                full_sync=False,
                trigger="test",
                user="tester",
                limit_days=0,
                update_weather=False,
            ))

        mock_build_weather.assert_not_called()
        service.strava.update_activity_description.assert_not_called()
        self.assertIn(
            "[1/1] (100%) Morning Hike (Hike) | Strava description deferred: weather unavailable",
            "".join(events),
        )

    def test_sync_limits_description_updates_to_latest_eligible_activities(self):
        service = self._make_service()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        activities = []
        for i in range(35):
            activities.append({
                "id": i + 1,
                "sport_type": "Ride",
                "name": f"Ride {i + 1}",
                "start_date": (base + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        service.strava.get_activities.return_value = iter([activities])
        service.strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}
        service.strava.get_activity_detail.return_value = {"description": ""}
        service.strava.update_activity_description.return_value = None

        list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0))

        self.assertEqual(service.strava.update_activity_description.call_count, UPDATE_STRAVA_MAX_ITEMS)
        updated_ids = {call.args[0] for call in service.strava.update_activity_description.call_args_list}
        self.assertEqual(updated_ids, set(range(6, 36)))

    def test_update_strava_disabled_skips_description_and_omits_suffix(self):
        service = self._make_service()
        activity = {
            "id": 1, "sport_type": "Ride", "name": "Morning Ride",
            "start_date": "2026-07-22T08:00:00Z",
        }
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_streams.return_value = {"time": {"data": [1, 2, 3]}}

        events = list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0, update_strava=False))
        synced_line = next(e for e in events if "Morning Ride (Ride)" in e and "[1/1]" in e)

        self.assertNotIn("Kinetiqo description", synced_line)
        service.strava.get_activity_detail.assert_not_called()
        service.strava.update_activity_description.assert_not_called()


class TestCliUpdateStravaFlag(unittest.TestCase):
    """Tests for CLI --update-strava / -U option parsing."""

    def test_parse_bool_option(self):
        from kinetiqo.cli import _parse_bool_option
        self.assertTrue(_parse_bool_option(True))
        self.assertTrue(_parse_bool_option("true"))
        self.assertTrue(_parse_bool_option("TRUE"))
        self.assertTrue(_parse_bool_option("1"))
        self.assertTrue(_parse_bool_option("yes"))

        self.assertFalse(_parse_bool_option(False))
        self.assertFalse(_parse_bool_option("false"))
        self.assertFalse(_parse_bool_option("FALSE"))
        self.assertFalse(_parse_bool_option("0"))
        self.assertFalse(_parse_bool_option("no"))


if __name__ == "__main__":
    unittest.main()
