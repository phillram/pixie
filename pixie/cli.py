"""Run a saved sequence from the command line, without the GUI.

    python -m pixie sequences/my_job.json
    python -m pixie sequences/my_job.json --dry-run
    python -m pixie sequences/my_job.json --max-cycles 20

Build sequences in the window (`python -m pixie` with no arguments); this is
for running one unattended, from a shortcut or a scheduled task.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pixie.core import engine as engine_mod
from pixie.system import screen

from pixie.paths import APP_DIR as PROJECT_DIR


def make_printer(quiet: bool):
    def emit(event: dict[str, Any]) -> None:
        if event.get("kind") != "log":
            return
        if quiet and event.get("level") == "info":
            return
        print(f"[{datetime.now():%H:%M:%S}] {event['message']}", flush=True)
    return emit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sequence", type=Path, help="path to a saved sequence JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="detect and log, but never actually click")
    parser.add_argument("--max-cycles", type=int, metavar="N",
                        help="stop after N completed cycles (default: run until stopped)")
    parser.add_argument("--quiet", action="store_true",
                        help="only report warnings and errors")
    args = parser.parse_args(argv)

    if not args.sequence.exists():
        parser.error(f"No such sequence: {args.sequence}")

    screen.set_dpi_aware()
    sequence = engine_mod.Sequence.load(args.sequence)
    runner = engine_mod.Engine(sequence, emit=make_printer(args.quiet),
                               dry_run=args.dry_run, base_dir=PROJECT_DIR)
    runner.run(max_cycles=args.max_cycles)
    return 0 if runner.cycles_completed or args.max_cycles == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
