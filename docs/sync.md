# Real-Time Synchronization Engine & Architecture

The **Kinetiqo Sync Engine** manages two-way synchronization between the Strava API, external weather providers, and your local relational database warehouse, featuring **Server-Sent Events (SSE)** real-time progress updates, 4-phase ETL pipelining, and strict rate-limit protection.

---

## 1. Overview & Capabilities

- 🔄 **Incremental Fast Sync vs. Full History Audit**:
  - **Fast Sync**: Rapid 5–15 second check examining the newest 30 activities to pull recent workouts.
  - **Full Sync**: Comprehensive reconciliation of your entire athletic history, detecting remotely deleted workouts, backfilling missing telemetry streams, updating trophies, and verifying consistency.
- ⚡ **HTMX & Server-Sent Events (SSE) Reactivity**: Live interactive progress bar streaming current phase, activity name, percent complete, and elapsed time with zero page polling.
- 🛑 **Graceful Sync Cancellation**: Immediate, safe cancellation of active sync tasks via `/api/sync/stop` or CLI signals without database corruption.
- 🔒 **Rate-Limit Guardians**:
  - **Strava API**: Inspects `X-RateLimit-Limit`, `X-RateLimit-Usage`, `X-ReadRateLimit-Limit`, and `X-ReadRateLimit-Usage` headers on every API call. Proactively calculates remaining requests across 15-minute and daily windows, surfacing actionable warnings across both the Web interface and CLI as soon as 90% of any rate limit has been reached (`Strava API rate limit warning: 90% limit has been reached...`).
  - **Visual Crossing Weather**: In-memory multi-worker shared rate-limit lock automatically halting requests until UTC midnight upon quota exhaustion.
- 📝 **Comprehensive Audit Logging & Normalized Per-Activity Status**: Emits standardized, structured single-line progress updates combining Strava description update status with normalized tags (`[agent-<name>: <status>]`, `[weather: <status>]`). Execution logs for every sync run are persisted and viewable at `/logs`.
- 🤖 **Non-Destructive AI Agent Invalidation**: Retriggering evaluates only agent tokens configured in the activity's template, preserves all other cached agents on the activity, retains previous cached text if generation fails with an explicit log warning, and marks the status as `[agent-<name>: error kept cached]`.
- 🛡️ **Weather Configuration Safeguards**: If `VISUAL_CROSSING_API_KEY` is not configured, the sync UI automatically unchecks and disables "Fetch weather data" and "Resync weather", displaying an informative red tooltip alert.

---

## 2. 4-Phase Synchronization Pipeline

During a sync pass, each workout progresses through four discrete ETL phases:

```
┌────────────────────────────────────────────────────────┐
│ Phase 1: Summary Activities Discovery                  │
│ GET /api/v3/athlete/activities (Paging, 30-200/page)    │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 2: Detailed Workouts & Telemetry Streams         │
│ GET /api/v3/activities/{id} & /streams (1 Hz sensor)   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 3: True Verified KOMs & Segment Trophies         │
│ GET /api/v3/athletes/{id}/koms & segment_efforts       │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Phase 4: Historical Weather & Headwind Enrichment      │
│ Visual Crossing Timeline API & Route Bearing           │
└────────────────────────────────────────────────────────┘
```

