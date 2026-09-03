#!/usr/bin/env bash
# Run a syntax check (compile) on all Python files under the src/ directory.
# Run this from development/ or repo root; it will resolve the repo root and scan src/.
set -euo pipefail

# Resolve repo root (parent of this script's directory)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$REPO_ROOT/src"

declare -a files=()

# If src exists, scan it (preferred). Otherwise fallback to a repo-wide find.
if [ -d "$SRC_DIR" ]; then
  echo "Scanning all Python files under src/"
  pushd "$SRC_DIR" >/dev/null
  # read NUL-separated file list into array
  mapfile -d '' -t files < <(find . -type f -name "*.py" -print0)
  popd >/dev/null
  # normalize display paths to src/...
  for i in "${!files[@]}"; do
    files[$i]="$SRC_DIR/${files[$i]#./}"
  done
else
  echo "src/ not found; falling back to scanning repository"
  mapfile -d '' -t files < <(find "$REPO_ROOT" -type f -name "*.py" -not -path "./.venv/*" -not -path "./.git/*" -print0)
fi

if [ ${#files[@]} -eq 0 ]; then
  echo "No Python files found"
  exit 0
fi

# Pretty-print
echo "Checking ${#files[@]} Python files:"
for i in "${!files[@]}"; do
  idx=$((i+1))
  printf '%3d. %s\n' "$idx" "${files[$i]}"
done

# Compile all: run python -m py_compile with each absolute path
printf '%s\0' "${files[@]}" | xargs -0 python -m py_compile

echo "Syntax check OK"
