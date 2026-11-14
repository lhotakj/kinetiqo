---
name: sync-marketing-features
description: Instructions and standards to keep the 8 core fitness telemetry features, 16 basemaps, 4x2 grid layout, top navigation dropdown, environment variables, and CLI reference synchronized across the Kinetiqo marketing site (src/ and site/).
---

# Kinetiqo Marketing Features & Application Synchronization Skill

## 0. Python SSG Build Workflow & Architecture

All site content is built using a Jinja2 + PyYAML static site generator (`build.py`) with automated minification and validation:
1. **Editable Content Source (`src/`)**:
   - `src/data/` (`site.yaml`, `navigation.yaml`, `features.yaml`, `basemaps.yaml`, `env_vars.yaml`)
   - `src/templates/` (`layouts/base.html`, `partials/`, `components/`, `pages/`)
   - `src/public/` (`_headers`, `robots.txt`, `sitemap.xml`, `package.json`, `wrangler.toml`, `run-local.sh`, `server.py`, `.assetsignore`, `README.md`)
2. **Media & Script Assets**:
   - Image screenshots are placed in `src/assets/img/` and `src/assets/img/basemaps/`.
   - **Strict Image Standard**: Use **WebP format** (`.webp`) across the entire website for optimal loading speed and bandwidth reduction (>86% smaller than PNG). Retain `kinetiqo_logo.png` exclusively for Apple touch icon and fallback favicon compatibility.
   - All non-icon content images must support interactive fullscreen preview on click via modal overlay.
   - **Asset Cache Busting (`?v=<hash>`)**: All local CSS and JS links in HTML templates MUST include `?v={{ site.build_hash }}` (e.g. `<link rel="stylesheet" href="{{ asset_prefix }}static/css/style.css?v={{ site.build_hash }}">`, `<script src="{{ asset_prefix }}static/js/main.js?v={{ site.build_hash }}"></script>`). `build.py` automatically resolves `build_hash` (`git rev-parse --short HEAD` with fallback to `YYYYMMDD`).
3. **Build Execution & Automated Minification**:
   - Run `python build.py` to compile templates, copy assets, copy root public files, dynamically generate `sitemap.xml` and `robots.txt`, verify and synchronize WebP images (auto-converting newly added PNGs), dynamically inject `site.copyright_year` and `site.build_hash`, and automatically minify all `.html`, `.css`, and `.js` files in-place using `minify-html`, `rcssmin`, and `rjsmin`.
   - The build automatically verifies HTML5 structure, CSS balance, and JavaScript syntax (via Node.js V8 engine).
   - **Note**: The legacy `site-dynamic-bug/` directory is obsolete and deleted. `site/` is the sole production deployable output.
  
    ## Update PyPI / Requirements Workflow
  
    This repository provides an automation helper to check and optionally pin Python dependencies to the latest PyPI releases. The script is located at `scripts/check-pypi-updates.py` in the repository root.
  
    Agent/CI trigger keywords: `update pypi`, `update python` — use these phrases to request an automated workflow that executes the helper script as a dry-run or to apply updates depending on the automation setup.
4. **Line Endings & Typography Standard**:
   - All source and generated files must use Unix/Linux line endings (**LF / `\n`**), never CRLF. Use UTF-8 encoding without BOM.
   - Copyright year in footers is dynamic (`site.copyright_year`), followed by `<span class="footer-version">| version: {{ site.build_hash }}</span>` styled with `font-weight: 300`, `font-size: 0.75rem`, monospace typography, and theme-adaptive colors.

---

## 1. Synchronizing from Kinetiqo Application (`../kinetiqo`)

Whenever an AI assistant is asked to **"align kinetiqo-web with kinetiqo application"** or sync features, execute this structured audit:

### 1.1 CLI Commands & Global Options
- **Source of Truth**: `src/kinetiqo/cli.py` in `kinetiqo`.
- **Target in Website**: `src/templates/pages/cli.html` and `src/data/navigation.yaml`.
- Ensure all Click subcommands are documented:
  - `kinetiqo web` (options: `-p, --port`, `-h, --host`, `--debug`)
  - `kinetiqo sync` (options: `-f, --full`, `-p, --poll`, `-a, --activity-id`, `-d, --dry-run`)
  - `kinetiqo flightcheck` (diagnostics for database, credentials, Strava API connectivity)
  - `kinetiqo benchmark` (options: `-s, --scope`, `-d, --database-type` for comparing parameterized raw SQL across backends)
  - `kinetiqo version`
  - Global options: `--database-type`, `--log-level`.

