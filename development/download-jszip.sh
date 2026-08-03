#!/usr/bin/env bash
set -euo pipefail

VERSION="${JSZIP_VERSION:-3.10.1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/jszip"

OUT_FILE="$OUT_DIR/jszip-${VERSION}.min.js"
URL="https://cdn.jsdelivr.net/npm/jszip@${VERSION}/dist/jszip.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading JSZip ${VERSION} from:"
echo "  $URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$URL" -o "$OUT_FILE"
echo "JSZip written to $OUT_FILE"
