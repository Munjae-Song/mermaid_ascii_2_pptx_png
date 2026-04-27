"""Parse Mermaid flowchart / graph diagrams and build a Layout.

Supported:
  flowchart TD / LR / BT / RL
  graph     TD / LR / BT / RL

Node shapes:
  A[rect]  A(round)  A{diamond}  A([stadium])  A[[subprocess]]

Edge forms:
  A --> B           plain arrow
  A --- B           plain line
  A -.-> B          dotted arrow
  A ==> B           thick arrow
  A -->|label| B    pipe-labelled arrow
  A -- label --> B  inline-labelled arrow

Chains (A --> B --> C) are supported.
subgraph / end / style / classDef lines are silently skipped.
Cycles are handled by capping layer depth.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .layout import Arrow, Box, Label, Layout
from .style import (
    CANVAS_WIDTH,
    H_GAP,
    MARGIN_X,
    MARGIN_Y,
    MIN_BOX_H,
    MUTED,
    NAVY,
    PPTX_COLORS,
    V_GAP,
)

# ── Regex patterns ────────────────────────────────────────────────────────────

# First line: `flowchart LR` or `graph TD`
_DIRECTION_RE = re.compile(r"^(?:flowchart|graph)\s+(\w+)", re.IGNORECASE)

# Node with explicit shape: A[text], A(text), A{text}, A([text]), A[[text]]
_NODE_DEF_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_-]*)\s*"
    r"(?:"
    r"\(\[([^\]]*)\]\)"     # ([...]) — stadium / round-rectangle
    r"|\[\[([^\]]*)\]\]"    # [[...]] — subprocess (double-bracket)
    r"|\{([^}]*)\}"         # {...}   — diamond
    r"|\(([^)]*)\)"         # (...)   — rounded rectangle
    r"|\[([^\]]*)\]"        # [...]   — plain rectangle
    r")"
)

# ── Edge patterns (applied AFTER stripping shape labels) ──────────────────────

# Pipe-labelled:  A -->|label| B  or  A -.->|label| B
_PIPE_EDGE_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_-]*)\b\s*"
    r"(?:--+\.?-*>|==+>|\.->)\s*"
    r"\|([^|]*)\|\s*"
    r"\b([A-Za-z_][A-Za-z0-9_-]*)\b"
)

# Inline-labelled: A -- label --> B
_INLINE_EDGE_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_-]*)\b\s*"
    r"--([^->\n][^>\n]*?)-->\s*"
    r"\b([A-Za-z_][A-Za-z0-9_-]*)\b"
)

# Plain (no label):  A --> B  /  A --- B  /  A -.-> B  /  A ==> B
_PLAIN_EDGE_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_-]*)\b\s*"
    r"(?:--+\.?-*>?|==+>?|\.->)\s*"
    r"\b([A-Za-z_][A-Za-z0-9_-]*)\b"
)

# Lines to skip wholesale
_SKIP_RE = re.compile(
    r"^\s*(?:subgraph|end|classDef|class\s|style\s|click\s|linkStyle\s|%%)",
    re.IGNORECASE,
)

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class _Node:
    id: str
    label: str


@dataclass
class _Edge:
    src: str
    dst: str
    label: str = ""


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse(text: str) -> tuple[str, dict[str, str], list[_Edge], dict[str, int]]:
    """Return (direction, {id: label}, edges, {id: appearance_order})."""
    direction = "TD"
    nodes: dict[str, str] = {}      # id → display label
    edges: list[_Edge] = []
    appearance: dict[str, int] = {} # id → first-seen order
    _order = 0

    def _register(nid: str, label: str | None = None) -> None:
        nonlocal _order
        if nid not in appearance:
            appearance[nid] = _order
            _order += 1
        if label and nid not in nodes:
            nodes[nid] = label

    for raw in text.replace(";", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _SKIP_RE.match(line):
            continue

        # Direction header
        m = _DIRECTION_RE.match(line)
        if m:
            direction = m.group(1).upper()
            continue

        # Collect explicit node labels
        for m in _NODE_DEF_RE.finditer(line):
            nid = m.group(1)
            lbl = next((g for g in m.groups()[1:] if g is not None), nid)
            _register(nid, lbl.strip())

        # Strip shape brackets so edge regexes see bare IDs
        stripped = _NODE_DEF_RE.sub(r"\1", line)

        # Pipe-labelled edges (highest priority)
        found_pipe: set[tuple[str, str]] = set()
        for m in _PIPE_EDGE_RE.finditer(stripped):
            src, lbl, dst = m.group(1), m.group(2).strip(), m.group(3)
            if src != dst:
                edges.append(_Edge(src=src, dst=dst, label=lbl))
                found_pipe.add((src, dst))
                _register(src)
                _register(dst)

        # Inline-labelled edges
        found_inline: set[tuple[str, str]] = set()
        for m in _INLINE_EDGE_RE.finditer(stripped):
            src, lbl, dst = m.group(1), m.group(2).strip(), m.group(3)
            if src != dst and (src, dst) not in found_pipe:
                edges.append(_Edge(src=src, dst=dst, label=lbl))
                found_inline.add((src, dst))
                _register(src)
                _register(dst)

        # Plain edges (skip already captured)
        for m in _PLAIN_EDGE_RE.finditer(stripped):
            src, dst = m.group(1), m.group(2)
            if src != dst and (src, dst) not in found_pipe and (src, dst) not in found_inline:
                edges.append(_Edge(src=src, dst=dst, label=""))
                _register(src)
                _register(dst)

    return direction, nodes, edges, appearance


# ── Layer assignment ──────────────────────────────────────────────────────────

def _assign_layers(
    node_ids: set[str],
    edges: list[_Edge],
) -> dict[str, int]:
    """Longest-path layer assignment; handles cycles by capping iterations."""
    layer: dict[str, int] = {n: 0 for n in node_ids}
    changed = True
    max_iter = len(node_ids) + 1
    for _ in range(max_iter):
        if not changed:
            break
        changed = False
        for e in edges:
            if e.src in layer and e.dst in layer:
                if layer[e.dst] <= layer[e.src]:
                    layer[e.dst] = layer[e.src] + 1
                    changed = True
    return layer


# ── Box sizing ────────────────────────────────────────────────────────────────

_BOX_H   = MIN_BOX_H          # 90 px (tall enough for single-line labels)
_TD_VGAP = V_GAP + 20          # 80 px — breathing room between rows
_LR_HGAP = H_GAP + 120         # 200 px — wide enough for labels on connectors


def _box_w(n_in_layer: int, available: int) -> int:
    """Calculate box width so N boxes fit in *available* px with H_GAP between."""
    w = (available - (n_in_layer - 1) * H_GAP) // n_in_layer
    return max(240, min(400, w))


# ── Layout builders ───────────────────────────────────────────────────────────

def _build_td(
    nodes: dict[str, str],
    edges: list[_Edge],
    layer: dict[str, int],
    appearance: dict[str, int],
    reverse: bool = False,
) -> Layout:
    """Top-down (or bottom-up) layered layout."""
    by_layer: dict[int, list[str]] = defaultdict(list)
    for nid, lyr in layer.items():
        by_layer[lyr].append(nid)

    # Sort within each layer by appearance order
    for lyr_nodes in by_layer.values():
        lyr_nodes.sort(key=lambda n: appearance.get(n, 9999))

    n_layers = max(by_layer.keys(), default=0) + 1
    available_w = CANVAS_WIDTH - 2 * MARGIN_X

    # Compute per-layer box widths
    bw: dict[int, int] = {}
    for lyr_idx, nids in by_layer.items():
        bw[lyr_idx] = _box_w(len(nids), available_w)

    canvas_h = MARGIN_Y * 2 + n_layers * _BOX_H + (n_layers - 1) * _TD_VGAP

    # Map node → pixel rect
    pos: dict[str, tuple[int, int, int, int]] = {}
    for lyr_idx, nids in by_layer.items():
        n = len(nids)
        total_w = n * bw[lyr_idx] + (n - 1) * H_GAP
        start_x = MARGIN_X + (available_w - total_w) // 2
        display_lyr = (n_layers - 1 - lyr_idx) if reverse else lyr_idx
        y1 = MARGIN_Y + display_lyr * (_BOX_H + _TD_VGAP)
        y2 = y1 + _BOX_H
        for i, nid in enumerate(nids):
            x1 = start_x + i * (bw[lyr_idx] + H_GAP)
            x2 = x1 + bw[lyr_idx]
            pos[nid] = (x1, y1, x2, y2)

    boxes: list[Box] = []
    color_idx = 0
    for lyr_idx in sorted(by_layer):
        for nid in by_layer[lyr_idx]:
            if nid not in pos:
                continue
            x1, y1, x2, y2 = pos[nid]
            label = nodes.get(nid, nid)
            fill = PPTX_COLORS[color_idx % len(PPTX_COLORS)]
            color_idx += 1
            boxes.append(Box(x1=x1, y1=y1, x2=x2, y2=y2,
                             text=label, fill=fill, outline=fill))

    arrows, labels = _make_arrows_td(edges, pos)

    return Layout(
        width=CANVAS_WIDTH,
        height=canvas_h,
        boxes=boxes,
        arrows=arrows,
        labels=labels,
    )


def _build_lr(
    nodes: dict[str, str],
    edges: list[_Edge],
    layer: dict[str, int],
    appearance: dict[str, int],
    reverse: bool = False,
) -> Layout:
    """Left-right (or right-left) layered layout."""
    by_layer: dict[int, list[str]] = defaultdict(list)
    for nid, lyr in layer.items():
        by_layer[lyr].append(nid)

    for lyr_nodes in by_layer.values():
        lyr_nodes.sort(key=lambda n: appearance.get(n, 9999))

    n_layers = max(by_layer.keys(), default=0) + 1
    max_in_layer = max(len(v) for v in by_layer.values())

    _LR_BOX_W = 300
    _LR_BOX_H = 80
    _LR_VGAP  = 50

    canvas_w = MARGIN_X * 2 + n_layers * _LR_BOX_W + (n_layers - 1) * _LR_HGAP
    canvas_w = max(CANVAS_WIDTH, canvas_w)
    canvas_h = MARGIN_Y * 2 + max_in_layer * _LR_BOX_H + (max_in_layer - 1) * _LR_VGAP
    canvas_h = max(600, canvas_h)

    pos: dict[str, tuple[int, int, int, int]] = {}
    for lyr_idx, nids in by_layer.items():
        n = len(nids)
        total_h = n * _LR_BOX_H + (n - 1) * _LR_VGAP
        start_y = MARGIN_Y + (canvas_h - 2 * MARGIN_Y - total_h) // 2
        display_lyr = (n_layers - 1 - lyr_idx) if reverse else lyr_idx
        x1 = MARGIN_X + display_lyr * (_LR_BOX_W + _LR_HGAP)
        x2 = x1 + _LR_BOX_W
        for i, nid in enumerate(nids):
            y1 = start_y + i * (_LR_BOX_H + _LR_VGAP)
            y2 = y1 + _LR_BOX_H
            pos[nid] = (x1, y1, x2, y2)

    boxes: list[Box] = []
    color_idx = 0
    for lyr_idx in sorted(by_layer):
        for nid in by_layer[lyr_idx]:
            if nid not in pos:
                continue
            x1, y1, x2, y2 = pos[nid]
            label = nodes.get(nid, nid)
            fill = PPTX_COLORS[color_idx % len(PPTX_COLORS)]
            color_idx += 1
            boxes.append(Box(x1=x1, y1=y1, x2=x2, y2=y2,
                             text=label, fill=fill, outline=fill))

    arrows, labels = _make_arrows_lr(edges, pos)

    return Layout(
        width=canvas_w,
        height=canvas_h,
        boxes=boxes,
        arrows=arrows,
        labels=labels,
    )


def _make_arrows_td(
    edges: list[_Edge],
    pos: dict[str, tuple[int, int, int, int]],
) -> tuple[list[Arrow], list[Label]]:
    arrows: list[Arrow] = []
    labels: list[Label] = []
    seen: set[tuple[str, str]] = set()
    for e in edges:
        key = (e.src, e.dst)
        if key in seen or e.src not in pos or e.dst not in pos:
            continue
        seen.add(key)
        sx1, sy1, sx2, sy2 = pos[e.src]
        dx1, dy1, dx2, dy2 = pos[e.dst]
        start = ((sx1 + sx2) // 2, sy2)
        end   = ((dx1 + dx2) // 2, dy1)
        arrows.append(Arrow(start=start, end=end, color=NAVY))
        if e.label:
            mx = (start[0] + end[0]) // 2
            my = (start[1] + end[1]) // 2
            labels.append(Label(x=mx, y=my, text=e.label, color=MUTED, bold=False))
    return arrows, labels


def _make_arrows_lr(
    edges: list[_Edge],
    pos: dict[str, tuple[int, int, int, int]],
) -> tuple[list[Arrow], list[Label]]:
    arrows: list[Arrow] = []
    labels: list[Label] = []
    seen: set[tuple[str, str]] = set()
    for e in edges:
        key = (e.src, e.dst)
        if key in seen or e.src not in pos or e.dst not in pos:
            continue
        seen.add(key)
        sx1, sy1, sx2, sy2 = pos[e.src]
        dx1, dy1, dx2, dy2 = pos[e.dst]
        start = (sx2, (sy1 + sy2) // 2)
        end   = (dx1, (dy1 + dy2) // 2)
        arrows.append(Arrow(start=start, end=end, color=NAVY))
        if e.label:
            mx = (start[0] + end[0]) // 2
            my = (start[1] + end[1]) // 2
            labels.append(Label(x=mx, y=my, text=e.label, color=MUTED, bold=False))
    return arrows, labels


# ── Public API ────────────────────────────────────────────────────────────────

_NATIVE_RE = re.compile(r"^(?:flowchart|graph)\s+\w+", re.IGNORECASE | re.MULTILINE)


def is_native_mermaid(text: str) -> bool:
    """Return True if this is a flowchart/graph that can be rendered as native shapes."""
    # Strip optional ```mermaid fence
    stripped = re.sub(r"^```[\w]*\s*$", "", text, flags=re.MULTILINE).strip()
    return bool(_NATIVE_RE.search(stripped))


def mermaid_to_layout(text: str) -> Layout:
    """Parse Mermaid flowchart / graph text and return a Layout for PPTX export."""
    # Strip optional fence
    diagram = re.sub(r"^```[\w]*\s*$", "", text, flags=re.MULTILINE).strip()

    direction, nodes, edges, appearance = _parse(diagram)

    all_ids: set[str] = set(nodes.keys())
    for e in edges:
        all_ids.add(e.src)
        all_ids.add(e.dst)

    # Ensure every referenced node has a label
    for nid in all_ids:
        if nid not in nodes:
            nodes[nid] = nid

    if not all_ids:
        raise ValueError("No nodes found in Mermaid diagram.")

    layer = _assign_layers(all_ids, edges)

    if direction in ("LR", "RL"):
        return _build_lr(nodes, edges, layer, appearance, reverse=(direction == "RL"))
    else:  # TD, TB, BT
        return _build_td(nodes, edges, layer, appearance, reverse=(direction == "BT"))
