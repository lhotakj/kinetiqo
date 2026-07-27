# Copilot Instructions for Kinetiqo Project

## 1. Project Overview

Kinetiqo is a Python fitness-data platform that syncs activities from the **Strava API**, stores them in a relational database, and serves them through a web dashboard. It supports three database backends (PostgreSQL, MySQL, Firebird) via a Repository/Factory pattern and exposes both a **Click CLI** and a **Flask web UI**.

The web UI includes:
- A searchable and filterable activity list powered by **DataTables 2.x** with column reordering (ColReorder), export (Buttons), and bulk actions.
- Interactive activity mapping using **Leaflet.js** with multiple tile providers and a Canvas renderer.
- A **Fitness & Freshness** chart (CTL/ATL/TSB) based on suffer score, calculated with pandas.
- A **Power Skills** spider chart analyzing best average power over various durations (5s–1h).
- **FTP Estimation**: 95% of best 20-minute average power, with history chart.
- **VO₂max Estimation**: Townsend method from 5-minute MAP power, with trend and classification bands.
- **Activity Goals**: Weekly/monthly/yearly distance and elevation goals per activity type.
- **MEGA Stats**: Year/period infographic with persisted font-size, left-column width, and activity-group controls. Cycling is split into Cycling, Cycling (indoor), and Cycling (outdoor), and the page uses the shared `DATE_FORMAT` for its displayed dates.
- HTMX-powered reactivity for features like real-time sync progress via SSE.
- An asynchronous, cached check for new application versions against GitHub releases.
- **Dark mode** support with system preference detection and manual toggle.
- **Response compression** via `flask-compress` (gzip/brotli) for all HTTP responses.
- **Session-based authentication** via `flask-login`.

## 2. Testing Philosophy: Mocked Unit Tests First

**This is a critical instruction.** The default testing strategy for this project is **fast, isolated unit tests**. All external dependencies, especially the database and the Strava API, **must be mocked**.

- **When asked to create tests, always provide mocked unit tests by default.** Do not create integration tests that require a live database unless specifically requested.
- **Use `unittest.mock.patch`** to intercept calls to external services. The primary targets for patching are `kinetiqo.sync.create_repository`, `kinetiqo.cli.create_repository`, and `kinetiqo.sync.StravaClient`.
- **Canonical Example:** The file `tests/test_sync_logic.py` is the gold standard for how tests should be written in this project. Follow its structure (class-level patches, `subTest` for matrix tests) precisely.
- **Existing test files:** `test_sync_logic.py`, `test_cli_sync.py`, `test_ftp.py`, `test_vo2max.py`, `test_stats.py`.
- **Running tests:** `PYTHONPATH=src python -m unittest discover -s tests -v` (dependencies must be installed; in Docker the environment is pre-configured).

## 3. Key Technologies & Versions

| Concern | Technology | Version | Notes |
|---|---|---|---|
| Language | **Python** | 3.14 | Dockerised on `python:3.14-slim` |
| Testing | **unittest** + **unittest.mock** | stdlib | No pytest |
| Web framework | **Flask[async]** + **flask-login** | 3.1.3 / 0.6.3 | Jinja2 templates, Gunicorn (25.3) in production |
| Response compression | **flask-compress** | 1.24 | Automatic gzip/brotli for all responses |
| Frontend CSS | **Tailwind CSS** | CDN (play) | No build step |
| Reactivity | **HTMX** + **htmx-ext-sse** | 2.0.4 / 2.2.2 | SSE for sync progress |
| Data tables | **DataTables** + **Buttons** + **ColReorder** | 2.3.7 / 3.2.6 / 2.1.2 | Client-side processing mode |
| Charting | **Chart.js** + **chartjs-adapter-moment** | 4.x / 1.0 | Client-side rendering |
| Maps | **Leaflet.js** | 1.9 | Canvas renderer, server-side tile proxy |
| Dropdowns | **Select2** | 4.1 | Activity type filter |
| Date pickers | **DateRangePicker** + **Moment.js** | latest / 2.30 | Date filter presets |
| Drag & drop | **SortableJS** | 1.15 | Column reorder in activities grid |
| CLI | **Click** | 8.3.2 | Entry point: `python src/kinetiqo.py <command>` |
| Database drivers | **psycopg2-binary**, **mysql-connector-python**, **firebird-driver** | 2.9.11 / 9.6.0 / 2.0.2 | Raw SQL — no ORM |
| HTTP client | **httpx** | 0.28.1 | For async Strava & GitHub API calls |
| Data processing | **pandas** | 3.0.2 | Used for Fitness (CTL/ATL) calculations |
| Versioning | **packaging** | 26.0 | For SemVer comparisons |

