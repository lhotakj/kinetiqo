# AI Agent "Try This Prompt on Your Activity" Plan

## Goal

Let an athlete test the current text of any Strava AI-agent prompt against one
locally synced activity without saving the prompt, changing the activity, or
contacting Strava. The result must use the exact same telemetry prompt,
system instruction, default-model/fallback execution path, and response cleanup
as the `{{agent-ai-<name>}}` placeholder during Strava-description rendering.

## Scope and user experience

1. Add a per-agent **Try** control to the Strava AI Agent editor in
   `src/kinetiqo/web/templates/settings.html`.
   - It includes a text input whose placeholder is `Start typing name of the
     activity or Strava ID`.
   - The **Try** button is disabled by default and becomes enabled only when:
     - AI agents are enabled,
     - the current row's prompt textarea contains non-whitespace text,
     - a valid activity has been selected, and
     - the athlete has an explicitly configured default AI model.
   - The control works for draft rows and uses the textarea's current,
     unsaved value. It never saves that value automatically.
   - While a test is running, the row's prompt textarea is read-only and has
     an amber focus ring. Restore its original editable styling on both
     success and failure.

2. Search local activities while the athlete types.
   - Start searching after two characters with a 250 ms debounce.
   - Search only activities belonging to the current athlete, matching either
     activity name or a partial/exact Strava activity ID, case-insensitively
     where the database supports case-insensitive text.
   - Return at most ten newest matching activities.
   - Render a compact selectable result box below the input using safe DOM
     construction (`textContent`/`replaceChildren`), not HTML interpolation.
     Each item shows name, Strava ID, sport, and start date.
   - Selecting exactly one item replaces the input value with the same compact
     summary and records its ID. Editing the input afterwards clears that
     selection, hides/refreshes results, and disables **Try** until another
     item is selected.
   - Ignore stale asynchronous search results using an `AbortController` and/or
     monotonic request sequence.

3. Run and present the preview.
   - Clicking **Try** opens a modal immediately. It shows the standard
     `kinetiqo-loading-32x32.webp` loading image and progress text while the
     request is pending. The close button remains disabled until completion;
     closing never cancels a completed or in-flight generation.
   - The action button is disabled and replaces its contents exclusively with
     the standard loading image while pending, then restores its original
     markup in `finally`.
   - On success, the modal shows the generated plain-text response and the
     runner status (`generated` or the fallback-model status), then enables
     Close.
   - On failure, replace the modal progress view with the error and enable
     Close. Also render the same error in red beside that row's **Try** button.
   - A trial must not write `activities.ai_responses`, mutate the selected
     activity, save the agent prompt, or make any Strava API request.

## Backend design

1. Extend the existing keyword branch in `search_activities()` in
   `src/kinetiqo/db/postgresql.py`, `mysql.py`, and `firebird.py` so that a
   keyword matches activity name **or** the textual activity ID. Keep every
   query parameterized and preserve the existing athlete filter, newest-first
   ordering, cursor behavior, and limit handling. Use each backend's
   appropriate text-cast/safe comparison syntax.

2. Add authenticated JSON endpoints under the existing
   `/api/profile/strava-agents` API surface:
   - A read-only activity-search endpoint accepts the query, rejects
     insufficient input, reads the profile athlete ID, calls
     `repo.search_activities()` with that athlete ID, a keyword, descending
     date order, and a limit of ten, then returns only the summary fields
     required by the picker.
   - A preview endpoint accepts `activity_id` and the current prompt text.
     It validates JSON types, non-empty prompt text, an existing profile,
     enabled agent configuration, a valid explicit default model, and that
     the exact requested activity is locally stored and owned by the profile
     athlete. Reject invalid input with the repository-standard JSON error
     format and an appropriate 4xx status.

3. In the preview endpoint, construct `ChatRepository`/`ChatService` using
   the same configuration and athlete-ID resolution as sync, then call
   `run_agent_prompt(chat_service, athlete_id, activity, prompt)`. Do not
   route through `DescriptionContext`, because it deliberately persists
   generated responses for production placeholder rendering. Treat an empty
   response or failed status as a visible request failure rather than a
   success-shaped empty preview.

