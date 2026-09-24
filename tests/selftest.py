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
                # The crop comes off the real desktop, and a desktop can show
                # the same thing twice - a repeated panel, a blank stretch.
                # Landing on an identical copy is not the matcher failing.
                scores = cv2.matchTemplate(frame, screen.load_template(tpl_path),
                                           cv2.TM_CCOEFF_NORMED)
                copies = int((scores >= 0.9999).sum())
                if copies > 1:
                    print(f"                  (that crop appears {copies} times "
                          f"on screen, so either is correct)")
                else:
                    failures.append(
                        f"matched at {(match.x, match.y)}, expected {expected}")

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
    failures.extend(_check_a_check_guards_its_indented_steps())
    failures.extend(_check_a_jump_sends_the_run_somewhere())
    failures.extend(_check_a_section_that_achieves_nothing())
    failures.extend(_check_the_sequence_wide_timeout())
    failures.extend(_check_the_aim_warning_reads_as_english())
    failures.extend(_check_an_odd_sized_match_is_called_out())
    failures.extend(_check_parking_only_after_a_click())
    failures.extend(_check_a_section_can_hold_the_cursor_still())
    failures.extend(_check_parking_and_gliding())
    failures.extend(_check_a_near_miss_reports_its_score())
    failures.extend(_check_max_cycles_is_a_real_limit())
    failures.extend(_check_section_limits())
    failures.extend(_check_pick_order())
    failures.extend(_check_broken_outlines_join_up())
    failures.extend(_check_background_of_the_same_color())
    failures.extend(_check_aiming_at_an_edge())
    failures.extend(_check_edges_follow_the_shape())
    failures.extend(_check_a_mostly_hidden_outline())
    failures.extend(_check_a_speck_swept_up_by_the_join())
    failures.extend(_check_the_shape_split_is_suggested())
    failures.extend(_check_specks_are_dropped_before_joining())
    failures.extend(_check_joining_sideways_is_its_own_distance())
    failures.extend(_check_where_a_patch_sits_can_be_required())
    failures.extend(_check_a_section_with_nothing_switched_on())
    failures.extend(_check_every_wait_respects_the_cap())
    failures.extend(_check_declared_defaults())
    failures.extend(_check_click_box())
    failures.extend(_check_keyboard())
    failures.extend(_check_enter_is_the_main_one())
    failures.extend(_check_look_alike_keys_are_told_apart())
    failures.extend(_check_how_often_it_looks())
    failures.extend(_check_repeats_are_not_metronomic())
    failures.extend(_check_every_delay_around_a_press_varies())
    failures.extend(_check_the_cursor_travels_to_a_click())
    failures.extend(_check_cursor_travel_scales_with_distance())
    failures.extend(_check_nothing_grows_forever_during_a_run())
    failures.extend(_check_a_bad_stop_key_does_not_kill_the_run())
    failures.extend(_check_tidying_never_deletes_a_picture_in_use())
    failures.extend(_check_mouse_movement_is_injected())
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


def _check_a_check_guards_its_indented_steps() -> list[str]:
    """Steps indented under a check run only when that check finds something.

    The thing this exists for: a target prompt that only sometimes appears,
    with two or three actions to take when it does. Before this, the only way
    to express it was to put the actions behind a step whose failure restarted
    the section - which deadlocks the moment the prompt is what stops the
    other steps from finding anything.
    """
    ran: list[str] = []
    found = {"check": False}

    class Watching(engine_mod.Engine):
        def run_step(self, step):
            tag = step.get("tag", "")
            ran.append(tag)
            if tag == "check":
                return "ok" if found["check"] else "timeout"
            return "ok"

    def step(tag, indent=0, on_timeout=None):
        made = {"type": "wait_for_image", "name": tag, "enabled": True,
                "tag": tag, "image": "x", "pause": [0, 0]}
        if on_timeout:
            made["on_timeout"] = on_timeout
        if indent:
            made["indent"] = indent
        return made

    steps = [step("check", on_timeout="skip_block"),
             step("act one", indent=1),
             step("act two", indent=1),
             step("after")]
    sequence = engine_mod.Sequence(
        name="guarded", steps=steps,
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))

    problems = []
    for present in (False, True):
        found["check"], ran[:] = present, []
        Watching(sequence, dry_run=True).run(max_cycles=1)
        expected = (["check", "act one", "act two", "after"] if present
                    else ["check", "after"])
        if ran != expected:
            problems.append(f"with the check {'finding' if present else 'failing'}"
                            f", it ran {ran}, expected {expected}")
    print(f"Guarded steps   : check fails -> {['check', 'after']}, "
          f"check finds -> ran all 4")

    # The block is whatever is indented, so it ends where the indenting does.
    if step_defs.block_of(steps, 0) != (1, 3):
        problems.append(f"the block under the check is "
                        f"{step_defs.block_of(steps, 0)}, expected (1, 3)")
    # An indented step owns nothing itself - one level, not a tree.
    if step_defs.block_of(steps, 1) != (2, 2):
        problems.append("an indented step claimed a block of its own")

    # An indent with nothing above it to guard it is not an indent. This is
    # what stops a deleted check leaving its actions looking conditional.
    orphan = [step("act one", indent=1), step("after")]
    if not step_defs.normalize_indents(orphan) or step_defs.indent_of(orphan[0]):
        problems.append("an indent with nothing above it survived")
    # Nor can a step that cannot fail own a block.
    under_click = [{"type": "click_box", "name": "c", "enabled": True},
                   step("act one", indent=1)]
    if not step_defs.normalize_indents(under_click):
        problems.append("a step indented under something that cannot fail "
                        "was left alone")

    # And the validator says so before a run rather than after one.
    said = engine_mod.Sequence(name="x", steps=[
        step("check", on_timeout="restart"), step("act one", indent=1)]).warnings()
    if not any("whether it finds anything or not" in line for line in said):
        problems.append(f"indenting under a check that cannot skip drew no "
                        f"warning: {said}")
    said = engine_mod.Sequence(name="x", steps=[
        step("check", on_timeout="skip_block"), step("after")]).warnings()
    if not any("nothing is indented under it" in line for line in said):
        problems.append(f"a check set to skip nothing drew no warning: {said}")
    return problems


def _check_a_section_that_achieves_nothing() -> list[str]:
    """A check that fires when a section has gone round doing nothing.

    Every other check asks what is on screen. Some states do not announce
    themselves in pixels at all: a hand with nothing playable in it looks
    exactly like a hand you have not got to yet. What tells them apart is
    that nothing is being achieved - the loop goes round and round clicking
    nothing - and that is a fact about the run, not about the screen.
    """
    ran: list[str] = []
    playable = {"yes": True}
    laps = {"left": 6}

    class Watching(engine_mod.Engine):
        def run_step(self, step):
            tag = step.get("tag", "")
            if tag == "play":
                if not playable["yes"]:
                    return "timeout"
                ran.append("played")
                self._click(10, 10, step, "a card")   # this is what "acted" means
                return "ok"
            if tag == "pass":
                ran.append("passed")
                self._click(20, 20, step, "pass")
                return "ok"
            if tag == "limit":
                # Ends the run after a fixed number of laps, so the test
                # finishes whether or not the idle check ever fires.
                laps["left"] -= 1
                return "ok" if laps["left"] > 0 else "timeout"
            return super().run_step(step)

    def step(tag, on_timeout):
        return {"type": "wait_for_color_in_area", "name": tag, "tag": tag,
                "enabled": True, "on_timeout": on_timeout, "pause": [0, 0],
                "region": [0, 0, 10, 10], "color": [1, 2, 3]}

    idle = dict(step_defs.new_step("when_idle"), laps=3,
                on_timeout="skip_block")
    passer = dict(step("pass", "continue"), indent=1)
    steps = [{"type": "section", "name": "Playing", "enabled": True},
             idle, passer, step("play", "continue"),
             step("limit", "next_section")]
    sequence = engine_mod.Sequence(
        name="idling", steps=steps,
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     section_pause_min=0, section_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))

    problems = []
    # While cards are playable, the loop is achieving something and the idle
    # check must never fire, however long it runs.
    laps["left"] = 6
    Watching(sequence, dry_run=True).run(max_cycles=1)
    if "passed" in ran:
        problems.append(f"passed the turn while cards were still playable: {ran}")
    played_for = len(ran)

    # With nothing playable, it fires on the lap after the third idle one.
    playable["yes"], ran[:], laps["left"] = False, [], 6
    Watching(sequence, dry_run=True).run(max_cycles=1)
    if "passed" not in ran:
        problems.append("nothing playable for six laps and it never passed")
    print(f"Idle check      : {played_for} laps of playing -> never fired; "
          f"6 laps of nothing -> fired {ran.count('passed')}x")

    # And it fires once per run of idle laps, not on every one of them.
    if ran.count("passed") > 2:
        problems.append(f"fired {ran.count('passed')} times in 6 laps - it is "
                        "not resetting its count after acting")

    # Idle laps belong to the section that went round them. A count carried
    # across a hand-over would let one section's quiet spell fire another
    # section's check, having never run it once.
    crossing = Watching(engine_mod.Sequence(name="x"), dry_run=True)
    crossing.idle_laps = 4
    crossing._enter_section((0, 1, "somewhere else"))
    if crossing.idle_laps != 0:
        problems.append(f"entering a section inherited {crossing.idle_laps} "
                        "idle laps from the one before it")

    # A lap is idle when *that* lap achieved nothing. Going back to the top of
    # a section abandons the lap in progress, so whatever it managed before
    # giving up must not count towards the next one. Otherwise a click in a
    # lap that was thrown away makes the following idle lap look productive,
    # and the idle check never reaches its count.
    # Lap 1 clicks and is then abandoned part-way; laps 2 and 3 achieve
    # nothing and run to the end. Two idle laps, so the count must read 2. If
    # lap 1's click carries over, lap 2 looks productive and the count reads 1.
    done = {"clicked": False, "failed": False, "laps": 0}

    class Restarting(engine_mod.Engine):
        def run_step(self, step):
            tag = step.get("tag", "")
            if tag == "click_once":
                if not done["clicked"]:
                    done["clicked"] = True
                    self._click(10, 10, step, "something")
                return "ok"
            if tag == "fail_once":
                if not done["failed"]:
                    done["failed"] = True
                    return "timeout"      # -> back to the first step of this section
                return "ok"
            if tag == "count":
                done["laps"] += 1
                return "ok" if done["laps"] < 3 else "timeout"
            return super().run_step(step)

    restarter = Restarting(engine_mod.Sequence(
        name="restarting",
        steps=[{"type": "section", "name": "Looping", "enabled": True},
               step("click_once", "continue"),
               step("fail_once", "restart_section"),
               step("count", "next_section")],
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     section_pause_min=0, section_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False)), dry_run=True)
    restarter.run(max_cycles=1)
    if restarter.idle_laps != 2:
        problems.append(
            f"two laps achieved nothing but the count says {restarter.idle_laps}. "
            "A click in the lap that 'back to the first step of this section' "
            "abandoned was carried into the lap after it.")

    # Having done something is a fact about one step, and it has to be cleared
    # whatever that step then returns. Left set by a step that failed, it gets
    # attributed to whichever step runs next and succeeds.
    leaky = Watching(engine_mod.Sequence(name="x"), dry_run=True)
    leaky.acted = True
    leaky.run_cycle_consumed = None
    steps_run = [{"type": "press_key", "name": "fails", "enabled": True,
                  "key": "Q", "tag": "limit", "on_timeout": "next_section"}]
    leaky.sequence.steps = steps_run
    laps["left"] = 1          # 'limit' returns timeout straight away
    leaky.run_cycle()
    if leaky.acted:
        problems.append("a step that failed left 'something happened' set, so "
                        "the next step to succeed takes the credit for it")

    # The count itself: three idle laps, then it has something to report.
    solo = Watching(engine_mod.Sequence(name="x"), dry_run=True)
    outcomes = []
    for lap in range(5):
        outcomes.append(solo._do_when_idle({"type": "when_idle", "laps": 3}))
        solo.idle_laps += 1
    if outcomes != ["timeout", "timeout", "timeout", "ok", "timeout"]:
        problems.append(f"the count came out {outcomes}, expected it to hold "
                        "off for three laps, fire once, then start again")
    return problems


