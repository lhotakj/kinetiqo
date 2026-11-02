# Activity Detail Infographic

**Activity Detail Infographic** provides a comprehensive, publication-grade analytical showcase for individual workouts, combining responsive 2-column hero metrics with an interactive Leaflet route map, full multi-stream telemetry profiles, integrated AI Coach feedback, and pixel-perfect PNG/PDF exports.

---

## 1. Overview & Capabilities

- 📊 **2-Column Hero Overview Split**: Balanced 50/50 side-by-side design pairing a customizable Key Metrics card grid (1 to 6 columns) on the left with an interactive Leaflet route map on the right.
- 📈 **Interactive Multi-Stream Telemetry Chart**: Downsampled 1 Hz sensor stream canvas (Elevation fill with Power, Heart Rate, Cadence, and Speed overlays), clickable metric lozenge toggles, and an instant **Distance vs. Time** X-axis mode toggle.
- 🤖 **On-Demand AI Coach Analysis**: Interactive sidebar agent prompt workflow with cached indicator status, dynamic **Run prompt** / **Re-prompt** execution, and real-time generation indicators persisted to the database (`activities.ai_responses`).
- 🧩 **5-Column Analytical Card Grid**: Modular metric breakdown widgets spanning Power Zones (Coggan), Peak Power MMP curve, Heart Rate Zones, Major Climbs analysis, and Stored Historical Weather.
- 🎨 **WYSIWYG Appearance & Sizing Controls**: Responsive preview scaler with dimension presets (**M 1280px**, **L 1440px**, **XL 1600px**, **XXL 1920px**), aspect ratio locks (**Auto Fit**, **16:9**, **4:3**), generic Font Scale slider (-30% to +80%), background color picker, tint overlays, and custom background photo upload with instant reset.
- 🖨️ **High-Resolution Playwright Export**: Server-side headless Chromium rendering producing pixel-perfect standalone PNGs and vector PDFs with the official Kinetiqo brand watermark logo (`kinetiqo-logo.svg`).

---

## 2. Technical Details & Architecture

- **Server-Side Analytics**: Computed on demand from raw stream windows via `kinetiqo.analytics.activity_summary.build_activity_analytics()` against athlete FTP and maximum heart rate.
- **Intelligent Downsampling**: Streams are downsampled using dynamic Largest-Triangle-Three-Buckets (LTTB) algorithms to ensure responsive client-side rendering without sacrificing peak surge fidelity.
- **Tone Opacity Isolation**: Per Kinetiqo styling standards, the Map Tone Opacity slider isolates background tint fills without muting GPS track polyline coordinates or telemetry overlays.
- **Deep Technical Specification**: For complete architectural specifications and interrogation notes, see [docs/concepts/activity-detail.md](concepts/activity-detail.md).

---

## 3. Web UI & Interactive Controls

### 3.1 Control Sidebar Panels
All sidebar panels are collapsible via chevron toggles, open by default, and persisted to `localStorage`:
- **Action Buttons**: Instant **Download PNG** and **Download PDF** buttons using animated WebP waiting spinners (`kinetiqo-loading-32x32.webp`).
- **Infographic Size**: Sizing presets (M, L, XL, XXL) and aspect ratio constraints (Auto, 16:9, 4:3).
- **Appearance**: Background color picker, text/accent color picker, typography font selector (Google Fonts), Font Scale slider (`#detail-font-scale`), Tint Color (`_control_color_tint.html`), Opacity slider, and custom photo upload/reset.
- **Key Metrics**: Dynamic column count selector (1–6 cols) and 15 individual metric toggle checkboxes (`actDetail_km_*`).
- **Route Map**: Basemap provider selector (16 options across 7 providers), Map Opacity, Map Color Tone, Tone Opacity, Route Polyline Color, Stroke Weight, and Route Opacity.
- **Telemetry Streams**: Segmented X-Axis Mode toggle (Distance vs. Time) and channel checkboxes (Elevation, Heart Rate, Power, Cadence, Speed).
- **AI Agent & Prompt**: Agent selector dropdown displaying cached status (`(cached)`), action button (**Run prompt** / **Re-prompt**), and real-time generation indicator.
- **Visible Stats / Options**: Individual section toggles for Hero Overview, Key Metrics, Map, Telemetry Chart, AI Analysis, and Analytical Breakdown Cards.

### 3.2 State Persistence Keys (`localStorage`)
| Key | Default | Description |
|---|---|---|
| `activityDetailBoxCollapsed` | `{}` | JSON dictionary tracking sidebar panel collapse states |
| `actDetail_km_cols` | `4` | Number of columns in Key Metrics grid |
| `actDetail_km_<metric>` | `true` | Individual visibility toggle for each of the 15 key metrics |
| `actDetail_chart_x_mode` | `"distance"` | Telemetry chart X-axis mode (`distance` or `time`) |
| `actDetail_stream_<channel>` | `true` | Channel visibility toggles (elev, hr, watts, cadence, speed) |
| `actDetail_font_scale` | `0` | Canvas typography scale modifier (-30% to +80%) |

---

## 4. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/activity/<activity_id>` | GET | Main Activity Detail Infographic web page and preview canvas |
| `/api/activity/<activity_id>/streams` | GET | Downsampled 1 Hz telemetry stream points and GPS bounding box |
| `/api/activity/<activity_id>/ai-analyze` | POST | Triggers AI agent evaluation and persists response to database |
| `/api/activity/photo/<activity_id>` | GET | Retrieves cached custom background photo |
| `/api/activity/upload/<activity_id>` | POST | Uploads custom background image (PNG, JPG, WEBP, HEIC/HEIF) |
| `/api/activity/clear-image/<activity_id>` | POST | Deletes custom background image and restores default tint |
| `/api/activity/export/<activity_id>` | POST | Server-side Playwright rendering returning PNG or vector PDF |

---

## 5. Configuration & Environment Variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `ATHLETE_FTP` | float | `250.0` | Athlete Functional Threshold Power (Watts) used for Coggan power zone distribution |
| `ATHLETE_WEIGHT_KG` | float | `75.0` | Athlete body weight in kg used for relative power metrics (W/kg) |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` | string | `""` | Optional explicit path to Chromium executable for headless exports |
| `GEMINI_API_KEY` | string | `""` | Google AI Studio API key for Gemini-powered coach analysis |
| `OPENROUTER_API_KEY` | string | `""` | OpenRouter API key for Claude, OpenAI, and Llama coach analysis |

---

## 6. MCP & AI Integration

The Model Context Protocol (MCP) server exposes tools to query activity details and telemetry:
- `kinetiqo_get_activity_details`: Returns complete metadata, distance, time, elevation, and sensor coverage.
- `kinetiqo_get_stream_window`: Queries high-resolution sensor streams for granular AI analysis.
- `kinetiqo_export_activity_detail`: Headless export endpoint callable by AI assistants to generate PNG visual artifacts.

---

## 7. Deep Architecture & Concept

For extensive mathematical formulas, component hierarchies, and requirement analysis:
- [docs/concepts/activity-detail.md](concepts/activity-detail.md)

