import unittest
from unittest.mock import MagicMock, call
from kinetiqo.db.schema import SCHEMA_DEFINITION, SchemaManager


class TestSchemaDefinition(unittest.TestCase):
    """Validate completeness and consistency of SCHEMA_DEFINITION across dialects."""

    def test_schema_definition_structure(self):
        self.assertIn("activities", SCHEMA_DEFINITION)
        self.assertIn("streams", SCHEMA_DEFINITION)
        self.assertIn("profile", SCHEMA_DEFINITION)

        for table_name, table_def in SCHEMA_DEFINITION.items():
            self.assertIn("columns", table_def, f"Table {table_name} missing columns")
            for col in table_def["columns"]:
                self.assertIn("name", col)
                self.assertIn("type_mysql", col)
                self.assertIn("type_pg", col)
                self.assertIn("type_firebird", col)

    def test_mcp_pre_registered_tables(self):
        """Verify sync_jobs and verified_segment_efforts tables are pre-registered with dialect definitions."""
        self.assertIn("sync_jobs", SCHEMA_DEFINITION)
        self.assertIn("verified_segment_efforts", SCHEMA_DEFINITION)

        sync_cols = {col["name"] for col in SCHEMA_DEFINITION["sync_jobs"]["columns"]}
        expected_sync_cols = {"job_id", "sync_type", "status", "created_at", "started_at", "completed_at", "total_activities", "synced_activities", "error_message"}
        self.assertTrue(expected_sync_cols.issubset(sync_cols))

        vse_cols = {col["name"] for col in SCHEMA_DEFINITION["verified_segment_efforts"]["columns"]}
        expected_vse_cols = {"id", "athlete_id", "activity_id", "segment_id", "name", "rank", "elapsed_time", "moving_time", "start_date", "pr_rank"}
        self.assertTrue(expected_vse_cols.issubset(vse_cols))

    def test_chat_tables_are_portable_and_scoped(self):
        """Chat persistence must be bootstrapped for all supported databases."""
        for table_name in ("chat_sessions", "chat_messages", "chat_provider_keys"):
            with self.subTest(table=table_name):
                self.assertIn(table_name, SCHEMA_DEFINITION)
                columns = {column["name"] for column in SCHEMA_DEFINITION[table_name]["columns"]}
                self.assertIn("athlete_id", columns)
                for column in SCHEMA_DEFINITION[table_name]["columns"]:
                    self.assertIn("type_mysql", column)
                    self.assertIn("type_pg", column)
                    self.assertIn("type_firebird", column)
        chat_msg_indexes = {idx["name"] for idx in SCHEMA_DEFINITION["chat_messages"]["indexes"]}
        self.assertIn("idx_chat_messages_hist", chat_msg_indexes)
        self.assertIn("idx_chat_messages_session", chat_msg_indexes)

    def test_activities_reverse_composite_indexes(self):
        """Verify performance-critical reverse composite indexes exist for all dialects."""
        indexes = SCHEMA_DEFINITION["activities"]["indexes"]
        index_names = {idx["name"] for idx in indexes}

        expected_new_indexes = [
            "idx_activities_elev_start",
            "idx_activities_dist_start",
            "idx_activities_name_start",
            "idx_activities_speed_start",
            "idx_activities_time_start",
            "idx_activities_totals_date_cover",
        ]

        for expected in expected_new_indexes:
            self.assertIn(expected, index_names, f"Index {expected} missing in activities schema")

        # Verify definitions for each dialect
        by_name = {idx["name"]: idx for idx in indexes}

        # Check totals date covering index across all three dialects
        totals_idx = by_name["idx_activities_totals_date_cover"]
        self.assertIn("start_date", totals_idx["def_pg"])
        self.assertIn("INCLUDE (distance, total_elevation_gain, moving_time)", totals_idx["def_pg"])
        self.assertIn("(start_date, distance, total_elevation_gain, moving_time)", totals_idx["def_mysql"])
        self.assertIn('("start_date", "distance", "total_elevation_gain", "moving_time")', totals_idx["def_firebird"])

        # Check name index uses COLLATE "C" in PostgreSQL
        pg_name_sql = by_name["idx_activities_name_start"]["def_pg"]
        self.assertIn('COLLATE "C"', pg_name_sql)

        # Check elevation and distance reverse indexes
        self.assertIn("total_elevation_gain DESC, start_date DESC", by_name["idx_activities_elev_start"]["def_pg"])
        self.assertIn("total_elevation_gain DESC, start_date DESC", by_name["idx_activities_elev_start"]["def_mysql"])
        self.assertIn('"total_elevation_gain", "start_date"', by_name["idx_activities_elev_start"]["def_firebird"])

        self.assertIn("distance DESC, start_date DESC", by_name["idx_activities_dist_start"]["def_pg"])
        self.assertIn("distance DESC, start_date DESC", by_name["idx_activities_dist_start"]["def_mysql"])
        self.assertIn('"distance", "start_date"', by_name["idx_activities_dist_start"]["def_firebird"])

        # Check Firebird key size safety: def_firebird must be omitted for idx_activities_name_start
        # because VARCHAR(500) UTF-8 + TIMESTAMP exceeds Firebird's page_size / 4 limit.
        self.assertNotIn("def_firebird", by_name["idx_activities_name_start"])


