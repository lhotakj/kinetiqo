# UPDATE_STRAVA — Strava Description Auto-Update

Kinetiqo can automatically write a block of your own running/rolling statistics
into every synced activity's Strava description — total distance so far this
year, progress towards your goals, whether you're ahead of or behind your
training plan, activity counts with milestone celebrations, and more. By
default the block is appended to the **end** of the description (configurable
via `UPDATE_STRAVA_PLACEMENT`, see [Placement](#placement-beginning-or-end)
below).

This feature is **entirely optional** and controlled by **six independent
environment variables** — one template per activity-type/scope "bucket",
since e.g. your cycling description probably shouldn't look the same as your
swim description:

| Environment variable | Applies to |
|---|---|
| `UPDATE_STRAVA_CYCLING_INDOOR` | Indoor rides (`VirtualRide`, `IndoorRide`) |
| `UPDATE_STRAVA_CYCLING_OUTDOOR` | Outdoor rides (all other Ride variants) |
| `UPDATE_STRAVA_RUNNING_INDOOR` | Indoor runs (`VirtualRun`) |
| `UPDATE_STRAVA_RUNNING_OUTDOOR` | Outdoor runs (`Run`, `TrailRun`, etc.) |
| `UPDATE_STRAVA_WALKING` | Walks and hikes (`Walk`, `Hike` — no indoor/outdoor split in Strava's taxonomy) |
| `UPDATE_STRAVA_SWIMMING` | Swims (`Swim` — no indoor/outdoor split in Strava's taxonomy) |

- Each variable is **independently optional**. If it's **unset or empty**,
  activities in that bucket are left completely untouched — no extra Strava
  API calls are made for them.
- If a variable is set to a **template string** containing one or more
  `{{placeholder}}` tokens (see the full reference below), that template is
  rendered — with the placeholders replaced with real numbers — and merged
  into that bucket's activities' Strava descriptions during sync, at the
  position configured by `UPDATE_STRAVA_PLACEMENT` (default: the end).
- Every activity uses **exactly one** of the six templates, chosen by its own
  `sport_type` — e.g. an `IndoorRide` always uses
  `UPDATE_STRAVA_CYCLING_INDOOR`, never `UPDATE_STRAVA_CYCLING_OUTDOOR`. An
  activity whose sport type doesn't map to any of the six buckets (e.g.
  `WeightTraining`, `AlpineSki`) is never touched, regardless of what's
  configured.
- If **all six** variables are unset/empty, the feature is fully disabled
  (matches the original single-`UPDATE_STRAVA` opt-in design) — no extra
  Strava API calls are made at all during sync.

## Placement (beginning or end)

| Environment variable | Values | Default |
|---|---|---|
| `UPDATE_STRAVA_PLACEMENT` | `begin`, `end` | `end` |

Controls where a **newly-inserted** stats block is placed relative to any
existing text in the activity's description:

- `end` (default) — the rendered block is appended after your existing
  description, separated by a blank line.
- `begin` — the rendered block is inserted before your existing description
  (this was the only behavior before `UPDATE_STRAVA_PLACEMENT` existed).

An invalid/unrecognized value falls back to `end` with a `WARNING` logged.

> ℹ️ This setting only affects **where a brand-new block is inserted**. If
> Kinetiqo recognizes a previously-rendered block already in the description
> (see [Smart merge](#smart-merge-never-loses-your-text) below), that block is
> always **replaced in place** — its position never changes — regardless of
> `UPDATE_STRAVA_PLACEMENT`.

## How it works

1. On every sync (full or fast), for each activity that gets written to the
   database, Kinetiqo also:
   - Determines which of the six templates applies, based on the activity's
     own `sport_type` (see [Activity type classification](#activity-type-classification)).
     If that template is unset, or the sport type doesn't map to any bucket,
     nothing further happens for this activity.
   - Fetches the activity's **current, full description** from Strava (the
     activity-list endpoint used for the main sync doesn't include
     descriptions, so this is one extra `GET` per activity — only when the
     applicable template is configured).
   - Renders the template using stats **as of that activity's own date and
     time** (not "now" — so re-running a full sync produces the same
     historically-correct numbers for old activities), and automatically
     prefixes it with `✨ Kinetiqo:` in the final Strava description line.
     Do **not** include this prefix in your template value.
   - Removes any existing description line starting with `✨ Kinetiqo:` (see
     [Smart merge](#smart-merge-never-loses-your-text) below), then inserts
     the freshly rendered line at the position configured by
     `UPDATE_STRAVA_PLACEMENT` (**end** of the description by default, or
     **beginning** if configured).
   - If the resulting description is identical to what's already on Strava,
     **no update API call is made** (saves your Strava API rate limit).
   - To protect API rate limits, description writes are attempted only for the
     latest 30 eligible activities per sync run.
2. Any failure while resolving a single placeholder, fetching the current
   description, or pushing the update to Strava is logged as a `WARNING`/`ERROR`
   and **never aborts the sync** — at worst, that one activity's description is
   left unchanged for this run and will be retried on the next sync.

## Smart merge — never loses your text

Kinetiqo stores its stats as one dedicated line that always starts with
`✨ Kinetiqo:`. During sync it removes any existing line with that prefix and
inserts the newly rendered one, leaving the rest of your description untouched.

```
Year-to-date: 6,500.0 km cycled (55.80% of the goal).
<-- rest of your own hand-written description below, always preserved -->
```

## Placeholder grammar

Every placeholder has the shape:

```
{{<activity>-<metric>[-<modifier>]-<scope>-<period>}}
```

| Token | Values | Notes |
|---|---|---|
| `<activity>` | `cycling`, `running`, `walking`, `swimming` | Follows Strava's own activity taxonomy (see [Activity type classification](#activity-type-classification)). |
| `<metric>` | `distance`, `elevation`, `activities`, `count`, `ordinal` | What to measure. |
| `<modifier>` | `goal`, `percent`, `deviation` (optional, `distance`/`elevation` only) | Compares the achieved value against your configured [Activity Goal](#4-athlete-configuration). |
| `<scope>` | `total`, `outdoor`, `indoor` | Restricts to outdoor-only or indoor-only activities of that type (see limitations below). |
| `<period>` | `week`, `month`, `year` | The period **to date of the activity** (see [Period math](#period-math-to-date-of-the-activity)). |

| Token | Meaning |
|---|---|
| `{{current-year}}` | The 4-digit year of the activity being synced (e.g. `2026`). |
| `{{current-month}}` | The full month name of the activity being synced (e.g. `July`). |
| `{{new-line}}` | A literal line break (`\n`) — Strava descriptions don't render Markdown, so use this instead of a raw newline in your `UPDATE_STRAVA_*` env var. |
| `{{workout-summary}}` | Inserts a RestOrTrain-style workout summary (e.g. `Endurance | 120min @ 191W`, `Tempo | 120min @ 224W`, `Endurance | 45min @ 195W + 2min @ 244W`, `Endurance | 4h @ 209W normalized (74% FTP), with 10-15min blocks @ 220-243W (78-86%)`, or HR fallback `Endurance | About 2h30m aerobic riding @ 125bpm average HR`). |

Any placeholder that doesn't match this grammar, or references data that can't
be resolved (e.g. no goal configured, running with a `goal`/`percent`/`deviation`
modifier since only cycling & walking support goals), resolves to an **empty
string** and logs a `WARNING` explaining why — it never breaks the render.

## Metric reference

| Metric | Unit | Meaning |
|---|---|---|
| `distance` | km (constant `DISTANCE_UNIT`, see [Units](#units)) | Total distance covered by matching activities in the period (adds `" 🎉"` on the first activity that reaches or passes positive multiples of 1,000 km). |
| `elevation` | m (constant `ELEVATION_UNIT`, see [Units](#units)) | Total elevation gain of matching activities in the period (adds `" 🎉"` on the first activity that reaches or passes positive multiples of 1,000 m). |
| `activities` | count | Number of matching activities in the period (no 🎉 celebration). |
| `count` | count | Same as `activities`, but adds `" 🎉"` when the number is a milestone (`1`, or any multiple of `100`). |
| `ordinal` | ordinal | Same count as above, formatted as an ordinal number (`1st`, `2nd`, `3rd`, `4th`, … `11th`, `12th`, `13th`, `21st`, …), with the same 🎉 milestone rule (adds `" 🎉"` on `1st` or multiples of `100`). |

### Modifiers (`distance` / `elevation` only)

Modifiers compare the achieved value against the goal configured on the
**Settings → Activity Goals** page. **Goals only exist for `cycling` and
`walking`** (matching the pre-existing Activity Goals feature) — using a
modifier with `running` or `swimming`, or with an activity that has no goal
configured for that period, resolves to an empty string with a warning logged.

| Modifier | Meaning |
|---|---|
| `goal` | The configured goal value itself, for that period (weekly/monthly/yearly), formatted with its unit. The `<scope>` suffix is accepted for grammar consistency, but goals aren't split by indoor/outdoor — all scopes return the same configured goal. |
| `percent` | `achieved ÷ goal × 100`, to 2 decimal places, with a trailing `%` (e.g. `56.10%`). |
| `deviation` | Compares achieved-to-date against the goal **prorated** to how far through the period the activity's date falls (`planned = goal × elapsed_fraction`). Renders as `ahead of the plan by X`, `behind the plan by X`, or `right on the track` if the difference rounds to 0. |

## Period math ("to date of the activity")

All periods are computed **relative to the activity being rendered**, not to
"now" — this way, re-syncing old activities always reproduces the exact same
historically-correct numbers.

| Period | Start | End |
|---|---|---|
| `week` | Monday 00:00 of the activity's week | The activity's own date/time |
| `month` | The 1st, 00:00, of the activity's month | The activity's own date/time |
| `year` | January 1st, 00:00, of the activity's year | The activity's own date/time |

## Activity type classification

Each activity is assigned to exactly one of the six template buckets, based
on its Strava `sport_type`:

| Bucket / env var | Strava `sport_type`s |
|---|---|
| `cycling` / `UPDATE_STRAVA_CYCLING_INDOOR` | `VirtualRide`, `IndoorRide` |
| `cycling` / `UPDATE_STRAVA_CYCLING_OUTDOOR` | All other Ride variants (matches the MEGA Stats "Cycling (outdoor)" group) |
| `running` / `UPDATE_STRAVA_RUNNING_INDOOR` | `VirtualRun` |
| `running` / `UPDATE_STRAVA_RUNNING_OUTDOOR` | `Run`, `TrailRun`, etc. |
| `walking` / `UPDATE_STRAVA_WALKING` | `Walk`, `Hike` — **no indoor/outdoor split**, a single template covers both |
| `swimming` / `UPDATE_STRAVA_SWIMMING` | `Swim` — **no indoor/outdoor split**, a single template covers both |

Any other `sport_type` (e.g. `WeightTraining`, `AlpineSki`, `Yoga`, …) doesn't
map to any bucket — those activities are never touched by this feature,
regardless of what's configured.

The `<scope>` token (`total`/`outdoor`/`indoor`) used **inside placeholders**
is independent of which *template* is selected for the activity — e.g. your
`UPDATE_STRAVA_CYCLING_OUTDOOR` template can still reference
`{{cycling-distance-indoor-year}}` if you want to show indoor mileage in an
outdoor ride's description. For `walking`/`swimming`, since there's no
indoor/outdoor distinction, the `indoor` scope always resolves to `0` (with a
warning logged) and `outdoor` behaves the same as `total`.

> Note: the spec's `{{waking-...}}` spelling (missing the "l") is tolerated as
> an alias for `walking` for backwards compatibility with early drafts of this
> feature, but prefer the correctly-spelled `{{walking-...}}` form going forward.

## Formatting & units

| Value | Format | Example |
|---|---|---|
| Distance | `{value:,.1f} km` | `6,540.0 km` |
| Elevation | `{value:,.0f} m` | `12,345 m` |
| Percent | `{value:.2f}%` | `56.10%` |
| Count | `{value:,}` | `1,234` |
| Ordinal | `{value:,}` + `st`/`nd`/`rd`/`th` | `11th`, `102nd`, `1,001st` |

### Units

The distance unit (`km`) and elevation unit (`m`) are defined as single
constants (`DISTANCE_UNIT` / `ELEVATION_UNIT`) in
`src/kinetiqo/strava_description.py`, in preparation for a future
"imperial units" configuration option (miles / feet) — changing units will
only require updating these two constants and their formatting helpers.

## Example

```bash
UPDATE_STRAVA_CYCLING_OUTDOOR="Total {{cycling-distance-total-year}} cycled in {{current-year}}, this is your {{cycling-ordinal-total-year}} cycling activity this year. Achieved {{cycling-distance-percent-total-year}} of the yearly goal, {{cycling-distance-deviation-total-year}}.{{new-line}}"
```

Might render as:

```
Total 6,540.0 km cycled in 2026, this is your 150th cycling activity this year. Achieved 56.10% of the yearly goal, ahead of the plan by 1,201.0 km.
```

A different bucket can use an entirely different wording/format — for
example a much shorter swim template:

```bash
UPDATE_STRAVA_SWIMMING="{{swimming-distance-total-year}} swum in {{current-year}} ({{swimming-count-total-year}} sessions).{{new-line}}"
```

By default this block is appended to the **end** of the description. To
instead insert it at the **beginning** (the original behavior):

```bash
UPDATE_STRAVA_PLACEMENT=begin
```

## Full placeholder reference

The tables below are generated from every valid combination of
`<activity>-<metric>[-<modifier>]-<scope>-<period>` (goal/percent/deviation
are only listed for `cycling` and `walking`, since those are the only
activity types with configurable goals).


<details>
<summary><strong>Cycling placeholders (99)</strong></summary>

| Placeholder | Description |
|---|---|
| `{{cycling-distance-total-week}}` | Total all cycling distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{cycling-distance-total-month}}` | Total all cycling distance, so far this month (1st 00:00 to the activity), in km. |
| `{{cycling-distance-total-year}}` | Total all cycling distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{cycling-distance-outdoor-week}}` | Total outdoor-only cycling distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{cycling-distance-outdoor-month}}` | Total outdoor-only cycling distance, so far this month (1st 00:00 to the activity), in km. |
| `{{cycling-distance-outdoor-year}}` | Total outdoor-only cycling distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{cycling-distance-indoor-week}}` | Total indoor-only cycling distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{cycling-distance-indoor-month}}` | Total indoor-only cycling distance, so far this month (1st 00:00 to the activity), in km. |
| `{{cycling-distance-indoor-year}}` | Total indoor-only cycling distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{cycling-distance-goal-total-week}}` | The configured week distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-total-month}}` | The configured month distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-total-year}}` | The configured year distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-outdoor-week}}` | The configured week distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-outdoor-month}}` | The configured month distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-outdoor-year}}` | The configured year distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-indoor-week}}` | The configured week distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-indoor-month}}` | The configured month distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-goal-indoor-year}}` | The configured year distance goal for cycling (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{cycling-distance-percent-total-week}}` | Percentage of the week distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-total-month}}` | Percentage of the month distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-total-year}}` | Percentage of the year distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-outdoor-week}}` | Percentage of the week distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-outdoor-month}}` | Percentage of the month distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-outdoor-year}}` | Percentage of the year distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-indoor-week}}` | Percentage of the week distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-indoor-month}}` | Percentage of the month distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-percent-indoor-year}}` | Percentage of the year distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-distance-deviation-total-week}}` | Compares distance achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-total-month}}` | Compares distance achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-total-year}}` | Compares distance achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-outdoor-week}}` | Compares distance achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-outdoor-month}}` | Compares distance achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-outdoor-year}}` | Compares distance achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-indoor-week}}` | Compares distance achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-indoor-month}}` | Compares distance achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-distance-deviation-indoor-year}}` | Compares distance achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-total-week}}` | Total all cycling elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{cycling-elevation-total-month}}` | Total all cycling elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{cycling-elevation-total-year}}` | Total all cycling elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{cycling-elevation-outdoor-week}}` | Total outdoor-only cycling elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{cycling-elevation-outdoor-month}}` | Total outdoor-only cycling elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{cycling-elevation-outdoor-year}}` | Total outdoor-only cycling elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{cycling-elevation-indoor-week}}` | Total indoor-only cycling elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{cycling-elevation-indoor-month}}` | Total indoor-only cycling elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{cycling-elevation-indoor-year}}` | Total indoor-only cycling elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{cycling-elevation-goal-total-week}}` | The configured week elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-total-month}}` | The configured month elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-total-year}}` | The configured year elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-outdoor-week}}` | The configured week elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-outdoor-month}}` | The configured month elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-outdoor-year}}` | The configured year elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-indoor-week}}` | The configured week elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-indoor-month}}` | The configured month elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-goal-indoor-year}}` | The configured year elevation gain goal for cycling (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{cycling-elevation-percent-total-week}}` | Percentage of the week elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-total-month}}` | Percentage of the month elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-total-year}}` | Percentage of the year elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-outdoor-week}}` | Percentage of the week elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-outdoor-month}}` | Percentage of the month elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-outdoor-year}}` | Percentage of the year elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-indoor-week}}` | Percentage of the week elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-indoor-month}}` | Percentage of the month elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-percent-indoor-year}}` | Percentage of the year elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{cycling-elevation-deviation-total-week}}` | Compares elevation gain achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-total-month}}` | Compares elevation gain achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-total-year}}` | Compares elevation gain achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-outdoor-week}}` | Compares elevation gain achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-outdoor-month}}` | Compares elevation gain achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-outdoor-year}}` | Compares elevation gain achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-indoor-week}}` | Compares elevation gain achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-indoor-month}}` | Compares elevation gain achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-elevation-deviation-indoor-year}}` | Compares elevation gain achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{cycling-activities-total-week}}` | Number of all cycling activities, so far this week (Monday 00:00 to the activity). |
| `{{cycling-activities-total-month}}` | Number of all cycling activities, so far this month (1st 00:00 to the activity). |
| `{{cycling-activities-total-year}}` | Number of all cycling activities, so far this year (Jan 1 00:00 to the activity). |
| `{{cycling-activities-outdoor-week}}` | Number of outdoor-only cycling activities, so far this week (Monday 00:00 to the activity). |
| `{{cycling-activities-outdoor-month}}` | Number of outdoor-only cycling activities, so far this month (1st 00:00 to the activity). |
| `{{cycling-activities-outdoor-year}}` | Number of outdoor-only cycling activities, so far this year (Jan 1 00:00 to the activity). |
| `{{cycling-activities-indoor-week}}` | Number of indoor-only cycling activities, so far this week (Monday 00:00 to the activity). |
| `{{cycling-activities-indoor-month}}` | Number of indoor-only cycling activities, so far this month (1st 00:00 to the activity). |
| `{{cycling-activities-indoor-year}}` | Number of indoor-only cycling activities, so far this year (Jan 1 00:00 to the activity). |
| `{{cycling-count-total-week}}` | Number of all cycling activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-total-month}}` | Number of all cycling activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-total-year}}` | Number of all cycling activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-outdoor-week}}` | Number of outdoor-only cycling activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-outdoor-month}}` | Number of outdoor-only cycling activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-outdoor-year}}` | Number of outdoor-only cycling activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-indoor-week}}` | Number of indoor-only cycling activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-indoor-month}}` | Number of indoor-only cycling activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-count-indoor-year}}` | Number of indoor-only cycling activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{cycling-ordinal-total-week}}` | Number of all cycling activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-total-month}}` | Number of all cycling activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-total-year}}` | Number of all cycling activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-outdoor-week}}` | Number of outdoor-only cycling activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-outdoor-month}}` | Number of outdoor-only cycling activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-outdoor-year}}` | Number of outdoor-only cycling activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-indoor-week}}` | Number of indoor-only cycling activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-indoor-month}}` | Number of indoor-only cycling activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{cycling-ordinal-indoor-year}}` | Number of indoor-only cycling activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |

