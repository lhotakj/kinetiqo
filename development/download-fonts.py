#!/usr/bin/env python3
"""Download and self-host base Google Fonts (Inter + Italiana).

Usage
-----
From the repository root::

    python development/download-fonts.py

What it does
------------
1. Fetches the Google Fonts CSS for Inter and Italiana from Google's CDN,
   using a modern browser User-Agent so the API returns woff2 format.
2. Parses every ``@font-face`` block from the response.
3. Downloads each woff2 file and saves it to ``static/fonts/`` with a
   human-readable name derived from the font family, style and script subset::

       inter_italic_latin.woff2
       inter_normal_latin.woff2
       inter_normal_cyrillic-ext.woff2
       italiana_normal_latin.woff2
       …

4. Writes ``static/css/google_fonts_local.css`` — a clean ``@font-face``
   stylesheet with all ``url()`` values pointing at ``/static/fonts/``.

When to run this script
-----------------------
- After cloning the repo if the font files are missing (they are normally
  committed, so this should be rare).
- When you want to pull fresh font files from Google (e.g. after Google
  updates Inter to a new version).  Delete the old woff2 files first or
  pass ``--force`` to overwrite them.

The generated files are committed to the repository so that Docker images
are built with fonts already present — zero internet access required at
runtime.
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
    BASE_GOOGLE_FONTS_URL,
    LOCAL_FONTS_CSS_NAME,
    _BROWSER_UA,
    generate_local_css,
    parse_font_blocks,
)

STATIC_DIR = _REPO_ROOT / "src" / "kinetiqo" / "web" / "static"
FONTS_DIR = STATIC_DIR / "fonts"
CSS_PATH = STATIC_DIR / "css" / LOCAL_FONTS_CSS_NAME


def _download(force: bool = False) -> None:
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is not installed.  Run: pip install httpx", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching font CSS from:\n  {BASE_GOOGLE_FONTS_URL}\n")
    resp = httpx.get(
        BASE_GOOGLE_FONTS_URL,
        headers={"User-Agent": _BROWSER_UA},
        follow_redirects=True,
        timeout=15,
    )
    resp.raise_for_status()

    blocks = parse_font_blocks(resp.text)
    if not blocks:
        print("ERROR: no @font-face blocks found in the CSS response.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(blocks)} @font-face blocks:\n")
    max_name = max(len(b["filename"]) for b in blocks)
    for b in blocks:
        name_col = b["filename"].ljust(max_name)
        print(f"  {name_col}  ({b['family']}, {b['style']}, {b['script']})")
    print()

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    CSS_PATH.parent.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    for b in blocks:
        local_file = FONTS_DIR / b["filename"]
        if local_file.exists() and not force:
            print(f"  skip  {b['filename']}  (already exists; use --force to overwrite)")
            skipped += 1
            continue
        print(f"  GET   {b['filename']}  ({b['src_url'].rsplit('/', 1)[-1]})")
        font_resp = httpx.get(b["src_url"], timeout=30, follow_redirects=True)
        font_resp.raise_for_status()
        tmp = local_file.with_suffix(".tmp")
        tmp.write_bytes(font_resp.content)
        tmp.rename(local_file)
        downloaded += 1

    # Always regenerate the CSS so it reflects the current file list.
    css_content = generate_local_css(blocks)
    CSS_PATH.write_text(css_content, encoding="utf-8")

    print()
    print(f"Done.  {downloaded} downloaded, {skipped} skipped.")
    print(f"  CSS  → {CSS_PATH.relative_to(_REPO_ROOT)}")
    print(f"  Fonts → {FONTS_DIR.relative_to(_REPO_ROOT)}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Inter + Italiana from Google Fonts CDN for local serving.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and overwrite existing woff2 files.",
    )
    args = parser.parse_args()
    _download(force=args.force)


if __name__ == "__main__":
    main()
