"""Find captured pictures that no sequence uses any more.

Recapturing a step writes a new file and leaves the old one behind, so
images/ collects clutter. This lists what nothing points at.

    python tools/tidy_images.py            # list them, delete nothing
    python tools/tidy_images.py --apply    # delete them

It reads every sequence in sequences/. A picture used by any of them is
safe. Save your work before running it with --apply: an unsaved step in the
Pixie window is not in any file yet, so its picture looks unused from here.
"""

from __future__ import annotations

import argparse
import json
import sys

import _bootstrap  # noqa: F401  (sys.path)

from pixie.paths import APP_DIR, IMAGES_DIR, SEQUENCES_DIR


def referenced() -> tuple[set[str], int]:
    """Every image path mentioned by a saved sequence, and how many files."""
    used: set[str] = set()
    sequences = sorted(SEQUENCES_DIR.glob("*.json"))
    for path in sequences:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            # Better to keep a picture than to delete one because a file we
            # could not read happened to mention it.
            print(f"  ! {path.name} could not be read ({error}). Stopping, "
                  "because anything it uses would look unused.")
            raise SystemExit(2) from None
        for step in data.get("steps", []):
            if isinstance(step, dict) and step.get("image"):
                used.add(str(step["image"]).replace("\\", "/"))
    return used, len(sequences)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually delete them (default: just list)")
    args = parser.parse_args()

    if not IMAGES_DIR.exists():
        print("No images folder yet, so nothing to tidy.")
        return 0

    used, sequence_count = referenced()
    files = sorted(p for p in IMAGES_DIR.iterdir() if p.is_file())
    unused = [p for p in files
              if p.relative_to(APP_DIR).as_posix() not in used]

    print(f"{len(files)} pictures in images/, "
          f"{sequence_count} sequence file(s) checked.")
    if not unused:
        print("Every picture is in use. Nothing to tidy.")
        return 0

    total = sum(p.stat().st_size for p in unused)
    print(f"\n{len(unused)} unused, {total / 1024:.0f}KB:")
    for path in unused:
        print(f"  {path.name:44s} {path.stat().st_size / 1024:6.0f}KB")

    if not args.apply:
        print("\nNothing was deleted. Run again with --apply to delete these.")
        print("Check the list first: a sequence you have not saved yet does "
              "not count as using a picture.")
        return 0

    deleted = 0
    for path in unused:
        try:
            path.unlink()
            deleted += 1
        except OSError as error:
            print(f"  could not delete {path.name}: {error}")
    print(f"\nDeleted {deleted} of {len(unused)}, freeing {total / 1024:.0f}KB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
