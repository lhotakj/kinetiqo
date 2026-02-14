import os
import sys
import logging
import click
from kinetiqo.config import Config
from kinetiqo.cache import CacheManager
from kinetiqo.db.factory import create_repository
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

def validate_config(config):
    logger.debug("Configuration validation started...")
    if not config.strava_client_id:
        logger.error("Environment variable STRAVA_CLIENT_ID is required.")
        sys.exit(1)
    if not config.strava_client_secret:
        logger.error("Environment variable STRAVA_CLIENT_SECRET is required.")
        sys.exit(1)
    if not config.strava_refresh_token:
        logger.error("Environment variable STRAVA_REFRESH_TOKEN is required.")
        sys.exit(1)

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
            sys.exit(1)
    elif config.database_type == "mysql":
        missing = []
        if not config.mysql_host:
            missing.append("MYSQL_HOST")
        if not config.mysql_port:
            missing.append("MYSQL_PORT")
        if not config.mysql_user:
            missing.append("MYSQL_USER")
        if not config.mysql_password:
            missing.append("MYSQL_PASSWORD")
        if not config.mysql_database:
            missing.append("MYSQL_DATABASE")
        if missing:
            logger.error(f"Missing required MySQL environment variables: {', '.join(missing)}")
            sys.exit(1)

class State:
    """A simple state object to pass config to subcommands."""
    def __init__(self):
        self.config = None

# -----------------------------
# CLI
# -----------------------------
@click.group(help="Kinetiqo - Strava Sync Tool")
@click.option('--database', '-d',
              type=click.Choice(['mysql', 'postgresql'], case_sensitive=False),
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

    # Initialize schema for any command that needs the database.
    # This ensures the DB and tables are ready before the command logic runs.
    if ctx.invoked_subcommand in ['web', 'sync', 'flightcheck']:
        validate_config(config)
        try:
            config.database_connect_verbose = False
            repository = create_repository(config)
            repository.initialize_schema()
            repository.close()
            ctx.obj.config.database_connect_verbose = True  # The init DB will be called later to hide connect info
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)

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
    
    # Import here to avoid circular imports or unnecessary loading.
    # The web app will create its own repository using the global config.
    from kinetiqo.web.app import app, set_config
    
    # Pass the config from CLI to the web app
    set_config(ctx.obj.config)
    
    app.run(debug=True, port=port, host=host, use_reloader=False)

@cli.command(help="Check database availability and schema")
@click.pass_context
def flightcheck(ctx):
    """Perform a health check on the database."""
    logger.info("Performing flight check...")

    config = ctx.obj.config
    try:
        repository = create_repository(config)
        if repository.flightcheck():
            logger.info("Database is ready.")
            sys.exit(0)
        else:
            logger.error("Database check failed.")
            sys.exit(1)
    except Exception as e:
        logger.error(f"An error occurred during flight check: {e}")
        sys.exit(1)

@cli.command(help="Synchronize activities with database")
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
@click.pass_context
def sync(ctx, full_sync, fast_sync, enable_strava_cache, cache_ttl, clear_cache):
    """
    Synchronize activities with database.
    """

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

    config = ctx.obj.config
    
    # Config validation is now handled in cli() via validate_config()

    config.enable_strava_cache = enable_strava_cache
    config.cache_ttl = cache_ttl

    # Clear cache if requested
    if clear_cache:
        cache_manager = CacheManager(config)
        cache_manager.clear()

    sync_service = SyncService(config)

    try:
        # Consume the generator to execute the sync process
        for _ in sync_service.sync(full_sync=is_full_sync, trigger="cli", user="-"):
            pass
    finally:
        sync_service.close()

if __name__ == "__main__":
    cli()
