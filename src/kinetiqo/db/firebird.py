import sys
import logging
import fdb
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, List, Dict, Any
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
                logger.info(f"Connected to Firebird at {config.firebird_host}:{config.firebird_port} - {self.get_firebird_version()}")
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
            
            conn = fdb.connect(
                dsn=dsn,
                user=self.config.firebird_user,
                password=self.config.firebird_password,
                charset='UTF8'
            )
            conn.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITTED
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to Firebird: {e}")
            raise

    def _ensure_database(self):
        """Ensures the target database exists. If it doesn't, try to create it."""
        try:
            # Try to check if database is accessible
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM RDB$DATABASE")
                cur.fetchone()
        except Exception as e:
            logger.warning(f"Database check failed: {e}")
            # Try to create database if it doesn't exist
            try:
                dsn = f"{self.config.firebird_host}/{self.config.firebird_port}:{self.config.firebird_database}"
                fdb.create_database(
                    f"CREATE DATABASE '{dsn}' USER '{self.config.firebird_user}' PASSWORD '{self.config.firebird_password}'"
                )
                logger.info(f"Database '{self.config.firebird_database}' created successfully.")
                # Reconnect to the newly created database
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
        """Create or update the database schema using SchemaManager."""
        schema_manager = SchemaManager(self.conn, 'firebird')
        
        # For Firebird, we need to create a sequence/generator for the auto-increment logs.id
        with self.conn.cursor() as cur:
            try:
                cur.execute("CREATE SEQUENCE logs_id_seq")
                self.conn.commit()
            except Exception:
                # Sequence already exists
                pass
        
        schema_manager.ensure_schema()
        
        # Create trigger for auto-increment on logs.id
        with self.conn.cursor() as cur:
            try:
                cur.execute("""
                    CREATE TRIGGER logs_bi FOR logs
                    ACTIVE BEFORE INSERT POSITION 0
                    AS
                    BEGIN
                        IF (NEW.id IS NULL) THEN
                            NEW.id = NEXT VALUE FOR logs_id_seq;
                    END
                """)
                self.conn.commit()
            except Exception:
                # Trigger already exists
                pass

    def flightcheck(self) -> bool:
        """Perform a health check on the database."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM RDB$DATABASE")
                
                # Check if tables exist
                cur.execute("""
                    SELECT TRIM(RDB$RELATION_NAME)
                    FROM RDB$RELATIONS
                    WHERE RDB$RELATION_NAME IN (UPPER('activities'), UPPER('streams'), UPPER('logs'))
                    AND RDB$SYSTEM_FLAG = 0
                """)
                tables = {row[0].lower() for row in cur.fetchall()}
                
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

            cur.execute("SELECT timestamp FROM activities WHERE activity_id = ?", (max_activity_id,))

            result = cur.fetchone()
            if result and result[0]:
                ts = int(result[0].replace(tzinfo=timezone.utc).timestamp())
                logger.debug(f"Latest activity {max_activity_id} start time: {ts}")
                return ts
            return None

    def get_synced_activity_ids(self) -> Set[str]:
        """Get all activity IDs already in the database."""
        logger.debug("Querying Firebird for all synced activity IDs...")
        with self.conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities")
            synced_ids = {str(row[0]) for row in cur.fetchall()}
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from Firebird.")
        return synced_ids

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT FIRST ?
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
            """, (limit,))

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
                    'average_heartrate': row[8]
                }
                activities.append(activity)
            return activities

    def get_activities_web(self, limit=10, offset=0, sort_by='timestamp', sort_order='DESC', types=None, start_date=None, end_date=None):
        """Fetch activities with pagination and sorting from Firebird"""
        allowed_columns = ['timestamp', 'activity_id', 'name', 'sport', 'distance', 'moving_time',
                           'total_elevation_gain', 'average_speed', 'average_heartrate']
        if sort_by not in allowed_columns:
            sort_by = 'timestamp'

        sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'

        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['?'] * len(types))
            where_conditions.append(f"sport IN ({placeholders})")
            params.extend(types)

        if start_date:
            where_conditions.append("timestamp >= ?")
            params.append(start_date)

        if end_date:
            if len(end_date) == 10:
                end_date += " 23:59:59.999999"
            where_conditions.append("timestamp <= ?")
            params.append(end_date)

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        # Firebird uses FIRST/SKIP for pagination
        query = f"""
            SELECT FIRST ? SKIP ?
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
        """
        # FIRST and SKIP come before other params
        all_params = [limit, offset] + params

        with self.conn.cursor() as cur:
            cur.execute(query, tuple(all_params))

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
                    'average_heartrate': row[8]
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
                WHERE activity_id IN ({placeholders})
                ORDER BY timestamp DESC
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
                    'average_heartrate': row[8]
                }
                activities.append(activity)
            return activities

    def get_activities_totals(self, types=None, start_date=None, end_date=None) -> Dict[str, float]:
        """Get totals for distance, elevation, and moving_time for the filtered activities."""
        where_conditions = []
        params = []

        if types:
            placeholders = ', '.join(['?'] * len(types))
            where_conditions.append(f"sport IN ({placeholders})")
            params.extend(types)

        if start_date:
            where_conditions.append("timestamp >= ?")
            params.append(start_date)

        if end_date:
            if len(end_date) == 10:
                end_date += " 23:59:59.999999"
            where_conditions.append("timestamp <= ?")
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
            where_clause = f"WHERE sport IN ({placeholders})"
            params.extend(types)

        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM activities {where_clause}", tuple(params))
            result = cur.fetchone()
            return result[0] if result else 0

    def write_activity(self, activity: dict):
        """Write activity metadata to Firebird."""
        activity_id = activity["id"]
        start_date = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))
        start_date = self._validate_timestamp(start_date)

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

        logger.debug(f"Writing activity metadata for {activity_id} to Firebird...")

        with self.conn.cursor() as cur:
            # Firebird uses UPDATE OR INSERT (MERGE in later versions)
            cur.execute("""
                UPDATE OR INSERT INTO activities (timestamp, activity_id, name, sport, athlete_id, distance,
                                        moving_time, elapsed_time, total_elevation_gain, average_speed,
                                        max_speed, average_heartrate, max_heartrate, average_cadence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                MATCHING (activity_id)
            """, row)
        self.conn.commit()

    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to Firebird."""
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
        start_date = self._validate_timestamp(start_date)

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

        logger.debug(f"Writing {len(rows)} stream rows to Firebird for activity {activity_id}...")

        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM streams WHERE activity_id = ?", (activity_id,))
            
            for row in rows:
                cur.execute("""
                    INSERT INTO streams (timestamp, activity_id, sport, athlete_id, lat, lng, altitude,
                                        heartrate, cadence, speed, distance)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, row)
        self.conn.commit()

    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from Firebird."""
        logger.debug(f"Deleting activity {activity_id} from Firebird...")

        aid = int(activity_id)

        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM activities WHERE activity_id = ?", (aid,))
            logger.info(f"Deleted activity {aid} and its streams.")
        self.conn.commit()

    def delete_activities(self, activity_ids: List[str]):
        """Delete multiple activities and their streams from Firebird."""
        if not activity_ids:
            return

        logger.debug(f"Deleting {len(activity_ids)} activities from Firebird...")
        int_ids = [int(aid) for aid in activity_ids]
        placeholders = ', '.join(['?'] * len(int_ids))

        with self.conn.cursor() as cur:
            cur.execute(f"DELETE FROM activities WHERE activity_id IN ({placeholders})", int_ids)
            logger.info(f"Deleted {len(activity_ids)} activities and their streams.")
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
                SELECT activity_id, lat, lng
                FROM streams
                WHERE activity_id IN ({placeholders})
                  AND lat IS NOT NULL
                  AND lng IS NOT NULL
                ORDER BY activity_id, timestamp
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

    def get_activity_name(self, activity_id: str) -> Optional[str]:
        """Get the name of an activity by its ID."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT name FROM activities WHERE activity_id = ?", (int(activity_id),))
            row = cur.fetchone()
            return row[0] if row else None

    def log_sync(self, added: int, removed: int, trigger: str, success: bool, action: str, user: str):
        """Log the result of a sync operation."""
        with self.conn.cursor() as cur:
            # Convert boolean to smallint for Firebird
            success_int = 1 if success else 0
            cur.execute("""
                INSERT INTO logs (added, removed, trigger_source, success, action, "user")
                VALUES (?, ?, ?, ?, ?, ?)
            """, (added, removed, trigger, success_int, action, user))
        self.conn.commit()

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the latest sync logs."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT FIRST ?
                    timestamp, added, removed, trigger_source, success, action, "user"
                FROM logs
                ORDER BY timestamp DESC
            """, (limit,))
            
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

    def close(self):
        self.conn.close()
