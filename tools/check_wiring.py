"""Check the package holds together, without needing a screen.

The full self-tests capture the real desktop and send real input, so they need
a logged-in session and cannot run on a build server. This is the part that
can: every module imports, and every declared step type has an engine handler
and a complete set of defaults.

    python tools/check_wiring.py
"""

from __future__ import annotations

import importlib
import sys

import _bootstrap  # noqa: F401  (sys.path)

MODULES = (
    "pixie",
    "pixie.paths",
    "pixie.cli",
    "pixie.__main__",
    "pixie.core.engine",
    "pixie.core.steps",
    "pixie.system.screen",
    "pixie.system.mouse",
    "pixie.system.keyboard",
    "pixie.ui.app",
    "pixie.ui.theme",
    "pixie.ui.capture",
    "pixie.ui.editing",
)


def main() -> int:
    problems: list[str] = []

    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - report, don't stop
            problems.append(f"{name} does not import: {error!r}")

    if problems:
        _report(problems)
        return 1

    import pixie
    from pixie.core import engine, steps

    print(f"Pixie {pixie.__version__}")
    print(f"  {len(MODULES)} modules import cleanly")

    for key, step_type in steps.STEP_TYPES.items():
        if not hasattr(engine.Engine, f"_do_{key}"):
            problems.append(f"step type {key!r} has no _do_{key} on Engine")
        step = steps.new_step(key)
        for spec in step_type.fields:
            if spec.key not in step:
                problems.append(f"step type {key!r} has no default for {spec.key!r}")
        if not steps.describe(step):
            problems.append(f"step type {key!r} describes itself as an empty string")

    print(f"  {len(steps.STEP_TYPES)} step types, all wired to the engine")

    # Every kind of field must have an editor to draw it. Without this, a new
    # kind quietly falls back to a number box that edits the wrong thing.
    from pixie.ui.app import App

    kinds = {spec.kind for step_type in steps.STEP_TYPES.values()
             for spec in step_type.fields}
    for kind in sorted(kinds):
        builder = App.FIELD_BUILDERS.get(kind)
        if builder is None:
            problems.append(f"field kind {kind!r} has no editor in App.FIELD_BUILDERS")
        elif not hasattr(App, builder):
            problems.append(f"field kind {kind!r} points at missing App.{builder}")

    print(f"  {len(kinds)} field kinds, all with an editor")

    # Every value a dropdown can hold needs plain English to show for it, and
    # the engine has to know what to do with every 'if not found' option.
    for step_type in steps.STEP_TYPES.values():
        for spec in step_type.fields:
            if spec.kind != "choice":
                continue
            labels = steps.CHOICE_LABELS.get(spec.key, {})
            for value in spec.choices:
                if value not in labels:
                    problems.append(f"choice {value!r} on {spec.key!r} has no "
                                    "label in CHOICE_LABELS")
            if spec.default not in spec.choices:
                problems.append(f"{step_type.key}.{spec.key} defaults to "
                                f"{spec.default!r}, which is not one of its choices")

    carried_out = _outcomes_the_engine_handles()
    for value in steps.ON_TIMEOUT:
        if value not in carried_out:
            problems.append(f"'if not found' option {value!r} is offered but "
                            "run_cycle never acts on it")
        if value not in steps.ON_TIMEOUT_NOTES:
            problems.append(f"'if not found' option {value!r} has no note")
    print(f"  {len(steps.ON_TIMEOUT)} 'if not found' options, all acted on")

    # Every level the engine logs at needs a color in the GUI.
    from pixie.ui.app import LOG_COLORS

    for level in engine.LOG_LEVELS:
        if level not in LOG_COLORS:
            problems.append(f"log level {level!r} has no color in the GUI")

    for name in ("hue", "rgb"):
        if name not in steps.COLOR_MATCH:
            problems.append(f"color match mode {name!r} has gone missing")

    if problems:
        _report(problems)
        return 1

    print("\nWIRING OK")
    return 0


def _outcomes_the_engine_handles() -> set[str]:
    """Which 'if not found' values run_cycle actually has a branch for.

    Read back out of the source, so offering a new option in steps.py without
    teaching the engine to carry it out is caught here rather than by a
    sequence quietly doing the wrong thing at three in the morning.
    """
    import inspect
    import re

    from pixie.core.engine import Engine

    source = inspect.getsource(Engine.run_cycle)
    return set(re.findall(r'on_timeout == "([a-z_]+)"', source))


def _report(problems: list[str]) -> None:
    print(f"\nFAILED ({len(problems)}):")
    for problem in problems:
        print(f"  - {problem}")


if __name__ == "__main__":
    sys.exit(main())
