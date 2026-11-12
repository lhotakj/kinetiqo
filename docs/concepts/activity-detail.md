# Kinetiqo Activity Detail — Implementation Specification

> **Status:** Implemented & Tested (v1.0)  
> **Route:** `/activity/<activity_id>`  
> **Scope:** Dedicated desktop-grade Activity Detail view mimicking Strava's desktop layout, enhanced with deep local telemetry analytics, interactive synchronized multi-channel stream charts, an AI Analysis showcase card, collapsible left-hand infographic sidebar controls (sizing S–XXL, ratio, font, background & text colors, custom background image, element visibility toggles), an AI Agent Re-Prompting control box with real-time status and error checking, and pixel-perfect PNG / vector PDF export via Playwright.  
> **Database support:** PostgreSQL, MySQL, and Firebird (100% Parameterized Raw SQL, zero ORM).  
> **Required project instructions:** Read and follow `AGENTS.md`, `SKILLS.md`, `README.md`, `docs/DATABASE.md`, and `.agents/skills/grill-me/SKILL.md`.

---

## 1. Executive Summary & Product Outcome

The **Activity Detail** page (`/activity/<activity_id>`) provides athletes with an in-depth, self-hosted breakdown of an individual activity synced from Strava. It serves a dual purpose:
1. **Interactive Analytical Dashboard**: Explore full-resolution sensor telemetry, toggle individual streams (Heart Rate, Power, Elevation, Cadence, Speed) with synchronized Leaflet map scrubber cursor, review Coggan power zones, peak MMP intervals, HR zones, climbing grades, stored hourly weather, and generate/inspect AI coaching insights.
2. **Customizable & Exportable Infographic Canvas**: Configure the canvas via a collapsible left-hand sidebar matching Mega Stats and Poster Generator (sizing S–XXL, aspect ratio, custom fonts, background/text colors, custom image overlay with tint/opacity), toggle individual stat visibility, re-prompt AI agents with custom directives, and export pixel-perfect PNG images or vector PDFs via Playwright.

---

## 2. Decision Tree & Grilling Results

During the requirements interrogation sessions, all foundational architectural branches were resolved:

1. **Overall Layout**:
   - **Left-Hand Control Sidebar**: Follows the exact layout, geometry, and styling of Mega Stats (`stats.html`):
     - Sidebar container width: `w-full lg:w-72 flex-shrink-0`.
     - Standard dark control box theme (`#18181b` background, `#202023` headers, `#27272a` borders) with chevron collapse toggles and `localStorage` persistence under `activityDetailBoxCollapsed`.
     - Action buttons: Download PNG and Download PDF (`_infographic_action_buttons.html`).
     - Size box: Presets M (1280px), L (1440px), XL (1600px), XXL (1920px), ratio (Auto / 16:9 / 4:3), and live dimensions display (`_infographic_size_box.html`).
     - Appearance box: Background color picker, text/accent color picker, font selector (`_font_select.html`), generic Font Size Scale range slider (`#detail-font-scale`, -30% to +80%, default 0% / 1.0x, unified via `_control_range.html`), tint overlay (`_control_color_tint.html`), opacity slider (`_control_range.html`), custom background photo upload & reset (`_image_upload_buttons.html`).
     - **Key Metrics Box**: Columns selector (1, 2, 3, 4, 5, or 6 columns) and 15 individual metric toggles (all ON by default, persisted under `actDetail_km_*`).
     - Dedicated Map box: Migrated from `/map` with Base Map select, Map Opacity, Map Color Tone + Clear, Tone Opacity (in Leaflet `tonePane` z-index 250), Route Color, Route Width, and Route Opacity.
     - **Dedicated Telemetry Streams Box**: X-Axis mode segmented toggle (Distance vs Time) and Visible Streams checkboxes (Elevation, Heart Rate, Power, Cadence, Speed — all ON by default).
     - **AI Agent & Re-Prompt Box**: Configured agent selector dropdown, optional custom directive textarea, real-time status indicator, error checking with theme-aware styling, and "Generate / Re-Prompt" action button.
     - Visible Stats / Options box: Checkboxes matching Mega Stats `stat-toggle` styling (uniform `text-xs`, 3px margin, truncation) to toggle individual sections.
   - **Main Canvas & Scaler Preview Area**:
     - Embedded in a responsive preview scaler (`stats-preview-scaler` / `infographic-wrapper`) calculating dynamic scale transforms (`scale = Math.min(1.0, availWidth / width)`) so the entire canvas fits compactly on a single screen without vertical or horizontal scrolling.
     - Top row: Clean activity header with Name on left, Date & Time far on the right, no underline line or sport badge clutter.
     - Hero overview: 2-column side-by-side design (`#overview-two-col`, 50% Key metrics grid on left, 50% Leaflet route map on right with matched height and robust `invalidateSize()` tile rendering). Leaflet zoom controls (+ -) are suppressed during PNG/PDF exports.
     - Middle row: Compact telemetry multi-stream profile chart with clickable stream lozenges (Elev, HR, Power, Cadence, Speed) floating without underline separator lines.
     - Bottom row: Compact AI Analysis card (2-line quote with scroll) + 5-column analytical card grid (Power Zones, Peak MMP, HR Zones, Climb, Stored Weather) designed for optimal horizontal space utilization without underline lines below widget titles.
