#!/usr/bin/env bash
set -euo pipefail

VERSION="${HTML2CANVAS_VERSION:-1.4.1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/html2canvas"

OUT_FILE="$OUT_DIR/html2canvas-${VERSION}.min.js"
URL="https://cdn.jsdelivr.net/npm/html2canvas@${VERSION}/dist/html2canvas.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading html2canvas ${VERSION} from:"
echo "  $URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$URL" -o "$OUT_FILE"
echo "html2canvas written to $OUT_FILE"
