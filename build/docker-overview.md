# Kinetiqo

Kinetiqo liberates your Strava activities, syncing them into a high-performance SQL database (**PostgreSQL**, **MySQL/MariaDB**, or **Firebird**) for ultimate control.

Visualize your progress with our **built-in Web UI** or dive deep with the included **Grafana dashboards**. Whether you're a data nerd or just want to see your stats without limits, Kinetiqo is your personal fitness data warehouse.

## Features

- 📊 **Rich Visualization**: Includes a sleek Web UI for quick access and powerful Grafana dashboards for deep analysis.
- 📈 **MEGA Stats Infographic**: Generate Veloviewer-style infographics with activity calendar heatmaps, configurable metrics and persisted layout settings for any year or period. Export as PNG or PDF.
- 📸 **Activity Poster Generator**: Create professional posters with self-hosted fonts, colors, draggable layouts, 4:3/16:9/1:1 ratios, background photos or configurable Leaflet maps, persistent map center/zoom, and Playwright-powered PNG export.
- 🗺️ **Map Export**: Use multiple tile providers, fullscreen mode, persistent route/map styling, tone controls, and viewport PNG export with attribution and watermarking.
- 🔄 **Smart Sync**:
  - **Full Sync**: Complete library audit—fetches everything, fills gaps, and prunes deleted activities.
  - **Fast Sync**: Lightning-fast updates for your latest workouts.
- 🐳 **Docker Native**: Drop it into your stack and forget it.
- ⏱️ **Set & Forget**: Built-in cron scheduler keeps your data fresh automatically.
- 💾 **Database Agnostic**:
  - **PostgreSQL** (version 12+)
  - **MySQL 8 / MariaDB 10+**
  - **Firebird** (3.0, 4.0, 5.0)
- 🚀 **Optimized**: Intelligent caching minimizes API usage and maximizes speed.
- 🔒 **Secure**: OAuth 2.0 authentication keeps your Strava account safe.

## Quick Start

Kinetiqo builds two official container variants:
- **`kinetiqo/web:latest` (Standalone)**: Web Dashboard (`0.0.0.0:4444`) + background Cron sync.
- **`kinetiqo/web-mcp:latest` (Kinetiqo + MCP)**: Web Dashboard (`0.0.0.0:4444`) + Cron + **FastMCP SSE Server** (`0.0.0.0:8000/sse`) running concurrently.

---

### Option 1: Standalone Kinetiqo (Web UI + Cron Sync)

#### Docker Run (Standalone)

```bash
docker run -d \
  --name kinetiqo \
  --restart unless-stopped \
  -p 4444:4444 \
  -e STRAVA_CLIENT_ID="your_strava_client_id" \
  -e STRAVA_CLIENT_SECRET="your_strava_client_secret" \
  -e STRAVA_REFRESH_TOKEN="your_strava_refresh_token" \
  -e SECRET_KEY="replace_with_output_from_openssl_rand_hex_32" \
  -e KINETIQO_PRODUCTION=1 \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword13" \
  -e DATABASE_TYPE="postgresql" \
  -e POSTGRESQL_HOST="postgresql" \
  -e POSTGRESQL_PORT="5432" \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="your_password" \
  -e POSTGRESQL_DATABASE="kinetiqo" \
  -e POSTGRESQL_SSL_MODE="disable" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e MAPY_API_KEY="your_mapy_com_api_token" \
  -e THUNDERFOREST_API_KEY="your_thunderforest_api_token" \
  -e MAPTILER_API_KEY="your_maptiler_api_token" \
  -e GEOAPIFY_API_KEY="your_geoapify_api_token" \
  -e CARTO_API_KEY="your_carto_api_key" \
  -e ATHLETE_WEIGHT="75" \
  -e DATE_FORMAT="%b %d, %Y" \
  -e GPS_SIMPLIFICATION="0" \
  -e LOG_LEVEL="INFO" \
  -e UPDATE_STRAVA_CYCLING_OUTDOOR="Year-to-date: {{cycling-distance-total-year}} cycled.{{new-line}}" \
  -e UPDATE_STRAVA_CYCLING_INDOOR="Indoor ride — {{cycling-distance-total-year}} cycled so far.{{new-line}}" \
  -e UPDATE_STRAVA_PLACEMENT="end" \
  -e WORKOUT_SUMMARY_PEAK_THRESHOLD_W="300" \
  -e PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="" \
  kinetiqo/web:latest
```

