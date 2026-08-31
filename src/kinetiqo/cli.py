
import logging
import os
import re
import sys
import platform
from collections import deque
from typing import Dict, Any

import click
from kinetiqo.cache import CacheManager
from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository, get_version
from kinetiqo.logging_utils import configure_logging, LOG_LEVEL_CHOICES
from kinetiqo.profile_sync import (
    seed_profile_from_strava,
    sync_all_profile_env_vars,
    sync_update_strava_from_env,
    sync_gps_simplification_from_env,
    sync_athlete_weight_from_env,
    resolve_refresh_token_from_db,
    wire_refresh_token_persistence,
)
from kinetiqo.sync import SyncService
logger = logging.getLogger("kinetiqo")


def print_version():
    """Prints the application version."""
    print(f"Kinetiqo {get_version()}")


def validate_config(config):
    """Ensures all required environment variables are set."""
    from kinetiqo.config import VALID_DATABASE_TYPES
    if config.database_type not in VALID_DATABASE_TYPES:
        logger.error(f"Invalid database type {config.database_type!r}. Valid choices are: {', '.join(VALID_DATABASE_TYPES)}.")
        sys.exit(1)

    if not all([config.strava_client_id, config.strava_client_secret, config.strava_refresh_token]):
        logger.error("STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, and STRAVA_REFRESH_TOKEN are required.")
        sys.exit(1)

    db_type = config.database_type
    if db_type == "postgresql":
        reqs = ['postgresql_host', 'postgresql_port', 'postgresql_user', 'postgresql_password', 'postgresql_database']
    elif db_type == "mysql":
        reqs = ['mysql_host', 'mysql_port', 'mysql_user', 'mysql_password', 'mysql_database']
    elif db_type == "firebird":
        reqs = ['firebird_host', 'firebird_port', 'firebird_user', 'firebird_password', 'firebird_database']
    else:
        reqs = []

    missing = [f"{db_type.upper()}_{v.split('_')[-1].upper()}" for v in reqs if not getattr(config, v)]
    if missing:
        logger.error(f"Missing required {db_type.capitalize()} environment variables: {', '.join(missing)}")
        sys.exit(1)


def parse_period(period_str):
    """Parses a period string like '7d', '1m', '1y' into days."""
    if not period_str:
        return 0

    match = re.match(r'^(\d+)([dDwWmMyY])$', period_str)
    if not match:
        raise click.BadParameter(f"Invalid period format: {period_str}. Use format like '7d', '2w', '1m', '1y'.")

    value = int(match.group(1))
    unit = match.group(2).lower()

    if unit == 'd':
        return value
    if unit == 'w':
        return value * 7
    if unit == 'm':
        return value * 30
    if unit == 'y':
        return value * 365
    return 0


class State:
    """A simple state object to pass config to subcommands."""
    def __init__(self):
        self.config = None


def _get_db_info(config, repo):
    """Return (db_version, host_info) for the configured database backend."""
    db_type = config.database_type.capitalize()
    if db_type == 'Postgresql':
        return repo.get_pg_version(), f"{config.postgresql_host}:{config.postgresql_port}"
    if db_type == 'Mysql':
        return repo.get_mysql_version(), f"{config.mysql_host}:{config.mysql_port}"
    if db_type == 'Firebird':
        return repo.get_firebird_version(), f"{config.firebird_host}:{config.firebird_port}"
    return "Unknown", "Unknown"


def _load_api_keys(config):
    """Read optional map API keys from the environment into *config*."""
    mapy_key = os.getenv("MAPY_API_KEY", "")
    if mapy_key:
        config.mapy_api_key = mapy_key
    if config.mapy_api_key:
        logger.info("API key for mapy.com provided")
    else:
        logger.warning("No mapy.com key provided, Mapy.cz map layers won't be available")

    tf_key = os.getenv("THUNDERFOREST_API_KEY", "")
    if tf_key:
        config.thunderforest_api_key = tf_key
    if config.thunderforest_api_key:
        logger.info("API key for Thunderforest provided")
    else:
        logger.warning("No Thunderforest key provided, Thunderforest map layers won't be available")

    geoapify_key = os.getenv("GEOAPIFY_API_KEY", "")
    if geoapify_key:
        config.geoapify_api_key = geoapify_key
    if config.geoapify_api_key:
        logger.info("API key for Geoapify provided")
    else:
        logger.warning("No Geoapify key provided, Geoapify map layers won't be available")


