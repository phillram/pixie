"""Screen capture, template matching and color sampling.

All coordinates are absolute virtual-desktop pixels, so they work across
multiple monitors (including ones positioned left of or above the primary,
which give negative coordinates).
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path

import cv2
import mss
import numpy as np

Region = tuple[int, int, int, int]  # left, top, width, height

_session: mss.base.MSSBase | None = None


def set_dpi_aware() -> None:
    """Report true physical pixels so our coordinates match what mss sees.

    Without this, Windows lies about screen size on scaled displays and every
    click lands in the wrong place.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _sct() -> mss.base.MSSBase:
    global _session
    if _session is None:
        _session = mss.mss()
    return _session


def virtual_bounds() -> Region:
    """The bounding box of every monitor combined."""
    m = _sct().monitors[0]
    return m["left"], m["top"], m["width"], m["height"]


def primary_bounds() -> Region:
    """The primary monitor alone, not the whole multi-monitor desktop."""
    m = _sct().monitors[1]
    return m["left"], m["top"], m["width"], m["height"]


def primary_center() -> tuple[int, int]:
    """Middle of the primary monitor.

    Deliberately not the middle of the virtual desktop -- on a multi-monitor
    setup that lands on the seam between two screens, which is nowhere useful.
    """
    left, top, width, height = primary_bounds()
    return left + width // 2, top + height // 2


def grab(region: Region | None = None) -> np.ndarray:
    """Capture the whole virtual desktop, or `region`, as a BGR image."""
    left, top, width, height = region if region else virtual_bounds()
    shot = _sct().grab({"left": left, "top": top, "width": width, "height": height})
    return cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)


@dataclass(frozen=True)
class Match:
    """Where a template was found, in absolute screen coordinates."""

    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def load_template(path: str | Path) -> np.ndarray:
    template = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"Could not read template image: {path}")
    return template


def find_template(
    template: np.ndarray,
    region: Region | None = None,
    confidence: float = 0.85,
) -> Match | None:
    """Find the single best match for `template`, or None if nothing scores high enough."""
    screen = grab(region)
    t_h, t_w = template.shape[:2]
    s_h, s_w = screen.shape[:2]
    if t_h > s_h or t_w > s_w:
        raise ValueError(
            f"Template ({t_w}x{t_h}) is larger than the search area ({s_w}x{s_h})"
        )

    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (loc_x, loc_y) = cv2.minMaxLoc(result)
    if score < confidence:
        return None

    off_x, off_y = (region[0], region[1]) if region else virtual_bounds()[:2]
    return Match(loc_x + off_x, loc_y + off_y, t_w, t_h, float(score))


def best_score(template: np.ndarray, region: Region | None = None) -> float:
    """Best match score regardless of threshold - useful when tuning confidence."""
    result = cv2.matchTemplate(grab(region), template, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(result)[1])


def sample_pixels(x: int, y: int, radius: int = 0) -> np.ndarray:
    """RGB pixels in the square of side 2*radius+1 centered on (x, y)."""
    size = radius * 2 + 1
    patch = grab((x - radius, y - radius, size, size))
    return cv2.cvtColor(patch, cv2.COLOR_BGR2RGB).reshape(-1, 3)


def pixel_color(x: int, y: int) -> tuple[int, int, int]:
    r, g, b = sample_pixels(x, y)[0]
    return int(r), int(g), int(b)


def color_present(
    x: int,
    y: int,
    target_rgb: tuple[int, int, int],
    tolerance: float = 30.0,
    radius: int = 3,
    mode: str = "any",
) -> bool:
    """Is `target_rgb` showing at (x, y)?

    `tolerance` is a straight-line distance in RGB space, so 0 is an exact
    match and ~441 would match anything. `mode` is "any" (any pixel in the
    sampled square matches) or "mean" (the square's average color matches).
    """
    pixels = sample_pixels(x, y, radius).astype(np.int32)
    target = np.array(target_rgb, dtype=np.int32)
    if mode == "mean":
        return bool(np.linalg.norm(pixels.mean(axis=0) - target) <= tolerance)
    return bool((np.linalg.norm(pixels - target, axis=1) <= tolerance).any())


