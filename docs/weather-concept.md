# Activity Weather Enrichment — Implementation Plan

## Status and decisions

This document is an implementation plan, not an implementation. The user confirmed:

- Use Open-Meteo's free public service for personal, non-commercial use and add required attribution.
- Use **hourly** history, not 15-minute samples. Open-Meteo's historical series is hourly; writing repeated or interpolated readings as 15-minute observations would imply unsupported precision.
- Store weather in JSON in a new `weather` table associated with an activity.
- Save a profile preference, `enable_weather_data`, to permit/default weather enrichment.
- Normal sync fills missing weather only. Explicit resync replaces weather in the selected activity scope.
- Fast Sync resync covers all eligible activities already stored in the Fast Sync date window, not only newly returned activities. The current Fast Sync lower bound is the latest stored activity timestamp minus two days, floored to UTC midnight; if there is no stored activity it falls back to the full fetch (or the explicit period limit).
- Open-Meteo currently publishes a 10,000-calls/day free limit, but its pricing page does not specify the quota reset timezone/window. Do not claim that Open-Meteo resets at UTC midnight. Track this installation's attempted requests in a rolling 24-hour window, warn at 8,000, and hard-stop at 9,000 to reduce midnight-boundary bursts. Reserve/count before each request; a timeout may still have reached the provider, so do not refund an ambiguous attempt. This local guard is conservative, not an authoritative Open-Meteo quota meter; other consumers sharing the public IP may also use quota.
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
- Add mocked tests using the repository's existing sync, CLI, web, schema, and MCP test patterns. Never call Strava, Open-Meteo, or a live database in unit tests.

## Recommended architecture

### 1. Data model and portable persistence

Create the following tables in the shared schema after `activities`. Use the repository's existing backend-specific ID/foreign-key conventions and schema upgrade path; definitions below are logical contracts, not dialect-specific DDL.

**Web sync job persistence — shared state for POST-started syncs and SSE readers**

Extend the existing `sync_jobs` table with a requester/owner identifier, serialized run options, `cancel_requested`, and `last_event_sequence`. Keep its status, timestamps, activity counters, and error summary as the durable job summary; use explicit `queued`, `running`, `completed`, `failed`, `cancelled`, and `interrupted` statuses. If the worker cannot be scheduled, mark the created job failed and return an error rather than a usable stream URL.

Add **`sync_job_events`** with `(job_id, event_sequence)` as the primary key, a foreign key to `sync_jobs`, `event_payload` as JSON text, and a UTC `created_at` timestamp. Add an index on `created_at` for retention cleanup. Append the next sequence and event in one transaction so a client can resume from `Last-Event-ID` and any app worker can serve the stream. Event payloads contain progress/warnings only—never route coordinates, tokens, or provider request data. Retain events for 24 hours after completion and job summaries for 30 days, then prune them in bounded cleanup.

The start POST validates options and CSRF, creates the job, and schedules its worker before returning its ID. The authenticated SSE GET verifies the requesting user owns the job, reads events after the supplied sequence, and never starts or mutates a sync. A CSRF-protected stop POST sets that job's cancellation flag; the worker checks it between activities and request chunks.

**`sync_execution_lock` — serialize all sync entry points**

Seed one row per configured database. Store an opaque `owner_token`, optional `job_id`, and UTC `lease_expires_at`. `SyncService.sync()` must acquire this lease atomically before doing sync work, regardless of whether it was called by web, CLI, or MCP; a second active caller gets a clear “sync already running” outcome. Renew the lease every 30 seconds from a heartbeat independent of the sync generator, with a five-minute expiry; release it in `finally` only when the owner token matches. If renewal fails, signal the worker to stop before the next write or external request. Reclaim an expired lease atomically and mark its associated web job interrupted before admitting a new worker. Use cryptographically secure tokens; do not hold a database transaction open for the duration of a sync.

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
| `quota_key` | Short string | Primary key; seed one stable row for the shared free Open-Meteo endpoint during schema initialization. |
| `lock_version` | Integer | Required, initialized to zero; incremented inside the reservation transaction to obtain a write lock. |