## 4. Project Structure

```
src/
├── kinetiqo.py                 # CLI entry point (Click)
├── app.py                      # Alternative WSGI entry point
└── kinetiqo/                   # Core application package
    ├── __init__.py
    ├── __main__.py
    ├── cache.py                 # Strava API response cache
    ├── cli.py                   # Click CLI commands (sync, web, flightcheck, version)
    ├── config.py                # Config dataclass (reads all env vars)
    ├── strava.py                # Strava API client (OAuth2, activity streams)
    ├── sync.py                  # SyncService (core sync logic, SSE progress)
    ├── version_check.py         # Async GitHub release version check
    ├── db/
    │   ├── repository.py        # DatabaseRepository ABC (contract for all backends)
    │   ├── factory.py           # create_repository() factory
    │   ├── schema.py            # DDL schema definitions
    │   ├── postgresql.py        # PostgreSQL implementation (raw SQL)
    │   ├── mysql.py             # MySQL/MariaDB implementation (raw SQL)
    │   └── firebird.py          # Firebird implementation (raw SQL)
    └── web/
        ├── app.py               # Flask app, all routes & JSON API endpoints (~1700 lines)
        ├── auth.py              # flask-login User model & auth helpers
        ├── fitness.py           # CTL/ATL/TSB calculation (pandas)
        ├── fonts.py             # Single source of truth for all 20 Google Fonts
        ├── vo2max.py            # VO₂max estimation (Townsend method)
        ├── progress.py          # SSE sync progress stream
        ├── static/
        │   ├── css/google_fonts_local.css   # Generated @font-face CSS (self-hosted)
        │   └── fonts/           # 15 woff2 files baked into Docker image (Inter, Italiana)
        └── templates/           # Jinja2 templates (base.html + 15 page/partial templates)
tests/
├── test_sync_logic.py           # Canonical mocked unit test example
├── test_cli_sync.py             # CLI sync command tests
├── test_ftp.py                  # FTP estimation tests
├── test_vo2max.py               # VO₂max estimation tests
└── test_web_fonts.py            # Google Fonts catalog & local font helpers
```

## 5. Architecture & Design Patterns

### 5.1 Repository Pattern (Database)
- **`DatabaseRepository`** (ABC in `db/repository.py`) defines the contract. Key methods include `upsert_activity`, `get_activities_web`, `get_activities_totals`, `get_profile`, `upsert_profile`, `get_goals`, `upsert_goal`, `get_activity_streams`, `get_elevation_streams_for_activity`, etc.
- The **`create_repository()`** factory in `db/factory.py` is the single entry point for creating a database object. **This is the primary function to mock in tests.**
- All three backends (`postgresql.py`, `mysql.py`, `firebird.py`) implement identical SQL logic adapted to each dialect.
- **Firebird** uses `?` parameter placeholders and quoted identifiers; **PostgreSQL** and **MySQL** use `%s`.

### 5.2 Web Layer & Data Visualization
- The Flask app in `kinetiqo/web/app.py` defines all routes and API endpoints. It uses `flask-compress` for automatic response compression.
- Data-heavy pages render a template shell, which then calls a JSON API endpoint (e.g., `/api/fitness_data`, `/api/ftp_history`, `/api/vo2max_history`, `/api/activities`) to load data for client-side rendering with Chart.js or DataTables.
- The activities page uses client-side DataTables processing with extensive localStorage state persistence (column visibility, order, sort, filters, selection).
- The MEGA Stats page also persists its controls in localStorage (font size, left-column width, selected activity group) and formats dates with `DATE_FORMAT`.
- Map rendering uses compact `[lat, lng]` arrays via `/api/map/data` with Leaflet Canvas renderer.
- **Internal app navigation stays in the same tab.** Only external links (Strava, documentation, license URLs) open in new tabs.

