#!/usr/bin/env bash
set -euo pipefail

VERSION='2.0.10'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/htmx"
OUT_FILE="$OUT_DIR/htmx-${VERSION}.min.js"
URL="https://cdn.jsdelivr.net/npm/htmx.org@${VERSION}/dist/htmx.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading HTMX ${VERSION} from:"
echo "  $URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$URL" -o "$OUT_FILE"
echo "HTMX written to $OUT_FILE"
