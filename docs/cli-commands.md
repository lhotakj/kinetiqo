---
layout: default
title: CLI Commands
nav_order: 4
---

# Command-Line Interface (CLI)

The CLI tool is located in the `src` directory. All commands are available via `python src/kinetiqo.py <command>`.

## CLI Reference

- `--database` / `-d`: Selects the database backend (`mysql`, `postgresql`, or `firebird`), overriding environment variables.
- `sync`: Initiates data synchronization.
  - `--full-sync` / `-f`: Executes a full synchronization audit.
  - `--fast-sync` / `-q`: Executes an incremental synchronization.
  - `--period` / `-p`: Restricts full synchronization to a specific timeframe (e.g., '7d', '2w', '1m', '1y').
  - `--enable-strava-cache`: Activates API response caching.
  - `--cache-ttl`: Defines cache time-to-live in minutes (default: 60).
  - `--clear-cache`: Purges the cache prior to synchronization.
- `web`: Launches the web server.
  - `--port`: Specifies the listening port (default: 4444).
  - `--host`: Specifies the bind address (default: 0.0.0.0).
- `flightcheck`: Validates database connectivity and schema integrity.
- `version`: Outputs the current version information.

## Examples

### Synchronization

#### Full Sync
Perform a complete audit of your Strava history.

```bash
python src/kinetiqo.py sync --full-sync
```

#### Incremental Sync
Fetch only the most recent activities.

```bash
python src/kinetiqo.py sync --fast-sync
```

#### Limited Scope Sync
Sync only the last 7 days of activities (Full Sync mode).

```bash
python src/kinetiqo.py sync --full-sync --period 7d
```

Sync only the last 2 weeks.

```bash
python src/kinetiqo.py sync --full-sync --period 2w
```

Sync only the last month.

```bash
python src/kinetiqo.py sync --full-sync --period 1m
```

Sync only the last year.

```bash
python src/kinetiqo.py sync --full-sync --period 1y
```

#### Caching
Enable caching to speed up repeated runs during development.

```bash
python src/kinetiqo.py sync --fast-sync --enable-strava-cache
```

Set a custom cache TTL (e.g., 30 minutes).

```bash
python src/kinetiqo.py sync --fast-sync --enable-strava-cache --cache-ttl 30
```

Clear the cache before syncing.

```bash
python src/kinetiqo.py sync --fast-sync --clear-cache
```

### Web Server

Start the web server on the default port (4444).

```bash
python src/kinetiqo.py web
```

Start on a custom port (e.g., 8000).

```bash
python src/kinetiqo.py web --port 8000
```

Bind to a specific host (e.g., localhost only).

```bash
python src/kinetiqo.py web --host 127.0.0.1
```

### Database Selection

Force usage of MySQL backend.

```bash
python src/kinetiqo.py --database mysql web
```

Force usage of PostgreSQL backend.

```bash
python src/kinetiqo.py --database postgresql sync --fast-sync
```

Force usage of Firebird backend.

```bash
python src/kinetiqo.py --database firebird web
```

### Diagnostics

Check database connection and schema.

```bash
python src/kinetiqo.py flightcheck
```

Check version.

```bash
python src/kinetiqo.py version
```

## Troubleshooting
- If you encounter database errors, check your environment variables and database connectivity.
- For more help, see [Configuration](configuration.md) and [Deployment](deployment.md).
