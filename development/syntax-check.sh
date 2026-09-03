#!/usr/bin/env bash
# Run a syntax check (compile) on all Python files in the repository (excluding virtualenvs)
set -euo pipefail

# Find python files, excluding common virtualenv and .git directories
PY_FILES=$(git ls-files -- "*.py" || true)
if [ -z "$PY_FILES" ]; then
  echo "No Python files found via git. Falling back to find."
  PY_FILES=$(find . -type f -name "*.py" -not -path "./.venv/*" -not -path "./.git/*")
fi

echo "Checking ${PY_FILES}"
python -m py_compile $PY_FILES

echo "Syntax check OK"
