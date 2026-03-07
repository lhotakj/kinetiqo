# Gemini Instructions for Kinetiqo Project

This document provides comprehensive context and guidelines for assisting with the Kinetiqo project.

## 1. Project Overview

Kinetiqo is a Python fitness-data platform that syncs activities from the **Strava API**, stores them in a relational database, and serves them through a web dashboard. It supports three database backends (PostgreSQL, MySQL, Firebird) via a Repository/Factory pattern and exposes both a **Click CLI** and a **Flask web UI** with HTMX-powered reactivity.

## 2. Key Technologies & Versions

| Concern | Technology | Notes |
|---|---|---|
| Language | **Python 3.13** | Dockerised on `python:3.13-alpine` |
| Web framework | **Flask 3.1** + **flask-login 0.6** | Jinja2 templates, Gunicorn in production |
| Frontend | **Tailwind CSS** (CDN), **HTMX 1.9** (SSE extension), **DataTables 2.x**, **Select2**, **Folium** (maps) | No build step; all loaded from CDN |
| CLI | **Click 8.3** | Entry point: `python src/kinetiqo.py <command>` |
| Database drivers | **psycopg2-binary 2.9** (PostgreSQL), **mysql-connector-python 9.6** (MySQL), **firebird-driver 2.0** (Firebird) | Raw SQL — no ORM |
| HTTP client | **requests 2.32** | For Strava API calls |
| Data processing | **pandas 3.0** | Used for data manipulation |
| Date handling | **python-dateutil 2.9** | Flexible date parsing |
| Mapping | **folium 0.20** | Generating Leaflet.js maps server-side |
| WSGI server | **gunicorn 25.1** | Production only (Docker) |
| Container | **Docker** (multi-stage Alpine build) + **dcron** for scheduled syncs |

## 3. Project Structure

```
src/
├── app.py                  # Standalone demo/mock Flask app (NOT the main app)
├── kinetiqo.py             # CLI entry point (calls kinetiqo.cli:cli)
├── version.txt / short_version.txt  # Build-generated version strings
└── kinetiqo/               # Core application package
    ├── __init__.py
    ├── __main__.py          # `python -m kinetiqo` → calls cli()
    ├── cli.py               # Click CLI: version, web, sync, flightcheck commands
    ├── config.py            # @dataclass Config — all env-var-driven settings
    ├── strava.py            # StravaClient — token refresh, activities, streams (with retry & cache)
    ├── sync.py              # SyncService — orchestrates Strava→DB sync (generator yielding SSE progress)
    ├── cache.py             # CacheManager — file-based JSON cache with TTL
    ├── db/
    │   ├── repository.py    # DatabaseRepository ABC — defines the contract
    │   ├── factory.py       # create_repository() — factory dispatching on config.database_type
    │   ├── schema.py        # SchemaManager + SCHEMA_DEFINITION dict (multi-dialect DDL)
    │   ├── postgresql.py    # PostgresqlRepository(DatabaseRepository)
    │   ├── mysql.py         # MySQLRepository(DatabaseRepository)
    │   └── firebird.py      # FirebirdRepository(DatabaseRepository)
    └── web/
        ├── app.py           # Main Flask app — routes, SSE sync, HTMX endpoints
        ├── auth.py          # Simple env-var-based user/password + flask-login UserMixin
        ├── static/css/      # Custom CSS (common.css)
        └── templates/       # Jinja2: base.html, activities.html, sync.html, map.html, logs.html, login.html, settings.html
build/
├── Dockerfile              # Multi-stage: builder (pip + Firebird client) → alpine runtime
├── entrypoint.sh           # Prints banner, runs flightcheck, sets up cron, starts gunicorn + web
└── build.sh
dashboards/                 # Grafana JSON dashboards (PostgreSQL, QuestDB)
development/                # Dev helper scripts (direnv setup)
secrets/                    # GPG-encrypted secrets (git-ignored)
tests/                      # Docker-based integration test scripts
requirements.txt            # Pinned Python dependencies
```

## 4. Architecture & Design Patterns

