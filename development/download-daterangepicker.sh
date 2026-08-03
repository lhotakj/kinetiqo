#!/usr/bin/env bash
set -euo pipefail

VERSION="${DATERANGEPICKER_VERSION:-3.1.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/daterangepicker"

CSS_FILE="$OUT_DIR/daterangepicker-${VERSION}.css"
JS_FILE="$OUT_DIR/daterangepicker-${VERSION}.min.js"
CSS_URL="https://cdn.jsdelivr.net/npm/daterangepicker@${VERSION}/daterangepicker.css"
JS_URL="https://cdn.jsdelivr.net/npm/daterangepicker@${VERSION}/daterangepicker.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading Date Range Picker ${VERSION} from:"
echo "  $CSS_URL"
echo "  $JS_URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$CSS_URL" -o "$CSS_FILE"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$JS_URL" -o "$JS_FILE"
echo "Date Range Picker written to $OUT_DIR"
