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
  - **Strava API**: Monitors 15-minute (100 request) and daily (1,000 request) quotas, enforcing automatic backoff to prevent token blacklisting.
  - **Visual Crossing Weather**: In-memory multi-worker shared rate-limit lock automatically halting requests until UTC midnight upon quota exhaustion.
- 📝 **Comprehensive Audit Logging**: Persists detailed execution logs for every sync run (trigger source, activities added, deleted, durations, errors) viewable at `/logs`.

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
4. **Phase 4: Weather Enrichment**: If enabled, requests historical hourly weather at the activity midpoint and calculates route headwind vectors.

---

## 3. Web Routes & API Endpoints

| URL Route / Endpoint | Method | Purpose |
|---|---|---|
| `/fastsync` | POST | Trigger an incremental fast sync |
| `/fullsync` | POST | Trigger a full historical audit sync |
| `/sync/start/<type>` | GET | Render the interactive SSE progress bar view |
| `/api/sync/stream/<type>` | GET | Server-Sent Events (SSE) event stream |
| `/api/sync/stop` | POST | Cancel active synchronization operation |
| `/logs` | GET | View sync execution history and audit logs |

---

## 4. CLI Execution

Sync operations can be executed directly from terminal or automated cron jobs:

```bash
# Incremental fast sync
python src/kinetiqo.py sync --fast

# Full sync audit
python src/kinetiqo.py sync

# Full sync limited to last 30 days
python src/kinetiqo.py sync --days 30

# Sync skipping Strava description updates
python src/kinetiqo.py sync --no-update-strava

# Sync skipping weather enrichment
python src/kinetiqo.py sync --no-weather
```

---

## 5. Visual Artifacts

- Real-Time SSE Sync Progress Bar: `docs/activities-sync.webp`

