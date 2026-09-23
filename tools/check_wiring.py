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

    for name in ("hue", "rgb"):
        if name not in steps.COLOR_MATCH:
            problems.append(f"color match mode {name!r} has gone missing")

    if problems:
        _report(problems)
        return 1

    print("\nWIRING OK")
    return 0


def _report(problems: list[str]) -> None:
    print(f"\nFAILED ({len(problems)}):")
    for problem in problems:
        print(f"  - {problem}")


if __name__ == "__main__":
    sys.exit(main())
