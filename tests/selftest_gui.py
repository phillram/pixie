"""Drive the GUI without a human: add every step type, edit fields, save, reload.

Catches tkinter widget errors, theme typos and schema/editor mismatches that
would otherwise only show up when clicking around by hand. Needs a desktop
session; it builds a real window but never shows it.

    python selftest_gui.py
"""

import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path

import _bootstrap  # noqa: F401  (sys.path)

from pixie.core import engine as engine_mod
from pixie.ui import app as gui
from pixie.core import steps as step_defs

failures = []

root = tk.Tk()
root.withdraw()  # never actually show it
app = gui.App(root)

# Start from a blank sequence, not whichever one was open last, so the test
# result doesn't depend on what the user was working on.
app.sequence = engine_mod.Sequence(name="selftest_gui")
app.selected = -1
app.refresh_list()
root.update()
print(f"App built. {len(step_defs.STEP_TYPES)} step types available.")

# Add one of every step type and render its editor.
for key in step_defs.STEP_TYPES:
    try:
        app.add_step(key)
        root.update()
        widgets = len(app.editor.winfo_children())
        if widgets == 0:
            failures.append(f"{key}: editor rendered no widgets")
        print(f"  {key:26s} editor ok ({widgets} widgets, "
              f"{len(app.field_vars)} fields)")
    except Exception as error:  # noqa: BLE001
        failures.append(f"{key}: {error!r}")
        print(f"  {key:26s} FAILED {error!r}")

# Reordering and enable/disable.
try:
    app.selected = 0
    app.move_down()
    app.move_up()
    app.toggle_enabled()
    app.toggle_enabled()
    app.duplicate()
    app.remove()
    root.update()
    print(f"Reorder/toggle/duplicate/remove ok ({len(app.sequence.steps)} steps)")
except Exception as error:  # noqa: BLE001
    failures.append(f"list operations: {error!r}")

# Editing a field through the bound variable must reach the step dict.
try:
    app.selected = next(i for i, s in enumerate(app.sequence.steps)
                        if s["type"] == "click_point")
    app.build_editor()
    root.update()
    app.field_vars["clicks"].set("2")
    root.update()
    step = app.sequence.steps[app.selected]
    if step.get("clicks") != 2:
        failures.append(f"editing 'clicks' did not reach the step: {step.get('clicks')!r}")
    else:
        print(f"Field edit ok: clicks -> {step['clicks']}, "
              f"summary now '{step_defs.describe(step)}'")
except Exception as error:  # noqa: BLE001
    failures.append(f"field editing: {error!r}")

# Validation should complain about the unset images and points.
problems = app.sequence.problems()
print(f"Validation reported {len(problems)} problems on a blank sequence "
      f"(expected: several)")
if not problems:
    failures.append("validation passed a sequence full of unset images")

# Save and reload.
try:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "roundtrip.json"
        app.sequence.save(target)
        reloaded = engine_mod.Sequence.load(target)
        if len(reloaded.steps) != len(app.sequence.steps):
            failures.append("round-trip changed the step count")
        elif reloaded.steps != app.sequence.steps:
            failures.append("round-trip changed the step contents")
        else:
            print(f"Save/reload ok ({len(reloaded.steps)} steps, "
                  f"{target.stat().st_size} bytes)")
except Exception as error:  # noqa: BLE001
    failures.append(f"save/reload: {error!r}")


def check_typing_does_not_steal_focus():
    """Typing in a field must not rebuild the editor underneath you.

    Regression test. `_set_value` used to refresh the whole list, which
    rebuilt every editor widget, so each keystroke destroyed the entry being
    typed into and the caret jumped out. You could enter one character at a
    time. The window has to be genuinely visible for focus and key events to
    behave, so it is shown for this check and hidden again afterwards.
    """
    problems = []
    root.deiconify()
    root.geometry("1100x760+30+30")
    root.update()
    root.focus_force()
    root.update()

    # One step of every type that has something to type into.
    samples = {
        "section": ("name", "Screen One"),
        "note": ("text", "why this exists"),
        "press_key": ("presses", "3"),
        "click_point": ("clicks", "2"),
        "wait": ("seconds", "1.75"),
    }
    app.sequence = engine_mod.Sequence(
        name="typing", steps=[step_defs.new_step(k) for k in samples])
    app.refresh_list(keep=0)
    root.update()

    for index, (kind, (field, text)) in enumerate(samples.items()):
        app.selected = index
        app.build_editor()
        root.update()

        before = [str(w) for w in app.editor.winfo_children()]

        if field == "text":                       # the multi-line note box
            box = next(w for w in app.editor.winfo_children()
                       if isinstance(w, tk.Text))
            box.focus_set()
            root.update()
            for char in text:
                box.insert("end", char)
                box.event_generate("<KeyRelease>")
                root.update()
        else:
            var = app.field_vars[field]
            typed = ""
            for char in text:                      # one keystroke at a time
                typed += char
                var.set(typed)
                root.update()

        after = [str(w) for w in app.editor.winfo_children()]
        if before != after:
            problems.append(f"{kind}: editor was rebuilt while typing into "
                            f"{field!r} ({len(before)} widgets -> {len(after)})")

        stored = app.sequence.steps[index].get(field)
        expected = text if field in ("name", "text") else float(text)
        if field not in ("name", "text"):
            stored = float(stored)
        if stored != expected:
            problems.append(f"{kind}: {field!r} stored as {stored!r}, "
                            f"expected {expected!r}")

    print(f"Typing ok: {len(samples)} field types survive being typed into")
    root.withdraw()
    return problems


def check_names_show_in_the_list():
    """A step you have named must read by that name in the sequence list.

    Ordinary steps used to show only their generated summary, so renaming one
    appeared to do nothing at all.
    """
    problems = []
    named = step_defs.new_step("click_image")
    named["name"] = "Click the OK button"
    named["image"] = "images/ok.png"
    untouched = step_defs.new_step("click_image")
    untouched["image"] = "images/cancel.png"
    divider = step_defs.new_step("section")
    divider["name"] = "Screen One"

    app.sequence = engine_mod.Sequence(name="names",
                                       steps=[divider, named, untouched])
    app.refresh_list(keep=0)
    root.update()

    rows = [app.listbox.get(i) for i in range(app.listbox.size())]
    if "Screen One" not in rows[0]:
        problems.append(f"section name missing from the list: {rows[0]!r}")
    if "Click the OK button" not in rows[1]:
        problems.append(f"step name missing from the list: {rows[1]!r}")
    if "ok.png" not in rows[1]:
        problems.append(f"step summary lost when a name is set: {rows[1]!r}")
    # A step left on its default name should not repeat that name pointlessly.
    if untouched["name"] in rows[2]:
        problems.append(f"default name shown needlessly: {rows[2]!r}")

    # And renaming must take effect immediately, without a rebuild.
    app.selected = 1
    app.build_editor()
    root.update()
    app.field_vars["name"].set("Dismiss the dialog")
    root.update()
    if "Dismiss the dialog" not in app.listbox.get(1):
        problems.append(f"rename did not reach the list: {app.listbox.get(1)!r}")

    print("Names ok: custom names show in the list and update as you type")
    return problems