2. **Canvas Sizing & Ratio**:
   - Default: **Auto Height (Fit All Content)** so all enabled cards fit cleanly without vertical clipping during PNG/PDF export.
   - Selectable fixed ratios (**4:3** and **16:9**) available in the ratio dropdown if the athlete desires a constrained poster/infographic frame.
   - Width presets: S (1024px), M (1280px), L (1440px), XL (1600px), XXL (1920px).
3. **Typography & Styling**:
   - Single unified Font Selector (`_font_select.html`) controlling the entire activity detail canvas (Inter, Italiana, Outfit, Space Grotesk, Roboto, Oswald, Playfair Display, etc.).
   - Background Color picker (`<input type="color">`) + Page Text/Accent Color picker.
   - Tint color picker and Opacity range slider (0–100%) for custom background image styling.
4. **AI Agent Selection, Re-Prompting & Database Persistence**:
   - **Database Storage**: Persisted directly in `activities.ai_responses` JSON column under key `agent-ai-<agent_name>` using `repo.update_activity_ai_responses(activity_id, ai_responses)`.
     - *Advantages*: Zero schema migration required, 100% database portability (PostgreSQL, MySQL, Firebird), immediately reflects on both Activity Detail canvas and `activities.html` grid table, and integrates seamlessly with `{{agent-ai-<name>}}` placeholders for Strava description updates.
   - **Sidebar Prompt Actions & Cached Status**:
     - Agent pulldown displays cached status directly in each option (e.g. `coach (cached)` vs `witty`).
     - Dynamic action button: shows **"Run prompt"** when no cached response exists for the selected agent, and **"Re-prompt"** when a response is already cached.
     - Removed one-off "Custom Directive" field to keep the prompt workflow focused and streamlined.
   - **Execution & Real-Time Progress**:
     - *Running State*: Button replaces with rotating `kinetiqo-loading-32x32.webp` icon (disabled per UI loading standards), sidebar status displays running progress (e.g. *"Running prompt with coach..."*), and the canvas card displays an animated generation indicator.
     - *Completion*: Persists response to database `activities.ai_responses`, updates local cache, renders text in canvas card, marks pulldown option as `(cached)`, changes button to **"Re-prompt"**, and flashes green **`Saved ✓`** tag.
5. **Telemetry Chart Interactivity**:
   - Full interactive Chart.js canvas with area fill for elevation, colored lines for Power (orange), Heart Rate (red), Cadence (green), and Speed (blue).
   - Individual toggle pills for each metric.
   - Dual-mode X-axis toggle: Distance (km) vs. Time (elapsed).
   - Synchronized mouse hover cursor updates the position marker on the Leaflet map in real time.
