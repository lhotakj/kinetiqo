# Interactive Leaflet Maps & Multi-Provider Basemaps

Kinetiqo includes an interactive mapping engine powered by **Leaflet.js** and **HTML5 Canvas**, supporting 16 basemaps across 7 providers, high-density GPS track visualization, distance-based geometry simplification, server-side tile proxying, and viewport PNG export.

---

## 1. Overview & Capabilities

- 🗺️ **16 Basemaps Across 7 Providers**: Switch seamlessly between topographic, cycling, hiking, street, dark matter, and satellite imagery.
- ⚡ **Hardware-Accelerated Canvas Renderer**: Renders tens of thousands of GPS track points smoothly without DOM element bloat or browser lag.
- 📉 **Intelligent GPS Simplification**: Configurable Ramer-Douglas-Peucker track simplification (`GPS_SIMPLIFICATION` levels 1–10) delivering 10–30× payload reduction while preserving sharp turns and track fidelity.
- 🛡️ **Built-in Server-Side OSM Tile Proxy**: Built-in `/tiles/osm/<z>/<x>/<y>.png` endpoint caches OpenStreetMap tiles locally, reducing external network round-trips and complying with OSM tile usage policies.
- 🎨 **Persistent Route & Canvas Styling**: Custom polyline color picker, stroke weight slider (1–10px), opacity slider (0–100%), and background tone overlay with full `localStorage` persistence.
- 🔒 **Tone Opacity Isolation Standard**: Tone opacity adjustments strictly affect the background map tint overlay and never dim the GPS polyline or control widgets.
- 🔄 **Multi-Activity Route Overlay**: Select multiple workouts from the Activity Grid and view them overlaid on the same canvas to compare laps, routes, or multi-day bikepacking stages.
- 📷 **High-Resolution PNG Export**: Export the active map viewport to high-resolution PNG with one click.

---

## 2. Supported Basemap Providers

| Provider | Layer Name | Key Required? | Free Tier / Notes |
|---|---|---|---|
| **OpenStreetMap** | Standard | No | Direct local tile proxy via `/tiles/osm/...` |
| **OpenStreetMap** | CyclOSM | No | Specialized cycling infrastructure & elevation contours |
| **OpenStreetMap** | Humanitarian (HOT) | No | High-contrast topography |
| **Mapy.cz** | Outdoor / Tourist | No | World-renowned European tourist and hiking trails with contour lines |
| **Mapy.cz** | Standard | No | Clean general road and terrain cartography |
| **Mapy.cz** | Winter | No | Cross-country ski trails and ski resort pistes |
| **CARTO** | Positron | No | Ultra-clean light minimalist map |
| **CARTO** | Dark Matter | No | High-contrast dark theme basemap |
| **Esri** | World Imagery | No | High-resolution global satellite photography |
| **MapTiler** | Outdoor | `MAPTILER_API_KEY` | Vector terrain with hillshading |
| **MapTiler** | Streets | `MAPTILER_API_KEY` | Clean street typography |
| **MapTiler** | Topo | `MAPTILER_API_KEY` | Comprehensive contour lines |
| **MapTiler** | Satellite | `MAPTILER_API_KEY` | Seamless aerial orthophotos |
| **Thunderforest** | OpenCycleMap | `THUNDERFOREST_API_KEY` | Global cycling network with hillshading |
| **Thunderforest** | Outdoors | `THUNDERFOREST_API_KEY` | Dedicated hiking and camping features |
| **Thunderforest** | Landscape | `THUNDERFOREST_API_KEY` | Forest and natural landcover emphasis |

---

## 3. GPS Track Simplification Architecture

GPS streams recorded at 1 Hz generate ~3,600 coordinates per hour of activity. For long rides (5–10 hours), transfer sizes can exceed several megabytes of JSON.

Kinetiqo implements server-side Ramer-Douglas-Peucker distance simplification controlled via `GPS_SIMPLIFICATION`:
- **Level 0 (Off)**: Raw sensor points (100% resolution).
- **Level 1–2 (Subtle)**: Discards collinear points within 0.5–1.0 meter deviation (~3× compression).
- **Level 3 (Default)**: Optimal balance for road and trail navigation, achieving **10–15× payload reduction** with zero perceptible geometric distortion.
- **Level 4–10 (Aggressive)**: Suitable for continental or multi-week overview maps (~20–40× compression).

---

## 4. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/map` | GET | Render the full-screen interactive Leaflet map interface |
| `/api/map/data` | POST | Receive activity ID array, return simplified coordinate streams and elevations |
| `/tiles/osm/<z>/<x>/<y>.png` | GET | Local proxy and server cache for OpenStreetMap tiles |

---

## 5. Visual Artifacts

- Interactive Canvas Maps: `docs/map-dark.webp`
- Route Polyline Styling & Multi-Stage Maps: `docs/map2.webp`

