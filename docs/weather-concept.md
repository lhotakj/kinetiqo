# Activity Weather Enrichment - Implementation Plan & Concept

## Status and decisions

Kinetiqo enriches eligible outdoor activities with historical hourly weather from
the Visual Crossing Timeline Weather API. The provider key is supplied through
`VISUAL_CROSSING_API_KEY`; it must never be logged or persisted.

- Use hourly history only. Do not copy or interpolate hourly readings into
  quarter-hour observations.
- Request the API in UTC (`timezone=Z`) with metric units and `lang=en`.
- Store only provider-returned weather values, condition text, source, and
  calculated route-relative data. Missing values remain missing.
- Save one versioned JSON weather document per activity in the `weather` table.
- Maintain precomputed summary scalar columns on the `activities` table for $O(1)$
  fast client-side grid display and sorting in `/activities`.
- The profile's `enable_weather_data` preference controls the Fast Sync default.
  Full Sync remains opt-in; explicit resync replaces weather in the selected
  scope.
- Never store route coordinates in weather JSON, logs, or MCP responses. GPS
  positions are used transiently for the provider lookup and bearing calculation.
- Attribute displayed or exported data as [Weather data by Visual Crossing](https://www.visualcrossing.com/).

## Visual Crossing API rate limits

Visual Crossing reports the remaining quota for the current UTC day in the
`X-RateLimit-Remaining` response header. Its daily allowance resets at
00:00 UTC.

Kinetiqo deliberately does **not** calculate or store its own quota total:

1. A valid `X-RateLimit-Remaining: 0` response is authoritative. Kinetiqo uses
   the response's weather data, then stops making further weather requests in
   that process until the next UTC midnight.
2. HTTP `429 Too Many Requests` is the fallback when the header is absent,
   malformed, or was not seen before the provider rejects a request. It also
   stops further weather requests for that process until the next UTC midnight.
3. Missing or invalid remaining-quota headers do not interrupt a successful
   weather request. Kinetiqo continues normally until it receives a valid zero
   value or HTTP 429.
4. The stop state is in-memory only. Gunicorn workers do not share process
   memory, and a server restart clears it. Another worker or a restarted server
   may therefore make a request; it stops as soon as Visual Crossing returns
   zero remaining quota or HTTP 429.
5. A quota stop affects weather enrichment only. The Strava sync completes and
   reports one clear warning. No counter, warning threshold, manual reset, or
   quota bypass is exposed.

## Weather Column in Activities Grid

The activities grid features a dedicated, toggleable **Weather** column:
```text
<temperature-icon> <min - max>°C <weather-condition-icon> <wind-direction-arrow> <wind-speed>m/s <precipitation-word-with-amount>
```

- **Temperature**: Thermometer SVG with temperature range (e.g. `14 - 18°C` or `18°C` if constant). Sorts by average temperature (`weather_temp_avg`).
- **Weather Condition Icon**: Cloudiness duration-weighted average (Clear, Partially cloudy, Overcast) with severe condition promotion (Thunderstorm, Rain, Snow).
- **Wind Direction Vector**: Arrow rotated to wind travel direction with cardinal tooltip (e.g. `West wind (270°) · 3.4 m/s`).
- **Precipitation**: Omitted when dry; displayed as `Rain (1.8mm)` or `Snow (0.5cm)` when wet.
- **Indoor / Missing**: Muted dash `-`, sorts nulls-last.
- **Default Visibility**: Hidden by default, toggleable via Column Visibility picker.
- **Auto-Backfill**: Runs on startup to populate activities from existing cached `weather_json` in the database, with a CLI command `kinetiqo backfill-weather`.

Detailed specification and formulas: [docs/concepts/weather-concept.md](docs/concepts/weather-concept.md).
