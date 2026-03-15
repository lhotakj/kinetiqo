#!/bin/sh
# build.sh — Build and (optionally) push the Kinetiqo application image.
#
# This script builds the APPLICATION image only. It relies on the pre-built
# lhotakj/firebird-python base image which already contains the compiled
# Firebird 5.x client library (~40-minute compilation step is NOT run here).
#
# To rebuild the base image (needed only when upgrading Python or Firebird):
#   ./build-base.sh              # locally
#   GitHub Actions → "Build Firebird Python Base Image" (manual trigger)
#
# Usage:
#   ./build.sh           # build locally for linux/amd64
#   ./build.sh --push    # build for amd64+arm64 and push to DockerHub

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

# Default values
PUSH_FLAG=""
DOCKER_USERNAME="lhotakj"

# Parse command-line arguments
for arg in "$@"
do
    case $arg in
        --push)
        PUSH_FLAG="--push"
        shift
        ;;
    esac
done

(
cd ../src || exit 1
info "Reading version ..."
VERSION=$(cat ./version.template)
export VERSION

if [ -n "$GITHUB_RUN_NUMBER" ]; then
  info "Using GITHUB_RUN_NUMBER value $GITHUB_RUN_NUMBER"
  VERSION=$(echo $VERSION | awk -F. -v runid="$GITHUB_RUN_NUMBER" '{print $1"."$2"."runid}')
else
  VERSION=$(echo $VERSION | awk -F. -v runid="dev" '{print $1"."$2"."runid}')
  warn "GITHUB_RUN_NUMBER is not set. Using 'dev' instead."
fi

SHORT_VERSION=$(echo $VERSION | cut -d. -f1,2)

echo "$VERSION" > ./version.txt
echo "$SHORT_VERSION" > ./short_version.txt

if [ -n "$PUSH_FLAG" ]; then
    info "Building and pushing version ${VERSION} (Short: ${SHORT_VERSION}) for linux/amd64 and linux/arm64 ..."
    docker buildx build \
      --platform linux/amd64,linux/arm64 \
      --no-cache \
      --pull=true \
      --build-arg VERSION=${SHORT_VERSION} \
      -t ${DOCKER_USERNAME}/kinetiqo:latest \
      -t ${DOCKER_USERNAME}/kinetiqo:${SHORT_VERSION} \
      -t ${DOCKER_USERNAME}/kinetiqo:${VERSION} \
      -f ../build/Dockerfile \
      --push \
      ..
else
    # On CI (GITHUB_ACTIONS=true) pull the base image from DockerHub even in
    # the non-push path (fresh runner has no local image cache).
    # Locally, use --pull=false so Docker uses the image loaded by build-base.sh
    # instead of hitting DockerHub before you have published the base image.
    if [ -n "$GITHUB_ACTIONS" ]; then
      PULL_FLAG="--pull=true"
      info "CI environment detected — base image will be pulled from DockerHub."
    else
      PULL_FLAG="--pull=false"
      info "Using locally cached base image (lhotakj/firebird-python:3.13) — run build-base.sh first if missing."
    fi

    info "Building locally version ${VERSION} (Short: ${SHORT_VERSION}) for linux/amd64 ..."
    docker buildx build \
      --platform linux/amd64 \
      --load \
      --no-cache \
      ${PULL_FLAG} \
      --build-arg VERSION=${SHORT_VERSION} \
      -t ${DOCKER_USERNAME}/kinetiqo:latest \
      -t ${DOCKER_USERNAME}/kinetiqo:${SHORT_VERSION} \
      -t ${DOCKER_USERNAME}/kinetiqo:${VERSION} \
      -f ../build/Dockerfile \
      ..

    info "Built image size:"
    docker image ls ${DOCKER_USERNAME}/kinetiqo:${SHORT_VERSION}
fi
)
