---
layout: default
title: Home
nav_order: 1
---

# Local Development

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

```
STRAVA_CLIENT_ID=12345
STRAVA_CLIENT_SECRET=your_secret_here
STRAVA_REFRESH_TOKEN=your_refresh_token_here
DATABASE_TYPE=firebird  # or postgresql or mysql

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

For advanced environment handling and safe secret persistence in GitHub, see the [Direnv setup](direnv-setup.md).

## 4. Run the Application

- **CLI:**
  ```bash
  python -m kinetiqo.cli --help
  ```
- **Web UI:**
  ```bash
  python -m kinetiqo.web.app
  # or use gunicorn for production
  gunicorn -b 0.0.0.0:4444 kinetiqo.web.app:app
  ```

## 5. Database Support

- **PostgreSQL**: version 18+
- **MySQL**: version 8+ / MariaDB 12+
- **Firebird**: versions 3.0, 4.0, 5.0

## 6. Additional Notes

- All dependencies are listed in `requirements.txt`.
- For Docker-based development, see `build/docker-overview.md`.