def check_numbering_and_section_highlight():
    """Dividers take no number, each section counts from 1, and the running
    section is lit up while it runs."""
    from pixie.ui import theme

    problems = []
    steps = [step_defs.new_step(k) for k in
             ("section", "wait_for_image", "note", "click_point",
              "section", "press_key")]
    steps[0]["name"] = "Before Game"
    steps[4]["name"] = "In Game"
    app.sequence = engine_mod.Sequence(name="numbering", steps=steps)
    app.refresh_list(keep=0)
    root.update()

    rows = [app.listbox.get(i) for i in range(app.listbox.size())]
    numbered = {1: " 1.", 3: " 2.", 5: " 1."}
    for index, prefix in numbered.items():
        if not rows[index].startswith(prefix):
            problems.append(f"row {index} reads {rows[index]!r}, expected to "
                            f"start {prefix!r}")
    for index in (0, 2, 4):
        if any(ch.isdigit() for ch in rows[index][:4]):
            problems.append(f"marker row {index} was numbered: {rows[index]!r}")
    print(f"Numbering ok: {[r.strip()[:14] for r in rows]}")

    # The editor title agrees with the list rather than the list position.
    app.selected = 5
    app.build_editor()
    root.update()
    title = str(app.editor_title.cget("text"))
    if not title.startswith("Step 1:"):
        problems.append(f"editor titled {title!r} for the first step of a section")

    # Lighting up a section, then the next one, leaves only the live one lit.
    app._handle({"kind": "section", "name": "Before Game", "index": 0})
    root.update()
    if str(app.listbox.itemcget(0, "background")) != theme.ACCENT_DARK:
        problems.append("the running section was not highlighted")
    app._handle({"kind": "section", "name": "In Game", "index": 4})
    root.update()
    if str(app.listbox.itemcget(0, "background")) == theme.ACCENT_DARK:
        problems.append("the previous section stayed highlighted")
    if str(app.listbox.itemcget(4, "background")) != theme.ACCENT_DARK:
        problems.append("the second section was not highlighted")
    app._on_finished("stopped")
    root.update()
    if str(app.listbox.itemcget(4, "background")) == theme.ACCENT_DARK:
        problems.append("a section stayed highlighted after the run finished")
    print("Section highlight ok: follows the run, clears at the end")
    return problems


def check_word_deletion():
    """Ctrl+Backspace deletes a word, not a letter, and the edit is stored."""
    from tkinter import ttk

    from pixie.ui import editing

    problems = []
    # The boundary rules on their own, where the answers are exact.
    cases = [
        ("Click the OK button", 19, "Click the OK "),
        ("Click the OK button ", 20, "Click the OK "),
        ("images/ok.png", 13, "images/ok."),
        ("one", 3, ""),
        ("", 0, ""),
    ]
    for text, caret, expected in cases:
        got = text[:editing.word_start(text, caret)] + text[caret:]
        if got != expected:
            problems.append(f"deleting a word from {text!r} gave {got!r}, "
                            f"expected {expected!r}")

    # And through a real entry, wired to a real step. Tk delivers a generated
    # key event to whatever has focus, so the window has to be up for this.
    step = step_defs.new_step("click_image")
    app.sequence = engine_mod.Sequence(name="typing", steps=[step])
    app.refresh_list(keep=0)
    app.selected = 0
    app.build_editor()
    root.deiconify()
    root.geometry("1100x760+30+30")
    root.update()
    root.focus_force()
    root.update()

    name_var = app.field_vars["name"]
    entry = next((w for w in _descendants(app.editor)
                  if isinstance(w, ttk.Entry)
                  and str(w.cget("textvariable")) == str(name_var)), None)
    if entry is None:
        problems.append("could not find the name entry to type into")
        return problems

    entry.focus_set()
    name_var.set("Click the OK button")
    entry.icursor("end")
    root.update()
    if root.focus_get() is not entry:
        print("Word editing   : SKIPPED (the entry could not take focus)")
        root.withdraw()
        return problems
    entry.event_generate("<Control-BackSpace>")
    root.update()
    if name_var.get() != "Click the OK ":
        problems.append(f"Ctrl+Backspace left {name_var.get()!r} in the entry")
    if step.get("name") != "Click the OK ":
        problems.append(f"the deletion did not reach the step: {step.get('name')!r}")

    entry.event_generate("<Shift-BackSpace>")
    root.update()
    if name_var.get() != "Click the ":
        problems.append(f"Shift+Backspace left {name_var.get()!r}")

    entry.icursor(0)
    entry.event_generate("<Control-Delete>")
    root.update()
    if name_var.get() != " the ":
        problems.append(f"Ctrl+Delete left {name_var.get()!r}")

    entry.event_generate("<Control-a>")
    root.update()
    if not entry.selection_present():
        problems.append("Ctrl+A did not select the whole field")

    root.withdraw()
    print("Word editing ok: Ctrl+Backspace, Shift+Backspace, Ctrl+Delete, Ctrl+A")
    return problems


def check_start_stop_hotkey():
    """One press of the hotkey toggles the run; holding it does not repeat."""
    problems = []
    pressed = {"down": False}
    toggles = {"count": 0}

    original_key_pressed = gui.screen.key_pressed
    original_toggle = app.toggle_run
    gui.screen.key_pressed = lambda name: pressed["down"]
    app.toggle_run = lambda: toggles.__setitem__("count", toggles["count"] + 1)

    def tick():
        app._poll_hotkey()
        if app._hotkey_job is not None:      # it reschedules itself; we drive it
            root.after_cancel(app._hotkey_job)
            app._hotkey_job = None

    try:
        app.sequence.settings.toggle_key = "F9"
        pressed["down"] = True
        tick(), tick(), tick()               # held down for three polls
        if toggles["count"] != 1:
            problems.append(f"holding the hotkey toggled {toggles['count']} times, "
                            "expected 1")
        pressed["down"] = False
        tick()
        pressed["down"] = True
        tick()
        if toggles["count"] != 2:
            problems.append(f"a second press toggled {toggles['count']} times in "
                            "total, expected 2")

        # Off means off, and so does a key Windows has never heard of.
        pressed["down"] = False
        tick()
        app.sequence.settings.toggle_key = gui.OFF
        pressed["down"] = True
        tick()
        if toggles["count"] != 2:
            problems.append("the hotkey fired while it was switched off")

        app.sequence.settings.toggle_key = "NOT A KEY"
        gui.screen.key_pressed = original_key_pressed
        tick()
        if toggles["count"] != 2:
            problems.append("an unknown hotkey name did not stay quiet")

        # Capturing borrows the whole screen, so the hotkey must stand down.
        app.sequence.settings.toggle_key = "F9"
        gui.screen.key_pressed = lambda name: True
        app.capturing = True
        tick()
        app.capturing = False
        if toggles["count"] != 2:
            problems.append("the hotkey fired while the screen picker was up")
    finally:
        gui.screen.key_pressed = original_key_pressed
        app.toggle_run = original_toggle
        app.sequence.settings.toggle_key = "F9"

    print("Hotkey ok: one toggle per press, ignored when off or capturing")
    return problems


def check_editor_cannot_scroll_into_nothing():
    """A step shorter than the editor pane must sit at the top and stay there.

    Tk lets you scroll a canvas up until the bottom of its scroll region
    reaches the bottom of the widget, so a short step used to scroll down into
    a band of empty space -- while the scrollbar went on reporting the whole
    thing was in view.
    """
    problems = []
    root.deiconify()
    root.geometry("1180x1300+40+0")   # tall, so short steps leave room to spare
    root.update()

    app.sequence = engine_mod.Sequence(
        name="scrolling", steps=[step_defs.new_step("click_box"),
                                 step_defs.new_step("click_image"),
                                 step_defs.new_step("click_image")])
    app.refresh_list(keep=0)
    app.selected = 0
    app.build_editor()
    root.update()

    canvas = app.canvas
    content = canvas.bbox("all")[3]
    if content >= canvas.winfo_height():
        print("Editor scroll  : SKIPPED (the window is too short to test it)")
        root.withdraw()
        return problems

    for _ in range(40):
        canvas.yview_scroll(-1, "units")
    root.update()
    above = -canvas.canvasy(0)
    if above > 1:
        problems.append(f"scrolling up on a short step opened {above:.0f}px of "
                        "empty space above it")

    print(f"Editor scroll ok: {content}px of content in a "
          f"{canvas.winfo_height()}px pane stays at the top")

    # Scrolling down one step and then picking another must start the new one
    # at its top. Both steps here are taller than the pane, so the view is
    # free to stay where it was if nothing moves it back.
    root.geometry("1180x700+40+40")
    root.update()
    app.selected = 1
    app.build_editor()
    root.update()
    if canvas.bbox("all")[3] <= canvas.winfo_height():
        print("  (scroll position not checked: no step is taller than the pane)")
        root.withdraw()
        return problems
    canvas.yview_moveto(0.5)
    root.update()
    scrolled = canvas.canvasy(0)
    app.selected = 2
    app.build_editor()
    root.update()
    if canvas.canvasy(0) != 0:
        problems.append(f"selecting a step left the editor scrolled to "
                        f"{canvas.canvasy(0)}, expected the top")
    else:
        print(f"  scrolled to {scrolled:.0f}px, then back to the top on the "
              "next step")
    root.withdraw()
    return problems


