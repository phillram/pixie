"""Smoke test that doesn't need the target application.

Crops a chunk of the real screen, treats it as a reference image, then checks
that the matcher finds it back at exactly the right coordinates, that color
sampling works, and that the engine runs a whole sequence end to end in dry-run
mode.

    python selftest.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

import engine as engine_mod
import screen
import steps as step_defs

PROJECT_DIR = Path(__file__).resolve().parent
CROP = (300, 300, 120, 60)  # x, y, w, h -- an arbitrary but non-flat patch


def main() -> int:
    screen.set_dpi_aware()
    failures: list[str] = []

    left, top, width, height = screen.virtual_bounds()
    print(f"Virtual desktop : {width}x{height} at {left},{top}")

    frame = screen.grab()
    if (frame.shape[1], frame.shape[0]) != (width, height):
        failures.append(
            f"grab() returned {frame.shape[1]}x{frame.shape[0]}, expected {width}x{height}")

    failures.extend(_check_step_definitions())

    with tempfile.TemporaryDirectory() as tmp:
        tpl_path = Path(tmp) / "template.png"
        x, y, w, h = _distinctive_crop(frame)
        cv2.imwrite(str(tpl_path), frame[y : y + h, x : x + w])

        # Random noise: something guaranteed not to be anywhere on screen, so
        # the "if it appears" step has a real absence to cope with.
        absent_path = Path(tmp) / "absent.png"
        cv2.imwrite(str(absent_path),
                    np.random.randint(0, 256, (40, 40, 3), dtype=np.uint8))

        # Match against the *same* frame we cropped from. Re-grabbing would
        # race the live desktop: a cursor blink or an animation between the two
        # captures can shift the best match by a pixel or two, which says
        # nothing about whether the matcher works.
        original_grab = screen.grab
        screen.grab = lambda _region=None: frame
        try:
            started = time.perf_counter()
            match = screen.find_template(screen.load_template(tpl_path), confidence=0.85)
            elapsed = (time.perf_counter() - started) * 1000
        finally:
            screen.grab = original_grab

        expected = (x + left, y + top)
        if match is None:
            failures.append("template matching found nothing")
            print("Template match  : FAILED (no match)")
        else:
            print(f"Template match  : ({match.x}, {match.y}) score {match.score:.4f}"
                  f"  ({elapsed:.0f} ms)")
            if (match.x, match.y) != expected:
                failures.append(f"matched at {(match.x, match.y)}, expected {expected}")

            cx, cy = match.center
            color = screen.pixel_color(cx, cy)
            print(f"Color sampling : RGB{color} at {cx},{cy}")
            if not screen.color_present(cx, cy, color, tolerance=0, radius=0):
                failures.append("exact color match failed")
            if screen.color_present(cx, cy, tuple(255 - v for v in color), 5, 0):
                failures.append("inverse color matched when it should not have")

            failures.extend(_check_engine(tpl_path, absent_path, color, (cx, cy)))

    failures.extend(_check_color_search())
    failures.extend(_check_hue_matching())
    failures.extend(_check_sections())
    failures.extend(_check_keyboard())
    failures.extend(_check_mouse())

    try:
        screen.key_pressed("F8")
        print("Abort key       : readable")
    except Exception as error:  # noqa: BLE001 - reporting, not handling
        failures.append(f"key_pressed failed: {error}")

    print()
    if failures:
        print(f"FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


def _check_sections() -> list[str]:
    """Each section must repeat until its start point fails, then hand over."""
    budget = {"A": 3, "B": 2, "C": 1}
    calls = {key: 0 for key in budget}

    class Counting(engine_mod.Engine):
        def run_step(self, step):
            tag = step.get("tag")
            if not tag:
                return "ok"
            calls[tag] += 1
            return "ok" if calls[tag] <= budget[tag] else "timeout"

    def divider(name):
        return {"type": "section", "name": name, "enabled": True}

    def start(tag):
        return {"type": "wait_for_image", "name": f"find {tag}", "enabled": True,
                "tag": tag, "image": "x", "on_timeout": "next_section",
                "pause": [0, 0]}

    def work(tag):
        return {"type": "press_key", "name": f"work {tag}", "enabled": True,
                "key": "Q", "pause": [0, 0]}

    sequence = engine_mod.Sequence(
        name="sections",
        steps=[divider("A"), start("A"), work("A"),
               {"type": "note", "text": "does nothing", "enabled": True},
               divider("B"), start("B"), work("B"),
               divider("C"), start("C"), work("C")],
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False),
    )

    runner = Counting(sequence, dry_run=True)
    names = [name for _, _, name in runner.sections()]
    runner.run(max_cycles=1)

    # Each start point runs until it fails once: budget + 1 calls.
    expected = {tag: limit + 1 for tag, limit in budget.items()}
    print(f"Sections        : {names} -> start-point calls {calls}")

    problems = []
    if names != ["A", "B", "C"]:
        problems.append(f"sections parsed as {names}, expected ['A', 'B', 'C']")
    if calls != expected:
        problems.append(f"start points called {calls}, expected {expected}")
    if runner.cycles_completed != 1:
        problems.append(f"completed {runner.cycles_completed} cycles, expected 1")

    # A sectioned sequence with no way out should be flagged, not silently hung.
    stuck = engine_mod.Sequence(name="stuck", steps=[divider("A"), work("A")])
    if not stuck.warnings():
        problems.append("a section with no 'next section' exit was not flagged")

    # And no dividers at all must behave exactly as it always did.
    plain = engine_mod.Sequence(
        name="plain", steps=[work("A"), work("A")],
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))
    plain_runner = engine_mod.Engine(plain, dry_run=True)
    plain_runner.run(max_cycles=2)
    if plain_runner.cycles_completed != 2:
        problems.append("a sequence with no sections no longer completes cycles")
    return problems


def _check_hue_matching() -> list[str]:
    """Hue matching must survive a brightness gradient that defeats RGB.

    Builds a cyan glow that fades from near-white at its core to nearly black
    at its edge -- which is what a real glow looks like -- and checks hue mode
    catches far more of it than a distance match on one sampled color.
    """
    import screen as screen_mod

    height, width = 200, 300
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    # A horizontal band of cyan running from very dark to washed-out white.
    for x in range(40, 260):
        fraction = (x - 40) / 219
        value = int(30 + fraction * 225)
        whiteness = int(fraction * 170)
        frame[80:120, x] = (value, value, whiteness)  # BGR: cyan-ish

    sampled = tuple(int(v) for v in frame[100, 150][::-1])  # mid-gradient, as RGB

    original_grab = screen_mod.grab
    try:
        screen_mod.grab = lambda _region=None: frame
        rgb_hit = screen_mod.find_color((0, 0, width, height), sampled,
                                        tolerance=50, min_pixels=10, match="rgb")
        hue_hit = screen_mod.find_color((0, 0, width, height), sampled,
                                        tolerance=14, min_pixels=10, match="hue",
                                        min_saturation=60, min_brightness=50)
    finally:
        screen_mod.grab = original_grab

    rgb_pixels = rgb_hit.pixels if rgb_hit else 0
    hue_pixels = hue_hit.pixels if hue_hit else 0
    print(f"Hue vs RGB      : sampled RGB{sampled} on a fading glow -> "
          f"rgb match {rgb_pixels} px, hue match {hue_pixels} px")

    problems = []
    if hue_hit is None:
        problems.append("hue matching found nothing on a plain color gradient")
    elif hue_pixels <= rgb_pixels:
        problems.append(f"hue matched {hue_pixels}px, no better than rgb's {rgb_pixels}px")
    return problems


def _check_keyboard() -> list[str]:
    """Send real key presses to our own window and check they arrive.

    Guarded: if our test window doesn't actually hold focus we skip rather than
    fire stray keystrokes into whatever else is on screen.
    """
    import ctypes
    import tkinter as tk

    import keyboard as kb

    received: list[str] = []
    root = tk.Tk()
    root.title("Pixie key test")
    root.geometry("260x90+60+60")
    root.bind("<Key>", lambda event: received.append(event.keysym))
    root.focus_force()
    root.update()
    time.sleep(0.4)
    root.update()

    foreground = ctypes.windll.user32.GetForegroundWindow()
    ours = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
    if foreground != ours:
        root.destroy()
        print("Key sending    : SKIPPED (test window could not take focus)")
        return []

    kb.press("Q", presses=2, interval=0.06)
    kb.press("Enter")

    deadline = time.time() + 3.0
    while time.time() < deadline and len(received) < 3:
        root.update()
        time.sleep(0.02)
    root.destroy()

    got = [k.lower() for k in received]
    print(f"Key sending    : received {received}")
    problems = []
    if got.count("q") < 2:
        problems.append(f"expected two 'q' presses, got {received}")
    if "return" not in got and "kp_enter" not in got:
        problems.append(f"expected Enter, got {received}")
    return problems


def _check_mouse() -> list[str]:
    """Send a real double-click to our own window and check it lands."""
    import ctypes
    import tkinter as tk

    import mouse as ms

    events: list[str] = []
    root = tk.Tk()
    root.title("Pixie click test")
    root.geometry("260x140+70+70")
    root.bind("<Button-1>", lambda _e: events.append("click"))
    root.bind("<Double-Button-1>", lambda _e: events.append("double"))
    root.focus_force()
    root.update()
    time.sleep(0.4)
    root.update()

    foreground = ctypes.windll.user32.GetForegroundWindow()
    ours = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
    if foreground != ours:
        root.destroy()
        print("Mouse clicking : SKIPPED (test window could not take focus)")
        return []

    restore_to = ms.position()
    target = (root.winfo_rootx() + 130, root.winfo_rooty() + 70)
    ms.double_click(*target)

    deadline = time.time() + 3.0
    while time.time() < deadline and "double" not in events:
        root.update()
        time.sleep(0.02)
    root.destroy()
    ms.move_to(*restore_to)  # put the pointer back where it was

    print(f"Mouse clicking : {events.count('click')} clicks, "
          f"{events.count('double')} double at {target}")
    if "double" not in events:
        return [f"double-click did not register (got {events})"]
    return []


def _distinctive_crop(frame: np.ndarray) -> tuple[int, int, int, int]:
    """Pick a patch of screen busy enough to have exactly one match.

    A crop of flat background matches equally well in a thousand places, so
    asserting *where* it was found would be a coin toss. Take the highest
    contrast candidate instead, which makes this test about the matcher rather
    than about what happens to be on the desktop.
    """
    height, width = frame.shape[:2]
    w, h = CROP[2], CROP[3]
    best, best_score = (300, 300, w, h), -1.0
    for y in range(80, min(height - h, 1400), 190):
        for x in range(80, min(width - w, 2000), 230):
            patch = frame[y : y + h, x : x + w]
            score = float(patch.std())
            if score > best_score:
                best, best_score = (x, y, w, h), score
    return best


def _check_color_search() -> list[str]:
    """A glowing outline must be found by its glow, whatever is inside it.

    Uses the real find_color code path against synthetic frames rather than
    the live screen, so the result doesn't depend on what is on the desktop.
    """
    import screen as screen_mod

    glow = (255, 215, 0)
    outline = (120, 60, 200, 140)  # left, top, width, height within the frame
    problems = []
    centers = []

    original_grab = screen_mod.grab
    try:
        for fill in ((30, 30, 30), (200, 40, 40), (10, 180, 90)):
            frame = np.zeros((400, 600, 3), dtype=np.uint8)
            left, top, width, height = outline
            # Completely different picture inside the glowing border each time.
            frame[top + 6 : top + height - 6, left + 6 : left + width - 6] = fill[::-1]
            cv2.rectangle(frame, (left, top), (left + width, top + height),
                          glow[::-1], thickness=5)

            screen_mod.grab = lambda _region=None, _f=frame: _f
            hit = screen_mod.find_color((0, 0, 600, 400), glow,
                                         tolerance=50, min_pixels=40)
            if hit is None:
                problems.append(f"glow not found with interior {fill}")
                continue
            centers.append((hit.x, hit.y))

        # And it must NOT fire on a frame with no glow at all.
        blank = np.full((400, 600, 3), 40, dtype=np.uint8)
        screen_mod.grab = lambda _region=None, _f=blank: _f
        if screen_mod.find_color((0, 0, 600, 400), glow, 50, 40) is not None:
            problems.append("glow reported on a frame that has none")
    finally:
        screen_mod.grab = original_grab

    expected = (outline[0] + outline[2] // 2, outline[1] + outline[3] // 2)
    if centers and len(set(centers)) != 1:
        problems.append(f"glow center moved with the interior: {centers}")
    elif centers and abs(centers[0][0] - expected[0]) > 4:
        problems.append(f"glow center {centers[0]} is not near {expected}")

    print(f"Glow detection  : center {centers[0] if centers else '-'} across "
          f"{len(centers)} different interiors" if not problems
          else "Glow detection  : PROBLEMS")
    return problems


def _check_step_definitions() -> list[str]:
    """Every declared step type must have a handler and buildable defaults."""
    problems = []
    for key, step_type in step_defs.STEP_TYPES.items():
        if not hasattr(engine_mod.Engine, f"_do_{key}"):
            problems.append(f"step type {key!r} has no handler in the engine")
        step = step_defs.new_step(key)
        if not step_defs.describe(step):
            problems.append(f"step type {key!r} produced an empty description")
        for spec in step_type.fields:
            if spec.key not in step:
                problems.append(f"step type {key!r} is missing a default for {spec.key!r}")
    print(f"Step types      : {len(step_defs.STEP_TYPES)} defined, all wired up"
          if not problems else "Step types      : PROBLEMS")
    return problems


def _check_engine(template: Path, absent: Path, color: tuple[int, int, int],
                  point: tuple[int, int]) -> list[str]:
    """Run a real multi-step sequence through the engine in dry-run mode."""
    messages: list[str] = []
    sequence = engine_mod.Sequence(
        name="selftest",
        steps=[
            {"type": "wait_for_color", "name": "Wait for the color", "enabled": True,
             "pos": list(point), "color": list(color), "tolerance": 20, "radius": 3,
             "mode": "any", "timeout": 2.0, "on_timeout": "stop"},
            {"type": "click_last_match", "name": "Double-click it", "enabled": True,
             "clicks": 2, "button": "left", "offset": [0, 0]},
            {"type": "click_image", "name": "Click the image", "enabled": True,
             "image": str(template), "region": None, "confidence": 0.85,
             "timeout": 5.0, "on_timeout": "stop", "clicks": 1, "button": "left",
             "offset": [0, 0]},
            {"type": "click_image_if_present", "name": "Optional popup", "enabled": True,
             "image": str(absent), "region": None, "confidence": 0.85,
             "timeout": 0.3, "clicks": 1, "button": "left", "offset": [0, 0]},
            {"type": "click_point", "name": "Click a button", "enabled": True,
             "pos": [123, 456], "clicks": 1, "button": "left"},
            {"type": "wait", "name": "Settle", "enabled": True, "seconds": 0.1},
        ],
        settings=engine_mod.Settings(cycle_pause_min=0.1, cycle_pause_max=0.1,
                                     step_pause_min=0.0, step_pause_max=0.0,
                                     poll_interval=0.1),
    )

    problems = sequence.problems()
    if problems:
        return [f"valid sequence reported as broken: {problems}"]

    runner = engine_mod.Engine(sequence, emit=lambda e: messages.append(e), dry_run=True)
    print("\n--- engine dry run, 1 cycle, 6 steps ---")
    runner.run(max_cycles=1)
    for event in messages:
        if event.get("kind") == "log":
            print(f"  {event['message']}")
    print("---\n")

    failures = []
    if runner.cycles_completed != 1:
        failures.append(f"engine completed {runner.cycles_completed} cycles, expected 1")
    logged = " ".join(e.get("message", "") for e in messages if e.get("kind") == "log")
    if "double-click" not in logged:
        failures.append("engine did not report a double-click")
    if "123, 456" not in logged:
        failures.append("engine did not report the fixed-point click")
    if "not there, skipping" not in logged:
        failures.append("the optional step did not skip when its image was absent")
    steps_seen = {e["index"] for e in messages if e.get("kind") == "step"}
    if steps_seen != set(range(6)):
        failures.append(f"engine reported steps {sorted(steps_seen)}, expected 0-5")
    return failures


if __name__ == "__main__":
    sys.exit(main())
