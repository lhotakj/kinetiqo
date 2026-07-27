# Tailwind CSS CLI for Ubuntu Bash

This document shows how to download the Tailwind CSS CLI binary on Ubuntu
with Bash, and how to use it to build the production stylesheet.

## 1. Download script

Save this as `development/download-tailwind-cli.sh`:

```bash
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

if [ "$VERSION" = "latest" ]; then
  URL="https://github.com/tailwindlabs/tailwindcss/releases/latest/download/${ASSET}"
else
  URL="https://github.com/tailwindlabs/tailwindcss/releases/download/${VERSION}/${ASSET}"
fi

mkdir -p "$OUT_DIR"

echo "Downloading Tailwind CLI from:"
echo "  $URL"

curl -fsSL "$URL" -o "$OUT_DIR/tailwindcss"
chmod +x "$OUT_DIR/tailwindcss"

"$OUT_DIR/tailwindcss" --help >/dev/null
echo "Tailwind CLI downloaded to $OUT_DIR/tailwindcss"
```

## 2. Install prerequisites

On Ubuntu, make sure you have:

- `curl`
- `bash`
- `chmod` and standard GNU coreutils

## 3. Use the download script

```bash
chmod +x development/download-tailwind-cli.sh
./development/download-tailwind-cli.sh
```

Optional pinned version:

```bash
TAILWIND_VERSION=v4.3.3 ./development/download-tailwind-cli.sh
```

Optional custom output directory:

```bash
TAILWIND_OUT_DIR="$HOME/tools/tailwind" ./development/download-tailwind-cli.sh
```

## 4. Check the binary

```bash
./development/bin/tailwindcss --help
./development/bin/tailwindcss --version
```

## 5. Build CSS

Example production build:

```bash
./development/download-tailwind.sh
```

Example watch mode for development:

```bash
./development/bin/tailwindcss \
  -i ./src/kinetiqo/web/static/css/tailwind.input.css \
  -o ./src/kinetiqo/web/static/css/tailwind.css \
  --watch
```

## 6. Input CSS

Use the input file that matches the Tailwind major version you download.

- Tailwind v4 CLI: usually starts with `@import "tailwindcss";`
- Tailwind v3 CLI: usually uses the classic `@tailwind base;`, `@tailwind components;`, and `@tailwind utilities;`

If you pin a Tailwind version, keep the input CSS in sync with that major
version.

## 7. Recommended workflow

1. Download the CLI.
2. Create or update your input CSS file.
3. Run the CLI once with `--minify` for production.
4. Run again with `--watch` while developing.
5. Replace any runtime Tailwind CDN script with the generated CSS file.

## 8. Current repo files

- `development/download-tailwind-cli.sh` downloads the CLI.
- `development/download-tailwind.sh` builds `src/kinetiqo/web/static/css/tailwind.css`.
- `src/kinetiqo/web/static/css/tailwind.input.css` is the Tailwind v4 input file.
- `src/kinetiqo/web/static/css/tailwind.css` is the generated production asset.
