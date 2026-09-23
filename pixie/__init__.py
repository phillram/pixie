"""Pixie: watch the screen, find things, click them, repeat.

The package is split three ways:

    pixie.core     the sequence engine and the step vocabulary
    pixie.system   talking to Windows: screen capture, mouse, keyboard
    pixie.ui       the tkinter application and its screen picker

Nothing in core or system imports from ui, so the engine can run headless.
"""

__version__ = "1.0.8"
