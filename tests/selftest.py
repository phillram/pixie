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

import _bootstrap  # noqa: F401  (sys.path)

from pixie.core import engine as engine_mod
from pixie.system import screen
from pixie.core import steps as step_defs

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
    failures.extend(_check_numbering())
    failures.extend(_check_section_pause())
    failures.extend(_check_restart_section())
    failures.extend(_check_max_cycles_is_a_real_limit())
    failures.extend(_check_section_limits())
    failures.extend(_check_pick_order())
    failures.extend(_check_broken_outlines_join_up())
    failures.extend(_check_background_of_the_same_color())
    failures.extend(_check_every_wait_respects_the_cap())
    failures.extend(_check_declared_defaults())
    failures.extend(_check_click_box())
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


def _check_numbering() -> list[str]:
    """Dividers and notes are not steps, so they take no number.

    Numbering the raw list position made the first step of a sectioned
    sequence read as 2, which is what the divider above it had taken.
    """
    steps = [
        {"type": "section", "name": "Before Game"},
        {"type": "wait_for_image", "name": "Look for main menu"},
        {"type": "note", "text": "the menu takes a while"},
        {"type": "click_point", "name": "Click Play"},
        {"type": "section", "name": "In Game"},
        {"type": "press_key", "name": "Play a card"},
    ]
    numbers = step_defs.display_numbers(steps)
    expected = [None, 1, None, 2, None, 1]

    problems = []
    print(f"Numbering       : {numbers}")
    if numbers != expected:
        problems.append(f"numbered {numbers}, expected {expected}")

    where = step_defs.location(steps, 5)
    if where != "Step 1 of 'In Game' (Play a card)":
        problems.append(f"step located as {where!r}")
    if step_defs.location(steps, 1) != "Step 1 of 'Before Game' (Look for main menu)":
        problems.append(f"first step located as {step_defs.location(steps, 1)!r}")

    # No sections at all: plain numbering, no section name to mention.
    plain = [{"type": "press_key", "name": "Q"}, {"type": "wait", "name": "Settle"}]
    if step_defs.display_numbers(plain) != [1, 2]:
        problems.append("an unsectioned sequence stopped numbering from 1")
    if step_defs.location(plain, 1) != "Step 2 (Settle)":
        problems.append(f"unsectioned step located as {step_defs.location(plain, 1)!r}")
    return problems


def _check_section_pause() -> list[str]:
    """Sections can pause differently from steps, including not at all."""
    problems = []
    settings = engine_mod.Settings(step_pause_min=0.4, step_pause_max=0.4,
                                   section_pause_min=0, section_pause_max=0)
    if settings.section_pause() != 0:
        problems.append("a zero section pause did not come out as zero")
    if settings.step_pause() != 0.4:
        problems.append("the step pause changed when the section pause did")

    # A sequence saved before section pauses existed must not suddenly start
    # sprinting between sections: it inherits whatever its cycle pause was.
    old = engine_mod.Settings.from_dict({"cycle_pause_min": 2.0, "cycle_pause_max": 3.0})
    if (old.section_pause_min, old.section_pause_max) != (2.0, 3.0):
        problems.append(f"an old sequence inherited {old.section_pause_min}-"
                        f"{old.section_pause_max}s between sections, expected 2.0-3.0")
    # But a new one starts at zero, so sections run straight on.
    if engine_mod.Settings().section_pause_max != 0.0:
        problems.append("a new sequence defaulted to a pause between sections")

    # And the engine must actually wait it. Three sections, each handing over
    # at once, so the run is section pauses and nothing else.
    waits: list[float] = []

    class Timed(engine_mod.Engine):
        def _sleep(self, seconds):
            waits.append(seconds)

        def run_step(self, step):
            return "timeout"  # every start point fails: hand straight over

    def divider(name):
        return {"type": "section", "name": name, "enabled": True}

    def start():
        return {"type": "wait_for_image", "enabled": True, "image": "x",
                "on_timeout": "next_section"}

    sequence = engine_mod.Sequence(
        name="pauses", steps=[divider("A"), start(), divider("B"), start()],
        settings=engine_mod.Settings(section_pause_min=0.7, section_pause_max=0.7,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))
    Timed(sequence, dry_run=True).run(max_cycles=1)
    print(f"Section pause   : waits {waits} on a two-section handover")
    if 0.7 not in waits:
        problems.append(f"no section pause was waited: {waits}")
    return problems


