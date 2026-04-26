import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any, Tuple

import firebird.driver
from firebird.driver import tpb, Isolation, TraAccessMode
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository
from kinetiqo.db.schema import SchemaManager

logger = logging.getLogger("kinetiqo")


class FirebirdRepository(DatabaseRepository):
    # Minimum seconds between active connection probes.  Within this window
    # only a cheap ``is_closed()`` check is performed.  The web layer creates
    # a fresh connection per request (lifetime < 1 s), so the probe is
    # effectively skipped for every web call.  The CLI, which keeps a single
    # repository alive for minutes, will re-probe after the interval expires.
    _VERIFY_INTERVAL: float = 30.0

    def __init__(self, config: Config):
        self.config = config
        self._last_verified: float = 0.0
        try:
            self.conn = self._connect()
            self._last_verified = time.monotonic()
        except Exception as err:
            logger.warning(f"Cannot connect to Firebird: {err}")
            sys.exit(1)

        try:
            self._ensure_database()
        except Exception as err:
            logger.warning(f"Cannot ensure database: {err}")
            sys.exit(1)

    def _validate_timestamp(self, timestamp: datetime) -> datetime:
        """Validate and fix timestamps that are before Unix epoch."""
        if timestamp.timestamp() <= 0:
            return datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
        return timestamp

    def _connect(self):
        """Helper to connect to the Firebird database."""
        try:
            dsn = f"{self.config.firebird_host}/{self.config.firebird_port}:{self.config.firebird_database}"

            conn = firebird.driver.connect(
                database=dsn,
                user=self.config.firebird_user,
                password=self.config.firebird_password,
                charset='UTF8'
            )

            # READ COMMITTED RECORD VERSION ensures we see the latest committed data
            # without the overhead of SNAPSHOT isolation.
            rc_tpb = tpb(isolation=Isolation.READ_COMMITTED_RECORD_VERSION,
                         access_mode=TraAccessMode.WRITE)
            conn.main_transaction.default_tpb = rc_tpb

            return conn
        except Exception as e:
            logger.error(f"Failed to connect to Firebird: {e}")
            raise

    def _ensure_connected(self):
        """Verify the connection is alive; transparently reconnect if not.

        Uses a time-based check to avoid redundant network round-trips.
        The connection is only actively probed when more than
        ``_VERIFY_INTERVAL`` seconds have elapsed since the last successful
        verification.  For per-request web connections (lifetime < 1 s)
        the probe is effectively skipped — only a cheap ``is_closed()``
        check runs.
        """
        now = time.monotonic()
        if (now - self._last_verified) < self._VERIFY_INTERVAL:
            # Connection was recently verified — skip the expensive probe.
            if not self.conn.is_closed():
                return
        try:
            if self.conn.is_closed():
                raise ConnectionError("Connection is closed")
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM RDB$DATABASE")
                cur.fetchone()
            # Do NOT commit — the read-only check doesn't need it and
            # commit() adds an extra network round-trip.
            self._last_verified = now
        except Exception:
            logger.warning("Firebird connection lost, reconnecting...")
            try:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = self._connect()
                self._last_verified = time.monotonic()
            except Exception as e:
                logger.error(f"Failed to reconnect to Firebird: {e}")
                raise

    def _ensure_database(self):
        """Ensures the target database exists."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM RDB$DATABASE")
                cur.fetchone()
        except Exception as e:
            logger.warning(f"Database check failed: {e}")
            try:
                if self.conn:
                    try:
                        self.conn.close()
                    except:
                        pass
                dsn = f"{self.config.firebird_host}/{self.config.firebird_port}:{self.config.firebird_database}"
                firebird.driver.create_database(
                    f"CREATE DATABASE '{dsn}' USER '{self.config.firebird_user}' PASSWORD '{self.config.firebird_password}'"
                )
                logger.info(f"Database '{self.config.firebird_database}' created successfully.")
                self.conn = self._connect()
            except Exception as create_err:
                logger.error(f"Could not create database: {create_err}")
                sys.exit(1)

    def get_firebird_version(self) -> str:
        """Get the Firebird version string."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("SELECT rdb$get_context('SYSTEM', 'ENGINE_VERSION') FROM rdb$database")
            result = cur.fetchone()
            return result[0] if result else "Unknown"

    def _migrate_blob_columns(self):
        """Convert BLOB SUB_TYPE TEXT columns to VARCHAR for performance.

        Firebird stores BLOBs out-of-line on separate pages.  The pure-Python
        ``firebird-driver`` must make 3 extra protocol round-trips per row to
        fetch each BLOB value (open → read segments → close).  With 2 000
        activities loaded by DataTables this adds ~6 000 round-trips (~30 s)
        **just for the name field**.

        Converting to ``VARCHAR(500)`` stores the value inline on the data
        page so it is returned in the normal row-fetch buffer with zero
        extra protocol calls.

        The migration uses a temporary column because Firebird does not
        support ``ALTER COLUMN … TYPE`` from BLOB to VARCHAR directly.
        """
        migrations = [
            ("activities", "name", "VARCHAR(500)"),
        ]
        for table, column, new_type in migrations:
            try:
                with self.conn.cursor() as cur:
                    # Check current field type: RDB$FIELD_TYPE 261 = BLOB
                    cur.execute("""
                        SELECT f.RDB$FIELD_TYPE
                        FROM RDB$RELATION_FIELDS rf
                        JOIN RDB$FIELDS f ON rf.RDB$FIELD_SOURCE = f.RDB$FIELD_NAME
                        WHERE TRIM(rf.RDB$RELATION_NAME) = ?
                          AND TRIM(rf.RDB$FIELD_NAME) = ?
                    """, (table, column))
                    row = cur.fetchone()
                    if not row or row[0] != 261:
                        # Not a BLOB — nothing to migrate.
                        continue

                    logger.info(
                        f"Migrating {table}.{column} from BLOB to {new_type} "
                        f"(eliminates per-row blob round-trips)..."
                    )
                    tmp = f"{column}_tmp"
                    cur.execute(
                        f'ALTER TABLE "{table}" ADD "{tmp}" {new_type}'
                    )
                    self.conn.commit()

                    cur.execute(
                        f'UPDATE "{table}" SET "{tmp}" = CAST("{column}" AS {new_type})'
                    )
                    self.conn.commit()

                    cur.execute(f'ALTER TABLE "{table}" DROP "{column}"')
                    self.conn.commit()

                    cur.execute(
                        f'ALTER TABLE "{table}" ALTER COLUMN "{tmp}" TO "{column}"'
                    )
                    self.conn.commit()
                    logger.info(f"Migrated {table}.{column} to {new_type} successfully.")
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                logger.warning(
                    f"Could not migrate {table}.{column} from BLOB to VARCHAR: {e}. "
                    f"Queries will use CAST as a fallback."
                )

    def initialize_schema(self):
        """Create or update the database schema."""
        self._ensure_connected()
        schema_manager = SchemaManager(self.conn, 'firebird')

        with self.conn.cursor() as cur:
            try:
                cur.execute("CREATE SEQUENCE logs_id_seq")
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

            try:
                cur.execute("""
                    CREATE GLOBAL TEMPORARY TABLE "gtt_activity_ids" (
                        "activity_id" BIGINT NOT NULL PRIMARY KEY
                    ) ON COMMIT DELETE ROWS
                """)
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

        schema_manager.ensure_schema()

        # --- Migration: BLOB → VARCHAR for the name column ----------------
        # Firebird stores BLOBs out-of-line.  The pure-Python firebird-driver
        # must open / read-segments / close each BLOB value individually,
        # adding ~3 network round-trips per row.  With 2 000 activities this
        # means ~6 000 extra round-trips just for the name field.
        # Converting to VARCHAR(500) stores the value inline on the data
        # page so it arrives with the row fetch buffer — zero extra trips.
        self._migrate_blob_columns()

        with self.conn.cursor() as cur:
            try:
                cur.execute("""
                    CREATE TRIGGER logs_bi FOR "logs"
                    ACTIVE BEFORE INSERT POSITION 0
                    AS
                    BEGIN
                        IF (NEW."id" IS NULL) THEN
                            NEW."id" = NEXT VALUE FOR logs_id_seq;
                    END
                """)
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

    def flightcheck(self) -> bool:
        """Perform a health check on the database."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            try:
                cur.execute("SELECT 1 FROM RDB$DATABASE")
                cur.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = 'activities'")
                if cur.fetchone()[0] == 0:
                    return False
                return True
            except Exception:
                return False

    def get_latest_activity_time(self) -> Optional[int]:
        """Get the start timestamp of the most recent activity by date."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute('SELECT MAX("start_date") FROM "activities"')
            result = cur.fetchone()
            if result and result[0]:
                dt = result[0]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = int(dt.timestamp())
                logger.debug(f"Latest activity start time: {ts}")
                return ts
            return None

    def get_synced_activity_ids(self) -> Set[str]:
        """Get all activity IDs already in the database."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute('SELECT "activity_id" FROM "activities"')
            return {str(row[0]) for row in cur.fetchall()}

    def get_synced_activity_ids_since(self, after_epoch: int) -> Set[str]:
        """Get activity IDs whose start_date is at or after *after_epoch*."""
        self._ensure_connected()
        dt = datetime.fromtimestamp(after_epoch, tz=timezone.utc)
        with self.conn.cursor() as cur:
            cur.execute('SELECT "activity_id" FROM "activities" WHERE "start_date" >= ?', (dt,))
            return {str(row[0]) for row in cur.fetchall()}

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT FIRST {limit}
                    "activity_id" as id,
                    CAST("name" AS VARCHAR(500)) as "name",
                    "sport" as type,
                    "distance",
                    "moving_time",
                    "total_elevation_gain",
                    "start_date",
                    "average_speed",
                    "average_heartrate",
                    "average_watts",
                    "max_watts",
                    "weighted_average_watts",
                    "device_watts",
                    "calories",
                    "kilojoules",
                    "achievement_count",
                    "pr_count",
                    "suffer_score",
                    "average_temp",
                    "elev_high",
                    "elev_low",
                    "gear_id",
                    "has_heartrate",
                    "workout_type"
                FROM "activities" 
                ORDER BY "start_date" DESC
            """)

            activities = []
            for row in cur.fetchall():
                activity = {
                    'id': row[0],
                    'name': row[1],
                    'type': row[2],
                    'distance': row[3],
                    'moving_time': row[4],
                    'total_elevation_gain': row[5],
                    'start_date': row[6].isoformat() if isinstance(row[6], datetime) else row[6],
                    'average_speed': row[7],
                    'average_heartrate': row[8],
                    'average_watts': row[9],
                    'max_watts': row[10],
                    'weighted_average_watts': row[11],
                    'device_watts': row[12],
                    'calories': row[13],
                    'kilojoules': row[14],
                    'achievement_count': row[15],
                    'pr_count': row[16],
                    'suffer_score': row[17],
                    'average_temp': row[18],
                    'elev_high': row[19],
                    'elev_low': row[20],
                    'gear_id': row[21],
                    'has_heartrate': row[22],
                    'workout_type': row[23]
                }
                activities.append(activity)
            return activities

    def get_activities_web(self, limit=10, offset=0, sort_by='start_date', sort_order='DESC', types=None,
                           start_date=None, end_date=None):
        """Fetch activities with pagination and sorting from Firebird"""
        self._ensure_connected()
        allowed_columns = ['start_date', 'activity_id', 'name', 'sport', 'distance', 'moving_time',
                           'total_elevation_gain', 'average_speed', 'average_heartrate', 'average_watts', 'max_watts']
        if sort_by not in allowed_columns:
            sort_by = 'start_date'

        sort_by = f'"{sort_by}"'
        sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['?'] * len(types))
            where_conditions.append(f'"sport" IN ({placeholders})')
            params.extend(types)

        if start_date:
            where_conditions.append('"start_date" >= ?')
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date)
            params.append(start_date)

        if end_date:
            where_conditions.append('"start_date" <= ?')
            if isinstance(end_date, str):
                if len(end_date) == 10:
                    end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
                else:
                    end_date = datetime.fromisoformat(end_date)
            params.append(end_date)

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        query = f"""
            SELECT FIRST {limit} SKIP {offset}
                "activity_id" as id,
                CAST("name" AS VARCHAR(500)) as "name",
                "sport" as type,
                "distance",
                "moving_time",
                "total_elevation_gain",
                "start_date",
                "average_speed",
                "average_heartrate",
                "average_watts",
                "max_watts",
                "weighted_average_watts",
                "device_watts",
                "calories",
                "kilojoules",
                "achievement_count",
                "pr_count",
                "suffer_score",
                "average_temp",
                "elev_high",
                "elev_low",
                "gear_id",
                "has_heartrate",
                "workout_type",
                "max_speed"
            FROM "activities"
            {where_clause}
            ORDER BY {sort_by} {sort_order}
        """

        with self.conn.cursor() as cur:
            cur.execute(query, tuple(params))

            activities = []
            for row in cur.fetchall():
                activity = {
                    'id': row[0],
                    'name': row[1],
                    'type': row[2],
                    'distance': row[3],
                    'moving_time': row[4],
                    'total_elevation_gain': row[5],
                    'start_date': row[6].isoformat() if isinstance(row[6], datetime) else row[6],
                    'average_speed': row[7],
                    'average_heartrate': row[8],
                    'average_watts': row[9],
                    'max_watts': row[10],
                    'weighted_average_watts': row[11],
                    'device_watts': row[12],
                    'calories': row[13],
                    'kilojoules': row[14],
                    'achievement_count': row[15],
                    'pr_count': row[16],
                    'suffer_score': row[17],
                    'average_temp': row[18],
                    'elev_high': row[19],
                    'elev_low': row[20],
                    'gear_id': row[21],
                    'has_heartrate': row[22],
                    'workout_type': row[23],
                    'max_speed': row[24]
                }
                activities.append(activity)
            return activities

    def get_activities_by_ids(self, activity_ids: List[str]) -> List[Dict[str, Any]]:
        """Get a list of activities by their IDs."""
        if not activity_ids:
            return []

        self._ensure_connected()
        int_ids = [int(aid) for aid in activity_ids]
        placeholders = ', '.join(['?'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    "activity_id" as id,
                    CAST("name" AS VARCHAR(500)) as "name",
                    "sport" as type,
                    "distance",
                    "moving_time",
                    "total_elevation_gain",
                    "start_date",
                    "average_speed",
                    "average_heartrate",
                    "average_watts",
                    "max_watts",
                    "weighted_average_watts",
                    "device_watts",
                    "calories",
                    "kilojoules",
                    "achievement_count",
                    "pr_count",
                    "suffer_score",
                    "average_temp",
                    "elev_high",
                    "elev_low",
                    "gear_id",
                    "has_heartrate",
                    "workout_type"
                FROM "activities" 
                WHERE "activity_id" IN ({placeholders})
                ORDER BY "start_date" DESC
            """, int_ids)

            activities = []
            for row in cur.fetchall():
                activity = {
                    'id': row[0],
                    'name': row[1],
                    'type': row[2],
                    'distance': row[3],
                    'moving_time': row[4],
                    'total_elevation_gain': row[5],
                    'start_date': row[6].isoformat() if isinstance(row[6], datetime) else row[6],
                    'average_speed': row[7],
                    'average_heartrate': row[8],
                    'average_watts': row[9],
                    'max_watts': row[10],
                    'weighted_average_watts': row[11],
                    'device_watts': row[12],
                    'calories': row[13],
                    'kilojoules': row[14],
                    'achievement_count': row[15],
                    'pr_count': row[16],
                    'suffer_score': row[17],
                    'average_temp': row[18],
                    'elev_high': row[19],
                    'elev_low': row[20],
                    'gear_id': row[21],
                    'has_heartrate': row[22],
                    'workout_type': row[23]
                }
                activities.append(activity)
            return activities

    def get_activities_totals(self, types=None, start_date=None, end_date=None) -> Dict[str, float]:
        """Get totals for distance, elevation, and moving_time for the filtered activities."""
        self._ensure_connected()
        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['?'] * len(types))
            where_conditions.append(f'"sport" IN ({placeholders})')
            params.extend(types)

        if start_date:
            where_conditions.append('"start_date" >= ?')
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date)
            params.append(start_date)

        if end_date:
            where_conditions.append('"start_date" <= ?')
            if isinstance(end_date, str):
                if len(end_date) == 10:
                    end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
                else:
                    end_date = datetime.fromisoformat(end_date)
            params.append(end_date)

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        query = f"""
            SELECT COALESCE(SUM("distance"), 0) as total_distance,
                COALESCE(SUM("total_elevation_gain"), 0) as total_elevation,
                COALESCE(SUM("moving_time"), 0) as total_moving_time
            FROM "activities"
            {where_clause}
        """

        with self.conn.cursor() as cur:
            cur.execute(query, tuple(params))
            result = cur.fetchone()
            return {
                'total_distance': result[0] if result else 0,
                'total_elevation': result[1] if result else 0,
                'total_moving_time': result[2] if result else 0
            }

    def count_activities(self, types=None):
        """Get total count of activities"""
        self._ensure_connected()
        where_clause = ""
        params = []
        if types:
            placeholders = ', '.join(['?'] * len(types))
            where_clause = f'WHERE "sport" IN ({placeholders})'
            params.extend(types)

        with self.conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "activities" {where_clause}', tuple(params))
            result = cur.fetchone()
            return result[0] if result else 0

    def write_activity(self, activity: dict):
        """Write activity metadata to Firebird."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            def to_int(val):
                if val is None:
                    return None
                return int(val)

            cur.execute(
                'UPDATE OR INSERT INTO "activities" ("start_date", "activity_id", "name", "sport", "athlete_id", "distance", "moving_time", "elapsed_time", "total_elevation_gain", "average_speed", "max_speed", "average_heartrate", "max_heartrate", "average_cadence", "average_watts", "max_watts", "achievement_count", "average_temp", "calories", "device_watts", "elev_high", "elev_low", "gear_id", "has_heartrate", "kilojoules", "pr_count", "suffer_score", "weighted_average_watts", "workout_type") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) MATCHING ("activity_id")',
                (
                    self._validate_timestamp(datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))),
                    int(activity["id"]),
                    activity.get("name"),
                    activity.get("sport_type"),
                    int(activity["athlete"]["id"]),
                    float(activity.get("distance", 0.0)),
                    int(activity.get("moving_time", 0)),
                    int(activity.get("elapsed_time", 0)),
                    float(activity.get("total_elevation_gain", 0.0)),
                    float(activity.get("average_speed", 0.0)),
                    float(activity.get("max_speed", 0.0)),
                    to_int(activity.get("average_heartrate")),
                    to_int(activity.get("max_heartrate")),
                    activity.get("average_cadence"),
                    activity.get("average_watts"),
                    activity.get("max_watts"),
                    to_int(activity.get("achievement_count")),
                    activity.get("average_temp"),
                    activity.get("calories"),
                    to_int(activity.get("device_watts")) if activity.get("device_watts") is not None else None,
                    activity.get("elev_high"),
                    activity.get("elev_low"),
                    activity.get("gear_id"),
                    to_int(activity.get("has_heartrate")) if activity.get("has_heartrate") is not None else None,
                    activity.get("kilojoules"),
                    to_int(activity.get("pr_count")),
                    to_int(activity.get("suffer_score")),
                    activity.get("weighted_average_watts"),
                    to_int(activity.get("workout_type"))
                )
            )
            self.conn.commit()

    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to Firebird."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM "streams" WHERE "activity_id" = ?', (int(activity["id"]),))
            start_date = self._validate_timestamp(datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00")))

            rows = []
            for i, t in enumerate(streams.get("time", {}).get("data", [])):
                lat, lng = streams.get("latlng", {}).get("data", [])[i] if i < len(
                    streams.get("latlng", {}).get("data", [])) else (None, None)

                def get_val(key, type_func=lambda x: x):
                    data = streams.get(key, {}).get("data", [])
                    if i < len(data):
                        val = data[i]
                        return type_func(val) if val is not None else None
                    return None

                rows.append((
                    start_date + timedelta(seconds=t),
                    int(activity["id"]),
                    activity["sport_type"],
                    int(activity["athlete"]["id"]),
                    float(lat) if lat is not None else None,
                    float(lng) if lng is not None else None,
                    get_val("altitude", float),
                    get_val("heartrate", int),
                    get_val("cadence", int),
                    get_val("velocity_smooth", float),
                    get_val("distance", float),
                    get_val("watts", float),
                    get_val("temp", float),
                    get_val("grade_smooth", float),
                    get_val("moving", lambda v: 1 if v else 0)
                ))

            cur.executemany(
                'INSERT INTO "streams" ("ts", "activity_id", "sport", "athlete_id", "lat", "lng", "altitude", "heartrate", "cadence", "speed", "distance", "watts", "temp", "grade_smooth", "moving") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                rows
            )
            self.conn.commit()

    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from Firebird."""
        self._ensure_connected()
        aid = int(activity_id)
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM "activities" WHERE "activity_id" = ?', (aid,))
            logger.info(f"Deleted activity {aid} and its streams.")
            self.conn.commit()

    def delete_activities(self, activity_ids: List[str]):
        """Delete multiple activities and their streams from Firebird."""
        if not activity_ids:
            return
        self._ensure_connected()
        with self.conn.cursor() as cur:
            placeholders = ','.join(['?'] * len(activity_ids))
            cur.execute(f'DELETE FROM "activities" WHERE "activity_id" IN ({placeholders})',
                        [int(aid) for aid in activity_ids])
            self.conn.commit()

    # -----------------------------------------------------------------
    # Chunked IN-clause helpers
    # -----------------------------------------------------------------
    # Firebird's Global Temporary Tables (GTT) have zero persistent
    # statistics — RDB$RECORD_COUNT is always 0.  The cost-based
    # optimizer therefore treats a GTT JOIN as if the driving table is
    # empty, and falls back to scanning the entire streams index (7 M+
    # rows) while probing the GTT per row.  This is catastrophically
    # slow for the watts / GPS queries.
    #
    # Replacing the GTT JOIN with a plain ``IN (?, ?, …)`` clause gives
    # the optimizer explicit cardinality information.  It can then do
    # targeted index range scans on ``idx_streams_activity_ts_watts``
    # per activity_id — the same plan MySQL uses with its pure-Python
    # driver, which is proven fast.
    #
    # _IN_CHUNK_SIZE caps the number of parameters per query to stay
    # well within Firebird's protocol limits (~1 500 params) while
    # keeping the number of round-trips minimal.
    # -----------------------------------------------------------------
    _IN_CHUNK_SIZE: int = 500

    def get_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get GPS streams (lat, lng) for a list of activity IDs."""
        if not activity_ids:
            return {}

        self._ensure_connected()
        result: Dict[str, List[Dict[str, Any]]] = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            cur.prefetch = 10000
            for i in range(0, len(int_ids), self._IN_CHUNK_SIZE):
                chunk = int_ids[i:i + self._IN_CHUNK_SIZE]
                placeholders = ', '.join(['?'] * len(chunk))
                cur.execute(f"""
                    SELECT "activity_id", "lat", "lng"
                    FROM "streams"
                    WHERE "activity_id" IN ({placeholders})
                      AND "lat" IS NOT NULL
                      AND "lng" IS NOT NULL
                    ORDER BY "activity_id", "ts"
                """, chunk)

                for row in cur:
                    aid = str(row[0])
                    if aid not in result:
                        result[aid] = []
                    result[aid].append({
                        'lat': float(row[1]),
                        'lng': float(row[2])
                    })

        return result

    def get_streams_coords_for_activities(self, activity_ids: List[str]) -> Dict[str, List[List[float]]]:
        """Get GPS coordinate arrays for a list of activity IDs as compact [lat, lng] pairs."""
        if not activity_ids:
            return {}

        self._ensure_connected()
        result: Dict[str, List[List[float]]] = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            cur.prefetch = 10000
            for i in range(0, len(int_ids), self._IN_CHUNK_SIZE):
                chunk = int_ids[i:i + self._IN_CHUNK_SIZE]
                placeholders = ', '.join(['?'] * len(chunk))
                cur.execute(f"""
                    SELECT "activity_id", "lat", "lng"
                    FROM "streams"
                    WHERE "activity_id" IN ({placeholders})
                      AND "lat" IS NOT NULL
                      AND "lng" IS NOT NULL
                    ORDER BY "activity_id", "ts"
                """, chunk)

                for row in cur:
                    aid = str(row[0])
                    if aid not in result:
                        result[aid] = []
                    result[aid].append([float(row[1]), float(row[2])])

        return result

    def get_streams_bounds_for_activities(self, activity_ids: List[str]) -> Optional[Tuple[float, float, float, float]]:
        """Get GPS bounding box for a list of activity IDs via SQL aggregation."""
        if not activity_ids:
            return None

        self._ensure_connected()
        int_ids = [int(aid) for aid in activity_ids]
        min_lat = min_lng = float('inf')
        max_lat = max_lng = float('-inf')
        found = False

        with self.conn.cursor() as cur:
            for i in range(0, len(int_ids), self._IN_CHUNK_SIZE):
                chunk = int_ids[i:i + self._IN_CHUNK_SIZE]
                placeholders = ', '.join(['?'] * len(chunk))
                cur.execute(f"""
                    SELECT MIN("lat"), MIN("lng"), MAX("lat"), MAX("lng")
                    FROM "streams"
                    WHERE "activity_id" IN ({placeholders})
                      AND "lat" IS NOT NULL
                      AND "lng" IS NOT NULL
                """, chunk)
                row = cur.fetchone()
                if row and row[0] is not None:
                    found = True
                    min_lat = min(min_lat, float(row[0]))
                    min_lng = min(min_lng, float(row[1]))
                    max_lat = max(max_lat, float(row[2]))
                    max_lng = max(max_lng, float(row[3]))

        return (min_lat, min_lng, max_lat, max_lng) if found else None

    def get_activity_name(self, activity_id: str) -> Optional[str]:
        """Get the name of an activity by its ID."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute('SELECT CAST("name" AS VARCHAR(500)) FROM "activities" WHERE "activity_id" = ?', (int(activity_id),))
            row = cur.fetchone()
            return row[0] if row else None

    def log_sync(self, added: int, removed: int, trigger: str, success: bool, action: str, user: str):
        """Log the result of a sync operation."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "logs" ("added", "removed", "trigger_source", "success", "action", "user") VALUES (?, ?, ?, ?, ?, ?)',
                (added, removed, trigger, 1 if success else 0, action, user)
            )
            self.conn.commit()

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest sync logs."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT FIRST {limit}
                    "created_at", "added", "removed", "trigger_source", "success", "action", "user"
                FROM "logs"
                ORDER BY "created_at" DESC
            """)

            logs = []
            for row in cur.fetchall():
                log = {
                    'timestamp': row[0].isoformat() if isinstance(row[0], datetime) else row[0],
                    'added': row[1],
                    'removed': row[2],
                    'trigger_source': row[3],
                    'success': bool(row[4]),
                    'action': row[5],
                    'user': row[6]
                }
                logs.append(log)
            return logs


    def get_watts_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[float]]:
        """Get watts time-series for a list of activity IDs.

        Uses chunked ``IN (?, …)`` clauses instead of a GTT JOIN so that
        Firebird's optimizer has explicit cardinality information and can
        do targeted index range scans on ``idx_streams_activity_ts_watts``
        per activity_id.
        """
        if not activity_ids:
            return {}

        self._ensure_connected()
        result: Dict[str, List[float]] = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            cur.prefetch = 10000
            for i in range(0, len(int_ids), self._IN_CHUNK_SIZE):
                chunk = int_ids[i:i + self._IN_CHUNK_SIZE]
                placeholders = ', '.join(['?'] * len(chunk))
                cur.execute(f"""
                    SELECT "activity_id", "watts"
                    FROM "streams"
                    WHERE "activity_id" IN ({placeholders})
                      AND "watts" IS NOT NULL
                    ORDER BY "activity_id", "ts"
                """, chunk)

                for row in cur:
                    aid = str(row[0])
                    if aid not in result:
                        result[aid] = []
                    result[aid].append(float(row[1]))

        return result

    def get_best_power_per_activity(
        self,
        activity_ids: List[str],
        duration_seconds: int,
        min_total_samples: int = 0,
    ) -> Dict[str, float]:
        """Compute best rolling-average power per activity.

        Uses the **Python sliding-window** path (same as MySQL): fetches raw
        watts via ``get_watts_streams_for_activities`` and computes the O(N)
        rolling maximum in Python with ``compute_best_power_per_activity``.

        **Why not SQL window functions?**
        Firebird **materialises CTEs** into temporary tables.  The cumulative-
        SUM + LAG approach generates two intermediate result sets of ~1.8 M
        rows each, which Firebird writes to temp storage and reads back.  On a
        typical setup this takes 10–15 s — slower than the ~5 s needed to
        transfer the raw watts through the pure-Python ``firebird-driver`` and
        compute the sliding window in Python.

        The ``get_watts_streams_for_activities`` method uses chunked ``IN (?)``
        clauses with ``prefetch = 10 000`` so the data transfer is I/O-
        efficient.  Combined with the application-level cache in the web layer
        (which makes subsequent loads instant), this approach keeps Firebird
        competitive with the other backends.
        """
        from kinetiqo.db.repository import compute_best_power_per_activity
        watts_data = self.get_watts_streams_for_activities(activity_ids)
        return compute_best_power_per_activity(watts_data, duration_seconds, min_total_samples)

    def get_activity_ids_by_types(
        self,
        types: List[str],
        since_date=None,
        watts_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get lightweight activity records filtered by sport type."""
        if not types:
            return []

        self._ensure_connected()
        extra = ' AND "average_watts" IS NOT NULL' if watts_only else ""
        with self.conn.cursor() as cur:
            placeholders = ', '.join(['?'] * len(types))
            if since_date is not None:
                params = list(types) + [since_date]
                cur.execute(f"""
                    SELECT "activity_id", CAST("name" AS VARCHAR(500)) AS "name", "start_date"
                    FROM "activities"
                    WHERE "sport" IN ({placeholders})
                      AND "start_date" >= ?{extra}
                    ORDER BY "start_date" DESC
                """, params)
            else:
                cur.execute(f"""
                    SELECT "activity_id", CAST("name" AS VARCHAR(500)) AS "name", "start_date"
                    FROM "activities"
                    WHERE "sport" IN ({placeholders}){extra}
                    ORDER BY "start_date" DESC
                """, types)

            activities = []
            for row in cur.fetchall():
                activity = {
                    'id': row[0],
                    'name': row[1],
                    'start_date': row[2].isoformat() if isinstance(row[2], datetime) else row[2]
                }
                activities.append(activity)
            return activities

    def get_table_record_counts(self) -> Dict[str, int]:
        """Return a dict of table names and their record counts."""
        self._ensure_connected()
        tables = ['activities', 'streams', 'logs']
        counts = {}
        with self.conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                    result = cur.fetchone()
                    counts[table] = result[0] if result else 0
                except Exception:
                    counts[table] = None
        return counts

    def get_activities_with_suffer_score(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all activities that have a suffer_score > 0, ordered by date."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            if days is not None:
                start_date_limit = datetime.now(timezone.utc) - timedelta(days=days)
                cur.execute("""
                    SELECT "start_date", "suffer_score"
                    FROM "activities"
                    WHERE "suffer_score" > 0 AND "start_date" >= ?
                    ORDER BY "start_date" ASC
                """, (start_date_limit,))
            else:
                cur.execute("""
                    SELECT "start_date", "suffer_score"
                    FROM "activities"
                    WHERE "suffer_score" > 0
                    ORDER BY "start_date" ASC
                """)
            
            activities = []
            for row in cur.fetchall():
                activity = {
                    'start_date': row[0].isoformat() if isinstance(row[0], datetime) else row[0],
                    'suffer_score': row[1]
                }
                activities.append(activity)
            return activities

    def get_profile(self):
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                'SELECT "athlete_id", "first_name", "last_name", "weight" '
                'FROM "profile" ROWS 1'
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                'athlete_id': row[0],
                'first_name': row[1],
                'last_name': row[2],
                'weight': row[3],
            }

    def upsert_profile(self, athlete_id: int, first_name: str, last_name: str, weight: float):
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                'UPDATE OR INSERT INTO "profile" '
                '("athlete_id", "first_name", "last_name", "weight") '
                'VALUES (?, ?, ?, ?) '
                'MATCHING ("athlete_id")',
                (athlete_id, first_name, last_name, weight)
            )
        self.conn.commit()

    def get_goals(self, athlete_id: int):
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT "activity_type_id",
                       "weekly_distance_goal", "monthly_distance_goal", "yearly_distance_goal",
                       "weekly_elevation_goal", "monthly_elevation_goal", "yearly_elevation_goal"
                FROM "activity_goals"
                WHERE "athlete_id" = ?
                ORDER BY "activity_type_id"
            """, (athlete_id,))
            cols = [
                'activity_type_id',
                'weekly_distance_goal', 'monthly_distance_goal', 'yearly_distance_goal',
                'weekly_elevation_goal', 'monthly_elevation_goal', 'yearly_elevation_goal',
            ]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def upsert_goal(self, athlete_id, activity_type_id,
                    weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                    weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal):
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                'UPDATE OR INSERT INTO "activity_goals" '
                '("athlete_id", "activity_type_id", '
                '"weekly_distance_goal", "monthly_distance_goal", "yearly_distance_goal", '
                '"weekly_elevation_goal", "monthly_elevation_goal", "yearly_elevation_goal") '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?) '
                'MATCHING ("athlete_id", "activity_type_id")',
                (athlete_id, activity_type_id,
                 weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                 weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal)
            )
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception as e:
            logger.warning(f"Error closing Firebird connection: {e}")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
