"""Unit tests for chat visual artifacts storage, retrieval, and tool execution."""

import unittest
from unittest.mock import MagicMock, patch

from kinetiqo.chat.artifacts import (
    get_chat_artifact,
    store_chat_artifact,
    _ARTIFACT_ID_PATTERN,
)
from kinetiqo.chat.tools import execute_chat_tool
from kinetiqo.mcp.tools import generator


class TestChatArtifacts(unittest.TestCase):
    def test_store_and_get_chat_artifact(self):
        sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        artifact_id = store_chat_artifact(sample_png)
        self.assertTrue(artifact_id.startswith("art_"))
        self.assertTrue(_ARTIFACT_ID_PATTERN.fullmatch(artifact_id))

        retrieved = get_chat_artifact(artifact_id)
        self.assertEqual(retrieved, sample_png)

        # Also supports retrieving with .png suffix
        retrieved_with_ext = get_chat_artifact(f"{artifact_id}.png")
        self.assertEqual(retrieved_with_ext, sample_png)

    def test_path_traversal_rejection(self):
        # Strict pattern rejects path traversal attempts
        self.assertIsNone(get_chat_artifact("../etc/passwd"))
        self.assertIsNone(get_chat_artifact("art_../../etc/passwd"))
        self.assertIsNone(get_chat_artifact("art_invalid_non_hex_id"))
        self.assertIsNone(get_chat_artifact("art_123"))

    def test_generator_tools_include_image_url_and_artifact_id(self):
        mock_repo = MagicMock()
        mock_config = MagicMock()
        mock_png = b"\x89PNG\r\n\x1a\nTEST_MEGA_STATS"

        with patch("kinetiqo.mcp.tools.generator.render_stats_artifact", return_value=mock_png) as mock_render:
            result = generator.kinetiqo_generate_mega_stats_infographic(
                repo=mock_repo,
                config=mock_config,
                year=2026,
                sport_group="cycling outdoor",
            )
            data = result.get("data", {})
            self.assertIn("image_url", data)
            self.assertIn("artifact_id", data)
            self.assertTrue(data["image_url"].startswith("/api/chat/artifacts/art_"))
            self.assertTrue(data["image_url"].endswith(".png"))
            self.assertEqual(data["artifact_type"], "mega_stats_infographic")
            self.assertEqual(data["sport_group"], "cycling_outdoor")
            mock_render.assert_called_once()
            self.assertEqual(mock_render.call_args[1]["sport_group"], "cycling_outdoor")

    def test_execute_chat_tool_optimizes_visual_payload(self):
        mock_repo = MagicMock()
        mock_config = MagicMock()
        mock_png = b"\x89PNG\r\n\x1a\nTEST_EXECUTE_TOOL"

        with patch("kinetiqo.mcp.tools.generator.render_stats_artifact", return_value=mock_png):
            payload, elapsed_ms = execute_chat_tool(
                repo=mock_repo,
                tool_name="kinetiqo_generate_mega_stats_infographic",
                arguments={"year": 2026, "sport_group": "cycling"},
                config=mock_config,
            )
            data = payload.get("data", {})
            self.assertIn("image_url", data)
            self.assertTrue(data["image_url"].startswith("/api/chat/artifacts/art_"))
            # inline_image_base64 must NOT be the huge base64 payload to save LLM context
            self.assertIn("[Stored locally", data.get("inline_image_base64", ""))


if __name__ == "__main__":
    unittest.main()
