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
- **MEGA Stats Infographic**: Infographic with selectable period/activity groups, custom photo background upload & reset, configurable tint overlay and opacity slider, font selector (Inter, Italiana, Outfit, etc.), unified collapsible control panels (Stats Options, Appearance, Size, Period), responsive column width with stacked default (20%) and expanded full-width row layout (>20% up to 50%), most active month by distance & elevation metrics, custom date formatting, full localStorage state persistence, and vector PDF / PNG export.
- **Activity Poster Generator**: WYSIWYG poster builder with elevation profile, custom fonts, 4:3 / 16:9 / 1:1 aspect ratios, background photo mode (with clear image option) or interactive Leaflet map mode (tile provider selection, map opacity control, route line color/opacity/weight), collapsible control boxes with element checkboxes, and Playwright-powered PNG export.
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
| Web Framework | **Flask[async]** + **flask-login** | 3.1.3 / 0.6.3 | Jinja2 templates, Gunicorn 26.2.0 in production |
| Session & CSRF | **Flask-WTF** / **flask-login** | 1.3.0 / 0.6.3 | CSRF tokens on all POST/PUT/DELETE routes |
| Response Compression | **flask-compress** | 1.25 | Automatic gzip/brotli compression |
| Frontend CSS | **Tailwind CSS** | v4 CLI (4.3.3) | Compiled to `static/css/tailwind.css` via `download-tailwind.sh` |
| Reactivity | **HTMX** + **htmx-ext-sse** | 2.0.10 / 2.2.2 | SSE for sync progress bar |
| Data Tables | **DataTables** + **Buttons** + **ColReorder** | 2.3.7 / 3.2.6 / 2.1.2 | Client-side processing mode with SRI |
| Charting | **Chart.js** + **chartjs-adapter-moment** | 4.5.1 / 1.0 | Client-side Canvas rendering |
| Maps | **Leaflet.js** | 1.9.4 | Canvas renderer, self-hosted vendor files, server-side tile proxy |
| CLI | **Click** | 8.5.0 | Entry point: `python src/kinetiqo.py <command>` (`web`, `sync`, `flightcheck`, `benchmark`) |
| Database Drivers | **psycopg2-binary**, **mysql-connector-python**, **firebird-driver** | 2.9.13 / 9.7.0 / 2.0.3 | Parameterized raw SQL — **no ORM** |
| HTTP Client | **httpx** / **requests** | 0.28.1 / 2.34.2 | Async/sync clients for Strava & GitHub APIs |
| Data Processing | **pandas** | 3.0.5 | CTL/ATL/TSB calculation |
| Browser Automation | **Playwright** | ≥1.63.0 | PNG poster and infographic rendering |
| Image Processing | **Pillow** | ≥12.3.0 | Poster and image processing |
| Date Parsing | **python-dateutil** | ≥2.9.0.post0 | Date parsing utilities |
| Versioning | **packaging** | ≥26.3 | SemVer comparisons |

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

### 4.4 Form Accessibility & Control Association (Sonar Web:S6853 / Web:InputWithoutLabelCheck)
- **Mandatory Form Labeling**: Every form control (`<input>`, `<select>`, `<textarea>`, including checkboxes, radio buttons, file uploads, range sliders, and color pickers) MUST have an associated accessible label.
  - Use `<label for="element_id">` with a matching `id="element_id"` on the control.
  - Or nest the control inside a `<label>` element.
  - Always provide an explicit `aria-label` or `aria-labelledby` on inputs (e.g. `aria-label="Toggle Activity Name on poster"`).
  - Checkboxes and toggles (e.g. `.box-visible-checkbox`, toggle switches, and header controls) must always have an associated `<label for="...">` or wrap the text description in a `<label>`.