### 4.1 Repository Pattern (Database)
- **`DatabaseRepository`** (ABC in `db/repository.py`) defines every DB operation as an abstract method.
- Three concrete implementations: `PostgresqlRepository`, `MySQLRepository`, `FirebirdRepository`.
- **`create_repository(config)`** factory in `db/factory.py` instantiates the correct one based on `config.database_type`.
- All SQL is **raw** (no ORM). Use parameterised queries (`%s` for psycopg2/mysql, `?` for Firebird).
- Schema is defined in `db/schema.py` as a Python dict (`SCHEMA_DEFINITION`) with per-dialect type keys (`type_pg`, `type_mysql`, `type_firebird`).

### 4.2 Sync Pipeline (Generator / SSE)
- `SyncService.sync()` is a **generator** that yields HTML-formatted SSE messages.
- Steps: fetch synced IDs → determine `after` timestamp → paginate Strava activities → diff & upsert → delete removed → log.
- The web route `/sync/start/<type>` streams these yields as `text/event-stream` for HTMX SSE consumption.
- The CLI consumes the same generator by iterating silently.

### 4.3 Strava Integration
- `StravaClient` in `strava.py` handles OAuth2 **refresh-token flow** (no user-interactive OAuth).
- Two main endpoints: `get_activities()` (paginated, generator) and `get_streams()` (per-activity detail).
- Built-in **retry with exponential backoff** and **HTTP 429 rate-limit** handling (respects `Retry-After` header).
- Responses are optionally cached via `CacheManager` (file-based JSON, keyed by MD5 of endpoint+params).

