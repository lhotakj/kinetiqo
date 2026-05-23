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

# ---------------------------------------------------------------------------
# Write ALL current environment variables to the crontab header BEFORE any
# job entries. BusyBox crond (Alpine) does not inherit the Docker container
# environment, so we snapshot it here. Any new variable added to the
# container is picked up automatically — no manual list to maintain.
# ---------------------------------------------------------------------------
{
  echo "SHELL=/bin/sh"
  echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  echo ""
  # Loop through every variable present at container startup.
  # `printenv` outputs NAME=VALUE, one per line.
  # We split on the first `=` only, then double-quote the value so that
  # entries containing spaces are handled correctly by BusyBox crond.
  printenv | while IFS= read -r line; do
    var_name="${line%%=*}"
    var_value="${line#*=}"
    # Skip the shell's internal `_` variable (last-command path) — it changes
    # with every command and has no meaning inside a cron job.
    [ "$var_name" = "_" ] && continue
    # Escape any embedded double-quotes so the crontab line stays valid.
    var_value=$(printf '%s' "$var_value" | sed 's/"/\\"/g')
    printf '%s="%s"\n' "$var_name" "$var_value"
  done
  echo ""
} >> $CRONFILE

# ---------------------------------------------------------------------------
# Append cron job entries AFTER the environment variable block
# ---------------------------------------------------------------------------
if [ "$FULL_SYNC" != "" ]; then
  echo "$FULL_SYNC $PYTHON_PATH /app/kinetiqo.py sync --full-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  info "Adding full sync to cron: $FULL_SYNC"
  CRON_ADDED=1
else
  warn "No full sync schedule set (FULL_SYNC is empty)"
fi

if [ "$FAST_SYNC" != "" ]; then
  echo "$FAST_SYNC $PYTHON_PATH /app/kinetiqo.py sync --fast-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  info "Adding fast sync to cron: ${FAST_SYNC}"
  CRON_ADDED=1
else
  warn "No fast sync schedule set (FAST_SYNC is empty)"
fi

if [ $CRON_ADDED -eq 1 ]; then
  crontab $CRONFILE
  # Start Debian cron daemon in foreground mode, backgrounded so exec "$@"
  # can proceed. `-f` keeps it in the foreground (no double-fork) so the
  # process is visible and its output goes to docker logs.
  cron -f &
  info "Cron daemon started (PID $!)"
fi

# Execute the command passed to docker run
exec "$@"