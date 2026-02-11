#!/bin/sh
# entrypoint.sh

VERSION=$(cat /app/version.txt)

echo "   _     _                   _"
echo "  | |   (_)              _  (_)"
echo "  | |  _ _ ____  _____ _| |_ _  ____  ___"
echo "  | |_/ ) |  _ \| ___ (_   _) |/ _  |/ _ \ "
echo "  |  _ (| | | | | ____| | |_| | |_| | |_| |"
echo "  |_| \_)_|_| |_|_____)  \__)_|\__  |\___/ "
echo "                                  |_|      "
echo ""
echo "[INFO] Starting Kinetiqo v.${VERSION} ..."

CRON_ADDED=0
CRONFILE=/tmp/crontab

# shellcheck disable=SC2188
> $CRONFILE

if [ "$FULL_SYNC" != "" ]; then
  echo "$FULL_SYNC python3 /app/kinetiqo.py sync --full-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  echo "[INFO] Adding full sync to cron: $FULL_SYNC"
  CRON_ADDED=1
else
  echo "[WARN] No full sync set"
fi

if [ "$FAST_SYNC" != "" ]; then
  echo "$FAST_SYNC python3 /app/kinetiqo.py sync --fast-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  echo "[INFO] Adding fast sync to cron: ${FAST_SYNC}"
  CRON_ADDED=1
else
  echo "[WARN] No fast sync set"
fi

if [ $CRON_ADDED -eq 1 ]; then
  crontab $CRONFILE
  # Start cron in background
  crond -b -L /dev/stdout
  echo "[INFO] Cron started in background"
fi

echo "[INFO] Check version"
python3 /app/kinetiqo.py --version

# Execute the command passed to docker run
exec "$@"