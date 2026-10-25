"""Unit tests for Kinetiqo FastMCP server initialization, gating, resources, and prompts."""

import os
import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.mcp.server import create_mcp_server


class TestMCPServer(unittest.TestCase):
    """Test FastMCP server construction, tool gating, and metadata."""

    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.athlete_id = 1
        self.mock_repo = MagicMock()

    def _get_server_tool_names(self, server):
        # Extract registered tool names from FastMCP instance
        # FastMCP stores registered tools in _tool_manager._tools or list_tools()
        if hasattr(server, "_tool_manager") and hasattr(server._tool_manager, "_tools"):
            return set(server._tool_manager._tools.keys())
        return set()

    def test_server_creation_read_only_default(self):
        """When write flags are unset/0, mutating tools MUST be omitted from tool registry."""
        env_patch = {
            "KINETIQO_MCP_ALLOW_PROFILE_WRITE": "0",
            "KINETIQO_MCP_ALLOW_SYNC": "0",
            "KINETIQO_MCP_ALLOW_STRAVA_WRITE": "0",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            server = create_mcp_server(self.mock_config, repo_factory=lambda: self.mock_repo)
            tool_names = self._get_server_tool_names(server)

            # Read-only discovery and telemetry tools must be present
            self.assertIn("kinetiqo_search_activities", tool_names)
            self.assertIn("kinetiqo_get_activity_details", tool_names)
            self.assertIn("kinetiqo_get_activity_streams", tool_names)
            self.assertIn("kinetiqo_get_fitness_and_freshness", tool_names)
            self.assertIn("kinetiqo_get_verified_koms", tool_names)
            self.assertIn("kinetiqo_generate_activity_poster", tool_names)

            # Mutating tools MUST be absent
            self.assertNotIn("kinetiqo_update_training_goals", tool_names)
            self.assertNotIn("kinetiqo_trigger_sync", tool_names)
            self.assertNotIn("kinetiqo_update_strava_description", tool_names)
            self.assertNotIn("kinetiqo_update_athlete_profile", tool_names)

    def test_server_creation_with_mutations_enabled(self):
        """When write flags are 1, mutating tools MUST be registered."""
        env_patch = {
            "KINETIQO_MCP_ALLOW_PROFILE_WRITE": "1",
            "KINETIQO_MCP_ALLOW_SYNC": "1",
            "KINETIQO_MCP_ALLOW_STRAVA_WRITE": "1",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            server = create_mcp_server(self.mock_config, repo_factory=lambda: self.mock_repo)
            tool_names = self._get_server_tool_names(server)

            self.assertIn("kinetiqo_update_training_goals", tool_names)
            self.assertIn("kinetiqo_trigger_sync", tool_names)
            self.assertIn("kinetiqo_update_strava_description", tool_names)
            self.assertIn("kinetiqo_update_athlete_profile", tool_names)

    def test_server_resources_registered(self):
        """Verify all 6 core resources are registered."""
        server = create_mcp_server(self.mock_config, repo_factory=lambda: self.mock_repo)
        if hasattr(server, "_resource_manager") and hasattr(server._resource_manager, "_resources"):
            res_uris = set(server._resource_manager._resources.keys())
            self.assertIn("kinetiqo://profile", res_uris)
            self.assertIn("kinetiqo://goals", res_uris)
            self.assertIn("kinetiqo://activities/latest", res_uris)
            self.assertIn("kinetiqo://analytics/fitness-freshness", res_uris)
            self.assertIn("kinetiqo://analytics/power-skills", res_uris)
            self.assertIn("kinetiqo://analytics/koms", res_uris)

    def test_mcp_server_fast_smoke_listing(self):
        """Fast smoke test verifying FastMCP protocol endpoints: list_tools, list_resources, list_prompts."""
        import asyncio
        server = create_mcp_server(self.mock_config, repo_factory=lambda: self.mock_repo)

        # Test tools discovery
        tools = asyncio.run(server.list_tools())
        self.assertEqual(len(tools), 31)
        for tool in tools:
            self.assertTrue(tool.name.startswith("kinetiqo_"))
            self.assertTrue(len(tool.description) > 0)
            self.assertIsInstance(tool.inputSchema, dict)
            self.assertEqual(tool.inputSchema.get("type"), "object")

        # Test resources discovery
        resources = asyncio.run(server.list_resources())
        self.assertEqual(len(resources), 6)
        uris = {str(r.uri) for r in resources}
        self.assertIn("kinetiqo://profile", uris)
        self.assertIn("kinetiqo://goals", uris)
        self.assertIn("kinetiqo://activities/latest", uris)
        self.assertIn("kinetiqo://analytics/fitness-freshness", uris)
        self.assertIn("kinetiqo://analytics/power-skills", uris)
        self.assertIn("kinetiqo://analytics/koms", uris)

        # Test prompts discovery
        prompts = asyncio.run(server.list_prompts())
        self.assertEqual(len(prompts), 12)
        prompt_names = {p.name for p in prompts}
        self.assertEqual(
            prompt_names,
            {
                "post_ride_debrief",
                "race_readiness_assessment",
                "poster_creative_director",
                "weekly_training_review",
                "endurance_recovery_advisor",
                "season_power_audit",
                "training_habit_and_volume_profile",
                "aerobic_decoupling_and_efficiency",
                "ftp_breakthrough_and_power_zones_audit",
                "training_stress_and_overreaching_check",
                "cadence_and_pedaling_efficiency_analysis",
                "interval_session_quality_audit",
            },
        )

    def test_mcp_server_fast_smoke_listing_with_mutations(self):
        """Fast smoke test with mutation gates enabled verifying all 35 tools are registered."""
        import asyncio
        env_patch = {
            "KINETIQO_MCP_ALLOW_PROFILE_WRITE": "1",
            "KINETIQO_MCP_ALLOW_SYNC": "1",
            "KINETIQO_MCP_ALLOW_STRAVA_WRITE": "1",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            server = create_mcp_server(self.mock_config, repo_factory=lambda: self.mock_repo)
            tools = asyncio.run(server.list_tools())
            self.assertEqual(len(tools), 35)
            tool_names = {t.name for t in tools}
            self.assertIn("kinetiqo_trigger_sync", tool_names)
            self.assertIn("kinetiqo_update_strava_description", tool_names)
            self.assertIn("kinetiqo_update_athlete_profile", tool_names)
            self.assertIn("kinetiqo_update_training_goals", tool_names)
            self.assertIn("kinetiqo_get_weekly_training_profile", tool_names)
            self.assertIn("kinetiqo_analyze_recovery_turnaround", tool_names)

    def test_mcp_server_call_tool_execution(self):
        """Smoke test executing a tool through FastMCP call_tool and parsing response envelope."""
        import asyncio
        import json
        self.mock_repo.search_activities.return_value = ([], None, False)
        self.mock_repo.get_activity_count.return_value = 0

        server = create_mcp_server(self.mock_config, repo_factory=lambda: self.mock_repo)
        result = asyncio.run(server.call_tool("kinetiqo_search_activities", {}))

        self.assertIsInstance(result, tuple)
        text_content = result[0][0]
        payload = json.loads(text_content.text)

        self.assertEqual(payload.get("schema_version"), 1)
        self.assertEqual(payload.get("data_status"), "complete")
        self.assertIn("activities", payload.get("data", {}))
        self.assertIn("pagination", payload.get("data", {}))

    def test_cli_mcp_command_and_logging_redirection(self):
        """Test Click CLI 'kinetiqo mcp' command launches STDIO server and redirects logs to stderr."""
        from click.testing import CliRunner
        from kinetiqo.cli import cli
        import logging
        import sys

        runner = CliRunner()
        with patch("kinetiqo.cli.validate_db_config") as mock_validate, \
             patch("kinetiqo.mcp.server.create_mcp_server") as mock_create:
            mock_server = MagicMock()
            mock_create.return_value = mock_server

            result = runner.invoke(cli, ["mcp"])
            self.assertEqual(result.exit_code, 0)
            mock_validate.assert_called_once()
            mock_create.assert_called_once()
            mock_server.run.assert_called_once_with(transport="stdio")

            # Verify StreamHandler was attached to root logger
            root_logger = logging.getLogger()
            stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
            self.assertGreater(len(stream_handlers), 0)

    def test_mcp_tool_request_logging(self):
        """Test that MCP tool invocations log MCP Request and MCP Response at INFO level."""
        import asyncio
        import logging
        self.mock_repo.search_activities.return_value = ([], None, False)
        self.mock_repo.get_activity_count.return_value = 0

        server = create_mcp_server(self.mock_config, repo_factory=lambda: self.mock_repo)

        with self.assertLogs("kinetiqo.mcp", level=logging.INFO) as log_ctx:
            asyncio.run(server.call_tool("kinetiqo_search_activities", {"limit": 10}))

        output_str = "\n".join(log_ctx.output)
        self.assertIn("MCP Request: kinetiqo_search_activities(limit=10)", output_str)
        self.assertIn("MCP Response: kinetiqo_search_activities -> complete", output_str)

    def test_cli_mcp_keyboard_interrupt_graceful_exit(self):
        """Test that KeyboardInterrupt (Ctrl+C) shuts down MCP server cleanly via os._exit(0)."""
        from click.testing import CliRunner
        from kinetiqo.cli import cli

        runner = CliRunner()
        with patch("kinetiqo.cli.validate_db_config"), \
             patch("kinetiqo.mcp.server.create_mcp_server") as mock_create, \
             patch("os._exit") as mock_exit:
            mock_server = MagicMock()
            mock_server.run.side_effect = KeyboardInterrupt
            mock_create.return_value = mock_server

            runner.invoke(cli, ["mcp"])
            mock_exit.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
