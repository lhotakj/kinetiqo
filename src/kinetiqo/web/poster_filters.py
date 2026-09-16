"""Modular image processing filters for the Kinetiqo Poster generator.

Provides high-performance image adjustments for Color, Light, and Details
categories matching photo editor workflows (e.g. Lightroom, Apple Photos).
Built on Pillow with graceful fallbacks.
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping

from PIL import Image, ImageEnhance, ImageFilter

# Default filter settings dictionary
DEFAULT_PHOTO_FILTERS: dict[str, dict[str, int]] = {
    'color': {
        'vibrance': 0,      # -100 .. +100
        'saturation': 0,    # -100 .. +100
        'temperature': 0,   # -100 (cool/blue) .. +100 (warm/amber)
        'tint': 0,          # -100 (magenta) .. +100 (green)
        'hue': 0,           # -100 .. +100 (-180° .. +180°)
    },
    'light': {
        'brightness': 0,    # -100 .. +100
        'exposure': 0,      # -100 .. +100
        'contrast': 0,      # -100 .. +100
        'black': 0,         # -100 .. +100
        'white': 0,         # -100 .. +100
        'highlights': 0,    # -100 .. +100
        'shadows': 0,       # -100 .. +100
    },
    'details': {
        'sharpen': 0,       # 0 .. 100
        'clarity': 0,       # -100 .. +100
        'smooth': 0,        # 0 .. 100
        'blur': 0,          # 0 .. 100
        'grain': 0,         # 0 .. 100
    },
}


def clamp(val: float | int, low: float | int, high: float | int) -> float:
    """Clamp a numeric value between lower and upper bounds.

    Args:
        val: Input number to clamp.
        low: Minimum acceptable bound.
        high: Maximum acceptable bound.

    Returns:
        The value bounded between low and high inclusive.
    """
    return max(low, min(val, high))


def normalize_filter_settings(raw: Mapping[str, Any] | None) -> dict[str, dict[str, int]]:
    """Normalize and validate filter settings dictionary with defaults.

    Ensures all 17 keys are present, type-safe, and bounded within their
    respective permissible ranges.

    Args:
        raw: Potentially partial or untrusted settings mapping from request
            payload or localStorage JSON.

    Returns:
        Complete validated dictionary guaranteed to have 'color', 'light',
        and 'details' sub-dictionaries with all integer values clamped.
    """
    out: dict[str, dict[str, int]] = {
        'color': dict(DEFAULT_PHOTO_FILTERS['color']),
        'light': dict(DEFAULT_PHOTO_FILTERS['light']),
        'details': dict(DEFAULT_PHOTO_FILTERS['details']),
    }
    if not isinstance(raw, (dict, Mapping)):
        return out

    color_in = raw.get('color', {})
    if isinstance(color_in, (dict, Mapping)):
        for k in out['color']:
            if k in color_in:
                try:
                    val = int(round(float(color_in[k])))
                    out['color'][k] = int(clamp(val, -100, 100))
                except (ValueError, TypeError):
                    pass

    light_in = raw.get('light', {})
    if isinstance(light_in, (dict, Mapping)):
        for k in out['light']:
            if k in light_in:
                try:
                    val = int(round(float(light_in[k])))
                    out['light'][k] = int(clamp(val, -100, 100))
                except (ValueError, TypeError):
                    pass

    details_in = raw.get('details', {})
    if isinstance(details_in, (dict, Mapping)):
        for k in out['details']:
            if k in details_in:
                try:
                    val = int(round(float(details_in[k])))
                    low = 0 if k in ('sharpen', 'smooth', 'blur', 'grain') else -100
                    out['details'][k] = int(clamp(val, low, 100))
                except (ValueError, TypeError):
                    pass

    return out


# ── Color Filters ─────────────────────────────────────────────────────────────

def apply_color_filters(img: Image.Image, color_settings: Mapping[str, Any]) -> Image.Image:
    """Apply Color adjustments: Vibrance, Saturation, Temperature, Tint, Hue.

    Args:
        img: Input Pillow Image (RGB or RGBA mode).
        color_settings: Dictionary of color adjustment parameters.

    Returns:
        Color-adjusted Pillow Image preserving image dimensions and alpha channel.
    """
    settings = normalize_filter_settings({'color': color_settings})['color']
    vibrance = settings['vibrance']
    saturation = settings['saturation']
    temperature = settings['temperature']
    tint = settings['tint']
    hue = settings['hue']

    if all(v == 0 for v in (vibrance, saturation, temperature, tint, hue)):
        return img

    has_alpha = img.mode == 'RGBA'
    alpha = img.getchannel('A') if has_alpha else None
    working = img.convert('RGB')

    # 1. Temperature & Tint (Channel balance)
    if temperature != 0 or tint != 0:
        # Temperature: negative = cooler (blue), positive = warmer (amber/red)
        # Tint: negative = magenta (R+B), positive = green (G)
        t_factor = temperature / 100.0  # -1.0 .. 1.0
        g_factor = tint / 100.0         # -1.0 .. 1.0

        r_scale = 1.0 + 0.22 * t_factor - 0.08 * g_factor
        g_scale = 1.0 + 0.20 * g_factor
        b_scale = 1.0 - 0.22 * t_factor - 0.08 * g_factor

        r_lut = [int(clamp(i * r_scale, 0, 255)) for i in range(256)]
        g_lut = [int(clamp(i * g_scale, 0, 255)) for i in range(256)]
        b_lut = [int(clamp(i * b_scale, 0, 255)) for i in range(256)]

        r, g, b = working.split()
        r = r.point(r_lut)
        g = g.point(g_lut)
        b = b.point(b_lut)
        working = Image.merge('RGB', (r, g, b))

    # 2. Hue rotation
    if hue != 0:
        hsv = working.convert('HSV')
        h, s, v = hsv.split()
        shift = int(round((hue / 100.0) * 128))  # maps -100..100 to -128..128 in 0..255 space
        h_lut = [(i + shift) % 256 for i in range(256)]
        h = h.point(h_lut)
        working = Image.merge('HSV', (h, s, v)).convert('RGB')

    # 3. Saturation
    if saturation != 0:
        sat_factor = max(0.0, 1.0 + saturation / 100.0)
        enhancer = ImageEnhance.Color(working)
        working = enhancer.enhance(sat_factor)

    # 4. Vibrance (Smart non-linear saturation)
    if vibrance != 0:
        vib_factor = vibrance / 100.0
        hsv = working.convert('HSV')
        h, s, v = hsv.split()
        # Non-linear curve: boosts lower-saturated pixels more than high-saturation pixels
        s_lut = []
        for i in range(256):
            norm_s = i / 255.0
            if vib_factor > 0:
                # Boost low saturation more
                boost = (1.0 - norm_s) * vib_factor * 0.75
                new_s = norm_s + boost
            else:
                # Attenuate gently
                new_s = norm_s * (1.0 + vib_factor * 0.6)
            s_lut.append(int(clamp(round(new_s * 255), 0, 255)))
        s = s.point(s_lut)
        working = Image.merge('HSV', (h, s, v)).convert('RGB')

    if has_alpha and alpha is not None:
        working.putalpha(alpha)
    return working


# ── Light Filters ─────────────────────────────────────────────────────────────

def apply_light_filters(img: Image.Image, light_settings: Mapping[str, Any]) -> Image.Image:
    """Apply Light adjustments: Brightness, Exposure, Contrast, Black, White, Highlights, Shadows.

    Args:
        img: Input Pillow Image (RGB or RGBA mode).
        light_settings: Dictionary of light and exposure adjustment parameters.

    Returns:
        Light-adjusted Pillow Image preserving image dimensions and alpha channel.
    """
    settings = normalize_filter_settings({'light': light_settings})['light']
    brightness = settings['brightness']
    exposure = settings['exposure']
    contrast = settings['contrast']
    black = settings['black']
    white = settings['white']
    highlights = settings['highlights']
    shadows = settings['shadows']

    if all(v == 0 for v in (brightness, exposure, contrast, black, white, highlights, shadows)):
        return img

    has_alpha = img.mode == 'RGBA'
    alpha = img.getchannel('A') if has_alpha else None
    working = img.convert('RGB')

    # 1. Exposure (photographic exponential scaling 2^EV)
    if exposure != 0:
        ev_factor = math.pow(2.0, exposure / 60.0)  # -100 to 100 maps to ~0.31x .. 3.17x
        enhancer = ImageEnhance.Brightness(working)
        working = enhancer.enhance(ev_factor)

    # 2. Brightness
    if brightness != 0:
        b_factor = max(0.0, 1.0 + brightness / 100.0)
        enhancer = ImageEnhance.Brightness(working)
        working = enhancer.enhance(b_factor)

    # 3. Contrast
    if contrast != 0:
        c_factor = max(0.0, 1.0 + contrast / 100.0)
        enhancer = ImageEnhance.Contrast(working)
        working = enhancer.enhance(c_factor)

    # 4. Black / White clipping & Highlights / Shadows curves via single LUT
    if black != 0 or white != 0 or highlights != 0 or shadows != 0:
        black_shift = (black / 100.0) * 35.0        # -35 .. +35
        white_shift = (white / 100.0) * 35.0        # -35 .. +35
        hi_factor = highlights / 100.0              # -1.0 .. 1.0
        sh_factor = shadows / 100.0                 # -1.0 .. 1.0

        lut = []
        for i in range(256):
            val = float(i)
            # Black point adjust (mostly affects 0..80)
            if val < 128:
                weight_b = (128.0 - val) / 128.0
                val = val + black_shift * weight_b

            # White point adjust (mostly affects 128..255)
            if val > 128:
                weight_w = (val - 128.0) / 128.0
                val = val + white_shift * weight_w

            # Shadows curve (affects lower half)
            if sh_factor != 0 and val < 128:
                sh_weight = math.sin((val / 128.0) * math.pi)
                val = val + (sh_factor * 30.0 * sh_weight)

            # Highlights curve (affects upper half)
            if hi_factor != 0 and val >= 128:
                hi_weight = math.sin(((val - 128.0) / 128.0) * math.pi)
                val = val + (hi_factor * 30.0 * hi_weight)

            lut.append(int(clamp(round(val), 0, 255)))

        working = working.point(lut * 3)

    if has_alpha and alpha is not None:
        working.putalpha(alpha)
    return working


# ── Details Filters ───────────────────────────────────────────────────────────

def apply_detail_filters(img: Image.Image, detail_settings: Mapping[str, Any]) -> Image.Image:
    """Apply Details adjustments: Sharpen, Clarity, Smooth, Blur, Grain.

    Args:
        img: Input Pillow Image (RGB or RGBA mode).
        detail_settings: Dictionary of detail/texture parameters.

    Returns:
        Detail-adjusted Pillow Image preserving image dimensions and alpha channel.
    """
    settings = normalize_filter_settings({'details': detail_settings})['details']
    sharpen = settings['sharpen']
    clarity = settings['clarity']
    smooth = settings['smooth']
    blur = settings['blur']
    grain = settings['grain']

    if all(v == 0 for v in (sharpen, clarity, smooth, blur, grain)):
        return img

    has_alpha = img.mode == 'RGBA'
    alpha = img.getchannel('A') if has_alpha else None
    working = img.convert('RGB')

    # 1. Blur
    if blur > 0:
        radius = (blur / 100.0) * 8.0  # up to 8px radius
        working = working.filter(ImageFilter.GaussianBlur(radius=radius))

    # 2. Smooth (Bilateral-like edge-preserving smoothing)
    if smooth > 0:
        # Box/Gaussian blur blended with base by smooth amount
        smooth_radius = 1.0 + (smooth / 100.0) * 3.0
        smoothed = working.filter(ImageFilter.GaussianBlur(radius=smooth_radius))
        alpha_mix = (smooth / 100.0) * 0.70
        working = Image.blend(working, smoothed, alpha_mix)

    # 3. Sharpen
    if sharpen > 0:
        sharp_factor = 1.0 + (sharpen / 100.0) * 3.0
        enhancer = ImageEnhance.Sharpness(working)
        working = enhancer.enhance(sharp_factor)

    # 4. Clarity (local midtone contrast via unsharp mask with large radius)
    if clarity != 0:
        percent = int(abs(clarity) * 2.0)
        unsharp = working.filter(ImageFilter.UnsharpMask(radius=12, percent=percent, threshold=3))
        if clarity > 0:
            mix = min(1.0, clarity / 100.0)
            working = Image.blend(working, unsharp, mix * 0.7)
        else:
            # Negative clarity softens midtones
            mix = min(1.0, abs(clarity) / 100.0)
            soft = working.filter(ImageFilter.GaussianBlur(radius=4))
            working = Image.blend(working, soft, mix * 0.4)

    # 5. Film Grain
    if grain > 0:
        working = _apply_film_grain(working, grain)

    if has_alpha and alpha is not None:
        working.putalpha(alpha)
    return working


def _apply_film_grain(img: Image.Image, grain_level: int) -> Image.Image:
    """Generate subtle monochromatic film grain overlaid on image.

    Args:
        img: RGB Pillow Image.
        grain_level: Integer grain intensity (0 .. 100).

    Returns:
        Image with film grain texture blended.
    """
    w, h = img.size
    strength = (grain_level / 100.0) * 45.0  # max noise amplitude

    # Generate pseudo-random noise buffer for speed
    rng = random.Random(42)  # consistent seed per pass
    noise_data = bytes(
        int(clamp(128 + (rng.random() - 0.5) * strength * 2, 0, 255))
        for _ in range(w * h)
    )
    noise_img = Image.frombytes('L', (w, h), noise_data).convert('RGB')
    # Blend noise with soft light / overlay approximation
    return Image.blend(img, noise_img, (grain_level / 100.0) * 0.28)


# ── Full Pipeline ─────────────────────────────────────────────────────────────

def apply_all_poster_filters(img: Image.Image, filter_settings: Mapping[str, Any] | None) -> Image.Image:
    """Run full Color, Light, and Details processing pipeline on an image.

    Args:
        img: Input Pillow Image (RGB or RGBA mode).
        filter_settings: Dictionary containing optional 'color', 'light',
            and 'details' sub-dictionaries.

    Returns:
        Fully processed Pillow Image.
    """
    if not filter_settings:
        return img
    normalized = normalize_filter_settings(filter_settings)

    res = apply_color_filters(img, normalized['color'])
    res = apply_light_filters(res, normalized['light'])
    res = apply_detail_filters(res, normalized['details'])
    return res
