# Historical Activity Weather Enrichment

**Historical Activity Weather** automatically enriches outdoor GPS workouts with true hourly weather conditions, ambient and apparent temperatures, wind vectors, gusts, and route-relative headwind analysis using the Visual Crossing Timeline API.

---

## 1. Overview & Capabilities

- 🌦️ **True Historical Conditions**: Enriches eligible outdoor GPS activities with historical hourly observations matching the exact time and GPS route of the activity.
- 🌡️ **Monochromatic Skin-Adaptive Telemetry**: Clean temperature range display (`min-max°C` or steady `avg°C`) paired with a monochromatic outline thermometer icon that automatically adapts to the active UI skin and dark mode.
- 💨 **Route-Relative Wind & Headwind Vectors**: Calculates dynamic bearing between GPS track points and wind direction, determining actual headwind and crosswind impact.
- 🌪️ **Wind Gust Tracking**: Automatically alerts on significant peak wind gusts (`>= 10 m/s` or `>= spd + 3 m/s`) with regular inline styling and detailed km/h conversion tooltips.
- 🌧️ **Precipitation Detection**: Identifies rain or snow with total accumulated amounts (e.g. `Rain (1.8mm)`).
- 🔒 **Privacy-First Zero Coordinate Persistence**: GPS track coordinates are sent transiently to the weather API in UTC; coordinates are never saved in weather JSON documents, audit logs, or AI/MCP responses.
- 🛡️ **In-Memory Rate Limit Protection (Multi-Worker Safe)**: Respects provider rate limits (`X-RateLimit-Remaining: 0` or HTTP 429) using POSIX shared memory across all Gunicorn workers. Ceases queries until UTC midnight without slamming the API gateway.
- 📝 **Strava Description Integration**: Dynamically injects weather summaries and 15+ weather placeholders (`{{weather-summary}}`, `{{weather-temp-avg}}`, `{{weather-headwind-pct}}`) into Strava activity descriptions.

---

## 2. Weather Column in Activities Grid

The `/activities` grid features a dedicated, toggleable **Weather** column:

```text
[thermometer-icon] <min-max>°C [condition-icon] [wind-direction-arrow] <speed> m/s (gust <speed> m/s) <precipitation>
```

- **Temperature**: Monochromatic outline thermometer icon rendered in `currentColor` (matching the selected theme/skin) followed by compact temperature range without spaces (e.g. `14-20°C` or `18°C` when steady). Sorts numerically by `weather_temp_avg`.
- **Weather Condition Icon**: Duration-weighted condition icon (Clear, Partially cloudy, Overcast) with severe condition promotion (Thunderstorm, Rain, Snow).
- **Wind Vector**: Dynamic arrow rotated to the wind travel direction with cardinal tooltip (e.g. `West wind (270°) · 3.4 m/s`).
- **Wind Gust**: Regular inline text (no lozenges/pills) displaying `(gust 12.3 m/s)` with peak km/h conversion tooltip.
- **Precipitation**: Regular blue inline text displaying rain/snow accumulations (e.g. `Rain (1.8mm)`).
- **Default Visibility**: Hidden by default, toggleable via the **Column Visibility** picker.

---

## 3. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/activities` | GET | Interactive activities grid featuring the toggleable Weather column |
| `/api/activities` | GET | JSON activities list including the structured `weather` payload |
| `/fastsync` | POST | Incremental sync pass honoring the `enable_weather_data` profile preference |
| `/fullsync` | POST | Full sync audit pass with opt-in weather resync |

---

## 4. Configuration & Environment Variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `VISUAL_CROSSING_API_KEY` | string | `""` | Optional Visual Crossing Timeline API key. When omitted, weather enrichment is gracefully disabled. |

The API key is strictly maintained on the server; it is never transmitted to the browser, stored in activity tables, or logged.

### How to Get Your Free API Key:
1. **Sign Up**: Register for a free account at [visualcrossing.com/weather-api](https://www.visualcrossing.com/weather-api). No credit card is required to get started.
2. **Free Allowance**: The free plan provides **1,000 free weather records per day**, which resets automatically every day at **00:00 UTC**.
3. **Pay-As-You-Go**: If you exceed the free allowance, additional records are metered at **$0.0001 per record** ($1 per 10,000 records). See [Visual Crossing Editions & Pricing](https://www.visualcrossing.com/weather-data-editions) for details.
4. **Efficiency & Spatial Caching**:
   - Visual Crossing counts 1 record per requested hour along the workout route.
   - Kinetiqo includes a **15 km spatial proximity cache** and saves all hourly observations in the local database. Multiple activities in the same area on the same day share weather data with zero extra API queries, making 1,000 records/day sufficient for hundreds of hours of outdoor activities.
   - Re-syncing or restoring activities re-computes summaries directly from local records with **0 Visual Crossing queries**.

---

## 5. Rate Limit Architecture

Visual Crossing reports remaining daily quota in the `X-RateLimit-Remaining` HTTP response header, which resets at 00:00 UTC.

1. **Authoritative Limit Signal**: A response header `X-RateLimit-Remaining: 0` or HTTP 429 immediately stops further weather queries.
2. **Multi-Worker Shared Memory**: State is shared across all Gunicorn web and background workers via `/dev/shm` (POSIX shared memory) with filesystem fallback.
3. **Graceful Sync Completion**: Activity synchronization continues uninterrupted. Only weather enrichment is skipped for subsequent activities until the daily quota resets at UTC midnight.

---

## 6. MCP & AI Integration

The Model Context Protocol (MCP) server exposes weather data to AI assistants:
- `kinetiqo_get_activity_weather`: Retrieves hourly conditions, apparent temperature, precipitation, wind speed, gusts, and route headwind for any activity.
- AI Search: Assistants can search workouts with criteria like `weather_condition='rain'`, `max_temp_c=0` (freezing rides), or `min_temp_c=30` (hot summer runs).

---

## 7. Deep Architecture & Concept

For full mathematical formulas, headwind bearing calculations, database schemas, and weighted average computations, refer to:
- [docs/concepts/weather-concept.md](concepts/weather-concept.md)

---

## 8. Attribution & Service Terms

Weather data is provided by [Visual Crossing](https://www.visualcrossing.com/) via the Timeline Weather API:
- **Service Website**: [visualcrossing.com](https://www.visualcrossing.com/)
- **Get Free API Key**: [visualcrossing.com/weather-api](https://www.visualcrossing.com/weather-api) (1,000 free records/day)
- **Editions & Pricing**: [visualcrossing.com/weather-data-editions](https://www.visualcrossing.com/weather-data-editions)
- **Terms of Service**: [visualcrossing.com/terms](https://www.visualcrossing.com/terms/)
