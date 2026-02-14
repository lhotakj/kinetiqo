import logging

logger = logging.getLogger("kinetiqo")

# Define the schema in a database-agnostic way where possible, 
# or provide specific types for each dialect.
SCHEMA_DEFINITION = {
    "activities": {
        "columns": [
            {"name": "timestamp", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE"},
            {"name": "activity_id", "type_mysql": "BIGINT PRIMARY KEY", "type_pg": "BIGINT PRIMARY KEY"},
            {"name": "name", "type_mysql": "TEXT", "type_pg": "TEXT"},
            {"name": "sport", "type_mysql": "VARCHAR(255)", "type_pg": "TEXT"},
            {"name": "athlete_id", "type_mysql": "BIGINT", "type_pg": "BIGINT"},
            {"name": "distance", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "moving_time", "type_mysql": "INTEGER", "type_pg": "INTEGER"},
            {"name": "elapsed_time", "type_mysql": "INTEGER", "type_pg": "INTEGER"},
            {"name": "total_elevation_gain", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "average_speed", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "max_speed", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "average_heartrate", "type_mysql": "INTEGER", "type_pg": "INTEGER"},
            {"name": "max_heartrate", "type_mysql": "INTEGER", "type_pg": "INTEGER"},
            {"name": "average_cadence", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"}
        ],
        "indexes": [
            "CREATE INDEX idx_activities_timestamp ON activities (timestamp DESC)"
        ],
        "engine_mysql": "ENGINE=InnoDB"
    },
    "streams": {
        "columns": [
            {"name": "timestamp", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE"},
            {"name": "activity_id", "type_mysql": "BIGINT", "type_pg": "BIGINT"},
            {"name": "sport", "type_mysql": "VARCHAR(255)", "type_pg": "TEXT"},
            {"name": "athlete_id", "type_mysql": "BIGINT", "type_pg": "BIGINT"},
            {"name": "lat", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "lng", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "altitude", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "heartrate", "type_mysql": "INTEGER", "type_pg": "INTEGER"},
            {"name": "cadence", "type_mysql": "INTEGER", "type_pg": "INTEGER"},
            {"name": "speed", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"},
            {"name": "distance", "type_mysql": "DOUBLE PRECISION", "type_pg": "DOUBLE PRECISION"}
        ],
        "constraints": [
            {
                "name": "fk_activity",
                "def_mysql": "CONSTRAINT fk_activity FOREIGN KEY(activity_id) REFERENCES activities(activity_id) ON DELETE CASCADE",
                "def_pg": "CONSTRAINT fk_activity FOREIGN KEY(activity_id) REFERENCES activities(activity_id) ON DELETE CASCADE"
            }
        ],
        "indexes": [
            "CREATE INDEX idx_streams_activity_id ON streams (activity_id)",
            "CREATE INDEX idx_streams_timestamp ON streams (timestamp)"
        ],
        "engine_mysql": "ENGINE=InnoDB"
    },
    "logs": {
        "columns": [
            {"name": "id", "type_mysql": "BIGINT AUTO_INCREMENT PRIMARY KEY", "type_pg": "SERIAL PRIMARY KEY"},
            {"name": "timestamp", "type_mysql": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"},
            {"name": "added", "type_mysql": "BIGINT", "type_pg": "BIGINT"},
            {"name": "removed", "type_mysql": "BIGINT", "type_pg": "BIGINT"},
            {"name": "trigger_source", "type_mysql": "VARCHAR(50)", "type_pg": "TEXT"},
            {"name": "action", "type_mysql": "VARCHAR(50)", "type_pg": "TEXT"},
            {"name": "user", "type_mysql": "VARCHAR(100) DEFAULT '-'", "type_pg": "TEXT DEFAULT '-'"},
            {"name": "success", "type_mysql": "BOOLEAN", "type_pg": "BOOLEAN"}
        ],
        "indexes": [
            "CREATE INDEX idx_logs_timestamp ON logs (timestamp DESC)"
        ],
        "engine_mysql": "ENGINE=InnoDB"
    }
}

class SchemaManager:
    def __init__(self, conn, db_type):
        self.conn = conn
        self.db_type = db_type  # 'mysql' or 'postgresql'

    def ensure_schema(self):
        """Ensures the database schema matches the definition."""
        logger.info(f"{self.db_type.upper()}: Checking schema consistency...")
        
        for table_name, definition in SCHEMA_DEFINITION.items():
            self._ensure_table(table_name, definition)

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
        with self.conn.cursor() as cur:
            if self.db_type == 'mysql':
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s", (table_name,))
            else:
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name = %s", (table_name,))
            return cur.fetchone() is not None

    def _create_table(self, table_name, definition):
        logger.info(f"{self.db_type.upper()}: Creating table '{table_name}'...")
        
        columns_def = []
        for col in definition["columns"]:
            col_type = col[f"type_{'mysql' if self.db_type == 'mysql' else 'pg'}"]
            quoted_name = self._quote_identifier(col['name'])
            columns_def.append(f"{quoted_name} {col_type}")

        if "constraints" in definition:
            for const in definition["constraints"]:
                const_def = const[f"def_{'mysql' if self.db_type == 'mysql' else 'pg'}"]
                columns_def.append(const_def)

        create_sql = f"CREATE TABLE {self._quote_identifier(table_name)} ({', '.join(columns_def)})"
        
        if self.db_type == 'mysql' and "engine_mysql" in definition:
            create_sql += f" {definition['engine_mysql']}"

        with self.conn.cursor() as cur:
            cur.execute(create_sql)
            
            # Create indexes
            if "indexes" in definition:
                for idx_sql in definition["indexes"]:
                    cur.execute(idx_sql)
        
        self.conn.commit()
        logger.info(f"{self.db_type.upper()}: Table '{table_name}' created.")

    def _update_table(self, table_name, definition):
        # Check for missing columns
        existing_columns = self._get_existing_columns(table_name)
        
        for col in definition["columns"]:
            if col["name"] not in existing_columns:
                logger.info(f"{self.db_type.upper()}: Adding missing column '{col['name']}' to table '{table_name}'...")
                col_type = col[f"type_{'mysql' if self.db_type == 'mysql' else 'pg'}"]
                
                quoted_table = self._quote_identifier(table_name)
                quoted_col = self._quote_identifier(col['name'])
                
                alter_sql = f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} {col_type}"
                
                with self.conn.cursor() as cur:
                    cur.execute(alter_sql)
                self.conn.commit()

    def _get_existing_columns(self, table_name):
        with self.conn.cursor() as cur:
            if self.db_type == 'mysql':
                cur.execute(f"SHOW COLUMNS FROM {table_name}")
                # MySQL returns (Field, Type, Null, Key, Default, Extra)
                return {row[0] for row in cur.fetchall()}
            else:
                # PostgreSQL
                cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'")
                return {row[0] for row in cur.fetchall()}
