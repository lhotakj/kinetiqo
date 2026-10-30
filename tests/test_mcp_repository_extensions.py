"""Unit tests for MCP repository layer extensions across PostgreSQL, MySQL, and Firebird."""

import json
import time
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from kinetiqo.db.pagination import encode_cursor, decode_cursor
from kinetiqo.db.postgresql import PostgresqlRepository
from kinetiqo.db.mysql import MySQLRepository
from kinetiqo.db.firebird import FirebirdRepository


class TestPaginationCursor(unittest.TestCase):
    """Test URL-safe base64 opaque cursor round-tripping."""

    def test_encode_and_decode_cursor(self):
        cursor = encode_cursor(12345.6, "2026-05-15T10:00:00Z", 987654321)
        self.assertIsInstance(cursor, str)

        decoded = decode_cursor(cursor)
        self.assertIsNotNone(decoded)
        val, date_str, act_id = decoded
        self.assertEqual(val, 12345.6)
        self.assertEqual(date_str, "2026-05-15T10:00:00Z")
        self.assertEqual(act_id, 987654321)

    def test_decode_invalid_cursor(self):
        self.assertIsNone(decode_cursor(None))
        self.assertIsNone(decode_cursor(""))
        self.assertIsNone(decode_cursor("not-base64!"))
        self.assertIsNone(decode_cursor("e30="))  # {} without required keys


