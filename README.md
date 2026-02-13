# Kinetiqo

Kinetiqo liberates your Strava activities, syncing them into a high-performance SQL database (**PostgreSQL** or **MySQL/MariaDB**) for ultimate control.

Visualize your progress with our **built-in Web UI** or dive deep with the included **Grafana dashboards**. Whether you're a data nerd or just want to see your stats without limits, Kinetiqo is your personal fitness data warehouse.

## Table of Contents

- [Features](#features)
- [Running Kinetiqo as python script](#running-kinetiqo-as-python-script)
  - [Dependencies](#dependencies)
  - [Setup local environment](#setup-local-environment)
  - [Configuration](#configuration)
- [Kinetiqo CLI explained](#kinetiqo-cli-explained)
  - [CLI Commands](#cli-commands)
  - [Manual sync (command `sync`)](#manual-sync-command-sync)
  - [Run the web server (command `web`)](#run-the-web-server-command-web)
- [Deployment](#deployment)
  - [Docker Run](#docker-run)
  - [Docker Compose](#docker-compose)
- [License](#license)

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

---

## Running Kinetiqo as python script

### Dependencies

Kinetiqo is written in Python and requires a database backend of your choice (MySQL/MariaDB or PostgreSQL).
- Python 3.12+
- Dependencies listed in `requirements.txt`.

### Setup local environment

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/lhotakj/kinetiqo.git
    cd kinetiqo
    ```

2.  **Setup your virtual environment using venv**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ``` 

3. **Alternatively use direnv to handle your environment**
   [Direnv](https://direnv.net/) installation is shipped in the `development` folder
   ```bash
   cd development
   ./setup_direnv.sh
   ```
   This command installs [Direnv](https://direnv.net/docs/installation.html) together with all required packages.
   Once you enter the folder `kinetiqo` it activates the venv, it deactivates when leaving the folder
   ```shell
    $ cd kinetiqo/
    direnv: loading ~/WORKING/kinetiqo/.envrc
    [INFO] Activating Python Python 3.12.3 venv...
    [INFO] Installing dependencies from requirements.txt ...
    [INFO] Loading environment variables from .env.development...
    direnv: export +CACHE_DIR +MYSQL_DATABASE +MYSQL_HOST +MYSQL_PASSWORD +MYSQL_SSL_MODE +MYSQL_USER +POSTGRESQL_DATABASE +POSTGRESQL_HOST +POSTGRESQL_PASSWORD +POSTGRESQL_PORT +POSTGRESQL_USER +STRAVA_CLIENT_ID +STRAVA_CLIENT_SECRET +STRAVA_REFRESH_TOKEN +VIRTUAL_ENV +VIRTUAL_ENV_PROMPT +WEB_LOGIN +WEB_PASSWORD ~PATH
   ```

4.  **Configure your environment variables.**
    Create a `.env` file in the project root to store your secrets. This file is ignored by Git.
    
    **kinetiqo.env example:**
    ```env
    STRAVA_CLIENT_ID=12345
    STRAVA_CLIENT_SECRET=your_secret_here
    STRAVA_REFRESH_TOKEN=your_refresh_token_here
    DATABASE_TYPE=postgresql
    POSTGRESQL_HOST=localhost
    POSTGRESQL_USER=postgres
    POSTGRESQL_PASSWORD=password
    ```

### Configuration

Kinetiqo is configured entirely via environment variables.

### 1. Strava API Configuration
You need to register an application on [Strava settings](https://www.strava.com/settings/api) to get these credentials.

| Variable | Description | Required |
|----------|-------------|----------|
| `STRAVA_CLIENT_ID` | Your Strava Application Client ID | ✅ |
| `STRAVA_CLIENT_SECRET` | Your Strava Application Client Secret | ✅ |
| `STRAVA_REFRESH_TOKEN` | A valid Refresh Token with `activity:read_all` scope | ✅ |

### 2. Database Configuration

Set `DATABASE_TYPE` to either `postgresql` (default) or `mysql`.

#### PostgreSQL (Default)
| Variable | Description | Default    |
|----------|-------------|------------|
| `POSTGRESQL_HOST` | Hostname of the PostgreSQL server | -          |
| `POSTGRESQL_PORT` | PostgreSQL port | `5432`     |
| `POSTGRESQL_USER` | Database username | `postgres` |
| `POSTGRESQL_PASSWORD` | Database password | `postgres` |
| `POSTGRESQL_DATABASE` | Database name | `kinetiqo` |
| `POSTGRESQL_SSL_MODE` | SSL mode for the connection. Can be `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`. | `disable`  |

#### MySQL / MariaDB
| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` | Hostname of the MySQL server | - |
| `MYSQL_PORT` | MySQL port | `3306` |
| `MYSQL_USER` | Database username | - |
| `MYSQL_PASSWORD` | Database password | - |
| `MYSQL_DATABASE` | Database name | - |

Note that you need to explicitly grant permission to the `MYSQL_USER` on that DB to create database for you.
Run this query to grant the permission before you run the tool, replace `$MYSQL_USER` with your username.
```sql
GRANT CREATE ON *.* TO '$MYSQL_USER'@'%';
GRANT ALL PRIVILEGES ON *.* TO '$MYSQL_USER'@'%';
FLUSH PRIVILEGES;
```

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

> **Note:** Sync failures are logged in logs, your can review them using `docker logs` command.  


## Kinetiqo CLI explained

The source code sits in `src`.
```shell
cd src
```

### CLI Commands

*   `--database` / `-d`: Database backend to use (overrides config). Choices: `mysql`, `postgresql`.
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


### Manual sync (command `sync`)

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
```

### Run the web server (command `web`)

Default port for the web interface is `4444`, with default `postgres` database. It expects PostgreSQL environments loaded, see above.
```bash
python kinetiqo.py web
```
You can define own port by `--port <number>`, the example below defines database type `mysql` and port `8000`. It expects MySQL environments loaded, see above. 
```bash
python kinetiqo.py --database mysql web --port 8000
```

## Deployment

### Docker Run

Example if you prefer to run it using `docker` command.
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
  -e WEB_PASSWORD="securepassword13" \
  kinetiqo:latest
```

### Docker Compose

Here is a complete example stack with PostgreSQL and Grafana.

`docker-compose.yml`:

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
      - POSTGRESQL_SSL_MODE=disable
      - FAST_SYNC=*/15 * * * *  # Every 15 minutes
      - FULL_SYNC=0 3 * * *     # Daily at 3 AM
      - WEB_LOGIN=admin
      - WEB_PASSWORD=securepassword13
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
POSTGRESQL_PASSWORD=your_password_here
```

Then run:
```bash
docker-compose up -d
```

## License

See [LICENSE](LICENSE) file for details.
