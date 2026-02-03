# Kinetiqo

Kinetiqo is a robust, containerized tool designed to synchronize your Strava activities with a time-series database. It supports both **QuestDB** and **InfluxDB 2.x** as backends, allowing you to visualize and analyze your fitness data with tools like Grafana.

## Features

- 🔄 **Two Sync Modes**:
  - **Full Sync**: Fetches all activities, downloads missing ones, and removes deleted activities from the database.
  - **Fast Sync**: Fetches only new activities since the last sync for quick updates.
- 🐳 **Dockerized**: Ready to deploy anywhere with Docker.
- ⏱️ **Scheduled Execution**: Built-in cron support for automated syncing.
- 💾 **Database Support**:
  - **QuestDB** (via PostgreSQL wire protocol)
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

Set `DATABASE_TYPE` to either `questdb` (default) or `influxdb2`.

#### QuestDB (Default)
| Variable | Description | Default |
|----------|-------------|---------|
| `QUESTDB_HOST` | Hostname of the QuestDB server | - |
| `QUESTDB_PORT` | PostgreSQL wire protocol port | `8812` |
| `QUESTDB_USER` | Database username | `admin` |
| `QUESTDB_PASSWORD` | Database password | `quest` |
| `QUESTDB_DATABASE` | Database name | `qdb` |

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
  -e DATABASE_TYPE="questdb" \
  -e QUESTDB_HOST="questdb" \
  -e QUESTDB_PORT="8812" \
  -e QUESTDB_USER="admin" \
  -e QUESTDB_PASSWORD="quest" \
  -e QUESTDB_DATABASE="qdb" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  kinetiqo:latest
```

### Docker Compose

Here is a complete example stack with QuestDB and Grafana.

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
      - DATABASE_TYPE=questdb
      - QUESTDB_HOST=questdb
      - QUESTDB_PORT=8812
      - QUESTDB_USER=admin
      - QUESTDB_PASSWORD=quest
      - QUESTDB_DATABASE=qdb
      - FAST_SYNC=*/15 * * * *  # Every 15 minutes
      - FULL_SYNC=0 3 * * *     # Daily at 3 AM
    depends_on:
      - questdb

  questdb:
    image: questdb/questdb:latest
    container_name: questdb
    restart: always
    ports:
      - "9000:9000"  # Web Console
      - "8812:8812"  # Postgres Wire Protocol
      - "9009:9009"  # InfluxDB Line Protocol
    environment:
      - QDB_PG_USER=admin
      - QDB_PG_PASSWORD=quest

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: always
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - questdb
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

# Run a full sync
python kinetiqo.py --full-sync

# Run a fast sync with caching enabled
python kinetiqo.py --fast-sync --enable-strava-cache
```

## License

See [LICENSE](LICENSE) file for details.
