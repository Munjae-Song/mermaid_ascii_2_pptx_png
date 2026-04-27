from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class Node:
    text: str
    level: int = 0
    bullets: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class DiagramModel:
    kind: str           # vertical_flow | two_column_flow | timeline | branch_from_root
    title: str | None
    nodes: list[Node]
    columns: list[list[Node]] = field(default_factory=list)


# ── Detection helpers ─────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"^\s*(\d{1,2}:\d{2}|Later|Soon|After)\s+\S", re.IGNORECASE)
_BRANCH_RE = re.compile(r"\+--+>")
_UNDERLINE_RE = re.compile(r"^-{3,}")


def _is_timeline(lines: list[str]) -> bool:
    hits = sum(1 for line in lines if _TIME_RE.match(line))
    return hits >= 3


def _is_branch_from_root(lines: list[str]) -> bool:
    hits = sum(1 for line in lines if _BRANCH_RE.search(line))
    return hits >= 2


def _is_two_column(lines: list[str]) -> bool:
    """Detect two-column layout: first content line has two groups separated by many spaces."""
    for line in lines:
        if not line.strip():
            continue
        # Look for text, then 4+ spaces, then more text
        parts = re.split(r" {4,}", line.strip())
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            return True
        break
    return False


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_timeline(lines: list[str]) -> DiagramModel:
    nodes: list[Node] = []
    footer_lines: list[str] = []
    in_footer = False

    for line in lines:
        if not line.strip():
            continue
        m = _TIME_RE.match(line)
        if m:
            parts = line.strip().split(None, 1)
            time_label = parts[0]
            event_text = parts[1] if len(parts) > 1 else ""
            nodes.append(Node(text=event_text, note=time_label))
        else:
            # Lines after the time entries become footer/context
            in_footer = True
            footer_lines.append(line.strip())

    title = footer_lines[0] if footer_lines else None
    return DiagramModel(kind="timeline", title=title, nodes=nodes)


def _parse_two_column(lines: list[str]) -> DiagramModel:
    """Parse two-column flow diagrams."""
    # Find the divider column position from the underline row
    split_pos = None
    col_headers: list[str] = []

    content_lines: list[str] = []
    header_done = False

    for line in lines:
        if not line.strip():
            if header_done:
                content_lines.append("")
            continue

        if not header_done:
            # First non-empty line is the header row
            if not col_headers:
                # Find split position: look for large gap
                m = re.search(r" {4,}", line)
                if m:
                    split_pos = m.start() + len(m.group()) // 2
                    parts = re.split(r" {4,}", line.strip())
                    col_headers = [p.strip() for p in parts[:2]]
                continue

            # Second non-empty line may be underlines
            if _UNDERLINE_RE.match(line.lstrip()):
                header_done = True
                continue
            else:
                header_done = True
                content_lines.append(line)
        else:
            content_lines.append(line)

    if split_pos is None:
        split_pos = 40  # fallback

    left_nodes: list[Node] = []
    right_nodes: list[Node] = []

    i = 0
    while i < len(content_lines):
        line = content_lines[i]
        if not line.strip():
            i += 1
            continue

        # Split at the detected column position
        if len(line) > split_pos:
            left_text = line[:split_pos].strip()
            right_text = line[split_pos:].strip()
        else:
            left_text = line.strip()
            right_text = ""

        # Collect continuation lines until blank
        j = i + 1
        while j < len(content_lines) and content_lines[j].strip():
            extra = content_lines[j]
            if len(extra) > split_pos:
                left_text = (left_text + " " + extra[:split_pos].strip()).strip()
                right_text = (right_text + " " + extra[split_pos:].strip()).strip()
            else:
                left_text = (left_text + " " + extra.strip()).strip()
            j += 1

        if left_text or right_text:
            left_nodes.append(Node(text=left_text))
            right_nodes.append(Node(text=right_text))
        i = j + 1

    title = col_headers[0] if col_headers else None
    nodes: list[Node] = []
    columns = [left_nodes, right_nodes]

    return DiagramModel(
        kind="two_column_flow",
        title=" / ".join(col_headers) if col_headers else None,
        nodes=nodes,
        columns=columns,
    )


def _parse_branch_from_root(lines: list[str]) -> DiagramModel:
    """Parse branch-from-root diagrams (figure 6-1 style)."""
    nodes: list[Node] = []
    root_lines: list[str] = []
    found_root = False

    # Collect root text (lines before first branch)
    for line in lines:
        if _BRANCH_RE.search(line):
            break
        if line.strip() and line.strip() not in ("|", "v", "+"):
            root_lines.append(line.strip())
            found_root = True

    root_text = " ".join(root_lines).strip() if root_lines else "Root"
    nodes.append(Node(text=root_text, level=0))

    # Now collect branches
    current_branch_text: str | None = None
    current_bullets: list[str] = []

    def flush_branch() -> None:
        if current_branch_text is not None:
            nodes.append(Node(text=current_branch_text, level=1, bullets=list(current_bullets)))

    for line in lines:
        branch_m = re.match(r"^\s*\+--+>\s*(.+)$", line)
        if branch_m:
            flush_branch()
            current_branch_text = branch_m.group(1).strip()
            current_bullets = []
            continue

        bullet_m = re.match(r"^\s*\|?\s*-\s+(.+)$", line)
        if bullet_m and current_branch_text is not None:
            current_bullets.append(bullet_m.group(1).strip())
            continue

    flush_branch()
    return DiagramModel(kind="branch_from_root", title=None, nodes=nodes)


def _parse_vertical_flow(lines: list[str]) -> DiagramModel:
    """Default fallback: parse vertical flow separated by | / v / blank lines."""
    nodes: list[Node] = []
    current_lines: list[str] = []
    title: str | None = None

    # Check for section titles (e.g. lines followed by dashed underlines)
    # and branch side notes (+--> pattern handled for side branches)
    branch_side: str | None = None

    def flush_node() -> None:
        nonlocal branch_side
        text = " ".join(current_lines).strip()
        if text:
            node = Node(text=text)
            if branch_side:
                node.note = branch_side
                branch_side = None
            nodes.append(node)
        current_lines.clear()

    for line in lines:
        stripped = line.strip()

        # Connector / separator lines → flush current node and skip
        if stripped in ("", "|", "v", "↓", "+"):
            flush_node()
            continue

        # Side branch arrow line: +--> some text
        side_m = re.match(r"^\s*\+--+>\s*(.+)$", stripped)
        if side_m:
            flush_node()
            branch_side = side_m.group(1).strip()
            continue

        # Skip separator/arrow-only lines
        if re.match(r"^[-|v+> ]+$", stripped) and len(stripped) <= 8:
            continue

        # Section title followed by underline on next line: detect via context
        # Just collect it as text for now
        current_lines.append(stripped)

    flush_node()
    return DiagramModel(kind="vertical_flow", title=title, nodes=nodes)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_ascii_diagram(text: str) -> DiagramModel:
    """Convert raw ASCII diagram text into a DiagramModel."""
    lines = text.splitlines()

    # Strip trailing blank lines
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return DiagramModel(kind="vertical_flow", title=None, nodes=[Node(text="(empty)")])

    if _is_timeline(lines):
        return _parse_timeline(lines)

    if _is_branch_from_root(lines):
        return _parse_branch_from_root(lines)

    if _is_two_column(lines):
        return _parse_two_column(lines)

    return _parse_vertical_flow(lines)
