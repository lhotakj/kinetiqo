#!/bin/python3
import os
import sys
import requests
import logging
import click
from abc import ABC, abstractmethod
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timezone, timedelta
import time
from dataclasses import dataclass
from typing import Optional, Set, List
import psycopg2
from psycopg2.extras import execute_batch
import json
import hashlib
from pathlib import Path

# -----------------------------
# LOGGING SETUP
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("sync")
logger.setLevel(logging.DEBUG)

# Reduce noise from libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("influxdb_client").setLevel(logging.WARNING)


# -----------------------------
# CONFIGURATION
# -----------------------------
@dataclass
class Config:
    # Strava
    strava_client_id: str = os.getenv("STRAVA_CLIENT_ID")
    strava_client_secret: str = os.getenv("STRAVA_CLIENT_SECRET")
    strava_refresh_token: str = os.getenv("STRAVA_REFRESH_TOKEN")

    # Cache
    enable_strava_cache: bool = False
    cache_ttl: int = 60  # minutes
    cache_dir: Path = Path(".cache")

    # Database - Common
    database_type: str = os.getenv("DATABASE_TYPE", "questdb").lower()  # influxdb2 or questdb

    # InfluxDB2
    influx_token: str = os.getenv("INFLUX_TOKEN")
    influx_url: str = os.getenv("INFLUX_URL")
    influx_org: str = os.getenv("INFLUX_ORG")
    influx_bucket: str = os.getenv("INFLUX_BUCKET")
    influx_verify_ssl: bool = os.getenv("INFLUX_VERIFY_SSL", "True").lower() == "true"

    # QuestDB
    questdb_host: str = os.getenv("QUESTDB_HOST")
    questdb_port: int = 8812
    if os.getenv("QUESTDB_PORT"):
        try:
            questdb_port = int(os.getenv("QUESTDB_PORT"))
        except ValueError:
            logger.error(f"Environment variable QUESTDB_PORT should be a number")
            exit(1)

    questdb_user: str = os.getenv("QUESTDB_USER")
    questdb_password: str = os.getenv("QUESTDB_PASSWORD")
    questdb_database: str = os.getenv("QUESTDB_DATABASE")


