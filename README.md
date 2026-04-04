# Kinetiqo

Kinetiqo is a self-hosted data warehouse for your Strava activities. It synchronizes your data into a high-performance SQL database (**PostgreSQL**, **MySQL/MariaDB**, or **Firebird**), providing full ownership and control over your fitness history.

Visualize your progress with the **built-in Web UI** or integrate with your preferred business intelligence tools. For advanced analytics, Kinetiqo includes pre-configured **Grafana dashboards**, transforming your workout data into actionable insights.

> Full project documentation is available at [kinetiqo.lhotak.net](https://kinetiqo.lhotak.net) 

## Table of Contents

- [Features](#features)
- [Getting Started](#getting-started)
  - [Dependencies](#dependencies)
  - [Local Setup](#local-setup)
  - [Configuration](#configuration)
    - [1. Strava API Credentials](#1-strava-api-credentials)
    - [2. Database Configuration](#2-database-configuration)
    - [3. Scheduling (Cron)](#3-scheduling-cron)
    - [4. Web Interface Configuration](#4-web-interface-configuration)
    - [5. Athlete Configuration](#5-athlete-configuration)
    - [6. Display Configuration](#6-display-configuration)
    - [7. Map Configuration](#7-map-configuration)
- [Command-Line Interface (CLI)](#command-line-interface-cli)
  - [CLI Commands](#cli-commands)
  - [Manual Sync](#manual-sync)
  - [Web Interface](#web-interface)
- [Building Docker Images](#building-docker-images)
  - [Architecture: Two-Phase Build](#architecture-two-phase-build)
  - [Local Build](#local-build)
  - [CI/CD Workflows](#cicd-workflows)
- [Deployment](#deployment)
  - [Docker Run](#docker-run)
  - [Docker Compose](#docker-compose)
- [License](#license)
  - [Map Tile Attributions](#map-tile-attributions)

## Features

- 📊 **Advanced Visualization**: A streamlined web interface for daily monitoring and comprehensive Grafana dashboards for in-depth analysis.
- ⚡ **Power Skills Analysis**: Visualize your best power efforts across different time intervals (5s to 1h) with a Strava-like spider chart.
- 🏋️ **FTP Estimation**: Automatically estimates your Functional Threshold Power (95 % of best 20-minute average power) from your recorded power-meter data, with a per-ride history chart.
- 🫁 **VO2max Estimation**: Estimates your VO2max from your best 5-minute MAP power using the Townsend method, including a smoothed history trend and classification band.
- 🗺️ **Interactive Maps**: View your activities on an interactive map with customizable styles, filtering, and performance optimizations for large datasets. Tiles are served through a server-side proxy that satisfies the OSM usage policy.
- 🌓 **Dark Mode Support**: Fully supported dark theme with automatic system preference detection and manual toggle.
- 📝 **Audit Logging**: Records all synchronization operations and data modifications, providing a complete audit trail within the Web UI.
- 🔄 **Intelligent Synchronization**:
  - **Full Synchronization**: Conducts a comprehensive audit of your Strava history, retrieving all activities and reconciling any deletions.
  - **Incremental Synchronization**: Efficiently retrieves only the most recent activities, optimized for frequent updates.
- 🐳 **Container-Native**: Architected for Docker environments, facilitating seamless integration into existing infrastructure.
- ⏱️ **Automated Scheduling**: Includes a built-in cron scheduler to ensure data currency without manual intervention.
- 💾 **Database Compatibility**:
  - **PostgreSQL** (version 12+)
  - **MySQL 8 / MariaDB 10+**
  - **Firebird** (versions 3.0, 4.0, 5.0)
- 🚀 **Performance Optimization**: Utilizes intelligent caching strategies to minimize API consumption and accelerate data retrieval.
- 🔒 **Security**: Implements standard OAuth 2.0 protocols to safeguard user credentials.

---

## Getting Started

### Dependencies

- Python 3.13+
- A running instance of PostgreSQL, MySQL/MariaDB, or Firebird.
- Python package dependencies as listed in `requirements.txt`.
- For Firebird, the client library is compiled from source inside the Docker base image (see [Building Docker Images](#building-docker-images)). For local (non-Docker) development on Ubuntu, install `libfbclient2`.

### Local Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/lhotakj/kinetiqo.git
    cd kinetiqo
    ```
    
2.  **Install Firebird Client (Optional):**
    Required only if using Firebird as the database backend. Install on Ubuntu:
    ```bash
    sudo apt update
    sudo apt install -y libfbclient2
    ```

3.  **Initialize Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    pip install -r requirements.txt
    ```

4.  **Environment Management with `direnv` (Optional):**
    The `development` directory contains a script to configure `direnv` for automated environment management.
    ```bash
    cd development
    ./setup-direnv.sh
    ```
    Upon configuration, `direnv` will automatically load the environment variables when entering the project directory.

5.  **Configure Environment Variables:**
    Create a `.env` file in the project root to define your configuration. This file is excluded from version control.
    
    **Example `.env` file:**
    ```env
    STRAVA_CLIENT_ID=12345
    STRAVA_CLIENT_SECRET=your_secret_here
    STRAVA_REFRESH_TOKEN=your_refresh_token_here
    DATABASE_TYPE=postgresql  # or mysql or firebird
    # PostgreSQL
    POSTGRESQL_HOST=localhost
    POSTGRESQL_PORT=5432
    POSTGRESQL_USER=postgres
    POSTGRESQL_PASSWORD=password
    POSTGRESQL_DATABASE=kinetiqo
    POSTGRESQL_SSL_MODE=disable
    # MySQL
    MYSQL_HOST=localhost
    MYSQL_PORT=3306
    MYSQL_USER=root
    MYSQL_PASSWORD=password
    MYSQL_DATABASE=kinetiqo
    MYSQL_SSL_MODE=disable
    # Firebird
    FIREBIRD_HOST=localhost
    FIREBIRD_PORT=3050
    FIREBIRD_USER=firebird
    FIREBIRD_PASSWORD=firebird
    FIREBIRD_DATABASE=/db/data/kinetiqo.fdb
    ```
    - Set `DATABASE_TYPE` to `postgresql`, `mysql`, or `firebird` as needed.
    - Only the relevant database section is required for your selected type.

6.  **Secure Secret Storage with GPG (Optional):**
    For enhanced security, environment files can be encrypted using GPG. The included `.envrc` script supports automatic decryption.
    
    1. **Import GPG Key:**
       ```shell
       gpg --import ~/.ssh/id_rsa
       gpg --list-secret-keys
       ```

    2. **Encrypt Environment File:**
       The following command encrypts `.env.development`.
       ```shell
       mkdir -p secrets
       gpg -r <your-key-id> -o secrets/development.gpg -e .env.development
       ```
       Ensure the unencrypted source file (`.env.development`) is included in `.gitignore`.

### Configuration

Configuration is managed exclusively via environment variables.

#### 1. Strava API Credentials
Register an application in the [Strava API Settings](https://www.strava.com/settings/api) to obtain the necessary credentials.

| Variable | Description | Required |
|----------|-------------|----------|
| `STRAVA_CLIENT_ID` | Strava Application Client ID. | ✅ |
| `STRAVA_CLIENT_SECRET` | Strava Application Client Secret. | ✅ |
| `STRAVA_REFRESH_TOKEN` | Valid Refresh Token with `activity:read_all` scope. | ✅ |

#### 2. Database Configuration
Define `DATABASE_TYPE` as either `postgresql` (default), `mysql`, or `firebird`.

**PostgreSQL (Default):**

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRESQL_HOST` | Database server hostname. | Required |
| `POSTGRESQL_PORT` | Database server port. Override via env var. | `5432` |
| `POSTGRESQL_USER` | Database username. | Required |
| `POSTGRESQL_PASSWORD` | Database password. | Required |
| `POSTGRESQL_DATABASE` | Database name. | Required |
| `POSTGRESQL_SSL_MODE` | SSL connection mode (`disable`, `require`, etc.). | `disable` |

**MySQL / MariaDB:**

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` | Database server hostname. | Required |
| `MYSQL_PORT` | Database server port. Override via env var. | `3306` |
| `MYSQL_USER` | Database username. | Required |
| `MYSQL_PASSWORD` | Database password. | Required |
| `MYSQL_DATABASE` | Database name. | Required |
| `MYSQL_SSL_MODE` | SSL connection mode. | `disable` |

> **Note:** For MySQL, ensure the user has `CREATE` and `ALL PRIVILEGES` on the target database to allow for schema management.

**Firebird:**

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREBIRD_HOST` | Database server hostname. | Required |
| `FIREBIRD_PORT` | Database server port. Override via env var. | `3050` |
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

#### 3. Scheduling (Cron)
The Docker image includes a built-in cron scheduler powered by `dcron`. When the container starts, the entrypoint script registers cron jobs for any sync schedules you define via environment variables. If neither variable is set, no automatic synchronization occurs.

| Variable | Description | Example |
|----------|-------------|---------|
| `FULL_SYNC` | Schedule for full synchronization. | `0 3 * * *` (Daily at 3 AM) |
| `FAST_SYNC` | Schedule for incremental synchronization. | `*/15 * * * *` (Every 15 minutes) |

Both variables accept standard **5-field cron expressions** (`minute hour day-of-month month day-of-week`):

| Field | Allowed Values |
|-------|---------------|
| Minute | `0–59` |
| Hour | `0–23` |
| Day of month | `1–31` |
| Month | `1–12` |
| Day of week | `0–7` (0 and 7 = Sunday) |

**How the two sync modes differ:**

- **`FAST_SYNC`** runs an incremental sync (`--fast-sync`). It only fetches activities newer than the most recent one already in the database. This is lightweight and ideal for frequent scheduling (e.g., every 15 minutes) to keep data nearly real-time.
- **`FULL_SYNC`** runs a comprehensive audit (`--full-sync`). It retrieves your entire Strava activity history, inserts any missing activities, and removes any that were deleted on Strava. This is heavier and best scheduled infrequently (e.g., once daily during off-hours).

**Recommended setup:** Use both together — `FAST_SYNC` for frequent, low-cost updates and `FULL_SYNC` as a daily reconciliation pass.

**Common cron examples:**

| Expression | Meaning |
|-----------|---------|
| `*/15 * * * *` | Every 15 minutes |
| `0 * * * *` | Every hour, on the hour |
| `0 3 * * *` | Daily at 3:00 AM |
| `0 3 * * 0` | Weekly on Sunday at 3:00 AM |
| `0 */6 * * *` | Every 6 hours |

#### 4. Web Interface Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_LOGIN` | Username for web access. | `admin` |
| `WEB_PASSWORD` | Password for web access. | `admin123` |

#### 5. Athlete Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `ATHLETE_WEIGHT` | Athlete body weight in kilograms, used for VO2max estimation. Can also be set from the **Settings → Athlete** page in the Web UI. | `0` (not set) |

#### 6. Display Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `DATE_FORMAT` | Date format string (Python `strftime` syntax). | `%b %d, %Y` |

#### 7. Map Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `MAPY_API_KEY` | API key for Mapy.cz tile layers (Outdoor & Base). Obtain a free key at [developer.mapy.com](https://developer.mapy.com). When not set, Mapy.cz layers are hidden from the map selector. | _(empty)_ |

> **Note:** Synchronization errors are recorded in the `logs` database table and are accessible via the Web UI or `docker logs`.

## Command-Line Interface (CLI)

The CLI tool is located in the `src` directory.

### CLI Commands

-   `--database` / `-d`: Selects the database backend (`mysql`, `postgresql`, or `firebird`), overriding environment variables.
-   `sync`: Initiates data synchronization.
    -   `--full-sync` / `-f`: Executes a full synchronization audit.
    -   `--fast-sync` / `-q`: Executes an incremental synchronization.
    -   `--period` / `-p`: Restricts full synchronization to a specific timeframe (e.g., '7d', '2w', '1m', '1y').
    -   `--enable-strava-cache`: Activates API response caching.
    -   `--cache-ttl`: Defines cache time-to-live in minutes (default: 60).
    -   `--clear-cache`: Purges the cache prior to synchronization.
-   `web`: Launches the web server.
    -   `--port`: Specifies the listening port (default: 4444).
    -   `--host`: Specifies the bind address (default: 0.0.0.0).
-   `flightcheck`: Validates database connectivity and schema integrity.
-   `version`: Outputs the current version information.

### Manual Sync

Execute the `sync` command from the `src` directory:

```bash
# Execute full synchronization
python kinetiqo.py sync --full-sync

# Execute full synchronization limited to the last 30 days
python kinetiqo.py sync --full-sync --period 30d

# Execute incremental synchronization
python kinetiqo.py sync --fast-sync
```

### Web Interface

Launch the web server using the `web` command:

```bash
# Start server on default port (4444)
python kinetiqo.py web

# Start server on custom port with specific database backend
python kinetiqo.py --database mysql web --port 8000
```

## Building Docker Images

### Architecture: Two-Phase Build

The Docker build is split into **two independent phases** to keep day-to-day builds fast. Compiling the Firebird 5.x client library from source takes ~40 minutes on CI, so it is isolated into a dedicated **base image** that rarely needs rebuilding.

```
Phase 1 (rare)                          Phase 2 (every release)
┌──────────────────────────┐            ┌──────────────────────────┐
│  Dockerfile.firebird-base│            │  Dockerfile              │
│                          │            │                          │
│  python:3.13-alpine      │            │  python:3.13-alpine      │ ← pip install only
│    + compile Firebird    │            │    (builder stage)       │
│    + runtime libs        │            │                          │
│           ↓              │            │  lhotakj/firebird-python │ ← FROM base image
│  lhotakj/firebird-python │ ──────────│    + pip packages        │
│         :3.13            │  used as   │    + app source          │
└──────────────────────────┘  base      │           ↓              │
                                        │  lhotakj/kinetiqo:x.y.z │
                                        └──────────────────────────┘
```

| Phase | Image | Dockerfile | Rebuild when… |
|---|---|---|---|
| 1 — Base | `lhotakj/firebird-python:3.13` | `build/Dockerfile.firebird-base` | Python or Firebird version changes |
| 2 — App | `lhotakj/kinetiqo:x.y.z` | `build/Dockerfile` | Application code or dependencies change |

### Local Build

Both phases can be run entirely locally without pushing anything to Docker Hub.

```bash
# Phase 1 — build the base image (~40 min, one-time)
cd build
./build-base.sh

# Phase 2 — build the application image (~2 min)
./build.sh
```

`build-base.sh` compiles the Firebird client and loads `lhotakj/firebird-python:3.13` into your local Docker daemon. `build.sh` then uses that local image as its `FROM` target (with `--pull=false` to prevent Docker from reaching out to Docker Hub).

You only need to re-run `build-base.sh` when you change the Python or Firebird version. For day-to-day code changes, `./build.sh` alone is sufficient.

Both scripts accept the `--push` flag to publish to Docker Hub instead:

| Script | Without `--push` | With `--push` |
|---|---|---|
| `build-base.sh` | Builds for `linux/amd64`, loads locally | Builds for `linux/amd64` + `linux/arm64`, pushes to DockerHub |
| `build.sh` | Builds for `linux/amd64`, loads locally | Builds for `linux/amd64` + `linux/arm64`, pushes to DockerHub |

`build-base.sh` also accepts `--python <version>` and `--firebird <version>` to override the defaults (`3.13` and `5.0.3`).

### CI/CD Workflows

Two GitHub Actions workflows mirror the two-phase build:

| Workflow | File | Trigger | Purpose |
|---|---|---|---|
| **Build Firebird Python Base Image** | `.github/workflows/build-base-image.yaml` | Manual (`workflow_dispatch`) | Compiles Firebird, pushes `lhotakj/firebird-python` to DockerHub |
| **Build and publish Docker image** | `.github/workflows/build.yaml` | Manual or push to `main` with `/publish` or `/release` in commit message | Builds the app image, optionally pushes to DockerHub and creates a GitHub Release |

#### Build Firebird Python Base Image

Triggered **manually only** from the GitHub Actions UI. Inputs:

| Input | Default | Description |
|---|---|---|
| `python_version` | `3.13` | Python version for the base Alpine image |
| `firebird_version` | `5.0.3` | Firebird version to compile from source |
| `platforms` | `linux/amd64,linux/arm64` | Target architectures |

Pushes two tags to DockerHub:
- `lhotakj/firebird-python:3.13`
- `lhotakj/firebird-python:3.13-firebird5.0.3`

#### Build and publish Docker image

Triggered **manually** (with `publish` and `create_release` boolean inputs) or automatically on push to `main` when the commit message contains `/publish` and/or `/release`.

| Commit commands | Effect |
|---|---|
| `/publish` | Build and push the Docker image to DockerHub |
| `/release` | Create a GitHub Release with an auto-generated changelog |

## Deployment

### Docker Run

Example command to deploy Kinetiqo as a standalone container (supports PostgreSQL, MySQL/MariaDB, and Firebird):

```bash
docker run -d \
  --name kinetiqo \
  -p 8080:4444 \
  -e STRAVA_CLIENT_ID="your_id" \
  -e STRAVA_CLIENT_SECRET="your_secret" \
  -e STRAVA_REFRESH_TOKEN="your_token" \
  -e DATABASE_TYPE="postgresql" \
  -e POSTGRESQL_HOST="host.docker.internal" \
  -e POSTGRESQL_PORT=5432 \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="password" \
  -e POSTGRESQL_DATABASE="kinetiqo" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword13" \
  lhotakj/kinetiqo:latest
```

- Set `DATABASE_TYPE` and only the relevant database variables for your chosen backend (`postgresql`, `mysql`, or `firebird`).
- The web UI will be available at http://localhost:8080

**Cron schedule in this example:**

| Variable | Value | Effect |
|----------|-------|--------|
| `FAST_SYNC` | `*/15 * * * *` | Runs an incremental sync every 15 minutes — quickly picks up any new activities recorded on Strava. |
| `FULL_SYNC` | `0 3 * * *` | Runs a full audit every day at 3:00 AM — reconciles all activities and detects deletions on Strava. |

Both schedules are optional. If omitted, no automatic sync occurs and you would need to trigger syncs manually via the Web UI or CLI.

### Docker Compose

For a production-grade deployment, use Docker Compose. The following configuration includes PostgreSQL and Grafana. You can adapt for MySQL or Firebird as needed.

**`docker-compose.yml`:**

```yaml
services:
  kinetiqo:
    image: lhotakj/kinetiqo:latest
    container_name: kinetiqo
    restart: always
    ports:
      - "80:4444"
    environment:
      - STRAVA_CLIENT_ID=${STRAVA_CLIENT_ID}
      - STRAVA_CLIENT_SECRET=${STRAVA_CLIENT_SECRET}
      - STRAVA_REFRESH_TOKEN=${STRAVA_REFRESH_TOKEN}
      - DATABASE_TYPE=postgresql  # or mysql or firebird
      - POSTGRESQL_HOST=postgresql
      - POSTGRESQL_PORT=5432
      - POSTGRESQL_USER=postgres
      - POSTGRESQL_PASSWORD=${POSTGRESQL_PASSWORD}
      - POSTGRESQL_DATABASE=kinetiqo
      - FAST_SYNC="*/15 * * * *"
      - FULL_SYNC="0 3 * * *"
      - WEB_LOGIN=admin
      - WEB_PASSWORD=securepassword13
    depends_on:
      - postgresql
  postgresql:
    image: postgres:latest
    container_name: postgresql
    restart: always
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${POSTGRESQL_PASSWORD}
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

For MySQL or Firebird, replace the `postgresql` service and environment variables accordingly.

Create a `.env` file in the same directory:

```env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
STRAVA_REFRESH_TOKEN=your_strava_refresh_token
POSTGRESQL_PASSWORD=your_secure_password
```

Deploy the stack:

```bash
docker-compose up -d
```

- For more details and advanced configuration, see the project documentation at [kinetiqo.lhotak.net](https://kinetiqo.lhotak.net).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

### Map Tile Attributions

Kinetiqo displays map tiles from the following third-party providers. Their respective licenses and required attributions are listed below.

| Provider | License / Terms | Required Attribution |
|----------|----------------|----------------------|
| [OpenStreetMap](https://www.openstreetmap.org) | Data: [ODbL 1.0](https://opendatacommons.org/licenses/odbl/) · Tiles: [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/) · [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) | © OpenStreetMap contributors |
| [Mapy.cz](https://mapy.com) (Seznam.cz, a.s.) | [Mapy.cz Developer Terms & Conditions](https://developer.mapy.com/terms-and-conditions/) — free tier for non-commercial / personal use; map data may not be used for competing map services | © Seznam.cz, a.s. · © OpenStreetMap |
| [CARTO](https://carto.com/) (Positron & Dark Matter) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | © OpenStreetMap contributors · © CARTO |
| [Esri World Imagery](https://www.esri.com/) | [Esri Master License Agreement](https://www.esri.com/en-us/legal/terms/full-master-agreement) | © Esri, Maxar, Earthstar Geographics |

> **Mapy.cz API key:** To enable the Mapy.cz Outdoor and Base map layers, obtain a free API key from [developer.mapy.com](https://developer.mapy.com) and set the `MAPY_API_KEY` environment variable. Without a key, the Mapy.cz layers are hidden from the map selector.

