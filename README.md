# Kinetiqo

Kinetiqo is a self-hosted data warehouse for your Strava activities. It syncs your data into a high-performance SQL database (**PostgreSQL** or **MySQL/MariaDB**), giving you full ownership and control over your fitness history.

Visualize your progress with the **built-in Web UI** or connect your favorite business intelligence tools. For advanced analytics, Kinetiqo includes pre-built **Grafana dashboards**, turning your workout data into actionable insights.

## Table of Contents

- [Features](#features)
- [Getting Started](#getting-started)
  - [Dependencies](#dependencies)
  - [Local Setup](#local-setup)
  - [Configuration](#configuration)
- [Command-Line Interface (CLI)](#command-line-interface-cli)
  - [CLI Commands](#cli-commands)
  - [Manual Sync](#manual-sync)
  - [Web Interface](#web-interface)
- [Deployment](#deployment)
  - [Docker Run](#docker-run)
  - [Docker Compose](#docker-compose)
- [License](#license)

## Features

- 📊 **Rich Visualization**: A clean web interface for daily use and powerful Grafana dashboards for deep analysis.
- 📝 **Comprehensive Logging**: Tracks all sync operations and deletions, providing a detailed audit trail in the Web UI.
- 🔄 **Smart Synchronization**:
  - **Full Sync**: Performs a complete audit of your Strava history, fetching all activities and removing any that have been deleted from Strava.
  - **Fast Sync**: Efficiently fetches only the most recent activities, ideal for daily updates.
- 🐳 **Docker-Native**: Designed for containerized deployments, making it easy to integrate into your existing stack.
- ⏱️ **Automated Scheduling**: A built-in cron scheduler keeps your data fresh automatically, so it's always ready for analysis.
- 💾 **Database Support**:
  - **PostgreSQL** (version 18+)
  - **MySQL 8 / MariaDB 12**
- 🚀 **Optimized Performance**: Intelligent caching minimizes Strava API usage and maximizes data retrieval speed.
- 🔒 **Secure Authentication**: Uses the standard OAuth 2.0 protocol to protect your Strava account credentials.

---

## Getting Started

### Dependencies

- Python 3.12+
- A running instance of PostgreSQL or MySQL/MariaDB.
- Python package dependencies as listed in `requirements.txt`.

### Local Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/lhotakj/kinetiqo.git
    cd kinetiqo
    ```

2.  **Set Up a Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Use `direnv` for Automatic Environment Management (Optional):**
    The `development` directory includes a script to set up `direnv`, which automatically manages your virtual environment and variables.
    ```bash
    cd development
    ./setup-direnv.sh
    ```
    Once configured, `direnv` will automatically activate the environment when you enter the project directory.

4.  **Configure Environment Variables:**
    Create a `.env` file in the project root to store your configuration. This file is kept private and is ignored by Git.
    
    **Example `.env` file:**
    ```env
    STRAVA_CLIENT_ID=12345
    STRAVA_CLIENT_SECRET=your_secret_here
    STRAVA_REFRESH_TOKEN=your_refresh_token_here
    DATABASE_TYPE=postgresql
    POSTGRESQL_HOST=localhost
    POSTGRESQL_USER=postgres
    POSTGRESQL_PASSWORD=password
    ```

5.  **Store Secrets Securely with GPG (Optional):**
    For enhanced security, you can encrypt your environment files using GPG. The included `.envrc` script will automatically decrypt them.
    
    1. **Import Your GPG Key:**
       ```shell
       gpg --import ~/.ssh/id_rsa
       gpg --list-secret-keys
       ```

    2. **Encrypt Your Environment File:**
       This example encrypts a file named `.env.development`.
       ```shell
       mkdir -p secrets
       gpg -r <your-key-id> -o secrets/development.gpg -e .env.development
       ```
       Ensure the unencrypted file (`.env.development`) is listed in your `.gitignore`.

### Configuration

Kinetiqo is configured entirely through environment variables.

#### 1. Strava API Configuration
Register an application at [Strava's API settings page](https://www.strava.com/settings/api) to obtain these credentials.

| Variable | Description | Required |
|----------|-------------|----------|
| `STRAVA_CLIENT_ID` | Your Strava application's Client ID. | ✅ |
| `STRAVA_CLIENT_SECRET` | Your Strava application's Client Secret. | ✅ |
| `STRAVA_REFRESH_TOKEN` | A valid Refresh Token with `activity:read_all` scope. | ✅ |

#### 2. Database Configuration
Set `DATABASE_TYPE` to either `postgresql` (default) or `mysql`.

**PostgreSQL (Default):**

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRESQL_HOST` | Hostname of the PostgreSQL server. | `localhost` |
| `POSTGRESQL_PORT` | Port for the PostgreSQL server. | `5432` |
| `POSTGRESQL_USER` | Database username. | `postgres` |
| `POSTGRESQL_PASSWORD` | Database password. | `postgres` |
| `POSTGRESQL_DATABASE` | Name of the database to use. | `kinetiqo` |
| `POSTGRESQL_SSL_MODE` | SSL mode for the connection (`disable`, `require`, etc.). | `disable` |

**MySQL / MariaDB:**

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` | Hostname of the MySQL server. | `localhost` |
| `MYSQL_PORT` | Port for the MySQL server. | `3306` |
| `MYSQL_USER` | Database username. | `root` |
| `MYSQL_PASSWORD` | Database password. | - |
| `MYSQL_DATABASE` | Name of the database to use. | `kinetiqo` |
| `MYSQL_SSL_MODE` | SSL mode for the connection. | `disable` |

> **Note:** For MySQL, the specified user must have `CREATE` and `ALL PRIVILEGES` grants to allow Kinetiqo to manage the database schema.

#### 3. Scheduling (Cron)
The Docker container includes a built-in cron scheduler. Define schedules using standard cron syntax.

| Variable | Description | Example |
|----------|-------------|---------|
| `FULL_SYNC` | Cron schedule for a full sync. | `0 3 * * *` (Daily at 3 AM) |
| `FAST_SYNC` | Cron schedule for a fast sync. | `*/15 * * * *` (Every 15 minutes) |

#### 4. Web Interface Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_LOGIN` | Username for the web interface. | `admin` |
| `WEB_PASSWORD` | Password for the web interface. | `admin123` |

> **Note:** Sync failures are logged to the `logs` table in the database and can be viewed in the Web UI or by running `docker logs <container_id>`.

## Command-Line Interface (CLI)

The CLI is available in the `src` directory.

### CLI Commands

-   `--database` / `-d`: Specifies the database backend (`mysql` or `postgresql`), overriding the environment variable.
-   `sync`: Synchronizes activities with the database.
    -   `--full-sync` / `-f`: Performs a full sync, auditing all activities.
    -   `--fast-sync` / `-q`: Performs a fast sync, fetching only new activities.
    -   `--period` / `-p`: Limits the full sync to a specific period (e.g., '7d', '2w', '1m', '1y').
    -   `--enable-strava-cache`: Enables caching of Strava API responses to speed up development.
    -   `--cache-ttl`: Sets the cache time-to-live in minutes (default: 60).
    -   `--clear-cache`: Clears the cache before syncing.
-   `web`: Starts the web interface.
    -   `--port`: Port to run the web server on (default: 4444).
    -   `--host`: Host to bind to (default: 0.0.0.0).
-   `flightcheck`: Checks the database connection and schema integrity.
-   `version`: Displays the application version.

### Manual Sync

To run a sync manually, execute the `sync` command from the `src` directory:

```bash
# Run a full sync of all activities
python kinetiqo.py sync --full-sync

# Run a full sync limited to the last 30 days
python kinetiqo.py sync --full-sync --period 30d

# Run a fast sync to fetch only new activities
python kinetiqo.py sync --fast-sync
```

### Web Interface

To start the web server, use the `web` command:

```bash
# Start the web server on the default port (4444)
python kinetiqo.py web

# Start with a specific port and database
python kinetiqo.py --database mysql web --port 8000
```

## Deployment

### Docker Run

The following is an example of running Kinetiqo as a standalone Docker container.

```bash
docker run -d \
  --name kinetiqo \
  -p 8080:4444 \
  -e STRAVA_CLIENT_ID="your_id" \
  -e STRAVA_CLIENT_SECRET="your_secret" \
  -e STRAVA_REFRESH_TOKEN="your_token" \
  -e DATABASE_TYPE="postgresql" \
  -e POSTGRESQL_HOST="host.docker.internal" \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="password" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword13" \
  lhotakj/kinetiqo:latest
```

### Docker Compose

For a complete, production-ready stack, use Docker Compose. This example includes PostgreSQL and Grafana.

**`docker-compose.yml`:**
```yaml
---
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
      - DATABASE_TYPE=postgresql
      - POSTGRESQL_HOST=postgresql
      - POSTGRESQL_PORT=5432
      - POSTGRESQL_USER=postgres
      - POSTGRESQL_PASSWORD=${POSTGRESQL_PASSWORD}
      - POSTGRESQL_DATABASE=kinetiqo
      - FAST_SYNC=*/15 * * * *
      - FULL_SYNC=0 3 * * *
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

Create a `.env` file in the same directory:

```env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
STRAVA_REFRESH_TOKEN=your_strava_refresh_token
POSTGRESQL_PASSWORD=your_secure_password
```

Launch the stack with:
```bash
docker-compose up -d
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