# -----------------------------
# CACHE MANAGER
# -----------------------------
class CacheManager:
    def __init__(self, config: Config):
        self.config = config
        self.cache_dir = config.cache_dir
        self.ttl_seconds = config.cache_ttl * 60

        if config.enable_strava_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cache enabled: TTL={config.cache_ttl}min, dir={self.cache_dir}")

    def _get_cache_key(self, endpoint: str, params: dict = None) -> str:
        """Generate a cache key from endpoint and parameters."""
        param_str = json.dumps(params or {}, sort_keys=True)
        key_str = f"{endpoint}:{param_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Get cached data if valid, otherwise return None."""
        if not self.config.enable_strava_cache:
            return None

        cache_key = self._get_cache_key(endpoint, params)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            logger.debug(f"Cache MISS: {endpoint}")
            return None

        try:
            with open(cache_path, 'r') as f:
                cached = json.load(f)

            cached_time = cached.get('timestamp', 0)
            age_seconds = time.time() - cached_time

            if age_seconds > self.ttl_seconds:
                logger.debug(f"Cache EXPIRED: {endpoint} (age: {age_seconds/60:.1f}min)")
                cache_path.unlink()
                return None

            logger.debug(f"Cache HIT: {endpoint} (age: {age_seconds/60:.1f}min)")
            return cached.get('data')

        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            return None

    def set(self, endpoint: str, data: any, params: dict = None):
        """Cache the data with current timestamp."""
        if not self.config.enable_strava_cache:
            return

        cache_key = self._get_cache_key(endpoint, params)
        cache_path = self._get_cache_path(cache_key)

        try:
            cached = {
                'timestamp': time.time(),
                'endpoint': endpoint,
                'params': params,
                'data': data
            }
            with open(cache_path, 'w') as f:
                json.dump(cached, f)
            logger.debug(f"Cache SET: {endpoint}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def clear(self):
        """Clear all cached files."""
        if not self.config.enable_strava_cache:
            return

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        logger.info(f"Cache cleared: {count} files removed")


# -----------------------------
# STRAVA CLIENT
# -----------------------------
class StravaClient:
    BASE_URL = "https://www.strava.com/api/v3"

    def __init__(self, config: Config):
        self.config = config
        self._access_token = None
        self.cache = CacheManager(config)

    def _get_access_token(self) -> str:
        """Exchange refresh token for a new access token."""
        if self._access_token:
            return self._access_token

        logger.debug("Access token not found or expired. Refreshing...")
        url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": self.config.strava_client_id,
            "client_secret": self.config.strava_client_secret,
            "refresh_token": self.config.strava_refresh_token,
            "grant_type": "refresh_token"
        }

        logger.debug(f"POST {url}")
        r = requests.post(url, data=payload)

        if r.status_code != 200:
            logger.error(f"Token exchange failed: {r.status_code}")
            logger.error(f"Response: {r.text}")
            r.raise_for_status()

        data = r.json()
        self._access_token = data["access_token"]
        logger.debug("Access token refreshed successfully.")

        # Strava returns a new refresh token - store it for next time
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token and new_refresh_token != self.config.strava_refresh_token:
            logger.warning(f"⚠ New refresh token issued: {new_refresh_token}")
            logger.warning("Update your STRAVA_REFRESH_TOKEN environment variable!")

        return self._access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def get_activities(self, after: int = None) -> list:
        """Fetch activities, optionally after a given Unix timestamp."""
        # Check cache first
        cache_params = {"after": after} if after else {}
        cached_activities = self.cache.get("activities", cache_params)
        if cached_activities is not None:
            logger.info(f"Using cached activities list ({len(cached_activities)} activities)")
            return cached_activities

        page = 1
        per_page = 200
        activities = []

        logger.info(f"Fetching activities list from Strava (after={after})...")

        while True:
            url = f"{self.BASE_URL}/athlete/activities"
            params = {"page": page, "per_page": per_page}
            if after:
                params["after"] = after

            logger.debug(f"GET {url} | params={params}")
            r = requests.get(url, headers=self._headers(), params=params)
            r.raise_for_status()
            batch = r.json()

            if not batch:
                logger.debug(f"Page {page} is empty. Reached end of activities.")
                break

            logger.debug(f"Page {page}: Found {len(batch)} activities.")
            activities.extend(batch)
            page += 1

        # Cache the results
        self.cache.set("activities", activities, cache_params)

        return activities

    def get_streams(self, activity_id: int) -> dict:
        """Fetch detailed streams for an activity."""
        # Check cache first
        cached_streams = self.cache.get(f"streams/{activity_id}")
        if cached_streams is not None:
            logger.debug(f"Using cached streams for activity {activity_id}")
            return cached_streams

        url = f"{self.BASE_URL}/activities/{activity_id}/streams"
        params = {
            "keys": "time,latlng,altitude,heartrate,cadence,velocity_smooth,distance",
            "key_by_type": "true"
        }
        logger.debug(f"GET {url} | params={params}")
        r = requests.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        streams = r.json()

        # Cache the streams
        self.cache.set(f"streams/{activity_id}", streams)

        return streams


# -----------------------------
# DATABASE REPOSITORY INTERFACE
# -----------------------------
class DatabaseRepository(ABC):
    """Abstract base class for database operations."""

    @abstractmethod
    def initialize_schema(self):
        """Initialize or update the database schema."""
        pass

    @abstractmethod
    def get_latest_activity_time(self) -> Optional[int]:
        """Get the start timestamp of the activity with the highest ID."""
        pass

    @abstractmethod
    def get_synced_activity_ids(self) -> Set[str]:
        """Get all activity IDs already in the database."""
        pass

    @abstractmethod
    def write_activity(self, activity: dict):
        """Write activity metadata to the database."""
        pass

    @abstractmethod
    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to the database."""
        pass

    @abstractmethod
    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from the database."""
        pass

    @abstractmethod
    def close(self):
        """Close database connection."""
        pass


