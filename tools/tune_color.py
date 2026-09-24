"""Work out the best color settings for something on screen.

Drag a box over the thing you want Pixie to detect -- a glowing border, a
highlight, a colored button -- and this reports the settings to type into the
step, along with how much of the box they would actually match.

    python tools/tune_color.py

The same thing is built into Pixie: the "Sample an area..." button beside any
color that can be matched by hue. This is here for when you want the numbers
without opening the window.

Drag tightly over the color itself. Including a lot of background makes the
recommendation worse, not better.
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (sys.path)

from pixie.core import steps as step_defs
from pixie.ui import capture
from pixie.system import screen

# The step editor's own words for each setting. Restating them here meant the
# tool told you to set "Tolerance" while the editor called it "How far off it
# may be", and you went looking for a box that was not there.
_FIELDS = step_defs.STEP_TYPES["wait_for_color_in_area"].field_map()


def label(key: str) -> str:
    spec = _FIELDS.get(key)
    return spec.label if spec else key

# Where each color name starts, in degrees.
HUE_NAMES = (
    (0, "red"), (16, "orange"), (36, "yellow"), (66, "green"), (156, "cyan"),
    (196, "blue"), (256, "purple"), (310, "pink"), (344, "red"),
)


def hue_name(degrees: int) -> str:
    name = "red"
    for start, label in HUE_NAMES:
        if degrees >= start:
            name = label
    return name


def main() -> int:
    screen.set_dpi_aware()
    print(__doc__.strip().splitlines()[0])
    print()
    print("Drag a box over the color you want to detect...")

    picker = capture.Picker("area")
    box = picker.run()
    if box is None:
        print("Cancelled.")
        return 1

    x, y, w, h = box
    patch = picker.frame[y : y + h, x : x + w]
    left, top, width, height = picker.to_absolute(box)
    print()
    print(f"Sampled {width}x{height} pixels at {left}, {top}")
    print()

    advice = screen.suggest_color(patch)
    if advice is None:
        print("Almost nothing in that box has a usable color -- it's mostly")
        print("gray, white or black. Hue matching won't work here; use 'rgb'")
        print("mode and pick the color directly with the color picker.")
        return 1

    print(f"Dominant hue : {advice.hue_degrees} degrees "
          f"({hue_name(advice.hue_degrees)}), {advice.share:.0%} of the "
          "colored pixels")
    print()
    print("=" * 62)
    print("PUT THESE INTO THE STEP")
    print("=" * 62)
    shown = (("color", f"{advice.rgb}   "
              f"(#{advice.rgb[0]:02x}{advice.rgb[1]:02x}{advice.rgb[2]:02x})"),
             ("match", "hue"),
             ("tolerance", advice.tolerance),
             ("min_saturation", advice.min_saturation),
             ("min_brightness", advice.min_brightness))
    width = max(len(label(key)) for key, _ in shown)
    for key, value in shown:
        print(f"  {label(key):{width}}   {value}")
    print("=" * 62)
    print()

    print(f"These settings match {advice.matched:,} of the {advice.total:,} "
          f"pixels you selected ({advice.matched / advice.total:.0%}).")
    if advice.hue_beats_rgb:
        print("Hue mode is the better choice here.")
    else:
        print("This color is flat enough that 'rgb' mode works just as well.")
    print()
    print(f"Set '{label('min_pixels')}' below {advice.matched} -- try "
          f"{max(20, advice.matched // 4)} to allow for the highlight being "
          "partly hidden or smaller.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
