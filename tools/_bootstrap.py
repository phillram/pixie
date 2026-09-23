"""Put the project root on sys.path.

These scripts live in a subdirectory but import the `pixie` package from the
root, so running them directly (`python tools/tune_color.py`) needs the root
importable. Importing this module first arranges that.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
