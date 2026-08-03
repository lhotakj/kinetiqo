#!/usr/bin/env bash
set -euo pipefail

VERSION="${SELECT2_VERSION:-4.1.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/select2"

CSS_FILE="$OUT_DIR/select2-${VERSION}.min.css"
JS_FILE="$OUT_DIR/select2-${VERSION}.min.js"
CSS_URL="https://cdn.jsdelivr.net/npm/select2@${VERSION}/dist/css/select2.min.css"
JS_URL="https://cdn.jsdelivr.net/npm/select2@${VERSION}/dist/js/select2.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading Select2 ${VERSION} from:"
echo "  $CSS_URL"
echo "  $JS_URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$CSS_URL" -o "$CSS_FILE"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$JS_URL" -o "$JS_FILE"
echo "Select2 written to $OUT_DIR"
