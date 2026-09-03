# Unified AI Agent Instructions for Kinetiqo (Gemini & Copilot)

> **Notice to AI Assistants (Gemini, GitHub Copilot, Cursor, Antigravity)**: This is the single, authoritative, unified instruction file for the Kinetiqo codebase. All AI coding agents must follow these guidelines strictly when analyzing, modifying, or testing code in this repository.

---

## 1. Project Overview

Kinetiqo is a self-hosted Python fitness-data platform that synchronizes activity data from the **Strava API**, stores it in a relational database, and presents it via an async-enabled Flask web dashboard and a Click CLI.

### Core Web & Analytical Features:
- **Searchable & Filterable Activity Grid**: Powered by **DataTables 2.x** with column reordering (ColReorder), PNG/CSV export (Buttons), bulk selection/deletion, and `localStorage` state persistence.
- **Interactive Leaflet Maps**: Multi-provider maps (OpenStreetMap, Mapy.cz, Thunderforest, MapTiler, Geoapify, CARTO, Esri) using Canvas renderer and a built-in server-side OSM tile proxy (`/tiles/osm/...`).
- **Fitness & Freshness**: Suffer score CTL/ATL/TSB calculations powered by pandas.
- **Power Skills Analysis**: Spider chart of best average power over durations from 5s to 1h.
- **FTP & VO₂max Estimation**: 95% 20-min power history and Townsend 5-min MAP power trend analysis.
- **Activity Goals**: Weekly, monthly, and yearly distance/elevation goals per activity type.
- **MEGA Stats Infographic**: Infographic with selectable period/activity groups, persisted font size, left-column width, most active month by distance & elevation metrics, and custom date formatting.
- **Activity Poster Generator**: WYSIWYG poster builder with elevation profile, custom fonts, 4:3 / 16:9 / 1:1 aspect ratios, and Playwright-powered PNG export.
- **Strava Description Auto-Update (`UPDATE_STRAVA_*`)**: Description template engine with 150+ placeholders, 6 activity buckets, milestone triggers (`🎉`), and configurable placement (`begin`/`end`).
- **HTMX Reactivity & SSE**: Real-time progress updates for sync operations.
- **Security & Performance**: Session auth (`flask-login`), CSRF validation (`flask-wtf`), response compression (`flask-compress`), self-hosted base fonts, and compiled Tailwind CSS.

---

## 2. Testing Philosophy: Mocked Unit Tests First

**This is a critical instruction.** The default testing strategy for Kinetiqo is **fast, isolated unit tests**. All external dependencies, especially the database and the Strava API, **must be mocked**.

Note: Tests must not make real network or database calls. Use unittest.mock, local fakes, or test-only fixtures to simulate external services; CI jobs should never depend on live third-party services.

- **Always write mocked unit tests by default.** Do not write integration tests requiring a live database unless explicitly requested.
- **Use `unittest.mock.patch`** to intercept external boundary calls. Primary patch targets include:
  - `kinetiqo.sync.create_repository`
  - `kinetiqo.cli.create_repository`
  - `kinetiqo.sync.StravaClient`
- **Canonical Example**: `tests/test_sync_logic.py` is the gold standard for unit test structure (class-level patches, `subTest` matrix tests).
- **Execution Commands**:
  - `python -m pytest -o pythonpath=src`
  - `python -m unittest discover -s tests -v` (with `PYTHONPATH=src`)

---

## 3. Key Technologies & Pinned Versions

