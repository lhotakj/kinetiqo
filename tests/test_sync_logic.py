import unittest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from kinetiqo.cli import cli

# --- Mock Data ---
MOCK_ACTIVITIES_PAGE_1 = [
    {"id": 1001, "name": "Recent Ride", "sport_type": "Ride", "start_date": "2024-03-10T08:00:00Z", "athlete": {"id": 123}},
    {"id": 1002, "name": "Recent Run", "sport_type": "Run", "start_date": "2024-03-11T12:00:00Z", "athlete": {"id": 123}},
]
MOCK_ACTIVITIES_OLD = [
    {"id": 901, "name": "Very Old Ride", "sport_type": "Ride", "start_date": "2023-01-01T10:00:00Z", "athlete": {"id": 123}},
]
MOCK_STREAMS = {"time": {"data": [1, 2, 3]}, "watts": {"data": [100, 110, 120]}}
DB_TYPES = ['postgresql', 'mysql', 'firebird']

class TestSyncMatrix(unittest.TestCase):
    """A matrix of unit tests for sync logic against mocked databases."""

    def setUp(self):
        self.runner = CliRunner()

    @patch('kinetiqo.sync.StravaClient')
    @patch('kinetiqo.cli.create_repository')
    @patch('kinetiqo.sync.create_repository')
    def test_full_sync_adds_new_activities(self, mock_sync_repo, mock_cli_repo, mock_strava_client):
        """Full sync should add all activities to an empty database."""
        for db_type in DB_TYPES:
            with self.subTest(db_type=db_type):
                # Arrange
                mock_repo = MagicMock()
                mock_repo.get_synced_activity_ids.return_value = set()
                mock_cli_repo.return_value = mock_sync_repo.return_value = mock_repo

                mock_strava_instance = mock_strava_client.return_value
                mock_strava_instance.get_activities.return_value = iter([MOCK_ACTIVITIES_PAGE_1])
                mock_strava_instance.get_streams.return_value = MOCK_STREAMS

                # Act
                result = self.runner.invoke(cli, ['--database', db_type, 'sync', '--full-sync'], catch_exceptions=False)

                # Assert
                self.assertEqual(result.exit_code, 0)
                self.assertEqual(mock_repo.write_activity.call_count, 2)
                mock_repo.delete_activities.assert_not_called()

    @patch('kinetiqo.sync.StravaClient')
    @patch('kinetiqo.cli.create_repository')
    @patch('kinetiqo.sync.create_repository')
    def test_full_sync_removes_deleted_activities(self, mock_sync_repo, mock_cli_repo, mock_strava_client):
        """Full sync should delete activities from DB that are not on Strava."""
        for db_type in DB_TYPES:
            with self.subTest(db_type=db_type):
                # Arrange
                mock_repo = MagicMock()
                mock_repo.get_synced_activity_ids.return_value = {'1001', '9999'}  # DB has a stale activity
                mock_cli_repo.return_value = mock_sync_repo.return_value = mock_repo

                mock_strava_instance = mock_strava_client.return_value
                mock_strava_instance.get_activities.return_value = iter([MOCK_ACTIVITIES_PAGE_1]) # Strava only has 1001 and 1002
                mock_strava_instance.get_streams.return_value = MOCK_STREAMS

                # Act
                result = self.runner.invoke(cli, ['--database', db_type, 'sync', '--full-sync'], catch_exceptions=False)

                # Assert
                self.assertEqual(result.exit_code, 0)
                # 1 existing (1001 metadata update) + 1 new (1002 full sync) = 2 writes
                self.assertEqual(mock_repo.write_activity.call_count, 2)
                # Only 1 new activity fetches streams
                self.assertEqual(mock_strava_instance.get_streams.call_count, 1)
                mock_repo.delete_activities.assert_called_once_with(['9999'])

    @patch('kinetiqo.sync.StravaClient')
    @patch('kinetiqo.cli.create_repository')
    @patch('kinetiqo.sync.create_repository')
    def test_fast_sync_deletes_stale_activities_in_scope(self, mock_sync_repo, mock_cli_repo, mock_strava_client):
        """Fast sync should delete activities that are in the fetched time window but missing from Strava."""
        for db_type in DB_TYPES:
            with self.subTest(db_type=db_type):
                # Arrange
                mock_repo = MagicMock()
                mock_repo.get_synced_activity_ids.return_value = {'1001', '9999'}
                mock_repo.get_latest_activity_time.return_value = 1700000000 # A time before our mock activities
                # 9999 falls inside the scoped window — it should be deleted
                mock_repo.get_synced_activity_ids_since.return_value = {'1001', '9999'}
                mock_cli_repo.return_value = mock_sync_repo.return_value = mock_repo

                mock_strava_instance = mock_strava_client.return_value
                mock_strava_instance.get_activities.return_value = iter([MOCK_ACTIVITIES_PAGE_1])
                mock_strava_instance.get_streams.return_value = MOCK_STREAMS

                # Act
                result = self.runner.invoke(cli, ['--database', db_type, 'sync', '--fast-sync'], catch_exceptions=False)

                # Assert
                self.assertEqual(result.exit_code, 0)
                self.assertEqual(mock_repo.write_activity.call_count, 2)
                mock_repo.delete_activities.assert_called_once_with(['9999'])

    @patch('kinetiqo.sync.StravaClient')
    @patch('kinetiqo.cli.create_repository')
    @patch('kinetiqo.sync.create_repository')
    def test_full_sync_with_period_limit_does_not_delete_outside_scope(self, mock_sync_repo, mock_cli_repo, mock_strava_client):
        """Full sync with a --period limit should NOT delete activities outside that period."""
        for db_type in DB_TYPES:
            with self.subTest(db_type=db_type):
                # Arrange
                mock_repo = MagicMock()
                mock_repo.get_synced_activity_ids.return_value = {'901'} # A very old activity
                # 901 is outside the scoped window — get_synced_activity_ids_since returns empty
                mock_repo.get_synced_activity_ids_since.return_value = set()
                mock_cli_repo.return_value = mock_sync_repo.return_value = mock_repo

                mock_strava_instance = mock_strava_client.return_value
                # Strava client will return recent activities + the old one
                mock_strava_instance.get_activities.return_value = iter([MOCK_ACTIVITIES_PAGE_1 + MOCK_ACTIVITIES_OLD])
                mock_strava_instance.get_streams.return_value = MOCK_STREAMS

                # Act: Run a full sync limited to the last 7 days
                result = self.runner.invoke(cli, ['--database', db_type, 'sync', '--full-sync', '--period', '7d'], catch_exceptions=False)

                # Assert
                self.assertEqual(result.exit_code, 0)
                # 1 existing (901 metadata update) + 2 new (1001, 1002 full sync) = 3 writes
                self.assertEqual(mock_repo.write_activity.call_count, 3)
                mock_repo.delete_activities.assert_not_called() # Should not delete the old activity 901

    @patch('kinetiqo.sync.StravaClient')
    @patch('kinetiqo.cli.create_repository')
    @patch('kinetiqo.sync.create_repository')
    def test_sync_with_no_new_activities(self, mock_sync_repo, mock_cli_repo, mock_strava_client):
        """Sync should do nothing if no new activities are found."""
        for db_type in DB_TYPES:
            with self.subTest(db_type=db_type):
                # Arrange
                mock_repo = MagicMock()
                mock_repo.get_synced_activity_ids.return_value = {'1001', '1002'} # DB is up to date
                mock_cli_repo.return_value = mock_sync_repo.return_value = mock_repo

                mock_strava_instance = mock_strava_client.return_value
                mock_strava_instance.get_activities.return_value = iter([MOCK_ACTIVITIES_PAGE_1])
                mock_strava_instance.get_streams.return_value = MOCK_STREAMS

                # Act
                result = self.runner.invoke(cli, ['--database', db_type, 'sync', '--full-sync'], catch_exceptions=False)

                # Assert
                self.assertEqual(result.exit_code, 0)
                # Both activities are existing — metadata updated, no streams fetched
                self.assertEqual(mock_repo.write_activity.call_count, 2)
                mock_strava_instance.get_streams.assert_not_called()
                mock_repo.delete_activities.assert_not_called()
