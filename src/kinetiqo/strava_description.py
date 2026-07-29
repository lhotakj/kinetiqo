"""UPDATE_STRAVA_* description-template engine.

Renders one of six independent ``UPDATE_STRAVA_*`` templates (see
docs/UPDATE_STRAVA.md) — chosen per activity based on its own sport type —
into a plain-text block of statistics that gets inserted at the beginning of
a synced Strava activity's description, and knows how to find/replace a
previously-inserted block without disturbing the rest of the description.

The six templates, one per activity-type/scope "bucket" (see
:data:`ACTIVITY_BUCKETS` / :func:`classify_activity_bucket`), are configured
via separate environment variables:

    UPDATE_STRAVA_CYCLING_INDOOR
    UPDATE_STRAVA_CYCLING_OUTDOOR
    UPDATE_STRAVA_RUNNING_INDOOR
    UPDATE_STRAVA_RUNNING_OUTDOOR
    UPDATE_STRAVA_WALKING
    UPDATE_STRAVA_SWIMMING

(walking and swimming have no indoor/outdoor distinction in Strava's
taxonomy, so they get a single template each).

This module has no network or Flask dependency — it only talks to the
``DatabaseRepository`` contract, so it can be unit-tested with a mocked repo
and used from both the CLI sync path and (in the future) the web UI.

Placeholder grammar
--------------------
Every placeholder is of the form ``{{<activity>-<metric>[-<modifier>]-<scope>-<period>}}``
(tokens separated by ``-``), for example::

    {{cycling-distance-total-year}}
    {{cycling-distance-goal-total-year}}
    {{cycling-distance-percent-outdoor-month}}
    {{running-count-indoor-week}}

* ``activity``: ``cycling`` | ``walking`` | ``running`` | ``swimming``
* ``metric``: ``distance`` | ``elevation`` | ``activities`` | ``count`` | ``ordinal``
* ``modifier`` (distance/elevation only, optional): ``goal`` | ``percent`` | ``deviation``
* ``scope``: ``total`` | ``outdoor`` | ``indoor``
* ``period``: ``year`` | ``month`` | ``week`` (year/month/week **to date of the activity**)

Plus the special tokens ``{{current-year}}``, ``{{current-month}}`` and ``{{new-line}}``.

Note that the placeholder grammar itself is independent of which of the six
templates is being rendered — e.g. the ``UPDATE_STRAVA_RUNNING_OUTDOOR``
template is free to reference ``{{cycling-...}}`` placeholders too, though in
practice it will usually reference ``{{running-...}}`` ones.
"""

import calendar
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from kinetiqo.config import (
    DEFAULT_UPDATE_STRAVA_PLACEMENT,
    UPDATE_STRAVA_PLACEMENT,
    UPDATE_STRAVA_PLACEMENT_BEGIN,
    UPDATE_STRAVA_PLACEMENT_END,
    UPDATE_STRAVA_PREFIX,
)
from kinetiqo.db.repository import GOAL_TYPE_CYCLING, GOAL_TYPE_WALKING
from kinetiqo.web.stats import (
    ACTIVITY_GROUPS,
    CYCLING_ACTIVITY_TYPES,
    CYCLING_INDOOR_ACTIVITY_TYPES,
    CYCLING_OUTDOOR_ACTIVITY_TYPES,
)

logger = logging.getLogger("kinetiqo")

# ---------------------------------------------------------------------------
# Unit constants — kept as module-level constants so a future "imperial units"
# config option only needs to change these (and the formatting helpers) in
# one place.
# ---------------------------------------------------------------------------
DISTANCE_UNIT = "km"
ELEVATION_UNIT = "m"

# ---------------------------------------------------------------------------
# Sport-type classification per activity group / scope.
#
# cycling & running have Strava sport_type strings that reliably distinguish
# indoor equipment (VirtualRide/IndoorRide, VirtualRun) from outdoor activity.
# walking (Walk/Hike) and swimming (Swim) have no such distinction in Strava's
# taxonomy — indoor placeholders for those two sports always resolve to 0 and
# log a warning explaining why (see docs/UPDATE_STRAVA.md "Limitations").
# ---------------------------------------------------------------------------
RUNNING_ACTIVITY_TYPES = list(ACTIVITY_GROUPS["running"]["types"])
RUNNING_INDOOR_ACTIVITY_TYPES = ["VirtualRun"]
RUNNING_OUTDOOR_ACTIVITY_TYPES = [t for t in RUNNING_ACTIVITY_TYPES if t not in RUNNING_INDOOR_ACTIVITY_TYPES]