database_option = click.option(
    '--database-type', '--database', '-d', 'database',
    type=click.Choice(['mysql', 'postgresql', 'firebird'], case_sensitive=False),
    default=None,
    help='Database backend to use (overrides config).'
)


@click.group(help="Kinetiqo - Strava Sync Tool")
@click.option('--log-level',
              envvar='LOG_LEVEL',
              type=click.Choice(LOG_LEVEL_CHOICES, case_sensitive=False),
              default='INFO',
              show_default=True,
              help='Set the log verbosity for CLI commands.')
@database_option
@click.pass_context
def cli(ctx, log_level, database):
    """Main CLI entry point."""
    ctx.obj = State()
    config = Config()
    if database:
        config.database_type = database.lower()
    config.log_level = log_level.upper()
    ctx.obj.config = config
    ctx.obj.log_level = config.log_level
    configure_logging(config.log_level)


def _prepare_db(config, database=None):
    """Initialize schema and resolve refresh token for the chosen database."""
    if database:
        config.database_type = database.lower()
    validate_config(config)
    repo = None
    try:
        repo = create_repository(config)

        db_version, host_info = _get_db_info(config, repo)
        db_type = config.database_type.capitalize()
        logger.info(f"Using {db_type} backend (Kinetiqo v{get_version()}) on {host_info}")
        logger.info(f"Running in Python {platform.python_version()}")
        logger.info(f"DB Version: {db_version}")

        repo.initialize_schema()

        wire_refresh_token_persistence(config)
        resolve_refresh_token_from_db(config, repo.get_profile())

    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if repo:
            repo.close()


@cli.command(help="Show the version and exit")
def version():
    """Show the version and exit."""
    print_version()


@cli.command(help="Start the web interface")
@click.option('--port', default=4444, help='Port to run the web server on')
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@database_option
@click.pass_context
def web(ctx, port, host, database):
    """Start the web interface."""
    _prepare_db(ctx.obj.config, database)
    logger.info(f"Starting web server on {host}:{port}")

    # Seed athlete profile from Strava before starting the web server
    _seed_profile(ctx.obj.config)

    from kinetiqo.web.app import app, set_config
    set_config(ctx.obj.config)
    app.run(debug=False, port=port, host=host, use_reloader=False)


def _seed_profile(config):
    """Fetch athlete profile from Strava and persist it in the database.

    Runs once at web startup.  Failures are logged but never block the
    web server from starting.
    """
    repo = None
    try:
        repo = create_repository(config)
        seed_profile_from_strava(config, repo)
        sync_all_profile_env_vars(config, repo)
        from kinetiqo.web.app import mark_startup_sync_done
        mark_startup_sync_done()
    except Exception as e:
        logger.warning(f"Could not seed profile from Strava (non-fatal): {e}")
    finally:
        if repo:
            try:
                repo.close()
            except Exception:
                pass


@cli.command(help="Check database availability and schema")
@database_option
@click.pass_context
def flightcheck(ctx, database):
    """Perform a health check on the database."""
    logger.info("Performing flight check...")
    config = ctx.obj.config
    if database:
        config.database_type = database.lower()
    repo = None
    try:
        repo = create_repository(config)
        if repo.flightcheck():
            logger.info("Database is ready.")
            sys.exit(0)
        else:
            logger.error("Database check failed.")
            sys.exit(1)
    except Exception as e:
        logger.exception(f"An error occurred during flight check: {e}")
        sys.exit(1)
    finally:
        if repo:
            repo.close()


