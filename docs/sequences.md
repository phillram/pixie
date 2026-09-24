# Building sequences

Everything past the basics: how the editor behaves, how sections repeat
and hand over, how a step decides where the run goes next, and how to get
the timing right.

For getting a color step to find the right thing, see [matching a glow or a highlight](matching.md).

## Working in the editor

### Names, copies and pictures

Name a step and the list reads by that name, with the generated summary
following in brackets:

```
 2. Click the OK button   (Click ok.png)
 3. Confirm with Enter    (Press Enter  (the main one))
```

Names are labels and nothing reads them, so rename anything at any time. A
captured image keeps working after a rename, because the name only seeds the
filename when the image is first captured.

`Duplicate`, or Ctrl+D, copies the selected step with all its settings and drops
the copy underneath. It is the fast way to build several steps that differ only
by their image: duplicate, then recapture. Recapturing always writes a new file,
so it never overwrites the image the original is using.

Image and color fields show you what they hold. An image step displays the
picture and its size, and says plainly if the file has gone missing. A color
field shows a filled swatch and the hex value beside the RGB numbers.

Delete a step and Pixie offers to delete its picture too, but only when nothing
else uses it. Duplicated steps share one file, and so can two sequences.

Recapturing leaves the old file behind, which is how `images/` fills up with
near-identical pictures. To clear those out:

```
python tools/tidy_images.py            # list what nothing uses
python tools/tidy_images.py --apply    # delete them
```

Save your work first. A step you have not saved is not in any file, so its
picture looks unused.

### Typing

Every box takes the editing keys you would expect, which Tk leaves out:

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

**None of them start or stop a run.** That is the start/stop key in Settings,
which is a global hotkey precisely so it works when Pixie is not in front. A
test fails if the window ever answers to a key that is not in that table.

### What gets remembered

Pixie comes back the way you left her: the Dry run and Minimize settings, the
window size and position, whether it was maximized, which sequence was open, and
where the pane dividers were. A saved position on a monitor that no longer
exists is ignored rather than opening the window somewhere you cannot see it.

Pauses, keys and the cursor settings belong to the **sequence**, not to Pixie,
so different jobs can have different timing. Changing them saves the sequence
file straight away.

Sequences are JSON in `sequences/`. Captured images go in `images/`. Neither is
committed.


## Sections

If you have several independent screens to work through, split the sequence up.
Add a Section divider and everything below it belongs to that section until the
next divider.

A section repeats itself. When its last step finishes it goes back to that
section's first step. To leave, give a step (usually the first, the one that
detects the screen) `If it is not found: Leave this section and start the next
one`. After the last section Pixie wraps back to the first.

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

Each section counts its steps from 1. Dividers and notes are not counted, being
labels rather than instructions. While a sequence runs, the section Pixie is in
is highlighted in the list.

Select a divider and the section gets three settings of its own:

* **Pause when this section ends**, overriding the sequence-wide one here only
* **Cap every wait in here**, a ceiling on how long any step inside may wait. A
  step asking for 30 seconds, or for forever, gives up after the cap instead. A
  step that already waits less keeps its own shorter time. The log says so when
  the section starts: `=== Sign in === (nothing here waits longer than 3s)`
