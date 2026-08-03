#!/usr/bin/env bash
set -euo pipefail

VERSION="${TAILWIND_VERSION:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${TAILWIND_OUT_DIR:-$SCRIPT_DIR/bin}"

case "$(uname -m)" in
  x86_64|amd64) ASSET="tailwindcss-linux-x64" ;;
  aarch64|arm64) ASSET="tailwindcss-linux-arm64" ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

if [[ "$VERSION" == "latest" ]]; then
  URL="https://github.com/tailwindlabs/tailwindcss/releases/latest/download/${ASSET}"
else
  URL="https://github.com/tailwindlabs/tailwindcss/releases/download/${VERSION}/${ASSET}"
fi

mkdir -p "$OUT_DIR"

echo "Downloading Tailwind CLI from:"
echo "  $URL"

curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$URL" -o "$OUT_DIR/tailwindcss"
chmod +x "$OUT_DIR/tailwindcss"

"$OUT_DIR/tailwindcss" --help >/dev/null
echo "Tailwind CLI downloaded to $OUT_DIR/tailwindcss"