Implement `reserve_weather_api_request(now_utc, quota_units)` as one repository-level transaction in each backend: update/lock the seeded quota row, sum ledger `quota_units` where `attempted_at >= now_utc - 24 hours`, reject without inserting when the sum is already 9,000, otherwise insert the reservation and return the post-reservation total. Do not allow a reservation that would take the total above 9,000. The lock must be held until commit so two app workers sharing the same database cannot both pass the cap. A failed lock/count/insert fails closed. Backend-specific SQL/locking is acceptable behind the same repository contract and must be tested for each driver.

Before implementation enables weather requests, verify from current Open-Meteo documentation whether a multi-location HTTP request consumes one quota unit or one unit per location. Set `quota_units` to that documented cost; do not assume HTTP request count equals provider usage. If documentation is inconclusive, disable multi-location batching and count one unit per single-location request until verified.

Warn once per sync run whenever the observed rolling usage total is at least 8,000 (including runs that start above the threshold); do not rely on a one-time threshold-crossing event that could be missed by a later run.

**Quota storage and reset:** The request ledger is stored in the configured Kinetiqo database. The local allowance is rolling, not calendar-day based: each reservation checks attempts in the preceding 24 hours, so there is no midnight reset and no manual reset operation. An attempt ages out of the guard 24 hours after its timestamp. Keep ledger entries for 30 days for diagnostics, then prune older entries. Do not provide a CLI counter-reset/bypass command. Open-Meteo's published pricing page does not document the provider's daily reset boundary; verify that contract before release and treat the local rolling guard as protective headroom, not a guarantee of remaining provider quota. This installation also cannot see other clients sharing the same public IP.

**`weather_json` version 1 contract**

```json
{
  "schema_version": 1,
  "status": "complete",
  "provider": "open-meteo",
  "model": "actual model identifier returned/selected",
  "attribution_url": "https://open-meteo.com/en/licence",
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
      "weather_code": 0,
      "provider_events": [],
      "temperature_c": 0.0,
      "apparent_temperature_c": 0.0,
      "precipitation_mm": 0.0,
      "rain_mm": 0.0,
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

Only store values actually returned by the selected endpoint/model; absent values remain `null` or are omitted and must not be interpreted as zero. If the selected API/model explicitly returns named severe-weather events, preserve them per sample in an optional `provider_events` array containing the provider's event code/name, source field, and source-provided severity when present. Do not synthesize provider events from meteorological indicators; use the documented WMO weather code for its supported phenomena. For terminal, non-retryable outcomes, use the same JSON envelope with `status` set to a documented reason (for example `skipped_indoor` or `skipped_no_gps`) and an empty `samples` array. Transient API, network, malformed-response, or quota failures do not replace an earlier successful row and do not create a terminal skip row.

**`profile.enable_weather_data`** is a non-null boolean defaulting to false for existing and newly initialized profiles. It controls the Fast Sync default, not a hard prohibition: a user can explicitly opt in for a single run while the preference is off.

Do not persist exact latitude/longitude in the weather payload or expose it through MCP. Use the existing GPS stream transiently to locate the activity at each weather timestamp and calculate its bearing. Preserve the observed weather values and derived route-relative components, not unnecessary precise location history.

The request ledger counts attempted outbound HTTP requests, regardless of activity. This is separate from per-activity weather records: resyncing an activity must still add a request attempt even though only one weather row exists for that activity.

Repository work must add parameterized methods for reading/upserting activity weather, atomically reserving/counting recent quota units, creating/updating sync jobs and ordered progress events, and acquiring/renewing/releasing the sync lease in all three backends. The weather table's primary key is sufficient for direct activity lookup; do not add redundant indexes unless an identified query needs them.

### 2. Open-Meteo client and hourly route processing

Add a focused weather service/client module that:

1. Calls Open-Meteo's Archive API (`https://archive-api.open-meteo.com/v1/archive`) only from the server, with bounded timeouts, `timezone=UTC`, explicit date bounds and hourly variables (`temperature_2m`, `apparent_temperature`, `precipitation`, `rain`, `snowfall`, `weather_code`, `wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m`), validated coordinates/timestamps, and mocked HTTP tests. Confirm the exact model/variable support, the latest available historical timestamp, interval semantics, and current multi-location limit against official docs before enabling requests. Request any named hazard/event fields only if the selected endpoint/model explicitly documents them.
2. Uses the activity's GPS time/lat/lng stream to select a route position and travel bearing for each hourly provider interval overlapping the activity. Use the midpoint of the interval clipped to the activity's start/end as the route lookup time. Interpolate latitude/longitude by timestamp between the valid GPS points bracketing that time; derive bearing from that segment. Do not extrapolate; if the bracketing points are more than 15 minutes apart, omit that weather sample as a route-coverage gap. Request positions in a batched provider request where supported; if limits require chunks, count every HTTP request toward the rolling-24-hour guard.
3. Derives signed headwind component as `wind_speed_ms * cos(radians(wind_from_deg - route_bearing_deg))`. Positive means wind opposing travel; negative means tailwind. Never classify crosswind as headwind. Apply cycling bands only to positive headwind magnitude; values at or below zero have no headwind label.
4. Treat an hourly value as representative only for `[time_utc, time_utc + 3600 seconds)`. Clip the first/last activity interval to activity start/end; store the resulting overlap in `interval_seconds`, and weight headwind duration/distance by that overlap. Do not count a full hour for an activity that was active for only part of that hour. Hourly precipitation/snow totals remain provider-hour values; for activity-level totals prorate only the clipped first/last hour by overlap fraction and label the result as estimated.
5. Mark source resolution as hourly. Do not interpolate values into fictional quarter-hour observations.
6. Skips indoor activities and records a clear terminal status for an outdoor activity with no usable GPS/time stream, so it is not retried on every ordinary sync. Re-evaluate `skipped_no_gps` locally during explicit resync or when the activity's GPS stream is refreshed; do not make a weather request while it remains ineligible. A provider response that does not yet cover the activity's time range is deferred and remains retryable on a later sync, not stored as complete or terminal. API/network/quota failures remain retryable and must not replace a prior successful row.
7. Keeps weather enrichment isolated from Strava API calls and ensures an Open-Meteo outage or malformed response produces a warning, not a failed activity sync.
8. Retries connection/time-out and HTTP 5xx failures no more than once, after one second; each outbound attempt has a separate quota reservation. HTTP 429 stops weather work for the run and reports `Retry-After` when supplied. Other HTTP 4xx responses stop the weather phase without retrying, leaving incomplete weather eligible for a later run after configuration is corrected.

