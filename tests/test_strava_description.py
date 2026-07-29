"""Mocked unit tests for the UPDATE_STRAVA description-template engine.

Follows the style of ``tests/test_sync_logic.py``: no live database or Strava
API is ever contacted — the ``DatabaseRepository`` is mocked with
``unittest.mock.MagicMock`` and stubbed with canned return values.
"""

import unittest
from unittest.mock import MagicMock

from kinetiqo.config import UPDATE_STRAVA_PLACEMENT_BEGIN, UPDATE_STRAVA_PLACEMENT_END, UPDATE_STRAVA_PREFIX
from kinetiqo.db.repository import GOAL_TYPE_CYCLING, GOAL_TYPE_WALKING
from kinetiqo.strava_description import (
    DescriptionContext,
    ParsedPlaceholder,
    _is_milestone,
    _ordinal,
    _parse_placeholder,
    _period_bounds,
    any_update_strava_template_configured,
    build_match_pattern,
    classify_activity_bucket,
    extract_placeholders,
    get_template_for_activity,
    merge_description,
    render_and_merge_description,
    render_template,
)


class TestParsePlaceholder(unittest.TestCase):
    """Unit tests for placeholder tokenizing."""

    def test_simple_four_token_placeholder(self):
        parsed = _parse_placeholder("cycling-distance-total-year")
        self.assertIsInstance(parsed, ParsedPlaceholder)
        self.assertEqual(parsed.activity_type, "cycling")
        self.assertEqual(parsed.metric, "distance")
        self.assertIsNone(parsed.modifier)
        self.assertEqual(parsed.scope, "total")
        self.assertEqual(parsed.period, "year")

    def test_five_token_placeholder_with_modifier(self):
        parsed = _parse_placeholder("cycling-distance-goal-outdoor-month")
        self.assertEqual(parsed.modifier, "goal")
        self.assertEqual(parsed.scope, "outdoor")
        self.assertEqual(parsed.period, "month")

    def test_waking_typo_alias_resolves_to_walking(self):
        parsed = _parse_placeholder("waking-distance-percent-total-year")
        self.assertEqual(parsed.activity_type, "walking")

    def test_unknown_activity_type_returns_none(self):
        self.assertIsNone(_parse_placeholder("rowing-distance-total-year"))

    def test_unknown_metric_returns_none(self):
        self.assertIsNone(_parse_placeholder("cycling-bananas-total-year"))

    def test_modifier_on_count_metric_is_invalid(self):
        # "count" doesn't support goal/percent/deviation modifiers.
        self.assertIsNone(_parse_placeholder("cycling-count-goal-total-year"))

    def test_too_few_tokens_returns_none(self):
        self.assertIsNone(_parse_placeholder("cycling-distance-year"))

    def test_case_insensitive(self):
        parsed = _parse_placeholder("CYCLING-DISTANCE-TOTAL-YEAR")
        self.assertEqual(parsed.activity_type, "cycling")


class TestFormattingHelpers(unittest.TestCase):
    """Unit tests for number/ordinal/milestone formatting helpers."""

    def test_ordinal_suffixes(self):
        self.assertEqual(_ordinal(1), "1st")
        self.assertEqual(_ordinal(2), "2nd")
        self.assertEqual(_ordinal(3), "3rd")
        self.assertEqual(_ordinal(4), "4th")
        self.assertEqual(_ordinal(11), "11th")
        self.assertEqual(_ordinal(12), "12th")
        self.assertEqual(_ordinal(13), "13th")
        self.assertEqual(_ordinal(21), "21st")
        self.assertEqual(_ordinal(22), "22nd")
        self.assertEqual(_ordinal(111), "111th")
        self.assertEqual(_ordinal(1001), "1,001st")

    def test_milestone_detection(self):
        for n in (1, 100, 200, 500, 1000, 1500, 2000, 3000):
            self.assertTrue(_is_milestone(n), f"{n} should be a milestone")
        for n in (0, 2, 99, 101, 499, 999):
            self.assertFalse(_is_milestone(n), f"{n} should not be a milestone")

    def test_distance_and_elevation_milestones(self):
        from kinetiqo.strava_description import _is_distance_milestone, _is_elevation_milestone
        # Single argument fallback (defaults to prev_val = 0.0)
        self.assertTrue(_is_distance_milestone(1000.0))
        self.assertTrue(_is_distance_milestone(6000.0))
        self.assertFalse(_is_distance_milestone(650.0))

        # First activity reaching or crossing 1,000 km milestone threshold (e.g. 990 -> 1001)
        self.assertTrue(_is_distance_milestone(1001.0, 990.0))
        self.assertTrue(_is_distance_milestone(1000.0, 990.0))
        self.assertTrue(_is_distance_milestone(2005.0, 1990.0))

        # Subsequent activity in same milestone range (e.g. 1001 -> 1050) does not re-trigger
        self.assertFalse(_is_distance_milestone(1050.0, 1001.0))
        self.assertFalse(_is_distance_milestone(650.0, 600.0))

        # Elevation milestones
        self.assertTrue(_is_elevation_milestone(1000.0))
        self.assertTrue(_is_elevation_milestone(1050.0, 950.0))
        self.assertFalse(_is_elevation_milestone(1100.0, 1050.0))
        self.assertFalse(_is_elevation_milestone(750.0))