def _check_a_jump_sends_the_run_somewhere() -> list[str]:
    """'Go somewhere else' does on purpose what a failure does by accident.

    Every other branch is phrased as "if this is NOT found", which covers most
    things because a screen going away is usually the same event as the next
    one arriving. It is not always: a victory screen appearing over a game
    still in progress is its own event, and inverting it is not possible.

    Indented under a check, this is how "if this IS found, go there" is said.
    """
    ran: list[str] = []
    seen = {"end": False}

    class Watching(engine_mod.Engine):
        def run_step(self, step):
            if step.get("type") == "jump":
                return super().run_step(step)
            ran.append(step.get("tag", ""))
            if step.get("tag") == "is it over":
                return "ok" if seen["end"] else "timeout"
            # Everything else reports nothing found, so each section hands
            # over rather than repeating itself forever.
            return "timeout"

    def look(tag, on_timeout, indent=0):
        made = {"type": "wait_for_image", "name": tag, "tag": tag,
                "enabled": True, "image": "x", "on_timeout": on_timeout,
                "pause": [0, 0]}
        if indent:
            made["indent"] = indent
        return made

    steps = [
        {"type": "section", "name": "Playing", "enabled": True},
        look("is it over", "skip_block"),
        dict(step_defs.new_step("jump"), where="next_section", indent=1),
        look("play a card", "next_section"),
        {"type": "section", "name": "Finished", "enabled": True},
        look("tidy up", "next_section"),
    ]
    sequence = engine_mod.Sequence(
        name="jumping", steps=steps,
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     section_pause_min=0, section_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))

    problems = []
    # While the game is on, the check fails, its jump is skipped, and play
    # carries on in the first section.
    seen["end"], ran[:] = False, []
    Watching(sequence, dry_run=True).run(max_cycles=1)
    if "tidy up" not in ran or ran[:2] != ["is it over", "play a card"]:
        problems.append(f"with nothing detected it ran {ran}, expected to play "
                        "a card before ever leaving the section")

    # Once it is over, the check finds it and the jump leaves immediately -
    # without running the step below it.
    seen["end"], ran[:] = True, []
    Watching(sequence, dry_run=True).run(max_cycles=1)
    if "play a card" in ran:
        problems.append(f"the jump did not leave the section: {ran}")
    if ran != ["is it over", "tidy up"]:
        problems.append(f"detecting the end ran {ran}, expected to go straight "
                        "to the next section")
    print(f"Jump step       : not detected -> {['is it over', 'play a card']}, "
          f"detected -> {ran}")

    # Everywhere a jump can go is somewhere a failure can go, so both run down
    # the same branches rather than two copies of them.
    if not set(step_defs.JUMP_TARGETS) <= set(step_defs.ON_TIMEOUT):
        problems.append("a jump can go somewhere no 'if not found' can")
    return problems


def _check_an_odd_sized_match_is_called_out() -> list[str]:
    """A match far smaller than the step's usual find is probably not it.

    Every floor on a step is a number somebody guessed, and the guess only
    goes wrong one way: too low, so noise of roughly the right color slips
    through and gets clicked. "71 pixels" reads as a fact, not a problem -
    until you see the same step finding 12,000 the rest of the time.

    These are the real numbers from one run, where six stray finds between
    50 and 374 pixels each fired a click on an empty battlefield.
    """
    said: list[str] = []
    runner = engine_mod.Engine(
        engine_mod.Sequence(name="sizes"),
        emit=lambda event: said.append(str(event.get("message", "")))
        if event.get("level") == "warn" else None)

    step = dict(step_defs.new_step("wait_for_color_in_area"), min_pixels=40)

    def hit(pixels):
        return screen.ColorHit(0, 0, 0, 0, 158, 113, pixels)

    problems = []
    # The first few set the baseline and must not be second-guessed.
    for pixels in (12877, 13232, 11855):
        runner._odd_size(step, hit(pixels))
    if said:
        problems.append(f"the first few finds drew a warning: {said}")

    # ...then a stray one is called out, naming what the step usually finds.
    said.clear()
    runner._odd_size(step, hit(71))
    if not said:
        problems.append("a 71-pixel find among 12,000-pixel ones said nothing")
    elif "12,877" not in said[0]:
        problems.append(f"the warning did not name the usual size: {said[0]!r}")
    else:
        print("Odd size        : " + said[0].strip()[:74])

    # A normal one afterwards stays quiet, and the stray has not dragged the
    # yardstick down with it.
    said.clear()
    runner._odd_size(step, hit(13990))
    if said:
        problems.append(f"a normal find warned: {said}")
    said.clear()
    runner._odd_size(step, hit(374))
    if not said:
        problems.append("a stray find changed the baseline, so the next one "
                        "was accepted")

    # A step that genuinely varies in size is not nagged: real cards came in
    # between 3,566 and 13,622 pixels in the same run.
    said.clear()
    cards = engine_mod.Engine(engine_mod.Sequence(name="cards"),
                              emit=lambda event: said.append("warned")
                              if event.get("level") == "warn" else None)
    for pixels in (3566, 4361, 9359, 13622, 3873, 5013, 4935):
        cards._odd_size(step, hit(pixels))
    if said:
        problems.append("a step whose finds legitimately vary 4x was nagged")
    return problems


def _check_a_section_can_hold_the_cursor_still() -> list[str]:
    """A section can refuse to have the cursor moved after a click.

    Parking keeps the pointer off the next thing Pixie needs to see, and off
    one pixel for hours. Some screens do not want it: a menu where the cursor
    passing over an entry changes what is underneath, or anything that reacts
    to being hovered. That is a property of the screen, so it belongs to the
    section, and it has to go back to normal in the next one.
    """
    from pixie.system import mouse as mouse_mod

    moves: list[tuple[int, int]] = []
    settings = engine_mod.Settings(
        park_mouse="custom", park_box=[900, 500, 4, 4],
        step_pause_min=0, step_pause_max=0, section_pause_min=0,
        section_pause_max=0, cycle_pause_min=0, cycle_pause_max=0,
        failsafe_corner=False)

    def click(name, x):
        return {"type": "click_point", "name": name, "enabled": True,
                "pos": [x, 40], "clicks": 1, "button": "left", "pause": [0, 0]}

    def leave(name):
        return {"type": "wait_for_image", "name": name, "enabled": True,
                "image": "x", "on_timeout": "next_section", "pause": [0, 0]}

    still = dict(step_defs.new_step("section"), name="Still", park="off")
    normal = dict(step_defs.new_step("section"), name="Normal")

    class Watching(engine_mod.Engine):
        def run_step(self, step):
            if step["type"] == "wait_for_image":
                return "timeout"          # hands the section over
            return super().run_step(step)

    original = mouse_mod.move_to
    mouse_mod.move_to = lambda x, y: moves.append((int(x), int(y)))
    try:
        Watching(engine_mod.Sequence(
            name="stillness",
            steps=[still, click("in the still one", 100), leave("out"),
                   normal, click("in the normal one", 200), leave("out")],
            settings=settings)).run(max_cycles=1)
    finally:
        mouse_mod.move_to = original

    parked = [spot for spot in moves
              if 900 <= spot[0] < 904 and 500 <= spot[1] < 504]
    problems = []
    print(f"Section stillness: {len(moves)} cursor moves in all, "
          f"{len(parked)} of them to the parking spot")
    if not parked:
        problems.append("the ordinary section did not park after its click")
    # The still section's click is at x=100, the normal one's at x=200. Only
    # the second may be followed by a journey to the parking spot.
    order = [spot[0] for spot in moves]
    if 100 not in order or 200 not in order:
        problems.append(f"both clicks should have moved the cursor: {order}")
    elif order.index(200) > min((n for n, spot in enumerate(moves)
                                 if spot in parked), default=len(moves)):
        problems.append("the cursor was parked before the second section, so "
                        "the first section did not hold it still")

    # And the divider says so in the list, because it changes what runs
    # without appearing among the steps.
    if "held still" not in step_defs.describe(still):
        problems.append(f"a still section does not say so: "
                        f"{step_defs.describe(still)!r}")
    if "held still" in step_defs.describe(normal):
        problems.append("an ordinary section claims to hold the cursor still")
    return problems