def check_duplicate_step():
    """Duplicating copies everything, names the copy apart, and selects it."""
    problems = []
    original = step_defs.new_step("click_image")
    original["name"] = "Handle burst lightning"
    original["image"] = "images/burst.png"
    original["region"] = [10, 20, 300, 400]
    plain = step_defs.new_step("press_key")

    app.sequence = engine_mod.Sequence(name="dupes", steps=[original, plain])
    app.refresh_list(keep=0)
    app.selected = 0
    root.update()
    app.duplicate()
    root.update()

    if len(app.sequence.steps) != 3:
        problems.append(f"duplicate left {len(app.sequence.steps)} steps, expected 3")
        return problems

    copy = app.sequence.steps[1]
    if copy["image"] != original["image"] or copy["region"] != original["region"]:
        problems.append("the copy did not keep the original's settings")
    if copy["region"] is original["region"]:
        problems.append("the copy shares its region with the original - editing "
                        "one would change both")
    if copy["name"] != "Handle burst lightning copy":
        problems.append(f"the copy is named {copy['name']!r}, which does not "
                        "tell it apart from the original")
    if app.selected != 1:
        problems.append(f"the copy was not selected (selection is {app.selected})")

    # A step still on its default name gains nothing from being marked.
    app.selected = 2
    app.duplicate()
    root.update()
    if app.sequence.steps[3]["name"] != plain["name"]:
        problems.append(f"a default name was marked up: "
                        f"{app.sequence.steps[3]['name']!r}")

    # Ctrl+D duplicates from anywhere, including a text field -- where Tk's
    # own Ctrl+D would otherwise eat the character ahead of the caret.
    from tkinter import ttk

    root.deiconify()
    root.geometry("1100x760+30+30")
    root.update()
    root.focus_force()
    app.selected = 0
    app.build_editor()
    root.update()
    name_var = app.field_vars["name"]
    entry = next((w for w in _descendants(app.editor)
                  if isinstance(w, ttk.Entry)
                  and str(w.cget("textvariable")) == str(name_var)), None)
    if entry is not None:
        entry.focus_set()
        entry.icursor(0)
        root.update()
        if root.focus_get() is entry:
            before = len(app.sequence.steps)
            was = name_var.get()
            entry.event_generate("<Control-d>")
            root.update()
            if len(app.sequence.steps) != before + 1:
                problems.append("Ctrl+D did not duplicate the step")
            if name_var.get() != was:
                problems.append(f"Ctrl+D ate a character: {was!r} -> "
                                f"{name_var.get()!r}")
        else:
            print("  (Ctrl+D not checked: the entry could not take focus)")
    root.withdraw()

    print("Duplicate ok: settings copied, copy named apart, selected, Ctrl+D works")
    return problems


def check_choices_read_as_english():
    """Dropdowns show plain English but still store the short value."""
    from tkinter import ttk

    problems = []
    first = dict(step_defs.new_step("section"), name="Before Game")
    second = dict(step_defs.new_step("section"), name="In Game")
    step = step_defs.new_step("wait_for_image")
    app.sequence = engine_mod.Sequence(name="choices",
                                       steps=[first, second, step])
    app.refresh_list(keep=0)
    app.selected = 2
    # The note under the dropdown is an explanation like any other, so it is
    # only drawn with Hints on. Off, it lives on the dropdown as a tooltip.
    was_showing = bool(app.show_hints.get())
    app.show_hints.set(True)
    app.build_editor()
    root.update()

    var = app.field_vars["on_timeout"]
    if var.get() != step_defs.ON_TIMEOUT_LABELS["restart"]:
        problems.append(f"the dropdown shows {var.get()!r}, not the plain "
                        "English label")
    combo = next((w for w in _descendants(app.editor)
                  if isinstance(w, ttk.Combobox)
                  and str(w.cget("textvariable")) == str(var)), None)
    if combo is None:
        problems.append("could not find the on_timeout dropdown")
        return problems
    if "next_section" in combo.cget("values"):
        problems.append(f"raw values still on show: {combo.cget('values')}")

    # Picking one stores the short value, which is what the engine reads.
    var.set(step_defs.ON_TIMEOUT_LABELS["next_section"])
    root.update()
    if step["on_timeout"] != "next_section":
        problems.append(f"choosing a label stored {step['on_timeout']!r}")

    # The note underneath follows the choice, and names the real sections, so
    # "the whole sequence" can never be mistaken for "this section".
    shown = [_text_of(w) for w in _descendants(app.editor)]
    expected = step_defs.outcome_note("next_section", app.sequence.steps, 2)
    if not any(expected in text for text in shown):
        problems.append("the note under the dropdown did not follow the choice")
    if "In Game" not in expected:
        problems.append(f"the note does not name the section: {expected!r}")
    if "{" in expected:
        problems.append(f"the note still has a placeholder in it: {expected!r}")

    var.set(step_defs.ON_TIMEOUT_LABELS["restart"])
    root.update()
    restart_note = step_defs.outcome_note("restart", app.sequence.steps, 2)
    if "In Game" not in restart_note or "Before Game" not in restart_note:
        problems.append(f"'restart' does not name both sections: {restart_note!r}")
    if not any(restart_note in text for text in
               [_text_of(w) for w in _descendants(app.editor)]):
        problems.append("the note did not update when the choice changed")
    print(f"  restart reads: {restart_note}")

    print("Choices ok: dropdowns read as English, files keep the short value")
    app.show_hints.set(was_showing)
    return problems

