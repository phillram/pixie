"""Build Pixie.exe.

    python tools/build_exe.py

Produces a single self-contained Pixie.exe in this folder, which needs no
Python installed. Run it again after changing any of the code.

The exe reads and writes images/ and sequences/ next to itself, so the built
Pixie and the run-from-source Pixie share the same sequences.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent  # tools/ -> project root
EXE_PATH = APP_DIR / "Pixie.exe"
BUILD_DIR = APP_DIR / "build"
SPEC_PATH = APP_DIR / "Pixie.spec"

# Nothing here imports these, but they get dragged in transitively and add
# hundreds of megabytes if left alone.
EXCLUDES = ("matplotlib", "scipy", "pandas", "PyQt5", "PyQt6", "PySide2",
            "PySide6", "pytest", "IPython", "notebook", "sqlite3")


def _is_running() -> bool:
    """Is a built Pixie.exe already running? Windows locks a running exe."""
    if not EXE_PATH.exists():
        return False
    try:
        # Opening for append fails with a sharing violation while it's running.
        with EXE_PATH.open("ab"):
            return False
    except (PermissionError, OSError):
        return True


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. Run:")
        print(f"    {sys.executable} -m pip install pyinstaller")
        return 1

    if not (APP_DIR / "assets" / "pixie.ico").exists():
        print("assets/pixie.ico is missing - run `python tools/make_icon.py` first.")
        return 1

    if _is_running():
        print("Pixie.exe is currently running, so it can't be overwritten.")
        print("Close Pixie and run this again.")
        return 1

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--onefile", "--windowed",
        "--name", "Pixie",
        "--icon", "assets/pixie.ico",
        "--add-data", "assets/pixie.ico;.",
        "--distpath", str(APP_DIR),      # straight into the project folder
        "--workpath", str(BUILD_DIR),
        "--specpath", str(APP_DIR),
    ]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    command.append(str(APP_DIR / "pixie" / "__main__.py"))

    print(f"Building {EXE_PATH.name}. This takes a minute.\n")
    started = time.time()
    result = subprocess.run(command, cwd=APP_DIR)
    if result.returncode != 0:
        print("\nBuild failed - see the PyInstaller output above.")
        return result.returncode

    # PyInstaller's leftovers; the exe is self-contained without them.
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    SPEC_PATH.unlink(missing_ok=True)

    if not EXE_PATH.exists():
        print("\nBuild reported success but produced no exe.")
        return 1

    size_mb = EXE_PATH.stat().st_size / (1024 * 1024)
    print(f"\nBuilt {EXE_PATH.name} - {size_mb:.0f} MB in {time.time() - started:.0f}s")
    print(f"  {EXE_PATH}")
    print("\nDouble-click it. First launch takes a couple of seconds while it")
    print("unpacks itself; after that Windows caches it and it is quicker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
