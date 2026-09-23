"""Pixie -- build a sequence of screen steps, then run it on a loop.

    python gui.py

The left pane is the sequence. Pick a step to edit it on the right; every
image, color, point and search area has a Capture button that freezes the
screen and lets you point at what you mean. Start runs the sequence over and
over until you press Stop, or the start/stop key from anywhere.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from pixie.ui import capture
from pixie.ui import editing
from pixie.core import engine as engine_mod
from pixie.system import keyboard
from pixie.system import screen
from pixie.core import steps as step_defs
from pixie.ui import theme

from pixie.paths import (APP_DIR as PROJECT_DIR, APP_NAME, ICON_PATH, IMAGES_DIR,
                   SEQUENCES_DIR, STATE_PATH, ensure_dirs)

LOG_COLORS = {"info": theme.FG, "warn": theme.WARN, "error": theme.ERROR,
              "good": theme.OK, "muted": theme.MUTED}


OFF = "Off"  # what the start/stop key is set to when you don't want one
# The keys we can offer come from the ones screen.key_pressed can read, so the
# menu cannot drift into offering a key that would then fail.
HOTKEYS = list(screen.hotkey_names())
HOTKEY_POLL_MS = 90  # how often to ask Windows whether the start key is down

# Both from the engine, which owns what these settings mean.
PARK_LABELS = engine_mod.PARK_LABELS
PARK_MODES = {label: mode for mode, label in PARK_LABELS.items()}


def _range_text(low: float, high: float) -> str:
    return f"{low}-{high}s" if float(high) > float(low) else f"{low}s"


def _display_scale(window: tk.Misc) -> float:
    """How much bigger than 96 DPI this display is, e.g. 1.5 at 150%."""
    try:
        import ctypes

        window.update_idletasks()
        dpi = ctypes.windll.user32.GetDpiForWindow(window.winfo_id())
        return max(1.0, dpi / 96.0) if dpi else 1.0
    except (AttributeError, OSError, tk.TclError):
        return 1.0


class KeyGrabber:
    """Tiny modal that records the next key you press."""

    # tkinter's keysym names don't all match ours.
    TRANSLATE = {
        "Return": "Enter", "KP_Enter": "Enter", "Escape": "Escape",
        "space": "Space", "BackSpace": "Backspace", "Prior": "PageUp",
        "Next": "PageDown", "Caps_Lock": "CapsLock",
        "Shift_L": "Shift", "Shift_R": "Shift",
        "Control_L": "Ctrl", "Control_R": "Ctrl",
        "Alt_L": "Alt", "Alt_R": "Alt",
        "minus": "Minus", "equal": "Equals", "comma": "Comma",
        "period": "Period", "slash": "Slash", "semicolon": "Semicolon",
        "apostrophe": "Apostrophe", "bracketleft": "LeftBracket",
        "bracketright": "RightBracket", "backslash": "Backslash",
        "grave": "Backtick",
    }

    def __init__(self, parent: tk.Misc, scale: float = 1.0) -> None:
        self.result: str | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("Press a key")
        theme.dark_titlebar(self.window)
        self.window.configure(bg=theme.BG)
        self.window.resizable(False, False)
        self.window.transient(parent)  # type: ignore[arg-type]

        frame = ttk.Frame(self.window, padding=int(28 * scale))
        frame.pack()
        ttk.Label(frame, text="Press the key you want", style="Title.TLabel").pack()
        self.echo = ttk.Label(frame, text="waiting...", style="Muted.TLabel")
        self.echo.pack(pady=(10, 0))
        ttk.Label(frame, text="Escape cancels.", style="Muted.TLabel").pack(pady=(14, 0))

        self.window.bind("<Key>", self._on_key)
        self.window.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.window.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.window.winfo_height()) // 3
        self.window.geometry(f"+{x}+{y}")

    def _on_key(self, event: tk.Event) -> None:
        keysym = event.keysym
        if keysym == "Escape":
            self.window.destroy()
            return
        name = self.TRANSLATE.get(keysym)
        if name is None:
            if len(keysym) == 1 and keysym.isalnum():
                name = keysym.upper()
            elif keysym in keyboard.KEYS:
                name = keysym
        if name is None or name not in keyboard.KEYS:
            self.echo.configure(text=f"{keysym} is not a key Pixie can send - try another")
            return
        self.result = name
        self.window.destroy()

    def run(self) -> str | None:
        self.window.grab_set()
        self.window.focus_force()
        self.window.wait_window(self.window)
        return self.result


class SettingsDialog:
    """Edit the whole-sequence settings: pauses, the abort key, the failsafe."""

    RANGES = (
        ("step_pause", "Pause after each step",
         "Breathing room so the application can react. Give the two boxes "
         "different values and the pause varies randomly between them, which "
         "also stops every cycle taking exactly the same time."),
        ("section_pause", "Pause between sections",
         "Waited when Pixie moves on to the next section, or starts the "
         "current one again. Separate from the step pause, so you can have "
         "one without the other - set both to 0 to move between screens with "
         "no delay at all."),
        ("cycle_pause", "Pause between cycles",
         "One cycle is one trip through every section. This is waited at the "
         "end of that trip, before the sequence starts again from its very "
         "first step."),
    )

    def __init__(self, parent: tk.Misc, settings: engine_mod.Settings,
                 scale: float = 1.0) -> None:
        self.settings = settings
        self.saved = False
        self.window = tk.Toplevel(parent)
        self.window.title("Settings")
        theme.dark_titlebar(self.window)
        self.window.configure(bg=theme.BG)
        self.window.resizable(False, False)
        self.window.transient(parent)  # type: ignore[arg-type]

        frame = ttk.Frame(self.window, padding=int(20 * scale))
        frame.pack(fill="both", expand=True)

        self.vars: dict[str, tk.Variable] = {}
        row = 0
        ttk.Label(frame, text="These belong to this sequence, not to Pixie, so "
                              "different jobs can have different timing. Saving "
                              "here saves the sequence too.",
                  style="Muted.TLabel", wraplength=int(440 * scale),
                  justify="left").grid(row=row, column=0, columnspan=2,
                                       sticky="w", pady=(0, 14))
        row += 1
        for key, label, hint in self.RANGES:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w",
                                              padx=(0, 14), pady=(4, 0))
            box = ttk.Frame(frame)
            box.grid(row=row, column=1, sticky="w", pady=(4, 0))
            for suffix, prefix_text in (("_min", "between"), ("_max", "and")):
                ttk.Label(box, text=prefix_text, style="Muted.TLabel").pack(
                    side="left", padx=(0 if suffix == "_min" else 8, 6))
                var = tk.StringVar(value=str(getattr(settings, key + suffix)))
                ttk.Entry(box, textvariable=var, width=7).pack(side="left")
                self.vars[key + suffix] = var
            ttk.Label(box, text="seconds", style="Muted.TLabel").pack(
                side="left", padx=(6, 0))
            row += 1
            ttk.Label(frame, text=hint, style="Muted.TLabel",
                      wraplength=int(440 * scale), justify="left").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(0, 10))
            row += 1

        ttk.Label(frame, text="How often to re-check").grid(
            row=row, column=0, sticky="w", padx=(0, 14), pady=(4, 0))
        poll_var = tk.StringVar(value=str(settings.poll_interval))
        ttk.Entry(frame, textvariable=poll_var, width=7).grid(
            row=row, column=1, sticky="w", pady=(4, 0))
        self.vars["poll_interval"] = poll_var
        row += 1
        ttk.Label(frame, text="Seconds between looks while waiting for an image "
                              "or color. Smaller reacts faster, uses more CPU.",
                  style="Muted.TLabel", wraplength=int(440 * scale),
                  justify="left").grid(row=row, column=0, columnspan=2,
                                       sticky="w", pady=(0, 10))
        row += 1

        ttk.Label(frame, text="Start/stop key").grid(row=row, column=0, sticky="w",
                                                     padx=(0, 14), pady=(4, 0))
        self.toggle_var = tk.StringVar(value=settings.toggle_key)
        ttk.Combobox(frame, textvariable=self.toggle_var, state="readonly", width=10,
                     values=[OFF] + HOTKEYS).grid(row=row, column=1, sticky="w",
                                                  pady=(4, 0))
        row += 1
        ttk.Label(frame, text="One key that starts the run and stops it again, from "
                              "anywhere. Press it once to start, once more to stop.",
                  style="Muted.TLabel", wraplength=int(440 * scale),
                  justify="left").grid(row=row, column=0, columnspan=2,
                                       sticky="w", pady=(0, 10))
        row += 1

        ttk.Label(frame, text="Stop key").grid(row=row, column=0, sticky="w",
                                               padx=(0, 14), pady=(4, 0))
        self.abort_var = tk.StringVar(value=settings.abort_key)
        ttk.Combobox(frame, textvariable=self.abort_var, state="readonly", width=10,
                     values=HOTKEYS).grid(row=row, column=1, sticky="w", pady=(4, 0))
        row += 1
        ttk.Label(frame, text="Stops the run and nothing else. Works even when "
                              "another window has focus.",
                  style="Muted.TLabel").grid(row=row, column=0, columnspan=2,
                                             sticky="w", pady=(0, 10))
        row += 1

        ttk.Label(frame, text="After each step").grid(row=row, column=0, sticky="w",
                                                      padx=(0, 14), pady=(4, 0))
        park_box = ttk.Frame(frame)
        park_box.grid(row=row, column=1, sticky="w", pady=(4, 0))
        self.park_var = tk.StringVar(value=PARK_LABELS.get(settings.park_mouse,
                                                           PARK_LABELS["off"]))
        park_combo = ttk.Combobox(park_box, textvariable=self.park_var, state="readonly",
                                  width=26, values=list(PARK_LABELS.values()))
        park_combo.pack(side="left")

        self.park_point = list(settings.park_point) if settings.park_point else None
        self.park_point_label = ttk.Label(park_box, text=self._park_point_text(),
                                          style="Muted.TLabel")
        ttk.Button(park_box, text="Pick spot...", style="Tool.TButton",
                   command=self._pick_park_point).pack(side="left", padx=(8, 0))
        self.park_point_label.pack(side="left", padx=(8, 0))
        row += 1
        ttk.Label(frame, text="Parks the cursor somewhere harmless so it can't sit "
                              "over the next thing Pixie needs to see. 'Middle of the "
                              "screen' means the middle of your primary monitor.",
                  style="Muted.TLabel", wraplength=int(440 * scale),
                  justify="left").grid(row=row, column=0, columnspan=2,
                                       sticky="w", pady=(0, 10))
        row += 1

        self.corner_var = tk.BooleanVar(value=settings.failsafe_corner)
        ttk.Checkbutton(frame, text="Mouse in the top-left corner also stops the run",
                        variable=self.corner_var).grid(row=row, column=0, columnspan=2,
                                                       sticky="w", pady=(0, 14))
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", style="Tool.TButton",
                   command=self.window.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="right")

        self.window.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.window.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.window.winfo_height()) // 3
        self.window.geometry(f"+{x}+{y}")

    def _park_point_text(self) -> str:
        if not self.park_point:
            return "no spot picked yet"
        return f"{self.park_point[0]}, {self.park_point[1]}"

    def _pick_park_point(self) -> None:
        """Let the user click the spot, with this dialog out of the way."""
        self.window.withdraw()
        try:
            picker = capture.Picker("point", parent=self.window)
            picker.run()
            if picker.result is not None:
                self.park_point = list(picker.to_absolute(picker.result))
                self.park_point_label.configure(text=self._park_point_text())
                self.park_var.set(PARK_LABELS["custom"])
        finally:
            self.window.deiconify()
            self.window.lift()

    def _save(self) -> None:
        for key, var in self.vars.items():
            try:
                setattr(self.settings, key, max(0.0, float(var.get())))
            except (TypeError, ValueError):
                messagebox.showwarning(
                    "Not a number", f"'{var.get()}' isn't a number of seconds.")
                return
        if self.toggle_var.get() == self.abort_var.get():
            messagebox.showwarning(
                "Same key twice",
                f"{self.abort_var.get()} cannot both start and stop the run. "
                "Give the start/stop key a different key, or turn it off.")
            return
        self.settings.abort_key = self.abort_var.get()
        self.settings.toggle_key = self.toggle_var.get()
        self.settings.failsafe_corner = bool(self.corner_var.get())
        # Keep what was already set if the label somehow does not match one we
        # know. It used to fall back to "off", which silently undid the
        # setting and looked exactly like Pixie forgetting it.
        self.settings.park_mouse = PARK_MODES.get(self.park_var.get(),
                                                  self.settings.park_mouse)
        self.settings.park_point = self.park_point
        if self.settings.park_mouse == "custom" and not self.park_point:
            messagebox.showwarning(
                "No spot picked",
                "Pick the spot to move the cursor to, or choose a different option.")
            self.saved = False
            return
        self.saved = True
        self.window.destroy()

    def run(self) -> bool:
        self.window.grab_set()
        self.window.focus_force()
        self.window.wait_window(self.window)
        return self.saved


class PictureWindow:
    """A screenshot with notes under it. Used by every 'show me' answer.

    Reading numbers out of a log and picturing where they are on screen is
    the part people get wrong, so anything Pixie can show instead of
    describing, she shows.
    """

    def __init__(self, parent: tk.Misc, title: str, picture,
                 lines: list[tuple[str, str]], caption: str = "",
                 scale: float = 1.0, save_as: str = "picture") -> None:
        self.save_as = save_as
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        theme.dark_titlebar(self.window)
        self.window.configure(bg=theme.BG)
        self.window.transient(parent)  # type: ignore[arg-type]

        frame = ttk.Frame(self.window, padding=int(14 * scale))
        frame.pack(fill="both", expand=True)

        import cv2
        from PIL import Image, ImageTk

        shown = Image.fromarray(cv2.cvtColor(picture, cv2.COLOR_BGR2RGB))
        full = shown.size
        # Fit it on screen without losing which patch is which.
        limit = (int(parent.winfo_screenwidth() * 0.8),
                 int(parent.winfo_screenheight() * 0.5))
        shown.thumbnail(limit, Image.LANCZOS)
        photo = ImageTk.PhotoImage(shown)

        holder = tk.Frame(frame, bg=theme.BORDER)
        holder.pack(anchor="w")
        label = tk.Label(holder, image=photo, bd=0, bg=theme.PANEL)
        label.image = photo   # Tk drops the image without a reference
        label.pack(padx=1, pady=1)

        note = f"{full[0]} x {full[1]}"
        if shown.size != full:
            note += f", shown at {shown.size[0]} x {shown.size[1]}"
        ttk.Label(frame, text=f"{note}     {caption}", style="Muted.TLabel").pack(
            anchor="w", pady=(6, 10))

        report = theme.text(frame, height=min(14, max(3, len(lines) + 1)),
                            width=92, state="normal")
        report.pack(fill="both", expand=True)
        for level, color in LOG_COLORS.items():
            report.tag_configure(level, foreground=color)
        for text, tag in lines:
            report.insert("end", text + "\n", tag)
        report.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(10, 0))
        # Nothing is written to disk unless you ask: these are worth keeping
        # only when you want to compare two attempts or show someone.
        save = ttk.Button(buttons, text="Save picture...", style="Tool.TButton",
                          command=lambda: self._save(picture))
        save.pack(side="left", padx=(0, 6))
        theme.tip(save, "Write this picture to a file. Nothing is saved "
                        "automatically - it only exists in this window.")
        ttk.Button(buttons, text="Close", style="Tool.TButton",
                   command=self.window.destroy).pack(side="left")
        self.window.bind("<Escape>", lambda _e: self.window.destroy())
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.window.update_idletasks()
        x = parent.winfo_rootx() + 40
        y = parent.winfo_rooty() + 40
        self.window.geometry(f"+{x}+{y}")

    def _save(self, picture) -> None:
        import cv2

        target = filedialog.asksaveasfilename(
            parent=self.window, title="Save this picture",
            initialdir=str(PROJECT_DIR), initialfile=f"{self.save_as}.png",
            defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if target:
            cv2.imwrite(target, picture)


def show_matches(parent: tk.Misc, picture, kept, dropped,
                 step: dict[str, Any], scale: float = 1.0) -> PictureWindow:
    """The 'what is this color step matching' window."""
    lines: list[tuple[str, str]] = []
    if kept:
        lines.append((f"Would be used, in order ({step.get('pick')}):", "good"))
        for number, (hit, note) in enumerate(kept, start=1):
            lines.append((f"  {number}. {hit.width}x{hit.height} at {hit.left}, "
                          f"{hit.top}   {hit.pixels} pixels   middle {hit.x}, "
                          f"{hit.y}   {note}", "info"))
            if hit.clipped:
                lines.append((f"      runs off the {hit.clipped} of the search "
                              "area, so it is cut off - widen the area", "warn"))
    else:
        lines.append(("Nothing would be used.", "warn"))
    if dropped:
        lines.append(("", "muted"))
        lines.append((f"Ignored ({len(dropped)}):", "muted"))
        for hit, why in dropped[:40]:
            lines.append((f"  {hit.width}x{hit.height} at {hit.left}, {hit.top}"
                          f"   {why}", "muted"))
        if len(dropped) > 40:
            lines.append((f"  ...and {len(dropped) - 40} more", "muted"))

    name = step.get("name") or step.get("type")
    return PictureWindow(
        parent, f"What matches - {name}", picture, lines,
        caption=("magenta = matched the color     green box = would be used"
                 "     dot = the middle of the box, which is not where it "
                 "clicks unless the step aims there"),
        scale=scale, save_as=f"what-matched-{_slug(name)}")


def show_click(parent: tk.Misc, picture, region, points, boxes,
               lines: list[tuple[str, str]], step: dict[str, Any],
               scale: float = 1.0) -> PictureWindow:
    """The 'where would this step click' window."""
    name = step.get("name") or step.get("type")
    marked = screen.mark_up(picture, region, points=points[:1], boxes=boxes,
                            faint=points[1:])
    return PictureWindow(
        parent, f"Where this would click - {name}", marked, lines,
        caption="yellow crosshair = the click     green = what it found",
        scale=scale, save_as=f"where-it-clicks-{_slug(name)}")


def _slug(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "step").lower()).strip("_")


class App:
    # Which builder draws each kind of field. A kind that isn't listed falls
    # back to a plain number box, which is wrong but silent -- so
    # tools/check_wiring.py checks every declared kind appears here.
    FIELD_BUILDERS = {
        "image": "_field_image", "point": "_field_point", "color": "_field_color",
        "region": "_field_region", "box": "_field_box", "choice": "_field_choice",
        "integer": "_field_integer", "offset": "_field_offset", "key": "_field_key",
        "pause": "_field_pause", "limit": "_field_limit",
        "multiline": "_field_multiline", "number": "_field_number",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.style = theme.apply(root)
        theme.dark_titlebar(root)
        root.title(APP_NAME)
        if ICON_PATH.exists():
            try:
                root.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass  # an icon is nice, not essential
        # We tell Windows we are DPI aware so our coordinates are true pixels,
        # which means Windows will not scale the window for us. Tk already
        # scales point-sized fonts, but the geometry is in raw pixels, so on a
        # high-DPI screen an unscaled window comes out postage-stamp sized.
        self.scale = _display_scale(root)
        root.geometry(f"{int(1180 * self.scale)}x{int(780 * self.scale)}")
        root.minsize(int(940 * self.scale), int(640 * self.scale))

        self.sequence = engine_mod.Sequence(name="New sequence")
        self.dirty = False
        self.selected = -1
        self.engine: engine_mod.Engine | None = None
        self.worker: threading.Thread | None = None
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.field_vars: dict[str, tk.Variable] = {}
        # The four editable numbers behind each region or box field.
        self.region_boxes: dict[str, tuple[dict[str, tk.Variable], dict]] = {}
        self.running = False
        self.lit_section: int | None = None   # row painted as the live section
        self.capturing = False                # picker is up: ignore the hotkey
        self._hotkey_was_down = False
        self._last_normal_geometry: str | None = None
        # Where each divider should sit, updated when you drag one.
        self.sash_wanted: dict[str, int | None] = {}

        self.dry_run = tk.BooleanVar(value=True)
        self.hide_while_running = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="Idle")
        self.cycle_text = tk.StringVar(value="Cycles: 0")

        self._build_toolbar()
        self._build_body()
        self._build_log()
        # Ctrl+Backspace and friends, which Tk leaves out of every entry.
        editing.install(root)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Control-s>", lambda _e: self.save())
        root.bind("<Control-o>", lambda _e: self.open())
        root.bind("<Control-d>", lambda _e: self.duplicate())
        root.bind("<F5>", lambda _e: self.toggle_run())
        root.bind("<Configure>", self._watch_geometry)

        state = self._read_state()
        self._restore_preferences(state)
        self._restore_sashes(state)
        self._restore_last_sequence(state)
        self.refresh_list()
        self._drain_job: str | None = self.root.after(80, self._drain_events)
        self._hotkey_job: str | None = self.root.after(HOTKEY_POLL_MS,
                                                       self._poll_hotkey)
        settings = self.sequence.settings
        self.log("Ready. Build a sequence on the left, then press Start.", "muted")
        if self._hotkey():
            self.log(f"{settings.toggle_key} starts and stops the run from "
                     "anywhere, even with another window in front.", "muted")
        self.log(f"Stop any time with the Stop button, {settings.abort_key}, or the "
                 "mouse in the top-left corner of the screen.", "muted")

    # -- construction ----------------------------------------------------

    def _build_toolbar(self) -> None:
        # No native menu bar: Windows draws that itself in light gray and
        # ignores Tk's colors, which looks broken against a dark window.
        files = ttk.Frame(self.root, padding=(12, 10, 12, 0))
        files.pack(fill="x")
        file_tips = {
            "New": "Start an empty sequence.",
            "Open...": "Open a saved sequence from the sequences folder.\nShortcut: Ctrl+O",
            "Save": "Save this sequence.\nShortcut: Ctrl+S",
            "Save as...": "Save this sequence under a new name.",
        }
        for label, command in (("New", self.new), ("Open...", self.open),
                               ("Save", self.save), ("Save as...", self.save_as)):
            button = ttk.Button(files, text=label, style="Tool.TButton", command=command)
            button.pack(side="left", padx=(0, 6))
            theme.tip(button, file_tips[label])
        settings_button = ttk.Button(files, text="Settings...", style="Tool.TButton",
                                     command=self.edit_settings)
        settings_button.pack(side="left", padx=(10, 0))
        theme.tip(settings_button,
                  "Pauses between steps and cycles, which key stops the run, and "
                  "whether to park the mouse after each step. These apply to the "
                  "whole sequence.")
        self.sequence_label = ttk.Label(files, text="", style="Muted.TLabel")
        self.sequence_label.pack(side="left", padx=(12, 0))

        bar = ttk.Frame(self.root, padding=(12, 10))
        bar.pack(fill="x")

        self.run_button = ttk.Button(bar, text="▶  Start", style="Accent.TButton",
                                     command=self.toggle_run)
        self.run_button.pack(side="left")
        self.run_tip = theme.tip(self.run_button, self._run_tip_text())

        dry = ttk.Checkbutton(bar, text="Dry run (log clicks, don't send them)",
                              variable=self.dry_run, command=self.save_preferences)
        dry.pack(side="left", padx=(14, 0))
        theme.tip(dry, "Does the full detection and writes every click it WOULD "
                       "send to the log, without sending any of them. Leave this "
                       "on until the log looks right.")

        minimize = ttk.Checkbutton(bar, text="Minimize while running (untick to watch)",
                                   variable=self.hide_while_running,
                                   command=self.save_preferences)
        minimize.pack(side="left", padx=(14, 0))
        theme.tip(minimize, "Pixie hides herself while running so she isn't sitting "
                            "on top of the thing she's clicking. She keeps going - "
                            "bring her back from the taskbar.")

        ttk.Label(bar, textvariable=self.cycle_text, style="Status.TLabel").pack(side="right")
        ttk.Label(bar, textvariable=self.status_text, style="Status.TLabel").pack(
            side="right", padx=(0, 18))

        ttk.Separator(self.root).pack(fill="x")

    def _run_tip_text(self) -> str:
        """The Start/Stop tooltip, which names the live hotkeys."""
        key = self.sequence.settings.abort_key
        hotkey = self._hotkey()
        stops = (f"To stop: this button, {key} from anywhere (even when another "
                 "window has focus), or shove the mouse into the top-left corner "
                 "of the screen.")
        if hotkey:
            stops = f"{hotkey} starts and stops the run from anywhere.\n\n" + stops
        if self.running:
            return "Stop the run.\n\n" + stops
        return ("Start the sequence. It loops from the top over and over until "
                "you stop it.\nShortcut: F5\n\n" + stops)

    def _refresh_run_tip(self) -> None:
        if hasattr(self, "run_tip"):
            self.run_tip.update(self._run_tip_text())

    def _build_body(self) -> None:
        """Sequence, editor and log, with draggable dividers between them.

        Everything used to be a fixed split: a 340px list, whatever was left
        for the editor, and nine lines of log. Which pane you need bigger
        depends entirely on what you are doing, so the dividers move.
        """
        self.split_down = ttk.PanedWindow(self.root, orient="vertical")
        self.split_down.pack(fill="both", expand=True, padx=12, pady=(10, 12))

        self.split_across = ttk.PanedWindow(self.split_down, orient="horizontal")
        self.split_down.add(self.split_across, weight=4)

        sequence_side = ttk.Frame(self.split_across, padding=(0, 0, 8, 0))
        editor_side = ttk.Frame(self.split_across, padding=(8, 0, 0, 0))
        self.split_across.add(sequence_side, weight=2)
        self.split_across.add(editor_side, weight=5)

        self._build_sequence_pane(sequence_side)
        self._build_editor_pane(editor_side)

    def _build_sequence_pane(self, parent: ttk.Frame) -> None:
        pane = ttk.Frame(parent)
        pane.pack(fill="both", expand=True)
        pane.rowconfigure(1, weight=1)
        pane.columnconfigure(0, weight=1)

        ttk.Label(pane, text="Sequence", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6))

        holder = tk.Frame(pane, bg=theme.PANEL, highlightthickness=0)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        self.listbox = theme.listbox(holder)
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=6)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.toggle_enabled())

        buttons = ttk.Frame(pane)
        buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        add = ttk.Button(buttons, text="Add step", style="Tool.TButton",
                         command=self._show_add_menu)
        add.pack(side="left")
        theme.tip(add, "Add a step after the selected one. Includes Section "
                       "dividers and Notes, which do nothing when run.")

        step_tips = {
            "↑": "Move the selected step up.",
            "↓": "Move the selected step down.",
            "Duplicate": "Copy the selected step, settings and all, and drop the "
                         "copy underneath it. The quickest way to build several "
                         "steps that differ only by their image or their "
                         "position.\nShortcut: Ctrl+D",
            "Remove": "Delete the selected step.",
        }
        for label, command in (("↑", self.move_up), ("↓", self.move_down),
                               ("Duplicate", self.duplicate), ("Remove", self.remove)):
            button = ttk.Button(buttons, text=label, style="Tool.TButton",
                                command=command, width=6 if len(label) == 1 else 10)
            button.pack(side="left", padx=(6, 0))
            theme.tip(button, step_tips[label])

        ttk.Label(pane, text="Double-click a step to turn it on or off.",
                  style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(6, 0))

    def _build_editor_pane(self, parent: ttk.Frame) -> None:
        pane = ttk.Frame(parent)
        pane.pack(fill="both", expand=True)
        pane.rowconfigure(1, weight=1)
        pane.columnconfigure(0, weight=1)

        header = ttk.Frame(pane)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        self.editor_title = ttk.Label(header, text="Step settings", style="Title.TLabel")
        self.editor_title.grid(row=0, column=0, sticky="w")
        self.explain_button = ttk.Button(header, text="What matches?",
                                         style="Tool.TButton",
                                         command=self.explain_step, state="disabled")
        self.explain_button.grid(row=0, column=1, sticky="e", padx=(0, 6))
        theme.tip(self.explain_button,
                  "Shows the search area as Pixie sees it: every pixel of the "
                  "color tinted, every patch boxed, and the ones she would "
                  "reject greyed out.\n\nUse it when something is matching that "
                  "should not be - a background that happens to share the "
                  "color is impossible to diagnose any other way.")
        self.click_button = ttk.Button(header, text="Show the click",
                                       style="Tool.TButton",
                                       command=self.preview_click, state="disabled")
        self.click_button.grid(row=0, column=2, sticky="e", padx=(0, 6))
        theme.tip(self.click_button,
                  "Works out where this step would click, right now, and shows "
                  "you the spot on a picture of the screen.\n\nIt runs the step "
                  "for real except for the click itself, so the crosshair is "
                  "where the click would actually go - not a second guess at it.")
        self.test_button = ttk.Button(header, text="Test this step", style="Tool.TButton",
                                      command=self.test_step, state="disabled")
        self.test_button.grid(row=0, column=3, sticky="e")
        theme.tip(self.test_button,
                  "Run only the selected step, once, and report what it found in "
                  "the log. The quickest way to tune an image or a color without "
                  "running the whole sequence.")

        outer = tk.Frame(pane, bg=theme.PANEL, highlightthickness=0)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(outer, bg=theme.PANEL, highlightthickness=0, borderwidth=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        editor_scroll = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        editor_scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=editor_scroll.set)

        self.editor = ttk.Frame(self.canvas, style="Panel.TFrame", padding=16)
        self.editor_window = self.canvas.create_window((0, 0), window=self.editor, anchor="nw")
        self.editor.bind("<Configure>", lambda _e: self._fit_editor())
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _on_canvas_resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.editor_window, width=event.width)
        self._fit_editor()

    def _fit_editor(self) -> None:
        """Keep the scroll region at least as tall as the canvas itself.

        A Tk canvas lets you scroll up until the bottom of its scroll region
        reaches the bottom of the widget. When a short step leaves the region
        shorter than the canvas, that is an invitation to scroll the editor
        down into a band of empty space -- and the scrollbar goes on claiming
        the whole thing is in view, so it looks like a glitch rather than a
        scroll position. Padding the region to the full height means there is
        nothing above the editor to scroll into.
        """
        region = self.canvas.bbox("all")
        if region is None:
            return
        self.canvas.configure(
            scrollregion=(0, 0, region[2], max(region[3], self.canvas.winfo_height())))

    def _build_log(self) -> None:
        pane = ttk.Frame(self.split_down, padding=(0, 8, 0, 0))
        self.split_down.add(pane, weight=1)
        pane.columnconfigure(0, weight=1)
        pane.rowconfigure(1, weight=1)

        head = ttk.Frame(pane)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Log", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(head, text="Clear", style="Tool.TButton",
                   command=self.clear_log).grid(row=0, column=1, sticky="e")

        holder = tk.Frame(pane, bg=theme.PANEL)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.log_text = theme.text(holder, height=8, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(holder, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        for level, color in LOG_COLORS.items():
            self.log_text.tag_configure(level, foreground=color)

    def _on_wheel(self, event: tk.Event) -> None:
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        target = widget
        while target is not None:
            if target is self.canvas or target is self.editor:
                self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
                return
            if target is self.log_text:
                self.log_text.yview_scroll(-1 * (event.delta // 120), "units")
                return
            target = getattr(target, "master", None)

    # -- logging ---------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        self.log_text.configure(state="normal")
        stamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"{stamp}  {message}\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # -- sequence list ---------------------------------------------------

    def _numbers(self) -> list[int | None]:
        """The number shown against each row. Dividers and notes get none."""
        return step_defs.display_numbers(self.sequence.steps)

    @staticmethod
    def _row_label(number: int | None, step: dict[str, Any]) -> tuple[str, str | None]:
        """How one step reads in the list, and what color it should be.

        If you have given a step your own name, that is what you want to read
        first. The generated summary still follows in brackets, because it is
        what tells you which image or key the step is actually using.
        """
        enabled = step.get("enabled", True)
        kind = step.get("type", "")
        if kind == "section":
            return "  " + step_defs.describe(step), theme.ACCENT
        if kind == "note":
            return "     " + step_defs.describe(step), theme.MUTED

        summary = step_defs.describe(step)
        name = str(step.get("name") or "").strip()
        step_type = step_defs.STEP_TYPES.get(kind)
        # Every step starts out named after its type. Only show the name when
        # it says something the type label does not.
        if name and step_type is not None and name != step_type.label:
            text = f"{name}   ({summary})" if summary else name
        else:
            text = summary

        prefix = f"{number:>2}. " if enabled else f"{number:>2}. - "
        return prefix + text, None if enabled else theme.DISABLED

    def _refresh_row(self, index: int) -> None:
        """Redraw a single row, leaving every other widget untouched.

        Rebuilding the whole editor here would destroy the entry the user is
        currently typing into, which takes the keyboard focus with it. That is
        why this exists separately from refresh_list.
        """
        if not (0 <= index < self.listbox.size()):
            return
        label, color = self._row_label(self._numbers()[index],
                                       self.sequence.steps[index])
        was_selected = index in self.listbox.curselection()
        self.listbox.delete(index)
        self.listbox.insert(index, label)
        if color:
            self.listbox.itemconfigure(index, foreground=color)
        if was_selected:
            self.listbox.selection_set(index)
        if index == self.lit_section:
            # Reinserting the row threw away its colors, and this one is the
            # section currently running.
            self.listbox.itemconfigure(index, background=theme.ACCENT_DARK,
                                       foreground="#ffffff")

    def refresh_list(self, keep: int | None = None) -> None:
        selection = keep if keep is not None else self.selected
        self.listbox.delete(0, "end")
        self.lit_section = None  # the rows it was painted on have gone
        numbers = self._numbers()
        for index, step in enumerate(self.sequence.steps):
            label, color = self._row_label(numbers[index], step)
            self.listbox.insert("end", label)
            if color:
                self.listbox.itemconfigure(index, foreground=color)
        if self.sequence.steps:
            selection = max(0, min(selection, len(self.sequence.steps) - 1))
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(selection)
            self.selected = selection
        else:
            self.selected = -1
        self._update_title()
        self.build_editor()

    def _on_select(self, _event: tk.Event) -> None:
        picks = self.listbox.curselection()
        if picks and picks[0] != self.selected:
            self.selected = picks[0]
            self.build_editor()

    def current_step(self) -> dict[str, Any] | None:
        if 0 <= self.selected < len(self.sequence.steps):
            return self.sequence.steps[self.selected]
        return None

    def _show_add_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=0, bg=theme.PANEL, fg=theme.FG,
                       activebackground=theme.ACCENT_DARK, activeforeground="#ffffff",
                       borderwidth=0)
        for key, step_type in step_defs.STEP_TYPES.items():
            menu.add_command(label=step_type.label,
                             command=lambda k=key: self.add_step(k))
        widget = self.root.focus_get() or self.root
        menu.tk_popup(widget.winfo_pointerx(), widget.winfo_pointery())

    def add_step(self, type_key: str) -> None:
        step = step_defs.new_step(type_key)
        at = self.selected + 1 if self.selected >= 0 else len(self.sequence.steps)
        self.sequence.steps.insert(at, step)
        self.mark_dirty()
        self.refresh_list(keep=at)
        self.log(f"Added {step_defs.location(self.sequence.steps, at)}", "muted")

    def duplicate(self) -> None:
        """Copy the selected step and select the copy, ready to be changed."""
        step = self.current_step()
        if step is None:
            return
        copied = json.loads(json.dumps(step))  # deep: regions and colors are lists

        # Two rows reading exactly the same thing are impossible to tell apart.
        # Only worth marking a name you chose yourself; a default one already
        # repeats all over the list.
        step_type = step_defs.STEP_TYPES.get(copied.get("type", ""))
        name = str(copied.get("name") or "").strip()
        if name and (step_type is None or name != step_type.label):
            copied["name"] = f"{name} copy"

        at = self.selected + 1
        self.sequence.steps.insert(at, copied)
        self.mark_dirty()
        self.refresh_list(keep=at)
        self.log(f"Duplicated {step_defs.location(self.sequence.steps, at)}. "
                 "Change its image or position to suit.", "muted")

    def remove(self) -> None:
        step = self.current_step()
        if step is None:
            return
        removed = self.sequence.steps.pop(self.selected)
        self.mark_dirty()
        self.refresh_list(keep=max(0, self.selected - 1))
        self._offer_to_delete_image(removed)

    def _offer_to_delete_image(self, removed: dict[str, Any]) -> None:
        """A deleted step's picture is dead weight, but only if nothing else
        uses it. Duplicated steps share one file, and so can two sequences."""
        relative = str(removed.get("image") or "")
        if not relative or self._image_is_used(relative):
            return
        path = Path(relative)
        if not path.is_absolute():
            path = PROJECT_DIR / path
        if not path.exists():
            return

        if not messagebox.askyesno(
                "Delete the picture too?",
                f"Nothing else uses {path.name}.\n\nDelete the file as well, or "
                "keep it in images/ in case you want it back?",
                default="no"):
            return
        try:
            path.unlink()
        except OSError as error:
            self.log(f"Could not delete {path.name}: {error}", "warn")
            return
        self.log(f"Deleted {path.name}.", "muted")

    def _image_is_used(self, relative: str) -> bool:
        """Is this picture referenced by any step, here or in another sequence?

        The sequence being edited is checked in memory, because what is on
        disk is out of date the moment you change anything. Every other saved
        sequence is checked as a file -- deleting a picture that another job
        depends on would be a nasty surprise for a bit of tidiness.
        """
        if any(str(step.get("image") or "") == relative
               for step in self.sequence.steps):
            return True

        here = self.sequence.path.resolve() if self.sequence.path else None
        for other in SEQUENCES_DIR.glob("*.json"):
            if here is not None and other.resolve() == here:
                continue
            try:
                data = json.loads(other.read_text(encoding="utf-8"))
                steps = data.get("steps", [])
            except (OSError, ValueError, AttributeError):
                continue  # unreadable: assume nothing, keep the picture
            if any(str(step.get("image") or "") == relative for step in steps):
                self.log(f"{Path(relative).name} is still used by {other.name}, "
                         "so it stays.", "muted")
                return True
        return False

    def move_up(self) -> None:
        self._move(-1)

    def move_down(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        at = self.selected
        to = at + delta
        if not (0 <= at < len(self.sequence.steps) and 0 <= to < len(self.sequence.steps)):
            return
        items = self.sequence.steps
        items[at], items[to] = items[to], items[at]
        self.mark_dirty()
        self.refresh_list(keep=to)

    def toggle_enabled(self) -> None:
        step = self.current_step()
        if step is None:
            return
        step["enabled"] = not step.get("enabled", True)
        self.mark_dirty()
        self.refresh_list()

    # -- step editor -----------------------------------------------------

    def build_editor(self) -> None:
        for child in self.editor.winfo_children():
            child.destroy()
        self.field_vars.clear()
        self.region_boxes.clear()
        # Start each step at its top, rather than wherever you had scrolled
        # the last one to.
        self.canvas.yview_moveto(0)

        step = self.current_step()
        if step is None:
            self.editor_title.configure(text="Step settings")
            self.test_button.configure(state="disabled")
            self.explain_button.configure(state="disabled")
            self.click_button.configure(state="disabled")
            ttk.Label(self.editor, style="Panel.TLabel", justify="left",
                      text="No step selected.\n\nPress “Add step” to start "
                           "building your sequence.").grid(row=0, column=0, sticky="w")
            return

        step_type = step_defs.STEP_TYPES.get(step.get("type", ""))
        if step_type is None:
            ttk.Label(self.editor, style="Panel.TLabel",
                      text=f"Unknown step type: {step.get('type')!r}").grid(row=0, column=0)
            return

        number = self._numbers()[self.selected]
        self.editor_title.configure(
            text=step_type.label if number is None
            else f"Step {number}: {step_type.label}")
        self.test_button.configure(state="normal")
        fields = step_type.field_map()
        searches_an_area = "region" in fields and "color" in step
        self.explain_button.configure(
            state="normal" if searches_an_area else "disabled")
        # Anything with a click count is a step that clicks something.
        self.click_button.configure(
            state="normal" if "clicks" in fields else "disabled")
        self.editor.columnconfigure(1, weight=1)

        ttk.Label(self.editor, text=step_type.blurb, style="Blurb.TLabel",
                  wraplength=int(560 * self.scale), justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        row = 1
        row = self._add_name_row(step, row)
        for spec in step_type.fields:
            row = self._add_field_row(step, spec, row)

    def _add_name_row(self, step: dict[str, Any], row: int) -> int:
        ttk.Label(self.editor, text="Name", style="Panel.TLabel").grid(
            row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        var = tk.StringVar(value=step.get("name", ""))
        entry = ttk.Entry(self.editor, textvariable=var)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        var.trace_add("write", lambda *_: self._set_value(step, "name", var.get()))
        self.field_vars["name"] = var
        return row + 1

    def _add_field_row(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> int:
        ttk.Label(self.editor, text=spec.label, style="Panel.TLabel").grid(
            row=row, column=0, sticky="w", pady=4, padx=(0, 12))

        builder = getattr(self, self.FIELD_BUILDERS.get(spec.kind, "_field_number"))
        # A builder returns how many extra rows it used, so a field can put a
        # preview underneath itself.
        row += 1 + (builder(step, spec, row) or 0)

        if spec.hint:
            ttk.Label(self.editor, text=spec.hint, style="Blurb.TLabel",
                      wraplength=int(520 * self.scale), justify="left").grid(
                row=row, column=1, columnspan=2, sticky="w", pady=(0, 8))
            row += 1
        return row

    def _set_value(self, step: dict[str, Any], key: str, value: Any) -> None:
        if step.get(key) == value:
            return
        step[key] = value
        self.mark_dirty()
        # Only the one row's text can have changed, so redraw only that row.
        # Refreshing the whole list would rebuild the editor and pull the
        # focus out of whatever the user is typing in.
        self._refresh_row(self.selected)

    # Individual field widgets .........................................

    def _readonly_entry(self, row: int, var: tk.StringVar) -> ttk.Entry:
        entry = ttk.Entry(self.editor, textvariable=var, state="readonly")
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _field_image(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> int:
        var = tk.StringVar(value=str(step.get(spec.key) or ""))
        self._readonly_entry(row, var)

        preview = ttk.Frame(self.editor, style="Panel.TFrame")
        preview.grid(row=row + 1, column=1, columnspan=2, sticky="w", pady=(2, 6))

        ttk.Button(self.editor, text="Capture...", style="Tool.TButton",
                   command=lambda: self._capture_image(step, spec, var, preview)).grid(
            row=row, column=2, sticky="w", padx=(8, 0))

        self._show_image_preview(preview, step.get(spec.key))
        self.field_vars[spec.key] = var
        return 1

    def _show_image_preview(self, holder: ttk.Frame, relative: Any) -> None:
        """Draw the captured image itself, so you can see which one this is.

        A path like 'images/click_an_image_if_it_appears_2.png' tells you
        almost nothing when several steps look similar.
        """
        for child in holder.winfo_children():
            child.destroy()

        if not relative:
            ttk.Label(holder, text="nothing captured yet",
                      style="Blurb.TLabel").pack(anchor="w")
            return

        path = Path(relative)
        if not path.is_absolute():
            path = PROJECT_DIR / path
        if not path.exists():
            ttk.Label(holder, text=f"file is missing: {relative}",
                      foreground=theme.ERROR, background=theme.PANEL,
                      font=theme.FONT_SMALL).pack(anchor="w")
            return

        try:
            from PIL import Image, ImageTk

            with Image.open(path) as opened:
                full_width, full_height = opened.size
                shown = opened.copy()
            limit = (int(300 * self.scale), int(130 * self.scale))
            shown.thumbnail(limit, Image.LANCZOS)
            photo = ImageTk.PhotoImage(shown)
        except Exception as error:  # noqa: BLE001 - a bad file should not crash the editor
            ttk.Label(holder, text=f"cannot read the image: {error}",
                      foreground=theme.ERROR, background=theme.PANEL,
                      font=theme.FONT_SMALL).pack(anchor="w")
            return

        frame = tk.Frame(holder, bg=theme.BORDER)
        frame.pack(anchor="w")
        label = tk.Label(frame, image=photo, bd=0, bg=theme.PANEL)
        label.image = photo          # Tk drops the image unless a reference lives on
        label.pack(padx=1, pady=1)

        note = f"{full_width} x {full_height} pixels"
        if (full_width, full_height) != shown.size:
            note += f"  (shown at {shown.size[0]} x {shown.size[1]})"
        ttk.Label(holder, text=note, style="Blurb.TLabel").pack(anchor="w", pady=(3, 0))

    def _field_point(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        value = step.get(spec.key)
        var = tk.StringVar(value=f"{value[0]}, {value[1]}" if value else "not set")
        self._readonly_entry(row, var)
        ttk.Button(self.editor, text="Pick...", style="Tool.TButton",
                   command=lambda: self._capture_point(step, spec, var)).grid(
            row=row, column=2, sticky="w", padx=(8, 0))
        self.field_vars[spec.key] = var

    def _field_color(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        value = step.get(spec.key) or [255, 255, 255]
        holder = ttk.Frame(self.editor, style="Panel.TFrame")
        holder.grid(row=row, column=1, sticky="ew", pady=4)
        holder.columnconfigure(1, weight=1)

        swatch = tk.Frame(holder, width=int(64 * self.scale),
                          height=int(30 * self.scale), highlightthickness=1,
                          highlightbackground=theme.BORDER,
                          bg="#%02x%02x%02x" % tuple(value))
        swatch.grid(row=0, column=0, padx=(0, 10))
        swatch.grid_propagate(False)
        var = tk.StringVar(value=self._color_text(value))
        ttk.Entry(holder, textvariable=var, state="readonly").grid(row=0, column=1, sticky="ew")

        ttk.Button(self.editor, text="Pick...", style="Tool.TButton",
                   command=lambda: self._capture_color(step, spec, var, swatch)).grid(
            row=row, column=2, sticky="w", padx=(8, 0))
        self.field_vars[spec.key] = var

    @staticmethod
    def _color_text(rgb: Any) -> str:
        r, g, b = (int(v) for v in rgb)
        return f"RGB({r}, {g}, {b})    #{r:02x}{g:02x}{b:02x}"

    def _field_region(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> int:
        return self._region_field(step, spec, row, whole_screen=True)

    def _field_box(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> int:
        """A box to click inside. Same picker, but 'whole screen' makes no
        sense here -- it would mean clicking anywhere at all."""
        return self._region_field(step, spec, row, whole_screen=False)

    def _region_field(self, step: dict[str, Any], spec: step_defs.Field, row: int,
                      whole_screen: bool) -> int:
        """A box, as four numbers you can edit plus a button to drag a new one.

        Dragging is how you make a box; typing is how you fix one. Nudging an
        edge by ten pixels should not mean re-picking the whole thing.
        """
        empty = "whole screen (slower)" if whole_screen else "nothing picked yet"
        value = step.get(spec.key)
        var = tk.StringVar(value=self._region_label(value, empty))
        self._readonly_entry(row, var)

        holder = ttk.Frame(self.editor, style="Panel.TFrame")
        holder.grid(row=row, column=2, sticky="w", padx=(8, 0))
        ttk.Button(holder, text="Pick...", style="Tool.TButton",
                   command=lambda: self._capture_region(step, spec, var,
                                                        boxes)).pack(side="left")
        if whole_screen:
            ttk.Button(holder, text="Whole screen", style="Tool.TButton",
                       command=lambda: self._clear_region(step, spec, var, boxes,
                                                          empty)).pack(
                side="left", padx=(6, 0))

        edit = ttk.Frame(self.editor, style="Panel.TFrame")
        edit.grid(row=row + 1, column=1, columnspan=2, sticky="w", pady=(2, 6))
        current = list(value) if value else [0, 0, 0, 0]
        boxes: dict[str, tk.StringVar] = {}
        editing = {"live": False}  # stop our own writes from re-entering

        def store(*_args: object) -> None:
            if editing["live"]:
                return
            try:
                numbers = [int(float(boxes[name].get()))
                           for name in ("left", "top", "width", "height")]
            except (TypeError, ValueError):
                return  # mid-typing, or just a minus sign so far
            if numbers[2] <= 0 or numbers[3] <= 0:
                return  # a box with no width is not a box yet
            self._set_value(step, spec.key, numbers)
            var.set(self._region_label(numbers, empty))

        for label, name in (("left", "left"), ("top", "top"),
                            ("width", "width"), ("height", "height")):
            ttk.Label(edit, text=f"  {label} ", style="Blurb.TLabel").pack(side="left")
            boxes[name] = tk.StringVar(
                value=str(current[("left", "top", "width", "height").index(name)]))
            ttk.Entry(edit, textvariable=boxes[name], width=6).pack(side="left")
            boxes[name].trace_add("write", store)

        self.region_boxes[spec.key] = (boxes, editing)
        self.field_vars[spec.key] = var
        return 1

    def _fill_region_boxes(self, key: str, value: Any) -> None:
        """Put new numbers in the four boxes without them writing back."""
        entry = self.region_boxes.get(key)
        if entry is None:
            return
        boxes, editing = entry
        editing["live"] = True
        try:
            for name, number in zip(("left", "top", "width", "height"),
                                    value or [0, 0, 0, 0]):
                boxes[name].set(str(number))
        finally:
            editing["live"] = False

    def _clear_region(self, step: dict[str, Any], spec: step_defs.Field,
                      var: tk.StringVar, _boxes: Any, empty: str) -> None:
        self._set_value(step, spec.key, None)
        var.set(self._region_label(None, empty))
        self._fill_region_boxes(spec.key, None)

    @staticmethod
    def _region_label(value: Any, empty: str = "whole screen (slower)") -> str:
        if not value:
            return empty
        left, top, width, height = value
        return f"{width}x{height} at {left}, {top}"

    def _field_offset(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        """Two numbers, not a screen position -- an offset is a delta."""
        value = step.get(spec.key) or [0, 0]
        holder = ttk.Frame(self.editor, style="Panel.TFrame")
        holder.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)

        x_var = tk.StringVar(value=str(value[0]))
        y_var = tk.StringVar(value=str(value[1]))

        def store(*_args: object) -> None:
            try:
                self._set_value(step, spec.key, [int(float(x_var.get())),
                                                 int(float(y_var.get()))])
            except (TypeError, ValueError):
                pass  # mid-typing, or just a minus sign so far

        ttk.Label(holder, text="X", style="Panel.TLabel").pack(side="left")
        ttk.Entry(holder, textvariable=x_var, width=7).pack(side="left", padx=(6, 2))
        ttk.Label(holder, text="→ right", style="Blurb.TLabel").pack(side="left")

        ttk.Label(holder, text="     Y", style="Panel.TLabel").pack(side="left")
        ttk.Entry(holder, textvariable=y_var, width=7).pack(side="left", padx=(6, 2))
        ttk.Label(holder, text="↓ down", style="Blurb.TLabel").pack(side="left")

        x_var.trace_add("write", store)
        y_var.trace_add("write", store)
        self.field_vars[spec.key] = x_var

    def _field_pause(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        """Either 'use the sequence default' (stored as None) or a [min, max]."""
        value = step.get(spec.key)
        holder = ttk.Frame(self.editor, style="Panel.TFrame")
        holder.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)

        settings = self.sequence.settings
        # A section's pause overrides the between-sections default, not the
        # between-steps one, so it must quote the right number back at you.
        if step.get("type") == "section":
            default_text = _range_text(settings.section_pause_min,
                                       settings.section_pause_max)
        else:
            default_text = _range_text(settings.step_pause_min, settings.step_pause_max)
        use_default = tk.BooleanVar(value=value is None)
        low = tk.StringVar(value=str(value[0]) if value else "0.5")
        high = tk.StringVar(value=str(value[1]) if value else "1.5")
        entries: list[ttk.Entry] = []

        def store(*_args: object) -> None:
            for entry in entries:
                entry.configure(state="disabled" if use_default.get() else "normal")
            if use_default.get():
                self._set_value(step, spec.key, None)
                return
            try:
                self._set_value(step, spec.key,
                                [max(0.0, float(low.get())), max(0.0, float(high.get()))])
            except (TypeError, ValueError):
                pass  # mid-typing

        ttk.Checkbutton(holder, text=f"Use the sequence default ({default_text})",
                        variable=use_default, command=store).pack(anchor="w")

        line = ttk.Frame(holder, style="Panel.TFrame")
        line.pack(anchor="w", pady=(4, 0))
        ttk.Label(line, text="or instead, between", style="Panel.TLabel").pack(side="left")
        for var in (low, high):
            entry = ttk.Entry(line, textvariable=var, width=6)
            entry.pack(side="left", padx=6)
            entries.append(entry)
            if var is low:
                ttk.Label(line, text="and", style="Panel.TLabel").pack(side="left")
        ttk.Label(line, text="seconds", style="Panel.TLabel").pack(side="left", padx=(6, 0))

        low.trace_add("write", store)
        high.trace_add("write", store)
        for entry in entries:
            entry.configure(state="disabled" if use_default.get() else "normal")
        self.field_vars[spec.key] = low

    def _field_limit(self, step: dict[str, Any], spec: step_defs.Field,
                     row: int) -> None:
        """One optional number: either off, or a value. Stored as None or a float."""
        value = step.get(spec.key)
        holder = ttk.Frame(self.editor, style="Panel.TFrame")
        holder.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)

        off = tk.BooleanVar(value=not value)
        amount = tk.StringVar(value=str(value) if value else "3")

        check = ttk.Checkbutton(holder, text="Let every step decide for itself",
                                variable=off)
        check.pack(anchor="w")
        line = ttk.Frame(holder, style="Panel.TFrame")
        line.pack(anchor="w", pady=(4, 0))
        ttk.Label(line, text="or instead, never wait longer than",
                  style="Panel.TLabel").pack(side="left")
        # Parented to the line, not the holder: a widget packs inside its own
        # parent whatever you pack it into, so getting this wrong puts the box
        # on its own row above the sentence it belongs in.
        entry = ttk.Entry(line, textvariable=amount, width=6)
        entry.pack(side="left", padx=6)
        ttk.Label(line, text="seconds", style="Panel.TLabel").pack(side="left")

        def store(*_args: object) -> None:
            entry.configure(state="disabled" if off.get() else "normal")
            if off.get():
                self._set_value(step, spec.key, None)
                return
            try:
                self._set_value(step, spec.key, max(0.0, float(amount.get())))
            except (TypeError, ValueError):
                pass  # mid-typing

        check.configure(command=store)
        amount.trace_add("write", store)
        entry.configure(state="disabled" if off.get() else "normal")
        self.field_vars[spec.key] = amount

    def _field_multiline(self, step: dict[str, Any], spec: step_defs.Field,
                         row: int) -> None:
        box = theme.text(self.editor, height=6, wrap="word")
        box.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        box.insert("1.0", str(step.get(spec.key) or ""))

        def store(_event: tk.Event | None = None) -> None:
            self._set_value(step, spec.key, box.get("1.0", "end-1c"))

        box.bind("<KeyRelease>", store)
        box.bind("<FocusOut>", store)

    def _field_key(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        var = tk.StringVar(value=str(step.get(spec.key) or ""))
        self._readonly_entry(row, var)
        ttk.Button(self.editor, text="Press a key...", style="Tool.TButton",
                   command=lambda: self._capture_key(step, spec, var)).grid(
            row=row, column=2, sticky="w", padx=(8, 0))
        self.field_vars[spec.key] = var

    def _capture_key(self, step: dict[str, Any], spec: step_defs.Field,
                     var: tk.StringVar) -> None:
        chosen = KeyGrabber(self.root, self.scale).run()
        if chosen is None:
            return
        self._set_value(step, spec.key, chosen)
        var.set(chosen)
        self.log(f"Key set to {chosen}", "good")

    def _field_choice(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> int:
        """A dropdown that reads as English but stores the short value.

        The file keeps 'next_section'; the box says 'Move on to the next
        section'. Nobody should have to learn our vocabulary to use this.
        """
        labels = step_defs.CHOICE_LABELS.get(spec.key, {})
        shown = {value: labels.get(value, value) for value in spec.choices}
        stored = {text: value for value, text in shown.items()}

        current = str(step.get(spec.key, spec.default))
        var = tk.StringVar(value=shown.get(current, current))
        combo = ttk.Combobox(self.editor, textvariable=var, values=list(shown.values()),
                             state="readonly")
        combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        var.trace_add("write",
                      lambda *_: self._set_value(step, spec.key,
                                                 stored.get(var.get(), var.get())))
        self.field_vars[spec.key] = var

        if spec.key not in step_defs.CHOICE_NOTES:
            return 0

        # The consequence of the choice, spelled out under the box with this
        # sequence's real section names in it. "Start the whole sequence
        # again" is ambiguous however it is phrased; "Abandons 'In Game' and
        # starts the whole script again from 'Before Game'" is not.
        def explain(value: str) -> str:
            return step_defs.outcome_note(value, self.sequence.steps, self.selected)

        note = ttk.Label(self.editor, style="Blurb.TLabel", justify="left",
                         wraplength=int(520 * self.scale), text=explain(current))
        note.grid(row=row + 1, column=1, columnspan=2, sticky="w", pady=(0, 6))
        var.trace_add("write", lambda *_: note.configure(
            text=explain(stored.get(var.get(), var.get()))))
        return 1

    def _field_integer(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        var = tk.StringVar(value=str(step.get(spec.key, spec.default)))
        spin = ttk.Spinbox(self.editor, from_=spec.minimum, to=spec.maximum,
                           textvariable=var, width=10)
        spin.grid(row=row, column=1, sticky="w", pady=4)
        var.trace_add("write", lambda *_: self._set_number(step, spec.key, var.get(), int))
        self.field_vars[spec.key] = var

    def _field_number(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        var = tk.StringVar(value=str(step.get(spec.key, spec.default)))
        entry = ttk.Entry(self.editor, textvariable=var, width=12)
        entry.grid(row=row, column=1, sticky="w", pady=4)
        var.trace_add("write", lambda *_: self._set_number(step, spec.key, var.get(), float))
        self.field_vars[spec.key] = var

    def _set_number(self, step: dict[str, Any], key: str, raw: str, cast: type) -> None:
        try:
            self._set_value(step, key, cast(float(raw)))
        except (TypeError, ValueError):
            pass  # mid-typing; leave the stored value alone

    # -- capture ---------------------------------------------------------

    def _pick(self, mode: str) -> capture.Picker | None:
        """Hide the window, freeze the screen, and let the user point at something."""
        if self.running:
            messagebox.showinfo("Running", "Stop the run before capturing.")
            return None
        self.capturing = True  # the start/stop key must not fire mid-capture
        # Hiding and showing a window loses whether it was maximized, and puts
        # it back at whatever size it was before that. Remember both and put
        # them back, or capturing anything shrinks the window.
        was_maximized = self.root.state() == "zoomed"
        was_at = self._last_normal_geometry or self._current_geometry()
        self.root.withdraw()
        self.root.update()
        time.sleep(0.35)  # let the desktop repaint before we photograph it
        picker = None
        try:
            picker = capture.Picker(mode, parent=self.root)
            picker.run()
        except Exception as error:  # noqa: BLE001 - tell the user, don't vanish
            self.log(f"The screen picker could not open: {error!r}", "error")
        finally:
            self.capturing = False
            self.root.deiconify()
            self._restore_window(was_at, was_maximized)
            self.root.lift()

        # "Nothing happened" is the hardest thing to report, so say it.
        if picker is not None and picker.result is None:
            self.log("Nothing picked, so nothing changed. Drag a box, or click "
                     "a spot - Escape cancels.", "muted")
        return picker

    def _restore_window(self, geometry: str | None, maximized: bool) -> None:
        try:
            if geometry:
                self.root.geometry(geometry)
            if maximized:
                self.root.state("zoomed")
        except tk.TclError:
            pass  # a window we cannot place is still a usable window

    def _unique_image_path(self, hint: str) -> Path:
        IMAGES_DIR.mkdir(exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", hint.lower()).strip("_") or "image"
        candidate = IMAGES_DIR / f"{slug}.png"
        counter = 2
        while candidate.exists():
            candidate = IMAGES_DIR / f"{slug}_{counter}.png"
            counter += 1
        return candidate

    def _capture_image(self, step: dict[str, Any], spec: step_defs.Field,
                       var: tk.StringVar, preview: ttk.Frame | None = None) -> None:
        picker = self._pick("region")
        if picker is None or picker.result is None:
            return
        import cv2  # local: only needed when actually saving a capture

        x, y, w, h = picker.result
        path = self._unique_image_path(step.get("name") or step["type"])
        cv2.imwrite(str(path), picker.frame[y : y + h, x : x + w])
        relative = path.relative_to(PROJECT_DIR).as_posix()
        self._set_value(step, spec.key, relative)
        var.set(relative)
        if preview is not None:
            self._show_image_preview(preview, relative)
        self.log(f"Saved {relative}  ({w}x{h})", "good")
        if w * h < 300:
            self.log("That is a very small image - it may match the wrong thing. "
                     "Capture a bigger, more distinctive area if it misbehaves.", "warn")

    def _capture_point(self, step: dict[str, Any], spec: step_defs.Field,
                       var: tk.StringVar) -> None:
        picker = self._pick("point")
        if picker is None or picker.result is None:
            return
        x, y = picker.to_absolute(picker.result)
        self._set_value(step, spec.key, [x, y])
        var.set(f"{x}, {y}")
        self.log(f"{spec.label}: {x}, {y}", "good")

    def _capture_color(self, step: dict[str, Any], spec: step_defs.Field,
                        var: tk.StringVar, swatch: tk.Frame) -> None:
        picker = self._pick("color")
        if picker is None or picker.result is None:
            return
        rgb = picker.color_at(*picker.result)
        x, y = picker.to_absolute(picker.result)
        self._set_value(step, spec.key, list(rgb))
        var.set(self._color_text(rgb))
        swatch.configure(bg="#%02x%02x%02x" % rgb)
        self.log(f"Color RGB{rgb} sampled at {x}, {y}", "good")
        if step.get("pos") is None:
            self._set_value(step, "pos", [x, y])
            if "pos" in self.field_vars:
                self.field_vars["pos"].set(f"{x}, {y}")
            self.log(f"Also set this step's watch position to {x}, {y}", "muted")

    def _capture_region(self, step: dict[str, Any], spec: step_defs.Field,
                        var: tk.StringVar, _boxes: Any = None) -> None:
        picker = self._pick("area")
        if picker is None or picker.result is None:
            return
        left, top, width, height = picker.to_absolute(picker.result)
        self._set_value(step, spec.key, [left, top, width, height])
        var.set(self._region_label([left, top, width, height]))
        self._fill_region_boxes(spec.key, [left, top, width, height])
        if spec.kind == "box":
            self.log(f"Click box {width}x{height} at {left}, {top} - "
                     f"{width * height:,} pixels to choose from.", "good")
            return
        full_w, full_h = screen.virtual_bounds()[2:]
        share = (width * height) / (full_w * full_h)
        self.log(f"Search area {width}x{height} at {left}, {top} "
                 f"- about {1 / share:.0f}x faster than the whole screen.", "good")

    # -- files -----------------------------------------------------------

    def mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        mark = " *" if self.dirty else ""
        where = self.sequence.path.name if self.sequence.path else "unsaved"
        self.root.title(f"{APP_NAME} - {self.sequence.name} ({where}){mark}")
        if hasattr(self, "sequence_label"):
            count = len(self.sequence.steps)
            self.sequence_label.configure(
                text=f"{where}{mark}   ·   {count} step{'s' if count != 1 else ''}")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", f"Save changes to '{self.sequence.name}' first?")
        if answer is None:
            return False
        if answer:
            return self.save()
        return True

    def edit_settings(self) -> None:
        if self.running:
            messagebox.showinfo("Running", "Stop the run before changing settings.")
            return
        if SettingsDialog(self.root, self.sequence.settings, self.scale).run():
            self.mark_dirty()
            self._refresh_run_tip()
            # These live in the sequence file, so they are only remembered if
            # that file is written. Leaving it to the user to notice meant
            # settings appeared to reset themselves on the next open.
            if self.sequence.path is not None:
                self.save()
            else:
                self.log("Settings are saved with the sequence - save it to "
                         "keep them.", "warn")
            s = self.sequence.settings
            self.log(f"Settings: {_range_text(s.step_pause_min, s.step_pause_max)} "
                     f"after each step, "
                     f"{_range_text(s.section_pause_min, s.section_pause_max)} "
                     f"between sections, "
                     f"{_range_text(s.cycle_pause_min, s.cycle_pause_max)} "
                     f"between cycles, start/stop key {s.toggle_key}, "
                     f"stop key {s.abort_key}, "
                     f"cursor {PARK_LABELS.get(s.park_mouse, 'left alone')}.", "good")

    def new(self) -> None:
        if not self._confirm_discard():
            return
        self.sequence = engine_mod.Sequence(name="New sequence")
        self.dirty = False
        self.selected = -1
        self.refresh_list()
        self.log("Started a new sequence.", "muted")

    def open(self) -> None:
        if not self._confirm_discard():
            return
        SEQUENCES_DIR.mkdir(exist_ok=True)
        path = filedialog.askopenfilename(
            title="Open sequence", initialdir=str(SEQUENCES_DIR),
            filetypes=[("Sequences", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self._load(Path(path))

    def _load(self, path: Path) -> None:
        try:
            self.sequence = engine_mod.Sequence.load(path)
        except (OSError, json.JSONDecodeError) as error:
            messagebox.showerror("Could not open", f"{path}\n\n{error}")
            return
        self.dirty = False
        self.selected = 0
        self.refresh_list(keep=0)
        self._remember(path)
        self.log(f"Opened {path.name} ({len(self.sequence.steps)} steps).", "good")

    def save(self) -> bool:
        if self.sequence.path is None:
            return self.save_as()
        self.sequence.save()
        self.dirty = False
        self._update_title()
        self.log(f"Saved {self.sequence.path.name}.", "good")
        return True

    def save_as(self) -> bool:
        SEQUENCES_DIR.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Save sequence", initialdir=str(SEQUENCES_DIR),
            defaultextension=".json", initialfile=f"{self.sequence.name}.json",
            filetypes=[("Sequences", "*.json")])
        if not path:
            return False
        target = Path(path)
        self.sequence.name = target.stem
        self.sequence.save(target)
        self.dirty = False
        self._update_title()
        self._remember(target)
        self.log(f"Saved {target.name}.", "good")
        return True

    # -- remembering how you left things ---------------------------------

    def _read_state(self) -> dict[str, Any]:
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_state(self, **changes: Any) -> None:
        """Merge into the state file, so one setting never clobbers another."""
        state = self._read_state()
        state.update(changes)
        try:
            STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass  # remembering is a convenience, not worth an error dialog

    def _remember(self, path: Path) -> None:
        self._write_state(last=str(path))

    def save_preferences(self) -> None:
        self._write_state(
            dry_run=bool(self.dry_run.get()),
            minimize_while_running=bool(self.hide_while_running.get()),
            geometry=self._last_normal_geometry or self._current_geometry(),
            maximized=self._is_maximized(),
            **self._sash_positions(),
        )

    def _sash_positions(self) -> dict[str, int]:
        """Where the two dividers sit, so they come back where you put them."""
        where = {}
        for name, paned in (("split_across", self.split_across),
                            ("split_down", self.split_down)):
            try:
                where[name] = int(paned.sashpos(0))
            except (tk.TclError, IndexError):
                wanted = self.sash_wanted.get(name)
                if wanted is not None:
                    where[name] = wanted  # never laid out, but we know the plan
        return where

    def _restore_sashes(self, state: dict[str, Any]) -> None:
        """Hold each divider where it was put.

        Setting a sash once at startup does not work: the window has not
        reached its restored size yet, so the position gets clamped against a
        window that is still small and ends up somewhere else. Instead each
        divider is pinned to a remembered position and re-applied as the
        window settles, until you drag it -- at which point where you dragged
        it to becomes the remembered position.
        """
        for name, paned, share in (("split_across", self.split_across, 0.32),
                                   ("split_down", self.split_down, 0.72)):
            wanted = state.get(name)
            self.sash_wanted[name] = wanted if isinstance(wanted, int) else None
            self._pin_sash(name, paned, share)

    def _pin_sash(self, name: str, paned: ttk.PanedWindow, share: float) -> None:
        horizontal = str(paned.cget("orient")) == "horizontal"
        placed = {"done": False}

        def room() -> int:
            return paned.winfo_width() if horizontal else paned.winfo_height()

        def apply(_event: tk.Event | None = None) -> None:
            if placed["done"]:
                return  # the user owns it from here
            space = room()
            if space <= 240:
                return  # still being laid out; a later Configure will do it
            wanted = self.sash_wanted.get(name)
            if wanted is None:
                wanted = int(space * share)  # first run: a sensible default
            try:
                paned.sashpos(0, max(120, min(wanted, space - 120)))
                placed["done"] = True
            except tk.TclError:
                pass

        def dragged(_event: tk.Event) -> None:
            try:
                self.sash_wanted[name] = int(paned.sashpos(0))
                placed["done"] = True
            except tk.TclError:
                pass

        paned.bind("<Configure>", apply, add="+")
        paned.bind("<ButtonRelease-1>", dragged, add="+")
        # The window has its restored size by now, so the position we put the
        # divider at is measured against the window it will actually be in.
        self.root.update_idletasks()
        apply()

    def _is_maximized(self) -> bool:
        try:
            return self.root.state() == "zoomed"
        except tk.TclError:
            return False

    def _current_geometry(self) -> str | None:
        """Size and position, unless minimized or maximized right now."""
        try:
            if self.root.state() != "normal":
                return None
            return self.root.winfo_geometry()
        except tk.TclError:
            return None

    def _watch_geometry(self, event: tk.Event) -> None:
        """Keep the last un-maximized size and position as the window moves.

        Reading it only when closing is too late: a window closed while
        maximized has no ordinary size to report, and one closed after being
        maximized and restored reports whatever Tk last felt like. Catching it
        as it changes means there is always a sensible size to come back to.
        """
        if event.widget is not self.root:
            return  # every child widget reports its own Configure events
        current = self._current_geometry()
        if current:
            self._last_normal_geometry = current

    def _restore_preferences(self, state: dict[str, Any]) -> None:
        if isinstance(state.get("dry_run"), bool):
            self.dry_run.set(state["dry_run"])
        if isinstance(state.get("minimize_while_running"), bool):
            self.hide_while_running.set(state["minimize_while_running"])

        geometry = state.get("geometry")
        if isinstance(geometry, str) and self._geometry_is_on_screen(geometry):
            self._last_normal_geometry = geometry
            self._restore_window(geometry, bool(state.get("maximized")))
        elif state.get("maximized"):
            # The saved size was unusable, but "it was maximized" still holds.
            self._restore_window(None, True)

    def _geometry_is_on_screen(self, geometry: str) -> bool:
        """Reject a saved position that would open the window where it can't be seen.

        Monitors get unplugged and resolutions change. A window restored to a
        screen that no longer exists is invisible and feels like a crash.
        """
        match = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", geometry)
        if not match:
            return False
        width, height, left, top = (int(part) for part in match.groups())
        if width < 400 or height < 300:
            return False

        desktop_left, desktop_top, desktop_w, desktop_h = screen.virtual_bounds()
        # Require a decent slice of the title bar to land inside the desktop,
        # which is what you need to be able to grab and move it.
        visible_x = min(left + width, desktop_left + desktop_w) - max(left, desktop_left)
        visible_y = min(top + 40, desktop_top + desktop_h) - max(top, desktop_top)
        return visible_x >= 200 and visible_y >= 20

    def _restore_last_sequence(self, state: dict[str, Any]) -> None:
        last = state.get("last")
        if not isinstance(last, str):
            return
        path = Path(last)
        if path.exists():
            self._load(path)

    # -- running ---------------------------------------------------------

    def toggle_run(self) -> None:
        if self.running:
            self.stop_run()
        else:
            self.start_run()

    def _hotkey(self) -> str | None:
        """The start/stop key, or None if there isn't one.

        A file edited by hand can set it to the same key as the stop key,
        which would start the run and abort it in the same breath, leaving
        Pixie apparently unable to start. Settings will not let you do that;
        this makes sure a file cannot either.
        """
        key = str(self.sequence.settings.toggle_key or "").strip()
        if key.lower() in ("", "off", "none"):
            return None
        return None if key == self.sequence.settings.abort_key else key

    def _poll_hotkey(self) -> None:
        """Watch for the start/stop key while another window has focus.

        Tk only sees keys aimed at our own window, and the whole point of this
        one is to work while you are looking at the application being clicked.
        So we ask Windows directly, and act on the press rather than the hold,
        or one long press would start and stop the run a dozen times.
        """
        key = self._hotkey()
        try:
            down = bool(key) and not self.capturing and screen.key_pressed(key)
        except (ValueError, OSError):
            down = False  # an unknown key name: treat it as no hotkey at all
        if down and not self._hotkey_was_down:
            self.toggle_run()
        self._hotkey_was_down = down
        self._hotkey_job = self.root.after(HOTKEY_POLL_MS, self._poll_hotkey)

    def start_run(self) -> None:
        problems = self.sequence.problems()
        if problems:
            for problem in problems:
                self.log(problem, "error")
            messagebox.showwarning(
                "Not ready", "This sequence cannot run yet:\n\n" + "\n".join(problems))
            return

        self.engine = engine_mod.Engine(
            self.sequence, emit=self.events.put, dry_run=self.dry_run.get(),
            base_dir=PROJECT_DIR)
        self.running = True
        self.run_button.configure(text="■  Stop", style="Stop.TButton")
        self.status_text.set("Running")
        self.cycle_text.set("Cycles: 0")
        self._refresh_run_tip()
        self.root.title(f"{APP_NAME} - running")
        self.test_button.configure(state="disabled")
        self.explain_button.configure(state="disabled")
        self.click_button.configure(state="disabled")

        self.worker = threading.Thread(target=self.engine.run, daemon=True)
        self.worker.start()
        if self.hide_while_running.get():
            stop_keys = " or ".join(filter(None, (self._hotkey(),
                                                  self.sequence.settings.abort_key)))
            self.log("Minimizing to stay out of the way - Pixie is still running. "
                     f"Bring her back from the taskbar, or press {stop_keys} to "
                     "stop.", "warn")
            self.root.after(400, self.root.iconify)

    def stop_run(self) -> None:
        if self.engine:
            self.engine.stop()
        self.status_text.set("Stopping...")

    def explain_step(self) -> None:
        """Show what the selected color step is actually matching.

        Tuning a color search by reading numbers in a log is guesswork. This
        photographs the search area, paints every matching pixel, and boxes
        each patch, so a background that shares the color is obvious instead
        of mysterious.
        """
        step = self.current_step()
        if step is None or self.running:
            return
        region = step.get("region")
        if not region:
            self.log("Set the area to search first - there is nothing to look at.",
                     "warn")
            return

        self.root.withdraw()
        self.root.update()
        time.sleep(0.35)  # let the desktop repaint without Pixie on top of it
        try:
            picture, kept, dropped = screen.explain_colors(
                tuple(region),
                tuple(step.get("color") or (255, 255, 255)),
                float(self._setting(step, "tolerance")),
                int(self._setting(step, "min_pixels")),
                match=self._setting(step, "match"),
                min_saturation=int(self._setting(step, "min_saturation")),
                min_brightness=int(self._setting(step, "min_brightness")),
                order=self._setting(step, "pick"),
                join=int(self._setting(step, "join")),
                min_width=int(self._setting(step, "min_width")),
                min_height=int(self._setting(step, "min_height")),
            )
        except Exception as error:  # noqa: BLE001 - report, don't disappear
            self.log(f"Could not look at that area: {error!r}", "error")
            return
        finally:
            self.root.deiconify()
            self.root.lift()

        show_matches(self.root, picture, kept, dropped, step, self.scale)
        self.log(f"{len(kept)} patch(es) would be used, {len(dropped)} ignored.",
                 "good" if kept else "warn")

    def _setting(self, step: dict[str, Any], key: str) -> Any:
        """A step's value for a field, or the default its type declares."""
        return engine_mod.Engine._value(step, key, None)

    def preview_click(self) -> None:
        """Show exactly where the selected step would click, on the real screen.

        Runs the step for real except for the click itself, so the point comes
        from the same code the run would use, not from a second guess at it.
        A step that clicks whatever was found last needs the step before it to
        have found something, so that one is run too.
        """
        step = self.current_step()
        if step is None or self.running:
            return

        needed = self._steps_for_preview(step)
        self.root.withdraw()
        self.root.update()
        time.sleep(0.35)
        try:
            points, boxes, lines = self._rehearse(needed, step)
        except Exception as error:  # noqa: BLE001 - report, don't disappear
            self.log(f"Could not work out the click: {error!r}", "error")
            return
        finally:
            self.root.deiconify()
            self.root.lift()

        if not points:
            self.log("That step would not click anything right now - see the "
                     "log above for what it was looking for.", "warn")
            return
        picture, region = screen.picture_around(*points[0])
        show_click(self.root, picture, region, points, boxes, lines, step,
                   self.scale)
        self.log(f"It would click {points[0][0]}, {points[0][1]}.", "good")

    def _steps_for_preview(self, step: dict[str, Any]) -> list[dict[str, Any]]:
        """The step, plus whatever has to run first for it to make sense."""
        if step.get("type") != "click_last_match":
            return [step]
        # Walk back to the nearest step that would leave something to click.
        for index in range(self.selected - 1, -1, -1):
            earlier = self.sequence.steps[index]
            if (earlier.get("enabled", True)
                    and earlier.get("type") not in step_defs.MARKERS):
                return [earlier, step]
        return [step]

    def _rehearse(self, steps: list[dict[str, Any]], step: dict[str, Any]):
        """Run the steps with the clicks recorded instead of sent."""
        recorded: list[tuple[int, int, str]] = []

        class Rehearsal(engine_mod.Engine):
            def _click(self, x, y, one, what):  # noqa: ANN001 - matches the base
                recorded.append((x, y, what))
                super()._click(x, y, one, what)

        # No pauses and no parking: this is a rehearsal, not a run.
        settings = engine_mod.Settings.from_dict(vars(self.sequence.settings))
        settings.step_pause_min = settings.step_pause_max = 0.0
        settings.park_mouse = "off"
        runner = Rehearsal(
            engine_mod.Sequence(name="preview", steps=steps, settings=settings),
            emit=self.events.put, dry_run=True, base_dir=PROJECT_DIR)
        for one in steps:
            runner.run_step(one)

        boxes = [runner.last_box] if runner.last_box else []
        lines: list[tuple[str, str]] = []
        for x, y, what in recorded:
            lines.append((f"Would click {x}, {y}  -  {what}", "good"))
        if len(steps) > 1:
            lines.append((f"After running '{steps[0].get('name')}' first, which "
                          "is what it clicks the result of.", "muted"))
        if runner.last_box:
            left, top, width, height = runner.last_box
            lines.append((f"What it found: {width}x{height} at {left}, {top}",
                          "info"))
        # points[0] is the click. Anything after it is somewhere else the same
        # step could equally have landed, drawn faintly.
        points = [point[:2] for point in recorded[:1]]
        if step.get("type") == "click_box" and step.get("box"):
            lines.append(("This step picks a fresh spot inside the box every "
                          "time - the faint dots are twenty more it could "
                          "have chosen.", "muted"))
            for _ in range(20):
                runner.run_step(step)
                points.append(recorded[-1][:2])
            boxes = [tuple(step["box"])]
        return points, boxes, lines

    def test_step(self) -> None:
        step = self.current_step()
        if step is None or self.running:
            return
        where = step_defs.location(self.sequence.steps, self.selected)
        problems = step_defs.validate(step, where)
        if problems:
            for problem in problems:
                self.log(problem, "error")
            return

        single = engine_mod.Sequence(name="test", steps=[step],
                                     settings=self.sequence.settings)
        tester = engine_mod.Engine(single, emit=self.events.put,
                                   dry_run=self.dry_run.get(), base_dir=PROJECT_DIR)
        self.engine = tester
        self.running = True
        self.run_button.configure(text="■  Stop", style="Stop.TButton")
        self.status_text.set("Testing step")
        self.log(f"Testing {where}...", "muted")
        self.worker = threading.Thread(target=lambda: self._run_one(tester, step),
                                       daemon=True)
        self.worker.start()

    @staticmethod
    def _run_one(tester: engine_mod.Engine, step: dict[str, Any]) -> None:
        """Run a step exactly once and report what it did.

        Deliberately not the engine's own loop. 'If not found' answers a
        question about the sequence -- go back to this section, start over --
        which has no meaning for one step on its own, and one of the answers
        made testing a step retry it forever.
        """
        tester.emit({"kind": "started"})
        try:
            outcome = tester.run_step(step)
        except engine_mod.Aborted as stop:
            tester.emit({"kind": "finished", "reason": str(stop)})
            return
        except Exception as error:  # noqa: BLE001 - surface it, don't vanish
            tester.log(f"Unexpected error: {error!r}", "error")
            tester.emit({"kind": "finished", "reason": "an unexpected error"})
            return

        if outcome == "ok":
            tester.log("That step worked.", "good")
        else:
            on_timeout = tester._value(step, "on_timeout", None)
            doing = step_defs.ON_TIMEOUT_LABELS.get(on_timeout, "")
            tester.log("That step did not find what it wanted."
                       + (f" In a run it would: {doing.lower()}." if doing else ""),
                       "warn")
        tester.emit({"kind": "finished", "reason": "tested one step"})

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        self._drain_job = self.root.after(80, self._drain_events)

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event.get("kind")
        if kind == "log":
            self.log(event["message"], event.get("level", "info"))
        elif kind == "step":
            index = event["index"]
            if index < self.listbox.size():
                self.listbox.selection_clear(0, "end")
                self.listbox.selection_set(index)
                self.listbox.see(index)
        elif kind == "section":
            self._light_section(event.get("index"))
        elif kind == "cycle":
            done = event["completed"]
            self.cycle_text.set(f"Cycles: {done}")
            # Visible in the taskbar even while minimized.
            self.root.title(f"{APP_NAME} - running, {done} cycle"
                            f"{'s' if done != 1 else ''} done")
        elif kind == "finished":
            self._on_finished(event.get("reason", "stopped"))

    def _light_section(self, index: int | None) -> None:
        """Mark which section is running now, so the list says where you are.

        The running step is already shown by the selection, which moves every
        step or two. The section is the slower, more useful answer to 'what is
        it doing', so it gets its own, steadier highlight.
        """
        if self.lit_section is not None and self.lit_section < self.listbox.size():
            self.listbox.itemconfigure(self.lit_section, background=theme.PANEL,
                                       foreground=theme.ACCENT)
        self.lit_section = None
        if index is None or not (0 <= index < self.listbox.size()):
            return
        self.listbox.itemconfigure(index, background=theme.ACCENT_DARK,
                                   foreground="#ffffff")
        self.lit_section = index

    def _on_finished(self, reason: str) -> None:
        self.running = False
        self._light_section(None)
        self._update_title()
        self._refresh_run_tip()
        self.run_button.configure(text="▶  Start", style="Accent.TButton")
        self.status_text.set(f"Idle - {reason}")
        self.test_button.configure(state="normal" if self.current_step() else "disabled")
        self.build_editor()  # the What-matches button depends on the step type
        if self.root.state() == "iconic":
            self.root.deiconify()
        self.root.lift()
        self.listbox.selection_clear(0, "end")
        if 0 <= self.selected < self.listbox.size():
            self.listbox.selection_set(self.selected)

    def on_close(self) -> None:
        if self.running:
            if not messagebox.askokcancel("Still running", "Stop the run and quit?"):
                return
            self.stop_run()
            if self.worker:
                self.worker.join(timeout=2.0)
        if not self._confirm_discard():
            return
        self.save_preferences()
        # Cancel the pending poll, or it fires after the window is gone and
        # Tk complains about an invalid command.
        for job in ("_drain_job", "_hotkey_job"):
            pending = getattr(self, job, None)
            if pending is not None:
                self.root.after_cancel(pending)
                setattr(self, job, None)
        self.root.destroy()


def main() -> int:
    screen.set_dpi_aware()
    ensure_dirs()  # a freshly unzipped exe has no images/ or sequences/ yet
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