### 5.3 Configuration
- All configuration is via environment variables, read in the `Config` dataclass (`config.py`).
- Athlete weight resolution order: (1) profile DB table (synced from Strava), (2) Settings page, (3) `ATHLETE_WEIGHT` env var fallback.
- Map API keys (`MAPY_API_KEY`, `THUNDERFOREST_API_KEY`) conditionally show/hide tile layer options.

### 5.4 Logging
- The web layer currently uses standard `logging` module (`logging.getLogger("kinetiqo.web")`).
- The sync/CLI layer is migrating to `loguru.logger`. Use `loguru.logger` for all new logging in non-web code.

### 5.5 Frontend Patterns
- All frontend libraries are loaded from CDN — **no build step** required.
- Templates extend `base.html` which provides the sidebar layout, dark mode, and shared CDN imports.
- Reusable partials are prefixed with `_` (e.g., `_activity_filter.html`, `_activity_type_selector.html`, `_period_select.html`).
- Grid state (column visibility, order, sort) is persisted to `localStorage` with a schema version key for migrations.

### 5.6 Self-Hosted Fonts (no CDN for base UI)
- **`kinetiqo/web/fonts.py`** is the single source of truth for all 20 Google Fonts used by the app. Adding a font means adding it here.
- **Inter** and **Italiana** (the two fonts used on every page) are **self-hosted**: woff2 files are committed to `src/kinetiqo/web/static/fonts/` and baked into the Docker image. Zero internet dependency at runtime.
- `google_fonts_local.css` contains the `@font-face` declarations pointing to the local woff2 files. It is committed to the repo; regenerate with `python development/download-fonts.py --force`.
- `base.html` uses `<link rel="preload" as="font" crossorigin>` for the three critical woff2 files to prevent FOUT. **`crossorigin` is mandatory on font preloads** even for same-origin — the browser requires it for `@font-face` resources.
- The **poster page** uses a CDN URL for its 15+ poster-specific fonts (Oswald, Ubuntu, Bebas Neue, etc.) since they are not used on other pages and not worth self-hosting.

### Frontend includes & CDN best-practices

This project relies on CDN-delivered frontend assets but must follow strict rules to ensure security, stability, and performance. Copilot must apply these rules whenever modifying templates, upgrading libraries, or adding includes.

Key rules
- Pin exact CDN versions in URLs (no "latest" or floating tags).
- Always include Subresource Integrity (SRI) and set crossorigin="anonymous" when pulling cross-origin resources.
- Add rel="preconnect" hints for major CDN domains in <head> to reduce connection latency.
- Preload critical, self-hosted fonts with <link rel="preload" as="font" crossorigin>.
- Defer/async non-critical scripts and place them at the end of body where appropriate.
- Confirm plugin compatibility (DataTables core version must match plugins/extensions).
- Update license.html with library name + pinned version whenever changing CDN URLs.

Example include snippets (replace SRI placeholders and versions)

<!-- Preconnect for Google Fonts and CDN -->
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>

<!-- CSS: DataTables core + extension (pinned) with SRI and crossorigin -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/datatables@2.3.7/css/datatables.min.css" integrity="sha384-<SRI>" crossorigin="anonymous">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/datatables-buttons@3.2.6/css/buttons.dataTables.min.css" integrity="sha384-<SRI>" crossorigin="anonymous">

<!-- Preload critical woff2 (self-hosted) -->
<link rel="preload" as="font" href="/static/fonts/Inter-Variable.woff2" type="font/woff2" crossorigin>

<!-- JS: Defer non-critical scripts -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" integrity="sha384-<SRI>" crossorigin="anonymous" defer></script>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js" integrity="sha384-<SRI>" crossorigin="anonymous" defer></script>