6. **Analytical Scope**:
   - Coggan 7-Zone Power Distribution (% and duration in Z1–Z7 based on athlete FTP).
   - Peak Power MMP Table (Best 5s, 30s, 1m, 5m, 20m, 60m watts and % FTP).
   - Detailed Stored Weather Card (Temperature range, conditions, wind speed & direction, headwind impact).
   - Heart Rate Zones Distribution (Z1–Z5 distribution).
   - Climb & Elevation Breakdown (Ascent, descent, flat distance & time, steepest grade).
7. **Navigation & Zero Strava API Calls**:
   - Clickable activity name in `activities.html` navigating to `/activity/<id>`, plus a dedicated Details action icon in the Actions column.
   - Breadcrumbs and quick action buttons ("← Back to Activities", "Create Poster", "View on Strava") on the detail page.
   - Strictly local database (`streams`, `activities`, `weather`, `profile`). Zero on-demand Strava API calls during web browsing.

---

## 3. Architecture & Technical Design

### 3.1 Backend Routes (`src/kinetiqo/web/app.py`)

#### `GET /activity/<activity_id>`
- **Authentication**: `@login_required`
- **Data loaded**:
  - Activity details via `repo.get_activity_detail(activity_id)`
  - Athlete profile via `repo.get_profile()` (FTP, weight, configured agents)
  - Configured AI agents extracted via `_strava_agents_config(profile)`
  - Stored weather summary via `repo.get_activity_weather(activity_id)`
  - Stream coverage via `repo.get_stream_coverage(int(activity_id))`
  - Tile providers via `_build_tile_providers()`
  - Google Fonts URL via `poster_google_fonts_url` context
- **Template rendered**: `activity_detail.html`

#### `GET /api/activity/<activity_id>/streams`
- **Authentication**: `@login_required`
- **Query parameters**: `max_points` (default: 1500)
- **Data returned**: Downsampled, timestamp-aligned telemetry streams from `streams` table:
  ```json
  {
    "has_streams": true,
    "points": [
      {
        "distance": 0.0,
        "time": 0,
        "altitude": 245.2,
        "heartrate": 132,
        "watts": 185,
        "cadence": 88,
        "speed": 28.4,
        "lat": 50.087,
        "lng": 14.421,
        "grade": 1.2
      }
    ],
    "bounds": [[min_lat, min_lng], [max_lat, max_lng]]
  }
  ```

#### `POST /api/activity/<activity_id>/ai-analyze`
- **Authentication**: `@login_required`, CSRF validated
- **Payload**:
  ```json
  {
    "agent_name": "coach-summary",
    "custom_directive": "Focus on my pacing in the final 10km climb"
  }
  ```
- **Behavior**:
  - Validates `agent_name` in athlete's configured `strava_agents_config`.
  - Determines active prompt: Combines base agent prompt with `custom_directive` if provided.
  - Instantiates `ChatService` and executes `run_agent_prompt(chat_service, athlete_id, activity, prompt)`.
  - Persists response into `activities.ai_responses` under key `agent-ai-<agent_name>` using `repo.update_activity_ai_responses(activity_id, ai_responses)`.
  - Returns JSON:
    ```json
    {
      "success": true,
      "agent_name": "coach-summary",
      "response": "...",
      "status": "generated"
    }
    ```
  - On failure, returns HTTP 422 or 500 with descriptive error JSON:
    ```json
    {
      "success": false,
      "error": "No API key configured for provider in Settings."
    }
    ```

#### `POST /api/activity/<activity_id>/upload`
- **Authentication**: `@login_required`, CSRF validated
- **Behavior**: Accepts custom uploaded background image (PNG, JPG, WEBP, HEIC), converts to PNG via Pillow/pillow-heif, and caches at `activity-detail-cache/{activity_id}.png`.

#### `POST /api/activity/<activity_id>/clear-image`
- **Authentication**: `@login_required`, CSRF validated
- **Behavior**: Removes custom cached image at `activity-detail-cache/{activity_id}.png`.

#### `POST /api/activity/<activity_id>/export`
- **Authentication**: `@login_required`, CSRF validated
- **Payload**:
  ```json
  {
    "format": "png",
    "width": 1440,
    "ratio": "auto",
    "bg": "#1e293b",
    "textColor": "#ffffff",
    "fontFamily": "Inter",
    "hasImage": false,
    "tint": "#000000",
    "opacity": 40,
    "visibleStats": { ... }
  }
  ```
