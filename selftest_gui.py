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

import engine as engine_mod
import gui
import steps as step_defs

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
