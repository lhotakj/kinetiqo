"""Mocked unit tests for the UPDATE_STRAVA integration inside SyncService.

Focuses on kinetiqo.sync.SyncService._update_strava_description(), in
particular the "stop trying for the rest of this run after a 401" behavior
(missing activity:write scope). Follows the mocked-unit-test style of
tests/test_sync_logic.py: StravaClient and create_repository are patched so
no live network/database is ever contacted.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import requests

from kinetiqo.config import UPDATE_STRAVA_MAX_ITEMS
from kinetiqo.sync import (
    SyncService,
    DESC_NOT_CONFIGURED,
    DESC_UNCHANGED,
    DESC_SKIPPED,
    DESC_UPDATED,
    DESC_FAILED,
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
        service.config.update_strava_cycling_outdoor = "Year: {{current-year}}{{new-line}}"

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


class TestDescriptionStatusSuffix(unittest.TestCase):
    """Unit tests for the brief per-activity log-line status suffix helper."""

    def test_not_configured_has_no_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_NOT_CONFIGURED), "")

    def test_unchanged_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_UNCHANGED), " | Kinetiqo description skipped")

    def test_skipped_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_SKIPPED), " | Kinetiqo description skipped")

    def test_updated_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_UPDATED), " | Kinetiqo description updated")

    def test_failed_suffix(self):
        self.assertEqual(_description_status_suffix(DESC_FAILED), " | Kinetiqo description skipped")


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
        final_event = events[-1]

        self.assertIn("Sync completed successfully", final_event)
        self.assertNotIn("warning", final_event.lower())

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
        synced_line = next(e for e in events if "Morning Ride (Ride)" in e and "[1/1]" in e)

        self.assertIn("| Kinetiqo description updated", synced_line)

    def test_existing_activity_log_line_shows_status_inline(self):
        service = self._make_service()
        activity = {
            "id": 1, "sport_type": "Ride", "name": "Morning Ride",
            "start_date": "2026-07-22T08:00:00Z",
        }
        service.db.get_synced_activity_ids.return_value = {"1"}
        service.strava.get_activities.return_value = iter([[activity]])
        service.strava.get_activity_detail.return_value = {"description": "✨ Kinetiqo: Year: 2026\n"}
        service.config.update_strava_cycling_outdoor = "Year: {{current-year}}{{new-line}}"

        events = list(service.sync(full_sync=True, trigger="test", user="tester", limit_days=0))
        updated_line = next(e for e in events if "Morning Ride (Ride)" in e and "[1/1]" in e)

        self.assertIn("| Kinetiqo description skipped", updated_line)
        service.strava.update_activity_description.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