@dataclass(frozen=True)
class ColorHit:
    """A blob of pixels matching a color, in absolute screen coordinates."""

    x: int          # center of the blob's bounding box
    y: int
    left: int
    top: int
    width: int
    height: int
    pixels: int     # how many pixels actually matched
    # Which edges of the search area this patch runs into, if any. A patch
    # that touches an edge is probably a cut-off piece of something bigger,
    # which makes its size and its edges untrustworthy.
    clipped: str = ""

    @property
    def center(self) -> tuple[int, int]:
        return self.x, self.y


def _rgb_mask(patch: np.ndarray, target_rgb: tuple[int, int, int],
              tolerance: float) -> np.ndarray:
    """Pixels within `tolerance` straight-line distance of the target color."""
    values = patch.astype(np.int32)
    target_bgr = np.array(target_rgb[::-1], dtype=np.int32)
    difference = values - target_bgr
    # Squared distances, to skip a square root over every pixel.
    return (difference * difference).sum(axis=2) <= tolerance * tolerance


def _hue_mask(patch: np.ndarray, target_rgb: tuple[int, int, int],
              degrees: float, min_saturation: int, min_brightness: int) -> np.ndarray:
    """Pixels of roughly the same *hue*, whatever their brightness.

    A glow is one color smeared across a brightness gradient -- washed out and
    near-white at its core, dark at its edges. In RGB those are far apart, so a
    distance match catches only a slice of it. Hue barely moves across that
    gradient, which makes it a far steadier thing to match on.
    """
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    target_hsv = cv2.cvtColor(
        np.array([[list(target_rgb[::-1])]], dtype=np.uint8), cv2.COLOR_BGR2HSV)
    target_hue = int(target_hsv[0, 0, 0])

    # OpenCV packs 0-360 degrees into 0-179, so one unit is two degrees.
    limit = max(1.0, degrees / 2.0)
    distance = np.abs(hue.astype(np.int16) - target_hue)
    distance = np.minimum(distance, 180 - distance)  # hue wraps around

    return ((distance <= limit)
            & (saturation >= min_saturation)
            & (value >= min_brightness))


# When several separate patches of the color are on screen at once, which
# one to report. The engine and the GUI both take their list from here.
PICK_ORDERS = ("largest", "leftmost", "rightmost", "topmost", "bottommost")

# How close to the edge of the screen counts as being at it.
EDGE_SLACK = 4


def _sort_key(order: str):
    """How to rank candidate blobs, given as (left, top, width, height, area)."""
    return {
        "largest": lambda b: (-b[4], b[0], b[1]),
        "leftmost": lambda b: (b[0], b[1]),
        "rightmost": lambda b: (-(b[0] + b[2]), b[1]),
        "topmost": lambda b: (b[1], b[0]),
        "bottommost": lambda b: (-(b[1] + b[3]), b[0]),
    }.get(order, lambda b: (-b[4], b[0], b[1]))


