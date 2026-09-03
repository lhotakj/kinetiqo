#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify vendor asset references in HTML and PY files.

Search patterns supported:
 - jinja url_for: url_for('static', filename='vendor/...', v=app_version)
 - positional url_for: url_for('static', 'vendor/...')
 - plain static paths: /static/... or static/...

Usage examples:
  python development/verify_vendor_refs.py
  python development/verify_vendor_refs.py --root . --exclude venv,.venv

The script scans only under the 'src' folder by default and ignores virtualenv folders.
"""
from __future__ import annotations
import argparse
import re
import shutil
import sys
from pathlib import Path

DEFAULT_EXCLUDE = ['.venv', 'venv', 'env']

parser = argparse.ArgumentParser(
    description='Verify that template/static vendor references resolve to local files under src/kinetiqo/web/static',
    formatter_class=argparse.RawTextHelpFormatter,
)
parser.add_argument('--root', '-r', default='.', help='Repository root (default: current directory)')
parser.add_argument('--src', default=None, help="Source root (default: <root>/src)")
parser.add_argument('--exclude', default=','.join(DEFAULT_EXCLUDE), help='Comma-separated directory names to ignore (default: .venv,venv,env)')
parser.add_argument('--quiet', action='store_true', help='Suppress per-file scanning progress')
parser.add_argument('--missing-only', action='store_true', help='Show only missing entries in the final table')
parser.add_argument('--width', type=int, default=None, help='Max terminal width to format table (default: terminal width or 120)')
parser.add_argument('--max-col-width', type=int, default=60, help='Max width per column before truncating (default: 60)')
parser.add_argument('--version', action='version', version='verify_vendor_refs 1.1')
args = parser.parse_args()

REPO_ROOT = Path(args.root).resolve()
SRC_ROOT = Path(args.src).resolve() if args.src else (REPO_ROOT / 'src')
STATIC_BASE = SRC_ROOT / 'kinetiqo' / 'web' / 'static'
EXCLUDE_NAMES = [x.strip() for x in args.exclude.split(',') if x.strip()]
QUIET = args.quiet
MISSING_ONLY = args.missing_only

if not SRC_ROOT.exists():
    print(f"Source folder not found: {SRC_ROOT}. Run the script from the repository root or pass --src.")
    raise SystemExit(1)

# File globs to scan under src
SCAN_GLOBS = ['**/*.html', '**/*.py']

# Regex patterns
# url_for(...) with either filename=... or positional second arg
URLFOR_RE = re.compile(
    r"url_for\(\s*['\"]static['\"]\s*(?:,\s*filename\s*=\s*['\"]([^'\"]+)['\"][^)]*|,\s*['\"]([^'\"]+)['\"][^)]*)\)"
)
# capture src/href attributes pointing at /static/... or static/...
STATIC_PATH_RE = re.compile(r"(?:src|href)\s*=\s*['\"](/?static/[^'\"]+)['\"]")

found = []  # tuples (source_file, lineno, matched_text, resolved_path)

# helper to check if a file path contains any excluded dir name

def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_NAMES for part in path.parts)

# helper to trim left with ellipsis

def trim_left(s: str, maxlen: int) -> str:
    if len(s) <= maxlen:
        return s
    return '...' + s[-(maxlen - 3):]

# Walk files under src and collect matches
for glob in SCAN_GLOBS:
    for f in SRC_ROOT.glob(glob):
        if is_excluded(f):
            continue
        try:
            relf = f.relative_to(REPO_ROOT)
        except Exception:
            relf = f
        if not QUIET:
            print(f'Scanning {relf} ...', end=' ', flush=True)
        try:
            text = f.read_text(encoding='utf-8')
        except Exception:
            if not QUIET:
                print('skipped (binary/encoding)', flush=True)
            continue
        match_count = 0
        for i, line in enumerate(text.splitlines(), start=1):
            for m in URLFOR_RE.finditer(line):
                filename = m.group(1) or m.group(2)
                if not filename:
                    continue
                resolved = filename
                if resolved.startswith('/static/'):
                    resolved = resolved[len('/static/'):]
                local_path = STATIC_BASE / resolved
                found.append((str(relf), i, m.group(0), str(local_path)))
                match_count += 1
            for m in STATIC_PATH_RE.finditer(line):
                path_value = m.group(1)
                if path_value.startswith('/'):
                    path_value = path_value[1:]
                local_path = REPO_ROOT / path_value
                if path_value.startswith('static/'):
                    rel = path_value[len('static/'):]
                    local_path = STATIC_BASE / rel
                found.append((str(relf), i, m.group(0), str(local_path)))
                match_count += 1
        if not QUIET:
            if match_count:
                print(f'found {match_count} matches', flush=True)
            else:
                print('ok', flush=True)

# Prepare and print table
term_width = args.width or shutil.get_terminal_size((120, 20)).columns
max_col = args.max_col_width or 60

cols = ['Source', 'Matched', 'Resolved', 'Status']
# compute rows
rows = []
for src_file, lineno, matched, resolved in found:
    p = Path(resolved)
    exists = p.exists()
    status = 'OK' if exists else 'MISSING'
    src_label = f'{src_file}:{lineno}'
    rows.append((src_label, matched, resolved, status))

# Optionally filter to missing only
if MISSING_ONLY:
    rows = [r for r in rows if r[3] == 'MISSING']

# Determine column widths (right-align as requested)
col_widths = [0, 0, 0, 0]
for r in rows:
    col_widths[0] = max(col_widths[0], len(r[0]))
    col_widths[1] = max(col_widths[1], len(r[1]))
    col_widths[2] = max(col_widths[2], len(r[2]))
    col_widths[3] = max(col_widths[3], len(r[3]))
# clamp widths to max_col
col_widths = [min(w, max_col) for w in col_widths]
# ensure total fits terminal: allow Resolved to take remaining space
other_total = col_widths[0] + col_widths[1] + col_widths[3] + 6  # padding & separators
resolved_width = min(max_col, max(20, term_width - other_total))
col_widths[2] = resolved_width

# print header
print('\nVendor reference verification summary')
print(f'Repo root: {REPO_ROOT.relative_to(Path.cwd()) if REPO_ROOT.is_relative_to(Path.cwd()) else REPO_ROOT}')
print(f'Static base: {STATIC_BASE.relative_to(REPO_ROOT) if STATIC_BASE.is_relative_to(REPO_ROOT) else STATIC_BASE}\n')

if not rows:
    print('No vendor/static references found under src/.')
    sys.exit(0)

# table header
hdr = f"{cols[0].rjust(col_widths[0])} | {cols[1].rjust(col_widths[1])} | {cols[2].rjust(col_widths[2])} | {cols[3].rjust(col_widths[3])}"
print(hdr)
print('-' * len(hdr))

for src_label, matched, resolved, status in rows:
    matched_disp = trim_left(matched, col_widths[1])
    resolved_disp = trim_left(resolved, col_widths[2])
    print(f"{src_label.rjust(col_widths[0])} | {matched_disp.rjust(col_widths[1])} | {resolved_disp.rjust(col_widths[2])} | {status.rjust(col_widths[3])}")

# summary and exit
missing = [r for r in rows if r[3] == 'MISSING']
print(f"\nChecked {len(rows)} references. Missing: {len(missing)}")
if missing:
    sys.exit(2)
else:
    sys.exit(0)
