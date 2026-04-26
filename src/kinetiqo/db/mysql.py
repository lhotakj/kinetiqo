import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any, Tuple

import mysql.connector
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository
from kinetiqo.db.schema import SchemaManager
from mysql.connector import errorcode

logger = logging.getLogger("kinetiqo")


class MySQLRepository(DatabaseRepository):
    def __init__(self, config: Config):
        self.config = config
        try:
            self.conn = self._connect()
        except Exception as err:
            logger.warning(f"Cannot connect to MySQL: {err}")
            sys.exit(1)

        try:
            self._create_database()
        except Exception as err:
            logger.warning(f"Cannot create database: {err}")
            sys.exit(1)

    def _connect(self):
        """Helper to connect to a specific database."""
        connect_args = {
            "host": self.config.mysql_host,
            "port": self.config.mysql_port,
            "user": self.config.mysql_user,
            "password": self.config.mysql_password,
            "database": self.config.mysql_database  # Ensure database is selected
        }

        try:
            conn = mysql.connector.connect(**connect_args)
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_BAD_DB_ERROR:
                # Database does not exist, connect without database to create it
                del connect_args["database"]
                try:
                    conn = mysql.connector.connect(**connect_args)
                except Exception as e:
                    logger.error(str(e))
                    raise
            else:
                logger.error(str(err))
                raise
        except (ValueError, TypeError) as err:
            logger.error(str(err))
            raise

        # Enable autocommit so every statement (including SELECTs) sees the
        # latest committed data.  Without this, InnoDB's default REPEATABLE
        # READ isolation keeps a snapshot from the first statement in an
        # implicit transaction, causing the web UI to show stale data after
        # a CLI sync commits new activities from a different connection.
        conn.autocommit = True
        return conn

    def _ensure_connected(self):
        """Verify the connection is alive; transparently reconnect if not.

        Gunicorn workers or long-running CLI syncs may hold connections that
        the server has closed due to idle timeout (``wait_timeout``).  A
        lightweight ``ping()`` followed by a reconnect avoids unexpected
        "MySQL server has gone away" errors.
        """
        try:
            self.conn.ping(reconnect=True, attempts=3, delay=1)
        except Exception:
            logger.warning("MySQL connection lost, reconnecting...")
            try:
                self.conn = self._connect()
                self.conn.database = self.config.mysql_database
            except Exception as e:
                logger.error(f"Failed to reconnect to MySQL: {e}")
                raise
        # Re-apply autocommit in case ping's reconnect reset session state
        if not self.conn.autocommit:
            self.conn.autocommit = True

    def _create_database(self):
        """Creates the target database if it doesn't exist."""
        try:
            if self.conn.database == self.config.mysql_database:
                return

            with self.conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS {self.config.mysql_database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

            self.conn.database = self.config.mysql_database

        except Exception as err:
            try:
                self.conn.database = self.config.mysql_database
            except:
                logger.warning(f"Cannot create/select database: {err}")
                sys.exit(1)

    def get_mysql_version(self) -> str:
        """Get the MySQL version string."""
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("SELECT VERSION();")
            result = cur.fetchone()
            return result[0] if result else "Unknown"

    def initialize_schema(self):
        """Create or update the database schema using SchemaManager."""
        self._ensure_connected()
        schema_manager = SchemaManager(self.conn, 'mysql')
        schema_manager.ensure_schema()

    def flightcheck(self) -> bool:
        """Perform a health check on the database."""
        try:
            self._ensure_connected()
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")

                cur.execute("USE information_schema;")
                cur.execute(
                    "SELECT table_name FROM tables WHERE table_schema = %s AND table_name IN ('activities', 'streams', 'logs')",
                    (self.config.mysql_database,))
                tables = {row[0] for row in cur.fetchall()}
                cur.execute(f"USE {self.config.mysql_database};")

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
        """Get the start timestamp of the most recent activity."""
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
        logger.debug("Querying MySQL for all synced activity IDs...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities")
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from MySQL.")
        return synced_ids

    def get_synced_activity_ids_since(self, after_epoch: int) -> Set[str]:
        """Get activity IDs whose start_date is at or after *after_epoch*."""
        self._ensure_connected()
        dt = datetime.fromtimestamp(after_epoch, tz=timezone.utc)
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities WHERE start_date >= %s", (dt,))
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from MySQL since {dt}.")
        return synced_ids

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        self._ensure_connected()
        with self.conn.cursor(dictionary=True) as cur:
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
        """Fetch activities with pagination and sorting from MySQL"""
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
                workout_type,
                max_speed
            FROM activities
            {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        with self.conn.cursor(dictionary=True) as cur:
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
        placeholders = ', '.join(['%s'] * len(int_ids))

        with self.conn.cursor(dictionary=True) as cur:
            cur.execute(f"""
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
                WHERE activity_id IN ({placeholders})
                ORDER BY start_date DESC
            """, int_ids)

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

        with self.conn.cursor(dictionary=True) as cur:
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
        """Write activity metadata to MySQL."""
        self._ensure_connected()
        activity_id = activity["id"]
        start_date = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))

        if start_date.timestamp() <= 0:
            start_date = datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)

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

        logger.debug(f"Writing activity metadata for {activity_id} to MySQL...")

        with self.conn.cursor() as cur:
            cur.execute("""
                        INSERT INTO activities (start_date, activity_id, name, sport, athlete_id, distance,
                                                moving_time, elapsed_time, total_elevation_gain, average_speed,
                                                max_speed, average_heartrate, max_heartrate, average_cadence,
                                                average_watts, max_watts, achievement_count, average_temp,
                                                calories, device_watts, elev_high, elev_low, gear_id,
                                                has_heartrate, kilojoules, pr_count, suffer_score,
                                                weighted_average_watts, workout_type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY
                        UPDATE
                            start_date = VALUES (start_date),
                            name = VALUES (name),
                            sport = VALUES (sport),
                            athlete_id = VALUES (athlete_id),
                            distance = VALUES (distance),
                            moving_time = VALUES (moving_time),
                            elapsed_time = VALUES (elapsed_time),
                            total_elevation_gain = VALUES (total_elevation_gain),
                            average_speed = VALUES (average_speed),
                            max_speed = VALUES (max_speed),
                            average_heartrate = VALUES (average_heartrate),
                            max_heartrate = VALUES (max_heartrate),
                            average_cadence = VALUES (average_cadence),
                            average_watts = VALUES (average_watts),
                            max_watts = VALUES (max_watts),
                            achievement_count = VALUES (achievement_count),
                            average_temp = VALUES (average_temp),
                            calories = VALUES (calories),
                            device_watts = VALUES (device_watts),
                            elev_high = VALUES (elev_high),
                            elev_low = VALUES (elev_low),
                            gear_id = VALUES (gear_id),
                            has_heartrate = VALUES (has_heartrate),
                            kilojoules = VALUES (kilojoules),
                            pr_count = VALUES (pr_count),
                            suffer_score = VALUES (suffer_score),
                            weighted_average_watts = VALUES (weighted_average_watts),
                            workout_type = VALUES (workout_type)
                        """, row)
        self.conn.commit()

    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to MySQL."""
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

        if start_date.timestamp() <= 0:
            start_date = datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)

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

        logger.debug(f"Writing {len(rows)} stream rows to MySQL for activity {activity_id}...")

        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM streams WHERE activity_id = %s", (activity_id,))

            cur.executemany("""
                            INSERT INTO streams (ts, activity_id, sport, athlete_id, lat, lng, altitude,
                                                 heartrate, cadence, speed, distance, watts, temp,
                                                 grade_smooth, moving)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, rows)


        self.conn.commit()

    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from MySQL."""
        self._ensure_connected()
        logger.debug(f"Deleting activity {activity_id} from MySQL...")

        aid = int(activity_id)

        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM activities WHERE activity_id = %s", (aid,))
            logger.info(f"Deleted activity {aid} and its streams.")
        self.conn.commit()

    def delete_activities(self, activity_ids: List[str]):
        """Delete multiple activities and their streams from MySQL."""
        if not activity_ids:
            return

        self._ensure_connected()
        logger.debug(f"Deleting {len(activity_ids)} activities from MySQL...")
        int_ids = [int(aid) for aid in activity_ids]
        placeholders = ', '.join(['%s'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"DELETE FROM activities WHERE activity_id IN ({placeholders})", int_ids)
            logger.info(f"Deleted {len(activity_ids)} activities and their streams.")
        self.conn.commit()

    def get_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get GPS streams (lat, lng) for a list of activity IDs."""
        if not activity_ids:
            return {}

        self._ensure_connected()
        result = {}
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor(dictionary=True) as cur:
            placeholders = ', '.join(['%s'] * len(int_ids))
            cur.execute(f"""
                SELECT activity_id, lat, lng
                FROM streams
                WHERE activity_id IN ({placeholders})
                  AND lat IS NOT NULL
                  AND lng IS NOT NULL
                ORDER BY activity_id, ts
            """, int_ids)

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
        placeholders = ', '.join(['%s'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT activity_id, lat, lng
                FROM streams
                WHERE activity_id IN ({placeholders})
                  AND lat IS NOT NULL
                  AND lng IS NOT NULL
                ORDER BY activity_id, ts
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

        self._ensure_connected()
        int_ids = [int(aid) for aid in activity_ids]
        placeholders = ', '.join(['%s'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT MIN(lat), MIN(lng), MAX(lat), MAX(lng)
                FROM streams
                WHERE activity_id IN ({placeholders})
                  AND lat IS NOT NULL
                  AND lng IS NOT NULL
            """, int_ids)
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
                        INSERT INTO logs (added, removed, trigger_source, success, action, user)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (added, removed, trigger, success, action, user))
        self.conn.commit()

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest sync logs."""
        self._ensure_connected()
        with self.conn.cursor(dictionary=True) as cur:
            cur.execute("""
                        SELECT created_at as timestamp, added, removed, trigger_source, success, action, user
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
            placeholders = ', '.join(['%s'] * len(int_ids))
            cur.execute(f"""
                SELECT activity_id, watts
                FROM streams
                WHERE activity_id IN ({placeholders})
                  AND watts IS NOT NULL
                ORDER BY activity_id, ts
            """, int_ids)

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
        """Compute best rolling-average power per activity.

        MySQL 8.0 implements ``AVG() OVER (ROWS BETWEEN K PRECEDING …)`` with
        **O(N×K) naive recomputation** — it re-sums K values for every row
        rather than maintaining a sliding accumulator.  For FTP (K=1199) over
        ~500 K rows this means ~600 M arithmetic operations and the query
        never finishes.

        Instead we fetch the raw watts via ``get_watts_streams_for_activities``
        (which uses the ``idx_streams_activity_ts_watts`` covering index
        efficiently) and compute the sliding-window maximum in Python using
        the O(N) ``compute_best_power_per_activity`` helper.
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
        """Get lightweight activity records filtered by sport type.

        When *since_date* is provided the date predicate is pushed to SQL.
        The composite index ``idx_activities_sport_start_date`` on
        ``(sport, start_date DESC)`` covers both the filter and the sort.

        When *watts_only* is ``True``, only activities with measured power data
        (``average_watts IS NOT NULL``) are returned, cutting the stream I/O
        for VO2max / FTP calculations.
        """
        if not types:
            return []

        self._ensure_connected()
        extra = " AND average_watts IS NOT NULL" if watts_only else ""
        with self.conn.cursor(dictionary=True) as cur:
            placeholders = ', '.join(['%s'] * len(types))
            if since_date is not None:
                params = list(types) + [since_date]
                cur.execute(f"""
                    SELECT activity_id AS id, name, start_date
                    FROM activities
                    WHERE sport IN ({placeholders})
                      AND start_date >= %s{extra}
                    ORDER BY start_date DESC
                """, params)
            else:
                cur.execute(f"""
                    SELECT activity_id AS id, name, start_date
                    FROM activities
                    WHERE sport IN ({placeholders}){extra}
                    ORDER BY start_date DESC
                """, types)

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
        with self.conn.cursor(dictionary=True) as cur:
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
        with self.conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT athlete_id, first_name, last_name, weight FROM profile LIMIT 1")
            return cur.fetchone()

    def upsert_profile(self, athlete_id: int, first_name: str, last_name: str, weight: float):
        self._ensure_connected()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO profile (athlete_id, first_name, last_name, weight)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    first_name = VALUES(first_name),
                    last_name  = VALUES(last_name),
                    weight     = VALUES(weight)
            """, (athlete_id, first_name, last_name, weight))

    # ------------------------------------------------------------------
    # Activity goals
    # ------------------------------------------------------------------

    def get_goals(self, athlete_id: int):
        self._ensure_connected()
        with self.conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT activity_type_id,
                       weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                       weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal
                FROM activity_goals
                WHERE athlete_id = %s
                ORDER BY activity_type_id
            """, (athlete_id,))
            return list(cur.fetchall())

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
                ON DUPLICATE KEY UPDATE
                    weekly_distance_goal  = VALUES(weekly_distance_goal),
                    monthly_distance_goal = VALUES(monthly_distance_goal),
                    yearly_distance_goal  = VALUES(yearly_distance_goal),
                    weekly_elevation_goal  = VALUES(weekly_elevation_goal),
                    monthly_elevation_goal = VALUES(monthly_elevation_goal),
                    yearly_elevation_goal  = VALUES(yearly_elevation_goal)
            """, (athlete_id, activity_type_id,
                  weekly_distance_goal, monthly_distance_goal, yearly_distance_goal,
                  weekly_elevation_goal, monthly_elevation_goal, yearly_elevation_goal))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        try:
            if self.conn and self.conn.is_connected():
                self.conn.close()
        except Exception as e:
            logger.warning(f"Error closing MySQL connection: {e}")
