# Pixie

Pixie watches your screen, finds things on it, and clicks them. You build a
sequence by pointing at what you want her to look for, then she repeats it until
you tell her to stop.

It is for the kind of task that is too fiddly to script properly and too dull to
do by hand: the same twelve clicks through the same four screens, over and over.

Windows only. Dark themed.

## What it can do

* Find an image on screen and click it
* Find a color anywhere in a region and click the middle of it, which is how you
  detect a glowing border or a highlight
* Handle the dialog that only sometimes appears, without falling over when it
  does not
* Press keys
* Wait for things, with a timeout or indefinitely
* Group steps into sections, one per screen, each repeating until its start
  condition stops matching

Every pause can be a range rather than a fixed number, so the timing varies.

## Requirements

Python 3.10 or newer, and Windows. The GUI uses tkinter, which ships with
Python on Windows.

```
pip install -r requirements.txt
```

That pulls in mss for screen capture, OpenCV and NumPy for matching, and Pillow
for the capture overlay.

## Running it

Download `Pixie.exe` from the
[latest release](https://github.com/phillram/pixie/releases/latest) and double
click it. It needs no Python and nothing installed. Put it in a folder of its
own, because it creates `sequences/` and `images/` beside itself.

To run from source instead:

```
python -m pixie
```

To build the executable yourself:

```
python tools/build_exe.py
```

That produces `Pixie.exe` in the project root, about 70MB, in roughly twenty
seconds.

## How a sequence works

A sequence is a list of steps. Pixie runs them top to bottom, then starts again,
looping until you stop her.

Build one in the left pane, edit the selected step in the right pane, and watch
the log along the bottom. Every image, color, point and region has a Capture
button: the window hides, the screen freezes, and you drag a box or click a
pixel to say what you mean.

`Test this step` runs only the selected step and reports what it found. It is
the quickest way to tune a match without running everything.

Image and color fields show you what they hold. An image step displays the
picture it captured along with its size in pixels, and tells you plainly if the
file has gone missing. A color field shows a filled swatch and the hex value
next to the RGB numbers.

Step names are labels. They appear in the list and in the log and nothing else
reads them, so rename anything at any time without affecting what it does. A
captured image keeps working after a rename: the step name only seeds the
filename when the image is first captured, and the stored path is independent
of it afterwards.

Pixie remembers the Dry run and Minimize settings, the window size and position,
and which sequence you had open, so she comes back the way you left her. A saved
position on a monitor that no longer exists is ignored rather than opening the
window somewhere you cannot see it.

Sequences are saved as JSON in `sequences/`. Captured reference images go in
`images/`. Neither is committed.

### The steps

| Step | What it does |
| --- | --- |
| Wait for a color | Pause until a color appears at one spot |
| Find a color in an area | Search a region for a color and use the middle of what it finds |
| Click a color if it appears | Optional. Clicks it if present, skips if not |
| Wait for an image | Pause until a picture appears. Does not click |
| Click an image | Find a picture and click it |
| Click an image if it appears | Optional version of the above |
| Click a fixed spot | Always the same coordinates |
| Click the last thing found | Click wherever the previous step found something |
| Press a key | Send a keystroke, optionally several times |
| Wait a moment | Pause for a fixed or random length of time |
| Section divider | Marks the start of a section |
| Note | Does nothing. Somewhere to explain the sequence to yourself |

Any step that waits can be told what to do when its target never turns up:
start the sequence over, carry on regardless, move to the next section, or stop
the run. Set its timeout to 0 and it waits indefinitely instead.

## Matching a glow or a highlight

This is the part worth reading, because the obvious approach does not work well.

A glow is one color spread across a brightness gradient. It is close to white at
its core and nearly black at its edges. Those are far apart in RGB, so matching a
single sampled value catches only a slice of the glow, and which slice depends on
how bright it happens to be at that moment. That is why it feels unreliable.

Hue barely changes across that gradient. Set `Match by` to `hue`, give a
tolerance in degrees, and it catches the whole thing. On a cyan glow fading from
dark to white:

| Mode | Pixels matched |
| --- | --- |
| rgb, tolerance 50 | 1,640 |
| hue, tolerance 14 | 8,680 |

Same color, five times the coverage, and far steadier frame to frame.

To get the numbers for your own target:

```
python tools/tune_color.py
```

Drag a box over the thing you want detected. It reports the dominant hue and
prints the tolerance, minimum saturation and minimum brightness to type in,
along with what proportion of your selection those settings would match.

Use `rgb` mode instead for flat, solid colors that do not change.

## Speed

Scanning the whole desktop is the slow part. Measured on a 7680x2160 dual
monitor setup:

| Search area | Time per scan |
| --- | --- |
| Whole desktop, 7680x2160 | 793 ms |
| One monitor, 1920x1080 | 119 ms |
| A panel, 400x300 | 16 ms |

Set a search region on every image and color step. It is the single biggest
speed win available. Make the box comfortably larger than where the target
appears, because anything outside it is invisible to the matcher.

## Sections

If you have several independent screens to work through, split the sequence into
sections. Add a Section divider and everything below it belongs to that section
until the next divider.

A section repeats itself: when its last step finishes it goes back to that
section's first step. To leave, give a step (usually the first, the one that
detects the screen) `If not found: Move on to the next section`. After the last
section Pixie wraps back to the first.

