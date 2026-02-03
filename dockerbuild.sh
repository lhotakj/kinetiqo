#!/bin/sh

echo "[INFO] Reading version ..."
export VERSION=$(cat ./version.txt)

if [ -n "$GITHUB_RUN_ID" ]; then
  echo "[INFO] Using GITHUB_RUN_ID value $GITHUB_RUN_ID"
  VERSION=$(echo $VERSION | awk -F. -v runid="$GITHUB_RUN_ID" '{print $1"."$2"."runid}')
else
  echo "[WARN] GITHUB_RUN_ID is not set. Using version from version.txt."
fi

echo "[INFO] Building version ${VERSION} ..."
docker build \
  --no-cache \
  --build-arg VERSION=${VERSION} \
  -t kinetiqo:latest \
  -t kinetiqo:${VERSION} \
  .

echo "[INFO] Built image size:"
docker image ls kinetiqo:${VERSION}