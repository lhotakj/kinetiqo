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

docker run --rm \
   -e FAST_SYNC="${FAST_SYNC}" \
   -e STRAVA_CLIENT_ID="${STRAVA_CLIENT_ID}" \
   -e STRAVA_CLIENT_SECRET="${STRAVA_CLIENT_SECRET}" \
   -e STRAVA_REFRESH_TOKEN="${STRAVA_REFRESH_TOKEN}" \
   -e POSTGRESQL_HOST="${POSTGRESQL_HOST}" \
   -e POSTGRESQL_PORT="${POSTGRESQL_PORT}" \
   -e POSTGRESQL_USER="${POSTGRESQL_USER}" \
   -e POSTGRESQL_PASSWORD="${POSTGRESQL_PASSWORD}" \
   -e POSTGRESQL_DATABASE="${POSTGRESQL_DATABASE}" \
   kinetiqo:latest