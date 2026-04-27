# ASCII Diagram to PNG Coding Plan

## Goal

Build a Python desktop program that converts pasted ASCII diagrams into PNG images.

The user should be able to:

1. Run a tkinter GUI.
2. Paste ASCII diagram text into a large text area.
3. Click a generate button.
4. Receive a PNG file named with the current date and time.

Output filename format:

```text
YYYYMMDD_HHMMSS.png
```

Default output directory:

```text
outputs/
```

## Current Repository Inventory

The repository currently contains only the `samples` folder.

```text
samples/
  part6_ascii_diagrams.py
  generate_part6_docx.py
  inventory_discrepancy_investigator.py
  assets/
    figure_1_1.png
    figure_2_1.png
    figure_3_1.png
    figure_3_2.png
    figure_5_1.png
    figure_6_1.png
```

Relevant files:

- `samples/part6_ascii_diagrams.py`
  - Contains six ASCII diagram examples.
  - Use this as the main input reference.

- `samples/generate_part6_docx.py`
  - Contains the Pillow drawing code that generated the sample PNG assets.
  - Use this as the visual style reference.
  - Important helper ideas to reuse: font loading, canvas creation, rounded boxes, arrows, text wrapping, centered text, color palette.

- `samples/inventory_discrepancy_investigator.py`
  - Not directly relevant to the GUI or diagram renderer.

Relevant output assets:

```text
figure_1_1.png  1800x900
figure_2_1.png  1800x850
figure_3_1.png  1800x900
figure_3_2.png  1800x980
figure_5_1.png  1800x1185
figure_6_1.png  1800x950
```

Important observation:

`generate_part6_docx.py` does not parse ASCII diagrams automatically. It uses one custom drawing function per figure. The new program should reuse the visual approach, but it must generalize the rendering so pasted ASCII can be converted without writing a custom function for every diagram.

## Proposed Project Structure

```text
diagram_ascii2png/
  app.py
  diagram_renderer/
    __init__.py
    parser.py
    layout.py
    renderer.py
    style.py
    font.py
  outputs/
  samples/
  requirements.txt
  install.bat
  install.ps1
  install.sh
  run.bat
  run.ps1
  run.sh
  README.md
```

## Dependency Plan

Use the smallest practical dependency set.

`requirements.txt`:

```text
Pillow>=10.0.0
```

`tkinter` is part of the Python standard library on Windows and most Python distributions.

Linux note for README:

Some Linux systems require an OS package such as `python3-tk`.

## Environment Setup Scripts

Create scripts for Windows cmd, Windows PowerShell, and Unix-like shells.

### install.bat

```bat
@echo off
python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### install.ps1

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

### install.sh

```sh
#!/usr/bin/env sh
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### run.bat

```bat
@echo off
call venv\Scripts\activate.bat
python app.py
```

### run.ps1

```powershell
.\venv\Scripts\python.exe app.py
```

### run.sh

```sh
#!/usr/bin/env sh
. venv/bin/activate
python app.py
```

## Application Design

### app.py

Responsibilities:

- Build the tkinter window.
- Provide a multiline text input.
- Provide a generate button.
- Show status messages.
- Save generated files into `outputs/`.
- Use `datetime.now()` for the filename.
- Catch rendering errors and display user-readable error messages.

Suggested GUI layout:

```text
+--------------------------------------------------+
| ASCII Diagram to PNG                             |
+--------------------------------------------------+
| [ large multiline text area                    ] |
| [                                                ] |
| [                                                ] |
+--------------------------------------------------+
| [Generate PNG] [Open Output Folder]              |
| Status: outputs/20260427_153000.png created      |
+--------------------------------------------------+
```

Implementation notes:

- Use `tk.Text` for the input area.
- Use `tk.Button` for actions.
- Use `tk.StringVar` for status text.
- Use `pathlib.Path` for paths.
- The output folder should be created automatically.

## Renderer Package Design

### diagram_renderer/style.py

Centralize visual constants copied and simplified from `samples/generate_part6_docx.py`.

Recommended palette:

