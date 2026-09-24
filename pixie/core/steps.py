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
    ("skip_block",
     "Skip the steps indented under it",
     "Jumps over every step indented under this one and carries on with the "
     "next step at this level. This is how you make a check guard a group of "
     "actions: indent them under it, and they only run when it finds what it "
     "is looking for."),
    ("next_section",
     "Leave this section and start the next one",
     "Stops running {section} and moves on. This is how a section ends: it "
     "repeats until its first step stops finding what it looks for."),
    ("stop",
     "Stop the run completely",
     "Stops everything, as though you had pressed Stop."),
)
ON_TIMEOUT = tuple(key for key, _, _ in ON_TIMEOUT_CHOICES)

# Where a "Go somewhere else" step can send the run. The same actions, minus
# the two that only mean anything as a reaction to something not being found:
# "carry on" is what happens anyway, and "skip the steps indented under it"
# needs a check to have failed.
JUMP_TARGETS = tuple(key for key in ON_TIMEOUT
                     if key not in ("continue", "skip_block"))
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

# Where in the thing that was found to aim the click. The middle is the
# obvious answer until two targets side by side arrive as one patch, and then
# the middle is the gap between them -- an edge is the reliable thing.
ANCHORS = ("middle", "left", "right", "top", "bottom",
           "top_left", "top_right", "bottom_left", "bottom_right")
ANCHOR_LABELS = {
    "middle": "the middle of it",
    "left": "its left edge",
    "right": "its right edge",
    "top": "its top edge",
    "bottom": "its bottom edge",
    "top_left": "its top-left corner",
    "top_right": "its top-right corner",
    "bottom_left": "its bottom-left corner",
    "bottom_right": "its bottom-right corner",
}
_ANCHOR_HINT = (
    "Where in the thing that was found to aim, before the offset below is "
    "applied.\n"
    "The middle is right nearly always. An edge is the answer when two "
    "targets can sit side by side and be found as one: two highlighted cards "
    "touching become one wide patch, and its middle falls between them. Aim "
    "at the left edge with an offset to the right, and you land on the left "
    "one whether they merged or not.\n"
    "An edge follows the shape rather than the box round it, so it works on "
    "things that are tilted or at different heights - the left edge of a fan "
    "of cards is measured on the card that is actually there, not on the "
    "middle of a box that belongs to no card at all."
)

# Which patch to use when several match at once. The list itself comes from
# the matcher, so the dropdown cannot offer an order it does not implement.
# Whether a section lets the cursor be moved after a click. Sections can
# only turn it off, not point it somewhere else: a spot that is safe on one
# screen is rarely safe on another, which is the whole reason for wanting it
# off in the first place.
SECTION_PARK = ("inherit", "off")
SECTION_PARK_LABELS = {
    "inherit": "as the sequence settings say",
    "off": "leave it exactly where it is",
}

