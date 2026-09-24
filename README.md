# Pixie

Pixie watches your screen, finds things on it, and clicks them. You build a
sequence by pointing at what she should look for, then she repeats it until you
tell her to stop.

It is for the kind of job that is too fiddly to script properly and too dull to
do by hand: the same twelve clicks through the same four screens, over and over.

Windows only. Dark themed.

```
=== Sign in ===
 1. Wait for the sign-in box        If it is not found: move on to the next section
 2. Click the password field
 3. Press Enter
=== Main screen ===
 1. Look for the toolbar            If it is not found: move on to the next section
 2. Did a dialog open?              If it is not found: skip the steps indented under it
     ↳ 3. Click OK
 4. Pick the next item
```

## Getting it running

Download `Pixie.exe` from the
[latest release](https://github.com/phillram/pixie/releases/latest) and double
click it. No Python, nothing to install. Put it in a folder of its own, because
it creates `sequences/` and `images/` beside itself.

From source instead, with Python 3.10 or newer:

```
pip install -r requirements.txt
python -m pixie                # the window
python tools/build_exe.py      # produces Pixie.exe, about 70MB
```

## Your first sequence

A sequence is a list of steps. Pixie runs them top to bottom, then starts again,
looping until you stop her.

Build one in the left pane, edit the selected step in the right pane, watch the
log along the bottom. All three dividers drag, and where you put them is
remembered.

1. **Add step** → `Click an image`.
2. Press **Capture** beside `Image`. The window hides, the screen freezes, and
   you drag a box round the thing you want clicked.
3. Press **Capture** beside `Area to search` and drag a box round the part of
   the screen it appears in. Do this on every step: it is the single biggest
   speed win, because scanning a whole desktop is roughly fifty times slower
   than scanning a panel.
4. Tick **Dry run** and press **Start**. Pixie detects everything and writes
   every click she *would* have sent to the log, without sending any.
5. Happy with the coordinates? Untick Dry run and go again.

Every image, color, point and region has that Capture button. Boxes are four
editable numbers as well, so you can nudge an edge ten pixels without re-dragging
the whole thing.

### Seeing what a step will do

Three buttons answer the questions a log cannot. None of them write anything to
disk unless you press `Save picture...`.

**Test this step** runs only the selected step and reports what it found. The
quickest way to tune a match without running everything.

**What matches?** works on any step that searches an area for a color. It shows
your own screen back to you with every matching pixel tinted, each patch boxed
and numbered in the order the step would use them, the rejected ones greyed out
with the reason, and how saturated each one is. This is how you tell a highlight
from a background.

**Show the click** works on any step that clicks. A crosshair on the exact spot,
at life size, with the thing it found boxed around it. It runs the step for real
and intercepts only the click, so the crosshair is where the click would
genuinely go rather than a second guess at it.

## The steps

**Add step** groups them under these headings and repeats the short description
beside each name, so you can tell `Click an image` from `Click an image if it
appears` without opening both.

| Step | What it does |
| --- | --- |
| **Structure** | |
| Section divider | Marks the start of a section |
| Note | Does nothing. Somewhere to explain the sequence to yourself |
| Go somewhere else | Sends the run to another section or back to the top |
| When nothing has happened | Fires when this section has gone round achieving nothing |
| **Wait until something appears** | |
| Wait for an image | Pause until a picture appears. Does not click |
| Wait for a color | Pause until a color appears at one spot |
| Find a color in an area | Search a region for a color and use the middle of what it finds |
| **Click what Pixie finds** | |
| Click an image | Find a picture and click it |
| Click an image if it appears | Optional version of the above |
| Click a color if it appears | Optional. Clicks it if present, skips if not |
| Click the last thing found | Click wherever the previous step found something |
| **Click where you say** | |
| Click a fixed spot | Always the same coordinates |
| Click anywhere in a box | Drag a box, get a random spot inside it every time |
| **Keyboard and waiting** | |
| Press a key | Send a keystroke, optionally several times |
| Wait a moment | Pause for a fixed or random length of time |

Steps can be grouped: indent a run of steps under a check with Ctrl+Right, and
they only run when that check finds what it is looking for. Split a sequence
into sections, one per screen, and each repeats until its first step stops
matching. Both are covered in [building sequences](docs/sequences.md).

## Running it

F9 starts the run and stops it again. It works while the application you are
automating has focus, so you never have to go and find Pixie's window.

To stop, any of these, all of which work from another application:

* F9 again
* The Stop button
* F8
* Put the mouse in the top left corner of the screen

All of them are checked between every step and during every wait, so it stops
within about 50ms. Both keys are configurable in Settings.

Pixie minimizes herself when you press Start, so she is not sitting on top of
the thing she is clicking. The taskbar title counts the cycles. Untick
`Minimize while running` if you would rather watch.

For an unattended run, from a shortcut or a scheduled task:

```
python -m pixie sequences/my_job.json
python -m pixie sequences/my_job.json --dry-run
python -m pixie sequences/my_job.json --max-cycles 20
```

Leaving it going for hours is fine. Memory stays flat, and Pixie has no network
code: she reads your screen and writes to `images/` and `sequences/` beside
herself. The log lives in the window and nowhere else, keeping the most recent
few thousand lines, so redirect the command line form if you want to keep one.

## Going further

* **[Building sequences](docs/sequences.md)**: sections, branching, guarding a
  group of steps behind a check, jumping about, timing, the cursor, and keys.
* **[Matching a glow or a highlight](docs/matching.md)**: getting a color step
  to find the thing you mean and nothing else. Read this when a step finds the
  wrong thing or clicks somewhere strange.

## Is this the right tool?

Pixel matching works on anything you can see, which is its strength and its
weakness. It breaks when windows move, when the resolution changes, or when a
theme shifts.

If your target is a normal Windows application or a web app, look at pywinauto
or Playwright first. Those find the actual button labelled OK, and none of the
above bothers them.

Pixel matching is the right choice when there is nothing to read but the
picture, which covers anything that draws its own interface: games, Unity and
SDL applications, custom renderers.

```
python tools/check_target.py
```

That prints the window class of whatever is in the foreground, which tells you
which case you are in. It also catches exclusive fullscreen, which screen
capture reads as a black frame; the fix is usually a setting in the
application, switching it to borderless windowed.

## Tools

```
python tools/check_target.py   # can we see and click your application?
python tools/tune_color.py     # work out color settings for a glow
python tools/tidy_images.py    # list captured pictures no sequence uses
python tools/build_exe.py      # build Pixie.exe
```

`tidy_images.py` lists and deletes nothing unless you add `--apply`.

## Development

```
python tools/check_wiring.py   # imports and step wiring, no screen needed
python tests/selftest.py       # detection, color matching, sections, real input
python tests/selftest_gui.py   # every step editor, reordering, save and reload
```

`check_wiring.py` is what CI runs, because it needs no desktop. The other two
capture the real screen and send real input, so they need a logged-in session.

```
pixie/
├── pixie/
│   ├── __main__.py        entry point: window with no arguments, headless with
│   ├── cli.py             the headless runner
│   ├── paths.py           where files live, from source or from a frozen exe
│   ├── core/              the engine. No GUI, no Windows calls
│   │   ├── engine.py      runs a sequence
│   │   └── steps.py       the step vocabulary, declared as data
│   ├── system/            talking to Windows
│   │   ├── screen.py      capture, template matching, color searching
│   │   ├── mouse.py       movement and clicks
│   │   └── keyboard.py    key presses
│   └── ui/                the tkinter application
└── tools/                 standalone helpers, not imported by the app
```

Nothing in `core` or `system` imports from `ui`, so the engine runs headless.

Adding a step type means one entry in `STEP_TYPES` in `pixie/core/steps.py` and
one `_do_<key>` method on `Engine`. The GUI builds its editor from the field
declarations, so it needs no changes.

Anything named in two places eventually disagrees with itself. Step types,
field defaults, dropdown labels, key names, pick orders and the rest each have
exactly one home, and `check_wiring.py` fails the build if a second copy drifts
away from it. Declare it once and let that check prove the other places agree.
