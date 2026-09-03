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


VALID_DATABASE_TYPES = ("postgresql", "mysql", "firebird")


def resolve_database_type(env_val: str | None) -> str:
    """Resolves and validates the database type.

    Default is 'postgresql'.
    If *env_val* is set and valid ('postgresql', 'mysql', or 'firebird'), use it.
    If *env_val* is set and invalid, log a warning and fall back to 'postgresql'.
    """
    if env_val and isinstance(env_val, str):
        cleaned = env_val.strip().lower()
        if cleaned in VALID_DATABASE_TYPES:
            return cleaned
        logger.warning(
            "Invalid DATABASE_TYPE environment variable %r. Valid options are: %s. Defaulting to 'postgresql'.",
            env_val,
            ", ".join(repr(t) for t in VALID_DATABASE_TYPES),
        )
    return "postgresql"


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
    database_type: str = field(default_factory=lambda: resolve_database_type(os.getenv("DATABASE_TYPE") or os.getenv("DATABASE")))  # mysql, postgresql, or firebird

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

    # GPS Track Simplification
    gps_simplification: int = 0  # 0 (off, default) to 10 (max decimation)
    is_gps_simplification_env_set: bool = False  # True if env var was explicitly passed

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

    # Absolute watt floor for highlighting high-watt peaks in the
    # {{workout-summary}} placeholder (see docs/UPDATE_STRAVA.md). The
    # effective threshold is the higher of this value and 110% of FTP.
    workout_summary_peak_threshold_w: float = 300.0

    def __post_init__(self):
        """Post-initialization to coerce and validate environment values.

        Converts port and numeric environment variables to the appropriate
        numeric types and exits with an error message if values are malformed.
        """
        self.strava_client_id = os.getenv("STRAVA_CLIENT_ID")
        self.strava_client_secret = os.getenv("STRAVA_CLIENT_SECRET")
        self.strava_refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

        db_env = os.getenv("DATABASE_TYPE") or os.getenv("DATABASE")
        self.database_type = resolve_database_type(db_env)

        self.postgresql_host = os.getenv("POSTGRESQL_HOST")
        self.postgresql_user = os.getenv("POSTGRESQL_USER")
        self.postgresql_password = os.getenv("POSTGRESQL_PASSWORD")
        self.postgresql_database = os.getenv("POSTGRESQL_DATABASE")
        self.postgresql_ssl_mode = os.getenv("POSTGRESQL_SSL_MODE", "disable")

        if os.getenv("POSTGRESQL_PORT"):
            try:
                self.postgresql_port = int(os.getenv("POSTGRESQL_PORT"))
            except ValueError:
                logger.error("Environment variable POSTGRESQL_PORT should be a number")
                sys.exit(1)

        self.mysql_host = os.getenv("MYSQL_HOST")
        self.mysql_user = os.getenv("MYSQL_USER")
        self.mysql_password = os.getenv("MYSQL_PASSWORD")
        self.mysql_database = os.getenv("MYSQL_DATABASE")
        self.mysql_ssl_mode = os.getenv("MYSQL_SSL_MODE", "disable")

        if os.getenv("MYSQL_PORT"):
            try:
                self.mysql_port = int(os.getenv("MYSQL_PORT"))
            except ValueError:
                logger.error("Environment variable MYSQL_PORT should be a number")
                sys.exit(1)

        self.firebird_host = os.getenv("FIREBIRD_HOST")
        self.firebird_user = os.getenv("FIREBIRD_USER")
        self.firebird_password = os.getenv("FIREBIRD_PASSWORD")
        self.firebird_database = os.getenv("FIREBIRD_DATABASE")

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

        self.mapy_api_key = os.getenv("MAPY_API_KEY", "")
        self.thunderforest_api_key = os.getenv("THUNDERFOREST_API_KEY", "")
        self.maptiler_api_key = os.getenv("MAPTILER_API_KEY", "")
        self.geoapify_api_key = os.getenv("GEOAPIFY_API_KEY", "")
        self.date_format = os.getenv("DATE_FORMAT", "%b %d, %Y")

        self.update_strava_cycling_indoor = os.getenv("UPDATE_STRAVA_CYCLING_INDOOR", "") or ""
        self.update_strava_cycling_outdoor = os.getenv("UPDATE_STRAVA_CYCLING_OUTDOOR", "") or ""
        self.update_strava_running_indoor = os.getenv("UPDATE_STRAVA_RUNNING_INDOOR", "") or ""
        self.update_strava_running_outdoor = os.getenv("UPDATE_STRAVA_RUNNING_OUTDOOR", "") or ""
        self.update_strava_walking = os.getenv("UPDATE_STRAVA_WALKING", "") or ""
        self.update_strava_swimming = os.getenv("UPDATE_STRAVA_SWIMMING", "") or ""

        raw_placement = os.getenv("UPDATE_STRAVA_PLACEMENT", DEFAULT_UPDATE_STRAVA_PLACEMENT) or DEFAULT_UPDATE_STRAVA_PLACEMENT
        self.update_strava_placement = raw_placement.strip().lower()
        if self.update_strava_placement not in UPDATE_STRAVA_PLACEMENT:
            logger.warning(
                "Environment variable UPDATE_STRAVA_PLACEMENT=%r is not one of %s — "
                "falling back to the default (%r).",
                self.update_strava_placement, UPDATE_STRAVA_PLACEMENT, DEFAULT_UPDATE_STRAVA_PLACEMENT,
            )
            self.update_strava_placement = DEFAULT_UPDATE_STRAVA_PLACEMENT

        self.workout_summary_peak_threshold_w = 300.0
        raw_peak_threshold = os.getenv("WORKOUT_SUMMARY_PEAK_THRESHOLD_W")
        if raw_peak_threshold:
            try:
                val = float(raw_peak_threshold)
                if val > 0:
                    self.workout_summary_peak_threshold_w = val
                else:
                    logger.warning("Environment variable WORKOUT_SUMMARY_PEAK_THRESHOLD_W=%r should be a positive number (watts) — falling back to the default (300).", raw_peak_threshold)
            except ValueError:
                logger.warning("Environment variable WORKOUT_SUMMARY_PEAK_THRESHOLD_W=%r should be a number (watts) — falling back to the default (300).", raw_peak_threshold)

        gps_simp_env = os.getenv("GPS_SIMPLIFICATION") or os.getenv("GPS_SIMPLIFICATION_LEVEL")
        if gps_simp_env is not None and gps_simp_env.strip():
            self.is_gps_simplification_env_set = True
            try:
                val = int(gps_simp_env)
                if 0 <= val <= 10:
                    self.gps_simplification = val
                else:
                    logger.warning("Environment variable GPS_SIMPLIFICATION=%r is outside valid range (0-10) — defaulting to 0.", gps_simp_env)
                    self.gps_simplification = 0
            except ValueError:
                logger.warning("Environment variable GPS_SIMPLIFICATION=%r should be an integer (0-10) — defaulting to 0.", gps_simp_env)
                self.gps_simplification = 0

    database_connect_verbose: bool = True  # Show verbose output in init