When to self-host
- Self-host fonts used across the site (Inter, Italiana) and critical assets that are required on every page to ensure availability in restricted networks.
- Self-hosted assets should be versioned in filenames and served with long Cache-Control and immutable headers.

Frontend includes checklist (must follow when editing templates)
1. Pin version in URL.
2. Add integrity and crossorigin="anonymous" for cross-origin resources.
3. Add rel="preconnect" for new CDN domains in head.
4. Preload critical fonts with crossorigin.
5. Defer/async or place scripts at end-of-body when not required for initial render.
6. Verify plugin compatibility for DataTables and other plugin-ecosystem libs.
7. Update license.html with pinned version.
8. Run automated validation (see below).

SonarQube findings — required handling
- Web:S6853 (Form label association): ensure every <label> element is associated with a form control and has accessible text. When editing templates:
  - Prefer using <label for="..."> with a matching control id, or wrap the control inside the <label>.
  - Do not use <label> for non-form text; use <div> or <span> instead.
  - For non-standard controls, provide aria-labelledby or aria-label to associate the label.
  - When modifying templates, update or add id attributes to inputs/selects/textareas so labels can reference them.
  - Add unit tests (mocked) where appropriate to render templates and assert label-for pairs exist for important forms.

- Web:S5725 (Unsafe template insertion / XSS protections): ensure all user-controlled data is properly escaped or serialized before insertion into HTML or JavaScript. Recommended rules:
  - Keep Jinja2 autoescape enabled for HTML templates. Use the |e filter for explicit HTML escaping when needed.
  - When embedding values into JavaScript, use the |tojson filter to safely serialize values.
  - Avoid marking untrusted input with |safe; only do so after an explicit, reviewed sanitization step.
  - Avoid constructing HTML via string concatenation in client-side JS using untrusted data; prefer setting textContent, value, attributes, or using template elements and cloning.
  - Audit and avoid use of innerHTML, document.write or similar with untrusted content. If innerHTML is necessary, sanitize input with a vetted library.
  - Add/verify CSP (Content-Security-Policy) headers where appropriate and use safe defaults.
  - Add unit tests that ensure templates escape or serialize example malicious payloads correctly (mocked rendering tests).

Guidance for Copilot edits
- When Copilot modifies templates, automatically check for label-control associations and missing ids; fix S6853 by adding for/id or replacing non-form <label> with semantic elements.
- When Copilot inserts dynamic values into templates or JS, favor |e and |tojson and avoid |safe. Add a short comment where a |safe is used explaining why it is safe and link to the security review.
- Run the automated validation script (see above) after template edits to catch floating CDN tags and missing integrity attributes, and extend it to flag label elements without an associated control.
- When addressing Sonar findings in a PR, include a brief note in the PR description referencing the Sonar rule(s) and summarizing the applied fixes (e.g., "Fixed Web:S6853 by adding for/id pairs in login and settings templates; fixed Web:S5725 by replacing unsafe innerHTML usage with textContent and using |tojson where needed").

Automated validation (recommended)
Provide a small script (python/node) that checks templates for:
- Unpinned CDN URLs (flags any "latest" or floating tag).
- Presence of integrity and crossorigin attributes for CDN includes.
- Verifies that rel="preconnect" is present for newly introduced CDN domains.
- Optionally fetches the resource to verify SRI hash matches the content.

Security & CSP notes
- SRI requires crossorigin to function for cross-origin resources; ensure both are present.
- If CSP is in use, update script-src/style-src/font-src/img-src accordingly and prefer nonces for inline scripts over allowing unsafe-inline.

Caching, compression & headers
- Continue using flask-compress for gzip/brotli responses.
- Serve static JS/CSS/fonts with far-future Cache-Control and immutable when filename is versioned.