The web dashboard is available at **http://localhost:4444**.

#### Docker Compose (Standalone)

```yaml
services:
  kinetiqo:
    image: kinetiqo/web:latest
    container_name: kinetiqo
    restart: unless-stopped
    ports:
      - "4444:4444"
    env_file:
      - .env
    depends_on:
      postgresql:
        condition: service_healthy

  postgresql:
    image: postgres:16-alpine
    container_name: postgresql
    restart: unless-stopped
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${POSTGRESQL_PASSWORD}
      - POSTGRES_DB=kinetiqo
    volumes:
      - postgresql_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d kinetiqo"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgresql_data:
```

---

### Option 2: Kinetiqo + Embedded MCP Server (Web UI + Cron + MCP SSE)

#### Docker Run (Embedded MCP)

Expose **both ports** (`4444` for Web UI, `8000` for FastMCP SSE):

```bash
docker run -d \
  --name kinetiqo \
  --restart unless-stopped \
  -p 4444:4444 \
  -p 8000:8000 \
  -e ENABLE_MCP=1 \
  -e MCP_PORT=8000 \
  -e MCP_HOST="0.0.0.0" \
  -e MCP_TRANSPORT="sse" \
  -e KINETIQO_MCP_ALLOW_SYNC=0 \
  -e KINETIQO_MCP_ALLOW_PROFILE_WRITE=0 \
  -e KINETIQO_MCP_ALLOW_STRAVA_WRITE=0 \
  -e STRAVA_CLIENT_ID="your_strava_client_id" \
  -e STRAVA_CLIENT_SECRET="your_strava_client_secret" \
  -e STRAVA_REFRESH_TOKEN="your_strava_refresh_token" \
  -e SECRET_KEY="replace_with_output_from_openssl_rand_hex_32" \
  -e KINETIQO_PRODUCTION=1 \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword13" \
  -e DATABASE_TYPE="postgresql" \
  -e POSTGRESQL_HOST="postgresql" \
  -e POSTGRESQL_PORT="5432" \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="your_password" \
  -e POSTGRESQL_DATABASE="kinetiqo" \
  -e POSTGRESQL_SSL_MODE="disable" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e MAPY_API_KEY="your_mapy_com_api_token" \
  -e THUNDERFOREST_API_KEY="your_thunderforest_api_token" \
  -e MAPTILER_API_KEY="your_maptiler_api_token" \
  -e GEOAPIFY_API_KEY="your_geoapify_api_token" \
  -e CARTO_API_KEY="your_carto_api_key" \
  -e ATHLETE_WEIGHT="75" \
  -e DATE_FORMAT="%b %d, %Y" \
  -e GPS_SIMPLIFICATION="0" \
  -e LOG_LEVEL="INFO" \
  -e UPDATE_STRAVA_CYCLING_OUTDOOR="Year-to-date: {{cycling-distance-total-year}} cycled.{{new-line}}" \
  -e UPDATE_STRAVA_CYCLING_INDOOR="Indoor ride — {{cycling-distance-total-year}} cycled so far.{{new-line}}" \
  -e UPDATE_STRAVA_PLACEMENT="end" \
  -e WORKOUT_SUMMARY_PEAK_THRESHOLD_W="300" \
  -e PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="" \
  kinetiqo/web-mcp:latest
```

- Web Dashboard: **http://localhost:4444**
- FastMCP SSE Endpoint: **http://localhost:8000/sse**

#### Docker Compose (Embedded MCP)

