---
layout: default
title: Configuration
nav_order: 3
---

# Configuration

Kinetiqo is configured entirely through environment variables. All configuration options—including database, Strava API, scheduling, display, and map providers—are set via environment variables or a `.env` file.

## 1. Strava API Credentials

Register an application in the [Strava API Settings](https://www.strava.com/settings/api) to obtain the necessary credentials.

| Variable                | Description                                              | Required |
|-------------------------|----------------------------------------------------------|----------|
| `STRAVA_CLIENT_ID`      | Strava Application Client ID.                            | ✅        |
| `STRAVA_CLIENT_SECRET`  | Strava Application Client Secret.                        | ✅        |
| `STRAVA_REFRESH_TOKEN`  | Valid Refresh Token with `activity:read_all` scope.      | ✅        |

## 2. Database Configuration

Set `DATABASE_TYPE` to `postgresql`, `mysql`, or `firebird`.

### PostgreSQL (Default)
| Variable                | Description                        | Default    |
|-------------------------|------------------------------------|------------|
| `POSTGRESQL_HOST`       | Database server hostname.           | Required   |
| `POSTGRESQL_PORT`       | Database server port.               | `5432`     |
| `POSTGRESQL_USER`       | Database username.                  | Required   |
| `POSTGRESQL_PASSWORD`   | Database password.                  | Required   |
| `POSTGRESQL_DATABASE`   | Database name.                      | Required   |
| `POSTGRESQL_SSL_MODE`   | SSL connection mode.                | `disable`  |

### MySQL / MariaDB
| Variable                | Description                        | Default    |
|-------------------------|------------------------------------|------------|
| `MYSQL_HOST`            | Database server hostname.           | Required   |
| `MYSQL_PORT`            | Database server port.               | `3306`     |
| `MYSQL_USER`            | Database username.                  | Required   |
| `MYSQL_PASSWORD`        | Database password.                  | Required   |
| `MYSQL_DATABASE`        | Database name.                      | Required   |
| `MYSQL_SSL_MODE`        | SSL connection mode.                | `disable`  |

> **Note:** For MySQL, ensure the user has `CREATE` and `ALL PRIVILEGES` on the target database to allow for schema management.

### Firebird
| Variable                | Description                        | Default    |
|-------------------------|------------------------------------|------------|
| `FIREBIRD_HOST`         | Database server hostname.           | Required   |
| `FIREBIRD_PORT`         | Database server port.               | `3050`     |
| `FIREBIRD_USER`         | Database username.                  | Required   |
| `FIREBIRD_PASSWORD`     | Database password.                  | Required   |
| `FIREBIRD_DATABASE`     | Database file path or alias.        | Required   |

> **Note:** Kinetiqo will automatically create the Firebird database and schema if they don't exist.
> **Version Compatibility:** Firebird 3.0, 4.0, 5.0 supported. Uses only standard SQL features.
> **Permissions Required:**
> - User must have rights to create databases, tables, sequences, triggers, and indexes.
> - For embedded Firebird, ensure write access to the database file directory.

## 3. Scheduling (Cron)

The Docker image includes a built-in cron scheduler powered by `dcron`. Define schedules using standard cron syntax.

| Variable      | Description                        | Example                |
|---------------|------------------------------------|------------------------|
| `FULL_SYNC`   | Schedule for full synchronization. | `0 3 * * *` (Daily 3AM)|
| `FAST_SYNC`   | Schedule for incremental sync.     | `*/15 * * * *`         |

Both accept standard 5-field cron expressions. See [Deployment](deployment.md) for more details.

## 4. Web Interface Configuration
| Variable        | Description                | Default     |
|-----------------|---------------------------|-------------|
| `WEB_LOGIN`     | Username for web access.   | `admin`     |
| `WEB_PASSWORD`  | Password for web access.   | `admin123`  |

## 5. Athlete & Display Configuration
| Variable           | Description                                      | Default         |
|--------------------|--------------------------------------------------|-----------------|
| `ATHLETE_WEIGHT`   | Athlete body weight in kg (fallback only)        | `0` (not set)   |
| `DATE_FORMAT`      | Date format string (Python `strftime` syntax)    | `%b %d, %Y`     |

## 6. Map Configuration

Kinetiqo supports multiple map tile providers. Some require API keys:

| Variable                 | Description                                 | Default     |
|--------------------------|---------------------------------------------|-------------|
| `MAPY_API_KEY`           | API key for Mapy.cz tile layers             | _(empty)_   |
| `THUNDERFOREST_API_KEY`  | API key for Thunderforest tile layers       | _(empty)_   |

> Layers requiring a missing API key appear greyed-out in the map selector.

### How to Get Map API Keys

#### Mapy.cz (Seznam.cz)
- Free for non-commercial/personal use (up to 250,000 credits/month)
- 1. Go to [developer.mapy.com](https://developer.mapy.com)
- 2. Register or sign in with a Seznam account
- 3. Create a new project
- 4. Copy the API key
- 5. Set `MAPY_API_KEY` in your environment

#### Thunderforest
- Free for hobby/personal projects (up to 150,000 tiles/month)
- 1. Go to [manage.thunderforest.com/signup](https://manage.thunderforest.com/signup)
- 2. Register for a free "Hobby Project" account
- 3. Copy the API key from the dashboard
- 4. Set `THUNDERFOREST_API_KEY` in your environment

> If an API key is missing, the corresponding map layers will be disabled (greyed-out) in the web UI with a hint.

For more, see [Web Interface](web.md#map-tile-proxy--api-keys).

## 7. Advanced & Notes
- All configuration is via environment variables or a `.env` file (see [Local Development](local-dev.md)).
- For secure secret storage, see [Direnv setup](direnv-setup.md).
- Synchronization errors are recorded in the `logs` database table and are accessible via the Web UI or `docker logs`.
- For full details on all options, see the [README](https://github.com/lhotakj/kinetiqo#configuration).
