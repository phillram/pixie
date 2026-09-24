"""Key presses via SendInput.

Sends the virtual-key code and the hardware scan code together, which is what
real keyboards produce. Applications that read raw scan codes (games, mostly)
ignore virtual-key-only input, so sending both covers far more of them.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Callable

_user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
MAPVK_VK_TO_VSC = 0

# Keys that live on the extended part of the keyboard and need the extended
# flag, or applications see the numpad equivalent instead.
#
# Enter is deliberately absent. It is the one key where the rule runs the other
# way: the main Enter carries the plain scan code and the *numpad* Enter is the
# extended one. Flagging it made every "press Enter" arrive as numpad Enter,
# which window messages hide -- both report VK_RETURN -- but raw input does not,
# so games read it as a different key and ignore it.
# Right Ctrl and right Alt are extended; right Shift is not, because it has a
# scan code of its own (0x36) rather than sharing the left one's.
_EXTENDED = {
    "Insert", "Delete", "Home", "End", "PageUp", "PageDown",
    "Up", "Down", "Left", "Right", "PrintScreen", "NumLock",
    "NumpadEnter", "NumpadDivide", "RightCtrl", "RightAlt",
}

KEYS: dict[str, int] = {
    **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(digit): 0x30 + digit for digit in range(10)},
    **{f"F{n}": 0x6F + n for n in range(1, 13)},
    "Enter": 0x0D,
    "NumpadEnter": 0x0D,
    "Escape": 0x1B,
    "Space": 0x20,
    "Tab": 0x09,
    "Backspace": 0x08,
    "Delete": 0x2E,
    "Insert": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Up": 0x26,
    "Down": 0x28,
    "Left": 0x25,
    "Right": 0x27,
    # The plain three are the "either side" virtual keys Windows reports when
    # it does not care which one you used. Most applications accept them. The
    # sided ones below are separate keys, and a game may well bind only one.
    "Shift": 0x10,
    "Ctrl": 0x11,
    "Alt": 0x12,
    "LeftShift": 0xA0,
    "RightShift": 0xA1,
    "LeftCtrl": 0xA2,
    "RightCtrl": 0xA3,
    "LeftAlt": 0xA4,
    "RightAlt": 0xA5,
    "CapsLock": 0x14,
    "NumLock": 0x90,
    "PrintScreen": 0x2C,
    "Minus": 0xBD,
    "Equals": 0xBB,
    "Comma": 0xBC,
    "Period": 0xBE,
    "Slash": 0xBF,
    "Semicolon": 0xBA,
    "Apostrophe": 0xDE,
    "LeftBracket": 0xDB,
    "RightBracket": 0xDD,
    "Backslash": 0xDC,
    "Backtick": 0xC0,
    # The number pad. Every one of these is a distinct key from the one with
    # the same face on the main keyboard, and applications that read scan
    # codes tell them apart. The digits only produce these codes while Num
    # Lock is on; with it off the pad sends Home, End, the arrows and so on.
    **{f"Numpad{digit}": 0x60 + digit for digit in range(10)},
    "NumpadPlus": 0x6B,
    "NumpadMinus": 0x6D,
    "NumpadMultiply": 0x6A,
    "NumpadDivide": 0x6F,
    "NumpadPeriod": 0x6E,
}

KEY_NAMES: tuple[str, ...] = tuple(KEYS)

# Plain English for each key, and for the ones that have a look-alike
# elsewhere on the keyboard, which one this is. Two keys that read the same
# on their key cap are the single most confusing thing here: they share a
# virtual-key code, so nothing on screen distinguishes them, yet a game
# treats them as unrelated.
LABELS: dict[str, str] = {
    "Enter": "Enter  (the main one)",
    "NumpadEnter": "Numpad Enter",
    "Shift": "Shift  (either side)",
    "Ctrl": "Ctrl  (either side)",
    "Alt": "Alt  (either side)",
    "LeftShift": "Left Shift",
    "RightShift": "Right Shift",
    "LeftCtrl": "Left Ctrl",
    "RightCtrl": "Right Ctrl",
    "LeftAlt": "Left Alt",
    "RightAlt": "Right Alt",
    "NumpadPlus": "Numpad +",
    "NumpadMinus": "Numpad -",
    "NumpadMultiply": "Numpad *",
    "NumpadDivide": "Numpad /",
    "NumpadPeriod": "Numpad .",
    "Minus": "-  (main keyboard)",
    "Equals": "=",
    "Comma": ",",
    "Period": ".  (main keyboard)",
    "Slash": "/  (main keyboard)",
    "Semicolon": ";",
    "Apostrophe": "'",
    "LeftBracket": "[",
    "RightBracket": "]",
    "Backslash": "\\",
    "Backtick": "`",
    "PageUp": "Page Up",
    "PageDown": "Page Down",
    "CapsLock": "Caps Lock",
    "NumLock": "Num Lock",
    "PrintScreen": "Print Screen",
    "Up": "Up arrow",
    "Down": "Down arrow",
    "Left": "Left arrow",
    "Right": "Right arrow",
    **{f"Numpad{digit}": f"Numpad {digit}" for digit in range(10)},
    **{str(digit): f"{digit}  (main keyboard)" for digit in range(10)},
}

# Keys that share their face, and their virtual-key code, with another key.
# Recording one of these is worth saying out loud, because the two are not
# interchangeable and the mistake is invisible afterwards.
TWINS: dict[str, str] = {
    "Enter": "NumpadEnter", "NumpadEnter": "Enter",
    "Shift": "LeftShift", "Ctrl": "LeftCtrl", "Alt": "LeftAlt",
    "LeftShift": "Shift", "RightShift": "Shift",
    "LeftCtrl": "Ctrl", "RightCtrl": "Ctrl",
    "LeftAlt": "Alt", "RightAlt": "Alt",
    **{f"Numpad{digit}": str(digit) for digit in range(10)},
    **{str(digit): f"Numpad{digit}" for digit in range(10)},
    "NumpadPlus": "Equals", "NumpadMinus": "Minus",
    "NumpadDivide": "Slash", "NumpadPeriod": "Period",
    "Minus": "NumpadMinus", "Period": "NumpadPeriod", "Slash": "NumpadDivide",
}


def label(name: str) -> str:
    """Plain English for a key name, for showing to somebody."""
    return LABELS.get(name, name)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    """Only here so the union below comes out the right size."""

    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    # INPUT is a union sized by its largest member, MOUSEINPUT. Declaring only
    # the keyboard part makes the struct 32 bytes instead of 40, and SendInput
    # silently rejects anything whose cbSize doesn't match exactly.
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _send(vk: int, scan: int, flags: int) -> None:
    event = _INPUT(type=INPUT_KEYBOARD,
                   union=_INPUTUNION(ki=_KEYBDINPUT(vk, scan, flags, 0, None)))
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))
    if sent != 1:
        raise OSError(f"SendInput rejected the key event (error {ctypes.get_last_error()})")


def normalize(name: str) -> str:
    """Accept loose spellings and return the canonical key name."""
    if not name:
        raise ValueError("No key given")
    cleaned = str(name).strip().replace(" ", "").replace("_", "")
    for candidate in KEYS:
        if candidate.lower() == cleaned.lower():
            return candidate
    aliases = {
        "return": "Enter", "esc": "Escape", "del": "Delete", "ins": "Insert",
        "pgup": "PageUp", "pgdn": "PageDown", "control": "Ctrl",
        "spacebar": "Space", "arrowup": "Up", "arrowdown": "Down",
        "arrowleft": "Left", "arrowright": "Right",
    }
    if cleaned.lower() in aliases:
        return aliases[cleaned.lower()]
    raise ValueError(f"Unknown key {name!r}. Known keys: {', '.join(KEY_NAMES)}")


def press(name: str, presses: int = 1,
          interval: float | Callable[[], float] = 0.08,
          hold: float = 0.05) -> None:
    """Tap a key. `presses` is how many separate taps, `hold` how long each lasts.

    `hold` matters for applications that check the keyboard once a frame rather
    than reading every event. Too short a tap can start and finish between two
    checks and be missed entirely, so the default spans several frames.
    """
    key = normalize(name)
    vk = KEYS[key]
    scan = _user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    flags = KEYEVENTF_EXTENDEDKEY if key in _EXTENDED else 0

    for n in range(max(1, int(presses))):
        if n:
            time.sleep(interval() if callable(interval) else interval)
        _send(vk, scan, flags)
        time.sleep(hold)
        _send(vk, scan, flags | KEYEVENTF_KEYUP)