4. Ensure the endpoint requires a default model even though
   `ChatService.generate_single_turn()` can otherwise choose a configured
   provider/model automatically. This makes the server enforce the same
   condition as the disabled UI control and prevents direct API callers from
   bypassing it.

## Frontend integration

1. Extend the existing per-row DOM creation in `renderStravaAgents()` rather
   than adding server-rendered repeated markup. Keep selection, query,
   pending-search controller, and feedback state local to each rendered row.

2. Consume the existing AI-settings model payload/default-model state, or its
   existing loader, to maintain a `hasDefaultAiModel` condition. Re-evaluate
   all agent-row buttons whenever provider/model/default state, the global
   agent-enabled checkbox, prompt textarea value, or activity selection
   changes.

3. Add one accessible modal to the settings page with labelled title, result
   region, progress region, and Close button. Use explicit labels/ARIA
   attributes for the search input, results list, controls, and modal actions.
   Keep the selected-activity summary available to assistive technology.

4. Send mutation requests with the existing JSON/CSRF headers. Surface errors
   explicitly; do not silently fall back to another activity or model.

## Tests

1. Add mocked repository tests covering the extended keyword predicate for
   PostgreSQL, MySQL, and Firebird, including parameterization and the
   name-or-ID match semantics.

2. Add mocked web API tests for:
   - two-character search validation, athlete-scoped ten-result search, and
     summary-only output;
   - partial ID lookup;
   - preview rejection for missing/blank prompt, disabled agents, no default
     model, missing activity, and another athlete's activity;
   - a successful preview calling `run_agent_prompt()` with the exact current
     prompt and selected activity;
   - generated/fallback status output and propagated failure errors; and
   - proof that preview does not call `update_activity_ai_responses()` or any
     Strava client.

3. Extend settings/template tests to assert the picker controls, modal,
   accessibility labels, loading asset, and no-default disabled state hooks
   are present. Exercise the JavaScript state transitions with the project's
   existing frontend-test approach if one covers `settings.html`; otherwise
   keep the client logic small and cover the server behavior with mocked unit
   tests.

4. Run the focused AI-agent/settings tests first, then the full mocked pytest
   suite if the focused run passes.

## Non-goals

- Do not save an unsaved prompt, cache the preview, update a Strava
  description, or call Strava.
- Do not alter production `DescriptionContext` caching behavior.
- Do not add a separate activity-search index or a live database/network
  integration test.
- Do not enable a test merely because a provider is configured; an explicit
  default model remains mandatory.

## Alternatives considered

- **Use `DescriptionContext` for the preview:** rejected because its normal
  uncached AI path persists `ai_responses`, violating the preview-only
  requirement.
- **Reuse only the client-side activity grid data:** rejected because it may
  be filtered, stale, and does not provide authoritative athlete ownership
  validation.
- **Permit the AI service to auto-select a provider/model:** rejected because
  the requested UI contract requires **Try** to remain disabled without an
  explicit default model.

## Verified implementation facts

- `run_agent_prompt()` builds telemetry and calls
  `ChatService.generate_single_turn()`; sync uses this same runner for named
  Strava agents (`src/kinetiqo/chat/agent_runner.py`,
  `src/kinetiqo/sync.py`).
- `DescriptionContext` caches generated agent responses on the activity and
  persists them through `update_activity_ai_responses()`
  (`src/kinetiqo/strava_description.py`).
- The existing repository search is athlete-scoped, parameterized, newest
  first, and currently searches names only in all three backends
  (`src/kinetiqo/db/postgresql.py`, `mysql.py`, `firebird.py`).
- No prompt-history search renderer exists in this checkout, so the compact
  result card above is the agreed replacement rendering contract.

## Ambiguity Report

Ambiguity Report:
  Goals:        0.0   ✓ clear
  Acceptance:   0.0   ✓ clear
  Boundaries:   0.0   ✓ clear
  Alternatives: 0.25  ✓ considered
  Assumptions:  0.25  ✓ verified except absent prompt-history renderer
  ──────────────────────────────
  Aggregate:    0.10  ✓ below threshold (0.4 freeform)

Push lightly on: no remaining implementation decisions.
