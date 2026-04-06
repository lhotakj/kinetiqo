---
layout: default
title: Home
nav_order: 1
---

# Local Development

This guide covers setting up a local development environment for Kinetiqo.

## 1. Clone the Repository

```bash
git clone https://github.com/lhotakj/kinetiqo.git
cd kinetiqo
```

## 2. Initialize Virtual Environment

```bash
python -m venv .venv
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure Environment Variables

Create a `.env` file in the project root to define your configuration. This file is excluded from version control.

### Example `.env` file

```env
STRAVA_CLIENT_ID=12345
STRAVA_CLIENT_SECRET=your_secret_here
STRAVA_REFRESH_TOKEN=your_refresh_token_here
DATABASE_TYPE=postgresql  # or firebird or mysql

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

# Map API keys (optional)
MAPY_API_KEY=your_mapy_com_api_token
THUNDERFOREST_API_KEY=your_thunderforest_api_token
```

- Set `DATABASE_TYPE` to `postgresql`, `mysql`, or `firebird` as needed.
- Only the relevant database section is required for your selected type.

For advanced environment handling and secure secret storage, see the [Direnv setup](direnv-setup.md).

## 4. Run the Application

- **CLI:**
  ```bash
  python src/kinetiqo.py --help
  ```
- **Web UI:**
  ```bash
  python src/kinetiqo.py web
  # or use gunicorn for production
  gunicorn -b 0.0.0.0:4444 kinetiqo.web.app:app
  ```

## 5. Database Support

- **PostgreSQL**: version 12+
- **MySQL**: version 8+ / MariaDB 10+
- **Firebird**: versions 3.0, 4.0, 5.0

## 6. Testing

- All dependencies are listed in `requirements.txt`.
- Run unit tests with:
  ```bash
  PYTHONPATH=src python -m unittest discover -s tests -v
  ```
- All external dependencies (database, Strava API) are mocked in tests.

## 7. Docker-based Development

- For Docker-based development, see `build/docker-overview.md` and [Deployment](deployment.md).

## 8. Additional Notes

- For secure secret storage, see [Direnv setup](direnv-setup.md).
- For advanced configuration, see [Configuration](configuration.md).
