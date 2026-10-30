import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any, Tuple

import threading
import psycopg2
import psycopg2.pool
from kinetiqo.config import Config
from kinetiqo.db.pagination import encode_cursor, decode_cursor
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
    db_type = "postgresql"

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
                logger.exception(
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
        if self.conn is None:
            self.conn = self._connect()
            return
        try:
            if self.conn.closed:
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
                logger.exception(f"Failed to reconnect to PostgreSQL: {e}")
                raise

    def _create_database(self):
        """Creates the target database if it doesn't exist."""
        try:
            conn_temp = self._connect(dbname='postgres')
            with conn_temp.cursor() as cur:
                cur.execute(f"CREATE DATABASE {self.config.postgresql_database}")
                logger.info(f"Database '{self.config.postgresql_database}' created successfully.")
        except psycopg2.Error as e:
            logger.exception(f"Could not create database '{self.config.postgresql_database}': {e}")
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
            logger.exception(f"Flight check failed: {e}")
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
                               workout_type,
                               trophies
                        FROM activities
                        ORDER BY start_date DESC
                            LIMIT %s
                        """, (limit,))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                if activity.get('trophies') and isinstance(activity['trophies'], str):
                    try:
                        activity['trophies'] = json.loads(activity['trophies'])
                    except Exception:
                        pass
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
        order_col = f'{sort_by} COLLATE "C"' if sort_by == 'name' else sort_by

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
                max_speed,
                trophies,
                ai_responses
            FROM activities
            {where_clause}
            ORDER BY {order_col} {sort_order}
        """
        if limit is not None:
            query += "\n            LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        with self.conn.cursor() as cur:
            cur.execute(query, tuple(params))

            activities = []
            desc = getattr(cur, 'description', None)
            cols = [d[0] for d in desc] if desc else None
            for row in cur.fetchall():
                activity = dict(zip(cols, row)) if cols and not isinstance(row, dict) else dict(row)
                if isinstance(activity.get('start_date'), datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                trophies = activity.get('trophies')
                if trophies and isinstance(trophies, str):
                    try:
                        activity['trophies'] = json.loads(trophies)
                    except Exception:
                        pass
                ai_responses = activity.get('ai_responses')
                if ai_responses and isinstance(ai_responses, str):
                    try:
                        activity['ai_responses'] = json.loads(ai_responses)
                    except Exception:
                        pass
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
                               workout_type,
                               trophies
                        FROM activities
                        WHERE activity_id = ANY (%s)
                        ORDER BY start_date DESC
                        """, (int_ids,))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                if activity.get('trophies') and isinstance(activity['trophies'], str):
                    try:
                        activity['trophies'] = json.loads(activity['trophies'])
                    except Exception:
                        pass
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

        trophies_val = activity.get("trophies")
        if isinstance(trophies_val, dict):
            trophies_val = json.dumps(trophies_val)
        elif not isinstance(trophies_val, str):
            trophies_val = None

        ai_responses_val = activity.get("ai_responses")
        if isinstance(ai_responses_val, dict):
            ai_responses_val = json.dumps(ai_responses_val)
        elif not isinstance(ai_responses_val, str):
            ai_responses_val = None

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
            activity.get("workout_type"),
            trophies_val,
            ai_responses_val
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
                                                weighted_average_watts, workout_type, trophies, ai_responses)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (activity_id) DO
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
                            workout_type = EXCLUDED.workout_type,
                            trophies = COALESCE(EXCLUDED.trophies, activities.trophies),
                            ai_responses = COALESCE(EXCLUDED.ai_responses, activities.ai_responses)
                        """, row)

    def update_activity_trophies(self, activity_id: Any, trophies: Any):
        """Update placement achievements (trophies ranks 1-10) for an activity."""
        self._ensure_connected()
        val = json.dumps(trophies) if isinstance(trophies, dict) else (trophies or None)
        with self.conn.cursor() as cur:
            cur.execute("UPDATE activities SET trophies = %s WHERE activity_id = %s", (val, int(activity_id)))

    def update_activity_ai_responses(self, activity_id: Any, ai_responses: Any):
        """Update cached AI generated variable responses for an activity."""
        self._ensure_connected()
        val = json.dumps(ai_responses) if isinstance(ai_responses, dict) else (ai_responses or None)
        with self.conn.cursor() as cur:
            cur.execute("UPDATE activities SET ai_responses = %s WHERE activity_id = %s", (val, int(activity_id)))

    def get_activity_ai_responses(self, activity_id: Any) -> Optional[Dict[str, Any]]:
        """Get cached AI responses for an activity."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("SELECT ai_responses FROM activities WHERE activity_id = %s", (int(activity_id),))
            row = cur.fetchone()
            if row and row[0]:
                val = row[0]
                if isinstance(val, dict):
                    return val
                try:
                    return json.loads(val)
                except Exception:
                    return None
            return None

    def purge_activities_ai_responses(self, activity_ids: List[Any]):
        """Clear cached AI generated variable responses for specified activities."""
        if not activity_ids:
            return
        self._ensure_connected()
        ids = [int(aid) for aid in activity_ids]
        with self.conn.cursor() as cur:
            cur.execute("UPDATE activities SET ai_responses = NULL WHERE activity_id = ANY(%s)", (ids,))

    def purge_strava_agent_ai_responses(self, agent_name: str) -> int:
        self._ensure_connected()
        tokens = {f"agent-ai-{agent_name}"}
        affected = 0
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id, ai_responses FROM activities WHERE ai_responses IS NOT NULL")
            for activity_id, raw in cur.fetchall():
                try:
                    responses = raw if isinstance(raw, dict) else json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(responses, dict) and tokens.intersection(responses):
                    for token in tokens:
                        responses.pop(token, None)
                    cur.execute(
                        "UPDATE activities SET ai_responses = %s WHERE activity_id = %s",
                        (json.dumps(responses) if responses else None, activity_id),
                    )
                    affected += 1
        return affected

    def get_activities_needing_trophies(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get activities with achievements that have not yet had their trophies breakdown extracted."""
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT activity_id as id, name, sport, start_date, achievement_count, pr_count, trophies
                FROM activities
                WHERE achievement_count > 0 AND (trophies IS NULL OR trophies = '')
                ORDER BY start_date DESC
                LIMIT %s
            """, (limit,))
            activities = []
            for row in cur.fetchall():
                act = dict(row)
                if isinstance(act.get('start_date'), datetime):
                    act['start_date'] = act['start_date'].isoformat()
                activities.append(act)
            return activities

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
        with self.conn.cursor() as cur:
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
                dt, score = (row.get('start_date'), row.get('suffer_score')) if isinstance(row, dict) else (row[0], row[1])
                activities.append({
                    'start_date': dt.isoformat() if isinstance(dt, datetime) else dt,
                    'suffer_score': score,
                })
            return activities

    def get_profile(self):
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT athlete_id, first_name, last_name, weight, ftp, "
                "update_strava_cycling_indoor, update_strava_cycling_outdoor, "
                "update_strava_running_indoor, update_strava_running_outdoor, "
                "update_strava_walking, update_strava_swimming, refresh_token, "
                "gps_simplification, strava_agents_config, enable_weather_data "
                "FROM profile LIMIT 1"
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_profile(self, athlete_id: int, first_name: str, last_name: str, weight: float,
                       update_strava_cycling_indoor: str = "", update_strava_cycling_outdoor: str = "",
                       update_strava_running_indoor: str = "", update_strava_running_outdoor: str = "",
                       update_strava_walking: str = "", update_strava_swimming: str = "",
                       refresh_token: str = "", ftp: Optional[float] = None,
                       gps_simplification: Optional[int] = None,
                       strava_agents_config: Optional[str] = None,
                       enable_weather_data: Optional[bool] = None):
        self._ensure_connected()
        existing = self.get_profile()
        effective_ftp = ftp if ftp is not None else (existing.get('ftp') if existing else None)
        effective_gps_simplification = gps_simplification if gps_simplification is not None else (existing.get('gps_simplification') if existing else 0)
        effective_strava_agents_config = strava_agents_config if strava_agents_config is not None else (existing.get('strava_agents_config') if existing else "")
        effective_enable_weather_data = enable_weather_data if enable_weather_data is not None else bool(existing.get('enable_weather_data', False) if existing else False)

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO profile (athlete_id, first_name, last_name, weight, ftp,
                    update_strava_cycling_indoor, update_strava_cycling_outdoor,
                    update_strava_running_indoor, update_strava_running_outdoor,
                    update_strava_walking, update_strava_swimming, refresh_token,
                    gps_simplification, strava_agents_config, enable_weather_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        gps_simplification             = EXCLUDED.gps_simplification,
                        strava_agents_config           = EXCLUDED.strava_agents_config,
                        enable_weather_data             = EXCLUDED.enable_weather_data
            """, (athlete_id, first_name, last_name, weight, effective_ftp,
                  update_strava_cycling_indoor or "", update_strava_cycling_outdoor or "",
                  update_strava_running_indoor or "", update_strava_running_outdoor or "",
                  update_strava_walking or "", update_strava_swimming or "", refresh_token or "",
                  effective_gps_simplification, effective_strava_agents_config or "",
                  effective_enable_weather_data))

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
        import gc
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
        # Release the massive GPS stream dataset (~200MB) and collect GC before timing sorting
        # queries so garbage collection does not pause subsequent query measurements.
        del gps_rows
        gc.collect()

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

        # 5. Paged activity grid (50 rows per page - UI default)
        t0 = time.perf_counter()
        paged_activities = self.get_activities_web(limit=50, offset=0, sort_by='start_date', sort_order='DESC', start_date=since_date_iso)
        paged_ms = (time.perf_counter() - t0) * 1000.0
        paged_count = len(paged_activities)

        # 6. Aggregate metric totals (distance, elevation, moving time)
        t0 = time.perf_counter()
        totals = self.get_activities_totals(start_date=since_date_iso)
        totals_ms = (time.perf_counter() - t0) * 1000.0

        # 7. Fitness suffer scores (CTL/ATL/TSB trend)
        t0 = time.perf_counter()
        suffer_scores = self.get_activities_with_suffer_score(days=scope_days)
        suffer_ms = (time.perf_counter() - t0) * 1000.0
        suffer_count = len(suffer_scores)

        # 8. Activity count query
        t0 = time.perf_counter()
        activity_count = self.count_activities(start_date=since_date_iso)
        count_ms = (time.perf_counter() - t0) * 1000.0

        return {
            'gps_ms': gps_ms,
            'gps_count': gps_count,
            'order_name_ms': order_name_ms,
            'order_name_count': order_name_count,
            'order_dist_ms': order_dist_ms,
            'order_dist_count': order_dist_count,
            'order_elev_ms': order_elev_ms,
            'order_elev_count': order_elev_count,
            'paged_ms': paged_ms,
            'paged_count': paged_count,
            'totals_ms': totals_ms,
            'suffer_ms': suffer_ms,
            'suffer_count': suffer_count,
            'count_ms': count_ms,
            'activity_count': activity_count,
        }

    def search_activities(
        self,
        athlete_id: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
        """Search activities with multi-metric bounds, keyword search, and keyset pagination."""
        self._ensure_connected()
        filters = filters or {}
        limit = max(1, min(int(limit), 200))

        sort_field_map = {
            "date": "start_date",
            "start_date": "start_date",
            "distance": "distance",
            "elevation": "total_elevation_gain",
            "total_elevation_gain": "total_elevation_gain",
            "moving_time": "moving_time",
            "average_watts": "average_watts",
            "watts": "average_watts",
            "max_watts": "max_watts",
            "speed": "average_speed",
            "average_speed": "average_speed",
            "max_speed": "max_speed",
            "heartrate": "average_heartrate",
            "average_heartrate": "average_heartrate",
            "max_heartrate": "max_heartrate",
            "suffer_score": "suffer_score",
            "calories": "calories",
        }
        sort_by = filters.get("sort_by", "date")
        sort_col = sort_field_map.get(sort_by, "start_date")
        sort_order = "ASC" if str(filters.get("sort_order", "desc")).lower() == "asc" else "DESC"
        op = ">" if sort_order == "ASC" else "<"

        where_clauses = []
        params: List[Any] = []

        if athlete_id:
            where_clauses.append("athlete_id = %s")
            params.append(athlete_id)

        sport_types = filters.get("sport_types")
        if sport_types:
            placeholders = ", ".join(["%s"] * len(sport_types))
            where_clauses.append(f"sport IN ({placeholders})")
            params.extend(sport_types)

        if filters.get("start_date"):
            where_clauses.append("start_date >= %s")
            params.append(filters["start_date"])

        if filters.get("end_date"):
            where_clauses.append("start_date <= %s")
            params.append(filters["end_date"])

        min_dist_km = filters.get("min_distance_km")
        if min_dist_km is None and filters.get("min_distance") is not None:
            min_dist_km = float(filters["min_distance"]) / 1000.0
        if min_dist_km is not None:
            where_clauses.append("distance >= %s")
            params.append(float(min_dist_km) * 1000.0)

        max_dist_km = filters.get("max_distance_km")
        if max_dist_km is None and filters.get("max_distance") is not None:
            max_dist_km = float(filters["max_distance"]) / 1000.0
        if max_dist_km is not None:
            where_clauses.append("distance <= %s")
            params.append(float(max_dist_km) * 1000.0)

        min_elev = filters.get("min_elevation_m") if filters.get("min_elevation_m") is not None else filters.get("min_elevation")
        if min_elev is not None:
            where_clauses.append("total_elevation_gain >= %s")
            params.append(float(min_elev))

        max_elev = filters.get("max_elevation_m") if filters.get("max_elevation_m") is not None else filters.get("max_elevation")
        if max_elev is not None:
            where_clauses.append("total_elevation_gain <= %s")
            params.append(float(max_elev))

        min_mov_s = filters.get("min_moving_time_s")
        if min_mov_s is None and filters.get("min_moving_time") is not None:
            min_mov_s = int(filters["min_moving_time"])
        if min_mov_s is None and filters.get("min_moving_time_min") is not None:
            min_mov_s = int(float(filters["min_moving_time_min"]) * 60)
        if min_mov_s is not None:
            where_clauses.append("moving_time >= %s")
            params.append(int(min_mov_s))

        max_mov_s = filters.get("max_moving_time_s")
        if max_mov_s is None and filters.get("max_moving_time") is not None:
            max_mov_s = int(filters["max_moving_time"])
        if max_mov_s is None and filters.get("max_moving_time_min") is not None:
            max_mov_s = int(float(filters["max_moving_time_min"]) * 60)
        if max_mov_s is not None:
            where_clauses.append("moving_time <= %s")
            params.append(int(max_mov_s))

        if filters.get("min_watts") is not None:
            where_clauses.append("average_watts >= %s")
            params.append(float(filters["min_watts"]))

        if filters.get("max_watts") is not None:
            where_clauses.append("average_watts <= %s")
            params.append(float(filters["max_watts"]))

        if filters.get("min_max_watts") is not None:
            where_clauses.append("max_watts >= %s")
            params.append(float(filters["min_max_watts"]))

        if filters.get("max_max_watts") is not None:
            where_clauses.append("max_watts <= %s")
            params.append(float(filters["max_max_watts"]))

        if filters.get("has_power") is not None:
            if bool(filters["has_power"]):
                where_clauses.append("(device_watts = TRUE OR average_watts > 0)")
            else:
                where_clauses.append("(device_watts = FALSE OR device_watts IS NULL)")

        if filters.get("min_heartrate") is not None:
            where_clauses.append("average_heartrate >= %s")
            params.append(float(filters["min_heartrate"]))

        if filters.get("max_heartrate") is not None:
            where_clauses.append("average_heartrate <= %s")
            params.append(float(filters["max_heartrate"]))

        if filters.get("has_heartrate") is not None:
            if bool(filters["has_heartrate"]):
                where_clauses.append("(has_heartrate = TRUE OR average_heartrate > 0)")
            else:
                where_clauses.append("(has_heartrate = FALSE OR has_heartrate IS NULL)")

        if filters.get("min_speed_kmh") is not None:
            where_clauses.append("average_speed >= %s")
            params.append(float(filters["min_speed_kmh"]) / 3.6)

        if filters.get("max_speed_kmh") is not None:
            where_clauses.append("average_speed <= %s")
            params.append(float(filters["max_speed_kmh"]) / 3.6)

        if filters.get("min_suffer_score") is not None:
            where_clauses.append("suffer_score >= %s")
            params.append(int(float(filters["min_suffer_score"])))

        if filters.get("max_suffer_score") is not None:
            where_clauses.append("suffer_score <= %s")
            params.append(int(float(filters["max_suffer_score"])))

        if filters.get("min_pr_count") is not None:
            where_clauses.append("pr_count >= %s")
            params.append(int(filters["min_pr_count"]))

        if filters.get("gear_id"):
            where_clauses.append("gear_id = %s")
            params.append(str(filters["gear_id"]).strip())

        if filters.get("workout_type") is not None:
            where_clauses.append("workout_type = %s")
            params.append(int(filters["workout_type"]))

        if filters.get("has_trophies"):
            where_clauses.append("(trophies IS NOT NULL AND trophies != '' AND trophies != '{}')")

        if filters.get("koms_only"):
            where_clauses.append("trophies LIKE %s")
            params.append('%"1":%')

        keyword = filters.get("keyword") or filters.get("query")
        if keyword:
            where_clauses.append("(name ILIKE %s OR CAST(activity_id AS TEXT) LIKE %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        if cursor:
            decoded = decode_cursor(cursor)
            if decoded:
                c_val, c_date, c_id = decoded
                if sort_col == "start_date":
                    where_clauses.append(f"(start_date {op} %s OR (start_date = %s AND activity_id {op} %s))")
                    params.extend([c_date, c_date, c_id])
                else:
                    where_clauses.append(f"({sort_col} {op} %s OR ({sort_col} = %s AND (start_date {op} %s OR (start_date = %s AND activity_id {op} %s))))")
                    params.extend([c_val, c_val, c_date, c_date, c_id])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        if sort_col == "start_date":
            order_sql = f"ORDER BY start_date {sort_order}, activity_id {sort_order}"
        else:
            order_sql = f"ORDER BY {sort_col} {sort_order}, start_date {sort_order}, activity_id {sort_order}"

        fetch_limit = limit + 1
        query = f"""
            SELECT activity_id, name, sport, athlete_id, distance, moving_time, elapsed_time,
                   total_elevation_gain, start_date, average_speed, max_speed,
                   average_heartrate, max_heartrate, average_cadence, average_watts,
                   max_watts, weighted_average_watts, device_watts, calories,
                   kilojoules, achievement_count, pr_count, suffer_score, average_temp,
                   gear_id, has_heartrate, workout_type, trophies
            FROM activities
            {where_sql}
            {order_sql}
            LIMIT %s
        """
        params.append(fetch_limit)

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            raw_rows = cur.fetchall()

        rows = []
        for r in raw_rows:
            act = dict(r)
            if isinstance(act.get("start_date"), datetime):
                act["start_date"] = act["start_date"].isoformat()
            if act.get("trophies") and isinstance(act["trophies"], str):
                try:
                    act["trophies"] = json.loads(act["trophies"])
                except Exception:
                    pass
            rows.append(act)

        has_more = len(rows) > limit
        if has_more:
            activities = rows[:limit]
            last = activities[-1]
            next_cursor = encode_cursor(last.get(sort_col), last["start_date"], last["activity_id"])
        else:
            activities = rows
            next_cursor = None

        return activities, next_cursor, has_more

    def get_stream_coverage(self, activity_id: int) -> Dict[str, Any]:
        """Retrieve sensor presence, row counts, and timestamp coverage for an activity."""
        self._ensure_connected()
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) AS total_points,
                    MIN(ts) AS first_ts,
                    MAX(ts) AS last_ts,
                    COUNT(watts) AS watts_count,
                    COUNT(heartrate) AS heartrate_count,
                    COUNT(cadence) AS cadence_count,
                    COUNT(altitude) AS altitude_count,
                    COUNT(lat) AS latlng_count,
                    COUNT(speed) AS speed_count,
                    COUNT(temp) AS temp_count
                FROM streams
                WHERE activity_id = %s
            """, (activity_id,))
            row = cur.fetchone() or {}

        first_ts = row.get("first_ts")
        last_ts = row.get("last_ts")
        first_iso = first_ts.isoformat() if isinstance(first_ts, datetime) else str(first_ts) if first_ts else None
        last_iso = last_ts.isoformat() if isinstance(last_ts, datetime) else str(last_ts) if last_ts else None

        channels = {}
        for ch in ("watts", "heartrate", "cadence", "altitude", "latlng", "speed", "temp"):
            cnt = int(row.get(f"{ch}_count") or 0)
            channels[ch] = {
                "present": cnt > 0,
                "count": cnt,
            }

        return {
            "activity_id": activity_id,
            "total_points": int(row.get("total_points") or 0),
            "first_ts": first_iso,
            "last_ts": last_iso,
            "channels": channels,
        }

    def get_activity_stream_window(
        self,
        activity_id: int,
        columns: List[str],
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        max_rows: int = 500,
    ) -> List[Dict[str, Any]]:
        """Retrieve timestamp-aligned multi-channel stream samples within a window."""
        self._ensure_connected()
        allowed = {"ts", "lat", "lng", "altitude", "heartrate", "cadence", "speed", "distance", "watts", "temp", "grade_smooth", "moving"}
        cols = [c for c in columns if c in allowed]
        if "ts" not in cols:
            cols.insert(0, "ts")
        if len(cols) == 1 and cols[0] == "ts":
            cols.extend(["watts", "heartrate", "cadence", "altitude"])

        col_str = ", ".join(cols)
        where_clauses = ["activity_id = %s"]
        params: List[Any] = [activity_id]

        if start_ts is not None:
            where_clauses.append("ts >= %s")
            params.append(datetime.fromtimestamp(start_ts, tz=timezone.utc))

        if end_ts is not None:
            where_clauses.append("ts <= %s")
            params.append(datetime.fromtimestamp(end_ts, tz=timezone.utc))

        where_sql = " AND ".join(where_clauses)
        limit = max(1, min(int(max_rows), 20000))
        params.append(limit)

        query = f"SELECT {col_str} FROM streams WHERE {where_sql} ORDER BY ts ASC LIMIT %s"
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            raw_rows = cur.fetchall()

        result = []
        for r in raw_rows:
            d = dict(r)
            if isinstance(d.get("ts"), datetime):
                d["ts"] = d["ts"].isoformat()
            result.append(d)
        return result
