# Kinetiqo

Kinetiqo is a self-hosted data warehouse for your Strava activities. It synchronizes your data into a high-performance SQL database (**PostgreSQL**, **MySQL/MariaDB**, or **Firebird**), providing full ownership and control over your fitness history.

Visualize your progress with the **built-in Web UI** or integrate with your preferred business intelligence tools. For advanced analytics, Kinetiqo includes pre-configured **Grafana dashboards**, transforming your workout data into actionable insights.

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

- 📊 **Advanced Visualization**: A streamlined web interface for daily monitoring and comprehensive Grafana dashboards for in-depth analysis.
- 📝 **Audit Logging**: Records all synchronization operations and data modifications, providing a complete audit trail within the Web UI.
- 🔄 **Intelligent Synchronization**:
  - **Full Synchronization**: Conducts a comprehensive audit of your Strava history, retrieving all activities and reconciling any deletions.
  - **Incremental Synchronization**: Efficiently retrieves only the most recent activities, optimized for frequent updates.
- 🐳 **Container-Native**: Architected for Docker environments, facilitating seamless integration into existing infrastructure.
- ⏱️ **Automated Scheduling**: Includes a built-in cron scheduler to ensure data currency without manual intervention.
- 💾 **Database Compatibility**:
  - **PostgreSQL** (version 18+)
  - **MySQL 8 / MariaDB 12**
  - **Firebird** (versions 3.0, 4.0, 5.0)
- 🚀 **Performance Optimization**: Utilizes intelligent caching strategies to minimize API consumption and accelerate data retrieval.
- 🔒 **Security**: Implements standard OAuth 2.0 protocols to safeguard user credentials.

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

2.  **Initialize Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Environment Management with `direnv` (Optional):**
    The `development` directory contains a script to configure `direnv` for automated environment management.
    ```bash
    cd development
    ./setup-direnv.sh
    ```
    Upon configuration, `direnv` will automatically load the environment variables when entering the project directory.

4.  **Configure Environment Variables:**
    Create a `.env` file in the project root to define your configuration. This file is excluded from version control.
    
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

5.  **Secure Secret Storage with GPG (Optional):**
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
| `POSTGRESQL_HOST` | Database server hostname. | `localhost` |
| `POSTGRESQL_PORT` | Database server port. | `5432` |
| `POSTGRESQL_USER` | Database username. | `postgres` |
| `POSTGRESQL_PASSWORD` | Database password. | `postgres` |
| `POSTGRESQL_DATABASE` | Database name. | `kinetiqo` |
| `POSTGRESQL_SSL_MODE` | SSL connection mode (`disable`, `require`, etc.). | `disable` |

**MySQL / MariaDB:**

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` | Database server hostname. | `localhost` |
| `MYSQL_PORT` | Database server port. | `3306` |
| `MYSQL_USER` | Database username. | `root` |
| `MYSQL_PASSWORD` | Database password. | - |
| `MYSQL_DATABASE` | Database name. | `kinetiqo` |
| `MYSQL_SSL_MODE` | SSL connection mode. | `disable` |

> **Note:** For MySQL, ensure the user has `CREATE` and `ALL PRIVILEGES` on the target database to allow for schema management.

**Firebird:**

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

#### 3. Scheduling (Cron)
The Docker image includes a cron scheduler. Define schedules using standard cron syntax.

| Variable | Description | Example |
|----------|-------------|---------|
| `FULL_SYNC` | Schedule for full synchronization. | `0 3 * * *` (Daily at 3 AM) |
| `FAST_SYNC` | Schedule for incremental synchronization. | `*/15 * * * *` (Every 15 minutes) |

#### 4. Web Interface Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_LOGIN` | Username for web access. | `admin` |
| `WEB_PASSWORD` | Password for web access. | `admin123` |

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

## Deployment

### Docker Run

Example command to deploy Kinetiqo as a standalone container:

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

For a production-grade deployment, use Docker Compose. The following configuration includes PostgreSQL and Grafana.

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

Deploy the stack:
```bash
docker-compose up -d
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