Fonts lifecycle (brief)
- Add font names to kinetiqo/web/fonts.py when adding Google Fonts.
- Run development/download-fonts.py --force to fetch woff2 and regenerate google_fonts_local.css. This repository script is the recommended, single-source method because it reads kinetiqo/web/fonts.py and writes consistent @font-face rules.
- Commit generated woff2 files and CSS to src/kinetiqo/web/static/fonts and src/kinetiqo/web/static/css.
- Add preload hints for critical fonts in base.html with crossorigin.

Downloading Google Fonts (concrete methods)

A. Project script (recommended)
- Usage (PowerShell):
  python development/download-fonts.py --force
- Usage (Bash):
  python3 development/download-fonts.py --force
- The script downloads the families declared in kinetiqo/web/fonts.py (woff2), regenerates src/kinetiqo/web/static/css/google_fonts_local.css, and places files in src/kinetiqo/web/static/fonts. Commit the files after verifying the CSS and preload hints.

B. Using google-webfonts-helper (npm alternative)
- Install: npm install -g google-webfonts-helper
- Example (download Inter woff2 and output CSS):
  google-webfonts-helper --family "Inter" --variants "400;700;variable" --formats "woff2" --output "src/kinetiqo/web/static/fonts" --css > src/kinetiqo/web/static/css/google_fonts_local.css
- Adjust paths or move files as needed; add preload hints to base.html.

C. Manual method (HTTP + curl/wget)
- Fetch the Google-provided CSS (use a browser-like User-Agent to get the proper rules):
  curl -s "https://fonts.googleapis.com/css2?family=Inter:wght@100;400;700&display=swap" -H "User-Agent: Mozilla/5.0" -o inter.css
- Inspect inter.css for woff2 URLs and download each file:
  curl -LO "https://fonts.gstatic.com/s/inter/vX/.../inter-VariableFont.woff2"
- Create or adjust local @font-face rules in src/kinetiqo/web/static/css/google_fonts_local.css to point to the downloaded files in src/kinetiqo/web/static/fonts.

SRI, preloads & headers
- Add <link rel="preload" as="font" href="/static/fonts/Inter-Variable.woff2" type="font/woff2" crossorigin> for critical fonts.
- Serve fonts with correct Content-Type and long Cache-Control (immutable) when filenames are versioned.
- SRI is typically used for JS/CSS; if calculating SRI for a CDN JS/CSS include use: openssl dgst -sha384 -binary | openssl base64 -A (example shown in the appendix).

Notes & best-practices
- Prefer the project's download-fonts.py to keep a single source of truth and reproducible assets.
- Always commit downloaded font files and regenerated CSS to ensure offline availability and reproducible builds.
- Add preload hints and crossorigin to prevent FOUT and to satisfy browser requirements for @font-face resources.

Developer guidance for Copilot
- Follow the frontend includes checklist when editing templates.
- When upgrading a library, update license.html and run the validation script.
- Avoid inline scripts/styles; if necessary for CSP, use nonces and document them.

Applying changes
- This guidance should be inserted into copilot-instructions.md; follow the checklist and validation script before committing template edits.


## 6. Common Tasks & How-To

### Add a new feature with a web UI
1.  **Create the data logic** in a new file (e.g., `kinetiqo/web/my_feature.py`).
2.  **Define the route** in `kinetiqo/web/app.py` to render the template. Use `async def` for new routes.
3.  **Add a JSON API endpoint** in `app.py` to provide data for the UI. Use `async def`.
4.  **Create the template** in `kinetiqo/web/templates/`, extending `base.html`.
5.  **Write a mocked unit test** for the new logic. Create a new test file in `tests/` that mocks the database and any other external services, following the pattern in `tests/test_sync_logic.py`.

### Add a new database query
1.  Add the new method as an `@abstractmethod` in `db/repository.py`.
2.  Implement the method in all three concrete repositories (`postgresql.py`, `mysql.py`, `firebird.py`) using raw parameterised SQL.
3.  **Write a mocked unit test** that verifies the application logic correctly calls your new repository method with the expected arguments.

### Update a frontend library version
1.  Update the CDN URL in `base.html` (for core libs) or the relevant page template (for page-specific libs like Buttons, ColReorder).
2.  Verify plugin compatibility — DataTables plugins must be compatible with the core DataTables version.
3.  Update the version number in `license.html` in the Frontend Libraries table.

