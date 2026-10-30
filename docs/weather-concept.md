# Activity Weather Enrichment — Implementation Plan

## Status and decisions

This document records the implementation contract. Provider review found that Open-Meteo's historical endpoints are not included in its free plan, so the selected provider is Visual Crossing:

- Use Visual Crossing Timeline Weather API's free tier, which currently allows **1,000 historical weather records in any 24-hour period**. It requires a Visual Crossing API key, supplied as `VISUAL_CROSSING_API_KEY`; never log or persist the key. Verify the plan terms and record accounting before release.
- Query one requested hourly route location/time per request and use the provider's `queryCost` as the authoritative usage amount. Some hourly requests have returned a cost greater than one (24 in production); reserve the additional units before accepting the requested hour. Use a local rolling-24-hour guard of 800 records for a warning and 900 records as a hard cap, counting every retry attempt.
- Use **hourly** history, not 15-minute samples. Writing repeated or interpolated readings as 15-minute observations would imply unsupported precision.
- Request the API in UTC (`timezone=Z`) and preserve its `datetimeEpoch`, returned `source` (`obs`, `histfcst`, `stats`, `comb`, etc.) and `queryCost`. Treat provider conditions as provider descriptions, not WMO codes. Request `lang=en` and preserve exact condition text; never infer named hazards the source does not return.
- Visual Crossing documents historical `temp`, `feelslike`, `precip`, `snow`, `preciptype`, `conditions`, `winddir`, `windspeed`, and `windgust` fields. Missing values remain missing, never zero.
- Attribute displayed or exported data as `Weather data by Visual Crossing` and link to https://www.visualcrossing.com/ beside the display and to its API documentation. Confirm the current attribution terms and free-tier terms before release.
- Store weather in JSON in a new `weather` table associated with an activity.
- Save a profile preference, `enable_weather_data`, to permit/default weather enrichment.
- Normal sync fills missing weather only. Explicit resync replaces weather in the selected activity scope.
- Fast Sync resync covers all eligible activities already stored in the Fast Sync date window, not only newly returned activities. The current Fast Sync lower bound is the latest stored activity timestamp minus two days, floored to UTC midnight; if there is no stored activity it falls back to the full fetch (or the explicit period limit).
- Apply the user's cycling wind bands to **headwind component**, not ambient wind speed. Report ambient direction/speed and gusts separately. The bands are provisional and must remain easy to adjust:

  | Headwind component (m/s) | Cycling label |
  |---:|---|
  | 0.0–2.7 | Light breeze |
  | 2.8–5.4 | Moderate wind |
  | 5.5–8.3 | Notable headwind |
  | 8.4–12.5 | Strong wind |
  | >12.5 | Extreme wind |

  Implement contiguous thresholds using the component rounded to one decimal place so there are no gaps between the supplied ranges.
- Apply these cycling gust labels to the activity's maximum valid hourly gust, independently of steady wind/headwind:

  | Maximum gust (m/s) | Cycling label |
  |---:|---|
  | 0.0–7.9 | Mild gusts |
  | 8.0–10.9 | Moderate gusts |
  | 11.0–16.9 | Notable gusts |
  | 17.0–24.9 | Severe gusts |
  | ≥25.0 | Extreme / gale gusts |

  Round to one decimal place before classification to make the boundaries contiguous. Use the class and maximum speed in cycling templates; do not state unsupported lateral-displacement, equipment-damage, or crash-certainty claims from the supplied impact notes. For non-cycling activities, report numeric gusts without cycling-specific classifications.
- Add a read-only weather MCP tool for `/chat` and external MCP clients. Separately, generate Strava description weather placeholders deterministically in Python; do not make those placeholders depend on an LLM or an MCP round trip.
- Start web syncs through a CSRF-protected POST and make the job-ID SSE GET read-only. Persist job ownership, state, and ordered progress events in the configured database so any web worker can serve/replay the stream.
- Retry transient network/time-out and HTTP 5xx failures once after a bounded one-second delay, reserving quota for every attempt. A 429 stops weather requests for that run; report `Retry-After` if supplied and leave unfinished activities retryable.

## Goals

1. Enrich eligible GPS-tracked outdoor activities with hourly historical weather along the route, including temperature, apparent (“feels like”) temperature, weather condition, precipitation/rain, snowfall, wind direction, wind speed, gusts, and calculated headwind component.
2. Make weather fetching optional and profile-configurable, with Fast Sync enabled by preference and Full Sync disabled by default.
3. Avoid duplicate calls for activities with completed weather data. Allow deliberate, scope-limited resync with clear warnings and a conservative rolling-24-hour request guard.
4. Provide concise, useful human-readable Strava template placeholders produced by deterministic, unit-tested Python.
5. Let `/chat` request structured weather for a specific activity through a read-only MCP tool, without sending route coordinates to the AI provider.

## Non-goals

- Do not fetch current/forecast weather, make weather calls from browser code, or request weather on demand from an AI tool.
- Do not make a normal Fast Sync backfill all older activities that lack weather; only newly added activities are candidates in that mode.
- Do not store or expose route coordinates in weather JSON, chat/MCP output, or logs.
- Do not create quarter-hour records by copying/interpolating hourly reanalysis.
- Do not make weather failures fail the Strava activity sync, or replace a previously successful weather row with a transient failure.
- Do not add a manual quota-counter reset/bypass option or imply that the local guard is the provider's authoritative quota state.

## Current-codebase integration points

