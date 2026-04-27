from __future__ import annotations

# ── Color palette ────────────────────────────────────────────────────────────
BG         = "#FBFBF8"
INK        = "#1E2A36"
MUTED      = "#6C7A89"
NAVY       = "#244C5A"
TEAL       = "#2B7A78"
SKY        = "#CFE8E8"
GOLD       = "#E8B44B"
SAND       = "#F3E7CB"
RED        = "#C75D4D"
ROSE       = "#F3D7D2"
GREEN      = "#5B8E55"
MINT       = "#DCEBD8"
GRAY       = "#D9DEE3"
BLUE_FILL  = "#DCE7F5"

# Single style for all nodes: white fill, black outline/text
NODE_STYLES: list[tuple[str, str]] = [
    ("#FFFFFF", "#000000"),
]

# PPTX shape color: white fill, black text
PPTX_COLORS: list[str] = ["#FFFFFF"]
PPTX_TEXT   = "#000000"   # black text on white

# ── Layout constants ─────────────────────────────────────────────────────────
CANVAS_WIDTH     = 1800
MARGIN_X         = 120
MARGIN_Y         = 100
BOX_RADIUS       = 24
LINE_WIDTH       = 4
ARROW_HEAD       = 18
ARROW_LINE_WIDTH = 8
MIN_BOX_W        = 400
MIN_BOX_H        = 90
V_GAP            = 60    # vertical gap between consecutive boxes
H_GAP            = 80    # horizontal gap between side-by-side columns
SECTION_GAP      = 50    # extra vertical gap before section titles
BULLET_LINE_H    = 38    # height per bullet line inside branch boxes
BULLET_INDENT    = 36    # horizontal indent for bullet text
