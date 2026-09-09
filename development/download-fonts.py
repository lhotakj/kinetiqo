#!/usr/bin/env python3
"""Download and self-host all Google Fonts used by Kinetiqo.

Usage
-----
From the repository root::

    python development/download-fonts.py
    python development/download-fonts.py --force

What it does
------------
Downloads two sets of fonts from Google Fonts CDN and writes them to
``static/fonts/`` and ``static/css/``:

1. **Base fonts** (Inter, Italiana, Merriweather) — used on every page.
   Written to ``static/css/google_fonts_local.css``.

2. **Poster fonts** (Amatic SC, Bebas Neue, Cinzel, … 19 families total) —
   used only on the poster editor page.
   Written to ``static/css/google_fonts_poster_local.css``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make ``kinetiqo`` importable when running from the repo root.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from kinetiqo.web.fonts import (  # noqa: E402
    ALLOWED_SCRIPTS,
    BASE_GOOGLE_FONTS_URL,
    LOCAL_FONTS_CSS_NAME,
    POSTER_GOOGLE_FONTS_URL,
    POSTER_LOCAL_FONTS_CSS_NAME,
    _BROWSER_UA,
    generate_local_css,
    parse_font_blocks,
)

STATIC_DIR = _REPO_ROOT / "src" / "kinetiqo" / "web" / "static"
FONTS_DIR = STATIC_DIR / "fonts"


def print_row(name: str, status: str, info: str):
    """Print a single clean column-aligned row of output."""
    name_col = name[:32].ljust(32)
    status_col = status[:12].ljust(12)
    print(f"  {name_col} {status_col} {info}")


def print_table_header():
    """Print column header for font updates."""
    print(f"\n  {'Font / Asset'.ljust(32)} {'Status'.ljust(12)} Destination / Info")
    print(f"  {'─' * 32} {'─' * 12} {'─' * 45}")


def _download_set(
    url: str,
    css_path: Path,
    label: str,
    force: bool,
    verbose: bool = False,
) -> tuple[int, int]:
    """Download one font set and write its CSS file. Returns (downloaded, skipped)."""
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is not installed. Run: pip install httpx", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"  Fetching font CSS index from: {url}")

    resp = httpx.get(url, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True, timeout=15)
    resp.raise_for_status()

    blocks = parse_font_blocks(resp.text)
    blocks = [b for b in blocks if b["script"] in ALLOWED_SCRIPTS]
    if not blocks:
        print_row(label, "FAILED", f"No @font-face blocks found for {url}")
        return 0, 0

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    css_path.parent.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    for b in blocks:
        local_file = FONTS_DIR / b["filename"]
        rel_file = local_file.relative_to(_REPO_ROOT)
        font_name = f"{b['family']} ({b['style']}, {b['script']})"

        if local_file.exists() and not force:
            print_row(font_name, "SKIPPED", str(rel_file))
            skipped += 1
            continue

        repo_root = _REPO_ROOT.resolve()
        target_local_file = local_file.resolve()
        try:
            target_local_file.relative_to(repo_root)
        except ValueError:
            print_row(font_name, "FAILED", f"Path outside repository: {local_file}")
            continue

        try:
            font_resp = httpx.get(b["src_url"], timeout=30, follow_redirects=True)
            font_resp.raise_for_status()
            tmp = target_local_file.with_suffix(".tmp")
            tmp.write_bytes(font_resp.content)
            tmp.replace(target_local_file)
            size_kb = len(font_resp.content) / 1024.0
            print_row(font_name, "DOWNLOADED", f"{rel_file} ({size_kb:.1f} KB)")
            downloaded += 1
        except Exception as err:
            print_row(font_name, "FAILED", f"{rel_file} ({err})")

    css_content = generate_local_css(blocks)
    target_css_path = css_path.resolve()
    target_css_path.relative_to(_REPO_ROOT.resolve())
    target_css_path.write_text(css_content, encoding="utf-8")
    rel_css = css_path.relative_to(_REPO_ROOT)
    print_row(f"{label} CSS", "GENERATED", str(rel_css))

    return downloaded, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download all Google Fonts (base + poster) for local serving.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Re-download and overwrite existing woff2 files.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose download progress and URLs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print_table_header()

    total_dl = total_sk = 0

    dl, sk = _download_set(
        BASE_GOOGLE_FONTS_URL,
        STATIC_DIR / "css" / LOCAL_FONTS_CSS_NAME,
        "Base Fonts",
        force=args.force,
        verbose=args.verbose,
    )
    total_dl += dl
    total_sk += sk

    dl, sk = _download_set(
        POSTER_GOOGLE_FONTS_URL,
        STATIC_DIR / "css" / POSTER_LOCAL_FONTS_CSS_NAME,
        "Poster Fonts",
        force=args.force,
        verbose=args.verbose,
    )
    total_dl += dl
    total_sk += sk

    print(f"\n  Finished font updates ({total_dl} downloaded, {total_sk} skipped).\n")


if __name__ == "__main__":
    main()
