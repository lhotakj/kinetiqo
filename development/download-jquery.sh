#!/usr/bin/env bash
set -euo pipefail

VERSION='3.7.1'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/jquery"
OUT_FILE="$OUT_DIR/jquery-${VERSION}.min.js"
URL="https://code.jquery.com/jquery-${VERSION}.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading jQuery ${VERSION} from:"
echo "  $URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$URL" -o "$OUT_FILE"
echo "jQuery written to $OUT_FILE"