```yaml
services:
  kinetiqo:
    image: kinetiqo/web-mcp:latest
    container_name: kinetiqo
    restart: unless-stopped
    ports:
      - "4444:4444"   # Web UI
      - "8000:8000"   # FastMCP SSE
    env_file:
      - .env
    environment:
      - ENABLE_MCP=1
      - MCP_PORT=8000
      - MCP_HOST=0.0.0.0
      - MCP_TRANSPORT=sse
      - KINETIQO_MCP_ALLOW_SYNC=${KINETIQO_MCP_ALLOW_SYNC:-0}
      - KINETIQO_MCP_ALLOW_PROFILE_WRITE=${KINETIQO_MCP_ALLOW_PROFILE_WRITE:-0}
      - KINETIQO_MCP_ALLOW_STRAVA_WRITE=${KINETIQO_MCP_ALLOW_STRAVA_WRITE:-0}
    depends_on:
      postgresql:
        condition: service_healthy

  postgresql:
    image: postgres:16-alpine
    container_name: postgresql
    restart: unless-stopped
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${POSTGRESQL_PASSWORD}
      - POSTGRES_DB=kinetiqo
    volumes:
      - postgresql_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d kinetiqo"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgresql_data:
```

## Configuration

Kinetiqo is configured entirely via environment variables.

### Strava API
| Variable | Description | Required |
|----------|-------------|----------|
| `STRAVA_CLIENT_ID` | Your Strava Application Client ID | ✅ |
| `STRAVA_CLIENT_SECRET` | Your Strava Application Client Secret | ✅ |
| `STRAVA_REFRESH_TOKEN` | A valid Refresh Token with `activity:read_all` and `profile:read_all` scopes (also `activity:write` if using `UPDATE_STRAVA_*`) | ✅ |

### Database (PostgreSQL Default)
| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_TYPE` | `postgresql`, `mysql`, or `firebird` | `postgresql` |
| `POSTGRESQL_HOST` | Hostname of the PostgreSQL server | - |
| `POSTGRESQL_PORT` | PostgreSQL port | `5432` |
| `POSTGRESQL_USER` | Database username | `postgres` |
| `POSTGRESQL_PASSWORD` | Database password | `postgres` |
| `POSTGRESQL_DATABASE` | Database name | `kinetiqo` |
| `POSTGRESQL_SSL_MODE` | PostgreSQL SSL mode (`disable`, `require`, `verify-full`, etc.) | `disable` |

For MySQL/MariaDB, use `MYSQL_HOST`, `MYSQL_PORT` (default `3306`), `MYSQL_USER`,
`MYSQL_PASSWORD`, `MYSQL_DATABASE`, and `MYSQL_SSL_MODE` (default `disable`).
For Firebird, use `FIREBIRD_HOST`, `FIREBIRD_PORT` (default `3050`),
`FIREBIRD_USER`, `FIREBIRD_PASSWORD`, and `FIREBIRD_DATABASE`.

### Scheduling
| Variable | Description | Example |
|----------|-------------|---------|
| `FULL_SYNC` | Cron schedule for a full sync | `0 3 * * *` (Daily at 3 AM) |
| `FAST_SYNC` | Cron schedule for a fast sync | `*/15 * * * *` (Every 15 mins) |

### Web UI & Security
| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_LOGIN` | Username for the web interface | `admin` |
| `WEB_PASSWORD` | Password for the web interface | `admin123` |
| `SECRET_KEY` | Secret key used by Flask for signing session cookies and CSRF tokens | Auto-generated in dev; required in prod |
| `KINETIQO_PRODUCTION` | Set to `1` in production to enforce persistent `SECRET_KEY` | _(empty)_ |

### Athlete and display settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ATHLETE_WEIGHT` | Athlete body weight in kilograms, used by VO2max calculations | `0` |
| `DATE_FORMAT` | Python `strftime` format used by charts and statistics | `%b %d, %Y` |

### Strava description updates

