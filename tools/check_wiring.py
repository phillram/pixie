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

    # The Add step menu is the only way to create a step, so a type missing
    # from it cannot be used at all.
    grouped: list[str] = [key for _, keys in steps.STEP_GROUPS for key in keys]
    for key in steps.STEP_TYPES:
        if grouped.count(key) != 1:
            problems.append(f"step type {key!r} appears {grouped.count(key)} "
                            "times in STEP_GROUPS, should be once")
        if not steps.MENU_HINTS.get(key):
            problems.append(f"step type {key!r} has no hint in MENU_HINTS")
    for key in grouped:
        if key not in steps.STEP_TYPES:
            problems.append(f"STEP_GROUPS lists {key!r}, which is not a step type")

    print(f"  {len(steps.STEP_GROUPS)} menu groups, covering every step type")

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

    # The standalone tools are not imported by the app, so nothing else would
    # notice if one stopped parsing.
    import ast
    from pathlib import Path

    tools = sorted(Path(__file__).parent.glob("*.py"))
    for tool in tools:
        try:
            ast.parse(tool.read_text(encoding="utf-8"))
        except SyntaxError as error:
            problems.append(f"tools/{tool.name} does not parse: {error}")
    print(f"  {len(tools)} tools parse")

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

    # A 'Go somewhere else' step runs down the same branches, so anything it
    # can be set to has to be one of them.
    for value in steps.JUMP_TARGETS:
        if value not in carried_out:
            problems.append(f"'go somewhere else' offers {value!r}, but "
                            "run_cycle never acts on it")
        if value not in steps.ON_TIMEOUT:
            problems.append(f"'go somewhere else' offers {value!r}, which is "
                            "not one of the 'if not found' actions")
    print(f"  {len(steps.JUMP_TARGETS)} places a jump can send the run")

    # Every level the engine logs at needs a color in the GUI.
    from pixie.ui.app import LOG_COLORS

    for level in engine.LOG_LEVELS:
        if level not in LOG_COLORS:
            problems.append(f"log level {level!r} has no color in the GUI")

    for name in ("hue", "rgb"):
        if name not in steps.COLOR_MATCH:
            problems.append(f"color match mode {name!r} has gone missing")

    problems.extend(_check_every_choice_is_carried_out())
    problems.extend(_check_the_engine_keeps_no_defaults_of_its_own())

    if problems:
        _report(problems)
        return 1

    print("\nWIRING OK")
    return 0


def _check_every_choice_is_carried_out() -> list[str]:
    """A dropdown value nothing acts on is the quietest kind of broken.

    Every list here is offered to somebody in the interface, and every one is
    read somewhere else that decides what actually happens. Most of those
    readers fall back to a default when handed something they do not know, so
    adding a value in one place and forgetting the other produces no error at
    all: the setting simply does nothing, and looks like it worked.
    """
    from pixie.core import engine, steps
    from pixie.system import mouse, screen

    problems: list[str] = []

    # Pick order. _sort_key falls back to "largest" for anything it does not
    # recognise, so a missing order silently becomes the default.
    fallback = screen._sort_key("something that is not an order")
    sample = [(10, 20, 30, 40, 1200), (50, 60, 70, 80, 5600)]
    for order in screen.PICK_ORDERS:
        if order == "largest":
            continue
        if [fallback(b) for b in sample] == [screen._sort_key(order)(b) for b in sample]:
            problems.append(f"pick order {order!r} sorts exactly like the "
                            "fallback, so it has no rule of its own")

    # Must-reach sides. The matcher builds its list of reached sides from these
    # four names, so a side outside them can never be satisfied by anything.
    can_be_reached = {"left", "top", "right", "bottom"}
    for side in screen.REACH_SIDES:
        if side != "any" and side not in can_be_reached:
            problems.append(f"'must run off the edge' offers {side!r}, which "
                            "the matcher never reports reaching")
    if set(steps.REACH_SIDES) != set(screen.REACH_SIDES):
        problems.append("steps.REACH_SIDES and screen.REACH_SIDES disagree")
    if set(steps.PICK_ORDERS) != set(screen.PICK_ORDERS):
        problems.append("steps.PICK_ORDERS and screen.PICK_ORDERS disagree")

    # Where the cursor parks. The GUI offers exactly PARK_LABELS, and the
    # engine decides where to send it by branching on the same keys.
    import inspect

    park_source = inspect.getsource(engine.Engine._park_target)
    for mode in engine.PARK_LABELS:
        if mode != "off" and f'"{mode}"' not in park_source:
            problems.append(f"cursor mode {mode!r} is offered in Settings but "
                            "_park_target has no branch for it")

    # A section can override parking, and the engine reads that value back.
    section_source = inspect.getsource(engine.Engine._enter_section)
    for value in steps.SECTION_PARK:
        if value not in steps.SECTION_PARK_LABELS:
            problems.append(f"section cursor setting {value!r} has no label")
    if '"off"' not in section_source:
        problems.append("_enter_section no longer reads the section's cursor "
                        "setting, so 'leave it exactly where it is' does nothing")

    # Hotkeys. The GUI offers whatever hotkey_names says, and key_pressed is
    # what then has to recognise it.
    for name in screen.hotkey_names():
        try:
            screen.key_pressed(name)
        except ValueError:
            problems.append(f"hotkey {name!r} is offered but key_pressed "
                            "refuses it")
        except OSError:
            pass  # no desktop to ask; the lookup is what we were testing

    # Travel styles. Every one has to produce a plan the others do not, or
    # it is a word in a dropdown that changes nothing.
    class _Journey:
        sequence = type("S", (), {"settings": engine.Settings()})()

        _travel_time = lambda _self, _x, _y: 0.3  # noqa: E731
        _travel_plan = engine.Engine._travel_plan

    def shape_of(style: str) -> tuple:
        plan = _Journey()._travel_plan(style, 400, 300)
        return (plan.seconds is not None, plan.drift > 0, plan.overshoot > 0)

    plans = {style: shape_of(style) for style in steps.MOVING_STYLES}
    plans["warp"] = shape_of("warp")
    if len(set(plans.values())) != len(plans):
        problems.append(f"travel styles do not all behave differently: {plans}")
    # "random" is the odd one: it has to be capable of being any of them.
    drawn = {shape_of("random") for _ in range(60)}
    if len(drawn) < len(steps.MOVING_STYLES):
        problems.append(f"'random' only ever produced {len(drawn)} of the "
                        f"{len(steps.MOVING_STYLES)} journeys it picks between")
    for style in steps.MOVING_STYLES:
        if style not in steps.TRAVEL_STYLES:
            problems.append(f"'random' can pick {style!r}, which is not a "
                            "style the interface offers")
    for style in steps.TRAVEL_STYLES:
        if style not in steps.TRAVEL_STYLE_LABELS:
            problems.append(f"travel style {style!r} has nothing to show for it")
    if steps.TRAVEL_CHOICES != ("inherit",) + steps.TRAVEL_STYLES:
        problems.append("a step cannot be set to every travel style the "
                        f"sequence can: {steps.TRAVEL_CHOICES}")

    # Mouse buttons.
    for button in steps.BUTTONS:
        if button not in mouse._BUTTONS:
            problems.append(f"button {button!r} is offered but mouse.click "
                            "does not know it")

    # Anchors. Every one has to move the aim somewhere, or it is decoration.
    box = (100, 200, 300, 400)
    aimed = {}
    for anchor in steps.ANCHORS:
        step = {"anchor": anchor, "offset": (0, 0)}
        aimed[anchor] = engine.Engine._aim(_NoEngine(), step, box, None)
    if len(set(aimed.values())) != len(steps.ANCHORS):
        repeated = [a for a in aimed if list(aimed.values()).count(aimed[a]) > 1]
        problems.append(f"these anchors all aim at the same pixel: {repeated}")

    print(f"  {len(screen.PICK_ORDERS)} pick orders, "
          f"{len(steps.ANCHORS)} anchors, {len(screen.REACH_SIDES)} edges, "
          f"{len(engine.PARK_LABELS)} cursor modes, "
          f"{len(steps.TRAVEL_STYLES)} travel styles, all acted on")
    return problems


