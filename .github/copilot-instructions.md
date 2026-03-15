# Copilot Instructions for Kinetiqo Project

## 1. Project Overview

Kinetiqo is a Python fitness-data platform that syncs activities from the **Strava API**, stores them in a relational database, and serves them through a web dashboard. It supports three database backends (PostgreSQL, MySQL, Firebird) via a Repository/Factory pattern and exposes both a **Click CLI** and a **Flask web UI**.

The web UI includes:
- A searchable and filterable activity list powered by **DataTables**.
- Interactive activity mapping using **Leaflet.js**.
- A **Fitness & Freshness** chart (CTL/ATL/TSB) based on suffer score.
- A **Power Skills** spider chart analyzing best average power over various durations.
- HTMX-powered reactivity for features like real-time sync progress via SSE.
- An asynchronous, cached check for new application versions against GitHub releases.

## 2. Testing Philosophy: Mocked Unit Tests First

**This is a critical instruction.** The default testing strategy for this project is **fast, isolated unit tests**. All external dependencies, especially the database and the Strava API, **must be mocked**.

- **When asked to create tests, always provide mocked unit tests by default.** Do not create integration tests that require a live database unless specifically requested.
- **Use `unittest.mock.patch`** to intercept calls to external services. The primary targets for patching are `kinetiqo.sync.create_repository`, `kinetiqo.cli.create_repository`, and `kinetiqo.sync.StravaClient`.
- **Canonical Example:** The file `tests/test_sync_logic.py` is the gold standard for how tests should be written in this project. Follow its structure (class-level patches, `subTest` for matrix tests) precisely.

## 3. Key Technologies & Versions

| Concern | Technology | Notes |
|---|---|---|
| Language | **Python 3.13** | Dockerised on `python:3.13-alpine` |
| Testing | **unittest** + **unittest.mock** | Core testing framework |
| Web framework | **Flask[async] 3.1** + **flask-login 0.6** | Jinja2 templates, Gunicorn in production |
| Frontend | **Tailwind CSS** (CDN), **HTMX 1.9** (SSE), **DataTables 2.x**, **Select2**, **Chart.js 3.x** | No build step; all loaded from CDN |
| Charting | **Chart.js 3.x** + **chartjs-adapter-moment** | Client-side rendering for Fitness & Power Skills |
| CLI | **Click 8.3** | Entry point: `python src/kinetiqo.py <command>` |
| Database drivers | **psycopg2-binary 2.9**, **mysql-connector-python 9.6**, **firebird-driver 2.0** | Raw SQL — no ORM |
| HTTP client | **httpx 0.27** | For async Strava & GitHub API calls |
| Data processing | **pandas 3.0** | Used for Fitness (CTL/ATL) calculations |
| Versioning | **packaging 24.1** | For SemVer comparisons |
| Logging | **loguru 0.7** | For application logging |

## 4. Project Structure

```
src/
├── kinetiqo.py             # CLI entry point
└── kinetiqo/               # Core application package
    ├── cli.py               # Click CLI commands
    ├── config.py            # Config dataclass (reads env vars)
    ├── sync.py              # SyncService (core sync logic)
    ├── version_check.py     # New version check logic
    ├── db/
    │   ├── repository.py    # DatabaseRepository ABC
    │   ├── factory.py       # create_repository() factory
    │   ├── schema.py        # DDL schema definition
    │   ├── postgresql.py, mysql.py, firebird.py # Implementations
    └── web/
        ├── app.py           # Flask app, routes, API endpoints
        ├── fitness.py       # Logic for Fitness chart
        └── templates/       # Jinja2 templates
tests/
└── test_sync_logic.py      # Canonical example for mocked unit tests
```

## 5. Architecture & Design Patterns

### 5.1 Repository Pattern (Database)
- **`DatabaseRepository`** (ABC in `db/repository.py`) defines the contract.
- The **`create_repository()`** factory in `db/factory.py` is the single entry point for creating a database object. **This is the primary function to mock in tests.**

### 5.2 Web Layer & Data Visualization
- The Flask app in `kinetiqo/web/app.py` defines all routes. It supports `async` views.
- Data-heavy pages render a template shell, which then calls a JSON API endpoint (e.g., `/api/fitness_data`) to load data for client-side rendering with Chart.js.

### 5.3 Logging
- Use `loguru.logger` for all new logging. The project is migrating from the standard `logging` module.

## 6. Common Tasks & How-To

### Add a new feature with a web UI
1.  **Create the data logic** in a new file (e.g., `kinetiqo/web/my_feature.py`).
2.  **Define the route** in `kinetiqo/web/app.py` to render the template. Use `async def` for new routes.
3.  **Add a JSON API endpoint** in `app.py` to provide data for the UI. Use `async def`.
4.  **Create the template** in `kinetiqo/web/templates/`.
5.  **Write a mocked unit test** for the new logic. Create a new test file in `tests/` that mocks the database and any other external services, following the pattern in `tests/test_sync_logic.py`.

### Add a new database query
1.  Add the new method as an `@abstractmethod` in `db/repository.py`.
2.  Implement the method in all three concrete repositories (`postgresql.py`, `mysql.py`, `firebird.py`).
3.  **Write a mocked unit test** that verifies the application logic correctly calls your new repository method with the expected arguments.

## 7. Copilot-Specific Behaviour

- **Provide complete, runnable code snippets.** When editing a file, show the full file content, not just the changed lines.
- **Focus on one file at a time.** Do not attempt to make changes to multiple files in a single response.
- **When asked to create tests, always provide mocked unit tests by default.** Follow the structure in `tests/test_sync_logic.py`.
- **Always update all three database backends** when changing the `DatabaseRepository` interface, but do so in separate, sequential steps.
- **Use the `packaging.version.parse()` function** for any semantic version comparisons.
- **Use raw, parameterised SQL.** Do not introduce an ORM.
- **Use `loguru.logger`** for all operational output.
- **Follow the established import and type-hinting style.**
- **New configuration should be added as an environment variable** in the `Config` dataclass.