```
=== Screen 1 ===
 2. Wait for screen 1's marker      If not found: move on
 3. do the work
                                    end of section, back to step 2
=== Screen 2 ===
 6. Wait for screen 2's marker      If not found: move on
 7. do the work
```

Which reads as: do screen 1 until its marker stops appearing, then screen 2 the
same way, then start again.

A sequence with no dividers is treated as one section covering everything, which
behaves exactly as it did before sections existed.

## Stopping it

Three ways, all of which work while another application has focus:

* The Stop button
* F8, configurable in Settings
* Put the mouse in the top left corner of the screen

All three are checked between every step and during every wait, so it stops
within about 50ms.

Pixie minimizes herself when you press Start, so she is not sitting on top of the
thing she is clicking. She keeps running. The taskbar title counts the cycles.
Untick `Minimize while running` if you would rather watch.

**Leave Dry run ticked the first few times.** It does the full detection and
writes every click it would have sent to the log, without sending any. That is
how you confirm the coordinates are right before anything real happens.

## Running without the GUI

For an unattended run, from a shortcut or a scheduled task:

```
python -m pixie sequences/my_job.json
python -m pixie sequences/my_job.json --dry-run
python -m pixie sequences/my_job.json --max-cycles 20
```

## Is this the right tool?

Pixel matching works on anything you can see, which is its strength and its
weakness. It breaks when windows move, when the resolution changes, or when a
theme shifts.

If your target is a normal Windows application or a web app, look at pywinauto
or Playwright first. Those find the actual button labelled OK through the
accessibility tree, and none of the above bothers them.

Pixel matching is the right choice when there is no accessibility tree to read,
which covers anything that draws its own interface: games, Unity and SDL
applications, custom renderers. `tools/check_target.py` prints the window class of
whatever is in the foreground, which tells you which case you are in.

Some fullscreen applications use exclusive fullscreen, which screen capture
reads as a black frame. `tools/check_target.py` detects that too. The fix is usually a
setting in the application: switch it to borderless windowed.

## Development

```
python tools/check_wiring.py   # imports and step wiring, no screen needed
python tests/selftest.py       # detection, color matching, sections, real input
python tests/selftest_gui.py   # every step editor, reordering, save and reload
```

`check_wiring.py` is what CI runs, because it needs no desktop. The other two
do: they capture the real screen and send real input.

`selftest.py` crops a patch of your actual screen and matches it back, checks
hue matching beats RGB on a synthetic gradient, runs a three section sequence to
confirm each one repeats until its start point fails, and sends real keystrokes
and a real double click to its own window to prove input actually lands. It
skips the input checks rather than firing stray keystrokes if its test window
cannot take focus.

### Layout

```
pixie/
├── pixie/                 the package
│   ├── __main__.py        entry point: GUI with no arguments, headless with
│   ├── cli.py             the headless runner
│   ├── paths.py           where files live, from source or from a frozen exe
│   ├── core/              the engine. No GUI, no Windows calls
│   │   ├── engine.py      runs a sequence
│   │   └── steps.py       the step vocabulary, declared as data
│   ├── system/            talking to Windows
│   │   ├── screen.py      capture, template matching, color searching
│   │   ├── mouse.py       movement and clicks via SendInput
│   │   └── keyboard.py    key presses via SendInput
│   └── ui/                the tkinter application
│       ├── app.py         main window
│       ├── theme.py       dark theme and tooltips
│       └── capture.py     the freeze-screen picker
├── tools/                 standalone helpers, not imported by the app
│   ├── build_exe.py       builds Pixie.exe
│   ├── check_wiring.py    imports and step wiring, no screen needed
│   ├── check_target.py    can we see and click your application?
│   ├── tune_color.py      works out color settings for a glow
│   └── make_icon.py       regenerates assets/pixie.ico
├── tests/
├── assets/
└── sequences/
```

Nothing in `core` or `system` imports from `ui`, so the engine runs headless.

Adding a step type means one entry in `STEP_TYPES` in `pixie/core/steps.py` and
one `_do_<key>` method on `Engine`. The GUI builds its editor from the field
declarations, so it needs no changes. `tools/check_wiring.py` fails if the two
ever drift apart.