# -----------------------------
# INFLUXDB2 REPOSITORY
# -----------------------------
class InfluxDB2Repository(DatabaseRepository):
    def __init__(self, config: Config):
        self.config = config
        try:
            self.client = InfluxDBClient(
                url=config.influx_url,
                token=config.influx_token,
                org=config.influx_org,
                timeout=120000,  # 2 minutes
                verify_ssl=config.influx_verify_ssl
            )
            # Test connection
            self.client.ping()
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB2 at {config.influx_url}: {e}")
            sys.exit(1)

        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.delete_api = self.client.delete_api()

    def initialize_schema(self):
        """InfluxDB2 doesn't require schema initialization."""
        logger.info("InfluxDB2: No schema initialization required.")

    def get_latest_activity_time(self) -> Optional[int]:
        """Get the start timestamp of the activity with the highest ID."""
        ids = self.get_synced_activity_ids()
        if not ids:
            return None

        try:
            max_id = max(ids, key=lambda x: int(x))
        except ValueError:
            max_id = max(ids)

        logger.debug(f"Latest activity ID by value: {max_id}")

        query = f'''
            from(bucket: "{self.config.influx_bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "activity_metadata")
            |> filter(fn: (r) => r.activity_id == "{max_id}")
            |> first()
            |> keep(columns: ["_time"])
            |> yield(name: "time")
        '''
        try:
            tables = self.query_api.query(query)
            for table in tables:
                for record in table.records:
                    return int(record.get_time().timestamp())
        except Exception as e:
            logger.warning(f"Could not query time for activity {max_id}: {e}")
        return None

    def get_synced_activity_ids(self) -> Set[str]:
        """Get all activity IDs already in the database."""
        logger.debug("Querying InfluxDB2 for all synced activity IDs...")
        query = f'''
            import "influxdata/influxdb/schema"
            schema.measurementTagValues(bucket: "{self.config.influx_bucket}", measurement: "activity_metadata", tag: "activity_id")
        '''
        synced_ids = set()
        try:
            tables = self.query_api.query(query)
            for table in tables:
                for record in table.records:
                    synced_ids.add(record.get_value())
            logger.debug(f"Retrieved {len(synced_ids)} synced IDs from InfluxDB2.")
        except Exception as e:
            logger.warning(f"Could not query synced activities: {e}")
        return synced_ids

    def write_activity(self, activity: dict):
        """Write activity metadata to InfluxDB2."""
        activity_id = activity["id"]
        start_date = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))
        ts_ns = int(start_date.timestamp() * 1e9)

        p = (
            Point("activity_metadata")
            .tag("activity_id", str(activity_id))
            .tag("sport", activity.get("sport_type", "Unknown"))
            .tag("athlete_id", str(activity["athlete"]["id"]))
            .field("name", activity.get("name", "Unnamed Activity"))
            .field("distance", activity.get("distance", 0.0))
            .field("moving_time", activity.get("moving_time", 0))
            .field("elapsed_time", activity.get("elapsed_time", 0))
            .field("total_elevation_gain", activity.get("total_elevation_gain", 0.0))
            .field("average_speed", activity.get("average_speed", 0.0))
            .field("max_speed", activity.get("max_speed", 0.0))
            .field("average_heartrate", activity.get("average_heartrate"))
            .field("max_heartrate", activity.get("max_heartrate"))
            .field("average_cadence", activity.get("average_cadence"))
            .time(ts_ns, WritePrecision.NS)
        )

        logger.debug(f"Writing activity metadata for {activity_id} to InfluxDB2...")
        self.write_api.write(bucket=self.config.influx_bucket, record=p)

    def write_activity_streams(self, activity: dict, streams: dict):
        """Write activity streams to InfluxDB2."""
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

        points = []
        for i, t in enumerate(time_stream):
            ts_ns = int((start_date.timestamp() + t) * 1e9)
            lat, lng = latlng_stream[i] if i < len(latlng_stream) else (None, None)

            p = (
                Point("activity_streams")
                .tag("activity_id", str(activity_id))
                .tag("sport", sport)
                .tag("athlete_id", str(athlete_id))
                .field("lat", float(lat) if lat else None)
                .field("lng", float(lng) if lng else None)
                .field("altitude", altitude_stream[i] if i < len(altitude_stream) else None)
                .field("heartrate", hr_stream[i] if i < len(hr_stream) else None)
                .field("cadence", cadence_stream[i] if i < len(cadence_stream) else None)
                .field("speed", speed_stream[i] if i < len(speed_stream) else None)
                .field("distance", distance_stream[i] if i < len(distance_stream) else None)
                .time(ts_ns, WritePrecision.NS)
            )
            points.append(p)

        logger.debug(f"Writing {len(points)} stream points to InfluxDB2 for activity {activity_id}...")
        self.write_api.write(bucket=self.config.influx_bucket, record=points)

    def delete_activity(self, activity_id: str):
        """Delete an activity and its streams from InfluxDB2."""
        start = "1970-01-01T00:00:00Z"
        stop = datetime.now(timezone.utc).isoformat()

        # Delete metadata
        predicate_meta = f'_measurement="activity_metadata" AND activity_id="{activity_id}"'
        logger.debug(f"Deleting metadata with predicate: {predicate_meta}")
        self.delete_api.delete(start, stop, predicate_meta, bucket=self.config.influx_bucket, org=self.config.influx_org)

        # Delete streams
        predicate_streams = f'_measurement="activity_streams" AND activity_id="{activity_id}"'
        logger.debug(f"Deleting streams with predicate: {predicate_streams}")
        self.delete_api.delete(start, stop, predicate_streams, bucket=self.config.influx_bucket, org=self.config.influx_org)

    def close(self):
        self.client.close()


