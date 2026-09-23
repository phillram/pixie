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

from pixie.system import screen

# What to do when a step's timeout expires without the thing appearing.
#
# One table, three views. The key is what the file stores and the engine
# compares against; the label is what the dropdown shows; the note is the
# sentence underneath it. Adding an option here means adding it in one place,
# and tools/check_wiring.py fails if the engine cannot carry it out.
#
# The notes take {section} and {first} -- filled in with the real section
# names, because "the whole sequence" and "this section" are the exact pair
# people mix up.
ON_TIMEOUT_CHOICES: tuple[tuple[str, str, str], ...] = (
    ("restart",
     "Go back to the very first step of the sequence",
     "Abandons {section} and starts the whole script again from {first}. "
     "Everything before this step runs a second time."),
    ("restart_section",
     "Go back to the first step of this section",
     "Starts {section} again from its own step 1, and does not touch any "
     "other section. If this step is that first step, it simply tries again."),
    ("continue",
     "Skip it and run the next step anyway",
     "Carries on down {section} as though this step had worked. Only safe "
     "when the next step does not depend on this one."),
    ("next_section",
     "Leave this section and start the next one",
     "Stops running {section} and moves on. This is how a section ends: it "
     "repeats until its first step stops finding what it looks for."),
    ("stop",
     "Stop the run completely",
     "Stops everything, as though you had pressed Stop."),
)
ON_TIMEOUT = tuple(key for key, _, _ in ON_TIMEOUT_CHOICES)
ON_TIMEOUT_LABELS = {key: label for key, label, _ in ON_TIMEOUT_CHOICES}
ON_TIMEOUT_NOTES = {key: note for key, _, note in ON_TIMEOUT_CHOICES}

# Two situations where the general wording above would mislead, so they get
# their own. Without these, a step in the first section is told that it
# "abandons 'Before Game' and starts again from 'Before Game'".
ON_TIMEOUT_NOTES_FIRST_SECTION = {
    "restart": "Starts the whole script again from the top. This step is "
               "already in the first section, {section}, so in practice that "
               "is the same as starting this section over.",
}
ON_TIMEOUT_NOTES_NO_SECTIONS = {
    "restart": "Back to step 1. This sequence has no sections, so the whole "
               "of it starts again.",
    "restart_section": "Back to step 1. This sequence has no sections, so "
                       "there is only one and this does the same as starting "
                       "the whole sequence again.",
    "continue": "Runs the next step as though this one had worked. Only safe "
                "when the next step does not depend on this one.",
    "next_section": "There is no next section, so this finishes the cycle and "
                    "starts again from step 1.",
}

BUTTONS = ("left", "right", "middle")
BUTTON_LABELS = {"left": "Left button", "right": "Right button",
                 "middle": "Middle button"}
COLOR_MODES = ("any", "mean")
COLOR_MODE_LABELS = {"any": "any pixel in the square matches",
                     "mean": "the square's average color matches"}
COLOR_MATCH = ("hue", "rgb")
COLOR_MATCH_LABELS = {"hue": "Hue - the shade, at any brightness",
                      "rgb": "RGB - the exact color"}

# Which patch to use when several match at once. The list itself comes from
# the matcher, so the dropdown cannot offer an order it does not implement.
PICK_ORDERS = screen.PICK_ORDERS
PICK_LABELS = {
    "largest": "the biggest one",
    "leftmost": "the one furthest left",
    "rightmost": "the one furthest right",
    "topmost": "the one nearest the top",
    "bottommost": "the one nearest the bottom",
}