| Concern | Technology | Version | Notes |
|---|---|---|---|
| Language | **Python** | 3.14 | Dockerized on `python:3.14-slim` |
| Testing | **pytest** / **unittest** | stdlib + pytest | Mocked unit tests in `tests/` |
| Web Framework | **Flask[async]** + **flask-login** | 3.1.3 / 0.6.3 | Jinja2 templates, Gunicorn 26.0.0 in production |
| Session & CSRF | **Flask-WTF** / **flask-login** | 1.3.0 / 0.6.3 | CSRF tokens on all POST/PUT/DELETE routes |
| Response Compression | **flask-compress** | 1.24 | Automatic gzip/brotli compression |
| Frontend CSS | **Tailwind CSS** | v4 CLI (4.3.3) | Compiled to `static/css/tailwind.css` via `download-tailwind.sh` |
| Reactivity | **HTMX** + **htmx-ext-sse** | 2.0.10 / 2.2.2 | SSE for sync progress bar |
| Data Tables | **DataTables** + **Buttons** + **ColReorder** | 2.3.7 / 3.2.6 / 2.1.2 | Client-side processing mode with SRI |
| Charting | **Chart.js** + **chartjs-adapter-moment** | 4.4.1 / 1.0 | Client-side Canvas rendering |
| Maps | **Leaflet.js** | 1.9.4 | Canvas renderer, self-hosted vendor files, server-side tile proxy |
| CLI | **Click** | 8.4.1 | Entry point: `python src/kinetiqo.py <command>` (`web`, `sync`, `flightcheck`, `benchmark`) |
| Database Drivers | **psycopg2-binary**, **mysql-connector-python**, **firebird-driver** | 2.9.12 / 9.7.0 / 2.0.3 | Parameterized raw SQL — **no ORM** |
| HTTP Client | **httpx** / **requests** | 0.28.1 / 2.34.2 | Async/sync clients for Strava & GitHub APIs |
| Data Processing | **pandas** | 3.0.3 | CTL/ATL/TSB calculation |
| Browser Automation | **Playwright** | ≥1.60.0 | PNG poster and infographic rendering |
| Image Processing | **Pillow** | ≥12.2.0 | Poster and image processing |
| Date Parsing | **python-dateutil** | ≥2.8.2 | Date parsing utilities |
| Versioning | **packaging** | ≥26.2 | SemVer comparisons |

---

## 4. Secure Web Application Best Practices

### 4.1 Database Security & Repository Pattern
- **Parameterized SQL mandatory**: Never format or concatenate variables into SQL strings.
  - PostgreSQL & MySQL: Use `%s` placeholders.
  - Firebird: Use `?` placeholders and quoted identifiers.
- All database operations must go through `DatabaseRepository` (`db/repository.py`).
- When modifying the repository interface, **always update all three concrete backends** (`postgresql.py`, `mysql.py`, `firebird.py`).
- Detailed database layer architecture, driver benchmark analysis, and performance tuning recommendations are documented in [docs/DATABASE.md](docs/DATABASE.md).

### 4.2 Authentication, Session Security & CSRF Protection
- Authentication is managed via `flask-login`.
- `SECRET_KEY` must be persistent in production. Validate security settings when `KINETIQO_PRODUCTION=1`.
- **CSRF Protection**: All non-GET requests (POST, PUT, DELETE, HTMX forms) must include CSRF token validation (`flask-wtf` CSRF protection or `X-CSRFToken` headers).
- **Session Cookies**: Ensure session cookies use `HttpOnly`, `SameSite=Lax`, and `Secure` (when behind HTTPS).

### 4.3 XSS Prevention & Output Encoding (Sonar Web:S5725)
- Jinja2 autoescaping is enabled by default.
- Use the `|e` filter when explicitly escaping text in Jinja templates.
- **JavaScript Serialization**: When embedding Python/Jinja variables into inline `<script>` blocks, always use `|tojson` (e.g., `const data = {{ my_var | tojson }};`).
- **Never use `|safe`** unless rendering sanitized HTML that has been strictly validated. Document any use of `|safe`.
- **DOM Injection**: Avoid constructing HTML via string concatenation in client-side JS using untrusted data. Prefer setting `textContent`, `setAttribute()`, or using template cloning. Do not use `innerHTML` or `document.write()`.

