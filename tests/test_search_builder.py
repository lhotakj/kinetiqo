"""Unit tests for dialect-aware search query builder."""

from datetime import datetime, timezone
import json
import unittest

from kinetiqo.db.search_builder import (
    SORT_FIELD_MAP,
    build_search_activities_query,
    process_search_rows,
)
from kinetiqo.db.pagination import encode_cursor


class TestSearchBuilder(unittest.TestCase):
    def test_sort_field_map_coverage(self):
        self.assertIn("date", SORT_FIELD_MAP)
        self.assertIn("distance", SORT_FIELD_MAP)
        self.assertIn("wind", SORT_FIELD_MAP)
        self.assertEqual(SORT_FIELD_MAP["speed"], "average_speed")

    def test_build_query_postgresql_default(self):
        query, params, sort_col, fetch_limit = build_search_activities_query("postgresql", athlete_id=123)
        self.assertEqual(sort_col, "start_date")
        self.assertEqual(fetch_limit, 51)
        self.assertIn("athlete_id = %s", query)
        self.assertIn("ORDER BY start_date DESC, activity_id DESC", query)
        self.assertIn("LIMIT %s", query)
        self.assertEqual(params, [123, 51])

    def test_build_query_mysql_nulls_sorting(self):
        query, params, sort_col, fetch_limit = build_search_activities_query(
            "mysql",
            filters={"sort_by": "watts", "sort_order": "asc", "min_distance_km": 50},
        )
        self.assertEqual(sort_col, "average_watts")
        self.assertIn("ORDER BY (average_watts IS NULL), average_watts ASC", query)
        self.assertIn("distance >= %s", query)
        self.assertIn(50000.0, params)

    def test_build_query_firebird_quotes_and_question_marks(self):
        query, params, sort_col, fetch_limit = build_search_activities_query(
            "firebird",
            athlete_id=456,
            filters={"keyword": "Morning", "sport_types": ["Ride", "Run"]},
            limit=20,
        )
        self.assertEqual(sort_col, "start_date")
        self.assertEqual(fetch_limit, 21)
        self.assertIn('SELECT FIRST 21', query)
        self.assertIn('"athlete_id" = ?', query)
        self.assertIn('"sport" IN (?, ?)', query)
        self.assertIn('LOWER("name") LIKE LOWER(?)', query)
        self.assertNotIn("%s", query)

    def test_build_query_with_cursor(self):
        cursor = encode_cursor(250.0, "2026-05-01T10:00:00", 9999)
        query, params, sort_col, _ = build_search_activities_query(
            "postgresql",
            filters={"sort_by": "watts", "sort_order": "desc"},
            cursor=cursor,
        )
        self.assertIn("(average_watts < %s OR (average_watts = %s AND (start_date < %s OR (start_date = %s AND activity_id < %s))))", query)
        self.assertEqual(params[:-1], [250.0, 250.0, "2026-05-01T10:00:00", "2026-05-01T10:00:00", 9999])
        self.assertEqual(params[-1], 51)

    def test_process_search_rows_pagination(self):
        dt = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        raw_rows = [
            {"activity_id": 1, "start_date": dt, "average_watts": 200, "trophies": '{"1": 1}'},
            {"activity_id": 2, "start_date": dt, "average_watts": 210, "trophies": None},
        ]
        # Limit 1 -> has_more is True, next_cursor produced
        activities, next_cursor, has_more = process_search_rows(raw_rows, limit=1, sort_col="start_date")
        self.assertTrue(has_more)
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["activity_id"], 1)
        self.assertEqual(activities[0]["trophies"], {"1": 1})
        self.assertIsNotNone(next_cursor)

        # Limit 2 -> has_more is False, next_cursor is None
        activities, next_cursor, has_more = process_search_rows(raw_rows, limit=2, sort_col="start_date")
        self.assertFalse(has_more)
        self.assertEqual(len(activities), 2)
        self.assertIsNone(next_cursor)


if __name__ == "__main__":
    unittest.main()
