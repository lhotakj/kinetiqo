# Implementation Plan: AI Agent Placeholder for Strava Activity Descriptions (`{{ai-agent}}`)

> **Status: Implemented & Verified** (All components implemented, 19 unit tests passing, zero regressions across 104 existing tests).

## 1. Executive Summary & Objective

This feature allows athletes to personalize their automated Strava activity descriptions using custom AI-generated content. By placing the `{{ai-agent}}` token in any of the six sport description templates, Kinetiqo will prompt the athlete's configured AI model (Gemini, OpenRouter, Vercel, Kilo, or Ollama) with their custom prompt and activity stats, cache the response in the local database to eliminate duplicate API calls and prevent rate limits, and push the final rendered text to Strava.

---

## 2. Key Architectural Decisions & Scoping

| Area | Decision | Rationale |
|---|---|---|
| **Target Field** | Strava Activity Descriptions Only (Option A resolved) | Scoped strictly to the 6 sport description templates (`UPDATE_STRAVA_*`). Activity title renaming is excluded. |
| **Variable Token** | `{{ai-agent}}` | Matches existing placeholder syntax (e.g. `{{current-month}}`, `{{workout-summary}}`). |
| **Extensibility** | JSON dictionary structure `{"ai-agent": "response text"}` | Enables future expansion to multiple agent variables (e.g. `{{ai-summary}}`, `{{ai-coach}}`, `{{ai-haiku}}`) without schema migrations. |
| **API Optimization & Cache** | Run once on first sync, cache in database; manual purge available (Option B resolved) | Zero unexpected API calls during routine syncs. Athletes can selectively purge cached AI analysis to regenerate when desired. |
| **Grid Integration** | New "AI Analysis" column in Activities table + ColReorder support | Visible in DataTables grid, manageable in "Select Columns" popup, persisted in `localStorage` with `activities_schema_v7` migration. |
| **Cache Purge Control** | "Purge AI Analysis" action button with AI sparkle icon | Allows athlete to invalidate cached AI responses for selected activities and trigger fresh generation on next sync. |
| **Error Handling** | Fail-safe: Skip token on AI error, log single-line warning, do not crash sync | If the AI service fails or times out, the rest of the template renders normally and Strava sync continues uninterrupted. |
| **Fallback Models** | Automatically uses configured primary model, falling back to up to 3 models | Leverages existing `ChatRepository.get_fallback_models()` infrastructure. |
| **Security & Privacy** | Prompt executed securely server-side; API keys encrypted in DB | Athlete's encrypted keys from Chat Settings are reused; no new credentials required. |
| **Athlete ID Resolution** | Dual-identity bridging (`ChatRepository.resolve_athlete_id`) | Resolves discrepancy between web login owner (e.g. `admin` / `WEB_LOGIN`) holding AI keys/models and sync's numeric Strava `athlete_id`. |

---

## 3. Database Schema & Repository Updates

### 3.1 Schema Additions (`src/kinetiqo/db/schema.py`)
1. **`activities` Table**:
   - Add column `ai_responses`:
     - PostgreSQL: `TEXT`
     - MySQL: `TEXT`
     - Firebird: `BLOB SUB_TYPE TEXT`
   - Stores serialized JSON dictionary mapping variable token names to their generated string responses (e.g. `'{"ai-agent": "Solid tempo ride with strong surges on the hills!"}'`).

2. **`profile` Table**:
   - Add column `agent_prompt`:
     - PostgreSQL: `TEXT`
     - MySQL: `TEXT`
     - Firebird: `BLOB SUB_TYPE TEXT`
   - Stores the athlete's custom prompt instruction configured in Settings.

### 3.2 Repository Methods (`src/kinetiqo/db/repository.py` & Backends)
Update `DatabaseRepository` interface and concrete implementations (`postgresql.py`, `mysql.py`, `firebird.py`):
- `update_activity_ai_responses(activity_id: Any, ai_responses: Dict[str, str]) -> None`
- `purge_activities_ai_responses(activity_ids: List[Any]) -> None`
- Update `get_profile()` and `upsert_profile()` to include `agent_prompt`.
- Update `write_activity()`, `get_activities_web()`, and activity select queries to load and persist `ai_responses`.

---

## 4. Configuration & Profile Sync

1. **`src/kinetiqo/config.py`**:
   - Add `agent_prompt: str = os.getenv("KINETIQO_AGENT_PROMPT", "") or ""`
2. **`src/kinetiqo/profile_sync.py`**:
   - Add environment synchronization helper `sync_agent_prompt_from_env(config, repo)`.
   - Update `sync_profile_from_env()` to synchronize `agent_prompt`.

---

## 5. Description Engine & Token Validation

