# Kinetiqo

Kinetiqo liberates your Strava activities, syncing them into a high-performance SQL database (**PostgreSQL** or **MySQL/MariaDB**) for ultimate control.

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

### Docker Run

```bash
docker run -d \
  --name kinetiqo \
  -p 4444:4444 \
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
  -e SECRET_KEY="replace_with_output_from_openssl_rand_hex_32" \
  -e KINETIQO_PRODUCTION=1 \
  -e MAPY_API_KEY="your_mapy_com_api_token" \
  -e THUNDERFOREST_API_KEY="your_thunderforest_api_token" \
  -e MAPTILER_API_KEY="your_maptiler_api_token" \
  -e GEOAPIFY_API_KEY="your_geoapify_api_token" \
  -e CARTO_API_KEY="your_carto_api_key" \
  -e ATHLETE_WEIGHT="75" \
  -e DATE_FORMAT="%b %d, %Y" \
  -e UPDATE_STRAVA_CYCLING_INDOOR="" \
  -e UPDATE_STRAVA_CYCLING_OUTDOOR="" \
  -e UPDATE_STRAVA_RUNNING_INDOOR="" \
  -e UPDATE_STRAVA_RUNNING_OUTDOOR="" \
  -e UPDATE_STRAVA_WALKING="" \
  -e UPDATE_STRAVA_SWIMMING="" \
  -e UPDATE_STRAVA_PLACEMENT="end" \
  -e WORKOUT_SUMMARY_PEAK_THRESHOLD_W="300" \
  -e PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="" \
  -e GPS_SIMPLIFICATION="0" \
  -e LOG_LEVEL="INFO" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword13" \
  lhotakj/kinetiqo:latest
```
The web UI is available at http://localhost:4444.

### Docker Compose

For a complete stack including PostgreSQL and Grafana, check out the [GitHub Repository](https://github.com/lhotakj/kinetiqo).

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

`CARTO_API_KEY` is passed to CARTO tile URLs when configured. Provider layers that
require a missing key are disabled in the map selector.

## Links

- **Source Code**: [GitHub](https://github.com/lhotakj/kinetiqo)
- **Issues**: [Bug Tracker](https://github.com/lhotakj/kinetiqo/issues)
