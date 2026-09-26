"""Helpers for the checks that have to touch the real desktop.

Most of the suite is arithmetic and can only fail if the code is wrong. A
handful of checks cannot be: capture has to photograph a real screen, movement
has to move a real cursor, and key presses have to land in a real window that
really holds focus. Those checks failed whenever the desktop was busy -- a
mouse being used, a window repainting, focus moving -- and a suite that cries
wolf stops being read, which is worse than not having the checks at all.

Three answers, for three different problems:

`frozen_screen` is for checks that should never have looked at the live desktop
twice. One photograph, used for everything that follows.

`retried` is for a race. Interference rarely survives several attempts spread
over a second or two, while a real fault fails every one of them, so retrying
turns noise into silence without hiding a break.

`DISTURBED` is for when we can prove the check did not run -- the pointer is
being driven by something else, or another window holds focus. That is neither
a pass nor a failure, and reporting it as either is a lie. It is a skip.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import numpy as np

TRIES = 5
PAUSE = 0.3

# Returned by an attempt that could not be carried out. Not a problem with the
# code, so never a failure, and not evidence of anything, so never a pass.
DISTURBED = "<the desktop was in use>"


def retried(attempt: Callable[[], list[str]], tries: int = TRIES,
            pause: float = PAUSE) -> tuple[list[str], int]:
    """Run a desktop-dependent check until it passes, or give up and report.

    `attempt` returns its problems, empty when it passed, or [DISTURBED] when
    it could not be run at all. Returns the last attempt's problems and how
    many attempts were used, so a caller can say "passed, third try" rather
    than pretending nothing happened.
    """
    problems: list[str] = []
    for used in range(1, tries + 1):
        problems = list(attempt())
        if not problems:
            return [], used
        if used < tries:
            time.sleep(pause)
    return problems, tries


def unrunnable(problems: list[str]) -> bool:
    """Did every attempt fail to run, rather than fail?"""
    return problems == [DISTURBED]


def outcome(heading: str, problems: list[str], used: int, passed: str) -> None:
    """Print one line that matches what actually happened.

    Worth its own function because the first version of this printed the
    success sentence from the same place whether or not the check had passed,
    so a run that gave up after five tries announced that everything landed
    exactly, with the failure listed forty lines further down.
    """
    if unrunnable(problems):
        print(f"{heading}: SKIPPED ({DISTURBED.strip('<>')})")
    elif problems:
        print(f"{heading}: FAILED after {used} tries")
    else:
        print(f"{heading}: {passed}{tries_note(used)}")


def tries_note(used: int) -> str:
    """'  (2nd try)' when it took more than one, nothing when it did not."""
    if used <= 1:
        return ""
    suffix = {2: "nd", 3: "rd"}.get(used, "th")
    return f"  ({used}{suffix} try)"


def someone_else_is_moving(mouse: Any, samples: int = 5,
                           pause: float = 0.03) -> bool:
    """Is the pointer being driven by something other than us?

    Asked only when a movement check has already missed. A cursor that keeps
    moving while nobody here is moving it is a hand on the mouse, and the
    arithmetic this checks cannot be judged through that.

    Two readings is not enough evidence. Windows nudges the cursor once when a
    move is clamped at the edge of the desktop, and a pair of reads either side
    of that nudge looks exactly like interference -- which is how a deliberate
    three-pixel fault, injected to prove this suite still catches faults, got
    reported as a busy desktop instead. A hand keeps moving, so insist on
    seeing it move more than once.
    """
    readings = []
    for _ in range(samples):
        readings.append(mouse.position())
        time.sleep(pause)
    return sum(1 for a, b in zip(readings, readings[1:]) if a != b) >= 2


def has_focus(root: Any, ctypes: Any) -> bool:
    """Is our own test window the one Windows is sending input to?

    Asked before a real key or click goes out, so a stray press lands in our
    window rather than in whatever the user happens to be typing into, and
    again afterwards, because focus can be taken in between.
    """
    foreground = ctypes.windll.user32.GetForegroundWindow()
    ours = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
    return foreground == ours


@contextmanager
def frozen_screen(module: Any, frame: np.ndarray,
                  origin: tuple[int, int]) -> Iterator[None]:
    """Serve one photograph for every grab, cropped as the caller asked.

    `origin` is the top-left of the virtual desktop, because a region arrives
    in absolute screen coordinates and the frame's own (0, 0) is that corner.
    Ignoring the region -- handing back the whole desktop for a 7x7 sample --
    looks like it works right up until something reads the shape.
    """
    left, top = origin
    real = module.grab

    def grab(region: tuple[int, int, int, int] | None = None) -> np.ndarray:
        if region is None:
            return frame
        x, y, width, height = region
        return frame[y - top: y - top + height, x - left: x - left + width].copy()

    module.grab = grab
    try:
        yield
    finally:
        module.grab = real
