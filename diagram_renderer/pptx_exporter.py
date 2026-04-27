from __future__ import annotations

"""
PPTX exporter using python-pptx native shapes.

Converts a DiagramModel → Layout → real PowerPoint shapes
(rounded rectangles, lines with arrow heads, text frames, bullets).
No PNG embedding — everything is editable vector shapes.
"""

from pathlib import Path
from typing import Callable

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt
from lxml import etree

from .parser import parse_ascii_diagram
from .layout import build_layout, Layout, Box, Arrow, Label, Line
from .style import BG, INK, NAVY, TEAL, MUTED, GOLD, GREEN, PPTX_COLORS, PPTX_TEXT

# ── Slide dimensions: 16:9 widescreen ────────────────────────────────────────
_SLIDE_W_EMU = 9144000   # 10 inches
_SLIDE_H_EMU = 5143500   # 5.625 inches
_PX_PER_INCH  = 96.0
_EMU_PER_INCH = 914400.0

# Source canvas is 1800 px wide. Map that to slide width.
_CANVAS_PX   = 1800

# Reference ratio: 1800px canvas fills 10" slide width (9144000 / 1800 ≈ 5080 EMU/px)
_REF_RATIO = _SLIDE_W_EMU / _CANVAS_PX


def _font_pt(nominal_pt: float, ratio: float) -> float:
    """Scale a font size (nominal = calibrated at _REF_RATIO) to the current ratio."""
    return max(5.0, nominal_pt * ratio / _REF_RATIO)


def _rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _scale(px: int | float, canvas_h_px: int) -> tuple[Callable, Callable]:
    """Return (x_emu, y_emu) converter functions for the given canvas."""
    # Fit canvas into slide preserving aspect ratio
    canvas_w_px = _CANVAS_PX
    scale_x = _SLIDE_W_EMU / canvas_w_px
    scale_y = _SLIDE_H_EMU / canvas_h_px
    ratio = min(scale_x, scale_y)
    offset_x = (_SLIDE_W_EMU - canvas_w_px * ratio) / 2
    offset_y = (_SLIDE_H_EMU - canvas_h_px * ratio) / 2
    return (lambda px_: int(px_ * ratio + offset_x),
            lambda py_: int(py_ * ratio + offset_y),
            ratio)


def _set_bg(slide, hex_color: str) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(hex_color)


def _add_rounded_rect(slide, left: int, top: int, width: int, height: int,
                      fill_hex: str, outline_hex: str,
                      radius_emu: int = 180000, line_width_pt: float = 0.5) -> object:
    from pptx.util import Emu as E
    shape = slide.shapes.add_shape(
        1,  # MSO_AUTO_SHAPE_TYPE.RECTANGLE
        E(left), E(top), E(width), E(height)
    )

    # Patch geometry to roundRect via lxml
    nsmap_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    sp_elem = shape._element
    spPr = sp_elem.find(f"{{{nsmap_a}}}spPr")
    if spPr is None:
        spPr = etree.SubElement(sp_elem, f"{{{nsmap_a}}}spPr")

    for old in spPr.findall(f"{{{nsmap_a}}}prstGeom"):
        spPr.remove(old)
    prstGeom_el = etree.SubElement(spPr, f"{{{nsmap_a}}}prstGeom")
    prstGeom_el.set("prst", "roundRect")
    avLst = etree.SubElement(prstGeom_el, f"{{{nsmap_a}}}avLst")
    gd = etree.SubElement(avLst, f"{{{nsmap_a}}}gd")
    gd.set("name", "adj")
    shorter = min(width, height)
    adj_val = max(1000, min(50000, int(radius_emu / max(shorter, 1) * 100000)))
    gd.set("fmla", f"val {adj_val}")

    # Fill
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill_hex)
    # Line
    shape.line.color.rgb = _rgb(outline_hex)
    shape.line.width = Pt(line_width_pt)
    return shape


