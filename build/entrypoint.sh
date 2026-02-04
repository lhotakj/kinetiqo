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
  echo "$FULL_SYNC python3 /app/kinetiqo.py --full-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  echo "[INFO] Adding full sync to cron: $FULL_SYNC"
  CRON_ADDED=1
else
  echo "[WARN] No full sync set"
fi

if [ "$FAST_SYNC" != "" ]; then
  echo "$FAST_SYNC python3 /app/kinetiqo.py --fast-sync >> /proc/1/fd/1 2>&1" >> $CRONFILE
  echo "[INFO] Adding fast sync to cron: ${FAST_SYNC}"
  CRON_ADDED=1
else
  echo "[WARN] No fast sync set"

fi

if [ $CRON_ADDED -eq 1 ]; then
  crontab $CRONFILE
  crond -f
  echo "[INFO] Cron installed"
else
  echo "[WARN] No cron jobs defined. Exiting..."
  exit 1
fi

echo "[INFO] Check version"
python3 /app/kinetiqo.py --version

# Keep the container running
tail -f /dev/null