def check_deleting_a_step_offers_to_delete_its_image():
    """An orphaned picture is offered up; a shared one is left alone."""
    import cv2
    import numpy as np
    from tkinter import messagebox

    from pixie.paths import IMAGES_DIR, APP_DIR, SEQUENCES_DIR

    problems = []
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    lonely = IMAGES_DIR / "_orphan_probe.png"
    shared = IMAGES_DIR / "_shared_probe.png"
    for path in (lonely, shared):
        cv2.imwrite(str(path), np.random.randint(0, 255, (20, 20, 3), dtype=np.uint8))

    asked = []
    original_ask = gui.messagebox.askyesno
    gui.messagebox.askyesno = lambda *a, **k: (asked.append(a[1]), True)[1]

    other_sequence = SEQUENCES_DIR / "_probe_other.json"
    try:
        lonely_rel = lonely.relative_to(APP_DIR).as_posix()
        shared_rel = shared.relative_to(APP_DIR).as_posix()

        # Another saved sequence uses the shared one.
        other = engine_mod.Sequence(name="other", steps=[
            dict(step_defs.new_step("click_image"), image=shared_rel)])
        other.save(other_sequence)

        one = dict(step_defs.new_step("click_image"), image=lonely_rel)
        two = dict(step_defs.new_step("click_image"), image=shared_rel)
        twin = dict(step_defs.new_step("click_image"), image=lonely_rel)
        app.sequence = engine_mod.Sequence(name="deleting", steps=[one, two, twin])
        app.refresh_list(keep=0)
        root.update()

        # 1. a copy of the step still needs the file, so nothing is offered.
        app.selected = 0
        app.remove()
        root.update()
        if asked:
            problems.append("offered to delete a picture another step still uses")
        if not lonely.exists():
            problems.append("deleted a picture another step still uses")

        # 2. now it is the last user of it, so we are asked, and it goes.
        app.selected = 1              # the twin, after the first removal
        app.remove()
        root.update()
        if len(asked) != 1:
            problems.append(f"was asked {len(asked)} times about an orphan, "
                            "expected once")
        if lonely.exists():
            problems.append("said yes, but the picture is still there")

        # 3. the shared one belongs to another sequence: never offered.
        asked.clear()
        app.selected = 0
        app.remove()
        root.update()
        if asked:
            problems.append("offered to delete a picture another sequence uses")
        if not shared.exists():
            problems.append("deleted a picture another sequence uses")

        print("Deleting ok: orphaned pictures offered up, shared ones left alone")
    finally:
        gui.messagebox.askyesno = original_ask
        other_sequence.unlink(missing_ok=True)
        lonely.unlink(missing_ok=True)
        shared.unlink(missing_ok=True)
    return problems


def check_boxes_can_be_typed_into():
    """A box can be stretched by editing its numbers, not only by re-dragging."""
    problems = []
    step = dict(step_defs.new_step("click_box"), box=[100, 200, 300, 400])
    region_step = dict(step_defs.new_step("click_image"),
                       image="images/x.png", region=[10, 20, 30, 40])
    app.sequence = engine_mod.Sequence(name="boxes", steps=[step, region_step])
    app.refresh_list(keep=0)
    app.selected = 0
    app.build_editor()
    root.update()

    if "box" not in app.region_boxes:
        problems.append("a click box has no editable numbers")
        return problems

    boxes = app.region_boxes["box"][0]
    for name, value in (("width", "640"), ("left", "55")):
        boxes[name].set(value)
        root.update()
    if step["box"] != [55, 200, 640, 400]:
        problems.append(f"typing into the numbers gave {step['box']}")

    # Half-typed input must not wreck the stored box.
    boxes["left"].set("")
    root.update()
    if step["box"] != [55, 200, 640, 400]:
        problems.append(f"clearing a box mid-edit changed it to {step['box']}")
    boxes["width"].set("0")
    root.update()
    if step["box"][2] == 0:
        problems.append("a zero width was accepted as a box")
    boxes["left"].set("55")
    root.update()

    # The readable summary keeps up with the numbers.
    if "640x400 at 55, 200" not in app.field_vars["box"].get():
        problems.append(f"the summary did not follow: {app.field_vars['box'].get()!r}")

    # Search areas on an image step get the same treatment.
    app.selected = 1
    app.build_editor()
    root.update()
    if "region" not in app.region_boxes:
        problems.append("a search area has no editable numbers")
    else:
        app.region_boxes["region"][0]["height"].set("900")
        root.update()
        if region_step["region"] != [10, 20, 30, 900]:
            problems.append(f"search area edit gave {region_step['region']}")

    print("Boxes ok: left, top, width and height are typeable")
    return problems


def check_panes_can_be_dragged():
    """The dividers between sequence, editor and log move, and are remembered."""
    import json
    import tempfile

    problems = []
    original_state_path = gui.STATE_PATH
    gui.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    try:
        first_root = tk.Tk()
        first = gui.App(first_root)
        first_root.deiconify()
        first_root.geometry("1400x900+80+50")
        first_root.update()
        first_root.update_idletasks()

        narrow = first.listbox.winfo_width()
        first.split_across.sashpos(0, 640)
        first.split_down.sashpos(0, 420)
        first_root.update()
        wide = first.listbox.winfo_width()
        if wide <= narrow:
            problems.append(f"dragging the divider did not widen the sequence "
                            f"list ({narrow} -> {wide})")
        if first.log_text.winfo_height() <= 1:
            problems.append("the log collapsed to nothing")

        first.save_preferences()
        first.on_close()
        written = json.loads(gui.STATE_PATH.read_text(encoding="utf-8"))
        for name in ("split_across", "split_down"):
            if not isinstance(written.get(name), int):
                problems.append(f"{name} was not remembered")

        second_root = tk.Tk()
        second = gui.App(second_root)
        second_root.deiconify()
        second_root.geometry("1400x900+80+50")
        second_root.update()
        second_root.update_idletasks()
        second_root.update()
        back = second.split_across.sashpos(0)
        if abs(back - 640) > 40:
            problems.append(f"the divider came back at {back}, expected near 640")
        second.on_close()
        print(f"Panes ok: dividers move, remembered at {written['split_across']} "
              f"and {written['split_down']}")
    finally:
        gui.STATE_PATH = original_state_path
    return problems


def check_what_matches_window():
    """The What matches? window must actually list the patches it found.

    Regression test. The viewer was reading the patch list in the shape it
    had before saturation notes were added, so it rendered its heading and
    then threw - leaving a window with 'Would be used, in order' and nothing
    underneath. Building the window is the only way to catch that.
    """
    import cv2
    import numpy as np

    from pixie.system import screen as screen_mod

    problems = []

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    # A vivid outline that runs off the left edge, plus a clean one.
    frame = np.zeros((300, 900, 3), dtype=np.uint8)
    frame[:, :] = hsv(110, 80, 60)
    frame[40:260, 0:40] = hsv(90, 250, 250)        # cut off by the left edge
    for y0, y1, x0, x1 in ((60, 76, 400, 700), (240, 256, 400, 700),
                           (60, 256, 400, 416), (60, 256, 684, 700)):
        frame[y0:y1, x0:x1] = hsv(90, 250, 250)    # a whole outline

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        # Away from the edges of the screen, or a patch touching the edge of
        # the area is the monitor's doing and is deliberately not flagged.
        picture, kept, dropped = screen_mod.explain_colors(
            (500, 500, 900, 300), (37, 254, 254), tolerance=14, min_pixels=39,
            match="hue", order="leftmost", join=20)
    finally:
        screen_mod.grab = original

    if len(kept) < 2:
        problems.append(f"the sample only produced {len(kept)} patches")
        return problems

    step = dict(step_defs.new_step("wait_for_color_in_area"), name="probe")
    root.deiconify()
    root.update()
    try:
        viewer = gui.show_matches(root, picture, kept, dropped, step)
        root.update()
        shown = [w for w in _descendants(viewer.window) if isinstance(w, tk.Text)]
        if not shown:
            problems.append("the window has no report in it")
            return problems
        text = shown[0].get("1.0", "end")
        for wanted in ("1.", "pixels", "saturation"):
            if wanted not in text:
                problems.append(f"the report does not mention {wanted!r}: {text!r}")
        if text.count("\n") < len(kept) + 1:
            problems.append(f"the report has {text.count(chr(10))} lines for "
                            f"{len(kept)} patches - it stopped early")
        if "cut off" not in text:
            problems.append("a patch running off the edge was not flagged as "
                            f"cut off: {text!r}")
        # The 40px sliver and the 300px outline are two clear shapes, so the
        # report has to name the setting that tells them apart, spelled the
        # way the editor spells it.
        advice = [line for line in text.splitlines() if "split into two" in line]
        if not advice:
            problems.append(f"two very different shapes drew no advice: {text!r}")
        elif "Patch at least this wide (px)" not in advice[0]:
            problems.append(f"the advice does not name the real setting: {advice[0]!r}")
        else:
            print("  " + advice[0].strip())
        print("What matches ok: " + text.strip().splitlines()[1].strip()[:70])
        viewer.window.destroy()
    finally:
        root.withdraw()
    return problems