### 4.4 Form Accessibility & Control Association (Sonar Web:S6853)
- Every `<label>` element must be associated with a valid form input element.
  - Use `<label for="element_id">` with a matching `id="element_id"` on the input/select/textarea.
  - Alternatively, nest the input inside the `<label>`.
- Do not use `<label>` tags for non-form labels or section headers; use `<div>` or `<span>`.
- Provide `aria-label` or `aria-labelledby` for custom controls.

### 4.5 Supply Chain Security, CDN Guidelines & Self-Hosting
- **Base UI & Vendor Assets**: All frontend vendor assets (Tailwind CSS, HTMX, jQuery, Leaflet, Chart.js, Moment.js, DataTables, Select2, DateRangePicker, JSZip, SortableJS, html2canvas) must be **100% self-hosted** (`static/fonts/`, `static/css/tailwind.css`, `static/vendor/`) to guarantee offline availability and eliminate external supply chain dependencies.
- **Vendor Downloader & Config**:
  - `development/download-vendor-libraries.py` (Unified python manager for all vendor assets)
  - `development/vendor-libraries.yaml` (Central parameter definition for libraries & prerequisites)
  - Usage: `python development/download-vendor-libraries.py` (or `--library <id>`, `--force`)
- **External CDN Rules**: When referencing remaining external libraries:
  1. Pin exact versions in URLs (no `latest` or floating tags).
  2. Include **Subresource Integrity (SRI)** (`integrity="sha384-..."`) and `crossorigin="anonymous"`.
  3. Include `<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>` in `<head>`.
  4. Defer non-critical scripts (`defer` attribute).
  5. Update `license.html` with library name and pinned version whenever changing CDN URLs.

### 4.6 Security Headers & HTTP Compression
- Use `flask-compress` for automatic gzip/brotli compression on all routes.
- Include standard HTTP security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: SAMEORIGIN`
  - `Referrer-Policy: strict-origin-when-cross-origin`

### 4.7 API Security, OAuth Scope Safety & Credential Masking
- **OAuth Scope Checks**: Write endpoints (such as Strava description updates) must verify the presence of required OAuth scopes (`activity:write`). If a `401 Unauthorized` occurs, gracefully skip further update attempts for the sync run without crashing.
- **Credential Masking**: Never print or log tokens, API keys, client secrets, or database passwords. Mask sensitive attributes in operational output.

### 4.8 Navigation & User Experience
- **Internal links**: Must stay in the same browser tab (`target="_self"` or no target attribute).
- **External links**: Open in a new tab using `target="_blank"` and include `rel="noopener noreferrer"`.
- **State Persistence**: Grid controls, column visibility, and page settings saved to `localStorage` must include schema version keys to support smooth UI migrations.

### 4.9 Web Input Validation & Error Highlighting Standards
- **Server-Side Validation Mandatory**: All user input forms and textareas (e.g. `UPDATE_STRAVA_*` description templates, Athlete FTP, Weight) must perform strict server-side validation and return HTTP 422 Unprocessable Entity with `{ "error": "...", "field": "..." }` on violation.
- **FTP Validation Bounds**: FTP must be numeric, strictly greater than 0, and not exceeding 1000 W (`0 < FTP <= 1000`).
- **Template Validation**: Enforce brace count matching (`{{` vs `}}`) and validate placeholders against recognized tokens/rules.
- **Message Location & Alignment**: Validation messages (**`Saved ✓`** or error strings) must be left-aligned directly adjacent to the input field's label using flex layout (`flex items-center gap-2 mb-1`).
- **Theme-Aware Error Highlighting**: When validation fails, the input text box background must highlight in a light red tone (`bg-red-50 dark:bg-red-950/40 border-red-400 dark:border-red-600` or direct inline style override) in both light and dark modes.
- **Auto-Restoration**: When corrected to a valid value, the text box background restores to default (`bg-white dark:bg-zinc-700`), the green **`Saved ✓`** confirmation displays next to the label, and auto-fades after 3 seconds.

### 4.10 Mega Stats Infographic Design, Metric Separator & Control Panel Standards
- **Metric Divider Standard**: Every metric block in `#ig-stats` MUST have a corresponding `<div class="ig-stat-divider" id="ig-<key>-divider"></div>` immediately following its container element in HTML templates. In JavaScript `STAT_DEFS`, every metric entry MUST declare its divider ID (`div: 'ig-<key>-divider'`). The `applyStatVisibility()` function dynamically hides the divider after whichever metric happens to be the last visible stat, guaranteeing tiny 1px separator lines (`border-top: 1px solid rgba(255,255,255,0.08)`) are displayed between all adjacent metrics without trailing divider lines at the bottom of the stats column.
- **Control Panel Uniformity**: In Visible Stats control panels, every checkbox label MUST use uniform `text-xs` (12px) font size across light and dark modes. Checkbox `<input>` elements must enforce `flex-shrink-0 mr-1` and `style="margin-right: 3px;"` to maintain 3px spacing between the checkbox box and label text. Label text containers must enforce `min-w-0 overflow-hidden whitespace-nowrap <span class="truncate">` to prevent line wrapping or column overlap.
- **Typography & Label Clipping**: Metric labels in `.ig-stat-label` MUST enforce `white-space: nowrap`, `overflow: hidden`, `text-overflow: ellipsis`, letter spacing `0.08em`, font weight 600, opacity 0.55, and scaled font size (`calc(var(--stats-font-size) * 0.38)`).
- **State Persistence**: Grid controls, left column width (`statsColumnWidth`), title font size (`statsTitleFontSize`), selected activity group (`statsActivityGroup`), and visible stat toggles (`statsVisibleStats`) MUST be persisted to `localStorage` and restored on `DOMContentLoaded`.

