#!/usr/bin/env bash
# build.sh — Unified build script for Kinetiqo Docker images.
#
# Manages all Kinetiqo images:
#   • base:  kinetiqo/firebird-python:3.14 (compiled Firebird 5.x client + Chromium)
#   • web:   kinetiqo/web                  (standalone web dashboard + cron sync)
#   • mcp:   kinetiqo/web-mcp              (integrated web dashboard + FastMCP SSE)
#   • all:   Builds base -> web -> mcp in proper order
#
# Usage:
#   ./build.sh <TARGET> [OPTIONS]
#
# Mandatory Targets (specify at least one):
#   base                  Build Firebird + Python base image
#   web                   Build standalone Kinetiqo web image
#   mcp                   Build Kinetiqo + FastMCP image
#   all                   Build all images in order: base -> web -> mcp
#
# Options:
#   --push                Build multi-arch (linux/amd64,linux/arm64) and push to Docker Hub
#   -u, --username USER   Docker Hub username for login (default: $DOCKER_USERNAME or 'kinetiqo')
#   -t, --token TOKEN     Docker Hub access token or password (default: $DOCKER_TOKEN)
#   --org ORG             Docker repository namespace / org (default: $DOCKER_ORG or 'kinetiqo')
#   --python VER          Python base version for base image (default: 3.14)
#   --firebird VER        Firebird version for base image (default: 5.0.4)
#   --dry-run             Simulate build steps without running Docker commands
#   -h, --help            Show this help message

set -e

# ANSI Color Codes (enabled on TTY and GitHub Actions)
if [[ -t 1 || -n "${GITHUB_ACTIONS:-}" ]] && [[ "${TERM:-}" != "dumb" ]]; then
    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_DIM=$'\033[2m'
    C_UNDERLINE=$'\033[4m'
    C_RED=$'\033[1;31m'
    C_GREEN=$'\033[1;32m'
    C_YELLOW=$'\033[1;33m'
    C_BLUE=$'\033[1;34m'
    C_MAGENTA=$'\033[1;35m'
    C_CYAN=$'\033[1;36m'
    C_WHITE=$'\033[1;37m'
    C_GRAY=$'\033[0;90m'
else
    C_RESET=""
    C_BOLD=""
    C_DIM=""
    C_UNDERLINE=""
    C_RED=""
    C_GREEN=""
    C_YELLOW=""
    C_BLUE=""
    C_MAGENTA=""
    C_CYAN=""
    C_WHITE=""
    C_GRAY=""
fi

# Logging functions (info in red as requested)
info() {
    printf "${C_RED}[INFO]${C_RESET} %s\n" "$1"
}

debug() {
    printf "${C_GRAY}[DEBUG]${C_RESET} %s\n" "$1"
}

error() {
    printf "${C_BOLD}${C_RED}[ERROR]${C_RESET} ${C_BOLD}%s${C_RESET}\n" "$1"
}

warn() {
    printf "${C_YELLOW}[WARN]${C_RESET} %s\n" "$1"
}

success() {
    printf "${C_GREEN}[SUCCESS]${C_RESET} ${C_BOLD}%s${C_RESET}\n" "$1"
}

target_header() {
    echo ""
    printf "${C_BOLD}${C_CYAN}━━━ [TARGET: ${C_WHITE}%s${C_CYAN}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}\n" "$1"
}

