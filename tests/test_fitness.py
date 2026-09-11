"""Mocked unit tests for fitness & freshness calculations and insights."""

import unittest
from unittest.mock import MagicMock

from kinetiqo.web.fitness import (
    generate_ai_insight,
    calculate_fitness_freshness,
)


class TestFitnessInsight(unittest.TestCase):
    """Unit tests for generate_ai_insight."""

    def test_generate_ai_insight_contains_expected_prefix_and_content(self):
        valid_prefixes = [
            "Based on your recent activity patterns,",
            "Analyzing your training load,",
            "According to the impulse-response model,",
            "My analysis suggests that",
        ]
        # Form > 25 (deep recovery), trend > 0.5 (upward), fatigue high
        insight = generate_ai_insight(fitness=50.0, fatigue=70.0, form=30.0, trend_fitness=1.0)
        self.assertTrue(any(insight.startswith(p) for p in valid_prefixes))
        self.assertIn("deep recovery or transition phase", insight)
        self.assertIn("strong upward trajectory", insight)
        self.assertIn("Recent training has been very intense", insight)

    def test_generate_ai_insight_peak_performance(self):
        insight = generate_ai_insight(fitness=60.0, fatigue=50.0, form=15.0, trend_fitness=0.1)
        self.assertIn("peak performance zone", insight)
        self.assertIn("stable recently", insight)

    def test_generate_ai_insight_overtraining_warning(self):
        insight = generate_ai_insight(fitness=40.0, fatigue=80.0, form=-35.0, trend_fitness=-1.0)
        self.assertIn("High Risk of Overtraining", insight)
        self.assertIn("chronic training load is decreasing", insight)


class TestCalculateFitnessFreshness(unittest.TestCase):
    """Unit tests for calculate_fitness_freshness with mocked repository."""

    def test_empty_activities_returns_empty_chart_data(self):
        mock_repo = MagicMock()
        mock_repo.get_activities_with_suffer_score.return_value = []

        result = calculate_fitness_freshness(mock_repo, period="30")
        self.assertEqual(result["dates"], [])
        self.assertEqual(result["fitness"], [])
        self.assertEqual(result["fatigue"], [])
        self.assertEqual(result["form"], [])
        self.assertEqual(result["insight"], "No data available to analyze for the selected period.")

    def test_with_mocked_activities(self):
        mock_repo = MagicMock()
        mock_repo.get_activities_with_suffer_score.return_value = [
            {"start_date": "2026-01-01T10:00:00Z", "suffer_score": 50},
            {"start_date": "2026-01-02T10:00:00Z", "suffer_score": 60},
            {"start_date": "2026-01-03T10:00:00Z", "suffer_score": 70},
            {"start_date": "2026-01-04T10:00:00Z", "suffer_score": 40},
            {"start_date": "2026-01-05T10:00:00Z", "suffer_score": 80},
            {"start_date": "2026-01-06T10:00:00Z", "suffer_score": 65},
            {"start_date": "2026-01-07T10:00:00Z", "suffer_score": 55},
        ]

        result = calculate_fitness_freshness(mock_repo, period="14")
        self.assertIsInstance(result["dates"], list)
        self.assertGreater(len(result["dates"]), 0)
        self.assertEqual(len(result["dates"]), len(result["fitness"]))
        self.assertEqual(len(result["dates"]), len(result["fatigue"]))
        self.assertEqual(len(result["dates"]), len(result["form"]))
        self.assertIsInstance(result["insight"], str)
        self.assertNotEqual(result["insight"], "")


if __name__ == "__main__":
    unittest.main()