- Do not use `<label>` tags for non-form labels or section headers; use `<div>` or `<span>`.
- Provide `aria-label` or `aria-labelledby` for custom controls and collapse buttons.

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
- **Dynamic Copyright Year**: All template footers (`base.html`, `login.html`, `license.html`) MUST render `&copy; {{ current_year }} Jaroslav Lhoták` via Flask context processor (`@app.context_processor`). Never hardcode fixed year numbers.
- **Footer Links & Brand Icons**: Footer links (e.g. GitHub link and logo) must use matched, theme-adaptive text/icon colors, proper padding, and no underlines across light and dark modes.
- **State Persistence**: Grid controls, column visibility, and page settings saved to `localStorage` must include schema version keys to support smooth UI migrations.

### 4.9 Web Input Validation & Error Highlighting Standards
- **Server-Side Validation Mandatory**: All user input forms and textareas (e.g. `UPDATE_STRAVA_*` description templates, Athlete FTP, Weight) must perform strict server-side validation and return HTTP 422 Unprocessable Entity with `{ "error": "...", "field": "..." }` on violation.
- **FTP Validation Bounds**: FTP must be numeric, strictly greater than 0, and not exceeding 1000 W (`0 < FTP <= 1000`).
- **Template Validation**: Enforce brace count matching (`{{` vs `}}`) and validate placeholders against recognized tokens/rules.
- **Message Location & Alignment**: Validation messages (**`Saved ✓`** or error strings) must be left-aligned directly adjacent to the input field's label using flex layout (`flex items-center gap-2 mb-1`).
- **Theme-Aware Error Highlighting**: When validation fails, the input text box background must highlight in a light red tone (`bg-red-50 dark:bg-red-950/40 border-red-400 dark:border-red-600` or direct inline style override) in both light and dark modes.
- **Auto-Restoration**: When corrected to a valid value, the text box background restores to default (`bg-white dark:bg-zinc-700`), the green **`Saved ✓`** confirmation displays next to the label, and auto-fades after 3 seconds.

### 4.10 Poster & Map Tone Opacity Isolation Standard
- **Background Tone Opacity**: In both Poster and Map views, the "Tone Opacity" control strictly affects only the background fill tint / overlay layer. It must NEVER affect or dim other canvas elements (such as GPS route polyline, track points, text boxes, elevation profiles, or stats widgets).

### 4.11 Mega Stats Infographic Design, Metric Separator & Control Panel Standards
- **Metric Divider Standard**: Every metric block in `#ig-stats` MUST have a corresponding `<div class="ig-stat-divider" id="ig-<key>-divider"></div>` immediately following its container element in HTML templates. In JavaScript `STAT_DEFS`, every metric entry MUST declare its divider ID (`div: 'ig-<key>-divider'`). The `applyStatVisibility()` function dynamically hides the divider after whichever metric happens to be the last visible stat, guaranteeing tiny 1px separator lines (`border-top: 1px solid rgba(255,255,255,0.08)`) are displayed between all adjacent metrics without trailing divider lines at the bottom of the stats column.
- **Responsive Column Width & Full-Width Expanded Layout Standard**:
  - At default 20% column width (`data-layout="stacked"`), metrics use standard vertical stacking where label sits directly above value.
  - When column width is widened (`> 20%` up to `50%`, `data-layout="expanded"`), `#ig-stats` explicitly sets `flex: 0 0 [val]%; width: [val]%;`. Each metric wraps label and value in `<div class="ig-stat-row">` styled with `display: flex; justify-content: space-between; align-items: baseline; gap: 12px;` so that labels stay left-aligned and values align flush against the right column boundary, fully covering the wider left column. Details span cleanly across below the metric row, and dividers span full width.