# Plain English for the values stored in each 'choice' field, looked up by the
# field's key. The file still stores the short value; only the dropdown reads
# differently.
CHOICE_LABELS: dict[str, dict[str, str]] = {
    "on_timeout": ON_TIMEOUT_LABELS,
    "button": BUTTON_LABELS,
    "mode": COLOR_MODE_LABELS,
    "match": COLOR_MATCH_LABELS,
    "pick": PICK_LABELS,
}
# What the chosen value actually means, shown under the dropdown.
CHOICE_NOTES: dict[str, dict[str, str]] = {
    "on_timeout": ON_TIMEOUT_NOTES,
}

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
_TIMEOUT_HINT = (
    "How long to keep looking before giving up and doing whatever 'If not "
    "found' says. This is the setting that decides how long Pixie sits still "
    "when something does not turn up.\n"
    "**0 means wait forever**: she idles here until it appears, however long "
    "that takes. Use it when the next steps make no sense without it.\n"
    "A section's start point is usually the one to shorten - 30s of waiting "
    "before moving on to the next section is 30s of nothing happening."
)
_PICK_HINT = (
    "Several patches of the color can be on screen at once - a row of cards "
    "all glowing, for instance. This decides which one Pixie goes for.\n"
    "'the biggest one' is what she has always done, and is right when the "
    "real target is the strongest glow. Pick a direction instead to work "
    "through them in order: 'furthest left' takes the leftmost every time, so "
    "repeating the section deals with them left to right."
)
_SECTION_PAUSE_HINT = (
    "Replaces the sequence-wide pause between sections, for this section "
    "only. A section ends in one of two ways and this is waited for both: "
    "when it starts itself again, and when it hands over to the next "
    "section. Set both boxes to 0 for no wait at all."
)
_SECTION_LIMIT_HINT = (
    "A ceiling on every wait inside this section. A step that would wait 30s, "
    "or forever, gives up after this instead; a step that already waits less "
    "keeps its own shorter time.\n"
    "This is the quick way to stop a section idling: set it to 3 and nothing "
    "in the section can sit still for longer than that."
)



@dataclass(frozen=True)
class Field:
    """One editable setting on a step."""

    key: str
    # image | point | color | region | box | number | integer | choice |
    # offset | key | pause | limit | multiline
    kind: str
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
        Field("confidence", "number", "How close a match (0-1)", 0.85,
              hint="1.00 is pixel perfect and too strict for most things. Lower matches more loosely, at the risk of matching the wrong thing. 0.85 is a good start."),
        Field("timeout", "number", "Give up after (s)", timeout,
              hint=_TIMEOUT_HINT),
        Field("on_timeout", "choice", "If it is not found, then", on_timeout, choices=ON_TIMEOUT),
    )


_OFFSET_HINT = (
    "Where to click relative to the middle of what was found, in pixels.\n"
    "X: positive = right, negative = left.   Y: positive = DOWN, negative = up.\n"
    "0, 0 clicks dead center. To click just underneath, leave X at 0 and set\n"
    "Y to roughly half the height of the thing plus a bit — try 40 and adjust."
)

