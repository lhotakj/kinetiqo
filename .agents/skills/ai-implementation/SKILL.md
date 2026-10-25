---
name: ai-implementation
description: Architecture, contracts, gotchas, repository signatures, and multi-provider guidelines for Kinetiqo AI Chat and MCP tools.
---

# Kinetiqo AI Chat & MCP Tools Implementation Guide

This skill documents the complete forensic architecture, contracts, database repository quirks, gotchas, and implementation patterns for the Kinetiqo AI Chat system and FastMCP tools layer. It serves as the authoritative technical reference for current and future AI provider adapters (Gemini, OpenAI, Anthropic, Mistral, Ollama/Local).

---

## 1. AI Chat Architecture & Provider Model

Kinetiqo integrates an authenticated, in-browser AI Chat page (`/chat`) allowing athletes to ask natural language questions about their training history, power data, fitness trends, and visual artifacts.

### 1.1 Core Principles
- **Provider-Neutral Core**: Provider-specific request and response formats stay inside their respective adapters (`src/kinetiqo/chat/providers/`).
- **In-Process MCP Execution**: Chat tools are executed in-process without requiring a separate MCP daemon, network sockets, or STDIO subprocesses.
- **Strict Read-Only Gating**: Mutating operations (sync triggers, description updates, profile writes) are strictly excluded from AI Chat tool calling.
- **Zero Hallucination Grounding**: Tool envelopes provide structured local facts. The assistant must state measured values versus estimates and disclose missing sensors.
- **Bounded Context**: Responses are bounded via `_bound_tool_payload()` to prevent token blowout.

### 1.2 In-Process Tool Execution Pipeline
```
Athlete Prompt (/chat)
    │
    ▼
ChatService / Provider Adapter (e.g. Gemini, OpenAI)
    │
    ▼
get_chat_tools(provider="gemini" | "openai" | "mistral")
    │  (Dynamic discovery from create_mcp_server, filtering MUTATING_TOOL_NAMES)
    ▼
Model issues tool call: e.g. kinetiqo_get_ftp_history()
    │
    ▼
execute_chat_tool(repo, tool_name, arguments, config)
    │
    ▼
FastMCP server.call_tool() -> MCP Tool Handler -> DatabaseRepository
    │
    ▼
JSON Envelope Response -> Provider Adapter Turn -> Streaming SSE back to Web GUI
```

---

## 2. Database Repository Gotchas & Forensic Signatures (CRITICAL)

When writing or modifying MCP tools, chat helpers, or AI integrations, you must strictly respect the concrete `DatabaseRepository` interface (`src/kinetiqo/db/repository.py`) across all three backends (**PostgreSQL**, **MySQL**, and **Firebird**).

### Gotcha 1: `repo.get_profile()` Takes ZERO Positional Arguments
- **The Bug**: Calling `repo.get_profile(athlete_id)` raises:
  ```text
  TypeError: DatabaseRepository.get_profile() takes 1 positional argument but 2 were given
  ```
  In MCP tools wrapped in `try...except Exception`, this immediately triggers `create_error_envelope(ERROR_INVALID_ARGUMENT, ...)` in 0.000s, or silently zeroes out `weight` and `ftp`.
- **The Repository Contract**:
  ```python
  @abstractmethod
  def get_profile(self) -> Optional[Dict[str, Any]]:
  ```
- **Approved Pattern**:
  ```python
  try:
      profile = repo.get_profile() or {}
  except TypeError:
      # Defensive fallback for test mocks that mistakenly declared get_profile(athlete_id)
      profile = repo.get_profile(athlete_id) or {}
  ```
- **Profile Dictionary Keys**:
  `athlete_id`, `first_name`, `last_name`, `weight`, `ftp`, `gps_simplification`, `refresh_token`, and the six `update_strava_*` template fields.

---

