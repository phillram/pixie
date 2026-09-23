"""Pixie -- build a sequence of screen steps, then run it on a loop.

    python gui.py

The left pane is the sequence. Pick a step to edit it on the right; every
image, color, point and search area has a Capture button that freezes the
screen and lets you point at what you mean. Start runs the sequence over and
over until you press Stop or F8.
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
from pixie.core import engine as engine_mod
from pixie.system import keyboard
from pixie.system import screen
from pixie.core import steps as step_defs
from pixie.ui import theme

from pixie.paths import (APP_DIR as PROJECT_DIR, APP_NAME, ICON_PATH, IMAGES_DIR,
                   SEQUENCES_DIR, STATE_PATH, ensure_dirs)

LOG_COLORS = {"info": theme.FG, "warn": theme.WARN, "error": theme.ERROR,
              "good": theme.OK, "muted": theme.MUTED}


PARK_LABELS = {
    "off": "leave the cursor alone",
    "center": "move it to the middle of the screen",
    "custom": "move it to a spot I pick",
}
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
        ("cycle_pause", "Pause between cycles",
         "Extra wait after the last step, before starting the list again."),
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

        ttk.Label(frame, text="Stop key").grid(row=row, column=0, sticky="w",
                                               padx=(0, 14), pady=(4, 0))
        self.abort_var = tk.StringVar(value=settings.abort_key)
        ttk.Combobox(frame, textvariable=self.abort_var, state="readonly", width=10,
                     values=["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
                             "F10", "F11", "F12", "ESC", "PAUSE", "SCROLLLOCK"]).grid(
            row=row, column=1, sticky="w", pady=(4, 0))
        row += 1
        ttk.Label(frame, text="Works even when another window has focus.",
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
        self.settings.abort_key = self.abort_var.get()
        self.settings.failsafe_corner = bool(self.corner_var.get())
        self.settings.park_mouse = PARK_MODES.get(self.park_var.get(), "off")
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


class App:
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
        self.running = False

        self.dry_run = tk.BooleanVar(value=True)
        self.hide_while_running = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="Idle")
        self.cycle_text = tk.StringVar(value="Cycles: 0")

        self._build_toolbar()
        self._build_body()
        self._build_log()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Control-s>", lambda _e: self.save())
        root.bind("<Control-o>", lambda _e: self.open())
        root.bind("<F5>", lambda _e: self.toggle_run())

        state = self._read_state()
        self._restore_preferences(state)
        self._restore_last_sequence(state)
        self.refresh_list()
        self._drain_job: str | None = self.root.after(80, self._drain_events)
        self.log("Ready. Build a sequence on the left, then press Start.", "muted")
        self.log("Stop any time with the Stop button, F8, or the mouse in the "
                 "top-left corner of the screen.", "muted")

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
        """The Start/Stop tooltip, which names the live stop key."""
        key = self.sequence.settings.abort_key
        stops = (f"To stop: this button, {key} from anywhere (even when another "
                 "window has focus), or shove the mouse into the top-left corner "
                 "of the screen.")
        if self.running:
            return "Stop the run.\n\n" + stops
        return ("Start the sequence. It loops from the top over and over until "
                "you stop it.\nShortcut: F5\n\n" + stops)

    def _refresh_run_tip(self) -> None:
        if hasattr(self, "run_tip"):
            self.run_tip.update(self._run_tip_text())

    def _build_body(self) -> None:
        body = ttk.Frame(self.root, padding=(12, 10, 12, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0, minsize=int(340 * self.scale))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sequence_pane(body)
        self._build_editor_pane(body)

    def _build_sequence_pane(self, parent: ttk.Frame) -> None:
        pane = ttk.Frame(parent)
        pane.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
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
            "Copy": "Duplicate the selected step, settings and all.",
            "Remove": "Delete the selected step.",
        }
        for label, command in (("↑", self.move_up), ("↓", self.move_down),
                               ("Copy", self.duplicate), ("Remove", self.remove)):
            button = ttk.Button(buttons, text=label, style="Tool.TButton",
                                command=command, width=6 if len(label) == 1 else 8)
            button.pack(side="left", padx=(6, 0))
            theme.tip(button, step_tips[label])

        ttk.Label(pane, text="Double-click a step to turn it on or off.",
                  style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(6, 0))

    def _build_editor_pane(self, parent: ttk.Frame) -> None:
        pane = ttk.Frame(parent)
        pane.grid(row=0, column=1, sticky="nsew")
        pane.rowconfigure(1, weight=1)
        pane.columnconfigure(0, weight=1)

        header = ttk.Frame(pane)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        self.editor_title = ttk.Label(header, text="Step settings", style="Title.TLabel")
        self.editor_title.grid(row=0, column=0, sticky="w")
        self.test_button = ttk.Button(header, text="Test this step", style="Tool.TButton",
                                      command=self.test_step, state="disabled")
        self.test_button.grid(row=0, column=1, sticky="e")
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
        self.editor.bind("<Configure>",
                         lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.editor_window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _build_log(self) -> None:
        pane = ttk.Frame(self.root, padding=(12, 10, 12, 12))
        pane.pack(fill="both")
        pane.columnconfigure(0, weight=1)

        head = ttk.Frame(pane)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Log", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(head, text="Clear", style="Tool.TButton",
                   command=self.clear_log).grid(row=0, column=1, sticky="e")

        holder = tk.Frame(pane, bg=theme.PANEL)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        self.log_text = theme.text(holder, height=9, state="disabled")
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

    @staticmethod
    def _row_label(index: int, step: dict[str, Any]) -> tuple[str, str | None]:
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

        prefix = f"{index + 1:>2}. " if enabled else f"{index + 1:>2}. - "
        return prefix + text, None if enabled else theme.DISABLED

    def _refresh_row(self, index: int) -> None:
        """Redraw a single row, leaving every other widget untouched.

        Rebuilding the whole editor here would destroy the entry the user is
        currently typing into, which takes the keyboard focus with it. That is
        why this exists separately from refresh_list.
        """
        if not (0 <= index < self.listbox.size()):
            return
        label, color = self._row_label(index, self.sequence.steps[index])
        was_selected = index in self.listbox.curselection()
        self.listbox.delete(index)
        self.listbox.insert(index, label)
        if color:
            self.listbox.itemconfigure(index, foreground=color)
        if was_selected:
            self.listbox.selection_set(index)

    def refresh_list(self, keep: int | None = None) -> None:
        selection = keep if keep is not None else self.selected
        self.listbox.delete(0, "end")
        for index, step in enumerate(self.sequence.steps):
            label, color = self._row_label(index, step)
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
        self.log(f"Added step {at + 1}: {step['name']}", "muted")

    def duplicate(self) -> None:
        step = self.current_step()
        if step is None:
            return
        at = self.selected + 1
        self.sequence.steps.insert(at, json.loads(json.dumps(step)))
        self.mark_dirty()
        self.refresh_list(keep=at)

    def remove(self) -> None:
        step = self.current_step()
        if step is None:
            return
        self.sequence.steps.pop(self.selected)
        self.mark_dirty()
        self.refresh_list(keep=max(0, self.selected - 1))

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

        step = self.current_step()
        if step is None:
            self.editor_title.configure(text="Step settings")
            self.test_button.configure(state="disabled")
            ttk.Label(self.editor, style="Panel.TLabel", justify="left",
                      text="No step selected.\n\nPress “Add step” to start "
                           "building your sequence.").grid(row=0, column=0, sticky="w")
            return

        step_type = step_defs.STEP_TYPES.get(step.get("type", ""))
        if step_type is None:
            ttk.Label(self.editor, style="Panel.TLabel",
                      text=f"Unknown step type: {step.get('type')!r}").grid(row=0, column=0)
            return

        self.editor_title.configure(text=f"Step {self.selected + 1}: {step_type.label}")
        self.test_button.configure(state="normal")
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

        builder = {
            "image": self._field_image, "point": self._field_point,
            "color": self._field_color, "region": self._field_region,
            "choice": self._field_choice, "integer": self._field_integer,
            "offset": self._field_offset, "key": self._field_key,
            "pause": self._field_pause, "multiline": self._field_multiline,
        }.get(spec.kind, self._field_number)
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

    def _field_region(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        value = step.get(spec.key)
        var = tk.StringVar(value=self._region_label(value))
        self._readonly_entry(row, var)
        holder = ttk.Frame(self.editor, style="Panel.TFrame")
        holder.grid(row=row, column=2, sticky="w", padx=(8, 0))
        ttk.Button(holder, text="Pick...", style="Tool.TButton",
                   command=lambda: self._capture_region(step, spec, var)).pack(side="left")
        ttk.Button(holder, text="Whole screen", style="Tool.TButton",
                   command=lambda: (self._set_value(step, spec.key, None),
                                    var.set(self._region_label(None)))).pack(
            side="left", padx=(6, 0))
        self.field_vars[spec.key] = var

    @staticmethod
    def _region_label(value: Any) -> str:
        if not value:
            return "whole screen (slower)"
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

    def _field_choice(self, step: dict[str, Any], spec: step_defs.Field, row: int) -> None:
        var = tk.StringVar(value=str(step.get(spec.key, spec.default)))
        combo = ttk.Combobox(self.editor, textvariable=var, values=list(spec.choices),
                             state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        var.trace_add("write", lambda *_: self._set_value(step, spec.key, var.get()))
        self.field_vars[spec.key] = var
        if spec.key == "on_timeout":
            note = ttk.Label(self.editor, style="Blurb.TLabel",
                             text=step_defs.ON_TIMEOUT_LABELS.get(var.get(), ""))
            note.grid(row=row, column=2, sticky="w", padx=(8, 0))
            var.trace_add("write",
                          lambda *_: note.configure(
                              text=step_defs.ON_TIMEOUT_LABELS.get(var.get(), "")))

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
        self.root.withdraw()
        self.root.update()
        time.sleep(0.35)  # let the desktop repaint before we photograph it
        try:
            picker = capture.Picker(mode, parent=self.root)
            picker.run()
            return picker
        finally:
            self.root.deiconify()
            self.root.lift()

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
                        var: tk.StringVar) -> None:
        picker = self._pick("area")
        if picker is None or picker.result is None:
            return
        left, top, width, height = picker.to_absolute(picker.result)
        self._set_value(step, spec.key, [left, top, width, height])
        var.set(self._region_label([left, top, width, height]))
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
            s = self.sequence.settings
            self.log(f"Settings: {_range_text(s.step_pause_min, s.step_pause_max)} "
                     f"after each step, "
                     f"{_range_text(s.cycle_pause_min, s.cycle_pause_max)} "
                     f"between cycles, stop key {s.abort_key}, "
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
            geometry=self._current_geometry(),
        )

    def _current_geometry(self) -> str | None:
        """Size and position, unless minimized or maximized right now."""
        try:
            if self.root.state() != "normal":
                return None
            return self.root.winfo_geometry()
        except tk.TclError:
            return None

    def _restore_preferences(self, state: dict[str, Any]) -> None:
        if isinstance(state.get("dry_run"), bool):
            self.dry_run.set(state["dry_run"])
        if isinstance(state.get("minimize_while_running"), bool):
            self.hide_while_running.set(state["minimize_while_running"])

        geometry = state.get("geometry")
        if isinstance(geometry, str) and self._geometry_is_on_screen(geometry):
            try:
                self.root.geometry(geometry)
            except tk.TclError:
                pass

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

        self.worker = threading.Thread(target=self.engine.run, daemon=True)
        self.worker.start()
        if self.hide_while_running.get():
            self.log("Minimizing to stay out of the way - Pixie is still running. "
                     "Bring her back from the taskbar, or press F8 to stop.", "warn")
            self.root.after(400, self.root.iconify)

    def stop_run(self) -> None:
        if self.engine:
            self.engine.stop()
        self.status_text.set("Stopping...")

    def test_step(self) -> None:
        step = self.current_step()
        if step is None or self.running:
            return
        problems = step_defs.validate(step, self.selected)
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
        self.log(f"Testing step {self.selected + 1}...", "muted")
        self.worker = threading.Thread(target=lambda: tester.run(max_cycles=1), daemon=True)
        self.worker.start()

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
        elif kind == "cycle":
            done = event["completed"]
            self.cycle_text.set(f"Cycles: {done}")
            # Visible in the taskbar even while minimized.
            self.root.title(f"{APP_NAME} - running, {done} cycle"
                            f"{'s' if done != 1 else ''} done")
        elif kind == "finished":
            self._on_finished(event.get("reason", "stopped"))

    def _on_finished(self, reason: str) -> None:
        self.running = False
        self._update_title()
        self._refresh_run_tip()
        self.run_button.configure(text="▶  Start", style="Accent.TButton")
        self.status_text.set(f"Idle - {reason}")
        self.test_button.configure(state="normal" if self.current_step() else "disabled")
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
        if self._drain_job is not None:
            self.root.after_cancel(self._drain_job)
            self._drain_job = None
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
