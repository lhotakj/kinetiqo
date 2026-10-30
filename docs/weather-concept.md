# Activity Weather Enrichment - Implementation Plan

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

## Goals

1. Enrich eligible GPS-tracked outdoor activities with hourly historical
   temperature, apparent temperature, conditions, precipitation, snowfall,
   wind, gusts, and calculated headwind.
2. Fetch weather only during explicit sync work, never from browser code or on
   demand by AI.
3. Avoid duplicate requests for activities with complete weather while allowing
   scoped, explicit resync.
4. Provide deterministic Strava weather placeholders and a bounded read-only
   MCP weather tool without exposing coordinates.
5. Stop weather requests promptly when Visual Crossing reports quota exhaustion,
   without database quota accounting.

## Non-goals

- Do not fetch current or forecast weather.
- Do not infer named hazards from numeric conditions.
- Do not make weather failures fail the Strava activity sync.
- Do not create a shared quota store, database ledger, cross-worker lock, or
  manual counter reset.
- Do not persist partial weather after quota exhaustion. The activity remains
  eligible for a later retry after reset.

## Architecture

### Data and repository

The portable `weather` table stores one JSON payload and timestamp per activity.
The existing profile preference, sync job persistence, and global sync lease
remain unchanged. Remove the quota-ledger schema entries, repository methods,
retention cleanup, and tests; do not drop pre-existing tables automatically.

The weather JSON documents:

- provider: `visual-crossing`;
- hourly resolution, fetch time, activity start/end, sport type, and units;
- each returned hourly weather record with provider condition/source fields;
- derived route bearing, route distance, and signed headwind component.

Terminal ineligible results such as `skipped_indoor` or `skipped_no_gps` have
empty samples. Transient network, malformed-response, or provider-limit
failures do not replace successful data and remain retryable.

### Provider client and quota state

The weather client uses bounded timeouts and retries transient network and HTTP
5xx failures once after one second. It parses `X-RateLimit-Remaining` as a
non-negative integer, ignoring missing, negative, or malformed values.

An in-memory rate-limit state records the next UTC midnight when a valid zero
header or HTTP 429 is observed. It is checked before each outbound request.
The state expires lazily at the next UTC midnight. It is intentionally
best-effort and process-local rather than durable or shared across Gunicorn
workers.

If exhaustion is reported after the final sample of an activity, persist that
complete activity. If it occurs before all samples are available, discard the
partial payload and let a later sync retry the activity. The sync weather phase
then stops and produces one warning; non-weather synchronization continues.

### Route processing

For each hourly interval overlapping an activity:

1. Use the midpoint of the clipped interval to interpolate a GPS position and
   route bearing.
2. Reject interpolation gaps greater than 15 minutes and do not extrapolate.
3. Request one route location/hour from Visual Crossing and retain only the
   requested provider hour.
4. Calculate headwind as
   `wind_speed_ms * cos(radians(wind_from_deg - route_bearing_deg))`; positive
   values oppose travel.
5. Store clipped interval duration for activity-level weighting. Do not imply
   precision finer than one hour.

Indoor activities and routes without usable GPS are skipped without a provider
request. Provider data not yet available is deferred and retryable.

### User interfaces

Keep the **Fetch weather data** and **Resync weather** controls in the web sync
page and their CLI equivalents. Remove all local quota/counter text from sync
and Settings pages. When exhaustion occurs, show one warning that Visual
Crossing stopped weather enrichment; the rest of the sync completes normally.

## Acceptance criteria

1. Fresh schemas create `weather` but not `weather_api_usage` or
   `weather_api_quota_lock`; existing obsolete tables are never dropped.
2. No weather request reads or writes a local quota ledger, lock, counter, or
   `queryCost`-derived usage.
3. A valid zero remaining header stops subsequent weather requests in the same
   process until UTC midnight, while retaining a completed final activity.
4. A 429 stops weather work and emits one warning while the overall sync
   completes. Missing or invalid headers do not stop successful requests.
5. Quota exhaustion during an activity does not persist partial weather; a
   later sync can retry that activity.
6. Fast/Full defaults, explicit resync, GPS privacy, hourly route sampling,
   placeholder formatting, and read-only MCP behavior remain unchanged.
7. Mocked tests cover zero-header handling, HTTP 429, malformed/missing
   headers, UTC reset, partial activity retryability, completed activity
   persistence, and the absence of quota database operations.

## Delivery phases

1. Remove local quota-ledger schema/repository/runtime code and obsolete tests.
2. Add process-local provider-limit state and response-header parsing to the
   weather client.
3. Update sync behavior for completed versus partial activities and one warning
   per weather phase.
4. Remove quota text from Settings and sync UI.
5. Add focused mocked tests and update this concept and the user guide.
