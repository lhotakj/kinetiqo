# Kinetiqo

Kinetiqo liberates your Strava activities, syncing them into a high-performance SQL database (**PostgreSQL** or **MySQL/MariaDB**) for ultimate control.

Visualize your progress with our **built-in Web UI** or dive deep with the included **Grafana dashboards**. Whether you're a data nerd or just want to see your stats without limits, Kinetiqo is your personal fitness data warehouse.

## Features

- 📊 **Rich Visualization**: Includes a sleek Web UI for quick access and powerful Grafana dashboards for deep analysis.
- 🔄 **Smart Sync**:
  - **Full Sync**: Complete library audit—fetches everything, fills gaps, and prunes deleted activities.
  - **Fast Sync**: Lightning-fast updates for your latest workouts.
- 🐳 **Docker Native**: Drop it into your stack and forget it.
- ⏱️ **Set & Forget**: Built-in cron scheduler keeps your data fresh automatically.
- 💾 **Database Agnostic**:
  - **PostgreSQL** (version 18+)
  - **MySQL 8 / MariaDB 12**
- 🚀 **Optimized**: Intelligent caching minimizes API usage and maximizes speed.
- 🔒 **Secure**: OAuth 2.0 authentication keeps your Strava account safe.

## Quick Start

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
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  lhotakj/kinetiqo:latest
```
Your web will appears under http://localhost:4444

### Docker Compose

For a complete stack including PostgreSQL and Grafana, check out the [GitHub Repository](https://github.com/lhotakj/kinetiqo).

## Configuration

Kinetiqo is configured entirely via environment variables.

### Strava API
| Variable | Description | Required |
|----------|-------------|----------|
| `STRAVA_CLIENT_ID` | Your Strava Application Client ID | ✅ |
| `STRAVA_CLIENT_SECRET` | Your Strava Application Client Secret | ✅ |
| `STRAVA_REFRESH_TOKEN` | A valid Refresh Token with `activity:read_all` scope | ✅ |

### Database (PostgreSQL Default)
| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_TYPE` | `postgresql` or `mysql` | `postgresql` |
| `POSTGRESQL_HOST` | Hostname of the PostgreSQL server | - |
| `POSTGRESQL_PORT` | PostgreSQL port | `5432` |
| `POSTGRESQL_USER` | Database username | `postgres` |
| `POSTGRESQL_PASSWORD` | Database password | `postgres` |
| `POSTGRESQL_DATABASE` | Database name | `kinetiqo` |

### Scheduling
| Variable | Description | Example |
|----------|-------------|---------|
| `FULL_SYNC` | Cron schedule for a full sync | `0 3 * * *` (Daily at 3 AM) |
| `FAST_SYNC` | Cron schedule for a fast sync | `*/15 * * * *` (Every 15 mins) |

### Web UI
| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_LOGIN` | Username for the web interface | `admin` |
| `WEB_PASSWORD` | Password for the web interface | `admin123` |

## Links

- **Source Code**: [GitHub](https://github.com/lhotakj/kinetiqo)
- **Issues**: [Bug Tracker](https://github.com/lhotakj/kinetiqo/issues)
