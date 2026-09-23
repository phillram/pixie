"""Mouse movement and clicking via SendInput.

SendInput rather than the older mouse_event because more applications --
games and anything using raw input especially -- actually react to it.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

_user32 = ctypes.windll.user32

INPUT_MOUSE = 0
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


def _send(flags: int) -> None:
    event = _INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(0, 0, 0, flags, 0, None))
    _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))


def position() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def move_to(x: int, y: int) -> None:
    _user32.SetCursorPos(int(x), int(y))


def click(
    x: int,
    y: int,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.06,
    settle: float = 0.05,
) -> None:
    """Move to (x, y) and click.

    `settle` gives the target application a moment to register the hover --
    tooltips and hover states often need it. `interval` is the gap between
    clicks; keep it under the system double-click time (500ms by default)
    if you want `clicks=2` to read as a double-click.
    """
    if button not in _BUTTONS:
        raise ValueError(f"Unknown button {button!r}. Use left, right or middle.")

    move_to(x, y)
    time.sleep(settle)
    down, up = _BUTTONS[button]
    for n in range(clicks):
        if n:
            time.sleep(interval)
        _send(down)
        time.sleep(0.02)
        _send(up)


def double_click(x: int, y: int, button: str = "left") -> None:
    click(x, y, button=button, clicks=2, interval=0.06)