def _set_text(shape, text: str, font_size_pt: float = 10, bold: bool = False,
              color_hex: str = INK, wrap: bool = True, align=PP_ALIGN.CENTER) -> None:
    tf = shape.text_frame
    tf.word_wrap = wrap
    tf.auto_size = None
    from pptx.util import Pt as P
    from pptx.enum.text import MSO_ANCHOR
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    p.clear()
    run = p.add_run()
    run.text = text
    run.font.size = P(font_size_pt)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color_hex)


def _add_box_with_text(slide, box: Box, ratio: float,
                       x_fn, y_fn, fill_hex: str) -> None:
    left   = x_fn(box.x1)
    top    = y_fn(box.y1)
    width  = int((box.x2 - box.x1) * ratio)
    height = int((box.y2 - box.y1) * ratio)

    # Outline matches fill for flat, borderless look
    outline_hex = fill_hex

    outline_hex = box.outline

    if not box.bullets:
        shape = _add_rounded_rect(slide, left, top, width, height,
                                  fill_hex, outline_hex)
        _set_text(shape, box.text, font_size_pt=_font_pt(10, ratio), color_hex=PPTX_TEXT)
    else:
        # Box with title + bullet list
        shape = _add_rounded_rect(slide, left, top, width, height,
                                  fill_hex, outline_hex)
        tf = shape.text_frame
        tf.word_wrap = True
        from pptx.util import Pt as P
        from pptx.enum.text import MSO_ANCHOR
        tf.vertical_anchor = MSO_ANCHOR.TOP

        # Title paragraph
        p0 = tf.paragraphs[0]
        p0.alignment = PP_ALIGN.LEFT
        r0 = p0.add_run()
        r0.text = box.text
        r0.font.size = P(_font_pt(10, ratio))
        r0.font.bold = True
        r0.font.color.rgb = _rgb(PPTX_TEXT)

        # Bullet paragraphs
        for bullet in box.bullets:
            para = tf.add_paragraph()
            para.alignment = PP_ALIGN.LEFT
            para.space_before = P(max(1.0, _font_pt(3, ratio)))
            run = para.add_run()
            run.text = f"  • {bullet}"
            run.font.size = P(_font_pt(9, ratio))
            run.font.color.rgb = _rgb(PPTX_TEXT)


def _add_arrow(slide, arr: Arrow, x_fn, y_fn, ratio: float) -> None:
    from pptx.util import Emu as E, Pt as P
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    x1, y1 = x_fn(arr.start[0]), y_fn(arr.start[1])
    x2, y2 = x_fn(arr.end[0]),   y_fn(arr.end[1])

    # Use a connector shape (straight)
    connector = slide.shapes.add_connector(
        1,  # MSO_CONNECTOR.STRAIGHT
        E(x1), E(y1), E(x2), E(y2)
    )
    connector.line.color.rgb = _rgb(arr.color)
    connector.line.width = P(1.5)

    # Add arrowhead at end via XML
    nsmap_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    spPr = connector._element.find(f"{{{nsmap_a}}}spPr")
    ln = spPr.find(f"{{{nsmap_a}}}ln") if spPr is not None else None
    if ln is None and spPr is not None:
        ln = etree.SubElement(spPr, f"{{{nsmap_a}}}ln")

    # Try connector line element directly
    cxn_elem = connector._element
    lnEls = cxn_elem.findall(f".//{{{nsmap_a}}}ln")
    for lnEl in lnEls:
        tailEnd = etree.SubElement(lnEl, f"{{{nsmap_a}}}tailEnd")
        tailEnd.set("type", "triangle")
        tailEnd.set("w", "med")
        tailEnd.set("len", "med")
        break


def _add_label(slide, lbl: Label, x_fn, y_fn, ratio: float) -> None:
    from pptx.util import Emu as E, Pt as P
    w = int(400 * ratio)
    h = int(60 * ratio)
    txBox = slide.shapes.add_textbox(E(x_fn(lbl.x)), E(y_fn(lbl.y)), E(w), E(h))
    tf = txBox.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = lbl.text
    run.font.size = P(_font_pt(14 if lbl.bold else 11, ratio))
    run.font.bold = lbl.bold
    run.font.color.rgb = _rgb(lbl.color)