```python
BG = "#FBFBF8"
INK = "#1E2A36"
MUTED = "#6C7A89"
NAVY = "#244C5A"
TEAL = "#2B7A78"
SKY = "#CFE8E8"
GOLD = "#E8B44B"
SAND = "#F3E7CB"
RED = "#C75D4D"
ROSE = "#F3D7D2"
GREEN = "#5B8E55"
MINT = "#DCEBD8"
GRAY = "#D9DEE3"
BLUE_FILL = "#DCE7F5"
```

Also define:

- margins
- box radius
- line widths
- arrow head size
- minimum box width
- minimum box height
- vertical gap
- horizontal gap

### diagram_renderer/font.py

Responsibilities:

- Load fonts robustly across platforms.
- Prefer Korean-capable or common fonts when available.
- Fall back to Pillow default font.

Candidate font names:

```text
malgun.ttf
malgunbd.ttf
DejaVuSans.ttf
DejaVuSans-Bold.ttf
arial.ttf
arialbd.ttf
Arial Unicode.ttf
```

Expose:

```python
load_font(size: int, bold: bool = False)
```

### diagram_renderer/parser.py

Responsibilities:

- Convert raw ASCII text into a simple intermediate model.
- Detect the broad diagram shape.
- Extract node text, section titles, side notes, branch labels, and bullet lists where possible.

Suggested dataclasses:

```python
@dataclass
class Node:
    text: str
    level: int = 0
    bullets: list[str] = field(default_factory=list)
    note: str | None = None

@dataclass
class DiagramModel:
    kind: str
    title: str | None
    nodes: list[Node]
    columns: list[list[Node]] = field(default_factory=list)
```

Supported `kind` values:

```text
vertical_flow
two_column_flow
timeline
branch_from_root
```

Detection rules:

- `timeline`
  - Multiple lines begin with time-like values such as `08:20`, `09:50`, `Later`.

- `branch_from_root`
  - Contains repeated `+-->` lines.
  - Example: Figure 6-1.

- `two_column_flow`
  - First non-empty line has widely separated text groups.
  - Next line may contain two underline groups such as `--------------                    ------------`.
  - Example: Figure 1-1 and Figure 2-1.

- `vertical_flow`
  - Default fallback.
  - Lines separated by `|`, `v`, and blank lines become sequential nodes.

Parsing should be forgiving. If the parser is uncertain, it should still produce a `vertical_flow` model.

### diagram_renderer/layout.py

Responsibilities:

- Convert `DiagramModel` into drawable boxes and arrows.
- Compute canvas width and height automatically.
- Avoid the hardcoded height problem visible in the sample `figure_5_1.png`.

Suggested dataclasses:

```python
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

@dataclass
class Arrow:
    start: tuple[int, int]
    end: tuple[int, int]
    color: str

@dataclass
class Layout:
    width: int
    height: int
    boxes: list[Box]
    arrows: list[Arrow]
    title: str | None = None
```

Layout functions:

```python
layout_vertical_flow(model: DiagramModel) -> Layout
layout_two_column_flow(model: DiagramModel) -> Layout
layout_timeline(model: DiagramModel) -> Layout
layout_branch_from_root(model: DiagramModel) -> Layout
```

Rules:

- Use 1800px as the default wide canvas width for sample-like diagrams.
- Compute height based on number of nodes and text wrapping.
- Use stable box sizes with a minimum width and height.
- Increase box height for long text or bullet lists.
- Use alternating colors similar to sample figures.

### diagram_renderer/renderer.py

Responsibilities:

- Draw the final PNG using Pillow.
- Keep drawing helpers generic.

Reusable helper functions from sample:

- `canvas`
- `wrap_text`
- `draw_centered_text`
- `draw_label`
- `rounded_box`
- `arrow`
- `box_with_text`

Main public API:

```python
def render_ascii_to_png(text: str, output_path: Path) -> Path:
    model = parse_ascii_diagram(text)
    layout = build_layout(model)
    image = render_layout(layout)
    image.save(output_path)
    return output_path
```

## Initial ASCII Support Scope

The first implementation should support diagrams similar to the six sample diagrams.

### 1. Vertical Flow

Input:

