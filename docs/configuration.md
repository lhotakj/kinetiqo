---
layout: default
title: Configuration
nav_order: 3
---

# Configuration

Kinetiqo is configured entirely through environment variables.

## 1. Strava API Credentials

Register an application in the [Strava API Settings](https://www.strava.com/settings/api) to obtain the necessary credentials.

| Variable | Description | Required |
|----------|-------------|----------|
| `STRAVA_CLIENT_ID` | Strava Application Client ID. | ✅ |
| `STRAVA_CLIENT_SECRET` | Strava Application Client Secret. | ✅ |
| `STRAVA_REFRESH_TOKEN` | Valid Refresh Token with `activity:read_all` scope. | ✅ |

## 2. Database Configuration

Define `DATABASE_TYPE` as either `postgresql` (default) or `mysql`.

### PostgreSQL (Default)

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRESQL_HOST` | Database server hostname. | `localhost` |
| `POSTGRESQL_PORT` | Database server port. | `5432` |
| `POSTGRESQL_USER` | Database username. | `postgres` |
| `POSTGRESQL_PASSWORD` | Database password. | `postgres` |
| `POSTGRESQL_DATABASE` | Database name. | `kinetiqo` |
| `POSTGRESQL_SSL_MODE` | SSL connection mode (`disable`, `require`, etc.). | `disable` |

### MySQL / MariaDB

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` | Database server hostname. | `localhost` |
| `MYSQL_PORT` | Database server port. | `3306` |
| `MYSQL_USER` | Database username. | `root` |
| `MYSQL_PASSWORD` | Database password. | - |
| `MYSQL_DATABASE` | Database name. | `kinetiqo` |
| `MYSQL_SSL_MODE` | SSL connection mode. | `disable` |

> **Note:** For MySQL, ensure the user has `CREATE` and `ALL PRIVILEGES` on the target database to allow for schema management.

### Firebird

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREBIRD_HOST` | Database server hostname. | Required |
| `FIREBIRD_PORT` | Database server port. | `3050` |
| `FIREBIRD_USER` | Database username. | Required |
| `FIREBIRD_PASSWORD` | Database password. | Required |
| `FIREBIRD_DATABASE` | Database file path or alias. | Required |

> **Note:** Kinetiqo will automatically create the Firebird database and schema if they don't exist. 
> 
> **Version Compatibility:** Tested and fully compatible with Firebird 3.0, 4.0, and 5.0. Uses only standard SQL features available in all these versions (SEQUENCE, TRIGGER, UPDATE OR INSERT, FIRST/SKIP pagination).
> 
> **Permissions Required:**
> - The user must have rights to **create databases** on the Firebird server (typically `SYSDBA` or a user with equivalent privileges)
> - Once the database exists, the user needs rights to **create tables, sequences, triggers, and indexes**
> - For embedded Firebird, ensure the application has **write access** to the database file directory
> 
## 3. Scheduling (Cron)

The Docker image includes a cron scheduler. Define schedules using standard cron syntax.

| Variable | Description | Example |
|----------|-------------|---------|
| `FULL_SYNC` | Schedule for full synchronization. | `0 3 * * *` (Daily at 3 AM) |
| `FAST_SYNC` | Schedule for incremental synchronization. | `*/15 * * * *` (Every 15 minutes) |

## 4. Web Interface Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_LOGIN` | Username for web access. | `admin` |
| `WEB_PASSWORD` | Password for web access. | `admin123` |

> **Note:** Synchronization errors are recorded in the `logs` database table and are accessible via the Web UI or `docker logs`.
