# Building sequences

The editor, sections, branching, timing, the cursor and keys.

For getting a color step to find the right thing, see
[matching a glow or a highlight](matching.md).

## Working in the editor

**Hints**, at the top of the panel, shows an explanation under every setting.
It is off by default, so the panel is just the settings. With it off, hover a
setting's name to get its explanation, or the step title for the step's.

### Names, copies and pictures

Name a step and the list reads by that name, with the generated summary
following in brackets:

```
 2. Click the OK button   (Click ok.png)
 3. Confirm with Enter    (Press Enter  (the main one))
```

Names are labels; rename anything at any time. A captured image keeps working
after a rename.

`Duplicate`, or Ctrl+D, copies the selected step with all its settings. Fast way
to build steps that differ only by their image: duplicate, then recapture.
Recapturing writes a new file, so it never overwrites the original's image.

An image field shows the picture and its size, and says if the file has gone
missing. A color field shows a swatch and the hex value beside the RGB numbers.

Delete a step and Pixie offers to delete its picture, but only when nothing else
uses it: duplicated steps share one file, and so can two sequences.

Recapturing leaves the old file behind, so `images/` collects near-identical
pictures. To clear those out:

```
python tools/tidy_images.py            # list what nothing uses
python tools/tidy_images.py --apply    # delete them
```

Save your work first. A step you have not saved is not in any file, so its
picture looks unused.

### Typing

Every box takes the editing keys Tk otherwise leaves out:

| Key | What it does |
| --- | --- |
| Ctrl+Backspace, Shift+Backspace | Delete the word before the caret |
| Ctrl+Delete | Delete the word after it |
| Ctrl+A | Select everything in the box |

The window itself answers to these, and to nothing else:

| Key | What it does |
| --- | --- |
| Ctrl+S | Save the sequence |
| Ctrl+O | Open a sequence |
| Ctrl+D | Duplicate the selected step |
| Ctrl+Right | Indent the selected step under the one above |
| Ctrl+Left | Move the selected step back out |

**None of them start or stop a run.** That is the start/stop key in Settings, a
global hotkey so it works when Pixie is not in front.

### What gets remembered

Remembered between runs: Dry run, Minimize, window size and position, whether
it was maximized, which sequence was open, and the pane dividers. A position on
a monitor that no longer exists is ignored.

Pauses, keys and cursor settings belong to the **sequence**, not to Pixie, so
different jobs can have different timing. Changing them saves the file at
once.

Sequences are JSON in `sequences/`. Captured images go in `images/`. Neither is
committed.


## Sections

Add a Section divider and everything below it belongs to that section until the
next divider.

A section repeats: when its last step finishes it goes back to that section's
first step. To leave, give a step `If it is not found: Leave this section and
start the next one` -- usually the first step, the one that detects the screen.
After the last section Pixie wraps back to the first.

```
=== Screen 1 ===
 1. Wait for screen 1's marker      If not found: move on
 2. do the work
                                    end of section, back to step 1
=== Screen 2 ===
 1. Wait for screen 2's marker      If not found: move on
 2. do the work
```

Do screen 1 until its marker stops appearing, then screen 2 the same way, then
start again.

Each section counts its steps from 1; dividers and notes are not counted. The
section being run is highlighted in the list.

Select a divider and the section gets three settings of its own:

* **Pause when this section ends**, overriding the sequence-wide one here only
* **Cap every wait in here**, a ceiling on how long any step inside may wait. A
  step asking for 30 seconds, or for forever, gives up after the cap instead. A
  step that already waits less keeps its own shorter time. The log says so when
  the section starts: `=== Sign in === (nothing here waits longer than 3s)`