class TestPostgresqlMcpExtensions(unittest.TestCase):
    """Test PostgreSQL implementation of search_activities, get_stream_coverage, get_activity_stream_window."""

    def setUp(self):
        self.repo = object.__new__(PostgresqlRepository)
        self.repo.config = types.SimpleNamespace(
            postgresql_database="db",
            postgresql_host="localhost",
            postgresql_port=5432,
            postgresql_user="usr",
            postgresql_password="pwd",
            postgresql_ssl_mode="disable",
        )
        self.mock_conn = MagicMock()
        self.mock_conn.closed = False
        self.mock_cur = MagicMock()
        self.repo.conn = self.mock_conn
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cur

    def test_search_activities_with_bounds_and_limit(self):
        mock_rows = [
            {
                "activity_id": 101,
                "name": "Morning Ride",
                "sport": "Ride",
                "athlete_id": 1,
                "distance": 45000.0,
                "moving_time": 5400,
                "elapsed_time": 5600,
                "total_elevation_gain": 450.0,
                "start_date": datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc),
                "average_speed": 8.33,
                "max_speed": 15.0,
                "average_heartrate": 145,
                "max_heartrate": 175,
                "average_cadence": 88.0,
                "average_watts": 220.0,
                "max_watts": 650.0,
                "weighted_average_watts": 235.0,
                "device_watts": True,
                "calories": 1100.0,
                "kilojoules": 1050.0,
                "achievement_count": 5,
                "pr_count": 2,
                "suffer_score": 65,
                "average_temp": 18.0,
                "gear_id": "b1",
                "has_heartrate": True,
                "workout_type": 10,
                "trophies": json.dumps({"1": 1, "2": 0}),
            },
            {
                "activity_id": 100,
                "name": "Evening Commute",
                "sport": "Ride",
                "athlete_id": 1,
                "distance": 20000.0,
                "moving_time": 2400,
                "elapsed_time": 2500,
                "total_elevation_gain": 120.0,
                "start_date": datetime(2026, 4, 30, 17, 0, tzinfo=timezone.utc),
                "average_speed": 8.33,
                "max_speed": 12.0,
                "average_heartrate": 130,
                "max_heartrate": 150,
                "average_cadence": 85.0,
                "average_watts": 180.0,
                "max_watts": 450.0,
                "weighted_average_watts": 190.0,
                "device_watts": True,
                "calories": 450.0,
                "kilojoules": 420.0,
                "achievement_count": 1,
                "pr_count": 0,
                "suffer_score": 25,
                "average_temp": 20.0,
                "gear_id": "b1",
                "has_heartrate": True,
                "workout_type": 10,
                "trophies": None,
            },
        ]
        self.mock_cur.fetchall.return_value = mock_rows

        activities, next_cursor, has_more = self.repo.search_activities(
            athlete_id=1,
            filters={
                "sport_types": ["Ride"],
                "min_distance_km": 10.0,
                "max_distance_km": 100.0,
                "keyword": "Ride",
                "sort_by": "distance",
                "sort_order": "desc",
            },
            limit=1,
        )

        self.assertEqual(len(activities), 1)
        self.assertTrue(has_more)
        self.assertIsNotNone(next_cursor)
        self.assertEqual(activities[0]["activity_id"], 101)
        self.assertEqual(activities[0]["trophies"], {"1": 1, "2": 0})

        # Verify SQL execution parameters used %s
        sql, params = self.mock_cur.execute.call_args[0]
        self.assertIn("SELECT activity_id", sql)
        self.assertIn("athlete_id = %s", sql)
        self.assertIn("distance >= %s", sql)
        self.assertIn("distance <= %s", sql)
        self.assertIn("name ILIKE %s", sql)
        self.assertIn("CAST(activity_id AS TEXT) LIKE %s", sql)
        self.assertIn("ORDER BY distance DESC", sql)
        self.assertIn(10000.0, params)
        self.assertIn(100000.0, params)

    def test_search_activities_with_query_filter_and_meters(self):
        self.mock_cur.fetchall.return_value = []
        self.repo.search_activities(
            athlete_id=1,
            filters={
                "query": "Jonas",
                "min_distance": 5000.0,
                "max_distance": 25000.0,
                "min_elevation": 50.0,
            },
            limit=20,
        )
        sql, params = self.mock_cur.execute.call_args[0]
        self.assertIn("name ILIKE %s", sql)
        self.assertIn("CAST(activity_id AS TEXT) LIKE %s", sql)
        self.assertIn("%Jonas%", params)
        self.assertEqual(params.count("%Jonas%"), 2)
        self.assertIn("distance >= %s", sql)
        self.assertIn(5000.0, params)
        self.assertIn("total_elevation_gain >= %s", sql)
        self.assertIn(50.0, params)

    def test_get_stream_coverage(self):
        self.mock_cur.fetchone.return_value = {
            "total_points": 3600,
            "first_ts": datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc),
            "last_ts": datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
            "watts_count": 3580,
            "heartrate_count": 3600,
            "cadence_count": 3550,
            "altitude_count": 3600,
            "latlng_count": 3600,
            "speed_count": 3600,
            "temp_count": 0,
        }

        coverage = self.repo.get_stream_coverage(101)
        self.assertEqual(coverage["total_points"], 3600)
        self.assertTrue(coverage["channels"]["watts"]["present"])
        self.assertEqual(coverage["channels"]["watts"]["count"], 3580)
        self.assertFalse(coverage["channels"]["temp"]["present"])
        self.assertEqual(coverage["channels"]["temp"]["count"], 0)

    def test_get_activity_stream_window(self):
        self.mock_cur.fetchall.return_value = [
            {"ts": datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc), "watts": 200.0, "heartrate": 140},
            {"ts": datetime(2026, 5, 1, 8, 0, 1, tzinfo=timezone.utc), "watts": 210.0, "heartrate": 142},
        ]

        rows = self.repo.get_activity_stream_window(
            activity_id=101,
            columns=["watts", "heartrate"],
            start_ts=1777622400,
            end_ts=1777622460,
            max_rows=100,
        )

        self.assertEqual(len(rows), 2)
        self.assertIn("ts", rows[0])
        self.assertEqual(rows[0]["watts"], 200.0)

        sql, params = self.mock_cur.execute.call_args[0]
        self.assertIn("SELECT ts, watts, heartrate FROM streams", sql)
        self.assertIn("activity_id = %s", sql)
        self.assertIn("ts >= %s", sql)
        self.assertIn("ts <= %s", sql)