def check_show_the_click():
    """'Show the click' must work the point out the way a run would.

    Including the awkward case: a step that clicks whatever was found last
    has nothing to show on its own, so the step before it has to be run
    first.
    """
    import cv2
    import numpy as np

    from pixie.system import screen as screen_mod

    problems = []

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    frame = np.zeros((400, 900, 3), dtype=np.uint8)
    frame[100:340, 200:600] = hsv(90, 250, 250)   # one solid patch to find
    def fake_grab(region=None):
        """Pretend the sample frame is sitting at the top left of the desktop."""
        if region is None:
            return frame
        left, top, width, height = region
        out = np.zeros((height, width, 3), dtype=np.uint8)
        x0, y0 = max(left, 0), max(top, 0)
        x1 = min(left + width, frame.shape[1])
        y1 = min(top + height, frame.shape[0])
        if x1 > x0 and y1 > y0:
            out[y0 - top:y1 - top, x0 - left:x1 - left] = frame[y0:y1, x0:x1]
        return out

    original = screen_mod.grab
    screen_mod.grab = fake_grab

    finder = dict(step_defs.new_step("wait_for_color_in_area"),
                  name="find it", region=[0, 0, 900, 400], color=[37, 254, 254],
                  match="hue", tolerance=14, min_pixels=39, timeout=1.0)
    clicker = dict(step_defs.new_step("click_last_match"), name="click it",
                   anchor="left", offset=[50, 0], clicks=2)
    fixed = dict(step_defs.new_step("click_point"), name="fixed", pos=[640, 480])

    app.sequence = engine_mod.Sequence(name="clicks",
                                       steps=[finder, clicker, fixed])
    app.refresh_list(keep=0)
    try:
        # 1. the step that clicks the last match: the finder must run first.
        app.selected = 1
        needed = app._steps_for_preview(clicker)
        if [s.get("name") for s in needed] != ["find it", "click it"]:
            problems.append(f"it would rehearse {[s.get('name') for s in needed]}, "
                            "not the finder and then the click")
        points, boxes, lines = app._rehearse(needed, clicker)
        if not points:
            problems.append("no click point was worked out")
            return problems
        # The patch is 400x240 at 200,100, so its left edge plus the 50 offset
        # is x=250, and the middle of that edge is row 219 (100..339).
        if points[0] != (250, 219):
            problems.append(f"the click point came out as {points[0]}, "
                            "expected (250, 219)")
        if not any("Would click" in text for text, _ in lines):
            problems.append(f"the report does not say where: {lines}")
        if not boxes:
            problems.append("what it found was not reported as a box")

        # 2. a fixed spot needs nothing run first.
        app.selected = 2
        if [s.get("name") for s in app._steps_for_preview(fixed)] != ["fixed"]:
            problems.append("a fixed click dragged another step into it")
        points, _boxes, _lines = app._rehearse([fixed], fixed)
        if points[0] != (640, 480):
            problems.append(f"a fixed click previewed as {points[0]}")

        # 3. the picture gets marked where the click goes.
        picture, region = screen_mod.picture_around(*points[0], 400, 300)
        marked = screen_mod.mark_up(picture, region, points=points,
                                    boxes=[(600, 440, 80, 80)])
        if marked.shape != picture.shape:
            problems.append("marking up changed the size of the picture")
        if not (marked != picture).any():
            problems.append("marking up drew nothing at all")
        print(f"Show the click ok: {points[0]} marked on a "
              f"{region[2]}x{region[3]} view")
    finally:
        screen_mod.grab = original
    return problems


def check_testing_a_step_runs_it_once():
    """'Test this step' must run the step once, whatever 'If not found' says.

    Regression test. It used to hand the step to the engine's own loop, so a
    step set to 'go back to the first step of this section' was a section of
    one step that retried itself forever. Testing it never came back.
    """
    import numpy as np

    from pixie.system import screen as screen_mod

    problems = []
    original = screen_mod.grab
    screen_mod.grab = lambda region=None: np.zeros(
        (region[3] if region else 600, region[2] if region else 800, 3),
        dtype=np.uint8)
    try:
        # A color that is nowhere on a black screen, so the step always fails.
        for on_timeout in step_defs.ON_TIMEOUT:
            step = dict(step_defs.new_step("wait_for_color_in_area"),
                        name=f"never {on_timeout}", region=[0, 0, 400, 300],
                        color=[37, 254, 254], timeout=0.05,
                        on_timeout=on_timeout)
            sequence = engine_mod.Sequence(name="test", steps=[step])
            tester = engine_mod.Engine(sequence, emit=lambda _e: None,
                                       dry_run=True)
            finished = []
            tester.emit = lambda event: finished.append(event.get("kind"))

            done = threading.Event()

            def run():
                gui.App._run_one(tester, step)
                done.set()

            threading.Thread(target=run, daemon=True).start()
            if not done.wait(timeout=5.0):
                problems.append(f"testing a step set to {on_timeout!r} did not "
                                "come back within 5 seconds")
                tester.stop()
            elif "finished" not in finished:
                problems.append(f"testing a step set to {on_timeout!r} never "
                                "reported that it had finished")
        print(f"Test-one-step ok: all {len(step_defs.ON_TIMEOUT)} 'if not "
              "found' settings run once and return")
    finally:
        screen_mod.grab = original
    return problems


def check_window_size_is_remembered():
    """Maximized, and the size behind it, survive a restart and a capture."""
    import json
    import tempfile

    problems = []
    original_state_path = gui.STATE_PATH
    gui.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    try:
        first_root = tk.Tk()
        first = gui.App(first_root)
        first_root.deiconify()
        min_width, min_height = first_root.minsize()
        want = f"{min_width + 140}x{min_height + 100}+120+80"
        first_root.geometry(want)
        first_root.update()
        first_root.state("zoomed")          # maximize it, as the user had
        first_root.update()

        # Capturing hides and re-shows the window; it must come back maximized.
        was = first_root.state()
        first._restore_window(first._last_normal_geometry, was == "zoomed")
        first_root.withdraw()
        first_root.update()
        first_root.deiconify()
        first._restore_window(first._last_normal_geometry, True)
        first_root.update()
        if first_root.state() != "zoomed":
            problems.append("the window did not come back maximized after a "
                            "capture")

        first.save_preferences()
        first.on_close()

        written = json.loads(gui.STATE_PATH.read_text(encoding="utf-8"))
        if not written.get("maximized"):
            problems.append("maximized was not remembered")
        saved = str(written.get("geometry") or "")
        if saved.split("+")[0] != want.split("+")[0]:
            problems.append(f"the size behind the maximized window was saved as "
                            f"{written.get('geometry')!r}, expected {want!r}")

        second_root = tk.Tk()
        second = gui.App(second_root)
        second_root.update()
        if second_root.state() != "zoomed":
            problems.append(f"reopened as {second_root.state()!r}, not maximized")
        second.on_close()
        print(f"Window ok: reopened maximized, restores to "
              f"{written.get('geometry')}")
    finally:
        gui.STATE_PATH = original_state_path
    return problems


