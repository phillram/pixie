"""The frozen-screen picker, behind every Capture button in the window.

Freezing first is the point: the screen is photographed, and you drag your box
on the photograph, so the application underneath cannot move, animate or close
a menu while you are working on it.

Four modes, all returning coordinates on the real desktop rather than on the
photograph: "region" and "area" drag a box, "point" and "color" take a single
click.
"""

from __future__ import annotations

import tkinter as tk

import cv2
from PIL import Image, ImageTk

from pixie.system import screen

INSTRUCTIONS = {
    "region": "Drag a box around the thing to detect.  Esc cancels.",
    "area": "Drag a box around the area to search in.  Esc cancels.",
    "point": "Click the spot you want recorded.  Esc cancels.",
    "color": "Click the pixel whose color you want.  Esc cancels.",
}
BOX_MODES = ("region", "area")


class Picker:
    """Fullscreen frozen-screenshot overlay that returns a box or a point."""

    def __init__(self, mode: str, parent: tk.Misc | None = None) -> None:
        self.mode = mode
        self.result: tuple[int, ...] | None = None
        self.left, self.top, self.width, self.height = screen.virtual_bounds()
        self.frame = screen.grab()

        # Tk allows only one root per process, so when the GUI is already
        # running we hang the overlay off it as a Toplevel instead.
        self.owns_root = parent is None
        self.root = tk.Tk() if self.owns_root else tk.Toplevel(parent)
        self.root.overrideredirect(True)
        # Tk wants the sign as part of the offset: "1920x1080-1920+0"
        self.root.geometry(f"{self.width}x{self.height}{self.left:+d}{self.top:+d}")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")

        rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))

        self.canvas = tk.Canvas(
            self.root, width=self.width, height=self.height,
            highlightthickness=0, bd=0, cursor="crosshair", bg="black",
        )
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self._draw_banner()

        self.start: tuple[int, int] | None = None
        self.rect: int | None = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        self.root.focus_force()

    def _draw_banner(self) -> None:
        text = INSTRUCTIONS[self.mode]
        pad = 14
        self.canvas.create_rectangle(
            0, 0, self.width, 52, fill="#111111", outline="", stipple="gray75"
        )
        self.canvas.create_text(
            pad, 26, text=text, anchor="w", fill="#f5f5f5",
            font=("Segoe UI", 13, "bold"),
        )

    def _on_press(self, event: tk.Event) -> None:
        self.start = (event.x, event.y)
        if self.mode not in BOX_MODES:
            return
        self.rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#4ea1ff", width=2
        )

    def _on_drag(self, event: tk.Event) -> None:
        if self.mode in BOX_MODES and self.rect is not None and self.start:
            self.canvas.coords(self.rect, *self.start, event.x, event.y)

    def _on_release(self, event: tk.Event) -> None:
        if not self.start:
            return
        if self.mode in BOX_MODES:
            x0, y0 = self.start
            x1, y1 = event.x, event.y
            left, right = sorted((x0, x1))
            top, bottom = sorted((y0, y1))
            if right - left < 3 or bottom - top < 3:
                return  # a stray click, not a box -- keep waiting
            self.result = (left, top, right - left, bottom - top)
        else:
            self.result = (event.x, event.y)
        self.root.destroy()

    def run(self) -> tuple[int, ...] | None:
        if self.owns_root:
            self.root.mainloop()
        else:
            self.root.grab_set()
            self.root.wait_window(self.root)
        return self.result

    def color_at(self, canvas_x: int, canvas_y: int) -> tuple[int, int, int]:
        """RGB of a pixel in the frozen screenshot."""
        r, g, b = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)[canvas_y, canvas_x]
        return int(r), int(g), int(b)

    def to_absolute(self, canvas_coords: tuple[int, ...]) -> tuple[int, ...]:
        if len(canvas_coords) == 2:
            x, y = canvas_coords
            return x + self.left, y + self.top
        x, y, w, h = canvas_coords
        return x + self.left, y + self.top, w, h
