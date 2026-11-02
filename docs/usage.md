# Kinetiqo Usage & Deployment Guide

This guide covers running Kinetiqo in production and development across **Docker**, **Docker Compose**, and **Native Python**, including complete environment variable configurations, cron sync automation, and production reverse proxy setups.

---

## 1. Prerequisites

- **Strava Developer Application**: Required to obtain API credentials ([Strava Developers](https://www.strava.com/settings/api)).
- **Relational Database**: Running instance of **PostgreSQL** (12+), **MySQL** (8.0+) / **MariaDB** (10+), or **Firebird** (3.0–5.0).
- **Environment**:
  - Docker 24+ and Docker Compose v2+ (recommended for containers), OR
  - Python 3.14+ (for local native execution)

---

## 2. Docker Deployment

Kinetiqo provides official, multi-architecture Docker images on Docker Hub:
- `kinetiqo/web:latest`: Standalone Web application with built-in cron scheduler.
- `kinetiqo/mcp:latest`: Integrated Web application, cron scheduler, and FastMCP Server (STDIO & SSE).

### 2.1 Docker Run (Standalone)

Run Kinetiqo connected to an existing PostgreSQL database:

```bash
docker run -d \
  --name kinetiqo \
  -p 4444:4444 \
  -e STRAVA_CLIENT_ID="your_client_id" \
  -e STRAVA_CLIENT_SECRET="your_client_secret" \
  -e STRAVA_REFRESH_TOKEN="your_refresh_token" \
  -e STRAVA_ATHLETE_ID="your_athlete_id" \
  -e SECRET_KEY="generate_a_random_32_char_secret_key" \
  -e WEB_PASSWORD="your_secure_web_login_password" \
  -e DATABASE_TYPE="postgresql" \
  -e DB_HOST="10.0.0.10" \
  -e DB_PORT="5432" \
  -e DB_NAME="kinetiqo" \
  -e DB_USER="kinetiqo_user" \
  -e DB_PASSWORD="your_db_password" \
  -e CRON_SYNC_SCHEDULE="0 3 * * *" \
  -e CRON_FAST_SYNC_SCHEDULE="*/15 * * * *" \
  -e KINETIQO_PRODUCTION=1 \
  --restart unless-stopped \
  kinetiqo/web:latest
```

### 2.2 Docker Run (Integrated with FastMCP Server)

Exposes the Web UI on port 4444 and FastMCP SSE on port 8000:

```bash
docker run -d \
  --name kinetiqo-mcp \
  -p 4444:4444 \
  -p 8000:8000 \
  -e STRAVA_CLIENT_ID="your_client_id" \
  -e STRAVA_CLIENT_SECRET="your_client_secret" \
  -e STRAVA_REFRESH_TOKEN="your_refresh_token" \
  -e STRAVA_ATHLETE_ID="your_athlete_id" \
  -e SECRET_KEY="generate_a_random_32_char_secret_key" \
  -e WEB_PASSWORD="your_secure_web_login_password" \
  -e DATABASE_TYPE="postgresql" \
  -e DB_HOST="10.0.0.10" \
  -e DB_PORT="5432" \
  -e DB_NAME="kinetiqo" \
  -e DB_USER="kinetiqo_user" \
  -e DB_PASSWORD="your_db_password" \
  -e MCP_TRANSPORT="sse" \
  -e MCP_SSE_HOST="0.0.0.0" \
  -e MCP_SSE_PORT="8000" \
  -e KINETIQO_PRODUCTION=1 \
  --restart unless-stopped \
  kinetiqo/mcp:latest
```

---

## 3. Docker Compose Deployment

Docker Compose is the recommended deployment method for managing Kinetiqo alongside a dedicated database.

### 3.1 Docker Compose with PostgreSQL (Recommended)

Create `docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16-alpine
    container_name: kinetiqo-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: kinetiqo
      POSTGRES_USER: kinetiqo
      POSTGRES_PASSWORD: ChangeThisDatabasePassword123!
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kinetiqo -d kinetiqo"]
      interval: 10s
      timeout: 5s
      retries: 5

  web:
    image: kinetiqo/web:latest
    container_name: kinetiqo-web
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "4444:4444"
    env_file:
      - .env
    volumes:
      - app_data:/app/data

volumes:
  pgdata:
  app_data:
```

### 3.2 Docker Compose with MySQL 8

```yaml
services:
  db:
    image: mysql:8.0
    container_name: kinetiqo-mysql
    restart: unless-stopped
    command: --default-authentication-plugin=mysql_native_password
    environment:
      MYSQL_DATABASE: kinetiqo
      MYSQL_USER: kinetiqo
      MYSQL_PASSWORD: ChangeThisDatabasePassword123!
      MYSQL_ROOT_PASSWORD: ChangeThisRootPassword123!
    volumes:
      - mysqldata:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  web:
    image: kinetiqo/web:latest
    container_name: kinetiqo-web
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "4444:4444"
    env_file:
      - .env
    volumes:
      - app_data:/app/data

volumes:
  mysqldata:
  app_data:
```

---

## 4. Native Python Direct Run (Development & Bare Metal)

### 4.1 Setup Virtual Environment

```bash
# Clone the repository
git clone https://github.com/lhotakj/kinetiqo.git
cd kinetiqo

# Create virtual environment (Python 3.14+)
python -m venv .venv

# Activate virtual environment
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browser dependencies (for PNG/PDF poster & infographic exports)
playwright install chromium-headless-shell
```

### 4.2 Initialize Environment File

Copy the template and configure your parameters:

```bash
cp .env.example .env
```

### 4.3 Running Web Server & CLI

```bash
# Start Flask web server on default port (4444)
python src/kinetiqo.py web

# Start web server on custom port and host
python src/kinetiqo.py web --host 0.0.0.0 --port 5000

# Run incremental fast sync from terminal
python src/kinetiqo.py sync --fast

# Run full historical sync audit
python src/kinetiqo.py sync

# Run database performance benchmark
python src/kinetiqo.py benchmark --scope 365
```

---

## 5. Complete Environment Variables Reference (`.env`)

### 5.1 Strava API Credentials

| Variable | Required | Description |
|---|---|---|
| `STRAVA_CLIENT_ID` | Yes | Numeric client ID from your Strava API Application settings |
| `STRAVA_CLIENT_SECRET` | Yes | Client secret from your Strava API Application settings |
| `STRAVA_REFRESH_TOKEN` | Yes | OAuth refresh token with `read,activity:read_all` (or `activity:write` for description auto-updates) |
| `STRAVA_ATHLETE_ID` | Yes | Numeric Strava athlete ID |

### 5.2 Web Security & Sessions

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-secret-key-...` | Persistent cryptographic secret key used for session cookie signing and CSRF tokens |
| `WEB_PASSWORD` | `""` | Password for web login. If empty or unset, web authentication is disabled (local network trust mode) |
| `KINETIQO_PRODUCTION` | `0` | Set to `1` in production to enforce strict security settings (secure cookies, production CSRF enforcement) |
| `PORT` | `4444` | Default HTTP server listening port |

### 5.3 Database Configuration

| Variable | Default | Options / Notes |
|---|---|---|
| `DATABASE_TYPE` | `postgresql` | `postgresql`, `mysql`, `firebird` |
| `DB_HOST` | `localhost` | Hostname or IP of database server |
| `DB_PORT` | `5432` | `5432` (PostgreSQL), `3306` (MySQL), `3050` (Firebird) |
| `DB_NAME` | `kinetiqo` | Database name |
| `DB_USER` | `kinetiqo` | Database username |
| `DB_PASSWORD` | `""` | Database password |
| `FIREBIRD_PATH` | `""` | Local file path for Firebird embedded/server database file (e.g. `/var/lib/firebird/kinetiqo.fdb`) |

### 5.4 Automated Cron Synchronization

| Variable | Default | Description |
|---|---|---|
| `CRON_FAST_SYNC_SCHEDULE` | `*/15 * * * *` | Cron expression for incremental fast sync (checks newest 30 activities every 15 min) |
| `CRON_SYNC_SCHEDULE` | `0 3 * * *` | Cron expression for full historical audit sync (runs daily at 03:00 UTC) |

### 5.5 Basemap API Keys (Optional)

| Variable | Free Tier Link | Description |
|---|---|---|
| `MAPTILER_API_KEY` | [maptiler.com](https://cloud.maptiler.com/) | Unlocks MapTiler Outdoor, Streets, Topo, and Satellite tiles |
| `THUNDERFOREST_API_KEY` | [thunderforest.com](https://www.thunderforest.com/) | Unlocks OpenCycleMap, Outdoors, and Landscape tiles |
| `GEOAPIFY_API_KEY` | [geoapify.com](https://www.geoapify.com/) | Unlocks Geoapify OSM Bright, Dark, and Toner tiles |

*OpenStreetMap, Mapy.cz, CARTO Positron/Dark, and Esri World Imagery work out of the box with zero API keys required.*

### 5.6 Historical Activity Weather (Optional)

| Variable | Free Tier Link | Free Quota | Description |
|---|---|---|---|
| `VISUAL_CROSSING_API_KEY` | [visualcrossing.com/weather-api](https://www.visualcrossing.com/weather-api) | 1,000 records / day | Visual Crossing Timeline API key. When present, outdoor GPS workouts are automatically enriched with hourly historical weather and route-relative headwind calculations. |

* **Get a Free API Key**: Register at [visualcrossing.com/weather-api](https://www.visualcrossing.com/weather-api). No credit card required.
* **Daily Quota**: The free plan provides **1,000 weather records per day** (resets every day at 00:00 UTC). Additional records are metered at $0.0001 per record ($1 per 10,000 records).
* **Smart Caching**: Kinetiqo caches weather records within a **15 km radius** and stores hourly records in the database, meaning multiple activities in the same area share cached data with zero redundant API calls.
* **Rate-Limit Safe**: When Visual Crossing reports no remaining quota (`X-RateLimit-Remaining: 0` or HTTP 429), weather queries halt automatically across all workers until the next UTC midnight while activity sync proceeds normally.
* **Graceful Degradation**: When omitted or blank, weather sync options in the UI ("Fetch weather data" and "Resync weather") are automatically disabled with an informative red warning tooltip, preventing accidental network attempts.

### 5.7 FastMCP Server & Mutation Controls

| Variable | Default | Description |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `http` |
| `MCP_SSE_HOST` | `0.0.0.0` | Binding host for FastMCP SSE server |
| `MCP_SSE_PORT` | `8000` | Port for FastMCP SSE server (`http://<host>:8000/sse`) |
| `KINETIQO_MCP_ALLOW_SYNC` | `0` | Set `1` to allow AI agents to trigger activity synchronization |
| `KINETIQO_MCP_ALLOW_PROFILE_WRITE` | `0` | Set `1` to allow AI agents to modify athlete FTP and profile metrics |
| `KINETIQO_MCP_ALLOW_STRAVA_WRITE` | `0` | Set `1` to allow AI agents to publish updated descriptions to Strava |

### 5.8 In-App AI Chat Multi-Provider Keys

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key for Google Gemini models (`gemini-2.5-flash`, `gemini-2.5-pro`) |
| `OPENROUTER_API_KEY` | OpenRouter API key for OpenAI, Anthropic Claude, Meta Llama, and DeepSeek models |

### 5.9 Athlete Telemetry & Display Defaults

| Variable | Default | Description |
|---|---|---|
| `ATHLETE_WEIGHT_KG` | `75.0` | Default body weight in kg (used for W/kg calculations) |
| `ATHLETE_FTP` | `250` | Functional Threshold Power in Watts (used for Coggan zones and NP% FTP) |
| `GPS_SIMPLIFICATION` | `3` | Track simplification level (1–10). Level 3 achieves ~15× payload reduction with zero visual distortion |

---

## 6. Reverse Proxy & Production Hardening

When deploying Kinetiqo publicly, place it behind a reverse proxy (such as Nginx or Caddy) to handle HTTPS/TLS termination and WebSocket/SSE streaming.

### 6.1 Nginx Configuration Example

```nginx
server {
    listen 80;
    server_name kinetiqo.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name kinetiqo.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/kinetiqo.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kinetiqo.yourdomain.com/privkey.pem;

    client_max_body_size 25M;

    # Web Dashboard & API
    location / {
        proxy_pass http://127.0.0.1:4444;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Disable buffering for SSE sync progress
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }

    # Optional: FastMCP SSE Server (when using kinetiqo/mcp image)
    location /sse {
        proxy_pass http://127.0.0.1:8000/sse;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```

### 6.2 Caddy Configuration Example

```caddy
kinetiqo.yourdomain.com {
    reverse_proxy 127.0.0.1:4444 {
        # Streaming support for SSE
        flush_interval -1
    }
}
```