class TestPeriodBounds(unittest.TestCase):
    """Unit tests for period-math (year/month/week to date of the activity)."""

    def test_year_bounds(self):
        from datetime import datetime
        activity_dt = datetime(2026, 7, 22, 12, 0, 0)
        start, end, frac = _period_bounds(activity_dt, "year")
        self.assertEqual(start, datetime(2026, 1, 1, 0, 0, 0))
        self.assertEqual(end, activity_dt)
        self.assertGreater(frac, 0.5)
        self.assertLess(frac, 0.6)

    def test_month_bounds(self):
        from datetime import datetime
        activity_dt = datetime(2026, 7, 15, 0, 0, 0)
        start, end, frac = _period_bounds(activity_dt, "month")
        self.assertEqual(start, datetime(2026, 7, 1, 0, 0, 0))
        self.assertAlmostEqual(frac, 14 / 31, places=3)

    def test_week_bounds_monday_based(self):
        from datetime import datetime
        # 2026-07-22 is a Wednesday.
        activity_dt = datetime(2026, 7, 22, 12, 0, 0)
        start, end, frac = _period_bounds(activity_dt, "week")
        self.assertEqual(start.weekday(), 0)  # Monday
        self.assertEqual(start.date(), datetime(2026, 7, 20).date())


class TestTemplateRendering(unittest.TestCase):
    """Unit tests for template tokenizing/rendering (no repo involved)."""

    def test_extract_placeholders_preserves_order_and_dedups(self):
        template = "A {{foo}} B {{bar}} C {{foo}}"
        self.assertEqual(extract_placeholders(template), ["foo", "bar"])

    def test_render_template_calls_resolver_per_placeholder(self):
        template = "Hello {{name}}, you are {{age}} years old."
        resolver = {"name": "World", "age": "42"}.get
        result = render_template(template, resolver)
        self.assertEqual(result, "Hello World, you are 42 years old.")

    def test_render_template_resolver_exception_becomes_empty_string(self):
        def bad_resolver(token):
            raise ValueError("boom")
        result = render_template("X{{token}}Y", bad_resolver)
        self.assertEqual(result, "XY")

    def test_match_pattern_targets_prefixed_line(self):
        pattern = build_match_pattern("ignored-now")
        self.assertIsNotNone(pattern.search(f"{UPDATE_STRAVA_PREFIX} Stats: 42\n"))
        self.assertIsNotNone(pattern.search(f"{UPDATE_STRAVA_PREFIX}Stats: 42\n"))
        self.assertIsNone(pattern.search("Stats: 42\n"))