---

## 5. Common Development Workflows

### Add a New Web Feature
1. Create core logic in a module under `kinetiqo/web/` (e.g., `kinetiqo/web/feature.py`).
2. Add routes (`async def`) and JSON API endpoints in `kinetiqo/web/app.py`.
3. Create Jinja2 templates in `kinetiqo/web/templates/` extending `base.html`.
4. Follow accessibility (S6853) and XSS (S5725) rules.
5. Write mocked unit tests in `tests/test_feature.py`.

IMPORTANT: Any new feature, endpoint, CLI command, or public API change MUST include corresponding unit tests. Pull requests that add or modify functionality without appropriate tests will be returned for coverage before merging.

### Update the Database Interface
1. Add abstract methods to `DatabaseRepository` (`db/repository.py`).
2. Implement parameterized raw SQL in `postgresql.py`, `mysql.py`, and `firebird.py`.
3. Add unit tests asserting that repository methods are called with expected parameters.

### Add or Refresh Google Fonts
1. Register font names in `GOOGLE_FONTS` inside `kinetiqo/web/fonts.py`.
2. Run `python development/download-fonts.py --force` to download woff2 files and update `google_fonts_local.css`.
3. Preload critical fonts in `base.html` using `<link rel="preload" as="font" crossorigin>`.
4. Update font attributions in `license.html`.

### Update Tailwind CSS
1. Edit template Tailwind classes or `src/kinetiqo/web/static/css/tailwind.input.css`.
2. Run `python development/download-vendor-libraries.py --library tailwind` to compile `src/kinetiqo/web/static/css/tailwind.css`.

