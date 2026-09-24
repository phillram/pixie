# Pixie

Pixie watches your screen, finds things on it, and clicks them. You build a
sequence by pointing at what to look for; it repeats until you stop it.

For jobs too fiddly to script and too dull to do by hand: the same twelve clicks
through the same four screens, over and over.

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
[latest release](https://github.com/phillram/pixie/releases/latest). Put it in
its own folder: it creates `sequences/` and `images/` beside itself.

From source, Python 3.10 or newer:

```
pip install -r requirements.txt
python -m pixie                # the window
python tools/build_exe.py      # produces Pixie.exe, about 70MB
```

## Your first sequence

A sequence is a list of steps, run top to bottom, then again from the top.

Build it in the left pane, edit the selected step in the right pane, watch the
log along the bottom. All three dividers drag, and where you put them is
remembered.

1. **Add step** → `Click an image`.
2. **Capture** beside `Image`. The window hides, the screen freezes, drag a box
   round the thing to click.
3. **Capture** beside `Area to search`, drag a box round the part of the screen
   it appears in. Do this on every step: a panel scans about fifty times faster
   than the whole desktop.
4. Tick **Dry run** and press **Start**. Every click it would have sent goes to
   the log instead.
5. Untick Dry run and go again.

Every image, color, point and region has a Capture button. Boxes are also four
editable numbers, for nudging an edge without re-dragging.

### Seeing what a step will do

Three buttons, none of which write to disk unless you press `Save picture...`:

**Test this step** runs the selected step alone and reports what it found.

**What matches?** shows your screen back to you with every matching pixel
tinted, each patch boxed and numbered in the order the step would use them, and
the rejected ones greyed out with the reason. Color steps only.

**Show the click** puts a crosshair on the exact spot, at life size, with the
match boxed around it. Runs the step for real, intercepting only the click.

## The steps

**Add step** groups them under these headings:

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

Indent steps under a check with Ctrl+Right and they only run when that check
finds something. Split a sequence into sections, one per screen, and each
repeats until its first step stops matching. See
[building sequences](docs/sequences.md).

## Running it

Two keys, both set per sequence under Settings:

| Setting | Default | What it does |
| --- | --- | --- |
| **Start/stop key** | F9 | Starts the run. Press again to stop. Can be turned off |
| **Stop key** | F8 | Stops the run and nothing else |

Both work while the application you are automating has focus, so you never have
to go and find Pixie's window.

To stop: either key, the Stop button, or put the mouse in the top left corner of
the screen. All are checked between every step and during every wait, so it
stops within about 50ms.

The choosable keys are F1 to F12, Esc, Space, Pause and ScrollLock. Those are
the ones Pixie can watch for while another window has focus.

Pixie minimizes on Start and counts cycles in the taskbar title. Untick
`Minimize while running` to watch instead.

Unattended, from a shortcut or a scheduled task:

```
python -m pixie sequences/my_job.json
python -m pixie sequences/my_job.json --dry-run
python -m pixie sequences/my_job.json --max-cycles 20
```

Memory stays flat over long runs. Pixie has no network code; it reads the screen
and writes to `images/` and `sequences/`. The log lives in the window only and
keeps the most recent few thousand lines, so redirect the command line form to
keep one.

## Going further

* **[Building sequences](docs/sequences.md)**: sections, branching, guarding a
  group of steps behind a check, jumping about, timing, the cursor, keys.
* **[Matching a glow or a highlight](docs/matching.md)**: getting a color step
  to find the thing you mean. Read this when a step finds the wrong thing or
  clicks somewhere strange.

## Is this the right tool?

Pixel matching works on anything you can see. It breaks when windows move, when
the resolution changes, or when a theme shifts.

For a normal Windows application or a web app, try pywinauto or Playwright
first: they find the actual button labelled OK, and none of the above affects
them.

Pixel matching is for anything that draws its own interface, where there is
nothing to read but the picture: games, Unity and SDL applications, custom
renderers.

```
python tools/check_target.py
```

Prints the window class of whatever is in the foreground, so you know which case
you are in. Also catches exclusive fullscreen, which screen capture reads as a
black frame; switch the application to borderless windowed.

## Tools

```
python tools/check_target.py   # can we see and click your application?
python tools/tune_color.py     # work out color settings for a glow
python tools/tidy_images.py    # list captured pictures no sequence uses
python tools/build_exe.py      # build Pixie.exe
```

`tidy_images.py` deletes nothing without `--apply`.

## Development

```
python tools/check_wiring.py   # imports and step wiring, no screen needed
python tests/selftest.py       # detection, color matching, sections, real input
python tests/selftest_gui.py   # every step editor, reordering, save and reload
```

`check_wiring.py` is what CI runs; it needs no desktop. The other two capture the
real screen and send real input, so they need a logged-in session.

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

A new step type is one entry in `STEP_TYPES` in `pixie/core/steps.py` and one
`_do_<key>` method on `Engine`. The GUI builds its editor from the field
declarations.

Step types, field defaults, dropdown labels, key names and pick orders each have
one home, and `check_wiring.py` fails the build if a second copy drifts from it.
