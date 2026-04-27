from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext

import re

from PIL import Image, ImageTk

from diagram_renderer import (
    is_mermaid,
    render_ascii_to_png,
    render_ascii_to_pptx,
    render_mermaid_to_png,
    render_mermaid_to_pptx,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

_FENCE_RE = re.compile(r"^```[\w]*\s*$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    """Remove Markdown code-fence lines (```text / ```) and return inner content."""
    lines = text.splitlines()
    result: list[str] = []
    for line in lines:
        if _FENCE_RE.match(line.strip()):
            continue
        result.append(line)
    return "\n".join(result)


def _open_folder(path: Path) -> None:
    """Open the given directory in the OS file manager."""
    if sys.platform.startswith("win"):
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ASCII Diagram to PNG")
        self.resizable(True, True)
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Text area ────────────────────────────────────────────────────────
        frame_text = tk.Frame(self)
        frame_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        frame_text.columnconfigure(0, weight=1)
        frame_text.rowconfigure(0, weight=1)

        self._text = scrolledtext.ScrolledText(
            frame_text,
            wrap=tk.NONE,
            font=("Consolas", 11),
            undo=True,
            width=80,
            height=24,
        )
        self._text.grid(row=0, column=0, sticky="nsew")

        # Horizontal scrollbar
        hbar = tk.Scrollbar(frame_text, orient=tk.HORIZONTAL, command=self._text.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        self._text.configure(xscrollcommand=hbar.set)

        # ── Button bar ───────────────────────────────────────────────────────
        frame_btn = tk.Frame(self)
        frame_btn.grid(row=1, column=0, sticky="ew", padx=10, pady=4)

        btn_gen = tk.Button(
            frame_btn,
            text="Generate PNG",
            font=("Segoe UI", 11),
            bg="#244C5A",
            fg="white",
            activebackground="#2B7A78",
            activeforeground="white",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            command=self._on_generate,
        )
        btn_gen.pack(side=tk.LEFT, padx=(0, 8))

        btn_pptx = tk.Button(
            frame_btn,
            text="Generate PPTX",
            font=("Segoe UI", 11),
            bg="#8B4513",
            fg="white",
            activebackground="#A0522D",
            activeforeground="white",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            command=self._on_generate_pptx,
        )
        btn_pptx.pack(side=tk.LEFT, padx=(0, 8))

        btn_open = tk.Button(
            frame_btn,
            text="Open Output Folder",
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            padx=16,
            pady=6,
            command=self._on_open_folder,
        )
        btn_open.pack(side=tk.LEFT)

        # ── Status bar ───────────────────────────────────────────────────────
        frame_status = tk.Frame(self, bd=1, relief=tk.SUNKEN)
        frame_status.grid(row=2, column=0, sticky="ew")

        self._status_var = tk.StringVar(value="Ready.")
        lbl_status = tk.Label(
            frame_status,
            textvariable=self._status_var,
            anchor="w",
            font=("Segoe UI", 10),
            padx=8,
            pady=4,
        )
        lbl_status.pack(fill=tk.X)

        # ── Window minimum size ──────────────────────────────────────────────
        self.update_idletasks()
        self.minsize(640, 480)

    def _get_diagram_text(self) -> str | None:
        raw = self._text.get("1.0", tk.END).strip()
        if not raw:
            self._set_status("Nothing to render — paste an ASCII diagram first.", error=True)
            return None
        return _strip_fences(raw).strip()

    def _on_generate(self) -> None:
        text = self._get_diagram_text()
        if not text:
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".png"
        output_path = OUTPUT_DIR / filename

        try:
            if is_mermaid(text):
                self._set_status("Mermaid diagram detected — rendering…")
                render_mermaid_to_png(text, output_path)
            else:
                render_ascii_to_png(text, output_path)
            self._set_status(f"Saved: {output_path}")
            _PreviewWindow(self, output_path)
        except Exception as exc:
            self._set_status(f"Error: {exc}", error=True)
            messagebox.showerror("Render error", str(exc))

    def _on_generate_pptx(self) -> None:
        text = self._get_diagram_text()
        if not text:
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".pptx"
        output_path = OUTPUT_DIR / filename

        try:
            if is_mermaid(text):
                self._set_status("Mermaid diagram detected — rendering…")
                render_mermaid_to_pptx(text, output_path)
            else:
                render_ascii_to_pptx(text, output_path)
            self._set_status(f"Saved: {output_path}")
        except Exception as exc:
            self._set_status(f"Error: {exc}", error=True)
            messagebox.showerror("Render error", str(exc))

    def _on_open_folder(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _open_folder(OUTPUT_DIR)
        except Exception as exc:
            self._set_status(f"Cannot open folder: {exc}", error=True)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self._status_var.set(message)
        self._text.configure(highlightbackground="red" if error else "SystemButtonFace")


class _PreviewWindow(tk.Toplevel):
    """Scrollable preview window that shows the generated PNG."""

    # Max display size before scaling down
    _MAX_W = 1200
    _MAX_H = 800

    def __init__(self, parent: tk.Tk, image_path: Path) -> None:
        super().__init__(parent)
        self.title(image_path.name)
        self.resizable(True, True)
        self._build(image_path)
        self.focus_set()

    def _build(self, image_path: Path) -> None:
        img = Image.open(image_path)
        img = self._fit(img)

        # Keep a reference so GC doesn't destroy it
        self._photo = ImageTk.PhotoImage(img)

        # Scrollable canvas
        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(frame, bg="#FBFBF8",
                           width=min(img.width, self._MAX_W),
                           height=min(img.height, self._MAX_H))
        canvas.grid(row=0, column=0, sticky="nsew")

        vsb = tk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = tk.Scrollbar(frame, orient=tk.HORIZONTAL, command=canvas.xview)
        hsb.grid(row=1, column=0, sticky="ew")

        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.create_image(0, 0, anchor="nw", image=self._photo)
        canvas.configure(scrollregion=(0, 0, img.width, img.height))

        # Mouse-wheel scroll
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        canvas.bind("<Shift-MouseWheel>",
                    lambda e: canvas.xview_scroll(-1 * (e.delta // 120), "units"))

        # Close button
        btn_close = tk.Button(self, text="Close", command=self.destroy,
                              font=("Segoe UI", 10), padx=12, pady=4,
                              relief=tk.FLAT)
        btn_close.pack(pady=(4, 6))

    def _fit(self, img: Image.Image) -> Image.Image:
        """Scale image down if it exceeds the max display size."""
        w, h = img.size
        scale = min(self._MAX_W / w, self._MAX_H / h, 1.0)
        if scale < 1.0:
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
        return img


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