WALKING_ACTIVITY_TYPES = list(ACTIVITY_GROUPS["walking"]["types"])
WALKING_INDOOR_ACTIVITY_TYPES: List[str] = []
WALKING_OUTDOOR_ACTIVITY_TYPES = WALKING_ACTIVITY_TYPES

SWIMMING_ACTIVITY_TYPES = list(ACTIVITY_GROUPS["swimming"]["types"])
SWIMMING_INDOOR_ACTIVITY_TYPES: List[str] = []
SWIMMING_OUTDOOR_ACTIVITY_TYPES = SWIMMING_ACTIVITY_TYPES

ACTIVITY_TYPE_SPORTS: Dict[str, Dict[str, List[str]]] = {
    "cycling": {
        "total": CYCLING_ACTIVITY_TYPES,
        "outdoor": CYCLING_OUTDOOR_ACTIVITY_TYPES,
        "indoor": CYCLING_INDOOR_ACTIVITY_TYPES,
    },
    "running": {
        "total": RUNNING_ACTIVITY_TYPES,
        "outdoor": RUNNING_OUTDOOR_ACTIVITY_TYPES,
        "indoor": RUNNING_INDOOR_ACTIVITY_TYPES,
    },
    "walking": {
        "total": WALKING_ACTIVITY_TYPES,
        "outdoor": WALKING_OUTDOOR_ACTIVITY_TYPES,
        "indoor": WALKING_INDOOR_ACTIVITY_TYPES,
    },
    "swimming": {
        "total": SWIMMING_ACTIVITY_TYPES,
        "outdoor": SWIMMING_OUTDOOR_ACTIVITY_TYPES,
        "indoor": SWIMMING_INDOOR_ACTIVITY_TYPES,
    },
}

# Tolerate the "waking" typo that appears (repeatedly) in early spec drafts.
ACTIVITY_TYPE_ALIASES = {"waking": "walking"}

# Activity goals (Settings → Training Goals) are only configured per activity
# type (not per indoor/outdoor scope) and only exist for cycling & walking.
GOAL_TYPE_BY_ACTIVITY = {
    "cycling": GOAL_TYPE_CYCLING,
    "walking": GOAL_TYPE_WALKING,
}

# ---------------------------------------------------------------------------
# Per-activity-type/scope UPDATE_STRAVA_* template bucket classification.
#
# Each synced activity is classified into exactly one of six "buckets" (based
# on its own sport_type), and the corresponding UPDATE_STRAVA_* environment
# variable / Config field supplies the template used for that activity.
# Activities whose sport_type doesn't fall into any of these buckets (e.g.
# AlpineSki, WeightTraining, ...) are left untouched entirely.
# ---------------------------------------------------------------------------
ACTIVITY_BUCKETS: Tuple[str, ...] = (
    "cycling_indoor",
    "cycling_outdoor",
    "running_indoor",
    "running_outdoor",
    "walking",
    "swimming",
)

# Config attribute name backing each bucket's template.
CONFIG_FIELD_BY_BUCKET: Dict[str, str] = {
    "cycling_indoor": "update_strava_cycling_indoor",
    "cycling_outdoor": "update_strava_cycling_outdoor",
    "running_indoor": "update_strava_running_indoor",
    "running_outdoor": "update_strava_running_outdoor",
    "walking": "update_strava_walking",
    "swimming": "update_strava_swimming",
}


def classify_activity_bucket(sport_type: str) -> Optional[str]:
    """Classify a Strava ``sport_type`` string into one of the six UPDATE_STRAVA_* buckets.

    :return: One of :data:`ACTIVITY_BUCKETS`, or ``None`` if *sport_type* isn't a
        cycling/running/walking/swimming activity (e.g. WeightTraining, AlpineSki, ...).
    """
    if sport_type in CYCLING_INDOOR_ACTIVITY_TYPES:
        return "cycling_indoor"
    if sport_type in CYCLING_OUTDOOR_ACTIVITY_TYPES:
        return "cycling_outdoor"
    if sport_type in RUNNING_INDOOR_ACTIVITY_TYPES:
        return "running_indoor"
    if sport_type in RUNNING_OUTDOOR_ACTIVITY_TYPES:
        return "running_outdoor"
    if sport_type in WALKING_ACTIVITY_TYPES:
        return "walking"
    if sport_type in SWIMMING_ACTIVITY_TYPES:
        return "swimming"
    return None