def _check_parking_only_after_a_click() -> list[str]:
    """Parking after a step that never moved the pointer is pure cost.

    Parking exists to move the pointer off whatever was just clicked. A step
    that only looks at the screen never moved it, so there is nothing to move
    off - and with gliding switched on, each pointless park is a quarter of a
    second spent crossing the screen and back. In a loop of seven steps where
    two of them click, that was five wasted journeys on every single pass.
    """
    from pixie.system import mouse as mouse_mod

    parked: list[tuple[int, int]] = []
    settings = engine_mod.Settings(
        park_mouse="custom", park_box=[900, 500, 10, 10],
        step_pause_min=0, step_pause_max=0, cycle_pause_min=0,
        cycle_pause_max=0, failsafe_corner=False)

    looked = {"type": "wait_for_image", "name": "look", "enabled": True,
              "image": "x", "on_timeout": "continue", "pause": [0, 0]}
    clicked = {"type": "click_point", "name": "click", "enabled": True,
               "pos": [100, 200], "clicks": 1, "button": "left",
               "pause": [0, 0]}

    class Watching(engine_mod.Engine):
        def run_step(self, step):
            if step["type"] == "wait_for_image":
                return "ok"          # found it, without touching the mouse
            return super().run_step(step)

    original = mouse_mod.move_to
    mouse_mod.move_to = lambda x, y: parked.append((int(x), int(y)))
    try:
        runner = Watching(engine_mod.Sequence(
            name="parking", steps=[looked, looked, clicked, looked],
            settings=settings))
        runner.run(max_cycles=1)
    finally:
        mouse_mod.move_to = original

    problems = []
    # One click, so one park - plus the settle nudge, which is two more moves
    # at the same place.
    trips = [spot for spot in parked if spot != (100, 200)]
    inside = [spot for spot in trips
              if 900 <= spot[0] < 910 and 500 <= spot[1] < 510]
    print(f"Parking after   : 4 steps, 1 of them clicking -> {len(inside)} "
          "move(s) to the parking spot")
    if not inside:
        problems.append("clicking did not park at all")
    if len(inside) > 3:
        problems.append(f"parked {len(inside)} times for one click - the steps "
                        "that only looked are parking too")
    return problems


def _check_parking_and_gliding() -> list[str]:
    """The cursor parks somewhere in a box, and can travel rather than warp."""
    from pixie.system import mouse as mouse_mod

    problems = []
    sequence = engine_mod.Sequence(
        name="parking",
        settings=engine_mod.Settings(park_mouse="custom",
                                     park_box=[1000, 500, 200, 100]))
    runner = engine_mod.Engine(sequence)

    spots = {runner._park_target() for _ in range(200)}
    outside = [(x, y) for x, y in spots
               if not (1000 <= x < 1200 and 500 <= y < 600)]
    print(f"Parking         : {len(spots)} different spots in 200 goes, "
          f"{len(outside)} outside the box")
    if outside:
        problems.append(f"parked outside the box: {outside[:3]}")
    if len(spots) < 50:
        problems.append(f"only {len(spots)} distinct spots in 200 - a box is "
                        "meant to vary, not repeat")

    # A one-pixel box is a point, which is what an older sequence becomes.
    older = engine_mod.Settings.from_dict({"park_mouse": "custom",
                                           "park_point": [640, 480]})
    if older.park_box != [640, 480, 1, 1]:
        problems.append(f"an older parking point became {older.park_box}")
    exact = engine_mod.Engine(engine_mod.Sequence(name="x", settings=older))
    if {exact._park_target() for _ in range(20)} != {(640, 480)}:
        problems.append("a one-pixel box did not park exactly on its point")

    # Gliding visits places along the way; warping visits nothing.
    visited: list[tuple[int, int]] = []
    real_move, real_position = mouse_mod.move_to, mouse_mod.position
    mouse_mod.move_to = lambda x, y: visited.append((int(x), int(y)))
    mouse_mod.position = lambda: (0, 0)
    try:
        mouse_mod.glide_to(600, 400, seconds=0)
    finally:
        mouse_mod.move_to, mouse_mod.position = real_move, real_position

    print(f"Gliding         : {len(visited)} moves from 0,0 to 600,400, "
          f"ending {visited[-1] if visited else None}")
    if len(visited) < 5:
        problems.append(f"a glide across the screen took {len(visited)} moves")
    if visited[-1] != (600, 400):
        problems.append(f"the glide ended at {visited[-1]}, not the target")
    # Eased, so it does not crawl at a constant speed the whole way.
    steps = [visited[n + 1][0] - visited[n][0] for n in range(len(visited) - 1)]
    if max(steps) - min(steps) < 2:
        problems.append("the glide moved at a constant speed, so it is not eased")
    return problems


def _check_a_near_miss_reports_its_score() -> list[str]:
    """A picture that does not match must say how close it got.

    "It did not appear" reads the same whether the picture was a hair under
    the threshold or nothing like what is on screen - and those want opposite
    fixes. One wants the confidence nudged; the other wants a new picture.
    """
    said: list[str] = []
    runner = engine_mod.Engine(
        engine_mod.Sequence(name="scores"),
        emit=lambda event: said.append(str(event.get("message", ""))))

    problems = []
    for score, expected in ((0.82, "Lower"), (0.31, "nothing like it"),
                            (0.60, "recapture")):
        said.clear()
        runner._how_close(score, 0.85)
        if not said:
            problems.append(f"a best score of {score} was not reported at all")
        elif f"{score:.2f}" not in said[0] or expected not in said[0]:
            problems.append(f"a score of {score} said {said[0]!r}, expected it "
                            f"to mention {expected!r}")
    print("Near miss       : 0.82 -> lower the threshold, 0.31 -> wrong "
          "picture, 0.60 -> recapture")

    # The score has to come from the look that just failed, not a second one:
    # a step whose picture is never there pays for it on every single pass.
    import inspect
    if "best_score" in inspect.getsource(runner._find):
        problems.append("_find searches a second time just to report a score")

    # And the failing look really does hand its score back.
    # Two different patterns, so the correlation is meaningful rather than
    # the degenerate case of one flat image against another.
    dice = np.random.default_rng(1)
    picture = dice.integers(0, 255, (40, 40, 3), dtype=np.uint8)
    elsewhere = dice.integers(0, 255, (160, 160, 3), dtype=np.uint8)
    original = screen.grab
    screen.grab = lambda _region=None: elsewhere
    try:
        match, score = screen.match_template(picture, None, 0.85)
    finally:
        screen.grab = original
    if match is not None:
        problems.append(f"noise matched different noise at 0.85 ({score:.2f})")
    elif not 0.0 <= score < 0.85:
        problems.append(f"a failed match reported a score of {score}")
    else:
        print(f"                  a failed look still hands back its score "
              f"({score:.2f}), at no extra cost")
    return problems


def _check_the_sequence_wide_timeout() -> list[str]:
    """A step with no wait of its own takes the sequence's.

    Setting the same number on every step by hand is how a sequence ends up
    with a thirty-second wait nobody meant, sitting in the middle of a loop.
    """
    problems = []
    settings = engine_mod.Settings(wait_timeout=3.0)
    runner = engine_mod.Engine(engine_mod.Sequence(name="waits",
                                                   settings=settings))

    borrowed = runner._timeout({"type": "wait_for_image"})
    if borrowed != 3.0:
        problems.append(f"a step with no wait of its own took {borrowed}s, "
                        "expected the sequence's 3s")

    own = runner._timeout({"type": "wait_for_image", "timeout": 0.5})
    if own != 0.5:
        problems.append(f"a step with its own 0.5s took {own}s instead")

    # Changing the sequence changes every step that has not opted out.
    settings.wait_timeout = 8.0
    if runner._timeout({"type": "wait_for_image"}) != 8.0:
        problems.append("changing the sequence-wide wait did not reach a step")
    if runner._timeout({"type": "wait_for_image", "timeout": 0.5}) != 0.5:
        problems.append("changing the sequence-wide wait overrode a step "
                        "that had set its own")

    # A section cap still trumps both, which is what a cap is for.
    runner.wait_limit = 2.0
    capped = [runner._timeout({"type": "wait_for_image"}),
              runner._timeout({"type": "wait_for_image", "timeout": 30.0}),
              runner._timeout({"type": "wait_for_image", "timeout": 0.5})]
    if capped != [2.0, 2.0, 0.5]:
        problems.append(f"under a 2s section cap the waits came out {capped}, "
                        "expected [2.0, 2.0, 0.5]")
    runner.wait_limit = None

    # Every step type that waits declares no wait of its own now, so every
    # one of them follows the sequence.
    settings.wait_timeout = 4.0
    borrowing = []
    for key, step_type in step_defs.STEP_TYPES.items():
        if not any(f.key == "timeout" for f in step_type.fields):
            continue
        fresh = step_defs.new_step(key)
        if fresh.get("timeout") is not None:
            problems.append(f"{key} still ships with its own wait, "
                            f"{fresh['timeout']}")
        elif runner._timeout(fresh) == 4.0:
            borrowing.append(key)
    print(f"Sequence waits  : {len(borrowing)} step types follow the sequence, "
          "a step that sets its own keeps it, a section cap beats both")
    return problems


def _check_the_aim_warning_reads_as_english() -> list[str]:
    """A corner is two edges, and neither of them is called 'bottom_left'."""
    said: list[str] = []
    runner = engine_mod.Engine(
        engine_mod.Sequence(name="aim"),
        emit=lambda event: said.append(str(event.get("message", "")))
        if event.get("level") == "warn" else None)

    problems = []
    runner.last_pieces, runner.last_clipped = 3, "top and left"
    runner._aim_warning("bottom_left")
    joined = " ".join(said)
    if "bottom_left" in joined:
        problems.append(f"a field key leaked into the log: {joined!r}")
    if "its bottom-left corner" not in joined:
        problems.append(f"the corner was not named in English: {joined!r}")
    # Aiming at a corner aims at two edges; the left one really was cut.
    if "left" not in joined or "cut" not in joined:
        problems.append("aiming at a corner whose left edge was cut said "
                        f"nothing about it: {joined!r}")
    print("Aim warning     : " + [line for line in said if "cut" in line][0].strip()[:78])

    # The bottom was not cut, so it must not be named as though it were.
    said.clear()
    runner.last_pieces, runner.last_clipped = 1, "left"
    runner._aim_warning("bottom_right")
    if said:
        problems.append(f"a corner with no cut edge still warned: {said}")
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