def _check_restart_section() -> list[str]:
    """'Go back to the first step of this section' must do exactly that.

    The discriminator is the step before the first divider: restarting the
    whole sequence would run it a second time, restarting the section must
    not touch it.
    """
    calls = {"lead": 0, "first": 0, "second": 0, "b": 0}
    messages: list[str] = []

    class Counting(engine_mod.Engine):
        def run_step(self, step):
            tag = step.get("tag")
            if not tag:
                return "ok"
            calls[tag] += 1
            if tag == "lead" or tag == "b":
                return "timeout"                 # hands over immediately
            if tag == "first" and calls["first"] == 3:
                return "timeout"                 # third time around, give up
            if tag == "second" and calls["second"] == 1:
                return "timeout"                 # fails once, restarts section
            return "ok"

    def step(tag, on_timeout):
        return {"type": "wait_for_image", "name": tag, "enabled": True,
                "tag": tag, "image": "x", "on_timeout": on_timeout,
                "pause": [0, 0]}

    sequence = engine_mod.Sequence(
        name="restarts",
        steps=[step("lead", "next_section"),
               {"type": "section", "name": "A", "enabled": True},
               step("first", "next_section"),
               step("second", "restart_section"),
               {"type": "section", "name": "B", "enabled": True},
               step("b", "next_section")],
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     section_pause_min=0, section_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))

    runner = Counting(sequence, emit=lambda e: messages.append(e.get("message", "")),
                      dry_run=True)
    runner.run(max_cycles=1)

    problems = []
    print(f"Restart section : {calls}")
    if calls["lead"] != 1:
        problems.append(f"the step before the first section ran {calls['lead']} "
                        "times - restarting a section restarted the whole "
                        "sequence")
    if calls != {"lead": 1, "first": 3, "second": 2, "b": 1}:
        problems.append(f"steps ran {calls}, expected "
                        "{'lead': 1, 'first': 3, 'second': 2, 'b': 1}")
    if not any("back to the first step of 'A'" in m for m in messages):
        problems.append("the log did not say which section it went back to")

    # And an unknown value must be reported rather than quietly picking one.
    noise = engine_mod.Sequence(
        name="noise", steps=[step("lead", "wibble")],
        settings=engine_mod.Settings(failsafe_corner=False, cycle_pause_min=0,
                                     cycle_pause_max=0))
    said: list[str] = []
    Counting(noise, emit=lambda e: said.append(e.get("message", "")),
             dry_run=True).run(max_cycles=1)
    if not any("wibble" in m and "not something I know" in m for m in said):
        problems.append("an unknown 'if not found' value was accepted silently")
    return problems


def _check_max_cycles_is_a_real_limit() -> list[str]:
    """--max-cycles has to stop a sequence that never completes a cycle.

    A step set to 'start over' returns the run to the top without finishing
    anything. Counting only finished cycles meant the limit was never
    reached, so an unattended run went round forever.
    """
    tries = {"n": 0}

    class Restarting(engine_mod.Engine):
        def run_step(self, step):
            tries["n"] += 1
            return "timeout"          # always fails, always restarts

    sequence = engine_mod.Sequence(
        name="spinner",
        steps=[{"type": "wait_for_image", "name": "never", "enabled": True,
                "image": "x", "on_timeout": "restart", "pause": [0, 0]}],
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))
    runner = Restarting(sequence, dry_run=True)
    runner.run(max_cycles=3)

    problems = []
    print(f"Max cycles      : {tries['n']} attempts, "
          f"{runner.cycles_completed} completed")
    if tries["n"] != 3:
        problems.append(f"asked for 3 cycles, the step ran {tries['n']} times")
    if runner.cycles_completed != 0:
        problems.append(f"counted {runner.cycles_completed} completed cycles, "
                        "but none ever finished")
    return problems


