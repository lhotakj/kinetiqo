---
layout: default
title: Troubleshooting
nav_order: 99
---

# Troubleshooting

This page covers common issues and solutions for Kinetiqo. For further help, see the [official documentation](https://kinetiqo.lhotak.net) or open an issue on GitHub.

## General Tips
- Always check logs in the Web UI (Logs page) or with `docker logs kinetiqo`.
- Ensure all environment variables are set correctly (see [Configuration](configuration.md)).
- For database issues, verify connectivity and credentials.
- For Strava sync issues, check your Strava API credentials and token scopes.

## Common Issues

### 1. Database Connection Errors
- **Symptom:** App fails to start or sync, error about database connection.
- **Solution:**
  - Check `DATABASE_TYPE` and all relevant database environment variables.
  - Ensure the database server is running and accessible from the container.
  - For Firebird, ensure the user has rights to create databases/tables.

### 2. Strava API Errors
- **Symptom:** Sync fails, error about Strava API or invalid token.
- **Solution:**
  - Double-check `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and `STRAVA_REFRESH_TOKEN`.
  - Ensure the refresh token has `activity:read_all` scope.
  - If revoked, re-authorize the app in Strava and update the token.

### 3. Web UI Not Loading
- **Symptom:** Cannot access the web interface at the expected port.
- **Solution:**
  - Check the container is running (`docker ps`).
  - Verify the port mapping (`-p 8080:4444` or as configured).
  - Check for errors in the container logs.

### 4. Sync Progress Not Updating
- **Symptom:** Sync progress bar does not update in real time.
- **Solution:**
  - Ensure your browser supports Server-Sent Events (SSE).
  - Check for JavaScript errors in the browser console.
  - Verify the backend is not blocked by a reverse proxy/firewall.

### 5. Map Layers Greyed Out
- **Symptom:** Some map layers are disabled in the map selector.
- **Solution:**
  - Set the required API keys (`MAPY_API_KEY`, `THUNDERFOREST_API_KEY`) in your environment.
  - See [Configuration](configuration.md#6-map-configuration) for details.

### 6. Docker Build or CI/CD Fails
- **Symptom:** Docker build fails, especially on Firebird base image.
- **Solution:**
  - Ensure you are using the correct build scripts (`build-base.sh`, `build.sh`).
  - For CI/CD, check the workflow logs in GitHub Actions.

## Advanced Debugging
- Use `python src/kinetiqo.py flightcheck` to validate database connectivity and schema.
- For more verbose logs, set the `LOGURU_LEVEL` environment variable to `DEBUG` (for CLI/sync) or adjust logging in the web UI.
- For issues with environment variable loading, use [direnv](direnv-setup.md) or check your `.env` file.

## Getting Help
- See the [official documentation](https://kinetiqo.lhotak.net).
- Open an issue at [github.com/lhotakj/kinetiqo/issues](https://github.com/lhotakj/kinetiqo/issues).
- For feature requests or advanced troubleshooting, contact the maintainer via GitHub.