- **Behavior**:
  - Uses Playwright to render the internal URL `/activity/<activity_id>?export=1` headlessly with athlete session cookies.
  - Slices a generous viewport (`width + 700`, `(height or 1400) + 400`) matching Poster export to eliminate CSS transform shrinkage on `#detail-wrapper`.
  - Sets `animation: false` on Chart.js telemetry datasets to eliminate rendering race conditions and frame delays.
  - Waits explicitly for `#telemetry-chart` and `window.telemetryChartReady === true` via `page.wait_for_function()` (up to 30s timeout matching Poster elevation chart).
  - Re-triggers Chart.js instances resize (`c.resize()`) and Leaflet map bounds (`ensureMapBounds()`) after dimension overrides before screenshotting.
  - Captures pixel-perfect PNG screenshot (`#activity-canvas`) or vector PDF (`page.pdf()`), featuring the Kinetiqo brand watermark logo (`#canvasWatermark`, `.activity-canvas-watermark`) positioned at the bottom right.
  - Returns binary image or PDF with `Content-Disposition: attachment; filename="kinetiqo-activity-<id>.<ext>"`.

---

### 3.2 Database Layer (`src/kinetiqo/db/`)

To support complete activity details across PostgreSQL, MySQL, and Firebird without ORM dependencies:

1. **Add `get_activity_detail(self, activity_id: int | str) -> Optional[Dict[str, Any]]` to `DatabaseRepository` (`src/kinetiqo/db/repository.py`)**:
   - Queries all columns from `activities`: `activity_id AS id`, `name`, `sport AS type`, `athlete_id`, `distance`, `moving_time`, `elapsed_time`, `total_elevation_gain`, `start_date`, `average_speed`, `max_speed`, `average_heartrate`, `max_heartrate`, `average_cadence`, `average_watts`, `max_watts`, `weighted_average_watts`, `device_watts`, `calories`, `kilojoules`, `achievement_count`, `pr_count`, `suffer_score`, `average_temp`, `elev_high`, `elev_low`, `gear_id`, `has_heartrate`, `workout_type`, `trophies`, `ai_responses`, and `weather_*`.
   - Automatically deserializes `trophies` and `ai_responses` from JSON strings to dictionaries.
   - Formats `start_date` to ISO 8601 string.
2. **Implement concrete methods in**:
   - `src/kinetiqo/db/postgresql.py` (using `%s` parameterization)
   - `src/kinetiqo/db/mysql.py` (using `%s` parameterization)
   - `src/kinetiqo/db/firebird.py` (using `?` parameterization and quoted identifiers)

---

### 3.3 Analytics Computations (`src/kinetiqo/analytics/`)

1. **Coggan 7-Zone Power Distribution**:
   - Computes Coggan power zones relative to athlete FTP:
     - Z1 Active Recovery (< 55% FTP)
     - Z2 Endurance (56–75% FTP)
     - Z3 Tempo (76–90% FTP)
     - Z4 Threshold (91–105% FTP)
     - Z5 VO2 Max (106–120% FTP)
     - Z6 Anaerobic Capacity (121–150% FTP)
     - Z7 Neuromuscular Power (> 150% FTP)
   - Computes seconds and % of moving time in each zone.
2. **Mean Maximal Power (MMP)**:
   - Computes peak moving rolling average from `watts` stream for 5s, 30s, 1m, 5m, 20m, 60m.
   - Calculates percentage of FTP.
3. **Heart Rate Zones**:
   - Computes 5 standard zones (Z1 50–60%, Z2 60–70%, Z3 70–80%, Z4 80–90%, Z5 90–100%) based on activity max HR (or athlete profile max HR).
4. **Climb & Elevation Breakdown**:
   - Segments stream data into climbing (grade > 1.5%), flat (-1.5% to 1.5%), and descending (grade < -1.5%).
   - Calculates distance, time, and steepest ascent grade.