def _check_aiming_at_an_edge() -> list[str]:
    """Two targets found as one patch must still be clickable individually.

    Real numbers from a run: two highlighted cards touching came back as one
    782x314 patch, so its middle landed in the gap between them. Aiming at the
    patch's left edge and offsetting right lands on the left card whether the
    two merged or not, which is the whole point.
    """
    clicks: list[tuple[int, int]] = []

    class Watching(engine_mod.Engine):
        def _click(self, x, y, step, what):
            clicks.append((x, y))

    merged = (1168, 1845, 782, 314)      # left card starts at 1168
    runner = Watching(engine_mod.Sequence(name="aim", steps=[]), dry_run=True)
    runner.last_match = (merged[0] + merged[2] // 2, merged[1] + merged[3] // 2)
    runner.last_box = merged

    problems = []
    aims = {}
    for anchor in step_defs.ANCHORS:
        step = {"type": "click_last_match", "anchor": anchor, "offset": [0, 0]}
        aims[anchor] = runner._aim(step, merged)

    expected = {
        "middle": (1559, 2002), "left": (1168, 2002), "right": (1949, 2002),
        "top": (1559, 1845), "bottom": (1559, 2158),
        "top_left": (1168, 1845), "top_right": (1949, 1845),
        "bottom_left": (1168, 2158), "bottom_right": (1949, 2158),
    }
    print(f"Aiming          : middle {aims['middle']}, left edge {aims['left']}")
    for anchor, want in expected.items():
        if aims[anchor] != want:
            problems.append(f"aiming at {anchor!r} gave {aims[anchor]}, expected {want}")

    # The useful combination: left edge plus an offset into the card.
    step = {"type": "click_last_match", "anchor": "left", "offset": [90, 0]}
    on_the_left_card = runner._aim(step, merged)
    if on_the_left_card != (1258, 2002):
        problems.append(f"left edge plus 90 gave {on_the_left_card}")
    # That point must be inside the left half, where the left card is.
    if on_the_left_card[0] > merged[0] + merged[2] // 2:
        problems.append("left edge plus offset still landed on the right card")

    # A step with no anchor set behaves exactly as it always did.
    runner.run_step({"type": "click_last_match", "offset": [0, 50],
                     "clicks": 2, "button": "left"})
    if clicks[-1] != (1559, 2052):
        problems.append(f"an old step without an anchor clicked {clicks[-1]}, "
                        "expected the middle plus its offset")

    # And with no box remembered at all, the old point still works.
    runner.last_box = None
    runner.run_step({"type": "click_last_match", "offset": [0, 0],
                     "clicks": 1, "button": "left"})
    if clicks[-1] != runner.last_match:
        problems.append(f"without a box it clicked {clicks[-1]}, expected "
                        f"{runner.last_match}")
    return problems


def _check_edges_follow_the_shape() -> list[str]:
    """An edge anchor must land on the shape, not on the box around it.

    Cards in a fan are tilted and sit at different heights, so the box round
    a merged group belongs to no single card: its top edge comes from the
    highest card and its left edge from the lowest. Aiming at the middle of
    that box put a real click three pixels inside a card's top frame.
    """
    from pixie.system import screen as screen_mod

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    glow = hsv(90, 250, 250)
    frame = np.zeros((500, 700, 3), dtype=np.uint8)

    def outline(left, top):
        """A card outline 200x240, drawn as a ring."""
        frame[top:top + 10, left:left + 200] = glow
        frame[top + 230:top + 240, left:left + 200] = glow
        frame[top:top + 240, left:left + 10] = glow
        frame[top:top + 240, left + 190:left + 200] = glow

    outline(40, 240)     # the left card, sitting low
    outline(230, 0)      # the middle card, sitting high
    outline(420, 20)     # the right card
    left_card_middle_y = 240 + 120

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        hit = screen_mod.find_colors((0, 0, 700, 500), (37, 254, 254),
                                     tolerance=14, min_pixels=39, match="hue",
                                     order="leftmost", join=30)[0]
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Edge follows    : merged {hit.width}x{hit.height}, box middle "
          f"y={hit.y}, shape's left edge y={hit.left_y}")

    if hit.width < 500:
        problems.append(f"the three cards did not merge ({hit.width}px wide), "
                        "so this proves nothing")
    # The box's middle has to be useless for the left card, or the test is
    # idle. Landing within a few pixels of its top edge is exactly the real
    # failure: technically on the card, practically on its frame.
    if abs(hit.y - 240) > 15:
        problems.append(f"the box middle y={hit.y} is not on the left card's "
                        "top edge, so the failure is not being reproduced")
    if abs(hit.left_y - left_card_middle_y) > 15:
        problems.append(f"the left edge reports y={hit.left_y}, expected near "
                        f"{left_card_middle_y} - the middle of the left card")

    # Aiming has to use it.
    runner = engine_mod.Engine(engine_mod.Sequence(name="aim", steps=[]),
                               dry_run=True)
    box = (hit.left, hit.top, hit.width, hit.height)
    edges = runner._edges_of(hit)
    step = {"type": "click_last_match", "anchor": "left", "offset": [100, 0]}
    aimed = runner._aim(step, box, edges)
    if not (280 <= aimed[1] <= 440):
        problems.append(f"aiming at the left edge gave y={aimed[1]}, which is "
                        "not comfortably inside the left card (240-480)")
    without = runner._aim(step, box, None)
    if without[1] == aimed[1]:
        problems.append("the shape made no difference, so it is not being used")

    # A template match is a rectangle, so it has nothing to follow and says so.
    if runner._edges_of(screen.Match(10, 20, 30, 40, 1.0)) is not None:
        problems.append("an image match claimed to know where its shape is")
    return problems


def _check_a_mostly_hidden_outline() -> list[str]:
    """A glow that is mostly covered must still be found as one thing.

    A card in the middle of a fan shows only its top bar and two slivers of
    its side borders; the rest is behind its neighbours. Those pieces have a
    gap between them, and if the join does not bridge that gap they stay
    separate - three short pieces instead of one tall outline, which then
    fall foul of any minimum height and vanish entirely.
    """
    from pixie.system import screen as screen_mod

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    # The exact shape from a real hand: a 772x105 top bar, then a 57px gap,
    # then two slivers running down to the bottom.
    frame = np.zeros((320, 1000, 3), dtype=np.uint8)
    glow = hsv(90, 250, 250)
    frame[30:135, 40:812] = glow        # top bar
    frame[192:320, 31:45] = glow        # left sliver, after a 57px gap
    frame[197:320, 372:395] = glow      # right sliver

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 1000, 320), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=39, match="hue", order="leftmost")
        in_pieces = screen_mod.find_colors(join=25, **common)
        joined = screen_mod.find_colors(join=40, **common)
        filtered = screen_mod.find_colors(join=40, min_height=90, **common)
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Hidden outline  : {len(in_pieces)} pieces at join 25, "
          f"{len(joined)} at join 40")

    if len(in_pieces) < 2:
        problems.append("the pieces joined up at 25 anyway, so the gap this "
                        "test is about is not being reproduced")
    if len(joined) != 1:
        problems.append(f"join 40 gave {len(joined)} patches, expected the "
                        "pieces to become one outline")
        return problems
    if joined[0].height < 250:
        problems.append(f"the joined outline is only {joined[0].height}px tall, "
                        "so the pieces did not all come together")
    # And a height filter must not then throw the whole thing away.
    if not filtered:
        problems.append("a minimum height dropped the joined outline")
    # Each piece on its own is short enough that the filter would have killed
    # it, which is exactly how this went wrong.
    if any(piece.height >= 90 for piece in in_pieces):
        print(f"                  (tallest loose piece "
              f"{max(p.height for p in in_pieces)}px)")
    return problems


def _check_where_a_patch_sits_can_be_required() -> list[str]:
    """Position survives what color cannot.

    The cards fan wider with a bigger hand and tilt every which way, so their
    size, their angle and the gaps between them all move. What does not move
    is that a hand sits at the bottom of the screen: every card runs off the
    bottom edge, so every card's glow reaches the bottom of an area drawn over
    the hand. A lit prop in the background never does, whatever color it is.

    This is the one discriminator that holds when the background changes,
    which is why it is worth having as a setting rather than as more tuning.
    """
    from pixie.system import screen as screen_mod

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    glow = hsv(90, 250, 250)
    frame = np.zeros((313, 1600, 3), dtype=np.uint8)
    # A lit prop, floating in the background: card-sized, card-colored, and
    # nowhere near the bottom. Every size and color limit would pass it.
    frame[30:250, 100:600] = glow
    # Two cards at different angles, as a fan gives them, both running off
    # the bottom of the area the way a hand always does.
    for top, left in ((40, 800), (12, 1180)):
        frame[top:313, left : left + 260] = glow

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 1600, 313), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=39, match="hue", order="leftmost")
        anywhere = screen_mod.find_colors(**common)
        grounded = screen_mod.find_colors(must_reach="bottom", **common)
        _, rejected, _ = screen_mod._search(
            (0, 0, 1600, 313), (37, 254, 254), 14, 39, "hue",
            order="leftmost", must_reach="bottom")
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Must reach edge : {len(anywhere)} patches anywhere, "
          f"{len(grounded)} that run off the bottom")

    if len(anywhere) != 3:
        problems.append(f"the sample gave {len(anywhere)} patches, expected 3")
        return problems
    if anywhere[0].left != 100:
        problems.append("the floating prop was not the leftmost, so this test "
                        "is not reproducing the problem it is about")
    if len(grounded) != 2:
        problems.append(f"requiring the bottom left {len(grounded)} patches, "
                        "expected the two cards")
        return problems
    if grounded[0].left != 800:
        problems.append(f"the leftmost survivor starts at {grounded[0].left}, "
                        "expected the leftmost card at 800")
    print(f"                  leftmost is now the card at {grounded[0].left}, "
          f"not the prop at {anywhere[0].left}")

    # Rejections say why, so What matches? can show it rather than a patch
    # silently vanishing.
    if not any("does not reach the bottom" in why for _, why in rejected):
        problems.append(f"the prop was dropped without saying why: "
                        f"{[why for _, why in rejected]}")

    # Cards of different heights and angles all still qualify, because all of
    # them touch the bottom. That is the whole point.
    if {hit.height for hit in grounded} == {grounded[0].height}:
        problems.append("both cards came out the same height, so this is not "
                        "testing that differing angles all still qualify")
    return problems


