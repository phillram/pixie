"""Runs a sequence of steps, over and over, until told to stop.

The engine knows nothing about the GUI. It reports what it is doing through
an `emit` callback and checks a `threading.Event` to know when to stop, so
it works equally well behind the GUI or the command line.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pixie.system import keyboard
from pixie.system import mouse
from pixie.system import screen
from pixie.core import steps as step_defs

from pixie.paths import APP_DIR as PROJECT_DIR
FAILSAFE_CORNER = 5  # mouse within this many pixels of the top-left aborts
GUARD_INTERVAL = 0.05
IDLE_NOTICE_SECONDS = 15.0  # how often to say 'still waiting' while idling

# Every level `log` may be called with. The GUI colors them, and
# tools/check_wiring.py fails if it has no color for one of these.
LOG_LEVELS = ("info", "good", "warn", "error", "muted")

# Where the cursor goes after each step. The keys are what a sequence file
# stores; the labels are what Settings shows. One table, so the two cannot
# disagree about what "center" means.
PARK_LABELS = {
    "off": "leave the cursor alone",
    "center": "move it to the middle of the screen",
    "custom": "move it to a spot I pick",
}
PARK_MODES = tuple(PARK_LABELS)


class Aborted(Exception):
    """The user asked us to stop."""


@dataclass
class Settings:
    abort_key: str = "F8"
    # Starts the run when idle and stops it when running, from any window.
    # "off" disables it.
    toggle_key: str = "F9"
    poll_interval: float = 0.25
    # Pauses are ranges. Set min and max the same for a fixed delay, or spread
    # them for a varying one.
    step_pause_min: float = 0.3
    step_pause_max: float = 0.3
    # At a section boundary: moving on to the next section, or starting the
    # current one again. Separate from the step pause, because the time an
    # application needs between clicks is rarely the time it needs between
    # screens -- often it needs none at all.
    section_pause_min: float = 0.0
    section_pause_max: float = 0.0
    cycle_pause_min: float = 1.0
    cycle_pause_max: float = 1.0
    failsafe_corner: bool = True
    # Where to send the cursor after each step: "off", "center" (middle of the
    # primary monitor) or "custom" (park_point).
    park_mouse: str = "off"
    park_point: list[int] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Settings":
        data = dict(data or {})
        # Older sequences stored a single number per pause. Treat it as a
        # range of zero width so they keep behaving exactly as before.
        for old, prefix in (("step_pause", "step_pause"),
                            ("cycle_pause", "cycle_pause")):
            if old in data:
                value = data.pop(old)
                data.setdefault(f"{prefix}_min", value)
                data.setdefault(f"{prefix}_max", value)
        # The section pause arrived later. Before it existed, repeating a
        # section waited the cycle pause, so a sequence saved back then
        # inherits that value and goes on behaving exactly as it did.
        if "section_pause_min" not in data and "cycle_pause_min" in data:
            data["section_pause_min"] = data["cycle_pause_min"]
            data.setdefault("section_pause_max", data.get("cycle_pause_max",
                                                          data["cycle_pause_min"]))
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)

    def step_pause(self) -> float:
        return _between(self.step_pause_min, self.step_pause_max)

    def section_pause(self) -> float:
        return _between(self.section_pause_min, self.section_pause_max)

    def cycle_pause(self) -> float:
        return _between(self.cycle_pause_min, self.cycle_pause_max)


def _between(low: float, high: float) -> float:
    """A number in [low, high]. Returns low exactly when the range is empty."""
    low = max(0.0, float(low))
    high = max(0.0, float(high))
    if high <= low:
        return low
    return random.uniform(low, high)


@dataclass
class Sequence:
    """A named list of steps, plus the settings the run uses."""

    name: str = "Untitled"
    steps: list[dict[str, Any]] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    path: Path | None = None

    # Renamed when the project switched to American spelling.
    RENAMED_TYPES = {"wait_for_colour": "wait_for_color",
                     "wait_for_colour_in_area": "wait_for_color_in_area"}
    RENAMED_FIELDS = {"colour": "color"}

    @classmethod
    def load(cls, path: str | Path) -> "Sequence":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            name=data.get("name", path.stem),
            steps=cls._migrate(data.get("steps", [])),
            settings=Settings.from_dict(data.get("settings")),
            path=path,
        )

    @classmethod
    def _migrate(cls, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Bring sequences saved by an older Pixie up to date."""
        for step in steps:
            step["type"] = cls.RENAMED_TYPES.get(step.get("type", ""), step.get("type"))
            for old, new in cls.RENAMED_FIELDS.items():
                if old in step:
                    step[new] = step.pop(old)
        return steps

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("No path to save to")
        payload = {
            "name": self.name,
            "settings": vars(self.settings),
            "steps": self.steps,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.path = target
        return target

    def warnings(self) -> list[str]:
        """Things that will run but probably aren't what you meant."""
        active = [s for s in self.steps if s.get("enabled", True)]
        if not any(s.get("type") == "section" for s in active):
            return []
        if not any(s.get("on_timeout") == "next_section" for s in active):
            return ["This sequence has sections, but no step is set to "
                    f"'{step_defs.ON_TIMEOUT_LABELS['next_section']}' - so the "
                    "first section will repeat forever and the others will "
                    "never run."]
        return []

    def problems(self) -> list[str]:
        active = [s for s in self.steps if s.get("enabled", True)]
        if not active:
            return ["The sequence has no enabled steps."]
        found: list[str] = []
        for index, step in enumerate(self.steps):
            if step.get("enabled", True):
                found.extend(step_defs.validate(
                    step, step_defs.location(self.steps, index)))
        return found


class Engine:
    """Executes a Sequence repeatedly until stopped."""

    def __init__(
        self,
        sequence: Sequence,
        emit: Callable[[dict[str, Any]], None] | None = None,
        dry_run: bool = False,
        base_dir: Path | None = None,
    ) -> None:
        self.sequence = sequence
        self.emit = emit or (lambda event: None)
        self.dry_run = dry_run
        self.base_dir = base_dir or PROJECT_DIR
        self.stop_event = threading.Event()
        self.last_match: tuple[int, int] | None = None
        self._templates: dict[str, Any] = {}
        self.cycles_completed = 0
        # Set from the divider of whichever section is running: a ceiling on
        # how long any step inside it may wait. None means each step decides.
        self.wait_limit: float | None = None
        # How many patches the last color search turned up, so the log
        # can say which of them was chosen.
        self.last_candidates = 0

    # -- plumbing --------------------------------------------------------

    def log(self, message: str, level: str = "info") -> None:
        self.emit({"kind": "log", "level": level, "message": message})

    def stop(self) -> None:
        self.stop_event.set()

    def _guard(self) -> None:
        """Raise Aborted if anything says we should stop."""
        if self.stop_event.is_set():
            raise Aborted("stop requested")
        if screen.key_pressed(self.sequence.settings.abort_key):
            raise Aborted(f"{self.sequence.settings.abort_key} pressed")
        if self.sequence.settings.failsafe_corner:
            x, y = mouse.position()
            left, top, _, _ = screen.virtual_bounds()
            if x <= left + FAILSAFE_CORNER and y <= top + FAILSAFE_CORNER:
                raise Aborted("mouse in the top-left corner")

    def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            self._guard()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(GUARD_INTERVAL, remaining))

    def _template(self, relative: str):
        """Load and cache a template image."""
        if relative not in self._templates:
            path = Path(relative)
            if not path.is_absolute():
                path = self.base_dir / path
            self._templates[relative] = screen.load_template(path)
        return self._templates[relative]

    @staticmethod
    def _region(value: Any) -> tuple[int, int, int, int] | None:
        return tuple(value) if value else None  # type: ignore[return-value]

    def _click(self, x: int, y: int, step: dict[str, Any], what: str) -> None:
        clicks = int(self._value(step, "clicks", 1) or 1)
        button = self._value(step, "button", "left")
        suffix = "  [dry run]" if self.dry_run else ""
        verb = "double-click" if clicks == 2 else f"{clicks}x click" if clicks > 1 else "click"
        self.log(f"    {verb} {what} at {x}, {y}{suffix}")
        if not self.dry_run:
            mouse.click(x, y, button=button, clicks=clicks)

    # -- step handlers ---------------------------------------------------

    @staticmethod
    def _value(step: dict[str, Any], key: str, fallback: Any) -> Any:
        """What the step says, or what its type declares as the default.

        The GUI writes every key, but a hand-edited file can be missing one,
        and the engine used to carry its own fallbacks -- which had already
        drifted: it read a missing 'match' as rgb while the editor showed hue.
        Asking the step definition means there is only one answer.
        """
        if step.get(key) is not None:
            return step[key]
        step_type = step_defs.STEP_TYPES.get(step.get("type", ""))
        spec = step_type.field_map().get(key) if step_type else None
        if spec is not None and spec.default is not None:
            return spec.default
        return fallback

    def _timeout(self, step: dict[str, Any]) -> float:
        """How long this step may wait, honoring its section's ceiling.

        The number itself comes from the step, or failing that from the
        default its type declares -- never from a second copy kept here,
        which is how two sources drift apart.

        The section limit is a cap rather than a replacement: a step that
        already gives up sooner keeps its own time. A step set to wait forever
        (0) is the one this exists for, so the cap wins there outright.
        """
        own = float(self._value(step, "timeout", 30.0))
        if self.wait_limit is None:
            return own
        return self.wait_limit if own <= 0 else min(own, self.wait_limit)

    def _gave_up(self, waited: float) -> str:
        """Why a wait ended, for the log. Names the setting that decided it."""
        if waited <= 0:
            return "(waiting forever, so this should not happen)"
        capped = " - this section's cap" if self.wait_limit == waited else ""
        return f"after {waited:g}s{capped}"

    def _poll_until(self, check: Callable[[], Any], timeout: float, what: str) -> Any:
        """Call `check` until it returns something, or the timeout runs out.

        A timeout of 0 (or less) means wait indefinitely -- Pixie idles here
        until the thing turns up, however long that takes, which is what you
        want when a step simply cannot proceed without it.
        """
        deadline = time.monotonic() + timeout if timeout > 0 else math.inf
        started = time.monotonic()
        announced = started

        while True:
            self._guard()
            found = check()
            if found is not None and found is not False:
                waited = time.monotonic() - started
                if waited >= IDLE_NOTICE_SECONDS:
                    self.log(f"    ...there after {waited:.0f}s")
                return found

            now = time.monotonic()
            if now >= deadline:
                return None
            if now - announced >= IDLE_NOTICE_SECONDS:
                announced = now
                # Say how long this will go on for. A step quietly sitting on
                # its 30 second default looks like Pixie has hung.
                left = ("waiting as long as it takes" if timeout <= 0
                        else f"gives up in {deadline - now:.0f}s")
                self.log(f"    still waiting for {what}, {now - started:.0f}s so "
                         f"far ({left})", "muted")
            time.sleep(min(GUARD_INTERVAL, self.sequence.settings.poll_interval))

    def _find(self, step: dict[str, Any], timeout: float) -> screen.Match | None:
        """Wait for the step's image to appear."""
        template = self._template(step["image"])
        region = self._region(step.get("region"))
        confidence = float(self._value(step, "confidence", 0.85))
        name = Path(step["image"]).name
        return self._poll_until(
            lambda: screen.find_template(template, region, confidence), timeout, name)

    def _do_wait_for_color(self, step: dict[str, Any]) -> str:
        x, y = step["pos"]
        target = tuple(step["color"])
        found = self._poll_until(
            lambda: screen.color_present(
                x, y, target,
                float(self._value(step, "tolerance", 30)),
                int(self._value(step, "radius", 3)),
                self._value(step, "mode", "any"),
            ) or None,
            self._timeout(step),
            f"RGB{target} at {x}, {y}",
        )
        if found is None:
            self.log(f"    color RGB{target} not seen at {x}, {y} "
                     f"(saw RGB{screen.pixel_color(x, y)}) "
                     f"{self._gave_up(self._timeout(step))}", "warn")
            return "timeout"
        self.last_match = (x, y)
        self.log(f"    color RGB{target} present at {x}, {y}")
        return "ok"

    def _look_for_color(self, step: dict[str, Any],
                        region: tuple[int, int, int, int]) -> screen.ColorHit | None:
        """One search for the step's color, however it's configured to match."""
        hits = screen.find_colors(
            region,
            tuple(step["color"]),
            float(self._value(step, "tolerance", 50)),
            int(self._value(step, "min_pixels", 40)),
            match=self._value(step, "match", "hue"),
            min_saturation=int(self._value(step, "min_saturation", 90)),
            min_brightness=int(self._value(step, "min_brightness", 70)),
            order=self._value(step, "pick", "largest"),
        )
        # Keep the count for the log: "1 of 3" is the difference between
        # picking the right card and picking one at random.
        self.last_candidates = len(hits)
        return hits[0] if hits else None

    def _which_one(self, step: dict[str, Any]) -> str:
        """', 1 of 4 - the one furthest left' when there was a choice to make."""
        if self.last_candidates <= 1:
            return ""
        order = self._value(step, "pick", "largest")
        return (f" - {self.last_candidates} patches matched, took "
                f"{step_defs.PICK_LABELS.get(order, order)}")

    @staticmethod
    def _color_description(step: dict[str, Any]) -> str:
        target = tuple(step["color"])
        how = "hue of " if Engine._value(step, "match", "hue") == "hue" else ""
        return f"{how}RGB{target} in that area"

    def _do_click_color_if_present(self, step: dict[str, Any]) -> str:
        region = self._region(step.get("region"))
        if region is None:
            self.log("    no area set to search in", "error")
            return "ok"  # optional step: don't derail the run

        hit = self._poll_until(
            lambda: self._look_for_color(step, region),
            self._timeout(step),
            self._color_description(step),
        )
        if hit is None:
            self.last_match = None
            self.log(f"    no {self._color_description(step)} "
                     f"{self._gave_up(self._timeout(step))}, skipping")
            return "ok"

        self.last_match = hit.center
        off_x, off_y = step.get("offset") or (0, 0)
        self.log(f"    found it - {hit.pixels} pixels in a "
                 f"{hit.width}x{hit.height} box{self._which_one(step)}")
        self._click(hit.x + off_x, hit.y + off_y, step, "the color")
        return "ok"

    def _do_wait_for_color_in_area(self, step: dict[str, Any]) -> str:
        region = self._region(step.get("region"))
        if region is None:
            self.log("    no area set to search in", "error")
            return "timeout"
        hit = self._poll_until(
            lambda: self._look_for_color(step, region),
            self._timeout(step),
            self._color_description(step),
        )
        target = tuple(step["color"])
        min_pixels = int(self._value(step, "min_pixels", 40))
        if hit is None:
            # Don't leave a stale position behind for a later "click the last
            # thing found" to pick up and click somewhere wrong.
            self.last_match = None
            self.log(f"    no patch of RGB{target} at least {min_pixels}px "
                     f"in that area {self._gave_up(self._timeout(step))}",
                     "warn")
            return "timeout"
        self.last_match = hit.center
        self.log(f"    found RGB{target} - {hit.pixels} pixels in a "
                 f"{hit.width}x{hit.height} box, center {hit.x}, {hit.y}"
                 f"{self._which_one(step)}")
        return "ok"

    def _do_wait_for_image(self, step: dict[str, Any]) -> str:
        waited = self._timeout(step)
        match = self._find(step, waited)
        if match is None:
            self.last_match = None
            self.log(f"    {Path(step['image']).name} did not appear "
                     f"{self._gave_up(waited)}", "warn")
            return "timeout"
        self.last_match = match.center
        self.log(f"    found {Path(step['image']).name} at {match.x}, {match.y} "
                 f"(score {match.score:.3f})")
        return "ok"

    def _do_click_image(self, step: dict[str, Any]) -> str:
        waited = self._timeout(step)
        match = self._find(step, waited)
        if match is None:
            self.last_match = None
            self.log(f"    {Path(step['image']).name} did not appear "
                     f"{self._gave_up(waited)}", "warn")
            return "timeout"
        self.last_match = match.center
        self.log(f"    found {Path(step['image']).name} at {match.x}, {match.y} "
                 f"(score {match.score:.3f})")
        off_x, off_y = step.get("offset") or (0, 0)
        cx, cy = match.center
        self._click(cx + off_x, cy + off_y, step, Path(step["image"]).name)
        return "ok"

    def _do_click_image_if_present(self, step: dict[str, Any]) -> str:
        match = self._find(step, self._timeout(step))
        if match is None:
            self.last_match = None
            self.log(f"    {Path(step['image']).name} not there "
                     f"{self._gave_up(self._timeout(step))}, skipping")
            return "ok"
        self.last_match = match.center
        off_x, off_y = step.get("offset") or (0, 0)
        cx, cy = match.center
        self._click(cx + off_x, cy + off_y, step, Path(step["image"]).name)
        return "ok"

    def _do_click_point(self, step: dict[str, Any]) -> str:
        x, y = step["pos"]
        self.last_match = (x, y)
        self._click(x, y, step, "fixed point")
        return "ok"

    def _do_click_box(self, step: dict[str, Any]) -> str:
        box = self._region(step.get("box"))
        if box is None:
            self.log("    no box set to click in", "error")
            return "timeout"
        left, top, width, height = box
        # A fresh spot every time, so the clicks don't all land on one pixel.
        x = random.randint(left, left + max(0, int(width) - 1))
        y = random.randint(top, top + max(0, int(height) - 1))
        self.last_match = (x, y)
        self._click(x, y, step, f"somewhere in the {width}x{height} box")
        return "ok"

    def _do_click_last_match(self, step: dict[str, Any]) -> str:
        if self.last_match is None:
            self.log("    the step before this one found nothing, so there is "
                     "nothing to click", "error")
            return "timeout"
        off_x, off_y = step.get("offset") or (0, 0)
        x, y = self.last_match
        self._click(x + off_x, y + off_y, step, "last match")
        return "ok"

    def _do_press_key(self, step: dict[str, Any]) -> str:
        try:
            key = keyboard.normalize(step.get("key", ""))
        except ValueError as error:
            self.log(f"    {error}", "error")
            return "timeout"

        presses = int(self._value(step, "presses", 1) or 1)
        suffix = "  [dry run]" if self.dry_run else ""
        times = f" x{presses}" if presses > 1 else ""
        self.log(f"    press {key}{times}{suffix}")
        if not self.dry_run:
            keyboard.press(key, presses, float(step.get("interval", 0.08)))
        return "ok"

    # Markers. run_cycle skips these outright; these exist so that every
    # declared step type has a handler, and so nothing breaks if one is ever
    # reached by another route.
    def _do_section(self, _step: dict[str, Any]) -> str:
        return "ok"

    def _do_note(self, _step: dict[str, Any]) -> str:
        return "ok"

    def _do_wait(self, step: dict[str, Any]) -> str:
        low = float(step.get("seconds", 1.0))
        high = float(step.get("seconds_max", low) or low)
        pause = _between(low, high)
        self.log(f"    waiting {pause:.2f}s")
        self._sleep(pause)
        return "ok"


    def _pause_after(self, step: dict[str, Any]) -> float:
        """This step's own pause if it has one, otherwise the sequence default."""
        custom = step.get("pause")
        if custom:
            return _between(custom[0], custom[1])
        return self.sequence.settings.step_pause()

    def _park_target(self) -> tuple[int, int] | None:
        mode = self.sequence.settings.park_mouse
        if mode == "center":
            return screen.primary_center()
        if mode == "custom" and self.sequence.settings.park_point:
            x, y = self.sequence.settings.park_point
            return int(x), int(y)
        return None

    def _park_mouse(self) -> None:
        """Move the cursor out of the way so it can't sit over the next target."""
        target = self._park_target()
        if target is None or self.dry_run:
            return
        mouse.move_to(*target)

    # -- the loop --------------------------------------------------------

    def run_step(self, step: dict[str, Any]) -> str:
        handler = getattr(self, f"_do_{step['type']}", None)
        if handler is None:
            self.log(f"    unknown step type {step['type']!r}, skipping", "error")
            return "ok"
        return handler(step)

    def sections(self) -> list[tuple[int, int, str]]:
        """Split the step list into sections: (first, last_exclusive, name).

        A "Section divider" step starts a new one. Anything before the first
        divider forms a leading section, and a sequence with no dividers at all
        is simply one section covering everything -- which behaves exactly as
        it did before sections existed.
        """
        steps = self.sequence.steps
        starts = [i for i, s in enumerate(steps) if s.get("type") == "section"]
        if not starts:
            return [(0, len(steps), self.sequence.name)]

        bounds: list[tuple[int, int, str]] = []
        if starts[0] > 0:
            bounds.append((0, starts[0], "before the first section"))
        for n, start in enumerate(starts):
            end = starts[n + 1] if n + 1 < len(starts) else len(steps)
            bounds.append((start, end, steps[start].get("name") or "Untitled section"))
        return bounds

    def _section_of(self, index: int) -> int:
        for n, (start, end, _) in enumerate(self.sections()):
            if start <= index < end:
                return n
        return 0

    def _divider(self, section: tuple[int, int, str]) -> dict[str, Any]:
        """The divider step that owns a section, or {} for a leading one."""
        start = section[0]
        step = self.sequence.steps[start] if start < len(self.sequence.steps) else {}
        return step if step.get("type") == "section" else {}

    def _enter_section(self, section: tuple[int, int, str]) -> None:
        """Pick up the settings the section's divider carries."""
        limit = self._divider(section).get("wait_limit")
        self.wait_limit = float(limit) if limit else None

    def _section_pause(self, section: tuple[int, int, str]) -> float:
        """This section's own pause if its divider sets one, else the default."""
        own = self._divider(section).get("pause")
        if own:
            return _between(own[0], own[1])
        return self.sequence.settings.section_pause()

    def run_cycle(self) -> str:
        """Run sections until one wraps back to the top.

        Walks the list by index rather than looping over it, because a step can
        send us somewhere other than the next one: back to the top of its own
        section, on to the next section, or back to the very beginning.

        Returns 'ok' (a full trip through every section), or 'stop'.
        """
        sections = self.sections()
        # With no dividers at all there is nothing to repeat internally: one
        # pass through the list is one cycle, exactly as it always was.
        sectioned = any(s.get("type") == "section" for s in self.sequence.steps)
        # The numbers the GUI shows, so the log and the list agree.
        numbers = step_defs.display_numbers(self.sequence.steps)
        current = 0
        index = sections[0][0]
        self._enter_section(sections[current])
        self._announce_section(sections[current])

        while True:
            start, end, name = sections[current]

            if index >= end:
                if not sectioned:
                    return "ok"
                # Fell off the end of the section: run it again from its top.
                self.log(f"  -- repeating section '{name}'", "muted")
                index = start
                self._sleep(self._section_pause(sections[current]))
                continue

            step = self.sequence.steps[index]
            if not step.get("enabled", True) or step.get("type") in step_defs.MARKERS:
                index += 1
                continue

            self._guard()
            self.emit({"kind": "step", "index": index, "step": step})
            self.log(f"  {numbers[index]}. {step.get('name') or step['type']}")

            outcome = self.run_step(step)
            if outcome == "ok":
                self._park_mouse()
                # Most applications need a moment to react before the next step
                # looks at the screen or types into it.
                self._sleep(self._pause_after(step))
                index += 1
                continue

            on_timeout = self._value(step, "on_timeout", "restart")
            if on_timeout not in step_defs.ON_TIMEOUT:
                # Never from the GUI, but a hand-edited file can say anything,
                # and silently picking a branch would be worse than saying so.
                self.log(f"    '{on_timeout}' is not something I know how to do "
                         "when a step fails - starting the sequence over "
                         "instead", "error")
                on_timeout = "restart"

            if on_timeout == "stop":
                self.log("    giving up: this step is set to stop the run", "error")
                return "stop"
            if on_timeout == "continue":
                self.log("    skipping it, carrying on down this section", "warn")
                index += 1
                continue
            if on_timeout == "restart":
                self.log("    back to the very first step of the sequence", "warn")
                return "restart"
            if on_timeout == "restart_section":
                self.log(f"    back to the first step of '{name}'", "warn")
                index = start
                self._sleep(self._section_pause(sections[current]))
                continue
            if on_timeout == "next_section":
                current += 1
                if current >= len(sections):
                    self.log("    that was the last section - back to the top",
                             "warn")
                    return "ok"
                self.log(f"    moving on from '{name}'", "warn")
                self._sleep(self._section_pause(sections[current - 1]))
                index = sections[current][0]
                self._enter_section(sections[current])
                self._announce_section(sections[current])
                continue

            # Unreachable: the branches above cover every value in
            # step_defs.ON_TIMEOUT, and check_wiring.py proves it by reading
            # them back out of this method.
            raise AssertionError(f"no branch for on_timeout {on_timeout!r}")

    def _announce_section(self, section: tuple[int, int, str]) -> None:
        if len(self.sections()) <= 1:
            return
        start, _end, name = section
        capped = (f"  (nothing here waits longer than {self.wait_limit:g}s)"
                  if self.wait_limit else "")
        self.log(f"  === {name} ==={capped}")
        # The divider's own row, so the GUI can light it up. A sequence whose
        # first steps come before any divider has no row to point at.
        divider = start if self.sequence.steps[start].get("type") == "section" else None
        self.emit({"kind": "section", "name": name, "index": divider})

    def run(self, max_cycles: int | None = None) -> None:
        problems = self.sequence.problems()
        if problems:
            for problem in problems:
                self.log(problem, "error")
            self.emit({"kind": "finished", "reason": "the sequence is not ready to run"})
            return

        settings = self.sequence.settings
        stop_keys = [key for key in (settings.toggle_key, settings.abort_key)
                     if key and key.lower() not in ("off", "none")]
        self.emit({"kind": "started"})
        self.log(f"Running '{self.sequence.name}'. "
                 f"Press {' or '.join(dict.fromkeys(stop_keys))} to stop.")
        for warning in self.sequence.warnings():
            self.log(warning, "warn")
        if self.dry_run:
            self.log("DRY RUN - detecting and logging only, nothing will be clicked.", "warn")
        parked = self._park_target()
        if parked:
            self.log(f"Cursor returns to {parked[0]}, {parked[1]} after each step."
                     + ("  [not in dry run]" if self.dry_run else ""), "muted")

        reason = "stopped"
        try:
            # Count attempts, not completed cycles. A sequence whose first
            # step keeps failing with "start over" completes nothing, and
            # counting only completions meant --max-cycles never arrived and
            # an unattended run went round forever.
            attempts = 0
            while max_cycles is None or attempts < max_cycles:
                attempts += 1
                self._guard()
                self.log(f"Cycle {attempts}")
                outcome = self.run_cycle()
                if outcome == "stop":
                    reason = "a step asked to stop"
                    break
                if outcome == "ok":
                    self.cycles_completed += 1
                    self.emit({"kind": "cycle", "completed": self.cycles_completed})
                self.last_match = None
                self._sleep(self.sequence.settings.cycle_pause())
            else:
                reason = f"finished {max_cycles} cycle(s)"
                if self.cycles_completed < max_cycles:
                    reason += (f", {self.cycles_completed} of which got all the "
                               "way through")
        except Aborted as stop:
            reason = str(stop)
        except FileNotFoundError as missing:
            self.log(str(missing), "error")
            reason = "an image file is missing"
        except Exception as error:  # noqa: BLE001 - surface it rather than dying silently
            self.log(f"Unexpected error: {error!r}", "error")
            reason = "an unexpected error"

        self.log(f"Stopped after {self.cycles_completed} cycle(s): {reason}")
        self.emit({"kind": "finished", "reason": reason})