def _print_benchmark_results(db_type: str, scope_days: int, results: Dict[str, Any]):
    """Format and print database performance benchmark metrics to stdout."""
    db_name = (db_type or "default").upper()
    gps_ms = results.get('gps_ms', 0.0)
    gps_count = results.get('gps_count', 0)
    order_name_ms = results.get('order_name_ms', 0.0)
    order_name_count = results.get('order_name_count', 0)
    order_dist_ms = results.get('order_dist_ms', 0.0)
    order_dist_count = results.get('order_dist_count', 0)
    order_elev_ms = results.get('order_elev_ms', 0.0)
    order_elev_count = results.get('order_elev_count', 0)

    print("\n" + "=" * 74)
    print(f"  Kinetiqo Database Benchmark ({db_name})")
    print(f"  Scope: Last {scope_days} days")
    print("=" * 74)
    print(f"  * Fetch all GPS data for last {scope_days} days all activity types: {gps_ms:.2f} ms ({gps_count:,} records)")
    print(f"  * Order all activities by name:                             {order_name_ms:.2f} ms ({order_name_count:,} activities)")
    print(f"  * Order all activities by distance:                         {order_dist_ms:.2f} ms ({order_dist_count:,} activities)")
    print(f"  * Order all activities by elevation gained:                 {order_elev_ms:.2f} ms ({order_elev_count:,} activities)")
    print("=" * 74 + "\n")


@cli.command(help="Run performance benchmarks on database operations")
@click.option('--scope', '-s', type=int, default=365, show_default=True, help='Lookback window in days for database benchmark operations.')
@database_option
@click.pass_context
def benchmark(ctx, scope, database):
    """Perform database optimization benchmarks for a given day lookback scope."""
    config = ctx.obj.config
    if database:
        config.database_type = database.lower()
    validate_config(config)
    repo = None
    try:
        repo = create_repository(config)
        logger.info(f"Running database benchmark (backend={config.database_type.upper()}, scope={scope} days)...")
        results = repo.run_benchmarks(scope_days=scope)
        _print_benchmark_results(config.database_type, scope, results)
    except Exception as e:
        logger.exception(f"An error occurred during benchmark execution: {e}")
        sys.exit(1)
    finally:
        if repo:
            repo.close()


def _parse_bool_option(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    val_str = str(value).strip().lower()
    if val_str in ("true", "1", "yes"):
        return True
    if val_str in ("false", "0", "no"):
        return False
    raise click.BadParameter(f"Invalid boolean value: {value!r}. Expected true/false, 1/0, or yes/no.")


@cli.command(help="Synchronize activities with database")
@click.option('--full-sync', '-f', is_flag=True, help='Perform a full sync.')
@click.option('--fast-sync', '-q', is_flag=True, help='Perform a fast sync.')
@click.option('--period', '-p', help="Limit sync scope (e.g., '7d', '2w', '1m').")
@click.option('--enable-strava-cache', is_flag=True, help='Enable caching of Strava API responses.')
@click.option('--cache-ttl', type=int, default=60, help='Cache TTL in minutes.')
@click.option('--clear-cache', is_flag=True, help='Clear the cache before syncing.')
@click.option('--update-strava-description', '--update-strava', '-U', 'update_strava_description', default='true', help='Update Strava activity descriptions (true/false, 1/0, yes/no). Default: true.')
@database_option
@click.pass_context
def sync(ctx, full_sync, fast_sync, period, enable_strava_cache, cache_ttl, clear_cache, update_strava_description, database):
    """Synchronize activities with database."""
    _prepare_db(ctx.obj.config, database)

    if full_sync and fast_sync:
        raise click.UsageError("Cannot specify both --full-sync and --fast-sync.")

    is_full_sync = not fast_sync
    if not full_sync and not fast_sync:
        logger.info("No sync mode specified, defaulting to full sync.")

    limit_days = parse_period(period) if period else 0
    if limit_days and not is_full_sync:
        logger.warning("Period limit is ignored for fast sync.")

    config = ctx.obj.config
    config.enable_strava_cache = enable_strava_cache
    config.cache_ttl = cache_ttl

    if clear_cache:
        CacheManager(config).clear()

    update_strava_flag = _parse_bool_option(update_strava_description)

    sync_service = SyncService(config)
    try:
        # Exhaust the generator returned by sync() for its side-effects.
        # Using deque(..., maxlen=0) efficiently consumes the iterator without
        # storing items in memory. This keeps behavior identical to the
        # previous empty for-loop but avoids Sonar S108 (empty loop bodies).
        deque(sync_service.sync(full_sync=is_full_sync, trigger="cli", user="-", limit_days=limit_days, update_strava=update_strava_flag), maxlen=0)
    finally:
        sync_service.close()


if __name__ == "__main__":
    cli()
