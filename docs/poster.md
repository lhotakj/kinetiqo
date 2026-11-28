# WYSIWYG Activity Poster Generator

The **Activity Poster Generator** is a live WYSIWYG canvas builder for individual workouts, featuring custom aspect ratios, typography selection, background photo editing, interactive Leaflet map backgrounds, elevation profiles, and Playwright-powered high-resolution PNG export.

---

## 1. Overview & Capabilities

- 🎨 **Live WYSIWYG Editor**: Interactive real-time preview reflecting exact typography, colors, layout positions, and element visibility before exporting.
- 📐 **Multiple Aspect Ratios**:
  - **4:3 Portrait / Landscape**: Classic print format.
  - **16:9 Widescreen**: High-definition display format.
  - **1:1 Square**: Social feed and avatar format.
- 🖼️ **Dual Background Modes**:
  1. **Photo Mode**:
     - Reload original workout photos cached from Strava.
     - Upload personal photos in PNG, JPG, WEBP, or Apple HEIC/HEIF formats.
     - **Built-in Photo Editor**: Fine-tune Color (Vibrance, Saturation, Temperature, Tint, Hue), Light (Exposure, Contrast, Highlights, Shadows, Whites, Blacks), and Details (Sharpness, Vignette).
     - Clear photo button to instantly return to solid or tinted background canvas.
  2. **Interactive Leaflet Map Mode**:
     - Choose from 16 basemaps across 7 tile providers.
     - Interactive pan and zoom with persistent coordinates.
     - Route polyline customization (color picker, stroke weight 1–10px, opacity 0–100%).
- 🔒 **Tone Opacity Isolation Standard**: The Tone Opacity slider exclusively adjusts the background tint overlay; it never dims the route polyline, elevation profile, or text widgets.
- 📈 **Elevation Profile Chart**: Smooth SVG elevation profile with translucent gradient fill matching the chosen accent color.
- 🔤 **Typography & Font Selector**: Choose between curated typefaces (Italiana, Inter, Outfit, JetBrains Mono, Fanwood Text) with live Google Fonts rendering.
- 🎛️ **Draggable Layout & Element Toggles**: Toggle and reposition Activity Name, Date, Distance, Elevation Gain, Moving Time, Average Speed, Average Power, Heart Rate, and Elevation Chart.
- 🖨️ **High-Resolution PNG Export**: Server-side Playwright rendering exporting at exact pixel dimensions (800px to 2048px width) without browser scaling artifacts.

---

## 2. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/poster/<activity_id>` | GET | Render the live WYSIWYG poster builder for an activity |
| `/api/poster/photo/<activity_id>` | GET | Retrieve the cached poster background photo |
| `/api/poster/photo/<activity_id>` | POST | Fetch and cache the activity primary photo from Strava API |
| `/api/poster/upload/<activity_id>` | POST | Upload a custom background image (PNG, JPG, WEBP, HEIC) |
| `/api/poster/elevation/<activity_id>` | GET | Fetch smoothed elevation stream points for the profile chart |
| `/api/poster/export/<activity_id>` | POST | Trigger server-side Playwright rendering to export a high-resolution PNG |

---

## 3. UI State Persistence (`localStorage`)

Customizations are preserved per-activity and globally:
- `poster_ratio`: Active aspect ratio (4:3, 16:9, 1:1).
- `poster_size`: Export width in pixels (800, 1200, 1600, 2048).
- `poster_font`: Selected typography font family.
- `poster_mode`: Background mode (`photo` vs. `map`).
- `poster_map_settings`: Center coordinates, zoom level, tile provider, and line styling.
- `poster_photo_filters`: Photo adjustments for Color, Light, and Details.
- `poster_visible_elements`: Checkbox states for individual stats widgets.

---

## 4. MCP & AI Integration

The Model Context Protocol server exposes:
- `kinetiqo_generate_activity_poster`: Allows AI assistants to generate and return a customized high-resolution PNG activity poster directly from a conversational prompt.

---

## 5. Visual Artifacts

- Poster Generator Showcase: `docs/poster-example.webp`
- Poster Leaflet Map Mode: `docs/poster-map.webp`

