#!/usr/bin/env bash
set -euo pipefail

VERSION="${SORTABLE_VERSION:-1.15.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/sortable"

OUT_FILE="$OUT_DIR/sortable-${VERSION}.min.js"
URL="https://cdn.jsdelivr.net/npm/sortablejs@${VERSION}/Sortable.min.js"

mkdir -p "$OUT_DIR"

echo "Downloading SortableJS ${VERSION} from:"
echo "  $URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$URL" -o "$OUT_FILE"
echo "SortableJS written to $OUT_FILE"
