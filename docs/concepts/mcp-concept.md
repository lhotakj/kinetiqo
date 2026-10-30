# Kinetiqo MCP Server — Architecture, Toolset & Implementation Plan

> **Document Status**: Reviewed implementation blueprint; proposed feature, not yet implemented
> **Target Version**: Kinetiqo 2.x
> **Author**: Kinetiqo Architectural Team  
> **Location**: `docs/mcp-concept.md`

---

## 1. Executive Summary & Vision

The **Model Context Protocol (MCP)** is an open standard that connects Large Language Model (LLM) agents (such as Claude Desktop, Cursor, Antigravity IDE, Claude Code, ChatGPT, and custom AI agents) to external data sources and execution environments.

Remote Strava integrations are constrained by API access, permissions and provider limits. Avoid relying on a competitor's current limits, tool inventory or capabilities as a design assumption: these can change. Local queries against *previously synced* Kinetiqo data do not spend Strava API quota; sync, description writes, optional Strava lookups and external map tiles still use external services.

**Kinetiqo can become a private athlete-data assistant.** It stores activity metadata and available timestamped telemetry in PostgreSQL, MySQL or Firebird, computes power/fitness estimates, and renders posters and infographics via Playwright. Not every activity contains every sensor or a continuous 1 Hz stream. MCP can provide:

1. **Evidence-based training review**: Answers about recorded sessions, progress and workload that cite source activities, disclose missing data and distinguish measurements from estimates.
2. **A creative visual assistant**: Private posters, maps and infographic artifacts, once browser rendering has been extracted into reusable services.
3. **A guarded training assistant**: Optional, separately enabled syncs, goal changes and preview-bound Strava description publishing, never automatic writes from a read-only question.

> **MCP on/off switch (proposed, not implemented yet):** Docker deployments run **web only by default**. To start a separate MCP server, include the planned `build/compose.mcp.yaml` overlay **and** enable Docker Compose's `mcp` profile with `COMPOSE_PROFILES=mcp` (or Compose's `--profile mcp` option). Neither the profile without the overlay nor the overlay without the profile starts MCP. Local desktop MCP is instead enabled by registering the `kinetiqo mcp` stdio command in the client. See **Minimal MCP activation and environment-variable contract** in Section 5 and the **future-user setup guide** in Section 8 for required settings, client attachment and troubleshooting. There is no separate application-level enable switch inside the web server.
### Athlete jobs to be done

| Athlete question | Kinetiqo basis | MCP answer / dependency |
| :--- | :--- | :--- |
| What did I do this week, and am I on track? | Activities, totals and goals | Period totals, goal progress and remaining weekly pace; local calendar must be defined. |
| Did I improve compared with last month or season? | Activity metadata, FTP and Power Skills | Equal-period comparisons and qualifying source rides; add `kinetiqo_compare_periods` and personal records. |
| How did today's session go? | Available power, HR and suffer score | Structured workout analysis with coverage warnings; IF/TSS/HR drift are new calculations. |
| Am I ready for a race? | Suffer-score fitness trends and available power | Conditional training-load context, **not** a diagnosis, guaranteed race outcome or exact recovery prescription. |
| What was my best week for power output, and what is my usual week? | Multi-week activity history, watts, kJ, elevation | Calendar-week rollups (`kinetiqo_get_weekly_training_profile`) highlighting peak power weeks and weekly volume/habit profiles. |
| What is my usual recovery time after a 100km+ ride? | Fondo milestones, subsequent ride dates, TSB history | Post-milestone turnaround analysis (`kinetiqo_analyze_recovery_turnaround`) measuring rest days and TSB rebound. |
| Where did I ride and where was I strongest? | GPS, altitude and power where recorded | Map artifact now; route matching/highlight analysis and privacy redaction require new work. |
| What can I share? | Poster, MEGA Stats and Fondo-o-meter pages | Private artifact after extracting reusable renderers; protect home location and attribution. |
| Can you update my Strava activity? | Existing template/Strava client | Read-only preview first, then separately enabled, conflict-checked publish. |

---

## 2. Kinetiqo MCP vs. Strava Official MCP

| Dimension | Strava Official MCP | Kinetiqo Super-Power MCP |
| :--- | :--- | :--- |
| **Data Source** | Remote Strava Cloud REST API | Local Relational DB (PostgreSQL, MySQL, Firebird) |
| **Rate Limits** | Subject to current provider/client terms | Local DB reads spend no Strava requests; sync, writes and map providers have external limits |
| **Stream Resolution** | Depends on provider and granted access | Locally synced timestamps and channels **when recorded**; missing/irregular samples are reported |
| **Query Latency** | Depends on service/network | Depends on backend, data volume and limits; no universal millisecond guarantee |
| **Visual Artifacts** | Depends on connector | Planned private posters, MEGA Stats, Fondo-o-meter and maps after rendering refactor |
| **Physiology & Modeling** | Depends on connector | Existing NP/text summaries, suffer-score CTL/ATL/TSB and FTP/VO₂max estimates; structured IF/TSS and seven-zone model are new work |
| **Milestone Tracking** | Depends on connector | Locally cached verified KOM **counts**, trophy breakdowns and distance milestones; segment details need persistence |
| **Write & Automation** | Depends on granted scopes | Optional, disabled-by-default sync/profile/description tools with server-side safeguards |
| **Data Privacy** | Depends on client and service | Self-hosted storage; tool results may still be sent to a third-party LLM by its client |

---

## 3. The Kinetiqo MCP Tool Taxonomy

To deliver maximum utility without overwhelming LLM context windows, tools are categorized into **six specialized functional groups**:

```
                       ┌──────────────────────────────────────┐
                       │        Kinetiqo MCP Server           │
                       └──────────────────┬───────────────────┘
                                          │
       ┌──────────────┬───────────────────┼───────────────────┬──────────────┐
       ▼              ▼                   ▼                   ▼              ▼
┌─────────────┐┌─────────────┐     ┌─────────────┐     ┌─────────────┐┌─────────────┐
│  Activity   ││  Telemetry  │     │ Physiology  │     │ Visual &    ││ Operations  │
│  Discovery  ││  & Streams  │     │  & Fitness  │     │ Generation  ││   & Sync    │
│  (Group A)  ││  (Group B)  │     │  (Group C)  │     │  (Group E)  ││  (Group F)  │
└─────────────┘└─────────────┘     └─────────────┘     └─────────────┘└─────────────┘
                                          ▲
                                          │
                                   ┌─────────────┐
                                   │ Achievements│
                                   │  & Goals    │
                                   │  (Group D)  │
                                   └─────────────┘
```

---

### Master Tool Catalog

> **Dynamic Tool Registration for Gated Mutations**: Mutating tools (`kinetiqo_update_training_goals` [24], `kinetiqo_trigger_sync` [29], `kinetiqo_update_strava_description` [32], and `kinetiqo_update_athlete_profile` [33]) are **completely omitted from the MCP tool registry (`tools/list`)** when their respective gate flag (`KINETIQO_MCP_ALLOW_PROFILE_WRITE`, `KINETIQO_MCP_ALLOW_SYNC`, `KINETIQO_MCP_ALLOW_STRAVA_WRITE`) is `0` or unset. This keeps the LLM context window lean and eliminates hallucinated tool calls. When enabled (`1`), call-time gate checks are also enforced as defense-in-depth.

> **Unified Initial Analytical Release**: The implementation roadmap groups **Phases 0, 1, and 2** into a cohesive initial read-only analytical release (Tools 1–19, 34–35), delivering full activity discovery, telemetry downsampling, power curves, personal records, and exercise physiology models (CTL/ATL/TSB, FTP history, VO₂max, Power Skills, weekly profiles, recovery turnaround) together via local stdio before progressing to visual rendering and write automations.

The table below provides the authoritative master index of all 35 Kinetiqo MCP tools, their functional grouping, target Python module in `src/kinetiqo/mcp/tools/`, delivery phase, priority, and mutation gating:

| # | Tool Name | Group | Target Module | Phase & Priority | Mutating? (Gate Flag) | Purpose Summary |
| :- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `kinetiqo_search_activities` | A: Discovery | `activities.py` | Phase 1 [P0 / MVP] | No (Read-Only) | Filter & search activities with metric bounds & keyset cursor |
| 2 | `kinetiqo_get_activity_details` | A: Discovery | `activities.py` | Phase 1 [P0 / MVP] | No (Read-Only) | Detailed metadata & coverage flags for single activity |
| 3 | `kinetiqo_get_activity_totals` | A: Discovery | `activities.py` | Phase 1 [P0 / MVP] | No (Read-Only) | Aggregated distance, elevation, moving time, count |
| 4 | `kinetiqo_compare_activities` | A: Discovery | `activities.py` | Phase 1 [P0 / MVP] | No (Read-Only) | Side-by-side comparison of 2–5 activities |
| 5 | `kinetiqo_compare_periods` | A: Discovery | `activities.py` | Phase 1 [P0 / MVP] | No (Read-Only) | Fair comparison of two time periods with elapsed-day alignment |
| 6 | `kinetiqo_find_similar_routes` | A: Discovery | `activities.py` | Phase 2 [P1] | No (Read-Only) | Find past attempts on the same route via GPS signature matching |
| 7 | `kinetiqo_compare_route_attempts` | A: Discovery | `activities.py` | Phase 2 [P1] | No (Read-Only) | Compare matched-section timing on identical/reversed routes |
| 8 | `kinetiqo_get_activity_streams` | B: Telemetry | `telemetry.py` | Phase 2 [P0] | No (Read-Only) | Aligned time-series telemetry (auto/medium/low/high resolution) |
| 9 | `kinetiqo_get_data_coverage` | B: Telemetry | `telemetry.py` | Phase 1 [P0 / MVP] | No (Read-Only) | Per-channel sensor presence, sample count, gaps, timestamps |
| 10 | `kinetiqo_calculate_power_curve` | B: Telemetry | `telemetry.py` | Phase 2 [P0] | No (Read-Only) | Mean Maximal Power (MMP) curve for activity or time window |
| 11 | `kinetiqo_get_personal_records` | B: Telemetry | `telemetry.py` | Phase 2 [P0] | No (Read-Only) | Verified peak power records for validated continuous durations |
| 12 | `kinetiqo_analyze_workout_structure` | B: Telemetry | `telemetry.py` | Phase 2 [P0] | No (Read-Only) | Structured NP, IF, TSS, sustained blocks, and sprint surges |
| 13 | `kinetiqo_analyze_pacing` | B: Telemetry | `telemetry.py` | Phase 2 [P1] | No (Read-Only) | First/second half splits, stops, pacing, and aerobic decoupling |
| 14 | `kinetiqo_get_route_highlights` | B: Telemetry | `telemetry.py` | Phase 2 [P1] | No (Read-Only) | Top climbs, peak wattage segments, with GPS privacy redaction |
| 15 | `kinetiqo_get_fitness_and_freshness` | C: Physiology | `physiology.py` | Phase 2 [P0] | No (Read-Only) | CTL/ATL/TSB trends computed from suffer score history |
| 16 | `kinetiqo_get_ftp_history` | C: Physiology | `physiology.py` | Phase 2 [P0] | No (Read-Only) | Configured FTP and historical 95% of 20-min breakthrough efforts |
| 17 | `kinetiqo_get_vo2max_trend` | C: Physiology | `physiology.py` | Phase 2 [P0] | No (Read-Only) | Storer-Davis (5m MAP) & Coggan FTP estimated VO2max trends |
| 18 | `kinetiqo_get_power_skills` | C: Physiology | `physiology.py` | Phase 2 [P0] | No (Read-Only) | Best rolling power benchmarks (5s, 30s, 1m, 5m, 10m, 20m, 1h) |
| 19 | `kinetiqo_get_training_load_trends` | C: Physiology | `physiology.py` | Phase 4 [P2] | No (Read-Only) | Rolling 7d/28d volume changes, acute-to-chronic workload review |
| 20 | `kinetiqo_get_verified_koms` | D: Achievements | `achievements.py` | Phase 4 [P0 count / P1 details] | No (Read-Only) | Locally verified Strava KOM/QOM crowns and segments |
| 21 | `kinetiqo_get_segment_trophies` | D: Achievements | `achievements.py` | Phase 4 [P0] | No (Read-Only) | Scanned top-10 segment ribbons (ranks 1st–10th) breakdown |
| 22 | `kinetiqo_get_fondo_milestones` | D: Achievements | `achievements.py` | Phase 4 [P0] | No (Read-Only) | Gran Fondos (100k+), centuries, double metrics, marathons |
| 23 | `kinetiqo_get_training_goals` | D: Achievements | `achievements.py` | Phase 4 [P0 read / P1 pacing] | No (Read-Only) | Active distance & elevation targets, current progress, required pace |
| 24 | `kinetiqo_update_training_goals` | D: Achievements | `achievements.py` | Phase 4 [P1] | **Yes** (`KINETIQO_MCP_ALLOW_PROFILE_WRITE=1`) | Update athlete distance and elevation goals for cycling/walking |
| 25 | `kinetiqo_generate_activity_poster` | E: Generation | `generator.py` | Phase 3 [P1] | No (Render only) | Playwright export of activity poster (dual stdio inline + local file) |
| 26 | `kinetiqo_generate_mega_stats_infographic` | E: Generation | `generator.py` | Phase 3 [P1] | No (Render only) | Playwright export of 365-day MEGA Stats calendar heatmap |
| 27 | `kinetiqo_generate_fondo_infographic` | E: Generation | `generator.py` | Phase 3 [P1] | No (Render only) | Playwright export of Fondo-o-meter concentric rings |
| 28 | `kinetiqo_generate_map_artifact` | E: Generation | `generator.py` | Phase 3 [P1] | No (Render only) | Standalone Leaflet map or PNG with privacy start/end clipping |
| 29 | `kinetiqo_trigger_sync` | F: Operations | `operations.py` | Phase 4 [P1] | **Yes** (`KINETIQO_MCP_ALLOW_SYNC=1`) | Trigger fast or full sync with cross-process lease lock |
| 30 | `kinetiqo_get_sync_job_status` | F: Operations | `operations.py` | Phase 4 [P1] | No (Read-Only) | Check status, progress counts, and duration of background sync |
| 31 | `kinetiqo_preview_strava_description` | F: Operations | `operations.py` | Phase 4 [P1] | No (Read-Only) | Preview 150+ placeholder description merge without writing |
| 32 | `kinetiqo_update_strava_description` | F: Operations | `operations.py` | Phase 4 [P1] | **Yes** (`KINETIQO_MCP_ALLOW_STRAVA_WRITE=1`) | Publish approved preview to Strava with collision check |
| 33 | `kinetiqo_update_athlete_profile` | F: Operations | `operations.py` | Phase 4 [P1] | **Yes** (`KINETIQO_MCP_ALLOW_PROFILE_WRITE=1`) | Update weight, FTP, and description templates with audit logging |
| 34 | `kinetiqo_get_weekly_training_profile` | C: Physiology | `physiology.py` | Phase 2 [P0] | No (Read-Only) | Multi-week volume, elevation, power (watts/kJ), best power weeks, and day-of-week habits |
| 35 | `kinetiqo_analyze_recovery_turnaround` | C: Physiology | `physiology.py` | Phase 2 [P1] | No (Read-Only) | Post-long-ride turnaround time, rest days, and TSB form rebound duration |

---

### Group A: Activity Discovery & Query Engine

Tools designed to help the LLM filter, search, compare, and summarize the athlete's activity catalog.

#### 1. `kinetiqo_search_activities` [P0 / MVP]
* **Description**: Search and filter activities using comprehensive telemetry criteria (sport types, date range, date presets, distance, elevation, moving time, watts, heartrate, speed, suffer score, gear, trophies, keywords) with deterministic keyset pagination.
* **Inputs**:
  * `query` (optional string, at most 200 characters): Case-insensitive activity **name** search; descriptions are not stored in the current activities schema.
  * `sport_types` (optional array of strings): e.g. `["Ride", "VirtualRide", "GravelRide", "Run", "Walk"]` or broad categories `["cycling"]`, `["running"]`.
  * `start_date` / `end_date` (optional strings): Flexible date boundary filters supporting ISO timestamps, single years (`"2026"`), year-months (`"2026-08"`), European dates (`"24.10.2026"`), US dates (`"10/24/2026"`), and human date strings.
  * `date_preset` (optional string): Named time presets matching web UI (`"today"`, `"yesterday"`, `"this_week"`, `"last_week"`, `"7_days"`, `"14_days"`, `"this_month"`, `"last_month"`, `"this_year"`, `"last_year"`, `"year"`, `"all_time"`).
  * `min_distance_km` / `max_distance_km` (optional numbers): Distance bounds in km.
  * `min_elevation_m` / `max_elevation_m` (optional numbers): Elevation gain bounds in meters.
  * `min_moving_time_min` / `max_moving_time_min` (optional numbers): Moving duration bounds in minutes.
  * `min_watts` / `max_watts` (optional numbers): Average power bounds in Watts.
  * `min_max_watts` / `max_max_watts` (optional numbers): Maximum power (peak sprint) bounds in Watts.
  * `min_heartrate` / `max_heartrate` (optional numbers): Average heart rate bounds in bpm.
  * `has_heartrate` (optional boolean): Filter for activities with recorded heart rate telemetry.
  * `has_power` (optional boolean): Filter for activities with recorded power meter telemetry.
  * `min_speed_kmh` / `max_speed_kmh` (optional numbers): Average speed bounds in km/h.
  * `min_suffer_score` / `max_suffer_score` (optional integers): Suffer score bounds.
  * `min_pr_count` (optional integer): Minimum number of personal records achieved.
  * `gear_id` (optional string): Athlete equipment / bike ID.
  * `workout_type` (optional integer): Strava workout type enum.
  * `has_trophies` (optional boolean): Filter for activities with verified segment trophies / ribbons.
  * `koms_only` (optional boolean): Filter exclusively for activities with verified 1st place KOM / CR placements.
  * `cursor` (optional string): Opaque base64 cursor from previous response for keyset pagination.
  * `limit` (integer, default `20`, max `100`): Maximum results to return per page.
  * `sort_by` (string, default `"start_date"`): `start_date`, `distance`, `elevation`, `moving_time`, `average_watts`, `max_watts`, `speed`, `heartrate`, `suffer_score`, `calories`.
  * `sort_order` (string, default `"desc"`): `"desc"` or `"asc"`.
* **Output**: Compact JSON envelope with `data.activities` containing items with `activity_id`, `name`, `start_date`, `sport`, `distance_km`, `moving_time_s`, `elevation_gain_m`, `average_speed_kmh`, `average_watts`, `max_watts`, `average_heartrate`, `max_heartrate`, `suffer_score`, `gear_id`, `trophies`, `pr_count`, and `data.pagination` (`next_cursor`, `has_more`, `count`). Supported consistently across PostgreSQL, MySQL, and Firebird.

#### 2. `kinetiqo_get_activity_details` [P0 / MVP]
* **Description**: Retrieve comprehensive metadata for a specific activity by ID.
* **Inputs**:
  * `activity_id` (string or integer, required): Locally synced activity ID.
* **Output**: Locally stored activity columns with explicit units (`distance_km`, `moving_time_s`, `elapsed_time_s`, `elevation_gain_m`, `average_speed_kmh`, `max_speed_kmh`, `average_watts`, `max_watts`, `average_heartrate_bpm`, `max_heartrate_bpm`, `average_cadence_rpm`, `calories_kcal`, `suffer_score`) plus coverage and source. Temperature is available when recorded; description, timezone, gear details and segment-level trophies are **not** in the current local schema. Historical weather, when previously populated during sync, is available only through the dedicated bounded read-only weather tool; never fabricate it or silently fetch a provider.

#### 3. `kinetiqo_get_activity_totals` [P0 / MVP]
* **Description**: Compute aggregated distance, elevation, moving time, and count across a specified scope or sport type.
* **Inputs**:
  * `sport_types` (optional array of strings): Sport types to aggregate.
  * `start_date` / `end_date` (optional ISO strings): Period bounds.
* **Output**: Total distance (`distance_km`), total elevation gain (`elevation_m`), total moving time (`moving_time_hours`), activity count, and averages.

