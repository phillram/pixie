"""The editing keys Tk leaves out.

Tk's entry and text bindings are older than the conventions every Windows
application now shares. Ctrl+Backspace does nothing, and Ctrl+A jumps to the
start of the line instead of selecting everything, which is startling when
muscle memory says otherwise.

`install(root)` adds the missing ones to every entry, spinbox and text box in
the window at once, by binding the widget classes rather than each widget:

    Ctrl+Backspace, Shift+Backspace   delete the word before the caret
    Ctrl+Delete                       delete the word after it
    Ctrl+A                            select everything

Shift+Delete is deliberately left alone, because it has meant Cut since long
before any of this.
"""

from __future__ import annotations

import tkinter as tk

# Classes whose contents are edited as a single line. ttk widgets carry the
# "T" names; plain tk ones are here too in case anything uses them.
ENTRY_CLASSES = ("TEntry", "Entry", "TSpinbox", "Spinbox")
TEXT_CLASSES = ("Text",)


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def word_start(text: str, caret: int) -> int:
    """Where the word before the caret begins.

    Skips any spaces immediately behind the caret first, so a trailing space
    does not eat a whole keystroke on its own, then takes the run of letters
    or the run of punctuation -- whichever the caret is sitting behind.
    """
    at = min(max(caret, 0), len(text))
    while at > 0 and text[at - 1].isspace():
        at -= 1
    if at == 0:
        return 0
    wanted = _is_word_char(text[at - 1])
    while at > 0 and not text[at - 1].isspace() and _is_word_char(text[at - 1]) == wanted:
        at -= 1
    return at


def word_end(text: str, caret: int) -> int:
    """Where the word after the caret ends. The mirror of `word_start`."""
    at = min(max(caret, 0), len(text))
    while at < len(text) and text[at].isspace():
        at += 1
    if at >= len(text):
        return len(text)
    wanted = _is_word_char(text[at])
    while at < len(text) and not text[at].isspace() and _is_word_char(text[at]) == wanted:
        at += 1
    return at


# -- single-line widgets ------------------------------------------------

def _drop_entry_selection(widget: tk.Widget) -> bool:
    if not widget.selection_present():  # type: ignore[attr-defined]
        return False
    widget.delete("sel.first", "sel.last")  # type: ignore[attr-defined]
    return True


def _entry_delete_word_left(event: tk.Event) -> str:
    widget = event.widget
    try:
        if _drop_entry_selection(widget):
            return "break"
        caret = widget.index("insert")
        start = word_start(widget.get(), caret)
        if start < caret:
            widget.delete(start, caret)
    except tk.TclError:
        pass  # read-only, or a widget that does not take edits
    return "break"


def _entry_delete_word_right(event: tk.Event) -> str:
    widget = event.widget
    try:
        if _drop_entry_selection(widget):
            return "break"
        caret = widget.index("insert")
        end = word_end(widget.get(), caret)
        if end > caret:
            widget.delete(caret, end)
    except tk.TclError:
        pass
    return "break"


def _entry_select_all(event: tk.Event) -> str:
    widget = event.widget
    try:
        widget.selection_range(0, "end")  # type: ignore[attr-defined]
        widget.icursor("end")             # type: ignore[attr-defined]
    except tk.TclError:
        pass
    return "break"


# -- multi-line widgets -------------------------------------------------

def _drop_text_selection(box: tk.Text) -> bool:
    if not box.tag_ranges("sel"):
        return False
    box.delete("sel.first", "sel.last")
    return True


def _text_delete_word_left(event: tk.Event) -> str:
    box = event.widget
    try:
        if _drop_text_selection(box):
            return "break"
        line = box.get("insert linestart", "insert")
        if not line:
            # At the very start of a line, take the line break itself.
            if box.index("insert") != "1.0":
                box.delete("insert-1c", "insert")
            return "break"
        back = len(line) - word_start(line, len(line))
        if back:
            box.delete(f"insert-{back}c", "insert")
    except tk.TclError:
        pass  # the log is a disabled Text, and refuses edits
    return "break"


def _text_delete_word_right(event: tk.Event) -> str:
    box = event.widget
    try:
        if _drop_text_selection(box):
            return "break"
        line = box.get("insert", "insert lineend")
        if not line:
            if box.index("insert") != box.index("end-1c"):
                box.delete("insert", "insert+1c")
            return "break"
        forward = word_end(line, 0)
        if forward:
            box.delete("insert", f"insert+{forward}c")
    except tk.TclError:
        pass
    return "break"


def _text_select_all(event: tk.Event) -> str:
    box = event.widget
    try:
        box.tag_add("sel", "1.0", "end-1c")
        box.mark_set("insert", "end-1c")
    except tk.TclError:
        pass
    return "break"


def install(root: tk.Misc) -> None:
    """Add the missing editing keys to every entry and text box in `root`."""
    bindings = (
        ("<Control-BackSpace>", _entry_delete_word_left, _text_delete_word_left),
        ("<Shift-BackSpace>", _entry_delete_word_left, _text_delete_word_left),
        ("<Control-Delete>", _entry_delete_word_right, _text_delete_word_right),
        ("<Control-a>", _entry_select_all, _text_select_all),
        ("<Control-A>", _entry_select_all, _text_select_all),
    )
    for sequence, on_entry, on_text in bindings:
        for name in ENTRY_CLASSES:
            root.bind_class(name, sequence, on_entry)
        for name in TEXT_CLASSES:
            root.bind_class(name, sequence, on_text)

    # Tk binds Ctrl+D to "delete the character ahead", an emacs habit no
    # Windows application has. Replace it with a handler that does nothing and
    # does not swallow the event, so the window's own Ctrl+D still fires.
    for name in ENTRY_CLASSES + TEXT_CLASSES:
        root.bind_class(name, "<Control-d>", lambda _event: None)
