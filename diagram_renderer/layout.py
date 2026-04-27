from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from .parser import DiagramModel, Node
from .style import (
    CANVAS_WIDTH, MARGIN_X, MARGIN_Y,
    MIN_BOX_W, MIN_BOX_H, V_GAP, H_GAP, SECTION_GAP,
    BULLET_LINE_H, BULLET_INDENT,
    NODE_STYLES,
    NAVY, TEAL, GOLD, GREEN, SAND, SKY, MINT, ROSE, RED, BLUE_FILL, GRAY,
    INK, MUTED,
)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Box:
    x1: int
    y1: int
    x2: int
    y2: int
    text: str
    fill: str
    outline: str
    bullets: list[str] = field(default_factory=list)
    is_title: bool = False


@dataclass
class Arrow:
    start: tuple[int, int]
    end: tuple[int, int]
    color: str = NAVY


@dataclass
class Label:
    x: int
    y: int
    text: str
    color: str = NAVY
    bold: bool = False


@dataclass
class Line:
    start: tuple[int, int]
    end: tuple[int, int]
    color: str = NAVY
    width: int = 6


@dataclass
class Layout:
    width: int
    height: int
    boxes: list[Box]
    arrows: list[Arrow]
    title: str | None = None
    labels: list[Label] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)


# ── Height estimation ─────────────────────────────────────────────────────────

_WRAP_CHARS = 28   # approx chars per line for normal box width
_LINE_H     = 36   # px per wrapped text line

def _estimate_box_height(text: str, bullets: list[str], wrap: int = _WRAP_CHARS) -> int:
    text_lines = max(1, len(textwrap.wrap(text, width=wrap, break_long_words=False)))
    h = max(MIN_BOX_H, text_lines * _LINE_H + 24)
    if bullets:
        for b in bullets:
            h += BULLET_LINE_H * max(1, len(textwrap.wrap(b, width=wrap, break_long_words=False)))
        h += 30  # extra padding below bullets
    return h


# ── Layout functions ──────────────────────────────────────────────────────────

def layout_vertical_flow(model: DiagramModel) -> Layout:
    boxes: list[Box] = []
    arrows: list[Arrow] = []

    center_x = CANVAS_WIDTH // 2
    box_w = min(560, CANVAS_WIDTH - 2 * MARGIN_X)
    x1 = center_x - box_w // 2
    x2 = center_x + box_w // 2

    y = MARGIN_Y

    for i, node in enumerate(model.nodes):
        fill, outline = NODE_STYLES[i % len(NODE_STYLES)]
        h = _estimate_box_height(node.text, node.bullets)
        box = Box(x1=x1, y1=y, x2=x2, y2=y + h,
                  text=node.text, fill=fill, outline=outline,
                  bullets=node.bullets)
        boxes.append(box)

        # Side note branch (+--> style)
        if node.note:
            note_x1 = x2 + H_GAP
            note_x2 = note_x1 + 360
            note_h = _estimate_box_height(node.note, [])
            note_mid_y = y + h // 2
            note_y1 = note_mid_y - note_h // 2
            note_y2 = note_y1 + note_h
            note_box = Box(x1=note_x1, y1=note_y1, x2=note_x2, y2=note_y2,
                           text=node.note, fill="#F7F7F4", outline=GRAY)
            boxes.append(note_box)
            mid_y = y + h // 2
            arrows.append(Arrow(start=(x2, mid_y), end=(note_x1, mid_y), color=TEAL))

        if i < len(model.nodes) - 1:
            next_h = _estimate_box_height(model.nodes[i + 1].text, model.nodes[i + 1].bullets)
            arrows.append(Arrow(
                start=(center_x, y + h),
                end=(center_x, y + h + V_GAP),
                color=NAVY,
            ))

        y += h + V_GAP

    total_height = y + MARGIN_Y
    return Layout(
        width=CANVAS_WIDTH,
        height=total_height,
        boxes=boxes,
        arrows=arrows,
        title=model.title,
    )


