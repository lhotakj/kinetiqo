#!/usr/bin/env bash
set -euo pipefail

VERSION="${MOMENT_VERSION:-2.30.1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/moment"
OUT_FILE="$OUT_DIR/moment-${VERSION}.min.js"
URL="https://cdn.jsdelivr.net/npm/moment@${VERSION}/min/moment.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading Moment.js ${VERSION} from:"
echo "  $URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$URL" -o "$OUT_FILE"
echo "Moment.js written to $OUT_FILE"
