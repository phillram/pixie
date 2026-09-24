"""Mouse movement and clicking via SendInput.

SendInput rather than the older mouse_event because more applications --
games and anything using raw input especially -- actually react to it.
"""

from __future__ import annotations

import ctypes
import math
import time
from ctypes import wintypes
from typing import Callable

_user32 = ctypes.windll.user32

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000  # absolute coordinates span every monitor
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", _MOUSEINPUT)]


def _send(flags: int, dx: int = 0, dy: int = 0) -> None:
    event = _INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(dx, dy, 0, flags, 0, None))
    _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))


def position() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def _virtual_desktop() -> tuple[int, int, int, int]:
    """left, top, width, height of every monitor combined."""
    return (_user32.GetSystemMetrics(76), _user32.GetSystemMetrics(77),
            _user32.GetSystemMetrics(78), _user32.GetSystemMetrics(79))


def move_to(x: int, y: int) -> None:
    """Put the cursor at (x, y) as an input event, not by teleporting it.

    SetCursorPos moves the cursor and nothing else: no input is generated, so
    an application reading raw input (WM_INPUT, which is what game engines
    normally use) never learns the pointer moved. The cursor is drawn
    somewhere new while the application still believes it is where it was --
    which is how a card stays enlarged after the pointer has visibly left it.

    SendInput goes in at the bottom of the input stack instead, so a raw-input
    reader sees the movement exactly as it sees a real hand. Clicks were
    already sent this way; movement was not, and that asymmetry is the bug.
    """
    x, y = int(x), int(y)
    left, top, width, height = _virtual_desktop()
    # Absolute coordinates are 0-65535 across the virtual desktop, whatever
    # its real size, and the far edge is 65535 rather than 65536.
    _send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
          ((x - left) * 65535) // max(1, width - 1),
          ((y - top) * 65535) // max(1, height - 1))
    # That scaling rounds, so it can land a pixel out. The movement has
    # already been reported by then; this only corrects where the click goes.
    if position() != (x, y):
        _user32.SetCursorPos(x, y)


# How a glide is drawn: a step every few pixels, and a cap so crossing a wide
# desktop does not take all day.
GLIDE_STEP = 24
GLIDE_MAX_STEPS = 60


def _moment(value: float | Callable[[], float]) -> float:
    """A delay that may be a number, or a function returning a fresh one.

    Callers that want every occurrence to differ pass the function; callers
    that want one length pass the number.
    """
    return float(value() if callable(value) else value)


def settle() -> None:
    """A pixel of movement in place, and back.

    Arriving somewhere is one event, and an application that only re-checks
    what is under the pointer when the pointer moves can be left holding a
    hover state for something the cursor has already left. A hand never lands
    dead still; this is the smallest honest version of that.
    """
    x, y = position()
    move_to(x + 1, y)
    move_to(x, y)


def glide_to(x: int, y: int, seconds: float = 0.25) -> None:
    """Travel to (x, y) over `seconds` instead of appearing there.

    Warping the cursor is one event: the pointer is somewhere, then it is
    somewhere else, having crossed nothing. Applications that track hover
    never see it pass over anything, and some never register that it left
    where it was. Moving in steps looks to them like an ordinary hand.

    Eased at both ends, because a constant-speed slide is its own tell.

    `seconds` is the whole journey however far it is, so the caller has to
    scale it by distance. Leaving that to a default here is what made a 40px
    nudge and a 7000px sweep both take a quarter of a second, the second of
    them at twenty-four thousand pixels a second.
    """
    from_x, from_y = position()
    x, y = int(x), int(y)
    distance = math.hypot(x - from_x, y - from_y)
    if distance < 1:
        move_to(x, y)
        return

    count = max(2, min(GLIDE_MAX_STEPS, int(distance // GLIDE_STEP)))
    pause = max(0.0, seconds) / count
    for step in range(1, count + 1):
        # Ease in and out: slow at the start, quickest in the middle, slow
        # into the target.
        fraction = step / count
        eased = fraction * fraction * (3 - 2 * fraction)
        move_to(round(from_x + (x - from_x) * eased),
                round(from_y + (y - from_y) * eased))
        if pause:
            time.sleep(pause)
    move_to(x, y)


def click(
    x: int,
    y: int,
    button: str = "left",
    clicks: int = 1,
    interval: float | Callable[[], float] = 0.06,
    before: float | Callable[[], float] = 0.05,
    hold: float | Callable[[], float] = 0.02,
) -> None:
    """Move to (x, y) and click.

    Three delays, any of which may be a function so that no two clicks are
    timed alike:

    `before` is the wait between arriving and pressing. Some applications
    will not accept a click until they have noticed the pointer arrive, and
    process it against wherever the cursor was before otherwise.

    `hold` is how long the button stays down.

    `interval` is the gap between clicks when there is more than one. Keep it
    under the system double-click time (500ms by default) if you want
    `clicks=2` to read as a double-click.

    The first was named `settle` and shadowed the settle() function below.
    """
    if button not in _BUTTONS:
        raise ValueError(f"Unknown button {button!r}. Use left, right or middle.")

    move_to(x, y)
    time.sleep(_moment(before))
    down, up = _BUTTONS[button]
    for n in range(clicks):
        if n:
            time.sleep(_moment(interval))
        _send(down)
        time.sleep(_moment(hold))
        _send(up)