def check_settings_stick():
    """Changing a setting writes it to the sequence, so it survives a reload."""
    import tempfile

    problems = []
    original_dialog = gui.SettingsDialog
    target = Path(tempfile.mkdtemp()) / "settings.json"

    class FakeDialog:
        """Stands in for the modal: sets what the user would have set."""

        def __init__(self, parent, settings, scale=1.0, show_hints=None):
            self.settings = settings

        def run(self):
            self.settings.park_mouse = "custom"
            self.settings.park_box = [1234, 567, 40, 20]
            self.settings.travel_style = "drift"
            return True

    gui.SettingsDialog = FakeDialog
    try:
        app.sequence = engine_mod.Sequence(name="sticky",
                                           steps=[step_defs.new_step("press_key")])
        app.sequence.save(target)
        app.refresh_list(keep=0)
        app.edit_settings()
        root.update()

        reloaded = engine_mod.Sequence.load(target)
        if reloaded.settings.park_mouse != "custom":
            problems.append("the park setting was not written to the sequence, "
                            "so it would be lost on the next open")
        if reloaded.settings.park_box != [1234, 567, 40, 20]:
            problems.append(f"the parked spot came back as "
                            f"{reloaded.settings.park_box}")
        if reloaded.settings.travel_style != "drift":
            problems.append("the travel style did not survive a save")
        if app.dirty:
            problems.append("the sequence was left unsaved after saving settings")
        print("Settings ok: written to the sequence as soon as they change")
    finally:
        gui.SettingsDialog = original_dialog
        target.unlink(missing_ok=True)
    return problems


def check_image_and_color_previews():
    """An image step shows the picture; a color step shows the color."""
    import cv2
    import numpy as np

    from pixie.paths import IMAGES_DIR, APP_DIR

    problems = []
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    sample = IMAGES_DIR / "_preview_probe.png"
    cv2.imwrite(str(sample), np.random.randint(0, 255, (48, 90, 3), dtype=np.uint8))

    try:
        step = step_defs.new_step("click_image")
        step["image"] = sample.relative_to(APP_DIR).as_posix()
        color_step = step_defs.new_step("wait_for_color")
        color_step["color"] = [12, 200, 240]
        missing = step_defs.new_step("click_image")
        missing["image"] = "images/_does_not_exist.png"

        app.sequence = engine_mod.Sequence(
            name="previews", steps=[step, color_step, missing])
        app.refresh_list(keep=0)
        root.update()

        # 1. a real image renders as an actual picture
        app.selected = 0
        app.build_editor()
        root.update()
        labels = [w for w in _descendants(app.editor)
                  if isinstance(w, tk.Label) and getattr(w, "image", None)]
        if not labels:
            problems.append("image step showed no thumbnail")
        else:
            shown = labels[0].image
            print(f"  image preview: {shown.width()}x{shown.height()} thumbnail "
                  f"of a 90x48 capture")
        if not any("90 x 48" in _text_of(w) for w in _descendants(app.editor)):
            problems.append("image preview did not report the pixel size")

        # 2. a color renders as a filled swatch of that color
        app.selected = 1
        app.build_editor()
        root.update()
        wanted = "#%02x%02x%02x" % (12, 200, 240)
        swatches = [w for w in _descendants(app.editor)
                    if isinstance(w, tk.Frame) and str(w.cget("bg")) == wanted]
        if not swatches:
            problems.append(f"color step showed no swatch of {wanted}")
        else:
            print(f"  color preview: swatch filled {wanted}")
        if not any("#0cc8f0" in _text_of(w).lower() for w in _descendants(app.editor)):
            problems.append("color field did not show the hex value")

        # 3. a missing file says so rather than rendering nothing
        app.selected = 2
        app.build_editor()
        root.update()
        if not any("missing" in _text_of(w).lower() for w in _descendants(app.editor)):
            problems.append("a missing image file was not reported in the editor")
        else:
            print("  missing file: reported in the editor")
    finally:
        sample.unlink(missing_ok=True)
    return problems


def check_indenting_steps():
    """Indent and outdent must work, show, and refuse where it means nothing."""
    problems = []
    check = dict(step_defs.new_step("wait_for_image"), name="Is it there")
    check["on_timeout"] = "skip_block"
    action = dict(step_defs.new_step("click_box"), name="Do the thing")
    later = dict(step_defs.new_step("press_key"), name="Afterwards")

    app.sequence = engine_mod.Sequence(name="indents",
                                       steps=[check, action, later])
    app.refresh_list(keep=1)
    root.update()

    # 1. indenting under a check that can fail
    app.selected = 1
    app.indent()
    root.update()
    if step_defs.indent_of(action) != 1:
        problems.append("indenting under a check did nothing")
    if "↳" not in app.listbox.get(1):
        problems.append(f"an indented step is drawn no differently: "
                        f"{app.listbox.get(1)!r}")

    # 2. the first step has nothing above it to be guarded by
    app.selected = 0
    app.indent()
    root.update()
    if step_defs.indent_of(check):
        problems.append("the first step was indented under nothing")

    # 3. outdent puts it back, leaving no leftover key in the file
    app.selected = 1
    app.outdent()
    root.update()
    if "indent" in action:
        problems.append(f"outdent left {action.get('indent')!r} behind")

    # 4. deleting the check must not leave the action looking guarded
    app.selected = 1
    app.indent()
    app.selected = 0
    app.remove()
    root.update()
    if step_defs.indent_of(app.sequence.steps[0]):
        problems.append("deleting the check left its action still indented")

    # 5. switching the check off has to show on the group, because the run
    # skips the whole thing. Drawn in full color it read as still active, and
    # the only way to find out otherwise was to run the sequence.
    app.sequence = engine_mod.Sequence(
        name="inert", steps=[check, dict(action, indent=1), later])
    from pixie.ui import theme
    app.refresh_list(keep=0)
    root.update()
    lit = str(app.listbox.itemcget(1, "foreground"))
    app.selected = 0
    app.toggle_enabled()
    root.update()
    dimmed = str(app.listbox.itemcget(1, "foreground"))
    if dimmed != theme.DISABLED:
        problems.append(f"switching a check off left its group drawn "
                        f"{dimmed!r}, expected {theme.DISABLED!r}")
    if lit == dimmed:
        problems.append("a group looks the same whether its check is on or off")
    if str(app.listbox.itemcget(2, "foreground")) == theme.DISABLED:
        problems.append("the step after the group was dimmed too")
    app.selected = 0
    app.toggle_enabled()
    root.update()
    if str(app.listbox.itemcget(1, "foreground")) == theme.DISABLED:
        problems.append("switching the check back on left its group dimmed")

    print("Indenting ok: indents under a check, refuses at the top, "
          "un-indents when its check is deleted, dims its group when off")
    return problems


def check_every_explanation_obeys_the_hints_box():
    """Hints off should mean no paragraphs, on every step type.

    The note under an 'If it is not found' dropdown was drawn regardless, so a
    panel with Hints off still carried a paragraph of explanation - and it was
    the longest one in the editor. Anything styled as a blurb is an
    explanation, so anything styled as a blurb has to answer to the box.
    """
    problems = []
    was = bool(app.show_hints.get())

    def paragraphs():
        found = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    if str(child.cget("style")) == "Blurb.TLabel":
                        text = str(child.cget("text")).strip()
                        # Short ones are captions beside a box - "left",
                        # "down", the size under a preview - not explanations.
                        if len(text) > 25:
                            found.append(text[:60])
                except tk.TclError:
                    pass
                walk(child)

        walk(app.editor)
        return found

    try:
        for kind in step_defs.STEP_TYPES:
            app.sequence = engine_mod.Sequence(name="gating",
                                               steps=[step_defs.new_step(kind)])
            app.selected = 0

            app.show_hints.set(False)
            app.build_editor()
            root.update()
            escaped = paragraphs()
            if escaped:
                problems.append(f"{kind}: {len(escaped)} explanation(s) shown "
                                f"with Hints off: {escaped}")

            app.show_hints.set(True)
            app.build_editor()
            root.update()
            if not paragraphs() and step_defs.STEP_TYPES[kind].blurb:
                problems.append(f"{kind}: Hints on showed no explanation at all")
    finally:
        app.show_hints.set(was)
        app.selected = -1
        app.sequence = engine_mod.Sequence(name="selftest_gui")
        app.refresh_list()

    print(f"Hint gating ok: {len(step_defs.STEP_TYPES)} step types, no "
          "explanation escapes the box")
    return problems


