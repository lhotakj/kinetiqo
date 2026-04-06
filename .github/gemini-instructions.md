# Gemini Instructions for Kinetiqo Project

## 1. Project Overview

Kinetiqo is a Python fitness-data platform that syncs activities from the **Strava API**, stores them in a relational database, and serves them through a web dashboard. It supports three database backends (PostgreSQL, MySQL, Firebird) via a Repository/Factory pattern and exposes both a **Click CLI** and a **Flask web UI**.

The web UI includes:
- A searchable and filterable activity list powered by **DataTables 2.x** with column reordering (ColReorder), export (Buttons), and bulk actions.
- Interactive activity mapping using **Leaflet.js** with multiple tile providers and a Canvas renderer.
- A **Fitness & Freshness** chart (CTL/ATL/TSB) based on suffer score, calculated with pandas.
- A **Power Skills** spider chart analyzing best average power over various durations (5s–1h).
- **FTP Estimation**: 95% of best 20-minute average power, with history chart.
- **VO₂max Estimation**: Townsend method from 5-minute MAP power, with trend and classification bands.
- **Activity Goals**: Weekly/monthly/yearly distance and elevation goals per activity type.
- HTMX-powered reactivity for features like real-time sync progress via SSE.
- An asynchronous, cached check for new application versions against GitHub releases.
- **Dark mode** support with system preference detection and manual toggle.
- **Response compression** via `flask-compress` (gzip/brotli) for all HTTP responses.
- **Session-based authentication** via `flask-login`.

## 2. Testing Philosophy: Mocked Unit Tests First

**This is a critical instruction.** The default testing strategy for this project is **fast, isolated unit tests**. All external dependencies, especially the database and the Strava API, **must be mocked**.

- **When asked to create tests, always provide mocked unit tests by default.** Do not create integration tests that require a live database unless specifically requested.
- **Use `unittest.mock.patch`** to intercept calls to external services. The primary targets for patching are `kinetiqo.sync.create_repository`, `kinetiqo.cli.create_repository`, and `kinetiqo.sync.StravaClient`.
- **Canonical Example:** The file `tests/test_sync_logic.py` is the gold standard for how tests should be written in this project. Follow its structure (class-level patches, `subTest` for matrix tests) precisely.
- **Existing test files:** `test_sync_logic.py`, `test_cli_sync.py`, `test_ftp.py`, `test_vo2max.py`.
- **Running tests:** `PYTHONPATH=src python -m unittest discover -s tests -v` (dependencies must be installed; in Docker the environment is pre-configured).

## 3. Key Technologies & Versions

| Concern | Technology | Version | Notes |
|---|---|---|---|
| Language | **Python** | 3.13 | Dockerised on `python:3.13-alpine` |
| Testing | **unittest** + **unittest.mock** | stdlib | No pytest |
| Web framework | **Flask[async]** + **flask-login** | 3.1.3 / 0.6.3 | Jinja2 templates, Gunicorn (25.3) in production |
| Response compression | **flask-compress** | 1.24 | Automatic gzip/brotli for all responses |
| Frontend CSS | **Tailwind CSS** | CDN (play) | No build step |
| Reactivity | **HTMX** + **htmx-ext-sse** | 2.0.4 / 2.2.2 | SSE for sync progress |
| Data tables | **DataTables** + **Buttons** + **ColReorder** | 2.3.7 / 3.2.6 / 2.1.2 | Client-side processing mode |
| Charting | **Chart.js** + **chartjs-adapter-moment** | 4.x / 1.0 | Client-side rendering |
| Maps | **Leaflet.js** | 1.9 | Canvas renderer, server-side tile proxy |
| Dropdowns | **Select2** | 4.1 | Activity type filter |
| Date pickers | **DateRangePicker** + **Moment.js** | latest / 2.30 | Date filter presets |
| Drag & drop | **SortableJS** | 1.15 | Column reorder in activities grid |
| CLI | **Click** | 8.3.2 | Entry point: `python src/kinetiqo.py <command>` |
| Database drivers | **psycopg2-binary**, **mysql-connector-python**, **firebird-driver** | 2.9.11 / 9.6.0 / 2.0.2 | Raw SQL — no ORM |
| HTTP client | **httpx** | 0.28.1 | For async Strava & GitHub API calls |
| Data processing | **pandas** | 3.0.2 | Used for Fitness (CTL/ATL) calculations |
| Versioning | **packaging** | 26.0 | For SemVer comparisons |