def _check_section_limits() -> list[str]:
    """A section can cap how long the steps inside it wait."""
    def divider(name, **extra):
        return {"type": "section", "name": name, "enabled": True, **extra}

    steps = [
        divider("Capped", wait_limit=3, pause=[0, 0]),
        {"type": "wait_for_image", "name": "thirty", "enabled": True,
         "image": "x", "timeout": 30.0},
        {"type": "wait_for_image", "name": "forever", "enabled": True,
         "image": "x", "timeout": 0.0},
        {"type": "click_image_if_present", "name": "quick", "enabled": True,
         "image": "x", "timeout": 2.0},
        divider("Uncapped"),
        {"type": "wait_for_image", "name": "plain", "enabled": True,
         "image": "x", "timeout": 30.0},
    ]
    runner = engine_mod.Engine(
        engine_mod.Sequence(name="caps", steps=steps,
                            settings=engine_mod.Settings(section_pause_min=5,
                                                         section_pause_max=5)),
        dry_run=True)

    problems = []
    capped, uncapped = runner.sections()

    runner._enter_section(capped)
    waits = {steps[i]["name"]: runner._timeout(steps[i]) for i in (1, 2, 3)}
    print(f"Section cap     : {waits}")
    if waits != {"thirty": 3.0, "forever": 3.0, "quick": 2.0}:
        problems.append(f"the 3s cap produced {waits}")
    if runner._section_pause(capped) != 0.0:
        problems.append("a section's own pause did not override the default")

    runner._enter_section(uncapped)
    if runner._timeout(steps[5]) != 30.0:
        problems.append("the cap leaked into the next section")
    if runner._section_pause(uncapped) != 5.0:
        problems.append("a section without its own pause ignored the default")

    # A step that waits forever must still be able to wait forever when
    # nothing caps it.
    if runner._timeout({"type": "wait_for_image", "timeout": 0.0}) != 0.0:
        problems.append("'wait forever' stopped meaning forever")
    return problems


def _check_pick_order() -> list[str]:
    """A row of glowing cards must be workable left to right, not at random."""
    from pixie.system import screen as screen_mod

    # Three patches of the same cyan, different sizes, left to right. The
    # middle one is the biggest, so "largest" and "leftmost" disagree and the
    # test can tell them apart.
    frame = np.zeros((300, 900, 3), dtype=np.uint8)
    cyan = (254, 254, 37)  # BGR
    boxes = {"left": (60, 100, 40, 40), "middle": (400, 100, 90, 90),
             "right": (760, 100, 50, 50)}
    for x, y, w, h in boxes.values():
        frame[y:y + h, x:x + w] = cyan

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 900, 300), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=40, match="hue")
        found = {order: screen_mod.find_color(order=order, **common)
                 for order in screen_mod.PICK_ORDERS}
        every = screen_mod.find_colors(order="leftmost", **common)
    finally:
        screen_mod.grab = original

    problems = []
    print("Pick order      : "
          + ", ".join(f"{name}->x{hit.x}" for name, hit in found.items()))
    if len(every) != 3:
        problems.append(f"found {len(every)} patches, expected 3")
    if [hit.left for hit in every] != sorted(hit.left for hit in every):
        problems.append("'leftmost' did not return the patches in order")

    expected = {"largest": 400 + 45, "leftmost": 60 + 20,
                "rightmost": 760 + 25, "topmost": 60 + 20,
                "bottommost": 400 + 45}
    for order, want in expected.items():
        got = found[order]
        if got is None:
            problems.append(f"{order!r} found nothing")
        elif got.x != want:
            problems.append(f"{order!r} chose x={got.x}, expected {want}")

    # The whole point: picking leftmost must not be the same as largest here.
    if found["leftmost"].x == found["largest"].x:
        problems.append("'leftmost' and 'largest' chose the same patch, so the "
                        "test proves nothing")
    return problems