### Add or refresh a Google Font
1.  Add the font name to `GOOGLE_FONTS` in `kinetiqo/web/fonts.py` and to the relevant `*_FONT_NAMES` tuple (`BASE_GOOGLE_FONT_NAMES`, `POSTER_GOOGLE_FONT_NAMES`, etc.).
2.  Run `python development/download-fonts.py` to download the woff2 files and regenerate `google_fonts_local.css`. Use `--force` to re-download existing files.
3.  Commit the new woff2 file(s) and the updated CSS to the repository.
4.  Add a `<link rel="preload">` hint in `base.html` if the font is used on every page (FOUT prevention).
5.  Update the font attribution table in `license.html`.

## 7. Copilot-Specific Behaviour

- **Provide complete, runnable code snippets.** When editing a file, show the full file content, not just the changed lines.
- **Focus on one file at a time.** Do not attempt to make changes to multiple files in a single response.
- **When asked to create tests, always provide mocked unit tests by default.** Follow the structure in `tests/test_sync_logic.py`.
- **Always update all three database backends** when changing the `DatabaseRepository` interface, but do so in separate, sequential steps.
- **Use the `packaging.version.parse()` function** for any semantic version comparisons.
- **Use raw, parameterised SQL.** Do not introduce an ORM.
- **Use `loguru.logger`** for all operational output in non-web code. Use standard `logging` in `web/app.py`.
- **Follow the established import and type-hinting style.**
- **New configuration should be added as an environment variable** in the `Config` dataclass.
- **When updating CDN library versions**, also update `license.html` to keep the attribution page accurate.
- **Internal app links must stay in the same browser tab.** Only external links (Strava, documentation, third-party sites) should use `target="_blank"`.
- **When adding a Google Font**, update `fonts.py` (single source of truth), run `development/download-fonts.py`, commit woff2 + CSS, and update `license.html`.
- **Poster elevation data** (`/api/poster/elevation/<id>`) reads from the local `streams` DB table first via `repo.get_elevation_streams_for_activity()`. Strava is only called if DB has no rows for that activity. Never add direct Strava calls to this or other data endpoints that serve already-synced data.

## 8. Development environment: PyCharm SSH terminal mapping

Note: on some developer machines the project files are accessible from Windows as a mapped drive (for example
`H:\WORKING\kinetiqo`), while the PyCharm built-in terminal is connected to a remote SSH session where the
same repository is mounted under a POSIX home path (for example `~/WORKING/kinetiqo`). This difference matters when
running console commands inside the PyCharm terminal — use the SSH/remote path (~/WORKING/kinetiqo) there, not the
Windows-style `H:\...` path.

Examples:

From the PyCharm terminal (SSH session):

```bash
cd ~/WORKING/kinetiqo && python -m pip install --user pydocstyle && python -m pydocstyle src
```

From a local Windows PowerShell or CMD where the repo is mounted as H::

```powershell
cd H:\WORKING\kinetiqo
python -m pip install pydocstyle
python -m pydocstyle src
```

When you share terminal output or ask for help, please state which path you used and whether the terminal was an
SSH (remote) session or a local Windows shell. That prevents confusion (for example, `cd H:/WORKING/kinetiqo` will fail
inside an SSH shell where the code lives under `~/WORKING/kinetiqo`).

This repository note helps contributors and automation know which path to use when running commands in the
PyCharm-built terminal vs. locally on Windows.

### Tailwind self-hosting
- Tailwind Play CDN script is self-hosted at src/kinetiqo/web/static/vendor/tailwind/tailwind.js to avoid CORS issues with the play CDN.
- Version detected: play-cdn. Record the specific version in the file header when updating.
- When updating Tailwind: fetch the Play CDN script from https://cdn.tailwindcss.com and replace the local file; update the version comment in the file header and in this note.
- Prefer building a production CSS via Tailwind CLI for deterministic builds; if unable, self-hosting the Play CDN script is an acceptable fallback for local/offline environments.