class TestSchemaManager(unittest.TestCase):
    """Test SchemaManager logic across PostgreSQL, MySQL, and Firebird dialects."""

    def test_type_suffix(self):
        sm_pg = SchemaManager(MagicMock(), "postgresql")
        self.assertEqual(sm_pg._get_type_suffix(), "pg")

        sm_mysql = SchemaManager(MagicMock(), "mysql")
        self.assertEqual(sm_mysql._get_type_suffix(), "mysql")

        sm_fb = SchemaManager(MagicMock(), "firebird")
        self.assertEqual(sm_fb._get_type_suffix(), "firebird")

    def test_get_existing_index_names_postgresql(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [("idx_one",), ("idx_two",)]

        sm = SchemaManager(mock_conn, "postgresql")
        names = sm._get_existing_index_names("activities")

        self.assertEqual(names, {"idx_one", "idx_two"})
        mock_cur.execute.assert_called_once()
        self.assertIn("pg_indexes", mock_cur.execute.call_args[0][0])

    def test_get_existing_index_names_mysql(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [("PRIMARY",), ("idx_start",)]

        sm = SchemaManager(mock_conn, "mysql")
        names = sm._get_existing_index_names("activities")

        self.assertEqual(names, {"PRIMARY", "idx_start"})
        mock_cur.execute.assert_called_once()
        self.assertIn("information_schema.statistics", mock_cur.execute.call_args[0][0])

    def test_get_existing_index_names_firebird(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [("RDB$PRIMARY1",), ("IDX_START_DATE",)]

        sm = SchemaManager(mock_conn, "firebird")
        names = sm._get_existing_index_names("activities")

        self.assertEqual(names, {"rdb$primary1", "idx_start_date"})
        mock_cur.execute.assert_called_once()
        self.assertIn("RDB$INDICES", mock_cur.execute.call_args[0][0])

    def test_create_index_pg_if_not_exists(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        sm = SchemaManager(mock_conn, "postgresql")
        sm._get_existing_index_names = MagicMock(return_value={"idx_test"})

        success = sm._create_index("idx_test", "CREATE INDEX idx_test ON test (col)", "test")
        self.assertTrue(success)
        mock_cur.execute.assert_called_once_with("CREATE INDEX IF NOT EXISTS idx_test ON test (col)")
        mock_conn.commit.assert_called_once()

    def test_ensure_indexes_creates_missing(self):
        mock_conn = MagicMock()
        sm = SchemaManager(mock_conn, "postgresql")
        # idx_two is already present, idx_one is missing
        sm._get_existing_index_names = MagicMock(side_effect=[
            {"idx_two"},       # initial check
            {"idx_two", "idx_one"},  # verify after creation
        ])
        sm._create_index = MagicMock(return_value=True)

        indexes = [
            {"name": "idx_one", "def_pg": "CREATE INDEX idx_one ON t (a)"},
            {"name": "idx_two", "def_pg": "CREATE INDEX idx_two ON t (b)"},
        ]
        checked, created, failed = sm._ensure_indexes("t", indexes)

        self.assertEqual(checked, 2)
        self.assertEqual(created, 1)
        self.assertEqual(failed, 0)
        sm._create_index.assert_called_once_with("idx_one", "CREATE INDEX idx_one ON t (a)", "t")
