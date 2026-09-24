"""Dark theme for the tkinter GUI.

ttk's stock themes are light and largely ignore color options, so we base
everything on 'clam' -- the one built-in theme that honours them properly.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#17181c"        # window background
PANEL = "#22242a"     # raised panels, list backgrounds
FIELD = "#2b2e36"     # entry and combobox interiors
BORDER = "#3a3e48"
FG = "#e4e6eb"        # primary text
MUTED = "#9ba1ad"     # hints, secondary text
ACCENT = "#4ea1ff"
ACCENT_DARK = "#1b4a78"
OK = "#5cc87a"
WARN = "#ffb454"
ERROR = "#ff6b6b"
DISABLED = "#6b7280"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI", 12, "bold")
FONT_MONO = ("Cascadia Mono", 9)


def dark_titlebar(window: tk.Misc) -> None:
    """Ask Windows for a dark title bar, so the frame matches the window."""
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            20,  # DWMWA_USE_IMMERSIVE_DARK_MODE
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int),
        )
    except (AttributeError, OSError, tk.TclError):
        pass  # older Windows, or no dwmapi - a light title bar is survivable


def apply(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(bg=BG)
    style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                    bordercolor=BORDER, lightcolor=BG, darkcolor=BG, font=FONT)

    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=PANEL, foreground=FG)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
    style.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_TITLE)
    # Blurbs and hints only ever sit inside the editor panel, so they take the
    # panel background rather than the window one.
    style.configure("Blurb.TLabel", background=PANEL, foreground=MUTED, font=FONT_SMALL)
    style.configure("Status.TLabel", background=BG, foreground=MUTED)

    style.configure("TButton", background=FIELD, foreground=FG, borderwidth=0,
                    focuscolor=BG, padding=(10, 5))
    style.map("TButton",
              background=[("active", "#3a3e48"), ("disabled", "#23252b")],
              foreground=[("disabled", DISABLED)])

    style.configure("Accent.TButton", background=ACCENT_DARK, foreground="#ffffff",
                    padding=(16, 7), font=FONT_BOLD)
    style.map("Accent.TButton",
              background=[("active", "#24598e"), ("disabled", "#23252b")],
              foreground=[("disabled", DISABLED)])

    style.configure("Stop.TButton", background="#7a2d2d", foreground="#ffffff",
                    padding=(16, 7), font=FONT_BOLD)
    style.map("Stop.TButton", background=[("active", "#953737")])

    style.configure("Tool.TButton", padding=(8, 4), font=FONT_SMALL)

    style.configure("TEntry", fieldbackground=FIELD, foreground=FG,
                    insertcolor=FG, borderwidth=0, padding=5)
    style.map("TEntry", fieldbackground=[("disabled", PANEL)],
              foreground=[("disabled", MUTED)])

    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD,
                    foreground=FG, arrowcolor=MUTED, borderwidth=0, padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)],
              selectbackground=[("readonly", FIELD)],
              selectforeground=[("readonly", FG)])
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_DARK)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    style.configure("TSpinbox", fieldbackground=FIELD, background=FIELD,
                    foreground=FG, arrowcolor=MUTED, borderwidth=0, padding=4)

    style.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG,
                    indicatorbackground=FIELD, indicatorforeground=ACCENT,
                    indicatormargin=(0, 0, 8, 0), borderwidth=0, padding=(2, 4))
    style.map("TCheckbutton",
              background=[("active", BG)],
              foreground=[("disabled", DISABLED)],
              indicatorbackground=[("selected", ACCENT), ("active", "#3a3e48"),
                                   ("disabled", PANEL)],
              indicatorforeground=[("selected", "#ffffff")])

    # Sits among the Tool.TButton row in a panel header, so it takes the
    # panel's background rather than the window's.
    style.configure("Tool.TCheckbutton", background=PANEL, foreground=MUTED,
                    focuscolor=PANEL, indicatorbackground=FIELD,
                    indicatorforeground=ACCENT, indicatormargin=(0, 0, 6, 0),
                    borderwidth=0, padding=(2, 4), font=FONT_SMALL)
    style.map("Tool.TCheckbutton",
              background=[("active", PANEL)],
              foreground=[("selected", FG), ("active", FG)],
              indicatorbackground=[("selected", ACCENT), ("active", "#3a3e48")],
              indicatorforeground=[("selected", "#ffffff")])

    style.configure("TSeparator", background=BORDER)
    style.configure("Vertical.TScrollbar", background=FIELD, troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, borderwidth=0)
    style.map("Vertical.TScrollbar", background=[("active", "#464b57")])
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", background=BORDER, sashthickness=6)

    return style


class Tooltip:
    """A small dark popup that explains a widget when you hover over it."""

    DELAY_MS = 450
    OFFSET = (14, 26)

    def __init__(self, widget: tk.Misc, text: str, wraplength: int = 320) -> None:
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self.window: tk.Toplevel | None = None
        self.scheduled: str | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        self.scheduled = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self.scheduled is not None:
            self.widget.after_cancel(self.scheduled)
            self.scheduled = None

    def _show(self) -> None:
        if self.window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + self.OFFSET[0]
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + self.OFFSET[1] // 4

        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)  # no title bar, no border
        self.window.wm_geometry(f"+{x}+{y}")
        self.window.configure(bg=BORDER)
        tk.Label(
            self.window, text=self.text, justify="left", bg=PANEL, fg=FG,
            font=FONT_SMALL, wraplength=self.wraplength, padx=10, pady=7,
        ).pack(padx=1, pady=1)
        try:
            self.window.attributes("-topmost", True)
        except tk.TclError:
            pass

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self.window is not None:
            self.window.destroy()
            self.window = None

    def update(self, text: str) -> None:
        self.text = text
        self._hide()


def tip(widget: tk.Misc, text: str, wraplength: int = 320) -> Tooltip:
    """Attach a tooltip to a widget and hand it back, in case it needs updating."""
    return Tooltip(widget, text, wraplength)


def wrapping_label(parent: tk.Misc, text: str, style: str = "Blurb.TLabel",
                   minimum: int = 200, **kwargs) -> ttk.Label:
    """A paragraph that re-wraps to whatever width it is given.

    Tk labels wrap at a fixed pixel count, so a paragraph written for a narrow
    pane keeps that shape in a wide one and leaves the right-hand half of the
    panel empty. Grid it with sticky="ew" and this one follows the pane as you
    drag the divider.

    `minimum` is the starting width, and it matters: the label's requested
    width is what the grid uses to decide how wide the column needs to be, so
    starting unwrapped would size the panel to the longest paragraph in it.
    """
    label = ttk.Label(parent, text=text, style=style, justify="left",
                      wraplength=minimum, **kwargs)
    settled = {"width": minimum}

    def refit(event: tk.Event) -> None:
        # Re-wrapping changes the height, which fires <Configure> again. Only
        # a real change of width is worth acting on, or this never settles.
        if abs(event.width - settled["width"]) <= 8:
            return
        settled["width"] = event.width
        label.configure(wraplength=max(minimum, event.width))

    label.bind("<Configure>", refit)
    return label


def listbox(parent: tk.Misc, **kwargs) -> tk.Listbox:
    """A tk.Listbox styled to match. ttk has no listbox of its own."""
    options = dict(
        bg=PANEL, fg=FG, selectbackground=ACCENT_DARK, selectforeground="#ffffff",
        highlightthickness=0, borderwidth=0, activestyle="none", font=FONT,
        relief="flat", selectborderwidth=0,
    )
    options.update(kwargs)
    return tk.Listbox(parent, **options)


def text(parent: tk.Misc, **kwargs) -> tk.Text:
    options = dict(
        bg=PANEL, fg=FG, insertbackground=FG, highlightthickness=0,
        borderwidth=0, relief="flat", font=FONT_MONO, wrap="word",
        padx=10, pady=8,
    )
    options.update(kwargs)
    return tk.Text(parent, **options)