- `SyncService.sync()` in `src/kinetiqo/sync.py` owns activity synchronization and yields status/warnings. Add weather as an independent optional phase so a weather failure does not invalidate successfully synced Strava activity data.
- The Click `sync` command is in `src/kinetiqo/cli.py`; the web sync page and SSE entry points are `src/kinetiqo/web/templates/sync.html` and `/sync/start/<type>` plus `/api/sync/stream/<type>` in `src/kinetiqo/web/app.py`. The current stream GET starts the sync; the implementation must replace this with a CSRF-protected POST that creates a durable job and a read-only SSE GET keyed by job ID.
- Profile schema is centrally defined in `src/kinetiqo/db/schema.py`; the `DatabaseRepository` contract and PostgreSQL, MySQL, and Firebird implementations must stay aligned.
- MCP activity tools are registered in `src/kinetiqo/mcp/server.py`, with activity helpers in `src/kinetiqo/mcp/tools/`. Chat discovers read-only MCP tools through its existing tool-discovery pipeline.
- Add mocked tests using the repository's existing sync, CLI, web, schema, and MCP test patterns. Never call Strava, Visual Crossing, or a live database in unit tests.

## Recommended architecture

### 1. Data model and portable persistence

Create the following tables in the shared schema after `activities`. Use the repository's existing backend-specific ID/foreign-key conventions and schema upgrade path; definitions below are logical contracts, not dialect-specific DDL.

**Web sync job persistence — shared state for POST-started syncs and SSE readers**

Extend the existing `sync_jobs` table with a requester/owner identifier, serialized run options, `cancel_requested`, and `last_event_sequence`. Keep its status, timestamps, activity counters, and error summary as the durable job summary; use explicit `queued`, `running`, `completed`, `failed`, `cancelled`, and `interrupted` statuses. If the worker cannot be scheduled, mark the created job failed and return an error rather than a usable stream URL.

Add **`sync_job_events`** with `(job_id, event_sequence)` as the primary key, a foreign key to `sync_jobs`, `event_payload` as JSON text, and a UTC `created_at` timestamp. Add an index on `created_at` for retention cleanup. Append the next sequence and event in one transaction so a client can resume from `Last-Event-ID` and any app worker can serve the stream. Event payloads contain progress/warnings only—never route coordinates, tokens, or provider request data. Retain events for 24 hours after completion and job summaries for 30 days, then prune them in bounded cleanup.

The start POST validates options and CSRF, creates the job, and schedules its worker before returning its ID. The authenticated SSE GET verifies the requesting user owns the job, reads events after the supplied sequence, and never starts or mutates a sync. A CSRF-protected stop POST sets that job's cancellation flag; the worker checks it between activities and request chunks.

**`sync_execution_lock` — serialize all sync entry points**

Seed one row per configured database. Store an opaque `owner_token`, optional `job_id`, and UTC `lease_expires_at`. `SyncService.sync()` must acquire this lease atomically before doing sync work, regardless of whether it was called by web, CLI, or MCP; a second active caller gets a clear “sync already running” outcome. Renew the lease every 30 seconds from a heartbeat independent of the sync generator, with a five-minute expiry; release it in `finally` only when the owner token matches. If renewal fails, signal the worker to stop before the next write or external request. Reclaim an expired lease atomically and mark its associated web job interrupted before admitting a new worker. On the first request after a web-app process starts, interrupt all persisted queued/running web jobs, set their cancellation flags, and clear the global lease so stale state from a stopped app cannot block a new sync; workers in other app processes are also cancelled by this policy. Use cryptographically secure tokens; do not hold a database transaction open for the duration of a sync.

**`weather` — one current weather result or terminal skip state per activity**

| Column | Logical type | Rules |
|---|---|---|
| `activity_id` | Same type as `activities.activity_id` | Primary key and foreign key to `activities`; cascade delete if supported consistently, otherwise explicitly delete the weather row in the activity-delete transaction. |
| `weather_json` | Text/CLOB | Non-null, versioned JSON document described below. Keep JSON parsing/validation in Python, not dialect-specific JSON operators. |
| `updated_at` | UTC timestamp | Required; update only after a successful complete result or a terminal, non-retryable eligibility result is stored. |

The primary key supports direct lookup and the left join used to find activities without a weather row. Do not add a redundant activity index.

**`weather_api_usage` — append-only request-attempt ledger for a rolling window**

| Column | Logical type | Rules |
|---|---|---|
| `attempt_id` | Fixed-length string (UUID text) | Primary key, generated before reservation. |
| `attempted_at` | UTC timestamp | Required; written before the HTTP request. Ambiguous timeouts remain counted. |
| `quota_units` | Positive integer | Provider usage charged by this request, determined by documented accounting (for example one per HTTP request or one per requested location). |

Add an index on `attempted_at`. Do not attach this row to an activity or cascade-delete it; it exists to account for provider quota even after activity deletion. Prune entries older than 30 days during a bounded maintenance step, never before the 24-hour guard has expired.

**`weather_api_quota_lock` — serialize concurrent local reservations**

| Column | Logical type | Rules |
|---|---|---|
| `quota_key` | Short string | Primary key; seed one stable row for Visual Crossing usage associated with this configured API key. |
| `lock_version` | Integer | Required, initialized to zero; incremented inside the reservation transaction to obtain a write lock. |

Implement `reserve_weather_api_request(now_utc, quota_units)` as one repository-level transaction in each backend: update/lock the seeded quota row, sum ledger `quota_units` where `attempted_at >= now_utc - 24 hours`, reject without inserting when the sum is already 900, otherwise insert the reservation and return the post-reservation total. Do not allow a reservation that would take the total above 900. The lock must be held until commit so two app workers sharing the same database cannot both pass the cap. A failed lock/count/insert fails closed. Backend-specific SQL/locking is acceptable behind the same repository contract and must be tested for each driver.

The Free plan supports one location per Timeline API request. Reserve one unit before dispatch, then reconcile any additional units reported by `queryCost` before accepting the requested hourly row. If the additional reservation is rejected, stop weather work for the run; do not accept data whose reported cost could not be accounted for. Do not batch locations.

Warn once per sync run whenever the observed rolling usage total is at least 800 records (including runs that start above the threshold); do not rely on a one-time threshold-crossing event that could be missed by a later run.