```text
Load task cards
      |
      v
Add part requirements
      |
      v
Calculate expected use by station and part
```

Expected output:

- One centered vertical stack.
- Rounded boxes.
- Down arrows between boxes.

### 2. Vertical Flow With Side Branch

Input:

```text
Add linked issue quantity
      |
      +--> keep orphan issue rows separate
      |
      v
Add latest cycle count
```

Expected output:

- Main node remains in vertical stack.
- Side branch appears to the right.
- Horizontal arrow connects branch.

### 3. Two Column Flow

Input:

```text
Physical world                    Record world
--------------                    ------------
12 seal rings in bin              12 seal rings in system

Technician uses 1 ring            No issue posted yet

11 seal rings in bin              System still says 12
```

Expected output:

- Two columns.
- Each column has its own heading.
- Matching row pairs become boxes.
- Down arrows connect each column.

### 4. Branch From Root

Input:

```text
Investigation queue row
        |
        +--> Materials review
        |      - recount the bin
        |      - review issue and receipt history
        |
        +--> Maintenance review
        |      - confirm actual part use for the task IDs
        |
        +--> Accounting review
               - confirm whether ledger correction is needed
```

Expected output:

- Root box at top.
- Three branch boxes below.
- Bullet lists are rendered inside branch boxes.
- Arrows connect root to each branch.

### 5. Timeline

Input:

```text
08:20   Task opens
09:50   Seal replacement task closes
09:55   Part has already been physically consumed
10:00   Aircraft is released back to service
11:10   Issue row is posted without a task ID
Later   Cycle count shows the bin is short
```

Expected output:

- Horizontal timeline.
- Time labels above or near each marker.
- Event labels in boxes below the line.

## Implementation Order for Mini

1. Create `requirements.txt`.
2. Create install and run scripts:
   - `install.bat`
   - `install.ps1`
   - `install.sh`
   - `run.bat`
   - `run.ps1`
   - `run.sh`
3. Create the `diagram_renderer` package.
4. Implement `style.py`.
5. Implement `font.py`.
6. Implement generic drawing helpers in `renderer.py`.
7. Implement the parser in `parser.py`.
8. Implement layout functions in `layout.py`.
9. Implement `render_ascii_to_png`.
10. Implement `app.py` tkinter GUI.
11. Add `README.md`.
12. Test manually with each sample ASCII diagram.

## Manual Verification Plan

Use the six diagrams from `samples/part6_ascii_diagrams.py`.

For each diagram:

1. Paste the ASCII text into the GUI.
2. Click the generate button.
3. Confirm a file is created in `outputs/`.
4. Compare the generated image with the matching file in `samples/assets/`.

Check:

- The node order is correct.
- The diagram type is detected correctly.
- Arrows point in the expected direction.
- Long text wraps inside boxes.
- Bullet lists render inside branch boxes.
- Canvas height is large enough.
- No black bottom area appears.
- Output filename uses the expected date/time format.
- The app does not crash on empty input.

## Acceptance Criteria

The first version is complete when:

- The app runs from `run.bat`, `run.ps1`, and `run.sh` after installation.
- A user can paste ASCII text and create a PNG.
- Output files are written to `outputs/YYYYMMDD_HHMMSS.png`.
- The six sample diagrams produce readable PNG diagrams.
- The visual style is close to the existing sample PNG files.
- The renderer does not depend on hardcoded sample-specific figure functions.

## Known Limitations for Version 1

- The parser will be heuristic-based, not a complete ASCII art parser.
- Complex arbitrary box drawings using `+---+` borders may not render perfectly.
- Diagrams with many crossing arrows may need manual cleanup or future parser rules.
- Perfect pixel matching with `samples/assets` is not required.
- The target is readable, polished PNG output for common flow-style ASCII diagrams.

## Future Improvements

- Add a preview pane in the tkinter GUI.
- Add canvas size options.
- Add light/dark theme presets.
- Add explicit diagram type selector for ambiguous inputs.
- Add drag-and-drop text file input.
- Add CLI mode:

```text
python -m diagram_renderer input.txt output.png
```

- Add tests for parser detection and layout generation.
