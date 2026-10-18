# Fondo-o-meter Infographic

**Fondo-o-meter** is a dedicated infographic feature in Kinetiqo designed to celebrate epic endurance efforts, distance milestones, King of the Mountains (KOMs), and Personal Records (PRs).

---

## 1. Overview & Capabilities

- **Concentric Radial Gauge Chart**: Renders up to 8 harmonic concentric rings showcasing distance breakdown and endurance milestones for qualifying activities.
  - **Outer Ring**: Dedicated to the single longest activity of the season with full 180° sweep, brightest lime hue, and bold distance label (e.g. **213.2 km**).
  - **Inner Rings**: Dynamically binned distance tiers (smart binning) from sport threshold up to the maximum recorded distance with proportional arc lengths and harmonic inverse gradient.
- **Badges & Hero Section Badges**: Features high-resolution 306px badge trophies (`fondo-o-meter-*.png`) top-aligned across all metric columns:
  - **Gran Fondo Badge** (`fondo-o-meter-gf.png`): Paired with a hero-sized total Fondos completed counter styled with an adaptive color gradient matching the concentric arcs.
  - **Crown Badge (KOM / QOM)** (`fondo-o-meter-kom.png` / `fondo-o-meter-qom.png`): User-selectable King vs. Queen of the Mountains switcher dynamically updating badges and headings.
  - **Personal Records Trophy** (`fondo-o-meter-pr.png`): Highlighting segment PR achievements.
  - **Thropies** (`fondo-o-meter-thropies.png`): Celebrates all top-10 segment achievements with rank breakdown: 1st place gold medal, 2nd place silver medal, 3rd place bronze medal, and 4th–10th place metallic gray medals with exact placement counts.
- **Sport-Specific Baseline Thresholds**:
  - **Cycling / Outdoor / Indoor**: ≥ 100 km (Century / Gran Fondo)
  - **Running & Walking**: ≥ 42.195 km (Marathon)
  - **Skiing**: ≥ 50 km
  - **Swimming**: ≥ 10 km
- **King of the Mountains (KOMs)**: Verified count of segment titles conquered across cycling activities, synchronized directly from Strava's athlete KOMs endpoint during sync and backed by local cache (`verified_koms.json`) with zero on-demand API calls.
- **Personal Records (PRs)**: Aggregated segment PRs achieved across the year.
- **Thropies (Top 10 Placements)**: Comprehensive 1st through 10th place segment effort achievements aggregated across activities, stored in the database `activities.trophies` column and backed by `verified_trophies.json` with zero on-demand API calls.
- **Customizable Appearance & Backgrounds**:
  - Color picker for background canvas.
  - Custom photo upload supporting PNG, JPG, WEBP, and HEIC (with Reset button).
  - Configurable tint color overlay and opacity slider (0–100%).
  - Arc color picker with instant reset to harmonic lime green (`#94C03B`), dynamically recoloring both gauge arcs and hero number gradient.
  - Arc width slider (80%–160%), arc text size scaling (70%–140%), rounded arc stroke endcaps, and section blur slider (0%–100%, default 100% / 8px).
  - Vignette slider (-50% to +50%, default 0%) applying dark or light edge falloff to background canvas and custom photos with state persistence in `localStorage` (`fondoOMeterVignette`).
  - Typography font family selector (with live Google Fonts loading across all text and SVG elements) and title/body font size sliders.
  - Toggleable metric blocks (Fondo Analysis, KOMs, PRs, Thropies) with auto-expanding layout.
- **Pixel-Perfect Vector PDF & PNG Export**: Server-side Playwright rendering with exact dimensions (1280px to 2048px, 4:3 aspect ratio), honoring background images, tint overlays, custom fonts, and visible metric selections.

---

## 2. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/fondo-o-meter` | GET | Render the interactive Fondo-o-meter infographic view |
| `/api/fondo_o_meter_data` | GET | Fetch JSON payload of computed rings, verified KOMs, PRs, and longest activity |
| `/api/fondo_o_meter/upload` | POST | Upload a custom background photo for Fondo-o-meter |
| `/api/fondo_o_meter/image` | GET | Serve the cached custom background photo |
| `/api/fondo_o_meter/image/reset` | POST/DELETE | Reset custom background photo |
| `/api/fondo_o_meter/export` | POST | Generate pixel-perfect PNG or PDF export via Playwright |

---

## 3. Computation & Binning Algorithm

1. **Activity Filtering**: Filters activities strictly by the requested year and sport type group (e.g. `cycling`, `running`, `walking`, `swimming`, `skiing`).
2. **Threshold Qualification**: Selects all activities where $\text{distance} \ge \text{sport threshold}$.
3. **Smart Binning**:
   - Spanning range: $\text{span} = \text{max\_km} - \text{threshold\_km}$.
   - Step size $\text{step} \in \{5, 10, 20, 25, 50, 100, 200, 250, 500\}$ chosen so that $\text{span} / \text{step} \le 7$.
   - Up to 7 active bins distributed + 1 outer ring for the absolute longest activity (max 8 rings total).
4. **Inverse Gradient**:
   - Innermost ring (lowest distance tier) receives deep harmonic olive tone.
   - Outermost ring (longest distance) receives brightest lime (`#F7FBE2`).
