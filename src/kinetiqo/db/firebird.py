import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any, Tuple

import firebird.driver
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository
from kinetiqo.db.schema import SchemaManager

logger = logging.getLogger("kinetiqo")


class FirebirdRepository(DatabaseRepository):
    def __init__(self, config: Config):
        self.config = config
        try:
            self.conn = self._connect()
            if config.database_connect_verbose:
                logger.info(
                    f"Connected to Firebird at {config.firebird_host}:{config.firebird_port} - {self.get_firebird_version()}")
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
            # Firebird connection string format: host:port/path_to_database or host/port:path_to_database
            dsn = f"{self.config.firebird_host}/{self.config.firebird_port}:{self.config.firebird_database}"

            conn = firebird.driver.connect(
                database=dsn,
                user=self.config.firebird_user,
                password=self.config.firebird_password,
                charset='UTF8'
            )
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to Firebird: {e}")
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
        with self.conn.cursor() as cur:
            cur.execute("SELECT rdb$get_context('SYSTEM', 'ENGINE_VERSION') FROM rdb$database")
            result = cur.fetchone()
            return result[0] if result else "Unknown"

    def initialize_schema(self):
        """Create or update the database schema."""
        schema_manager = SchemaManager(self.conn, 'firebird')

        # For Firebird, we need to create a sequence/generator for the auto-increment logs.id
        with self.conn.cursor() as cur:
            try:
                cur.execute("CREATE SEQUENCE logs_id_seq")
                self.conn.commit()
            except Exception:
                pass

        schema_manager.ensure_schema()

        # Create trigger for auto-increment on logs.id
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
                pass

    def flightcheck(self) -> bool:
        """Perform a health check on the database."""
        with self.conn.cursor() as cur:
            try:
                cur.execute("SELECT 1 FROM RDB$DATABASE")
                # Check for exact table name 'activities' (lowercase)
                cur.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = 'activities'")
                if cur.fetchone()[0] == 0:
                    return False
                return True
            except Exception:
                return False

    def get_latest_activity_time(self) -> Optional[int]:
        """Get the start timestamp of the activity with the highest ID."""
        with self.conn.cursor() as cur:
            cur.execute('SELECT MAX("activity_id") FROM "activities"')
            result = cur.fetchone()
            if not result or result[0] is None:
                return None
            max_activity_id = result[0]
            cur.execute('SELECT "start_date" FROM "activities" WHERE "activity_id" = ?', (max_activity_id,))
            result = cur.fetchone()
            if result and result[0]:
                ts = int(result[0].replace(tzinfo=timezone.utc).timestamp())
                return ts
            return None

    def get_synced_activity_ids(self) -> Set[str]:
        """Get all activity IDs already in the database."""
        with self.conn.cursor() as cur:
            cur.execute('SELECT "activity_id" FROM "activities"')
            return {str(row[0]) for row in cur.fetchall()}

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT FIRST {limit}
                    "activity_id" as id,
                    "name",
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
                "name",
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
                    'workout_type': row[23]
                }
                activities.append(activity)
            return activities

    def get_activities_by_ids(self, activity_ids: List[str]) -> List[Dict[str, Any]]:
        """Get a list of activities by their IDs."""
        if not activity_ids:
            return []

        int_ids = [int(aid) for aid in activity_ids]
        placeholders = ', '.join(['?'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    "activity_id" as id,
                    "name",
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
        with self.conn.cursor() as cur:
            # Helper to safely cast to int or return None
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
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM "streams" WHERE "activity_id" = ?', (int(activity["id"]),))
            start_date = self._validate_timestamp(datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00")))

            rows = []
            for i, t in enumerate(streams.get("time", {}).get("data", [])):
                lat, lng = streams.get("latlng", {}).get("data", [])[i] if i < len(
                    streams.get("latlng", {}).get("data", [])) else (None, None)

                # Helper to get value safely
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
        aid = int(activity_id)
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM "activities" WHERE "activity_id" = ?', (aid,))
            logger.info(f"Deleted activity {aid} and its streams.")
            self.conn.commit()

    def delete_activities(self, activity_ids: List[str]):
        """Delete multiple activities and their streams from Firebird."""
        if not activity_ids:
            return
        with self.conn.cursor() as cur:
            placeholders = ','.join(['?'] * len(activity_ids))
            cur.execute(f'DELETE FROM "activities" WHERE "activity_id" IN ({placeholders})',
                        [int(aid) for aid in activity_ids])
            self.conn.commit()

    def get_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get GPS streams (lat, lng) for a list of activity IDs."""
        if not activity_ids:
            return {}

        result = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            placeholders = ', '.join(['?'] * len(int_ids))
            cur.execute(f"""
                SELECT "activity_id", "lat", "lng"
                FROM "streams"
                WHERE "activity_id" IN ({placeholders})
                  AND "lat" IS NOT NULL
                  AND "lng" IS NOT NULL
                ORDER BY "activity_id", "ts"
            """, int_ids)

            for row in cur.fetchall():
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

        result: Dict[str, List[List[float]]] = {}
        int_ids = [int(aid) for aid in activity_ids]
        placeholders = ', '.join(['?'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT "activity_id", "lat", "lng"
                FROM "streams"
                WHERE "activity_id" IN ({placeholders})
                  AND "lat" IS NOT NULL
                  AND "lng" IS NOT NULL
                ORDER BY "activity_id", "ts"
            """, int_ids)

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

        int_ids = [int(aid) for aid in activity_ids]
        placeholders = ', '.join(['?'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT MIN("lat"), MIN("lng"), MAX("lat"), MAX("lng")
                FROM "streams"
                WHERE "activity_id" IN ({placeholders})
                  AND "lat" IS NOT NULL
                  AND "lng" IS NOT NULL
            """, int_ids)
            row = cur.fetchone()
            if row and row[0] is not None:
                return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
            return None

    def get_activity_name(self, activity_id: str) -> Optional[str]:
        """Get the name of an activity by its ID."""
        with self.conn.cursor() as cur:
            cur.execute('SELECT "name" FROM "activities" WHERE "activity_id" = ?', (int(activity_id),))
            row = cur.fetchone()
            return row[0] if row else None

    def log_sync(self, added: int, removed: int, trigger: str, success: bool, action: str, user: str):
        """Log the result of a sync operation."""
        with self.conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "logs" ("added", "removed", "trigger_source", "success", "action", "user") VALUES (?, ?, ?, ?, ?, ?)',
                (added, removed, trigger, 1 if success else 0, action, user)
            )
            self.conn.commit()

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest sync logs."""
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
                    'success': bool(row[4]),  # Convert smallint back to boolean
                    'action': row[5],
                    'user': row[6]
                }
                logs.append(log)
            return logs

    def get_watts_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[float]]:
        """Get watts time-series for a list of activity IDs."""
        if not activity_ids:
            return {}

        result = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            placeholders = ', '.join(['?'] * len(int_ids))
            cur.execute(f"""
                SELECT "activity_id", "watts"
                FROM "streams"
                WHERE "activity_id" IN ({placeholders})
                  AND "watts" IS NOT NULL
                ORDER BY "activity_id", "ts"
            """, int_ids)

            for row in cur.fetchall():
                aid = str(row[0])
                if aid not in result:
                    result[aid] = []
                result[aid].append(float(row[1]))

        return result

    def get_table_record_counts(self) -> Dict[str, int]:
        """Return a dict of table names and their record counts."""
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        try:
            if self.conn:
                # Firebird driver does not have 'closed' attribute, just try to close
                self.conn.close()
        except Exception as e:
            logger.warning(f"Error closing Firebird connection: {e}")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