# How to click. Steps that click a fixed spot or a box take only these.
_BUTTON_FIELDS: tuple[Field, ...] = (
    Field("clicks", "integer", "How many clicks", 1,
          hint="2 for a double-click: two clicks 60ms apart, which is well "
               "inside Windows' double-click time, so the application reads "
               "them as one double-click."),
    Field("button", "choice", "Which mouse button", "left", choices=BUTTONS),
)
# ...plus where to click, for the steps that click whatever they just found.
_CLICK_FIELDS: tuple[Field, ...] = _BUTTON_FIELDS + (
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
              "Use the Name box above as the section's title. The two settings "
              "below apply to every step in this section.",
        fields=(
            Field("pause", "pause", "Pause when this section ends", None,
                  hint=_SECTION_PAUSE_HINT),
            Field("wait_limit", "limit", "Cap every wait in here at (s)", None,
                  hint=_SECTION_LIMIT_HINT),
        ),
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
            Field("tolerance", "number", "How far off it may be", 30,
                  hint="How far off the color may be. 10 is strict, 60 is loose."),
            Field("radius", "integer", "Look this far around it (px)", 3, minimum=0, maximum=200,
                  hint="Checks a square this many pixels out, to absorb drift."),
            Field("mode", "choice", "Counts as a match when", "any", choices=COLOR_MODES,
                  hint="Averaging is steadier on a speckled or anti-aliased target; any-pixel reacts to the smallest trace of the color."),
            Field("timeout", "number", "Give up after (s)", 30.0, hint=_TIMEOUT_HINT),
            Field("on_timeout", "choice", "If it never appears, then", "restart", choices=ON_TIMEOUT),
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
            Field("match", "choice", "Match the color by", "hue", choices=COLOR_MATCH,
                  hint=_MATCH_HINT),
            Field("tolerance", "number", "How far off it may be", 14, hint=_TOLERANCE_HINT),
            Field("min_saturation", "integer", "Min saturation", 90,
                  minimum=0, maximum=255, hint=_SATURATION_HINT),
            Field("min_brightness", "integer", "Min brightness", 70,
                  minimum=0, maximum=255, hint=_BRIGHTNESS_HINT),
            Field("min_pixels", "integer", "Smallest patch (pixels)", 40, minimum=1, maximum=100000,
                  hint="Ignore patches smaller than this many pixels, so stray "
                       "matching pixels elsewhere don't count."),
            Field("pick", "choice", "If several match, use", "largest",
                  choices=PICK_ORDERS, hint=_PICK_HINT),
            Field("timeout", "number", "Give up after (s)", 30.0, hint=_TIMEOUT_HINT),
            Field("on_timeout", "choice", "If it never appears, then", "restart",
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
            Field("match", "choice", "Match the color by", "hue", choices=COLOR_MATCH,
                  hint=_MATCH_HINT),
            Field("tolerance", "number", "How far off it may be", 14, hint=_TOLERANCE_HINT),
            Field("min_saturation", "integer", "Min saturation", 90,
                  minimum=0, maximum=255, hint=_SATURATION_HINT),
            Field("min_brightness", "integer", "Min brightness", 70,
                  minimum=0, maximum=255, hint=_BRIGHTNESS_HINT),
            Field("min_pixels", "integer", "Smallest patch (pixels)", 40,
                  minimum=1, maximum=100000,
                  hint="Ignore patches smaller than this, so a few stray matching pixels elsewhere don't count as a find."),
            Field("pick", "choice", "If several match, use", "largest",
                  choices=PICK_ORDERS, hint=_PICK_HINT),
            Field("timeout", "number", "Give it this long (s)", 1.0,
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
            Field("confidence", "number", "How close a match (0-1)", 0.85,
                  hint="Lower matches more loosely. 0.85 is a good start."),
            Field("timeout", "number", "Give it this long (s)", 1.0,
                  hint="How long to give it before deciding it is not there."),
        ) + _CLICK_FIELDS,
        describe=lambda s: f"If {_stem(s.get('image'))} appears, {_clicks_word(s).lower()} it",
    ),
    "click_point": StepType(
        key="click_point",
        label="Click a fixed spot",
        blurb="Click the same screen position every time.",
        fields=(Field("pos", "point", "Where", None, required=True),) + _BUTTON_FIELDS,
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
                           "inside it, chosen fresh each time."),) + _BUTTON_FIELDS,
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
            Field("presses", "integer", "How many taps", 1, minimum=1, maximum=50,
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
            Field("seconds", "number", "Wait at least (s)", 1.0),
            Field("seconds_max", "number", "and at most (s)", 1.0,
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


def section_starts(steps: list[dict[str, Any]]) -> list[int]:
    """Where each section begins. The one source for how a list is divided."""
    starts = [i for i, step in enumerate(steps) if step.get("type") == "section"]
    if not starts or starts[0] != 0:
        starts.insert(0, 0)  # whatever comes before the first divider
    return starts


def _quoted_section(steps: list[dict[str, Any]], index: int) -> str:
    name = section_name(steps, index)
    return f"'{name}'" if name else "this sequence"


def outcome_note(key: str, steps: list[dict[str, Any]], index: int) -> str:
    """What one 'if it is not found' choice means for this particular step.

    Filled in with the real section names. "Start the whole sequence again"
    reads as ambiguous however it is worded; "Abandons 'In Game' and starts
    the whole script again from 'Before Game'" does not.
    """
    note = ON_TIMEOUT_NOTES.get(key, "")
    if not note or not steps or not (0 <= index < len(steps)):
        return note

    divided = any(step.get("type") == "section" for step in steps)
    if not divided:
        return ON_TIMEOUT_NOTES_NO_SECTIONS.get(key, note).format(
            section="this sequence", first="the top")

    starts = section_starts(steps)
    first_start = starts[0]
    first = (f"'{steps[first_start].get('name') or 'Untitled section'}'"
             if steps[first_start].get("type") == "section" else "the top")

    # Is this step in the first section? Then "the whole sequence" and "this
    # section" land in nearly the same place, and saying so is clearer than
    # pretending they are different.
    mine = max((start for start in starts if start <= index), default=0)
    if mine == first_start:
        note = ON_TIMEOUT_NOTES_FIRST_SECTION.get(key, note)

    return note.format(section=_quoted_section(steps, index), first=first)


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