def check_settings_hints_can_be_hidden():
    """Settings has a paragraph per row and nine rows of numbers.

    The same Hints box the editor uses hides them there too, and a hidden
    paragraph has to stay reachable or the dialog becomes a wall of unexplained
    boxes. One hint had been written without a wraplength, and the old test for
    "is this a paragraph" asked exactly that, so it was neither stretched nor
    hidden.
    """
    problems = []
    box = tk.BooleanVar(value=False)
    dialog = gui.SettingsDialog(root, engine_mod.Settings(), 1.0, show_hints=box)
    try:
        if len(dialog.hints) < 10:
            problems.append(f"only {len(dialog.hints)} paragraphs found in "
                            "Settings, so some are not being managed")

        # grid_remove leaves a widget with no grid_info; winfo_ismapped is no
        # use here, because the test window is withdrawn and nothing is mapped.
        hidden = [label for label, _caption in dialog.hints
                  if not label.grid_info()]
        if len(hidden) != len(dialog.hints):
            showing = [str(label.cget("text"))[:40]
                       for label, _c in dialog.hints if label.grid_info()]
            problems.append(f"with Hints off, {len(showing)} paragraphs were "
                            f"still on screen: {showing}")

        # Hidden does not mean lost: the caption above each one explains it.
        without = [str(label.cget("text"))[:40] for label, caption in dialog.hints
                   if caption is not None
                   and not getattr(caption, "_hint_tip", None)]
        if without:
            problems.append(f"paragraphs hidden with nothing to reach them "
                            f"by: {without}")
        tips = [getattr(caption, "_hint_tip", None)
                for _label, caption in dialog.hints if caption is not None]
        if any(tip is not None and not tip.text for tip in tips):
            problems.append("a caption's tooltip was empty while its "
                            "paragraph was hidden")

        short = dialog.window.winfo_reqheight()
        box.set(True)
        dialog._hints_toggled()
        root.update()
        tall = dialog.window.winfo_reqheight()
        back = [label for label, _c in dialog.hints if label.grid_info()]
        if len(back) != len(dialog.hints):
            problems.append(f"turning Hints on brought back {len(back)} of "
                            f"{len(dialog.hints)} paragraphs")
        if tall <= short:
            problems.append(f"showing the paragraphs did not make the dialog "
                            f"taller: {short} -> {tall}")
        # ...and the tooltips go quiet again, rather than repeating what is
        # already on screen.
        loud = [tip for tip in tips if tip is not None and tip.text]
        if loud:
            problems.append(f"{len(loud)} tooltips still had text while the "
                            "paragraphs were visible")
    finally:
        dialog.window.destroy()

    print(f"Settings hints ok: {len(dialog.hints)} paragraphs hide and come "
          f"back, {short}px -> {tall}px")
    return problems


def check_the_log_stays_a_sensible_size():
    """The log is capped, so an overnight run does not fill memory with it.

    A busy loop writes about ten lines a second. Left alone that is most of a
    million lines by morning, and Tk holds every one of them with its tags and
    gets steadily slower at appending. Nothing is written to disk, so these
    lines are the only copy, and they are worth less the older they get.
    """
    app.clear_log()
    problems = []

    def lines():
        return int(app.log_text.index("end-1c").split(".")[0])

    for n in range(gui.LOG_MAX_LINES + 600):
        app.log(f"line {n}")

    held = lines()
    if held > gui.LOG_MAX_LINES:
        problems.append(f"after {gui.LOG_MAX_LINES + 600} lines the log holds "
                        f"{held}, over its own limit of {gui.LOG_MAX_LINES}")
    if held < gui.LOG_KEEP_LINES // 2:
        problems.append(f"the log trimmed down to {held} lines, far more than "
                        "asked - it is throwing away what you are watching")

    # The newest line has to survive. Trimming the wrong end would be worse
    # than not trimming at all.
    body = app.log_text.get("1.0", "end")
    last = f"line {gui.LOG_MAX_LINES + 600 - 1}"
    if last not in body:
        problems.append(f"the most recent line ({last}) was trimmed away")
    if "line 0\n" in body:
        problems.append("the oldest line survived, so the wrong end was cut")
    if "earlier lines dropped" not in body:
        problems.append("the log was trimmed without saying so")

    app.clear_log()
    if lines() != 1:
        problems.append("clearing the log did not empty it")

    print(f"Log size ok: {gui.LOG_MAX_LINES + 600} lines written, {held} held, "
          "newest kept")
    return problems


def check_no_hidden_keybinds():
    """The window answers to the declared shortcuts and nothing else.

    There used to be an F5 in here that started the run. Nothing mentioned it,
    Settings did not list it, and the only way to discover it was to press it
    and watch your screen start being clicked. A key that begins clicking has
    no business being undocumented.

    So the bindings are made from one table, and this fails if the window has
    picked up anything that is not in it.
    """
    problems = []
    # Tk answers with its own spelling - <Control-s> comes back as
    # <Control-Key-s> - so both sides are compared in the same one.
    def plain(name):
        return str(name).replace("Key-", "")

    declared = {plain(sequence) for sequence, _method, _what in gui.SHORTCUTS}
    # Tk reports every binding on the toplevel, including the ones that are
    # not keys at all.
    bound = {plain(name) for name in root.bind()}
    events = {name for name in bound if name.startswith("<Key") or
              any(part in name for part in ("Control-", "Alt-", "F1", "F2", "F3",
                                            "F4", "F5", "F6", "F7", "F8", "F9",
                                            "F10", "F11", "F12"))}
    extra = events - declared
    if extra:
        problems.append(f"the window answers to keys nothing declares: {sorted(extra)}")
    missing = declared - bound
    if missing:
        problems.append(f"declared shortcuts that are not bound: {sorted(missing)}")

    # Nothing in the table may start or stop a run - that is the global
    # hotkey's job, and it is in Settings where it can be seen and changed.
    for sequence, method, _what in gui.SHORTCUTS:
        if method in ("toggle_run", "start", "stop"):
            problems.append(f"{sequence} runs the sequence; that belongs to the "
                            "start/stop key in Settings")
        if not hasattr(app, method):
            problems.append(f"{sequence} points at missing App.{method}")

    print(f"Keybinds ok: {len(declared)} declared, none hidden, none of them "
          "start a run")
    return problems


