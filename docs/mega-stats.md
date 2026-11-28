# MEGA Stats Infographic

The **MEGA Stats Infographic** is a comprehensive, Veloviewer-style performance showcase that aggregates season, quarter, half-year, or custom-period statistics alongside a 365-day activity calendar heatmap, customizable background photos, and vector PDF / high-resolution PNG export.

---

## 1. Overview & Capabilities

- 📅 **365-Day Activity Calendar Heatmap**: Displays daily training consistency, rest days, and workout volume across the entire year.
- 📐 **Responsive Column Width & Full-Width Expanded Layout**:
  - **Stacked Layout (20% Default)**: Compact vertical presentation where metric labels sit directly above values.
  - **Expanded Layout (>20% to 50%)**: Metric rows dynamically switch to flexbox spacing (`display: flex; justify-content: space-between`), flush-aligning labels to the left and values to the right.
- 📏 **Metric Divider Standard & Dynamic 1px Hairlines**:
  - Subtle 1px dividers (`rgba(255, 255, 255, 0.08)`) cleanly separate each visible metric.
  - Dynamic auto-cleanup ensures the last visible metric never exhibits a dangling trailing divider line.
- 🎨 **Appearance Controls & Photo Upload**:
  - Custom background photo upload supporting PNG, JPG, WEBP, and HEIC with one-click **Reset**.
  - Configurable tint color overlay with opacity slider (0–100%).
  - Typography font family selector (Inter, Italiana, Outfit, JetBrains Mono, Fanwood Text) with live Google Fonts loading.
- 🎛️ **Unified Collapsible Control Panels**:
  - Unified **Stats Options** panel combining Title Size, Column Width, and Visible Metric toggles.
  - Collapsible **Appearance**, **Size**, and **Period** boxes with persistent states in `localStorage`.
- 📊 **Rich Metric Catalog**:
  - Total Workouts, Distance, Cumulative Elevation, Moving Time, and Elapsed Time.
  - Suffer Score / Relative Effort, Calories, Kilojoules, and Average/Max Speed.
  - **Most Active Month by Distance** and **Most Active Month by Elevation**.
- 🖨️ **Pixel-Perfect Vector PDF & PNG Export**: Server-side Playwright rendering generating publication-ready vector PDFs and high-resolution PNGs at exact dimensions.

---

## 2. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/stats` | GET | Render the interactive MEGA Stats infographic builder |
| `/api/stats_data` | GET | Fetch aggregated summary metrics and 365-day calendar heatmap data |
| `/api/stats/upload` | POST | Upload a custom background image (PNG, JPG, WEBP, HEIC) |
| `/api/stats/image` | GET | Serve the cached custom background photo |
| `/api/stats/image/reset` | POST / DELETE | Reset the custom background image to default canvas |
| `/api/stats/export` | POST | Generate a high-resolution PNG or vector PDF export via Playwright |

---

## 3. UI State Persistence (`localStorage`)

All visual customizations are automatically preserved across browser sessions:
- `statsYear`, `statsPeriod`, `statsActivityGroup`
- `statsBgColor`, `statsTint`, `statsOpacity`
- `statsFontFamily`, `statsTitleFontSize`, `statsColumnWidth`
- `statsVisibleStats` (array of active metric keys)
- Control box collapse states (`statsBoxCollapsed_*`)

---

## 4. MCP & AI Integration

The Model Context Protocol server exposes:
- `kinetiqo_get_activity_totals`: Fetches aggregated yearly and period totals, active days, distance, elevation, and suffer score.
- `kinetiqo_generate_mega_stats_infographic`: Triggers automated Playwright rendering of the MEGA Stats infographic directly from an AI prompt.

---

## 5. Visual Artifacts

- MEGA Stats Infographic: `docs/mega-stats.webp`

