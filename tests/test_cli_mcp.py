"""Unit tests for Kinetiqo CLI MCP command options and server startup."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from click.testing import CliRunner
from kinetiqo.cli import cli


class TestCliMcpCommand(unittest.TestCase):
    """Test suite for 'kinetiqo mcp' Click subcommand."""

    def setUp(self):
        self.runner = CliRunner()

    def test_cli_mcp_help_options(self):
        result = self.runner.invoke(cli, ["mcp", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--transport", result.output)
        self.assertIn("--host", result.output)
        self.assertIn("--port", result.output)
        self.assertIn("8000", result.output)

    @patch("kinetiqo.cli.validate_db_config")
    @patch("kinetiqo.mcp.server.create_mcp_server")
    def test_cli_mcp_stdio_default(self, mock_create_server, mock_validate_db):
        mock_server = MagicMock()
        mock_create_server.return_value = mock_server

        result = self.runner.invoke(cli, ["mcp", "--database", "postgresql"])
        self.assertEqual(result.exit_code, 0)
        mock_validate_db.assert_called_once()
        mock_create_server.assert_called_once()
        mock_server.run.assert_called_once_with(transport="stdio")

    @patch("kinetiqo.cli.validate_db_config")
    @patch("kinetiqo.mcp.server.create_mcp_server")
    def test_cli_mcp_sse_custom_port(self, mock_create_server, mock_validate_db):
        mock_server = MagicMock()
        mock_create_server.return_value = mock_server

        result = self.runner.invoke(
            cli,
            ["mcp", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000", "--database", "postgresql"],
        )
        self.assertEqual(result.exit_code, 0)
        mock_create_server.assert_called_once()
        _, kwargs = mock_create_server.call_args
        self.assertEqual(kwargs.get("host"), "0.0.0.0")
        self.assertEqual(kwargs.get("port"), 8000)
        mock_server.run.assert_called_once_with(transport="sse")

    @patch("kinetiqo.cli.validate_db_config")
    @patch("kinetiqo.mcp.server.create_mcp_server")
    def test_cli_mcp_env_var_defaults(self, mock_create_server, mock_validate_db):
        mock_server = MagicMock()
        mock_create_server.return_value = mock_server

        env_patch = {
            "MCP_TRANSPORT": "sse",
            "MCP_PORT": "8000",
            "MCP_HOST": "127.0.0.1",
        }
        with patch.dict(os.environ, env_patch):
            result = self.runner.invoke(cli, ["mcp", "--database", "postgresql"])
            self.assertEqual(result.exit_code, 0)
            mock_create_server.assert_called_once()
            _, kwargs = mock_create_server.call_args
            self.assertEqual(kwargs.get("host"), "127.0.0.1")
            self.assertEqual(kwargs.get("port"), 8000)
            mock_server.run.assert_called_once_with(transport="sse")


if __name__ == "__main__":
    unittest.main()
