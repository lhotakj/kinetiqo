
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
    sync_all_profile_env_vars,
    resolve_refresh_token_from_db,
    wire_refresh_token_persistence,
)
from kinetiqo.sync import SyncService
logger = logging.getLogger("kinetiqo")


def print_version():
    """Prints the application version."""
    print(f"Kinetiqo {get_version()}")


def validate_db_config(config):
    """Ensures all required database environment variables are set."""
    from kinetiqo.config import VALID_DATABASE_TYPES
    if config.database_type not in VALID_DATABASE_TYPES:
        logger.error(f"Invalid database type {config.database_type!r}. Valid choices are: {', '.join(VALID_DATABASE_TYPES)}.")
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


def validate_config(config):
    """Ensures all required environment variables are set."""
    from kinetiqo.config import VALID_DATABASE_TYPES
    if config.database_type not in VALID_DATABASE_TYPES:
        logger.error(f"Invalid database type {config.database_type!r}. Valid choices are: {', '.join(VALID_DATABASE_TYPES)}.")
        sys.exit(1)

    if not all([config.strava_client_id, config.strava_client_secret, config.strava_refresh_token]):
        logger.error("STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, and STRAVA_REFRESH_TOKEN are required.")
        sys.exit(1)

    validate_db_config(config)


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

    carto_key = os.getenv("CARTO_API_KEY", "")
    if carto_key:
        config.carto_api_key = carto_key
    if config.carto_api_key:
        logger.info("API key for CARTO provided")
    else:
        logger.warning("No CARTO key provided, CARTO basemap layers won't be available")


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

    # Sync environment variables to profile table (no external Strava call on startup)
    _sync_profile_from_env(ctx.obj.config)

    from kinetiqo.web.app import app, set_config
    set_config(ctx.obj.config)
    app.run(debug=False, port=port, host=host, use_reloader=False)


def _sync_profile_from_env(config):
    """Synchronize environment variables to database on startup without external Strava API calls."""
    repo = None
    try:
        repo = create_repository(config)
        sync_all_profile_env_vars(config, repo)
        from kinetiqo.web.app import mark_startup_sync_done
        mark_startup_sync_done()
    except Exception as e:
        logger.warning(f"Startup profile sync from environment failed (non-fatal): {e}")
    finally:
        if repo:
            try:
                repo.close()
            except Exception:
                pass


_seed_profile = _sync_profile_from_env  # Backward-compatibility alias


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
    paged_ms = results.get('paged_ms')
    paged_count = results.get('paged_count', 0)
    totals_ms = results.get('totals_ms')
    suffer_ms = results.get('suffer_ms')
    suffer_count = results.get('suffer_count', 0)
    count_ms = results.get('count_ms')
    activity_count = results.get('activity_count', 0)

    print("\n" + "=" * 74)
    print(f"  Kinetiqo Database Benchmark ({db_name})")
    print(f"  Scope: Last {scope_days} days")
    print("=" * 74)
    print(f"  * Fetch all GPS data for last {scope_days} days all activity types: {gps_ms:.2f} ms ({gps_count:,} records)")
    print(f"  * Order all activities by name:                             {order_name_ms:.2f} ms ({order_name_count:,} activities)")
    print(f"  * Order all activities by distance:                         {order_dist_ms:.2f} ms ({order_dist_count:,} activities)")
    print(f"  * Order all activities by elevation gained:                 {order_elev_ms:.2f} ms ({order_elev_count:,} activities)")
    if paged_ms is not None:
        print(f"  * Paged grid fetch (LIMIT 50 - UI DataTables):              {paged_ms:.2f} ms ({paged_count:,} activities)")
    if totals_ms is not None:
        print(f"  * Aggregate metric totals (Infographics/Goals):             {totals_ms:.2f} ms (distance, elev, time)")
    if suffer_ms is not None:
        print(f"  * Fitness suffer scores (CTL/ATL/TSB trend):                {suffer_ms:.2f} ms ({suffer_count:,} activities)")
    if count_ms is not None:
        print(f"  * Activity count query (Filter badges & pagination):        {count_ms:.2f} ms ({activity_count:,} activities)")
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
@click.option('--weather-data/--no-weather-data', default=None, help='Fetch missing historical weather data (default: enabled for fast sync only when the profile preference is enabled).')
@click.option('--resync-weather', is_flag=True, help='Replace stored weather data in this sync scope; uses the same rolling quota guard.')
@database_option
@click.pass_context
def sync(ctx, full_sync, fast_sync, period, enable_strava_cache, cache_ttl, clear_cache, update_strava_description, weather_data, resync_weather, database):
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
    if resync_weather and weather_data is False:
        raise click.UsageError("--resync-weather cannot be combined with --no-weather-data.")

    sync_service = SyncService(config)
    try:
        # Exhaust the generator returned by sync() for its side-effects.
        # Using deque(..., maxlen=0) efficiently consumes the iterator without
        # storing items in memory. This keeps behavior identical to the
        # previous empty for-loop but avoids Sonar S108 (empty loop bodies).
        deque(
            sync_service.sync(
                full_sync=is_full_sync,
                trigger="cli",
                user="-",
                limit_days=limit_days,
                update_strava=update_strava_flag,
                update_weather=weather_data,
                resync_weather=resync_weather,
            ),
            maxlen=0,
        )
    finally:
        sync_service.close()


