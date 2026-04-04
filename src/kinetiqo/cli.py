import logging
import os
import re
import sys

import click
from kinetiqo.cache import CacheManager
from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository, get_version
from kinetiqo.sync import SyncService

# -----------------------------
# LOGGING SETUP
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("kinetiqo")
logger.setLevel(logging.INFO)

# Reduce noise from libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)


def print_version():
    """Prints the application version."""
    print(f"Kinetiqo {get_version()}")


def validate_config(config):
    """Ensures all required environment variables are set."""
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

    if unit == 'd': return value
    if unit == 'w': return value * 7
    if unit == 'm': return value * 30
    if unit == 'y': return value * 365
    return 0


class State:
    """A simple state object to pass config to subcommands."""
    def __init__(self):
        self.config = None


@click.group(help="Kinetiqo - Strava Sync Tool")
@click.option('--database', '-d',
              type=click.Choice(['mysql', 'postgresql', 'firebird'], case_sensitive=False),
              default=None,
              help='Database backend to use (overrides config).')
@click.pass_context
def cli(ctx, database):
    """Main CLI entry point."""
    ctx.obj = State()
    config = Config()
    if database:
        config.database_type = database.lower()
    ctx.obj.config = config

    if ctx.invoked_subcommand in ['web', 'sync', 'flightcheck']:
        validate_config(config)
        repo = None
        try:
            # This is the single point for startup logging.
            repo = create_repository(config)
            
            db_type = config.database_type.capitalize()
            db_version = "Unknown"
            host_info = "Unknown"

            if db_type == 'Postgresql':
                db_version = repo.get_pg_version()
                host_info = f"{config.postgresql_host}:{config.postgresql_port}"
            elif db_type == 'Mysql':
                db_version = repo.get_mysql_version()
                host_info = f"{config.mysql_host}:{config.mysql_port}"
            elif db_type == 'Firebird':
                db_version = repo.get_firebird_version()
                host_info = f"{config.firebird_host}:{config.firebird_port}"

            logger.info(f"Using {db_type} backend (Kinetiqo v{get_version()}) on {host_info}")
            logger.info(f"DB Version: {db_version}")
            
            repo.initialize_schema()

            # Mapy.cz API key — free, obtain at https://developer.mapy.cz
            if os.getenv("MAPY_API_KEY"):
                config.mapy_api_key = os.getenv("MAPY_API_KEY", "")
            if config.mapy_api_key == "":
                logger.warning("No mapy.com key provided, base map provider won't be available")
            else:
                logger.info("API key for mapy.com provided")


        except Exception as e:
            logger.error(f"Failed to initialize database: {e}", exc_info=True)
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
@click.pass_context
def web(ctx, port, host):
    """Start the web interface."""
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
    from kinetiqo.strava import StravaClient
    repo = None
    try:
        strava = StravaClient(config)
        athlete = strava.get_athlete()
        athlete_id = int(athlete.get("id", 0))
        if athlete_id <= 0:
            logger.warning("Strava athlete profile has no valid ID — skipping profile seed.")
            return

        first_name = athlete.get("firstname", "") or ""
        last_name = athlete.get("lastname", "") or ""
        strava_weight = float(athlete.get("weight", 0) or 0)

        repo = create_repository(config)

        # Preserve the existing DB weight when Strava returns null/0
        existing = repo.get_profile()
        if strava_weight > 0:
            weight = strava_weight
        elif existing:
            weight = float(existing.get("weight", 0) or 0)
        else:
            weight = 0.0

        repo.upsert_profile(athlete_id, first_name, last_name, weight)
        logger.info(f"Profile seeded from Strava: {first_name} {last_name}, {weight} kg"
                     + (" (weight kept from DB — Strava returned 0)" if strava_weight <= 0 and weight > 0 else ""))
    except Exception as e:
        logger.warning(f"Could not seed profile from Strava (non-fatal): {e}")
    finally:
        if repo:
            try:
                repo.close()
            except Exception:
                pass


@cli.command(help="Check database availability and schema")
@click.pass_context
def flightcheck(ctx):
    """Perform a health check on the database."""
    logger.info("Performing flight check...")
    config = ctx.obj.config
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
        logger.error(f"An error occurred during flight check: {e}")
        sys.exit(1)
    finally:
        if repo:
            repo.close()


@cli.command(help="Synchronize activities with database")
@click.option('--full-sync', '-f', is_flag=True, help='Perform a full sync.')
@click.option('--fast-sync', '-q', is_flag=True, help='Perform a fast sync.')
@click.option('--period', '-p', help="Limit sync scope (e.g., '7d', '2w', '1m').")
@click.option('--enable-strava-cache', is_flag=True, help='Enable caching of Strava API responses.')
@click.option('--cache-ttl', type=int, default=60, help='Cache TTL in minutes.')
@click.option('--clear-cache', is_flag=True, help='Clear the cache before syncing.')
@click.pass_context
def sync(ctx, full_sync, fast_sync, period, enable_strava_cache, cache_ttl, clear_cache):
    """Synchronize activities with database."""
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

    sync_service = SyncService(config)
    try:
        for _ in sync_service.sync(full_sync=is_full_sync, trigger="cli", user="-", limit_days=limit_days):
            pass
    finally:
        sync_service.close()


if __name__ == "__main__":
    cli()
