#!/bin/sh

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


(
cd ../src
ls -al
info "Reading version ..."
export VERSION=$(cat ./version.template)

if [ -n "$GITHUB_RUN_ID" ]; then
  info "Using GITHUB_RUN_ID value $GITHUB_RUN_ID"
  VERSION=$(echo $VERSION | awk -F. -v runid="$GITHUB_RUN_ID" '{print $1"."$2"."runid}')
else
  VERSION=$(echo $VERSION | awk -F. -v runid="dev" '{print $1"."$2"."runid}')
  warn "GITHUB_RUN_ID is not set. Using 'dev' instead."
fi

echo "$VERSION" > ./version.txt

info "Building version ${VERSION} ..."
docker build \
  --no-cache \
  --build-arg VERSION=${VERSION} \
  -t kinetiqo:latest \
  -t kinetiqo:${VERSION} \
  -f ../build/Dockerfile \
  ..

info "Built image size:"
docker image ls kinetiqo:${VERSION}
)