### 1.2 Environment Variables & Port Mappings
- **Source of Truth**: `src/kinetiqo/config.py`, `build/Dockerfile`, `build/entrypoint.sh`.
- **Target in Website**: `src/data/env_vars.yaml` and `src/templates/pages/installation.html`.
- Port mapping: `4444:4444` (container port 4444, Debian-slim, `cron` scheduler).
- Environment variables:
  - Verify every single config variable exists in `src/data/env_vars.yaml` with name, required/optional status, default value, description, and group.
  - Examples: `DATABASE_TYPE`, `POSTGRES_*`, `MYSQL_*`, `FIREBIRD_*`, `GPS_SIMPLIFICATION` (levels 1–10), `UPDATE_STRAVA_*`, `WORKOUT_SUMMARY_*`, etc.
  - Enforce valid `{{...}}` double-curly syntax in `.env` templates on the site.

### 1.3 Basemaps & Tile Providers
- **Source of Truth**: `src/kinetiqo/web/templates/map.html`, `poster.html`, `fonts.py`, and tile proxy routes in `app.py`.
- **Target in Website**: `src/data/basemaps.yaml` and `src/templates/pages/base-maps.html`.
- **16 Basemaps across 7 Providers**:
  - `openstreetmap`: `osm_standard` (Built-in server proxy at `/tiles/osm/...`)
  - `mapy`: `mapy_basic`, `mapy_outdoor` (`MAPY_API_KEY`, 250k credits/mo)
  - `thunderforest`: `thunderforest_cycle`, `thunderforest_outdoors` (`THUNDERFOREST_API_KEY`, 150k tiles/mo, zoom 22)
  - `maptiler`: `maptiler_bright`, `maptiler_outdoor`, `maptiler_topo`, `maptiler_satellite`, `maptiler_aquarelle` (`MAPTILER_API_KEY`, 100k req/mo)
  - `geoapify`: `geoapify_osm_bright`, `geoapify_osm_carto`, `geoapify_dark_matter` (`GEOAPIFY_API_KEY`, 360k tiles/mo)
  - `carto`: `carto_positron`, `carto_dark` (`CARTO_API_KEY`, 5M requests)
  - `esri`: `esriworldimagery` (Public service, 2M tiles/mo)
- **Metadata Requirements for `src/data/basemaps.yaml`**:
  - Every basemap MUST define `spotlight_order` (1 to 16), `spotlight_subtitle` (concise cartographic title), `spotlight_app` (`map` or `poster`), and `spotlight_desc`.
  - Every basemap MUST have a matching screenshot in `src/assets/img/basemaps/<image_slug>.webp`.
  - The Interactive Spotlight Carousel and Technical Matrix in `base-maps.html` are dynamically generated from this YAML file.

---

## 2. Authoritative 8-Feature Matrix & 4×2 Grid Structure

The Kinetiqo marketing site presents fitness telemetry across **8 core feature cards** organized into a responsive **4×2 grid on desktop** (`@media (min-width: 1100px): repeat(4, 1fr)`), 2 columns on tablet (`min-width: 640px: repeat(2, 1fr)`), and 1 column on mobile.

Both the homepage (`src/templates/pages/index.html`) and the features portal (`src/templates/pages/features/index.html`) must strictly maintain this 8-card order from `src/data/features.yaml`:

| # | Feature Card Title | Target Landing Page | Icon Theme | Key Capability |
|---|--------------------|---------------------|------------|----------------|
| 1 | **Activity Sync & Data Grid** | `features/activities.html` | Bolt / Flash | Fast incremental sync, audit reconciliation, DataTables 2.x with state persistence |
| 2 | **Power Skills & FTP Estimation** | `features/analytics.html` | Trending Chart | Spider charts across 5s–1h durations, automated 95% 20-min FTP tracking |
| 3 | **Fitness, Freshness & VO₂max** | `features/analytics.html` | Heart / Vitality | Banister impulse-response CTL/ATL/TSB curves, Townsend MAP & Coggan VO₂max |
| 4 | **WYSIWYG Poster** | `features/poster.html` | Framed Photo | High-res activity posters with draggable elements, map/photo backgrounds, Playwright PNG export |
| 5 | **MEGA Stats** | `features/stats.html` | 3-Bar Histogram | Veloviewer-style yearly/custom infographics, calendar heatmaps, visible stat toggles, PNG/PDF export |
| 6 | **Strava Auto-Description Engine** | `features/strava-sync.html` | Edit / Pencil | 150+ placeholders across 6 activity buckets, milestone triggers (🎉), server validation |
| 7 | **Interactive Canvas Maps** | `features/maps.html` | Folded Map Route | Leaflet Canvas rendering for thousands of GPS points, 16 layers, 7 tile providers |
| 8 | **Multi-DB Zero-ORM Warehouse** | `features/databases.html` | Database Cylinder | Parameterized raw SQL across PostgreSQL 12+, MySQL 8 / MariaDB, Firebird 3.0/4.0/5.0 |