def _search(
    region: Region,
    target_rgb: tuple[int, int, int],
    tolerance: float = 40.0,
    min_pixels: int = 30,
    match: str = "rgb",
    min_saturation: int = 90,
    min_brightness: int = 70,
    order: str = "largest",
    join: int = 0,
    min_width: int = 0,
    min_height: int = 0,
) -> tuple[list[ColorHit], list[tuple[ColorHit, str]], np.ndarray]:
    """Everything the search knows: what passed, what did not and why, and the mask.

    `find_colors` is the usual way in. This exists as well so the GUI can show
    you what Pixie is actually matching, which is the only way to tell a
    highlight from a background that happens to be the same color.

    Built for things like a glowing highlight around an item: the glow keeps
    its color even when whatever it surrounds changes, so we look for the
    color and report the center of the box it encloses.

    `match` is "rgb" (within `tolerance` of the exact color) or "hue" (the same
    hue give or take `tolerance` degrees, at any brightness). Use "hue" for
    anything that glows or pulses.

    `order` decides which patch comes first when several match at once:
    "largest" (the default, and what Pixie has always done), or by position --
    "leftmost" works through a row of cards in the order you would read them.

    `join` treats fragments within that many pixels of each other as one
    patch. An outline around something is almost never one connected blob, so
    without this a row of five highlighted cards can arrive as forty specks,
    and "leftmost" picks the leftmost speck rather than the leftmost card.

    Patches with fewer than `min_pixels` pixels are dropped, which keeps stray
    anti-aliased pixels from counting as a hit.
    """
    patch = grab(region)
    if match == "hue":
        within = _hue_mask(patch, target_rgb, tolerance,
                           min_saturation, min_brightness)
    else:
        within = _rgb_mask(patch, target_rgb, tolerance)

    mask = within.astype(np.uint8)
    if not mask.any():
        return [], [], mask

    # Connected blobs, so two separate glows don't average into a meaningless
    # point between them.
    #
    # An outline is rarely one connected blob: a glow around a card is broken
    # up by whatever overlaps it, by anti-aliasing, and by the corners fading
    # out, so it arrives as a handful of fragments. Grouping is done on a
    # fattened copy of the mask, which bridges gaps up to `join` pixels, while
    # the box each group reports is measured from the real pixels -- so
    # joining changes what counts as one thing, not where that thing is.
    grouping = mask
    if join > 0:
        span = int(join) * 2 + 1
        grouping = cv2.dilate(mask, np.ones((span, span), np.uint8))

    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        grouping, connectivity=8)

    blobs = []
    for n in range(1, count):
        if join > 0:
            member = (labels == n) & (mask > 0)
            area = int(np.count_nonzero(member))
            if not area:
                continue
            rows, columns = np.nonzero(member)
            blob_left, blob_top = int(columns.min()), int(rows.min())
            width = int(columns.max()) - blob_left + 1
            height = int(rows.max()) - blob_top + 1
        else:
            area = int(stats[n, cv2.CC_STAT_AREA])
            blob_left = int(stats[n, cv2.CC_STAT_LEFT])
            blob_top = int(stats[n, cv2.CC_STAT_TOP])
            width = int(stats[n, cv2.CC_STAT_WIDTH])
            height = int(stats[n, cv2.CC_STAT_HEIGHT])
        blobs.append((blob_left, blob_top, width, height, area))

    blobs.sort(key=_sort_key(order))

    desktop_left, desktop_top, desktop_width, desktop_height = virtual_bounds()
    desktop_right = desktop_left + desktop_width
    desktop_bottom = desktop_top + desktop_height

    hits: list[ColorHit] = []
    turned_down: list[tuple[ColorHit, str]] = []
    for blob_left, blob_top, width, height, area in blobs:
        left = region[0] + blob_left
        top = region[1] + blob_top
        # Only count an edge as a crop if moving the search area could
        # actually help. An area that already reaches the edge of the screen
        # cannot be widened, so saying "widen the area" there is noise.
        # A few pixels of slack: an area dragged to "the bottom of the
        # screen" lands a pixel or two short of it, and warning that such an
        # area could be widened is a lie you cannot act on.
        touching = []
        if blob_left <= 0 and region[0] > desktop_left + EDGE_SLACK:
            touching.append("left")
        if blob_top <= 0 and region[1] > desktop_top + EDGE_SLACK:
            touching.append("top")
        if (blob_left + width >= region[2]
                and region[0] + region[2] < desktop_right - EDGE_SLACK):
            touching.append("right")
        if (blob_top + height >= region[3]
                and region[1] + region[3] < desktop_bottom - EDGE_SLACK):
            touching.append("bottom")
        hit = ColorHit(left + width // 2, top + height // 2,
                       left, top, width, height, area, " and ".join(touching))
        # Why a patch is not the thing we are looking for, kept as words so
        # the GUI can show it rather than leaving you to guess.
        if area < min_pixels:
            turned_down.append((hit, f"{area} pixels, under {min_pixels}"))
        elif width < min_width:
            turned_down.append((hit, f"{width}px wide, under {min_width}"))
        elif height < min_height:
            turned_down.append((hit, f"{height}px tall, under {min_height}"))
        else:
            hits.append(hit)
    return hits, turned_down, mask


def find_colors(
    region: Region,
    target_rgb: tuple[int, int, int],
    tolerance: float = 40.0,
    min_pixels: int = 30,
    match: str = "rgb",
    min_saturation: int = 90,
    min_brightness: int = 70,
    order: str = "largest",
    join: int = 0,
    min_width: int = 0,
    min_height: int = 0,
) -> list[ColorHit]:
    """Every patch of `target_rgb` inside `region`, in the order asked for."""
    return _search(region, target_rgb, tolerance, min_pixels, match,
                   min_saturation, min_brightness, order, join,
                   min_width, min_height)[0]


