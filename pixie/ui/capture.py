"""Capture helper: grab reference images, click points and colors off the screen.

Every mode freezes the screen first and lets you work on the frozen copy, so
the application underneath can't change while you're dragging a box.

    python capture.py region --name my_button   # drag a box -> images/my_button.png
    python capture.py area                      # drag a box -> search_region bounds
    python capture.py point                     # click once -> screen coordinates
    python capture.py color                    # click once -> RGB value
    python capture.py test                      # check config.json against the screen
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tkinter as tk
from pathlib import Path

import cv2
from PIL import Image, ImageTk

from pixie.system import screen

from pixie.paths import APP_DIR as PROJECT_DIR, IMAGES_DIR

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


def cmd_region(args: argparse.Namespace) -> int:
    picker = Picker("region")
    box = picker.run()
    if box is None:
        print("Canceled.")
        return 1

    x, y, w, h = box
    abs_x, abs_y, _, _ = picker.to_absolute(box)
    IMAGES_DIR.mkdir(exist_ok=True)
    path = IMAGES_DIR / f"{args.name}.png"
    cv2.imwrite(str(path), picker.frame[y : y + h, x : x + w])

    print(f"Saved {path}  ({w}x{h})")
    print(f"Captured from screen position: {abs_x}, {abs_y}")
    print("\nPut this in config.json:")
    print(f'  "template": "images/{args.name}.png"')
    print("\nScanning the whole desktop takes a while on a large or multi-monitor")
    print("setup. If this image only ever appears in one part of the screen, run")
    print("`python capture.py area` and set `search_region` to narrow the scan.")
    return 0


def cmd_area(_args: argparse.Namespace) -> int:
    picker = Picker("area")
    box = picker.run()
    if box is None:
        print("Canceled.")
        return 1

    left, top, w, h = picker.to_absolute(box)
    full_w, full_h = screen.virtual_bounds()[2:]
    ratio = (w * h) / (full_w * full_h)
    print(f"Search area: {w}x{h} at {left}, {top}")
    print(f"That is {ratio:.1%} of the desktop, so roughly {1 / ratio:.0f}x faster to scan.")
    print("\nPut this in config.json:")
    print(f'  "search_region": [{left}, {top}, {w}, {h}]')
    print("\nMake it comfortably bigger than the place the image appears - if the")
    print("image ever lands outside this box it will never be found.")
    return 0


def cmd_point(_args: argparse.Namespace) -> int:
    picker = Picker("point")
    point = picker.run()
    if point is None:
        print("Canceled.")
        return 1
    x, y = picker.to_absolute(point)
    print(f"Screen position: {x}, {y}")
    print("\nPut this in config.json:")
    print(f'  "pos": [{x}, {y}]')
    return 0


def cmd_color(_args: argparse.Namespace) -> int:
    picker = Picker("color")
    point = picker.run()
    if point is None:
        print("Canceled.")
        return 1
    r, g, b = picker.color_at(*point)
    x, y = picker.to_absolute(point)
    print(f"Color at {x}, {y}:  RGB({r}, {g}, {b})  #{r:02x}{g:02x}{b:02x}")
    print("\nPut this in config.json:")
    print(f'  "color": [{r}, {g}, {b}]')
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Report what the automator would see right now, without clicking anything."""
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    trigger = config["trigger"]
    settings = config.get("settings", {})
    check = config["color_check"]

    template = screen.load_template(PROJECT_DIR / trigger["template"])
    region = trigger.get("search_region")
    region = tuple(region) if region else None
    confidence = settings.get("confidence", 0.85)

    started = time.perf_counter()
    score = screen.best_score(template, region)
    elapsed = (time.perf_counter() - started) * 1000
    print(f"Template : {trigger['template']}")
    print(f"Scan time: {elapsed:.0f} ms" + ("" if region else "   (whole desktop)"))
    print(f"Best match score: {score:.3f}   (threshold {confidence})")
    if elapsed > 300 and not region:
        print("  Slow. Run `python capture.py area` and set `search_region`.")

    if score < confidence:
        print("\nNOT FOUND at the current threshold.")
        print("If the image is visible on screen right now, lower `confidence`")
        print(f"in {args.config} to just under {score:.3f}, or recapture the image.")
        return 1

    match = screen.find_template(template, region, confidence)
    assert match is not None
    cx, cy = match.center
    print(f"Found at : {match.x}, {match.y}  ({match.width}x{match.height})")
    print(f"Would double-click: {cx}, {cy}")

    off_x, off_y = check.get("offset", [0, 0])
    px, py = cx + off_x, cy + off_y
    target = tuple(check["color"])
    tolerance = check.get("tolerance", 30)
    radius = check.get("radius", 3)
    mode = check.get("mode", "any")
    actual = screen.pixel_color(px, py)
    present = screen.color_present(px, py, target, tolerance, radius, mode)

    print(f"\nColor check at {px}, {py}")
    print(f"  looking for : RGB{target}  (tolerance {tolerance}, radius {radius}, mode {mode})")
    print(f"  center pixel: RGB{actual}")
    print(f"  match       : {'YES' if present else 'no'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    screen.set_dpi_aware()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command", required=True)

    p_region = subs.add_parser("region", help="drag a box and save it as a reference image")
    p_region.add_argument("--name", default="target", help="filename stem under images/")
    p_region.set_defaults(func=cmd_region)

    subs.add_parser("area", help="drag a box to get search_region bounds").set_defaults(func=cmd_area)
    subs.add_parser("point", help="click once to record a screen coordinate").set_defaults(func=cmd_point)
    subs.add_parser("color", help="click once to read a pixel color").set_defaults(func=cmd_color)

    p_test = subs.add_parser("test", help="check a config against the current screen")
    p_test.add_argument("--config", default=str(PROJECT_DIR / "config.json"))
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
