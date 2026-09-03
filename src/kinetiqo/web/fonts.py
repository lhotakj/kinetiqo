"""Shared Google Fonts catalog and URL helpers for the web UI."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger("kinetiqo.web")


@dataclass(frozen=True, slots=True)
class GoogleFont:
    """Metadata for a Google Font used by the application."""

    name: str
    designer: str
    specimen_url: str
    stylesheet_fragment: str


GOOGLE_FONTS: tuple[GoogleFont, ...] = (
    GoogleFont(
        name="Amatic SC",
        designer="Vernon Adams, Ben Nathan, Thomas Jockin",
        specimen_url="https://fonts.google.com/specimen/Amatic+SC",
        stylesheet_fragment="Amatic+SC:wght@400;700",
    ),
    GoogleFont(
        name="Bebas Neue",
        designer="Ryoichi Tsunekawa",
        specimen_url="https://fonts.google.com/specimen/Bebas+Neue",
        stylesheet_fragment="Bebas+Neue:wght@400",
    ),
    GoogleFont(
        name="Cinzel",
        designer="Natanael Gama",
        specimen_url="https://fonts.google.com/specimen/Cinzel",
        stylesheet_fragment="Cinzel:wght@400;700",
    ),
    GoogleFont(
        name="Cormorant",
        designer="Christian Thalmann",
        specimen_url="https://fonts.google.com/specimen/Cormorant",
        stylesheet_fragment="Cormorant:wght@400;700",
    ),
    GoogleFont(
        name="Faculty Glyphic",
        designer="Dalton Maag",
        specimen_url="https://fonts.google.com/specimen/Faculty+Glyphic",
        stylesheet_fragment="Faculty+Glyphic",
    ),
    GoogleFont(
        name="IBM Plex Sans Condensed",
        designer="Mike Abbink (IBM), Bold Monday",
        specimen_url="https://fonts.google.com/specimen/IBM+Plex+Sans+Condensed",
        stylesheet_fragment="IBM+Plex+Sans+Condensed:wght@400;700",
    ),
    GoogleFont(
        name="IBM Plex Serif",
        designer="Mike Abbink (IBM), Bold Monday",
        specimen_url="https://fonts.google.com/specimen/IBM+Plex+Serif",
        stylesheet_fragment="IBM+Plex+Serif:wght@400;700",
    ),
    GoogleFont(
        name="Inter",
        designer="Rasmus Andersson",
        specimen_url="https://rsms.me/inter/",
        stylesheet_fragment="Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900",
    ),
    GoogleFont(
        name="Italiana",
        designer="—",
        specimen_url="https://fonts.google.com/specimen/Italiana",
        stylesheet_fragment="Italiana",
    ),
    GoogleFont(
        name="Limelight",
        designer="Santiago Orozco",
        specimen_url="https://fonts.google.com/specimen/Limelight",
        stylesheet_fragment="Limelight",
    ),
    GoogleFont(
        name="Merriweather",
        designer="Sorkin Type Co",
        specimen_url="https://fonts.google.com/specimen/Merriweather",
        stylesheet_fragment="Merriweather:ital,wght@0,300..900;1,300..900",
    ),
    GoogleFont(
        name="Nunito",
        designer="Vernon Adams, Cyreal, Jacques Le Bailly",
        specimen_url="https://fonts.google.com/specimen/Nunito",
        stylesheet_fragment="Nunito:wght@400;700",
    ),
    GoogleFont(
        name="Open Sans",
        designer="Steve Matteson",
        specimen_url="https://fonts.google.com/specimen/Open+Sans",
        stylesheet_fragment="Open+Sans:wght@400;700",
    ),
    GoogleFont(
        name="Oswald",
        designer="Vernon Adams",
        specimen_url="https://fonts.google.com/specimen/Oswald",
        stylesheet_fragment="Oswald:wght@400;700",
    ),
    GoogleFont(
        name="PT Sans",
        designer="Alexandra Korolkova, Olga Umpeleva, Vladimir Yefimov",
        specimen_url="https://fonts.google.com/specimen/PT+Sans",
        stylesheet_fragment="PT+Sans:wght@400;700",
    ),
    GoogleFont(
        name="PT Sans Narrow",
        designer="Alexandra Korolkova, Olga Umpeleva, Vladimir Yefimov",
        specimen_url="https://fonts.google.com/specimen/PT+Sans+Narrow",
        stylesheet_fragment="PT+Sans+Narrow:wght@400;700",
    ),
    GoogleFont(
        name="Roboto",
        designer="Christian Robertson",
        specimen_url="https://fonts.google.com/specimen/Roboto",
        stylesheet_fragment="Roboto:wght@400;700",
    ),
    GoogleFont(
        name="Roboto Condensed",
        designer="Christian Robertson",
        specimen_url="https://fonts.google.com/specimen/Roboto+Condensed",
        stylesheet_fragment="Roboto+Condensed:wght@400;700",
    ),
    GoogleFont(
        name="Ubuntu",
        designer="Dalton Maag",
        specimen_url="https://fonts.google.com/specimen/Ubuntu",
        stylesheet_fragment="Ubuntu:wght@400;700",
    ),
    GoogleFont(
        name="Yanone Kaffeesatz",
        designer="Yanone",
        specimen_url="https://fonts.google.com/specimen/Yanone+Kaffeesatz",
        stylesheet_fragment="Yanone+Kaffeesatz:wght@400;700",
    ),
    # Added fonts
    GoogleFont(
        name="Quicksand",
        designer="Pablo Impallari, Rodrigo Fuenzalida, Andrew Paglinawan",
        specimen_url="https://fonts.google.com/specimen/Quicksand",
        stylesheet_fragment="Quicksand:wght@300;400;500;600;700",
    ),
    GoogleFont(
        name="Special Elite",
        designer="Astigmatic",
        specimen_url="https://fonts.google.com/specimen/Special+Elite",
        stylesheet_fragment="Special+Elite",
    ),
    GoogleFont(
        name="Asap",
        designer="Omnibus-Type",
        specimen_url="https://fonts.google.com/specimen/Asap",
        stylesheet_fragment="Asap:wght@400;700",
    ),
)

GOOGLE_FONT_CATALOG: dict[str, GoogleFont] = {font.name: font for font in GOOGLE_FONTS}

BASE_GOOGLE_FONT_NAMES: tuple[str, ...] = (
    "Inter",
    "Italiana",
    "Merriweather",
)

LOGIN_GOOGLE_FONT_NAMES: tuple[str, ...] = BASE_GOOGLE_FONT_NAMES

POSTER_GOOGLE_FONT_NAMES: tuple[str, ...] = (
    "Amatic SC",
    "Bebas Neue",
    "Cinzel",
    "Cormorant",
    "Faculty Glyphic",
    "IBM Plex Sans Condensed",
    "IBM Plex Serif",
    "Inter",
    "Limelight",
    "Merriweather",
    "Nunito",
    "Open Sans",
    "Oswald",
    "PT Sans",
    "PT Sans Narrow",
    "Roboto",
    "Roboto Condensed",
    "Ubuntu",
    "Yanone Kaffeesatz",
    "Quicksand",
    "Special Elite",
    "Asap",
)


def get_google_fonts(*font_names: str) -> tuple[GoogleFont, ...]:
    """Return Google font metadata for the requested *font_names*."""

    return tuple(GOOGLE_FONT_CATALOG[name] for name in font_names)


def build_google_fonts_stylesheet_url(font_names: tuple[str, ...] | list[str]) -> str:
    """Build a Google Fonts stylesheet URL for the given *font_names*."""

    unique_names = tuple(dict.fromkeys(font_names))
    families = "&".join(
        f"family={quote_plus(GOOGLE_FONT_CATALOG[name].stylesheet_fragment, safe=':,;@.+-')}"
        for name in unique_names
    )
    return f"https://fonts.googleapis.com/css2?{families}&display=swap"


# Pre-computed stylesheet URLs — stable string constants so the browser can
# cache them across page navigations without any per-request URL variance.
BASE_GOOGLE_FONTS_URL: str = build_google_fonts_stylesheet_url(BASE_GOOGLE_FONT_NAMES)
LOGIN_GOOGLE_FONTS_URL: str = build_google_fonts_stylesheet_url(LOGIN_GOOGLE_FONT_NAMES)
POSTER_GOOGLE_FONTS_URL: str = build_google_fonts_stylesheet_url(POSTER_GOOGLE_FONT_NAMES)

# Filename written to static/css/ when fonts are successfully self-hosted.
LOCAL_FONTS_CSS_NAME: str = "google_fonts_local.css"
POSTER_LOCAL_FONTS_CSS_NAME: str = "google_fonts_poster_local.css"

# Scripts to download/serve — latin covers standard ASCII; latin-ext covers
# Czech diacritics (á, č, ď, é, ě, í, ň, ó, ř, š, ť, ú, ů, ý, ž).
ALLOWED_SCRIPTS: frozenset[str] = frozenset({"latin", "latin-ext"})

# User-Agent that makes Google Fonts return woff2 (modern browser format).
_BROWSER_UA: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def parse_font_blocks(css_text: str) -> list[dict]:
    """Parse a Google Fonts CSS response into a list of structured block dicts.

    Each dict contains:
    ``script``, ``family``, ``style``, ``weight``, ``display``,
    ``unicode_range``, ``src_url`` (original CDN URL), ``filename``
    (human-readable local filename, e.g. ``inter_italic_latin.woff2``).
    """
    block_re = re.compile(
        r"/\*\s*([^*]+?)\s*\*/\s*@font-face\s*\{([^}]+)\}",
        re.DOTALL,
    )
    blocks: list[dict] = []
    for m in block_re.finditer(css_text):
        script = m.group(1).strip()
        body = m.group(2)

        def _prop(name: str, default: str = "") -> str:
            mo = re.search(rf"{name}:\s*([^;]+)", body)
            return mo.group(1).strip() if mo else default

        family = _prop("font-family").strip("'\"")
        style = _prop("font-style", "normal")
        weight = _prop("font-weight", "400")
        display = _prop("font-display", "swap")
        unicode_range = _prop("unicode-range")

        url_match = re.search(r"url\(([^)]+\.woff2[^)]*)\)", body)
        if not url_match:
            continue
        src_url = url_match.group(1).strip("'\"")

        # Human-readable filename: family_style_script.woff2
        # e.g. inter_italic_latin.woff2, italiana_normal_latin.woff2
        family_slug = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
        script_slug = re.sub(r"\s+", "-", script.lower())
        filename = f"{family_slug}_{style}_{script_slug}.woff2"

        blocks.append(
            {
                "script": script,
                "family": family,
                "style": style,
                "weight": weight,
                "display": display,
                "unicode_range": unicode_range,
                "src_url": src_url,
                "filename": filename,
            }
        )
    return blocks


def generate_local_css(
    blocks: list[dict],
    static_fonts_path: str = "/static/fonts",
) -> str:
    """Render a ``@font-face`` CSS file with all ``url()`` pointing to *static_fonts_path*."""
    lines: list[str] = []
    for b in blocks:
        lines += [
            f"/* {b['script']} */",
            "@font-face {",
            f"  font-family: '{b['family']}';",
            f"  font-style: {b['style']};",
            f"  font-weight: {b['weight']};",
             "  font-display: block;",
            f"  src: url('{static_fonts_path}/{b['filename']}') format('woff2');",
            f"  unicode-range: {b['unicode_range']};",
            "}",
            "",
        ]
    return "\n".join(lines)


def ensure_fonts_local(static_dir: str | None) -> str:
    """Return the URL for locally served base Google Fonts CSS.

    The Inter and Italiana woff2 files and the rewritten CSS are committed to
    the repository (``static/fonts/`` and ``static/css/google_fonts_local.css``)
    and are therefore present in every Docker image via ``COPY src ./``.

    On a fresh clone without the committed assets (e.g. a stripped checkout),
    this function downloads them from Google Fonts CDN as a one-time recovery
    step.  Falls back to the CDN URL if the download fails.

    To refresh fonts intentionally, run ``python development/download-fonts.py``.
    """
    static_dir = "" if static_dir is None else static_dir

    css_path = Path(static_dir) / "css" / LOCAL_FONTS_CSS_NAME
    if css_path.exists():
        return f"/static/css/{LOCAL_FONTS_CSS_NAME}"

    # Fonts are missing — attempt a one-time recovery download.
    logger.warning("Local Google Fonts not found in %s; downloading from CDN.", static_dir)
    try:
        import httpx  # already in requirements.txt

        resp = httpx.get(
            BASE_GOOGLE_FONTS_URL,
            headers={"User-Agent": _BROWSER_UA},
            follow_redirects=True,
            timeout=15,
        )
        resp.raise_for_status()

        blocks = [b for b in parse_font_blocks(resp.text) if b["script"] in ALLOWED_SCRIPTS]
        fonts_dir = Path(static_dir) / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)

        for block in blocks:
            local_file = fonts_dir / block["filename"]
            if not local_file.exists():
                font_resp = httpx.get(block["src_url"], timeout=30, follow_redirects=True)
                font_resp.raise_for_status()
                tmp = local_file.with_suffix(".tmp")
                tmp.write_bytes(font_resp.content)
                tmp.replace(local_file)

        css_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_css = css_path.with_suffix(".tmp")
        tmp_css.write_text(generate_local_css(blocks), encoding="utf-8")
        tmp_css.replace(css_path)

        logger.info("Google Fonts downloaded and served locally from /static/")
        return f"/static/css/{LOCAL_FONTS_CSS_NAME}"

    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not download Google Fonts locally (%s); using CDN.", exc)
        return BASE_GOOGLE_FONTS_URL


def ensure_poster_fonts_local(static_dir: str | None) -> str:
    """Return the URL for locally served poster Google Fonts CSS.

    All poster fonts (Amatic SC, Bebas Neue, Cinzel, etc.) are downloaded to
    ``static/fonts/`` on first use and referenced via ``static/css/google_fonts_poster_local.css``.

    Falls back to the CDN URL only if the download fails (e.g. no network access
    at startup time).  To refresh intentionally, run ``python development/download-fonts.py``.
    """

    static_dir = "" if static_dir is None else static_dir

    css_path = Path(static_dir) / "css" / POSTER_LOCAL_FONTS_CSS_NAME
    if css_path.exists():
        return f"/static/css/{POSTER_LOCAL_FONTS_CSS_NAME}"

    logger.warning("Local poster Google Fonts not found in %s; downloading from CDN.", static_dir)
    try:
        import httpx  # already in requirements.txt

        resp = httpx.get(
            POSTER_GOOGLE_FONTS_URL,
            headers={"User-Agent": _BROWSER_UA},
            follow_redirects=True,
            timeout=15,
        )
        resp.raise_for_status()

        blocks = [b for b in parse_font_blocks(resp.text) if b["script"] in ALLOWED_SCRIPTS]
        fonts_dir = Path(static_dir) / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)

        for block in blocks:
            local_file = fonts_dir / block["filename"]
            if not local_file.exists():
                font_resp = httpx.get(block["src_url"], timeout=30, follow_redirects=True)
                font_resp.raise_for_status()
                tmp = local_file.with_suffix(".tmp")
                tmp.write_bytes(font_resp.content)
                tmp.replace(local_file)

        css_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_css = css_path.with_suffix(".tmp")
        tmp_css.write_text(generate_local_css(blocks), encoding="utf-8")
        tmp_css.replace(css_path)

        logger.info("Poster Google Fonts downloaded and served locally from /static/")
        return f"/static/css/{POSTER_LOCAL_FONTS_CSS_NAME}"

    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not download poster Google Fonts locally (%s); using CDN.", exc)
        return POSTER_GOOGLE_FONTS_URL