class TestMergeDescription(unittest.TestCase):
    """Unit tests for the prefix-based find/replace-or-insert (begin/end) merge logic."""

    def test_appends_at_end_by_default_when_no_existing_block_found(self):
        existing = "My hand-written ride notes."
        template = "Stats: {{value}}."
        rendered = "Stats: 42."
        result = merge_description(existing, template, rendered)
        self.assertTrue(result.endswith(f"{UPDATE_STRAVA_PREFIX} {rendered}\n"))
        self.assertIn(existing, result)

    def test_placement_end_explicit_appends_at_end(self):
        existing = "My hand-written ride notes."
        template = "Stats: {{value}}."
        rendered = "Stats: 42."
        result = merge_description(existing, template, rendered, placement=UPDATE_STRAVA_PLACEMENT_END)
        self.assertEqual(result, existing + "\n\n" + f"{UPDATE_STRAVA_PREFIX} {rendered}\n")

    def test_placement_begin_prepends(self):
        existing = "My hand-written ride notes."
        template = "Stats: {{value}}."
        rendered = "Stats: 42."
        result = merge_description(existing, template, rendered, placement=UPDATE_STRAVA_PLACEMENT_BEGIN)
        self.assertTrue(result.startswith(f"{UPDATE_STRAVA_PREFIX} {rendered}\n"))
        self.assertIn(existing, result)

    def test_invalid_placement_falls_back_to_end(self):
        existing = "My hand-written ride notes."
        template = "Stats: {{value}}."
        rendered = "Stats: 42."
        result = merge_description(existing, template, rendered, placement="somewhere-else")
        self.assertTrue(result.endswith(f"{UPDATE_STRAVA_PREFIX} {rendered}\n"))

    def test_replaces_prefixed_block_and_honors_placement(self):
        template = "Stats: {{value}}.{{new-line}}"
        old_rendered = f"{UPDATE_STRAVA_PREFIX} Stats: 41.\n"
        new_rendered = "Stats: 42.\n"
        existing = old_rendered + "My hand-written ride notes."
        for placement in (UPDATE_STRAVA_PLACEMENT_BEGIN, UPDATE_STRAVA_PLACEMENT_END):
            with self.subTest(placement=placement):
                result = merge_description(existing, template, new_rendered, placement=placement)
                if placement == UPDATE_STRAVA_PLACEMENT_BEGIN:
                    self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} Stats: 42.\nMy hand-written ride notes.")
                else:
                    self.assertEqual(result, f"My hand-written ride notes.\n\n{UPDATE_STRAVA_PREFIX} Stats: 42.\n")

    def test_empty_existing_description_just_uses_rendered_block(self):
        result = merge_description("", "Stats: {{value}}.", "Stats: 42.")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} Stats: 42.\n")

    def test_user_text_is_never_lost(self):
        template = "Stats: {{value}}.{{new-line}}"
        existing = f"{UPDATE_STRAVA_PREFIX} Stats: 10.\nGreat ride with @friend, saw a fox!"
        rendered = "Stats: 20.\n"
        result = merge_description(existing, template, rendered)
        self.assertIn("Great ride with @friend, saw a fox!", result)
        self.assertNotIn("Stats: 10.", result)
        self.assertIn(f"{UPDATE_STRAVA_PREFIX} Stats: 20.\n", result)