# -----------------------------
# QUESTDB REPOSITORY
# -----------------------------
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
                    CREATE TABLE activities (
                        timestamp TIMESTAMP,
                        activity_id LONG,
                        name STRING,
                        sport STRING,
                        athlete_id LONG,
                        distance DOUBLE,
                        moving_time INT,
                        elapsed_time INT,
                        total_elevation_gain DOUBLE,
                        average_speed DOUBLE,
                        max_speed DOUBLE,
                        average_heartrate INT,
                        max_heartrate INT,
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
                    CREATE TABLE streams (
                        timestamp TIMESTAMP,
                        activity_id LONG,
                        sport STRING,
                        athlete_id LONG,
                        lat DOUBLE,
                        lng DOUBLE,
                        altitude DOUBLE,
                        heartrate INT,
                        cadence INT,
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
                VALUES (to_timestamp(%s, 'yyyy-MM-ddTHH:mm:ss.SSSUUUZ'), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                VALUES (to_timestamp(%s, 'yyyy-MM-ddTHH:mm:ss.SSSUUUZ'), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


# -----------------------------
# DATABASE FACTORY
# -----------------------------
def create_repository(config: Config) -> DatabaseRepository:
    """Factory function to create the appropriate database repository."""
    if config.database_type == "influxdb2":
        logger.info("Using InfluxDB2 as the database backend.")
        return InfluxDB2Repository(config)
    elif config.database_type == "questdb":
        logger.info("Using QuestDB as the database backend.")
        return QuestDBRepository(config)
    else:
        raise ValueError(f"Unsupported database type: {config.database_type}")


# -----------------------------
# SYNC SERVICE
# -----------------------------
class SyncService:
    def __init__(self, config: Config):
        self.strava = StravaClient(config)
        self.db = create_repository(config)

    def sync(self, full_sync: bool = True):
        """
        Perform sync of Strava activities.

        :param full_sync: If True, fetches ALL activities from Strava and checks for deletions.
                          If False, fetches only activities newer than the latest one in the database.
        """
        logger.info(f"Starting sync process (Mode: {'FULL' if full_sync else 'FAST'})...")

        # 0. Initialize database schema
        self.db.initialize_schema()

        # 1. Get already synced activity IDs
        synced_ids = self.db.get_synced_activity_ids()
        logger.info(f"Found {len(synced_ids)} already synced activities in database.")

        # 2. Determine fetch strategy
        after = None
        if not full_sync:
            latest_ts = self.db.get_latest_activity_time()
            if latest_ts:
                after = latest_ts - 86400  # Go back 1 day
                logger.info(f"Fast sync: Fetching activities after {datetime.fromtimestamp(after, tz=timezone.utc)}")
            else:
                logger.info("Fast sync: No previous data found, falling back to full fetch.")

        # 3. Fetch activities from Strava
        activities = self.strava.get_activities(after=after)
        logger.info(f"Found {len(activities)} activities from Strava.")

        # 4. Identify new activities to sync
        new_activities = [a for a in activities if str(a["id"]) not in synced_ids]
        logger.info(f"Identified {len(new_activities)} new activities to sync.")

        # 5. Identify deleted activities (ONLY in Full Sync mode)
        ids_to_delete = set()
        if full_sync:
            strava_ids = set(str(a["id"]) for a in activities)
            ids_to_delete = synced_ids - strava_ids
            if ids_to_delete:
                logger.info(f"Found {len(ids_to_delete)} activities in database that are missing from Strava.")
            else:
                logger.info("No activities to delete.")
        else:
            logger.info("Fast sync: Skipping deletion check.")

        # 6. Sync new activities
        total_new = len(new_activities)
        for i, activity in enumerate(new_activities, 1):
            activity_id = activity["id"]
            sport = activity["sport_type"]
            name = activity.get("name", "Unknown Activity")
            percent = (i / total_new) * 100

            logger.info(f"[{i}/{total_new}] ({percent:.1f}%) Syncing activity {activity_id}: '{name}' ({sport})...")

            try:
                # Write activity metadata
                self.db.write_activity(activity)

                # Fetch and write streams
                streams = self.strava.get_streams(activity_id)
                point_count = len(streams.get('time', {}).get('data', []))

                if point_count > 0:
                    self.db.write_activity_streams(activity, streams)
                    logger.info(f"  ✓ Synced {point_count} data points for activity {activity_id}.")
                else:
                    logger.warning(f"  ⚠ Activity {activity_id} has no stream data.")

            except Exception as e:
                logger.error(f"  ✗ Error syncing activity {activity_id}: {e}")

            time.sleep(1)  # Respect rate limits

        # 7. Delete removed activities
        if ids_to_delete:
            total_del = len(ids_to_delete)
            for i, act_id in enumerate(ids_to_delete, 1):
                logger.info(f"[{i}/{total_del}] Deleting activity {act_id} from database...")
                try:
                    self.db.delete_activity(act_id)
                    logger.info(f"  ✓ Deleted activity {act_id}.")
                except Exception as e:
                    logger.error(f"  ✗ Error deleting activity {act_id}: {e}")

        logger.info("Sync complete.")

    def close(self):
        self.db.close()


def print_version():
    with open(os.path.join(os.path.dirname(__file__), "version.txt"), "r") as vf:
        version = vf.read().strip()
    print(f"Kinetiqo {version}")


# -----------------------------
# CLI
# -----------------------------
@click.command(help="""
Kinetiqo

This tool synchronizes your Strava activities with a time-series database.
Supported databases: InfluxDB2, QuestDB.

\b
DATABASE SELECTION:
  Use --database to choose your backend:
  - influxdb2: InfluxDB 2.x
  - questdb: QuestDB (PostgreSQL wire protocol) [default]

\b
SYNC MODES:

\b
1. FULL SYNC (Default or --full-sync):
   - Fetches ALL activities from Strava.
   - Downloads missing activities.
   - DELETES activities from database that are no longer in Strava.
   - Use this periodically to ensure perfect consistency.

\b
2. FAST SYNC (--fast-sync):
   - Fetches only activities newer than the latest one in database.
   - Downloads missing activities.
   - DOES NOT check for deletions.
   - Use this for frequent, quick updates.

\b
CACHING:
  Enable caching to reduce API calls to Strava:
  --enable-strava-cache: Enable caching (disabled by default)
  --cache-ttl: Cache time-to-live in minutes (default: 60)
  --clear-cache: Clear the cache before syncing

\b
DATABASE SCHEMA:
  Two tables are created:
  - activities: Metadata (name, sport, distance, times, averages)
  - streams: Time-series data (GPS, HR, cadence, speed, etc.)

\b
EXAMPLES:
  # Full sync with QuestDB and caching enabled
  python sync-questdb.py --database=questdb --full-sync --enable-strava-cache --cache-ttl=30

  # Fast sync with InfluxDB2 using cache
  python sync-questdb.py --database=influxdb2 --fast-sync --enable-strava-cache

  # Clear cache and do full sync
  python sync-questdb.py --clear-cache --full-sync

  # Default (full sync with QuestDB, no cache)
  python sync-questdb.py
""")
@click.option('--database', '-d',
              type=click.Choice(['influxdb2', 'questdb'], case_sensitive=False),
              default='questdb',
              help='Database backend to use (default: questdb)')
@click.option('--full-sync', '-f',
              is_flag=True,
              help='Perform a full sync. Checks all activities and removes deleted ones from database.')
@click.option('--fast-sync', '-q',
              is_flag=True,
              help='Perform a fast sync. Only checks for new activities since the last sync.')
@click.option('--enable-strava-cache',
              is_flag=True,
              help='Enable caching of Strava API responses.')
@click.option('--cache-ttl',
              type=int,
              default=60,
              help='Cache time-to-live in minutes (default: 60)')
@click.option('--clear-cache',
              is_flag=True,
              help='Clear the cache before syncing.')
@click.option('--version', is_flag=True, help='Show the version and exit.')
def cli(version, database, full_sync, fast_sync, enable_strava_cache, cache_ttl, clear_cache):
    """
    Main entry point for the sync tool.
    """

    if version:
        print_version()
        sys.exit(0)

    print_version()

    if full_sync and fast_sync:
        click.echo(click.style("Error: Cannot specify both --full-sync and --fast-sync.", fg="red"), err=True)
        exit(1)

    is_full_sync = True
    if fast_sync:
        is_full_sync = False
    elif full_sync:
        is_full_sync = True
    else:
        logger.warning("No mode specified, defaulting to Full Sync.")
        is_full_sync = True

    config = Config()

    if not config.strava_client_id:
        logger.error("Environment variable STRAVA_CLIENT_ID is required.")
        exit(1)
    if not config.strava_client_secret:
        logger.error("Environment variable STRAVA_CLIENT_SECRET is required.")
        exit(1)
    if not config.strava_refresh_token:
        logger.error("Environment variable STRAVA_REFRESH_TOKEN is required.")
        exit(1)

    # Comprehensive config validation
    if config.database_type == "questdb":
        missing = []
        if not config.questdb_host:
            missing.append("QUESTDB_HOST")
        if not config.questdb_port:
            missing.append("QUESTDB_PORT")
        if not config.questdb_user:
            missing.append("QUESTDB_USER")
        if not config.questdb_password:
            missing.append("QUESTDB_PASSWORD")
        if not config.questdb_database:
            missing.append("QUESTDB_DATABASE")
        if missing:
            logger.error(f"Missing required QuestDB environment variables: {', '.join(missing)}")
            exit(1)
    elif config.database_type == "influxdb2":
        missing = []
        if not config.influx_token:
            missing.append("INFLUX_TOKEN")
        if not config.influx_url:
            missing.append("INFLUX_URL")
        if not config.influx_org:
            missing.append("INFLUX_ORG")
        if not config.influx_bucket:
            missing.append("INFLUX_BUCKET")
        if missing:
            logger.error(f"Missing required InfluxDB2 environment variables: {', '.join(missing)}")
            exit(1)



    config.database_type = database.lower()
    config.enable_strava_cache = enable_strava_cache
    config.cache_ttl = cache_ttl

    # Clear cache if requested
    if clear_cache:
        cache_manager = CacheManager(config)
        cache_manager.clear()

    sync_service = SyncService(config)

    try:
        sync_service.sync(full_sync=is_full_sync)
    finally:
        sync_service.close()


if __name__ == "__main__":
    cli()
