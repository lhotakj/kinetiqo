#!/bin/sh
# export FAST_SYNC="0 * * * *"
export FAST_SYNC="*/1 * * * *"

# Unique container name to ensure we can stop it
CONTAINER_NAME="kinetiqo-test-$$"

# Cleanup function to stop the container
cleanup() {
    echo "Stopping container..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1
    echo "Removing container..."
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1
}

# Trap signals (EXIT, SIGINT, SIGTERM) to run cleanup
trap cleanup EXIT INT TERM

FIREBIRD_HOST='10.0.0.100'

docker run --rm \
   --name "$CONTAINER_NAME" \
   -e FAST_SYNC="${FAST_SYNC}" \
   -e STRAVA_CLIENT_ID="${STRAVA_CLIENT_ID}" \
   -e STRAVA_CLIENT_SECRET="${STRAVA_CLIENT_SECRET}" \
   -e STRAVA_REFRESH_TOKEN="${STRAVA_REFRESH_TOKEN}" \
   -e DATABASE_TYPE="firebird" \
   -e FIREBIRD_HOST="${FIREBIRD_HOST}" \
   -e FIREBIRD_PORT="${FIREBIRD_PORT}" \
   -e FIREBIRD_USER="${FIREBIRD_USER}" \
   -e FIREBIRD_PASSWORD="${FIREBIRD_PASSWORD}" \
   -e FIREBIRD_DATABASE="${FIREBIRD_DATABASE}" \
   -e WEB_LOGIN="${WEB_LOGIN}" \
   -e WEB_PASSWORD="${WEB_PASSWORD}" \
   -p "4444:4444" \
   kinetiqo:latest
