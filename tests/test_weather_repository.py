"""Mocked weather and sync repository tests across supported SQL dialects."""

import unittest
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from kinetiqo.db.postgresql import PostgresqlRepository


class WeatherRepositoryTests(unittest.TestCase):
    def _repository(self, repository_type, database_type):
        repository = object.__new__(repository_type)
        repository.db_type = database_type
        repository.conn = MagicMock()
        repository.conn.closed = False
        cursor = MagicMock()
        repository.conn.cursor.return_value.__enter__.return_value = cursor
        repository._ensure_connected = lambda: None
        return repository, cursor

    def test_postgresql_repository_exposes_backend_dialect_for_shared_methods(self):
        repository, cursor = self._repository(PostgresqlRepository, "postgresql")
        del repository.db_type
        self.assertEqual(PostgresqlRepository.db_type, "postgresql")
        cursor.rowcount = 0
        cursor.fetchone.return_value = (None, None)
        self.assertEqual(repository.recover_expired_sync_jobs(), 0)
        repository.conn.commit.assert_called_once()

    def test_create_sync_job_uses_boolean_value_for_backend_column_type(self):
        for database_type in ("postgresql", "mysql", "firebird"):
            with self.subTest(database_type=database_type):
                repository, cursor = self._repository(PostgresqlRepository, database_type)
                repository.create_sync_job(
                    "job-id",
                    "fast",
                    "owner-id",
                    {"full_sync": False},
                )
                params = cursor.execute.call_args.args[1]
                if database_type == "firebird":
                    self.assertEqual(params[6], 0)
                else:
                    self.assertIs(params[6], False)

    def test_request_sync_job_cancel_uses_boolean_value_for_backend_column_type(self):
        for database_type in ("postgresql", "mysql", "firebird"):
            with self.subTest(database_type=database_type):
                repository, cursor = self._repository(PostgresqlRepository, database_type)
                cursor.rowcount = 1

                self.assertTrue(repository.request_sync_job_cancel("job-id", "owner-id"))

                sql, params = cursor.execute.call_args.args
                self.assertIn("cancel_requested", sql)
                self.assertEqual(params[1:], ("job-id", "owner-id"))
                if database_type == "firebird":
                    self.assertEqual(params[0], 1)
                    self.assertIn("= ?", sql)
                else:
                    self.assertIs(params[0], True)
                    self.assertIn("= %s", sql)
                repository.conn.commit.assert_called_once()

    def test_startup_interrupts_active_jobs_and_clears_lease_for_each_backend(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for database_type in ("postgresql", "mysql", "firebird"):
            with self.subTest(database_type=database_type):
                repository, cursor = self._repository(PostgresqlRepository, database_type)
                cursor.rowcount = 2

                interrupted = repository.interrupt_active_sync_jobs(now)

                self.assertEqual(interrupted, 2)
                calls = cursor.execute.call_args_list
                self.assertEqual(len(calls), 2)
                self.assertIn("sync_execution_lock", calls[0].args[0])
                self.assertEqual(calls[0].args[1], ("global",))
                job_sql, job_params = calls[1].args
                self.assertIn("status", job_sql)
                self.assertEqual(job_params[0], "interrupted")
                self.assertEqual(job_params[1], now.replace(tzinfo=None)
                                 if database_type in ("mysql", "firebird") else now)
                if database_type == "firebird":
                    self.assertEqual(job_params[2], 1)
                    self.assertIn("= ?", job_sql)
                else:
                    self.assertIs(job_params[2], True)
                    self.assertIn("= %s", job_sql)
                repository.conn.commit.assert_called_once()

    def test_quota_reservation_uses_dialect_parameters_and_commits(self):
        for database_type in ("postgresql", "mysql", "firebird"):
            with self.subTest(database_type=database_type):
                repository, cursor = self._repository(PostgresqlRepository, database_type)
                cursor.rowcount = 1
                cursor.fetchone.return_value = (4,)
                total = repository.reserve_weather_api_request(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    quota_units=1,
                    hard_cap=900,
                )
                self.assertEqual(total, 5)
                self.assertEqual(cursor.execute.call_count, 3)
                sql = cursor.execute.call_args_list[0].args[0]
                self.assertIn("weather_api_quota_lock", sql)
                self.assertEqual("?" in sql, database_type == "firebird")
                repository.conn.commit.assert_called_once()

    def test_expired_web_lease_marks_its_job_interrupted_before_reclaim(self):
        now = datetime.now(timezone.utc)
        for database_type in ("postgresql", "mysql", "firebird"):
            with self.subTest(database_type=database_type):
                repository, cursor = self._repository(PostgresqlRepository, database_type)
                cursor.rowcount = 1
                cursor.fetchone.return_value = ("stale-job", now - timedelta(minutes=10))
                acquired = repository.acquire_sync_lease(
                    "new-owner-token",
                    "new-job",
                    now,
                    now + timedelta(minutes=5),
                )
                self.assertTrue(acquired)
                calls = cursor.execute.call_args_list
                statements = [call.args[0] for call in calls]
                self.assertIn("interrupted", calls[2].args[1])
                self.assertEqual("?" in statements[-1], database_type == "firebird")
                repository.conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