#### 4. `kinetiqo_compare_activities` [P0 / MVP]
* **Description**: Compare 2 to 5 activities side-by-side (e.g. repeated time trials, interval sessions on the same route, or yearly race editions).
* **Inputs**:
  * `activity_ids` (array of strings or integers, required): IDs of 2 to 5 activities to compare.
* **Output**: Side-by-side measured duration, distance, speed, power, HR and elevation with per-metric availability. NP requires a qualifying power stream; HR drift and efficiency factor require separate, documented stream methods and must be null until implemented.

#### 5. `kinetiqo_compare_periods` [P0 / MVP]
* **Description**: Compare fair training periods (e.g. this month vs last month, this season vs last season) with equal elapsed-day alignment and local timezone semantics.
* **Inputs**:
  * `period_a` (object, required): `{ "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }`.
  * `period_b` (object, required): `{ "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }`.
  * `sport_types` (optional array of strings): Sport types to filter.
  * `align` (string, default `"elapsed_days"`): `"elapsed_days"` (compares identical first N calendar days of each period) or `"full_period"`.
* **Output**: Activity count, total distance (`distance_km`), moving time (`moving_time_s`), elevation gain (`elevation_m`), active-day averages, absolute differences, and percentage deltas. Flags partial periods and avoids division by zero.

#### 6. `kinetiqo_find_similar_routes` [P1 / Phase 2]
* **Description**: Identify past activity tracks matching a source activity's GPS path using spatial bounding-box indexing and normalized track correlation.
* **Inputs**:
  * `activity_id` (string, required): Source activity ID.
  * `sport_types` (optional array of strings): Sport filters.
  * `max_candidates` (integer, default `10`, max `25`): Candidate limit.
* **Output**: Matched candidate activities with similarity score (0.0 to 1.0), direction (`same`, `reverse`, `partial`), matched distance percentage, and overlap confidence.

#### 7. `kinetiqo_compare_route_attempts` [P1 / Phase 2]
* **Description**: Compare performance on identical or reversed route sections across different sessions, isolating the common GPS segment.
* **Inputs**:
  * `source_activity_id` (string, required): Baseline activity ID.
  * `target_activity_id` (string, required): Attempt activity ID to compare.
* **Output**: Matched section elapsed time, moving time, average power, average heart rate, speed deltas, and segment elevation gain.

---

### Group B: High-Resolution Telemetry & Power Analytics

Tools that leverage previously synced local telemetry without consuming Strava API requests. Sampling may be irregular, incomplete or absent.

#### 8. `kinetiqo_get_activity_streams` [P0 / Phase 2]
* **Description**: Retrieve raw or downsampled telemetry time-series for an activity.
* **Inputs**:
  * `activity_id` (string, required): Activity ID.
  * `stream_types` (array, default `["time", "watts", "heartrate", "cadence", "altitude"]`): Supported `time`, `watts`, `heartrate`, `cadence`, `altitude`, `speed`, `distance`, `latlng`, `temp`, `grade_smooth`, `moving`. `time` maps to stored timestamps; verify Strava-to-DB speed units before exposing `velocity_smooth` as an alias.
  * `resolution` (default `"auto"`): `"auto"` (up to 500 representative samples), `"medium"` (10-second timestamp buckets), `"low"` (60-second buckets), `"high"` (explicit raw request, hard-capped at 20,000 rows and a server-side query/time budget once implemented).
* **Output**: Timestamp-aligned samples and per-channel count, missing percentage, min/max/mean/stddev, original and returned point counts, units and downsampling method. Preserve endpoints/extrema; never treat row index as seconds. Add a bounded multi-channel repository method in all backends.

#### 9. `kinetiqo_get_data_coverage` [P0 / MVP Phase 1]
* **Description**: Fast pre-flight check returning sensor availability, recorded channels, row counts, timestamp ranges, and sampling gaps without loading full telemetry.
* **Inputs**:
  * `activity_id` (string, required): Activity ID.
* **Output**: Per-channel coverage records for `watts`, `heartrate`, `cadence`, `altitude`, `latlng`, `speed`, and `temp` with status (`present`, `absent`, `unknown`), non-null row count, first/last timestamp, detected gaps (>2s), and qualifying status.

#### 10. `kinetiqo_calculate_power_curve` [P0 / Phase 2]
* **Description**: Compute the Mean Maximal Power (MMP) curve for a single activity or the athlete's best power curve across a specified timeframe.
* **Inputs**:
  * `activity_id` (optional string): Specific activity ID.
  * `days` (optional integer): If `activity_id` is omitted, calculates peak powers across all activities in the last N days (e.g. `30`, `90`, `365`).
  * `durations` (optional array of integers in seconds, default `[5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600]`): Window durations.
* **Output**: Best average watts per duration, source activity/date, qualifying sample coverage, and W/kg only if weight > 0. Verify continuous elapsed-time windows before treating existing row-based rolling power as a precise time duration; no result for an insufficient or gapped window.

#### 11. `kinetiqo_get_personal_records` [P0 / Phase 2]
* **Description**: Retrieve verified all-time and period personal power records for benchmark durations, enforcing continuous-window timestamp rules.
* **Inputs**:
  * `durations` (optional array of integers, default `[5, 60, 300, 1200, 3600]`): Durations in seconds.
  * `sport_types` (optional array of strings): Sport types (e.g. `["Ride", "VirtualRide"]`).
  * `start_date` / `end_date` (optional ISO strings): Period filter.
  * `activity_id` (optional string): If specified, checks whether this activity achieved a personal record.
* **Output**: Peak average watts per duration, date achieved, source activity ID, qualifying sample coverage, and W/kg (using profile weight at calculation time).

#### 12. `kinetiqo_analyze_workout_structure` [P0 / Phase 2]
* **Description**: Structured calculation service reusing Kinetiqo's NP and interval logic where valid; `generate_workout_summary()` currently returns prose, not structured IF/TSS/blocks. Do not use its implicit 250 W FTP fallback for MCP metrics.
* **Inputs**:
  * `activity_id` (string, required): Activity ID.
  * `ftp` (optional number): Athlete FTP override (defaults to DB profile FTP).
* **Output**:
  * Classification (e.g. `"Endurance with Threshold blocks"`).
  * Normalized Power (`normalized_power_w`) & % FTP.
  * Maximum Power (`max_watts`), time from start to maximum power (`time_to_max_watts_s`, `time_to_max_watts_min`) for warmup and pacing discovery.
  * Intensity Factor (`intensity_factor`) and Training Stress Score (`training_stress_score`).
  * Sustained Blocks: List of blocks (duration in min, average watts, % FTP, start time).
  * Short Surges: High-intensity efforts (1–3 min @ >105% FTP).
  * Sprint Peaks: Verified ≥1000 W peaks when power coverage supports them; deterministic numbers, with optional presentation labels separate from measurement.
* **Rules**: `IF = NP / FTP`; `TSS = duration_seconds × NP × IF / (FTP × 3600) × 100`. Use continuous moving/recorded time under a documented policy; if FTP is missing or data are insufficient, return null IF/TSS/zones and explain why. Intervals include start/end timestamps and detection thresholds; no medical recommendation.

#### 13. `kinetiqo_analyze_pacing` [P1 / Phase 2]
* **Description**: Detailed pacing and execution breakdown for an activity, computing split halves, stopped time, terrain impacts, and aerobic decoupling.
* **Inputs**:
  * `activity_id` (string, required): Activity ID.
  * `split_basis` (string, default `"moving_time"`): `"moving_time"` or `"distance"`.
  * `num_splits` (integer, default `2`, max `10`): Number of even splits to analyze.
* **Output**: Per-split metrics (elapsed seconds, moving seconds, distance, elevation, average watts, average heart rate), split 1 vs split 2 comparison, and Aerobic Decoupling (`decoupling_pct` via `(P1/HR1) / (P2/HR2) - 1`) requiring ≥80% paired HR/power coverage.

#### 14. `kinetiqo_get_route_highlights` [P1 / Phase 2]
* **Description**: Extract standout climbs, summit points, and maximum sustained efforts, with mandatory privacy start/end location clipping.
* **Inputs**:
  * `activity_id` (string, required): Activity ID.
  * `hide_start_end_km` (number, default `0.0`): Distance in km to redact from both ends before highlight detection.
* **Output**: List of identified climbs (start/end timestamp, elevation gain in m, average gradient %, distance in km) and peak power segments, with GPS coordinates only when within unredacted zones.

---

### Group C: Endurance Physiology & Training Load

Tools implementing exercise physiology models (Coggan, Storer-Davis, impulse-response).

#### 15. `kinetiqo_get_fitness_and_freshness` [P0 / Phase 2]
* **Description**: Report current suffer-score-derived CTL/ATL/TSB trends. TSS is a **different scale** and must never silently be mixed with suffer scores.
* **Inputs**:
  * `period_days` (integer or string, default `"90"`): Number of days or `"all"`.
* **Output**:
  * Current status: `fitness` (CTL), `fatigue` (ATL), `form` (TSB).
  * Descriptive workload context and missing-data caveats, not a diagnosis of overtraining or injury.
  * Time-series points for plotting CTL/ATL/TSB trends.
  * Calculation method, lookback/warm-up coverage and last computation date. Calculate sufficient prior history and zero-activity days through today, then trim displayed points to the requested period; do not equate a truncated history with the full-history current CTL.

#### 16. `kinetiqo_get_ftp_history` [P0 / Phase 2]
* **Description**: Retrieve the athlete's Functional Threshold Power (FTP) history based on 95% of 20-minute best rolling efforts.
* **Inputs**:
  * `lookback_months` (integer, default `12`): Lookback period in months.
* **Output**:
  * Configured profile FTP.
  * Chronological list of 20-minute breakthrough efforts and estimated FTP values.
  * W/kg only if athlete profile weight is configured; separate configured FTP from estimated historical 95%-of-20-min values.

#### 17. `kinetiqo_get_vo2max_trend` [P0 / Phase 2]
* **Description**: Retrieve VO₂max progression estimated via Storer-Davis (5-min MAP proxy) and Coggan FTP methods, smoothed via asymmetric EWMA (Firstbeat/Garmin style).
* **Inputs**:
  * `lookback_months` (integer, default `12`): Lookback period in months.
* **Output**: Estimated VO₂max (ml/kg/min), qualifying effort count, method/weight assumptions and smoothed points. Existing classification thresholds are approximate male age-30–39 bands, not personalized age/sex classifications; omit or explicitly qualify the category until improved.

#### 18. `kinetiqo_get_power_skills` [P0 / Phase 2]
* **Description**: Report power benchmarks at validated durations; the current UI advertises seven points. Ten-point expansion and rider phenotype classification require new calculation and tested thresholds.
* **Inputs**:
  * `timeframe_days` (integer, default `365`): Time window.
* **Output**: Implemented duration/peak watts, source ride and optional W/kg. Add the proposed 10s, 2m and 30m durations before claiming a ten-point profile; omit phenotype until scientifically documented.

#### 19. `kinetiqo_get_training_load_trends` [P2 / Phase 4]
* **Description**: Longitudinal multi-week training load volume and intensity progression (acute:chronic workload review), surfacing abrupt volume swings.
* **Inputs**:
  * `weeks` (integer, default `12`, max `52`): Number of historical weeks.
  * `sport_types` (optional array of strings): Sport types to include.
* **Output**: Weekly aggregates (total distance, total moving time, total elevation, suffer score sum), rolling 4-week moving average, week-over-week % changes, and missing-data caveats.

#### 34. `kinetiqo_get_weekly_training_profile` [P0 / Phase 2]
* **Description**: Compute multi-week training load profiles grouped by ISO calendar weeks, surfacing weekly energy/work (kJ), average power, weighted average power (NP), distance, elevation gain, peak power weeks, and day-of-week riding habits.
* **Inputs**:
  * `year` (optional integer): Calendar year to analyze (e.g. `2026`). If provided, analyzes all ISO weeks of that year.
  * `weeks` (optional integer, default `12`, max `52`): Rolling weeks lookback if `year` is omitted.
  * `sport_types` (optional array of strings, default `["Ride", "VirtualRide", "GravelRide"]`): Sport filter.
* **Output**:
  * `weekly_history`: Chronological list of weekly summaries: `iso_week`, `start_date`, `end_date`, `activity_count`, `distance_km`, `elevation_m`, `moving_time_hours`, `kilojoules`, `average_watts`, `weighted_average_watts` (when power recorded).
  * `peak_weeks`: Best week of the period by:
    - `power_output`: Highest weekly average watts and total kilojoules (kJ).
    - `distance`: Highest weekly distance (km).
    - `elevation`: Highest weekly elevation gain (m).
  * `typical_week_profile`:
    - `median_weekly_distance_km` and `mean_weekly_distance_km`.
    - `median_weekly_elevation_m` and `mean_weekly_elevation_m`.
    - `typical_ride_count`: Average active days and rides per week.
    - `day_of_week_distribution`: Breakdown of rides across days of the week (Monday through Sunday) showing preferred training days.

#### 35. `kinetiqo_analyze_recovery_turnaround` [P1 / Phase 2]
* **Description**: Analyze athlete recovery turnaround time and training fatigue dissipation following major endurance milestones (e.g. 100km+ rides, marathons, or high suffer-score sessions).
* **Inputs**:
  * `min_distance_km` (number, default `100.0`): Minimum activity distance threshold to qualify as an endurance milestone.
  * `sport_group` (string, default `"cycling"`): Sport group (`"cycling"`, `"running"`, `"walking"`).
  * `lookback_days` (integer, default `365`): Historical evaluation window in days.
* **Output**:
  * `qualifying_milestone_count`: Number of evaluated 100km+ activities.
  * `recovery_turnaround`:
    - `median_rest_days_until_next_ride`: Typical days elapsed before the next activity.
    - `median_days_until_hard_ride`: Typical days elapsed before the next high-intensity or threshold workout.
    - `tsb_form_rebound_days`: Average days for Training Stress Balance (TSB) to recover from post-ride fatigue trough back to neutral (`TSB >= 0`) or pre-ride baseline.
  * `milestone_breakdown`: List of evaluated milestone rides with their date, distance, suffer score, subsequent rest days, and TSB recovery duration.
  * `recovery_summary`: Descriptive summary of typical recovery speed, fatigue impact, and evidence-based turnaround recommendations.

---

### Group D: Achievements, Milestones & Goals

Tools for tracking verified crowns, ribbons, Gran Fondos, and training targets.

#### 20. `kinetiqo_get_verified_koms` [P0 count / P1 details]
* **Description**: Report locally cached verified KOM/QOM **counts per activity** with cache freshness/availability. The current `verified_koms.json` contains counts; segment details become available once Phase 4 segment persistence is deployed.
* **Output**: Count, matching activity IDs and verification status; add segment-level persistence/backfill before promising segment details. Missing cache does not mean zero crowns.

#### 21. `kinetiqo_get_segment_trophies` [P0 / Phase 4]
* **Description**: Retrieve top-10 segment finishes (ranks 1st through 10th ribbons) extracted from detailed segment efforts.
* **Inputs**:
  * `year` (optional integer): Filter by year.
  * `activity_id` (optional string): Filter for a single activity.
* **Output**: Counts by rank 1–10 and scanned/unscanned coverage; do not conflate ribbons and verified KOMs. An unscanned ride is not a zero-trophy ride.

#### 22. `kinetiqo_get_fondo_milestones` [P0 / Phase 4]
* **Description**: Query endurance distance milestone completions: Gran Fondos (≥100km cycling), Centuries (≥160km), Double Metrics (≥200km), Marathons (≥42.2km running), 50k Ultra/Skiing, and 10k Swimming.
* **Inputs**:
  * `year` (optional integer or `"all"`, default `"all"`): Filter by year.
  * `sport_group` (optional string, default `"cycling"`): `"cycling"`, `"running"`, `"skiing"`, `"swimming"`.
* **Output**: Total milestone count, longest distance activity, and list of milestone activities sorted by distance.

#### 23. `kinetiqo_get_training_goals` [P0 read / P1 pacing]
* **Description**: Retrieve athlete's weekly, monthly, and yearly distance and elevation goals along with current progress and pacing.
* **Output**: Target, actual, remaining, percentage, elapsed fraction and required remaining weekly pace for configured cycling/walking goal types. Current goal mapping does not include running; extend schema, mapping, UI and tests before claiming it.

#### 24. `kinetiqo_update_training_goals` [P1 / Phase 4 — Mutating: `KINETIQO_MCP_ALLOW_PROFILE_WRITE`]
* **Description**: Update weekly, monthly, or yearly distance and elevation goals for configured sports (Cycling or Walking).
* **Inputs**:
  * `sport_group` (string, required): `"cycling"` or `"walking"`.
  * `weekly_distance_km` (optional number): Weekly distance target in km.
  * `monthly_distance_km` (optional number): Monthly distance target in km.
  * `yearly_distance_km` (optional number): Yearly distance target in km.
  * `weekly_elevation_m` (optional number): Weekly elevation gain target in metres.
  * `monthly_elevation_m` (optional number): Monthly elevation gain target in metres.
  * `yearly_elevation_m` (optional number): Yearly elevation gain target in metres.
* **Output**: Updated goal summary, effective timestamp, and sanitized audit identifier. Requires `KINETIQO_MCP_ALLOW_PROFILE_WRITE=1`.

---

### Group E: Creative Visual Generation (Posters, Maps, Infographics)

Visual exports leverage headless Playwright Chromium rendering. To guarantee full offline functionality under local stdio when the Flask web application is not running, rendering services in `src/kinetiqo/web/renderers/` synthesize standalone HTML in-process using Jinja2 templates, injecting activity data, SVG assets, and self-hosted CSS directly. Playwright loads the document via `page.set_content(html, wait_until="networkidle")`, eliminating any dependence on an active Flask HTTP server, local port binding, or browser session cookies. Map tiles use cached/direct provider URLs with attribution, or photo background mode.

#### Dual Delivery Contract (Local Desktop Stdio vs Remote HTTP)

* **Local Desktop (stdio)**: When running under local stdio (e.g. Claude Desktop, Cursor, Antigravity IDE), the server executes the render, writes the file to the user's local application data directory (e.g. `%LOCALAPPDATA%\kinetiqo\artifacts\` on Windows or `~/.local/share/kinetiqo/artifacts/` on Linux), and returns **both**:
  1. A clickable local file URI (`file:///...`) and artifact metadata in the JSON response envelope.
  2. The standard MCP **`ImageContent` object** containing the base64-encoded WebP image and MIME type (`image/webp`).
  *This dual delivery ensures that AI chat clients can render the image directly inside the interactive chat window while simultaneously giving the user the exact filesystem path to open or share.*
* **Remote Containerized HTTP**: When running over HTTP, large base64 payloads are omitted by default to conserve bandwidth. The server returns `{ "artifact_id": "...", "download_url": "https://.../api/mcp/artifacts/{artifact_id}", "mime_type": "image/webp", "expires_at": "..." }`, where the download URL requires Bearer token authentication.

#### 25. `kinetiqo_generate_activity_poster` [P1 / Phase 3]
* **Description**: Trigger Kinetiqo's headless Playwright Chromium rendering engine to export a pixel-perfect, high-resolution activity poster.
* **Inputs**:
  * `activity_id` (string, required): Activity to render.
  * `ratio` (string, default `"4/3"`): Aspect ratio: `"4/3"`, `"16/9"`, or `"1/1"`.
  * `poster_size` (integer, default `1280`): Width in pixels (800 to 2048).
  * `background_mode` (string, default `"map"`): `"map"` (Leaflet canvas with selected provider) or `"photo"` (athlete custom photo).
  * `map_provider` (string, default `"osm"`): One of Kinetiqo's 16 basemap styles (`osm`, `mapy_outdoor`, `thunderforest_outdoors`, `maptiler_topo`, `esri_satellite`, `carto_dark`, etc.).
  * `font_family` (string, default `"Inter"`): Custom font (`Inter`, `Italiana`, `Outfit`, `Montserrat`, etc.).
  * `route_color` (string, default `"#ef4444"`): Hex color for GPS polyline.
  * `visible_elements` (optional object): Toggle visibility of `title`, `date`, `stats`, `elevation_profile`, `map_scale`.
* **Output**: Artifact metadata with private `artifact_id`, dimensions, expiry, local `file_uri`, plus inline MCP `ImageContent` in stdio mode (or authenticated `download_url` in HTTP mode).

