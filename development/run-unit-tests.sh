#!/usr/bin/env bash
# Run unit tests for the repo. Resolves repo root and runs pytest from it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# Ensure pytest available; install if missing (convenience for local runs)
if ! python -c "import pytest" >/dev/null 2>&1; then
  echo "pytest not found; installing pytest via pip"
  python -m pip install pytest
fi

echo "Running pytest (pythonpath=src)"
pytest -o pythonpath=src "$@"
