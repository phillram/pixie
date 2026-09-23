"""Where Pixie keeps her things.

Two directories matter and they are not the same one:

APP_DIR is where the user's own files live, the sequences they build and the
images they capture. From source that is the project root; from a built exe it
is the folder holding the exe. It is never inside the package, because a
PyInstaller onefile build unpacks the code to a temporary directory that is
deleted on exit, and anything written there would vanish.

RESOURCE_DIR is where files shipped *with* the code live, like the icon. In a
frozen build that is the temporary unpack directory, which is exactly where
those files are and exactly where user data must not go.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "Pixie"

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    # This file is pixie/paths.py, so the project root is two levels up.
    APP_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = APP_DIR / "assets"

IMAGES_DIR = APP_DIR / "images"
SEQUENCES_DIR = APP_DIR / "sequences"
STATE_PATH = APP_DIR / ".pixie_state.json"
ICON_PATH = RESOURCE_DIR / "pixie.ico"


def ensure_dirs() -> None:
    """Make the folders Pixie writes into, so a fresh exe works first time."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    SEQUENCES_DIR.mkdir(parents=True, exist_ok=True)


def resolve(relative: str | Path) -> Path:
    """Turn a stored relative path (like 'images/button.png') into a real one."""
    path = Path(relative)
    return path if path.is_absolute() else APP_DIR / path