Use the free API only for non-commercial deployment and include appropriate Open-Meteo/data-provider attribution and licence links in Settings/help documentation. Preserve the specific source/model used for each result. Re-check the current terms and endpoint access before release; do not present free access as suitable for commercial use. Reference the [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), [pricing/free API terms](https://open-meteo.com/en/pricing), and [licence](https://open-meteo.com/en/licence).

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
4. When resync is selected, do not start a sync immediately. First request an authenticated, CSRF-protected `POST /api/sync/weather/estimate` with `{sync_type, limit_days, resync_weather: true}`. The estimate returns count of eligible activities already in the database, estimated provider quota units for those rows (including provider chunking where predictable), current rolling-24-hour usage units, remaining local capacity, and an explicit note that the provider reset boundary is undocumented. It performs no Strava/Open-Meteo requests and reserves no quota. Since the Strava fetch has not run yet, clearly label the estimate as a lower bound that excludes new Strava activities; those new Strava activities are still subject to the live quota guard.
5. Show the estimate in an accessible confirmation dialog. State that processing stops at the 9,000 local rolling-window cap and may leave some scoped activities unprocessed if actual calls exceed remaining capacity. Canceling does not create a job, start sync, or alter stored weather.
6. Only after confirmation, send a CSRF-protected `POST /api/sync/start/<type>` with the selected options. It creates a durable `sync_jobs` row and starts the worker; return a job ID and SSE URL. Do not start a sync from an HTMX/EventSource GET. `GET /api/sync/stream/<job_id>` is read-only, verifies authentication and job ownership, replays persisted events after `Last-Event-ID`, and never starts work. The worker appends progress events through the shared database, so the stream may be served by another web worker. `POST /api/sync/stop/<job_id>` sets that job's cancellation flag. At most one active web sync per requester is allowed.
7. Pass weather/resync options into `SyncService.sync()` from the durable job. Before worker execution, validate mode/options and recompute scope/candidates; the per-request database reservation, not the estimate, is authoritative for quota. Return these JSON fields from the estimate: `eligible_activity_count`, `estimated_quota_units`, `rolling_24h_quota_units`, `remaining_local_quota_units`, `local_warning_threshold` (8000), `local_hard_cap` (9000), `provider_daily_limit` (10000), and `provider_reset_window_known` (false until verified). Log effective options without sensitive coordinates. Do not put sync state or options in the SSE GET URL.
8. Display progress and terminal summaries for weather candidates fetched, already-current rows skipped, terminal ineligible rows, retryable failures, and activities skipped at the quota cap. The worker must check its per-job cancellation flag between activities and request chunks.

Settings and sync-page behavior are deliberately separate: the Settings checkbox stores the Fast Sync default, while the two sync-page checkboxes control only a single run. Use the same option semantics in CLI and web; do not add a web-only behavior that can resync while weather fetching is disabled.

- CLI: add the following options to the existing `sync` command. An omitted weather option follows the same mode/profile defaults as the web UI. Keep existing sync mode, period, and Strava-description options unchanged:
  - `--weather-data` / `--no-weather-data`: tri-state per-run override. If omitted, FAST follows the saved profile preference and FULL defaults off. `--no-weather-data` always skips weather for this run.
  - `--resync-weather`: explicitly replaces existing weather for eligible activities in the selected sync scope. It implies `--weather-data`; combining it with `--no-weather-data` is a usage error.
  - `--resync-weather` is explicit user intent and starts without an additional confirmation prompt. This works in interactive and non-interactive CLI runs. Full Sync also needs no confirmation flag; weather remains off by default unless explicitly enabled.
  - Show local rolling-24-hour quota units and the 9,000-unit local cap in CLI status/warnings. Do not expose a manual quota reset flag.
- At 8,000 locally counted provider quota units in the preceding 24 hours, emit a visible/logged warning. At 9,000 units, stop issuing weather HTTP requests until usage ages out of that window, retain already fetched data, and report how many activities were skipped. Do not claim to know Open-Meteo's true remaining quota or reset boundary.
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

- Map every supported WMO weather code to its documented condition wording, with table-driven tests for each code: 0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, and 99. In addition to the dominant condition, always retain valid coded events for freezing drizzle/rain (56–57, 66–67), heavy rain/snow or violent/heavy showers (65, 75, 82, 86), and thunderstorms/hail (95, 96, 99), even if they occur in only one sample. Preserve event timing and distinguish hail when the WMO code indicates hail.
- If an API/model explicitly supplies a named extreme event (for example, blizzard or supercell), preserve and report that exact event label and provider severity. Standard WMO codes do not identify a supercell or blizzard: never infer either label from CAPE, snow, wind, gusts, visibility, or combinations of fields. Describe the available evidence instead (for example, heavy snow with strong gusts). Verify the selected endpoint/model's available hazard fields before requesting them; omit unsupported fields without treating them as zero.
- Report duration-weighted air temperature and apparent temperature when available, rounded to the nearest whole °C. Add “hot” when peak apparent temperature is 30.0–34.9°C and “very hot” at 35.0°C or above; do not infer safety thresholds.
- Mention rain when a rain WMO code occurs or prorated activity precipitation is at least 0.1 mm; mention snow when a snow WMO code occurs or snowfall is greater than 0.0 cm. Round reported amounts to one decimal place. Omit precipitation wording otherwise.
- Mention ambient wind when the interval-weighted mean reaches 5 m/s or any gust reaches 8 m/s; report rounded mean speed and highest gust. Compute displayed mean direction using circular, not arithmetic, averaging.
- For cycling, classify the maximum valid gust after rounding to one decimal place: 0.0–7.9 mild, 8.0–10.9 moderate, 11.0–16.9 notable, 17.0–24.9 severe, and ≥25.0 m/s extreme/gale. Include the label and peak speed in `{{weather-wind}}`; keep steady-wind/headwind classification separate. Do not include unverified claims about sideways movement, wheel damage, or guaranteed crashes. For other sports, report gust speed without cycling labels.
- For cycling, classify only positive headwind component with the selected bands; report no headwind classification for zero, tailwind, or crosswind. Report duration/distance only for intervals with a positive headwind component.

Initial placeholders:

- `{{weather-basic}}`: one sentence summarizing the most relevant conditions across the activity; include duration-weighted air temperature and apparent temperature when available, and add “hot”/“very hot” only by the peak apparent-temperature thresholds above. Include only noteworthy precipitation or wind. For cycling, mention gusts only at 8.0 m/s or higher and use the matching class; omit mild gusts from this compact summary. Never say “no rain” merely because precipitation is absent.
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
- Determine the dominant condition from the stored WMO weather code categories, weighted by covered seconds. Resolve an overall duration tie by severity, in this order: thunderstorm/hail, freezing precipitation, heavy snow, heavy/violent rain, other snow, other rain/drizzle, fog, overcast, other cloud, clear. Use the code-specific mapping; do not infer cloud cover or thunderstorm probability. If condition data is absent, omit the sky/weather-condition phrase.

**Sentence composition**

Build one grammatical sentence from the available components, in this order, omitting unavailable components and avoiding repeated information:

1. **Condition and explicit extreme events:** Use a concise dominant WMO description (for example, `clear`, `partly cloudy`, `overcast`, `rain`, or `snow`). For a change, compare the duration-weighted dominant WMO category in the first and second halves of the activity. Weight each category by its valid sample-interval overlap with the relevant half. Emit at most one transition, only if the categories differ and each category accounts for at least 20% of total valid covered time; otherwise report only the overall dominant category. If either half has a tied dominant category, omit the transition. Use plain wording such as `partly cloudy, turning to overcast`. Never call clear conditions `sunny` unless the stored WMO code supports that wording.
   - Do not let a dominant-condition summary hide a brief coded event. Always include valid samples with WMO codes 56–57 (freezing drizzle), 66–67 (freezing rain), 65 (heavy rain), 75 (heavy snow), 82 (violent rain showers), 86 (heavy snow showers), or 95, 96, and 99 (thunderstorms, including hail where indicated). Coalesce consecutive intervals with the same event code into one event phrase; assign its time as early/middle/late using the sample interval midpoint and activity thirds. Use the exact code-specific description and avoid repeating an event already stated in the dominant condition or precipitation phrase.
   - If the API explicitly supplies a named severe event in `provider_events`, include that provider-supplied label and severity. Do not infer `blizzard`, `supercell`, or another named extreme from CAPE, snowfall, wind, gusts, visibility, or other proxy combinations. When no explicit event label is available, describe the supported conditions without assigning an unsupported event name.
2. **Precipitation:** Mention rain or snow only when the corresponding valid amount is greater than zero. Sum rain in millimeters and snow in centimeters over clipped intervals. Round displayed rain to 0.1 mm and snow to 0.1 cm; if a positive total rounds to 0.0, say `trace rain` or `trace snow` without a numeric amount. Divide elapsed activity time into three equal-duration segments: early `[start, start + duration/3)`, middle `[start + duration/3, start + 2×duration/3)`, and late `[start + 2×duration/3, end]`. Allocate each sample's prorated precipitation amount to a segment in proportion to its interval overlap. A segment is wet when its allocated rain or snow amount is positive; combine adjacent wet segments into one span (for example, `rain early through mid-ride`). Give the total and timing when timing is available; do not claim continuous rain or invent a shower count. Mention snow separately from rain, and avoid repeating precipitation already clearly stated by the WMO phrase. When precipitation fields are missing, omit precipitation rather than describing it as absent.
3. **Temperature:** Include duration-weighted air and apparent temperature, rounded to the nearest whole degree Celsius, when available; phrase apparent temperature as `feels like`. Add `hot` when peak apparent temperature is 30.0–34.9°C and `very hot` when it is at least 35.0°C. Do not label conditions unsafe or invent other heat/cold thresholds.
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
- Return a compact source/provenance-aware summary by default and, when requested, the saved chronological hourly samples including WMO weather codes, any explicit provider events, ambient wind, precipitation/snow, temperature/apparent temperature, gusts, and headwind data. Tool instructions should request samples when timing or changing conditions are relevant.
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
6. **Station-observation-only weather:** Not selected for MVP. Station availability/distance creates uneven route coverage; Open-Meteo provides broad reanalysis coverage. Station observations may be added later as a provenance-labeled validation/fallback source.

## Efficiency, quota, AI, and MCP risks

- **API quotas:** Count provider quota units, not route samples; also record every outbound HTTP attempt. Batch route coordinates only after confirming how the provider charges batched locations. The local rolling-24-hour total cannot account for other clients sharing the IP and is not synchronized to a confirmed provider reset window. Reservation timestamps/units are stored in `weather_api_usage`; usage ages out 24 hours after reservation.
- **Model uncertainty:** Historical hourly reanalysis is not a sensor on the rider. Local showers, valley winds, buildings, and road-level gusts can differ; expose source/resolution and phrase output as an estimate.
- **False precision:** Store hourly values only. Route bearing and headwind are derived from GPS and should be labeled calculated, not provider-observed.
- **AI tokens:** One activity per MCP call; include only requested activity weather. Return summary by default and hourly samples only when requested, with an explicit maximum/truncation marker.
- **Privacy:** GPS coordinates are sent to Open-Meteo for weather lookup but not stored in the weather JSON or returned to the AI. Explain this in Settings.
- **Long syncs:** Full activity sync must not trigger weather by default. Explicit weather runs are interruptible and have bounded per-request timeouts and quota checks.
- **Data gaps:** Indoor/no-GPS activities, missing provider variables, and API failures must be distinct statuses; do not turn missing data into “dry” or “calm.”
- **Third-party terms:** Free endpoint use is non-commercial. Require attribution and verify current limits/licence before release; a commercial deployment needs a properly licensed plan.
- **Portability:** JSON text, a shared schema definition, parameterized SQL, transaction-safe usage counting, and backend-specific tests are required across all database backends.

## Delivery phases

1. **Confirm provider contract and data model (blocking before enabling API calls):** verify current free historical endpoint, attribution wording, multi-location quota-unit accounting, coordinate-batch limit, hourly variable units, latest available timestamp, interval semantics, every supported WMO code, and any explicitly named hazard/event fields available in the selected model; finalize the model and quota reservation strategy. Do not promise blizzard/supercell naming unless the provider explicitly returns those labels.
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
4. CLI and web can explicitly resync only their selected activity scope, preserve prior successful data on failed replacement, and stop at the local rolling-24-hour cap. Web shows an estimate/confirmation before starting; CLI treats `--resync-weather` itself as explicit intent and never prompts. Web preflight and cancel do not make Open-Meteo calls or reserve quota.
5. Quota behavior warns once per sync run when rolling-24-hour usage is at least 8,000 units and stops reservations that would exceed 9,000 units within that window; usage ages out after 24 hours, ledger entries are retained for 30 days, and no CLI option can bypass/reset the guard. Provider quota units are based on verified Open-Meteo accounting, not an assumed request count.
6. CLI exposes `--weather-data/--no-weather-data` and `--resync-weather` with the documented defaults and conflict validation. The explicit `--resync-weather` option requires no additional flag or prompt, and no CLI option disables quota protection.
7. Settings and both web sync pages expose all controls: saved Fast Sync default, per-run weather enable/disable, and explicit resync. The estimate/confirmation flow is canceled without side effects, and server-side validation enforces the same option rules as CLI.
8. Headwind is calculated from meteorological wind-from direction, wind speed, and route bearing; the supplied cycling classifications are applied only to projected headwind, with gusts reported separately.
9. `{{weather-basic}}`, `{{weather-start}}`, `{{weather-precipitation}}`, and `{{weather-wind}}` render deterministic, grammatical output; absent rain/snow are omitted and missing weather yields empty placeholders. Every supported WMO code has a tested mapping, and coded severe events are included even when brief and non-dominant. Explicit provider-named extremes are retained; unsupported labels such as blizzard/supercell are never inferred from proxies. Condition changes use the first/second-half rule; precipitation timing allocates interval amounts across equal-duration thirds and merges adjacent wet thirds; direction is emitted only when at least 70% of valid wind-covered seconds lie within ±45° of the weighted circular mean.
10. The read-only MCP tool returns the requested activity's bounded hourly data and provenance, includes WMO codes and explicit provider events, excludes GPS coordinates, and is discoverable by `/chat` and external MCP clients.
11. The web start action is a CSRF-protected POST; its SSE GET is read-only, verifies job ownership, and can replay persisted events from `Last-Event-ID` across different app workers. Worker scheduling failure produces a failed job, not a dead stream. Sync-job event rows expire 24 hours after completion and job summaries after 30 days. Stop requests are per-job and cancellation is checked between activities and request chunks.
12. All web, CLI, and MCP sync invocations acquire the shared database sync lease; concurrent callers are rejected, lease renewal/release is owner-token guarded, renewal is independent of blocking generator/network work, and an expired lease is safely reclaimed with its web job marked interrupted.
13. Retry tests prove network/time-out and 5xx failures get at most one retry after one second, each attempt consumes reserved quota, 429 stops weather work and reports `Retry-After`, and other 4xx responses stop the weather phase without retrying.
14. Unit tests make no real network or database calls; all three SQL backend implementations and failure cases are covered. Backend tests verify quota and sync-lease locking/renewal/release/fail-closed behavior; service tests simulate concurrent reservations, confirm the hard cap, timeout accounting, 24-hour expiry, retention pruning, and that failed reservation prevents HTTP dispatch. Route math tests cover interval-midpoint interpolation, bearing, and the 15-minute gap boundary. Formatter tests cover every supported WMO code and brief/non-dominant freezing precipitation, heavy/violent precipitation, thunderstorms, and hail; same-code contiguous events are coalesced, provider-named extremes are rendered as supplied, and proxy-only blizzard/supercell inference is rejected. Also test hot/very-hot threshold boundaries, all five cycling headwind classes and gust classes at their rounding boundaries, and non-cycling output.
15. Settings/help and documentation explain hourly model estimates, privacy, free/non-commercial limits, the local conservative request cap, quota storage/reset behavior, CLI flags, and required attribution.

## Grill-me resolutions

- Use hourly records because that matches the historical source resolution.
- The profile preference controls automatic defaults; Fast Sync may default on when enabled, Full Sync remains opt-in, and explicit user override/resync is visible.
- Resync replaces saved weather only within the selected sync scope; ordinary sync only fills missing weather.
- Use a local rolling-24-hour guard of 8,000 warning / 9,000 hard stop under the published 10,000-calls/day free limit.
- Store request-attempt timestamps and provider quota units in `weather_api_usage`; apply a rolling-24-hour local guard, retain ledger entries for 30 days, and provide no manual reset/bypass CLI option. Open-Meteo's published pricing information does not specify the reset boundary or settle multi-location accounting, so verify both before enabling weather requests and do not present UTC as the provider's reset time.
- Use `--weather-data/--no-weather-data` and `--resync-weather` for CLI weather controls; the explicit resync option needs no extra prompt, while the quota guard remains mandatory.
- Use the user's supplied cycling labels on calculated headwind component and their gust-speed classes independently; report ambient wind and gusts separately, and avoid unverified impact claims. Headwind percentage is positive-headwind seconds divided by valid wind-covered seconds, is phrased as a percentage of covered ride time, and is omitted when wind coverage is below 30% of total activity duration.
- Classify cycling gusts using the maximum valid gust, independently of headwind; emit a gust class in `{{weather-wind}}`, use only moderate-or-higher classes in `{{weather-basic}}`, and leave non-cycling gusts numeric.
- `/chat` uses a read-only MCP weather tool; Strava weather placeholders use a separate deterministic Python formatter over the same stored data.
- For ambient wind direction, require at least 70% of valid wind-covered seconds within ±45° of the duration-weighted circular mean; otherwise omit direction.
- For condition changes, compare duration-weighted dominant WMO categories in the first and second activity halves; emit at most one transition when they differ and each accounts for at least 20% of total valid coverage, and omit transitions on ties.
- Assign precipitation timing to early/middle/late activity thirds, combine adjacent wet thirds, round rain/snow totals to 0.1 mm/0.1 cm, and describe positive totals rounding to zero as trace precipitation.
- Preserve and report every supported WMO code, including coded severe events even when they occur in one valid sample. Use named extremes such as blizzard or supercell only when the selected API/model explicitly supplies that event label; otherwise describe the available conditions without inference.
- For temperature wording, include duration-weighted air/apparent temperature when available and add `hot`/`very hot` only at peak apparent-temperature thresholds of 30.0°C and 35.0°C.
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

Push lightly on: Open-Meteo quota-unit accounting, reset window, historical data availability, and explicit named hazard-event support before enabling requests.