### Gotcha 2: `repo.get_activity_ids_by_types(...)` Returns Dicts, NOT IDs
- **The Bug**: Treating `repo.get_activity_ids_by_types(...)` as a list of ID strings or ints (e.g. passing them directly to `get_best_power_per_activity`) causes SQL syntax errors or slicing failures.
- **The Repository Contract**:
  Returns a `List[Dict[str, Any]]` where each item has keys:
  ```python
  {"id": <activity_id>, "name": <activity_name>, "start_date": <iso_or_datetime>}
  ```
- **Approved Pattern**:
  Use `extract_activity_summaries()` from `kinetiqo.mcp.utils`:
  ```python
  from kinetiqo.mcp.utils import extract_activity_summaries

  raw_acts = repo.get_activity_ids_by_types(types=["Ride", "VirtualRide"], watts_only=True) or []
  summaries = extract_activity_summaries(raw_acts)
  str_ids = [s["id"] for s in summaries]
  ```

---

### Gotcha 3: `repo.get_best_power_per_activity` Takes a Single Scalar Duration
- **The Bug**: Passing a `List[int]` (e.g. `durations=[5, 30, 60]`) to `repo.get_best_power_per_activity(activity_ids, durations)` breaks:
  - In PostgreSQL: breaks the SQL window function `AVG(watts) OVER (ROWS BETWEEN {rows_back} PRECEDING)`.
  - In MySQL / Firebird: causes `TypeError` in sliding-window calculations.
- **The Repository Contract**:
  ```python
  @abstractmethod
  def get_best_power_per_activity(
      self,
      activity_ids: List[str],
      duration_seconds: int,
      min_total_samples: int = 0,
  ) -> Dict[str, float]:
  ```
- **Approved Pattern**:
  Use the utilities in `kinetiqo.mcp.utils`:
  - Single duration: `get_best_power_for_single_duration(repo, str_ids[:150], 1200)`
  - Multiple durations: `get_best_powers_for_durations(repo, str_ids[:150], [5, 60, 300, 1200])` (iterates per-duration against production DBs while handling multi-duration mock returns gracefully).

---

### Gotcha 4: `repo.get_activities_totals` Returns `total_*` Prefixed Keys
- **The Bug**: Reading `totals.get("distance")` or `totals.get("elevation")` yields `None`, causing totals and period comparisons to report `0.0` distance and elevation against real databases.
- **The Repository Contract**:
  PostgreSQL, MySQL, and Firebird return:
  ```python
  {
      "total_distance": float,      # in meters
      "total_elevation": float,     # in meters
      "total_moving_time": int,     # in seconds
  }
  ```
- **Approved Pattern**:
  ```python
  dist_m = float(totals.get("total_distance") or totals.get("distance") or 0.0)
  elev_m = float(totals.get("total_elevation") or totals.get("elevation") or 0.0)
  mov_s = float(totals.get("total_moving_time") or totals.get("moving_time") or 0.0)
  ```

---

### Gotcha 5: Training Goals Schema & `upsert_goal`
- **The Bug**: Expecting `repo.get_goals()` to return `{"period": "weekly", "metric": "distance", "target": 100}` or calling non-existent `repo.set_goal()`.
- **The Repository Contract**:
  Rows in `get_goals(athlete_id)` are structured by `activity_type_id` (`1` = Cycling, `2` = Walking):
  ```python
  {
      "activity_type_id": 1,
      "weekly_distance_goal": float | None,
      "monthly_distance_goal": float | None,
      "yearly_distance_goal": float | None,
      "weekly_elevation_goal": float | None,
      "monthly_elevation_goal": float | None,
      "yearly_elevation_goal": float | None,
  }
  ```
  Updating goals MUST use:
  ```python
  repo.upsert_goal(
      athlete_id,
      activity_type_id,
      weekly_distance_goal,
      monthly_distance_goal,
      yearly_distance_goal,
      weekly_elevation_goal,
      monthly_elevation_goal,
      yearly_elevation_goal,
  )
  ```

---

