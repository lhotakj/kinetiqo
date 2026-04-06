---
layout: default
title: Deployment
nav_order: 5
---

# Deployment

This guide covers deploying Kinetiqo using Docker or Docker Compose, including advanced build and CI/CD options.

## Docker Run

Example command to deploy Kinetiqo as a standalone container (supports PostgreSQL, MySQL/MariaDB, and Firebird):

```bash
docker run -d \
  --name kinetiqo \
  -p 8080:4444 \
  -e STRAVA_CLIENT_ID="your_id" \
  -e STRAVA_CLIENT_SECRET="your_secret" \
  -e STRAVA_REFRESH_TOKEN="your_token" \
  -e DATABASE_TYPE="postgresql" \  # or firebird or mysql
  # PostgreSQL example
  -e POSTGRESQL_HOST="host.docker.internal" \
  -e POSTGRESQL_PORT=5432 \
  -e POSTGRESQL_USER="postgres" \
  -e POSTGRESQL_PASSWORD="password" \
  -e POSTGRESQL_DATABASE="kinetiqo" \
  # MySQL example
  -e MYSQL_HOST="host.docker.internal" \
  -e MYSQL_PORT=3306 \
  -e MYSQL_USER="root" \
  -e MYSQL_PASSWORD="password" \
  -e MYSQL_DATABASE="kinetiqo" \
  # Firebird example
  -e FIREBIRD_HOST="host.docker.internal" \
  -e FIREBIRD_PORT=3050 \
  -e FIREBIRD_USER="firebird" \
  -e FIREBIRD_PASSWORD="firebird" \
  -e FIREBIRD_DATABASE="/db/data/kinetiqo.fdb" \
  -e FAST_SYNC="*/15 * * * *" \
  -e FULL_SYNC="0 3 * * *" \
  -e WEB_LOGIN="admin" \
  -e WEB_PASSWORD="securepassword13" \
  -e MAPY_API_KEY="your_mapy_com_api_token" \
  -e THUNDERFOREST_API_KEY="your_thunderforest_api_token" \
  lhotakj/kinetiqo:latest
```

- Set only the relevant database variables for your selected `DATABASE_TYPE`.
- The web UI will be available at http://localhost:8080

## Docker Compose

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
      - MAPY_API_KEY="${MAPY_API_KEY}"
      - THUNDERFOREST_API_KEY="${THUNDERFOREST_API_KEY}"
      - FAST_SYNC="*/15 * * * *"
      - FULL_SYNC="0 3 * * *"
      - WEB_LOGIN=admin
      - WEB_PASSWORD="${KINETIQO_WEB_PASSWORD}"
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
      - GF_SECURITY_ADMIN_PASSWORD={GRAFANA_ADMIN_PASSWORD}
    depends_on:
      - postgresql
volumes:
  postgresql_data:
```

- For MySQL or Firebird, replace the `postgresql` service and environment variables accordingly.

Create a `.env` file in the same directory:

```env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
STRAVA_REFRESH_TOKEN=your_strava_refresh_token
POSTGRESQL_PASSWORD=your_secure_password
GRAFANA_ADMIN_PASSWORD=your_grafana_admin_password
MAPY_API_KEY=your_mapy_com_api_token
THUNDERFOREST_API_KEY=your_thunderforest_api_token
KINETIQO_WEB_PASSWORD=your_password_for_web_interface
```

Deploy the stack:

```bash
docker-compose up -d
```

## Docker Build & CI/CD

Kinetiqo uses a two-phase Docker build for fast iteration and Firebird support:

- **Phase 1 (Base):** Compiles Firebird client, rarely rebuilt. See `build/Dockerfile.firebird-base` and `build-base.sh`.
- **Phase 2 (App):** Installs app code and dependencies. See `build/Dockerfile` and `build.sh`.

For local builds:

```bash
cd build
./build-base.sh   # Only needed if Python or Firebird version changes
./build.sh        # Build the app image
```

See the [README](https://github.com/lhotakj/kinetiqo#building-docker-images) for full details.

## CI/CD Workflows

- **Build Firebird Python Base Image:** `.github/workflows/build-base-image.yaml` (manual trigger)
- **Build and publish Docker image:** `.github/workflows/build.yaml` (manual or push to main)

## Troubleshooting

- All logs are available via the Web UI or `docker logs`.
- Synchronization errors are recorded in the `logs` database table.
- For advanced troubleshooting, see [Troubleshooting](troubleshooting.md) (to be created).

For more details and advanced configuration, see the project documentation at [kinetiqo.lhotak.net](https://kinetiqo.lhotak.net).