- **Appearance Controls & Reusable Partials**: The Appearance box provides background photo upload and reset (`_image_upload_buttons.html`), tint color picker (`_control_color_tint.html`), opacity slider (`_control_range.html`), and typography font selector (`_font_select.html`) shared with Poster Generator.
- **Unified Stats Options & Collapsible Panels**: Title Size, Col Width, and Visible Stats checkboxes are unified inside a single collapsible "Stats Options" box with balanced spacing. All control boxes are collapsible via chevron toggles, Open by default, and persisted in `localStorage`.
- **Control Panel Uniformity**: In Visible Stats control panels, every checkbox label MUST use uniform `text-xs` (12px) font size across light and dark modes. Checkbox `<input>` elements must enforce `flex-shrink-0 mr-1` and `style="margin-right: 3px;"` to maintain 3px spacing between the checkbox box and label text. Label text containers must enforce `min-w-0 overflow-hidden whitespace-nowrap <span class="truncate">` to prevent line wrapping or column overlap.
- **Typography & Label Clipping**: Metric labels in `.ig-stat-label` MUST enforce `white-space: nowrap`, `overflow: hidden`, `text-overflow: ellipsis`, letter spacing `0.08em`, font weight 600, opacity 0.55, and scaled font size (`calc(var(--stats-font-size) * 0.38)`).
- **Extended State Persistence**: `statsSize`, `statsYear`, `statsPeriod`, `statsBgColor`, `statsActivityGroup`, `statsFontFamily`, `statsTint`, `statsOpacity`, `statsTitleFontSize`, `statsColumnWidth`, `statsVisibleStats`, and box collapse states MUST be persisted to `localStorage` and restored on `DOMContentLoaded`.

---

## 5. Common Development Workflows

### Add a New Web Feature
1. Create core logic in a module under `kinetiqo/web/` (e.g., `kinetiqo/web/feature.py`).
2. Add routes (`async def`) and JSON API endpoints in `kinetiqo/web/app.py`.
3. Create Jinja2 templates in `kinetiqo/web/templates/` extending `base.html`.
4. Follow accessibility (S6853) and XSS (S5725) rules.
5. Write mocked unit tests in `tests/test_feature.py`.

IMPORTANT: Any new feature, endpoint, CLI command, or public API change MUST include corresponding unit tests. Pull requests that add or modify functionality without appropriate tests will be returned for coverage before merging.

### Update 3rd Party Components

When executing an 'update 3rd party components' workflow, follow these structured steps:

1. **Check Latest Versions**: Review pip packages, JS vendor libraries, and CSS tools against their latest available versions.
2. **Provide Component Matrix**: Present a matrix of all components showing current version, available version, and nature of the change (major/minor/patch).
3. **Analyze & Suggest**: Based on release notes and semantic versioning, suggest which packages are safe to update (typically minor/patch) and which should be deferred or skipped.
4. **User Decision**: Wait for the user to confirm the update plan.
5. **Download & Clean**: Run the download tool with the --clean flag to ensure the endor/ directory is cleared of stale files before pulling the approved versions.
6. **Update Code**: Update 
equirements.txt and any corresponding endor-libraries.yaml configurations.
7. **Update Documentation**: Synchronize versions in README.md, AGENTS.md (Key Technologies matrix), and src/kinetiqo/web/templates/license.html.
8. **Run Tests**: Execute the test suite to ensure all tests still pass.
9. **Final Report**: Provide a summary report of the updates, highlighting any significant items from the release notes.

### Update the Database Interface
1. Add abstract methods to `DatabaseRepository` (`db/repository.py`).
2. Implement parameterized raw SQL in `postgresql.py`, `mysql.py`, and `firebird.py`.
3. Add unit tests asserting that repository methods are called with expected parameters.

### Add or Refresh Google Fonts

When adding a new Google Font to the offline font library, execute every step below in order. Skipping any step will leave the font partially integrated.

#### Step 1: Identify the font on Google Fonts
- Visit the Google Fonts specimen page (e.g. `https://fonts.google.com/specimen/Fanwood+Text`).
- Note the **font family name** (exactly as shown on Google Fonts), the **designer/foundry**, the **specimen URL**, and the **stylesheet fragment** (e.g. `Fanwood+Text:ital@0;1` or `Roboto:wght@400;700`).
- The stylesheet fragment encodes which axes, styles, and weights to download. Use `wght@400;700` for standard regular+bold, `ital@0;1` for normal+italic, or variable axis ranges as appropriate.

