#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Strava (dummy values for mocked tests) ---
export STRAVA_CLIENT_ID="dummy"
export STRAVA_CLIENT_SECRET="dummy"
export STRAVA_REFRESH_TOKEN="dummy"

# --- Main Execution ---
export PYTHONPATH=$(pwd)/src

# Run the comprehensive unit test matrix
echo "================================================================="
echo "  RUNNING SYNC LOGIC UNIT TEST MATRIX (MOCKED DB & API)"
echo "================================================================="
python3 -m unittest tests.test_sync_logic
echo "✅ All sync logic tests passed successfully."
echo "================================================================="