### Phase Details:
1. **Phase 1: Summary Discovery**: Fetches activity summaries, checks for existing records in the database, and identifies new or modified workouts.
2. **Phase 2: Detailed Streams**: Downloads full sensor time-series (time, lat/lng, distance, altitude, velocity, heart rate, cadence, watts, temperature, moving, grade).
3. **Phase 3: Verified KOMs & Trophies**: Queries Strava's athlete KOM endpoint to retrieve true King of the Mountains crowns, and parses detailed segment efforts to log top-10 leaderboard trophies.
4. **Phase 4: Weather Enrichment**: If enabled, requests historical hourly weather at the activity midpoint and calculates route headwind vectors via Visual Crossing Timeline API (1,000 free records/day from [visualcrossing.com/weather-api](https://www.visualcrossing.com/weather-api); see [docs/weather.md](weather.md)).

---

## 3. Normalized Sync Log Specification & Tag Taxonomy

During synchronization, each activity outputs a clean, single-line progress update formatted as:

```text
[{i}/{total}] ({percent}%) {name} ({sport}){trophies}{desc_status} [agent-<name>: <status>] [weather: <status>]
```

### Ordering Rule
The regular Strava description update status (`{desc_status}`) appears **first**, followed by standardized square-bracket status tags for AI agents and weather:
- `| Strava description updated` — Fresh description content was rendered and successfully written to Strava via the API.
- `| Skipping Strava description update` — Description update was skipped (unchanged, sport has no template, or OAuth write scope absent).
- `| Strava description deferred: weather unavailable` — Template requires weather placeholders (`{{weather-*}}`), but weather was not yet available.

### Standardized Status Tags

#### AI Agent Status Tags (`[agent-<name>: <status>]`)
| Tag | Meaning |
|---|---|
| `[agent-<name>: cache]` | Successfully read and reused existing cached response from local database. |
| `[agent-<name>: refreshed]` | Fresh response generated by the AI provider and persisted to the database. |
| `[agent-<name>: error kept cached]` | Generation failed/timed out, but previous cached response was **retained**; logged a warning. |
| `[agent-<name>: error]` | Generation failed with no prior cached response available to fall back to. |

> **Non-Destructive Invalidation:** When **Retrigger AI agents** is active, cache invalidation is per activity and per agent token. Retriggering only touches tokens present in that activity's sport template; any other agent responses cached on that activity are **preserved**. Invalidation only occurs upon successfully fetching a non-empty response. If regeneration fails, the previous response is kept and logged as a warning.

#### Weather Status Tags (`[weather: <status>]`)
| Tag | Meaning |
|---|---|
| `[weather: cache]` | Weather already existed in the database and was reused (no API query made). |
| `[weather: refreshed]` | Fresh hourly weather successfully retrieved from Visual Crossing and saved to DB. |
| `[weather: deferred]` | Deferred because Visual Crossing rate limit was exhausted, GPS route did not cover sample, or template deferred. |
| `[weather: error - indoor activity]` | Weather skipped because the activity is indoor/virtual (VirtualRide, Treadmill, etc.). |
| `[weather: error - no GPS route]` | Weather skipped because no GPS route coordinates exist for this activity. |
| `[weather: error]` | Weather provider error or network failure. |

#### Weather Configuration Safeguards
When `VISUAL_CROSSING_API_KEY` is unset or empty:
- **"Fetch weather data"** and **"Resync weather"** checkboxes are disabled and forced unchecked in the UI.
- The `(i)` tooltip beside both options displays red text: `Weather is not configured. Please provide VISUAL_CROSSING_API_KEY<br>`.
- Server endpoints (`/fastsync`, `/fullsync`, `/sync/start/<type>`) automatically force weather processing off.

---

## 4. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/fastsync` | GET | Render the Fast Sync UI page |
| `/fullsync` | GET | Render the Full Sync UI page |
| `/sync/start/<type>` | POST | Start sync job (`fast` or `full`) and return HTMX SSE progress container |
| `/api/sync/stream/<job_id>` | GET | Server-Sent Events (SSE) real-time event stream |
| `/api/sync/stop` | POST | Cancel active synchronization operation |
| `/logs` | GET | View sync execution history and audit logs |

---

## 5. CLI Execution

Sync operations can be executed directly from terminal or automated cron jobs:

```bash
# Incremental fast sync
python src/kinetiqo.py sync --fast

# Full sync audit
python src/kinetiqo.py sync

# Full sync limited to last 30 days
python src/kinetiqo.py sync --period 30d

# Sync skipping Strava description updates
python src/kinetiqo.py sync --no-update-strava-description

# Sync skipping weather enrichment
python src/kinetiqo.py sync --no-weather-data

# Sync retriggering AI agents
python src/kinetiqo.py sync --retrigger-ai-agents
```

---

## 6. Visual Artifacts

- Real-Time SSE Sync Progress Bar: `docs/activities-sync.webp`