def _check_joining_sideways_is_its_own_distance() -> list[str]:
    """Reaching up must not mean reaching sideways by the same amount.

    An outline broken by an overlapping neighbour arrives as a top bar with
    slivers of its sides below it: pieces stacked *above one another*. Anything
    else glowing the same color is *beside* it. A square reach cannot tell
    those apart, so the reach a broken outline needs is exactly the reach that
    lets a lit prop 40px to the left take over the patch - and with it the left
    edge, which is what the click aims at.

    The numbers are from a real hand: a lit bottle in the background about 40px
    clear of a card's outline, pulled in by a join of 40.
    """
    from pixie.system import screen as screen_mod

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    glow = hsv(90, 250, 250)
    frame = np.zeros((313, 1600, 3), dtype=np.uint8)
    # A lit prop in the background: beside the cards, overlapping them in
    # height, and 40px clear of the nearest one.
    frame[0:50, 460:500] = glow
    # A card whose outline is broken the way a fan breaks it: a top bar, then
    # a 57px gap, then slivers of its two sides.
    frame[20:125, 540:1020] = glow
    frame[182:310, 540:556] = glow
    frame[182:310, 1004:1020] = glow

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 1600, 313), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=39, match="hue",
                      order="leftmost", join=40)
        square = screen_mod.find_colors(**common)
        upright = screen_mod.find_colors(join_across=0, **common)
        filtered = screen_mod.find_colors(join_across=0, min_width=200, **common)
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Sideways join   : square reach -> {len(square)} patch "
          f"{square[0].width}x{square[0].height} at {square[0].left}; "
          f"upright only -> {len(upright)} patches")

    # The old behaviour, which is what a sequence saved before this still gets.
    if len(square) != 1 or square[0].left != 460:
        problems.append(f"a square reach gave {[(h.left, h.width) for h in square]}"
                        ", expected one patch starting at the prop (460)")
    # With no sideways reach the prop stands alone, and the outline still
    # comes together through the bar above its slivers.
    if len(upright) != 2:
        problems.append(f"an upright-only reach gave {len(upright)} patches, "
                        "expected the prop and the outline separately")
        return problems
    card = [hit for hit in upright if hit.left == 540]
    if not card:
        problems.append(f"the outline did not come together: "
                        f"{[(h.left, h.width, h.height) for h in upright]}")
    elif card[0].width < 470 or card[0].height < 280:
        problems.append(f"the outline came out {card[0].width}x{card[0].height}, "
                        "so its pieces did not all join up the way they should")
    # And the prop, alone, is nothing like card-shaped.
    if len(filtered) != 1 or filtered[0].left != 540:
        problems.append(f"a width limit did not leave just the card: "
                        f"{[(h.left, h.width) for h in filtered]}")
    else:
        print(f"                  card survives {filtered[0].width}x"
              f"{filtered[0].height} at {filtered[0].left}, prop dropped")

    # A file saved before this setting existed must behave exactly as it did.
    older = engine_mod.Sequence._migrate([{"type": "wait_for_color_in_area",
                                           "join": 40}])
    if older[0].get("join_across") != 40:
        problems.append(f"an older file did not inherit its join sideways: {older}")

    # Whatever the reach, a patch is measured on the pixels that are really
    # there. Grouping happens on a fattened copy of the mask, and measuring
    # that copy instead reported a patch wider than it was, with its left edge
    # half the reach too far left - which is where a left-edge anchor clicks.
    solid = np.zeros((300, 400, 3), dtype=np.uint8)
    solid[80:140, 100:220] = (200, 40, 40)
    screen_mod.grab = lambda _region=None: solid
    bounds = screen_mod.virtual_bounds
    screen_mod.virtual_bounds = lambda: (0, 0, 400, 300)
    try:
        shape = dict(region=(0, 0, 400, 300), target_rgb=(40, 40, 200),
                     tolerance=30, min_pixels=10, match="rgb")
        for reach_down, reach_across in ((0, 0), (10, 0), (0, 8), (10, 8)):
            found = screen_mod.find_colors(join=reach_down,
                                           join_across=reach_across, **shape)
            if not found:
                problems.append(f"join {reach_down}/{reach_across} found nothing")
                continue
            got = (found[0].width, found[0].height, found[0].left, found[0].top)
            if got != (120, 60, 100, 80):
                problems.append(
                    f"join {reach_down} up and down, {reach_across} sideways "
                    f"measured the shape as {got[0]}x{got[1]} at {got[2]},{got[3]} "
                    "instead of 120x60 at 100,80 - it measured the fattened "
                    "copy rather than the real pixels")
    finally:
        screen_mod.grab = original
        screen_mod.virtual_bounds = bounds
    print("                  a solid 120x60 measures 120x60 at every reach")
    return problems


def _check_specks_are_dropped_before_joining() -> list[str]:
    """A scatter of specks must not add up to a patch.

    Joining gathers anti-aliased noise as readily as it gathers the pieces of
    a real outline. From a real run: 45 pieces totalling 476 pixels, spread
    over a 500x110 box, reported as a find and clicked. Every limit on the
    step passed, because they are all measured on the assembled shape - 476
    pixels is over the 39 floor, and 500x110 is over both size floors.

    Dropping the specks *before* joining is the only place this can be caught.
    """
    from pixie.system import screen as screen_mod

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    glow = hsv(90, 250, 250)
    frame = np.zeros((320, 900, 3), dtype=np.uint8)
    # 45 specks of about 10 pixels each, scattered the way anti-aliasing is.
    spread = np.random.default_rng(7)
    for n in range(45):
        x = 60 + (n * 11) % 500
        y = 40 + (n * 37) % 110
        frame[y : y + 3, x : x + 4] = glow
    # ...and, well away from them, a real outline made of chunky fragments.
    for y0, y1, x0, x1 in ((40, 60, 400, 760), (260, 280, 400, 760),
                           (40, 280, 400, 420), (40, 280, 740, 760)):
        frame[y0:y1, x0:x1] = glow

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 900, 320), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=39, match="hue",
                      order="leftmost", join=40)
        noisy = screen_mod.find_colors(**common)
        clean = screen_mod.find_colors(min_piece=100, **common)
        # The outline's own fragments are chunky, so a floor well above speck
        # size must still leave it alone.
        generous = screen_mod.find_colors(min_piece=1000, **common)
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Specks          : {len(noisy)} patches with every piece kept, "
          f"{len(clean)} once pieces under 100px go")
    if not noisy:
        return ["the specks did not survive at all, so this test is not "
                "reproducing the problem it is about"]
    if noisy[0].left >= 400:
        problems.append("the specks were not picked ahead of the outline, so "
                        "this no longer reproduces the failure")
    if len(clean) != 1:
        problems.append(f"dropping specks left {len(clean)} patches, expected "
                        "just the outline")
        return problems
    if clean[0].left < 380 or clean[0].width < 300:
        problems.append(f"what survived is {clean[0].width}px at "
                        f"{clean[0].left}, which is not the outline")
    print(f"                  outline survives at {clean[0].left}, "
          f"{clean[0].width}x{clean[0].height}, {clean[0].pieces} piece(s)")

    if not generous:
        problems.append("a 1000px floor threw the real outline away too")
    return problems


def _check_the_shape_split_is_suggested() -> list[str]:
    """Patches of two clear shapes must point at the setting that splits them.

    A background is full of things the same color as the thing you want -- a
    lit beam, a rim light, a glowing prop -- but hardly ever the same shape.
    These are the real sizes from one hand of cards: two slivers of a lit beam
    running down the background, and the cards themselves.
    """
    from pixie.system import screen as screen_mod

    def hit(width, height):
        return screen_mod.ColorHit(0, 0, 0, 0, width, height, width * height)

    beams_and_cards = [hit(45, 306), hit(776, 306), hit(31, 188)]
    split = screen_mod.suggest_size_filter(beams_and_cards)

    problems = []
    if split is None:
        return ["45px beams next to 776px cards produced no advice at all"]
    print(f"Shape split     : {split.drops} up to {split.largest_dropped}px "
          f"and {split.keeps} from {split.smallest_kept}px -> min "
          f"{split.field} {split.value}")
    if split.field != "width":
        problems.append(f"split by {split.field}, but the beams and the cards "
                        "are the same height - width is the one that separates them")
    if not 45 < split.value < 776:
        problems.append(f"a minimum width of {split.value} does not sit "
                        "between the two groups")
    if (split.keeps, split.drops) != (1, 2):
        problems.append(f"keeps {split.keeps} and drops {split.drops}, "
                        "expected to keep the 1 card and drop the 2 beams")

    # Patches that are all much of a muchness have no split to offer, and
    # inventing one would send you off tuning a filter that cannot help.
    if screen_mod.suggest_size_filter([hit(480, 300), hit(486, 290),
                                       hit(470, 305)]) is not None:
        problems.append("three cards of the same size were said to fall into "
                        "two groups")
    if screen_mod.suggest_size_filter([hit(45, 306)]) is not None:
        problems.append("a single patch was split into two groups")
    return problems