def _add_line(slide, ln: Line, x_fn, y_fn, ratio: float) -> None:
    from pptx.util import Emu as E, Pt as P
    x1, y1 = x_fn(ln.start[0]), y_fn(ln.start[1])
    x2, y2 = x_fn(ln.end[0]),   y_fn(ln.end[1])
    connector = slide.shapes.add_connector(1, E(x1), E(y1), E(x2), E(y2))
    connector.line.color.rgb = _rgb(ln.color)
    connector.line.width = P(max(0.5, ln.width * 0.5))


# ── Public API ────────────────────────────────────────────────────────────────

def export_layout_to_pptx(layout: Layout, output_path: Path) -> Path:
    """Render a pre-built Layout as native PowerPoint shapes."""
    prs = Presentation()
    prs.slide_width  = Emu(_SLIDE_W_EMU)
    prs.slide_height = Emu(_SLIDE_H_EMU)

    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)
    _set_bg(slide, BG)

    x_fn, y_fn, ratio = _scale(0, layout.height)

    for ln in layout.lines:
        _add_line(slide, ln, x_fn, y_fn, ratio)

    for arr in layout.arrows:
        _add_arrow(slide, arr, x_fn, y_fn, ratio)

    color_idx = 0
    for box in layout.boxes:
        if not box.text and not box.bullets:
            fill = PPTX_COLORS[0]
        else:
            fill = box.fill if box.fill.startswith("#") else PPTX_COLORS[color_idx % len(PPTX_COLORS)]
            color_idx += 1
        _add_box_with_text(slide, box, ratio, x_fn, y_fn, fill)

    for lbl in layout.labels:
        _add_label(slide, lbl, x_fn, y_fn, ratio)

    if layout.title:
        from pptx.util import Emu as E, Pt as P
        tx = slide.shapes.add_textbox(
            E(x_fn(120)), E(y_fn(30)),
            E(int(1560 * ratio)), E(int(70 * ratio))
        )
        tf = tx.text_frame
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = layout.title
        run.font.size = P(_font_pt(22, ratio))
        run.font.bold = True
        run.font.color.rgb = _rgb(NAVY)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    return output_path


def render_ascii_to_pptx(text: str, output_path: Path) -> Path:
    """Render ASCII diagram as native PowerPoint shapes."""
    model  = parse_ascii_diagram(text)
    layout = build_layout(model)

    prs = Presentation()
    prs.slide_width  = Emu(_SLIDE_W_EMU)
    prs.slide_height = Emu(_SLIDE_H_EMU)

    blank_layout = prs.slide_layouts[6]   # blank
    slide = prs.slides.add_slide(blank_layout)
    _set_bg(slide, BG)

    x_fn, y_fn, ratio = _scale(0, layout.height)

    # Draw order: lines → arrows → boxes → labels
    for ln in layout.lines:
        _add_line(slide, ln, x_fn, y_fn, ratio)

    for arr in layout.arrows:
        _add_arrow(slide, arr, x_fn, y_fn, ratio)

    color_idx = 0
    for box in layout.boxes:
        # Timeline dot boxes (text empty, square aspect) use first color
        if not box.text and not box.bullets:
            fill = PPTX_COLORS[0]
        else:
            fill = PPTX_COLORS[color_idx % len(PPTX_COLORS)]
            color_idx += 1
        _add_box_with_text(slide, box, ratio, x_fn, y_fn, fill)

    for lbl in layout.labels:
        _add_label(slide, lbl, x_fn, y_fn, ratio)

    # Title text box
    if layout.title:
        from pptx.util import Emu as E, Pt as P
        tx = slide.shapes.add_textbox(
            E(x_fn(120)), E(y_fn(30)),
            E(int(1560 * ratio)), E(int(70 * ratio))
        )
        tf = tx.text_frame
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = layout.title
        run.font.size = P(_font_pt(22, ratio))
        run.font.bold = True
        run.font.color.rgb = _rgb(NAVY)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    return output_path
