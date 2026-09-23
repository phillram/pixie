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
        first_root.geometry("1234x789+150+90")
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
        if not geometry.startswith("1234x789"):
            problems.append(f"window size was not restored, got {geometry}")
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