@cli.command(name="scan-trophies", help="Scan and backfill segment trophies (placements 1st-10th) from Strava")
@click.option('--limit', '-l', type=int, default=50, show_default=True, help='Maximum number of activities to scan.')
@database_option
@click.pass_context
def scan_trophies(ctx, limit, database):
    """Scan and backfill segment trophies for activities in the database."""
    import time
    _prepare_db(ctx.obj.config, database)
    config = ctx.obj.config
    repo = create_repository(config)
    try:
        from kinetiqo.strava import StravaClient
        from kinetiqo.koms import (
            extract_trophies_from_segment_efforts,
            record_activity_trophies,
            load_verified_trophies,
            save_verified_trophies,
        )
        strava = StravaClient(config)
        logger.info(f"Scanning up to {limit} activities with achievements needing trophies...")
        unscanned = repo.get_activities_needing_trophies(limit=limit)
        if not unscanned:
            logger.info("No unscanned activities found needing trophies.")
            return
        logger.info(f"Found {len(unscanned)} activities to scan.")
        trophies_cache = load_verified_trophies()
        scanned_count = 0
        for act in unscanned:
            act_id = str(act.get("id") or act.get("activity_id"))
            name = act.get("name", "Activity")
            try:
                detail = strava.get_activity_detail(act_id)
                efforts = (detail or {}).get("segment_efforts", [])
                t_dict = extract_trophies_from_segment_efforts(efforts) if efforts else {r: 0 for r in range(1, 11)}
                record_activity_trophies(act_id, t_dict)
                repo.update_activity_trophies(act_id, t_dict)
                trophies_cache[act_id] = {str(r): t_dict[r] for r in range(1, 11)}
                trophies_cache[act_id]["scanned"] = 1
                scanned_count += 1
                podium = [f"{r}: {t_dict[r]}" for r in range(1, 11) if t_dict[r] > 0]
                ranks_str = ", ".join(podium) if podium else "none"
                logger.info(f"[{scanned_count}/{len(unscanned)}] {name} ({act_id}) -> trophies: {ranks_str}")
                time.sleep(0.05)
            except Exception as e:
                logger.warning(f"Failed to scan trophies for {act_id}: {e}")
        save_verified_trophies(trophies_cache)
        logger.info(f"Successfully scanned trophies for {scanned_count} activities.")
    finally:
        repo.close()


@cli.command(name="mcp", help="Run the Kinetiqo Model Context Protocol (MCP) server")
@click.option("--transport", "-t", type=click.Choice(["stdio", "sse", "streamable-http"]), default=lambda: os.environ.get("MCP_TRANSPORT", "stdio"), help="Transport protocol (stdio or sse). Default: stdio")
@click.option("--host", "-h", default=lambda: os.environ.get("MCP_HOST", "0.0.0.0"), help="Host to bind for SSE transport. Default: 0.0.0.0")
@click.option("--port", "-p", type=int, default=lambda: int(os.environ.get("MCP_PORT", "8000")), help="Port to bind for SSE transport. Default: 8000")
@database_option
@click.pass_context
def mcp(ctx, transport, host, port, database):
    """Start the Kinetiqo MCP server in STDIO or SSE mode for AI agent integration."""
    import signal
    config = ctx.obj.config
    if database:
        config.database_type = database.lower()

    if transport == "stdio":
        # Route all Python logging to stderr so stdout carries strictly JSON-RPC protocol frames
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                root_logger.removeHandler(handler)
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        root_logger.addHandler(stderr_handler)

    # Validate database connectivity without enforcing Strava credentials
    validate_db_config(config)

    db_type = config.database_type.capitalize()
    logger.info("Using %s backend (Kinetiqo v%s)", db_type, get_version())
    if transport == "stdio":
        logger.info("Starting Kinetiqo MCP server (STDIO transport, database: %s)", config.database_type)
    else:
        logger.info("Starting Kinetiqo MCP server (%s transport on http://%s:%d/sse, database: %s)", transport.upper(), host, port, config.database_type)

    allow_profile = os.environ.get("KINETIQO_MCP_ALLOW_PROFILE_WRITE", "0").strip() == "1"
    allow_sync = os.environ.get("KINETIQO_MCP_ALLOW_SYNC", "0").strip() == "1"
    allow_strava = os.environ.get("KINETIQO_MCP_ALLOW_STRAVA_WRITE", "0").strip() == "1"
    mode_desc = "Read-Only mode" if not any([allow_profile, allow_sync, allow_strava]) else "Mutations enabled"
    logger.info(
        "Mutation gates: sync=%s, profile_write=%s, strava_write=%s (%s)",
        "enabled" if allow_sync else "disabled",
        "enabled" if allow_profile else "disabled",
        "enabled" if allow_strava else "disabled",
        mode_desc,
    )

    from kinetiqo.mcp.server import create_mcp_server
    server = create_mcp_server(config, host=host, port=port)

    tool_count = len(getattr(getattr(server, "_tool_manager", None), "_tools", {}))
    res_count = len(getattr(getattr(server, "_resource_manager", None), "_resources", {}))
    prompt_count = len(getattr(getattr(server, "_prompt_manager", None), "_prompts", {}))
    logger.info("Registered %d tools, %d resources, %d prompts", tool_count, res_count, prompt_count)

    if transport == "stdio":
        logger.info("MCP server listening on STDIO. Ready to accept AI requests (Press Ctrl+C to stop).")
    else:
        logger.info("MCP server listening on http://%s:%d/sse. Ready to accept AI SSE connections (Press Ctrl+C to stop).", host, port)

    def _sigint_handler(signum, frame):
        logger.info("Shutdown signal received. Terminating Kinetiqo MCP server cleanly.")
        sys.stderr.flush()
        os._exit(0)

    try:
        signal.signal(signal.SIGINT, _sigint_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _sigint_handler)
    except (ValueError, AttributeError):
        pass

    try:
        server.run(transport=transport)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Kinetiqo MCP server stopped.")
        sys.stderr.flush()
        os._exit(0)
    except Exception as e:
        logger.exception("Kinetiqo MCP server encountered an error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    cli()