### Gotcha 6: Profile Updates Must Use `upsert_profile`
- **The Bug**: Calling `repo.update_profile(updates)`. No such method exists on `DatabaseRepository`.
- **The Repository Contract**:
  Use `repo.upsert_profile(...)` while preserving existing attributes:
  ```python
  existing = repo.get_profile() or {}
  repo.upsert_profile(
      athlete_id=int(existing.get("athlete_id") or 1),
      first_name=str(existing.get("first_name") or ""),
      last_name=str(existing.get("last_name") or ""),
      weight=float(updates.get("weight", existing.get("weight", 70.0))),
      refresh_token=existing.get("refresh_token", "") or "",
      ftp=updates.get("ftp", existing.get("ftp")),
      gps_simplification=int(existing.get("gps_simplification", 0)),
      **preserved_templates,
  )
  ```

---

### Gotcha 7: Multi-Turn Tool Looping & Silent Stream Termination
- **The Bug**: For complex multi-year queries (e.g. "what was my absolute best year in terms of kilometers ridden"), models (Gemini, Claude, GPT) issue sequential tool calls year-by-year across 8+ turns. If the adapter loop limit (`max_turns`) is low or ends after a tool execution round, the stream loop exits with 0 text events, appearing to the user as a frozen/unresponsive chat.
- **The Protocol**:
  1. Set `max_turns = 16` to provide sufficient headroom for multi-year queries.
  2. On the penultimate/final turn (`turn_idx == max_turns - 1`), omit tool declarations so the model is forced to synthesize its final answer using the collected data.
  3. Implement a safety fallback: if the loop exits and `not any_text_streamed`, make one synthesis request with tools omitted to guarantee an answer is returned.

---

### Gotcha 8: Cycling Activity Taxonomy & Incomplete Distance Sums
- **The Bug**: When an athlete asks "how much did I ride this year" or "what was my best year in km ridden", AI models naturally generate queries with `sport_types=['Ride']`. In Strava and Kinetiqo, cycling is split across multiple sport types: `Ride`, `VirtualRide` (indoor Zwift, Rouvy), `GravelRide`, `MountainBikeRide`, `EBikeRide`, etc. Querying only `['Ride']` excludes all virtual and gravel training, causing severe mileage and elevation undercounts.
- **The Protocol**:
  1. System instruction specifies the Sport Taxonomy Mandate: biking queries must encompass `['Ride', 'VirtualRide', 'GravelRide', 'MountainBikeRide', 'EBikeRide', 'EMountainBikeRide', 'Velomobile', 'Handcycle']`.
  2. The normalization utility `normalize_sport_types()` in `src/kinetiqo/mcp/utils.py` automatically expands shorthand sport filters like `['cycling']`, `['bike']`, or single `['Ride']` queries to include all biking activities.

---

### Gotcha 9: Flask Streaming Teardown & Lazy DB Reconnection
- **The Bug**: When returning a streaming generator from a Flask view, Flask pops the application context as soon as the view function returns, closing `g.db_repo`. When the stream generator begins and issues an MCP tool query, the repository is closed, forcing a reconnect and logging `[WARNING] PostgreSQL connection lost, reconnecting...`.
- **The Protocol**:
  1. Wrap streaming generators with `Response(stream_with_context(generate()), mimetype='text/event-stream')` to keep the application context active until the stream finishes.
  2. In `PostgresqlRepository._ensure_connected()`, if `self.conn is None`, connect cleanly without emitting false-alarm "connection lost" warnings.

---

