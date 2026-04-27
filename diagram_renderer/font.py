from __future__ import annotations

from PIL import ImageFont

# Preferred font candidates ordered by preference.
# Korean-capable fonts are listed first so they work on Windows with Malgun Gothic.
_REGULAR_CANDIDATES = [
    "malgun.ttf",
    "DejaVuSans.ttf",
    "arial.ttf",
    "Arial Unicode.ttf",
]

_BOLD_CANDIDATES = [
    "malgunbd.ttf",
    "DejaVuSans-Bold.ttf",
    "arialbd.ttf",
    "Arial Unicode.ttf",
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font of the given size, falling back gracefully."""
    candidates = _BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES
    for name in candidates:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    # Pillow built-in default (no size control, but always available)
    return ImageFont.load_default()