## 4. Project Structure

```
src/
├── kinetiqo.py                 # CLI entry point (Click)
├── app.py                      # Alternative WSGI entry point
└── kinetiqo/                   # Core application package
    ├── __init__.py
    ├── __main__.py
    ├── cache.py                 # Strava API response cache
    ├── cli.py                   # Click CLI commands (sync, web, flightcheck, version)
    ├── config.py                # Config dataclass (reads all env vars)
    ├── strava.py                # Strava API client (OAuth2, activity streams)
    ├── sync.py                  # SyncService (core sync logic, SSE progress)
    ├── version_check.py         # Async GitHub release version check
    ├── db/
    │   ├── repository.py        # DatabaseRepository ABC (contract for all backends)
    │   ├── factory.py           # create_repository() factory
    │   ├── schema.py            # DDL schema definitions
    │   ├── postgresql.py        # PostgreSQL implementation (raw SQL)
    │   ├── mysql.py             # MySQL/MariaDB implementation (raw SQL)
    │   └── firebird.py          # Firebird implementation (raw SQL)
    └── web/
        ├── app.py               # Flask app, all routes & JSON API endpoints (~1667 lines)
        ├── auth.py              # flask-login User model & auth helpers
        ├── fitness.py           # CTL/ATL/TSB calculation (pandas)
        ├── vo2max.py            # VO₂max estimation (Townsend method)
        ├── progress.py          # SSE sync progress stream
        ├── static/              # Static assets (CSS, JS, images)
        └── templates/           # Jinja2 templates (base.html + 15 page/partial templates)
tests/
├── test_sync_logic.py           # Canonical mocked unit test example
├── test_cli_sync.py             # CLI sync command tests
├── test_ftp.py                  # FTP estimation tests
└── test_vo2max.py               # VO₂max estimation tests
build/
├── Dockerfile                   # Application image (Phase 2)
├── Dockerfile.firebird-base     # Firebird base image (Phase 1)
├── build.sh / build-base.sh     # Local build scripts
└── entrypoint.sh                # Container entrypoint (cron + Gunicorn)
```

## 5. Architecture & Design Patterns

### 5.1 Repository Pattern (Database)
- **`DatabaseRepository`** (ABC in `db/repository.py`) defines the contract. Key methods include `upsert_activity`, `get_activities_web`, `get_activities_totals`, `get_profile`, `upsert_profile`, `get_goals`, `upsert_goal`, `get_activity_streams`, etc.
- The **`create_repository()`** factory in `db/factory.py` is the single entry point for creating a database object. **This is the primary function to mock in tests.**
- All three backends (`postgresql.py`, `mysql.py`, `firebird.py`) implement identical SQL logic adapted to each dialect.

### 5.2 Web Layer & Data Visualization
- The Flask app in `kinetiqo/web/app.py` defines all routes and API endpoints. It uses `flask-compress` for automatic response compression.
- Data-heavy pages render a template shell, which then calls a JSON API endpoint (e.g., `/api/fitness_data`, `/api/ftp_history`, `/api/vo2max_history`, `/api/activities`) to load data for client-side rendering with Chart.js or DataTables.
- The activities page uses client-side DataTables processing with extensive localStorage state persistence (column visibility, order, sort, filters, selection).
- Map rendering uses compact `[lat, lng]` arrays via `/api/map/data` with Leaflet Canvas renderer.
- **Internal app navigation stays in the same tab.** Only external links (Strava, documentation, license URLs) open in new tabs.

### 5.3 Web Routes & API Endpoints

**Page routes:** `/`, `/activities`, `/map`, `/powerskills`, `/ftp`, `/fitness`, `/vo2max`, `/settings`, `/logs`, `/license`, `/login`, `/logout`, `/sync`

