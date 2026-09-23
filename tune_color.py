"""Work out the best color settings for something on screen.

Drag a box over the thing you want Pixie to detect -- a glowing border, a
highlight, a colored button -- and this reports the settings to type into the
step, along with how much of the box they would actually match.

    python tune_color.py

Drag tightly over the color itself. Including a lot of background makes the
recommendation worse, not better.
"""

from __future__ import annotations

import sys
from collections import Counter

import cv2
import numpy as np

import capture
import screen

# Hue is stored 0-179 by OpenCV; these are the human names for each arc.
HUE_NAMES = (
    (0, "red"), (8, "orange"), (18, "yellow"), (33, "green"), (78, "cyan"),
    (98, "blue"), (128, "purple"), (155, "pink"), (172, "red"),
)


def hue_name(opencv_hue: int) -> str:
    name = "red"
    for start, label in HUE_NAMES:
        if opencv_hue >= start:
            name = label
    return name


def main() -> int:
    screen.set_dpi_aware()
    print(__doc__.strip().splitlines()[0])
    print("\nDrag a box over the color you want to detect...")

    picker = capture.Picker("area")
    box = picker.run()
    if box is None:
        print("Cancelled.")
        return 1

    x, y, w, h = box
    patch = picker.frame[y : y + h, x : x + w]
    left, top, width, height = picker.to_absolute(box)
    print(f"\nSampled {width}x{height} pixels at {left}, {top}\n")

    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    # Only colored pixels have a meaningful hue; gray and near-black don't.
    colored = (saturation >= 60) & (value >= 50)
    if colored.sum() < 20:
        print("Almost nothing in that box has a usable color -- it's mostly")
        print("gray, white or black. Hue matching won't work here; use 'rgb'")
        print("mode and pick the color directly with the color picker.")
        return 1

    hues = hue[colored]
    dominant = int(Counter(hues.tolist()).most_common(1)[0][0])
    share = float((np.minimum(np.abs(hues - dominant),
                              180 - np.abs(hues - dominant)) <= 7).mean())

    spread = np.minimum(np.abs(hues - dominant), 180 - np.abs(hues - dominant))
    tolerance_units = int(np.percentile(spread, 90)) + 2
    tolerance_degrees = max(8, min(40, tolerance_units * 2))

    sats = saturation[colored]
    vals = value[colored]
    min_sat = max(30, int(np.percentile(sats, 10)) - 15)
    min_val = max(30, int(np.percentile(vals, 10)) - 15)

    # A representative color: median of the pixels close to the dominant hue.
    core = colored & (np.minimum(np.abs(hue.astype(np.int16) - dominant),
                                 180 - np.abs(hue.astype(np.int16) - dominant)) <= 7)
    pixels = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)[core]
    representative = tuple(int(v) for v in np.median(pixels, axis=0))

    print(f"Dominant hue : {dominant * 2} degrees ({hue_name(dominant)}), "
          f"{share:.0%} of the colored pixels")
    print(f"Saturation   : {int(sats.min())}-{int(sats.max())} "
          f"(10th percentile {int(np.percentile(sats, 10))})")
    print(f"Brightness   : {int(vals.min())}-{int(vals.max())} "
          f"(10th percentile {int(np.percentile(vals, 10))})")

    matched = _count(patch, representative, tolerance_degrees, min_sat, min_val)
    rgb_matched = _count_rgb(patch, representative, 50)

    print("\n" + "=" * 62)
    print("PUT THESE INTO THE STEP")
    print("=" * 62)
    print(f"  Color          {representative}   "
          f"(#{representative[0]:02x}{representative[1]:02x}{representative[2]:02x})")
    print(f"  Match by       hue")
    print(f"  Tolerance      {tolerance_degrees}")
    print(f"  Min saturation {min_sat}")
    print(f"  Min brightness {min_val}")
    print("=" * 62)

    total = patch.shape[0] * patch.shape[1]
    print(f"\nThese settings match {matched:,} of the {total:,} pixels you "
          f"selected ({matched / total:.0%}).")
    print(f"An 'rgb' match on the same color with tolerance 50 would get "
          f"{rgb_matched:,} ({rgb_matched / total:.0%}).")
    if matched > rgb_matched:
        print("Hue mode is the better choice here.")
    else:
        print("This color is flat enough that 'rgb' mode works just as well.")

    print(f"\nSet 'Smallest blob' below {matched} -- try {max(20, matched // 4)} "
          "to allow for the highlight being partly off-screen or smaller.")
    return 0


def _count(patch: np.ndarray, rgb: tuple[int, int, int], degrees: float,
           min_sat: int, min_val: int) -> int:
    return int(screen._hue_mask(patch, rgb, degrees, min_sat, min_val).sum())


def _count_rgb(patch: np.ndarray, rgb: tuple[int, int, int], tolerance: float) -> int:
    return int(screen._rgb_mask(patch, rgb, tolerance).sum())


if __name__ == "__main__":
    sys.exit(main())
