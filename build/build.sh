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
cd ../src
info "Reading version ..."
export VERSION=$(cat ./version.template)

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
      --build-arg VERSION=${SHORT_VERSION} \
      -t ${DOCKER_USERNAME}/kinetiqo:latest \
      -t ${DOCKER_USERNAME}/kinetiqo:${SHORT_VERSION} \
      -t ${DOCKER_USERNAME}/kinetiqo:${VERSION} \
      -f ../build/Dockerfile \
      --push \
      ..
else
    info "Building locally version ${VERSION} (Short: ${SHORT_VERSION}) for linux/amd64 ..."
    docker buildx build \
      --platform linux/amd64 \
      --load \
      --no-cache \
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
