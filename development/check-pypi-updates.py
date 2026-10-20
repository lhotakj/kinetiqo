#!/usr/bin/env python3
"""Check and optionally update Python requirements files against PyPI.

This utility follows the same CLI style as other scripts in `development/`.

Usage examples:
  python development/check-pypi-updates.py                 # check default files
  python development/check-pypi-updates.py --apply         # update files to latest pinned versions (==)
  python development/check-pypi-updates.py -v requirements.txt other/reqs.txt

Notes:
  - By default this script only checks and reports available updates.
  - Use `--apply` to write changes (pins packages to the latest PyPI release using ==).
  - Use `-f/--force` with `--apply` to skip confirmation prompts.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from shutil import copy2
from typing import List, Optional, Tuple

import requests
from packaging.requirements import InvalidRequirement, Requirement

_REPO_ROOT = Path(__file__).resolve().parent.parent


logger = logging.getLogger("check-pypi-updates")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def print_row(name: str, status: str, info: str) -> None:
    """Print a single status row to stdout (kept user-facing)."""
    name_col = name[:32].ljust(32)
    status_col = status[:12].ljust(12)
    print(f"  {name_col} {status_col} {info}")


def print_table_header() -> None:
    print(f"\n  {'File / Package'.ljust(32)} {'Status'.ljust(12)} Info")
    print(f"  {'─'*32} {'─'*12} {'─'*45}")


def validate_safe_path(path: Path) -> Path:
    """Validate and resolve path strictly within repository root to prevent path traversal."""
    resolved = path.resolve()
    base_dir = _REPO_ROOT.resolve()
    if base_dir not in resolved.parents and resolved != base_dir:
        raise ValueError(f"Path traversal detected: {path} is outside repository root.")
    return resolved


def parse_requirements(path: Path) -> List[str]:
    lines: List[str] = []
    try:
        safe_path = validate_safe_path(path)
    except ValueError as err:
        logger.warning("Skipping untrusted path: %s", err)
        return lines
    if not safe_path.is_file():
        return lines
    with safe_path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            lines.append(ln.rstrip("\n"))
    return lines


def get_latest_version(package: str) -> Optional[str]:
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            logger.debug("PyPI returned status %s for %s", r.status_code, package)
            return None
        j = r.json()
        # be defensive: ensure json structure exists
        if not isinstance(j, dict):
            return None
        return j.get("info", {}).get("version")
    except requests.RequestException as exc:
        logger.debug("Network error when contacting PyPI for %s: %s", package, exc)
        return None


def analyze_line(line: str) -> Optional[dict]:
    """Analyze a single line from a requirements file.

    Returns None for comments/blank lines or a dict with keys: line, name, req, latest.
    """
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    try:
        req = Requirement(s)
    except InvalidRequirement:
        # fallback: try to extract bare package name from first token
        token = s.split()[0]
        name = token.split("==")[0].split(">=")[0].split("~=")[0].split("<")[0].split(">")[0]
        latest = get_latest_version(name)
        return {"line": line, "name": name, "req": None, "latest": latest}
    latest = get_latest_version(req.name)
    return {"line": line, "name": req.name, "req": req, "latest": latest}


def build_new_requirement(req_obj: Requirement, latest: str) -> str:
    extras = ""
    if req_obj.extras:
        extras = "[" + ",".join(sorted(req_obj.extras)) + "]"
    marker = f"; {str(req_obj.marker)}" if getattr(req_obj, "marker", None) else ""
    return f"{req_obj.name}{extras}=={latest}{marker}"


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def write_atomic(path: Path, lines: List[str]) -> None:
    """Write lines to file atomically by writing to a temporary file then replacing.

    This reduces the risk of partial writes.
    """
    safe_path = validate_safe_path(path)
    dirpath = safe_path.parent
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(dirpath)) as tf:
        tf.write("\n".join(lines) + "\n")
        tmp = Path(tf.name)
    os.replace(str(tmp), str(safe_path))


def make_backup(path: Path) -> Path:
    safe_path = validate_safe_path(path)
    ts = int(time.time())
    bak = safe_path.with_suffix(safe_path.suffix + f".bak-{ts}")
    # copy original file to backup path
    copy2(str(safe_path), str(bak))
    return bak


def update_file(path: Path, new_lines: List[str], backup: bool = False) -> None:
    if backup and path.exists():
        bak = make_backup(path)
        write_atomic(path, new_lines)
        print_row(str(path), "UPDATED", f"backup={bak.name}")
    else:
        write_atomic(path, new_lines)
        print_row(str(path), "UPDATED", "no-backup")


def collect_targets(paths: List[str]) -> List[Path]:
    if paths:
        validated_paths: List[Path] = []
        for p in paths:
            try:
                candidate = Path(p) if Path(p).is_absolute() else _REPO_ROOT / p
                validated_paths.append(validate_safe_path(candidate))
            except ValueError as err:
                logger.warning("Ignoring unsafe path argument: %s", err)
        return validated_paths
    targets: List[Path] = []
    for p in _REPO_ROOT.rglob("requirements.txt"):
        targets.append(p)
    # deduplicate while preserving order
    seen = set()
    dedup: List[Path] = []
    for t in targets:
        try:
            tp = validate_safe_path(t)
        except Exception:
            continue
        if tp not in seen:
            dedup.append(tp)
            seen.add(tp)
    return dedup


def process_file(p: Path, args) -> Tuple[bool, bool]:
    """Process a single requirements file.

    Returns (any_updates_detected, file_written).
    """
    lines = parse_requirements(p)
    if not lines:
        print_row(str(p), "SKIPPED", "empty or missing")
        return False, False
    updates_for_file: List[Tuple[str, str]] = []
    new_lines: List[str] = []
    any_updates = False
    for ln in lines:
        info = analyze_line(ln)
        if info is None:
            new_lines.append(ln)
            continue
        name = info.get("name")
        latest = info.get("latest")
        req_obj = info.get("req")
        if not latest:
            print_row(f"{p.name}:{name}", "ERROR", "PyPI lookup failed")
            new_lines.append(ln)
            continue
        old_spec = ""
        try:
            old_spec = str(req_obj.specifier) if req_obj else ""
        except Exception:
            old_spec = ""
        if old_spec.startswith("=="):
            pinned = old_spec.lstrip("==")
            if pinned == latest:
                print_row(f"{p.name}:{name}", "UP-TO-DATE", latest)
                new_lines.append(ln)
                continue
            else:
                print_row(f"{p.name}:{name}", "OUTDATED", f"{pinned} -> {latest}")
                any_updates = True
                new_req = build_new_requirement(req_obj, latest) if req_obj else ln
                updates_for_file.append((ln, new_req))
                new_lines.append(new_req)
                continue
        else:
            print_row(f"{p.name}:{name}", "AVAILABLE", f"{old_spec or '(no spec)'} -> {latest}")
            any_updates = True
            if args.apply:
                if req_obj is not None:
                    new_req = build_new_requirement(req_obj, latest)
                    updates_for_file.append((ln, new_req))
                    new_lines.append(new_req)
                else:
                    new_lines.append(ln)
            else:
                new_lines.append(ln)

    if args.apply and updates_for_file:
        if not args.force:
            print()
            print(f"Proposed changes for {p}:")
            for old, new in updates_for_file:
                print(f"  - {old} --> {new}")
            print()
            if not confirm("Apply these changes? [y/N]: "):
                print_row(str(p), "ABORTED", "user declined")
                return any_updates, False
        try:
            update_file(p, new_lines, backup=args.backup)
            return any_updates, True
        except Exception as e:
            print_row(str(p), "FAILED", str(e))
            return any_updates, False
    else:
        if args.apply:
            print_row(str(p), "NO-CHANGES", "No updates detected or nothing to apply")
        return any_updates, False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check and optionally update requirements.txt files against PyPI.")
    parser.add_argument("paths", nargs="*", help="Requirements files to check (default: discovered requirements.txt files in the repo)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-f", "--force", action="store_true", help="When applying updates, don't prompt for confirmation")
    parser.add_argument("--apply", action="store_true", help="Apply updates (pin to latest using ==). By default the script only checks and reports updates.")
    parser.add_argument("--backup", action="store_true", help="Create a timestamped .bak backup when writing files (default: no backup)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    targets = collect_targets(args.paths)
    if not targets:
        print("No requirements files found or specified.")
        return 1
    print_table_header()
    any_updates = False
    for p in targets:
        detected, written = process_file(p, args)
        any_updates = any_updates or detected
    if not any_updates:
        print('\nNo updates detected for checked requirements.')
    else:
        print('\nSome packages have newer versions available. Run with --apply to pin to latest versions.')

    return 0


if __name__ == "__main__":
    sys.exit(main())
