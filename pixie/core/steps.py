"""The vocabulary of steps a sequence can contain.

Each step type declares its fields as data. The engine reads them to run a
step; the GUI reads them to build an editor, including which fields get a
"Capture..." button. Adding a new step type means adding one entry here plus
one handler in engine.py -- the GUI needs no changes at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

# What to do when a step's timeout expires without the thing appearing.
ON_TIMEOUT = ("restart", "continue", "next_section", "stop")
ON_TIMEOUT_LABELS = {
    "restart": "Start the sequence over",
    "continue": "Carry on to the next step",
    "next_section": "Move on to the next section",
    "stop": "Stop the run",
}

BUTTONS = ("left", "right", "middle")
COLOR_MODES = ("any", "mean")
COLOR_MATCH = ("hue", "rgb")

_MATCH_HINT = (
    "'hue' matches the shade whatever its brightness - use it for anything that "
    "glows, pulses or fades, because a glow is one color smeared across a "
    "brightness gradient.\n"
    "'rgb' matches the exact color within a distance. Better for flat, solid, "
    "unchanging colors."
)
_TOLERANCE_HINT = (
    "In 'hue' mode this is degrees of hue, out of 360. 10-20 is a good range; "
    "12 catches a whole cyan glow without straying into green or blue.\n"
    "In 'rgb' mode it's straight-line distance in RGB. 30 is strict, 80 loose."
)
_SATURATION_HINT = (
    "Hue mode only. Ignores washed-out pixels, whose hue is unreliable. Raise "
    "it if it matches gray or white; lower it for pale, pastel targets."
)
_BRIGHTNESS_HINT = (
    "Hue mode only. Ignores near-black pixels, whose hue is meaningless too."
)



@dataclass(frozen=True)
class Field:
    """One editable setting on a step."""

    key: str
    kind: str  # image | point | color | region | number | integer | choice | text
    label: str
    default: Any = None
    choices: tuple[str, ...] = ()
    hint: str = ""
    required: bool = False  # the step cannot run until this is filled in
    minimum: float = 1      # spinbox range, for the "integer" kind
    maximum: float = 10


@dataclass(frozen=True)
class StepType:
    key: str
    label: str
    blurb: str
    fields: tuple[Field, ...]
    describe: Callable[[dict[str, Any]], str] = field(default=lambda step: "")

    def defaults(self) -> dict[str, Any]:
        return {f.key: f.default for f in self.fields}

    def field_map(self) -> dict[str, Field]:
        return {f.key: f for f in self.fields}


def _stem(value: Any) -> str:
    """Short display name for an image path."""
    return Path(str(value)).name if value else "(no image yet)"


def _clicks_word(step: dict[str, Any]) -> str:
    clicks = int(step.get("clicks", 1) or 1)
    button = step.get("button", "left")
    if clicks == 2 and button == "left":
        return "Double-click"
    if clicks == 1 and button == "left":
        return "Click"
    return f"{clicks}x {button}-click"


def _point(step: dict[str, Any]) -> str:
    pos = step.get("pos")
    return f"{pos[0]}, {pos[1]}" if pos else "(not set)"


def _wait_summary(step: dict[str, Any]) -> str:
    low = step.get("seconds", 1)
    high = step.get("seconds_max", low) or low
    return f"Wait {low}-{high}s" if float(high) > float(low) else f"Wait {low}s"


# Reusable field groups -------------------------------------------------

def _image_fields(timeout: float, on_timeout: str) -> tuple[Field, ...]:
    return (
        Field("image", "image", "Image", "", required=True,
              hint="The picture to look for on screen."),
        Field("region", "region", "Search area", None,
              hint="Limit the scan to part of the screen. Much faster."),
        Field("confidence", "number", "Confidence", 0.85,
              hint="0-1. Lower matches more loosely. 0.85 is a good start."),
        Field("timeout", "number", "Wait up to (s)", timeout,
              hint='How long to keep looking. **0 means wait forever** - Pixie idles here until it turns up, which is what you want when the next steps make no sense without it.'),
        Field("on_timeout", "choice", "If not found", on_timeout, choices=ON_TIMEOUT),
    )


_OFFSET_HINT = (
    "Where to click relative to the middle of what was found, in pixels.\n"
    "X: positive = right, negative = left.   Y: positive = DOWN, negative = up.\n"
    "0, 0 clicks dead center. To click just underneath, leave X at 0 and set\n"
    "Y to roughly half the height of the thing plus a bit — try 40 and adjust."
)

_CLICK_FIELDS: tuple[Field, ...] = (
    Field("clicks", "integer", "Clicks", 1, hint="2 for a double-click."),
    Field("button", "choice", "Button", "left", choices=BUTTONS),
    Field("offset", "offset", "Click offset", [0, 0], hint=_OFFSET_HINT),
)


# The step types --------------------------------------------------------

STEP_TYPES: dict[str, StepType] = {
    "section": StepType(
        key="section",
        label="Section divider",
        blurb="Marks the start of a section. Steps below it belong to this "
              "section until the next divider.\n\n"
              "A section repeats on its own: when its last step finishes it goes "
              "straight back to the section's first step. To leave, give one step "
              "- usually the first - 'If not found: Move on to the next section'. "
              "After the last section, Pixie goes back to the first one.\n\n"
              "Use the Name box above as the section's title.",
        fields=(),
        describe=lambda s: f"=== {s.get('name') or 'Untitled section'} ===",
    ),
    "note": StepType(
        key="note",
        label="Note",
        blurb="Does nothing at all when the sequence runs. Somewhere to write "
              "down what is meant to be happening, so the sequence still makes "
              "sense to you in six months.",
        fields=(Field("text", "multiline", "Note", ""),),
        describe=lambda s: "# " + (str(s.get("text") or "").strip().splitlines()
                                   or ["(empty note)"])[0][:70],
    ),
    "wait_for_color": StepType(
        key="wait_for_color",
        label="Wait for a color",
        blurb="Pause until a color shows up at a spot on screen.",
        fields=(
            Field("pos", "point", "Where", None, required=True, hint="The pixel to watch."),
            Field("color", "color", "Color", [255, 255, 255]),
            Field("tolerance", "number", "Tolerance", 30,
                  hint="How far off the color may be. 10 is strict, 60 is loose."),
            Field("radius", "integer", "Radius", 3, minimum=0, maximum=200,
                  hint="Checks a square this many pixels out, to absorb drift."),
            Field("mode", "choice", "Match", "any", choices=COLOR_MODES,
                  hint="'any' pixel in the square, or the square's 'mean'."),
            Field("timeout", "number", "Wait up to (s)", 30.0, hint='How long to keep looking. **0 means wait forever** - Pixie idles here until it turns up, which is what you want when the next steps make no sense without it.'),
            Field("on_timeout", "choice", "If it never appears", "restart", choices=ON_TIMEOUT),
        ),
        describe=lambda s: f"Wait for color at {_point(s)}",
    ),
    "wait_for_color_in_area": StepType(
        key="wait_for_color_in_area",
        label="Find a color in an area",
        blurb="Hunt for a color anywhere inside an area, and treat the middle of "
              "what it finds as the match. This is the one for a glow or highlight "
              "around an item: the glow stays the same color even when whatever "
              "it surrounds keeps changing. Follow it with 'Click the last thing "
              "found' to click the item inside.",
        fields=(
            Field("region", "region", "Area to search", None, required=True,
                  hint="The part of the screen the glow can appear in."),
            Field("color", "color", "Color", [255, 215, 0],
                  hint="Pick a mid-bright part of the glow, not the white-hot core."),
            Field("match", "choice", "Match by", "hue", choices=COLOR_MATCH,
                  hint=_MATCH_HINT),
            Field("tolerance", "number", "Tolerance", 14, hint=_TOLERANCE_HINT),
            Field("min_saturation", "integer", "Min saturation", 90,
                  minimum=0, maximum=255, hint=_SATURATION_HINT),
            Field("min_brightness", "integer", "Min brightness", 70,
                  minimum=0, maximum=255, hint=_BRIGHTNESS_HINT),
            Field("min_pixels", "integer", "Smallest blob", 40, minimum=1, maximum=100000,
                  hint="Ignore patches smaller than this many pixels, so stray "
                       "matching pixels elsewhere don't count."),
            Field("timeout", "number", "Wait up to (s)", 30.0, hint='How long to keep looking. **0 means wait forever** - Pixie idles here until it turns up, which is what you want when the next steps make no sense without it.'),
            Field("on_timeout", "choice", "If it never appears", "restart",
                  choices=ON_TIMEOUT),
        ),
        describe=lambda s: ("Find color in "
                            + (f"{s['region'][2]}x{s['region'][3]} area"
                               if s.get("region") else "(no area yet)")),
    ),
    "click_color_if_present": StepType(
        key="click_color_if_present",
        label="Click a color if it appears",
        blurb="Optional step. Looks briefly for a color in an area, clicks the "
              "middle of it if it's there, and moves straight on if it isn't. "
              "Use this for the thing that only shows up sometimes.",
        fields=(
            Field("region", "region", "Area to search", None, required=True),
            Field("color", "color", "Color", [255, 215, 0]),
            Field("match", "choice", "Match by", "hue", choices=COLOR_MATCH,
                  hint=_MATCH_HINT),
            Field("tolerance", "number", "Tolerance", 14, hint=_TOLERANCE_HINT),
            Field("min_saturation", "integer", "Min saturation", 90,
                  minimum=0, maximum=255, hint=_SATURATION_HINT),
            Field("min_brightness", "integer", "Min brightness", 70,
                  minimum=0, maximum=255, hint=_BRIGHTNESS_HINT),
            Field("min_pixels", "integer", "Smallest blob", 40,
                  minimum=1, maximum=100000),
            Field("timeout", "number", "Look for (s)", 2.0,
                  hint="How long to give it before deciding it isn't there."),
        ) + _CLICK_FIELDS,
        describe=lambda s: (f"If color appears, {_clicks_word(s).lower()} it"),
    ),
    "wait_for_image": StepType(
        key="wait_for_image",
        label="Wait for an image",
        blurb="Pause until a picture appears. Does not click.",
        fields=_image_fields(30.0, "restart"),
        describe=lambda s: f"Wait for {_stem(s.get('image'))}",
    ),
    "click_image": StepType(
        key="click_image",
        label="Click an image",
        blurb="Find a picture and click it. Waits for it to appear first.",
        fields=_image_fields(10.0, "restart") + _CLICK_FIELDS,
        describe=lambda s: f"{_clicks_word(s)} {_stem(s.get('image'))}",
    ),
    "click_image_if_present": StepType(
        key="click_image_if_present",
        label="Click an image if it appears",
        blurb="Optional step. Looks briefly, clicks if found, moves on if not.",
        fields=(
            Field("image", "image", "Image", "", required=True,
                  hint="The picture that may or may not appear."),
            Field("region", "region", "Search area", None),
            Field("confidence", "number", "Confidence", 0.85),
            Field("timeout", "number", "Look for (s)", 3.0,
                  hint="How long to give it before deciding it is not there."),
        ) + _CLICK_FIELDS,
        describe=lambda s: f"If {_stem(s.get('image'))} appears, {_clicks_word(s).lower()} it",
    ),
    "click_point": StepType(
        key="click_point",
        label="Click a fixed spot",
        blurb="Click the same screen position every time.",
        fields=(Field("pos", "point", "Where", None, required=True),) + _CLICK_FIELDS[:2],
        describe=lambda s: f"{_clicks_word(s)} at {_point(s)}",
    ),
    "click_box": StepType(
        key="click_box",
        label="Click anywhere in a box",
        blurb="Drag a box, and Pixie clicks a random spot inside it rather than "
              "the same pixel every time. Use it where the exact pixel does not "
              "matter: a big button, a card, an empty patch of table.\n\n"
              "The box is picked once and never moves, so make it cover only "
              "ground that is safe to click.",
        fields=(Field("box", "box", "Box to click in", None, required=True,
                      hint="Drag over the area. Every click lands somewhere "
                           "inside it, chosen fresh each time."),) + _CLICK_FIELDS[:2],
        describe=lambda s: (f"{_clicks_word(s)} somewhere in "
                            + (f"a {s['box'][2]}x{s['box'][3]} box"
                               if s.get("box") else "(no box yet)")),
    ),
    "click_last_match": StepType(
        key="click_last_match",
        label="Click the last thing found",
        blurb="Click wherever the previous wait step found its image or color.",
        fields=_CLICK_FIELDS,
        describe=lambda s: f"{_clicks_word(s)} the last match",
    ),
    "press_key": StepType(
        key="press_key",
        label="Press a key",
        blurb="Tap a key on the keyboard. Set 'Times' above 1 to press it "
              "repeatedly — two taps of Q, for instance. Whatever window has "
              "focus receives it, so make sure a click step put focus there first.",
        fields=(
            Field("key", "key", "Key", "Enter", required=True),
            Field("presses", "integer", "Times", 1, minimum=1, maximum=50,
                  hint="How many separate taps. 2 = press it twice."),
            Field("interval", "number", "Gap between taps (s)", 0.08,
                  hint="Raise this if the application misses the second press."),
        ),
        describe=lambda s: (f"Press {s.get('key', '?')}"
                            + (f" x{s['presses']}" if int(s.get("presses", 1) or 1) > 1
                               else "")),
    ),
    "wait": StepType(
        key="wait",
        label="Wait a moment",
        blurb="Pause for a fixed time, to let the application catch up.",
        fields=(
            Field("seconds", "number", "At least (s)", 1.0),
            Field("seconds_max", "number", "At most (s)", 1.0,
                  hint="Set this higher than 'At least' and the pause varies "
                       "randomly between the two."),
        ),
        describe=lambda s: _wait_summary(s),
    ),
}


# Every step can override the sequence-wide pause, so the field is appended to
# all of them here rather than repeated in each definition above.
_PAUSE_FIELD = Field(
    "pause", "pause", "Pause after this step", None,
    hint="Replaces the sequence-wide pause for this step only - the two are "
         "never added together. Use it when one step needs different timing: "
         "a slow animation to finish, or a menu to open. Set it to 0 and 0 for "
         "no pause at all after this step.",
)

# Labels rather than instructions: never executed, never paused after, and
# never given a number in the sequence list.
MARKERS = ("section", "note")
NO_PAUSE = MARKERS

STEP_TYPES = {
    key: (step_type if key in NO_PAUSE
          else replace(step_type, fields=step_type.fields + (_PAUSE_FIELD,)))
    for key, step_type in STEP_TYPES.items()
}


def new_step(type_key: str) -> dict[str, Any]:
    """A fresh step of the given type, with every field at its default."""
    step_type = STEP_TYPES[type_key]
    return {"type": type_key, "name": step_type.label, "enabled": True, **step_type.defaults()}


def describe(step: dict[str, Any]) -> str:
    """One-line summary for the sequence list."""
    step_type = STEP_TYPES.get(step.get("type", ""))
    if step_type is None:
        return f"Unknown step type: {step.get('type')!r}"
    try:
        return step_type.describe(step)
    except Exception:  # noqa: BLE001 - a half-filled step must still render
        return step_type.label


def display_numbers(steps: list[dict[str, Any]]) -> list[int | None]:
    """The number each step shows in the list, or None if it shows none.

    Section dividers and notes are labels rather than instructions, so they
    are not counted, and each divider starts the count again at 1. Numbering
    the raw list position instead made the first real step of a sectioned
    sequence read as step 2, which is nobody's idea of the first step.
    """
    numbers: list[int | None] = []
    count = 0
    for step in steps:
        kind = step.get("type", "")
        if kind == "section":
            count = 0
        if kind in MARKERS:
            numbers.append(None)
        else:
            count += 1
            numbers.append(count)
    return numbers


def section_name(steps: list[dict[str, Any]], index: int) -> str:
    """The name of the section a step sits in, or '' if it is outside one."""
    for earlier in range(index, -1, -1):
        if steps[earlier].get("type") == "section":
            return str(steps[earlier].get("name") or "Untitled section")
    return ""


def location(steps: list[dict[str, Any]], index: int) -> str:
    """How to refer to one step in a message, the way the list shows it."""
    step = steps[index]
    step_type = STEP_TYPES.get(step.get("type", ""))
    label = str(step.get("name") or (step_type.label if step_type else step.get("type")))

    number = display_numbers(steps)[index]
    if number is None:
        return label

    section = section_name(steps, index)
    where = f"Step {number}" + (f" of '{section}'" if section else "")
    return f"{where} ({label})"


def validate(step: dict[str, Any], where: str) -> list[str]:
    """Human-readable problems that would stop this step from running.

    `where` names the step for the message -- see `location`.
    """
    step_type = STEP_TYPES.get(step.get("type", ""))
    if step_type is None:
        return [f"{where}: unknown step type {step.get('type')!r}"]

    return [f"{where}: {spec.label.lower()} is not set"
            for spec in step_type.fields
            if spec.required and not step.get(spec.key)]