def _check_the_engine_keeps_no_defaults_of_its_own() -> list[str]:
    """The engine must read a field's default from the field, not restate it.

    `step.get("confidence", 0.85)` works perfectly until the declared default
    changes, and then the editor shows one number while the run uses another.
    Nothing fails; the step simply behaves unlike what the interface says. The
    engine has `_value` for exactly this, so a literal second argument to
    step.get on a declared field is the smell.

    A handful are deliberate, and say why here rather than going unremarked.
    """
    import ast
    import inspect
    from pathlib import Path

    from pixie.core import engine, steps

    deliberate = {
        # An empty key must be an error, not a quiet press of the default one.
        "key": "an unset key has to fail rather than press Enter",
        # No upper bound means a fixed pause, not the declared default.
        "seconds_max": "a missing maximum means 'no range', not 1.0",
        # Structural, and true of steps the vocabulary has never heard of.
        "enabled": "every step is on unless it says otherwise",
        "type": "read before we know which type it is",
        "pause": "presence is the question, not the value",
        "offset": "absent means no offset at all",
        "indent": "structure, not a setting",
    }
    declared = {spec.key: spec.default
                for step_type in steps.STEP_TYPES.values()
                for spec in step_type.fields}

    source = Path(inspect.getfile(engine)).read_text(encoding="utf-8")
    problems = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "step"
                and len(node.args) == 2
                and isinstance(node.args[0], ast.Constant)):
            continue
        key = node.args[0].value
        if key in deliberate or key not in declared or declared[key] is None:
            continue
        if not isinstance(node.args[1], ast.Constant):
            continue
        problems.append(
            f"engine.py line {node.lineno}: step.get({key!r}, "
            f"{node.args[1].value!r}) keeps its own copy of a default the "
            f"field declares as {declared[key]!r}. Use self._value.")

    print(f"  {len(declared)} declared fields, no second copy of any default")

    # Instructions that cannot be followed. --help prints a docstring
    # verbatim, and the tools print commands at people mid-run, so a script
    # named in either has to still be there. automator.py, gui.py and
    # capture.py were all named long after they were renamed or removed.
    import re

    root = Path(__file__).resolve().parent.parent
    sources = sorted((root / "pixie").rglob("*.py")) + sorted((root / "tools").glob("*.py"))
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for named in re.findall(r"python ([A-Za-z_][\w/]*\.py)", line):
                if (root / named).exists():
                    continue
                where = source.relative_to(root).as_posix()
                problems.append(f"{where} line {line_number} tells you to run "
                                f"{named!r}, which is not there. Use "
                                "'python -m pixie' or the path under tools/.")

    print(f"  {len(sources)} modules checked for commands that no longer exist")
    return problems


class _NoEngine:
    """Just enough of an Engine for _aim, which only reads the step."""

    def _value(self, step, key, default):
        value = step.get(key)
        return default if value is None else value


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
