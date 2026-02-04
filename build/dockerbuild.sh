#!/bin/sh

(
cd ../src
ls -al
echo "[INFO] Reading version ..."
export VERSION=$(cat ./version.template)

if [ -n "$GITHUB_RUN_ID" ]; then
  echo "[INFO] Using GITHUB_RUN_ID value $GITHUB_RUN_ID"
  VERSION=$(echo $VERSION | awk -F. -v runid="$GITHUB_RUN_ID" '{print $1"."$2"."runid}')
else
  VERSION=$(echo $VERSION | awk -F. -v runid="dev" '{print $1"."$2"."runid}')
  echo "[WARN] GITHUB_RUN_ID is not set. Using 'dev' instead."
fi

echo "$VERSION" > ./version.txt

echo "[INFO] Building version ${VERSION} ..."
docker build \
  --no-cache \
  --build-arg VERSION=${VERSION} \
  -t kinetiqo:latest \
  -t kinetiqo:${VERSION} \
  -f ../build/Dockerfile \
  ..

echo "[INFO] Built image size:"
docker image ls kinetiqo:${VERSION}
)