# Colorized Help
show_help() {
    echo -e "${C_BOLD}${C_CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║                          ${C_WHITE}KINETIQO DOCKER BUILD${C_CYAN}                               ║
╚══════════════════════════════════════════════════════════════════════════════╝${C_RESET}

${C_BOLD}${C_YELLOW}USAGE:${C_RESET}
  ${C_BOLD}./build.sh${C_RESET} ${C_GREEN}<TARGET>${C_RESET} ${C_CYAN}[OPTIONS]${C_RESET}

${C_BOLD}${C_MAGENTA}MANDATORY TARGETS:${C_RESET} ${C_DIM}(specify at least one)${C_RESET}
  ${C_BOLD}${C_GREEN}base${C_RESET}                   Compile Firebird 5.x client + Chromium base image
                         ${C_DIM}Tag: ${C_WHITE}${DOCKER_ORG}/firebird-python:3.14${C_RESET}
  ${C_BOLD}${C_GREEN}web${C_RESET}                    Build standalone Kinetiqo web application
                         ${C_DIM}Tag: ${C_WHITE}${DOCKER_ORG}/web:latest${C_RESET}
  ${C_BOLD}${C_GREEN}mcp${C_RESET}                    Build integrated Kinetiqo + FastMCP application
                         ${C_DIM}Tag: ${C_WHITE}${DOCKER_ORG}/web-mcp:latest${C_RESET}
  ${C_BOLD}${C_GREEN}all${C_RESET}                    Build all images in sequence: ${C_BOLD}base${C_RESET} → ${C_BOLD}web${C_RESET} → ${C_BOLD}mcp${C_RESET}

${C_BOLD}${C_MAGENTA}OPTIONS:${C_RESET}
  ${C_BOLD}${C_CYAN}--push${C_RESET}                 Build multi-arch (${C_WHITE}linux/amd64,linux/arm64${C_RESET}) and push to Docker Hub
  ${C_BOLD}${C_CYAN}-u, --username${C_RESET} ${C_YELLOW}USER${C_RESET}    Docker Hub login username ${C_DIM}(default: \$DOCKER_USERNAME or '${DOCKER_ORG}')${C_RESET}
  ${C_BOLD}${C_CYAN}-t, --token${C_RESET} ${C_YELLOW}TOKEN${C_RESET}      Docker Hub access token or password ${C_DIM}(default: \$DOCKER_TOKEN)${C_RESET}
  ${C_BOLD}${C_CYAN}--org${C_RESET} ${C_YELLOW}ORG${C_RESET}              Docker Hub repository namespace ${C_DIM}(default: \$DOCKER_ORG or '${DOCKER_ORG}')${C_RESET}
  ${C_BOLD}${C_CYAN}--python${C_RESET} ${C_YELLOW}VER${C_RESET}           Python base version for base image ${C_DIM}(default: 3.14)${C_RESET}
  ${C_BOLD}${C_CYAN}--firebird${C_RESET} ${C_YELLOW}VER${C_RESET}         Firebird version for base image ${C_DIM}(default: 5.0.4)${C_RESET}
  ${C_BOLD}${C_CYAN}--dry-run${C_RESET}              Simulate build steps and print commands without invoking Docker
  ${C_BOLD}${C_CYAN}-h, --help${C_RESET}             Show this help message

${C_BOLD}${C_MAGENTA}EXAMPLES:${C_RESET}
  ${C_DIM}# Local builds (linux/amd64, no push, no login required):${C_RESET}
  ${C_WHITE}./build.sh web${C_RESET}
  ${C_WHITE}./build.sh mcp${C_RESET}
  ${C_WHITE}./build.sh base${C_RESET}
  ${C_WHITE}./build.sh all${C_RESET}

  ${C_DIM}# Multi-arch publishing to Docker Hub (executes docker login):${C_RESET}
  ${C_WHITE}./build.sh web --push${C_RESET}
  ${C_WHITE}./build.sh all --push -u kinetiqo -t dckr_pat_...${C_RESET}

  ${C_DIM}# Dry-run simulation:${C_RESET}
  ${C_WHITE}./build.sh all --dry-run${C_RESET}
  ${C_WHITE}./build.sh web mcp --push --dry-run${C_RESET}"
}