def explain_colors(
    region: Region,
    target_rgb: tuple[int, int, int],
    tolerance: float = 40.0,
    min_pixels: int = 30,
    match: str = "rgb",
    min_saturation: int = 90,
    min_brightness: int = 70,
    order: str = "largest",
    join: int = 0,
    min_width: int = 0,
    min_height: int = 0,
) -> tuple[np.ndarray, list[tuple[ColorHit, str]], list[tuple[ColorHit, str]]]:
    """A picture of what matched, plus the patches kept and the ones dropped.

    Every matching pixel is tinted, each kept patch is boxed and numbered in
    the order the search would use them, and each dropped one is boxed faintly.
    When a background happens to share the color you are hunting for, this is
    the difference between guessing at settings and seeing the problem.
    """
    kept, dropped, mask = _search(region, target_rgb, tolerance, min_pixels,
                                  match, min_saturation, min_brightness, order,
                                  join, min_width, min_height)

    picture = grab(region).copy()
    # How saturated each patch actually is. This is the number that separates
    # a vivid highlight from a washed-out background of the same hue, and
    # there is no way to guess it -- it has to be measured.
    saturation = cv2.cvtColor(picture, cv2.COLOR_BGR2HSV)[:, :, 1]

    def describe(hit: ColorHit) -> str:
        left, top = hit.left - region[0], hit.top - region[1]
        inside = mask[top:top + hit.height, left:left + hit.width].astype(bool)
        values = saturation[top:top + hit.height, left:left + hit.width][inside]
        if not values.size:
            return ""
        return (f"saturation {int(np.percentile(values, 10))}-"
                f"{int(np.percentile(values, 90))}")

    kept_rows = [(hit, describe(hit)) for hit in kept]
    dropped_rows = [(hit, f"{why}, {describe(hit)}") for hit, why in dropped]
    # Tint what matched, keeping some of the original so you can still see
    # what part of the screen it sits on.
    if mask.any():
        tint = np.zeros_like(picture)
        tint[:, :] = (255, 0, 255)  # magenta, which nothing on screen is
        where = mask.astype(bool)
        picture[where] = (0.35 * picture[where] + 0.65 * tint[where]).astype(np.uint8)

    for hit, _why in dropped_rows:
        left, top = hit.left - region[0], hit.top - region[1]
        cv2.rectangle(picture, (left, top), (left + hit.width, top + hit.height),
                      (120, 120, 120), 1)
    for number, hit in enumerate(kept, start=1):
        left, top = hit.left - region[0], hit.top - region[1]
        cv2.rectangle(picture, (left, top), (left + hit.width, top + hit.height),
                      (0, 230, 0), 2)
        cv2.circle(picture, (hit.x - region[0], hit.y - region[1]), 5, (0, 230, 0), -1)
        cv2.putText(picture, str(number), (left + 4, max(16, top - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 230, 0), 2)
    return picture, kept_rows, dropped_rows


def find_color(
    region: Region,
    target_rgb: tuple[int, int, int],
    tolerance: float = 40.0,
    min_pixels: int = 30,
    match: str = "rgb",
    min_saturation: int = 90,
    min_brightness: int = 70,
    order: str = "largest",
    join: int = 0,
    min_width: int = 0,
    min_height: int = 0,
) -> ColorHit | None:
    """The one patch of `target_rgb` that `order` puts first. See find_colors."""
    hits = find_colors(region, target_rgb, tolerance, min_pixels, match,
                       min_saturation, min_brightness, order, join,
                       min_width, min_height)
    return hits[0] if hits else None


_VK_CODES = {
    "ESC": 0x1B,
    "SPACE": 0x20,
    "PAUSE": 0x13,
    "SCROLLLOCK": 0x91,
    **{f"F{n}": 0x6F + n for n in range(1, 13)},
}


def hotkey_names() -> tuple[str, ...]:
    """Every key we can watch for globally, in the order to offer them.

    The GUI builds its Stop key and Start/stop key menus from this, so it can
    never offer a key that `key_pressed` would then refuse.
    """
    function_keys = [f"F{n}" for n in range(1, 13) if f"F{n}" in _VK_CODES]
    rest = sorted(name for name in _VK_CODES if name not in function_keys)
    return tuple(function_keys + rest)


def key_pressed(name: str) -> bool:
    """Is the named key down right now, even if we don't have focus?"""
    try:
        vk = _VK_CODES[name.upper()]
    except KeyError:
        raise ValueError(
            f"Unsupported abort key {name!r}. Choose one of: "
            + ", ".join(hotkey_names())
        ) from None
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
