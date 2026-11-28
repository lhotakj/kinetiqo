"""Unit tests for MCP contracts, envelopes, and utilities."""

import unittest
from kinetiqo.mcp.contracts import (
    create_envelope,
    create_error_envelope,
    MCPResponseEnvelope,
    ERROR_INVALID_ARGUMENT,
    ERROR_NOT_FOUND,
)
from kinetiqo.mcp.utils import downsample_stream_window, detect_stream_gaps


class TestMCPContracts(unittest.TestCase):
    """Test standard response envelope generation and validation."""

    def test_create_envelope_structure(self):
        data = {"activity_id": "12345", "name": "Morning Ride"}
        envelope = create_envelope(data, source="local_db", data_status="complete")
        self.assertEqual(envelope["schema_version"], 1)
        self.assertEqual(envelope["source"], "local_db")
        self.assertEqual(envelope["data_status"], "complete")
        self.assertEqual(envelope["data"]["activity_id"], "12345")
        self.assertIn("generated_at", envelope)
        self.assertEqual(envelope["warnings"], [])

    def test_create_error_envelope(self):
        envelope = create_error_envelope(ERROR_NOT_FOUND, "Activity not found", {"id": "999"})
        self.assertEqual(envelope["data_status"], "unavailable")
        self.assertEqual(envelope["source"], "calculated")
        self.assertIn("[NOT_FOUND] Activity not found", envelope["warnings"][0])
        self.assertEqual(envelope["data"]["error_code"], ERROR_NOT_FOUND)
        self.assertEqual(envelope["data"]["details"]["id"], "999")

    def test_downsample_stream_window_auto(self):
        # 1000 sample rows
        rows = [{"ts": i, "watts": 200 + (i % 50), "heartrate": 140} for i in range(1000)]
        downsampled, method = downsample_stream_window(rows, resolution="auto", max_auto_samples=500)
        self.assertLessEqual(len(downsampled), 600)
        self.assertIn("extrema_preserved", method)
        self.assertEqual(downsampled[0]["ts"], 0)
        self.assertEqual(downsampled[-1]["ts"], 999)

    def test_downsample_stream_window_buckets(self):
        rows = [{"ts": i, "watts": 200.0} for i in range(100)]
        downsampled, method = downsample_stream_window(rows, resolution="medium")
        self.assertEqual(method, "bucket_10s")
        self.assertEqual(len(downsampled), 10)
        self.assertEqual(downsampled[0]["watts"], 200.0)

    def test_detect_stream_gaps(self):
        # Samples with a 5-second gap between sample 1 and 2
        rows = [{"ts": 0}, {"ts": 1}, {"ts": 6}, {"ts": 7}]
        gaps = detect_stream_gaps(rows, threshold_s=2)
        self.assertEqual(gaps["total_gaps"], 1)
        self.assertEqual(gaps["max_gap_seconds"], 4)


if __name__ == "__main__":
    unittest.main()
