# Copilot Instructions for Kinetiqo Project

## 1. Project Overview

Kinetiqo is a Python fitness-data platform that syncs activities from the **Strava API**, stores them in a relational database, and serves them through a web dashboard. It supports three database backends (PostgreSQL, MySQL, Firebird) via a Repository/Factory pattern and exposes both a **Click CLI** and a **Flask web UI**.

The web UI includes:
- A searchable and filterable activity list powered by **DataTables**.
- Interactive activity mapping using **Leaflet.js**.
- A **Fitness & Freshness** chart (CTL/ATL/TSB) based on suffer score.
- A **Power Skills** spider chart analyzing best average power over various durations.
- HTMX-powered reactivity for features like real-time sync progress via SSE.

## 2. Key Technologies & Versions

| Concern | Technology | Notes |
|---|---|---|
| Language | **Python 3.13** | Dockerised on `python:3.13-alpine` |
| Web framework | **Flask 3.1** + **flask-login 0.6** | Jinja2 templates, Gunicorn in production |
| Frontend | **Tailwind CSS** (CDN), **HTMX 1.9** (SSE), **DataTables 2.x**, **Select2**, **Chart.js 3.x** | No build step; all loaded from CDN |
| Charting | **Chart.js 3.x** + **chartjs-adapter-moment** | Client-side rendering for Fitness & Power Skills |
| CLI | **Click 8.3** | Entry point: `python src/kinetiqo.py <command>` |
| Database drivers | **psycopg2-binary 2.9**, **mysql-connector-python 9.6**, **firebird-driver 2.0** | Raw SQL — no ORM |
| HTTP client | **requests 2.32** | For Strava API calls |
| Data processing | **pandas 3.0** | Used for Fitness (CTL/ATL) calculations |
| Date handling | **moment.js** (frontend), **python-dateutil** (backend) |
| WSGI server | **gunicorn 25.1** | Production only (Docker) |
| Container | **Docker** (multi-stage Alpine build) + **dcron** for scheduled syncs |

## 3. Project Structure

```
src/
├── kinetiqo.py             # CLI entry point (calls kinetiqo.cli:cli)
└── kinetiqo/               # Core application package
    ├── __init__.py
    ├── cli.py               # Click CLI: version, web, sync, flightcheck commands
    ├── config.py            # @dataclass Config — all env-var-driven settings
    ├── strava.py            # StravaClient — token refresh, activities, streams
    ├── sync.py              # SyncService — orchestrates Strava→DB sync
    ├── cache.py             # CacheManager — file-based JSON cache
    ├── db/
    │   ├── repository.py    # DatabaseRepository ABC — defines the contract
    │   ├── factory.py       # create_repository() — factory for DB backends
    │   ├── schema.py        # SchemaManager + SCHEMA_DEFINITION dict
    │   ├── postgresql.py    # PostgresqlRepository
    │   ├── mysql.py         # MySQLRepository
    │   └── firebird.py      # FirebirdRepository
    └── web/
        ├── app.py           # Main Flask app — routes, SSE sync, API endpoints
        ├── auth.py          # Simple user/password auth
        ├── fitness.py       # Data calculation logic for the Fitness & Freshness chart
        ├── static/          # Static assets (CSS, JS)
        └── templates/       # Jinja2: base.html, activities.html, fitness.html, powerskills.html, etc.
build/
├── Dockerfile
└── entrypoint.sh
```

## 4. Architecture & Design Patterns

### 4.1 Repository Pattern (Database)
- **`DatabaseRepository`** (ABC in `db/repository.py`) defines the contract for all database operations.
- Three concrete implementations exist for PostgreSQL, MySQL, and Firebird.
- The **`create_repository()`** factory in `db/factory.py` is the single entry point for creating a database connection. It instantiates the correct repository based on `config.database_type`.
- All SQL is **raw** (no ORM). Use parameterised queries (`%s` for psycopg2/mysql, `?` for Firebird).

### 4.2 Web Layer & Data Visualization
- The Flask app in `kinetiqo/web/app.py` defines all routes.
- Data-heavy pages follow a pattern:
  1. A route (e.g., `/fitness`) renders a template shell (`fitness.html`).
  2. The template contains JavaScript that calls a dedicated API endpoint (e.g., `/api/fitness_data`).
  3. The API endpoint fetches data from the database via the repository and returns it as JSON.
  4. The JavaScript then uses a client-side library like **Chart.js** to render the visualization.
