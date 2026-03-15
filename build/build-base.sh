#!/bin/sh
# build-base.sh — Local helper to build and (optionally) push the
# lhotakj/firebird-python base image.
#
# Usage:
#   ./build-base.sh                  # build locally for linux/amd64 only
#   ./build-base.sh --push           # build for amd64+arm64 and push to DockerHub
#   ./build-base.sh --push --python 3.13 --firebird 5.0.3

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

# Defaults
PUSH_FLAG=""
PYTHON_VERSION="3.13"
FIREBIRD_VERSION="5.0.3"
DOCKER_USERNAME="lhotakj"

# Parse arguments
while [ "$#" -gt 0 ]; do
    case "$1" in
        --push)
            PUSH_FLAG="--push"
            shift
            ;;
        --python)
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --firebird)
            FIREBIRD_VERSION="$2"
            shift 2
            ;;
        *)
            warn "Unknown argument: $1"
            shift
            ;;
    esac
done

IMAGE="${DOCKER_USERNAME}/firebird-python"
TAG_VERSION="${PYTHON_VERSION}"
TAG_FULL="${PYTHON_VERSION}-firebird${FIREBIRD_VERSION}"

info "Building base image: ${IMAGE}:${TAG_VERSION}"
info "  Python version  : ${PYTHON_VERSION}"
info "  Firebird version: ${FIREBIRD_VERSION}"

# Move to repo root so Docker context is correct
cd "$(dirname "$0")/.." || exit 1

if [ -n "$PUSH_FLAG" ]; then
    info "Building for linux/amd64 and linux/arm64, then pushing ..."
    docker buildx build \
        --platform linux/amd64,linux/arm64 \
        --no-cache \
        --build-arg PYTHON_VERSION="${PYTHON_VERSION}" \
        --build-arg FIREBIRD_VERSION="${FIREBIRD_VERSION}" \
        -t "${IMAGE}:${TAG_VERSION}" \
        -t "${IMAGE}:${TAG_FULL}" \
        -f build/Dockerfile.firebird-base \
        --push \
        .
else
    info "Building locally for linux/amd64 only (use --push to publish) ..."
    docker buildx build \
        --platform linux/amd64 \
        --load \
        --no-cache \
        --build-arg PYTHON_VERSION="${PYTHON_VERSION}" \
        --build-arg FIREBIRD_VERSION="${FIREBIRD_VERSION}" \
        -t "${IMAGE}:${TAG_VERSION}" \
        -t "${IMAGE}:${TAG_FULL}" \
        -f build/Dockerfile.firebird-base \
        .

    info "Built image size:"
    docker image ls "${IMAGE}:${TAG_VERSION}"
fi