### Gotcha 10: Activity Search Keyword vs Query Discrepancy
- **The Bug**: `kinetiqo_search_activities` accepts `query: Optional[str]`, but database repositories historically checked `filters.get("keyword")`. This caused title/keyword searches (e.g. searching for activities with specific names, routes, or people like "Jonas") to be completely omitted from the SQL WHERE clause. The repository fell back to returning the first `limit` rows (the 20 most recent activities) without name filtering, leading AI models to conclude zero matching records exist.
- **The Protocol**:
  1. In `kinetiqo_search_activities`, assign both `filters["query"]` and `filters["keyword"]`.
  2. In `search_activities` across all concrete repository backends (PostgreSQL, MySQL, Firebird), check `keyword = filters.get("keyword") or filters.get("query")`.
  3. Support both `min_distance` (meters) and `min_distance_km` (kilometers), as well as `min_elevation` and `min_elevation_m`.



---

## 3. Complete MCP Tool Inventory (31 Tools)

| Group | Tool Name | Scope | Primary Arguments | Data Source |
|---|---|---|---|---|
| **A: Activities** | `kinetiqo_search_activities` | Read | `query`, `sport_types`, `start_date`, `end_date`, `min_distance_km`, `max_distance_km`, `min_elevation_m`, `max_elevation_m`, `cursor`, `limit`, `sort_by` | Local DB |
| | `kinetiqo_get_activity_details` | Read | `activity_id` | Local DB |
| | `kinetiqo_get_activity_totals` | Read | `sport_types`, `start_date`, `end_date` | Local DB |
| | `kinetiqo_compare_activities` | Read | `activity_ids` (2 to 5 IDs) | Local DB |
| | `kinetiqo_compare_periods` | Read | `period_a`, `period_b`, `sport_types`, `align` | Calculated |
| | `kinetiqo_find_similar_routes` | Read | `activity_id`, `sport_types`, `max_candidates` | Calculated |
| | `kinetiqo_compare_route_attempts` | Read | `source_activity_id`, `target_activity_id` | Calculated |
| **B: Telemetry** | `kinetiqo_get_activity_streams` | Read | `activity_id`, `stream_types`, `resolution` | Local DB |
| | `kinetiqo_get_data_coverage` | Read | `activity_id` | Local DB |
| | `kinetiqo_calculate_power_curve` | Read | `activity_id`, `days`, `durations` | Calculated |
| | `kinetiqo_get_personal_records` | Read | `durations`, `sport_types`, `start_date`, `end_date` | Calculated |
| | `kinetiqo_analyze_workout_structure` | Read | `activity_id`, `athlete_ftp` | Calculated |
| | `kinetiqo_analyze_pacing` | Read | `activity_id`, `split_basis`, `num_splits` | Calculated |
| | `kinetiqo_get_route_highlights` | Read | `activity_id`, `hide_start_end_km` | Calculated |
| **C: Physiology** | `kinetiqo_get_fitness_and_freshness` | Read | `period_days`, `warmup_days` | Calculated |
| | `kinetiqo_get_ftp_history` | Read | *(none / athlete_id)* | Calculated |
| | `kinetiqo_get_vo2max_trend` | Read | `days` | Calculated |
| | `kinetiqo_get_power_skills` | Read | *(none / athlete_id)* | Calculated |
| | `kinetiqo_get_training_load_trends` | Read | `weeks` | Calculated |
| | `kinetiqo_get_weekly_training_profile`| Read | `year`, `weeks`, `sport_types` | Calculated |
| | `kinetiqo_analyze_recovery_turnaround`| Read | `min_distance_km`, `sport_group`, `lookback_days`| Calculated |
| **D: Achievements**| `kinetiqo_get_verified_koms` | Read | *(none / athlete_id)* | Local Cache |
| | `kinetiqo_get_segment_trophies` | Read | *(none / athlete_id)* | Local Cache |
| | `kinetiqo_get_fondo_milestones` | Read | `sport_group`, `year` | Calculated |
| | `kinetiqo_get_training_goals` | Read | *(none / athlete_id)* | Local DB |
| | `kinetiqo_update_training_goals` | Write | `period`, `goal_type`, `target`, `metric` | Gated Profile |
| **E: Generation** | `kinetiqo_generate_activity_poster` | Visual | `activity_id`, `ratio`, `map_provider`, `route_color`, `font_family`, `hide_start_end_km` | Rendered (PNG) |
| | `kinetiqo_generate_mega_stats_infographic` | Visual | `year`, `sport_group`, `font_family` | Rendered (PNG) |
| | `kinetiqo_generate_fondo_infographic` | Visual | `year`, `sport_group`, `arc_color` | Rendered (PNG) |
| | `kinetiqo_generate_map_artifact` | Visual | `activity_id`, `map_provider`, `route_color`, `hide_start_end_km` | Rendered (PNG) |
| **F: Operations** | `kinetiqo_get_sync_job_status` | Read | `job_id` | Local DB |
| | `kinetiqo_preview_strava_description` | Read | `activity_id` | Calculated |
| | `kinetiqo_trigger_sync` | Mutate | `sync_type`, `full_sync_ack` | Gated Sync |
| | `kinetiqo_update_strava_description` | Mutate | `activity_id`, `preview_id` | Gated Strava |
| | `kinetiqo_update_athlete_profile` | Mutate | `weight_kg`, `ftp_watts` | Gated Profile |