**JSON API endpoints:** `/api/activities` (GET/DELETE), `/api/activities/<id>` (DELETE), `/api/map/data` (POST), `/api/fitness_data` (GET), `/api/ftp_history` (GET), `/api/vo2max_history` (GET), `/api/settings` (GET), `/api/profile` (GET/PUT), `/api/goals` (GET/PUT)

**Tile proxy:** `/tiles/osm/<z>/<x>/<y>.png`

### 5.4 Configuration
- All configuration is via environment variables, read in the `Config` dataclass (`config.py`).
- Athlete weight resolution order: (1) profile DB table (synced from Strava), (2) Settings page, (3) `ATHLETE_WEIGHT` env var fallback.
- Map API keys (`MAPY_API_KEY`, `THUNDERFOREST_API_KEY`) conditionally show/hide tile layer options.

### 5.5 Logging
- The web layer currently uses standard `logging` module (`logging.getLogger("kinetiqo.web")`).
- The sync/CLI layer is migrating to `loguru.logger`. Use `loguru.logger` for all new logging in non-web code.

### 5.6 Frontend Patterns
- All frontend libraries are loaded from CDN — **no build step** required.
- Templates extend `base.html` which provides the sidebar layout, dark mode, and shared CDN imports.
- Reusable partials are prefixed with `_` (e.g., `_activity_filter.html`, `_activity_type_selector.html`, `_period_select.html`).
- Grid state (column visibility, order, sort) is persisted to `localStorage` with a schema version key for migrations.
- SortableJS handles visual drag-and-drop on the `<thead>` row; ColReorder API applies the reorder to DataTables internally.

### 5.7 Docker & Deployment
- Two-phase Docker build: Firebird base image (`Dockerfile.firebird-base`) + app image (`Dockerfile`).
- Production: Gunicorn with 4 workers, 180s timeout, port 4444.
- `dcron` in the Alpine container handles scheduled sync jobs (`FULL_SYNC`, `FAST_SYNC` env vars).

## 6. Common Tasks & How-To

### Add a new feature with a web UI
1.  **Create the data logic** in a new file (e.g., `kinetiqo/web/my_feature.py`).
2.  **Define the route** in `kinetiqo/web/app.py` to render the template. Use `async def` for new routes.
3.  **Add a JSON API endpoint** in `app.py` to provide data for the UI. Use `async def`.
4.  **Create the template** in `kinetiqo/web/templates/`, extending `base.html`.
5.  **Write a mocked unit test** for the new logic. Create a new test file in `tests/` that mocks the database and any other external services, following the pattern in `tests/test_sync_logic.py`.

### Add a new database query
1.  Add the new method as an `@abstractmethod` in `db/repository.py`.
2.  Implement the method in all three concrete repositories (`postgresql.py`, `mysql.py`, `firebird.py`) using raw parameterised SQL.
3.  **Write a mocked unit test** that verifies the application logic correctly calls your new repository method with the expected arguments.

### Update a frontend library version
1.  Update the CDN URL in `base.html` (for core libs) or the relevant page template (for page-specific libs).
2.  Verify plugin compatibility — DataTables plugins must be compatible with the core DataTables version.
3.  Update the version number in `license.html` in the Frontend Libraries table.

## 7. Gemini-Specific Behaviour

- **You are capable of multi-file updates. When a task requires changing multiple files (e.g., updating a repository and its callers), please do so in a single turn.**
- **When asked to create tests, always provide mocked unit tests by default.** Follow the structure in `tests/test_sync_logic.py`.
- **Always update all three database backends** when changing the `DatabaseRepository` interface.
- **Use the `packaging.version.parse()` function** for any semantic version comparisons.
- **Use raw, parameterised SQL.** Do not introduce an ORM.
- **Use `loguru.logger`** for all operational output in non-web code. Use standard `logging` in `web/app.py`.
- **Follow the established import and type-hinting style.**
- **New configuration should be added as an environment variable** in the `Config` dataclass.
- **When updating CDN library versions**, also update `license.html` to keep the attribution page accurate.
- **Internal app links must stay in the same browser tab.** Only external links (Strava, documentation, third-party sites) should use `target="_blank"`.
