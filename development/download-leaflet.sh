#!/usr/bin/env bash
set -euo pipefail

VERSION='1.9.4'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/leaflet"
CSS_FILE="$OUT_DIR/leaflet-${VERSION}.css"
JS_FILE="$OUT_DIR/leaflet-${VERSION}.min.js"
CSS_URL="https://unpkg.com/leaflet@${VERSION}/dist/leaflet.css"
JS_URL="https://unpkg.com/leaflet@${VERSION}/dist/leaflet.js"

mkdir -p "$OUT_DIR"

echo "Downloading Leaflet ${VERSION} from:"
echo "  $CSS_URL"
echo "  $JS_URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$CSS_URL" -o "$CSS_FILE"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$JS_URL" -o "$JS_FILE"
echo "Leaflet assets written to $OUT_DIR"