5. **Weather & Wind Direction Impact**:
   - Compares wind direction (`weather_wind_deg`) against average activity heading to compute headwind/tailwind angles.

---

### 3.4 Frontend Layout & Sidebar Controls (`templates/activity_detail.html`)

The page consists of an infographic workspace with a sticky left-hand sidebar and a scalable canvas:

```
+-----------------------------------------------------------------------------------------+
| Top Navigation & Breadcrumbs: Activities / <Activity Name>                             |
+-------------------+---------------------------------------------------------------------+
| LEFT SIDEBAR      | MAIN CANVAS (#activity-canvas)                                     |
| (Sticky Controls) |                                                                     |
|                   | +-----------------------------------------------------------------+ |
| [PNG] [PDF]       | | Header: Title, Sport Badge, Date/Time, Gear, "View on Strava"   | |
|                   | +--------------------------------+--------------------------------+ |
| ▼ Size Box        | | Key Stats Grid (5 cols)        | Leaflet Route Map (7 cols)     | |
|   Width: S, M, L..| | Distance, Time, Elev, Avg/Max  | Route polyline, Start/Finish   | |
|   Ratio: Auto, 4:3| | Speed, Power, HR, Cadence,     | Synchronized scrubber marker   | |
|   Dimensions: ... | | Calories, Suffer Score         |                                | |
|                   | +--------------------------------+--------------------------------+ |
| ▼ Appearance Box  | | Telemetry Stream Profile (Chart.js)                             | |
|   Background Color| | [✓ Elev] [✓ HR] [✓ Power] [✓ Cadence] [✓ Speed]   [Dist | Time] | |
|   Text Color      | | Elevation area fill with overlaid metric curves                 | |
|   Font Selector   | +-----------------------------------------------------------------+ |
|   Tint & Opacity  | | AI Analysis Card (✨)                                            | |
|   Upload Photo    | | Selected Agent: [Coach Summary]                                 | |
|                   | | Cached or freshly generated insight formatted cleanly           | |
| ▼ AI Agent Box    | +-----------------------------------------------------------------+ |
|   Agent: [Coach ▼]| | Analytical Cards Grid (3 columns)                               | |
|   Directive: [...]| | • Coggan Power Zones (Z1-Z7)  • Peak Power MMP (5s to 60m)      | |
|   [Re-Prompt]     | | • HR Zones (Z1-Z5)            • Climb & Grade Breakdown         | |
|   Status: Saved ✓ | | • Stored Weather Details      • Headwind / Tailwind Compass     | |
|                   | +-----------------------------------------------------------------+ |
| ▼ Visible Stats   |                                                                     |
|   [✓] Key Stats   |                                                                     |
|   [✓] Map         |                                                                     |
|   [✓] Telemetry   |                                                                     |
|   [✓] AI Analysis |                                                                     |
|   [✓] Power Zones |                                                                     |
|   [✓] Peak MMP    |                                                                     |
|   [✓] HR Zones    |                                                                     |
|   [✓] Climb Stats |                                                                     |
|   [✓] Weather     |                                                                     |
+-------------------+---------------------------------------------------------------------+
```

#### Reusable Sidebar Partials Integrated:
- `_infographic_action_buttons.html` (PNG & PDF export buttons with `kinetiqo-loading-32x32.webp` waiting states)
- `_infographic_size_box.html` (Width S–XXL, Ratio Auto/4:3/16:9, Dimensions display)
- `_control_box_header.html` (Collapsible header with chevrons and persistent collapse state)
- `_font_select.html` (Typography font family selector)
- `_control_color_tint.html` (Tint overlay color picker)
- `_control_range.html` (Opacity range slider)
- `_image_upload_buttons.html` (Background photo upload and reset)

---

### 3.5 UI Standards Compliance

- **Modern ECMAScript**: Adheres to `javascript:S7773` using `Number.parseInt()`, `Number.parseFloat()`, `Number.isNaN()`.
- **Form Accessibility**: All select dropdowns, toggles, checkboxes, and buttons have associated labels or `aria-label` attributes (`Web:S6853`).
- **UI Loading Standard**: All waiting operations use `static/img/kinetiqo-loading-32x32.webp` without accompanying text in action buttons.
- **CSRF Protection**: All POST requests include `X-CSRFToken` header.
- **Self-Hosted Assets**: Uses existing self-hosted Tailwind, Leaflet, and Chart.js assets.
- **State Persistence**: Persists all control settings in `localStorage` under `activityDetail_*` schema keys.

