# Tailwind CSS CLI Workflow & Setup

This document describes how Tailwind CSS CLI binary acquisition and stylesheet compilation are managed in Kinetiqo using the unified vendor library downloader.

## 1. Unified Vendor Manager

Tailwind CLI binary downloading and CSS compilation are configured in `development/vendor-libraries.yaml` and executed by `development/download-vendor-libraries.py`.

```bash
# Download Tailwind CLI binary and compile minified production CSS
python development/download-vendor-libraries.py --library tailwind

# Download Tailwind CLI binary only (without compilation)
python development/download-vendor-libraries.py --library tailwind-cli
```

## 2. Configuration Parameters (`development/vendor-libraries.yaml`)

The `tailwind_cli` prerequisite block defines binary acquisition and compilation targets:

```yaml
prerequisites:
  tailwind_cli:
    id: "tailwind-cli"
    name: "Tailwind CSS CLI"
    version: "v4.3.3"
    target_dir: "development/bin"
    asset_template: "https://github.com/tailwindlabs/tailwindcss/releases/download/{version}/tailwindcss-{os}-{arch}{ext}"
    latest_template: "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-{os}-{arch}{ext}"
    os_map:
      linux: "linux"
      darwin: "macos"
      windows: "windows"
    arch_map:
      x86_64: "x64"
      amd64: "x64"
      aarch64: "arm64"
      arm64: "arm64"
    filename: "tailwindcss"
    build_step:
      input_css: "src/kinetiqo/web/static/css/tailwind.input.css"
      output_css: "src/kinetiqo/web/static/css/tailwind.css"
      vendor_css: "src/kinetiqo/web/static/vendor/tailwind/tailwind.css"
      minify: true
```

## 3. Direct Binary Commands & Watch Mode

Once acquired by `download-vendor-libraries.py`, the CLI binary is located at `development/bin/tailwindcss` (or `development/bin/tailwindcss.exe` on Windows).

```bash
# Check version
./development/bin/tailwindcss --version

# Run watcher for development auto-recompilation
./development/bin/tailwindcss \
  -i ./src/kinetiqo/web/static/css/tailwind.input.css \
  -o ./src/kinetiqo/web/static/css/tailwind.css \
  --watch
```

## 4. Input & Output Structure

- **Input CSS**: `src/kinetiqo/web/static/css/tailwind.input.css` (Tailwind v4 entry `@import "tailwindcss";`)
- **Output CSS**: `src/kinetiqo/web/static/css/tailwind.css` (minified production asset)
- **Vendor Copy**: `src/kinetiqo/web/static/vendor/tailwind/tailwind.css`
- **Play CDN JS**: `src/kinetiqo/web/static/vendor/tailwind/tailwind.js`

## 5. Repository Files

- `development/download-vendor-libraries.py`: Downloads all vendor assets & compiles Tailwind CSS.
- `development/vendor-libraries.yaml`: Defines Tailwind version, binary templates, and target paths.
- `src/kinetiqo/web/static/css/tailwind.input.css`: Source Tailwind v4 input stylesheet.
- `src/kinetiqo/web/static/css/tailwind.css`: Generated production stylesheet.
