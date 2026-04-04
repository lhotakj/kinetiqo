import logging
import os
import sys
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
    database_type: str = os.getenv("DATABASE_TYPE", "postgresql").lower()  # mysql, postgresql, or firebird

    # MySQL
    mysql_host: str = os.getenv("MYSQL_HOST")
    mysql_port: int = 3306
    mysql_user: str = os.getenv("MYSQL_USER")
    mysql_password: str = os.getenv("MYSQL_PASSWORD")
    mysql_database: str = os.getenv("MYSQL_DATABASE")
    mysql_ssl_mode: str = os.getenv("MYSQL_SSL_MODE", "disable")

    # PostgreSQL
    postgresql_host: str = os.getenv("POSTGRESQL_HOST")
    postgresql_port: int = 5432
    postgresql_user: str = os.getenv("POSTGRESQL_USER")
    postgresql_password: str = os.getenv("POSTGRESQL_PASSWORD")
    postgresql_database: str = os.getenv("POSTGRESQL_DATABASE")
    postgresql_ssl_mode: str = os.getenv("POSTGRESQL_SSL_MODE",
                                         "disable")  # e.g., disable, allow, prefer, require, verify-ca, verify-full

    # Firebird
    firebird_host: str = os.getenv("FIREBIRD_HOST")
    firebird_user: str = os.getenv("FIREBIRD_USER")
    firebird_password: str = os.getenv("FIREBIRD_PASSWORD")
    firebird_database: str = os.getenv("FIREBIRD_DATABASE")

    # Firebird port needs to be parsed in __post_init__ to handle errors properly
    firebird_port: int = 3050

    # Athlete
    athlete_weight: float = 0.0  # kg — set via ATHLETE_WEIGHT env var for VO2max estimation

    # Map API keys
    mapy_api_key: str = ""

    # Date Format
    date_format: str = os.getenv("DATE_FORMAT", "%b %d, %Y")

    def __post_init__(self):
        if os.getenv("POSTGRESQL_PORT"):
            try:
                self.postgresql_port = int(os.getenv("POSTGRESQL_PORT"))
            except ValueError:
                logger.error(f"Environment variable POSTGRESQL_PORT should be a number")
                sys.exit(1)

        if os.getenv("MYSQL_PORT"):
            try:
                self.mysql_port = int(os.getenv("MYSQL_PORT"))
            except ValueError:
                logger.error(f"Environment variable MYSQL_PORT should be a number")
                sys.exit(1)

        if os.getenv("FIREBIRD_PORT"):
            try:
                self.firebird_port = int(os.getenv("FIREBIRD_PORT"))
            except ValueError:
                logger.error(f"Environment variable FIREBIRD_PORT should be a number")
                sys.exit(1)

        if os.getenv("ATHLETE_WEIGHT"):
            try:
                self.athlete_weight = float(os.getenv("ATHLETE_WEIGHT"))
            except ValueError:
                logger.error("Environment variable ATHLETE_WEIGHT should be a number (kg)")
                sys.exit(1)

    database_connect_verbose: bool = True  # Show verbose output in init
