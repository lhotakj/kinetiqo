import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("kinetiqo")

# Where the rendered UPDATE_STRAVA_* stats block is inserted within (or, once
# found, replaces in place within) an activity's Strava description.
UPDATE_STRAVA_PLACEMENT_BEGIN = "begin"
UPDATE_STRAVA_PLACEMENT_END = "end"
UPDATE_STRAVA_PLACEMENT = (UPDATE_STRAVA_PLACEMENT_BEGIN, UPDATE_STRAVA_PLACEMENT_END)
DEFAULT_UPDATE_STRAVA_PLACEMENT = UPDATE_STRAVA_PLACEMENT_END
UPDATE_STRAVA_MAX_ITEMS = 30
UPDATE_STRAVA_PREFIX = "✨ Kinetiqo:"


@dataclass
class Config:
    """Application configuration read primarily from environment variables.

    Attributes correspond to various configurable settings such as Strava
    credentials, cache options, database connection parameters, and map API keys.
    """
    # Strava
    strava_client_id: str | None = os.getenv("STRAVA_CLIENT_ID")
    strava_client_secret: str | None = os.getenv("STRAVA_CLIENT_SECRET")
    strava_refresh_token: str | None = os.getenv("STRAVA_REFRESH_TOKEN")

    # Optional callback invoked with the new token whenever StravaClient
    # receives a rotated refresh_token from Strava (Strava issues a new one
    # — invalidating the previous one — on every token exchange). Wired up
    # at startup (see kinetiqo.profile_sync.wire_refresh_token_persistence)
    # to persist the rotated token to the database so it survives a restart.
    on_refresh_token_changed: Optional[Callable[[str], None]] = field(default=None, repr=False, compare=False)

    # Cache
    enable_strava_cache: bool = False
    cache_ttl: int = 60  # minutes
    cache_dir: Path = Path(".cache")

    # Database - Common
    database_type: str = (os.getenv("DATABASE_TYPE") or os.getenv("DATABASE") or "postgresql").strip().lower()  # mysql, postgresql, or firebird

    # MySQL
    mysql_host: str | None = os.getenv("MYSQL_HOST")
    mysql_port: int = 3306
    mysql_user: str | None = os.getenv("MYSQL_USER")
    mysql_password: str | None = os.getenv("MYSQL_PASSWORD")
    mysql_database: str | None = os.getenv("MYSQL_DATABASE")
    mysql_ssl_mode: str = os.getenv("MYSQL_SSL_MODE", "disable")

    # PostgreSQL
    postgresql_host: str | None = os.getenv("POSTGRESQL_HOST")
    postgresql_port: int = 5432
    postgresql_user: str | None = os.getenv("POSTGRESQL_USER")
    postgresql_password: str | None = os.getenv("POSTGRESQL_PASSWORD")
    postgresql_database: str | None = os.getenv("POSTGRESQL_DATABASE")
    postgresql_ssl_mode: str = os.getenv("POSTGRESQL_SSL_MODE",
                                         "disable")  # e.g., disable, allow, prefer, require, verify-ca, verify-full

    # Firebird
    firebird_host: str | None = os.getenv("FIREBIRD_HOST")
    firebird_user: str | None = os.getenv("FIREBIRD_USER")
    firebird_password: str | None = os.getenv("FIREBIRD_PASSWORD")
    firebird_database: str | None = os.getenv("FIREBIRD_DATABASE")

    # Firebird port needs to be parsed in __post_init__ to handle errors properly
    firebird_port: int = 3050

    # Athlete
    athlete_weight: float = 0.0  # kg — set via ATHLETE_WEIGHT env var for VO2max estimation

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Map API keys
    mapy_api_key: str | None = os.getenv("MAPY_API_KEY", "")
    thunderforest_api_key: str | None = os.getenv("THUNDERFOREST_API_KEY", "")
    maptiler_api_key: str | None = os.getenv("MAPTILER_API_KEY", "")
    geoapify_api_key: str | None = os.getenv("GEOAPIFY_API_KEY", "")

    # Date Format
    date_format: str | None = os.getenv("DATE_FORMAT", "%b %d, %Y")

    # Strava description auto-update (see docs/UPDATE_STRAVA.md)
    # One independent template per activity-type/scope bucket. Cycling and
    # running are split by indoor/outdoor (Strava's sport_type reliably tells
    # them apart); walking and swimming have no such distinction, so they get
    # a single template each.
    update_strava_cycling_indoor: str = os.getenv("UPDATE_STRAVA_CYCLING_INDOOR", "") or ""
    update_strava_cycling_outdoor: str = os.getenv("UPDATE_STRAVA_CYCLING_OUTDOOR", "") or ""
    update_strava_running_indoor: str = os.getenv("UPDATE_STRAVA_RUNNING_INDOOR", "") or ""
    update_strava_running_outdoor: str = os.getenv("UPDATE_STRAVA_RUNNING_OUTDOOR", "") or ""
    update_strava_walking: str = os.getenv("UPDATE_STRAVA_WALKING", "") or ""
    update_strava_swimming: str = os.getenv("UPDATE_STRAVA_SWIMMING", "") or ""

    # Where the rendered block goes: "begin" (start of the description) or
    # "end" (appended after any existing text). Invalid values fall back to
    # the default with a logged warning (see __post_init__).
    update_strava_placement: str = (os.getenv("UPDATE_STRAVA_PLACEMENT", DEFAULT_UPDATE_STRAVA_PLACEMENT) or DEFAULT_UPDATE_STRAVA_PLACEMENT).strip().lower()

    def __post_init__(self):
        """Post-initialization to coerce and validate environment values.

        Converts port and numeric environment variables to the appropriate
        numeric types and exits with an error message if values are malformed.
        """
        db_env = os.getenv("DATABASE_TYPE") or os.getenv("DATABASE")
        if db_env:
            self.database_type = db_env.strip().lower()
        if os.getenv("POSTGRESQL_PORT"):
            try:
                self.postgresql_port = int(os.getenv("POSTGRESQL_PORT"))
            except ValueError:
                logger.error("Environment variable POSTGRESQL_PORT should be a number")
                sys.exit(1)

        if os.getenv("MYSQL_PORT"):
            try:
                self.mysql_port = int(os.getenv("MYSQL_PORT"))
            except ValueError:
                logger.error("Environment variable MYSQL_PORT should be a number")
                sys.exit(1)

        if os.getenv("FIREBIRD_PORT"):
            try:
                self.firebird_port = int(os.getenv("FIREBIRD_PORT"))
            except ValueError:
                logger.error("Environment variable FIREBIRD_PORT should be a number")
                sys.exit(1)

        if os.getenv("ATHLETE_WEIGHT"):
            try:
                self.athlete_weight = float(os.getenv("ATHLETE_WEIGHT"))
            except ValueError:
                logger.error("Environment variable ATHLETE_WEIGHT should be a number (kg)")
                sys.exit(1)

        if self.update_strava_placement not in UPDATE_STRAVA_PLACEMENT:
            logger.warning(
                "Environment variable UPDATE_STRAVA_PLACEMENT=%r is not one of %s — "
                "falling back to the default (%r).",
                self.update_strava_placement, UPDATE_STRAVA_PLACEMENT, DEFAULT_UPDATE_STRAVA_PLACEMENT,
            )
            self.update_strava_placement = DEFAULT_UPDATE_STRAVA_PLACEMENT

    database_connect_verbose: bool = True  # Show verbose output in init