# Default values
TARGETS=()
PUSH_FLAG=""
DRY_RUN="${DRY_RUN:-false}"
PYTHON_VERSION="3.14"
FIREBIRD_VERSION="5.0.4"
DOCKER_ORG="${DOCKER_ORG:-kinetiqo}"
DOCKER_USERNAME="${DOCKER_USERNAME:-${DOCKERHUB_USERNAME:-$DOCKER_ORG}}"
DOCKER_TOKEN="${DOCKER_TOKEN:-${DOCKERHUB_TOKEN:-${DOCKER_PASSWORD:-}}}"
TIMESTAMP=$(date +%Y%m%d%H%M%S)

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        base|web|mcp|all)
            TARGETS+=("$1")
            shift
            ;;
        --push)
            PUSH_FLAG="--push"
            shift
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --username|-u)
            DOCKER_USERNAME="$2"
            shift 2
            ;;
        --token|-t)
            DOCKER_TOKEN="$2"
            shift 2
            ;;
        --org)
            DOCKER_ORG="$2"
            shift 2
            ;;
        --python)
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --firebird)
            FIREBIRD_VERSION="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            error "Unknown argument: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
done

# Validate mandatory target
if [[ ${#TARGETS[@]} -eq 0 ]]; then
    error "Missing mandatory target argument: base | web | mcp | all"
    echo ""
    show_help
    exit 1
fi

# Resolve directories (run all builds relative to repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# Command execution wrapper supporting dry-run simulation
run_docker() {
    if [[ "$DRY_RUN" == "true" ]]; then
        info "${C_YELLOW}[DRY-RUN]${C_RESET} ${C_DIM}docker $*${C_RESET}"
        return 0
    fi
    docker "$@"
}

# Docker Hub login helper (executed only when --push is set)
docker_login() {
    info "Preparing Docker Hub authentication..."
    if [[ "$DRY_RUN" == "true" ]]; then
        info "${C_YELLOW}[DRY-RUN]${C_RESET} Simulated docker login for user '${C_WHITE}${DOCKER_USERNAME}${C_RESET}'"
        return 0
    fi
    if [[ -n "$DOCKER_TOKEN" ]]; then
        info "Logging in to Docker Hub as '${C_WHITE}${DOCKER_USERNAME}${C_RESET}'..."
        if echo "$DOCKER_TOKEN" | docker login -u "$DOCKER_USERNAME" --password-stdin; then
            success "Docker Hub login successful."
        else
            error "Docker Hub login failed. Check DOCKER_USERNAME and DOCKER_TOKEN."
            exit 1
        fi
    elif [[ -t 0 ]]; then
        # Interactive session: prompt the user
        warn "Docker credentials not found in environment."
        read -r -p "Enter Docker Hub username [${DOCKER_USERNAME}]: " INPUT_USER
        if [[ -n "$INPUT_USER" ]]; then
            DOCKER_USERNAME="$INPUT_USER"
        fi
        read -r -s -p "Enter Docker Hub access token or password: " DOCKER_TOKEN
        echo ""
        if [[ -z "$DOCKER_TOKEN" ]]; then
            error "Docker token/password cannot be empty when pushing."
            exit 1
        fi
        info "Logging in to Docker Hub as '${C_WHITE}${DOCKER_USERNAME}${C_RESET}'..."
        if echo "$DOCKER_TOKEN" | docker login -u "$DOCKER_USERNAME" --password-stdin; then
            success "Docker Hub login successful."
        else
            error "Docker Hub login failed. Check credentials."
            exit 1
        fi
    else
        # Non-interactive session without explicit token
        if [[ -n "$GITHUB_ACTIONS" ]]; then
            info "Running in GitHub Actions without explicit DOCKER_TOKEN; proceeding with session established by workflow."
        else
            warn "DOCKER_TOKEN is not set and shell is non-interactive; proceeding with existing Docker credentials..."
        fi
    fi
}

# Version loader for application targets (web / mcp)
VERSION=""
SHORT_VERSION=""
load_version() {
    if [[ -n "$VERSION" && -n "$SHORT_VERSION" ]]; then
        return 0
    fi
    info "Reading version from ${C_CYAN}src/version.template${C_RESET} ..."
    VERSION=$(cat src/version.template)
    if [[ -n "$GITHUB_RUN_NUMBER" ]]; then
        info "Using GITHUB_RUN_NUMBER value ${C_YELLOW}$GITHUB_RUN_NUMBER${C_RESET}"
        VERSION=$(echo "$VERSION" | awk -F. -v runid="$GITHUB_RUN_NUMBER" '{print $1"."$2"."runid}')
    else
        VERSION=$(echo "$VERSION" | awk -F. -v runid="dev" '{print $1"."$2"."runid}')
        warn "GITHUB_RUN_NUMBER is not set. Using 'dev' instead."
    fi
    SHORT_VERSION=$(echo "$VERSION" | cut -d. -f1,2)
    export VERSION SHORT_VERSION
    echo "$VERSION" > src/version.txt
    echo "$SHORT_VERSION" > src/short_version.txt
    info "Resolved application version: ${C_WHITE}${VERSION}${C_RESET} (Short: ${C_YELLOW}${SHORT_VERSION}${C_RESET})"
}

# Target: base image
build_base() {
    target_header "base"
    local IMAGE="${DOCKER_ORG}/firebird-python"
    local TAG_VERSION="${PYTHON_VERSION}"
    local TAG_FULL="${PYTHON_VERSION}-firebird${FIREBIRD_VERSION}"
    info "Building base image ${C_WHITE}${IMAGE}:${TAG_VERSION}${C_RESET} (Firebird: ${C_YELLOW}${FIREBIRD_VERSION}${C_RESET}) ..."
    if [[ -n "$PUSH_FLAG" ]]; then
        info "Publishing multi-arch ${C_CYAN}linux/amd64,linux/arm64${C_RESET} to Docker Hub ..."
        run_docker buildx build \
            --platform linux/amd64,linux/arm64 \
            --no-cache \
            --build-arg PYTHON_VERSION="${PYTHON_VERSION}" \
            --build-arg FIREBIRD_VERSION="${FIREBIRD_VERSION}" \
            -t "${IMAGE}:${TAG_VERSION}" \
            -t "${IMAGE}:${TAG_FULL}" \
            -t "${IMAGE}:latest" \
            -f build/Dockerfile.firebird-base \
            --push \
            .
    else
        info "Building locally for ${C_CYAN}linux/amd64${C_RESET} only ..."
        run_docker buildx build \
            --platform linux/amd64 \
            --load \
            --no-cache \
            --build-arg PYTHON_VERSION="${PYTHON_VERSION}" \
            --build-arg FIREBIRD_VERSION="${FIREBIRD_VERSION}" \
            -t "${IMAGE}:${TAG_VERSION}" \
            -t "${IMAGE}:${TAG_FULL}" \
            -t "${IMAGE}:latest" \
            -f build/Dockerfile.firebird-base \
            .
    fi
}

# Target: standalone web application
build_web() {
    target_header "web"
    load_version
    local IMAGE="${DOCKER_ORG}/web"
    info "Building standalone Kinetiqo ${C_WHITE}${IMAGE}:${VERSION}${C_RESET} ..."
    if [[ -n "$PUSH_FLAG" ]]; then
        info "Publishing multi-arch ${C_CYAN}linux/amd64,linux/arm64${C_RESET} to Docker Hub (timestamp: ${C_YELLOW}${TIMESTAMP}${C_RESET}) ..."
        run_docker buildx build \
            --platform linux/amd64,linux/arm64 \
            --no-cache \
            --pull=true \
            --build-arg VERSION="${SHORT_VERSION}" \
            -t "${IMAGE}:latest" \
            -t "${IMAGE}:${SHORT_VERSION}" \
            -t "${IMAGE}:${VERSION}" \
            -t "${IMAGE}:${TIMESTAMP}" \
            -f build/Dockerfile.web \
            --push \
            .
    else
        local PULL_FLAG="--pull=false"
        if [[ -n "$GITHUB_ACTIONS" ]]; then
            PULL_FLAG="--pull=true"
            info "CI environment detected — base image will be pulled from Docker Hub."
        else
            info "Using locally cached base image (${C_WHITE}${DOCKER_ORG}/firebird-python:3.14${C_RESET}) — run './build.sh base' first if missing."
        fi
        info "Building locally for ${C_CYAN}linux/amd64${C_RESET} (timestamp: ${C_YELLOW}${TIMESTAMP}${C_RESET}) ..."
        run_docker buildx build \
            --platform linux/amd64 \
            --load \
            --no-cache \
            ${PULL_FLAG} \
            --build-arg VERSION="${SHORT_VERSION}" \
            -t "${IMAGE}:latest" \
            -t "${IMAGE}:${SHORT_VERSION}" \
            -t "${IMAGE}:${VERSION}" \
            -t "${IMAGE}:${TIMESTAMP}" \
            -f build/Dockerfile.web \
            .
    fi
}

# Target: integrated web + FastMCP application
build_mcp() {
    target_header "mcp"
    load_version
    local IMAGE="${DOCKER_ORG}/web-mcp"
    info "Building Kinetiqo + FastMCP ${C_WHITE}${IMAGE}:${VERSION}${C_RESET} ..."
    if [[ -n "$PUSH_FLAG" ]]; then
        info "Publishing multi-arch ${C_CYAN}linux/amd64,linux/arm64${C_RESET} to Docker Hub (timestamp: ${C_YELLOW}${TIMESTAMP}${C_RESET}) ..."
        run_docker buildx build \
            --platform linux/amd64,linux/arm64 \
            --no-cache \
            --pull=true \
            --build-arg VERSION="${SHORT_VERSION}" \
            -t "${IMAGE}:latest" \
            -t "${IMAGE}:mcp" \
            -t "${IMAGE}:${SHORT_VERSION}" \
            -t "${IMAGE}:${VERSION}" \
            -t "${IMAGE}:${TIMESTAMP}" \
            -t "${IMAGE}:${SHORT_VERSION}-mcp" \
            -t "${IMAGE}:${VERSION}-mcp" \
            -t "${IMAGE}:${TIMESTAMP}-mcp" \
            -f build/Dockerfile.mcp \
            --push \
            .
    else
        local PULL_FLAG="--pull=false"
        if [[ -n "$GITHUB_ACTIONS" ]]; then
            PULL_FLAG="--pull=true"
            info "CI environment detected — base image will be pulled from Docker Hub."
        else
            info "Using locally cached base image (${C_WHITE}${DOCKER_ORG}/firebird-python:3.14${C_RESET}) — run './build.sh base' first if missing."
        fi
        info "Building locally for ${C_CYAN}linux/amd64${C_RESET} (timestamp: ${C_YELLOW}${TIMESTAMP}${C_RESET}) ..."
        run_docker buildx build \
            --platform linux/amd64 \
            --load \
            --no-cache \
            ${PULL_FLAG} \
            --build-arg VERSION="${SHORT_VERSION}" \
            -t "${IMAGE}:latest" \
            -t "${IMAGE}:mcp" \
            -t "${IMAGE}:${SHORT_VERSION}" \
            -t "${IMAGE}:${VERSION}" \
            -t "${IMAGE}:${TIMESTAMP}" \
            -t "${IMAGE}:${SHORT_VERSION}-mcp" \
            -t "${IMAGE}:${VERSION}-mcp" \
            -t "${IMAGE}:${TIMESTAMP}-mcp" \
            -f build/Dockerfile.mcp \
            .
    fi
}

# Expand 'all' into sequential targets: base -> web -> mcp
EXPANDED_TARGETS=()
for target in "${TARGETS[@]}"; do
    if [[ "$target" == "all" ]]; then
        EXPANDED_TARGETS+=(base web mcp)
    else
        EXPANDED_TARGETS+=("$target")
    fi
done

# Perform docker login once if push is requested
if [[ -n "$PUSH_FLAG" ]]; then
    docker_login
fi

# Execute targets in sequence
for target in "${EXPANDED_TARGETS[@]}"; do
    case "$target" in
        base)
            build_base
            ;;
        web)
            build_web
            ;;
        mcp)
            build_mcp
            ;;
    esac
done

echo ""
success "All specified build targets completed successfully."
if [[ -z "$PUSH_FLAG" && "$DRY_RUN" != "true" ]]; then
    info "Built images size:"
    docker image ls "${DOCKER_ORG}/*" 2>/dev/null || true
fi