### 4.4 Configuration
- `Config` is a **`@dataclass`** reading everything from **environment variables** via `os.getenv()`.
- Port values are parsed in `__post_init__` with error handling.
- Supported env vars:
  - Strava: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`
  - Database selector: `DATABASE_TYPE` (postgresql | mysql | firebird)
  - PostgreSQL: `POSTGRESQL_HOST`, `POSTGRESQL_PORT`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_DATABASE`, `POSTGRESQL_SSL_MODE`
  - MySQL: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_SSL_MODE`
  - Firebird: `FIREBIRD_HOST`, `FIREBIRD_PORT`, `FIREBIRD_USER`, `FIREBIRD_PASSWORD`, `FIREBIRD_DATABASE`
  - Web: `WEB_LOGIN`, `WEB_PASSWORD`
  - Display: `DATE_FORMAT`
  - Docker cron: `FULL_SYNC`, `FAST_SYNC` (cron expressions)

### 4.5 Web Layer
- Flask app defined in `kinetiqo/web/app.py`; started via the `web` CLI command.
- Authentication: simple env-var-based username/password with `flask-login`.
- Frontend stack: **Tailwind CSS** (CDN, runtime config in `<script>`), **HTMX** for reactive updates (SSE for sync progress, `hx-get`/`hx-post` for partial page updates), **DataTables** for sortable/filterable activity grids, **Folium** for Leaflet map generation.
- Static asset caching uses `?v=<app_version>` query parameter; `Cache-Control` headers set in `@app.after_request`.
- Templates extend `base.html` (contains nav, Tailwind config, dark-mode support, CDN script tags).

### 4.6 Database Tables
Three main tables (defined in `schema.py`):
- **`activities`** — Primary key: `activity_id` (BIGINT). Contains all Strava activity metadata (sport, distance, time, heartrate, power, etc.).
- **`streams`** — Time-series data per activity (time, latlng, altitude, heartrate, cadence, watts, etc.).
- **`logs`** — Sync operation audit log (timestamp, added, removed, trigger, success, action, user).

### 4.7 Docker & Deployment
- Multi-stage Dockerfile: builder installs pip deps + compiles Firebird client, runtime copies artifacts to slim alpine image.
- `entrypoint.sh`: prints ASCII banner, runs `flightcheck`, configures `dcron` from `FULL_SYNC`/`FAST_SYNC` env vars, starts Gunicorn + web server.
- Grafana dashboards provided in `dashboards/` for monitoring.

## 5. Coding Conventions

### Style
- **PEP 8** compliance.
- **Type hints** on function signatures (see `repository.py`, `strava.py`, `config.py`).
- **Docstrings** on public methods — brief `:param` / `:return` style.
- **f-strings** for string formatting (no `.format()` or `%` operator).

### Logging
- Use `logging.getLogger("kinetiqo")` (or `"kinetiqo.web"` in the web module).
- Log levels: `DEBUG` for HTTP request details, `INFO` for sync progress, `WARNING` for recoverable issues (⚠ emoji prefix), `ERROR` for failures.
- Third-party loggers (`urllib3`, `werkzeug`) are suppressed to `WARNING`.

### Imports
- Standard library → third-party → project modules (PEP 8 ordering).
- Within the `kinetiqo` package, use **relative imports** for sibling modules (e.g., `from .config import Config`, `from .cache import CacheManager`).
- In `cli.py` (the entry point), use **absolute imports** (e.g., `from kinetiqo.config import Config`).
- Lazy imports where needed to avoid circular dependencies (e.g., `from kinetiqo.web.app import app` inside the `web` CLI command).

### Database Code
- Always use **parameterised queries** — never interpolate user data into SQL strings.
- When adding a new column or table: update `SCHEMA_DEFINITION` in `schema.py` with all three dialect keys (`type_pg`, `type_mysql`, `type_firebird`).
- When adding a new DB operation: add an `@abstractmethod` to `DatabaseRepository`, then implement in all three concrete repositories (`postgresql.py`, `mysql.py`, `firebird.py`).
- Use `execute_batch` (psycopg2) for bulk inserts where possible.

### Error Handling
- Strava API errors: retry with backoff, log warnings, yield user-facing messages.
- Database connection errors: log and `sys.exit(1)` — fail fast during startup.
- Config validation: checked in `validate_config()` before any command that needs the database.

## 6. How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Set required environment variables (Strava + database)
export STRAVA_CLIENT_ID=... STRAVA_CLIENT_SECRET=... STRAVA_REFRESH_TOKEN=...
export DATABASE_TYPE=postgresql
export POSTGRESQL_HOST=... POSTGRESQL_PORT=5432 POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DATABASE=...

# CLI commands (from src/ directory or with PYTHONPATH=src)
python src/kinetiqo.py version
python src/kinetiqo.py flightcheck
python src/kinetiqo.py sync --full-sync
python src/kinetiqo.py sync --fast-sync --enable-strava-cache --cache-ttl 120
python src/kinetiqo.py sync --full-sync --period 30d
python src/kinetiqo.py web --port 4444 --host 0.0.0.0

# Or via package:
python -m kinetiqo version

# Docker:
docker build -f build/Dockerfile -t kinetiqo .
docker run -e STRAVA_CLIENT_ID=... -e FULL_SYNC="0 */6 * * *" kinetiqo
```

## 7. Common Tasks & How-To

### Add a new Strava API endpoint
1. Add a method to `StravaClient` in `strava.py` following the `get_streams()` pattern (with retry logic, caching, and timeout).
2. If it feeds into sync, call it from `SyncService.sync()` in `sync.py` and yield progress messages.

### Add a new database table or column
1. Add the table/column definition to `SCHEMA_DEFINITION` in `db/schema.py` with all three dialect keys.
2. `SchemaManager.ensure_schema()` handles auto-creation of missing tables/columns.
3. Add any new query methods as `@abstractmethod` on `DatabaseRepository`.
4. Implement in **all three** repositories: `postgresql.py`, `mysql.py`, `firebird.py`.

### Add a new CLI command
1. Add a new `@cli.command()` function in `cli.py` using Click decorators.
2. Access config via `ctx.obj.config` (passed through Click context).
3. If the command needs the database, add its name to the `ctx.invoked_subcommand in [...]` check in `cli()`.

### Add a new web route
1. Add the route in `kinetiqo/web/app.py`.
2. Use `@login_required` for protected routes.
3. Access the database via the global `db_repo` object.
4. For reactive updates, use HTMX attributes in the Jinja2 template and return HTML fragments.
5. For SSE streaming, return a `Response(generator, mimetype='text/event-stream')`.

