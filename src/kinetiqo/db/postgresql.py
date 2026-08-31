import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any, Tuple

import threading
import psycopg2
import psycopg2.pool
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository
from kinetiqo.db.schema import SchemaManager
from psycopg2.extras import execute_batch, RealDictCursor

logger = logging.getLogger("kinetiqo")

_pg_pool = None
_pg_pool_lock = threading.Lock()


def _get_pg_pool(config: Config):
    """Retrieve or initialize the thread-safe PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    host=config.postgresql_host,
                    port=config.postgresql_port,
                    user=config.postgresql_user,
                    password=config.postgresql_password,
                    database=config.postgresql_database,
                    sslmode=config.postgresql_ssl_mode,
                )
    return _pg_pool


class PostgresqlRepository(DatabaseRepository):
    def __init__(self, config: Config):
        """Initialize PostgreSQL repository and establish a DB connection.

        Attempts to connect to the configured database and will create the
        target database if it does not exist (when the server permits).

        Args:
            config (Config): Application configuration instance.
        """
        self.config = config
        self._from_pool = False
        try:
            self.conn = self._connect()
        except psycopg2.OperationalError as e:
            if f'database "{config.postgresql_database}" does not exist' in str(e):
                logger.warning(f"Database '{config.postgresql_database}' does not exist. Attempting to create it...")
                self._create_database()
                self.conn = self._connect()
            else:
                logger.error(
                    f"Failed to connect to PostgreSQL at {config.postgresql_host}:{config.postgresql_port}: {e}")
                sys.exit(1)

    def _connect(self, dbname=None):
        """Helper to connect to a specific database using connection pool if available."""
        target_db = dbname or self.config.postgresql_database
        from_pool = False

        if dbname is None:
            try:
                pool = _get_pg_pool(self.config)
                conn = pool.getconn()
                from_pool = True
            except Exception as pool_err:
                logger.debug(f"Connection pool unavailable, falling back to direct connection: {pool_err}")
                conn = psycopg2.connect(
                    host=self.config.postgresql_host,
                    port=self.config.postgresql_port,
                    user=self.config.postgresql_user,
                    password=self.config.postgresql_password,
                    database=target_db,
                    sslmode=self.config.postgresql_ssl_mode
                )
        else:
            conn = psycopg2.connect(
                host=self.config.postgresql_host,
                port=self.config.postgresql_port,
                user=self.config.postgresql_user,
                password=self.config.postgresql_password,
                database=target_db,
                sslmode=self.config.postgresql_ssl_mode
            )

        conn.autocommit = True
        self._from_pool = from_pool
        return conn

    def _ensure_connected(self):
        """Verify the connection is alive; transparently reconnect if not."""
        try:
            if self.conn is None or self.conn.closed:
                raise psycopg2.OperationalError("Connection is closed")
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        except Exception:
            logger.warning("PostgreSQL connection lost, reconnecting...")
            try:
                if self.conn:
                    if getattr(self, '_from_pool', False) and _pg_pool is not None:
                        try:
                            _pg_pool.putconn(self.conn, close=True)
                        except Exception:
                            try:
                                self.conn.close()
                            except Exception:
                                pass
                    else:
                        try:
                            self.conn.close()
                        except Exception:
                            pass
                self.conn = self._connect()
            except Exception as e:
                logger.error(f"Failed to reconnect to PostgreSQL: {e}")
                raise

    def _create_database(self):
        """Creates the target database if it doesn't exist."""
        try:
            conn_temp = self._connect(dbname='postgres')
            with conn_temp.cursor() as cur:
                cur.execute(f"CREATE DATABASE {self.config.postgresql_database}")
                logger.info(f"Database '{self.config.postgresql_database}' created successfully.")
        except psycopg2.Error as e:
            logger.error(f"Could not create database '{self.config.postgresql_database}': {e}")
            sys.exit(1)
        finally:
            if 'conn_temp' in locals() and conn_temp:
                conn_temp.close()

    def get_pg_version(self) -> str:
        """Get the PostgreSQL version string."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("SELECT version();")
            result = cur.fetchone()
            return result[0] if result else "Unknown"

    def initialize_schema(self):
        """Create or update the database schema using SchemaManager."""
        self._ensure_connected()
        schema_manager = SchemaManager(self.conn, 'postgresql')
        schema_manager.ensure_schema()

    def flightcheck(self) -> bool:
        """Perform a health check on the database."""
        try:
            self._ensure_connected()
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")

                cur.execute("""
                            SELECT table_name
                            FROM information_schema.tables
                            WHERE table_name IN ('activities', 'streams', 'logs')
                            """)
                tables = {row[0] for row in cur.fetchall()}

                if 'activities' not in tables:
                    logger.error("Table 'activities' is missing.")
                    return False
                if 'streams' not in tables:
                    logger.error("Table 'streams' is missing.")
                    return False
                if 'logs' not in tables:
                    logger.error("Table 'logs' is missing.")
                    return False

                return True
        except Exception as e:
            logger.error(f"Flight check failed: {e}")
            return False

    def get_latest_activity_time(self) -> Optional[int]:
        """Get the start timestamp of the most recent activity by date.

        Used by fast sync to ask Strava for activities newer than this.
        We use ``MAX(start_date)`` — not ``MAX(activity_id)`` — because
        Strava IDs are not guaranteed to be sequential in chronological
        order (e.g. a manual upload of an old ride gets a high ID).
        """
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("SELECT MAX(start_date) FROM activities")
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
        logger.debug("Querying PostgreSQL for all synced activity IDs...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities")
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from PostgreSQL.")
        return synced_ids

    def get_synced_activity_ids_since(self, after_epoch: int) -> Set[str]:
        """Get activity IDs whose start_date is at or after *after_epoch*."""
        self._ensure_connected()
        dt = datetime.fromtimestamp(after_epoch, tz=timezone.utc)
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities WHERE start_date >= %s", (dt,))
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from PostgreSQL since {dt}.")
        return synced_ids

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                        SELECT activity_id as id,
                               name,
                               sport       as type,
                               distance,
                               moving_time,
                               total_elevation_gain,
                               start_date,
                                average_speed,
                                average_heartrate,
                                average_cadence,
                                average_watts,
                               max_watts,
                               weighted_average_watts,
                               device_watts,
                               calories,
                               kilojoules,
                               achievement_count,
                               pr_count,
                               suffer_score,
                               average_temp,
                               elev_high,
                               elev_low,
                               gear_id,
                               has_heartrate,
                               workout_type
                        FROM activities
                        ORDER BY start_date DESC
                            LIMIT %s
                        """, (limit,))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                activities.append(activity)
            return activities

    def get_activities_web(self, limit=10, offset=0, sort_by='start_date', sort_order='DESC', types=None,
                           start_date=None, end_date=None):
        """Fetch activities with pagination and sorting from PostgreSQL"""
        self._ensure_connected()
        allowed_columns = ['start_date', 'activity_id', 'name', 'sport', 'distance', 'moving_time',
                           'total_elevation_gain', 'average_speed', 'average_heartrate', 'average_cadence', 'average_watts', 'max_watts']
        if sort_by not in allowed_columns:
            sort_by = 'start_date'

        sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['%s'] * len(types))
            where_conditions.append(f"sport IN ({placeholders})")
            params.extend(types)

        if start_date:
            where_conditions.append("start_date >= %s")
            params.append(start_date)

        if end_date:
            if len(end_date) == 10:
                end_date += " 23:59:59.999999"
            where_conditions.append("start_date <= %s")
            params.append(end_date)

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        query = f"""
            SELECT
                activity_id as id,
                name,
                sport as type,
                distance,
                moving_time,
                total_elevation_gain,
                start_date,
                average_speed,
                average_heartrate,
                average_cadence,
                average_watts,
                max_watts,
                weighted_average_watts,
                device_watts,
                calories,
                kilojoules,
                achievement_count,
                pr_count,
                suffer_score,
                average_temp,
                elev_high,
                elev_low,
                gear_id,
                has_heartrate,
                workout_type,
                max_speed
            FROM activities
            {where_clause}
            ORDER BY {sort_by} {sort_order}
        """
        if limit is not None:
            query += "\n            LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                activities.append(activity)
            return activities

    def get_activities_by_ids(self, activity_ids: List[str]) -> List[Dict[str, Any]]:
        """Get a list of activities by their IDs."""
        if not activity_ids:
            return []

        self._ensure_connected()
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                        SELECT activity_id as id,
                               name,
                               sport       as type,
                               distance,
                               moving_time,
                               total_elevation_gain,
                               start_date,
                               average_speed,
                               average_heartrate,
                               average_cadence,
                               average_watts,
                               max_watts,
                               weighted_average_watts,
                               device_watts,
                               calories,
                               kilojoules,
                               achievement_count,
                               pr_count,
                               suffer_score,
                               average_temp,
                               elev_high,
                               elev_low,
                               gear_id,
                               has_heartrate,
                               workout_type
                        FROM activities
                        WHERE activity_id = ANY (%s)
                        ORDER BY start_date DESC
                        """, (int_ids,))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                activities.append(activity)
            return activities

    def get_activities_totals(self, types=None, start_date=None, end_date=None) -> Dict[str, float]:
        """Get totals for distance, elevation, and moving_time for the filtered activities."""
        self._ensure_connected()
        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['%s'] * len(types))
            where_conditions.append(f"sport IN ({placeholders})")
            params.extend(types)

        if start_date:
            where_conditions.append("start_date >= %s")
            params.append(start_date)

        if end_date:
            if len(end_date) == 10:
                end_date += " 23:59:59.999999"
            where_conditions.append("start_date <= %s")
            params.append(end_date)

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        query = f"""
            SELECT
                COALESCE(SUM(distance), 0) as total_distance,
                COALESCE(SUM(total_elevation_gain), 0) as total_elevation,
                COALESCE(SUM(moving_time), 0) as total_moving_time
            FROM activities
            {where_clause}
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            result = cur.fetchone()
            return dict(result) if result else {'total_distance': 0, 'total_elevation': 0, 'total_moving_time': 0}

    def count_activities(self, types=None, start_date=None, end_date=None):
        """Get total count of activities, optionally filtered by sport type and date range."""
        self._ensure_connected()
        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['%s'] * len(types))
            where_conditions.append(f"sport IN ({placeholders})")
            params.extend(types)

        if start_date:
            where_conditions.append("start_date >= %s")
            params.append(start_date)

        if end_date:
            if len(end_date) == 10:
                end_date += " 23:59:59.999999"
            where_conditions.append("start_date <= %s")
            params.append(end_date)

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM activities {where_clause}", tuple(params))
            result = cur.fetchone()
            return result[0] if result else 0

    def write_activity(self, activity: dict):
        """Write activity metadata to PostgreSQL."""
        self._ensure_connected()
        activity_id = activity["id"]
        start_date = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))

        row = (
            start_date,
            activity_id,
            activity.get("name", "Unnamed Activity"),
            activity.get("sport_type", "Unknown"),
            activity["athlete"]["id"],
            activity.get("distance", 0.0),
            activity.get("moving_time", 0),
            activity.get("elapsed_time", 0),
            activity.get("total_elevation_gain", 0.0),
            activity.get("average_speed", 0.0),
            activity.get("max_speed", 0.0),
            activity.get("average_heartrate"),
            activity.get("max_heartrate"),
            activity.get("average_cadence"),
            activity.get("average_watts"),
            activity.get("max_watts"),
            activity.get("achievement_count"),
            activity.get("average_temp"),
            activity.get("calories"),
            activity.get("device_watts"),
            activity.get("elev_high"),
            activity.get("elev_low"),
            activity.get("gear_id"),
            activity.get("has_heartrate"),
            activity.get("kilojoules"),
            activity.get("pr_count"),
            activity.get("suffer_score"),
            activity.get("weighted_average_watts"),
            activity.get("workout_type")
        )

        logger.debug(f"Writing activity metadata for {activity_id} to PostgreSQL...")

        with self.conn.cursor() as cur:
            cur.execute("""
                        INSERT INTO activities (start_date, activity_id, name, sport, athlete_id, distance,
                                                moving_time, elapsed_time, total_elevation_gain, average_speed,
                                                max_speed, average_heartrate, max_heartrate, average_cadence,
                                                average_watts, max_watts, achievement_count, average_temp,
                                                calories, device_watts, elev_high, elev_low, gear_id,
                                                has_heartrate, kilojoules, pr_count, suffer_score,
                                                weighted_average_watts, workout_type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (activity_id) DO
                        UPDATE SET
                            start_date = EXCLUDED.start_date,
                            name = EXCLUDED.name,
                            sport = EXCLUDED.sport,
                            athlete_id = EXCLUDED.athlete_id,
                            distance = EXCLUDED.distance,
                            moving_time = EXCLUDED.moving_time,
                            elapsed_time = EXCLUDED.elapsed_time,
                            total_elevation_gain = EXCLUDED.total_elevation_gain,
                            average_speed = EXCLUDED.average_speed,
                            max_speed = EXCLUDED.max_speed,
                            average_heartrate = EXCLUDED.average_heartrate,
                            max_heartrate = EXCLUDED.max_heartrate,
                            average_cadence = EXCLUDED.average_cadence,
                            average_watts = EXCLUDED.average_watts,
                            max_watts = EXCLUDED.max_watts,
                            achievement_count = EXCLUDED.achievement_count,
                            average_temp = EXCLUDED.average_temp,
                            calories = EXCLUDED.calories,
                            device_watts = EXCLUDED.device_watts,
                            elev_high = EXCLUDED.elev_high,
                            elev_low = EXCLUDED.elev_low,
                            gear_id = EXCLUDED.gear_id,
                            has_heartrate = EXCLUDED.has_heartrate,
                            kilojoules = EXCLUDED.kilojoules,
                            pr_count = EXCLUDED.pr_count,
                            suffer_score = EXCLUDED.suffer_score,
                            weighted_average_watts = EXCLUDED.weighted_average_watts,
                            workout_type = EXCLUDED.workout_type
                        """, row)

    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to PostgreSQL."""
        self._ensure_connected()
        activity_id = activity["id"]
        sport = activity["sport_type"]
        athlete_id = activity["athlete"]["id"]

        time_stream = streams.get("time", {}).get("data", [])
        latlng_stream = streams.get("latlng", {}).get("data", [])
        altitude_stream = streams.get("altitude", {}).get("data", [])
        hr_stream = streams.get("heartrate", {}).get("data", [])
        cadence_stream = streams.get("cadence", {}).get("data", [])
        speed_stream = streams.get("velocity_smooth", {}).get("data", [])
        distance_stream = streams.get("distance", {}).get("data", [])
        watts_stream = streams.get("watts", {}).get("data", [])
        temp_stream = streams.get("temp", {}).get("data", [])
        grade_stream = streams.get("grade_smooth", {}).get("data", [])
        moving_stream = streams.get("moving", {}).get("data", [])

        start_date = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))

        rows = []
        for i, t in enumerate(time_stream):
            ts = start_date + timedelta(seconds=t)
            lat, lng = latlng_stream[i] if i < len(latlng_stream) else (None, None)

            row = (
                ts,
                activity_id,
                sport,
                athlete_id,
                float(lat) if lat else None,
                float(lng) if lng else None,
                altitude_stream[i] if i < len(altitude_stream) else None,
                hr_stream[i] if i < len(hr_stream) else None,
                cadence_stream[i] if i < len(cadence_stream) else None,
                speed_stream[i] if i < len(speed_stream) else None,
                distance_stream[i] if i < len(distance_stream) else None,
                watts_stream[i] if i < len(watts_stream) else None,
                temp_stream[i] if i < len(temp_stream) else None,
                grade_stream[i] if i < len(grade_stream) else None,
                moving_stream[i] if i < len(moving_stream) else None
            )
            rows.append(row)

        logger.debug(f"Writing {len(rows)} stream rows to PostgreSQL for activity {activity_id}...")

        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM streams WHERE activity_id = %s", (activity_id,))

            execute_batch(cur, """
                               INSERT INTO streams (ts, activity_id, sport, athlete_id, lat, lng, altitude,
                                                    heartrate, cadence, speed, distance, watts, temp,
                                                    grade_smooth, moving)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                                       %s, %s, %s, %s, %s, %s)
                               """, rows, page_size=1000)


    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from PostgreSQL."""
        self._ensure_connected()
        logger.debug(f"Deleting activity {activity_id} from PostgreSQL...")

        aid = int(activity_id)

        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM activities WHERE activity_id = %s", (aid,))
            logger.info(f"Deleted activity {aid} and its streams.")

    def delete_activities(self, activity_ids: List[str]):
        """Delete multiple activities and their streams from PostgreSQL."""
        if not activity_ids:
            return

        self._ensure_connected()
        logger.debug(f"Deleting {len(activity_ids)} activities from PostgreSQL...")
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM activities WHERE activity_id = ANY(%s)", (int_ids,))
            logger.info(f"Deleted {len(activity_ids)} activities and their streams.")

    def get_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get GPS streams (lat, lng) for a list of activity IDs."""
        if not activity_ids:
            return {}

        self._ensure_connected()
        result = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                        SELECT activity_id, lat, lng
                        FROM streams
                        WHERE activity_id = ANY (%s)
                          AND lat IS NOT NULL
                          AND lng IS NOT NULL
                        ORDER BY activity_id, ts
                        """, (int_ids,))

            for row in cur.fetchall():
                aid = str(row['activity_id'])
                if aid not in result:
                    result[aid] = []
                result[aid].append({
                    'lat': float(row['lat']),
                    'lng': float(row['lng'])
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
            cur.execute("""
                SELECT activity_id, lat, lng
                FROM streams
                WHERE activity_id = ANY (%s)
                  AND lat IS NOT NULL
                  AND lng IS NOT NULL
                ORDER BY activity_id, ts
            """, (int_ids,))

            current_aid = None
            current_coords = None
            for row in cur:
                aid = row[0]
                if aid != current_aid:
                    current_aid = aid
                    current_coords = []
                    result[str(aid)] = current_coords
                current_coords.append([row[1], row[2]])

        return result

    def get_streams_bounds_for_activities(self, activity_ids: List[str]) -> Optional[Tuple[float, float, float, float]]:
        """Get GPS bounding box for a list of activity IDs via SQL aggregation."""
        if not activity_ids:
            return None

        self._ensure_connected()
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            cur.execute("""
                        SELECT MIN(lat), MIN(lng), MAX(lat), MAX(lng)
                        FROM streams
                        WHERE activity_id = ANY (%s)
                          AND lat IS NOT NULL
                          AND lng IS NOT NULL
                        """, (int_ids,))
            row = cur.fetchone()
            if row and row[0] is not None:
                return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
            return None

    def get_activity_name(self, activity_id: str) -> Optional[str]:
        """Get the name of an activity by its ID."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("""
                        SELECT name
                        FROM activities
                        WHERE activity_id = %s
                        """, (int(activity_id),))
            row = cur.fetchone()
            return row[0] if row else None

    def get_activity_average_cadence(self, activity_id: str) -> Optional[float]:
        """Compute average cadence (rpm) for an activity from streams (PostgreSQL)."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(cadence) FROM streams
                WHERE activity_id = %s AND cadence IS NOT NULL
            """, (int(activity_id),))
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None

    def get_elevation_streams_for_activity(
        self, activity_id: str
    ) -> tuple[list[float], list[float]]:
        """Return (distance_m, altitude_m) arrays for *activity_id* (PostgreSQL)."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT distance, altitude FROM streams
                WHERE activity_id = %s
                  AND distance IS NOT NULL
                  AND altitude IS NOT NULL
                ORDER BY ts
                """,
                (int(activity_id),),
            )
            rows = cur.fetchall()
        if not rows:
            return [], []
        distance = [float(r[0]) for r in rows]
        altitude = [float(r[1]) for r in rows]
        return distance, altitude

    def log_sync(self, added: int, removed: int, trigger: str, success: bool, action: str, user: str):
        """Log the result of a sync operation."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("""
                        INSERT INTO logs (added, removed, trigger_source, success, action, "user")
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (added, removed, trigger, success, action, user))

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest sync logs."""
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                        SELECT created_at as timestamp, added, removed, trigger_source, success, action, "user"
                        FROM logs
                        ORDER BY created_at DESC
                            LIMIT %s
                        """, (limit,))

            logs = []
            for row in cur.fetchall():
                log = dict(row)
                if isinstance(log['timestamp'], datetime):
                    log['timestamp'] = log['timestamp'].isoformat()
                logs.append(log)
            return logs

    def get_watts_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[float]]:
        """Get watts time-series for a list of activity IDs."""
        if not activity_ids:
            return {}

        self._ensure_connected()
        result = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            cur.execute("""
                        SELECT activity_id, watts
                        FROM streams
                        WHERE activity_id = ANY (%s)
                          AND watts IS NOT NULL
                        ORDER BY activity_id, ts
                        """, (int_ids,))

            for row in cur.fetchall():
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
        """Compute best rolling-average power per activity via SQL window functions.

        Uses ``idx_streams_activity_ts_watts`` partial covering index.
        Returns one row per activity instead of thousands of raw stream rows.
        """
        if not activity_ids:
            return {}

        self._ensure_connected()
        rows_back = duration_seconds - 1
        min_total = min_total_samples if min_total_samples > 0 else duration_seconds
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT activity_id, MAX(rolling_avg) AS best_avg
                FROM (
                    SELECT activity_id,
                           AVG(watts) OVER (
                               PARTITION BY activity_id
                               ORDER BY ts
                               ROWS BETWEEN {rows_back} PRECEDING AND CURRENT ROW
                           ) AS rolling_avg,
                           ROW_NUMBER() OVER (
                               PARTITION BY activity_id
                               ORDER BY ts
                           ) AS rn,
                           COUNT(*) OVER (
                               PARTITION BY activity_id
                           ) AS total_cnt
                    FROM streams
                    WHERE activity_id = ANY(%s)
                      AND watts IS NOT NULL
                ) sub
                WHERE rn >= {duration_seconds}
                  AND total_cnt >= {min_total}
                GROUP BY activity_id
            """, (int_ids,))

            return {str(row[0]): float(row[1]) for row in cur.fetchall()}

    def get_activity_ids_by_types(
        self,
        types: List[str],
        since_date=None,
        watts_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get lightweight activity records filtered by sport type.

        When *since_date* is provided the date predicate is pushed to SQL so
        only qualifying rows are transferred from the database.  The composite
        index ``idx_activities_sport_start_date`` on ``(sport, start_date DESC)``
        covers both the filter and the sort without a heap scan.

        When *watts_only* is ``True``, only activities with measured power data
        (``average_watts IS NOT NULL``) are returned.  This shrinks the activity
        list fed to subsequent stream queries, dramatically cutting I/O on the
        streams table for VO2max / FTP calculations.
        """
        if not types:
            return []

        self._ensure_connected()
        extra = ""
        if watts_only:
            extra += " AND average_watts IS NOT NULL"

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if since_date is not None:
                cur.execute(f"""
                    SELECT activity_id AS id, name, start_date
                    FROM activities
                    WHERE sport = ANY (%s)
                      AND start_date >= %s{extra}
                    ORDER BY start_date DESC
                """, (types, since_date))
            else:
                cur.execute(f"""
                    SELECT activity_id AS id, name, start_date
                    FROM activities
                    WHERE sport = ANY (%s){extra}
                    ORDER BY start_date DESC
                """, (types,))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
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
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    result = cur.fetchone()
                    counts[table] = result[0] if result else 0
                except Exception:
                    counts[table] = None
        return counts

    def get_activities_with_suffer_score(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all activities that have a suffer_score > 0, ordered by date."""
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if days is not None:
                start_date_limit = datetime.now(timezone.utc) - timedelta(days=days)
                cur.execute("""
                    SELECT start_date, suffer_score
                    FROM activities
                    WHERE suffer_score > 0 AND start_date >= %s
                    ORDER BY start_date ASC
                """, (start_date_limit,))
            else:
                cur.execute("""
                    SELECT start_date, suffer_score
                    FROM activities
                    WHERE suffer_score > 0
                    ORDER BY start_date ASC
                """)
            
            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                activities.append(activity)
            return activities

    def get_profile(self):
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT athlete_id, first_name, last_name, weight, ftp, "
                "update_strava_cycling_indoor, update_strava_cycling_outdoor, "
                "update_strava_running_indoor, update_strava_running_outdoor, "
                "update_strava_walking, update_strava_swimming, refresh_token, "
                "gps_simplification "
                "FROM profile LIMIT 1"
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_profile(self, athlete_id: int, first_name: str, last_name: str, weight: float,
                       update_strava_cycling_indoor: str = "", update_strava_cycling_outdoor: str = "",
                       update_strava_running_indoor: str = "", update_strava_running_outdoor: str = "",
                       update_strava_walking: str = "", update_strava_swimming: str = "",
                       refresh_token: str = "", ftp: Optional[float] = None,
                       gps_simplification: Optional[int] = None):
        self._ensure_connected()
        existing = self.get_profile()
        effective_ftp = ftp if ftp is not None else (existing.get('ftp') if existing else None)
        effective_gps_simplification = gps_simplification if gps_simplification is not None else (existing.get('gps_simplification') if existing else 0)

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO profile (athlete_id, first_name, last_name, weight, ftp,
                    update_strava_cycling_indoor, update_strava_cycling_outdoor,
                    update_strava_running_indoor, update_strava_running_outdoor,
                    update_strava_walking, update_strava_swimming, refresh_token,
                    gps_simplification)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (athlete_id) DO UPDATE
                    SET first_name = EXCLUDED.first_name,
                        last_name  = EXCLUDED.last_name,
                        weight     = EXCLUDED.weight,
                        ftp        = EXCLUDED.ftp,
                        update_strava_cycling_indoor  = EXCLUDED.update_strava_cycling_indoor,
                        update_strava_cycling_outdoor = EXCLUDED.update_strava_cycling_outdoor,
                        update_strava_running_indoor  = EXCLUDED.update_strava_running_indoor,
                        update_strava_running_outdoor = EXCLUDED.update_strava_running_outdoor,
                        update_strava_walking          = EXCLUDED.update_strava_walking,
                        update_strava_swimming         = EXCLUDED.update_strava_swimming,
                        refresh_token                  = EXCLUDED.refresh_token,
                        gps_simplification             = EXCLUDED.gps_simplification
            """, (athlete_id, first_name, last_name, weight, effective_ftp,
                  update_strava_cycling_indoor or "", update_strava_cycling_outdoor or "",
                  update_strava_running_indoor or "", update_strava_running_outdoor or "",
                  update_strava_walking or "", update_strava_swimming or "", refresh_token or "",
                  effective_gps_simplification))

    # ------------------------------------------------------------------
    # Activity goals
    # ------------------------------------------------------------------

    def get_goals(self, athlete_id: int):
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT activity_type_id,
                       weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                       weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal
                FROM activity_goals
                WHERE athlete_id = %s
                ORDER BY activity_type_id
            """, (athlete_id,))
            return [dict(row) for row in cur.fetchall()]

    def upsert_goal(self, athlete_id, activity_type_id,
                    weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                    weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal):
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO activity_goals
                    (athlete_id, activity_type_id,
                     weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                     weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (athlete_id, activity_type_id) DO UPDATE SET
                    weekly_distance_goal  = EXCLUDED.weekly_distance_goal,
                    monthly_distance_goal = EXCLUDED.monthly_distance_goal,
                    yearly_distance_goal  = EXCLUDED.yearly_distance_goal,
                    weekly_elevation_goal  = EXCLUDED.weekly_elevation_goal,
                    monthly_elevation_goal = EXCLUDED.monthly_elevation_goal,
                    yearly_elevation_goal  = EXCLUDED.yearly_elevation_goal
            """, (athlete_id, activity_type_id,
                  weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                  weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal))

    def __enter__(self):
        """Enter context manager; returns the repository instance."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and close the repository connection."""
        self.close()

    def close(self):
        """Close or return the PostgreSQL connection to the pool, ignoring close errors."""
        try:
            if self.conn:
                if getattr(self, '_from_pool', False) and _pg_pool is not None:
                    try:
                        _pg_pool.putconn(self.conn)
                    except Exception:
                        try:
                            self.conn.close()
                        except Exception:
                            pass
                else:
                    self.conn.close()
                self.conn = None
        except Exception as e:
            logger.warning(f"Error closing PostgreSQL connection: {e}")

    def run_benchmarks(self, scope_days: int = 365) -> Dict[str, Any]:
        """Run performance benchmarks on database queries for the given lookback scope."""
        import time
        self._ensure_connected()
        since_date = datetime.now(timezone.utc) - timedelta(days=scope_days)
        since_date_iso = since_date.isoformat()

        # 1. Fetch all GPS data for last scope_days days all activity types
        t0 = time.perf_counter()
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT s.activity_id, s.lat, s.lng
                FROM activities a
                JOIN streams s ON s.activity_id = a.activity_id
                WHERE a.start_date >= %s
                  AND s.lat IS NOT NULL
                  AND s.lng IS NOT NULL
            """, (since_date,))
            gps_rows = cur.fetchall()
        gps_ms = (time.perf_counter() - t0) * 1000.0
        gps_count = len(gps_rows)

        # 2. Order all activities by name
        t0 = time.perf_counter()
        name_activities = self.get_activities_web(limit=None, sort_by='name', sort_order='ASC', start_date=since_date_iso)
        order_name_ms = (time.perf_counter() - t0) * 1000.0
        order_name_count = len(name_activities)

        # 3. Order all activities by distance
        t0 = time.perf_counter()
        dist_activities = self.get_activities_web(limit=None, sort_by='distance', sort_order='DESC', start_date=since_date_iso)
        order_dist_ms = (time.perf_counter() - t0) * 1000.0
        order_dist_count = len(dist_activities)

        # 4. Order all activities by elevation gained
        t0 = time.perf_counter()
        elev_activities = self.get_activities_web(limit=None, sort_by='total_elevation_gain', sort_order='DESC', start_date=since_date_iso)
        order_elev_ms = (time.perf_counter() - t0) * 1000.0
        order_elev_count = len(elev_activities)

        return {
            'gps_ms': gps_ms,
            'gps_count': gps_count,
            'order_name_ms': order_name_ms,
            'order_name_count': order_name_count,
            'order_dist_ms': order_dist_ms,
            'order_dist_count': order_dist_count,
            'order_elev_ms': order_elev_ms,
            'order_elev_count': order_elev_count,
        }