---

## 4. Multi-Provider Schema Translation Standards

When implementing or extending AI provider adapters:

### 4.1 Gemini Function Declarations & Multi-Turn Protocol
- Uses uppercase types: `STRING`, `INTEGER`, `NUMBER`, `BOOLEAN`, `ARRAY`, `OBJECT`.
- Handles `anyOf: [type, null]` Pydantic schemas by unwrapping the non-null type branch.
- Formatted via `to_gemini_schema(prop)` in `src/kinetiqo/chat/tools.py`.
- **Function Response Role Mandate**: In multi-turn chat turns, Gemini API strictly requires `"role": "user"` for content objects containing `functionResponse`. Passing `"role": "function"` or `"role": "tool"` causes an immediate HTTP 400 `INVALID_ARGUMENT`. Model turns preceding the response must cleanly contain only the `functionCall` parts without empty text or thought tokens.

### 4.2 OpenAI / OpenRouter / Mistral Function Declarations
- Uses standard JSON Schema with lowercase types: `string`, `integer`, `number`, `boolean`, `array`, `object`.
- Wrapped in `{ "type": "function", "function": { "name": ..., "description": ..., "parameters": ... } }`.
- Formatted via `to_openai_schema(prop)` in `src/kinetiqo/chat/tools.py`.
- OpenRouter uses base URL `https://openrouter.ai/api/v1/chat/completions` with headers `HTTP-Referer: https://github.com/lhotakj/kinetiqo` and `X-Title: Kinetiqo`.
- OpenRouter models are validated and detailed via `GET https://openrouter.ai/api/v1/model/{author}/{slug}`.

### 4.3 Anthropic Claude Tool Declarations
- Direct `{ "name": name, "description": description, "input_schema": parameters }` structure.

---

## 5. Mandatory Documentation Synchronization (CRITICAL)

Whenever an agent touches AI features, providers, MCP tools, prompts, or settings:
- **`docs/concepts/ai-concept.md`** MUST be updated to reflect current technical contracts, schema definitions, and roadmap phases.
- **`docs/AI.md`** MUST be updated to reflect user-facing features, configuration workflows, and tool capabilities.
- Refer to `.agents/skills/sync-ai-documentation/SKILL.md` for the full synchronization checklist.

---

## 6. Testing & Verification Rules

1. **Always Mock External Boundaries**: Never invoke live Strava endpoints or require a running database server in unit tests.
2. **Test Real Repository Signatures**: Ensure test mocks replicate the actual parameter counts (e.g. `get_profile()` with 0 args, `get_best_power_per_activity` with integer duration).
3. **Run Execution Commands**:
   - `python -m pytest -o pythonpath=src tests/test_mcp_tools.py tests/test_chat_tools.py tests/test_mcp_server.py`
   - `python -m unittest discover -s tests -v` (with `PYTHONPATH=src`)

