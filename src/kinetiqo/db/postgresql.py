import sys
import logging
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository
from kinetiqo.db.schema import SchemaManager

logger = logging.getLogger("kinetiqo")

class PostgresqlRepository(DatabaseRepository):
    def __init__(self, config: Config):
        self.config = config
        try:
            self.conn = self._connect()
            if config.database_connect_verbose:
                logger.info(f"Connected to PostgreSQL at {config.postgresql_host}:{config.postgresql_port} - {self.get_pg_version()}")
        except psycopg2.OperationalError as e:
            # Check if the error is "database does not exist"
            if f'database "{config.postgresql_database}" does not exist' in str(e):
                logger.warning(f"Database '{config.postgresql_database}' does not exist. Attempting to create it...")
                self._create_database()
                self.conn = self._connect()
            else:
                logger.error(f"Failed to connect to PostgreSQL at {config.postgresql_host}:{config.postgresql_port}: {e}")
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
        conn.autocommit = True
        return conn

    def _create_database(self):
        """Creates the target database if it doesn't exist."""
        # Connect to the default 'postgres' database to run CREATE DATABASE
        try:
            conn_temp = self._connect(dbname='postgres')
            with conn_temp.cursor() as cur:
                # CREATE DATABASE cannot run inside a transaction block.
                # The _connect method already sets autocommit=True, so we don't need to explicitly manage it here.
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
        with self.conn.cursor() as cur:
            cur.execute("SELECT version();")
            result = cur.fetchone()
            return result[0] if result else "Unknown"

    def initialize_schema(self):
        """Create or update the database schema using SchemaManager."""
        schema_manager = SchemaManager(self.conn, 'postgresql')
        schema_manager.ensure_schema()

    def flightcheck(self) -> bool:
        """Perform a health check on the database."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
                
                # Check if tables exist
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
        """Get the start timestamp of the activity with the highest ID."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT MAX(activity_id) FROM activities")
            result = cur.fetchone()
            if not result or result[0] is None:
                return None

            max_activity_id = result[0]

            cur.execute("""
                        SELECT timestamp
                        FROM activities
                        WHERE activity_id = %s
                        """, (max_activity_id,))

            result = cur.fetchone()
            if result and result[0]:
                ts = int(result[0].replace(tzinfo=timezone.utc).timestamp())
                logger.debug(f"Latest activity {max_activity_id} start time: {ts}")
                return ts
            return None

    def get_synced_activity_ids(self) -> Set[str]:
        """Get all activity IDs already in the database."""
        logger.debug("Querying PostgreSQL for all synced activity IDs...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities")
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from PostgreSQL.")
        return synced_ids

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    activity_id as id,
                    name,
                    sport as type,
                    distance,
                    moving_time,
                    total_elevation_gain,
                    timestamp as start_date,
                    average_speed,
                    average_heartrate
                FROM activities 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (limit,))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                activities.append(activity)
            return activities

    def get_activities_web(self, limit=10, offset=0, sort_by='timestamp', sort_order='DESC', types=None, start_date=None, end_date=None):
        """Fetch activities with pagination and sorting from PostgreSQL"""
        allowed_columns = ['timestamp', 'activity_id', 'name', 'sport', 'distance', 'moving_time',
                           'total_elevation_gain', 'average_speed', 'average_heartrate']
        if sort_by not in allowed_columns:
            sort_by = 'timestamp'

        sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['%s'] * len(types))
            where_conditions.append(f"sport IN ({placeholders})")
            params.extend(types)

        if start_date:
            where_conditions.append("timestamp >= %s")
            params.append(start_date)

        if end_date:
            # Ensure end_date covers the full day
            if len(end_date) == 10:  # YYYY-MM-DD
                end_date += " 23:59:59.999999"
            where_conditions.append("timestamp <= %s")
            params.append(end_date)

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        # PostgreSQL supports LIMIT and OFFSET directly
        query = f"""
            SELECT
                activity_id as id,
                name,
                sport as type,
                distance,
                moving_time,
                total_elevation_gain,
                timestamp as start_date,
                average_speed,
                average_heartrate
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

    def get_activities_totals(self, types=None, start_date=None, end_date=None) -> Dict[str, float]:
        """Get totals for distance, elevation, and moving_time for the filtered activities."""
        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['%s'] * len(types))
            where_conditions.append(f"sport IN ({placeholders})")
            params.extend(types)

        if start_date:
            where_conditions.append("timestamp >= %s")
            params.append(start_date)

        if end_date:
            # Ensure end_date covers the full day
            if len(end_date) == 10:  # YYYY-MM-DD
                end_date += " 23:59:59.999999"
            where_conditions.append("timestamp <= %s")
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
            activity.get("average_cadence")
        )

        logger.debug(f"Writing activity metadata for {activity_id} to PostgreSQL...")

        with self.conn.cursor() as cur:
            cur.execute("""
                        INSERT INTO activities (timestamp, activity_id, name, sport, athlete_id, distance,
                                                moving_time, elapsed_time, total_elevation_gain, average_speed,
                                                max_speed, average_heartrate, max_heartrate, average_cadence)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s)
                        ON CONFLICT (activity_id) DO UPDATE SET
                            timestamp = EXCLUDED.timestamp,
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
                            average_cadence = EXCLUDED.average_cadence
                        """, row)

    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to PostgreSQL."""
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
                distance_stream[i] if i < len(distance_stream) else None
            )
            rows.append(row)

        logger.debug(f"Writing {len(rows)} stream rows to PostgreSQL for activity {activity_id}...")

        with self.conn.cursor() as cur:
            # First delete existing streams for this activity to avoid duplicates if re-syncing
            cur.execute("DELETE FROM streams WHERE activity_id = %s", (activity_id,))

            execute_batch(cur, """
                               INSERT INTO streams (timestamp, activity_id, sport, athlete_id, lat, lng, altitude,
                                                    heartrate, cadence, speed, distance)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                                       %s, %s)
                               """, rows, page_size=1000)

    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from PostgreSQL."""
        logger.debug(f"Deleting activity {activity_id} from PostgreSQL...")

        aid = int(activity_id)

        with self.conn.cursor() as cur:
            # Because of ON DELETE CASCADE on streams, a delete on activities is enough
            cur.execute("DELETE FROM activities WHERE activity_id = %s", (aid,))
            logger.info(f"Deleted activity {aid} and its streams.")

    def get_streams_for_activities(self, activity_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get GPS streams (lat, lng) for a list of activity IDs."""
        if not activity_ids:
            return {}

        result = {}
        # Convert to integers for PostgreSQL
        int_ids = [int(aid) for aid in activity_ids]

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Use ANY for list of IDs
            cur.execute("""
                SELECT activity_id, lat, lng
                FROM streams
                WHERE activity_id = ANY(%s)
                  AND lat IS NOT NULL
                  AND lng IS NOT NULL
                ORDER BY activity_id, timestamp
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

    def get_activity_name(self, activity_id: str) -> Optional[str]:
        """Get the name of an activity by its ID."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT name FROM activities WHERE activity_id = %s
            """, (int(activity_id),))
            row = cur.fetchone()
            return row[0] if row else None

    def log_sync(self, added: int, removed: int, trigger: str, success: bool, action: str, user: str):
        """Log the result of a sync operation."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO logs (added, removed, trigger_source, success, action, "user")
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (added, removed, trigger, success, action, user))

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest sync logs."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT timestamp, added, removed, trigger_source, success, action, "user"
                FROM logs
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))
            
            logs = []
            for row in cur.fetchall():
                log = dict(row)
                if isinstance(log['timestamp'], datetime):
                    log['timestamp'] = log['timestamp'].isoformat()
                logs.append(log)
            return logs

    def close(self):
        self.conn.close()
