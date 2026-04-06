import logging

logger = logging.getLogger("kinetiqo")

# Reusable SQL type literals to avoid duplication.
_BIGINT_NOT_NULL = "BIGINT NOT NULL"
_INTEGER_NOT_NULL = "INTEGER NOT NULL"
_DOUBLE_PRECISION = "DOUBLE PRECISION"

# Define the schema in a database-agnostic way where possible,
# or provide specific types for each dialect.
SCHEMA_DEFINITION = {
    "activities": {
        "columns": [
            {"name": "start_date", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE",
             "type_firebird": "TIMESTAMP"},
            {"name": "activity_id", "type_mysql": "BIGINT PRIMARY KEY", "type_pg": "BIGINT PRIMARY KEY",
             "type_firebird": "BIGINT PRIMARY KEY"},
            {"name": "name", "type_mysql": "TEXT", "type_pg": "TEXT", "type_firebird": "VARCHAR(500)"},
            {"name": "sport", "type_mysql": "VARCHAR(255)", "type_pg": "TEXT", "type_firebird": "VARCHAR(255)"},
            {"name": "athlete_id", "type_mysql": "BIGINT", "type_pg": "BIGINT", "type_firebird": "BIGINT"},
            {"name": "distance", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "moving_time", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
            {"name": "elapsed_time", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
            {"name": "total_elevation_gain", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "average_speed", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "max_speed", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "average_heartrate", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
            {"name": "max_heartrate", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
            {"name": "average_cadence", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "average_watts", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "max_watts", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "achievement_count", "type_mysql": "INTEGER", "type_pg": "INTEGER",
             "type_firebird": "INTEGER"},
            {"name": "average_temp", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "calories", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "device_watts", "type_mysql": "BOOLEAN", "type_pg": "BOOLEAN",
             "type_firebird": "SMALLINT"},
            {"name": "elev_high", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "elev_low", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "gear_id", "type_mysql": "VARCHAR(255)", "type_pg": "TEXT",
             "type_firebird": "VARCHAR(255)"},
            {"name": "has_heartrate", "type_mysql": "BOOLEAN", "type_pg": "BOOLEAN",
             "type_firebird": "SMALLINT"},
            {"name": "kilojoules", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "pr_count", "type_mysql": "INTEGER", "type_pg": "INTEGER",
             "type_firebird": "INTEGER"},
            {"name": "suffer_score", "type_mysql": "INTEGER", "type_pg": "INTEGER",
             "type_firebird": "INTEGER"},
            {"name": "weighted_average_watts", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "workout_type", "type_mysql": "INTEGER", "type_pg": "INTEGER",
             "type_firebird": "INTEGER"},
        ],
        "indexes": [
            {
                "name": "idx_activities_start_date",
                "def_mysql": "CREATE INDEX idx_activities_start_date ON activities (start_date DESC)",
                "def_pg": "CREATE INDEX idx_activities_start_date ON activities (start_date DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_start_date ON "activities" ("start_date")'
            },
            {
                "name": "idx_activities_sport_start_date",
                "def_mysql": "CREATE INDEX idx_activities_sport_start_date ON activities (sport, start_date DESC)",
                "def_pg": "CREATE INDEX idx_activities_sport_start_date ON activities (sport, start_date DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_sport_start_date ON "activities" ("sport", "start_date")'
            },
            {
                "name": "idx_activities_sport",
                "def_mysql": "CREATE INDEX idx_activities_sport ON activities (sport)",
                "def_pg": "CREATE INDEX idx_activities_sport ON activities (sport)",
                "def_firebird": 'CREATE INDEX idx_activities_sport ON "activities" ("sport")'
            },
            {
                "name": "idx_activities_totals_cover",
                "def_mysql": "CREATE INDEX idx_activities_totals_cover ON activities (sport, start_date, distance, total_elevation_gain, moving_time)",
                "def_pg": "CREATE INDEX idx_activities_totals_cover ON activities (sport, start_date) INCLUDE (distance, total_elevation_gain, moving_time)",
                "def_firebird": 'CREATE INDEX idx_activities_totals_cover ON "activities" ("sport", "start_date", "distance", "total_elevation_gain", "moving_time")'
            },
            {
                "name": "idx_activities_athlete_start_date",
                "def_mysql": "CREATE INDEX idx_activities_athlete_start_date ON activities (athlete_id, start_date DESC)",
                "def_pg": "CREATE INDEX idx_activities_athlete_start_date ON activities (athlete_id, start_date DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_athlete_start_date ON "activities" ("athlete_id", "start_date")'
            },
            {
                "name": "idx_activities_distance",
                "def_mysql": "CREATE INDEX idx_activities_distance ON activities (distance DESC)",
                "def_pg": "CREATE INDEX idx_activities_distance ON activities (distance DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_distance ON "activities" ("distance")'
            },
            {
                "name": "idx_activities_elevation",
                "def_mysql": "CREATE INDEX idx_activities_elevation ON activities (total_elevation_gain DESC)",
                "def_pg": "CREATE INDEX idx_activities_elevation ON activities (total_elevation_gain DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_elevation ON "activities" ("total_elevation_gain")'
            },
            {
                "name": "idx_activities_moving_time",
                "def_mysql": "CREATE INDEX idx_activities_moving_time ON activities (moving_time DESC)",
                "def_pg": "CREATE INDEX idx_activities_moving_time ON activities (moving_time DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_moving_time ON "activities" ("moving_time")'
            },
            {
                "name": "idx_activities_average_speed",
                "def_mysql": "CREATE INDEX idx_activities_average_speed ON activities (average_speed DESC)",
                "def_pg": "CREATE INDEX idx_activities_average_speed ON activities (average_speed DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_average_speed ON "activities" ("average_speed")'
            },
            {
                "name": "idx_activities_avg_watts",
                "def_mysql": "CREATE INDEX idx_activities_avg_watts ON activities (average_watts DESC)",
                "def_pg": "CREATE INDEX idx_activities_avg_watts ON activities (average_watts DESC) WHERE average_watts IS NOT NULL",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_avg_watts ON "activities" ("average_watts")'
            },
            {
                "name": "idx_activities_max_watts",
                "def_mysql": "CREATE INDEX idx_activities_max_watts ON activities (max_watts DESC)",
                "def_pg": "CREATE INDEX idx_activities_max_watts ON activities (max_watts DESC) WHERE max_watts IS NOT NULL",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_max_watts ON "activities" ("max_watts")'
            },
            {
                "name": "idx_activities_avg_hr",
                "def_mysql": "CREATE INDEX idx_activities_avg_hr ON activities (average_heartrate DESC)",
                "def_pg": "CREATE INDEX idx_activities_avg_hr ON activities (average_heartrate DESC) WHERE average_heartrate IS NOT NULL",
                "def_firebird": 'CREATE DESCENDING INDEX idx_activities_avg_hr ON "activities" ("average_heartrate")'
            },
            {
                "name": "idx_activities_gear",
                "def_mysql": "CREATE INDEX idx_activities_gear ON activities (gear_id)",
                "def_pg": "CREATE INDEX idx_activities_gear ON activities (gear_id) WHERE gear_id IS NOT NULL",
                "def_firebird": 'CREATE INDEX idx_activities_gear ON "activities" ("gear_id")'
            },
            {
                "name": "idx_activities_fitness_trends",
                "def_mysql": "CREATE INDEX idx_activities_fitness_trends ON activities (suffer_score, start_date)",
                "def_pg": "CREATE INDEX idx_activities_fitness_trends ON activities (start_date) INCLUDE (suffer_score) WHERE suffer_score > 0",
                "def_firebird": 'CREATE INDEX idx_activities_fitness_trends ON "activities" ("suffer_score", "start_date")'
            }
        ],
        "engine_mysql": "ENGINE=InnoDB"
    },
    "streams": {
        "columns": [
            {"name": "ts", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE",
             "type_firebird": "TIMESTAMP"},
            {"name": "activity_id", "type_mysql": "BIGINT", "type_pg": "BIGINT", "type_firebird": "BIGINT"},
            {"name": "sport", "type_mysql": "VARCHAR(255)", "type_pg": "TEXT", "type_firebird": "VARCHAR(255)"},
            {"name": "athlete_id", "type_mysql": "BIGINT", "type_pg": "BIGINT", "type_firebird": "BIGINT"},
            {"name": "lat", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "lng", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "altitude", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "heartrate", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
            {"name": "cadence", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
            {"name": "speed", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "distance", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "watts", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "temp", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "grade_smooth", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
            {"name": "moving", "type_mysql": "BOOLEAN", "type_pg": "BOOLEAN", "type_firebird": "SMALLINT"}
        ],
        "constraints": [
            {
                "name": "fk_activity",
                "def_mysql": "CONSTRAINT fk_activity FOREIGN KEY(activity_id) REFERENCES activities(activity_id) ON DELETE CASCADE",
                "def_pg": "CONSTRAINT fk_activity FOREIGN KEY(activity_id) REFERENCES activities(activity_id) ON DELETE CASCADE",
                "def_firebird": 'CONSTRAINT fk_activity FOREIGN KEY("activity_id") REFERENCES "activities"("activity_id") ON DELETE CASCADE'
            }
        ],
        "indexes": [
            {
                "name": "idx_streams_activity_id",
                "def_mysql": "CREATE INDEX idx_streams_activity_id ON streams (activity_id)",
                "def_pg": "CREATE INDEX idx_streams_activity_id ON streams (activity_id)",
                "def_firebird": 'CREATE INDEX idx_streams_activity_id ON "streams" ("activity_id")'
            },
            {
                "name": "idx_streams_activity_ts",
                "def_mysql": "CREATE INDEX idx_streams_activity_ts ON streams (activity_id, ts)",
                "def_pg": "CREATE INDEX idx_streams_activity_ts ON streams (activity_id, ts)",
                "def_firebird": 'CREATE INDEX idx_streams_activity_ts ON "streams" ("activity_id", "ts")'
            },
            {
                "name": "idx_streams_ts",
                "def_mysql": "CREATE INDEX idx_streams_ts ON streams (ts)",
                "def_pg": "CREATE INDEX idx_streams_ts ON streams (ts)",
                "def_firebird": 'CREATE INDEX idx_streams_ts ON "streams" ("ts")'
            },
            {
                "name": "idx_streams_activity_gps",
                "def_mysql": "CREATE INDEX idx_streams_activity_gps ON streams (activity_id, ts, lat, lng)",
                "def_pg": "CREATE INDEX idx_streams_activity_gps ON streams (activity_id, ts) INCLUDE (lat, lng) WHERE lat IS NOT NULL AND lng IS NOT NULL",
                "def_firebird": 'CREATE INDEX idx_streams_activity_gps ON "streams" ("activity_id", "ts", "lat", "lng")'
            },
            {
                "name": "idx_streams_sport_activity",
                "def_mysql": "CREATE INDEX idx_streams_sport_activity ON streams (sport, activity_id)",
                "def_pg": "CREATE INDEX idx_streams_sport_activity ON streams (sport, activity_id)",
                "def_firebird": 'CREATE INDEX idx_streams_sport_activity ON "streams" ("sport", "activity_id")'
            },
            {
                "name": "idx_streams_activity_watts",
                "def_mysql": "CREATE INDEX idx_streams_activity_watts ON streams (activity_id, watts)",
                "def_pg": "CREATE INDEX idx_streams_activity_watts ON streams (activity_id, watts) WHERE watts IS NOT NULL",
                "def_firebird": 'CREATE INDEX idx_streams_activity_watts ON "streams" ("activity_id", "watts")'
            },
            {
                # Covering ordered index for get_watts_streams_for_activities:
                #   SELECT activity_id, watts FROM streams
                #   WHERE activity_id IN (...) AND watts IS NOT NULL
                #   ORDER BY activity_id, ts
                #
                # PostgreSQL: (activity_id, ts) key eliminates the sort step;
                #   INCLUDE(watts) enables an index-only scan; partial WHERE keeps
                #   the index compact by excluding NULL-watts rows entirely.
                #
                # MySQL: (activity_id, ts, watts) — three-column covering index;
                #   the engine can satisfy the projection from the index leaf pages.
                #
                # Firebird: (activity_id, ts, watts) — three-column composite.
                #   Firebird has no INCLUDE or partial-index syntax, but storing
                #   watts as the third key column means the leaf page already
                #   contains the watts value, reducing random heap I/O per row.
                #   The (activity_id, ts) prefix also eliminates the sort step,
                #   which is a real win over the plain idx_streams_activity_ts index.
                "name": "idx_streams_activity_ts_watts",
                "def_mysql": "CREATE INDEX idx_streams_activity_ts_watts ON streams (activity_id, ts, watts)",
                "def_pg": "CREATE INDEX idx_streams_activity_ts_watts ON streams (activity_id, ts) INCLUDE (watts) WHERE watts IS NOT NULL",
                "def_firebird": 'CREATE INDEX idx_streams_activity_ts_watts ON "streams" ("activity_id", "ts", "watts")'
            }
        ],
        "engine_mysql": "ENGINE=InnoDB"
    },
    "logs": {
        "columns": [
            {"name": "id", "type_mysql": "BIGINT AUTO_INCREMENT PRIMARY KEY", "type_pg": "SERIAL PRIMARY KEY",
             "type_firebird": "BIGINT PRIMARY KEY"},
            {"name": "created_at", "type_mysql": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
             "type_pg": "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
             "type_firebird": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
            {"name": "added", "type_mysql": "BIGINT", "type_pg": "BIGINT", "type_firebird": "BIGINT"},
            {"name": "removed", "type_mysql": "BIGINT", "type_pg": "BIGINT", "type_firebird": "BIGINT"},
            {"name": "trigger_source", "type_mysql": "VARCHAR(50)", "type_pg": "TEXT", "type_firebird": "VARCHAR(50)"},
            {"name": "action", "type_mysql": "VARCHAR(50)", "type_pg": "TEXT", "type_firebird": "VARCHAR(50)"},
            {"name": "user", "type_mysql": "VARCHAR(100) DEFAULT '-'", "type_pg": "TEXT DEFAULT '-'",
             "type_firebird": "VARCHAR(100) DEFAULT '-'"},
            {"name": "success", "type_mysql": "BOOLEAN", "type_pg": "BOOLEAN", "type_firebird": "SMALLINT"}
        ],
        "indexes": [
            {
                "name": "idx_logs_created_at",
                "def_mysql": "CREATE INDEX idx_logs_created_at ON logs (created_at DESC)",
                "def_pg": "CREATE INDEX idx_logs_created_at ON logs (created_at DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_logs_created_at ON "logs" ("created_at")'
            },
            {
                "name": "idx_logs_action",
                "def_mysql": "CREATE INDEX idx_logs_action ON logs (action, created_at DESC)",
                "def_pg": "CREATE INDEX idx_logs_action ON logs (action, created_at DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_logs_action ON "logs" ("action", "created_at")'
            },
            {
                "name": "idx_logs_success",
                "def_mysql": "CREATE INDEX idx_logs_success ON logs (success, created_at DESC)",
                "def_pg": "CREATE INDEX idx_logs_success ON logs (success, created_at DESC)",
                "def_firebird": 'CREATE DESCENDING INDEX idx_logs_success ON "logs" ("success", "created_at")'
            }
        ],
        "engine_mysql": "ENGINE=InnoDB"
    },
    "profile": {
        "columns": [
            {"name": "athlete_id", "type_mysql": "BIGINT PRIMARY KEY", "type_pg": "BIGINT PRIMARY KEY",
             "type_firebird": "BIGINT PRIMARY KEY"},
            {"name": "first_name", "type_mysql": "VARCHAR(255)", "type_pg": "TEXT",
             "type_firebird": "VARCHAR(255)"},
            {"name": "last_name", "type_mysql": "VARCHAR(255)", "type_pg": "TEXT",
             "type_firebird": "VARCHAR(255)"},
            {"name": "weight", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION",
             "type_firebird": "DOUBLE PRECISION"},
        ],
        "indexes": [],
        "engine_mysql": "ENGINE=InnoDB"
    },
    # One row per (athlete_id, activity_type_id).
    # activity_type_id: 1=Cycling, 2=Walking (extensible — add rows for new types).
    # Distance goals in km; elevation goals in metres.
    "activity_goals": {
        "columns": [
            {"name": "athlete_id",             "type_mysql": _BIGINT_NOT_NULL,   "type_pg": _BIGINT_NOT_NULL,   "type_firebird": _BIGINT_NOT_NULL},
            {"name": "activity_type_id",        "type_mysql": _INTEGER_NOT_NULL,  "type_pg": _INTEGER_NOT_NULL,  "type_firebird": _INTEGER_NOT_NULL},
            {"name": "weekly_distance_goal",    "type_mysql": _DOUBLE_PRECISION,  "type_pg": _DOUBLE_PRECISION,  "type_firebird": _DOUBLE_PRECISION},
            {"name": "monthly_distance_goal",   "type_mysql": _DOUBLE_PRECISION,  "type_pg": _DOUBLE_PRECISION,  "type_firebird": _DOUBLE_PRECISION},
            {"name": "yearly_distance_goal",    "type_mysql": _DOUBLE_PRECISION,  "type_pg": _DOUBLE_PRECISION,  "type_firebird": _DOUBLE_PRECISION},
            {"name": "weekly_elevation_goal",   "type_mysql": _DOUBLE_PRECISION,  "type_pg": _DOUBLE_PRECISION,  "type_firebird": _DOUBLE_PRECISION},
            {"name": "monthly_elevation_goal",  "type_mysql": _DOUBLE_PRECISION,  "type_pg": _DOUBLE_PRECISION,  "type_firebird": _DOUBLE_PRECISION},
            {"name": "yearly_elevation_goal",   "type_mysql": _DOUBLE_PRECISION,  "type_pg": _DOUBLE_PRECISION,  "type_firebird": _DOUBLE_PRECISION},
        ],
        "constraints": [
            {
                "name": "pk_activity_goals",
                "def_mysql":    "CONSTRAINT pk_activity_goals PRIMARY KEY (athlete_id, activity_type_id)",
                "def_pg":       "CONSTRAINT pk_activity_goals PRIMARY KEY (athlete_id, activity_type_id)",
                "def_firebird": 'CONSTRAINT pk_activity_goals PRIMARY KEY ("athlete_id", "activity_type_id")',
            }
        ],
        "indexes": [],
        "engine_mysql": "ENGINE=InnoDB"
    },
    "gtt_activity_ids": {
        "columns": [
            {"name": "activity_id", "type_mysql": "BIGINT PRIMARY KEY", "type_pg": "BIGINT PRIMARY KEY", "type_firebird": "BIGINT PRIMARY KEY"}
        ],
        "indexes": [],
        "engine_mysql": "ENGINE=InnoDB"
    }
}


class SchemaManager:
    def __init__(self, conn, db_type):
        self.conn = conn
        self.db_type = db_type  # 'mysql', 'postgresql', or 'firebird'

    def _get_type_suffix(self):
        """Get the suffix for type keys based on database type."""
        if self.db_type == 'firebird':
            return 'firebird'
        elif self.db_type == 'mysql':
            return 'mysql'
        else:
            return 'pg'

    def ensure_schema(self):
        """Ensures the database schema matches the definition.

        Safe to call on every startup — existing objects are left
        untouched.  Tables are created/updated first, then all indexes
        are verified (and created when missing).  A summary line is
        logged so operators can tell at a glance what happened.
        """
        logger.info(f"{self.db_type.upper()}: Checking schema consistency...")

        for table_name, definition in SCHEMA_DEFINITION.items():
            self._ensure_table(table_name, definition)

        total_checked = 0
        total_created = 0
        total_failed = 0

        for table_name, definition in SCHEMA_DEFINITION.items():
            if "indexes" in definition:
                checked, created, failed = self._ensure_indexes(table_name, definition["indexes"])
                total_checked += checked
                total_created += created
                total_failed += failed

        if total_failed:
            logger.warning(
                f"{self.db_type.upper()}: Schema check complete — "
                f"indexes: {total_checked} checked, {total_created} created, {total_failed} FAILED."
            )
        else:
            logger.info(
                f"{self.db_type.upper()}: Schema check complete — "
                f"indexes: {total_checked} checked, {total_created} created."
            )

    def _get_existing_index_names(self, table_name: str) -> set:
        """Return a set of index names that currently exist on *table_name*.

        Fetching all indexes in a single query is faster and more
        reliable than one round-trip per index.
        """
        cur = self.conn.cursor()
        try:
            if self.db_type == 'mysql':
                cur.execute(
                    "SELECT DISTINCT index_name FROM information_schema.statistics "
                    "WHERE table_schema = DATABASE() AND table_name = %s",
                    (table_name,)
                )
            elif self.db_type == 'postgresql':
                cur.execute(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = %s",
                    (table_name,)
                )
            elif self.db_type == 'firebird':
                # Tables are created with quoted lowercase identifiers
                # ("activities"), so RDB$RELATION_NAME stores them in
                # lowercase.  Do NOT uppercase the table name here.
                cur.execute(
                    "SELECT TRIM(RDB$INDEX_NAME) FROM RDB$INDICES "
                    "WHERE TRIM(RDB$RELATION_NAME) = ?",
                    (table_name,)
                )
            else:
                return set()
            return {row[0].lower() if self.db_type == 'firebird' else row[0]
                    for row in cur.fetchall()}
        except Exception as e:
            logger.warning(
                f"{self.db_type.upper()}: Could not list indexes for '{table_name}': {e}"
            )
            return set()
        finally:
            cur.close()

    def _ensure_indexes(self, table_name: str, indexes: list) -> tuple:
        """Verify every defined index exists; create any that are missing.

        :return: Tuple of (checked, created, failed) counts.
        """
        type_suffix = self._get_type_suffix()
        checked = 0
        created = 0
        failed = 0

        # Fetch all existing indexes for this table in a single query
        existing = self._get_existing_index_names(table_name)

        for idx in indexes:
            idx_name = idx["name"]
            idx_def_key = f"def_{type_suffix}"

            if idx_def_key not in idx:
                continue

            idx_sql = idx[idx_def_key]
            checked += 1

            # For Firebird the catalog stores names in uppercase
            lookup_name = idx_name.lower() if self.db_type == 'firebird' else idx_name

            if lookup_name in existing:
                logger.debug(
                    f"{self.db_type.upper()}: Index '{idx_name}' on '{table_name}' — OK."
                )
                continue

            logger.info(
                f"{self.db_type.upper()}: Index '{idx_name}' missing on '{table_name}', creating..."
            )

            if self._create_index(idx_name, idx_sql, table_name):
                created += 1
            else:
                failed += 1

        return checked, created, failed

    def _create_index(self, idx_name: str, idx_sql: str, table_name: str) -> bool:
        """Create a single index.  Returns *True* on success."""
        cur = self.conn.cursor()
        try:
            if self.db_type == 'postgresql':
                safe_sql = idx_sql.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
                safe_sql = safe_sql.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ", 1)
            else:
                safe_sql = idx_sql

            cur.execute(safe_sql)
            self.conn.commit()

            # Verify the index is now visible in the catalog
            verify = self._get_existing_index_names(table_name)
            lookup_name = idx_name.lower() if self.db_type == 'firebird' else idx_name

            if lookup_name in verify:
                logger.info(
                    f"{self.db_type.upper()}: Index '{idx_name}' on '{table_name}' created successfully."
                )
                return True
            else:
                logger.error(
                    f"{self.db_type.upper()}: CREATE INDEX for '{idx_name}' on '{table_name}' "
                    f"did not raise an error but the index is not visible in the catalog."
                )
                return False

        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            error_str = str(e).lower()
            if 'already exists' in error_str or 'duplicate' in error_str:
                logger.debug(
                    f"{self.db_type.upper()}: Index '{idx_name}' already exists on '{table_name}'."
                )
                return True
            else:
                logger.error(
                    f"{self.db_type.upper()}: Failed to create index '{idx_name}' on '{table_name}': {e}"
                )
                return False
        finally:
            cur.close()

    def _index_exists(self, index_name: str, table_name: str) -> bool:
        """Check whether a single index already exists in the database."""
        cur = self.conn.cursor()
        try:
            if self.db_type == 'mysql':
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.statistics "
                    "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
                    (table_name, index_name)
                )
            elif self.db_type == 'postgresql':
                cur.execute(
                    "SELECT COUNT(*) FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = %s AND indexname = %s",
                    (table_name, index_name)
                )
            elif self.db_type == 'firebird':
                cur.execute(
                    "SELECT COUNT(*) FROM RDB$INDICES WHERE TRIM(RDB$INDEX_NAME) = ?",
                    (index_name.upper(),)
                )
            else:
                return False
            result = cur.fetchone()
            return (result[0] > 0) if result else False
        except Exception as e:
            logger.warning(f"{self.db_type.upper()}: Could not check index existence for '{index_name}': {e}")
            return False
        finally:
            cur.close()

    def _quote_identifier(self, identifier):
        """Quotes an identifier based on the database dialect."""
        if self.db_type == 'mysql':
            return f"`{identifier}`"
        else:
            return f'"{identifier}"'

    def _ensure_table(self, table_name, definition):
        if not self._table_exists(table_name):
            self._create_table(table_name, definition)
        else:
            self._update_table(table_name, definition)

    def _table_exists(self, table_name):
        cur = self.conn.cursor()
        try:
            if self.db_type == 'mysql':
                cur.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
                    (table_name,))
            elif self.db_type == 'firebird':
                cur.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE TRIM(RDB$RELATION_NAME) = ?",
                            (table_name,))
            else:
                # Filter by public schema to avoid false positives from
                # pg_catalog or information_schema tables with the same name.
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table_name,))
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _create_table(self, table_name, definition):
        logger.info(f"{self.db_type.upper()}: Creating table '{table_name}'...")

        type_suffix = self._get_type_suffix()
        columns_def = []
        for col in definition["columns"]:
            col_type_key = f"type_{type_suffix}"
            col_type = col[col_type_key]
            quoted_name = self._quote_identifier(col['name'])
            columns_def.append(f"{quoted_name} {col_type}")

        if "constraints" in definition:
            for const in definition["constraints"]:
                const_key = f"def_{type_suffix}"
                const_def = const[const_key]
                columns_def.append(const_def)

        quoted_table = self._quote_identifier(table_name)

        if self.db_type == 'firebird':
            create_sql = f"CREATE TABLE {quoted_table} ({', '.join(columns_def)})"
        else:
            create_sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} ({', '.join(columns_def)})"

        if self.db_type == 'mysql' and "engine_mysql" in definition:
            create_sql += f" {definition['engine_mysql']}"

        cur = self.conn.cursor()
        try:
            cur.execute(create_sql)
            self.conn.commit()
            logger.info(f"{self.db_type.upper()}: Table '{table_name}' ready.")
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            if self._table_exists(table_name):
                logger.info(f"{self.db_type.upper()}: Table '{table_name}' already exists.")
            else:
                logger.error(f"{self.db_type.upper()}: Failed to create table '{table_name}': {e}")
                raise
        finally:
            cur.close()

    def _update_table(self, table_name, definition):
        existing_columns = self._get_existing_columns(table_name)

        type_suffix = self._get_type_suffix()
        for col in definition["columns"]:
            col_name_check = col["name"].lower() if self.db_type == 'firebird' else col["name"]
            if col_name_check not in existing_columns:
                logger.info(f"{self.db_type.upper()}: Adding column '{col['name']}' to '{table_name}'...")
                col_type_key = f"type_{type_suffix}"
                col_type = col[col_type_key]

                quoted_table = self._quote_identifier(table_name)
                quoted_col = self._quote_identifier(col['name'])

                if self.db_type == 'firebird':
                    alter_sql = f"ALTER TABLE {quoted_table} ADD {quoted_col} {col_type}"
                else:
                    alter_sql = f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} {col_type}"

                cur = self.conn.cursor()
                try:
                    cur.execute(alter_sql)
                    self.conn.commit()
                except Exception as e:
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
                    logger.warning(f"{self.db_type.upper()}: Failed to add column '{col['name']}': {e}")
                finally:
                    cur.close()

        desired_columns = {col["name"].lower() if self.db_type == 'firebird' else col["name"]
                          for col in definition["columns"]}
        extra_columns = existing_columns - desired_columns
        for col_name in sorted(extra_columns):
            logger.info(f"{self.db_type.upper()}: Dropping column '{col_name}' from '{table_name}'...")
            quoted_table = self._quote_identifier(table_name)
            quoted_col = self._quote_identifier(col_name)

            if self.db_type == 'firebird':
                alter_sql = f"ALTER TABLE {quoted_table} DROP {quoted_col}"
            else:
                alter_sql = f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}"

            cur = self.conn.cursor()
            try:
                cur.execute(alter_sql)
                self.conn.commit()
            except Exception as exc:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                logger.warning(f"{self.db_type.upper()}: Failed to drop column '{col_name}': {exc}")
            finally:
                cur.close()

    def _get_existing_columns(self, table_name):
        cur = self.conn.cursor()
        try:
            if self.db_type == 'mysql':
                cur.execute(f"SHOW COLUMNS FROM {self._quote_identifier(table_name)}")
                return {row[0] for row in cur.fetchall()}
            elif self.db_type == 'firebird':
                cur.execute("SELECT TRIM(RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS WHERE TRIM(RDB$RELATION_NAME) = ?",
                            (table_name,))
                return {row[0].lower() for row in cur.fetchall()}
            else:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table_name,))
                return {row[0] for row in cur.fetchall()}
        finally:
            cur.close()