| Variable | Description | Default |
|----------|-------------|---------|
| `UPDATE_STRAVA_CYCLING_INDOOR` | Template for indoor cycling activities | _(empty — disabled)_ |
| `UPDATE_STRAVA_CYCLING_OUTDOOR` | Template for outdoor cycling activities | _(empty — disabled)_ |
| `UPDATE_STRAVA_RUNNING_INDOOR` | Template for indoor running activities | _(empty — disabled)_ |
| `UPDATE_STRAVA_RUNNING_OUTDOOR` | Template for outdoor running activities | _(empty — disabled)_ |
| `UPDATE_STRAVA_WALKING` | Template for walks and hikes | _(empty — disabled)_ |
| `UPDATE_STRAVA_SWIMMING` | Template for swimming activities | _(empty — disabled)_ |
| `UPDATE_STRAVA_PLACEMENT` | Insert the generated block at `begin` or `end` | `end` |
| `WORKOUT_SUMMARY_PEAK_THRESHOLD_W` | Watt floor for sustained peak highlights in `{{workout-summary}}` | `300` |

Description updates require Strava's `activity:write` OAuth scope. Updates are capped
at 30 eligible activities per sync.

### Logging
| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Log level for CLI, web server, and Gunicorn (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

### Map Configuration & Optimization
| Variable | Description | Default |
|----------|-------------|---------|
| `GPS_SIMPLIFICATION` | Coordinate decimation level (0-10, where 0=disabled, 1-10=3m-100m thresholds) | `0` |
| `MAPY_API_KEY` | API key for Mapy.cz tile layers | _(empty)_ |
| `THUNDERFOREST_API_KEY` | API key for Thunderforest tile layers | _(empty)_ |
| `MAPTILER_API_KEY` | API key for MapTiler tile layers | _(empty)_ |
| `GEOAPIFY_API_KEY` | API key for Geoapify tile layers | _(empty)_ |
| `CARTO_API_KEY` | API key for CARTO basemaps (Positron / Dark) | _(empty)_ |

### Browser export

| Variable | Description | Default |
|----------|-------------|---------|
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` | Optional path to a system Chromium executable used for poster and MEGA Stats PNG/PDF export | Auto-detected |

## Model Context Protocol (MCP) Server

Kinetiqo provides native Model Context Protocol (MCP) integration, enabling AI assistants (such as Claude Desktop, Cursor, Antigravity, and OpenClaw) to securely query your private fitness database over Server-Sent Events (SSE) or STDIO.

### Available Docker Images

Kinetiqo builds two official Docker image variants:

| Image Variant | Docker Tag | Default Ports | Included Services |
|---|---|---|---|
| **Standalone** (Original) | `kinetiqo/web:latest` | `4444` | • Web UI (`0.0.0.0:4444`)<br>• Background Cron Sync Daemon<br>• MCP disabled by default (`ENABLE_MCP=0`) |
| **Kinetiqo + MCP** | `kinetiqo/web-mcp:latest` | `4444`, `8000` | • Web UI (`0.0.0.0:4444`)<br>• Background Cron Sync Daemon<br>• **FastMCP SSE Server** (`0.0.0.0:8000/sse`) running concurrently |

*(Note: Both images are full-featured with system Chromium, Playwright, and Firebird client pre-installed, supporting all 35 MCP tools including Group E visual poster and infographic exports).*

### MCP Configuration Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_MCP` | Enable the background MCP server concurrently alongside Web UI and Cron (`1`/`0`, `true`/`false`) | `0` in `web`, `1` in `web-mcp` |
| `MCP_PORT` | Port for the MCP SSE server | `8000` |
| `MCP_HOST` | Host IP binding for the MCP server | `0.0.0.0` |
| `MCP_TRANSPORT` | Transport protocol (`sse` or `stdio`) | `sse` |
| `KINETIQO_MCP_ALLOW_SYNC` | Gated permission for AI to trigger background syncs (`1`/`0`) | `0` (disabled) |
| `KINETIQO_MCP_ALLOW_PROFILE_WRITE` | Gated permission for AI to edit athlete profile & goals (`1`/`0`) | `0` (disabled) |
| `KINETIQO_MCP_ALLOW_STRAVA_WRITE` | Gated permission for AI to publish descriptions to Strava (`1`/`0`) | `0` (disabled) |

### Docker Run Example (Web UI + MCP SSE in Parallel)

```bash
docker run -d \
  --name kinetiqo \
  -p 4444:4444 \
  -p 8000:8000 \
  -e ENABLE_MCP=1 \
  -e MCP_PORT=8000 \
  -e DATABASE_TYPE="postgresql" \
  -e POSTGRESQL_HOST="postgresql" \
  -e POSTGRESQL_PORT="5432" \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="password" \
  -e POSTGRESQL_DATABASE="kinetiqo" \
  -e SECRET_KEY="replace_with_hex_32" \
  kinetiqo/web-mcp:latest
```

- Web UI: **http://localhost:4444**
- AI MCP Endpoint: **http://localhost:8000/sse**

### Docker Compose Example

```yaml
services:
  kinetiqo:
    image: kinetiqo/web-mcp:latest
    container_name: kinetiqo
    ports:
      - "4444:4444"   # Web UI
      - "8000:8000"   # FastMCP SSE
    environment:
      - ENABLE_MCP=1
      - MCP_PORT=8000
      - MCP_HOST=0.0.0.0
      - MCP_TRANSPORT=sse
      - DATABASE_TYPE=postgresql
      - POSTGRESQL_HOST=db
      - POSTGRESQL_PORT=5432
      - POSTGRESQL_USER=postgres
      - POSTGRESQL_PASSWORD=secret
      - POSTGRESQL_DATABASE=kinetiqo
      - SECRET_KEY=your_persistent_secret_key
    restart: unless-stopped
```

### Claude Desktop Configuration (Connecting to Running Container)

Because the container exposes FastMCP over SSE, you don't need Claude Desktop to run Docker commands; simply point Claude Desktop to the running container's SSE URL:

```json
{
  "mcpServers": {
    "kinetiqo": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

## Building Images from Source (`build.sh`)

All Docker builds are managed through the single unified script `build/build.sh`. Specifying a target (`base`, `web`, `mcp`, or `all`) is **mandatory**:

```bash
# Compile Firebird 5.x C client & Python 3.14 base image
./build/build.sh base

# Build the standalone web application image (kinetiqo/web)
./build/build.sh web

# Build the web + FastMCP SSE server image (kinetiqo/web-mcp)
./build/build.sh mcp

# Build all three images in dependency order (base -> web -> mcp)
./build/build.sh all
```

### Options & Publishing

Add `--push` to authenticate and publish multi-architecture (`linux/amd64,linux/arm64`) images to Docker Hub:

```bash
# Push standalone web image to Docker Hub
./build/build.sh web --push

# Push all images using explicit credentials
./build/build.sh all --push -u kinetiqo -t your_dockerhub_token

# Simulate execution without building
./build/build.sh all --dry-run
```

| Target | Local Build (default) | Build & Push (`--push`) |
|---|---|---|
| `./build.sh base` | Builds base image for `linux/amd64`, loads locally | Authenticates via `docker login`, builds multi-arch (`linux/amd64,linux/arm64`), pushes `kinetiqo/firebird-python:3.14` |
| `./build.sh web` | Builds standalone web image for `linux/amd64`, loads locally | Authenticates via `docker login`, builds multi-arch (`linux/amd64,linux/arm64`), pushes `kinetiqo/web:latest` |
| `./build.sh mcp` | Builds web + MCP image for `linux/amd64`, loads locally | Authenticates via `docker login`, builds multi-arch (`linux/amd64,linux/arm64`), pushes `kinetiqo/web-mcp:latest` |
| `./build.sh all` | Builds `base`, then `web`, then `mcp` locally | Authenticates and builds all three multi-arch images in sequence and pushes to Docker Hub |

## Links

- **Source Code**: [GitHub](https://github.com/lhotakj/kinetiqo)
- **Issues**: [Bug Tracker](https://github.com/lhotakj/kinetiqo/issues)
- **MCP Documentation**: [docs/MCP.md](docs/MCP.md)
