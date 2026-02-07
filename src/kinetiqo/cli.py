import os
import sys
import logging
import click
from kinetiqo.config import Config
from kinetiqo.cache import CacheManager
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
logger.setLevel(logging.DEBUG)

# Reduce noise from libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("influxdb_client").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)


def print_version():
    version = "dev"
    version_file: str = "version.txt"
    try:
        # Look for version.txt in the package root or project root
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Check current dir (kinetiqo/)
        version_path = os.path.join(base_dir, version_file)
        if not os.path.exists(version_path):
            # Check parent dir (src/)
            version_path = os.path.join(os.path.dirname(base_dir), version_file)
        
        if os.path.exists(version_path):
            with open(version_path, "r") as vf:
                version = vf.read().strip()
    except:
        pass
    print(f"Kinetiqo {version}")

# -----------------------------
# CLI
# -----------------------------
@click.group(help="Kinetiqo - Strava Sync Tool")
@click.option('--version', is_flag=True, help='Show the version and exit.')
def cli(version):
    if version:
        print_version()
        sys.exit(0)

@cli.command(help="Start the web interface")
@click.option('--port', default=4444, help='Port to run the web server on')
@click.option('--host', default='0.0.0.0', help='Host to bind to')
def web(port, host):
    """Start the web interface."""
    print_version()
    logger.info(f"Starting web server on {host}:{port}")
    
    # Import here to avoid circular imports or unnecessary loading
    from kinetiqo.web.app import app
    app.run(debug=True, port=port, host=host, use_reloader=False)

@cli.command(help="Synchronize activities with database")
@click.option('--database', '-d',
              type=click.Choice(['influxdb2', 'postgresql'], case_sensitive=False),
              default='postgresql',
              help='Database backend to use (default: postgresql)')
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
def sync(database, full_sync, fast_sync, enable_strava_cache, cache_ttl, clear_cache):
    """
    Synchronize activities with database.
    """
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
    
    # Override database type from CLI argument if provided
    if database:
        config.database_type = database.lower()

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
    if config.database_type == "postgresql":
        missing = []
        if not config.postgresql_host:
            missing.append("POSTGRESQL_HOST")
        if not config.postgresql_port:
            missing.append("POSTGRESQL_PORT")
        if not config.postgresql_user:
            missing.append("POSTGRESQL_USER")
        if not config.postgresql_password:
            missing.append("POSTGRESQL_PASSWORD")
        if not config.postgresql_database:
            missing.append("POSTGRESQL_DATABASE")
        if missing:
            logger.error(f"Missing required PostgreSQL environment variables: {', '.join(missing)}")
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