PICK_ORDERS = screen.PICK_ORDERS
REACH_SIDES = screen.REACH_SIDES
REACH_LABELS = {
    "any": "anywhere in the area is fine",
    "bottom": "it must run off the bottom",
    "top": "it must run off the top",
    "left": "it must run off the left side",
    "right": "it must run off the right side",
}
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
    # A jump reads exactly like an 'if not found', because it does the same
    # things - just on purpose rather than on a failure. One set of words.
    "where": {key: ON_TIMEOUT_LABELS[key] for key in JUMP_TARGETS},
    "must_reach": REACH_LABELS,
    "park": SECTION_PARK_LABELS,
    "anchor": ANCHOR_LABELS,
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
    "Left alone it uses the one in Settings, so most steps need nothing here. "
    "Set it when this step is different: the checks that run every time round "
    "a loop and usually find nothing are the ones worth shortening, because "
    "their wait is paid on every single pass.\n"
    "**0 means wait forever**: she idles here until it appears, however long "
    "that takes. Use it when the next steps make no sense without it."
)
_TIMEOUT_OFF = "Use the sequence-wide setting"
_TIMEOUT_ON = "or instead, give up after"
_JOIN_HINT = (
    "Counts pieces of color this close together as one thing.\n"
    "An outline is hardly ever one solid shape: a glow around a card is "
    "broken up by whatever overlaps it, by anti-aliasing, and by its corners "
    "fading out, so it arrives as a handful of separate pieces. At 0 each "
    "piece counts on its own, which is why a row of highlighted cards can "
    "come back as forty specks and 'furthest left' picks the leftmost speck "
    "rather than the leftmost card.\n"
    "Set it to comfortably more than the widest gap in the outline - 20 to 40 "
    "for a card border - and the whole outline becomes one patch whose middle "
    "is the middle of the card."
)
_SPECK_HINT = (
    "Throws away pieces this small before anything is joined.\n"
    "Joining is what makes a broken outline one shape again, but it will "
    "happily gather up a scatter of anti-aliased specks too - forty pieces of "
    "ten pixels each become one 'patch' of four hundred, which then sails "
    "past 'Smallest patch' and every size limit, because those are measured "
    "on the assembled shape.\n"
    "Real pieces of an outline are hundreds of pixels; the specks are tens. "
    "Set this between the two - 100 is a good start - and the noise is gone "
    "before joining can rescue it. 0 keeps every piece."
)
_JOIN_ACROSS_HINT = (
    "The same thing, but sideways - and it usually wants to be much smaller, "
    "or zero.\n"
    "What breaks an outline up and what sits next to it are different things. "
    "A card overlapped by its neighbour shows a top bar with slivers of its "
    "sides below: pieces stacked above one another, so the reach they need is "
    "upward. Anything else on screen glowing the same color - a lamp, a lit "
    "prop, a beam - is *beside* the thing you want, and every pixel of "
    "sideways reach is an invitation to it.\n"
    "Start at 0. The two sides of one outline are a card's width apart and "
    "were never going to join sideways anyway; they join through the bar "
    "above them."
)
_REACH_HINT = (
    "Where something sits is often the steadiest thing about it.\n"
    "A hand of cards is always at the bottom of the screen, however many "
    "cards are in it and whatever angle they fan to, so every card's glow "
    "runs off the bottom of an area drawn over the hand. A lit prop in the "
    "background never does. Neither does a reflection, a lamp or a beam.\n"
    "That holds when nothing about the color does: it survives a change of "
    "background, a bigger hand, and cards tilted every which way. If your "
    "target is cut off by the edge of the area on purpose, say so here and "
    "everything that is not gets dropped for free."
)
_SIZE_HINT = (
    "Ignore anything smaller than this. Two numbers, because the thing that "
    "catches people out is a background which happens to share the color: a "
    "streak of it can easily have as many pixels as your target while being "
    "nothing like the same shape.\n"
    "An outline around a card is both wide and tall, so asking for both at "
    "once throws away thin streaks and stray glints without touching the "
    "thing you are after. Measure your target with 'What matches?' and set "
    "these to a bit under it. 0 means no limit."
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
_SECTION_PARK_HINT = (
    "Moving the cursor away after a click keeps it from sitting over the next "
    "thing Pixie needs to see, and stops it resting on one pixel for hours. "
    "Some screens do not want it: a menu where the cursor passing over an "
    "entry changes what is under it, or anything that reacts to being "
    "hovered.\n"
    "Set this to 'leave it exactly where it is' and nothing in this section "
    "moves the cursor except the clicks themselves - no parking, and none of "
    "the small nudge that follows it. The next section goes back to whatever "
    "Settings says."
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
    # For an optional number: the Settings field its default comes from when
    # the step leaves it alone, so the editor can show the value in force
    # rather than making you go and look it up.
    falls_back_to: str = ""
    off_text: str = "Let every step decide for itself"
    on_text: str = "or instead, never wait longer than"


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

def _image_fields(on_timeout: str) -> tuple[Field, ...]:
    return (
        Field("image", "image", "Image", "", required=True,
              hint="The picture to look for on screen."),
        Field("region", "region", "Search area", None,
              hint="Limit the scan to part of the screen. Much faster."),
        Field("confidence", "number", "How close a match (0-1)", 0.85,
              hint="1.00 is pixel perfect and too strict for most things. Lower matches more loosely, at the risk of matching the wrong thing. 0.85 is a good start."),
        Field("timeout", "limit", "Give up after (s)", None,
              falls_back_to="wait_timeout", off_text=_TIMEOUT_OFF,
              on_text=_TIMEOUT_ON, hint=_TIMEOUT_HINT),
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

_AIM_FIELD = Field("anchor", "choice", "Aim at", "middle", choices=ANCHORS,
                   hint=_ANCHOR_HINT)
# ...plus where to click, for the steps that click whatever they just found.
_CLICK_FIELDS: tuple[Field, ...] = _BUTTON_FIELDS + (
    _AIM_FIELD,
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
            Field("park", "choice", "Cursor after a click in here", "inherit",
                  choices=SECTION_PARK, hint=_SECTION_PARK_HINT),
        ),
        describe=lambda s: (f"=== {s.get('name') or 'Untitled section'} ==="
                            + ("   (cursor held still)"
                               if s.get("park") == "off" else "")),
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
    "when_idle": StepType(
        key="when_idle",
        label="When nothing has happened",
        blurb="Finds nothing, until this section has gone round several times "
              "without a single click or keystroke. Then it finds something, "
              "once, and starts counting again.\n\n"
              "Every other check asks what is on screen. This one asks whether "
              "anything is being achieved, which is the question behind "
              "'nothing is playable, so pass the turn'. Indent the steps to "
              "take in that case underneath it.\n\n"
              "A section that clicks something has not been idle, so a loop "
              "that is working never reaches this.",
        fields=(
            Field("laps", "integer", "Times round with nothing happening", 3,
                  minimum=1, maximum=100,
                  hint="How many times this section may go round achieving "
                       "nothing before this counts as stuck. Too low and it "
                       "fires during an ordinary pause in play; 3 to 5 is a "
                       "good range for a loop that usually does something "
                       "every time round."),
            Field("on_timeout", "choice", "While things are happening",
                  "skip_block", choices=ON_TIMEOUT),
        ),
        describe=lambda s: (f"After {s.get('laps', 3)} idle times round"),
    ),
    "jump": StepType(
        key="jump",
        label="Go somewhere else",
        blurb="Changes where the run goes next, and nothing else. On its own "
              "it is unconditional, which is rarely what you want - indent it "
              "under a check and it becomes 'if this is found, go there'.\n\n"
              "Every other branch in a sequence is phrased the other way "
              "round, as 'if this is NOT found'. That covers most things, "
              "because a screen you are waiting on going away is usually the "
              "same event as the next one arriving. When it is not - a "
              "victory screen appearing over a game still in progress - this "
              "is how you say it.",
        fields=(
            Field("where", "choice", "Go to", "next_section",
                  choices=JUMP_TARGETS,
                  hint="Where to carry on from. Reads exactly like the 'If it "
                       "is not found' settings, because it does the same "
                       "things - just on purpose rather than on a failure."),
        ),
        describe=lambda s: "-> " + CHOICE_LABELS["where"].get(
            s.get("where", "next_section"), "somewhere").lower(),
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
            Field("timeout", "limit", "Give up after (s)", None,
                  falls_back_to="wait_timeout", off_text=_TIMEOUT_OFF,
                  on_text=_TIMEOUT_ON, hint=_TIMEOUT_HINT),
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
            Field("min_piece", "integer", "Ignore pieces smaller than (px)", 0,
                  minimum=0, maximum=100000, hint=_SPECK_HINT),
            Field("join", "integer", "Join pieces up and down (px)", 0,
                  minimum=0, maximum=400, hint=_JOIN_HINT),
            Field("join_across", "integer", "Join pieces side to side (px)", 0,
                  minimum=0, maximum=400, hint=_JOIN_ACROSS_HINT),
            Field("min_width", "integer", "Patch at least this wide (px)", 0,
                  minimum=0, maximum=4000, hint=_SIZE_HINT),
            Field("min_height", "integer", "Patch at least this tall (px)", 0,
                  minimum=0, maximum=4000, hint=_SIZE_HINT),
            Field("must_reach", "choice", "Must run off the edge", "any",
                  choices=REACH_SIDES, hint=_REACH_HINT),
            Field("pick", "choice", "If several match, use", "largest",
                  choices=PICK_ORDERS, hint=_PICK_HINT),
            Field("timeout", "limit", "Give up after (s)", None,
                  falls_back_to="wait_timeout", off_text=_TIMEOUT_OFF,
                  on_text=_TIMEOUT_ON, hint=_TIMEOUT_HINT),
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
            Field("min_piece", "integer", "Ignore pieces smaller than (px)", 0,
                  minimum=0, maximum=100000, hint=_SPECK_HINT),
            Field("join", "integer", "Join pieces up and down (px)", 0,
                  minimum=0, maximum=400, hint=_JOIN_HINT),
            Field("join_across", "integer", "Join pieces side to side (px)", 0,
                  minimum=0, maximum=400, hint=_JOIN_ACROSS_HINT),
            Field("min_width", "integer", "Patch at least this wide (px)", 0,
                  minimum=0, maximum=4000, hint=_SIZE_HINT),
            Field("min_height", "integer", "Patch at least this tall (px)", 0,
                  minimum=0, maximum=4000, hint=_SIZE_HINT),
            Field("must_reach", "choice", "Must run off the edge", "any",
                  choices=REACH_SIDES, hint=_REACH_HINT),
            Field("pick", "choice", "If several match, use", "largest",
                  choices=PICK_ORDERS, hint=_PICK_HINT),
            Field("timeout", "limit", "Give it this long (s)", None,
                  falls_back_to="wait_timeout", off_text=_TIMEOUT_OFF,
                  on_text=_TIMEOUT_ON, hint=_TIMEOUT_HINT),
        ) + _CLICK_FIELDS,
        describe=lambda s: (f"If color appears, {_clicks_word(s).lower()} it"),
    ),
    "wait_for_image": StepType(
        key="wait_for_image",
        label="Wait for an image",
        blurb="Pause until a picture appears. Does not click.",
        fields=_image_fields("restart"),
        describe=lambda s: f"Wait for {_stem(s.get('image'))}",
    ),
    "click_image": StepType(
        key="click_image",
        label="Click an image",
        blurb="Find a picture and click it. Waits for it to appear first.",
        fields=_image_fields("restart") + _CLICK_FIELDS,
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
            Field("timeout", "limit", "Give it this long (s)", None,
                  falls_back_to="wait_timeout", off_text=_TIMEOUT_OFF,
                  on_text=_TIMEOUT_ON, hint=_TIMEOUT_HINT),
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
NO_PAUSE = MARKERS + ("jump",)

STEP_TYPES = {
    key: (step_type if key in NO_PAUSE
          else replace(step_type, fields=step_type.fields + (_PAUSE_FIELD,)))
    for key, step_type in STEP_TYPES.items()
}


# How the Add step menu is laid out ------------------------------------

# Thirteen step types in one flat list is a wall of similar-sounding names,
# and the difference between "Click an image" and "Click an image if it
# appears" is not something you should have to open each one to learn. The
# menu is grouped under these headings, and each entry carries a few words
# saying what it is for.
#
# Every step type belongs to exactly one group and has a hint; check_wiring
# enforces both, so a new type cannot be declared above and then quietly go
# missing from the only menu that can create it.
STEP_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Structure", ("section", "note", "jump", "when_idle")),
    ("Wait until something appears",
     ("wait_for_image", "wait_for_color", "wait_for_color_in_area")),
    ("Click what Pixie finds",
     ("click_image", "click_image_if_present", "click_color_if_present",
      "click_last_match")),
    ("Click where you say", ("click_point", "click_box")),
    ("Keyboard and waiting", ("press_key", "wait")),
)

MENU_HINTS: dict[str, str] = {
    "section": "start a new section",
    "note": "a reminder to yourself, never run",
    "jump": "send the run somewhere else",
    "when_idle": "fires when this section achieves nothing",
    "wait_for_image": "hold here until a picture shows up",
    "wait_for_color": "hold here until one spot turns a color",
    "wait_for_color_in_area": "find a glow and remember where it is",
    "click_image": "wait for a picture, then click it",
    "click_image_if_present": "click a picture, carry on if it is absent",
    "click_color_if_present": "click a glow, carry on if it is absent",
    "click_last_match": "click whatever the step above it found",
    "click_point": "click one exact spot",
    "click_box": "click a random spot inside a box",
    "press_key": "type keys, or a shortcut like Ctrl+S",
    "wait": "do nothing for a moment",
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


# Indented steps ------------------------------------------------------
#
# A step indented under another belongs to it: the one above is a check, and
# the indented run below it are the actions that check guards. The file stays
# a flat list -- nesting is one integer per step, not a tree -- because the
# engine walks the list by index, and a tree would mean rewriting that walk,
# the list widget, reordering and the save format all at once for something
# one level deep already expresses.
#
# One level only. Two would need a real tree, and nothing so far has wanted it.
MAX_INDENT = 1


def indent_of(step: dict[str, Any]) -> int:
    """How deeply a step is indented. Absent means not at all."""
    try:
        return max(0, min(MAX_INDENT, int(step.get("indent", 0) or 0)))
    except (TypeError, ValueError):
        return 0


def block_of(steps: list[dict[str, Any]], index: int) -> tuple[int, int]:
    """The run of steps indented under `index`, as a half-open range.

    Empty (start == end) when nothing is indented under it. Markers count as
    part of the block if they are indented, so a Note can sit inside one and
    explain what the group is for.
    """
    if indent_of(steps[index]) >= MAX_INDENT:
        return index + 1, index + 1  # an indented step owns nothing itself
    end = index + 1
    while end < len(steps) and indent_of(steps[end]) > 0:
        end += 1
    return index + 1, end


def can_own_a_block(step: dict[str, Any]) -> bool:
    """Could steps indented under this one ever be skipped?

    Only a step that can fail has an 'if not found' to say so. Indenting under
    anything else is decoration: the steps below run either way.
    """
    step_type = STEP_TYPES.get(step.get("type", ""))
    if step_type is None or step.get("type") in MARKERS:
        return False
    return any(spec.key == "on_timeout" for spec in step_type.fields)


def normalize_indents(steps: list[dict[str, Any]]) -> bool:
    """Clear indents that no longer belong to anything. True if any changed.

    Deleting a check, or moving one away, would otherwise leave its actions
    indented under whatever happened to fall above them -- which reads as a
    group that is guarded when it is not. Called after every structural edit
    so the list cannot drift into saying something untrue.
    """
    changed = False
    starts = set(section_starts(steps))
    for index, step in enumerate(steps):
        if not indent_of(step):
            continue
        # Nothing above it in this section, or the thing above cannot guard
        # anything: there is no owner, so it is not indented.
        owner = index - 1
        while owner >= 0 and indent_of(steps[owner]):
            owner -= 1
        orphaned = (index in starts or owner < 0
                    or steps[index - 1].get("type") == "section"
                    or not can_own_a_block(steps[owner]))
        if orphaned:
            step.pop("indent", None)
            changed = True
    return changed


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
