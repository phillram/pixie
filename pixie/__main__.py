"""Entry point.

    python -m pixie                        open the window
    python -m pixie sequences/job.json     run that sequence, no window

The headless form is for a shortcut or a scheduled task. Everything it accepts
is described by `python -m pixie --help`.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # A bare launch means the GUI. Anything else is for the command line
    # runner, including --help, so that `python -m pixie --help` describes the
    # arguments that actually take a sequence.
    if not argv:
        from pixie.ui.app import main as gui_main

        return gui_main()

    from pixie.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