class TestDescriptionContextResolution(unittest.TestCase):
    """Unit tests for DescriptionContext value resolution against a mocked repo."""

    def _make_repo(self, totals=None, count=0, goals=None, profile=None):
        repo = MagicMock()
        repo.get_profile.return_value = profile or {"athlete_id": 123}
        repo.get_goals.return_value = goals or []
        repo.get_activities_totals.return_value = totals or {"total_distance": 0, "total_elevation": 0}
        repo.count_activities.return_value = count
        return repo

    def test_distance_and_elevation_totals(self):
        repo = self._make_repo(totals={"total_distance": 6540000, "total_elevation": 12345})
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity(
            "{{cycling-distance-total-year}} / {{cycling-elevation-total-year}}",
            "2026-07-22T08:00:00Z",
            "",
        )
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 6,540.0 km / 12,345 m\n")

    def test_distance_first_reaching_1000km_triggers_celebration(self):
        repo = self._make_repo()
        # Mock get_activities_totals to return 990 km for previous end_date, 1001 km for current end_date
        def side_effect_totals(types, start_date, end_date):
            if "07:59:59" in end_date:
                return {"total_distance": 990000, "total_elevation": 0}
            return {"total_distance": 1001000, "total_elevation": 0}

        repo.get_activities_totals.side_effect = side_effect_totals
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-distance-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertIn("1,001.0 km", result)
        self.assertIn("🎉", result)

    def test_distance_subsequent_activity_after_1000km_has_no_celebration(self):
        repo = self._make_repo()
        # Mock get_activities_totals to return 1001 km for previous end_date, 1050 km for current end_date
        def side_effect_totals(types, start_date, end_date):
            if "07:59:59" in end_date:
                return {"total_distance": 1001000, "total_elevation": 0}
            return {"total_distance": 1050000, "total_elevation": 0}

        repo.get_activities_totals.side_effect = side_effect_totals
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-distance-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 1,050.0 km\n")
        self.assertNotIn("🎉", result)

    def test_count_with_milestone_celebration(self):
        repo = self._make_repo(count=100)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-count-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertIn(f"{UPDATE_STRAVA_PREFIX} ", result)
        self.assertIn("100", result)
        self.assertIn("🎉", result)

    def test_count_without_milestone_has_no_celebration(self):
        repo = self._make_repo(count=42)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-count-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 42\n")

    def test_ordinal_formatting(self):
        repo = self._make_repo(count=11)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-ordinal-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 11th\n")

    def test_activities_metric_has_no_celebration_ever(self):
        repo = self._make_repo(count=100)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-activities-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 100\n")

    def test_goal_placeholder_returns_configured_goal(self):
        goals = [{"activity_type_id": GOAL_TYPE_CYCLING, "yearly_distance_goal": 5000, "yearly_elevation_goal": 50000}]
        repo = self._make_repo(goals=goals)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-distance-goal-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 5,000.0 km\n")

    def test_percent_placeholder_computes_percentage(self):
        goals = [{"activity_type_id": GOAL_TYPE_CYCLING, "yearly_distance_goal": 1000}]
        repo = self._make_repo(totals={"total_distance": 550000, "total_elevation": 0}, goals=goals)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-distance-percent-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 55.00%\n")

    def test_deviation_ahead_of_plan(self):
        # Elapsed fraction of year at 2026-01-02 is tiny, so any real achieved
        # distance will be "ahead of the plan".
        goals = [{"activity_type_id": GOAL_TYPE_CYCLING, "yearly_distance_goal": 3650}]
        repo = self._make_repo(totals={"total_distance": 100000, "total_elevation": 0}, goals=goals)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-distance-deviation-total-year}}", "2026-01-02T08:00:00Z", "")
        self.assertIn("ahead of the plan by", result)

    def test_deviation_behind_plan(self):
        goals = [{"activity_type_id": GOAL_TYPE_CYCLING, "yearly_distance_goal": 3650}]
        # Late in the year but with almost no distance achieved -> behind plan.
        repo = self._make_repo(totals={"total_distance": 1000, "total_elevation": 0}, goals=goals)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-distance-deviation-total-year}}", "2026-12-30T08:00:00Z", "")
        self.assertIn("behind the plan by", result)

    def test_missing_goal_resolves_to_empty_string(self):
        repo = self._make_repo(goals=[])
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{cycling-distance-goal-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX}\n")

    def test_running_goal_placeholder_unsupported_resolves_empty(self):
        # Only cycling & walking have configurable goals.
        repo = self._make_repo()
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{running-distance-goal-total-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX}\n")

    def test_walking_indoor_scope_resolves_to_zero(self):
        repo = self._make_repo(totals={"total_distance": 999000, "total_elevation": 0}, count=5)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{walking-distance-indoor-year}}", "2026-07-22T08:00:00Z", "")
        # Indoor walking is never distinguishable -> always resolves to 0,
        # regardless of what the mocked repo would otherwise return.
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 0.0 km\n")

    def test_swimming_indoor_scope_resolves_to_zero_count(self):
        repo = self._make_repo(count=5)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{swimming-count-indoor-year}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 0\n")

    def test_unrecognized_placeholder_resolves_to_empty_string(self):
        repo = self._make_repo()
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{totally-not-a-thing}}", "2026-07-22T08:00:00Z", "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX}\n")

    def test_current_year_and_month_and_new_line(self):
        repo = self._make_repo()
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity(
            "{{current-year}}-{{current-month}}{{new-line}}end", "2026-07-22T08:00:00Z", ""
        )
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 2026-July end\n")

    def test_goals_are_only_fetched_once_per_context(self):
        goals = [{"activity_type_id": GOAL_TYPE_CYCLING, "yearly_distance_goal": 1000}]
        repo = self._make_repo(goals=goals)
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        ctx.render_for_activity("{{cycling-distance-goal-total-year}}", "2026-07-22T08:00:00Z", "")
        ctx.render_for_activity("{{cycling-distance-goal-total-month}}", "2026-07-23T08:00:00Z", "")
        repo.get_goals.assert_called_once()

    def test_invalid_activity_date_returns_none(self):
        repo = self._make_repo()
        ctx = DescriptionContext(config=MagicMock(), repo=repo)
        result = ctx.render_for_activity("{{current-year}}", "not-a-date", "existing description")
        self.assertIsNone(result)

    def test_merge_replaces_previous_render_for_same_context(self):
        repo = self._make_repo(count=5)
        ctx = DescriptionContext(config=MagicMock(update_strava_placement="begin"), repo=repo)
        template = "You have done {{cycling-count-total-year}} rides.{{new-line}}"
        first = ctx.render_for_activity(template, "2026-07-22T08:00:00Z", "")
        self.assertEqual(first, f"{UPDATE_STRAVA_PREFIX} You have done 5 rides.\n")

        repo.count_activities.return_value = 6
        second = ctx.render_for_activity(template, "2026-07-23T08:00:00Z", first + "My own notes.")
        self.assertEqual(second, f"{UPDATE_STRAVA_PREFIX} You have done 6 rides.\nMy own notes.")

    def test_placement_defaults_to_end_when_config_omits_it(self):
        """A Config without update_strava_placement (or a bare MagicMock) should still default to 'end'."""
        repo = self._make_repo(count=5)
        config = MagicMock(spec=[])  # no attributes at all, including update_strava_placement
        ctx = DescriptionContext(config=config, repo=repo)
        template = "You have done {{cycling-count-total-year}} rides.{{new-line}}"
        result = ctx.render_for_activity(template, "2026-07-22T08:00:00Z", "My own notes.")
        self.assertEqual(result, f"My own notes.\n\n{UPDATE_STRAVA_PREFIX} You have done 5 rides.\n")

    def test_placement_begin_inserts_before_existing_text(self):
        repo = self._make_repo(count=5)
        config = MagicMock(update_strava_placement="begin")
        ctx = DescriptionContext(config=config, repo=repo)
        template = "You have done {{cycling-count-total-year}} rides.{{new-line}}"
        result = ctx.render_for_activity(template, "2026-07-22T08:00:00Z", "My own notes.")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} You have done 5 rides.\nMy own notes.")

    def test_placement_end_appends_after_existing_text(self):
        repo = self._make_repo(count=5)
        config = MagicMock(update_strava_placement="end")
        ctx = DescriptionContext(config=config, repo=repo)
        template = "You have done {{cycling-count-total-year}} rides.{{new-line}}"
        result = ctx.render_for_activity(template, "2026-07-22T08:00:00Z", "My own notes.")
        self.assertEqual(result, f"My own notes.\n\n{UPDATE_STRAVA_PREFIX} You have done 5 rides.\n")


