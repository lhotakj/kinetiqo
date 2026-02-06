import sys
import logging
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository

logger = logging.getLogger("kinetiqo")

class QuestDBRepository(DatabaseRepository):
    def __init__(self, config: Config):
        self.config = config
        try:
            self.conn = psycopg2.connect(
                host=config.questdb_host,
                port=config.questdb_port,
                user=config.questdb_user,
                password=config.questdb_password,
                database=config.questdb_database
            )
            self.conn.autocommit = True
        except psycopg2.OperationalError as e:
            logger.error(f"Failed to connect to QuestDB at {config.questdb_host}:{config.questdb_port}: {e}")
            sys.exit(1)

    def initialize_schema(self):
        """Create or update the activities and streams tables in QuestDB."""
        logger.info("QuestDB: Initializing schema...")

        with self.conn.cursor() as cur:
            # Create activities metadata table
            cur.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_name = 'activities'
                        """)
            activities_exists = cur.fetchone() is not None

            if not activities_exists:
                logger.info("QuestDB: Creating 'activities' table...")
                cur.execute("""
                            CREATE TABLE activities
                            (
                                timestamp         TIMESTAMP,
                                activity_id       LONG,
                                name              STRING,
                                sport             STRING,
                                athlete_id        LONG,
                                distance DOUBLE,
                                moving_time       INT,
                                elapsed_time      INT,
                                total_elevation_gain DOUBLE,
                                average_speed DOUBLE,
                                max_speed DOUBLE,
                                average_heartrate INT,
                                max_heartrate     INT,
                                average_cadence DOUBLE
                            ) timestamp(timestamp) PARTITION BY DAY
                            """)
                logger.info("QuestDB: Table 'activities' created successfully.")
            else:
                logger.info("QuestDB: Table 'activities' already exists.")

            # Create streams data table
            cur.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_name = 'streams'
                        """)
            streams_exists = cur.fetchone() is not None

            if not streams_exists:
                logger.info("QuestDB: Creating 'streams' table...")
                cur.execute("""
                            CREATE TABLE streams
                            (
                                timestamp   TIMESTAMP,
                                activity_id LONG,
                                sport       STRING,
                                athlete_id  LONG,
                                lat DOUBLE,
                                lng DOUBLE,
                                altitude DOUBLE,
                                heartrate   INT,
                                cadence     INT,
                                speed DOUBLE,
                                distance DOUBLE
                            ) timestamp(timestamp) PARTITION BY DAY
                            """)
                logger.info("QuestDB: Table 'streams' created successfully.")
            else:
                logger.info("QuestDB: Table 'streams' already exists.")

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
        logger.debug("Querying QuestDB for all synced activity IDs...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT DISTINCT activity_id FROM activities")
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from QuestDB.")
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
                # Convert to dict and format if necessary
                activity = dict(row)
                # Ensure start_date is a string or datetime as expected by the template
                if isinstance(activity['start_date'], datetime):
                    activity['start_date'] = activity['start_date'].isoformat()
                activities.append(activity)
            return activities

    def get_activities_web(self, limit=10, offset=0, sort_by='timestamp', sort_order='DESC', types=None):
        """Fetch activities with pagination and sorting from QuestDB"""
        # Validate sort_by to prevent SQL injection
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

        # Add limit and offset params
        params.extend([offset, offset + limit])

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # QuestDB requires different pagination approach
            # Use row_number() to implement offset
            query = f"""
                SELECT * FROM (
                    SELECT
                        activity_id as id,
                        name,
                        sport as type,
                        distance,
                        moving_time,
                        total_elevation_gain,
                        timestamp as start_date,
                        row_number() OVER (ORDER BY {sort_by} {sort_order}) as rn
                    FROM activities
                    {where_clause}
                )
                WHERE rn > %s AND rn <= %s
            """
            cur.execute(query, tuple(params))

            activities = []
            for row in cur.fetchall():
                activity = dict(row)
                # Remove the row_number column
                activity.pop('rn', None)
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
        """Write activity metadata to QuestDB."""
        activity_id = activity["id"]
        start_date = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))

        row = (
            start_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
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

        logger.debug(f"Writing activity metadata for {activity_id} to QuestDB...")

        with self.conn.cursor() as cur:
            cur.execute("""
                        INSERT INTO activities (timestamp, activity_id, name, sport, athlete_id, distance,
                                                moving_time, elapsed_time, total_elevation_gain, average_speed,
                                                max_speed, average_heartrate, max_heartrate, average_cadence)
                        VALUES (to_timestamp(%s, 'yyyy-MM-ddTHH:mm:ss.SSSUUUZ'), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s)
                        """, row)

    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to QuestDB."""
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
                ts.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
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

        logger.debug(f"Writing {len(rows)} stream rows to QuestDB for activity {activity_id}...")

        with self.conn.cursor() as cur:
            execute_batch(cur, """
                               INSERT INTO streams (timestamp, activity_id, sport, athlete_id, lat, lng, altitude,
                                                    heartrate, cadence, speed, distance)
                               VALUES (to_timestamp(%s, 'yyyy-MM-ddTHH:mm:ss.SSSUUUZ'), %s, %s, %s, %s, %s, %s, %s, %s,
                                       %s, %s)
                               """, rows, page_size=1000)

    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from QuestDB."""
        logger.debug(f"Deleting activity {activity_id} from QuestDB...")
        with self.conn.cursor() as cur:
            # Delete from activities metadata table
            cur.execute("DELETE FROM activities WHERE activity_id = %s", (int(activity_id),))
            # Delete from streams data table
            cur.execute("DELETE FROM streams WHERE activity_id = %s", (int(activity_id),))

    def close(self):
        self.conn.close()