</details>

<details>
<summary><strong>Running placeholders (45)</strong></summary>

| Placeholder | Description |
|---|---|
| `{{running-distance-total-week}}` | Total all running distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{running-distance-total-month}}` | Total all running distance, so far this month (1st 00:00 to the activity), in km. |
| `{{running-distance-total-year}}` | Total all running distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{running-distance-outdoor-week}}` | Total outdoor-only running distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{running-distance-outdoor-month}}` | Total outdoor-only running distance, so far this month (1st 00:00 to the activity), in km. |
| `{{running-distance-outdoor-year}}` | Total outdoor-only running distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{running-distance-indoor-week}}` | Total indoor-only running distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{running-distance-indoor-month}}` | Total indoor-only running distance, so far this month (1st 00:00 to the activity), in km. |
| `{{running-distance-indoor-year}}` | Total indoor-only running distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{running-elevation-total-week}}` | Total all running elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{running-elevation-total-month}}` | Total all running elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{running-elevation-total-year}}` | Total all running elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{running-elevation-outdoor-week}}` | Total outdoor-only running elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{running-elevation-outdoor-month}}` | Total outdoor-only running elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{running-elevation-outdoor-year}}` | Total outdoor-only running elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{running-elevation-indoor-week}}` | Total indoor-only running elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{running-elevation-indoor-month}}` | Total indoor-only running elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{running-elevation-indoor-year}}` | Total indoor-only running elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{running-activities-total-week}}` | Number of all running activities, so far this week (Monday 00:00 to the activity). |
| `{{running-activities-total-month}}` | Number of all running activities, so far this month (1st 00:00 to the activity). |
| `{{running-activities-total-year}}` | Number of all running activities, so far this year (Jan 1 00:00 to the activity). |
| `{{running-activities-outdoor-week}}` | Number of outdoor-only running activities, so far this week (Monday 00:00 to the activity). |
| `{{running-activities-outdoor-month}}` | Number of outdoor-only running activities, so far this month (1st 00:00 to the activity). |
| `{{running-activities-outdoor-year}}` | Number of outdoor-only running activities, so far this year (Jan 1 00:00 to the activity). |
| `{{running-activities-indoor-week}}` | Number of indoor-only running activities, so far this week (Monday 00:00 to the activity). |
| `{{running-activities-indoor-month}}` | Number of indoor-only running activities, so far this month (1st 00:00 to the activity). |
| `{{running-activities-indoor-year}}` | Number of indoor-only running activities, so far this year (Jan 1 00:00 to the activity). |
| `{{running-count-total-week}}` | Number of all running activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-total-month}}` | Number of all running activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-total-year}}` | Number of all running activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-outdoor-week}}` | Number of outdoor-only running activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-outdoor-month}}` | Number of outdoor-only running activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-outdoor-year}}` | Number of outdoor-only running activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-indoor-week}}` | Number of indoor-only running activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-indoor-month}}` | Number of indoor-only running activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-count-indoor-year}}` | Number of indoor-only running activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{running-ordinal-total-week}}` | Number of all running activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-total-month}}` | Number of all running activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-total-year}}` | Number of all running activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-outdoor-week}}` | Number of outdoor-only running activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-outdoor-month}}` | Number of outdoor-only running activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-outdoor-year}}` | Number of outdoor-only running activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-indoor-week}}` | Number of indoor-only running activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-indoor-month}}` | Number of indoor-only running activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{running-ordinal-indoor-year}}` | Number of indoor-only running activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |

</details>

<details>
<summary><strong>Walking placeholders (99)</strong></summary>

| Placeholder | Description |
|---|---|
| `{{walking-distance-total-week}}` | Total all walking distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{walking-distance-total-month}}` | Total all walking distance, so far this month (1st 00:00 to the activity), in km. |
| `{{walking-distance-total-year}}` | Total all walking distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{walking-distance-outdoor-week}}` | Total outdoor-only walking distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{walking-distance-outdoor-month}}` | Total outdoor-only walking distance, so far this month (1st 00:00 to the activity), in km. |
| `{{walking-distance-outdoor-year}}` | Total outdoor-only walking distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{walking-distance-indoor-week}}` | Total indoor-only walking distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{walking-distance-indoor-month}}` | Total indoor-only walking distance, so far this month (1st 00:00 to the activity), in km. |
| `{{walking-distance-indoor-year}}` | Total indoor-only walking distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{walking-distance-goal-total-week}}` | The configured week distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-total-month}}` | The configured month distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-total-year}}` | The configured year distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-outdoor-week}}` | The configured week distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-outdoor-month}}` | The configured month distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-outdoor-year}}` | The configured year distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-indoor-week}}` | The configured week distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-indoor-month}}` | The configured month distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-goal-indoor-year}}` | The configured year distance goal for walking (Settings → Training Goals), in km. Same value regardless of scope. |
| `{{walking-distance-percent-total-week}}` | Percentage of the week distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-total-month}}` | Percentage of the month distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-total-year}}` | Percentage of the year distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-outdoor-week}}` | Percentage of the week distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-outdoor-month}}` | Percentage of the month distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-outdoor-year}}` | Percentage of the year distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-indoor-week}}` | Percentage of the week distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-indoor-month}}` | Percentage of the month distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-percent-indoor-year}}` | Percentage of the year distance goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-distance-deviation-total-week}}` | Compares distance achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-total-month}}` | Compares distance achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-total-year}}` | Compares distance achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-outdoor-week}}` | Compares distance achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-outdoor-month}}` | Compares distance achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-outdoor-year}}` | Compares distance achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-indoor-week}}` | Compares distance achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-indoor-month}}` | Compares distance achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-distance-deviation-indoor-year}}` | Compares distance achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-total-week}}` | Total all walking elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{walking-elevation-total-month}}` | Total all walking elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{walking-elevation-total-year}}` | Total all walking elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{walking-elevation-outdoor-week}}` | Total outdoor-only walking elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{walking-elevation-outdoor-month}}` | Total outdoor-only walking elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{walking-elevation-outdoor-year}}` | Total outdoor-only walking elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{walking-elevation-indoor-week}}` | Total indoor-only walking elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{walking-elevation-indoor-month}}` | Total indoor-only walking elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{walking-elevation-indoor-year}}` | Total indoor-only walking elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{walking-elevation-goal-total-week}}` | The configured week elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-total-month}}` | The configured month elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-total-year}}` | The configured year elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-outdoor-week}}` | The configured week elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-outdoor-month}}` | The configured month elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-outdoor-year}}` | The configured year elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-indoor-week}}` | The configured week elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-indoor-month}}` | The configured month elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-goal-indoor-year}}` | The configured year elevation gain goal for walking (Settings → Training Goals), in m. Same value regardless of scope. |
| `{{walking-elevation-percent-total-week}}` | Percentage of the week elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-total-month}}` | Percentage of the month elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-total-year}}` | Percentage of the year elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-outdoor-week}}` | Percentage of the week elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-outdoor-month}}` | Percentage of the month elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-outdoor-year}}` | Percentage of the year elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-indoor-week}}` | Percentage of the week elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-indoor-month}}` | Percentage of the month elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-percent-indoor-year}}` | Percentage of the year elevation gain goal achieved so far (achieved-to-date ÷ goal × 100), to 2 decimals. |
| `{{walking-elevation-deviation-total-week}}` | Compares elevation gain achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-total-month}}` | Compares elevation gain achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-total-year}}` | Compares elevation gain achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-outdoor-week}}` | Compares elevation gain achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-outdoor-month}}` | Compares elevation gain achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-outdoor-year}}` | Compares elevation gain achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-indoor-week}}` | Compares elevation gain achieved-to-date against the week goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-indoor-month}}` | Compares elevation gain achieved-to-date against the month goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-elevation-deviation-indoor-year}}` | Compares elevation gain achieved-to-date against the year goal prorated to the activity's date in the period; renders as "ahead of the plan by X", "behind the plan by X", or "right on the track". |
| `{{walking-activities-total-week}}` | Number of all walking activities, so far this week (Monday 00:00 to the activity). |
| `{{walking-activities-total-month}}` | Number of all walking activities, so far this month (1st 00:00 to the activity). |
| `{{walking-activities-total-year}}` | Number of all walking activities, so far this year (Jan 1 00:00 to the activity). |
| `{{walking-activities-outdoor-week}}` | Number of outdoor-only walking activities, so far this week (Monday 00:00 to the activity). |
| `{{walking-activities-outdoor-month}}` | Number of outdoor-only walking activities, so far this month (1st 00:00 to the activity). |
| `{{walking-activities-outdoor-year}}` | Number of outdoor-only walking activities, so far this year (Jan 1 00:00 to the activity). |
| `{{walking-activities-indoor-week}}` | Number of indoor-only walking activities, so far this week (Monday 00:00 to the activity). |
| `{{walking-activities-indoor-month}}` | Number of indoor-only walking activities, so far this month (1st 00:00 to the activity). |
| `{{walking-activities-indoor-year}}` | Number of indoor-only walking activities, so far this year (Jan 1 00:00 to the activity). |
| `{{walking-count-total-week}}` | Number of all walking activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-total-month}}` | Number of all walking activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-total-year}}` | Number of all walking activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-outdoor-week}}` | Number of outdoor-only walking activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-outdoor-month}}` | Number of outdoor-only walking activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-outdoor-year}}` | Number of outdoor-only walking activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-indoor-week}}` | Number of indoor-only walking activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-indoor-month}}` | Number of indoor-only walking activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-count-indoor-year}}` | Number of indoor-only walking activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{walking-ordinal-total-week}}` | Number of all walking activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-total-month}}` | Number of all walking activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-total-year}}` | Number of all walking activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-outdoor-week}}` | Number of outdoor-only walking activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-outdoor-month}}` | Number of outdoor-only walking activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-outdoor-year}}` | Number of outdoor-only walking activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-indoor-week}}` | Number of indoor-only walking activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-indoor-month}}` | Number of indoor-only walking activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{walking-ordinal-indoor-year}}` | Number of indoor-only walking activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |

</details>

<details>
<summary><strong>Swimming placeholders (45)</strong></summary>

| Placeholder | Description |
|---|---|
| `{{swimming-distance-total-week}}` | Total all swimming distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{swimming-distance-total-month}}` | Total all swimming distance, so far this month (1st 00:00 to the activity), in km. |
| `{{swimming-distance-total-year}}` | Total all swimming distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{swimming-distance-outdoor-week}}` | Total outdoor-only swimming distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{swimming-distance-outdoor-month}}` | Total outdoor-only swimming distance, so far this month (1st 00:00 to the activity), in km. |
| `{{swimming-distance-outdoor-year}}` | Total outdoor-only swimming distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{swimming-distance-indoor-week}}` | Total indoor-only swimming distance, so far this week (Monday 00:00 to the activity), in km. |
| `{{swimming-distance-indoor-month}}` | Total indoor-only swimming distance, so far this month (1st 00:00 to the activity), in km. |
| `{{swimming-distance-indoor-year}}` | Total indoor-only swimming distance, so far this year (Jan 1 00:00 to the activity), in km. |
| `{{swimming-elevation-total-week}}` | Total all swimming elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{swimming-elevation-total-month}}` | Total all swimming elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{swimming-elevation-total-year}}` | Total all swimming elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{swimming-elevation-outdoor-week}}` | Total outdoor-only swimming elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{swimming-elevation-outdoor-month}}` | Total outdoor-only swimming elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{swimming-elevation-outdoor-year}}` | Total outdoor-only swimming elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{swimming-elevation-indoor-week}}` | Total indoor-only swimming elevation gain, so far this week (Monday 00:00 to the activity), in m. |
| `{{swimming-elevation-indoor-month}}` | Total indoor-only swimming elevation gain, so far this month (1st 00:00 to the activity), in m. |
| `{{swimming-elevation-indoor-year}}` | Total indoor-only swimming elevation gain, so far this year (Jan 1 00:00 to the activity), in m. |
| `{{swimming-activities-total-week}}` | Number of all swimming activities, so far this week (Monday 00:00 to the activity). |
| `{{swimming-activities-total-month}}` | Number of all swimming activities, so far this month (1st 00:00 to the activity). |
| `{{swimming-activities-total-year}}` | Number of all swimming activities, so far this year (Jan 1 00:00 to the activity). |
| `{{swimming-activities-outdoor-week}}` | Number of outdoor-only swimming activities, so far this week (Monday 00:00 to the activity). |
| `{{swimming-activities-outdoor-month}}` | Number of outdoor-only swimming activities, so far this month (1st 00:00 to the activity). |
| `{{swimming-activities-outdoor-year}}` | Number of outdoor-only swimming activities, so far this year (Jan 1 00:00 to the activity). |
| `{{swimming-activities-indoor-week}}` | Number of indoor-only swimming activities, so far this week (Monday 00:00 to the activity). |
| `{{swimming-activities-indoor-month}}` | Number of indoor-only swimming activities, so far this month (1st 00:00 to the activity). |
| `{{swimming-activities-indoor-year}}` | Number of indoor-only swimming activities, so far this year (Jan 1 00:00 to the activity). |
| `{{swimming-count-total-week}}` | Number of all swimming activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-total-month}}` | Number of all swimming activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-total-year}}` | Number of all swimming activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-outdoor-week}}` | Number of outdoor-only swimming activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-outdoor-month}}` | Number of outdoor-only swimming activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-outdoor-year}}` | Number of outdoor-only swimming activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-indoor-week}}` | Number of indoor-only swimming activities, so far this week (Monday 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-indoor-month}}` | Number of indoor-only swimming activities, so far this month (1st 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-count-indoor-year}}` | Number of indoor-only swimming activities, so far this year (Jan 1 00:00 to the activity) (adds a 🎉 for milestone counts: 1, 100, 500, 1000, 2000, …). |
| `{{swimming-ordinal-total-week}}` | Number of all swimming activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-total-month}}` | Number of all swimming activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-total-year}}` | Number of all swimming activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-outdoor-week}}` | Number of outdoor-only swimming activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-outdoor-month}}` | Number of outdoor-only swimming activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-outdoor-year}}` | Number of outdoor-only swimming activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-indoor-week}}` | Number of indoor-only swimming activities, so far this week (Monday 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-indoor-month}}` | Number of indoor-only swimming activities, so far this month (1st 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |
| `{{swimming-ordinal-indoor-year}}` | Number of indoor-only swimming activities, so far this year (Jan 1 00:00 to the activity), formatted as an ordinal (e.g. "11th"), with the same 🎉 milestone rule. |

</details>

## Limitations

- **Requires the `activity:write` OAuth scope.** Every other Strava call made
  by Kinetiqo is read-only (`activity:read_all`, `profile:read_all`), but
  updating a description is a *write* call. If your `STRAVA_REFRESH_TOKEN`
  was authorized before this feature existed (or without ticking the write
  permission), Strava returns `401 Unauthorized` for the update — even though
  the sync itself, and even the `GET` used to fetch the current description,
  succeed fine. Fix it via **Settings → Reconnect with Strava**, which now
  requests `activity:write` automatically; paste the new refresh token into
  `STRAVA_REFRESH_TOKEN` and restart. Once a description update 401s,
  Kinetiqo assumes the scope is missing for the rest of that sync run and
  stops attempting further updates (skipping the wasted retries) rather than
  retrying and failing on every remaining activity — it will try again on
  the next sync.
- **Indoor detection for `walking` and `swimming`**: Strava's taxonomy has no
  concept of "indoor hike/walk" or "indoor swim" distinct from `IndoorRide`/
  `VirtualRide`/`VirtualRun`. `{{walking-*-indoor-*}}` and
  `{{swimming-*-indoor-*}}` placeholders always resolve to `0` (with a
  `WARNING` logged explaining why) rather than being silently wrong.
- **Goals only exist for `cycling` and `walking`** — this matches the
  pre-existing Activity Goals feature (Settings page). `goal`/`percent`/
  `deviation` placeholders for `running` or `swimming` always resolve to an
  empty string (with a warning logged).
- **Goal placeholders ignore the `<scope>` suffix** — a single goal is
  configured per activity type per period (not per indoor/outdoor), so
  `{{cycling-distance-goal-outdoor-year}}` and
  `{{cycling-distance-goal-indoor-year}}` both return the exact same
  configured yearly goal. Only the *achieved* value used by `percent`/
  `deviation` is scope-filtered.
- **Extra Strava API calls**: fetching the current description requires one
  extra `GET /activities/{id}` per synced activity (the summary
  activity-list endpoint doesn't include `description`). This call is only
  made for activities whose applicable `UPDATE_STRAVA_*` template is
  non-empty, and updates are only pushed (`PUT /activities/{id}`) when the
  description actually changed.
- **Write-cap per sync run:** description updates are attempted only for the
  latest 30 eligible activities to reduce the chance of hitting Strava's API
  rate limits on large/full syncs.
- **No imperial units yet** — `km`/`m` are hard-coded today (as constants, in
  preparation for a future `miles`/`feet` config option).