def layout_two_column_flow(model: DiagramModel) -> Layout:
    boxes: list[Box] = []
    arrows: list[Arrow] = []
    labels: list[Label] = []
    lines: list[Line] = []

    left_nodes, right_nodes = model.columns[0], model.columns[1]
    n_rows = max(len(left_nodes), len(right_nodes))

    col_w = (CANVAS_WIDTH - 2 * MARGIN_X - H_GAP) // 2
    left_x1 = MARGIN_X
    left_x2 = MARGIN_X + col_w
    right_x1 = CANVAS_WIDTH - MARGIN_X - col_w
    right_x2 = CANVAS_WIDTH - MARGIN_X

    # Column headers
    col_titles = []
    if model.title and "/" in model.title:
        col_titles = [t.strip() for t in model.title.split("/", 1)]
    elif model.title:
        col_titles = [model.title, ""]

    header_y = MARGIN_Y
    label_h = 60
    if col_titles:
        labels.append(Label(x=left_x1 + 20, y=header_y, text=col_titles[0], color=NAVY, bold=True))
        if len(col_titles) > 1:
            labels.append(Label(x=right_x1 + 20, y=header_y, text=col_titles[1], color=TEAL, bold=True))
        header_y += label_h

    # Divider line
    mid_x = CANVAS_WIDTH // 2
    lines.append(Line(start=(mid_x, MARGIN_Y), end=(mid_x, 0), color="#E6ECEF", width=1))

    y = header_y + 20
    left_colors = [(SKY, NAVY), (SAND, GOLD), (ROSE, RED)]
    right_colors = [(SKY, TEAL), (SAND, GOLD), (ROSE, RED)]

    row_heights: list[int] = []
    for i in range(n_rows):
        ln = left_nodes[i] if i < len(left_nodes) else Node(text="")
        rn = right_nodes[i] if i < len(right_nodes) else Node(text="")
        lh = _estimate_box_height(ln.text, [], wrap=24)
        rh = _estimate_box_height(rn.text, [], wrap=24)
        row_heights.append(max(lh, rh))

    for i in range(n_rows):
        ln = left_nodes[i] if i < len(left_nodes) else Node(text="")
        rn = right_nodes[i] if i < len(right_nodes) else Node(text="")
        h = row_heights[i]

        lfill, loutline = left_colors[i % len(left_colors)]
        rfill, routline = right_colors[i % len(right_colors)]

        if ln.text:
            boxes.append(Box(x1=left_x1, y1=y, x2=left_x2, y2=y + h,
                             text=ln.text, fill=lfill, outline=loutline))
        if rn.text:
            boxes.append(Box(x1=right_x1, y1=y, x2=right_x2, y2=y + h,
                             text=rn.text, fill=rfill, outline=routline))

        if i < n_rows - 1:
            next_y = y + h + V_GAP
            left_cx = (left_x1 + left_x2) // 2
            right_cx = (right_x1 + right_x2) // 2
            if i < len(left_nodes) - 1:
                arrows.append(Arrow(start=(left_cx, y + h), end=(left_cx, next_y), color=NAVY))
            if i < len(right_nodes) - 1:
                arrows.append(Arrow(start=(right_cx, y + h), end=(right_cx, next_y), color=TEAL))

        y += h + V_GAP

    # Fix divider line end
    for ln in lines:
        if ln.color == "#E6ECEF":
            ln.end = (mid_x, y + MARGIN_Y)

    total_height = y + MARGIN_Y
    return Layout(
        width=CANVAS_WIDTH,
        height=total_height,
        boxes=boxes,
        arrows=arrows,
        title=None,
        labels=labels,
        lines=lines,
    )


def layout_timeline(model: DiagramModel) -> Layout:
    boxes: list[Box] = []
    arrows: list[Arrow] = []
    labels: list[Label] = []
    lines: list[Line] = []

    n = len(model.nodes)
    if n == 0:
        return Layout(width=CANVAS_WIDTH, height=400, boxes=[], arrows=[], title=model.title)

    # Timeline baseline
    timeline_y = 280
    margin = MARGIN_X + 40
    usable_w = CANVAS_WIDTH - 2 * margin
    spacing = usable_w // max(n, 1)

    # Horizontal timeline line
    lines.append(Line(
        start=(margin, timeline_y),
        end=(margin + usable_w, timeline_y),
        color=NAVY,
        width=6,
    ))

    box_w = min(spacing - 20, 220)
    box_h = 120

    event_colors = [(SKY, NAVY), (SAND, GOLD), (ROSE, RED), (MINT, GREEN), (SKY, NAVY), (SAND, GOLD)]

    for i, node in enumerate(model.nodes):
        x = margin + i * spacing + spacing // 2
        fill, outline = event_colors[i % len(event_colors)]

        # Dot on timeline
        dot_r = 14
        boxes.append(Box(x1=x - dot_r, y1=timeline_y - dot_r,
                         x2=x + dot_r, y2=timeline_y + dot_r,
                         text="", fill=NAVY, outline=NAVY))

        # Time label above
        if node.note:
            labels.append(Label(x=x - 30, y=timeline_y - 70, text=node.note, color=INK))

        # Event box below
        bx1 = x - box_w // 2
        bx2 = x + box_w // 2
        by1 = timeline_y + 40
        by2 = by1 + box_h
        boxes.append(Box(x1=bx1, y1=by1, x2=bx2, y2=by2,
                         text=node.text, fill=fill, outline=outline))

    total_height = timeline_y + box_h + 2 * MARGIN_Y + 80
    return Layout(
        width=CANVAS_WIDTH,
        height=total_height,
        boxes=boxes,
        arrows=arrows,
        title=model.title,
        labels=labels,
        lines=lines,
    )


