"""Integration test verifying FastMCP SSE endpoint startup and connection."""

import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import httpx
from kinetiqo.config import Config
from kinetiqo.mcp.server import create_mcp_server


class TestFastMCPSSEIntegration(unittest.TestCase):
    """Verify FastMCP starts and responds over SSE transport."""

    def test_mcp_sse_endpoint_stream(self):
        mock_config = Config()
        mock_repo = MagicMock()
        mock_repo.get_athlete_profile.return_value = {"id": 1, "weight": 70.0}

        # Select an ephemeral port
        test_port = 8799
        server = create_mcp_server(mock_config, repo_factory=lambda: mock_repo, host="127.0.0.1", port=test_port)

        thread = threading.Thread(target=lambda: server.run(transport="sse"), daemon=True)
        thread.start()

        # Allow uvicorn to bind
        time.sleep(2.0)

        status_code = None
        content_type = ""
        first_chunk = ""
        try:
            with httpx.stream("GET", f"http://127.0.0.1:{test_port}/sse", timeout=5.0) as resp:
                status_code = resp.status_code
                content_type = resp.headers.get("content-type", "")
                # Read the initial endpoint event sent by FastMCP
                first_chunk = next(resp.iter_text())
        except (httpx.HTTPError, StopIteration, OSError) as e:
            self.fail(f"Failed connecting to FastMCP SSE endpoint: {e}")

        self.assertEqual(status_code, 200)
        self.assertIn("text/event-stream", content_type)
        self.assertIn("event: endpoint", first_chunk)
        self.assertIn("/messages/", first_chunk)


if __name__ == "__main__":
    unittest.main()