### Add a new HTML template
1. Create in `kinetiqo/web/templates/`, extending `base.html` with `{% extends "base.html" %}`.
2. Use Tailwind utility classes for styling (configured in `base.html` `<script>` block with custom `warm`/`dark` colour palette).
3. Use HTMX attributes (`hx-get`, `hx-post`, `hx-target`, `hx-swap`) for dynamic behaviour.

## 8. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `STRAVA_CLIENT_ID` | Yes | — | Strava OAuth app client ID |
| `STRAVA_CLIENT_SECRET` | Yes | — | Strava OAuth app client secret |
| `STRAVA_REFRESH_TOKEN` | Yes | — | Strava OAuth refresh token |
| `DATABASE_TYPE` | No | `postgresql` | `postgresql`, `mysql`, or `firebird` |
| `POSTGRESQL_HOST` | If PG | — | PostgreSQL host |
| `POSTGRESQL_PORT` | No | `5432` | PostgreSQL port |
| `POSTGRESQL_USER` | If PG | — | PostgreSQL user |
| `POSTGRESQL_PASSWORD` | If PG | — | PostgreSQL password |
| `POSTGRESQL_DATABASE` | If PG | — | PostgreSQL database name |
| `POSTGRESQL_SSL_MODE` | No | `disable` | PostgreSQL SSL mode |
| `MYSQL_HOST` | If MySQL | — | MySQL host |
| `MYSQL_PORT` | No | `3306` | MySQL port |
| `MYSQL_USER` | If MySQL | — | MySQL user |
| `MYSQL_PASSWORD` | If MySQL | — | MySQL password |
| `MYSQL_DATABASE` | If MySQL | — | MySQL database name |
| `MYSQL_SSL_MODE` | No | `disable` | MySQL SSL mode |
| `FIREBIRD_HOST` | If FB | — | Firebird host |
| `FIREBIRD_PORT` | No | `3050` | Firebird port |
| `FIREBIRD_USER` | If FB | — | Firebird user |
| `FIREBIRD_PASSWORD` | If FB | — | Firebird password |
| `FIREBIRD_DATABASE` | If FB | — | Firebird database path |
| `WEB_LOGIN` | No | `admin` | Web UI username |
| `WEB_PASSWORD` | No | `admin123` | Web UI password |
| `DATE_FORMAT` | No | `%b %d, %Y` | Activity date display format |
| `FULL_SYNC` | No | — | Cron expression for scheduled full syncs (Docker) |
| `FAST_SYNC` | No | — | Cron expression for scheduled fast syncs (Docker) |

## 9. Gemini-Specific Behaviour

When assisting with this project:

- **Match existing patterns exactly.** Before writing new code, look at the closest existing example in the codebase and mirror its structure, naming, and error-handling style.
- **Always update all three database backends.** Any change to `DatabaseRepository` must be reflected in `postgresql.py`, `mysql.py`, and `firebird.py`.
- **Use raw SQL with parameterised queries** — never introduce an ORM.
- **Yield SSE-compatible HTML** from sync/progress generators — the web layer relies on this contract.
- **Use `logging.getLogger("kinetiqo")`** — never use `print()` for operational output (except in `print_version()`).
- **Use relative imports** inside the `kinetiqo` package (`from .config import Config`), absolute imports in entry points (`cli.py`, `kinetiqo.py`, `__main__.py`).
- **Include type hints** on all function signatures and return types.
- **Write docstrings** on all public methods.
- **Respect the Config dataclass pattern** — new settings go as env-var-backed fields on `Config`, with `__post_init__` for type coercion.
- **Never hardcode secrets or credentials** — always read from environment variables.
- **For web templates**, use Tailwind CSS utility classes and HTMX attributes — no custom JavaScript frameworks.
- **Keep `requirements.txt` pinned** to exact versions when adding new dependencies.
- **For Strava API calls**, always include retry logic, timeout handling, and optional caching following the `StravaClient` pattern.
- **When generating HTML in Python** (e.g., SSE messages in `sync.py`), strip newlines to avoid breaking the SSE `data:` format.
