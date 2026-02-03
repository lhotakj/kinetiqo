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
   -e QUESTDB_HOST="${QUESTDB_HOST}" \
   -e QUESTDB_PORT="${QUESTDB_PORT}" \
   -e QUESTDB_USER="${QUESTDB_USER}" \
   -e QUESTDB_PASSWORD="${QUESTDB_PASSWORD}" \
   -e QUESTDB_DATABASE="${QUESTDB_DATABASE}" \
   kinetiqo:latest