#### 26. `kinetiqo_generate_mega_stats_infographic` [P1 / Phase 3]
* **Description**: Export a high-resolution Mega Stats infographic featuring a 365-day calendar heatmap, monthly distance/elevation progression, and total metrics.
* **Inputs**:
  * `year` (integer or string, default `"current"`): Specific year or `"all"` only if verified by the reused stats renderer; also specify period (`year`, half-year, quarter or supported custom interval).
  * `sport_group` (string, default `"cycling"`): Sport filter.
  * `format` (string, default `"png"`): `"png"` or `"pdf"`.
  * `font_family` (string, default `"Inter"`): Typography font.
  * `column_width` (integer, default `20`): Stats column width percentage (20 to 50).
* **Output**: Artifact metadata with private `artifact_id`, local `file_uri`, plus inline MCP `ImageContent` in stdio mode (or authenticated `download_url` in HTTP mode).

#### 27. `kinetiqo_generate_fondo_infographic` [P1 / Phase 3]
* **Description**: Export the Fondo-o-meter endurance showcase infographic featuring up to 8 harmonic concentric rings, Gran Fondo emblem, PRs, and KOMs.
* **Inputs**:
  * `year` (integer or string, default `"all"`): Year or `"all"`.
  * `arc_color` (string, default `"#f97316"`): Ring arc highlight color.
  * `format` (string, default `"png"`): `"png"` or `"pdf"`.
  * `arc_width` (integer, default `100`): Ring thickness percentage (80 to 160).
* **Output**: Artifact metadata with private `artifact_id`, local `file_uri`, plus inline MCP `ImageContent` in stdio mode (or authenticated `download_url` in HTTP mode).

#### 28. `kinetiqo_generate_map_artifact` [P1 / Phase 3]
* **Description**: Generate a standalone Leaflet HTML map file or static image showing one or multiple activity tracks with customizable GPS simplification.
* **Inputs**:
  * `activity_ids` (array of strings, required): IDs to display on the map (max 10).
  * `basemap` (string, default `"osm"`): Selected tile provider.
  * `gps_simplification` (integer, default `5`): Level `0` (raw) to `10` (maximum distance-based decimation); consult `gps_simplify.py` for exact thresholds.
  * `hide_start_end_km` (number, default `0.0`): Remove both ends of each track **before** serialization, rendering or cache creation.
* **Output**: Private HTML/PNG artifact with attribution and expiry. Third-party basemaps still require available keys, network access and provider-compliant attribution.

---

### Group F: Operations, Profile & Automations

Tools for managing sync, athlete profile, and automating Strava descriptions.

#### 29. `kinetiqo_trigger_sync` [P1 / Phase 4 — Mutating: `KINETIQO_MCP_ALLOW_SYNC`]
* **Description**: Initiate an asynchronous background synchronization run (fast sync or full historical sync) backed by cross-process lease locking in the database.
* **Inputs**:
  * `sync_type` (string, default `"fast"`): `"fast"` or `"full"`.
  * `lookback_period` (optional string): e.g. `"30d"`, `"1y"`, or `"all"` (allowed only for full sync).
  * `acknowledge_deletion` (optional boolean, default `false`): Required `true` when requesting full sync to confirm deletion reconciliation.
* **Output**: Non-blocking `job_id` and initial status (`queued` or `running`). Mutating tool gated by `KINETIQO_MCP_ALLOW_SYNC=1`.

#### 30. `kinetiqo_get_sync_job_status` [P1 / Phase 4]
* **Description**: Query the execution progress, current phase, activity counts, duration, and error status of a previously triggered synchronization job.
* **Inputs**:
  * `job_id` (string, required): Active or completed sync job ID.
* **Output**: Current job state (`queued`, `running`, `completed`, `failed`, `cancelled`), timestamps (`started_at`, `completed_at`), `synced_activities`, `total_activities`, duration, and sanitized error messages.

#### 31. `kinetiqo_preview_strava_description` [P1 / Phase 4]
* **Description**: Run Kinetiqo's 150+ placeholder description engine on an activity to preview the formatted text before publishing to Strava.
* **Inputs**:
  * `activity_id` (string, required): Activity ID.
  * `custom_template` (optional string): Kinetiqo `{{placeholder}}` syntax, validated against the existing engine; arbitrary Jinja2 evaluation is forbidden. If omitted, use the effective configured template, following existing environment/profile precedence.
* **Output**: Exact old/proposed description, changed block, unresolved placeholders, expiry and a one-time `preview_id` tied to activity, caller, and current-description fingerprint. A preview may require a Strava *read*; it never writes.

#### 32. `kinetiqo_update_strava_description` [P1 / Phase 4 — Mutating: `KINETIQO_MCP_ALLOW_STRAVA_WRITE`]
* **Description**: Publish only a previously approved, server-validated preview; requires explicit enablement and `activity:write` scope.
* **Inputs**:
  * `activity_id` (string, required): Activity ID.
  * `preview_id` (string, required): Short-lived, single-use server-side preview identifier; never accept unrestricted full-description replacement in the initial release.
* **Output**: `updated`, `unchanged` or a conflict/error. Re-read the remote description and compare its fingerprint, preserve user text via existing merge logic, audit the result and reject stale previews. Client approval alone does not replace server enforcement.

#### 33. `kinetiqo_update_athlete_profile` [P1 / Phase 4 — Mutating: `KINETIQO_MCP_ALLOW_PROFILE_WRITE`]
* **Description**: Optional, separately enabled update of allowlisted athlete settings (weight, FTP, description templates).
* **Inputs**:
  * `weight` (optional number): Body weight in kg.
  * `ftp` (optional number): Functional Threshold Power in Watts (0 < FTP ≤ 1000).
  * `update_strava_templates` (optional object): Validated existing six template buckets including swimming.
* **Output**: Sanitized profile with `refresh_token` and all secrets removed, audit ID, effective value/source and a warning when an environment override will replace a DB setting. Explicit field-level validation is mandatory.

---

## 4. MCP Resources & Prompt Templates

In addition to tools, the MCP protocol provides **Resources** (passive URIs an LLM can inspect) and **Prompts** (pre-packaged workflow templates).

### MCP Resources

Clients can read static and dynamic training context without executing tool calls:

| Resource URI | Description |
| :--- | :--- |
| `kinetiqo://athlete/profile` | Sanitized current profile, excluding refresh token and secrets; W/kg only if weight is valid |
| `kinetiqo://athlete/goals` | Active weekly/monthly/yearly distance and elevation targets and progress |
| `kinetiqo://activities/latest` | Most recent synced activity summary and stream availability (not unbounded telemetry) |
| `kinetiqo://activities/{id}` | Activity metadata and coverage; use the bounded stream tool for samples |
| `kinetiqo://analytics/fitness-freshness` | Current suffer-score-derived CTL/ATL/TSB and coverage warnings |
| `kinetiqo://analytics/power-skills` | Implemented power-duration benchmarks with contributing rides |
| `kinetiqo://analytics/koms` | Verified KOM counts and cache status, not invented segment details |

---

### MCP Prompts (Pre-Packaged Coaching Workflows)

MCP prompts supply instructions to LLM clients; they do **not** execute tools automatically or guarantee the client will call them. Every prompt must ask the client to disclose missing data and avoid presenting estimates as measurements. See **Example Prompts** near the end for end-user wording and required tool chains.

#### 1. `post_ride_debrief`
* **Arguments**: `activity_id` (optional, defaults to latest activity)
* **Behavior**:
  1. Request `kinetiqo_get_activity_details`, `kinetiqo_get_data_coverage` and (when supported) `kinetiqo_analyze_workout_structure`.
  2. Request `kinetiqo_get_fitness_and_freshness` for contextual workload trends, not an exact impact prediction.
  3. LLM synthesizes an intelligent debrief:
     * Measured ride breakdown; include pacing/decoupling only if the corresponding structured analysis exists and data suffice.
     * Available power zones and standout surges, with FTP source and coverage stated.
     * Recent workload trend and uncertainty; no exact recovery-hour or medical prediction.
     * Offers to generate a celebration poster or update Strava description.

#### 2. `race_readiness_assessment`
* **Arguments**: `target_date` (ISO date string), `target_event_type` (e.g. `"Gran Fondo 150km"`, `"Criterium"`, `"40km Time Trial"`)
* **Behavior**:
  1. Inspect current suffer-score-derived form, coverage and prior fitness history.
  2. Request qualifying peak powers (5m/20m/60m where available); a 3h+ pacing claim requires separately implemented long-duration analysis.
  3. Offer cautious training considerations, not a personalized medically validated taper or watts prescription when FTP/coverage is unavailable.

#### 3. `poster_creative_director`
* **Arguments**: `activity_id` (optional), `style_theme` (`"dark"`, `"vibrant"`, `"minimalist"`, `"satellite"`)
* **Behavior**:
  1. Selects the ideal basemap provider (e.g. `carto_dark` for dark theme, `thunderforest_outdoors` for mountain passes, `esri_satellite` for coastal rides).
  2. Chooses harmonious route colors and font pairings.
  3. Request the poster tool only if rendering is enabled, verify privacy/attribution, and present the private artifact reference (or inline image if supported).

---

## 5. System Architecture & Technical Design

### Directory Structure within Kinetiqo

The MCP server will be integrated directly into the existing `src/kinetiqo` package to share repositories, config, database drivers, and export routines:

```
src/kinetiqo/
├── cli.py                     # Adds `kinetiqo mcp` Click subcommand
├── config.py                  # Inherits existing DB and Strava configs
├── db/                        # Parameterized SQL repositories (PostgreSQL, MySQL, Firebird)
├── koms.py                    # Verified KOM cache
├── workout_summary.py         # NP, power zones, surge detection
├── web/
│   ├── fitness.py             # CTL/ATL/TSB engine
│   ├── vo2max.py              # Storer-Davis & Coggan VO2max
│   ├── fondo_o_meter.py       # Endurance rings calculation
│   ├── app.py                 # Existing browser-session-dependent export endpoints
│   └── renderers/             # NEW reusable poster, stats and fondo services
│
└── mcp/                       # << NEW MCP PACKAGE >>
    ├── __init__.py            # Package entry point
    ├── server.py              # FastMCP instance & version-verified transport
    ├── contracts.py           # Response envelopes, units, validation and limits
    ├── artifacts.py           # Private artifact registry, retrieval and expiry
    ├── jobs.py                # Cross-process sync coordination/status
    ├── tools/
    │   ├── __init__.py
    │   ├── activities.py      # Search, details, totals, compare
    │   ├── telemetry.py       # Streams, power curves, workout structure
    │   ├── physiology.py      # Fitness/Freshness, FTP, VO2max, Power Skills
    │   ├── achievements.py    # KOMs, trophies, Fondos, goals
    │   ├── generator.py       # Posters, Mega Stats, Fondo-o-meter, maps
    │   └── operations.py      # Sync, profile, Strava descriptions
    ├── resources.py           # MCP Resource handlers
    ├── prompts.py             # MCP Prompt workflows
    └── utils.py               # Timestamp-aware downsampling and formatting
```

---

### Core Technology Stack

* **MCP Framework**: Official Python `mcp` SDK; first pin a Python-3.14-compatible version, then verify the installed `FastMCP` constructor, tool/resource/prompt registration and transport APIs. Pseudocode is not a substitute for a runnable SDK smoke test.
* **Transports**:
  1. **Standard I/O (`stdio`)**: The default transport for local LLM clients (Claude Desktop, Cursor, Antigravity IDE, Claude Code).
  2. **HTTP (later phase)**: Use only a transport supported by the *pinned* SDK and target clients; do not assume legacy SSE and streamable HTTP are interchangeable. Bind to `127.0.0.1` by default, use authentication/TLS for non-loopback exposure.
* **Database Access**: Use repository factory at request/tool boundary and close every connection; never retain one mutable DB connection shared between concurrent calls. Ensure schema was initialized by the application's normal setup, not by a read-only MCP request.
* **Visual Rendering**: Refactor existing session-dependent Flask Playwright exports into reusable core renderers (`src/kinetiqo/web/renderers/`) invoked from both web and MCP. Headless Playwright uses in-process HTML synthesis (`page.set_content(html, wait_until="networkidle")`) with Jinja2 templates, injecting data, SVG assets, and self-hosted CSS directly. This eliminates any reliance on a running Flask web server, local HTTP port, or copying web cookies.

### Common response, validation and data provenance contract

Every tool returns compact JSON with `schema_version` (`1`), `generated_at` (UTC ISO 8601), `source` (`local_db`, `local_cache`, `calculated`, `strava_api` or `rendered`), `data_status` (`complete`, `partial`, `stale`, `unavailable`), `warnings` (list of strings) and a tool-specific `data` object. Record IDs are JSON strings. Use explicit units (`distance_km`, `elevation_m`, `moving_time_s`, `power_w`, `weight_kg`, `vo2max_ml_kg_min`). Put `method`, `inputs`, `assumptions`, qualifying sample count and source activity IDs on calculated/estimated results. Missing values are JSON `null`, **never zero**. Distinguish no matches, no sensor, stale cache and upstream failure.

#### Concrete Data Envelope & Payload Schemas (Pydantic / TypedDict)

```python
from typing import Generic, TypeVar, Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

T = TypeVar("T")

class MCPResponseEnvelope(BaseModel, Generic[T]):
    schema_version: int = Field(default=1, description="Protocol envelope schema version")
    generated_at: str = Field(description="UTC ISO-8601 timestamp")
    source: Literal["local_db", "local_cache", "calculated", "strava_api", "rendered"]
    data_status: Literal["complete", "partial", "stale", "unavailable"]
    warnings: List[str] = Field(default_factory=list)
    data: T

class PaginationMetadata(BaseModel):
    next_cursor: Optional[str] = Field(None, description="Opaque URL-safe base64 string for next page")
    has_more: bool = Field(description="True if more records exist beyond current page")
    total_matched: Optional[int] = Field(None, description="Total matching records count if requested")

class ActivitySummaryItem(BaseModel):
    activity_id: str
    name: str
    start_date: str
    sport: str
    distance_km: float
    moving_time_s: int
    elevation_gain_m: float
    average_watts: Optional[float] = None
    suffer_score: Optional[int] = None

class ActivitySearchData(BaseModel):
    activities: List[ActivitySummaryItem]
    pagination: PaginationMetadata
```

#### Keyset Pagination & Opaque Cursor Specification

To ensure stable, zero-offset pagination across growing activity catalogs, `kinetiqo_search_activities` uses **keyset pagination** on `(sort_metric, start_date DESC, activity_id DESC)`:

* **Cursor Encoding**: The `next_cursor` is a URL-safe Base64-encoded JSON string:
  ```json
  {"v": 1, "sort_val": 124.5, "start_date": "2026-05-12T08:30:00Z", "id": 1184729104}
  ```
* **Database Implementation Pattern**:
  * **PostgreSQL & MySQL** (Row-value / tuple comparison):
    ```sql
    WHERE athlete_id = %s
      AND (start_date, activity_id) < (%s, %s)
    ORDER BY start_date DESC, activity_id DESC
    LIMIT %s;
    ```
  * **Firebird** (Quoted identifiers & expanded disjunction):
    ```sql
    WHERE "athlete_id" = ?
      AND (("start_date" < ?) OR ("start_date" = ? AND "activity_id" < ?))
    ORDER BY "start_date" DESC, "activity_id" DESC
    FETCH FIRST ? ROWS ONLY;
    ```

Errors use stable codes `INVALID_ARGUMENT`, `NOT_FOUND`, `DATA_UNAVAILABLE`, `NOT_CONFIGURED`, `PERMISSION_DENIED`, `CONFLICT`, `RATE_LIMITED`, `RESOURCE_LIMIT`, `UPSTREAM_ERROR`, `INTERNAL_ERROR`. Do not return an empty successful result on upstream failure or reveal tokens/passwords/internal paths in errors. Timeout and cancellation must release cursors, browser contexts and job locks.

The analytical tools support the single configured athlete; callers cannot choose another `athlete_id`. Accept calendar dates as `YYYY-MM-DD`: inclusive start and inclusive end translated to a half-open SQL timestamp interval using the resolved `ATHLETE_TIMEZONE`. Timezone resolution follows a strict 3-tier hierarchy: (1) explicit `ATHLETE_TIMEZONE` environment variable (e.g. `Europe/Prague`, `America/New_York`), (2) athlete timezone stored in the database `profile` table (synced from Strava athlete profile), and (3) fallback to `'UTC'` with a logged operational warning advising the athlete to configure their IANA timezone for accurate calendar boundary alignment. Reject reversed ranges and invalid dates. Sport groups come from a single documented mapping, with indoor and assisted cycling distinguished when comparisons require it. Sort columns are allowlisted and ties resolve by `start_date DESC, activity_id DESC`. Reject negative bounds, non-finite floats, duplicate IDs, unknown streams and unsupported basemaps rather than silently coercing them.

| Limit | Default | Hard maximum |
| :--- | ---: | ---: |
| Activity results per call | 20 | 100 |
| Activities to compare | 2–5 | 5 |
| Tracks on a map | 3 | 10 |
| Samples in auto stream response | 500 | 500 (fixed target; high mode is separate) |
| Explicit raw stream response | Not requested by default | 20,000 samples, subject to a fixed DB/response budget |
| Requested power durations | 10 | 20, each at least 5 seconds |
| Concurrent browser renders | 1 | 1 (fixed until a measured scaling need) |
| Artifact lifetime | 24 hours | 24 hours (fixed; future ceiling no more than 7 days) |

These are starting budgets, not performance guarantees. Bound DB rows/time **as well as output size**; fetching millions of samples and then decimating in Python is not acceptable. Preserve timestamps and first/last samples; retain maxima/minima when downsampling, and report method and source/returned counts. For irregular data, use timestamp-continuous windows rather than treating N rows as N seconds.

### Repository changes and schema safety

Add filtered search, bounded timestamped multichannel telemetry, coverage and any goal/record queries to `db/repository.py`, then implement **all three** backends with parameterized predicates (`%s` for PostgreSQL/MySQL, `?` with quoted identifiers for Firebird). Validate sort identifiers against a fixed list, not user-supplied SQL; specify identical null, pagination and timezone semantics across backends. Existing `get_activities_web` supports type/date pagination, not all proposed query fields; existing stream access exposes GPS, elevation and watts through separate methods. Test calculations independently from SQL.

Do not invoke `initialize_schema()` as a side effect of a read-only MCP tool. Before adding persistence for segment details, artifacts, approvals or job state, review `db/schema.py`'s existing-column reconciliation: `_update_table` drops columns not present in its declared schema. New tables must be defined in `SCHEMA_DEFINITION` in `db/schema.py` and migrations tested without dropping user data.

#### Dialect-Ready Database Table Schemas (PostgreSQL, MySQL, Firebird)

To support cross-process sync coordination (Tool 29 & 30) and true segment-level KOM provenance (Tool 20), add the following dictionary definitions directly to `SCHEMA_DEFINITION` in `src/kinetiqo/db/schema.py`:

```python
# Definition for sync_jobs table (Cross-process coordination & status tracking)
"sync_jobs": {
    "columns": [
        {"name": "job_id", "type_mysql": "VARCHAR(64) PRIMARY KEY", "type_pg": "VARCHAR(64) PRIMARY KEY", "type_firebird": "VARCHAR(64) PRIMARY KEY"},
        {"name": "athlete_id", "type_mysql": "BIGINT", "type_pg": "BIGINT", "type_firebird": "BIGINT"},
        {"name": "sync_type", "type_mysql": "VARCHAR(32)", "type_pg": "VARCHAR(32)", "type_firebird": "VARCHAR(32)"},
        {"name": "lookback_period", "type_mysql": "VARCHAR(32)", "type_pg": "VARCHAR(32)", "type_firebird": "VARCHAR(32)"},
        {"name": "status", "type_mysql": "VARCHAR(32)", "type_pg": "VARCHAR(32)", "type_firebird": "VARCHAR(32)"},
        {"name": "total_activities", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
        {"name": "synced_activities", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
        {"name": "error_message", "type_mysql": "TEXT", "type_pg": "TEXT", "type_firebird": "VARCHAR(1000)"},
        {"name": "started_at", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE", "type_firebird": "TIMESTAMP"},
        {"name": "completed_at", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE", "type_firebird": "TIMESTAMP"},
        {"name": "heartbeat_at", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE", "type_firebird": "TIMESTAMP"},
        {"name": "created_at", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE", "type_firebird": "TIMESTAMP"}
    ],
    "constraints": [],
    "indexes": [
        {
            "name": "idx_sync_jobs_status_heartbeat",
            "def_mysql": "CREATE INDEX idx_sync_jobs_status_heartbeat ON sync_jobs (status, heartbeat_at)",
            "def_pg": "CREATE INDEX idx_sync_jobs_status_heartbeat ON sync_jobs (status, heartbeat_at)",
            "def_firebird": 'CREATE INDEX idx_sync_jobs_status_heartbeat ON "sync_jobs" ("status", "heartbeat_at")'
        },
        {
            "name": "idx_sync_jobs_athlete_created",
            "def_mysql": "CREATE INDEX idx_sync_jobs_athlete_created ON sync_jobs (athlete_id, created_at DESC)",
            "def_pg": "CREATE INDEX idx_sync_jobs_athlete_created ON sync_jobs (athlete_id, created_at DESC)",
            "def_firebird": 'CREATE DESCENDING INDEX idx_sync_jobs_athlete_created ON "sync_jobs" ("athlete_id", "created_at")'
        }
    ],
    "engine_mysql": "ENGINE=InnoDB"
},

# Definition for verified_segment_efforts table (Segment-level crowns & held status)
"verified_segment_efforts": {
    "columns": [
        {"name": "athlete_id", "type_mysql": _BIGINT_NOT_NULL, "type_pg": _BIGINT_NOT_NULL, "type_firebird": _BIGINT_NOT_NULL},
        {"name": "segment_id", "type_mysql": _BIGINT_NOT_NULL, "type_pg": _BIGINT_NOT_NULL, "type_firebird": _BIGINT_NOT_NULL},
        {"name": "effort_id", "type_mysql": _BIGINT_NOT_NULL, "type_pg": _BIGINT_NOT_NULL, "type_firebird": _BIGINT_NOT_NULL},
        {"name": "activity_id", "type_mysql": "BIGINT", "type_pg": "BIGINT", "type_firebird": "BIGINT"},
        {"name": "segment_name", "type_mysql": "TEXT", "type_pg": "TEXT", "type_firebird": "VARCHAR(500)"},
        {"name": "rank", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
        {"name": "elapsed_time_s", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
        {"name": "moving_time_s", "type_mysql": "INTEGER", "type_pg": "INTEGER", "type_firebird": "INTEGER"},
        {"name": "distance_m", "type_mysql": _DOUBLE_PRECISION, "type_pg": _DOUBLE_PRECISION, "type_firebird": _DOUBLE_PRECISION},
        {"name": "average_watts", "type_mysql": _DOUBLE_PRECISION, "type_pg": _DOUBLE_PRECISION, "type_firebird": _DOUBLE_PRECISION},
        {"name": "is_current_kom", "type_mysql": "BOOLEAN", "type_pg": "BOOLEAN", "type_firebird": "SMALLINT"},
        {"name": "awarded_date", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE", "type_firebird": "TIMESTAMP"},
        {"name": "verified_at", "type_mysql": "TIMESTAMP", "type_pg": "TIMESTAMP WITH TIME ZONE", "type_firebird": "TIMESTAMP"}
    ],
    "constraints": [
        {
            "name": "pk_verified_segment_efforts",
            "def_mysql": "CONSTRAINT pk_verified_segment_efforts PRIMARY KEY (athlete_id, segment_id, effort_id)",
            "def_pg": "CONSTRAINT pk_verified_segment_efforts PRIMARY KEY (athlete_id, segment_id, effort_id)",
            "def_firebird": 'CONSTRAINT pk_verified_segment_efforts PRIMARY KEY ("athlete_id", "segment_id", "effort_id")'
        }
    ],
    "indexes": [
        {
            "name": "idx_seg_efforts_athlete_kom",
            "def_mysql": "CREATE INDEX idx_seg_efforts_athlete_kom ON verified_segment_efforts (athlete_id, is_current_kom)",
            "def_pg": "CREATE INDEX idx_seg_efforts_athlete_kom ON verified_segment_efforts (athlete_id, is_current_kom)",
            "def_firebird": 'CREATE INDEX idx_seg_efforts_athlete_kom ON "verified_segment_efforts" ("athlete_id", "is_current_kom")'
        },
        {
            "name": "idx_seg_efforts_activity",
            "def_mysql": "CREATE INDEX idx_seg_efforts_activity ON verified_segment_efforts (activity_id)",
            "def_pg": "CREATE INDEX idx_seg_efforts_activity ON verified_segment_efforts (activity_id)",
            "def_firebird": 'CREATE INDEX idx_seg_efforts_activity ON "verified_segment_efforts" ("activity_id")'
        }
    ],
    "engine_mysql": "ENGINE=InnoDB"
}
```

---

### Calculation and coverage rules

* For power-duration records, verify continuous elapsed-time coverage; skip invalid/gapped windows rather than calling a series of non-null rows continuous. Weight must be positive for W/kg; FTP must be known and positive for IF/TSS and relative zones.
* NP uses the documented 30-second rolling fourth-power method; `IF = NP / FTP`, `TSS = duration_seconds × NP × IF / (FTP × 3600) × 100`. Define active-time and interval merge rules in a pure service, then test regular, irregular and stopped sessions. Never use `workout_summary.py`'s current fallback 250 W as the athlete's FTP.
* Fitness/Freshness currently consumes positive Strava suffer scores. Include history sufficient to warm the 42-day/7-day EWMA, add zero-activity days through the requested end, and trim *only display* to requested `period_days`. Keep suffer scores and power-based TSS on separate scales. Descriptive load labels are not medical diagnoses.
* Existing VO₂max values are estimates based on cycling power and configured weight. Disclose method and qualification; do not imply personalized age/sex classification from the current fixed approximate thresholds. Existing power-zone labels and Power Skills durations must not be advertised as seven zones/ten points until those models are actually added.
* `verified_koms.json` holds activity-level counts, not full segment records; `verified_trophies.json` and `activities.trophies` hold rank breakdowns. Carry `scanned`/cache-presence status, and never substitute `achievement_count - pr_count` for verified KOMs.

### Rendering, privacy and artifact contract

Share reusable poster/stats/fondo render services between web routes and MCP; only the existing web route handles Flask cookies. Validate aspect ratios, width/height, supported font, hex colors, visibility keys, year/period/group and basemap against server allowlists. Check API-key availability, keep required tile attribution, limit Chromium concurrency and runtime, close browsers on every failure. `photo` mode only uses an already-authorized athlete image; never accept a caller-supplied network URL or arbitrary filesystem path. Redact GPS start/end before serializing **any** map/poster preview or artifact; define no-GPS behavior.

Store rendered files outside source/static directories in a dedicated configurable private directory; name with random IDs, not athlete/activity details. Record MIME type, owner, created/expiry times and size; enforce size/quota and scheduled cleanup. An artifact ID is not a public URL. When HTTP delivery exists, authorize access, prevent traversal/symlinks and avoid forwarding third-party map keys to clients. Inline MCP images only if supported by the pinned SDK and client, size-limited and requested. Standalone HTML must escape all embedded names, not expose secrets, and document live tile-provider/network dependencies.

### Operations, permissions and audit contract

Registration of mutating tools is disabled by default and gated separately: `KINETIQO_MCP_ALLOW_SYNC=0`, `KINETIQO_MCP_ALLOW_PROFILE_WRITE=0`, `KINETIQO_MCP_ALLOW_STRAVA_WRITE=0`. When any of these flags is `0` or unset, the corresponding mutating tools (Tools 24, 29, 32, 33) are **completely omitted from the FastMCP tool registry (`tools/list`)**, preventing LLM context bloat and eliminating hallucinated tool calls. When enabled (`1`), tool handlers also enforce execution-time flag verification as defense-in-depth. See the **MCP activation and environment-variable contract** below for all proposed variable names, defaults and validation; none are implemented yet. Any enabled mutation validates the configured athlete and its allowlisted input, records a safe audit entry and never logs descriptions, passwords, refresh tokens or API keys. MCP is a separate security surface: Flask session auth and CSRF do not automatically protect it.

Sync returns a durable job ID and immediately reports `queued`/`running`; add a read-only `kinetiqo_get_sync_job_status` with `completed`, `failed`, `cancelled`, counts and duration. Default to no Strava description updates even when CLI defaults differ. Prevent overlapping jobs across processes and report `CONFLICT`; full sync may reconcile deletions and must require explicit acknowledgement. Follow `SyncService.sync`'s generator lifecycle and close service/repository on all exits.

Description preview uses only Kinetiqo's validated `{{placeholder}}` grammar. It can consume Strava read quota to obtain the current full description but **must not write**. Publish uses only a short-lived, single-use preview ID bound server-side to activity, caller, template/merged text and current remote-description hash. Re-read before writing; if remote text changed, return `CONFLICT` and request a new preview. Preserve manual text with existing merge logic; verify `activity:write`, stop after 401, and audit without storing sensitive full descriptions in logs. The client approving a tool call alone is not sufficient. Profile updates must preserve existing six templates and refresh token on upsert and respect `profile_sync.py` environment precedence; goals belong to `activity_goals` and use a separate allowlisted updater.

### Deployment and privacy boundary

STDIO stdout carries *only* MCP protocol frames; startup/error/debug logs go to stderr. Client configuration inherits secrets securely from the user environment/OS secret store; no committed credentials. Local DB reads spend no Strava quota but the chosen LLM client may send tool results, including GPS, to a cloud model—explain this clearly. For HTTP, first select a supported transport from the pinned SDK; bind to loopback by default and require explicit non-loopback opt-in, authentication, TLS termination, rate/payload limits and protected artifact endpoints. Minimize DB privileges; offer read-only DB credentials for read-only deployment. Do not claim offline maps when basemap tiles are remotely hosted.

### One image, separate web and MCP services

**Initial deployment choice:** Build **one** Kinetiqo application image and run it as separate processes/services; this is a rollout simplification, **not** a permanent ban on a smaller MCP image. `build/Dockerfile.web` already installs packages from `requirements.txt`, copies `src/`, and inherits Chromium/Firebird from `kinetiqo/firebird-python:3.14`. Pinning the official MCP SDK in `requirements.txt` adds it to the same built image; verify its Python 3.14 wheels because the builder uses `pip install --only-binary=:all:`. `./build/build.sh base` and the manual Firebird base-image workflow change only when Python/Firebird/base dependencies change, not for ordinary MCP code. Docker reuses an identical image's layers on the same host; **running** two containers still incurs separate Python memory/CPU. A read-only MCP process need not launch Chromium. Benchmark pulled image size, startup time, idle/peak RSS and rendering needs after the MVP; if materially beneficial, design a second slimmer image and pipeline based on a base **without Chromium**, while testing DB/schema and release compatibility. Two images inheriting the present Chromium-containing base would not yield that reduction.

The currently implemented `web` Click command calls blocking `app.run()`; production starts Gunicorn via `build/Dockerfile.web`'s default `CMD`. Click does **not** interpret `python src/kinetiqo.py web mcp` as two subcommands. Stdio MCP runs as a separately launched child of a desktop client; HTTP MCP (later phase) runs as a **second container service**, not a Gunicorn worker or background thread in Flask. Both services must use **the same immutable image digest/version** so schema, tools and Python dependencies match. They share one configured athlete/database, not a Python process or mutable DB connection.

| Role | Same image command and behavior | Network / exposure | Startup ownership |
| :--- | :--- | :--- | :--- |
| `web` | Existing default Gunicorn command, listening on 4444 | Existing dashboard exposure behind its usual auth/TLS proxy | Web setup, profile seeding and (transitionally) cron ownership. Do not run an extra Flask dev server in production. |
| `mcp-http` (opt-in, later phase) | `python /app/kinetiqo.py mcp --transport <verified-http-transport> --host 0.0.0.0 --port 4445` after SDK compatibility/auth are implemented | Container-private Docker network; **no** direct host `ports:` mapping. Proxy forwards an authenticated, TLS-protected MCP endpoint only. | Check config/schema without migration; no profile seed, no cron, no banner or credentials logged. |
| `mcp-stdio` (local-client mode) | Client launches `python src/kinetiqo.py mcp` in its own process; a containerized client may use a deliberately configured interactive exec if needed | Stdio, **not** an HTTP listener or permanently running server | Entrypoint, if used, must write **nothing except MCP protocol to stdout**; logs to stderr. No cron or schema changes. |
| `scheduler` (optional, recommended once scaling web) | Same image with a dedicated scheduler command/role | No inbound port | Exactly one instance owns scheduled syncs; replacing web-owned cron is a separate rollout step. |

**Role-aware entrypoint design (`build/entrypoint.sh`):** Currently the entrypoint prints a banner/version/flightcheck, writes environment variables into `/tmp/crontab`, starts cron whenever `FAST_SYNC` or `FULL_SYNC` is set, then `exec "$@"`. Starting an MCP service using it unchanged would duplicate the scheduled syncs; its stdout would also corrupt stdio MCP. Add an explicit, validated `KINETIQO_ROLE` with backward-compatible default `web` for existing deployments. Select role **before any stdout logging or cron setup**. For `mcp-stdio`, route permitted diagnostics to stderr and skip banners, version/flightcheck stdout, cron creation and profile seeding. For `mcp-http`, send startup diagnostics to stderr, perform a read-only DB/schema check, do not start cron or mutate profile/schema, and `exec` the MCP command. For `web`, retain the current behavior during migration but run cron only when `KINETIQO_ROLE=web`; if a `scheduler` role is introduced, move cron ownership **atomically** by enabling scheduler and disabling it in web, including rollback instructions. Never print the environment or copy secrets into build logs. Protect any cron file containing env values with restrictive permissions; avoid writing secrets to a world-readable `/tmp` file. Trap/forward termination so the main process receives SIGTERM and closes jobs/browsers.

**Compose/deployment specification:** Create a concrete base `build/compose.yaml` (web, existing DB or documented external DB, optional reverse proxy) and an opt-in `build/compose.mcp.yaml` overlay (MCP service and protected route). Neither file exists today; avoid assuming the illustrative Compose snippet in `README.md` is a checked-in deployment file. The MCP service in the overlay uses `profiles: [mcp]` and **the same pinned image digest** as web. An operator must include the overlay and opt into the `mcp` profile; simply installing the SDK or setting the **internal** `KINETIQO_ROLE` on web never starts MCP. Keep web and MCP DB backend/timezone consistent but grant only the privileges/credentials needed for each role (read-only DB for read-only MCP, Strava credentials only when a Strava-using feature is enabled). The overlay fixes the MCP command to the SDK-verified HTTP transport, bind `0.0.0.0` **inside the isolated Docker network** and port `4445`; internally sets `KINETIQO_ROLE=mcp-http`; mounts a protected authentication secret file; and disables `FAST_SYNC`/`FULL_SYNC` in MCP. These are deployment code choices, not user-facing environment variables. All three write flags default to `0`. The MCP service depends on DB *health/schema readiness*, not on scraping a web login page; app schema bootstrap/migrations are an explicit one-time step before either role starts. A Compose `depends_on` ordering alone does not guarantee schema readiness. Keep `/app` source immutable; migrate persistent KOM/trophy cache, authorized photos and private artifacts to configured mounted locations before using them from both services. The artifact directory is **never** web static; only the protected owner-aware artifact endpoint can deliver its contents. Size-limited images in stdio do not require an HTTP download URL.

**Network and authentication:** In local stdio mode no MCP port is needed. For containerized HTTP, `127.0.0.1` *inside the MCP container* is unreachable from a separate reverse-proxy container; the command therefore binds `0.0.0.0` **inside an isolated Docker network only**, after explicitly enabling remote mode. Do not publish `4445:4445` on the host. The reverse proxy terminates TLS and verifies caller identity; MCP itself must also enforce authenticated identity/authorization, request limits, origin/host policy appropriate to the pinned transport, write feature flags and per-artifact owner access. Web Flask login/CSRF does not secure this service. Log safe correlation IDs without activity descriptions, GPS paths, tokens or provider keys. Use authenticated health probes that reveal no athlete data (or an internal non-public readiness check); do not probe tools anonymously. Define separate resource/memory/concurrency limits for each service because Chromium exports can consume substantial RAM.

**Operational acceptance:** `docker compose` web-only startup behaves as before; with the opt-in MCP profile the two containers report the **same** image digest, web remains on 4444, only the proxy can reach MCP on 4445, no unauthenticated MCP client succeeds, and exactly **one** cron/scheduler instance runs. Restarting or crashing MCP cannot kill Gunicorn; restarting web does not duplicate MCP. Verify database schema/version compatibility, shared artifacts/ownership, no stdio stdout pollution, graceful shutdown, sync locking across processes and rollback to the last tested digest. These checks belong to the pipeline below, not only an operations manual.

### Minimal MCP activation and environment-variable contract (all proposed)

**None of these MCP capabilities exists in Kinetiqo yet.** Operators configure only **five user-facing values**: Docker Compose opt-in, HTTP authentication and three independent write permissions. Transport, bind address, port, render limits, stream caps and artifact retention are implementation/deployment constants, not additional env knobs. Do not add a separate activation variable inside Gunicorn: it would neither create a second container nor safely supervise a server.

**Default—no MCP:** The existing image continues running Gunicorn on 4444; cron/sync behavior, web credentials and `UPDATE_STRAVA_*` remain unchanged. Without the opt-in Compose profile and overlay, there is **no MCP container, port 4445 listener, MCP proxy route or MCP-initiated write**. Adding the SDK to the image does not start MCP. All three MCP write permissions are off by default.

**Local stdio:** Explicitly register `python src/kinetiqo.py mcp` in the desktop client's configuration; that client launches the child on demand. No Compose profile, HTTP token or open port is involved. If the container entrypoint is used for stdio, set the internal role before it prints anything so stdout remains protocol-only. Separate DB-only validation for the new CLI from today's Strava-requiring `cli.validate_config()`: read-only MCP needs DB settings but no Strava credentials.

