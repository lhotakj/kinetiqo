---
layout: default
title: Architecture
nav_order: 98
---

# Architecture

This page provides a high-level overview of Kinetiqo's architecture, design patterns, and technology stack.

## Project Structure

```
src/
├── kinetiqo.py                 # CLI entry point (Click)
├── app.py                      # Alternative WSGI entry point
└── kinetiqo/                   # Core application package
    ├── __init__.py
    ├── __main__.py
    ├── cache.py                 # Strava API response cache
    ├── cli.py                   # Click CLI commands (sync, web, flightcheck, version)
    ├── config.py                # Config dataclass (reads env vars)
    ├── strava.py                # Strava API client (OAuth2, activity streams)
    ├── sync.py                  # SyncService (core sync logic, SSE progress)
    ├── version_check.py         # Async GitHub release version check
    ├── db/
    │   ├── repository.py        # DatabaseRepository ABC (contract for all backends)
    │   ├── factory.py           # create_repository() factory
    │   ├── schema.py            # DDL schema definitions
    │   ├── postgresql.py        # PostgreSQL implementation
    │   ├── mysql.py             # MySQL/MariaDB implementation
    │   └── firebird.py          # Firebird implementation
    └── web/
        ├── app.py               # Flask app, all routes & JSON API endpoints
        ├── auth.py              # flask-login User model & auth helpers
        ├── fitness.py           # CTL/ATL/TSB calculation (pandas)
        ├── vo2max.py            # VO₂max estimation (Townsend method)
        ├── progress.py          # SSE sync progress stream
        ├── static/              # Static assets (CSS, JS, images)
        └── templates/           # Jinja2 templates
            ├── base.html            # Base layout (sidebar, dark mode, CDN imports)
            ├── activities.html      # Activity list (DataTables, Select2, DateRangePicker)
            ├── map.html             # Leaflet map with multi-provider tile layers
            ├── powerskills.html     # Power Skills spider chart (Chart.js)
            ├── ftp.html             # FTP estimation history chart
            ├── fitness.html         # Fitness & Freshness chart (CTL/ATL/TSB)
            ├── vo2max.html          # VO₂max estimation chart
            ├── settings.html        # Settings page (profile, goals, config)
            ├── logs.html            # Audit log viewer
            ├── license.html         # License & attribution page
            ├── login.html           # Login form
            ├── sync.html            # Sync trigger page
            ├── progress.html        # SSE progress bar
            └── _*.html              # Reusable partials (filters, selectors)
tests/
├── test_sync_logic.py           # Canonical mocked unit test example
├── test_cli_sync.py             # CLI sync command tests
├── test_ftp.py                  # FTP estimation tests
└── test_vo2max.py               # VO₂max estimation tests
```

## Key Design Patterns

- **Repository Pattern:** All database access is via the `DatabaseRepository` ABC, with a factory for backend selection.
- **Raw SQL:** No ORM; all queries are parameterized and backend-specific.
- **Async Flask Web UI:** All routes and JSON APIs are async for scalability.
- **HTMX:** Used for real-time sync progress and reactivity (SSE).
- **Pandas:** Used for fitness calculations (CTL/ATL/TSB, Power Skills, etc.).
- **Session Auth:** flask-login for secure sessions.
- **Response Compression:** flask-compress for all HTTP responses.

## Technology Stack

| Concern                | Technology                        | Version         |
|------------------------|-----------------------------------|-----------------|
| Language               | Python                            | 3.13            |
| Web framework          | Flask[async] + flask-login        | 3.1.3 / 0.6.3   |
| Response compression   | flask-compress                    | 1.24            |
| WSGI server            | Gunicorn                          | 25.3.0          |
| CLI                    | Click                             | 8.3.2           |
| HTTP client            | httpx                             | 0.28.1          |
| Data processing        | pandas                            | 3.0.2           |
| Versioning             | packaging                         | 26.0            |
| PostgreSQL driver      | psycopg2-binary                   | 2.9.11          |
| MySQL driver           | mysql-connector-python            | 9.6.0           |
| Firebird driver        | firebird-driver                   | 2.0.2           |
| Frontend CSS           | Tailwind CSS                      | CDN (play)      |
| Reactivity             | HTMX + htmx-ext-sse               | 2.0.4 / 2.2.2   |
| Data tables            | DataTables + Buttons + ColReorder | 2.3.7 / 3.2.6 / 2.1.2 |
| Charting               | Chart.js + chartjs-adapter-moment | 4.x / 1.0       |
| Maps                   | Leaflet.js                        | 1.9             |
| Dropdowns              | Select2                           | 4.1             |
| Date pickers           | DateRangePicker + Moment.js       | latest / 2.30   |
| Drag & drop            | SortableJS                        | 1.15            |
| Fonts                  | Inter (variable), Italiana        | Google Fonts    |
| Container base         | python:3.13-alpine                | —               |
| Scheduler              | dcron                             | Alpine package  |
| Testing                | unittest + unittest.mock           | stdlib          |

## Extensibility
- Add new database backends by implementing the `DatabaseRepository` ABC and registering in the factory.
- Add new web features by creating a new file in `kinetiqo/web/`, defining a route in `app.py`, and adding a template.
- All configuration is via environment variables (see [Configuration](configuration.md)).

## Security
- All user data is stored locally; no third-party cloud storage.
- OAuth 2.0 for Strava, session-based auth for the web UI.
- All SQL is parameterized to prevent injection.
- HTTPS recommended for production deployments.

For more details, see the [README](https://github.com/lhotakj/kinetiqo#architecture) and the sidebar topics.

