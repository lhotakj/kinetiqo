#!/bin/sh
set -e
# entrypoint.sh

VERSION=$(cat /app/version.txt)


# Logging functions
info() {
    printf "\033[0;32m[INFO]\033[0m %s\n"  "$1"
}

debug() {
    printf "\033[0;90m[DEBUG]\033[0m %s\n" "$1"
}

error() {
    printf "\033[0;31m[ERROR]\033[0m %s\n" "$1"
}

warn() {
    printf "\033[0;33m[WARN]\033[0m %s\n"  "$1"
}

echo "   _     _                   _"
echo "  | |   (_)              _  (_)"
echo "  | |  _ _ ____  _____ _| |_ _  ____  ___"
echo "  | |_/ ) |  _ \| ___ (_   _) |/ _  |/ _ \ "
echo "  |  _ (| | | | | ____| | |_| | |_| | |_| |"
echo "  |_| \_)_|_| |_|_____)  \__)_|\__  |\___/ "
echo "                                  |_|      "
echo ""
info " Starting Kinetiqo v.${VERSION} ..."

CRON_ADDED=0
CRONFILE=/tmp/crontab
PYTHON_PATH="/usr/local/bin/python"

info "Check Python version"
$PYTHON_PATH --version

info "Check version"
$PYTHON_PATH /app/kinetiqo.py version

info "Flight check"
$PYTHON_PATH /app/kinetiqo.py flightcheck

# shellcheck disable=SC2188
> $CRONFILE

if [ "$FULL_SYNC" != "" ]; then
  echo "$FULL_SYNC $PYTHON_PATH /app/kinetiqo.py sync --full-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  info "Adding full sync to cron: $FULL_SYNC"
  CRON_ADDED=1
else
  echo "[WARN] No full sync set"
fi

if [ "$FAST_SYNC" != "" ]; then
  echo "$FAST_SYNC $PYTHON_PATH /app/kinetiqo.py sync --fast-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  info "Adding fast sync to cron: ${FAST_SYNC}"
  CRON_ADDED=1
else
  warn "No fast sync set"
fi

if [ $CRON_ADDED -eq 1 ]; then
  # Add environment variables to crontab so cron jobs can access them
  {
    echo "STRAVA_CLIENT_ID=$STRAVA_CLIENT_ID"
    echo "STRAVA_CLIENT_SECRET=$STRAVA_CLIENT_SECRET"
    echo "SECRET_KEY=$SECRET_KEY"
    echo ""
  } >> $CRONFILE
  crontab $CRONFILE
  # Start cron daemon in background
  crond -f -l 2 &
  info "Cron daemon started in background"
fi

# Execute the command passed to docker run
exec "$@"