1. **`src/kinetiqo/strava_description.py`**:
   - Add `"ai-agent"` to `SPECIAL_TOKENS` so `validate_template()` recognizes `{{ai-agent}}` as a valid placeholder.
   - In `DescriptionContext`:
     - Accept optional `ai_generator` callable or pass `chat_service` / prompt runner.
     - In `_resolve_token(token, activity_dt, cache, activity)`:
       - When `token == "ai-agent"`:
         - Inspect `activity.get("ai_responses")`.
         - If present and contains `"ai-agent"`, return cached response.
         - If not cached and activity is eligible for live generation, invoke single-shot AI runner, persist result to `activity["ai_responses"]` and database, and return generated text.
         - If generation fails or AI is unconfigured, log single-line warning and return `""`.

---

## 6. AI Prompt Execution Service

Create a lightweight single-shot prompt runner in `src/kinetiqo/chat/` (e.g. `run_agent_prompt()`):
1. **Telemetry Context Assembly (Option A resolved)**:
   Automatically injects a concise summary of the activity's metrics into the LLM context:
   - Activity Name & Sport Type
   - Start Date & Time
   - Distance (km) & Moving Time (formatted H:MM:SS)
   - Elevation Gain (m) & Average/Max Speed (km/h)
   - Average & Max Power (Watts), Average & Max Heart Rate (bpm)
   - Calories, Cadence, Temperature
   - Trophies / Leaderboard rank / PR achievements (if present)
   - The athlete's custom prompt from `profile.agent_prompt` is appended as the directive.
2. **Prompt Construction**:
   - System instruction: Concise fitness assistant instruction enforcing plain text output without markdown quotes or formatting, suitable for Strava descriptions.
   - User turn: Structured activity statistics + athlete's custom `agent_prompt`.
3. **Execution with Fallbacks**:
   - Iterates through primary model then configured fallback models (up to 3).
   - Strict 10-second request timeout to prevent blocking sync progress.
   - Strips any accidental enclosing quotes or markdown blocks.

---

## 7. Sync Engine Integration (`src/kinetiqo/sync.py`)

1. **Sync Loop Execution**:
   - When processing an eligible activity where the matching template contains `{{ai-agent}}`:
     - Check if `activity` already has cached `ai-agent` response in `ai_responses`.
     - If not cached:
       - Run single-shot prompt runner.
       - If successful, persist to database `activities.ai_responses`.
       - If failed, log warning, leave variable empty, and record in `sync_warnings`.
2. **Sync Log Presentation (Option B resolved)**:
   - The sync output maintains strict one-line-per-activity formatting, appending a concise AI status suffix:
     - Normal generation: `[AI: generated]`
     - Fallback model used: `[AI: fallback <model>]` (e.g. `[AI: fallback gemini-2.5-flash]`)
     - Cached response used: `[AI: cached]`
     - Failure / skip: `[AI: failed]` (with specific reason appended to `sync_warnings`)
   - Example line:
     ```text
     [1/5] (20%) Morning Ride (Ride) [AI: generated] [updated]
     [2/5] (40%) Evening Commute (Ride) [AI: cached] [unchanged]
     [3/5] (60%) Hill Repeats (Ride) [AI: fallback gemini-2.5-flash] [updated]
     [4/5] (80%) Lunch Run (Run) [AI: failed] [updated]
     ```

---

## 8. Settings Web UI (`src/kinetiqo/web/templates/settings.html`)

1. **Card Placement & Styling**:
   - Positioned in "Strava Description Templates" section, immediately preceding "Supported Template Variables".
   - Header: **Kinetiqo Agent** with robot/sparkle icon.
   - Subtitle: *"Define custom prompt instructions for Kinetiqo Agent to analyze and enhance your synced activity descriptions."*
   - Variable Badge:
     ```html
     <span class="font-mono font-bold px-2.5 py-1 rounded bg-amber-100 dark:bg-amber-950/80 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-800 text-xs">
       {{ai-agent}}
     </span>
     ```
   - Textarea:
     - ID: `profile-agent-prompt`
     - Placeholder: *"e.g. Write a witty, single-sentence summary of this workout's pace and effort in the tone of a cycling commentator."*
     - Server-side auto-save on change/blur via `/api/settings/profile` with `Saved ✓` green confirmation.
2. **Activation Guard & Disabled State**:
   - Check if an AI provider is configured and default model is selected.
   - If **NOT active**:
     - Container receives `opacity-60 pointer-events-none`.
     - Displays informational alert banner:
       > ⚠️ **AI Agent Disabled**: Configure an AI provider and select a default model (optionally up to 3 fallback models) in **AI Chat Settings** to activate the Kinetiqo Agent.
     - Includes a one-click anchor link scrolling smoothly to `#ai-chat-settings`.
