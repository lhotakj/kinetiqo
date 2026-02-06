import sys
import logging
from datetime import datetime, timezone
from typing import Optional, Set, List, Dict, Any
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from kinetiqo.config import Config
from kinetiqo.db.repository import DatabaseRepository

logger = logging.getLogger("kinetiqo")

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

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get a list of activities for display."""
        query = f'''
            from(bucket: "{self.config.influx_bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "activity_metadata")
            |> group(columns: ["activity_id"])
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: {limit})
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> map(fn: (r) => ({{r with 
                id: r.activity_id,
                type: r.sport,
                start_date: string(v: r._time)
            }}))
        '''
        
        activities = []
        try:
            tables = self.query_api.query(query)
            for table in tables:
                for record in table.records:
                    activity = record.values
                    # The map function in flux should handle most of this, but we clean up
                    activity.pop('_start', None)
                    activity.pop('_stop', None)
                    activity.pop('_measurement', None)
                    activities.append(activity)
        except Exception as e:
            logger.error(f"Error querying activities from InfluxDB: {e}")
        
        # InfluxDB's `sort` and `limit` apply per-group, so we might get more than `limit`.
        # We need to sort and limit again in Python.
        activities.sort(key=lambda x: x.get('start_date', ''), reverse=True)
        return activities[:limit]

    def get_activities_web(self, limit=10, offset=0, sort_by='start_date', sort_order='DESC', types=None):
        """Fetch activities with pagination and sorting from InfluxDB2"""
        # Note: InfluxDB Flux language pagination and sorting is complex and might be slow for large datasets
        # This is a simplified implementation
        
        type_filter = ""
        if types:
            # Construct filter for types: r.sport == "Run" or r.sport == "Ride" ...
            conditions = [f'r.sport == "{t}"' for t in types]
            type_filter = f'|> filter(fn: (r) => {" or ".join(conditions)})'

        query = f'''
            from(bucket: "{self.config.influx_bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "activity_metadata")
            {type_filter}
            |> group(columns: ["activity_id"])
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> map(fn: (r) => ({{r with 
                id: r.activity_id,
                type: r.sport,
                start_date: string(v: r._time)
            }}))
            |> group()
            |> sort(columns: ["{sort_by}"], desc: {str(sort_order.upper() == 'DESC').lower()})
            |> limit(n: {limit}, offset: {offset})
        '''
        
        activities = []
        try:
            tables = self.query_api.query(query)
            for table in tables:
                for record in table.records:
                    activity = record.values
                    activity.pop('_start', None)
                    activity.pop('_stop', None)
                    activity.pop('_measurement', None)
                    activities.append(activity)
        except Exception as e:
            logger.error(f"Error querying activities from InfluxDB: {e}")
            
        return activities

    def count_activities(self, types=None):
        """Get total count of activities"""
        type_filter = ""
        if types:
            conditions = [f'r.sport == "{t}"' for t in types]
            type_filter = f'|> filter(fn: (r) => {" or ".join(conditions)})'

        query = f'''
            from(bucket: "{self.config.influx_bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "activity_metadata")
            {type_filter}
            |> group(columns: ["activity_id"])
            |> count(column: "_value") 
            |> group()
            |> count()
        '''
        # The above query is an approximation and might need adjustment based on exact schema
        # Counting unique series (activity_id) is tricky in Flux efficiently without high cardinality impact
        
        try:
            tables = self.query_api.query(query)
            for table in tables:
                for record in table.records:
                    # This returns the count of groups, which corresponds to activity count
                    return record.get_value()
        except Exception as e:
            logger.error(f"Error counting activities in InfluxDB: {e}")
            
        return 0

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
        self.delete_api.delete(start, stop, predicate_meta, bucket=self.config.influx_bucket,
                               org=self.config.influx_org)

        # Delete streams
        predicate_streams = f'_measurement="activity_streams" AND activity_id="{activity_id}"'
        logger.debug(f"Deleting streams with predicate: {predicate_streams}")
        self.delete_api.delete(start, stop, predicate_streams, bucket=self.config.influx_bucket,
                               org=self.config.influx_org)

    def close(self):
        self.client.close()