---

## 3. Global Navigation Consistency Rules

All navigation menus are defined centrally in `src/data/navigation.yaml`:

### Top Navigation ("Features ▾" Dropdown)
Header dropdown entries:
- `Activity Sync & Data Grid` (`features/activities.html`)
- `Power, FTP & Fitness Analytics` (`features/analytics.html`)
- `WYSIWYG Poster` (`features/poster.html`)
- `MEGA Stats` (`features/stats.html`)
- `Strava Description Auto-Update` (`features/strava-sync.html`)
- `Interactive Canvas Maps` (`features/maps.html`)
- `Multi-DB Zero-ORM Warehouse` (`features/databases.html`)

### Bottom Navigation (Footer)
- **`<h4>Navigation</h4>`**: Home, Features, Base Maps (`base-maps.html`), Video Demos (`demos.html`), Installation Guide (`installation.html`), CLI Reference (`cli.html`).
- **`<h4>Deep Dives</h4>`**: Activity Sync & Grid, Power & FTP Analytics, WYSIWYG Poster, MEGA Stats, Strava Auto-Update, Interactive Maps, Multi-DB Warehouse.
- **`<h4>Project</h4>`**: Source Code (`source.html`), Developer Contact (`contact.html`), GitHub Repository, MIT License.

---

## 4. Dedicated Feature & Showcase Landing Pages

1. **WYSIWYG Poster (`src/templates/pages/features/poster.html`)**:
   - Interactive poster generator, elevation profile styling, Leaflet map mode vs photo background, Playwright high-res PNG export (800–2048px).
   - Compatibility: `poster-stats.html` redirects via `<meta http-equiv="refresh" content="0; url=poster.html">`.

2. **MEGA Stats (`src/templates/pages/features/stats.html`)**:
   - Annual & custom period infographics (Year, Half-Year, Quarter, Custom Date Range), sport discipline filters, calendar heatmaps, visible stat toggles with 1px hairline dividers, M (1280px) and L (1440px) presets, vector PDF / PNG export.

3. **16 Base Maps Showcase (`src/templates/pages/base-maps.html`)**:
   - Gallery and technical specs of all 16 basemaps across 7 providers.
   - Provider filter tabs, 16-slide interactive spotlight carousel, technical comparison matrix, and environment variable configuration guide.

4. **Strava Auto-Description Engine (`src/templates/pages/features/strava-sync.html`)**:
   - Template engine with 150+ placeholders, workout summary surge detection (`WORKOUT_SUMMARY_PEAK_THRESHOLD_W`), milestone triggers, and HTML escaping inside `<pre>`/`<code>`.

---

## 5. SEO, Validation & Build Checklist

Before concluding any sync or alignment task:
1. **Edit Canonical Sources**: Make edits in `src/data/` or `src/templates/` (never edit `site/` files directly).
2. **Execute Build & Minification**: Run `python build.py` from repository root.
   - Compiles all Jinja2 templates into `site/`.
   - Copies static assets and root public files.
   - Dynamically generates `sitemap.xml` and `robots.txt` in both `site/` and `src/public/`.
   - In-place minifies all `.html`, `.css`, and `.js` files using `minify-html`, `rcssmin`, and `rjsmin`.
   - Automatically executes HTML5 structural checks, CSS balance checks, and V8 JavaScript syntax validation.
3. **Execute Automated Test Suite**:
   - Run `python -m unittest discover -s tests -v`.
   - All unit and integration tests (expected pages, sitemap, HTML5 validity, CSS syntax, V8 JS syntax, link/asset integrity) must pass with zero failures.
4. **Enforce SEO Standards**:
   - Exactly ONE `<h1>` per page with topic keywords.
   - `<title>`: 45–60 characters.
   - `<meta name="description">`: 140–160 characters.
   - `<meta name="theme-color" content="#090A0E">`.
   - Explicit `width` and `height` on all `<img>` tags (zero CLS).
   - Descriptive `alt` attributes on all images.
5. **Enforce Unix LF Line Endings**: Verify no CRLF line endings in any text or code files.