class TestRenderAndMergeConvenienceWrapper(unittest.TestCase):
    """Unit tests for the one-shot render_and_merge_description() helper."""

    def test_returns_none_when_template_not_configured(self):
        config = MagicMock(update_strava_cycling_indoor="", update_strava_cycling_outdoor="",
                            update_strava_running_indoor="", update_strava_running_outdoor="",
                            update_strava_walking="", update_strava_swimming="")
        repo = MagicMock()
        result = render_and_merge_description(
            config, repo, {"start_date": "2026-07-22T08:00:00Z", "sport_type": "Ride"}, "")
        self.assertIsNone(result)

    def test_renders_when_template_configured(self):
        config = MagicMock(update_strava_cycling_indoor="", update_strava_cycling_outdoor="{{current-year}}",
                            update_strava_running_indoor="", update_strava_running_outdoor="",
                            update_strava_walking="", update_strava_swimming="")
        repo = MagicMock()
        repo.get_profile.return_value = {"athlete_id": 1}
        repo.get_goals.return_value = []
        activity = {"start_date": "2026-07-22T08:00:00Z", "sport_type": "Ride"}
        result = render_and_merge_description(config, repo, activity, "")
        self.assertEqual(result, f"{UPDATE_STRAVA_PREFIX} 2026\n")

    def test_returns_none_when_sport_type_not_in_any_bucket(self):
        config = MagicMock(update_strava_cycling_indoor="{{current-year}}", update_strava_cycling_outdoor="{{current-year}}",
                            update_strava_running_indoor="{{current-year}}", update_strava_running_outdoor="{{current-year}}",
                            update_strava_walking="{{current-year}}", update_strava_swimming="{{current-year}}")
        repo = MagicMock()
        activity = {"start_date": "2026-07-22T08:00:00Z", "sport_type": "WeightTraining"}
        result = render_and_merge_description(config, repo, activity, "")
        self.assertIsNone(result)


