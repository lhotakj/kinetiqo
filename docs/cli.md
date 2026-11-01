# Command-Line Interface (CLI) Reference

Kinetiqo includes a comprehensive Click-powered command-line interface (`src/kinetiqo.py`) for operating the web dashboard, running automated sync passes, executing system diagnostics, running database benchmarks, and serving the FastMCP protocol.

---

## 1. Global Options & Invocation

Execute commands using Python or the installed entrypoint:

```bash
python src/kinetiqo.py [OPTIONS] COMMAND [ARGS]...
```

### Global Options:
- `--log-level, -l [DEBUG|INFO|WARNING|ERROR|CRITICAL]`: Set terminal logging verbosity (default: `INFO`).
- `--database, -d [postgresql|mysql|firebird]`: Override configured database backend for the current invocation.
- `--help`: Show command documentation and exit.

---

## 2. CLI Command Catalog

### 2.1 `kinetiqo web`
Starts the async-enabled Flask web application.

```bash
python src/kinetiqo.py web [OPTIONS]
```

- `--port, -p INTEGER`: Port to bind the HTTP server (default: `4444` or `$PORT`).
- `--host, -h TEXT`: Host interface to bind (default: `0.0.0.0`).
- `--database, -d [postgresql|mysql|firebird]`: Override default database backend.

*Example:*
```bash
python src/kinetiqo.py web --port 5000 --host 127.0.0.1
```

---

### 2.2 `kinetiqo sync`
Executes Strava synchronization, streams ingestion, trophy extraction, and weather enrichment.

```bash
python src/kinetiqo.py sync [OPTIONS]
```

- `--fast-sync, --fast`: Incremental fast sync checking the 30 newest activities (default for cron).
- `--full-sync, --full`: Complete historical audit of all activities.
- `--period, -p TEXT`: Limit synchronization scope (e.g. `30d`, `6m`, `1y`).
- `--update-strava-description / --no-update-strava-description`: Toggle automatic description generation.
- `--weather-data / --no-weather-data`: Toggle historical weather enrichment via Visual Crossing Timeline API (1,000 free records/day from [visualcrossing.com/weather-api](https://www.visualcrossing.com/weather-api); see [docs/weather.md](weather.md)).
- `--resync-weather`: Force weather re-download and recalculation for workouts in scope.
- `--database, -d [postgresql|mysql|firebird]`: Override database backend.

*Examples:*
```bash
# Rapid incremental sync
python src/kinetiqo.py sync --fast

# Full historical audit
python src/kinetiqo.py sync --full

# Sync last 90 days without modifying Strava descriptions
python src/kinetiqo.py sync --period 90d --no-update-strava-description
```

---

### 2.3 `kinetiqo mcp`
Launches the FastMCP Model Context Protocol server for AI assistant integration.

```bash
python src/kinetiqo.py mcp [OPTIONS]
```

- `--transport, -t [stdio|sse|http]`: Transport protocol (default: `stdio`).
- `--host, -h TEXT`: Host address for SSE/HTTP transports (default: `0.0.0.0`).
- `--port, -p INTEGER`: Port for SSE/HTTP transports (default: `8000`).
- `--database, -d [postgresql|mysql|firebird]`: Override database backend.

*Examples:*
```bash
# Run for Claude Desktop / Antigravity via STDIO
python src/kinetiqo.py mcp

# Run standalone FastMCP Server over SSE
python src/kinetiqo.py mcp --transport sse --port 8000
```

---

### 2.4 `kinetiqo flightcheck`
Performs comprehensive pre-flight verification of database connectivity, table schema validity, Strava OAuth token health, and Playwright Chromium availability.

```bash
python src/kinetiqo.py flightcheck
```

---

### 2.5 `kinetiqo benchmark`
Runs a standardized database benchmark measuring driver throughput across activities, stream points, and complex aggregates.

```bash
python src/kinetiqo.py benchmark [OPTIONS]
```

- `--scope, -s INTEGER`: Number of days of historical data to evaluate (default: `365`).
- `--database, -d [postgresql|mysql|firebird]`: Database engine to test.

*Example:*
```bash
python src/kinetiqo.py benchmark --scope 365 --database postgresql
```

---

### 2.6 `kinetiqo scan-trophies`
Scans and backfills historical segment trophies (KOMs, PRs, and 1st–10th place finishes) from detailed activity records into the database `activities.trophies` column and `verified_trophies.json`.

```bash
python src/kinetiqo.py scan-trophies [OPTIONS]
```

- `--limit, -l INTEGER`: Maximum number of activities to process.
- `--database, -d [postgresql|mysql|firebird]`: Target database.

---

### 2.7 `kinetiqo backfill-weather`
Populates summary scalar weather columns (`weather_temp_avg`, `weather_condition`, etc.) on the `activities` table from existing cached raw `weather_json` in the database.

```bash
python src/kinetiqo.py backfill-weather [OPTIONS]
```

- `--batch-size, -b INTEGER`: Number of records to process per transaction batch (default: `100`).

---

### 2.8 `kinetiqo version`
Prints the application version, build commit, and Python environment details.

```bash
python src/kinetiqo.py version
```

