"""Where Pixie keeps her things.

Running from source, that's this folder. Running as a built exe, PyInstaller
unpacks the *code* to a temporary directory that is deleted on exit -- so data
the user owns (their sequences, their captured images) has to live next to the
exe instead, where they can see it and it survives.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "Pixie"

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

IMAGES_DIR = APP_DIR / "images"
SEQUENCES_DIR = APP_DIR / "sequences"
STATE_PATH = APP_DIR / ".pixie_state.json"

# Read-only things shipped *with* the code. In a onefile build PyInstaller
# unpacks these to a temp dir it points _MEIPASS at, which is not APP_DIR.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) if FROZEN else APP_DIR
ICON_PATH = RESOURCE_DIR / "pixie.ico"


def ensure_dirs() -> None:
    """Make the folders Pixie writes into, so a fresh exe works first time."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    SEQUENCES_DIR.mkdir(parents=True, exist_ok=True)


def resolve(relative: str | Path) -> Path:
    """Turn a stored relative path (like 'images/button.png') into a real one."""
    path = Path(relative)
    return path if path.is_absolute() else APP_DIR / path