**Docker HTTP:** Include both the proposed base Compose file and `build/compose.mcp.yaml` overlay, then enable the built-in Compose `mcp` profile (for example via `COMPOSE_PROFILES=mcp` in the operator's Compose environment). The overlay selects the internally fixed, SDK-verified HTTP command, listens on 4445 **inside an isolated Docker network**, sets `KINETIQO_ROLE=mcp-http` internally, mounts the server secret and enables the authenticated TLS proxy. Supplying the overlay without the profile leaves MCP off; setting the profile without the overlay does nothing. Never publish port 4445 directly on the host. Both proxy and MCP must authenticate and authorize requests; no Flask cookie or CSRF shortcut. If the chosen SDK/client transport is not ready, HTTP mode is unavailable rather than silently falling back to an insecure transport.

**Exact proposed operator switch**, after the overlay, authenticated proxy, secret mount and SDK HTTP transport exist (these files/commands **do not work yet**):

```bash
# Web only (default): base deployment, no MCP process.
docker compose -f build/compose.yaml up -d

# Web + MCP: the same base plus the optional overlay AND the mcp profile.
COMPOSE_PROFILES=mcp docker compose -f build/compose.yaml -f build/compose.mcp.yaml up -d
```

Set `COMPOSE_PROFILES` in the **operator's shell/Compose invocation**, not as an env value inside the web container. The MCP HTTP service also needs `KINETIQO_MCP_AUTH_TOKEN_FILE` pointing to its mounted secret; without it the MCP container must refuse to start. The three `KINETIQO_MCP_ALLOW_*` write flags remain `0` unless each capability is deliberately approved. Do not use `docker compose down` to turn off only MCP: it would stop web too.

**Turn it off:** Disable the Compose profile/remove the overlay and stop the MCP service, or disconnect the local stdio client. Web and cron continue to run. Restart/recreate MCP to apply changes in write permissions; stopping it does not delete DB records or private artifacts (which expire on their normal schedule).

| User-facing setting | Default | Purpose / validation |
| :--- | :--- | :--- |
| `COMPOSE_PROFILES` (Docker Compose, **not** an app env) | unset | Set to `mcp` with the optional overlay to launch a separate MCP container. Unset = web only. No effect on local stdio or already-running services. |
| `KINETIQO_MCP_AUTH_TOKEN_FILE` (HTTP service only) | unset | Required read-only mounted file containing a strong secret. Require `Authorization: Bearer <token>` on MCP requests, compare the supplied token in constant time and authenticate before exposing tools/resources/artifacts. Fail HTTP startup if the file is missing, empty or unreadable. Stdio uses OS/client process trust instead. Never put the token itself in Compose YAML or logs. |
| `KINETIQO_MCP_ALLOW_SYNC` | `0` | If `1`, allow MCP-triggered sync with cross-process locking; defaults to `update_strava=False`. Full sync needs explicit per-request acknowledgment. Requires appropriate Strava/DB credentials. |
| `KINETIQO_MCP_ALLOW_PROFILE_WRITE` | `0` | If `1`, permit validated profile and goal changes with audit/field allowlists; preserve refresh token and respect environment overrides. |
| `KINETIQO_MCP_ALLOW_STRAVA_WRITE` | `0` | If `1`, permit preview-bound description publishing only with `activity:write` scope; never publish just because a template exists. Preview/Strava reads need their own credentials. |

**Fixed implementation settings, not operator env variables:** `KINETIQO_ROLE` is set by the Compose service/entrypoint (`web` by default, `mcp-http` for the optional service, `mcp-stdio` if the container entrypoint is used for stdio); it is **internal**, not an activation switch. CLI/Compose define transport (stdio for direct `mcp`, SDK-verified HTTP in the overlay), bind (loopback for any local HTTP CLI; container-private `0.0.0.0` for proxy reachability) and port (4445) without extra environment knobs. Non-loopback HTTP is accepted only in the reviewed private-network Compose role with token-file authentication and TLS proxy; arbitrary direct CLI non-loopback binds are rejected. Browser-origin policy belongs to the reviewed HTTP server/proxy configuration; no wildcard with credentials. Register renderers only after Phase 3 and private storage readiness. Fix auto streams to 500 returned samples and raw streams to 20,000 (on explicit request only), browser concurrency to one per service and artifact expiry to 24 hours. Enforce scan/size/timeout/ownership limits server-side. Use a fixed private container volume path such as `/data/mcp-artifacts`; for direct stdio choose a private per-user application-data directory. Tests must cover safe defaults, permissions, cleanup and quota rejection. If future operators genuinely need tuning, add narrowly scoped documented settings **after** measuring a need, not preemptively.

**Shared athlete setting (not an MCP activation variable):** `ATHLETE_TIMEZONE` is an application-wide IANA timezone setting for fair calendar comparisons. It resolves through a strict 3-tier hierarchy: (1) explicit `ATHLETE_TIMEZONE` environment variable, (2) athlete timezone read from database `profile` table (synced from Strava), (3) fallback to `'UTC'` with a logged operational warning. Web and MCP share this exact resolution logic. It does not turn on MCP or change stored timestamps.

**Existing Kinetiqo settings (not new MCP flags):** DB connectivity still uses `DATABASE_TYPE` (or legacy `DATABASE`) and the selected backend's `POSTGRESQL_*`, `MYSQL_*` or `FIREBIRD_*` credentials; MCP should reject an invalid backend instead of silently falling back. Read-only MCP needs DB credentials, not Strava tokens. MCP sync and preview/publish need existing `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET` and the persisted refresh token as appropriate. Rendering may use existing map API keys and `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`; missing providers have a safe fallback. `FAST_SYNC`/`FULL_SYNC` are cron schedules, **not** MCP activation switches; MCP role never starts their cron. `UPDATE_STRAVA_*`, `ATHLETE_WEIGHT`, `GPS_SIMPLIFICATION`, `DATE_FORMAT`, `LOG_LEVEL`, `WEB_LOGIN`, `WEB_PASSWORD`, `SECRET_KEY` and `KINETIQO_PRODUCTION` retain their existing meanings; Flask web login/CSRF does not protect MCP. Document backend credentials and how to mount the token file in deployment docs rather than copying the entire web environment into MCP.

**Fail closed and test:** Web-only startup ignores the five MCP settings and opens no MCP listener. HTTP requires its role, valid token file, supported pinned SDK transport, DB/schema readiness and secure Compose/proxy deployment; missing auth or invalid write flag exits with a safe, masked error. Stdio never opens a port or emits banners on stdout. A write flag set to `1` without the needed scope/credentials/privileges must **not** register a usable write tool or silently grant writes; fail startup or report disabled capability explicitly. For optional rendering, do not register generators if private storage/Chromium are unavailable. Mock web-only, overlay-without-profile, profile-with-overlay, stdio and HTTP matrices; verify defaults, auth failure, disabled writes, no duplicate cron and safe shutdown.

---

### CLI Command Integration

Add a Click `mcp` command following the existing `@click.pass_context` / `ctx.obj.config` pattern in `src/kinetiqo/cli.py`. The first implementation accepts only stdio; it validates DB config without requiring Strava credentials, checks that schema exists, starts a read-only FastMCP server and closes resources cleanly. Do **not** call `_prepare_db()` blindly because it initializes/mutates schema. Add HTTP transport support only in the authenticated remote phase and harden direct CLI usage to loopback; the reviewed Compose service supplies the fixed private-network bind on port 4445. Do not add operator env settings merely to select transport/host/port. Return a nonzero CLI exit code for missing DB/schema/config or unsupported transport.

Athletes can test the server locally with one command:
```bash
python src/kinetiqo.py mcp
```

The Docker/remote service requires its own explicit transport, secure listener, authentication and proxy design; it is **not** enabled by this CLI example.

---

### Server composition (`src/kinetiqo/mcp/server.py`)

Use a factory taking `Config` and explicitly enabled feature flags. Register modular tools/resources/prompts against the **pinned, smoke-tested SDK**. Inject a repository factory/callable, not a single long-lived repository connection. Tool handlers own their repo lifetime and use pure analysis services. Register only permitted capabilities; for gated writes, also check flags **at call time**, so policy changes cannot be bypassed via an already-open session. Log to stderr. Document cleanup on normal exit, cancellation and exception.

#### FastMCP Server & Lifecycle Boilerplate

```python
"""Kinetiqo MCP Server Implementation Blueprint (src/kinetiqo/mcp/server.py)."""
import logging
from contextlib import contextmanager
from typing import Generator
from mcp.server.fastmcp import FastMCP

from kinetiqo.config import Config
from kinetiqo.db.factory import create_repository
from kinetiqo.db.repository import DatabaseRepository
from kinetiqo.mcp.tools.activities import register_discovery_tools
from kinetiqo.mcp.tools.telemetry import register_telemetry_tools
from kinetiqo.mcp.tools.physiology import register_physiology_tools
from kinetiqo.mcp.tools.achievements import register_achievement_tools
from kinetiqo.mcp.tools.generator import register_generator_tools
from kinetiqo.mcp.tools.operations import register_operation_tools
from kinetiqo.mcp.resources import register_mcp_resources
from kinetiqo.mcp.prompts import register_mcp_prompts

logger = logging.getLogger("kinetiqo.mcp")


def create_mcp_server(config: Config) -> FastMCP:
    """Factory creating a configured FastMCP server instance with request-scoped DB sessions."""
    mcp = FastMCP("Kinetiqo", dependencies=["kinetiqo"])

    @contextmanager
    def get_repo() -> Generator[DatabaseRepository, None, None]:
        """Provides a request-scoped repository ensuring immediate connection closure."""
        repo = create_repository(config)
        try:
            yield repo
        finally:
            repo.close()

    # Register modular tool groups (mutating tools are registered ONLY if explicitly enabled)
    register_discovery_tools(mcp, get_repo, config)
    register_telemetry_tools(mcp, get_repo, config)
    register_physiology_tools(mcp, get_repo, config)
    register_achievement_tools(
        mcp,
        get_repo,
        config,
        allow_profile_write=bool(int(os.getenv("KINETIQO_MCP_ALLOW_PROFILE_WRITE", "0"))),
    )
    register_generator_tools(mcp, get_repo, config)
    register_operation_tools(
        mcp,
        get_repo,
        config,
        allow_sync=bool(int(os.getenv("KINETIQO_MCP_ALLOW_SYNC", "0"))),
        allow_strava_write=bool(int(os.getenv("KINETIQO_MCP_ALLOW_STRAVA_WRITE", "0"))),
        allow_profile_write=bool(int(os.getenv("KINETIQO_MCP_ALLOW_PROFILE_WRITE", "0"))),
    )

    # Register passive resources & coaching prompts
    register_mcp_resources(mcp, get_repo, config)
    register_mcp_prompts(mcp, config)

    return mcp
```

#### CLI Stdio Runner (`src/kinetiqo/cli.py`)

```python
@click.command(name="mcp")
@click.pass_context
def mcp_cmd(ctx):
    """Start the Kinetiqo Model Context Protocol (MCP) server via stdio."""
    config = ctx.obj["config"]

    # DB-only validation (does NOT require Strava credentials for read-only MCP)
    from kinetiqo.config import VALID_DATABASE_TYPES
    if config.database_type not in VALID_DATABASE_TYPES:
        click.echo(f"Invalid database type: {config.database_type}", err=True)
        sys.exit(1)

    # Ensure stderr logging only to avoid corrupting protocol frames on stdout
    configure_logging(level=config.log_level, stream=sys.stderr)

    server = create_mcp_server(config)
    server.run(transport="stdio")
```

---

## 6. MCP Code Pre-Requirements

Before writing MCP tool handlers or mounting protocol endpoints, several foundational prerequisites and refactorings must be completed across the Kinetiqo codebase. 

> **Transparency & Backward-Compatibility Guarantee**: None of these prerequisite refactorings may alter, degrade, or break existing web routes, DataTables grids, Chart.js visualizations, CLI subcommands (`web`, `sync`, `flightcheck`, `benchmark`), or cron schedules. Existing functions must either remain intact or have their internal calculations extracted into shared, pure-function services that both existing web code and the new MCP server invoke with identical outputs.

```
                  ┌────────────────────────────────────────┐
                  │       Existing Kinetiqo Web/CLI        │
                  │   (Unchanged API, routes, & cron)      │
                  └───────────────────┬────────────────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               │         Shared Foundational Services        │
               │   (Pure functions, repositories, renderers) │
               └──────────────────────┬──────────────────────┘
                                      │
                  ┌───────────────────▼────────────────────┐
                  │          New Kinetiqo MCP              │
                  │  (Stdio tools, resources, and prompts) │
                  └────────────────────────────────────────┘
```

The six prerequisite workstreams are detailed below:

### 6.1 CLI & Configuration Validation Decoupling [✓ COMPLETED]

* **Status**: Completed and verified via unit tests (`tests/test_config.py`).
* **Delivered Changes**:
  * [x] In `src/kinetiqo/cli.py`, introduced dedicated `validate_db_config(config)` helper that strictly checks `config.database_type` and the active backend's connection settings (`host`, `user`, `password`, `database`, `port`).
  * [x] Retained the existing `validate_config(config)` unchanged for `sync`, `web`, and `flightcheck` commands.
  * [x] In `src/kinetiqo/config.py`, added `athlete_timezone: str` and `get_athlete_timezone()` method implementing the 3-tier resolution hierarchy: (1) explicit `ATHLETE_TIMEZONE` env var, (2) database `profile.timezone` fallback, (3) default `'UTC'` with an operational warning.
* **Verification & Transparency**: Verified via unit tests (`test_validate_db_config_success_without_strava`, `test_athlete_timezone_env_var`, `test_athlete_timezone_db_fallback`, `test_athlete_timezone_default_utc`). All existing CLI and web commands remain 100% functional.

### 6.2 Repository Layer Extensions Across All 3 Dialects [✓ COMPLETED]

* **Status**: Completed and verified via unit tests (`tests/test_mcp_repository_extensions.py`).
* **Delivered Changes**:
  * [x] Added abstract methods to `DatabaseRepository` (`src/kinetiqo/db/repository.py`):
    - `search_activities(athlete_id: int, filters: dict, limit: int, cursor: str | None) -> tuple[list[dict], str | None, bool]`
    - `get_stream_coverage(activity_id: int) -> dict[str, dict]`
    - `get_activity_stream_window(activity_id: int, columns: list[str], start_ts: int | None, end_ts: int | None, max_rows: int) -> list[dict]`
  * [x] Implemented all three methods with dialect-specific parameterized SQL in `postgresql.py` (`%s`), `mysql.py` (`%s`), and `firebird.py` (`?` with quoted identifiers).
  * [x] Added URL-safe base64 opaque cursor serialization/deserialization in `src/kinetiqo/db/pagination.py` (`encode_cursor`, `decode_cursor`).
* **Verification & Transparency**: 100% test pass across PostgreSQL, MySQL, and Firebird mocked test suites. Existing repository methods (`get_activities_web`, `get_activity_gps`, etc.) remain completely untouched; web UI DataTables and charts continue to use their existing queries.

### 6.3 Decoupling Pure Analytical Services [✓ COMPLETED]

* **Status**: Completed and verified via unit tests (`tests/test_analytics.py`, `tests/test_workout_summary.py`).
* **Delivered Changes**:
  * [x] Extracted pure mathematical functions into `src/kinetiqo/analytics/`:
    - `src/kinetiqo/analytics/power.py`: Pure functions `calculate_normalized_power(watts_stream)`, `calculate_intensity_factor(np_w, ftp)`, `calculate_tss(duration_s, np_w, if_val, ftp)`, and `calculate_mmp_curve(timestamps, watts, durations)` using continuous elapsed-time sliding windows.
    - `src/kinetiqo/analytics/fitness.py`: Pure function `calculate_ctl_atl_tsb(activities, period_days, warmup_days=42)` ensuring full EWMA warm-up and zero-activity calendar padding.
    - `src/kinetiqo/analytics/pacing.py`: Pure function `calculate_pacing_splits(stream_data, split_basis, num_splits)` computing split deltas and aerobic decoupling `(P1/HR1)/(P2/HR2) - 1`.
  * [x] Refactored `src/kinetiqo/workout_summary.py` to import `calculate_normalized_power` from `kinetiqo.analytics.power`, ensuring byte-for-byte identical description output while eliminating duplicate math.
* **Verification & Transparency**: Verified with golden-fixture unit tests covering constant power, missing FTP/weight, irregular timestamps, paused sessions, and 42-day warm-up curves. Existing `workout_summary.py` tests pass 100%.

### 6.4 Decoupling Headless Playwright Renderers for Offline Stdio [✓ COMPLETED]

* **Status**: Completed and verified via unit tests (`tests/test_renderers.py`).
* **Delivered Changes**:
  * [x] Created reusable export services in `src/kinetiqo/web/renderers/`:
    - `poster_renderer.py`: `render_poster_artifact(activity_id, options, repo, config, html_content) -> bytes`
    - `stats_renderer.py`: `render_stats_artifact(year, sport_group, options, repo, config, html_content) -> bytes`
    - `fondo_renderer.py`: `render_fondo_artifact(year, sport_group, options, repo, config, html_content) -> bytes`
  * [x] Implemented system Chromium discovery and in-process HTML synthesis (`page.set_content(html, wait_until="networkidle")`) supporting offline execution under local stdio.
* **Verification & Transparency**: Verified via unit tests with mocked Playwright. Web UI routes and buttons retain their exact existing handlers with zero regressions.

### 6.5 Schema Safety Declarations & Migration Pre-Registration [✓ COMPLETED]

* **Status**: Completed and verified via unit tests (`tests/test_schema.py`).
* **Delivered Changes**:
  * [x] Added table definitions for `sync_jobs` and `verified_segment_efforts` directly into `SCHEMA_DEFINITION` in `src/kinetiqo/db/schema.py` for all 3 dialects (`type_mysql`, `type_pg`, `type_firebird`).
  * [x] Verified column types, constraints, and indexes across PostgreSQL, MySQL, and Firebird.
* **Verification & Transparency**: Running `python src/kinetiqo.py web` initializes the declared tables cleanly without dropping existing columns; existing tables (`activities`, `streams`, `profile`, `goals`) are untouched.

### 6.6 Dependency Pinning in requirements.txt [✓ COMPLETED]

* **Status**: Completed and verified (`pip check` passes with 74 compatible packages).
* **Delivered Changes**:
  * [x] Added `mcp==1.30.0` and `pydantic==2.14.1` to `requirements.txt`.
  * [x] Verified `pip check` passes cleanly with all pinned dependencies.
* **Verification & Transparency**: Dependencies install and import cleanly across both Python 3.13 and 3.14 environments without breaking existing dependencies.

---

## 7. Implementation Roadmap & Milestones

Each phase ships its own mocked tests, usage documentation and working examples. Later-phase tool descriptions are **planned contracts** until their exit gates pass. 

> **Implementation Scope Strategy**: The implementation roadmap groups **Phases 0, 1, and 2** into a single, cohesive **initial read-only analytical release** delivering all 19 discovery, telemetry, and physiology tools (Tools 1–19) via local stdio. This ensures that the athlete assistant provides complete analytical depth (activity discovery, period comparison, sensor coverage, MMP power curves, PR records, workout structure analysis, CTL/ATL/TSB trends, VO₂max estimates, and Power Skills) from day one, before subsequent milestones introduce visual rendering (Phase 3) and mutation automations (Phase 4).

### Detailed Phase Tasks

#### Phase 0: SDK and source-data verification [✓ COMPLETED]
1. [x] Pin a Python-3.14-compatible `mcp` version (`mcp==1.30.0`, `pydantic==2.14.1`) in `requirements.txt` after verifying official SDK API, license and dependency security.
2. [x] Smoke-test initialize, list/call tool, list/read resource and list/get prompt via STDIO in a local **mocked** client; stdout must contain only protocol frames.
3. [x] Audit repository/schema/API field availability and missing-data examples for each tool; record sport mapping, local calendar/timezone, formula, units, null policy and limits from Section 5.
4. [x] Freeze and test the **MCP activation and environment-variable contract** in Section 5, including web-only default, optional Compose profile, role/transport compatibility, stdio auth boundary and feature-specific credential validation.
**Exit gate:** approved versioned tool schemas and SDK smoke test; no production DB or Strava needed for normal tests.

#### Phase 1: Read-only discovery preview [✓ COMPLETED]
1. [x] Implement stdio-only `kinetiqo mcp`, package factory and per-call repository lifecycle without implicit schema migration.
2. [x] Add backend-parity parameterized search by name/sport/date/metric bounds, detail, totals and pagination (`kinetiqo_search_activities`, `kinetiqo_get_activity_details`, `kinetiqo_get_activity_totals`, `kinetiqo_compare_activities`, `kinetiqo_find_similar_routes`, `kinetiqo_compare_route_attempts`). Keep filters consistent in PostgreSQL/MySQL/Firebird.
3. [x] Implement `kinetiqo_get_data_coverage` and `kinetiqo_compare_periods` with inclusive local dates and equal elapsed-day options using the 3-tier `ATHLETE_TIMEZONE` resolution hierarchy.
4. [x] Register sanitized profile/goals/latest-activity resources and read-only coaching prompts.
5. [x] Mock repository factory in CLI/server tests; test SQL parameterization and result normalization for all backends.
**Exit gate:** real STDIO handshake against fixtures and discovery/coverage/period comparison prompts; verified in Antigravity IDE and automated unit test suite.

#### Phase 2: Telemetry Streams & Physiology [✓ COMPLETED]
1. [x] Add a bounded, timestamp-aligned multi-channel repository read (`get_activity_stream_window`), stream coverage and event/extrema-preserving downsampling (`kinetiqo_get_activity_streams`). Implement missing-sensor, pause, irregular-rate and no-GPS handling.
2. [x] Validate continuous-window semantics of `get_best_power_per_activity`; implement `kinetiqo_get_personal_records`, `kinetiqo_calculate_power_curve`, FTP history (`kinetiqo_get_ftp_history`) and Power Skills (`kinetiqo_get_power_skills`) with evidence activity IDs.
3. [x] Extract structured NP, IF, TSS and intervals into pure analysis functions (`kinetiqo_analyze_workout_structure`, `kinetiqo_analyze_pacing`, `kinetiqo_get_route_highlights`); retain `generate_workout_summary()` for prose only.
4. [x] Adapt `fitness.py` with historical warm-up and zero-load days through today; retain suffer score as its own scale (`kinetiqo_get_fitness_and_freshness`, `kinetiqo_get_training_load_trends`). Expose qualification/methods for VO₂max estimates (`kinetiqo_get_vo2max_trend`).
5. [x] Test formula fixtures, timestamps, missing/invalid FTP/weight, sample gaps, power/HR-free sports and long streams across all three repository implementations (PostgreSQL, MySQL, Firebird).
**Exit gate:** complete analytical suite operational via stdio; analysis prompts expose measurement versus estimate, nulls and coverage without medical claims. Real-world verification passes in Antigravity IDE.

#### Phase 3: Visual & Creative Generation [✓ COMPLETED]
1. [x] Refactor poster, MEGA Stats and Fondo Playwright rendering into shared services called by existing Flask routes and MCP without accepting arbitrary URLs or caller-supplied cookies.
2. [x] Add validated map-provider/font/color/size allowlists, per-render time/memory/concurrency budgets and missing-key/no-GPS fallbacks. Preserve map-provider attribution.
3. [x] Implement `kinetiqo_generate_activity_poster`, `kinetiqo_generate_mega_stats_infographic`, `kinetiqo_generate_fondo_infographic` and `kinetiqo_generate_map_artifact` with GPS start/end redaction.
4. [x] Dual delivery format (inline base64 image + metadata).
5. [x] Mock Playwright and tile requests; test forbidden paths, missing fonts/keys, browser failures/timeouts, cleanup, private file access and privacy redaction in generated output.
**Exit gate:** poster/stats/fondo still work in web UI; MCP renders independently of Flask session cookies and returns private references.

#### Phase 4: Achievements, Automations & Sync [✓ COMPLETED]
1. [x] Add read-only KOM count/cache freshness (`kinetiqo_get_verified_koms`), trophy scan-status (`kinetiqo_get_segment_trophies`), Fondo milestones (`kinetiqo_get_fondo_milestones`) and goal pacing (`kinetiqo_get_training_goals`).
2. [x] Implement durable sync job status checking (`kinetiqo_get_sync_job_status`); gated `kinetiqo_trigger_sync` disabled by default (`KINETIQO_MCP_ALLOW_SYNC=0`).
3. [x] Implement Strava description preview (`kinetiqo_preview_strava_description`) using the existing validated placeholder engine; gated publishing (`kinetiqo_update_strava_description`) disabled by default (`KINETIQO_MCP_ALLOW_STRAVA_WRITE=0`).
4. [x] Implement profile and training goal updaters (`kinetiqo_update_athlete_profile`, `kinetiqo_update_training_goals`) gated by `KINETIQO_MCP_ALLOW_PROFILE_WRITE=0`.
5. [x] Mock Strava, repo and job store; test conflict, preview, idempotency, and scope/flag enforcement.
**Exit gate:** no write tool available by default; approval of a read-only prompt never performs sync or publication.

#### Phase 5: Remote access and client documentation
1. Test supported desktop clients (including Antigravity and OpenClaw versions documented in Section 8) in stdio mode with **secrets-free** config examples and explicit working-directory/env instructions. Never commit client configs containing credentials.
2. If remote access is approved, verify SDK/client HTTP transport compatibility, implement caller authentication, TLS reverse proxy, loopback default, quotas and protected artifact delivery; test unauthorized and cross-user access.
3. Create the MCP-specific validation/deployment pipeline described below; gate the existing publishing workflow on its result, without building or publishing a second image.
4. Document privacy boundary (client may relay GPS to a cloud model), web-only-by-default behavior, exact `COMPOSE_PROFILES=mcp` opt-in and required overlay, one-image/two-service deployment, role-aware entrypoint, the Section 5 environment-variable table, required map/Playwright setup, performance limits, disabled tools and troubleshooting. Include an explicit procedure to turn MCP off without stopping web or deleting user data.
5. Run full mocked suite and opt-in dialect/client integration checks; keep SDK/transport compatibility checks versioned.
**Exit gate:** fresh read-only install follows documentation successfully; remote and mutations remain opt-in.

### Dedicated MCP build, verification and deployment pipeline

**"Own build pipeline" means an independently owned MCP quality and deployment gate, not two independently built application images.** The existing `build/build.sh` builds the application image (local `linux/amd64`, publish `linux/amd64,linux/arm64`); `.github/workflows/build.yaml` invokes it for manual dispatch or `/publish`/`/release` commits. `.github/workflows/build-base-image.yaml` builds the Firebird/Chromium base separately. `.github/workflows/ci.yml` already runs Python 3.14 syntax checks and unit tests. Reuse these foundations; creating a second image with a divergent dependency set would make the web/MCP shared schema and rendering behavior harder to validate. An MCP-only source or SDK change **still requires rebuilding the existing application image** before deployment. Never deploy an MCP service from a commit different from the web service while schema/tool compatibility is unverified.

Implement a dedicated `.github/workflows/mcp-ci.yml` or reusable workflow with the following explicit gates; run it on PRs and pushes changing `src/kinetiqo/mcp/**`, MCP-related `db/**`, `cli.py`, `sync.py`, `web/renderers/**`, `build/**`, `requirements.txt`, `docs/mcp-concept.md` or the workflow itself. Keep a manual dispatch for full validation when dependencies change. Pin third-party Actions by reviewed versions (or immutable SHAs under repo policy) and use least-privilege GitHub permissions; never expose publishing credentials to untrusted PRs.

| Gate | Execution / success requirement |
| :--- | :--- |
| **Contract and security** | Python 3.14 dependency install and `pip check`, existing syntax checks, mocked tests from Section 10 on CLI/STDIO/HTTP/roles, validation of secret masking and no surprise write-tool registration. Run dependency vulnerability/license review and fail on an approved severity threshold; check container dependencies too. |
| **SDK interoperability** | Install the **pinned** MCP SDK, initialize a stdio session with a local synthetic client and exercise list/call tool, read resource and get prompt; assert no stdout banners and correct errors/limits. Later add HTTP client handshake/auth tests for the selected pinned transport. |
| **Entrypoint matrix** | Invoke `build/entrypoint.sh` with mocked commands and unset/default `KINETIQO_ROLE`, `web`, `mcp-http`, `mcp-stdio` and optional `scheduler`: test valid/invalid roles, cron enabled only once, no STDIO stdout, no schema migration/profile seeding in MCP role, signal forwarding and no secrets echoed. Validate Section 5 env defaults, missing HTTP token, role/transport mismatch, disabled writes and DB-only validation without Strava credentials. Avoid real DB/Strava in this gate. |
| **Container smoke** | Build **one** local candidate image from `build/Dockerfile.web` using the existing Firebird base; test that the image contains MCP SDK, web server and Chromium without downloading another browser. Start web and MCP *from the same candidate image* against disposable fixture services if available; smoke-test port separation, read-only schema checks, health, artifact volume ownership and restart isolation. Keep DB/browser/network-dependent tests isolated from default mocked CI; provide a separately triggered full smoke gate for release. |
| **Compose/proxy policy** | Validate base config without overlay, overlay without profile, and overlay with `COMPOSE_PROFILES=mcp`: first two run web only; last runs web + exactly one MCP service. Assert no public MCP `ports:` mapping, no duplicate cron, network isolation, non-root/read-only permissions where compatible, mounted token-file auth and TLS proxy, feature flags off by default and shared image digest/version. Reject committed real credentials and public artifact directory mounts. |
| **Release evidence** | Record test summary, pinned SDK version/transport, supported platforms, SBOM/vulnerability report, image SHA/digest, Compose smoke result and migration notes as CI artifacts (no secrets or private GPS). A failed mandatory gate stops publish and deployment. |

**Wire the gate into the existing release path:** Today `build.yaml` has one conditional build/push job and can publish based on a commit message or manual input. Add a required MCP validation job (via reusable workflow or called job) with `needs` before **every** publish/release branch of that job; protect the main branch so publishing cannot bypass it. For no-publish PRs, run mocked MCP validation without DockerHub credentials. If MCP is not yet implemented, gate only documentation/contract checks; expand mandatory gates as Phases 0–5 land. Continue to publish multi-architecture `kinetiqo/web` and `kinetiqo/web-mcp` images through `build/build.sh`, but deploy using the tested **immutable digest** rather than mutable `latest` or a timestamp tag. If an MCP-specific smoke job builds a candidate image and `build.yaml` builds another, verify both use the same commit/context and test the **actual published digest** before production; preferably build once, promote the tested artifact/digest and avoid duplicate divergent builds. When changing Firebird/Python base, run the manual base-image workflow first, record the new base digest, rebuild the application and rerun all role smoke tests.

**Separate deployment pipeline:** Add an opt-in `.github/workflows/mcp-deploy.yml` (or equivalent deployment automation) that **pulls** a previously tested app image by digest; it must not independently rebuild or tag a second MCP image. Require a protected staging environment and manual approval for production, provision DB/Strava/proxy credentials from environment secrets (never build arguments or checked-in Compose), apply schema migrations once, then roll out the web and optional MCP services using the **same digest**. Stage the proxy and private artifact volume; run authenticated MCP initialize/tool checks plus web readiness. Only after those checks enable external routing. On failure, withdraw the MCP route, stop/revert the MCP service, restore the prior image digest for web if required and document schema rollback compatibility; do not assume an automatic destructive DB downgrade. Roll out web-only installations unchanged when the MCP profile is disabled. Maintain runbooks for rotating proxy/client credentials, replacing an expired artifact store and observing job locks/cron ownership.

**Definition of done for the pipeline:** A PR cannot silently ship untested MCP changes through `/publish`, the default install has **no MCP process/listener**, `COMPOSE_PROFILES=mcp` with the overlay deliberately starts one, both roles share an attested/tested digest, `mcp-stdio` emits protocol-only stdout, remote MCP is private and authenticated by default, scheduled jobs run in exactly one role, and production deployment/rollback is repeatable without a second Docker image build. The pipeline itself needs mocked workflow/entrypoint tests plus opt-in disposable-container smoke tests; Section 10 remains the default developer test suite.

---

## 8. Client Configuration Examples

### Future-user setup: run Kinetiqo MCP and connect a client

**Status:** This is the user workflow the implementation must deliver; **none of the MCP command, MCP Compose overlay or MCP HTTP endpoint exists yet**. Do not present these examples as working against the current release. First choose **local stdio** (simplest: your AI client launches Kinetiqo itself) or **Docker HTTP** (always-on server behind an authenticated TLS reverse proxy). In both modes, first install Kinetiqo and initialize/sync the chosen DB through the existing web/CLI workflow; a new read-only MCP process must check the schema but must **not** initialize or migrate it. Ensure the machine/container running MCP can reach that database. The normal web app may continue running concurrently, but is not required for **read-only stdio** access to an already initialized database. Rendering may additionally need the web/rendering services described in Section 5.

#### Exactly which environment variables are required?

All MCP-specific variable names in this subsection are **planned**; existing Kinetiqo DB/Strava variables are already in `src/kinetiqo/config.py`. Enter credentials using your OS secret manager or a private environment provided to the process; **do not commit them to a client JSON config**. Only credentials for the selected database backend are needed. `ATHLETE_TIMEZONE` is optional configuration (resolving via env var -> DB profile -> UTC fallback).

| Mode / feature | Required values | Set where | Unneeded or optional values |
| :--- | :--- | :--- | :--- |
| **Local read-only stdio** | `DATABASE_TYPE` (`postgresql`, `mysql`, `firebird`; current default is PostgreSQL) and the selected backend's host, user, password and database as detailed below | Environment of the **client-launched MCP child process**, supplied securely. Python command/arguments are in the client's MCP configuration, not environment variables. | No `COMPOSE_PROFILES`, MCP HTTP token, Strava credentials, web password, session `SECRET_KEY` or MCP permission flags required. `ATHLETE_TIMEZONE` optional (resolves via env var -> DB profile -> UTC fallback). |
| **Docker read-only HTTP** | Same backend DB settings; `COMPOSE_PROFILES=mcp` **plus both planned Compose files**; `KINETIQO_MCP_AUTH_TOKEN_FILE` pointing to a read-only mounted secret containing a strong token | `COMPOSE_PROFILES` in the **operator's Compose invocation**; DB settings and secret-file path in the **MCP service's runtime environment** / Compose secret mount, never in the web container to activate MCP | Three `KINETIQO_MCP_ALLOW_*` flags default to `0`; web/cron continue separately. Proxy TLS/auth, network isolation and secret provision are mandatory deployment configuration, **not** additional MCP env variables. |
| **MCP-triggered sync** (off by default) | `KINETIQO_MCP_ALLOW_SYNC=1` plus valid `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET` and effective refresh token persisted/resolved by Kinetiqo; write-capable DB permissions/job lock | **Only** MCP process/service, from secured deployment environment | Not required for ordinary local reads; setting this flag on the web service does **not** activate MCP. |
| **Profile/goal changes** (off by default) | `KINETIQO_MCP_ALLOW_PROFILE_WRITE=1` plus DB write privileges | MCP service/client-launched process | Strava credentials not needed solely to edit DB goals; honor env overrides for profile fields. |
| **Strava description publish** (off by default) | `KINETIQO_MCP_ALLOW_STRAVA_WRITE=1`, Strava client credentials/effective refresh token and `activity:write` OAuth scope | MCP process/service, never in the committed client JSON | Publishing additionally requires an approved unexpired preview; the flag and OAuth scope alone never cause a write. A preview that contacts Strava needs read credentials even when publishing is disabled. |

Backend variable names: **PostgreSQL** uses `POSTGRESQL_HOST`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_DATABASE` (optional `POSTGRESQL_PORT`, default `5432`, and `POSTGRESQL_SSL_MODE`). **MySQL** uses `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` (optional `MYSQL_PORT`, default `3306`, and `MYSQL_SSL_MODE`). **Firebird** uses `FIREBIRD_HOST`, `FIREBIRD_USER`, `FIREBIRD_PASSWORD`, `FIREBIRD_DATABASE` (optional `FIREBIRD_PORT`, default `3050`). Set only the selected group plus `DATABASE_TYPE`. On a Docker network, `localhost` inside MCP means the MCP container itself; use the DB service hostname or a reachable external DB host. Confirm network reachability, schema and permissions before connecting a chat client. Existing `cli.validate_config()` requires Strava credentials; the MCP command must implement **DB-only validation** for read-only tools, and add feature-specific Strava checks only when actually used.

**Local stdio procedure:** (1) Install the future MCP-enabled Kinetiqo dependency set into the Python interpreter you will configure in the client; supply the appropriate DB variables to that child. (2) Register the absolute path to that interpreter and the absolute path to `src/kinetiqo.py` with argument `mcp`. (3) Restart/reload the client if needed and verify `kinetiqo_search_activities` appears and returns a small result. The client launches and owns this process; do **not** run a standalone interactive stdio command in another terminal and expect the client to attach to it. For a Windows-native client use accessible Windows paths/interpreter and make sure the DB is reachable from Windows; for a client running on SSH/Linux use absolute POSIX paths and environment supplied on **that** host. The `~/.envrc` SSH shell environment does not magically propagate to a Windows GUI application. Logs go to stderr only; stdout is MCP protocol.

**Docker HTTP procedure:** (1) Deploy the web service/database normally and make sure the schema is initialized. (2) Provision the mounted auth token file, private artifact volume if later enabling rendering, and an authenticated HTTPS proxy; configure the MCP service with its minimum DB privileges. (3) Include `build/compose.mcp.yaml` and opt into `COMPOSE_PROFILES=mcp` (the exact proposed commands are in Section 5). (4) Verify two services from the same tested image, only one cron owner, and an authenticated MCP URL; direct host port 4445 must not be published. (5) Configure the client with the proxy's **actual authenticated HTTPS endpoint** and the transport confirmed by the pinned SDK, not `http://localhost:4445` or `/api/poster/photo/...`. Store the bearer credential in that client's secret store/scoped header editor so it sends `Authorization: Bearer <token>`; the token value must match the server-side mounted secret. A proxy may require an additional, separate authentication step. Never paste either secret into a shared configuration example. Test an unauthorized request fails, then list tools and call a read-only activity tool. Recreating/stopping only the MCP service must leave web working.

**Client troubleshooting checklist:** No tools listed → confirm the `mcp` process exists/HTTP profile was enabled, selected Python/working directory is valid, `DATABASE_TYPE` and selected DB credentials reach the DB and the tool is available in the implemented phase; check stderr, never protocol stdout. HTTP 401 → check the client's auth credential and `KINETIQO_MCP_AUTH_TOKEN_FILE` mount/rotation; proxy auth and server auth may be separate. HTTP connection refused → confirm overlay **and** profile, transport/path, TLS proxy routing and private container network. Permission denied → disabled write flag or missing OAuth scope is expected; do not enable all writes to fix a read-only failure. Missing artifact → renderer may not yet be implemented, or artifact expired/is not owned by this client. Never share real GPS, credentials or debug logs containing private activity data in issue reports.

### 1. Claude Desktop (`claude_desktop_config.json`)

On Windows: `%APPDATA%\Claude\claude_desktop_config.json`  
On macOS/Linux: `~/.config/Claude/claude_desktop_config.json`

Run a configured Kinetiqo Python environment and inherit database settings from the operating-system secret store or a secure, untracked launcher. Example **without credentials** (Windows path is illustrative; choose the Python interpreter from the installed environment):

```json
{
  "mcpServers": {
    "kinetiqo": {
      "command": "python",
      "args": ["H:\\WORKING\\kinetiqo\\src\\kinetiqo.py", "mcp"]
    }
  }
}
```

Verify whether the selected desktop client inherits the intended environment; do not assume it loads Kinetiqo's `.env` or `.envrc` automatically. The proposed read-only MCP must use DB-only validation, not today's `cli.validate_config()` requiring Strava credentials. Registering this client opts into stdio MCP; no Docker Compose profile or HTTP env setting is needed. See the Section 5 activation table for the complete proposed env contract.

### 2. Antigravity IDE (stdio)

In your installed Antigravity version, open its MCP server manager/settings and add a **stdio** server named `kinetiqo` with the absolute Kinetiqo Python interpreter as `command` and the absolute script path plus `mcp` as arguments. Use the configuration file **location shown by your installed client's MCP manager**; do not assume a workspace `.gemini/config/mcp_config.json` path works across versions. If that client supports a JSON `mcpServers` object, the following is an illustrative Windows-native entry; adapt the interpreter/script paths to the machine *running Antigravity* and set DB credentials securely in that machine's environment, not in the JSON:

```json
{
  "mcpServers": {
    "kinetiqo": {
      "command": "H:\\WORKING\\kinetiqo\\.venv\\Scripts\\python.exe",
      "args": ["H:\\WORKING\\kinetiqo\\src\\kinetiqo.py", "mcp"]
    }
  }
}
```

Save/reload the MCP connection, list tools and call `kinetiqo_search_activities(limit=1)` once implemented. If Antigravity runs on SSH/Linux instead, use its Linux interpreter/script paths; a Windows drive path is not valid there. The same client can use the authenticated HTTPS deployment instead **only if its installed version supports the pinned HTTP transport and secure credential configuration**.

### 3. OpenClaw (stdio or authenticated HTTP)

OpenClaw's [official MCP connection guide](https://docs.openclaw.ai/tools/mcp) documents **Settings → MCP → Add server**, choosing Stdio or Streamable HTTP, and its `openclaw mcp add` / `doctor` commands. OpenClaw acts as an MCP **client** of Kinetiqo; `openclaw mcp serve` is the reverse direction and is **not** needed. Prefer local stdio when the OpenClaw Gateway and Kinetiqo Python/database are reachable on the same machine. For a POSIX Gateway, use its real absolute Python and script paths (example paths below are illustrative; replace with yours):

```bash
openclaw mcp add kinetiqo \
  --command /home/athlete/WORKING/kinetiqo/.venv/bin/python \
  --arg /home/athlete/WORKING/kinetiqo/src/kinetiqo.py \
  --arg mcp \
  --cwd /home/athlete/WORKING/kinetiqo
openclaw mcp doctor kinetiqo --probe
```

Supply DB variables to the **Gateway's child-process environment**, not only an unrelated shell. In Settings → MCP, the alternative is to name the server `kinetiqo`, select **Stdio**, and supply that same command and arguments. Verify the probe can list read-only tools; OpenClaw tool-profile/policy settings can also hide an otherwise connected tool. Do not turn on profile/Strava writes just because an AI client has its own tool approvals.

For a separate Docker MCP server, select **Streamable HTTP** in OpenClaw Settings → MCP, enter the actual TLS proxy URL (for example `https://kinetiqo.example.org/mcp`, only if the deployed SDK/proxy uses that path), and configure its authentication credential using OpenClaw's **scoped config editor/secret mechanism**, not a literal in a committed config file. OpenClaw's documented HTTP CLI syntax is `openclaw mcp add kinetiqo --url <authenticated-https-url> --transport streamable-http`; perform credential setup through the client before `openclaw mcp doctor kinetiqo --probe`. Do not assume the same OpenClaw Gateway can reach Kinetiqo's container-private `4445` address from another host. Current guide/reference: [OpenClaw Connect MCP servers](https://docs.openclaw.ai/tools/mcp) (verify against the installed OpenClaw version at implementation time).

### 4. Other MCP clients and remote connector (future, after approval)

In any client supporting stdio, configure the executable path, `src/kinetiqo.py` and `mcp` argument, with secure DB environment on the machine running the client. In any client supporting the implemented HTTP transport, configure the **authenticated HTTPS reverse-proxy URL** and credential via its secret mechanism. A client limited to SSE cannot automatically speak streamable HTTP: test the exact SDK/client pairing, or add a separately secured compatible transport in a later release. Do not distribute an unauthenticated `http://LAN:4445/sse` command. Validate connection by listing tools/resources/prompts and calling a small read-only tool before granting optional writes.

---

## 9. Sample Conversational Scenarios

### Scenario A: Deep Post-Ride Coaching & Pacing Analysis

> **Athlete**:  
> *"Hey, how did today's ride go? Break down my pacing and tell me if I went too deep into the red."*

> **AI Assistant (using Kinetiqo MCP)**:
> 1. Search latest activity, fetch details and data coverage; analyze workout only if usable sensor data exist.
> 2. Fetch fitness/freshness for recent workload context, with sufficient calculation history.
> 3. **Respond with retrieved numbers only**: measured distance/elevation/power, computed intervals with coverage, estimated FTP-relative values only if configured, and qualified workload context. If HR or power is absent, state what cannot be inferred. Do not invent named climbs, CTL deltas or recovery hours.

---

### Scenario B: Generating an Art Poster via Chat

> **Athlete**:  
> *"I loved my 120km Dolomites ride last month. Can you make me a stunning dark-themed poster in 16:9 for my desktop background?"*

> **AI Assistant (using Kinetiqo MCP)**:
> 1. Calls `kinetiqo_search_activities(query="Dolomites", sport_types=["Ride"])`.
> 2. Identifies Activity #1184729104: *"Sellaronda Epic - 122.4 km | 3,340 m"*.
> 3. Verify GPS and CARTO key availability, choose a supported font and request `kinetiqo_generate_activity_poster(activity_id="1184729104", ratio="16/9", map_provider="carto_dark", route_color="#f97316", font_family="Outfit")`.
> 4. Respond with the actual artifact ID, dimensions, expiry and authenticated download reference **if returned**. Offer OSM or photo fallback if CARTO tiles are unavailable. `/api/poster/photo/<id>` is a background-photo endpoint, **not** an exported-poster URL.

---

### Scenario C: Season Achievements & Fondo-o-meter Showcase

> **Athlete**:  
> *"How many 100km+ rides have I done this year, and how do they compare to my all-time record?"*

> **AI Assistant (using Kinetiqo MCP)**:
> 1. Calls `kinetiqo_get_fondo_milestones(year=2026, sport_group="cycling")`.
> 2. Calls `kinetiqo_get_fondo_milestones(year="all", sport_group="cycling")`.
> 3. Optionally fetch locally verified KOM counts, indicating cache coverage/freshness.
> 4. Respond using only returned milestone counts and source activities; distinguish all-time from this year and avoid attributing KOMs to particular rides unless activity IDs match. Offer a Fondo-o-meter artifact only if visual generation is enabled.

---

## 10. Testing, Safety & Performance Standards

### Default testing policy and commands

Write fast, isolated **mocked unit tests with every phase**. Never require a live database, Strava account, map provider, Chromium download or network in the normal test run. Patch external boundaries where imported by the unit under test (e.g. `kinetiqo.mcp.server.create_repository`, a tool-module repository factory, `kinetiqo.sync.StravaClient`, Playwright launch); inspect import paths when code is written rather than assuming a patch at the original module works. Use `unittest.mock.patch` and `subTest` matrices, following `tests/test_sync_logic.py`. Use synthetic activity IDs/coordinates, not real athlete exports. Run from the project root:

```bash
python -m pytest -o pythonpath=src
PYTHONPATH=src python -m unittest discover -s tests -v
```

Optional SDK interoperability/browser/database integration suites run only by explicit operator request and use disposable fixtures; exclude them from the mocked default suite. Never copy production tokens into fixtures. For documentation-only changes, verify Markdown structure, links, document ordering and that example commands describe actual implemented capabilities.

### Required mocked test matrix

| Area | Required cases and assertions |
| :--- | :--- |
| Registration/STDIO | Exactly supported tool/resource/prompt names and schemas; no MCP process/container or HTTP listener by default; only read-only tools when flags unset; invalid transport/role fails; stdout contains protocol data only; startup errors use stderr; read-only MCP needs DB config but no Strava creds; repository closed. |
| Input validation | Valid/invalid ID, date, timezone, sort, sport type/group, finite numeric bounds, reversed range, duplicate IDs, unknown stream, oversized list, invalid format/font/basemap/color/path; stable error code and no database call on rejected input. |
| Repository parity | All new abstract methods implemented by PostgreSQL, MySQL and Firebird; proper `%s` or `?` binding, identifier allowlists/quoting, consistent inclusive-date semantics, deterministic ties, bounded pagination and no user data interpolated into SQL. |
| Activity discovery | Empty DB, no match, partial metadata, timezone boundary, assisted/indoor exclusions, huge requested limit, SQL/backend failure, units and ID serialized as string. |
| Stream access | Missing GPS on indoor ride, missing HR/power, nulls, pause and uneven timestamps, high-frequency peak, first/last preservation, aligned channels, auto limit 500, explicit high hard cap 20,000, cancellation/cleanup and DB row budget. |
| Power/workout | Constant power NP/IF/TSS golden fixture, variable power, 29-second stream, zero/unknown FTP or weight, gapped 20-min window, interval threshold/merge, stop duration, sport lacking power, deterministic numeric outputs (do not test random adjectives). |
| Fitness/FTP/VO₂max | Zero-activity days, sufficient historical EWMA warm-up, no suffer score, same-day activities, estimated versus configured FTP, VO₂max qualifying ride/outlier/missing weight, method metadata and no medical/age-sex certainty. |
| Achievements/goals | Missing cache vs zero crown, scanned vs unscanned trophy, date/year bounds, qualifying Fondo sport types, unset goal, goal period boundary/required pace, profile read excludes refresh token. |
| Render/artifacts | Mock browser and map tiles; unsupported/missing keyed basemap, photo permission, no GPS, timeout and browser cleanup, concurrent limit, color/size clamps or rejections, attribution, text escaping, GPS redaction **before** serialization, inaccessible expired/other-user artifact and symlink/path traversal. |
| Writes/sync | All feature flags off, unauthorized HTTP caller, overlapping sync across processes, default `update_strava=False`, full-sync acknowledgement, completed/failed/cancelled job, unsupported lookback, preview no-write, malformed placeholders, preview expiry/replay, remote-description hash conflict, OAuth 401/429, sanitized audit and idempotent retry. |
| Security/privacy | No credentials/refresh tokens in results, errors, stderr or artifacts; read-only calls never contact Strava; remote unauthorized client cannot enumerate tools/artifacts; rate and output limits are enforced. |

For each tool add at least one success, empty/partial, invalid-input, unavailable-data and boundary-failure test. Assert response-envelope fields, expected repository calls, safe error codes and cleanup. When a backend interface changes, add unit tests for **all three** implementations; optional disposable-DB smoke tests can separately catch driver-specific SQL errors. Keep external services mocked in CI. Every newly supported transport must have a version-pinned initialize/list/call smoke test. Render tests should validate the returned artifact metadata rather than asserting an uncontrolled pixel-perfect screenshot.

### Performance and safety acceptance

Enforce the Section 5 input/output limits in server code, not just documentation. Profile large local datasets per backend, check query plans and benchmark real-world GPS/watts reads separately; do not promise sub-millisecond results. For Firebird, avoid unbounded `IN` clauses and full-stream Python materialization. Apply browser resource/time limits and a cleanup policy to artifacts. Mutating operations are never invoked as an implicit consequence of a prompt, and activity deletion is **not an MCP tool**. Generated JavaScript, if needed, follows `javascript:S7773` and uses `Number.parseInt` / `Number.parseFloat` rather than legacy globals.

---

## 11. Conclusion & Next Steps

The MCP server is feasible as a phased, private athlete-data assistant. Its strongest differentiation is evidence-linked local longitudinal analysis, available telemetry and protected visual artifacts—not unsupported promises of complete sensor coverage, medical certainty or unlimited performance. The read-only MVP precedes rendering and explicit opt-in mutations.

### Immediate Action Items:
1. Complete **Phase 0**: pin/test SDK, approve data/response contract, verify repository and stream semantics; see Section 5.
2. Implement **Phase 1** with mocked tests and read-only STDIO tool registration; test a desktop client before widening scope.
3. Keep HTTP exposure, sync, profile/goals writes and Strava publishing disabled until separately approved and tested.

---

## 12. Example Prompts

These are user-facing acceptance scenarios, **not claims that all tools already exist**. Tools are indexed in the Master Tool Catalog (Section 3) with priority badges (`[P0]`, `[P1]`, `[P2]`, `[MVP]`). Return only facts present in tool responses; explain missing coverage and label estimates. Do not automatically publish, sync or share location when a user asks a question.

### Training history and goals (read-only MVP)

1. **"What did I do this week across cycling, running and walking? Include distance, moving time, elevation and links to the longest activities."** `kinetiqo_search_activities` (Tool 1) + `kinetiqo_get_activity_totals` (Tool 3); interpret week in configured athlete timezone; disclose excluded sports.
2. **"Compare this month with the same number of elapsed days last month and the same period last year."** `kinetiqo_compare_periods` (Tool 5, [P0]); do not compare a partial month with a full one without warning.
3. **"Am I on pace for my yearly cycling distance and elevation goals? What average per remaining week do I need?"** `kinetiqo_get_training_goals` (Tool 23, [P1]); report unset goals as unset, not failed.
4. **"Find my five longest outdoor rides this year; exclude e-bikes and indoor rides."** `kinetiqo_search_activities` (Tool 1); echo included Strava sport types and sorting.
5. **"Which rides this month have no GPS, HR or power, and what analyses are unavailable for each?"** `kinetiqo_search_activities` (Tool 1) + `kinetiqo_get_data_coverage` (Tool 9, [P0]); distinguish absent sensor from missing sync.
6. **"Which weeks did I ride most consistently, and how does that compare with last year?"** `kinetiqo_compare_periods` (Tool 5, [P0]) + `kinetiqo_get_activity_totals` (Tool 3); explain activity count versus training load.

### Performance and coaching with limits (Phase 2)

7. **"Debrief yesterday's ride: separate recorded facts, calculated power metrics and estimated training load; tell me if data are missing."** `kinetiqo_get_activity_details` (Tool 2) + `kinetiqo_get_data_coverage` (Tool 9) + `kinetiqo_analyze_workout_structure` (Tool 12); no invented climbs or recovery hours.
8. **"Was today's best five-minute power my personal best this year? Which ride previously held it?"** `kinetiqo_get_personal_records` (Tool 11, [P0]) + `kinetiqo_calculate_power_curve` (Tool 10); require qualifying continuous coverage.
9. **"How did my 5-minute, 20-minute and one-hour powers change versus the previous 90 days?"** `kinetiqo_calculate_power_curve` (Tool 10) for two periods; return source activities and explain incomplete histories.
10. **"Did my power fade during the second half of my ride, or were there more climbs?"** `kinetiqo_analyze_pacing` (Tool 13, [P1]) + GPS/altitude/power coverage; don't attribute terrain without aligned data.
11. **"How did my configured FTP and 20-minute-based estimates change over the past year?"** `kinetiqo_get_ftp_history` (Tool 16); clearly distinguish configuration from estimates and indicate body-weight availability.
12. **"What do my fitness, fatigue and form trends suggest about recent workload? Don't diagnose overtraining."** `kinetiqo_get_fitness_and_freshness` (Tool 15); state suffer-score coverage, method and last computed date.
13. **"Explain the VO₂max trend and whether it may reflect weight changes or a lack of maximal efforts."** `kinetiqo_get_vo2max_trend` (Tool 17) + sanitized profile/coverage; use estimate wording, not a lab measurement.

### Routes, achievements and shareable artifacts (Phases 3–4)

14. **"Find other attempts on my usual Saturday loop and compare the shared portion of each route."** `kinetiqo_find_similar_routes` (Tool 6, [P1]) + `kinetiqo_compare_route_attempts` (Tool 7, [P1]); report uncertain GPS matches and direction changes.
15. **"Show my three longest rides on a map and remove the first and last kilometre of each track before sharing."** `kinetiqo_search_activities` (Tool 1) + `kinetiqo_generate_map_artifact` (Tool 28, [P1]); redact before creating HTML, preview or PNG.
16. **"Where did I climb the most, and where did I produce my longest threshold effort?"** `kinetiqo_get_route_highlights` (Tool 14, [P1]); require aligned timestamped altitude, GPS and power or explain the gap.
17. **"How many qualifying Gran Fondos did I finish this year versus all time? List the rides behind those numbers."** `kinetiqo_get_fondo_milestones` (Tool 22); disclose sport eligibility and distances.
18. **"Which KOMs can be verified locally and when were those data last refreshed?"** `kinetiqo_get_verified_koms` (Tool 20, [P1]); report counts only until segment metadata and freshness are persisted via `verified_segment_efforts`.
19. **"Make a dark 16:9 poster of my longest ride this month, hide my home location and give me a private download reference."** `kinetiqo_search_activities` (Tool 1) + `kinetiqo_get_data_coverage` (Tool 9) + `kinetiqo_generate_activity_poster` (Tool 25, [P1]); choose another basemap if chosen provider is unavailable, retain attribution.

### Deliberate actions (opt-in Phase 4 only)

20. **"Preview the exact Kinetiqo stats block for my latest ride. Do not publish anything."** `kinetiqo_preview_strava_description` (Tool 31); no write; mention any Strava read/quota used.
21. **"Publish the preview I just approved, but stop if the remote Strava description changed."** Preview-bound `kinetiqo_update_strava_description` (Tool 32); reject stale or mismatched preview, preserve manual text.
22. **"Start a fast sync without Strava description updates; tell me whether another job is active and report its final result."** `kinetiqo_trigger_sync` (Tool 29) + `kinetiqo_get_sync_job_status` (Tool 30, [P2]); disabled unless operator opted in.
23. **"What parts of that answer came from my local database, and what required Strava or map-provider requests?"** Use response provenance and artifact/job metadata; never imply complete offline operation.

---

## 13. Feature Implementation & Algorithmic Deep Dives

This is intentionally the **last chapter**. It provides the deep architectural, algorithmic, and backend implementation specifications for the core gap deliverables required across Phases 1–4. The Master Tool Catalog in Section 3 indexes all 33 tools. P0 gaps are required before the read-only analytical MVP is signed off at the end of Phase 2; Phase 1 delivers the foundational repository extensions and initial read tools. P1 and P2 tools are added iteratively upon passing their respective backend-parity tests.

| Priority | Athlete need / missing capability | Tool / deliverable | Implementation details and acceptance rule |
| :--- | :--- | :--- | :--- |
| **P0** | Know why an analysis is unavailable | `kinetiqo_get_data_coverage` (Tool 9) | Per activity/channel first/last timestamp, presence, gap and qualifying sample coverage; distinguish absent, unsynced and zero. Implement bounded repo query in every backend; analysis tools surface these warnings. |
| **P0** | Compare fair training periods | `kinetiqo_compare_periods` (Tool 5) | Sport-filtered count/distance/moving time/elevation and deltas for two explicit periods or equal elapsed days; local timezone and incomplete-period flag. Never divide by zero or treat missing as zero. |
| **P0** | Verify power personal records | `kinetiqo_get_personal_records` (Tool 11) | Duration/sport/period qualifiers, watts, activity/date, W/kg only when weight > 0; require continuous-enough timestamps and return source/coverage. |
| **P0** | Search beyond current filters / retrieve joined streams | Backend repository extensions | Validated name, distance, elevation, time filters (`search_activities`, Tool 1) and bounded multi-channel timestamp-aligned read (`get_activity_stream_window`, Tool 8) in PostgreSQL/MySQL/Firebird; parameterization and parity tests. |
| **P1** | Understand why pace changed | `kinetiqo_analyze_pacing` (Tool 13) | Comparable first/second-half time- or distance-splits, stops, HR/power trends and terrain caveats. Define minimum coverage, distance alignment and drift formula before returning decoupling. |
| **P1** | Know what remains for a goal | Extend `kinetiqo_get_training_goals` (Tool 23) | Compute remaining distance/elevation, remaining calendar weeks, required weekly pace and actual recent pace. Honor currently supported cycling/walking goal categories; no fabricated running goals. |
| **P1** | Compare habitual routes rather than arbitrary activities | `kinetiqo_find_similar_routes` (Tool 6) / `kinetiqo_compare_route_attempts` (Tool 7) | Add GPS matching with tolerance, overlap fraction, direction reversal, matched-section timing and bad-GPS rejection; do not compare unrelated whole activities. |
| **P1** | Locate strongest efforts and climbs | `kinetiqo_get_route_highlights` (Tool 14) | Timestamp-align GPS/altitude/power; document elevation-noise thresholds, location privacy and confidence. Return null rather than fake a marker if channels cannot be aligned. |
| **P1** | Inspect individual held crowns & ribbons | Achievement persistence (`verified_segment_efforts`, Tools 20 & 21) | Current KOM cache contains counts only. Store segment ID/name/effort/activity metadata and refresh time via sync before exposing detailed `kinetiqo_get_verified_koms` and `kinetiqo_get_segment_trophies`. No per-read on-demand Strava call. |
| **P1** | Safely share media | Reusable renderer + artifact registry (Tools 25–28) | Decouple from Flask cookie/web loopback; private ID/expiry/authenticated delivery, quotas, attribution, custom-photo permission and pre-serialization GPS redaction with tests. Dual stdio delivery (inline base64 + local `file:///` URI). |
| **P2** | Understand abrupt training changes | `kinetiqo_get_training_load_trends` (Tool 19) | Rolling volume/intensity changes, data completeness and heuristic warnings, never medical injury/overtraining diagnosis. Keep suffer score separate from TSS. |
| **P2** | Follow and coordinate background sync | `kinetiqo_get_sync_job_status` (Tool 30) / `kinetiqo_trigger_sync` (Tool 29) | Durable `sync_jobs` table, cross-process exclusivity lease, final counts/duration/failure without credentials. Cancellation only if supported safely across workers. |
| **P2** | Broader goal categories and physiological profiles | Goal-mapping/UI/DB + model extension | Add running/swimming goals and precise seven-zone/ten-duration/phenotype models only with documented formulas, sport eligibility, migrations, backend parity and tests. |

### 13.1 Implementation

Implement the thirteen gaps below in priority order, sharing the contracts in Section 5. Every database method mentioned here is added to `src/kinetiqo/db/repository.py` **and** `postgresql.py`, `mysql.py`, `firebird.py`; no ORM or raw SQL from MCP handlers. Pure analysis belongs in independently testable modules, while MCP handlers validate inputs, call services and normalize the response envelope. Do not register a planned tool until its backend-parity tests and edge cases pass. All examples below assume one configured athlete, local-calendar filtering and read-only queries unless explicitly marked as an opt-in write.

#### 12.1.1 Data coverage — `kinetiqo_get_data_coverage` (Tool 9, [P0])

* **Surface:** `kinetiqo_get_data_coverage(activity_id)` returns one record per `watts`, `heartrate`, `cadence`, `altitude`, `latlng`, `speed` and `temp`, with availability (`present`, `absent`, `unknown`), total rows, non-null rows, first/last timestamps, observed gaps and a qualifying-window flag. `latlng` requires **both** lat and lng. Give activity start/end and `moving_time` separately; no inferred 1 Hz guarantee.
* **Source:** Add `get_stream_coverage(activity_id)` to the repository, selecting counts and min/max `ts` per channel for the one activity, plus a bounded/index-assisted gap calculation if needed. The `streams` table has `ts`, `watts`, `heartrate`, `cadence`, `altitude`, `lat`, `lng`, `speed`, `temp`, `distance`, `grade_smooth`, `moving`. Avoid fetching the whole stream just to decide presence. Use `activities.device_watts` / `has_heartrate` only as hints: a flag is **not** proof of stored samples.
* **Semantics:** Define a gap as adjacent timestamp difference >2 seconds for nominal one-second recordings; report `nominal_interval_s` (median positive interval) and threshold used so sparse native sampling is not automatically diagnosed as corrupt. For large recordings, either compute gap counts in backend SQL with a bounded plan or explicitly return `gap_status=unknown`; do not infer complete coverage from non-null count alone. Missing activity is `NOT_FOUND`; zero stream rows is `absent_or_not_synced`, **not** a definite claim the sensor was never used. A recorded 0 W is present data, not absent data. Check invalid/duplicate timestamps and GPS range.
* **Delivery/tests:** Register after all backends agree on null semantics. Add synthetic all-null, no-stream, sparse, paused, zero-power, partially populated GPS and fully populated fixtures. Test single indexed activity query and output size. Consume coverage in workout, map, record and pacing tools rather than duplicating ad hoc checks.

#### 12.1.2 Fair period comparisons — `kinetiqo_compare_periods` (Tool 5, [P0])

* **Surface:** `kinetiqo_compare_periods(period_a, period_b, sport_types=None, align="elapsed_days")` takes two start/end local dates. Expose count, sum distance (km), moving time (s), elevation (m), per-active-day and per-calendar-day averages, absolute differences and percentage changes. Include both resolved UTC half-open ranges, days observed, `as_of`, group mapping and `partial_period` flags.
* **Source:** Reuse `get_activities_totals` and `count_activities` where adequate; add a single aggregate method only if the existing implementations cannot provide correct equivalent date/athlete filters. Query each period with identical sport mapping. Keep stored distance in metres until formatting; convert once at the API boundary. Week starts Monday by default; comparisons of monthly periods offer `elapsed_days` (first N local days of each month, capped by each month's length) or `full_period` rather than shifting a fixed number of seconds across DST.
* **Rules/tests:** Reject overlapping/inverted ranges only when the caller requests disjoint comparison, otherwise label overlap; keep zero counts distinct from missing totals. If baseline is 0 and current >0, percent change is null with an explanatory warning, not infinity. Never compare current incomplete month with a completed month without an elapsed-day label. Test leap day, 28/30/31-day months, DST, UTC fallback, zero denominator, indoor/assisted exclusion and identical sport filters in each backend.

#### 12.1.3 Verified personal power records — `kinetiqo_get_personal_records` (Tool 11, [P0])

* **Surface:** `kinetiqo_get_personal_records(durations=[5,60,300,1200,3600], start_date=None, end_date=None, sport_types=None, activity_id=None)` returns best **qualifying** average watts, ride/date, optional W/kg and qualified ride count per duration; `activity_id` can answer whether one session beat the prior period's record. Cap durations at the Section 5 limit and reject non-positive/outlandish values.
* **Source/correction:** `get_activity_ids_by_types(..., watts_only=True)` identifies candidate rides; `get_best_power_per_activity` is a useful candidate accelerator, **not** an authoritative seconds-based record: PostgreSQL's `ROWS BETWEEN` counts non-null rows after filtering, while MySQL/Firebird `get_watts_streams_for_activities` also drops null watts and timestamps. First add a timestamp-preserving watts-window method or a guarded verified-read path to all three backends. For a window of D seconds require timestamps spanning the specified duration with documented gap tolerance and minimum valid-sample coverage, including the zero-power samples; do not stitch power on either side of a pause/null run. Record the winning window start/end and method/version. Batch candidate IDs to avoid huge Firebird `IN` lists.
* **Rules/tests:** Use **historical** weight only if actually stored; the current profile is a single current weight, so label W/kg as `using_current_weight` or omit it for old records. Include tied bests deterministically (date, then ID) and distinguish all-time from lookback PRs. Verify non-null-row compression does not create a false 20-minute PR; test gaps, zeroes, ties, cross-day activity dates, absent weight and sample intervals other than one second with a Python golden reference.

#### 12.1.4 Repository search and aligned streams (Tools 1 & 8, [P0])

* **Surface:** Introduce `search_activities(filters, limit, cursor)` and `get_activity_stream_window(activity_id, columns, start_ts, end_ts, max_rows)` as repository methods; keep the old `get_activities_web` and watts/GPS methods unchanged for existing UI code. The search tool accepts name, sport list, dates, metric bounds and sort from an allowlist; stream access returns **timestamped rows preserving nulls and GPS alignment**, not independently filtered arrays.
* **SQL/design:** Add allowlisted column projection and sort mapping per backend. Parameterize all search values; escape `%` and `_` in LIKE inputs with an explicit escape character if the query is intended as a literal substring. Use `(sort_metric, start_date, activity_id)` stable order and opaque cursor encoding (server-validated fields, no arbitrary SQL) as defined in Section 5.2. Keep indexes bounded and review plans before adding new ones. For streams select `ts` plus requested stored columns from one activity, ordered by `ts`, with validated time bounds and DB-side row cap; verify duplicate `ts` behavior and add a stable secondary key/schema migration only if duplicates matter. Keep a server-side maximum scan/time and return an explicit `RESOURCE_LIMIT` instead of silently truncating a raw requested window.
* **Tests:** For each backend mock its DB cursor and assert correct placeholders, quoted Firebird identifiers, parameter values, order/limit, substring escaping, null retention, pagination ties and malformed cursor rejection. Test missing stream, unknown column, invalid athlete access, oversize range and clean cursor/connection close on error. Do not treat GPS display simplification (`gps_simplify.py`) as a telemetry sampling algorithm: it drops time alignment.

#### 12.1.5 Session pacing — `kinetiqo_analyze_pacing` (Tool 13, [P1])

* **Surface:** Take an activity ID, optional split basis (`moving_time` or `distance`) and 2–10 splits. Return each split's actual start/end time, distance/elevation gain if present, average power/HR if present, speed, stopped time and valid sample counts; provide first-vs-second-half percentage difference for comparable halves. Do not call higher HR at the same power “fatigue” without a defined method and minimum coverage.
* **Engine:** Create `kinetiqo/mcp/analysis/pacing.py` as a pure calculation over the aligned stream method. Filter timestamp deltas/`moving` flags according to a stated policy; boundaries use cumulative **moving** duration or stored cumulative distance rather than arbitrary array halves. If cumulative distance is absent, compute GPS haversine distance as a separate, flagged fallback with impossible-jump rejection. For optional aerobic decoupling use `(power_w / HR_bpm)` first versus second comparable *moving* half with both HR and power available, enforce positive HR and at least 80% paired coverage in each half, and return the exact formula and direction convention. Do not mix climbs/descents into a causal explanation from summary power alone.
* **Tests:** Constant power/HR, uphill second half, stop, irregular timestamps, distance reset/jump, indoor no GPS, missing HR and uneven paired coverage; assert no drift conclusion on insufficient pairs. Avoid concatenating multiple activities with different sensors.

#### 12.1.6 Goal pacing — extend `kinetiqo_get_training_goals` (Tool 23, [P1])

* **Surface:** For each configured weekly/monthly/yearly distance/elevation target, return `target`, `actual`, `remaining=max(0,target-actual)`, `percent`, days remaining (including today's remaining calendar period), recent pace and `required_per_remaining_week`; mark complete/unset goals. User-configurable sport group must map to supported `GOAL_TYPE_CYCLING` or `GOAL_TYPE_WALKING`, not silently route running to walking.
* **Source:** Read `get_profile` for athlete ID, `get_goals(athlete_id)`, and `get_activities_totals` for matching mapped sport types and local period bounds; use `STRAVA_TYPE_TO_GOAL_TYPE` and keep group selection consistent with `web/stats.py`. Share a pure goal-pacing calculator with any web endpoint if needed, not a copy of its display logic. Compute actual totals for each period independently; a weekly target does not reset at the start of the year. Use an explicit convention for remaining fractional week: divide by remaining calendar days/7 (clamp at one day for end-of-period advice), disclose the convention and do not imply a prediction of performance.
* **Tests:** Unset/zero goals, exceeded goal, Monday/Sunday boundary, DST, last day of month, Dec 31, walking vs cycling overlap, elevation-only target and environment/profile precedence for changed goals. Write tools remain separately gated.

#### 12.1.7 Similar routes — `kinetiqo_find_similar_routes` and `kinetiqo_compare_route_attempts` (Tools 6 & 7, [P1])

* **Surface:** Input one source activity ID and sport/date filters; find bounded candidate IDs, then return score, direction (`same`, `reverse`, `partial`), matched distance/percentage, start/end of common section and GPS confidence. Comparison returns elapsed **and moving** seconds for the matched section, not whole-session speed when routes differ.
* **Engine:** Filter candidate records by approximate GPS bounding boxes and route length *before* reading GPS streams. Use timestamped GPS points from the new repository method, remove invalid coordinates/outliers and resample along cumulative geographic distance (e.g. every 100 m). An MVP matching algorithm can use endpoint proximity and a symmetric, distance-weighted nearest-track/ordered overlap score within a configurable tolerance (initial candidate: 100 m); handle reverse direction explicitly and demand e.g. >=70% overlap for a full-route match. For precise matched-section time, project matched endpoints back onto original timestamped points; reject ambiguous crossings, loops, sparse GPS and huge detours as `partial`/uncertain. `simplify_track()` is for display only and must not be used to time attempts. Cap candidate count/points and cache derived GPS signatures with a version and invalidation on resync/deletion.
* **Tests:** Same route, reversed route, shifted GPS, loop, short shared tail, indoor ride, sparse/teleporting track, stop on route and mismatched distances; test stable scores/tolerances on synthetic tracks and avoid claiming exact segment performance when overlap confidence is low.

#### 12.1.8 Route highlights — `kinetiqo_get_route_highlights` (Tool 14, [P1])

* **Surface:** For one activity ID return top climbs and supported peak efforts as timestamp ranges, distance range and optional redacted map markers; include method and confidence. Callers can request `hide_start_end_km`, which clips the **entire returned route-linked data** before highlights are selected to avoid leaking private endpoints.
* **Engine:** Load aligned timestamped GPS/altitude/power/distance and reject impossible coordinates and altitude spikes. Smooth altitude with a documented rolling distance window (start with 100–200 m, then benchmark) and find monotonically rising candidates with minimum elevation gain and length; group brief dips using defined merge rules. Reuse verified, time-continuous power-window computation for 1m/5m/20m highlights rather than scanning a downsampled map track. Associate event midpoints with GPS only if time gap to a GPS fix is bounded; otherwise return times but null coordinates. Apply location clipping *first*, then derive highlights, before writing caches/HTML or returning JSON.
* **Tests:** No-GPS indoor effort, altitude sawtooth, tunnel gap, overlapping climbs, peak during stop, GPS/power clocks offset, private start/end peak and null marker on sparse GPS; no raw clipped points must leak in nested result fields.

#### 12.1.9 Segment-level KOM & trophy provenance — `kinetiqo_get_verified_koms` / `kinetiqo_get_segment_trophies` (Tools 20 & 21, [P1])

* **Surface:** Until this lands, `kinetiqo_get_verified_koms` (Tool 20) returns counts only. Once enabled, add `segment_id`, segment name, effort ID, activity ID, awarded rank, observed_at and last_verified_at (where provider data actually supports them). Distinguish a crown **currently held** from a historical rank-1 effort; do not equate cached trophy rank 1 to a currently held KOM. Tool 21 (`kinetiqo_get_segment_trophies`) surfaces podium ranks (1-3) and top-10 ribbons.
* **Persistence & Schema:** Extend `koms.py` sync-time verification (`load_verified_koms` currently maps activity IDs to integer counts), and add the new `verified_segment_efforts` table declared in Section 5.3 (`SCHEMA_DEFINITION["verified_segment_efforts"]` supporting PostgreSQL, MySQL, and Firebird) with primary key `(athlete_id, segment_id, effort_id)`, activity/date, rank, and refresh timestamp. Implement repository reads/writes in all three backends and define reconciliation: on a completed full crown fetch, mark older no-longer-listed crowns not-current; on partial/failed fetch, keep previous values but mark them stale. Minimize provider calls by using the existing sync/scan flows, not an MCP read-time Strava request. Review Strava's actual response fields before final schema; missing gradient/elevation is null.
* **Tests:** Missing/partial cache, revoked crown after complete refresh, failed refresh retaining stale record, duplicate effort, tombstoned activity, rank-1 ribbon without verified crown and date/year filter; mocked Strava only, no live calls.

#### 12.1.10 Reusable media renderer and private artifacts (Tools 25–28, [P1])

* **Surface:** `kinetiqo_generate_*` returns artifact ID, MIME type, byte size/dimensions, expiry, dual stdio delivery (`file:///` URI + inline base64 WebP), or authenticated HTTP download URL as defined in Section 3 (Group E). Authorized same-athlete clients only; no public source-tree files or unrestricted base64 dumps.
* **Refactor:** Existing poster, stats and fondo exports live inside `web/app.py` and browse authenticated pages with Flask session cookies. Extract layout generation, browser launch, template synthesis, screenshot/PDF and cleanup into shared `web/renderers/` functions used by both Flask routes and MCP. Headless Playwright uses **in-process HTML synthesis (`page.set_content(html, wait_until="networkidle")`)** with Jinja2 templates, injecting data, SVG assets, and self-hosted CSS directly. This completely eliminates any dependence on an active Flask HTTP server, local port binding, or browser session cookies, enabling standalone stdio rendering. Use existing local fonts and vendor assets; preserve map attribution and avoid exposing tile keys or loading arbitrary untrusted network URLs. Keep web export behavior stable while adding MCP.
* **Artifact store:** Use a configured directory outside served static files, random opaque IDs, owner ID, MIME, expiry and size/total-quota records; atomic write, max concurrent Chromium processes, timeout, cleanup on failures and periodic expiration. For HTTP delivery enforce authentication and prevent path traversal/symlinks. For maps, redact first/last distance from the raw geometry **before** any simplification, caching, HTML generation, download or screenshot; for photo mode verify ownership of cached uploaded image.
* **Tests:** Mock browser/context/pages and provider availability; timeout/cancel cleans resources; expired/other-owner ID denied; route redaction checked in output bytes, not just preview; malformed colors, large dimensions, missing Chromium, no GPS and unavailable basemap receive safe errors/fallbacks. Do not demand a live browser in the default unit suite.

#### 12.1.11 Training load trends — `kinetiqo_get_training_load_trends` (Tool 19, [P2])

* **Surface:** Return per-sport weekly distance/time/elevation, optional recorded suffer-score total, rolling 7/28-day volumes and week-over-week changes with coverage and `method`. Words such as `increased` or `decreased` are descriptions, not diagnoses or individualized injury probabilities.
* **Source/engine:** Add a bounded date/sport aggregate repository query if `get_activities_totals` per day would cause N+1 calls. Use **all** matching activities for volume; `get_activities_with_suffer_score` alone omits workouts without scores. Produce daily zero-activity buckets in athlete local time. Keep suffer score and computed TSS as separately labeled axes and never sum or compare them as equal units. If baseline is zero, provide null ratio and an absolute change. Optional heuristics (e.g. >30% increase) must be documented as arbitrary review thresholds, never evidence of injury risk.
* **Tests:** Unscored rides, zero prior week, multisport mix, 7/28-day window warm-up, timezone rollover, incomplete current week and missing activities; ensure warnings appear when no representative history exists.

#### 12.1.12 Sync job state and coordination — `kinetiqo_get_sync_job_status` / `kinetiqo_trigger_sync` (Tools 29 & 30, [P2])

* **Surface:** `kinetiqo_trigger_sync` (Tool 29, opt-in) accepts `sync_type` (`fast` or `full`); `lookback_period` is allowed **only** for full sync and uses existing CLI `parse_period` semantics. Returns a job ID immediately (`202 Accepted`). `kinetiqo_get_sync_job_status(job_id)` (Tool 30) exposes `queued`, `running`, `completed`, `failed` or `cancelled`, timestamps, safe count summary and last error class. Cancellation is a separate optional mutating tool, not an implicit status side effect.
* **Coordinator & Schema:** Use the durable repository-backed `sync_jobs` table declared in Section 5.3 (`SCHEMA_DEFINITION["sync_jobs"]` supporting PostgreSQL, MySQL, and Firebird) with lease ownership (`worker_id`, `lease_expires_at`), heartbeat updates, and cross-process locking shared by MCP, cron, CLI, and web. This requires modifying existing sync entry points (`src/kinetiqo/sync.py`), not only the MCP wrapper. Lease has owner/expiry/heartbeat; recovers after process death without overlapping an existing live worker. Run `SyncService.sync(...)` to exhaustion in a bounded worker, default `update_strava=False`, and always call `close()`; avoid holding a DB transaction for the full network sync. Persist progress minimally and strip secrets, descriptions and raw exception bodies from job records. Full sync may reconcile deletions; require an explicit acknowledgment. If existing web stop-signal behavior is reused, document its global/process semantics and do **not** promise per-job cancellation without validating them.
* **Tests:** Simulated two-process lock contention, heartbeat expiry/restart, duplicate job request, fast+period rejection, no Strava write by default, generator failure/cleanup, progress and final counts, stop request during active job, ownership checks and redacted failure. Keep Strava and worker scheduler mocked.

#### 12.1.13 More goal sports and richer power profiles (Tools 18 & 24, [P2])

* **Goal extension:** `STRAVA_TYPE_TO_GOAL_TYPE` in `db/repository.py` currently maps cycling and walking; `activity_goals` stores integer type IDs, so add new stable IDs for running/swimming (do **not** reuse ID 2), update group mappings, profile/settings UI/API and all three backends only where contract/schema changes are needed. Backfill must preserve existing `(athlete_id, activity_type_id)` goals. Document virtual runs, trail runs and mixed sport filtering; validate targets and clear/unset operations. Keep six Strava description template buckets a separate concept from goal groups.
* **Power extension:** Current `workout_summary.get_power_zone_name` returns six named buckets, while the UI advertises seven Power Skills durations. To offer Coggan seven zones, specify non-overlapping FTP percentage boundaries including anaerobic/neuromuscular, exact edge inclusion and behavior when FTP is unset. Add 10s, 2m and 30m to the existing 5s/30s/1m/5m/10m/20m/1h Power Skills benchmark set using validated continuous-window power. Rider phenotype is optional: define transparent duration-normalized thresholds and cohort/weight caveats; do not present categorical type without evidence. Never overwrite configured FTP with an estimate.
* **Tests:** Existing two goal IDs and data unchanged after migration; new sports affect only correct totals, including indoor/virtual mappings. Test zone boundaries (exact threshold and ±epsilon), missing FTP, each power duration, gapped streams, absent weight and no phenotype when insufficient qualifying windows. Refresh relevant UI/docs and backend contract tests before advertising either capability.

**Cross-feature dependency order:** 12.1.4 (repository) and 12.1.1 (coverage) underpin 12.1.3, 12.1.5, 12.1.7 and 12.1.8; 12.1.2 can follow repository search; 12.1.6 depends on goal mapping; 12.1.9 depends on sync persistence; 12.1.10 depends on renderer extraction; 12.1.12 requires cross-process changes to *all* sync entry points. Implement and test the dependencies first, then register downstream MCP tools. Each delivered subsection needs unit tests matching Section 9 and corresponding documentation/client examples.

**Out-of-scope until a separate product decision:** Public unauthenticated MCP access, arbitrary full Strava-description replacement, raw SQL, arbitrary code/templates or file paths, athlete activity deletion, medical diagnosis, guaranteed recovery hours, and automatic transmission of GPS to a third-party model without a clear privacy disclosure.