---

## 4. Ambiguity Report

Using the `grill-me` rubric:

| Dimension | Score | Assessment |
|---|---|---|
| **Goals** | 0.0 | ✓ Clear. Detailed, desktop-grade Activity Detail page at `/activity/<id>` with left sidebar controls, AI agent selector & re-prompting, canvas styling, telemetry, map, analytics, and PNG/PDF export. |
| **Acceptance** | 0.0 | ✓ Clear. Verifiable criteria across sidebar controls, AI re-prompting & status feedback, routes, repository methods, telemetry toggles, map sync, export endpoints, and tests. |
| **Boundaries** | 0.0 | ✓ Clear. No on-demand Strava API calls (100% local database); no mutations to Strava; no breaking changes. |
| **Alternatives** | 0.0 | ✓ Clear. Evaluated and confirmed storing in `activities.ai_responses` JSON vs dedicated table; evaluated custom directive re-prompting vs strict profile prompts; evaluated Auto height vs fixed ratio. |
| **Assumptions** | 0.0 | ✓ Clear. Verified schemas for `streams`, `activities`, `weather`, `profile`, `agent_runner.py`, and Playwright infrastructure. |
| **Aggregate** | **0.0** | **✓ Pass (Threshold: 0.2 spec)** |

---

## 5. Implementation Step Plan

1. **Step 1: Database Repository Extension**
   - Add `get_activity_detail(activity_id)` to `DatabaseRepository` (`src/kinetiqo/db/repository.py`).
   - Implement `get_activity_detail()` in `postgresql.py`, `mysql.py`, and `firebird.py`.
   - Update repository tests to verify column mapping and JSON deserialization.
2. **Step 2: Backend Routes & APIs**
   - Implement `GET /activity/<activity_id>` in `src/kinetiqo/web/app.py`.
   - Implement `GET /api/activity/<activity_id>/streams` with downsampling and spatial bounding.
   - Implement `POST /api/activity/<activity_id>/ai-analyze` with CSRF validation, custom directive handling, `agent_runner.py` execution, and `activities.ai_responses` persistence.
   - Implement `POST /api/activity/<activity_id>/upload` and `POST /api/activity/<activity_id>/clear-image` for custom background photos.
   - Implement `POST /api/activity/<activity_id>/export` for Playwright PNG and vector PDF export.
3. **Step 3: Frontend View (`activity_detail.html`)**
   - Build layout with sticky left-hand controls sidebar and main canvas.
   - Include reusable control partials: Size box (S–XXL, Auto/4:3/16:9), Appearance box (bg color, text color, font selector, tint/opacity, photo upload), AI Agent & Re-Prompt box (agent selector, custom directive textarea, status/error feedback, re-prompt button), and Visible Stats checkboxes.
   - Integrate Chart.js multi-metric telemetry chart with pill toggles and distance/time switcher.
   - Implement bidirectional hover synchronization between Chart.js and Leaflet marker.
   - Build AI Analysis card on canvas showing the active agent's output.
   - Build analytical cards: Coggan Power Zones, Peak Power MMP, HR Zones, Climb breakdown, Stored Weather.
   - Wire up client-side export triggers calling `/api/activity/<activity_id>/export`.
4. **Step 4: Activities Grid Navigation Integration**
   - In `src/kinetiqo/web/templates/activities.html`, convert activity title to a link to `/activity/${row.id}`.
   - Add an Activity Detail icon link to the Actions column.
5. **Step 5: Testing & Verification**
   - Write mocked unit tests in `tests/test_activity_detail.py` verifying routes, stream downsampling, AI analysis trigger & re-prompting, photo upload, and export.
   - Run the complete test suite (`python -m pytest -o pythonpath=src`).
   - Validate accessibility, CSRF tokens, and code quality standards.
