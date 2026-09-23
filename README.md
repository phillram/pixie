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
* Click a random spot inside a box you draw, rather than the same pixel forever
* Press keys
* Wait for things, with a timeout or indefinitely
* Group steps into sections, one per screen, each repeating until its start
  condition stops matching

Every pause can be a range rather than a fixed number, so the timing varies.
Steps, sections and whole cycles each get their own, so you can have a delay
between clicks and none at all between screens.

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

`Duplicate`, or Ctrl+D, copies the selected step with all its settings and
drops the copy underneath. It is the fast way to build several steps that
differ only by their image or their position: duplicate, then recapture. A
recapture always writes a new file, so it never overwrites the image the
original is using.

Image and color fields show you what they hold. An image step displays the
picture it captured along with its size in pixels, and tells you plainly if the
file has gone missing. A color field shows a filled swatch and the hex value
next to the RGB numbers.

Name a step and the list reads by that name, with the generated summary
following in brackets so you can still see which image or key it uses:

```
 2. Click the OK button   (Click ok.png)
 3. Confirm with Enter    (Press Enter)
```

Step names are labels. They appear in the list and in the log and nothing else
reads them, so rename anything at any time without affecting what it does. A
captured image keeps working after a rename: the step name only seeds the
filename when the image is first captured, and the stored path is independent
of it afterwards.

### Typing in Pixie

Every box you can type in takes the editing keys you would expect:

| Key | What it does |
| --- | --- |
| Ctrl+Backspace, Shift+Backspace | Delete the word before the caret |
| Ctrl+Delete | Delete the word after it |
| Ctrl+A | Select everything in the box |
| Ctrl+D | Duplicate the selected step, even from inside a field |

Tk, which Pixie's window is built on, leaves these out and binds Ctrl+A to
"go to the start of the line" instead. Shift+Delete is left alone, because it
has meant Cut for longer than any of this.

Every box and search area is four editable numbers as well as a button. Drag
one to create it, then type to stretch or nudge it. You should not have to
re-drag a whole box to move an edge ten pixels.

Pixie remembers the Dry run and Minimize settings, the window size and
position, whether it was maximized, and which sequence you had open, so she
comes back the way you left her. The size behind a maximized window is kept
too, so unmaximizing gives you back the window you had. A saved position on a
monitor that no longer exists is ignored rather than opening the window
somewhere you cannot see it.

Pauses, keys and the cursor-parking setting belong to the **sequence**, not to
Pixie, so different jobs can have different timing. Changing them saves the
sequence file straight away, which is why they are still there next time.

Sequences are saved as JSON in `sequences/`. Captured reference images go in
`images/`. Neither is committed.

### Pictures you no longer need

Delete a step and Pixie offers to delete its picture too, but only when
nothing else uses it. A duplicated step shares one file with the original, and
so can two different sequences, so the offer only appears when this really was
the last step pointing at it.

Recapturing a step writes a new file and leaves the old one behind, which is
how `images/` fills up with near-identical pictures. To clear those out:

```
python tools/tidy_images.py            # list what nothing uses
python tools/tidy_images.py --apply    # delete them
```

It lists and deletes nothing unless you ask. Save your work first: a step you
have not saved yet is not in any file, so its picture looks unused.

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
| Click anywhere in a box | Drag a box, get a random spot inside it every time |
| Click the last thing found | Click wherever the previous step found something |
| Press a key | Send a keystroke, optionally several times |
| Wait a moment | Pause for a fixed or random length of time |
| Section divider | Marks the start of a section |
| Note | Does nothing. Somewhere to explain the sequence to yourself |

### When something does not turn up

Any step that waits has a `Give up after (s)` and an `If it is not found`.
That pair is worth understanding, because between them they decide how long
Pixie sits doing nothing:

| If it is not found | What happens |
| --- | --- |
| Go back to the very first step of the sequence | The whole script starts again. Everything before this step runs a second time |
| Go back to the first step of this section | Only this section starts again. No other section is touched |
| Skip it and run the next step anyway | Runs the next step as though this one had worked |
| Leave this section and start the next one | This is how a section ends |
| Stop the run completely | Same as pressing Stop |

Pixie spells the difference out underneath the dropdown, using the names of
your own sections, because the first two are the pair that get mixed up:

```
Go back to the very first step of the sequence
    Abandons 'In Game' and starts the whole script again from 'Before Game'.
    Everything before this step runs a second time.

Go back to the first step of this section
    Starts 'In Game' again from its own step 1, and does not touch any other
    section.
```

`Give up after` is the timeout. It defaults to 30 seconds on a step that waits
for something, so a section start point left at its default spends 30 seconds
waiting before it hands over to the next section. If moving between screens
feels slow, that is almost always why. Set it to 0 and it waits forever
instead.

The log tells you which is happening: `still waiting for main_menu.png, 15s so
far (gives up in 15s)`.

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

## Several things glowing at once

A row of cards can all be highlighted at the same time. `If several match,
use` decides which one Pixie goes for:

| Setting | Which patch |
| --- | --- |
| the biggest one | The largest patch of the color. The default, and what Pixie has always done |
| the one furthest left | Lowest x. Right for working along a row in reading order |
| the one furthest right | Highest x |
| the one nearest the top | Lowest y |
| the one nearest the bottom | Highest y |

The biggest patch is whichever glow happens to be brightest or fattest at that
instant, which is why it can look like it picks at random. Set it to
`the one furthest left` and it takes the leftmost every time, so a section that
repeats works along the row from the left.

The log says when there was a choice to make:

```
found RGB(37, 254, 254) - 8680 pixels in a 180x250 box, center 640, 900
    - 3 patches matched, took the one furthest left
```

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
 1. Wait for screen 1's marker      If not found: move on
 2. do the work
                                    end of section, back to step 1
=== Screen 2 ===
 1. Wait for screen 2's marker      If not found: move on
 2. do the work
```

Which reads as: do screen 1 until its marker stops appearing, then screen 2 the
same way, then start again.

Each section counts its steps from 1, and the dividers and notes are not
counted at all, because they are labels rather than instructions. While a
sequence runs, the section Pixie is in is highlighted in the list, so you can
tell where she is at a glance without reading the log.

The pause between sections is separate from the pause between steps. Set it to
0 in Settings and Pixie moves from one screen to the next without waiting,
while still pausing between clicks. It applies both when a section hands over
to the next one and when a section starts itself again.

Select a divider and the section gets two settings of its own:

* **Pause around this section**, which overrides the sequence-wide one for
  this section only
* **Cap every wait in here**, a ceiling on how long any step inside may wait.
  A step asking for 30 seconds, or for forever, gives up after the cap
  instead; a step that already waits less keeps its own shorter time

The cap is the quick way to stop one screen idling without going through its
steps one at a time. Set it to 3 and nothing in that section can sit still for
longer than that. The log says so when the section starts:
`=== Before Game === (nothing here waits longer than 3s)`.

A sequence with no dividers is treated as one section covering everything, which
behaves exactly as it did before sections existed.

## Starting and stopping it

F9 starts the run and stops it again. It works while the application you are
automating has focus, which is the only time it is any use, so you never have
to go and find Pixie's window to start a job.

To stop, any of these, all of which work from another application:

* F9 again
* The Stop button
* F8
* Put the mouse in the top left corner of the screen

All of them are checked between every step and during every wait, so it stops
within about 50ms. Both keys are configurable in Settings, and the start/stop
key can be switched off entirely if it clashes with something.

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
confirm each one repeats until its start point fails, checks a click box lands
inside itself and never twice in the same place, and sends real keystrokes and a
real double click to its own window to prove input actually lands. It skips the
input checks rather than firing stray keystrokes if its test window cannot take
focus.

`check_wiring.py` also checks that every kind of field a step can declare has
an editor to draw it, because a missing one falls back to a plain number box
and edits the wrong thing without complaining.

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
│       ├── editing.py     the editing keys Tk leaves out
│       └── capture.py     the freeze-screen picker
├── tools/                 standalone helpers, not imported by the app
│   ├── build_exe.py       builds Pixie.exe
│   ├── check_wiring.py    imports and step wiring, no screen needed
│   ├── check_target.py    can we see and click your application?
│   ├── tune_color.py      works out color settings for a glow
│   ├── tidy_images.py     lists pictures no sequence uses any more
│   └── make_icon.py       regenerates assets/pixie.ico
├── tests/
├── assets/
└── sequences/
```

Nothing in `core` or `system` imports from `ui`, so the engine runs headless.

Adding a step type means one entry in `STEP_TYPES` in `pixie/core/steps.py` and
one `_do_<key>` method on `Engine`. The GUI builds its editor from the field
declarations, so it needs no changes.

### One source for everything

Anything named in two places eventually disagrees with itself, usually where
nobody is looking. So each of these has exactly one home, and
`tools/check_wiring.py` fails the build if a copy drifts away from it:

| Thing | Lives in | Checked by |
| --- | --- | --- |
| Step types and their fields | `STEP_TYPES` | every type has a `_do_` handler and a full set of defaults |
| Default values for a field | the `Field` declaration | the engine reads them through `_value`, never its own copy |
| Which editor draws a field | `App.FIELD_BUILDERS` | every declared kind has one |
| The "if not found" options | `ON_TIMEOUT_CHOICES` | every option has a branch in `run_cycle`, found by reading the source |
| Labels for dropdown values | `CHOICE_LABELS` | every choice on every field has one |
| Keys that can be a hotkey | `screen.hotkey_names()` | the GUI cannot offer a key `key_pressed` would refuse |
| Where the cursor parks | `engine.PARK_LABELS` | the GUI imports it rather than restating it |
| Log levels | `engine.LOG_LEVELS` | every level has a color in the GUI |

The rule when adding anything: declare it once, and if a second place needs to
know about it, make `check_wiring.py` prove they agree.