def _check_broken_outlines_join_up() -> list[str]:
    """A glowing card border arrives in pieces and must count as one thing.

    This is the shape of a real failure: two highlighted cards, each outlined
    by a border that anti-aliasing and overlap have broken into fragments.
    Ranked as fragments, 'furthest left' picks the leftmost speck and its
    middle is nowhere near the middle of the card.
    """
    from pixie.system import screen as screen_mod

    frame = np.zeros((600, 1200, 3), dtype=np.uint8)
    cyan = (254, 254, 37)  # BGR

    def broken_outline(left, top, width, height, dash=26, gap=14):
        """A rectangle border drawn as dashes, like a partly hidden glow."""
        for x in range(left, left + width, dash + gap):
            frame[top:top + 4, x:min(x + dash, left + width)] = cyan
            frame[top + height - 4:top + height, x:min(x + dash, left + width)] = cyan
        for y in range(top, top + height, dash + gap):
            frame[y:min(y + dash, top + height), left:left + 4] = cyan
            frame[y:min(y + dash, top + height), left + width - 4:left + width] = cyan

    broken_outline(100, 150, 200, 300)    # left card
    broken_outline(700, 150, 200, 300)    # right card
    left_middle = (100 + 100, 150 + 150)
    right_middle = (700 + 100, 150 + 150)

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 1200, 600), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=40, match="hue", order="leftmost")
        loose = screen_mod.find_colors(**common)
        joined = screen_mod.find_colors(join=20, **common)
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Broken outline  : {len(loose)} pieces on their own, "
          f"{len(joined)} once joined")

    if len(loose) < 8:
        problems.append(f"the test outline only broke into {len(loose)} pieces, "
                        "so it does not reproduce the problem")
    if len(joined) != 2:
        problems.append(f"joining gave {len(joined)} patches, expected one per card")
        return problems

    first, second = joined
    if (first.x, first.y) != left_middle:
        problems.append(f"the joined left outline reports {first.center}, "
                        f"expected the middle of the card at {left_middle}")
    if (second.x, second.y) != right_middle:
        problems.append(f"the joined right outline reports {second.center}, "
                        f"expected {right_middle}")

    # The point of the fix: unjoined, the leftmost piece is a fragment whose
    # middle is well away from the middle of the card.
    off_by = abs(loose[0].x - left_middle[0]) + abs(loose[0].y - left_middle[1])
    if off_by < 50:
        problems.append("the unjoined fragment was already near the card middle, "
                        "so this proves nothing")
    else:
        print(f"                  unjoined, the first piece is {off_by}px away "
              f"from the middle of the card")

    # Joining must not glue two separate cards together.
    if joined[0].left > 300 or joined[1].left < 600:
        problems.append("joining merged the two cards into one patch")
    return problems


def _check_background_of_the_same_color() -> list[str]:
    """A washed-out background of the target hue must be separable from it.

    The nastiest version of this: the background is the same hue, passes the
    default saturation floor, and joining then glues it onto the real target
    so the middle of the patch is nowhere near the middle of the thing.
    Saturation is what tells them apart, and 'What matches?' is what tells
    you the number to use.
    """
    from pixie.system import screen as screen_mod

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    frame = np.zeros((308, 1200, 3), dtype=np.uint8)
    frame[:, :] = hsv(110, 80, 60)                 # dark panels
    frame[40:70, 100:1100] = hsv(90, 120, 230)     # pale cyan background streak
    for y0, y1, x0, x1 in ((10, 30, 500, 860), (280, 300, 500, 860),
                           (10, 300, 500, 520), (10, 300, 840, 860)):
        frame[y0:y1, x0:x1] = hsv(90, 250, 250)    # the vivid card outline
    target_middle = (680, 155)

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 1200, 308), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=39, match="hue",
                      order="leftmost", join=25)
        polluted = screen_mod.find_colors(min_saturation=90, **common)
        clean = screen_mod.find_colors(min_saturation=180, **common)
        _picture, kept, _dropped = screen_mod.explain_colors(
            min_saturation=90, **common)
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Same-hue background: default keeps {polluted[0].width}x"
          f"{polluted[0].height}, saturation floor 180 keeps "
          f"{clean[0].width}x{clean[0].height}")

    if polluted[0].center == target_middle:
        problems.append("the background did not contaminate the match, so this "
                        "test proves nothing")
    if clean[0].center != target_middle:
        problems.append(f"raising the saturation floor gave {clean[0].center}, "
                        f"expected the middle of the outline at {target_middle}")
    if len(clean) != 1:
        problems.append(f"a clean search found {len(clean)} patches, expected 1")

    # The viewer has to report the saturation range, because that range is
    # what tells you where to put the threshold.
    note = kept[0][1] if kept else ""
    if "saturation" not in note:
        problems.append(f"'What matches?' did not report saturation: {note!r}")
    else:
        low, high = (int(n) for n in note.split()[-1].split("-"))
        if not (low <= 130 and high >= 240):
            problems.append(f"the reported range {low}-{high} does not show "
                            "both the background and the target")
        else:
            print(f"                     reported {note}, so the threshold "
                  f"belongs between {low} and {high}")
    return problems