**Quota storage and reset:** The request ledger is stored in the configured Kinetiqo database. The local allowance is rolling: each reservation checks attempts in the preceding 24 hours, so there is no midnight reset or manual reset operation. An attempt ages out of the guard 24 hours after its timestamp. Keep ledger entries for 30 days for diagnostics, then prune older entries. Do not provide a CLI counter-reset/bypass command. Visual Crossing describes the Free limit over any 24-hour period; Kinetiqo's rolling window is a conservative local guard, not a guarantee of remaining provider quota. Requests from other clients sharing the API key are not visible to Kinetiqo.

**`weather_json` version 1 contract**

```json
{
  "schema_version": 1,
  "status": "complete",
  "provider": "visual-crossing",
  "attribution_url": "https://www.visualcrossing.com/",
  "resolution": "hourly",
  "fetched_at": "UTC ISO-8601 timestamp",
  "activity": {
    "start_utc": "UTC ISO-8601 timestamp",
    "end_utc": "UTC ISO-8601 timestamp",
    "sport_type": "Ride"
  },
  "units": {
    "temperature": "°C",
    "precipitation": "mm",
    "snowfall": "cm",
    "wind_speed": "m/s",
    "wind_direction": "degrees",
    "headwind_component": "m/s"
  },
  "samples": [
    {
      "time_utc": "UTC ISO-8601 timestamp",
      "interval_seconds": 3600,
      "conditions": "Rain, Overcast",
      "precipitation_types": ["rain"],
      "provider_events": [],
      "source": "obs",
      "query_cost": 1,
      "temperature_c": 0.0,
      "apparent_temperature_c": 0.0,
      "precipitation_mm": 0.0,
      "snowfall_cm": 0.0,
      "wind_speed_ms": 0.0,
      "wind_direction_deg": 0,
      "wind_gusts_ms": 0.0,
      "route_bearing_deg": 0.0,
      "headwind_component_ms": 0.0
    }
  ]
}
```

Only store values actually returned by the provider; absent values remain `null` or are omitted and must not be interpreted as zero. Store the provider's `conditions` text in English and the provider's exact `source` field. Preserve exact provider-supplied named weather labels only when the documented result explicitly includes them; never infer a blizzard, supercell, or other named event from meteorological indicators. For terminal, non-retryable outcomes, use the same JSON envelope with `status` set to a documented reason (for example `skipped_indoor` or `skipped_no_gps`) and an empty `samples` array. Transient API, network, malformed-response, or quota failures do not replace an earlier successful row and do not create a terminal skip row.

**`profile.enable_weather_data`** is a non-null boolean defaulting to false for existing and newly initialized profiles. It controls the Fast Sync default, not a hard prohibition: a user can explicitly opt in for a single run while the preference is off.

Do not persist exact latitude/longitude in the weather payload or expose it through MCP. Use the existing GPS stream transiently to locate the activity at each weather timestamp and calculate its bearing. Preserve the observed weather values and derived route-relative components, not unnecessary precise location history.

The request ledger counts attempted outbound HTTP requests, regardless of activity. This is separate from per-activity weather records: resyncing an activity must still add a request attempt even though only one weather row exists for that activity.

Repository work must add parameterized methods for reading/upserting activity weather, atomically reserving/counting recent quota units, creating/updating sync jobs and ordered progress events, and acquiring/renewing/releasing the sync lease in all three backends. The weather table's primary key is sufficient for direct activity lookup; do not add redundant indexes unless an identified query needs them.

### 2. Visual Crossing client and hourly route processing

Add a focused weather service/client module that:

1. Calls Visual Crossing's Timeline API (`https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/...`) only from the server, with bounded timeouts, `timezone=Z`, exact UTC hourly bounds, `lang=en`, metric units, and only the documented fields `datetimeEpoch`, `temp`, `feelslike`, `precip`, `snow`, `preciptype`, `conditions`, `winddir`, `windspeed`, `windgust`, `source`, and `queryCost`. Send the key from `VISUAL_CROSSING_API_KEY` without logging the URL or key. Follow the documented single-location free-tier endpoint. Validate that `queryCost` is positive, account for its full value in the local quota ledger, and accept the response only when it contains the requested historical hourly row.
2. Uses the activity's GPS time/lat/lng stream to select a route position and travel bearing for each hourly provider interval overlapping the activity. Use the midpoint of the interval clipped to the activity's start/end as the route lookup time. Interpolate latitude/longitude by timestamp between the valid GPS points bracketing that time; derive bearing from that segment. Do not extrapolate; if the bracketing points are more than 15 minutes apart, omit that weather sample as a route-coverage gap. Issue one single-location, one-hour query per valid sample and reserve quota before every request, reconciling the response's full `queryCost`. During a sync, keep returned hourly records in an in-memory cache keyed by the exact rounded request location and UTC date; reuse cached hours and never persist the coordinates.
3. Derives signed headwind component as `wind_speed_ms * cos(radians(wind_from_deg - route_bearing_deg))`. Positive means wind opposing travel; negative means tailwind. Never classify crosswind as headwind. Apply cycling bands only to positive headwind magnitude; values at or below zero have no headwind label.
4. Treat an hourly value as representative only for `[time_utc, time_utc + 3600 seconds)`. Clip the first/last activity interval to activity start/end; store the resulting overlap in `interval_seconds`, and weight headwind duration/distance by that overlap. Do not count a full hour for an activity that was active for only part of that hour. Hourly precipitation/snow totals remain provider-hour values; for activity-level totals prorate only the clipped first/last hour by overlap fraction and label the result as estimated.
5. Mark source resolution as hourly. Do not interpolate values into fictional quarter-hour observations.
6. Skips indoor activities and records a clear terminal status for an outdoor activity with no usable GPS/time stream, so it is not retried on every ordinary sync. Re-evaluate `skipped_no_gps` locally during explicit resync or when the activity's GPS stream is refreshed; do not make a weather request while it remains ineligible. A provider response that does not yet cover the activity's time range is deferred and remains retryable on a later sync, not stored as complete or terminal. API/network/quota failures remain retryable and must not replace a prior successful row.
7. Keeps weather enrichment isolated from Strava API calls and ensures a Visual Crossing outage or malformed response produces a warning, not a failed activity sync.
8. Retries connection/time-out and HTTP 5xx failures no more than once, after one second; each outbound attempt has a separate quota reservation. HTTP 429 stops weather work for the run and reports `Retry-After` when supplied. Other HTTP 4xx responses stop the weather phase without retrying, leaving incomplete weather eligible for a later run after configuration is corrected.

