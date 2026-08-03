#!/usr/bin/env bash
set -euo pipefail

DATATABLES_VERSION="${DATATABLES_VERSION:-2.3.7}"
BUTTONS_VERSION="${BUTTONS_VERSION:-3.2.6}"
COLREORDER_VERSION="${COLREORDER_VERSION:-2.1.2}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$REPO_ROOT/src/kinetiqo/web/static/vendor/datatables"

mkdir -p "$OUT_DIR"

# DataTables core
DT_CSS_FILE="$OUT_DIR/dataTables-${DATATABLES_VERSION}.min.css"
DT_JS_FILE="$OUT_DIR/dataTables-${DATATABLES_VERSION}.min.js"
DT_CSS_URL="https://cdn.datatables.net/${DATATABLES_VERSION}/css/dataTables.dataTables.min.css"
DT_JS_URL="https://cdn.datatables.net/${DATATABLES_VERSION}/js/dataTables.min.js"

echo "Downloading DataTables ${DATATABLES_VERSION}..."
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$DT_CSS_URL" -o "$DT_CSS_FILE"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$DT_JS_URL" -o "$DT_JS_FILE"

# Buttons extension
BTN_CSS_FILE="$OUT_DIR/buttons-${BUTTONS_VERSION}.dataTables.min.css"
BTN_JS_FILE="$OUT_DIR/dataTables.buttons-${BUTTONS_VERSION}.min.js"
BTN_HTML5_FILE="$OUT_DIR/buttons.html5-${BUTTONS_VERSION}.min.js"
BTN_CSS_URL="https://cdn.datatables.net/buttons/${BUTTONS_VERSION}/css/buttons.dataTables.min.css"
BTN_JS_URL="https://cdn.datatables.net/buttons/${BUTTONS_VERSION}/js/dataTables.buttons.min.js"
BTN_HTML5_URL="https://cdn.datatables.net/buttons/${BUTTONS_VERSION}/js/buttons.html5.min.js"

echo "Downloading DataTables Buttons ${BUTTONS_VERSION}..."
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$BTN_CSS_URL" -o "$BTN_CSS_FILE"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$BTN_JS_URL" -o "$BTN_JS_FILE"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$BTN_HTML5_URL" -o "$BTN_HTML5_FILE"

# ColReorder extension
COL_CSS_FILE="$OUT_DIR/colReorder.dataTables-${COLREORDER_VERSION}.min.css"
COL_JS_FILE="$OUT_DIR/dataTables.colReorder-${COLREORDER_VERSION}.min.js"
COL_CSS_URL="https://cdn.datatables.net/colreorder/${COLREORDER_VERSION}/css/colReorder.dataTables.min.css"
COL_JS_URL="https://cdn.datatables.net/colreorder/${COLREORDER_VERSION}/js/dataTables.colReorder.min.js"

echo "Downloading DataTables ColReorder ${COLREORDER_VERSION}..."
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$COL_CSS_URL" -o "$COL_CSS_FILE"
curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$COL_JS_URL" -o "$COL_JS_FILE"

echo "DataTables vendor assets written to $OUT_DIR"