def _check_every_wait_respects_the_cap() -> list[str]:
    """No step type may sit and wait longer than its section's ceiling.

    Written against the step definitions rather than a list kept here, so a
    new step type that waits is covered the day it is added.
    """
    waiting = [key for key, step_type in step_defs.STEP_TYPES.items()
               if "timeout" in step_type.field_map()]
    steps = [{"type": "section", "name": "Capped", "enabled": True, "wait_limit": 2}]
    steps += [dict(step_defs.new_step(key), timeout=45.0) for key in waiting]

    runner = engine_mod.Engine(engine_mod.Sequence(name="caps", steps=steps),
                              dry_run=True)
    runner._enter_section(runner.sections()[0])

    problems = []
    waits = {step["type"]: runner._timeout(step) for step in steps[1:]}
    print(f"Cap covers      : {len(waiting)} step types that wait -> "
          f"{sorted(set(waits.values()))}")
    for kind, waited in waits.items():
        if waited != 2.0:
            problems.append(f"{kind} waits {waited}s despite a 2s section cap")

    # And a step asking for less than the cap keeps its own shorter time.
    brief = dict(step_defs.new_step(waiting[0]), timeout=0.5)
    if runner._timeout(brief) != 0.5:
        problems.append("the cap lengthened a step that was already quicker")

    if not waiting:
        problems.append("no step types declare a timeout, which cannot be right")
    return problems


def _check_declared_defaults() -> list[str]:
    """A step missing a key must behave the way the editor says it would."""
    problems = []
    bare = {"type": "wait_for_color_in_area", "color": [0, 255, 255]}
    checks = {"match": "hue", "tolerance": 14, "min_pixels": 40,
              "min_saturation": 90, "min_brightness": 70}
    got = {key: engine_mod.Engine._value(bare, key, "WRONG") for key in checks}
    print(f"Declared defaults: {got}")
    for key, expected in checks.items():
        if got[key] != expected:
            problems.append(f"a missing {key!r} came out as {got[key]!r}, but the "
                            f"editor shows {expected!r}")
    # An explicit value still wins, including a falsy one.
    if engine_mod.Engine._value({"type": "wait_for_image", "timeout": 0}, "timeout", 9) != 0:
        problems.append("an explicit 0 was treated as unset")
    return problems


def _check_click_box() -> list[str]:
    """A click box must land inside itself, and not on the same pixel twice."""
    box = [400, 300, 200, 100]
    clicks: list[tuple[int, int]] = []

    class Watching(engine_mod.Engine):
        def _click(self, x, y, step, what):
            clicks.append((x, y))

    step = {"type": "click_box", "name": "anywhere", "enabled": True,
            "box": box, "clicks": 1, "button": "left"}
    runner = Watching(engine_mod.Sequence(name="box", steps=[step]), dry_run=True)
    for _ in range(60):
        runner.run_step(step)

    left, top, width, height = box
    problems = []
    outside = [c for c in clicks
               if not (left <= c[0] < left + width and top <= c[1] < top + height)]
    print(f"Click box       : {len(set(clicks))} distinct spots in {len(clicks)} "
          f"clicks, all inside {width}x{height}")
    if outside:
        problems.append(f"{len(outside)} clicks landed outside the box: {outside[:3]}")
    if len(set(clicks)) < 20:
        problems.append(f"only {len(set(clicks))} distinct spots in 60 clicks - "
                        "the randomness is not working")
    if runner.last_match not in clicks:
        problems.append("the box click did not leave a last match to build on")

    # No box picked: say so rather than clicking 0,0.
    if Watching(engine_mod.Sequence(name="box", steps=[]), dry_run=True)._do_click_box(
            {"type": "click_box"}) != "timeout":
        problems.append("a click box with no box set did not report a problem")
    return problems


def _check_hue_matching() -> list[str]:
    """Hue matching must survive a brightness gradient that defeats RGB.

    Builds a cyan glow that fades from near-white at its core to nearly black
    at its edge -- which is what a real glow looks like -- and checks hue mode
    catches far more of it than a distance match on one sampled color.
    """
    from pixie.system import screen as screen_mod

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

    from pixie.system import keyboard as kb

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

    from pixie.system import mouse as ms

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
    from pixie.system import screen as screen_mod

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
    if "not there" not in logged or "skipping" not in logged:
        failures.append("the optional step did not skip when its image was absent")
    # It must also say how long it waited, because an optional step that is
    # never there costs that much time on every single cycle.
    if "not there after" not in logged:
        failures.append("the skip did not say how long it waited first")
    steps_seen = {e["index"] for e in messages if e.get("kind") == "step"}
    if steps_seen != set(range(6)):
        failures.append(f"engine reported steps {sorted(steps_seen)}, expected 0-5")
    return failures


if __name__ == "__main__":
    sys.exit(main())
