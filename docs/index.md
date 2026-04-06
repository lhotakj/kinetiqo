---
layout: default
title: Home
nav_order: 1
---
<div class="video-crop">
  <video class="full-width-video" loop autoplay muted>
    <source src="{{ '/assets/promo.mov' | relative_url }}" type="video/mp4">
    Your browser does not support the video tag.
  </video>
</div>


**Kinetiqo** is a self-hosted fitness-data platform for Strava users. It syncs your activities from Strava into a high-performance SQL database (**PostgreSQL**, **MySQL/MariaDB**, or **Firebird**), giving you full ownership and control over your fitness history.

Visualize your progress with the **built-in Web UI** or integrate with business intelligence tools. For advanced analytics, Kinetiqo includes pre-configured **Grafana dashboards**.

---

## Key Features

- **Advanced Visualization**: Modern web UI for daily monitoring, plus Grafana dashboards for in-depth analysis.
- **Power Skills Analysis**: Spider chart of your best average power over 5s–1h durations.
- **FTP Estimation**: Automatic calculation of Functional Threshold Power (95% of best 20-min power) with history chart.
- **VO₂max Estimation**: Townsend method from 5-min MAP power, with trend and classification bands.
- **Fitness & Freshness**: CTL/ATL/TSB chart based on suffer score, configurable time constants.
- **Activity Goals**: Set and track weekly, monthly, yearly distance/elevation goals per activity type.
- **Interactive Maps**: Leaflet.js maps with multiple tile providers, server-side proxy, and Canvas renderer.
- **Dark Mode**: System preference detection and manual toggle.
- **Audit Logging**: All sync operations and data changes are logged and viewable in the Web UI.
- **Intelligent Synchronization**: Full and incremental sync modes, with real-time progress via SSE.
- **Automated Scheduling**: Built-in cron for unattended sync.
- **Response Compression**: All HTTP responses compressed (gzip/brotli) for fast loading.
- **Session-based Authentication**: Secure login with flask-login.
- **Container-Native**: Dockerized on `python:3.13-alpine` with a two-phase build.
- **Database Compatibility**: PostgreSQL (12+), MySQL 8/MariaDB 10+, Firebird (3.0, 4.0, 5.0).

---

## Supported Backends

- **PostgreSQL** (12+)
- **MySQL** (8+) / **MariaDB** (10+)
- **Firebird** (3.0, 4.0, 5.0)

---

## Web UI Highlights

- **Activities**: Searchable, filterable list with DataTables 2.x, column reordering, export, and bulk actions.
- **Mapping**: Interactive Leaflet.js maps with multiple tile providers and Canvas renderer.
- **Charts**: Fitness & Freshness (CTL/ATL/TSB), Power Skills, FTP, VO₂max, and goals.
- **Settings**: Manage athlete profile, goals, and app configuration.
- **Logs**: View audit logs of all sync and data operations.
- **Dark Mode**: Automatic and manual toggle.

---

## Command-Line Interface (CLI)

- **Sync**: Full and incremental sync with Strava.
- **Web**: Launch the web server.
- **Flightcheck**: Validate database connectivity and schema.
- **Version**: Show current version.

See [CLI Commands](cli-commands.md) for full details and examples.

---

## Architecture Overview

- **Repository Pattern**: Pluggable database backends via a factory.
- **Raw SQL**: No ORM, for maximum performance and transparency.
- **Async Flask Web UI**: All routes and JSON APIs are async for scalability.
- **HTMX**: Real-time sync progress and reactivity.
- **Pandas**: Used for fitness calculations.
- **Response Compression**: flask-compress for all HTTP responses.
- **Session Auth**: flask-login for secure sessions.

---

## Getting Started

1. **Install dependencies**: Python 3.13+, Docker (optional), and a supported database.
2. **Clone the repository** and set up your environment (see [Local Development](local-dev.md)).
3. **Configure environment variables**: See [Configuration](configuration.md) for all options.
4. **Run the app**: Use the CLI or Docker (see [Deployment](deployment.md)).

For full details, see the sidebar or visit each section above.