def layout_branch_from_root(model: DiagramModel) -> Layout:
    boxes: list[Box] = []
    arrows: list[Arrow] = []
    labels: list[Label] = []

    # Separate root from branches
    root_nodes = [n for n in model.nodes if n.level == 0]
    branch_nodes = [n for n in model.nodes if n.level == 1]

    root_text = root_nodes[0].text if root_nodes else "Root"
    root_w = 480
    root_h = _estimate_box_height(root_text, [])
    root_x1 = CANVAS_WIDTH // 2 - root_w // 2
    root_x2 = CANVAS_WIDTH // 2 + root_w // 2
    root_y1 = MARGIN_Y
    root_y2 = root_y1 + root_h

    boxes.append(Box(x1=root_x1, y1=root_y1, x2=root_x2, y2=root_y2,
                     text=root_text, fill=BLUE_FILL, outline=NAVY))

    n_branches = len(branch_nodes)
    if n_branches == 0:
        return Layout(width=CANVAS_WIDTH, height=400, boxes=boxes, arrows=arrows)

    branch_gap = H_GAP
    branch_y1 = root_y2 + 200  # enough space for diagonal arrows

    # Compute per-branch box sizes
    branch_w = min(460, (CANVAS_WIDTH - 2 * MARGIN_X - (n_branches - 1) * branch_gap) // n_branches)
    total_branches_w = n_branches * branch_w + (n_branches - 1) * branch_gap
    start_x = (CANVAS_WIDTH - total_branches_w) // 2

    branch_colors = [
        (SKY, NAVY),
        (SAND, GOLD),
        (MINT, GREEN),
        (ROSE, RED),
        (BLUE_FILL, NAVY),
    ]

    for i, node in enumerate(branch_nodes):
        fill, outline = branch_colors[i % len(branch_colors)]
        bh = _estimate_box_height(node.text, node.bullets, wrap=22)
        bx1 = start_x + i * (branch_w + branch_gap)
        bx2 = bx1 + branch_w
        by2 = branch_y1 + bh

        boxes.append(Box(x1=bx1, y1=branch_y1, x2=bx2, y2=by2,
                         text=node.text, fill=fill, outline=outline,
                         bullets=node.bullets))

        # Arrow from root bottom-center to branch top-center
        root_cx = CANVAS_WIDTH // 2
        branch_cx = (bx1 + bx2) // 2
        arrows.append(Arrow(
            start=(root_cx, root_y2),
            end=(branch_cx, branch_y1),
            color=outline,
        ))

    max_branch_h = max(
        _estimate_box_height(n.text, n.bullets, wrap=22) for n in branch_nodes
    )
    total_height = branch_y1 + max_branch_h + MARGIN_Y
    return Layout(
        width=CANVAS_WIDTH,
        height=total_height,
        boxes=boxes,
        arrows=arrows,
        title=model.title,
        labels=labels,
    )


# ── Public API ────────────────────────────────────────────────────────────────

_LAYOUT_MAP = {
    "vertical_flow":    layout_vertical_flow,
    "two_column_flow":  layout_two_column_flow,
    "timeline":         layout_timeline,
    "branch_from_root": layout_branch_from_root,
}


def build_layout(model: DiagramModel) -> Layout:
    fn = _LAYOUT_MAP.get(model.kind, layout_vertical_flow)
    return fn(model)
