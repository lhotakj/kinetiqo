#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TAILWIND_BIN="${TAILWIND_BIN:-$SCRIPT_DIR/bin/tailwindcss}"
INPUT_CSS="$REPO_ROOT/src/kinetiqo/web/static/css/tailwind.input.css"
OUTPUT_CSS="$REPO_ROOT/src/kinetiqo/web/static/css/tailwind.css"

if [ ! -x "$TAILWIND_BIN" ]; then
  echo "Tailwind CLI not found at $TAILWIND_BIN" >&2
  echo "Download it first with ./download-tailwind-cli.sh" >&2
  exit 1
fi

if [ ! -f "$INPUT_CSS" ]; then
  echo "Missing Tailwind input CSS: $INPUT_CSS" >&2
  exit 1
fi

"$TAILWIND_BIN" \
  -i "$INPUT_CSS" \
  -o "$OUTPUT_CSS" \
  --minify