### Promo Website Synchronization (`promo-web/` at `kinetiqo.org`)
> **MANDATORY INSTRUCTION FOR ALL AI ASSISTANTS**: The static promo website lives in `promo-web/` and powers the official public site `kinetiqo.org`. Whenever you add, modify, or deprecate any feature, environment variable, CLI command/flag, or web page in Kinetiqo, **you MUST update the static site in `promo-web/` in the same pull request / change turn**:
> 1. **New / Modified Environment Variable**: Update [promo-web/installation.html](file:///h:/WORKING/kinetiqo/promo-web/installation.html) (the single, authoritative source of documentation for all environment variables). Add the variable name, required/optional status, default value, description, and annotated example to the `.env` template block.
> 2. **New / Modified CLI Command or Flag**: Update [promo-web/cli.html](file:///h:/WORKING/kinetiqo/promo-web/cli.html) with full syntax, options, and usage examples.
> 3. **New Feature or Page**: Update [promo-web/index.html](file:///h:/WORKING/kinetiqo/promo-web/index.html) and add/update feature subpages in `promo-web/features/`.
> 4. **Navigation Consistency**: Ensure navigation links in header and footer remain synchronized across all files in `promo-web/`.
> 5. **Mandatory SEO Standards & Sitemap Regeneration**: Any change or addition to HTML files in `promo-web/` MUST strictly comply with the following SEO principles and trigger immediate revalidation of [promo-web/sitemap.xml](file:///h:/WORKING/kinetiqo/promo-web/sitemap.xml):
>    - **Title Tags**: Must be 45–60 characters long. Primary target keywords (`Kinetiqo`, `Strava Data Warehouse`, `PostgreSQL`, `Click CLI`, etc.) must appear early without truncation.
>    - **Meta Descriptions**: Must be 140–160 characters long, summarizing the page content with a clear value proposition.
>    - **Heading Structure**: Exactly ONE `<h1>` tag per page containing primary topic keywords. Heading hierarchy (`<h1>` → `<h2>` → `<h3>`) must be strictly sequential without missing levels.
>    - **Zero Cumulative Layout Shift (CLS)**: Every `<img>` tag MUST specify explicit `width="..."` and `height="..."` attributes.
>    - **Image Alt Tags**: Every `<img>` tag MUST have a descriptive, non-empty `alt="..."` attribute.
>    - **Canonical & Social Open Graph Tags**: Every HTML page MUST contain `<link rel="canonical" href="https://kinetiqo.org/...">`, `<meta name="theme-color" content="#090A0E">`, Open Graph metadata (`og:type`, `og:site_name`, `og:locale`, `og:url`, `og:title`, `og:description`, `og:image`), and Twitter Card metadata (`twitter:card`, `twitter:title`, `twitter:description`, `twitter:image`).
>    - **Sitemap & Robots**: Every new or updated HTML file MUST be added to `promo-web/sitemap.xml` with `<lastmod>` date and priority, and verified against `promo-web/robots.txt`.

---

## 6. AI Agent Guidelines (Gemini & Copilot)

- **Multi-File Edits**: Update multiple files in a single response turn when a change spans repositories, web endpoints, templates, test files, or promo docs (`promo-web/`).
- **Promo Site Synchronization & SEO Compliance**: Always update `promo-web/` (`installation.html`, `cli.html`, `index.html`) whenever changing CLI commands, environment variables, or platform features, and **always enforce strict SEO standards & regenerate `sitemap.xml`** whenever modifying HTML files.
- **Mocked Unit Tests**: Always default to creating fast, mocked unit tests in `tests/`. Do not require live external services or live databases.
- **Complete, Production-Ready Code**: Provide complete code snippets without placeholders or missing imports.
- **No ORMs**: Use parameterized raw SQL queries exclusively across PostgreSQL, MySQL, and Firebird.
- **Strict Compliance**: Follow SonarQube rules for label association (`Web:S6853`), XSS output encoding (`Web:S5725`), SRI hashes, and same-tab internal link navigation.

---

## 7. Development Environment Notes

When running commands in developer environments (e.g., PyCharm SSH terminal vs. local Windows shell):
- Windows path: `H:\WORKING\kinetiqo`
- SSH / POSIX path: `~/WORKING/kinetiqo`

Commands run inside an SSH session must use POSIX paths (`cd ~/WORKING/kinetiqo && python -m pytest -o pythonpath=src`).
