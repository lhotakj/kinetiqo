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
import sys
import time
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent


def print_row(name: str, status: str, info: str):
    name_col = name[:32].ljust(32)
    status_col = status[:12].ljust(12)
    print(f"  {name_col} {status_col} {info}")


def print_table_header():
    print(f"\n  {'File / Package'.ljust(32)} {'Status'.ljust(12)} Info")
    print(f"  {'─'*32} {'─'*12} {'─'*45}")


def parse_requirements(path: Path) -> List[str]:
    lines: List[str] = []
    if not path.is_file():
        return lines
    with path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            lines.append(ln.rstrip("\n"))
    return lines


def get_latest_version(package: str) -> Optional[str]:
    import requests

    url = f"https://pypi.org/pypi/{package}/json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None
        j = r.json()
        return j.get("info", {}).get("version")
    except Exception:
        return None


def analyze_line(line: str):
    # preserve comments and editable tokens
    from packaging.requirements import Requirement

    s = line.strip()
    if not s or s.startswith("#"):
        return None
    try:
        req = Requirement(s)
    except Exception:
        # fallback: try to split on whitespace and take first token
        token = s.split()[0]
        # strip common comparators and extras
        name = token.split("==")[0].split(">=")[0].split("~=")[0].split("<")[0].split(">")[0]
        latest = get_latest_version(name)
        return {"line": line, "name": name, "req": None, "latest": latest}
    latest = get_latest_version(req.name)
    return {"line": line, "name": req.name, "req": req, "latest": latest}


def build_new_requirement(req_obj, latest: str) -> Optional[str]:
    # req_obj may be a packaging.Requirement or None
    if req_obj is None:
        return None
    extras = ""
    if req_obj.extras:
        extras = "[" + ",".join(sorted(req_obj.extras)) + "]"
    marker = f"; {req_obj.marker}" if getattr(req_obj, "marker", None) else ""
    return f"{req_obj.name}{extras}=={latest}{marker}"


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def update_file(path: Path, new_lines: List[str], backup: bool = False) -> None:
    if backup:
        bak = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
        # create a copy rather than move to keep original intact
        path.replace(bak)
        with path.open("w", encoding="utf-8") as fh:
            fh.write("\n".join(new_lines) + "\n")
        print_row(str(path), "UPDATED", f"backup={bak.name}")
    else:
        with path.open("w", encoding="utf-8") as fh:
            fh.write("\n".join(new_lines) + "\n")
        print_row(str(path), "UPDATED", "no-backup")


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
    targets: List[Path] = []
    if args.paths:
        for p in args.paths:
            targets.append(Path(p))
    else:
        # discover all requirements.txt under the repo root
        for p in _REPO_ROOT.rglob("requirements.txt"):
            targets.append(p)
        # deduplicate while preserving order
        seen = set()
        dedup: List[Path] = []
        for t in targets:
            try:
                tp = t.resolve()
            except Exception:
                tp = t
            if tp not in seen:
                dedup.append(t)
                seen.add(tp)
        targets = dedup

    if not targets:
        print("No requirements files found or specified.")
        return 1

    print_table_header()
    any_updates = False
    for p in targets:
        lines = parse_requirements(p)
        if not lines:
            print_row(str(p), "SKIPPED", "empty or missing")
            continue
        updates_for_file = []
        new_lines: List[str] = []
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
            # Decide whether update is needed
            # If pinned == and matches, it's up-to-date
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
                    new_req = build_new_requirement(req_obj, latest) or ln
                    updates_for_file.append((ln, new_req))
                    new_lines.append(new_req)
                    continue
            else:
                # any other specifier or no specifier -> report available and offer pin
                print_row(f"{p.name}:{name}", "AVAILABLE", f"{old_spec or '(no spec)'} -> {latest}")
                any_updates = True
                if args.apply:
                    # pin to latest
                    if req_obj is not None:
                        new_req = build_new_requirement(req_obj, latest) or ln
                        updates_for_file.append((ln, new_req))
                        new_lines.append(new_req)
                    else:
                        # fallback
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
                    continue
            # write file with optional backup
            try:
                update_file(p, new_lines, backup=args.backup)
            except Exception as e:
                print_row(str(p), "FAILED", str(e))
        else:
            if args.apply:
                print_row(str(p), "NO-CHANGES", "No updates detected or nothing to apply")

    if not any_updates:
        print('\nNo updates detected for checked requirements.')
    else:
        print('\nSome packages have newer versions available. Run with --apply to pin to latest versions.')

    return 0


if __name__ == "__main__":
    sys.exit(main())
