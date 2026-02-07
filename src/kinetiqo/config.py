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
    database_type: str = os.getenv("DATABASE_TYPE", "postgresql").lower()  # influxdb2 or postgresql

    # InfluxDB2
    influx_token: str = os.getenv("INFLUX_TOKEN")
    influx_url: str = os.getenv("INFLUX_URL")
    influx_org: str = os.getenv("INFLUX_ORG")
    influx_bucket: str = os.getenv("INFLUX_BUCKET")
    influx_verify_ssl: bool = os.getenv("INFLUX_VERIFY_SSL", "True").lower() == "true"

    # PostgreSQL
    postgresql_host: str = os.getenv("POSTGRESQL_HOST")
    postgresql_port: int = 5432
    postgresql_user: str = os.getenv("POSTGRESQL_USER")
    postgresql_password: str = os.getenv("POSTGRESQL_PASSWORD")
    postgresql_database: str = os.getenv("POSTGRESQL_DATABASE")
    postgresql_ssl_mode: str = os.getenv("POSTGRESQL_SSL_MODE", "disable")  # e.g., disable, allow, prefer, require, verify-ca, verify-full
    
    # Date Format
    date_format: str = os.getenv("DATE_FORMAT", "%b %d, %Y")
    
    def __post_init__(self):
        if os.getenv("POSTGRESQL_PORT"):
            try:
                self.postgresql_port = int(os.getenv("POSTGRESQL_PORT"))
            except ValueError:
                logger.error(f"Environment variable POSTGRESQL_PORT should be a number")
                sys.exit(1)