Include the Visual Crossing attribution link in Settings/help documentation. The free allowance is currently 1,000 historical records per 24 hours; count the provider-reported `queryCost` for each request, regardless of how many fields are selected. Preserve the returned source category for each sample (`obs`, `histfcst`, etc.). Re-check [Timeline API documentation](https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api/), [record accounting](https://www.visualcrossing.com/resources/documentation/weather-data/what-exactly-is-a-weather-record/), [pricing](https://www.visualcrossing.com/weather-data-pricing/), and attribution terms before release.

### 3. Sync behavior, defaults, and resync

Add `enable_weather_data` to the profile schema and preserve it in profile reads/upserts for PostgreSQL, MySQL, and Firebird. Expose one **Enable Weather data** checkbox in Settings with a concise explanation of hourly reanalysis, route-derived headwind estimates, privacy, limits, and attribution.

Use the saved setting as the weather-sync default, with per-run selection:

- FAST: weather checkbox defaults to the saved preference; when enabled, fetch only missing weather for activities newly added by the current Fast Sync. Do not silently use Fast Sync as a backfill over all older activities that lack weather.
- FULL: weather checkbox is unchecked by default even if the profile preference is enabled. The user may explicitly opt in for that run.
- A disabled preference means no automatic weather requests. A deliberate per-run opt-in or explicit resync is a user override and must be clearly visible.

**Web controls and interactions (required on both Fast Sync and Full Sync pages):**

1. Add an accessible **Fetch weather data for this sync** checkbox. Fast Sync initializes it from `profile.enable_weather_data`; Full Sync initializes it unchecked. The submitted checkbox state is authoritative for that run; do not let stale `localStorage` override the server-side profile default. Unchecking it disables weather for the current run only and does not change the saved Settings preference.
2. Add an accessible **Resync existing weather** checkbox, unchecked by default. Checking it automatically checks/enables the weather checkbox. If weather is unchecked afterward, clear and disable resync. Resync remains available even when the saved preference is off because it is an explicit per-run user action.
3. Ordinary Fast Sync considers only activities newly added in that run; it does not backfill missing weather on older activities in the Fast Sync date window. Full Sync considers eligible activities inside the selected Full Sync scope. Resync considers all eligible activities already stored in the same scope, including rows that already have weather. For Fast Sync, the scope is its current cutoff (`latest_activity_time - 2 days`, floored to UTC midnight), or all-time/period-limited on a first sync. No UI action may widen the selected scope silently.
4. When resync is selected, warn that processing may stop before all eligible activities are refreshed when the local rolling-window cap is reached. Per-request quota reservations remain authoritative; do not claim an exact provider quota balance.
5. Show the warning in an accessible confirmation dialog. Canceling does not create a job, start sync, or alter stored weather.
6. Only after confirmation, send a CSRF-protected `POST /api/sync/start/<type>` with the selected options. It creates a durable `sync_jobs` row and starts the worker; return a job ID and SSE URL. Do not start a sync from an HTMX/EventSource GET. `GET /api/sync/stream/<job_id>` is read-only, verifies authentication and job ownership, replays persisted events after `Last-Event-ID`, and never starts work. The worker appends progress events through the shared database, so the stream may be served by another web worker. `POST /api/sync/stop/<job_id>` sets that job's cancellation flag. At most one active web sync per requester is allowed.
7. Pass weather/resync options into `SyncService.sync()` from the durable job. Before worker execution, validate mode/options and recompute scope/candidates; per-request database reservation, not an estimate, is authoritative for quota. Log effective options without sensitive coordinates. Do not put sync state or options in the SSE GET URL.
8. Display progress and terminal summaries for weather candidates fetched, already-current rows skipped, terminal ineligible rows, retryable failures, and activities skipped at the quota cap. The worker must check its per-job cancellation flag between activities and request chunks.

Settings and sync-page behavior are deliberately separate: the Settings checkbox stores the Fast Sync default, while the two sync-page checkboxes control only a single run. Use the same option semantics in CLI and web; do not add a web-only behavior that can resync while weather fetching is disabled.

- CLI: add the following options to the existing `sync` command. An omitted weather option follows the same mode/profile defaults as the web UI. Keep existing sync mode, period, and Strava-description options unchanged:
  - `--weather-data` / `--no-weather-data`: tri-state per-run override. If omitted, FAST follows the saved profile preference and FULL defaults off. `--no-weather-data` always skips weather for this run.
  - `--resync-weather`: explicitly replaces existing weather for eligible activities in the selected sync scope. It implies `--weather-data`; combining it with `--no-weather-data` is a usage error.
  - `--resync-weather` is explicit user intent and starts without an additional confirmation prompt. This works in interactive and non-interactive CLI runs. Full Sync also needs no confirmation flag; weather remains off by default unless explicitly enabled.
  - Show local rolling-24-hour quota units and the 900-record local cap in CLI status/warnings. Do not expose a manual quota reset flag.
- At 800 locally counted provider records in the preceding 24 hours, emit a visible/logged warning. At 900 records, stop issuing weather HTTP requests until usage ages out of that window, retain already fetched data, and report how many activities were skipped. Do not claim to know Visual Crossing's true remaining quota or reset boundary.
- A row is complete only after valid data is stored. Missing/incomplete weather remains retryable on later enabled Fast Syncs. Resync overwrites the existing row atomically after a successful fetch; failures preserve the previous successful row.
- Weather errors and quota stops appear in CLI output and the web job summary/events. Stop signals should be honored between activities and request chunks; the web stop action is per job rather than a process-global signal.
- The weather client retries connection/time-out failures and HTTP 5xx responses at most once, after a one-second delay. Each attempt reserves quota independently; ambiguous timeouts remain charged. On HTTP 429, stop weather work for that run without retrying, and report the provider's `Retry-After` header if present. Other HTTP 4xx responses stop weather work for the run without retrying; leave incomplete activity rows retryable after configuration is corrected.

CLI examples:

```text
python src/kinetiqo.py sync --fast-sync
python src/kinetiqo.py sync --fast-sync --weather-data
python src/kinetiqo.py sync --full-sync --period 30d --weather-data
python src/kinetiqo.py sync --full-sync --period 30d --resync-weather
python src/kinetiqo.py sync --fast-sync --no-weather-data
```

The first command follows the stored preference; `--weather-data` explicitly enables weather for that run; Full Sync requires explicit opt-in. `--resync-weather` itself is the explicit request and does not prompt; the live local quota guard remains active.

### 4. Deterministic Strava description placeholders

Add a dedicated Python formatter that consumes the stored JSON and returns concise English text without calling an AI service. It must handle missing/invalid data safely, use named thresholds, suppress absent conditions, avoid claims beyond hourly model data, and have table-driven tests for rain, snow, heat, calm weather, strong gusts, headwind/tailwind/crosswind, and no data. Use these initial defaults as descriptive—not official hazard—cutoffs:

- Use Visual Crossing's documented `conditions` descriptions and `precipitation_types`; do not assume WMO weather codes are available. Preserve provider-returned severe wording such as thunderstorm, hail, freezing precipitation, blizzard, or supercell even when it occurs in only one hourly sample. Do not infer named events from proxy measurements or absent fields.
- Visual Crossing's hourly historical API does not expose a general severe-event catalog. Preserve any explicit event data only when the response actually includes it; use the provider's `conditions` text for hazards it names, and never synthesize an unsupported event label.
- Report duration-weighted air temperature and apparent temperature when available, rounded to the nearest whole °C. Add “hot” when peak apparent temperature is 30.0–34.9°C and “very hot” at 35.0°C or above. Also report “cold” when the lowest air or apparent temperature is below 5°C, and “freezing” when either reaches 0°C or below, with the corresponding minimum value. These are descriptive cues, not safety assessments.
- Mention rain or snow only when provider-returned precipitation type or amount supports it. Round reported amounts to one decimal place. Omit precipitation wording otherwise.
- Mention ambient wind when the interval-weighted mean reaches 2.8 m/s or any gust reaches 8 m/s; report rounded mean speed and highest gust. Compute displayed mean direction using circular, not arithmetic, averaging.
- For cycling, classify the maximum valid gust after rounding to one decimal place: 0.0–7.9 mild, 8.0–10.9 moderate, 11.0–16.9 notable, 17.0–24.9 severe, and ≥25.0 m/s extreme/gale. Include the label and peak speed in `{{weather-wind}}`; keep steady-wind/headwind classification separate. Do not include unverified claims about sideways movement, wheel damage, or guaranteed crashes. For other sports, report gust speed without cycling labels.
- For cycling, classify only positive headwind component with the selected bands; report no headwind classification for zero, tailwind, or crosswind. Report duration/distance only for intervals with a positive headwind component.

Initial placeholders:

- `{{weather-basic}}`: one sentence summarizing the most relevant conditions across the activity; include duration-weighted air temperature and apparent temperature when available, add “hot”/“very hot” by the peak apparent-temperature thresholds, and “cold”/“freezing” by the lowest air or apparent temperature thresholds above. Include only noteworthy precipitation or wind. For cycling, mention gusts only at 8.0 m/s or higher and use the matching class; omit mild gusts from this compact summary. Never say “no rain” merely because precipitation is absent.
- `{{weather-start}}`: conditions from the first available hourly sample at the beginning of the activity, including rain/snow only when recorded.
- `{{weather-precipitation}}`: concise rain and/or snow amount/duration/event timing; resolve to an empty string when neither occurred.
- `{{weather-wind}}`: ambient wind direction, maximum non-zero gust with its cycling class where applicable, and cycling headwind duration/distance plus the user's classification/mean/peak headwind component when meaningful. Omit gust details if gust values are missing or all zero.

The user's cycling bands apply to the **headwind component** for cycling activities only. For other outdoor sports, describe ambient wind/gusts without labeling the ride-specific headwind bands. Keep classification boundaries in named constants so the user can refine them later. For missing samples, placeholders resolve empty rather than fabricating dry/calm conditions. Add these tokens to template validation, supported-variable discovery, help text, and preview output.

#### 4.1 Rules for generating a natural-language weather summary

`{{weather-basic}}` is a deterministic, concise English sentence generated from the stored hourly samples. It describes modeled conditions along the activity route, not conditions measured by the athlete's device. Use only fields present in the versioned weather payload; do not make a provider request or infer missing values while formatting.

**Input eligibility and weighting**

- Return an empty string when weather status is not complete or there are no valid hourly samples. Ignore invalid samples and samples outside the activity's start/end time.
- For each sample, use its stored `interval_seconds`, clipped to the activity time range. Use these seconds as weights for temperature, apparent temperature, wind speed, and projected headwind calculations. Do not treat every hourly sample as an equal-duration observation when the first or last interval is partial.
- Use the interval midpoint for ordering rain/snow samples. Sum precipitation amounts proportionally to the clipped interval duration. Do not interpolate samples or manufacture quarter-hour precision.
- Determine the dominant condition from provider-returned `conditions` descriptions, weighted by covered seconds. Preserve any explicit severe condition text even when it is brief and non-dominant. If condition data is absent, omit the sky/weather-condition phrase.

**Sentence composition**

Build one grammatical sentence from the available components, in this order, omitting unavailable components and avoiding repeated information:

1. **Conditions and extreme events:** Use concise provider-returned condition text as the dominant description. Preserve explicit provider wording for named events (including blizzards, thunderstorms, hail, or supercells) even when brief. Never infer events or severity labels from proxies such as temperature, wind, precipitation, or visibility. Omit a condition phrase when conditions are missing.
   - If the API explicitly supplies a named severe event in `provider_events`, include that provider-supplied label and severity. Do not infer `blizzard`, `supercell`, or another named extreme from CAPE, snowfall, wind, gusts, visibility, or other proxy combinations. When no explicit event label is available, describe the supported conditions without assigning an unsupported event name.
2. **Precipitation:** Mention rain or snow only when provider-returned types or amounts indicate it. Sum rain in millimeters and snow in centimeters over clipped intervals, rounded to one decimal place. If a positive total rounds to 0.0, say `trace rain` or `trace snow`; if precipitation fields are missing, omit precipitation rather than describing it as absent.
3. **Temperature:** Include duration-weighted air and apparent temperature, rounded to the nearest whole degree Celsius, when available; phrase apparent temperature as `feels like`. Add `hot` when peak apparent temperature is 30.0–34.9°C and `very hot` when it is at least 35.0°C. Add `cold` when the minimum air or apparent temperature is below 5°C, and `freezing` when either minimum is at or below 0°C; include the corresponding minimum, distinguishing an apparent-temperature minimum with `feels like`. Compare unrounded values to the thresholds. These are descriptive labels only, not safety advice.
4. **Ambient wind and gusts:** Mention duration-weighted ambient wind only when its average is at least 2.8 m/s. Include a compass direction only when at least 70% of valid wind-covered seconds have a direction within ±45° of the duration-weighted circular-mean direction. Compute that mean from the duration-weighted sine and cosine components of valid directions; compute angular distance with wrap-around, and omit direction if the circular mean is undefined. Do not imply that ambient wind direction is headwind. For cycling, report the maximum valid gust using the supplied classification: 0.0–7.9 m/s mild, 8.0–10.9 m/s moderate, 11.0–16.9 m/s notable, 17.0–24.9 m/s severe, and at least 25.0 m/s extreme/gale. In `{{weather-basic}}`, omit mild gusts and mention moderate-or-higher gusts. Do not attach impact or safety claims to these labels.
5. **Cycling headwind:** Calculate the headwind component for each sample as `wind_speed_ms × cos(radians(wind_from_deg - route_bearing_deg))`; positive values are headwind components and negative values are tailwind components. Use the stored route bearing and meteorological wind-from direction. For classification and mean, weight positive components by their interval duration only:
   - `positive_headwind_seconds = sum(interval_seconds where headwind_component_ms > 0)`
   - `mean_positive_headwind_ms = sum(max(headwind_component_ms, 0) × interval_seconds) / positive_headwind_seconds`
   - Omit the headwind class and mean if `positive_headwind_seconds` is zero. Otherwise round the mean to one decimal place and use the user's cycling headwind classes: 0.0–2.7 m/s `Light breeze`, 2.8–5.4 `Moderate wind`, 5.5–8.3 `Notable headwind`, 8.4–12.5 `Strong wind`, and at least 12.6 `Extreme wind`.
   - Report the positive-headwind share as `positive_headwind_seconds / valid_wind_covered_seconds × 100`, rounded to a whole percent. This is the percentage of **covered ride time**, not total activity time. Show it only when valid wind coverage is at least 30% of total activity duration. Do not count invalid or missing wind intervals in either numerator or denominator.
   - Mention headwind in `{{weather-basic}}` only when the mean positive component is at least 2.8 m/s and the coverage requirement is met. Do not describe a headwind as a safety threat.

Do not output a hard-coded “perfect day” sentence, assert safety or danger, or claim conditions that cannot be derived from the valid stored fields. If only some components are available, return a natural sentence using those components rather than filling gaps with assumptions.

**Examples**

- `Clear, feels like 19°C, with a moderate 3.4 m/s headwind during 35% of covered ride time.`
- `Overcast with 2 mm of rain later, around 12°C.`
- `Partly cloudy with snow, around 1°C, and notable gusts up to 12.4 m/s.`
- `Partly cloudy, with a brief thunderstorm and hail late in the ride, around 12°C.`
- If the source reports heavy snow and strong gusts but no explicit blizzard event, describe those conditions without calling it a blizzard.
- If there is no complete weather payload or no valid sample, return an empty string.

`{{weather-wind}}` may be more detailed than the compact sentence: include valid headwind duration/distance and the interval-weighted mean and peak positive headwind component when meaningful; include the coverage-qualified percentage above. For cycling, its gust class is based on the maximum valid gust independently of headwind. For other sports, report ambient wind/gusts numerically without applying cycling-specific headwind or gust labels.


### 5. `/chat` MCP weather tool

Register a read-only tool such as `kinetiqo_get_activity_weather(activity_id, include_samples=False)`:

- Resolve one activity and its weather row through the repository; enforce existing athlete scoping and normalize integer/string activity IDs consistently.
- Return a compact source/provenance-aware summary by default and, when requested, saved chronological hourly samples including provider condition text, explicit provider events when present, ambient wind, precipitation/snow, temperature/apparent temperature, gusts, and headwind data. Never include GPS coordinates.
- Exclude GPS coordinates and unrelated activity data. Bound output size and report truncation/status explicitly for unusually long or partial activities.
- Add the tool to normal chat tool discovery and external MCP registration; it must not be classified as mutating.
- Update AI prompts/docs so the model calls this tool for activity-specific historical weather questions, distinguishes measured/model-estimated values, and does not infer unavailable conditions.
- This tool serves `/chat` and external MCP clients. The Strava `{{weather-basic}}` family remains deterministic Python expansion; do not add MCP execution to the Strava AI-agent pipeline in this plan.

## Alternatives and tradeoffs

1. **Hourly route samples (chosen):** Matches the source resolution and lets Kinetiqo project wind onto the route at each hour. Less detailed than quarter-hour output, but avoids fake temporal precision and keeps API/storage/token use modest.
2. **Quarter-hour output:** Rejected for the first version because the chosen historical source is hourly. Replicating/interpolating hourly values into four records per hour would misrepresent their precision.
3. **Weather fetched by the AI on demand:** Rejected. It adds repeated API calls, makes descriptions non-deterministic, increases provider-token/context usage, leaks more location data, and couples results to external network availability.
4. **Only a compact activity summary:** Cheaper to store and pass to AI, but insufficient for questions about when headwinds/rain occurred. Store hourly samples and provide a bounded MCP response.
5. **Native dialect-specific JSON columns:** Rejected initially because PostgreSQL, MySQL, and Firebird must share portable repository behavior. Store validated JSON text and parse in Python.
6. **Station-observation-only weather:** Not selected for MVP. Station availability/distance creates uneven route coverage; Visual Crossing provides historical observation and other provenance sources. Station-only filtering may be added later as an explicit mode.

## Efficiency, quota, AI, and MCP risks

- **API quotas:** Count provider quota units, not route samples; also record every outbound HTTP attempt. Batch route coordinates only after confirming how the provider charges batched locations. The local rolling-24-hour total cannot account for other clients sharing the IP and is not synchronized to a confirmed provider reset window. Reservation timestamps/units are stored in `weather_api_usage`; usage ages out 24 hours after reservation.
- **Model uncertainty:** Historical hourly reanalysis is not a sensor on the rider. Local showers, valley winds, buildings, and road-level gusts can differ; expose source/resolution and phrase output as an estimate.
- **False precision:** Store hourly values only. Route bearing and headwind are derived from GPS and should be labeled calculated, not provider-observed.
- **AI tokens:** One activity per MCP call; include only requested activity weather. Return summary by default and hourly samples only when requested, with an explicit maximum/truncation marker.
- **Privacy:** GPS coordinates are sent to Visual Crossing for weather lookup but not stored in the weather JSON or returned to the AI. Explain this in Settings.
- **Long syncs:** Full activity sync must not trigger weather by default. Explicit weather runs are interruptible and have bounded per-request timeouts and quota checks.
- **Data gaps:** Indoor/no-GPS activities, missing provider variables, and API failures must be distinct statuses; do not turn missing data into “dry” or “calm.”
- **Third-party terms:** Free endpoint use is non-commercial. Require attribution and verify current limits/licence before release; a commercial deployment needs a properly licensed plan.
- **Portability:** JSON text, a shared schema definition, parameterized SQL, transaction-safe usage counting, and backend-specific tests are required across all database backends.

## API rate limits of Visual crossing
The Visual Crossing API daily limit resets at 00:00 (Midnight) UTC each day.

### Key Timing Details

• The Reset Mechanism: Your daily pool of 1,000 records zeroes out exactly at midnight Universal Coordinated Time (UTC).
• Local Time Impact: Depending on your location, this means the limit resets at a different time on your local clock. For example, midnight UTC corresponds to:
	• 7:00 PM EST / 4:00 PM PST (North America)
	• 1:00 AM CET (Central Europe)

### How to Track Your Usage

Visual Crossing tracks your exact remaining quota dynamically. You can inspect how close you are to the reset by looking at the HTTP Response Headers of your API calls:
• Look for the X-RateLimit-Remaining header to see how many records you have left before the next midnight UTC reset.
• If you exceed your limit before midnight UTC, the API will return an HTTP 429 Too Many Requests error until the clock strikes 00:00 UTC.

## Delivery phases

1. **Verify provider contract and data model:** confirm current free-tier allowance, attribution wording, per-record quota accounting, hourly variable units, historical availability, and exact endpoint behavior before release. Visual Crossing condition text is provider-authored; named hazard labels must not be promised unless actually returned.
2. **Database/repository:** add the profile preference, weather payload, rolling-attempt ledger, quota-lock row, durable sync-job fields/event table, portable repository methods, bounded cleanup, and PostgreSQL/MySQL/Firebird mocked tests.
3. **Weather service:** implement hourly route sampling, wind projection, source/status metadata, per-request quota accounting, retries/failure semantics, and mocked HTTP/math tests.
4. **Sync/CLI/web:** add mode-aware defaults, profile checkbox, per-run checkbox, accessible web resync estimate/confirmation, CSRF-protected POST job creation, database-backed progress/replay and per-job cancellation, immediate CLI resync via explicit flag (no confirmation prompt), progress/warnings, stop handling, retry policy, and CLI/web parity tests.
5. **Description placeholders:** implement deterministic formatter, token validation/discovery, and golden/table-driven cases for all weather combinations.
6. **MCP/chat:** add the read-only activity weather tool, output bounds, chat discovery, and instruction tests.
7. **Documentation and release checks:** update `docs/AI.md`, technical AI/MCP docs, Settings attribution/help, and relevant CLI documentation. Run the focused mocked suites and the repository's broader test suite; perform an opt-in manual smoke test only if credentials/network are available.

## Acceptance criteria

1. Schema initialization creates `weather`, `weather_api_usage`, the seeded `weather_api_quota_lock`, `sync_job_events`, the seeded `sync_execution_lock`, the non-null profile preference, and required indexes automatically on PostgreSQL, MySQL, and Firebird; existing profiles default to weather disabled.
2. Hourly values are stored once per eligible activity, with valid source/model/units/status metadata and no duplicate fetch during ordinary sync. Route lookup uses timestamp interpolation at each clipped hourly interval midpoint, rejects bracketing gaps greater than 15 minutes, and never stores interpolated weather as finer-than-hourly data. Provider data not yet available remains deferred and retryable; `skipped_no_gps` is reconsidered on explicit resync or when GPS becomes available.
3. FAST and FULL default behavior matches the saved profile setting and stated opt-ins; FULL never starts weather automatically. Ordinary FAST only fills missing weather for newly inserted activities; FAST resync refetches all eligible existing database activities in the current Fast Sync date window.
4. CLI and web can explicitly resync only their selected activity scope, preserve prior successful data on failed replacement, and stop at the local rolling-24-hour cap. CLI treats `--resync-weather` itself as explicit intent and never prompts.
5. Quota behavior warns once per sync run when rolling-24-hour usage is at least 800 records and stops reservations that would exceed 900 records within that window; usage ages out after 24 hours, ledger entries are retained for 30 days, and no CLI option can bypass/reset the guard.
6. CLI exposes `--weather-data/--no-weather-data` and `--resync-weather` with the documented defaults and conflict validation. The explicit `--resync-weather` option requires no additional flag or prompt, and no CLI option disables quota protection.
7. Settings and both web sync pages expose all controls: saved Fast Sync default, per-run weather enable/disable, and explicit resync. The estimate/confirmation flow is canceled without side effects, and server-side validation enforces the same option rules as CLI.
8. Headwind is calculated from meteorological wind-from direction, wind speed, and route bearing; the supplied cycling classifications are applied only to projected headwind, with gusts reported separately.
9. `{{weather-basic}}`, `{{weather-start}}`, `{{weather-precipitation}}`, and `{{weather-wind}}` render deterministic output; absent rain/snow are omitted and missing weather yields empty placeholders. Provider-named severe conditions are retained even when brief; unsupported labels are never inferred from proxies.
10. The read-only MCP tool returns bounded hourly data and provenance, excludes GPS coordinates, and is discoverable by `/chat` and external MCP clients.
11. The web start action is a CSRF-protected POST; its SSE GET is read-only, verifies job ownership, and can replay persisted events from `Last-Event-ID` across different app workers. Worker scheduling failure produces a failed job, not a dead stream. Sync-job event rows expire 24 hours after completion and job summaries after 30 days. Stop requests are per-job and cancellation is checked between activities and request chunks.
12. All web, CLI, and MCP sync invocations acquire the shared database sync lease; concurrent callers are rejected, lease renewal/release is owner-token guarded, renewal is independent of blocking generator/network work, and an expired lease is safely reclaimed with its web job marked interrupted.
13. Retry tests prove network/time-out and 5xx failures get at most one retry after one second, each attempt consumes reserved quota, 429 stops weather work and reports `Retry-After`, and other 4xx responses stop the weather phase without retrying.
14. Unit tests make no real network or database calls; all three SQL backend implementations and failure cases are covered. Test quota reservations, retries, route interpolation, formatting of provider severe condition text, all cycling headwind/gust boundaries, and non-cycling output.
15. Settings/help and documentation explain hourly model estimates, privacy, free/non-commercial limits, the local conservative request cap, quota storage/reset behavior, CLI flags, and required attribution.

## Grill-me resolutions

- Use hourly records because that matches the historical source resolution.
- The profile preference controls automatic defaults; Fast Sync may default on when enabled, Full Sync remains opt-in, and explicit user override/resync is visible.
- Resync replaces saved weather only within the selected sync scope; ordinary sync only fills missing weather.
- Use a local rolling-24-hour guard of 800 warning / 900 hard stop under the provider's currently documented 1,000-record free allowance.
- Store request-attempt timestamps and provider quota units in `weather_api_usage`; apply a rolling-24-hour local guard, retain ledger entries for 30 days, and provide no manual reset/bypass CLI option. This is a conservative Kinetiqo window, not a provider reset time or an estimate of requests made elsewhere.
- Use `--weather-data/--no-weather-data` and `--resync-weather` for CLI weather controls; the explicit resync option needs no extra prompt, while the quota guard remains mandatory.
- Use the user's supplied cycling labels on calculated headwind component and their gust-speed classes independently; report ambient wind and gusts separately, and avoid unverified impact claims. Headwind percentage is positive-headwind seconds divided by valid wind-covered seconds, is phrased as a percentage of covered ride time, and is omitted when wind coverage is below 30% of total activity duration.
- Classify cycling gusts using the maximum valid gust, independently of headwind; emit a gust class in `{{weather-wind}}`, use only moderate-or-higher classes in `{{weather-basic}}`, and leave non-cycling gusts numeric.
- `/chat` uses a read-only MCP weather tool; Strava weather placeholders use a separate deterministic Python formatter over the same stored data.
- For ambient wind direction, require at least 70% of valid wind-covered seconds within ±45° of the duration-weighted circular mean; otherwise omit direction.
- Use the dominant provider condition text, weighted by duration; preserve explicit severe labels even when brief.
- Assign precipitation timing to early/middle/late activity thirds, combine adjacent wet thirds, round rain/snow totals to 0.1 mm/0.1 cm, and describe positive totals rounding to zero as trace precipitation.
- Preserve provider-returned severe weather wording; never infer a blizzard, supercell, thunderstorm, or other named event from proxy measurements.
- For temperature wording, include duration-weighted air/apparent temperature when available, add `hot`/`very hot` at peak apparent-temperature thresholds of 30.0°C and 35.0°C, and add `cold` below 5.0°C or `freezing` at/below 0.0°C using the lowest air or apparent temperature.
- Web sync starts via CSRF-protected POST; job state and progress events are persisted in the configured database. The stream GET is read-only and job-ID keyed. Retain progress events for 24 hours after completion and job summaries for 30 days.
- Retry weather-client transient network/time-out and 5xx errors once after one second, counting every attempt; a 429 stops weather work for that run and reports `Retry-After`, while other 4xx stop the weather phase without retry.
- All sync entry points (web, CLI, MCP) share a renewable database lease; only one sync may run against the configured database at a time.

## Ambiguity Report

  Goals:        0.0   ✓ clear
  Acceptance:   0.25  ✓ mostly clear; preflight excludes not-yet-fetched Strava activities
  Boundaries:   0.0   ✓ clear
  Alternatives: 0.0   ✓ compared
  Assumptions:  0.25  ✓ provider quota accounting/reset and named hazard-event availability must be verified before enabling requests
  ──────────────────────────────
  Aggregate:    0.10  ✓ below threshold (0.2 spec)

Push lightly on: verification of provider free-tier quota accounting, attribution, and availability of explicit named hazard-event text.
