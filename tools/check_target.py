"""Check whether this tool can see and click your application.

Fullscreen applications are the awkward case. Some render in a way that screen
capture cannot read (you get a black frame), and some refuse synthetic clicks.
Find out in ten seconds rather than after building a whole sequence.

    python check_target.py

Switch to your application during the countdown. It reports what it found and
saves a screenshot so you can see exactly what the matcher would be working
from.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np

import _bootstrap  # noqa: F401  (sys.path)

from pixie.system import screen

from pixie.paths import APP_DIR as PROJECT_DIR
COUNTDOWN = 6
SHOT_PATH = PROJECT_DIR / "target_check.png"

_user32 = ctypes.windll.user32


def foreground_window() -> tuple[int, str, str, wintypes.RECT]:
    hwnd = _user32.GetForegroundWindow()

    length = _user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, title_buffer, length + 1)

    class_buffer = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, class_buffer, 256)

    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, title_buffer.value, class_buffer.value, rect


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def main() -> int:
    screen.set_dpi_aware()

    print(__doc__.strip().splitlines()[0])
    print()
    print(f"Switch to your application now. Capturing in {COUNTDOWN} seconds...")
    for remaining in range(COUNTDOWN, 0, -1):
        print(f"  {remaining}...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 20, end="\r")

    hwnd, title, class_name, rect = foreground_window()
    width, height = rect.right - rect.left, rect.bottom - rect.top
    _, _, screen_w, screen_h = screen.virtual_bounds()

    print("Foreground window")
    print(f"  Title      : {title or '(none)'}")
    print(f"  Class      : {class_name}")
    print(f"  Position   : {rect.left}, {rect.top}")
    print(f"  Size       : {width} x {height}")

    monitor_sized = width >= screen_w * 0.98 or height >= screen_h * 0.98
    print(f"  Fullscreen : {'looks like it' if monitor_sized else 'no, windowed'}")

    frame = screen.grab((rect.left, rect.top, max(width, 1), max(height, 1)))
    cv2.imwrite(str(SHOT_PATH), frame)

    mean = float(frame.mean())
    unique = len(np.unique(frame.reshape(-1, frame.shape[2]), axis=0))
    print("\nScreen capture")
    print(f"  Saved      : {SHOT_PATH.name}")
    print(f"  Brightness : {mean:.1f} / 255")
    print(f"  Distinct colors: {unique}")

    problems = []
    if mean < 2.0 and unique < 5:
        problems.append(
            "The capture came back essentially black. This application is very "
            "likely using exclusive fullscreen, which screen capture cannot read.\n"
            "      Fix: set the application to 'borderless windowed' or 'windowed "
            "fullscreen' mode. That is the usual option and costs nothing.")
    elif unique < 50:
        problems.append(
            "The capture has very few distinct colors. Open the saved PNG and "
            "check it actually shows your application.")
    else:
        print("  Verdict    : capture works - open the PNG to confirm it looks right")

    print("\nClicking")
    print(f"  This process elevated: {'yes' if is_elevated() else 'no'}")
    if not is_elevated():
        print("      If the application runs as administrator it will silently ignore")
        print("      synthetic clicks. Start your terminal as administrator if so.")
    print("  Synthetic clicks via SendInput work with almost all Windows")
    print("  applications, including fullscreen ones. Prove it with a dry run first.")

    print()
    if problems:
        print("PROBLEMS TO SORT OUT FIRST:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Looks workable. Next: python gui.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
