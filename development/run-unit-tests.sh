#!/usr/bin/env bash
# Run unit tests for the repo. Resolves repo root and runs pytest from it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# Ensure pytest and pytest-cov are available; install if missing (convenience for local runs)
if ! python -c "import pytest, pytest_cov" >/dev/null 2>&1; then
  echo "pytest/pytest-cov not found; installing via pip"
  python -m pip install pytest pytest-cov
fi

echo "Running pytest with coverage (pythonpath=src)"
pytest -o pythonpath=src --cov=src --cov-report=xml:coverage.xml --cov-report=term "$@"
