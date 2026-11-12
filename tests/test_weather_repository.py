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

    def test_update_activity_weather_summary_across_dialects(self):
        summary = {
            "weather_temp_min": 12.0,
            "weather_temp_max": 18.0,
            "weather_temp_avg": 15.0,
            "weather_condition": "Partially cloudy",
            "weather_condition_icon": "partly-cloudy-day",
            "weather_wind_deg": 270,
            "weather_wind_speed": 3.4,
            "weather_wind_gust_max": 9.5,
            "weather_precipitation": "Rain (1.2mm)",
        }
        from kinetiqo.db.mysql import MySQLRepository
        from kinetiqo.db.firebird import FirebirdRepository

        repo_classes = {
            "postgresql": PostgresqlRepository,
            "mysql": MySQLRepository,
            "firebird": FirebirdRepository,
        }
        for database_type, repo_class in repo_classes.items():
            with self.subTest(database_type=database_type):
                repository, cursor = self._repository(repo_class, database_type)
                repository.update_activity_weather_summary("12345", summary)
                cursor.execute.assert_called_once()
                sql, params = cursor.execute.call_args.args
                self.assertIn("weather_temp_min", sql)
                self.assertIn("weather_wind_gust_max", sql)
                self.assertIn("weather_precipitation", sql)
                self.assertEqual(params[-1], 12345)
                if database_type == "firebird":
                    self.assertIn("?", sql)
                else:
                    self.assertIn("%s", sql)
                repository.conn.commit.assert_called_once()

    def test_backfill_weather_summary_processes_completed_rows(self):
        import json
        repository, cursor = self._repository(PostgresqlRepository, "postgresql")
        cursor.fetchall.return_value = [
            (
                1001,
                json.dumps({
                    "status": "complete",
                    "samples": [
                        {
                            "temperature_c": 17.0,
                            "conditions": "Clear",
                            "wind_direction_deg": 180,
                            "wind_speed_ms": 2.5,
                            "interval_seconds": 3600,
                            "precipitation_mm": 0,
                        }
                    ],
                }),
            )
        ]
        repository.update_activity_weather_summary = MagicMock()
        count = repository.backfill_weather_summary(batch_size=10)
        self.assertEqual(count, 1)
        repository.update_activity_weather_summary.assert_called_once()
        args = repository.update_activity_weather_summary.call_args.args
        self.assertEqual(args[0], 1001)
        self.assertEqual(args[1]["weather_condition"], "Clear")
        self.assertEqual(args[1]["weather_temp_avg"], 17.0)

    def test_load_weather_cache_populates_spatial_dictionary(self):
        import json
        repository, cursor = self._repository(PostgresqlRepository, "postgresql")
        cursor.fetchall.side_effect = [
            [
                (
                    2001,
                    json.dumps({
                        "status": "complete",
                        "samples": [
                            {
                                "time_utc": "2026-10-15T16:00:00+00:00",
                                "latitude": 50.045,
                                "longitude": 14.322,
                                "temperature_c": 12.9,
                            }
                        ],
                    }),
                )
            ]
        ]
        cache = repository.load_weather_cache(limit=50)
        self.assertIn(("50.04500,14.32200", "2026-10-15"), cache)
        epoch = int(datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc).timestamp())
        self.assertIn(epoch, cache[("50.04500,14.32200", "2026-10-15")])
        self.assertEqual(cache[("50.04500,14.32200", "2026-10-15")][epoch]["temperature_c"], 12.9)

    def test_search_activities_weather_filters_and_wind_gust_sort_across_dialects(self):
        from kinetiqo.db.mysql import MySQLRepository
        from kinetiqo.db.firebird import FirebirdRepository

        repo_classes = {
            "postgresql": PostgresqlRepository,
            "mysql": MySQLRepository,
            "firebird": FirebirdRepository,
        }
        for database_type, repo_class in repo_classes.items():
            with self.subTest(database_type=database_type):
                repository, cursor = self._repository(repo_class, database_type)
                cursor.fetchall.return_value = []
                cursor.description = [("activity_id",), ("name",), ("start_date",)]
                filters = {
                    "weather_condition": "rain",
                    "min_wind_gust_kmh": 40.0,
                    "min_temp_c": 12.0,
                    "max_temp_c": 24.0,
                    "has_weather": True,
                    "sort_by": "wind_gust",
                    "sort_order": "desc",
                }
                repository.search_activities(athlete_id=1, filters=filters, limit=10)
                cursor.execute.assert_called_once()
                sql = cursor.execute.call_args.args[0]
                self.assertIn("weather_wind_gust_max", sql)
                self.assertIn("weather_condition", sql)
                self.assertIn("weather_temp_avg", sql)
                self.assertIn("ORDER BY", sql)


if __name__ == "__main__":
    unittest.main()