#### Step 2: Register in `GOOGLE_FONTS` catalog (`src/kinetiqo/web/fonts.py`)
- Add a new `GoogleFont(...)` entry to the `GOOGLE_FONTS` tuple (maintain alphabetical order within the "Added fonts" section).
- Required fields: `name` (exact Google Fonts family name), `designer`, `specimen_url`, `stylesheet_fragment`.

#### Step 3: Add to the appropriate font group (`src/kinetiqo/web/fonts.py`)
- **Poster fonts**: Add the font name string to `POSTER_GOOGLE_FONT_NAMES` tuple. This makes it available in the poster font dropdown (`_font_options.html`) and triggers download via the poster fonts CSS.
- **Base fonts**: Only add to `BASE_GOOGLE_FONT_NAMES` if the font should load on every page (rare — currently only Inter, Italiana, Merriweather).

#### Step 4: Download woff2 files
- Run `python development/download-fonts.py` (or `--force` to re-download all).
- Verify new `.woff2` files appear in `src/kinetiqo/web/static/fonts/` (e.g. `fanwood-text_normal_latin.woff2`).
- Verify the font's `@font-face` declarations appear in `src/kinetiqo/web/static/css/google_fonts_poster_local.css` (or `google_fonts_local.css` for base fonts).

#### Step 5: Update `license.html` (`src/kinetiqo/web/templates/license.html`)
- The dynamic Google Fonts license table (lines 34–45) auto-renders from the `google_fonts` context variable, so no change is needed there.
- **However**, the static third-party credits table (further down in `license.html`) must have a new `<tr>` row added with: font name, designer, license (`OFL 1.1`), and specimen link.

#### Step 6: Update unit tests (`tests/test_web_fonts.py`)
- Add the new font name to the `test_catalog_includes_new_fonts` subtest tuple.
- Add the new font name to the `test_font_groups_include_expected_fonts` subtest tuple.
- Add the font's stylesheet fragment assertion to `test_stylesheet_url_contains_poster_fonts`.

#### Step 7: Run the full test suite and verify
- Run `python -m pytest -o pythonpath=src -v` and confirm all tests pass (including the updated font tests).
- Optionally start the dev server (`python src/kinetiqo.py web`) and verify the new font appears in the poster font dropdown and renders correctly.

### Update Tailwind CSS
1. Edit template Tailwind classes or `src/kinetiqo/web/static/css/tailwind.input.css`.
2. Run `python development/download-vendor-libraries.py --library tailwind` to compile `src/kinetiqo/web/static/css/tailwind.css`.
---

## 6. AI Agent Guidelines (Gemini & Copilot)

- **Line Endings Standard (LF / Linux format)**: ALWAYS generate, edit, and save files with Unix/Linux line endings (**LF / `\n`**), NEVER Windows CRLF (`\r\n`). All text, python, template, shell, markdown, and config files must use standard UTF-8 without Byte Order Marks (no UTF-8 BOM `\xef\xbb\xbf`).
- **Mocked Unit Tests**: Always default to creating fast, mocked unit tests in `tests/`. Do not require live external services or live databases.
- **Complete, Production-Ready Code**: Provide complete code snippets without placeholders or missing imports.
- **No ORMs**: Use parameterized raw SQL queries exclusively across PostgreSQL, MySQL, and Firebird.
- **Strict Compliance**: Follow SonarQube rules for label association (`Web:S6853` / `Web:InputWithoutLabelCheck`), XSS output encoding (`Web:S5725`), SRI hashes, and same-tab internal link navigation.

---

## 7. Development Environment Notes

When running commands in developer environments (e.g., PyCharm SSH terminal vs. local Windows shell):
- Windows path: `H:\WORKING\kinetiqo`
- SSH / POSIX path: `~/WORKING/kinetiqo`

Commands run inside an SSH session must use POSIX paths (`cd ~/WORKING/kinetiqo && python -m pytest -o pythonpath=src`).