def get_template_for_activity(config, sport_type: str) -> Optional[str]:
    """Return the configured UPDATE_STRAVA_* template that applies to *sport_type*.

    :return: ``None`` both when *sport_type* doesn't map to any of the six
        buckets, and when the corresponding template is unset/empty.
    """
    bucket = classify_activity_bucket(sport_type)
    if bucket is None:
        return None
    template = getattr(config, CONFIG_FIELD_BY_BUCKET[bucket], "") or ""
    return template if template.strip() else None


def any_update_strava_template_configured(config) -> bool:
    """Whether at least one of the six ``UPDATE_STRAVA_*`` templates is non-empty.

    Used by the sync loop to decide whether to pay the cost of fetching each
    activity's current description at all.
    """
    return any((getattr(config, field, "") or "").strip() for field in CONFIG_FIELD_BY_BUCKET.values())


_METRIC_TOKENS = {"distance", "elevation", "activities", "count", "ordinal"}
_MODIFIER_TOKENS = {"goal", "percent", "deviation"}
_SCOPE_TOKENS = {"total", "outdoor", "indoor"}
_PERIOD_TOKENS = {"year", "month", "week"}
_PERIOD_GOAL_PREFIX = {"year": "yearly", "month": "monthly", "week": "weekly"}

_CELEBRATION_SUFFIX = " 🎉"

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9\-]+)\}\}")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_count(n: int) -> str:
    return f"{int(n):,}"


def _format_distance(value_km: float) -> str:
    return f"{value_km:,.1f} {DISTANCE_UNIT}"


def _format_elevation(value_m: float) -> str:
    return f"{value_m:,.0f} {ELEVATION_UNIT}"


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"


def _is_milestone(n: int) -> bool:
    """Whether *n* activities/count deserves a 🎉 (1, or any multiple of 100)."""
    if n <= 0:
        return False
    return n == 1 or n % 100 == 0


