# Kinetiqo

Kinetiqo is a robust, containerized tool designed to synchronize your Strava activities with a time-series database. It supports both **PostgreSQL** and **InfluxDB 2.x** as backends, allowing you to visualize and analyze your fitness data with tools like Grafana.

## Features

- 🔄 **Two Sync Modes**:
  - **Full Sync**: Fetches all activities, downloads missing ones, and removes deleted activities from the database.
  - **Fast Sync**: Fetches only new activities since the last sync for quick updates.
- 🐳 **Dockerized**: Ready to deploy anywhere with Docker.
- ⏱️ **Scheduled Execution**: Built-in cron support for automated syncing.
- 💾 **Database Support**:
  - **PostgreSQL** (version 18 or compatible)
  - **InfluxDB 2.x**
- 🚀 **Performance**: Efficient caching to minimize Strava API calls.
- 🔒 **Secure**: Uses OAuth 2.0 for Strava authentication.

---

## Configuration

Kinetiqo is configured entirely via environment variables.

### 1. Strava API Configuration
You need to register an application on [Strava settings](https://www.strava.com/settings/api) to get these credentials.

| Variable | Description | Required |
|----------|-------------|----------|
| `STRAVA_CLIENT_ID` | Your Strava Application Client ID | ✅ |
| `STRAVA_CLIENT_SECRET` | Your Strava Application Client Secret | ✅ |
| `STRAVA_REFRESH_TOKEN` | A valid Refresh Token with `activity:read_all` scope | ✅ |

### 2. Database Configuration

Set `DATABASE_TYPE` to either `postgresql` (default) or `influxdb2`.

#### PostgreSQL (Default)
| Variable | Description | Default    |
|----------|-------------|------------|
| `POSTGRESQL_HOST` | Hostname of the PostgreSQL server | -          |
| `POSTGRESQL_PORT` | PostgreSQL port | `5432`     |
| `POSTGRESQL_USER` | Database username | `postgres` |
| `POSTGRESQL_PASSWORD` | Database password | `postgres` |
| `POSTGRESQL_DATABASE` | Database name | `kinetiqo` |
| `POSTGRESQL_SSL_MODE` | SSL mode for the connection. Can be `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`. | `disable`  |

#### InfluxDB 2.x
| Variable | Description | Default |
|----------|-------------|---------|
| `INFLUX_URL` | Full URL to InfluxDB (e.g., `http://influxdb:8086`) | - |
| `INFLUX_TOKEN` | API Token with write access to the bucket | - |
| `INFLUX_ORG` | Organization name | - |
| `INFLUX_BUCKET` | Bucket name | - |
| `INFLUX_VERIFY_SSL` | Verify SSL certificates (`True`/`False`) | `True` |

### 3. Scheduling (Cron)
The container has a built-in cron scheduler. You can define schedules using standard cron syntax (e.g., `0 * * * *` for hourly).

| Variable | Description | Example |
|----------|-------------|---------|
| `FULL_SYNC` | Cron schedule for a full sync | `0 3 * * *` (Daily at 3 AM) |
| `FAST_SYNC` | Cron schedule for a fast sync | `*/15 * * * *` (Every 15 mins) |

### 4. Web Interface Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_LOGIN` | Username for the web interface | `admin` |
| `WEB_PASSWORD` | Password for the web interface | `admin123` |

> **Note:** If the sync script fails, the container is designed to crash (exit code 1) to allow your orchestrator (Docker/K8s) to restart it.

---

## Deployment

### Docker Run

```bash
docker run -d \
  --name kinetiqo \
  -e STRAVA_CLIENT_ID="your_id" \
  -e STRAVA_CLIENT_SECRET="your_secret" \
  -e STRAVA_REFRESH_TOKEN="your_token" \
  -e DATABASE_TYPE="postgresql" \
  -e POSTGRESQL_HOST="postgresql" \
  -e POSTGRESQL_PORT="5432" \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="password" \
  -e POSTGRESQL_DATABASE="kinetiqo" \
  -e POSTGRESQL_SSL_MODE="disable" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword" \
  kinetiqo:latest
```

### Docker Compose

Here is a complete example stack with PostgreSQL and Grafana.

`docker-compose.yml`:

```yaml
version: '3.8'

services:
  kinetiqo:
    image: kinetiqo:latest
    container_name: kinetiqo
    restart: always
    environment:
      - STRAVA_CLIENT_ID=${STRAVA_CLIENT_ID}
      - STRAVA_CLIENT_SECRET=${STRAVA_CLIENT_SECRET}
      - STRAVA_REFRESH_TOKEN=${STRAVA_REFRESH_TOKEN}
      - DATABASE_TYPE=postgresql
      - POSTGRESQL_HOST=postgresql
      - POSTGRESQL_PORT=5432
      - POSTGRESQL_USER=postgres
      - POSTGRESQL_PASSWORD=password
      - POSTGRESQL_DATABASE=kinetiqo
      - POSTGRESQL_SSL_MODE=disable
      - FAST_SYNC=*/15 * * * *  # Every 15 minutes
      - FULL_SYNC=0 3 * * *     # Daily at 3 AM
      - WEB_LOGIN=admin
      - WEB_PASSWORD=admin123
    depends_on:
      - postgresql

  postgresql:
    image: postgres:18
    container_name: postgresql
    restart: always
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=kinetiqo
    volumes:
      - postgresql_data:/var/lib/postgresql/data

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: always
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - postgresql

volumes:
  postgresql_data:
```

Create a `.env` file alongside it:

```env
STRAVA_CLIENT_ID=12345
STRAVA_CLIENT_SECRET=your_secret_here
STRAVA_REFRESH_TOKEN=your_refresh_token_here
```

Then run:
```bash
docker-compose up -d
```

---

## Manual Usage (CLI)

You can also run the python script directly if you have the environment set up.

```bash
# Show help
python kinetiqo.py --help

# Show version
python kinetiqo.py version

# Run a full sync
python kinetiqo.py sync --full-sync

# Run a fast sync with caching enabled
python kinetiqo.py sync --fast-sync --enable-strava-cache

# Check database availability
python kinetiqo.py flightcheck

# Start the web interface
python kinetiqo.py web --port 8000
```

### CLI Commands

*   `sync`: Synchronize activities with database.
    *   `--full-sync` / `-f`: Perform a full sync.
    *   `--fast-sync` / `-q`: Perform a fast sync.
    *   `--enable-strava-cache`: Enable caching of Strava API responses.
    *   `--cache-ttl`: Cache time-to-live in minutes.
    *   `--clear-cache`: Clear the cache before syncing.
*   `web`: Start the web interface.
    *   `--port`: Port to run the web server on (default: 4444).
    *   `--host`: Host to bind to (default: 0.0.0.0).
*   `flightcheck`: Check database availability and schema.
*   `version`: Show the version and exit.

## License

See [LICENSE](LICENSE) file for details.
