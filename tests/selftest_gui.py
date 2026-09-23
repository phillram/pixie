"""Drive the GUI without a human: add every step type, edit fields, save, reload.

Catches tkinter widget errors, theme typos and schema/editor mismatches that
would otherwise only show up when clicking around by hand. Needs a desktop
session; it builds a real window but never shows it.

    python selftest_gui.py
"""

import sys
import tempfile
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
        "press_key": ("interval", "0.25"),
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
    step = step_defs.new_step("wait_for_image")
    app.sequence = engine_mod.Sequence(name="choices", steps=[step])
    app.refresh_list(keep=0)
    app.selected = 0
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

    # The note underneath has to follow the choice, because that is the part
    # that says "the whole sequence" rather than "this section".
    notes = [_text_of(w) for w in _descendants(app.editor)]
    if not any(step_defs.ON_TIMEOUT_NOTES["next_section"][:30] in n for n in notes):
        problems.append("the note under the dropdown did not follow the choice")

    # And a reload must survive the round trip.
    if engine_mod.Sequence(name="x", steps=[step]).steps[0]["on_timeout"] != "next_section":
        problems.append("the stored value changed on reload")

    print("Choices ok: dropdowns read as English, files keep the short value")
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