- **Fitness Page (`/fitness`):**
  - Logic is in `kinetiqo/web/fitness.py`.
  - `calculate_fitness_freshness()` uses `pandas` to calculate Chronic Training Load (CTL), Acute Training Load (ATL), and Training Stress Balance (TSB) from `suffer_score`.
- **Power Skills Page (`/powerskills`):**
  - Logic is in the `/powerskills` route in `kinetiqo/web/app.py`.
  - It calculates the best average power for various durations by fetching `watts` streams and processing them in Python.

### 4.3 Sync Pipeline (Generator / SSE)
- `SyncService.sync()` is a **generator** that yields HTML-formatted SSE messages for real-time progress updates in the web UI.
- The web route `/sync/start/<type>` streams these yields as `text/event-stream` for HTMX to consume.

### 4.4 Configuration
- `Config` is a **`@dataclass`** in `config.py` that reads all settings from **environment variables**.
- Key env vars: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `DATABASE_TYPE`, and DB-specific connection details (`POSTGRESQL_HOST`, etc.).

### 4.5 Database Tables
- **`activities`**: Metadata for each activity (name, distance, time, power, etc.). Primary key: `activity_id`.
- **`streams`**: Time-series data for activities (lat/lng, altitude, watts, etc.).
- **`logs`**: Audit trail for sync operations.

## 5. Coding Conventions

### Logging
- Use `logging.getLogger("kinetiqo")`. The default level is `INFO`.
- **Log-Once Pattern:** The database factory (`db/factory.py`) is responsible for logging connection details. It logs a comprehensive "Connected to..." message with version info only on the *first* call. Subsequent creations of the repository are silent to avoid cluttering logs during web requests.
- Use `INFO` for key lifecycle events (startup, sync completion) and `ERROR` for failures. `DEBUG` is available for verbose troubleshooting but is off by default.

### Imports & Style
- **PEP 8** compliance, with type hints on function signatures.
- Use **relative imports** within the `kinetiqo` package (e.g., `from .config import Config`).
- Use **absolute imports** in top-level scripts like `cli.py` (e.g., `from kinetiqo.config import Config`).

### Database Code
- **Always update all three backends.** A change to `DatabaseRepository` must be implemented in `postgresql.py`, `mysql.py`, and `firebird.py`.
- **Always use parameterised queries** to prevent SQL injection.
- Schema changes go into `db/schema.py`.

## 6. How to Run

```bash
# Set required environment variables (Strava + database)
export STRAVA_CLIENT_ID=...
export DATABASE_TYPE=postgresql
export POSTGRESQL_HOST=...

# Run the web UI (from src/ directory)
python kinetiqo.py web
```

## 7. Common Tasks & How-To

### Add a new database-backed web page
1.  **Define the route** in `kinetiqo/web/app.py`. Have it render a new Jinja2 template.
2.  **Create the template** in `kinetiqo/web/templates/`. Extend `base.html`.
3.  **Add a data API endpoint** (e.g., `/api/my_new_data`) in `app.py` that fetches data from the database using the `db_repo` object and returns JSON.
4.  In the template's JavaScript, use `fetch()` to call your new API endpoint and render the data (e.g., using Chart.js).

### Add a new database query
1.  Add the new method as an `@abstractmethod` in `db/repository.py`.
2.  Implement the method in all three concrete repositories (`postgresql.py`, `mysql.py`, `firebird.py`), writing the appropriate raw SQL for each dialect.
3.  Call the new method from your application logic (e.g., from a web route or the sync service).

## 8. Copilot-Specific Behaviour

- **Mirror existing patterns.** For a new web page, look at `/fitness` and `fitness.py`. For a new DB query, look at existing methods in the repositories.
- **Always update all three database backends** when changing the database interface.
- **Use raw, parameterised SQL.** Do not introduce an ORM.
- **Use `logging.getLogger("kinetiqo")`** for all operational output.
- **Follow the established import and type-hinting style.**
- **New configuration should be added as an environment variable** in the `Config` dataclass.
