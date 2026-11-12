# Activity Weather Enrichment & Grid Column Concept

## 1. Overview & Goals

Kinetiqo enriches eligible outdoor activities with historical hourly weather data from the **Visual Crossing Timeline Weather API**.
This document defines both the historical data ingestion architecture and the **Weather Grid Column** in `/activities`.

The Weather column presents a concise, visually rich, and instantly sortable representation of outdoor conditions for each activity in the format:
```text
<temperature-icon> <min - max>°C <weather-condition-icon> <wind-direction-arrow> <wind-speed>m/s <precipitation-word-with-amount>
```
Example:
* **Dry activity**: `🌡️ 14 - 18°C ⛅ ↗ 3.4 m/s` (or `🌡️ 18°C ☀️ ↗ 2.1 m/s` if temperature was steady)
* **Wet activity**: `🌡️ 11 - 15°C 🌧️ ↘ 4.5 m/s Rain (1.8mm)`
* **Indoor / Non-GPS activity**: `-` (muted dash, sorts to the bottom)

---

## 2. Architectural Analysis & Database Decision

### Evaluated Approaches:
1. **Option 1 — Precomputed HTML String in DB**: Storing raw HTML (`<svg...>...`) in a text column breaks DataTables sorting/filtering, locks markup in the database, hardcodes units (°C vs °F), and bloats storage.
2. **Option 2 — Normalized Relational Multi-Row Table (`weather_samples`)**: Storing 1 row per hour per activity requires multi-table joins and computing trigonometric circular vector averages across 10,000+ rows on every grid load, destroying client-side responsiveness.
3. **Option 3 (Selected) — Hybrid Architecture**:
   * The **`weather` table** retains the complete hourly JSON (`weather_json`) as the single source of truth for Strava description updates, headwind profile graphs, and MCP tools.
   * The **`activities` table** stores precomputed, lightweight summary metrics in 8 discrete scalar columns.

### Benefits of the Selected Architecture:
* **$O(1)$ Grid Performance**: The `/api/activities` endpoint executes a single-table `SELECT` from `activities` with zero joins and zero JSON deserialization.
* **Native DataTables Sorting & Filtering**: The column sorts numerically by average temperature (`weather_temp_avg`) and filters cleanly on condition or precipitation text.
* **Firebird 64KB Row Limit Safe**: The scalar columns add under 120 bytes per row.
* **Zero Visual Crossing API Cost**: Re-syncing or restoring activities re-derives summaries from existing local JSON with zero external API calls.

---

## 3. Database Schema Changes

In `SCHEMA_DEFINITION["activities"]["columns"]` across PostgreSQL, MySQL, and Firebird:

```python
{"name": "weather_temp_min", "type_mysql": _DOUBLE_PRECISION, "type_pg": _DOUBLE_PRECISION, "type_firebird": _DOUBLE_PRECISION},
{"name": "weather_temp_max", "type_mysql": _DOUBLE_PRECISION, "type_pg": _DOUBLE_PRECISION, "type_firebird": _DOUBLE_PRECISION},
{"name": "weather_temp_avg", "type_mysql": _DOUBLE_PRECISION, "type_pg": _DOUBLE_PRECISION, "type_firebird": _DOUBLE_PRECISION},
{"name": "weather_condition", "type_mysql": "VARCHAR(64)", "type_pg": "TEXT", "type_firebird": "VARCHAR(64)"},
{"name": "weather_condition_icon", "type_mysql": "VARCHAR(32)", "type_pg": "TEXT", "type_firebird": "VARCHAR(32)"},
{"name": "weather_wind_deg", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
{"name": "weather_wind_speed", "type_mysql": _DOUBLE_PRECISION, "type_pg": _DOUBLE_PRECISION, "type_firebird": _DOUBLE_PRECISION},
{"name": "weather_precipitation", "type_mysql": "VARCHAR(64)", "type_pg": "TEXT", "type_firebird": "VARCHAR(64)"},
```

---

## 4. Visual Crossing API Data & Extraction Algorithms

### Visual Crossing Elements Requested:
`elements: datetimeEpoch,temp,feelslike,precip,snow,preciptype,conditions,icon,winddir,windspeed,windgust,source`

### 1. Temperature Calculation
* Filter samples with valid `temperature_c`.
* $T_{\min} = \min(T)$, $T_{\max} = \max(T)$.
* $T_{\text{avg}} = \frac{\sum T_i \cdot \Delta t_i}{\sum \Delta t_i}$ (duration-weighted arithmetic mean).
* Display: if $\operatorname{round}(T_{\min}) == \operatorname{round}(T_{\max})$, render e.g. `18°C`; otherwise render e.g. `14 - 18°C`.

### 2. Sky Condition & Icon Determination
Visual Crossing conditions (`Clear`, `Partially cloudy`, `Overcast`, `Rain, Overcast`, etc.) and icons (`clear-day`, `partly-cloudy-day`, `cloudy`, `rain`, `snow`, `wind`, `fog`).

* **Cloudiness Scoring**:
  * Clear / Sunny = 0.0
  * Partially cloudy = 1.0
  * Overcast = 2.0
* Duration-weighted mean score:
  $$\bar{C} = \frac{\sum C_i \cdot \Delta t_i}{\sum \Delta t_i}$$
  * $\bar{C} < 0.4 \implies$ `"Clear"`, icon `"clear-day"`
  * $0.4 \le \bar{C} \le 1.6 \implies$ `"Partially cloudy"`, icon `"partly-cloudy-day"`
  * $\bar{C} > 1.6 \implies$ `"Overcast"`, icon `"cloudy"`