def _is_distance_milestone(curr_distance_km: float, prev_distance_km: float = 0.0) -> bool:
    """Whether distance in km reaches or crosses a positive multiple of 1000 (e.g. 1000, 2000, 6000 km) for the first time."""
    curr_val = round(curr_distance_km, 3)
    if curr_val < 1000.0:
        return False
    prev_val = round(prev_distance_km, 3)
    return (int(curr_val) // 1000) > (int(prev_val) // 1000)


def _is_elevation_milestone(curr_elevation_m: float, prev_elevation_m: float = 0.0) -> bool:
    """Whether elevation gain in m reaches or crosses a positive multiple of 1000 (e.g. 1000, 2000, 10000 m) for the first time."""
    curr_val = round(curr_elevation_m, 1)
    if curr_val < 1000.0:
        return False
    prev_val = round(prev_elevation_m, 1)
    return (int(curr_val) // 1000) > (int(prev_val) // 1000)


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n:,}{suffix}"


# ---------------------------------------------------------------------------
# Placeholder parsing
# ---------------------------------------------------------------------------

class ParsedPlaceholder:
    """A single ``{{...}}`` placeholder, broken down into its tokens."""

    __slots__ = ("activity_type", "metric", "modifier", "scope", "period", "raw")

    def __init__(self, activity_type: str, metric: str, modifier: Optional[str],
                scope: str, period: str, raw: str):
        self.activity_type = activity_type
        self.metric = metric
        self.modifier = modifier
        self.scope = scope
        self.period = period
        self.raw = raw


def _parse_placeholder(token: str) -> Optional[ParsedPlaceholder]:
    """Parse a placeholder token (without braces) into its tokens, or ``None`` if unrecognized."""
    parts = token.lower().split("-")
    if len(parts) < 4:
        return None

    activity_type = ACTIVITY_TYPE_ALIASES.get(parts[0], parts[0])
    if activity_type not in ACTIVITY_TYPE_SPORTS:
        return None

    metric = parts[1]
    if metric not in _METRIC_TOKENS:
        return None

    modifier = None
    if metric in ("distance", "elevation") and len(parts) == 5 and parts[2] in _MODIFIER_TOKENS:
        modifier = parts[2]
        scope, period = parts[3], parts[4]
    elif len(parts) == 4:
        scope, period = parts[2], parts[3]
    else:
        return None

    if scope not in _SCOPE_TOKENS or period not in _PERIOD_TOKENS:
        return None

    return ParsedPlaceholder(activity_type, metric, modifier, scope, period, token)


# ---------------------------------------------------------------------------
# Period math — "year/month/week to date of the activity"
# ---------------------------------------------------------------------------

def _parse_activity_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None


def _period_bounds(activity_dt: datetime, period: str) -> Tuple[datetime, datetime, float]:
    """Return ``(period_start, activity_dt, elapsed_fraction)`` for *period*.

    ``elapsed_fraction`` is how far through the period (year/month/week) the
    activity's own timestamp falls — used to prorate goals for the
    "deviation" (ahead/behind plan) placeholders.
    """
    if period == "year":
        start = activity_dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        total_seconds = (366 if calendar.isleap(activity_dt.year) else 365) * 86400
    elif period == "month":
        start = activity_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_in_month = calendar.monthrange(activity_dt.year, activity_dt.month)[1]
        total_seconds = days_in_month * 86400
    else:  # week — Monday-based, matching the rest of the app (e.g. MEGA Stats)
        monday = activity_dt - timedelta(days=activity_dt.weekday())
        start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        total_seconds = 7 * 86400

    elapsed_seconds = (activity_dt - start).total_seconds()
    elapsed_fraction = max(0.0, min(1.0, elapsed_seconds / total_seconds)) if total_seconds > 0 else 0.0
    return start, activity_dt, elapsed_fraction


# ---------------------------------------------------------------------------
# Template tokenizing / rendering / merge helpers
# ---------------------------------------------------------------------------

def _iter_template_parts(template: str):
    pos = 0
    for m in PLACEHOLDER_RE.finditer(template):
        yield "literal", template[pos:m.start()]
        yield "placeholder", m.group(1)
        pos = m.end()
    yield "literal", template[pos:]


def extract_placeholders(template: str) -> List[str]:
    """Return the unique list of placeholder tokens (without braces) found in *template*."""
    seen: List[str] = []
    for kind, val in _iter_template_parts(template):
        if kind == "placeholder" and val not in seen:
            seen.append(val)
    return seen


def render_template(template: str, resolver: Callable[[str], str]) -> str:
    """Render *template*, calling ``resolver(token)`` for every ``{{token}}`` found."""
    parts = []
    for kind, val in _iter_template_parts(template):
        if kind == "literal":
            parts.append(val)
        else:
            try:
                parts.append(resolver(val) or "")
            except Exception as e:
                logger.warning(f"UPDATE_STRAVA: error resolving placeholder '{{{{{val}}}}}': {e}")
                parts.append("")
    return "".join(parts)


def _normalize_newlines(value: str) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n")


def _build_prefixed_stats_line(rendered_block: str) -> str:
    """Build the canonical one-line stats block persisted in Strava descriptions."""
    rendered = _normalize_newlines(rendered_block).strip("\n")
    # New behavior stores Kinetiqo stats as a single line; flatten any
    # accidental embedded newlines from templates.
    rendered = " ".join(part.strip() for part in rendered.split("\n") if part.strip())
    if rendered.startswith(UPDATE_STRAVA_PREFIX):
        rendered = rendered[len(UPDATE_STRAVA_PREFIX):].strip()
    if rendered:
        return f"{UPDATE_STRAVA_PREFIX} {rendered}\n"
    return f"{UPDATE_STRAVA_PREFIX}\n"


def build_match_pattern(template: str) -> re.Pattern:
    """Return a regex that matches one previously-inserted Kinetiqo stats line."""
    del template  # Prefix-based replacement no longer derives matching from template text.
    prefix = re.escape(UPDATE_STRAVA_PREFIX)
    return re.compile(rf"(?m)^{prefix}[^\n]*(?:\n|$)")


def merge_description(existing_description: str, template: str, rendered_block: str,
                       placement: str = DEFAULT_UPDATE_STRAVA_PLACEMENT) -> str:
    """Insert/replace *rendered_block* into *existing_description*.

    Any line starting with :data:`kinetiqo.config.UPDATE_STRAVA_PREFIX` is
    treated as Kinetiqo-owned and removed before inserting the newly rendered
    line. The fresh line is inserted at the beginning or end of
    *existing_description*, per *placement* (one of
    :data:`kinetiqo.config.UPDATE_STRAVA_PLACEMENT` — ``"begin"`` or
    ``"end"``, default ``"end"``). The rest of the description (anything the
    user or Strava wrote) is always preserved.
    """
    existing_description = _normalize_newlines(existing_description or "")
    pattern = build_match_pattern(template)
    existing_without_kinetiqo = pattern.sub("", existing_description)
    rendered_block = _build_prefixed_stats_line(rendered_block)

    if not existing_without_kinetiqo.strip():
        return rendered_block

    if placement not in UPDATE_STRAVA_PLACEMENT:
        logger.warning(
            f"UPDATE_STRAVA: unknown placement '{placement}' — falling back to "
            f"'{DEFAULT_UPDATE_STRAVA_PLACEMENT}'."
        )
        placement = DEFAULT_UPDATE_STRAVA_PLACEMENT

    if placement == UPDATE_STRAVA_PLACEMENT_BEGIN:
        joiner = "" if rendered_block.endswith("\n") else "\n\n"
        return rendered_block + joiner + existing_without_kinetiqo

    assert placement == UPDATE_STRAVA_PLACEMENT_END
    joiner = "" if existing_without_kinetiqo.endswith("\n") else "\n\n"
    return existing_without_kinetiqo + joiner + rendered_block


# ---------------------------------------------------------------------------
# Value resolution — talks to the repository
# ---------------------------------------------------------------------------

class DescriptionContext:
    """Resolves placeholder values for a sync run.

    One instance should be reused across all activities processed in a
    single ``SyncService.sync()`` call so that the athlete's goals are only
    fetched once.
    """

    def __init__(self, config, repo):
        self.config = config
        self.repo = repo
        self._goals_by_type: Optional[Dict[int, Dict[str, Any]]] = None

    def _goals(self) -> Dict[int, Dict[str, Any]]:
        if self._goals_by_type is None:
            self._goals_by_type = {}
            try:
                profile = self.repo.get_profile()
                athlete_id = profile.get("athlete_id") if profile else None
                if athlete_id:
                    for row in self.repo.get_goals(athlete_id):
                        self._goals_by_type[int(row["activity_type_id"])] = row
            except Exception as e:
                logger.warning(f"UPDATE_STRAVA: failed to load activity goals: {e}")
        return self._goals_by_type

    def _stats(self, types: List[str], start_str: str, end_str: str, cache: dict) -> Dict[str, float]:
        key = (tuple(types), start_str, end_str)
        if key in cache:
            return cache[key]
        totals = self.repo.get_activities_totals(types=types, start_date=start_str, end_date=end_str)
        count = self.repo.count_activities(types=types, start_date=start_str, end_date=end_str)
        result = {
            "distance_km": float(totals.get("total_distance") or 0) / 1000.0,
            "elevation_m": float(totals.get("total_elevation") or 0),
            "count": int(count or 0),
        }
        cache[key] = result
        return result

    def _resolve_token(self, token: str, activity_dt: datetime, cache: dict) -> str:
        if token == "new-line":
            return "\n"
        if token == "current-year":
            return str(activity_dt.year)
        if token == "current-month":
            return activity_dt.strftime("%B")

        parsed = _parse_placeholder(token)
        if parsed is None:
            logger.warning(f"UPDATE_STRAVA: unrecognized placeholder '{{{{{token}}}}}' — leaving it empty.")
            return ""

        sports = ACTIVITY_TYPE_SPORTS[parsed.activity_type]
        scope_types = sports.get(parsed.scope) or []
        start_dt, end_dt, elapsed_fraction = _period_bounds(activity_dt, parsed.period)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        prev_end_dt = end_dt - timedelta(microseconds=1)
        prev_end_str = prev_end_dt.strftime("%Y-%m-%d %H:%M:%S.%f")

        if not scope_types:
            logger.warning(
                f"UPDATE_STRAVA: '{parsed.scope}' {parsed.activity_type} activities cannot be "
                f"distinguished by Strava's sport type — '{{{{{token}}}}}' resolved to 0."
            )
            stats = {"distance_km": 0.0, "elevation_m": 0.0, "count": 0}
            prev_stats = {"distance_km": 0.0, "elevation_m": 0.0, "count": 0}
        else:
            try:
                stats = self._stats(scope_types, start_str, end_str, cache)
                prev_stats = self._stats(scope_types, start_str, prev_end_str, cache)
            except Exception as e:
                logger.warning(f"UPDATE_STRAVA: failed to fetch data for '{{{{{token}}}}}': {e}")
                return ""

        if parsed.metric == "activities":
            return _format_count(stats["count"])
        if parsed.metric == "count":
            suffix = _CELEBRATION_SUFFIX if _is_milestone(stats["count"]) else ""
            return _format_count(stats["count"]) + suffix
        if parsed.metric == "ordinal":
            suffix = _CELEBRATION_SUFFIX if _is_milestone(stats["count"]) else ""
            return _ordinal(stats["count"]) + suffix

        # metric is "distance" or "elevation", possibly with a goal/percent/deviation modifier
        metric_key = parsed.metric
        achieved = stats["distance_km"] if metric_key == "distance" else stats["elevation_m"]

        if parsed.modifier is None:
            if metric_key == "distance":
                prev_achieved = prev_stats["distance_km"]
                suffix = _CELEBRATION_SUFFIX if _is_distance_milestone(achieved, prev_achieved) else ""
                return _format_distance(achieved) + suffix
            else:
                prev_achieved = prev_stats["elevation_m"]
                suffix = _CELEBRATION_SUFFIX if _is_elevation_milestone(achieved, prev_achieved) else ""
                return _format_elevation(achieved) + suffix

        goal_type_id = GOAL_TYPE_BY_ACTIVITY.get(parsed.activity_type)
        goal_row = self._goals().get(goal_type_id) if goal_type_id else None
        goal_field = f"{_PERIOD_GOAL_PREFIX[parsed.period]}_{metric_key}_goal"
        goal_value = goal_row.get(goal_field) if goal_row else None

        if goal_value is None or float(goal_value) <= 0:
            logger.warning(
                f"UPDATE_STRAVA: no {parsed.period}ly {metric_key} goal configured for "
                f"'{parsed.activity_type}' — '{{{{{token}}}}}' resolved to empty."
            )
            return ""
        goal_value = float(goal_value)

        if parsed.modifier == "goal":
            return _format_distance(goal_value) if metric_key == "distance" else _format_elevation(goal_value)

        if parsed.modifier == "percent":
            return _format_percent(achieved / goal_value * 100.0)

        # deviation: compare achieved-to-date against the prorated ("planned") goal
        planned = goal_value * elapsed_fraction
        diff = achieved - planned
        formatter = _format_distance if metric_key == "distance" else _format_elevation
        if round(diff, 2) == 0:
            return "right on the track"
        if diff > 0:
            return f"ahead of the plan by {formatter(diff)}"
        return f"behind the plan by {formatter(abs(diff))}"

    def render_for_activity(self, template: str, activity_start_date: Any,
                            existing_description: str) -> Optional[str]:
        """Render *template* for the activity dated *activity_start_date* and merge it
        into *existing_description*.

        The merged block is placed per ``config.update_strava_placement``
        (``"begin"`` or ``"end"``, default ``"end"``) — see
        :func:`merge_description`.

        :return: The full new description text, or ``None`` if the activity date
            could not be parsed (nothing is changed in that case).
        """
        if not template or not template.strip():
            return None

        activity_dt = _parse_activity_datetime(activity_start_date)
        if activity_dt is None:
            logger.warning(
                f"UPDATE_STRAVA: could not parse activity start date '{activity_start_date}' — "
                "skipping description update for this activity."
            )
            return None

        placement = getattr(self.config, "update_strava_placement", DEFAULT_UPDATE_STRAVA_PLACEMENT) \
            or DEFAULT_UPDATE_STRAVA_PLACEMENT
        cache: dict = {}
        rendered_block = render_template(template, lambda tok: self._resolve_token(tok, activity_dt, cache))
        return merge_description(existing_description or "", template, rendered_block, placement=placement)


def render_and_merge_description(config, repo, activity: dict, existing_description: str) -> Optional[str]:
    """Convenience one-shot wrapper around :class:`DescriptionContext`.

    Selects the correct ``UPDATE_STRAVA_*`` template for *activity* based on
    its own ``sport_type`` (see :func:`get_template_for_activity`), then
    renders and merges it. Returns ``None`` if the activity's sport type
    doesn't map to any of the six template buckets, or if the applicable
    template is unset/empty.

    Prefer instantiating :class:`DescriptionContext` directly and reusing it
    across a whole sync run (so goals are only fetched once); this function
    is provided for simple / one-off callers and tests.
    """
    template = get_template_for_activity(config, activity.get("sport_type", ""))
    if not template:
        return None
    context = DescriptionContext(config, repo)
    return context.render_for_activity(template, activity.get("start_date"), existing_description)