class TestActivityBucketClassification(unittest.TestCase):
    """Unit tests for classify_activity_bucket() / get_template_for_activity() / any_update_strava_template_configured()."""

    def test_classify_cycling_indoor(self):
        self.assertEqual(classify_activity_bucket("VirtualRide"), "cycling_indoor")
        self.assertEqual(classify_activity_bucket("IndoorRide"), "cycling_indoor")

    def test_classify_cycling_outdoor(self):
        self.assertEqual(classify_activity_bucket("Ride"), "cycling_outdoor")
        self.assertEqual(classify_activity_bucket("MountainBikeRide"), "cycling_outdoor")

    def test_classify_running_indoor(self):
        self.assertEqual(classify_activity_bucket("VirtualRun"), "running_indoor")

    def test_classify_running_outdoor(self):
        self.assertEqual(classify_activity_bucket("Run"), "running_outdoor")
        self.assertEqual(classify_activity_bucket("TrailRun"), "running_outdoor")

    def test_classify_walking(self):
        self.assertEqual(classify_activity_bucket("Walk"), "walking")
        self.assertEqual(classify_activity_bucket("Hike"), "walking")

    def test_classify_swimming(self):
        self.assertEqual(classify_activity_bucket("Swim"), "swimming")

    def test_classify_unmatched_sport_type_returns_none(self):
        self.assertIsNone(classify_activity_bucket("WeightTraining"))
        self.assertIsNone(classify_activity_bucket("AlpineSki"))
        self.assertIsNone(classify_activity_bucket(""))

    def test_get_template_for_activity_returns_bucket_template(self):
        config = MagicMock(update_strava_cycling_outdoor="Hello {{current-year}}")
        self.assertEqual(get_template_for_activity(config, "Ride"), "Hello {{current-year}}")

    def test_get_template_for_activity_returns_none_when_empty(self):
        config = MagicMock(update_strava_cycling_outdoor="")
        self.assertIsNone(get_template_for_activity(config, "Ride"))

    def test_get_template_for_activity_returns_none_for_unmatched_sport_type(self):
        config = MagicMock(update_strava_cycling_outdoor="Hello")
        self.assertIsNone(get_template_for_activity(config, "WeightTraining"))

    def test_any_update_strava_template_configured_false_when_all_empty(self):
        config = MagicMock(update_strava_cycling_indoor="", update_strava_cycling_outdoor="",
                            update_strava_running_indoor="", update_strava_running_outdoor="",
                            update_strava_walking="", update_strava_swimming="")
        self.assertFalse(any_update_strava_template_configured(config))

    def test_any_update_strava_template_configured_true_when_one_set(self):
        config = MagicMock(update_strava_cycling_indoor="", update_strava_cycling_outdoor="",
                            update_strava_running_indoor="", update_strava_running_outdoor="",
                            update_strava_walking="", update_strava_swimming="{{current-year}}")
        self.assertTrue(any_update_strava_template_configured(config))


if __name__ == "__main__":
    unittest.main()