3. **Template Variables Explorer**:
   - Add `{{ai-agent}}` to `strava-variables-data` JSON list with explanation: *"Custom AI-generated text based on your Kinetiqo Agent prompt"*.

---

## 9. Activities Table Grid & ColReorder Integration (`src/kinetiqo/web/templates/activities.html`)

1. **Schema Migration Version Bump**:
   - Update `SCHEMA_VERSION_KEY` from `'activities_schema_v6'` to `'activities_schema_v7'` to invalidate old column orders cleanly and load the new column definition.
2. **Column Definition Array (`columnDefs`)**:
   - Insert new column `{label: 'AI Analysis', mandatory: false, selectable: true, visible: true, default: false, defaultOrder: 24, defaultSort: null}`.
   - Preserves mandatory pinning of `Select`, `Name`, and `Actions`.
3. **HTML Table Header (`<thead>` & `<tfoot>`)**:
   - Add `<th class="py-3 px-4 w-48">AI Analysis</th>` in `<thead>` and matching footer cell in `<tfoot>`.
4. **DataTables Column Specification**:
   - Map `ai_responses`:
     ```javascript
     {
         "data": "ai_responses",
         "render": function (data, type, row) {
             if (type === 'display') {
                 if (!data) return '-';
                 let val = (typeof data === 'object') ? (data['ai-agent'] || JSON.stringify(data)) : data;
                 return `<span class="truncate block max-w-xs text-xs text-gray-700 dark:text-gray-300" title="${escapeHtml(val)}">${escapeHtml(val)}</span>`;
             }
             return data ? (typeof data === 'object' ? (data['ai-agent'] || '') : data) : '';
         }
     }
     ```
5. **Reorder Column Modal (`showColumnSelectModal`)**:
   - Automatically surfaces the "AI Analysis" column with drag handle `☰`, checkbox, and SortableJS drag-and-drop capability.
6. **"Purge AI Analysis" Action Button (`#custom-buttons-wrapper`)**:
   - Add button to bulk action toolbar with AI sparkle icon:
     ```html
     <button id="purgeAiBtn" disabled class="px-2.5 py-1 text-xs font-medium text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/60 border border-purple-200 dark:border-purple-800 rounded hover:bg-purple-100 disabled:opacity-40 transition-colors inline-flex items-center gap-1.5" title="Purge cached AI analysis for selected activities">
         <span class="text-xs">✨</span>
         <span>Purge AI Analysis</span>
     </button>
     ```
   - Enabled when 1 or more activities are selected (`updateSelectionButtons()`).
   - On click: calls `POST /api/activities/purge-ai` with selected `activity_ids`, sets `ai_responses = NULL` in database, reloads table without changing page, and displays toast notification.
7. **Row-level Purge (Optional shortcut)**:
   - In row actions or AI column tooltip/popover, provide an inline purge icon when AI response exists.

---

## 10. Verification & Testing Plan

1. **Unit Tests (`tests/test_strava_ai_agent.py`)**:
   - `test_validate_template_with_ai_agent()`: verifies template parser accepts `{{ai-agent}}`.
   - `test_resolve_ai_agent_from_cache()`: verifies cached response is returned without calling AI provider.
   - `test_resolve_ai_agent_generates_and_persists()`: verifies uncached activity triggers AI call and saves to DB.
   - `test_resolve_ai_agent_error_fallback()`: verifies AI exception returns `""` and logs warning without failing sync.
   - `test_fallback_models_cascade()`: verifies primary failure triggers fallback model.
2. **Database Repository Tests**:
   - Verify `update_activity_ai_responses` and `agent_prompt` profile handling across all backends with mocks.
   - Verify `purge_activities_ai_responses(activity_ids)` across PostgreSQL, MySQL, and Firebird.
3. **Web & API Tests**:
   - Verify Settings API saves and returns `agent_prompt`.
   - Verify activation guard logic in template rendering.
   - Verify `/api/activities/purge-ai` endpoint clears `ai_responses` for specified activities.
   - Verify ColReorder `activities_schema_v7` loads without index shifting or JavaScript errors.

---

## 11. Ambiguity Report & Sign-Off

```text
Ambiguity Report:
  Goals:        0.0   ✓ clear (Strava activity description {{ai-agent}} integration)
  Acceptance:   0.0   ✓ clear (verifiable DB persistence, ColReorder, single-line log, purge button)
  Boundaries:   0.0   ✓ clear (activity names untouched, no live web API calls)
  Alternatives: 0.0   ✓ clear (evaluated caching, telemetry context, and log presentation)
  Assumptions:  0.0   ✓ clear (verified against repo signatures, ChatService & DataTables)
  ──────────────────────────────
  Aggregate:    0.0   ✓ below threshold (0.2 spec gate passed)
```
