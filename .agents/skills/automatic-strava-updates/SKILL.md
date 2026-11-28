---
name: automatic-strava-updates
description: Maintain Kinetiqo's deterministic one-line Strava description update contract.
---

# Automatic Strava Description Updates

Apply these rules whenever modifying `UPDATE_STRAVA_*` templates, description
rendering, merge behavior, sync logging, or related documentation.

## One-line contract

- Normalize literal `\r\n`, `\r`, and `\n` to spaces when Settings saves a
  template.
- Apply the same normalization when rendering environment-supplied templates.
- Generate exactly one Kinetiqo-owned line ending in `\n`.
- Use `✨ Kinetiqo:` unless the template contains an AI placeholder; then use
  `✨ Kinetiqo AI:`.
- Templates must not include either prefix.

## Merge and update behavior

1. Read the full current Strava description.
2. Find the first line beginning with either Kinetiqo prefix.
3. If that line exactly equals the generated line, do not call Strava's
   description-update API and report that the update was skipped.
4. If it differs, replace only that line in place, preserving every other
   description line.
5. If neither prefix exists, insert the generated line at
   `UPDATE_STRAVA_PLACEMENT` (`begin` or `end`).

Do not add product-specific migration heuristics for prior generated content.
Never delete or rewrite non-prefixed lines.

## Sync ordering with weather

When weather enrichment is enabled, process every fetched activity in exactly
this order before continuing to the next activity:

1. Persist the activity and, for new activities, its streams.
2. Read cached weather; when it is absent (or weather resync is requested),
   fetch and persist historical weather.
3. Render the template and update the Strava description, including any
   deterministic weather placeholders or AI placeholders.
4. Emit one final per-activity log line with the weather and description
   outcomes.

The weather flag is authoritative. A weather placeholder must use already
stored weather when the flag is disabled; it must not trigger a hidden provider
request. If complete weather is unavailable, defer the description write
instead of writing an empty generated line.

## Required coverage

Use mocked unit tests to cover standard and AI prefixes, equal-line skips,
changed-line replacement, begin/end insertion, one-line normalization, and
preservation of non-Kinetiqo description content. Cover the per-activity order
of persistence, weather enrichment, and description update, plus weather
placeholder deferral when weather is disabled.
