import logging

logger = logging.getLogger("kinetiqo")

# Define the schema in a database-agnostic way where possible, 
# or provide specific types for each dialect.
SCHEMA_DEFINITION = {
    "activities": {
        "columns": [
            {"name": "start_date", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE",
             "type_firebird": "TIMESTAMP"},
            {"name": "activity_id", "type_mysql": "BIGINT PRIMARY KEY", "type_pg": "BIGINT PRIMARY KEY",
             "type_firebird": "BIGINT PRIMARY KEY"},
            {"name": "name", "type_mysql": "TEXT", "type_pg": "TEXT", "type_firebird": "BLOB SUB_TYPE TEXT"},
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
             "type_firebird": "INTEGER"}
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
                "name": "idx_streams_ts",
                "def_mysql": "CREATE INDEX idx_streams_ts ON streams (ts)",
                "def_pg": "CREATE INDEX idx_streams_ts ON streams (ts)",
                "def_firebird": 'CREATE INDEX idx_streams_ts ON "streams" ("ts")'
            },
            {
                "name": "idx_streams_activity_id_ts_gps",
                "def_mysql": "CREATE INDEX idx_streams_activity_id_ts_gps ON streams (activity_id, ts, lat, lng)",
                "def_pg": "CREATE INDEX idx_streams_activity_id_ts_gps ON streams (activity_id, ts) WHERE lat IS NOT NULL AND lng IS NOT NULL",
                "def_firebird": 'CREATE INDEX idx_streams_activity_id_ts_gps ON "streams" ("activity_id", "ts")'
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
            }
        ],
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
        """Ensures the database schema matches the definition."""
        logger.info(f"{self.db_type.upper()}: Checking schema consistency...")

        for table_name, definition in SCHEMA_DEFINITION.items():
            self._ensure_table(table_name, definition)

        # Safely apply indexes after all tables are confirmed to exist.
        # Idempotent — safe to run on every startup.
        for table_name, definition in SCHEMA_DEFINITION.items():
            if "indexes" in definition:
                self._ensure_indexes(table_name, definition["indexes"])

    def _ensure_indexes(self, table_name: str, indexes: list):
        """Safely create indexes that don't yet exist. Idempotent — safe on every startup."""
        type_suffix = self._get_type_suffix()
        for idx in indexes:
            idx_name = idx["name"]
            idx_sql = idx[f"def_{type_suffix}"]

            if self._index_exists(idx_name, table_name):
                continue  # Already exists, skip silently

            cur = self.conn.cursor()
            try:
                if self.db_type == 'postgresql':
                    # PostgreSQL supports CREATE INDEX IF NOT EXISTS natively
                    safe_sql = idx_sql.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
                    safe_sql = safe_sql.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ", 1)
                else:
                    # MySQL / Firebird: existence already confirmed above
                    safe_sql = idx_sql
                cur.execute(safe_sql)
                self.conn.commit()
                logger.info(f"{self.db_type.upper()}: Created index '{idx_name}' on '{table_name}'.")
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                logger.warning(f"{self.db_type.upper()}: Could not create index '{idx_name}' on '{table_name}': {e}")
            finally:
                cur.close()

    def _index_exists(self, index_name: str, table_name: str) -> bool:
        """Check whether an index already exists in the database."""
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
                    "SELECT COUNT(*) FROM pg_indexes WHERE tablename = %s AND indexname = %s",
                    (table_name, index_name)
                )
            elif self.db_type == 'firebird':
                cur.execute(
                    "SELECT COUNT(*) FROM RDB$INDICES WHERE RDB$INDEX_NAME = ?",
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
        elif self.db_type == 'firebird':
            return f'"{identifier}"'
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
                # Check for exact table name (case sensitive if quoted)
                cur.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?", (table_name,))
            else:
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name = %s", (table_name,))
            return cur.fetchone() is not None
        finally:
            cur.close()

    def _create_table(self, table_name, definition):
        logger.info(f"{self.db_type.upper()}: Creating table '{table_name}' if not exists...")

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

        # Use IF NOT EXISTS at DB level — safe for concurrent workers (Gunicorn etc.)
        if self.db_type == 'firebird':
            # Firebird does not support CREATE TABLE IF NOT EXISTS — wrap in existence check
            # under an exception handler; concurrent duplicate is harmless
            create_sql = f"CREATE TABLE {quoted_table} ({', '.join(columns_def)})"
        else:
            create_sql = f"CREATE TABLE IF NOT EXISTS {quoted_table} ({', '.join(columns_def)})"

        if self.db_type == 'mysql' and "engine_mysql" in definition:
            create_sql += f" {definition['engine_mysql']}"

        cur = self.conn.cursor()
        try:
            cur.execute(create_sql)
            self.conn.commit()
            # Indexes are NOT created here — _ensure_indexes() in ensure_schema() handles
            # them after all tables exist, idempotently and safely on every re-run.
            logger.info(f"{self.db_type.upper()}: Table '{table_name}' ready.")
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            # On Firebird (no IF NOT EXISTS), a concurrent worker may have created the
            # table between our existence check and CREATE — that is fine, just log it.
            if self._table_exists(table_name):
                logger.info(f"{self.db_type.upper()}: Table '{table_name}' already exists (created by another worker).")
            else:
                logger.error(f"{self.db_type.upper()}: Failed to create table '{table_name}': {e}")
                raise
        finally:
            cur.close()

    def _update_table(self, table_name, definition):
        # Check for missing columns
        existing_columns = self._get_existing_columns(table_name)

        type_suffix = self._get_type_suffix()
        for col in definition["columns"]:
            if col["name"] not in existing_columns:
                logger.info(f"{self.db_type.upper()}: Adding missing column '{col['name']}' to table '{table_name}'...")
                col_type_key = f"type_{type_suffix}"
                col_type = col[col_type_key]

                quoted_table = self._quote_identifier(table_name)
                quoted_col = self._quote_identifier(col['name'])

                # Firebird uses ADD without COLUMN keyword
                if self.db_type == 'firebird':
                    alter_sql = f"ALTER TABLE {quoted_table} ADD {quoted_col} {col_type}"
                else:
                    alter_sql = f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} {col_type}"

                cur = self.conn.cursor()
                try:
                    cur.execute(alter_sql)
                    self.conn.commit()
                finally:
                    cur.close()

        # Drop columns not in the schema definition
        desired_columns = {col["name"] for col in definition["columns"]}
        extra_columns = existing_columns - desired_columns
        if extra_columns:
            for col_name in sorted(extra_columns):
                logger.info(f"{self.db_type.upper()}: Dropping extra column '{col_name}' from table '{table_name}'...")
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
                    logger.warning(f"{self.db_type.upper()}: Failed to drop column '{col_name}' on '{table_name}': {exc}")
                finally:
                    cur.close()

    def _get_existing_columns(self, table_name):
        cur = self.conn.cursor()
        try:
            if self.db_type == 'mysql':
                cur.execute(f"SHOW COLUMNS FROM {table_name}")
                # MySQL returns (Field, Type, Null, Key, Default, Extra)
                return {row[0] for row in cur.fetchall()}
            elif self.db_type == 'firebird':
                # Check for exact column name
                cur.execute("SELECT TRIM(RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = ?",
                            (table_name,))
                return {row[0].lower() for row in cur.fetchall()}
            else:
                # PostgreSQL
                cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'")
                return {row[0] for row in cur.fetchall()}
        finally:
            cur.close()
