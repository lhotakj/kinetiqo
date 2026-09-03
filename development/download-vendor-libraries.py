#!/usr/bin/env python3
"""Unified vendor library manager and downloader for Kinetiqo.

Downloads all frontend vendor libraries (HTMX, jQuery, Leaflet, Chart.js,
DataTables, Select2, Date Range Picker, Moment, JSZip, SortableJS, html2canvas,
Tailwind) and prerequisite binaries (Tailwind CLI) based on parameters defined
in ``development/vendor-libraries.yaml``.

Usage
-----
    python development/download-vendor-libraries.py
    python development/download-vendor-libraries.py --force
    python development/download-vendor-libraries.py --library htmx
"""

from __future__ import annotations

import argparse
import os
import platform
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _REPO_ROOT / "development" / "vendor-libraries.yaml"


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load and parse the vendor libraries YAML configuration file."""
    repo_root = _REPO_ROOT.resolve()
    target_path = config_path.resolve()

    try:
        target_path.relative_to(repo_root)
    except ValueError:
        print(f"ERROR: Configuration file path outside repository: {config_path}", file=sys.stderr)
        sys.exit(1)

    if not target_path.is_file():
        print(f"ERROR: Configuration file not found: {target_path}", file=sys.stderr)
        sys.exit(1)

    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    with open(target_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_template_str(template: str, version: str | None, versions: dict[str, str] | None) -> str:
    """Format string template replacing {version} and {versions.key} placeholders."""
    result = template
    if version:
        result = result.replace("{version}", version)
    if versions:
        for k, v in versions.items():
            result = result.replace(f"{{versions.{k}}}", v)
    return result


def print_row(name: str, status: str, info: str):
    """Print a single clean column-aligned row of output."""
    name_col = name[:32].ljust(32)
    status_col = status[:12].ljust(12)
    print(f"  {name_col} {status_col} {info}")


def print_table_header():
    """Print column header for vendor library updates."""
    print(f"\n  {'Library / Asset'.ljust(32)} {'Status'.ljust(12)} Destination / Info")
    print(f"  {'─' * 32} {'─' * 12} {'─' * 45}")


def download_file(
    url: str,
    dest_path: Path,
    label: str = "",
    force: bool = False,
    verbose: bool = False,
) -> tuple[bool, str]:
    """Download a file from a URL to dest_path if not already present or force=True.

    Returns (was_downloaded, status_string).
    """
    if not label:
        label = dest_path.name
    rel_path = dest_path.relative_to(_REPO_ROOT) if dest_path.is_relative_to(_REPO_ROOT) else dest_path

    if dest_path.is_file() and not force:
        print_row(label, "SKIPPED", str(rel_path))
        return False, "SKIPPED"

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        pass

    if verbose:
        print(f"  Downloading {url} -> {rel_path}")

    try:
        import httpx

        resp = httpx.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
        content = resp.content
    except ImportError:
        req = urllib.request.Request(url, headers={"User-Agent": "kinetiqo-vendor-downloader/1.0"})
        with urllib.request.urlopen(req, timeout=30.0) as response:
            content = response.read()

    repo_root = _REPO_ROOT.resolve()
    target_path = dest_path.resolve()

    try:
        target_path.relative_to(repo_root)
    except ValueError:
        print_row(label, "FAILED", f"Destination path outside repository: {dest_path}")
        return False, "FAILED"

    with open(target_path, "wb") as f:
        f.write(content)

    size_kb = len(content) / 1024.0
    size_str = f"{size_kb:.1f} KB" if size_kb >= 1.0 else f"{len(content)} B"
    print_row(label, "DOWNLOADED", f"{rel_path} ({size_str})")
    return True, "DOWNLOADED"


def detect_platform_os_arch(
    os_map: dict[str, str],
    arch_map: dict[str, str],
) -> tuple[str, str]:
    """Detect current operating system and hardware architecture."""
    sys_os = platform.system().lower()
    if "linux" in sys_os:
        detected_os = os_map.get("linux", "linux")
    elif "darwin" in sys_os:
        detected_os = os_map.get("darwin", "macos")
    elif "win" in sys_os:
        detected_os = os_map.get("windows", "windows")
    else:
        detected_os = "linux"

    machine = platform.machine().lower()
    detected_arch = arch_map.get(machine, "x64")

    return detected_os, detected_arch


def download_tailwind_cli(
    prereq_cfg: dict[str, Any],
    force: bool = False,
    verbose: bool = False,
) -> Path:
    """Download the standalone Tailwind CSS CLI executable binary for current platform."""
    version = prereq_cfg["version"]
    target_dir = _REPO_ROOT / prereq_cfg["target_dir"]
    os_mapped, arch_mapped = detect_platform_os_arch(
        prereq_cfg.get("os_map", {}),
        prereq_cfg.get("arch_map", {}),
    )

    bin_name = prereq_cfg["filename"]
    if sys.platform.startswith("win32") and not bin_name.endswith(".exe"):
        bin_name += ".exe"

    binary_path = target_dir / bin_name
    ext = ".exe" if os_mapped == "windows" else ""

    if version == "latest":
        url_template = prereq_cfg["latest_template"]
    else:
        url_template = prereq_cfg["asset_template"]

    url = url_template.format(version=version, os=os_mapped, arch=arch_mapped, ext=ext)
    label = f"{prereq_cfg['name']} ({version})"

    download_file(url, binary_path, label=label, force=force, verbose=verbose)

    # Ensure owner and group executable permissions on POSIX systems (Sonar rule python:S2612)
    if not sys.platform.startswith("win32") and binary_path.is_file():
        st = os.stat(binary_path)
        os.chmod(binary_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP)

    return binary_path


def build_tailwind_css(
    build_cfg: dict[str, Any],
    binary_path: Path,
) -> bool:
    """Execute the Tailwind CLI to compile input CSS to minified output CSS."""
    input_css = _REPO_ROOT / build_cfg["input_css"]
    output_css = _REPO_ROOT / build_cfg["output_css"]

    if not binary_path.is_file() or not input_css.is_file():
        print_row("Tailwind CSS Compiler", "FAILED", f"Missing binary ({binary_path.name}) or input CSS")
        return False

    output_css.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(binary_path), "-i", str(input_css), "-o", str(output_css)]
    if build_cfg.get("minify", True):
        cmd.append("--minify")

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print_row("Tailwind CSS Compiler", "FAILED", res.stderr.strip() or "Compilation error")
        return False

    rel_out = output_css.relative_to(_REPO_ROOT)
    print_row("Tailwind CSS Compiler", "COMPILED", str(rel_out))

    if "vendor_css" in build_cfg:
        vendor_css = _REPO_ROOT / build_cfg["vendor_css"]
        try:
            vendor_css.parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass
        import shutil

        shutil.copy2(output_css, vendor_css)
        rel_vendor = vendor_css.relative_to(_REPO_ROOT)
        print_row("Tailwind CSS Vendor Copy", "COPIED", str(rel_vendor))

    return True


def download_library(
    lib_cfg: dict[str, Any],
    vendor_base_dir: Path,
    force: bool = False,
    verbose: bool = False,
) -> int:
    """Download all files for a single library entry. Returns total files downloaded."""
    name = lib_cfg["name"]
    version = lib_cfg.get("version")
    versions = lib_cfg.get("versions")
    target_dir = vendor_base_dir / lib_cfg["target_dir"]

    downloaded_count = 0
    for file_spec in lib_cfg.get("files", []):
        filename = format_template_str(file_spec["filename"], version, versions)
        url = format_template_str(file_spec["url"], version, versions)
        dest_file = target_dir / filename
        label = f"{name}" if len(lib_cfg.get("files", [])) == 1 else f"{name} ({filename})"

        was_dl, _ = download_file(url, dest_file, label=label, force=force, verbose=verbose)
        if was_dl:
            downloaded_count += 1

    return downloaded_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and update Kinetiqo vendor libraries and CLI binaries."
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to vendor-libraries.yaml configuration file.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force re-download and overwrite existing files.",
    )
    parser.add_argument(
        "-l",
        "--library",
        type=str,
        help="Filter downloads by specific library ID (e.g. htmx, jquery, tailwind).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose download progress and URLs.",
    )
    parser.add_argument(
        "--skip-cli",
        action="store_true",
        help="Skip downloading Tailwind CLI binary.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building Tailwind CSS output file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_yaml_config(args.config)

    settings = config.get("settings", {})
    vendor_base_dir = _REPO_ROOT / settings.get("vendor_base_dir", "src/kinetiqo/web/static/vendor")

    target_lib_filter = args.library.lower().strip() if args.library else None

    print_table_header()

    # Handle Tailwind CLI prerequisite
    tw_cli_binary = None
    prereqs = config.get("prerequisites", {})
    if "tailwind_cli" in prereqs and not args.skip_cli:
        tw_cfg = prereqs["tailwind_cli"]
        tw_id = tw_cfg.get("id", "tailwind-cli")
        if target_lib_filter is None or target_lib_filter in (tw_id, "tailwind_cli", "tailwind-cli"):
            tw_cli_binary = download_tailwind_cli(tw_cfg, force=args.force, verbose=args.verbose)

            if "build_step" in tw_cfg and not args.skip_build:
                build_tailwind_css(tw_cfg["build_step"], tw_cli_binary)

    # If only targeting tailwind-cli, exit early
    if target_lib_filter in ("tailwind-cli", "tailwind_cli"):
        print()
        return 0

    libraries = config.get("libraries", [])
    total_downloaded = 0

    for lib in libraries:
        lib_id = lib.get("id", "").lower().strip()
        if target_lib_filter and target_lib_filter != lib_id:
            continue

        total_downloaded += download_library(lib, vendor_base_dir, force=args.force, verbose=args.verbose)

    print(f"\n  Finished vendor updates ({total_downloaded} downloaded/updated).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
