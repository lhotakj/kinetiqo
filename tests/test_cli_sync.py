"""Unit tests for CLI database options and validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from click.testing import CliRunner
from kinetiqo.cli import cli


class TestCliDatabaseOptions(unittest.TestCase):
    """Tests for --database-type and --database CLI options."""

    def setUp(self):
        self.runner = CliRunner()

    def test_cli_version_command(self):
        result = self.runner.invoke(cli, ["version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Kinetiqo", result.output)

    def test_cli_database_type_option(self):
        result = self.runner.invoke(cli, ["--database-type", "mysql", "version"])
        self.assertEqual(result.exit_code, 0)

    def test_cli_database_option(self):
        result = self.runner.invoke(cli, ["--database", "firebird", "version"])
        self.assertEqual(result.exit_code, 0)

    def test_cli_invalid_database_type_terminates(self):
        result = self.runner.invoke(cli, ["--database-type", "invalid_backend", "version"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value", result.output)

    def test_cli_invalid_database_terminates(self):
        result = self.runner.invoke(cli, ["--database", "invalid_backend", "version"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid value", result.output)


if __name__ == "__main__":
    unittest.main()
