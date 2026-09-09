"""Unit tests for the kinetiqo benchmark CLI command and repository metrics."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from click.testing import CliRunner
from kinetiqo.cli import cli, _print_benchmark_results


class TestBenchmarkCLI(unittest.TestCase):
    """Tests for the `kinetiqo benchmark` CLI command."""

    def setUp(self):
        self.runner = CliRunner()

    def test_benchmark_help(self):
        result = self.runner.invoke(cli, ["benchmark", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--scope", result.output)
        self.assertIn("-s", result.output)
        self.assertIn("--database", result.output)

    @patch("kinetiqo.cli.create_repository")
    @patch("kinetiqo.cli.validate_config")
    def test_benchmark_default_scope(self, mock_validate, mock_create_repo):
        mock_repo = MagicMock()
        mock_repo.run_benchmarks.return_value = {
            'gps_ms': 12.34,
            'gps_count': 5000,
            'order_name_ms': 1.23,
            'order_name_count': 150,
            'order_dist_ms': 1.11,
            'order_dist_count': 150,
            'order_elev_ms': 0.99,
            'order_elev_count': 150,
        }
        mock_create_repo.return_value = mock_repo

        result = self.runner.invoke(cli, ["benchmark"])

        self.assertEqual(result.exit_code, 0)
        mock_repo.run_benchmarks.assert_called_once_with(scope_days=365)
        self.assertIn("Kinetiqo Database Benchmark", result.output)
        self.assertIn("Scope: Last 365 days", result.output)
        self.assertIn("12.34 ms (5,000 records)", result.output)
        self.assertIn("1.23 ms (150 activities)", result.output)
        mock_repo.close.assert_called_once()

    @patch("kinetiqo.cli.create_repository")
    @patch("kinetiqo.cli.validate_config")
    def test_benchmark_custom_scope_and_database(self, mock_validate, mock_create_repo):
        mock_repo = MagicMock()
        mock_repo.run_benchmarks.return_value = {
            'gps_ms': 45.67,
            'gps_count': 12000,
            'order_name_ms': 2.34,
            'order_name_count': 300,
            'order_dist_ms': 2.10,
            'order_dist_count': 300,
            'order_elev_ms': 1.95,
            'order_elev_count': 300,
        }
        mock_create_repo.return_value = mock_repo

        result = self.runner.invoke(cli, ["benchmark", "-s", "90", "-d", "postgresql"])

        self.assertEqual(result.exit_code, 0)
        mock_repo.run_benchmarks.assert_called_once_with(scope_days=90)
        self.assertIn("Kinetiqo Database Benchmark (POSTGRESQL)", result.output)
        self.assertIn("Scope: Last 90 days", result.output)
        mock_repo.close.assert_called_once()

    def test_print_benchmark_results_formatter(self):
        sample_results = {
            'gps_ms': 100.5,
            'gps_count': 25000,
            'order_name_ms': 5.5,
            'order_name_count': 500,
            'order_dist_ms': 4.2,
            'order_dist_count': 500,
            'order_elev_ms': 3.8,
            'order_elev_count': 500,
        }
        with patch("sys.stdout.write") as mock_write:
            _print_benchmark_results("postgresql", 365, sample_results)
            self.assertTrue(mock_write.called)


if __name__ == "__main__":
    unittest.main()
