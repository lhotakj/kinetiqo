import sys
import logging
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository

logger = logging.getLogger("kinetiqo")

class PostgresRepository(DatabaseRepository):
    def __init__(self, config: Config):
        self.config = config
        try:
            self.conn = self._connect()
        except psycopg2.OperationalError as e:
            # Check if the error is "database does not exist"
            if f'database "{config.postgres_database}" does not exist' in str(e):
                logger.warning(f"Database '{config.postgres_database}' does not exist. Attempting to create it...")
                self._create_database()
                self.conn = self._connect()
            else:
                logger.error(f"Failed to connect to Postgres at {config.postgres_host}:{config.postgres_port}: {e}")
                sys.exit(1)

    def _connect(self, dbname=None):
        """Helper to connect to a specific database."""
        conn = psycopg2.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            database=dbname or self.config.postgres_database
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
                cur.execute(f"CREATE DATABASE {self.config.postgres_database}")
                logger.info(f"Database '{self.config.postgres_database}' created successfully.")
        except psycopg2.Error as e:
            logger.error(f"Could not create database '{self.config.postgres_database}': {e}")
            sys.exit(1)
        finally:
            if 'conn_temp' in locals() and conn_temp:
                conn_temp.close()

    def initialize_schema(self):
        """Create or update the activities and streams tables in Postgres."""
        logger.info("Postgres: Initializing schema...")

        with self.conn.cursor() as cur:
            # Create activities metadata table
            cur.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_name = 'activities'
                        """)
            activities_exists = cur.fetchone() is not None

            if not activities_exists:
                logger.info("Postgres: Creating 'activities' table...")
                cur.execute("""
                            CREATE TABLE activities
                            (
                                timestamp         TIMESTAMP WITH TIME ZONE,
                                activity_id       BIGINT PRIMARY KEY,
                                name              TEXT,
                                sport             TEXT,
                                athlete_id        BIGINT,
                                distance          DOUBLE PRECISION,
                                moving_time       INTEGER,
                                elapsed_time      INTEGER,
                                total_elevation_gain DOUBLE PRECISION,
                                average_speed     DOUBLE PRECISION,
                                max_speed         DOUBLE PRECISION,
                                average_heartrate INTEGER,
                                max_heartrate     INTEGER,
                                average_cadence   DOUBLE PRECISION
                            )
                            """)
                # Create index on timestamp for faster queries
                cur.execute("CREATE INDEX idx_activities_timestamp ON activities (timestamp DESC);")
                logger.info("Postgres: Table 'activities' created successfully.")
            else:
                logger.info("Postgres: Table 'activities' already exists.")

            # Create streams data table
            cur.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_name = 'streams'
                        """)
            streams_exists = cur.fetchone() is not None

            if not streams_exists:
                logger.info("Postgres: Creating 'streams' table...")
                cur.execute("""
                            CREATE TABLE streams
                            (
                                timestamp   TIMESTAMP WITH TIME ZONE,
                                activity_id BIGINT,
                                sport       TEXT,
                                athlete_id  BIGINT,
                                lat         DOUBLE PRECISION,
                                lng         DOUBLE PRECISION,
                                altitude    DOUBLE PRECISION,
                                heartrate   INTEGER,
                                cadence     INTEGER,
                                speed       DOUBLE PRECISION,
                                distance    DOUBLE PRECISION,
                                CONSTRAINT fk_activity
                                    FOREIGN KEY(activity_id) 
                                    REFERENCES activities(activity_id)
                                    ON DELETE CASCADE
                            )
                            """)
                # Create index on activity_id and timestamp
                cur.execute("CREATE INDEX idx_streams_activity_id ON streams (activity_id);")
                cur.execute("CREATE INDEX idx_streams_timestamp ON streams (timestamp);")
                logger.info("Postgres: Table 'streams' created successfully.")
            else:
                logger.info("Postgres: Table 'streams' already exists.")

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
        logger.debug("Querying Postgres for all synced activity IDs...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities")
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from Postgres.")
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
                    timestamp as start_date
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

    def get_activities_web(self, limit=10, offset=0, sort_by='timestamp', sort_order='DESC', types=None):
        """Fetch activities with pagination and sorting from Postgres"""
        allowed_columns = ['timestamp', 'activity_id', 'name', 'sport', 'distance', 'moving_time',
                           'total_elevation_gain']
        if sort_by not in allowed_columns:
            sort_by = 'timestamp'

        sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

        where_clause = ""
        params = []
        if types:
            placeholders = ', '.join(['%s'] * len(types))
            where_clause = f"WHERE sport IN ({placeholders})"
            params.extend(types)

        # Postgres supports LIMIT and OFFSET directly
        query = f"""
            SELECT
                activity_id as id,
                name,
                sport as type,
                distance,
                moving_time,
                total_elevation_gain,
                timestamp as start_date
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
        """Write activity metadata to Postgres."""
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

        logger.debug(f"Writing activity metadata for {activity_id} to Postgres...")

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
        """Write activity streams to Postgres."""
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

        logger.debug(f"Writing {len(rows)} stream rows to Postgres for activity {activity_id}...")

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
        """Delete an activity and its streams from Postgres."""
        logger.debug(f"Deleting activity {activity_id} from Postgres...")
        
        aid = int(activity_id)
        
        with self.conn.cursor() as cur:
            # Because of ON DELETE CASCADE on streams, deleting from activities is enough
            # But let's be explicit or rely on cascade. I added CASCADE in schema.
            # If schema was already created without cascade, we might need to delete streams first.
            # Let's delete streams first to be safe if schema wasn't recreated.
            cur.execute("DELETE FROM streams WHERE activity_id = %s", (aid,))
            cur.execute("DELETE FROM activities WHERE activity_id = %s", (aid,))
            logger.info(f"Deleted activity {aid} and its streams.")

    def close(self):
        self.conn.close()
