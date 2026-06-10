#!/usr/bin/env python3
"""Download and self-host all Google Fonts used by Kinetiqo.

Usage
-----
From the repository root::

    python development/download-fonts.py

What it does
------------
Downloads two sets of fonts from Google Fonts CDN and writes them to
``static/fonts/`` and ``static/css/``:

1. **Base fonts** (Inter, Italiana, Merriweather) — used on every page.
   Written to ``static/css/google_fonts_local.css``.

2. **Poster fonts** (Amatic SC, Bebas Neue, Cinzel, … 19 families total) —
   used only on the poster editor page.
   Written to ``static/css/google_fonts_poster_local.css``.

woff2 files are saved with human-readable names::

    inter_italic_latin.woff2
    inter_normal_latin.woff2
    italiana_normal_latin.woff2
    merriweather_normal_latin.woff2
    oswald_normal_latin.woff2
    …

When to run this script
-----------------------
- After cloning the repo if the font files are missing (they are normally
  committed, so this should be rare).
- When you want to pull fresh font files from Google (e.g. after Google
  updates a font to a new version).  Pass ``--force`` to overwrite existing
  files.

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


def _download_set(
    url: str,
    css_path: Path,
    label: str,
    force: bool,
) -> tuple[int, int]:
    """Download one font set and write its CSS file. Returns (downloaded, skipped)."""
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is not installed.  Run: pip install httpx", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(f"  CSS URL: {url}\n")

    resp = httpx.get(url, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True, timeout=15)
    resp.raise_for_status()

    blocks = parse_font_blocks(resp.text)
    blocks = [b for b in blocks if b["script"] in ALLOWED_SCRIPTS]
    if not blocks:
        print(f"  ERROR: no @font-face blocks found for {label}.", file=sys.stderr)
        return 0, 0

    print(f"  Found {len(blocks)} @font-face blocks:\n")
    max_name = max(len(b["filename"]) for b in blocks)
    for b in blocks:
        print(f"    {b['filename'].ljust(max_name)}  ({b['family']}, {b['style']}, {b['script']})")
    print()

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    css_path.parent.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    for b in blocks:
        local_file = FONTS_DIR / b["filename"]
        if local_file.exists() and not force:
            print(f"  skip  {b['filename']}  (already exists; use --force to overwrite)")
            skipped += 1
            continue
        print(f"  GET   {b['filename']}")
        font_resp = httpx.get(b["src_url"], timeout=30, follow_redirects=True)
        font_resp.raise_for_status()
        tmp = local_file.with_suffix(".tmp")
        tmp.write_bytes(font_resp.content)
        tmp.replace(local_file)
        downloaded += 1

    css_content = generate_local_css(blocks)
    css_path.write_text(css_content, encoding="utf-8")
    print(f"\n  CSS written → {css_path.relative_to(_REPO_ROOT)}")
    return downloaded, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download all Google Fonts (base + poster) for local serving.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and overwrite existing woff2 files.",
    )
    args = parser.parse_args()

    total_dl = total_sk = 0

    dl, sk = _download_set(
        BASE_GOOGLE_FONTS_URL,
        STATIC_DIR / "css" / LOCAL_FONTS_CSS_NAME,
        "Base fonts (Inter, Italiana, Merriweather)",
        args.force,
    )
    total_dl += dl; total_sk += sk

    dl, sk = _download_set(
        POSTER_GOOGLE_FONTS_URL,
        STATIC_DIR / "css" / POSTER_LOCAL_FONTS_CSS_NAME,
        "Poster fonts (Amatic SC, Bebas Neue, Cinzel, Cormorant, …)",
        args.force,
    )
    total_dl += dl; total_sk += sk

    print(f"\n{'═' * 60}")
    print(f"  Total: {total_dl} downloaded, {total_sk} skipped.")
    print(f"  Fonts → {FONTS_DIR.relative_to(_REPO_ROOT)}/")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()