class TestMySQLMcpExtensions(unittest.TestCase):
    """Test MySQL implementation of search_activities, get_stream_coverage, get_activity_stream_window."""

    def setUp(self):
        self.repo = object.__new__(MySQLRepository)
        self.repo.config = types.SimpleNamespace(
            mysql_database="db",
            mysql_host="localhost",
            mysql_port=3306,
            mysql_user="usr",
            mysql_password="pwd",
            mysql_ssl_mode="disable",
        )
        self.mock_conn = MagicMock()
        self.mock_conn.is_connected.return_value = True
        self.mock_cur = MagicMock()
        self.repo.conn = self.mock_conn
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cur

    def test_mysql_search_activities(self):
        self.mock_cur.fetchall.return_value = [
            {
                "activity_id": 201,
                "name": "Tempo Ride",
                "sport": "Ride",
                "athlete_id": 2,
                "distance": 30000.0,
                "moving_time": 3600,
                "elapsed_time": 3700,
                "total_elevation_gain": 200.0,
                "start_date": datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
                "average_speed": 8.33,
                "max_speed": 14.0,
                "average_heartrate": 150,
                "max_heartrate": 180,
                "average_cadence": 90.0,
                "average_watts": 240.0,
                "max_watts": 700.0,
                "weighted_average_watts": 250.0,
                "device_watts": True,
                "calories": 800.0,
                "kilojoules": 780.0,
                "achievement_count": 3,
                "pr_count": 1,
                "suffer_score": 50,
                "average_temp": 22.0,
                "gear_id": "b2",
                "has_heartrate": True,
                "workout_type": 10,
                "trophies": None,
            }
        ]

        activities, next_cursor, has_more = self.repo.search_activities(
            athlete_id=2,
            filters={"min_watts": 200.0, "max_watts": 300.0, "keyword": "Tempo"},
            limit=10,
        )

        self.assertEqual(len(activities), 1)
        self.assertFalse(has_more)
        self.assertIsNone(next_cursor)
        self.assertEqual(activities[0]["activity_id"], 201)

        sql, params = self.mock_cur.execute.call_args[0]
        self.assertIn("name LIKE %s", sql)
        self.assertIn("CAST(activity_id AS CHAR) LIKE %s", sql)
        self.assertIn("average_watts >= %s", sql)
        self.assertIn("average_watts <= %s", sql)


class TestFirebirdMcpExtensions(unittest.TestCase):
    """Test Firebird implementation of search_activities, get_stream_coverage, get_activity_stream_window."""

    def setUp(self):
        self.repo = object.__new__(FirebirdRepository)
        self.repo.config = types.SimpleNamespace(
            firebird_database="db.fdb",
            firebird_host="localhost",
            firebird_port=3050,
            firebird_user="usr",
            firebird_password="pwd",
        )
        self.repo._last_verified = time.monotonic()
        self.mock_conn = MagicMock()
        self.mock_conn.is_closed.return_value = False
        self.mock_cur = MagicMock()
        self.repo.conn = self.mock_conn
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cur

    def test_firebird_search_activities(self):
        self.mock_cur.description = [
            ("activity_id",), ("name",), ("sport",), ("athlete_id",), ("distance",),
            ("moving_time",), ("elapsed_time",), ("total_elevation_gain",), ("start_date",),
            ("average_speed",), ("max_speed",), ("average_heartrate",), ("max_heartrate",),
            ("average_cadence",), ("average_watts",), ("max_watts",), ("weighted_average_watts",),
            ("device_watts",), ("calories",), ("kilojoules",), ("achievement_count",),
            ("pr_count",), ("suffer_score",), ("average_temp",), ("gear_id",),
            ("has_heartrate",), ("workout_type",), ("trophies",)
        ]
        self.mock_cur.fetchall.return_value = [
            (
                301, "Gravel Ride", "GravelRide", 3, 50000.0, 6000, 6200, 600.0,
                datetime(2026, 7, 1, 10, 0), 8.33, 16.0, 155, 185, 85.0, 230.0,
                800.0, 245.0, 1, 1200.0, 1150.0, 4, 1, 70, 24.0, "g1", 1, 10, None
            )
        ]

        activities, next_cursor, has_more = self.repo.search_activities(
            athlete_id=3,
            filters={"keyword": "301", "min_elevation_m": 500.0, "sort_by": "elevation", "sort_order": "desc"},
            limit=5,
        )

        self.assertEqual(len(activities), 1)
        self.assertFalse(has_more)
        self.assertIsNone(next_cursor)
        self.assertEqual(activities[0]["activity_id"], 301)
        self.assertIn("2026-07-01", activities[0]["start_date"])

        sql, params = self.mock_cur.execute.call_args[0]
        self.assertIn('SELECT FIRST 6', sql)
        self.assertIn('"athlete_id" = ?', sql)
        self.assertIn('"total_elevation_gain" >= ?', sql)
        self.assertIn('CAST("activity_id" AS VARCHAR(20)) LIKE ?', sql)
        self.assertIn('ORDER BY "total_elevation_gain" DESC', sql)


if __name__ == "__main__":
    unittest.main()