* **Severe / Wet Override**:
  * If `"thunder"` in conditions: `"Thunderstorm"`, icon `"thunder-rain"`.
  * If `"snow"` in conditions or `snowfall_cm > 0`: `"Snow"`, icon `"snow"`.
  * If `"rain"` in conditions or `precipitation_mm > 0`: icon `"rain"`.

### 3. Wind Direction & Speed (Circular Vector Mean)
Wind direction is circular; arithmetic mean produces incorrect results for angles crossing 0°/360°.
$$\bar{X} = \sum (\text{speed}_i \cdot \Delta t_i \cdot \cos(\theta_i)), \quad \bar{Y} = \sum (\text{speed}_i \cdot \Delta t_i \cdot \sin(\theta_i))$$
$$\bar{\theta} = \operatorname{atan2}(\bar{Y}, \bar{X}) \pmod{360^\circ}$$
$$\bar{S} = \frac{\sum \text{speed}_i \cdot \Delta t_i}{\sum \Delta t_i}$$

* **Display**: Directional arrow rotated by $\bar{\theta}$ pointing in the direction the wind blows.
* **Tooltip**: e.g., `West wind (270°) · 3.4 m/s`.

### 4. Precipitation Word & Amount
* Total precipitation $P_{\text{rain}} = \sum \text{precip}_i$, $P_{\text{snow}} = \sum \text{snow}_i$.
* If $P_{\text{snow}} > 0$ or `"snow"` in `precipitation_types`: `Snow (X.Xcm)`.
* Else if $P_{\text{rain}} \ge 0.1\text{mm}$ or `"rain"` in `precipitation_types`: `Rain (X.Xmm)`.
* Else: `None` (omitted when dry).

---

## 5. UI & DataTables Integration

* **Table Header**: Added as `<th class="py-3 px-4 w-52">Weather</th>` in `activities.html`.
* **Visibility**: Hidden by default (`visible: false`), selectable via the Column Visibility picker.
* **Sorting**: Orthogonal sorting on `temp_avg` (ascending/descending). Nulls sort to the bottom.
* **SVGs**: Self-hosted SVG icons for thermometer, weather states, and wind vector arrow, styled with Tailwind light & dark themes.

---

## 6. Migration & Backfill Strategy

1. **Automatic Startup Backfill**: On startup, `backfill_unsummarized_weather()` identifies activities with rows in `weather` where `weather_temp_avg IS NULL`, computes the summary, and updates `activities` in batches.
2. **CLI Command**: Exposed as `python src/kinetiqo.py backfill-weather` for manual or headless triggering.
3. **Sync Pipeline**: As new activities sync or are enriched, `update_activity_weather_summary()` is called directly after `upsert_activity_weather()`.

---

## 7. Nearest Data & Spatial Cache Architecture

To protect against external API quota exhaustion (Visual Crossing HTTP 429) and prevent GPS sample dropouts on short or sparse activities:

1. **GPS Route "Nearest" Fallback**:
   * If a calculated hourly interval has no recorded GPS points strictly within its start and end boundaries (common with short activities, GPS startup delays, or paused intervals), `weather_sample_position()` falls back to the temporally nearest recorded point from the activity route (`min(valid, key=lambda p: abs((p[0] - at).total_seconds()))`).
   * If streams are completely empty but `activity.start_latlng` is present, a pseudo-point is created from the summary coordinates.
2. **Spatial Proximity Hourly Weather Cache (15 km)**:
   * Instead of requiring exact 5-decimal coordinate matches, `_find_cached_hour()` matches cached hourly records within `MAX_WEATHER_CACHE_DISTANCE_METRES = 15,000` (15 km) for the same date and hour.
   * Multiple activities in the same neighborhood or city on the same day share weather records with zero redundant API calls.
3. **Local Database Pre-Populated Cache**:
   * On sync startup, `DatabaseRepository.load_weather_cache()` loads recent completed records from the local `weather` table.
   * Activities that overlap previously fetched weather hours in the same region are enriched directly from local database records without consuming Visual Crossing API quota.
4. **Hour Matching Nearest Fallback**:
   * If Visual Crossing or cached records return timestamps slightly offset from the exact requested epoch (e.g. half-hour reporting), `_weather_hour()` selects the nearest hour within 3600 seconds.

---

## 8. Visual Crossing Service Quotas & API Key Setup

* **Registration & Free API Key**: Obtain a key at [visualcrossing.com/weather-api](https://www.visualcrossing.com/weather-api). No credit card required.
* **Daily Free Quota**: **1,000 free records per day**, resetting automatically at 00:00 UTC.
* **Overage Rate**: Metered pay-as-you-go pricing at $0.0001 per record ($1 per 10,000 records).
* **Multi-Worker Rate Limiting**: Visual Crossing supplies `X-RateLimit-Remaining` headers. When remaining reaches 0 or HTTP 429 is received, Kinetiqo's POSIX shared memory rate limiter locks further requests across all Gunicorn workers until UTC midnight.
* **Privacy**: Latitude and longitude are sent in real-time transiently to Visual Crossing in UTC; route coordinates are never stored in weather tables or logs.

