import os
import sys
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("kinetiqo")

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
    
    # Date Format
    date_format: str = os.getenv("DATE_FORMAT", "%b %d, %Y")
    
    def __post_init__(self):
        if os.getenv("QUESTDB_PORT"):
            try:
                self.questdb_port = int(os.getenv("QUESTDB_PORT"))
            except ValueError:
                logger.error(f"Environment variable QUESTDB_PORT should be a number")
                sys.exit(1)

    questdb_user: str = os.getenv("QUESTDB_USER")
    questdb_password: str = os.getenv("QUESTDB_PASSWORD")
    questdb_database: str = os.getenv("QUESTDB_DATABASE")
