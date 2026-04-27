from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from .font import load_font
from .layout import Box, Arrow, Label, Line, Layout, build_layout
from .parser import parse_ascii_diagram
from .style import (
    BG, INK, NAVY, TEAL, MUTED,
    BOX_RADIUS, LINE_WIDTH, ARROW_HEAD, ARROW_LINE_WIDTH,
    BULLET_INDENT, BULLET_LINE_H,
    SECTION_GAP,
)

# Pre-load font sizes (lazy enough for module import)
_TITLE_FONT  = load_font(44, bold=True)
_SECTION_FONT = load_font(32, bold=True)
_BODY_FONT   = load_font(26)
_SMALL_FONT  = load_font(22)


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [""]


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font,
    fill: str = INK,
    wrap_width: int = 28,
) -> None:
    lines = _wrap(text, wrap_width)
    spacing = 8
    bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    total_h = sum(b[3] - b[1] for b in bboxes) + spacing * max(0, len(lines) - 1)
    top = box[1] + (box[3] - box[1] - total_h) / 2
    for line, bbox in zip(lines, bboxes):
        line_w = bbox[2] - bbox[0]
        x = box[0] + (box[2] - box[0] - line_w) / 2
        draw.text((x, top), line, font=font, fill=fill)
        top += (bbox[3] - bbox[1]) + spacing


def _draw_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill: str = INK) -> None:
    draw.text((x, y), text, font=font, fill=fill)


def _rounded_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str,
    outline: str = NAVY,
    radius: int = BOX_RADIUS,
    width: int = LINE_WIDTH,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    fill: str = NAVY,
    width: int = ARROW_LINE_WIDTH,
    head: int = ARROW_HEAD,
) -> None:
    draw.line([start, end], fill=fill, width=width)
    sx, sy = start
    ex, ey = end
    if sx == ex:  # vertical
        if ey >= sy:
            pts = [(ex, ey), (ex - head, ey - head), (ex + head, ey - head)]
        else:
            pts = [(ex, ey), (ex - head, ey + head), (ex + head, ey + head)]
    elif sy == ey:  # horizontal
        if ex >= sx:
            pts = [(ex, ey), (ex - head, ey - head), (ex - head, ey + head)]
        else:
            pts = [(ex, ey), (ex + head, ey - head), (ex + head, ey + head)]
    else:
        # diagonal – point toward end
        import math
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length == 0:
            return
        udx, udy = dx / length, dy / length
        perp_x, perp_y = -udy, udx
        pts = [
            (ex, ey),
            (ex - head * udx + head * 0.5 * perp_x, ey - head * udy + head * 0.5 * perp_y),
            (ex - head * udx - head * 0.5 * perp_x, ey - head * udy - head * 0.5 * perp_y),
        ]
    draw.polygon(pts, fill=fill, outline=fill)


def _draw_box(draw: ImageDraw.ImageDraw, box: Box) -> None:
    """Draw a single Box including bullets if present."""
    if not box.text and not box.bullets and box.fill == NAVY:
        # Timeline dot: filled circle/ellipse
        draw.ellipse((box.x1, box.y1, box.x2, box.y2), fill=box.fill, outline=box.outline)
        return

    _rounded_box(draw, (box.x1, box.y1, box.x2, box.y2), fill=box.fill, outline=box.outline)

    if not box.bullets:
        _draw_centered_text(draw, (box.x1, box.y1, box.x2, box.y2), box.text, _BODY_FONT, fill=INK, wrap_width=28)
    else:
        # Title text at top of box
        _draw_label(draw, box.x1 + 30, box.y1 + 24, box.text, _SECTION_FONT, box.outline)
        y = box.y1 + 24 + 44  # below title
        for bullet in box.bullets:
            _draw_label(draw, box.x1 + BULLET_INDENT - 6, y, "•", _SECTION_FONT, INK)
            lines = _wrap(bullet, 24)
            for idx, line in enumerate(lines):
                _draw_label(draw, box.x1 + BULLET_INDENT + 20, y + idx * 32, line, _SMALL_FONT, INK)
            y += BULLET_LINE_H * max(1, len(lines)) + 8


# ── Canvas and render ─────────────────────────────────────────────────────────

def _make_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    return image, draw


def render_layout(layout: Layout) -> Image.Image:
    image, draw = _make_canvas(layout.width, layout.height)

    # Draw divider / decoration lines first
    for ln in layout.lines:
        draw.line([ln.start, ln.end], fill=ln.color, width=ln.width)

    # Title
    if layout.title:
        draw.text((120, 60), layout.title, font=_TITLE_FONT, fill=NAVY)

    # Labels (column headers, time labels, etc.)
    for lbl in layout.labels:
        font = _SECTION_FONT if lbl.bold else _BODY_FONT
        draw.text((lbl.x, lbl.y), lbl.text, font=font, fill=lbl.color)

    # Boxes
    for box in layout.boxes:
        _draw_box(draw, box)

    # Arrows
    for arr in layout.arrows:
        _arrow(draw, arr.start, arr.end, fill=arr.color)

    return image


# ── Public API ────────────────────────────────────────────────────────────────

def render_ascii_to_png(text: str, output_path: Path) -> Path:
    """Parse ASCII diagram text and save a PNG to output_path."""
    model = parse_ascii_diagram(text)
    layout = build_layout(model)
    image = render_layout(layout)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output_path))
    return output_path
