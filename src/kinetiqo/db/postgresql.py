import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any, Tuple

import psycopg2
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository
from kinetiqo.db.schema import SchemaManager
from psycopg2.extras import execute_batch, RealDictCursor

logger = logging.getLogger("kinetiqo")


class PostgresqlRepository(DatabaseRepository):
    def __init__(self, config: Config):
        self.config = config
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
        """Helper to connect to a specific database."""
        conn = psycopg2.connect(
            host=self.config.postgresql_host,
            port=self.config.postgresql_port,
            user=self.config.postgresql_user,
            password=self.config.postgresql_password,
            database=dbname or self.config.postgresql_database,
            sslmode=self.config.postgresql_ssl_mode
        )
        # Autocommit ensures every statement (including SELECTs) runs outside
        # a transaction and always sees the latest committed data.  This is
        # critical when the CLI syncs new activities from a separate process
        # while Gunicorn serves web requests.
        conn.autocommit = True
        return conn

    def _ensure_connected(self):
        """Verify the connection is alive; transparently reconnect if not.

        Gunicorn workers may hold connections that the server has closed due
        to idle timeout or network disruption.  ``psycopg2``'s ``conn.closed``
        attribute is a lightweight check (no round-trip), but we also issue
        a ``SELECT 1`` to catch connections that appear open but are actually
        severed at the TCP level.
        """
        try:
            if self.conn.closed:
                raise psycopg2.OperationalError("Connection is closed")
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        except Exception:
            logger.warning("PostgreSQL connection lost, reconnecting...")
            try:
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
                           'total_elevation_gain', 'average_speed', 'average_heartrate', 'average_watts', 'max_watts']
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
            {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT %s OFFSET %s
        """
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

    def count_activities(self, types=None):
        """Get total count of activities"""
        self._ensure_connected()
        where_clause = ""
        params = []
        if types:
            placeholders = ', '.join(['%s'] * len(types))
            where_clause = f"WHERE sport IN ({placeholders})"
            params.extend(types)

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

    def get_activity_ids_by_types(self, types: List[str]) -> List[Dict[str, Any]]:
        """Get lightweight activity records filtered by sport type."""
        if not types:
            return []

        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT activity_id AS id, name, start_date
                FROM activities
                WHERE sport = ANY (%s)
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

    def __enter__(self):
        return self

    # ------------------------------------------------------------------
    # Map Explorer cache
    # ------------------------------------------------------------------

    def get_mapexplorer_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT result_json, created_at FROM mapexplorer_cache WHERE cache_key = %s",
                (cache_key,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def set_mapexplorer_cache(self, cache_key: str, activity_ids_json: str,
                              paved_only: bool, result_json: str) -> None:
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mapexplorer_cache (cache_key, activity_ids, paved_only, result_json, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (cache_key) DO UPDATE
                    SET result_json = EXCLUDED.result_json,
                        created_at  = NOW()
            """, (cache_key, activity_ids_json, paved_only, result_json))

    def delete_mapexplorer_cache(self, cache_key: str) -> None:
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM mapexplorer_cache WHERE cache_key = %s", (cache_key,))

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception as e:
            logger.warning(f"Error closing PostgreSQL connection: {e}")