* **Cursor after a click in here**, covered under [The cursor](#the-cursor)

A sequence with no dividers is one section covering everything.

A section with every step switched off has nothing to run and nothing to end
it. Pixie says so before the run starts and moves past it during one.

## Making a sequence decide things

### If it is not found

Any step that waits has a `Give up after (s)` and an `If it is not found`.

| If it is not found | What happens |
| --- | --- |
| Go back to the very first step of the sequence | The whole script starts again. Everything before this step runs a second time |
| Go back to the first step of this section | Only this section starts again. No other section is touched |
| Skip it and run the next step anyway | Runs the next step as though this one had worked |
| Skip the steps indented under it | Jumps the whole group below it |
| Leave this section and start the next one | This is how a section ends |
| Stop the run completely | Same as pressing Stop |

The first two get mixed up, so Pixie spells the difference out under the
dropdown using your own section names:

```
Go back to the very first step of the sequence
    Abandons 'Main screen' and starts the whole script again from 'Sign in'.
    Everything before this step runs a second time.

Go back to the first step of this section
    Starts 'Main screen' again from its own step 1, and does not touch any
    other section.
```

### Checks that guard a group

Ctrl+Right indents a step under the one above. That step above becomes a check,
and the indented run below it only happens when the check finds something:

```
 1. Look for the toolbar
 2. Did a dialog open?           If it is not found: skip the steps indented under it
     ↳ 3. Tick 'do not ask again'
     ↳ 4. Click OK
 5. Pick the next item
```

If step 2 finds nothing, 3 and 4 are skipped and the run carries on at 5.
Ctrl+Left takes a step back out.

Use this for something that only sometimes happens and needs more than one
action when it does. For a single click, `Click a color if it appears` is
enough on its own.

`↑` and `↓` understand groups:

* Moving a check moves everything indented under it, as one thing, and it steps
  over a neighbouring group rather than landing inside it
* Moving an indented step reorders it within its group
* At either end of a group, moving further takes that step out of it. Only the
  first and last can do that without splitting the group in half

Delete or move a check and its group un-indents itself. Pixie also warns when
an indent is not actually guarding anything, which looks identical to one that
is:

```
'Did a dialog open?' has 2 step(s) indented under it, but 'If it is not
found' is not set to 'Skip the steps indented under it', so they run whether
it finds anything or not.
```

Groups go one level deep, not more.

### When you need "if this IS found"

Every branch above is phrased as `If it is not found`, which covers most cases:
a screen going away is usually the same event as the next one arriving.

Not always. A "finished" banner appearing over a screen still working is its own
event, and nothing's *absence* means the same thing.

`Go somewhere else` changes where the run goes next and nothing else. Indent it
under a check and it becomes the missing half:

```
 1. Look for the finished banner   If it is not found: skip the steps indented under it
     ↳ 2. Go somewhere else        -> leave this section and start the next one
 3. Pick the next item
```

If the banner is there, step 2 runs and the section is over. If not, step 2 is
skipped and the work carries on at 3.

It can send the run to the same four places an `If it is not found` can.

### When nothing is on screen to check

Some states do not show up in pixels at all: a list with nothing left to act on
looks exactly like a list you have not got to yet. What separates them is that
nothing is being *achieved*.

`When nothing has happened` finds nothing until its section has gone round that
many times without a single click or keystroke. Then it finds something once and
starts counting again:

```
 12. Pick the next item           If it is not found: skip the steps indented under it
     ...
 14. When nothing has happened    After 3 idle times round
     ↳ 15. Press Enter
```

A lap that clicked something is not idle, so a working loop never reaches it.
**Put it at the end of the section**, after everything that might achieve
something has had its go; otherwise a lap counts as idle before the steps that
would have made it productive have run.

The count belongs to the section and resets on hand-over.

## Timing and speed

### Give up after

`Give up after` decides how long Pixie sits doing nothing. Steps leave it unset
by default and take the sequence-wide value from Settings, which starts at 3
seconds. Set it to 0 to wait forever.

**The steps worth setting it on are the checks that run every lap and usually
find nothing**, because their wait is paid on every pass. Three such checks at 3
seconds is 9 seconds of every loop; a tenth of a second is often plenty.

**If a cycle feels slow, this is almost always why.** Look for these in the
log:

```
popup.png not there after 3s, skipping
toolbar.png did not appear after 30s
still waiting for toolbar.png, 15s so far (gives up in 15s)
```

Either shorten that step's own `Give up after`, or cap the whole section at once
from its divider.

### Search regions

Scanning the whole desktop is the slow part, and it scales with the area:

| Search area | Time per scan |
| --- | --- |
| A whole multi-monitor desktop | around 800 ms |
| One 1920x1080 monitor | around 120 ms |
| A 400x300 panel | around 16 ms |

Set a search region on every image and color step. Make the box comfortably
larger than where the target appears: anything outside it is invisible.

`How often to re-check` in Settings sets the gap between scans while a step
waits. At the default 0.25s a three-second wait scans about twelve times; at
0.05 it scans sixty. Lower it to catch something brief, raise it to save CPU.
The stop key is checked every 50ms regardless.

### Pauses

Every pause can be a range rather than a fixed number, so the timing varies.
Steps, sections and cycles each get their own: a delay between clicks and none
between screens.

**Pausing and parking only happen after a step that did something.** A step that
only looked at the screen has nothing to react to and nothing to move off. In a
loop of seven steps where two click, skipping the other five saves more than
every timeout in the loop put together. A step with its own pause still takes
it.

`Gap between repeats` covers the inside of a step rather than the space around
it: between the two clicks of a double-click, and between repeated taps of one
key step. It defaults to 0.05 to 0.12 seconds and is drawn fresh for every gap,
so no double-click is the same length as the last. Keep it under half a second
or two clicks stop reading as a double-click.

Every one of these has a per-step override, and the box says which
sequence-wide value it would use if you left it alone.

## The cursor

`After each step` sends the cursor somewhere harmless so it cannot sit over the
next thing Pixie looks at. Two settings:

* **Pick area...** drags a box instead of one spot, and the cursor lands
  somewhere different inside it every time.
* **Move the cursor there rather than warping it** travels over about a quarter
  of a second, eased at both ends.

Movement is sent as genuine input, the same way clicks are. A warped cursor
generates no input at all, so a game never learns the pointer moved and carries
on believing it is where it was: that is how something you hover stays enlarged
after the pointer has left it. Parking also nudges a pixel and back on arrival,
to shake loose a hover the application should have dropped.

**A section can refuse all of it.** Set `Cursor after a click in here` on the
divider to *leave it exactly where it is* and nothing in that section moves the
pointer except the clicks. The next section goes back to whatever Settings says.
Useful on a menu where hovering changes what is underneath.

The divider says so in the list:

```
=== Sign in ===   (cursor held still)
=== Main screen ===
```

A sequence saved with a single parking point gets a box one pixel across, so it
lands where it always did until you widen it.

## Pressing keys

`Press a key` records the key you actually press. `How many taps` and `Gap
between taps` repeat it. Whatever window has focus receives it, so make sure a
click step put focus there first.

When the log says `press Enter` and nothing happens, it is one of two things.

**The tap was too short.** Games usually check the keyboard once a frame, and a
tap that starts and finishes between two checks never happened as far as they
are concerned. `Hold each tap for (s)` defaults to 0.05, about three frames at
60fps. Try 0.1.

**It was the wrong key.** Enter, the digits, Shift, Ctrl and Alt each appear
twice on a keyboard, and Windows reports each pair as one key with a flag on it.
Games read input more directly and bind the two separately. If a press does
nothing, try its twin.

Pixie keeps them apart everywhere it shows a key:

```
Press Enter  (the main one)        Press Numpad Enter
Press Left Ctrl                    Press Right Ctrl
Press 5  (main keyboard)           Press Numpad 5
Press Q                            Press F8
```

Keys with no twin are shown plainly. Record one of a pair and the capture window
holds open a moment longer to name the other.