def check_moving_keeps_groups_together():
    """Nudging a step must not quietly ungroup it."""
    problems = []

    def look(name):
        step = dict(step_defs.new_step("wait_for_image"), name=name)
        step["on_timeout"] = "skip_block"
        return step

    check = look("Check")
    one = dict(step_defs.new_step("click_box"), name="One")
    two = dict(step_defs.new_step("click_box"), name="Two")
    other = look("Other")

    app.sequence = engine_mod.Sequence(name="moves",
                                       steps=[check, one, two, other])
    app.refresh_list(keep=1)
    app.selected = 1
    app.indent()
    app.selected = 2
    app.indent()
    root.update()
    if [step_defs.indent_of(s) for s in app.sequence.steps] != [0, 1, 1, 0]:
        problems.append(f"setting up the group failed: "
                        f"{[s['name'] for s in app.sequence.steps]}")
        return problems

    # 1. Moving the check down takes its group with it.
    app.selected = 0
    app.move_down()
    root.update()
    names = [s["name"] for s in app.sequence.steps]
    if names != ["Other", "Check", "One", "Two"]:
        problems.append(f"moving the check gave {names}, expected its group "
                        "to travel with it")
    if [step_defs.indent_of(s) for s in app.sequence.steps] != [0, 0, 1, 1]:
        problems.append("the group lost its indent when the check moved")

    # 2. Reordering inside the group keeps both indented.
    app.selected = 2
    app.move_down()
    root.update()
    names = [s["name"] for s in app.sequence.steps]
    if names != ["Other", "Check", "Two", "One"]:
        problems.append(f"reordering inside the group gave {names}")
    if [step_defs.indent_of(s) for s in app.sequence.steps] != [0, 0, 1, 1]:
        problems.append("reordering inside the group dropped an indent")

    # 3. Moving the last one down again takes it out of the group, which is
    #    the only thing it can mean - and does not split the group in half.
    app.selected = 3
    app.move_down()
    root.update()
    if step_defs.indent_of(app.sequence.steps[3]):
        problems.append("the last step in a group could not step out of it")
    if not step_defs.indent_of(app.sequence.steps[2]):
        problems.append("stepping out of a group took the others with it")

    print("Moving ok: a check carries its group, reordering inside keeps it, "
          "the last one can step out")
    return problems


def check_add_menu_is_grouped():
    """Add step lists every type under a heading, with a hint on each."""
    problems = []
    captured = {}

    # tk_popup blocks on a real menu, so catch the menu as it is posted.
    original = tk.Menu.tk_popup
    tk.Menu.tk_popup = lambda self, *rest: captured.setdefault("menu", self)
    try:
        app._show_add_menu()
    finally:
        tk.Menu.tk_popup = original

    menu = captured.get("menu")
    if menu is None:
        return ["Add step never posted a menu"]

    headings, entries = [], {}
    for index in range(menu.index("end") + 1):
        if menu.type(index) == "separator":
            continue
        label = str(menu.entrycget(index, "label"))
        if str(menu.entrycget(index, "state")) == "disabled":
            headings.append(label)
        else:
            entries[label.strip()] = str(menu.entrycget(index, "accelerator"))

    wanted = [heading.upper() for heading, _ in step_defs.STEP_GROUPS]
    if headings != wanted:
        problems.append(f"menu headings are {headings}, expected {wanted}")

    for key, step_type in step_defs.STEP_TYPES.items():
        if step_type.label not in entries:
            problems.append(f"{key!r} is missing from the Add step menu")
        elif not entries[step_type.label]:
            problems.append(f"{key!r} has no hint beside it in the menu")

    print(f"  add menu: {len(headings)} headings, {len(entries)} step types, "
          "all with a hint")
    print(f"    {headings[1]}: " + ", ".join(
        step_defs.STEP_TYPES[key].label for key in step_defs.STEP_GROUPS[1][1]))
    return problems


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _text_of(widget) -> str:
    """Whatever this widget is showing.

    Entry-like widgets must be asked with get(). cget("text") on a ttk entry
    returns the name of its text variable, not the text, which looks like a
    real answer and silently is not.
    """
    from tkinter import ttk

    if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox, ttk.Spinbox)):
        try:
            return str(widget.get())
        except tk.TclError:
            return ""
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return ""


def check_preferences_persist():
    """Dry run, minimize and the window geometry survive a restart."""
    import json
    import tempfile

    problems = []
    original_state_path = gui.STATE_PATH
    temp_state = Path(tempfile.mkdtemp()) / "state.json"
    gui.STATE_PATH = temp_state
    try:
        first_root = tk.Tk()
        first = gui.App(first_root)
        first.dry_run.set(False)
        first.hide_while_running.set(False)
        # Must be above the window's own minimum, or Tk clamps it and the
        # size we read back is the minimum rather than what we asked for.
        min_width, min_height = first_root.minsize()
        want = f"{min_width + 120}x{min_height + 90}+150+90"
        first_root.geometry(want)
        first_root.update()
        first.save_preferences()
        first.on_close()

        written = json.loads(temp_state.read_text(encoding="utf-8"))
        for key in ("dry_run", "minimize_while_running", "geometry"):
            if key not in written:
                problems.append(f"{key} was not written to the state file")

        second_root = tk.Tk()
        second = gui.App(second_root)
        second_root.update()
        geometry = second_root.winfo_geometry()
        if second.dry_run.get() is not False:
            problems.append("dry run was not restored")
        if second.hide_while_running.get() is not False:
            problems.append("minimize setting was not restored")
        if not geometry.startswith(want.split("+")[0]):
            problems.append(f"window size was not restored: asked for {want}, "
                            f"got {geometry}")
        second.on_close()

        # A position on a monitor that no longer exists must be ignored.
        third_root = tk.Tk()
        third = gui.App(third_root)
        checks = {
            "1200x800+99999+99999": False,   # way off the desktop
            "10x10+0+0": False,              # absurdly small
            "not a geometry": False,
            "1200x800+100+100": True,
        }
        for geometry_text, expected in checks.items():
            if third._geometry_is_on_screen(geometry_text) is not expected:
                problems.append(f"off-screen guard wrong for {geometry_text!r}")
        third.on_close()

        print("Preferences ok: dry run, minimize and geometry survive a restart")
    finally:
        gui.STATE_PATH = original_state_path
    return problems


try:
    failures.extend(check_typing_does_not_steal_focus())
except Exception as error:  # noqa: BLE001
    failures.append(f"typing check: {error!r}")

try:
    failures.extend(check_names_show_in_the_list())
except Exception as error:  # noqa: BLE001
    failures.append(f"name display check: {error!r}")

try:
    failures.extend(check_numbering_and_section_highlight())
except Exception as error:  # noqa: BLE001
    failures.append(f"numbering check: {error!r}")

try:
    failures.extend(check_word_deletion())
except Exception as error:  # noqa: BLE001
    failures.append(f"word editing check: {error!r}")

try:
    failures.extend(check_start_stop_hotkey())
except Exception as error:  # noqa: BLE001
    failures.append(f"hotkey check: {error!r}")

try:
    failures.extend(check_editor_cannot_scroll_into_nothing())
except Exception as error:  # noqa: BLE001
    failures.append(f"editor scrolling check: {error!r}")

try:
    failures.extend(check_duplicate_step())
except Exception as error:  # noqa: BLE001
    failures.append(f"duplicate check: {error!r}")

try:
    failures.extend(check_choices_read_as_english())
except Exception as error:  # noqa: BLE001
    failures.append(f"choice label check: {error!r}")

try:
    failures.extend(check_deleting_a_step_offers_to_delete_its_image())
except Exception as error:  # noqa: BLE001
    failures.append(f"image cleanup check: {error!r}")

for check in (check_boxes_can_be_typed_into, check_panes_can_be_dragged,
              check_what_matches_window, check_show_the_click,
              check_testing_a_step_runs_it_once,
              check_window_size_is_remembered,
              check_settings_stick, check_add_menu_is_grouped,
              check_indenting_steps,
              check_moving_keeps_groups_together,
              check_no_hidden_keybinds, check_the_log_stays_a_sensible_size,
              check_settings_hints_can_be_hidden,
              check_every_explanation_obeys_the_hints_box):
    try:
        failures.extend(check())
    except Exception as error:  # noqa: BLE001
        failures.append(f"{check.__name__}: {error!r}")

try:
    failures.extend(check_image_and_color_previews())
except Exception as error:  # noqa: BLE001
    failures.append(f"preview check: {error!r}")

try:
    failures.extend(check_preferences_persist())
except Exception as error:  # noqa: BLE001
    failures.append(f"preferences check: {error!r}")

app.log("test message", "warn")
root.update()
root.destroy()

print()
if failures:
    print(f"FAILED ({len(failures)}):")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)
print("GUI CHECKS PASSED")