def _check_a_speck_swept_up_by_the_join() -> list[str]:
    """Joining can rescue something the size filters were there to reject.

    Size is only measured after joining, which is the whole point: an outline
    broken into fragments is short in pieces and tall together. The cost is
    that a speck of the same color near enough to be swept up inherits the
    outline's size, passes every filter, and then owns whichever edge of the
    patch it lies on - so aiming at that edge aims at the speck.

    Nothing about the patch looks wrong when this happens. The only way to
    notice is to be told how many pieces went into it.
    """
    from pixie.system import screen as screen_mod

    def hsv(h, s, v):
        return tuple(int(c) for c in cv2.cvtColor(
            np.array([[[h, s, v]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0])

    frame = np.zeros((313, 1200, 3), dtype=np.uint8)
    glow = hsv(90, 250, 250)
    frame[20:310, 120:600] = glow       # the card outline we actually want
    frame[0:58, 16:68] = glow           # a lit prop in the background, 52px off

    original = screen_mod.grab
    screen_mod.grab = lambda _region=None: frame
    try:
        common = dict(region=(0, 0, 1200, 313), target_rgb=(37, 254, 254),
                      tolerance=14, min_pixels=39, match="hue",
                      order="leftmost", min_height=90)
        alone = screen_mod.find_colors(join=0, **common)
        swept = screen_mod.find_colors(join=40, **common)
    finally:
        screen_mod.grab = original

    problems = []
    print(f"Swept-up speck  : join 0 keeps {len(alone)} patch, "
          f"join 40 keeps {len(swept)} of {swept[0].pieces if swept else 0} "
          "pieces")

    # On its own the speck is 58px tall and the filter drops it.
    if len(alone) != 1 or alone[0].left != 120:
        problems.append("without joining, the speck was not filtered out on "
                        f"its own - kept {[(h.left, h.height) for h in alone]}")
    if len(swept) != 1:
        problems.append(f"joining gave {len(swept)} patches, expected 1")
        return problems
    if swept[0].pieces != 2:
        problems.append(f"the patch reports {swept[0].pieces} pieces, "
                        "expected 2 - the speck is not being counted")
    if swept[0].left != 16:
        problems.append("the speck was not actually swept in, so this test no "
                        "longer reproduces the problem it is about")
    print(f"                  left edge moved {120 - swept[0].left}px onto the "
          "speck, which the piece count now reports")

    # And the engine has to say so at the click, where the aim is known.
    said: list[str] = []
    runner = engine_mod.Engine(engine_mod.Sequence(), emit=lambda event: said.append(
        str(event.get("message", ""))) if event.get("level") == "warn" else None)
    runner._remember_color(swept[0])
    runner._aim_warning("left")
    if not any("2 separate pieces" in line for line in said):
        problems.append(f"aiming at an edge of a joined patch said nothing "
                        f"useful: {said}")
    said.clear()
    runner._aim_warning("middle")
    if said:
        problems.append(f"aiming at the middle warned needlessly: {said}")
    return problems


def _check_a_section_with_nothing_switched_on() -> list[str]:
    """A section whose steps are all off must not spin forever.

    Nothing runs, so nothing fails, so nothing ever triggers the move to the
    next section - the engine just went round that section for ever, printing
    nothing. Switching off the last steps of a sequence is an ordinary thing
    to do, and it should not hang.
    """
    ran: list[str] = []

    class Counting(engine_mod.Engine):
        def run_step(self, step):
            ran.append(step.get("name"))
            if len(ran) > 20:
                raise engine_mod.Aborted("this should never be reached")
            # Fails, so the first section hands over to the empty one, which
            # is the thing being tested.
            return "timeout"

    steps = [
        {"type": "section", "name": "Does things", "enabled": True},
        {"type": "press_key", "name": "work", "enabled": True, "key": "Q",
         "on_timeout": "next_section", "pause": [0, 0]},
        {"type": "section", "name": "Switched off", "enabled": True},
        {"type": "press_key", "name": "never", "enabled": False, "key": "Q"},
    ]
    sequence = engine_mod.Sequence(
        name="empty", steps=steps,
        settings=engine_mod.Settings(step_pause_min=0, step_pause_max=0,
                                     section_pause_min=0, section_pause_max=0,
                                     cycle_pause_min=0, cycle_pause_max=0,
                                     failsafe_corner=False))

    messages: list[str] = []
    runner = Counting(sequence, emit=lambda e: messages.append(e.get("message", "")),
                      dry_run=True)
    runner.run(max_cycles=1)

    problems = []
    print(f"Empty section   : finished after running {ran}, "
          f"{runner.cycles_completed} cycle(s)")
    if runner.cycles_completed != 1:
        problems.append(f"the run did not finish cleanly: "
                        f"{runner.cycles_completed} cycles")
    if "never" in ran:
        problems.append("a switched-off step was run")
    if not any("nothing in 'Switched off' is switched on" in m for m in messages):
        problems.append("it did not say why it moved on")

    # And it should be said up front, before the run starts.
    complaints = sequence.warnings()
    if not any("Switched off" in c for c in complaints):
        problems.append(f"the empty section was not warned about: {complaints}")

    # A section with steps in it must not be flagged.
    fine = engine_mod.Sequence(name="fine", steps=steps[:2])
    if any("no steps switched on" in c for c in fine.warnings()):
        problems.append(f"a perfectly good section was flagged: {fine.warnings()}")
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
    # A window message cannot tell the main Enter from the numpad one - both
    # report VK_RETURN, so both arrive here as "return". Which one we actually
    # sent is checked below, at the flags.
    if "return" not in got:
        problems.append(f"expected Enter, got {received}")
    return problems


def _check_enter_is_the_main_one() -> list[str]:
    """Enter must go out as the main Enter, not the numpad Enter.

    The two keys share a virtual-key code and a scan code, and are told apart
    only by the extended flag, which puts an E0 prefix on the scan code. Window
    messages hide the difference entirely; raw input, which is what games read,
    does not. Flagging Enter as extended therefore looked completely fine
    everywhere except in the one place it mattered, where the game saw a key
    nobody had bound and did nothing.

    The rule reads backwards for this key: extended means numpad here, whereas
    for the arrows and the navigation cluster extended means the main key.
    """
    from pixie.system import keyboard as kb

    sent: list[tuple[int, int, int]] = []
    real_send = kb._send
    kb._send = lambda vk, scan, flags: sent.append((vk, scan, flags))
    try:
        for name in ("Enter", "NumpadEnter", "Up", "Q"):
            sent.clear()
            kb.press(name, hold=0)
            if not sent:
                return [f"pressing {name} sent nothing at all"]
            _, _, flags = sent[0]
            extended = bool(flags & kb.KEYEVENTF_EXTENDEDKEY)
            wanted = name in ("NumpadEnter", "Up")
            if extended != wanted:
                verb = "was" if extended else "was not"
                return [f"{name} {verb} flagged extended, which makes a game "
                        f"read it as {'the numpad' if extended else 'a different'} key"]
    finally:
        kb._send = real_send

    print("Enter identity : main Enter (no E0 prefix), numpad Enter separate")
    return []


def _check_repeats_are_not_metronomic() -> list[str]:
    """Repeated clicks and taps take their gap from a range, drawn each time.

    A double-click was 60ms, written into mouse.py and never passed by the
    engine, so every double-click in a session was identical to the
    millisecond. A repeated key press was editable but a single fixed number,
    so its gaps were identical to each other.

    The gap is handed over as a function rather than a number, which is what
    makes each one in a run its own draw rather than the same one repeated.
    """
    from pixie.system import keyboard as kb
    from pixie.system import mouse as mouse_mod

    problems = []
    runner = engine_mod.Engine(engine_mod.Sequence(name="x"), dry_run=False)

    def gaps_from(stamps):
        return [(b - a) * 1000 for a, b in zip(stamps[::2], stamps[2::2])]

    # Clicks, with the button held for no time at all, so what is measured
    # is the gap and nothing else.
    sent: list[float] = []
    real_send, real_move = mouse_mod._send, mouse_mod.move_to
    mouse_mod._send = lambda *_a, **_k: sent.append(time.perf_counter())
    mouse_mod.move_to = lambda *_a: None
    try:
        step = {"type": "click_point", "clicks": 6}
        mouse_mod.click(0, 0, clicks=6, interval=runner._repeat_gap(step),
                        before=0, hold=0)
        clicks = gaps_from(sent)

        sent.clear()
        step["gap"] = [0.25, 0.35]
        mouse_mod.click(0, 0, clicks=4, interval=runner._repeat_gap(step),
                        before=0, hold=0)
        own = gaps_from(sent)
    finally:
        mouse_mod._send, mouse_mod.move_to = real_send, real_move

    if len({round(gap) for gap in clicks}) < 2:
        problems.append(f"six clicks were spaced identically ({clicks}), so "
                        "the gap is not being drawn per click")
    if not all(50 - 12 <= gap <= 120 + 15 for gap in clicks):
        problems.append(f"click gaps {[round(g) for g in clicks]}ms fall "
                        "outside the sequence default of 50-120ms")
    if not all(250 - 12 <= gap <= 350 + 15 for gap in own):
        problems.append(f"a step asking for 250-350ms got "
                        f"{[round(g) for g in own]}ms, so its own range is "
                        "not being used")

    # Key taps, where nothing is held down, so the gap is the gap.
    taps: list[float] = []
    real_key = kb._send
    kb._send = lambda *_a: taps.append(time.perf_counter())
    try:
        kb.press("Q", 6, runner._repeat_gap({"type": "press_key"}), hold=0)
    finally:
        kb._send = real_key
    key_gaps = gaps_from(taps)
    if len({round(gap) for gap in key_gaps}) < 2:
        problems.append(f"six taps were spaced identically ({key_gaps})")
    if not all(50 - 12 <= gap <= 120 + 15 for gap in key_gaps):
        problems.append(f"tap gaps {[round(g) for g in key_gaps]}ms fall "
                        "outside the sequence default of 50-120ms")

    # A file written before the gap was a range keeps the pace it had.
    older = engine_mod.Sequence._migrate(
        [{"type": "press_key", "key": "Q", "interval": 0.08}])
    if older[0].get("gap") != [0.08, 0.08] or "interval" in older[0]:
        problems.append(f"an older file did not carry its gap over: {older}")

    print(f"Repeat gaps     : clicks {[round(g) for g in clicks]}ms, "
          f"taps {[round(g) for g in key_gaps]}ms, none the same twice")
    return problems


def _check_every_delay_around_a_press_varies() -> list[str]:
    """Nothing about a click should be the same length twice.

    A click has four timings: arriving before pressing, the button held down,
    the gap to the next click, and that one held down. Three of the four were
    written into mouse.py as literals the engine never passed, so every click
    Pixie made carried an identical signature either side of the one gap that
    did vary.
    """
    from pixie.system import keyboard as kb
    from pixie.system import mouse as mouse_mod

    problems = []
    runner = engine_mod.Engine(engine_mod.Sequence(name="x"), dry_run=False)
    stamps: list[float] = []
    real_send, real_move = mouse_mod._send, mouse_mod.move_to
    mouse_mod._send = lambda *_a, **_k: stamps.append(time.perf_counter())
    mouse_mod.move_to = lambda *_a: stamps.append(time.perf_counter())

    arrivals, holds = [], []
    try:
        step = {"type": "click_point", "clicks": 1}
        for _attempt in range(6):
            stamps.clear()
            mouse_mod.click(0, 0, clicks=1, before=runner._settle_before(),
                            hold=runner._press_hold(step))
            arrivals.append((stamps[1] - stamps[0]) * 1000)
            holds.append((stamps[2] - stamps[1]) * 1000)

        # A step's own hold beats the sequence-wide one.
        stamps.clear()
        step["hold"] = [0.30, 0.34]
        mouse_mod.click(0, 0, clicks=1, before=runner._settle_before(),
                        hold=runner._press_hold(step))
        own = (stamps[2] - stamps[1]) * 1000
    finally:
        mouse_mod._send, mouse_mod.move_to = real_send, real_move

    settings = runner.sequence.settings
    for name, measured, low, high in (
            ("arrive-before-pressing", arrivals,
             settings.press_settle_min, settings.press_settle_max),
            ("button held down", holds,
             settings.press_hold_min, settings.press_hold_max)):
        if len({round(value) for value in measured}) < 2:
            problems.append(f"{name} was the same on all six clicks "
                            f"({[round(v) for v in measured]}ms)")
        if not all(low * 1000 - 12 <= value <= high * 1000 + 20
                   for value in measured):
            problems.append(f"{name} came out {[round(v) for v in measured]}ms, "
                            f"outside {low * 1000:.0f}-{high * 1000:.0f}ms")
    if not 290 <= own <= 365:
        problems.append(f"a step asking to hold 300-340ms held {own:.0f}ms")

    # Keys use the same range, so a tap is held like a button.
    taps: list[float] = []
    real_key = kb._send
    kb._send = lambda *_a: taps.append(time.perf_counter())
    try:
        kb.press("Q", 5, runner._repeat_gap({}), runner._press_hold({}))
    finally:
        kb._send = real_key
    tap_holds = [(b - a) * 1000 for a, b in zip(taps[::2], taps[1::2])]
    if len({round(value) for value in tap_holds}) < 2:
        problems.append(f"five taps were all held the same ({tap_holds}ms)")

    # A file written when the hold was one number keeps that length exactly.
    older = engine_mod.Sequence._migrate([{"type": "press_key", "hold": 0.1}])
    if older[0].get("hold") != [0.1, 0.1]:
        problems.append(f"an older file lost its hold: {older[0].get('hold')!r}")

    print(f"Press timing    : arrive {[round(v) for v in arrivals[:4]]}ms, "
          f"held {[round(v) for v in holds[:4]]}ms, none repeated")
    return problems


def _check_the_cursor_travels_to_a_click() -> list[str]:
    """Gliding has to cover the journey in, not only the journey out.

    It was a parking setting, so the cursor crossed the screen smoothly on its
    way away from a click and teleported on its way to one. The approach is
    the half an application watches: a hover state opens because the pointer
    arrived over something, and it cannot arrive over anything it skipped.
    """
    from pixie.system import mouse as mouse_mod

    problems = []
    visited: list[tuple[int, int]] = []
    real_move, real_send, real_pos = (mouse_mod.move_to, mouse_mod._send,
                                      mouse_mod.position)
    mouse_mod.move_to = lambda x, y: visited.append((x, y))
    mouse_mod._send = lambda *_a, **_k: None
    mouse_mod.position = lambda: visited[-1] if visited else (0, 0)

    def clicks_from(there: tuple[int, int]) -> list[tuple[int, int]]:
        visited.clear()
        visited.append((0, 0))
        runner._click(there[0], there[1], {"type": "click_point"}, "a thing")
        return visited[1:]

    try:
        sequence = engine_mod.Sequence(
            name="travel", settings=engine_mod.Settings(glide=False,
                                                        park_mouse="off"))
        runner = engine_mod.Engine(sequence, dry_run=False)
        warped = clicks_from((900, 600))

        sequence.settings.glide = True
        glided = clicks_from((900, 600))
    finally:
        (mouse_mod.move_to, mouse_mod._send,
         mouse_mod.position) = real_move, real_send, real_pos

    if len(warped) != 1:
        problems.append(f"with gliding off a click took {len(warped)} moves, "
                        "expected one straight there")
    if len(glided) < 8:
        problems.append(f"with gliding on a click still took only "
                        f"{len(glided)} moves, so it is warping to the target")
    if glided and glided[-1] != (900, 600):
        problems.append(f"a glided click finished at {glided[-1]}, not on the "
                        "target")
    # It has to actually pass over the ground between, not jump most of it.
    if glided and any(point == (900, 600) for point in glided[:len(glided) // 2]):
        problems.append("the glide arrived in its first half, so it is not "
                        "crossing the distance")

    older = engine_mod.Settings.from_dict({"park_glide": True})
    if not older.glide:
        problems.append("a sequence that had gliding on lost it in the rename")

    # A step can override the sequence either way, and "inherit" has to mean
    # inherit, or switching the sequence-wide setting off would quietly
    # un-set every step that had been left alone.
    wanted = {
        (False, "inherit"): "warp", (True, "inherit"): "glide",
        (False, "glide"): "glide", (True, "glide"): "glide",
        (False, "warp"): "warp", (True, "warp"): "warp",
    }
    runner = engine_mod.Engine(engine_mod.Sequence(name="mix"), dry_run=False)
    real_pos = mouse_mod.position
    mouse_mod.position = lambda: (0, 0)
    try:
        for (sequence_wide, per_step), expected in wanted.items():
            runner.sequence.settings.glide = sequence_wide
            got = runner._travel_to({"type": "click_point",
                                     "travel": per_step}, 900, 600)
            actual = "warp" if got is None else "glide"
            if actual != expected:
                problems.append(
                    f"sequence gliding {'on' if sequence_wide else 'off'} with "
                    f"a step set to {per_step!r} gave {actual}, wanted {expected}")
    finally:
        mouse_mod.position = real_pos

    print(f"Travel to click : warping {len(warped)} move, gliding "
          f"{len(glided)} moves; 6 step/sequence combinations all correct")
    return problems


def _check_cursor_travel_scales_with_distance() -> list[str]:
    """A long move must take longer than a short one.

    The glide divided a fixed quarter of a second by however many steps the
    distance needed, so the duration was the same whatever the distance and
    the *speed* was whatever fell out: 159 pixels a second across 40px, and
    24,000 across a two-monitor desktop. Speed is drawn now, and the duration
    follows the distance.
    """
    from pixie.system import mouse as mouse_mod

    problems = []
    runner = engine_mod.Engine(engine_mod.Sequence(name="x"), dry_run=False)
    real_send, real_pos = mouse_mod._send, mouse_mod.position
    mouse_mod._send = lambda *_a, **_k: None
    mouse_mod.position = lambda: (0, 0)
    try:
        times = {}
        for distance in (50, 500, 3000):
            drawn = [runner._travel_time(distance, 0) for _ in range(8)]
            times[distance] = drawn
    finally:
        mouse_mod._send, mouse_mod.position = real_send, real_pos

    short, medium, far = (sum(times[d]) / len(times[d]) for d in (50, 500, 3000))
    if not short < medium < far:
        problems.append(f"travel time does not follow distance: 50px took "
                        f"{short:.3f}s, 500px {medium:.3f}s, 3000px {far:.3f}s")
    if len({round(value, 4) for value in times[500]}) < 2:
        problems.append("every 500px move took exactly the same time")
    for distance, drawn in times.items():
        for value in drawn:
            if not engine_mod.TRAVEL_MIN_SECONDS <= value <= engine_mod.TRAVEL_MAX_SECONDS:
                problems.append(f"a {distance}px move was given {value:.3f}s, "
                                "outside the clamps")
                break
    # The speed a long move ends up at must at least be in the realm of a hand.
    fastest = 3000 / min(times[3000])
    if fastest > 20000:
        problems.append(f"a 3000px move still crosses at {fastest:.0f} px/sec")

    print(f"Cursor travel   : 50px {short * 1000:.0f}ms, 500px "
          f"{medium * 1000:.0f}ms, 3000px {far * 1000:.0f}ms")
    return problems


def _check_nothing_grows_forever_during_a_run() -> list[str]:
    """What a run remembers has to stop growing, or hours cost more than minutes.

    The per-step size history grew by one number on every successful find and
    was re-sorted on every one too, so a step checked every couple of seconds
    added tens of thousands a day and the cost of using them climbed all run.
    It keeps a window now, which also means the yardstick follows a target
    that legitimately changes size rather than being pinned to this morning.
    """
    class Hit:
        def __init__(self, pixels):
            self.pixels = pixels

    problems = []
    runner = engine_mod.Engine(engine_mod.Sequence(name="x"), dry_run=True)
    step = {"type": "wait_for_color_in_area", "min_pixels": 40}

    for n in range(engine_mod.MATCH_HISTORY * 40):
        runner._odd_size(step, Hit(10_000 + (n % 7)))

    held = sum(len(seen) for seen in runner._match_sizes.values())
    if held > engine_mod.MATCH_HISTORY:
        problems.append(f"after {engine_mod.MATCH_HISTORY * 40} finds the step "
                        f"remembers {held} sizes, over its own cap of "
                        f"{engine_mod.MATCH_HISTORY}")

    # It still has to do its job: a find far smaller than usual gets called out.
    said: list[str] = []
    runner.emit = lambda event: said.append(event.get("message", ""))
    runner._odd_size(step, Hit(71))
    if not any("far smaller" in message for message in said):
        problems.append("a find a hundred times smaller than usual was not "
                        "called out, so the window broke the check it feeds")

    # ...and the window follows a target that genuinely changes size, rather
    # than nagging forever about a new normal.
    quiet = engine_mod.Engine(engine_mod.Sequence(name="y"), dry_run=True)
    for _ in range(engine_mod.MATCH_HISTORY * 2):
        quiet._odd_size(step, Hit(10_000))
    for _ in range(engine_mod.MATCH_HISTORY * 2):
        quiet._odd_size(step, Hit(600))          # the target really did shrink
    complaints: list[str] = []
    quiet.emit = lambda event: complaints.append(event.get("message", ""))
    quiet._odd_size(step, Hit(600))
    if any("far smaller" in message for message in complaints):
        problems.append("a target that settled at a new smaller size is still "
                        "being reported as odd, so the yardstick never moved on")

    print(f"Run growth      : {engine_mod.MATCH_HISTORY * 40} finds -> "
          f"{held} remembered, still spots an odd one, follows a new normal")
    return problems


def _check_a_bad_stop_key_does_not_kill_the_run() -> list[str]:
    """A stop key Windows cannot watch is a bad setting, not a dead run.

    Only a short list of keys can be watched for globally. The guard asked
    about whatever the sequence named, several times a second, and an
    unwatchable name raised out of the guard, through run_cycle, and into the
    catch-all in run() -- so the sequence died with 'Unexpected error' before
    running a single step. The opening log line already allowed for no stop
    key at all, so the two halves disagreed.
    """
    def attempt(key: str):
        messages: list[str] = []
        sequence = engine_mod.Sequence(
            name="stopping",
            steps=[{"type": "press_key", "name": "work", "enabled": True,
                    "key": "Q"}],
            settings=engine_mod.Settings(
                abort_key=key, failsafe_corner=False,
                step_pause_min=0, step_pause_max=0,
                cycle_pause_min=0, cycle_pause_max=0))
        runner = engine_mod.Engine(
            sequence, emit=lambda e: messages.append(e.get("message", "")),
            dry_run=True)
        runner.run(max_cycles=1)
        return runner, messages

    problems = []
    for key in ("off", "", "F13", "Enter", "Ctrl"):
        runner, messages = attempt(key)
        if any("Unexpected error" in m for m in messages):
            problems.append(f"a stop key of {key!r} killed the run outright")
        elif not runner.cycles_completed:
            problems.append(f"a stop key of {key!r} stopped the run completing")
    # A name that cannot be watched has to say so, or it looks like a working
    # stop key right up until you need it.
    _runner, messages = attempt("F13")
    if not any("watch for" in m for m in messages):
        problems.append("an unwatchable stop key was accepted in silence")
    # ...once, not several times a second.
    if len([m for m in messages if "watch for" in m]) > 1:
        problems.append("the unwatchable stop key was reported more than once")

    # And a real one still stops things.
    working, _messages = attempt("F8")
    if not working.cycles_completed:
        problems.append("a usable stop key stopped the run from completing")

    print("Stop key        : unwatchable names warn once and the run carries on")
    return problems


def _check_tidying_never_deletes_a_picture_in_use() -> list[str]:
    """tidy_images --apply deletes, so being wrong here loses work.

    It decided what was unused by comparing the path a sequence stores against
    one it built from the folder, as plain strings. The same picture can be
    written several ways that all mean the same file: relative or absolute,
    either slash, any case. A picture written one way and looked for another
    matched nothing, so it was reported as used by nobody and deleted, while a
    step was still pointing at it.
    """
    import json
    import sys as sys_mod
    import tempfile
    from pathlib import Path as PathType

    tools = PathType(__file__).resolve().parent.parent / "tools"
    if str(tools) not in sys_mod.path:
        sys_mod.path.insert(0, str(tools))
    import tidy_images

    import pixie.paths as paths_mod

    kept = []
    problems = []
    saved = (paths_mod.APP_DIR, tidy_images.IMAGES_DIR, tidy_images.SEQUENCES_DIR)
    try:
        for description, spelling in (
                ("relative", "images/button.png"),
                ("backslashes", "images\\button.png"),
                ("absolute", None),
                ("other case", "Images/Button.png")):
            with tempfile.TemporaryDirectory() as temp:
                root = PathType(temp)
                (root / "images").mkdir()
                (root / "sequences").mkdir()
                picture = root / "images" / "button.png"
                picture.write_bytes(b"x")
                stored = str(picture) if spelling is None else spelling

                paths_mod.APP_DIR = root
                tidy_images.IMAGES_DIR = root / "images"
                tidy_images.SEQUENCES_DIR = root / "sequences"
                (root / "sequences" / "job.json").write_text(
                    json.dumps({"name": "job",
                                "steps": [{"type": "click_image",
                                           "image": stored}]}),
                    encoding="utf-8")

                used, _count = tidy_images.referenced()
                unused = [p for p in tidy_images.IMAGES_DIR.iterdir()
                          if p.is_file()
                          and tidy_images.same_file_key(p) not in used]
                if unused:
                    problems.append(
                        f"a picture stored as {description} ({stored!r}) was "
                        "reported unused while a step still points at it, so "
                        "--apply would delete it")
                else:
                    kept.append(description)

        # ...and something genuinely unreferenced is still found, or the tool
        # would be safe by the simple method of never finding anything.
        with tempfile.TemporaryDirectory() as temp:
            root = PathType(temp)
            (root / "images").mkdir()
            (root / "sequences").mkdir()
            (root / "images" / "leftover.png").write_bytes(b"x")
            paths_mod.APP_DIR = root
            tidy_images.IMAGES_DIR = root / "images"
            tidy_images.SEQUENCES_DIR = root / "sequences"
            (root / "sequences" / "job.json").write_text(
                json.dumps({"name": "job", "steps": []}), encoding="utf-8")
            used, _count = tidy_images.referenced()
            if not [p for p in tidy_images.IMAGES_DIR.iterdir()
                    if tidy_images.same_file_key(p) not in used]:
                problems.append("a picture no sequence mentions was not "
                                "reported as unused, so the tool finds nothing")
    finally:
        paths_mod.APP_DIR, tidy_images.IMAGES_DIR, tidy_images.SEQUENCES_DIR = saved

    print(f"Tidying pictures: kept when stored as {', '.join(kept)}; "
          "still finds a genuine leftover")
    return problems


def _check_how_often_it_looks() -> list[str]:
    """'How often to re-check' has to be what actually happens.

    The setting promises seconds between looks while waiting. The wait used to
    sleep whichever was shorter, it or the 50ms guard that watches the stop
    key, so every value above 0.05 did nothing: the screen was scanned twenty
    times a second whatever Settings said, at several times the CPU the label
    warns about.

    Both halves matter, and they pull against each other. The stop key has to
    stay responsive during a long interval, so the wait cannot simply sleep
    the whole interval in one go either.
    """
    problems = []
    looks: list[float] = []
    guards = {"count": 0}

    class Counting(engine_mod.Engine):
        def _guard(self):
            guards["count"] += 1

    def run(interval: float, timeout: float) -> None:
        looks.clear()
        guards["count"] = 0
        runner = Counting(engine_mod.Sequence(
            name="polling",
            settings=engine_mod.Settings(poll_interval=interval,
                                         failsafe_corner=False)), dry_run=True)
        runner._poll_until(lambda: looks.append(time.monotonic()) or None,
                           timeout, "something that never turns up")

    # A quarter of a second between looks over three quarters of a second is
    # three or four looks, not fifteen.
    run(0.25, 0.75)
    if not 2 <= len(looks) <= 5:
        problems.append(f"0.25s between looks over 0.75s gave {len(looks)} of "
                        "them, expected about 3 - the interval is not honored")
    gaps = [b - a for a, b in zip(looks, looks[1:])]
    if gaps and min(gaps) < 0.2:
        problems.append(f"the shortest gap between looks was {min(gaps):.3f}s, "
                        "under the 0.25s asked for")

    # ...while the stop key is still checked several times within each of
    # those gaps, or stopping a run would feel sluggish.
    slow_looks, slow_guards = len(looks), guards["count"]
    if slow_guards < slow_looks * 3:
        problems.append(f"only {slow_guards} stop-key checks across "
                        f"{slow_looks} looks, so a long interval makes the "
                        "stop key slow to answer")

    # A small interval still runs fast.
    run(0.01, 0.3)
    if len(looks) < 8:
        problems.append(f"0.01s between looks over 0.3s gave only {len(looks)}")

    print(f"Poll interval   : 0.25s over 0.75s -> {slow_looks} looks and "
          f"{slow_guards} stop-key checks; 0.01s over 0.3s -> {len(looks)} looks")
    return problems


def _check_look_alike_keys_are_told_apart() -> list[str]:
    """Keys that appear twice on a keyboard must be separable, and readable.

    Pressing the numpad Enter used to record plain "Enter": the grabber folded
    the two onto one name, so the interface could not show a difference it had
    already thrown away. Every key needs to survive being recorded, and every
    key a person can end up with needs English to show for it.
    """
    from pixie.system import keyboard as kb
    from pixie.ui import app as app_mod

    problems = []

    # _EXTENDED names keys by hand, so it can drift out of step with KEYS and
    # nothing would say so - a flag set for a key that does not exist simply
    # never applies to anything. NumLock and PrintScreen sat there unbacked
    # until this check went in.
    for name in kb._EXTENDED:
        if name not in kb.KEYS:
            problems.append(f"{name} is flagged extended but is not a key, "
                            "so the flag applies to nothing")

    # Every keysym the grabber recognises must name a key we can actually send.
    for keysym, name in app_mod.KeyGrabber.TRANSLATE.items():
        if name not in kb.KEYS:
            problems.append(f"the grabber maps {keysym} to {name!r}, "
                            "which is not a key Pixie can send")

    # Nothing may fold two distinct keys onto one name. The number pad is the
    # exception: it reports a different keysym for the same physical key
    # depending on Num Lock, so several KP_ names landing on one key is right.
    folded: dict[str, list[str]] = {}
    for keysym, name in app_mod.KeyGrabber.TRANSLATE.items():
        if not keysym.startswith("KP_"):
            folded.setdefault(name, []).append(keysym)
    for name, keysyms in folded.items():
        if len(keysyms) > 1:
            problems.append(f"{sorted(keysyms)} all record as {name!r}, "
                            "so they cannot be told apart afterwards")

    # Two keys sharing one label would put us back where we started: the
    # difference exists, but nothing on screen shows it.
    shown: dict[str, str] = {}
    for name in kb.KEYS:
        text = kb.label(name)
        if not text:
            problems.append(f"{name} has no plain English to show")
        elif text in shown:
            problems.append(f"{name} and {shown[text]} both read as {text!r}")
        else:
            shown[text] = name
        twin = kb.TWINS.get(name)
        if twin and twin not in kb.KEYS:
            problems.append(f"{name}'s twin {twin!r} is not a key at all")

    pairs = [("Enter", "NumpadEnter"), ("LeftCtrl", "RightCtrl"),
             ("LeftShift", "RightShift"), ("5", "Numpad5")]
    for one, other in pairs:
        if one not in kb.KEYS or other not in kb.KEYS:
            problems.append(f"{one} and {other} are not both keys")
            continue
        if kb.label(one) == kb.label(other):
            problems.append(f"{one} and {other} both read as "
                            f"{kb.label(one)!r} on screen")

    print(f"Look-alike keys: {len(kb.KEYS)} keys, "
          f"{len(kb.TWINS)} with a twin, all labelled")
    return problems


def _check_mouse_movement_is_injected() -> list[str]:
    """Movement must be sent as input, and still land on the exact pixel.

    SetCursorPos moves the cursor and generates no input, so an application
    reading raw input never learns the pointer moved - it goes on believing
    the cursor is over whatever it was over, which is how a hovered card
    stays enlarged after the pointer has visibly left it. SendInput goes in
    at the bottom of the input stack instead, the same way clicks always did.

    The cost is that absolute coordinates are scaled to a 0-65535 grid across
    the whole virtual desktop, so the arithmetic has to be right or every
    click lands slightly off. That is what this checks.
    """
    from pixie.system import mouse as ms

    left, top, width, height = screen.virtual_bounds()
    was = ms.position()
    problems = []
    tried = [
        (left + 1, top + 1),                      # the very corner
        (left + width - 2, top + height - 2),     # the far corner
        (left + width // 2, top + height // 2),
        (left + width // 3, top + height // 4),
    ]
    try:
        missed = []
        for target in tried:
            ms.move_to(*target)
            time.sleep(0.01)
            landed = ms.position()
            if landed != target:
                missed.append((target, landed))

        # ...and a glide has to arrive exactly too, not just nearby.
        ms.move_to(left + 10, top + 10)
        ms.glide_to(*tried[2], seconds=0)
        if ms.position() != tried[2]:
            missed.append((tried[2], ms.position()))

        # The settle leaves the cursor where it found it.
        ms.settle()
        if ms.position() != tried[2]:
            missed.append(("after settle", ms.position()))
    finally:
        ms.move_to(*was)

    if missed:
        problems.append(f"movement landed off target: {missed}")
    print(f"Mouse moving   : {len(tried)} points across {width}x{height} "
          f"hit exactly, glide and settle land true")

    # SendInput is what makes it visible; SetCursorPos alone is the old bug.
    import inspect
    source = inspect.getsource(ms.move_to)
    if "SendInput" not in source and "_send" not in source:
        problems.append("move_to no longer sends the movement as input")
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
    # Two clicks close enough together that Windows reads them as one
    # double-click. The gap is the sequence default, well inside its limit.
    ms.click(*target, clicks=2, interval=0.06)

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
