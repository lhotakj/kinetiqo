#!/usr/bin/env bash
set -euo pipefail

CHARTJS_VERSION="${CHARTJS_VERSION:-4.4.1}"
DATEFNS_ADAPTER_VERSION="${DATEFNS_ADAPTER_VERSION:-3.0.0}"
MOMENT_ADAPTER_VERSION="${MOMENT_ADAPTER_VERSION:-1.0.1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/chartjs"

CHARTJS_FILE="$OUT_DIR/chart-${CHARTJS_VERSION}.umd.min.js"
DATEFNS_FILE="$OUT_DIR/chartjs-adapter-date-fns-${DATEFNS_ADAPTER_VERSION}.bundle.min.js"
MOMENT_FILE="$OUT_DIR/chartjs-adapter-moment-${MOMENT_ADAPTER_VERSION}.min.js"

CHARTJS_URL="https://cdn.jsdelivr.net/npm/chart.js@${CHARTJS_VERSION}/dist/chart.umd.min.js"
DATEFNS_URL="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@${DATEFNS_ADAPTER_VERSION}/dist/chartjs-adapter-date-fns.bundle.min.js"
MOMENT_URL="https://cdn.jsdelivr.net/npm/chartjs-adapter-moment@${MOMENT_ADAPTER_VERSION}/dist/chartjs-adapter-moment.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading Chart.js ${CHARTJS_VERSION} from:"
echo "  $CHARTJS_URL"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$CHARTJS_URL" -o "$CHARTJS_FILE"

echo "Downloading chartjs-adapter-date-fns ${DATEFNS_ADAPTER_VERSION} from:"
echo "  $DATEFNS_URL"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$DATEFNS_URL" -o "$DATEFNS_FILE"

echo "Downloading chartjs-adapter-moment ${MOMENT_ADAPTER_VERSION} from:"
echo "  $MOMENT_URL"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$MOMENT_URL" -o "$MOMENT_FILE"

echo "Chart.js assets written to $OUT_DIR"