* **Cursor after a click in here**, covered under [The cursor](#the-cursor)

A sequence with no dividers is one section covering everything.

Switch off every step in a section and there is nothing to run and nothing to
end it, so Pixie says so before the run starts, and moves past it during one
rather than going round it forever in silence.

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

The first two get mixed up, so Pixie spells the difference out underneath the
dropdown using the names of your own sections:

```
Go back to the very first step of the sequence
    Abandons 'Main screen' and starts the whole script again from 'Sign in'.
    Everything before this step runs a second time.

Go back to the first step of this section
    Starts 'Main screen' again from its own step 1, and does not touch any
    other section.
```

### Checks that guard a group

Select a step and press Ctrl+Right to indent it under the step above. The step
above is then a check, and the indented run below it only happens when that
check finds what it is looking for:

```
 1. Look for the toolbar
 2. Did a dialog open?           If it is not found: skip the steps indented under it
     ↳ 3. Tick 'do not ask again'
     ↳ 4. Click OK
 5. Pick the next item
```

If step 2 finds nothing, 3 and 4 are skipped and the sequence carries on at 5.
If it does find something, they run in order. Ctrl+Left takes a step back out.

This is for the thing that only sometimes happens and needs more than one action
when it does. `Click a color if it appears` already covers the case where the
only action is a single click. Indenting is what you want when it is two clicks,
or a click and a pause, or a click and a keystroke.

`↑` and `↓` understand groups:

* Moving a check moves everything indented under it, as one thing, and it steps
  over a neighbouring group rather than landing inside it
* Moving an indented step reorders it within its group
* At either end of a group, moving further takes that step out of it. Only the
  first and last can do that without splitting the group in half

Delete or move a check and its group un-indents itself rather than being left
looking conditional under whatever fell above it. Pixie also checks the two
halves agree, because an indent that is not actually guarding anything looks
identical to one that is:

```
'Did a dialog open?' has 2 step(s) indented under it, but 'If it is not
found' is not set to 'Skip the steps indented under it', so they run whether
it finds anything or not.
```

Groups go one level deep, not more.

### When you need "if this IS found"

Every branch above is phrased the other way round, as `If it is not found`. That
covers most things, because a screen you were waiting on going away is usually
the same event as the next one arriving. The work area emptying *is* the job
finishing.

Sometimes it is not. A "finished" banner appearing over a screen that is still
working is its own event, and there is nothing whose absence means the same
thing.

`Go somewhere else` does nothing but change where the run goes next. On its own
it is unconditional, which is rarely useful. Indent it under a check and it
becomes the missing half:

```
 1. Look for the finished banner   If it is not found: skip the steps indented under it
     ↳ 2. Go somewhere else        -> leave this section and start the next one
 3. Pick the next item
```

If the banner is there, step 2 runs and the section is over. If it is not, step
2 is skipped and the work carries on at 3.

It can send the run to the same four places an `If it is not found` can, with
the same words for them.

### When nothing is on screen to check

Every other check asks what is on screen. Some states do not announce themselves
in pixels at all: a list with nothing left to act on looks exactly like a list
you have not got to yet. What tells them apart is that nothing is being
*achieved*, which is a fact about the run rather than about the screen.

`When nothing has happened` finds nothing until its section has gone round that
many times without a single click or keystroke. Then it finds something once,
and starts counting again:

```
 12. Pick the next item           If it is not found: skip the steps indented under it
     ...
 14. When nothing has happened    After 3 idle times round
     ↳ 15. Press Enter
```

A lap that clicked something is not idle, so a loop that is working never
reaches it. Put it at the **end** of the section, after everything that might
achieve something has had its go. Otherwise a lap counts as idle before the
steps that would have made it productive have run.

The count belongs to the section. Handing over to another section resets it, so
one section's quiet spell can never fire another section's check.

## Timing and speed

### Give up after

`Give up after` is the setting that decides how long Pixie sits doing nothing.
Steps leave it alone by default and take the sequence-wide one from Settings,
which starts at 3 seconds. So most steps need nothing here, and there is no row
of thirty-second waits nobody meant.

Set it on a step when that step is different. **The ones worth setting are the
checks that run every time round a loop and usually find nothing**, because
their wait is paid on every single pass. Three such checks at 3 seconds is 9
seconds of every loop spent waiting for things that are not there, and a tenth
of a second is often plenty. Set it to 0 to wait forever instead.

**If a cycle feels slow, this is almost always why.** The log gives you the
number to look for:

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

Set a search region on every image and color step. It is the single biggest
speed win available. Make the box comfortably larger than where the target
appears, because anything outside it is invisible to the matcher.

`How often to re-check` in Settings decides how many of those scans happen
while a step is waiting. At the default of 0.25 seconds a step waiting three
seconds scans about twelve times; at 0.05 it scans sixty. Lower it when you
need to catch something brief, raise it when a step is just burning CPU
waiting for a screen that takes a while. The stop key is checked every 50ms
regardless, so a long interval never makes stopping sluggish.

### Pauses

Every pause can be a range rather than a fixed number, so the timing varies.
Steps, sections and whole cycles each get their own, so you can have a delay
between clicks and none at all between screens.

**Pausing and parking only happen after a step that did something.** Both exist
to deal with the aftermath of an action. The application needs a moment to
react, and the cursor needs moving off whatever it just clicked. A step that only
looked at the screen has neither. In a loop of seven steps where two of them
click, skipping the other five saves more time than every timeout in the loop put
together. A step with its own pause still takes it, because that was asked for
deliberately.

## The cursor

`After each step` sends the cursor somewhere harmless so it cannot sit over the
next thing Pixie needs to look at. Two settings make it less mechanical:

* **Pick area...** drags a box rather than clicking one spot, and the cursor
  lands somewhere different inside it every time. One pixel, hit exactly, every
  few seconds for hours, is not what a hand does.
* **Move the cursor there rather than warping it** travels to the spot over about
  a quarter of a second, eased at both ends, instead of teleporting.

All movement is sent the same way clicks are, as genuine input. The obvious way
to move a cursor moves it without telling anyone, so a game never learns the
pointer went anywhere and carries on believing it is where it was. That is how
something that grows when you hover it stays grown after the pointer has
visibly left it.

Parking also nudges a pixel and back on arrival, because an application that
only re-checks what is under the pointer when the pointer moves can otherwise be
left holding a hover it should have dropped.

**A section can refuse all of it.** Set `Cursor after a click in here` on the
divider to *leave it exactly where it is*, and nothing in that section moves the
pointer except the clicks themselves. No parking, and none of the nudge that
follows one. The next section goes back to whatever Settings says.

That is a property of the screen rather than of the job. A menu where the cursor
passing over an entry changes what is underneath it does not want the pointer
wandering, while the screen after it may need exactly that. The divider says so
in the list, because it changes what runs without appearing among the steps:

```
=== Sign in ===   (cursor held still)
=== Main screen ===
```

A sequence saved before this existed had a single point, which becomes a box one
pixel across. It carries on landing exactly where it always did until you widen
it.

## Pressing keys

`Press a key` records the key you actually press. `How many taps` and `Gap
between taps` repeat it. Whatever window has focus receives it, so make sure a
click step put focus there first.

When the log says `press Enter` and the application carries on as if nothing
happened, it is one of two things.

**The tap was too short.** Applications that read every keyboard event cannot
miss a tap however brief, but games usually check the keyboard once a frame
instead, and a tap that starts and finishes between two checks never existed as
far as that game is concerned. `Hold each tap for (s)` is the dial. It defaults
to 0.05, around three frames at 60fps. Try 0.1 before suspecting anything
subtler.

**It was the wrong key.** A keyboard has several keys printed twice: Enter, the
digits, Shift, Ctrl, Alt. Windows reports each pair as one key with a flag on it,
so anything reading ordinary window messages cannot tell you which one you sent.
Games read input more directly, where the difference is plainly visible, and they
bind the two separately. If a press does nothing, try its twin.

Pixie keeps them apart and says which is which everywhere it shows a key:

```
Press Enter  (the main one)        Press Numpad Enter
Press Left Ctrl                    Press Right Ctrl
Press 5  (main keyboard)           Press Numpad 5
Press Q                            Press F8
```

Keys with no twin are shown plainly, so the qualifier only appears where it earns
its space. When you record one of a pair, the capture window holds open a moment
longer to name the other one.

