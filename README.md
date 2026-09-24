# Pixie

Pixie watches your screen, finds things on it, and clicks them. You build a
sequence by pointing at what she should look for, then she repeats it until you
tell her to stop.

It is for the kind of job that is too fiddly to script properly and too dull to
do by hand: the same twelve clicks through the same four screens, over and over.

Windows only. Dark themed.

## Contents

1. [Getting it running](#getting-it-running)
2. [Building a sequence](#building-a-sequence)
3. [The steps](#the-steps)
4. [Sections](#sections)
5. [Making a sequence decide things](#making-a-sequence-decide-things)
6. [Timing and speed](#timing-and-speed)
7. [The cursor](#the-cursor)
8. [Pressing keys](#pressing-keys)
9. [Finding a glow or a highlight](#finding-a-glow-or-a-highlight)
10. [When it picks the wrong thing](#when-it-picks-the-wrong-thing)
11. [Running it](#running-it)
12. [Is this the right tool?](#is-this-the-right-tool)
13. [Development](#development)

## Getting it running

Download `Pixie.exe` from the
[latest release](https://github.com/phillram/pixie/releases/latest) and double
click it. No Python, nothing to install. Put it in a folder of its own, because
it creates `sequences/` and `images/` beside itself.

From source instead, with Python 3.10 or newer:

```
pip install -r requirements.txt
python -m pixie
python tools/build_exe.py      # produces Pixie.exe, about 70MB, twenty seconds
```

That pulls in mss for screen capture, OpenCV and NumPy for matching, and Pillow
for the capture overlay. tkinter ships with Python on Windows.

## Building a sequence

A sequence is a list of steps. Pixie runs them top to bottom, then starts again,
looping until you stop her.

Build one in the left pane, edit the selected step in the right pane, watch the
log along the bottom. The three panes are separated by dividers you can drag,
and where you put them is remembered.

Every image, color, point and region has a Capture button. The window hides, the
screen freezes, and you drag a box or click a pixel to say what you mean. Boxes
are four editable numbers as well, so you can nudge an edge ten pixels without
re-dragging the whole thing.

### Seeing what a step will do

Three buttons answer the questions a log cannot.

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
genuinely go rather than a second guess at it. A step that clicks whatever was
found last has nothing to show alone, so the step before it runs first. A step
that picks a random spot in a box shows twenty more it could have chosen.

None of them write anything to disk unless you press `Save picture...`.

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

One level deep, deliberately. The file stays a flat list with one number per
step, so reordering, sections and the save format are untouched by it.

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

## Finding a glow or a highlight

This is the part worth reading, because the obvious approach does not work well.

A glow is one color spread across a brightness gradient, close to white at its
core and nearly black at its edges. Those are far apart in RGB, so matching a
single sampled value catches only a slice of the glow, and which slice depends on
how bright it happens to be at that moment. That is why it feels unreliable.

Hue barely changes across that gradient. Set `Match the color by` to `hue`, give
a tolerance in degrees, and it catches the whole thing. On a cyan glow fading
from dark to white:

| Mode | Pixels matched |
| --- | --- |
| rgb, tolerance 50 | 1,640 |
| hue, tolerance 14 | 8,680 |

Same color, five times the coverage, and far steadier frame to frame. Use `rgb`
for flat, solid colors that do not change.

### Sampling the color

One pixel is a poor sample of a glow. Its edges are washed out and its middle is
nearly white, so whichever pixel you happen to land on decides everything. Land
on the pale fringe and the step will never match the thing you meant.

`Sample an area...`, beside the color picker, drags a box instead and works the
settings out from what is in it: the color, the tolerance, and the saturation and
brightness floors. It reports how much of what you dragged over those settings
would match, and tells you when the color is flat enough that RGB would do just
as well. `python tools/tune_color.py` does the same from a terminal.

### An outline is not one shape

This is the thing that will bite you.

A highlight around a tile or a button is almost never one connected patch of
color. Whatever overlaps it cuts it up, its edges soften, and its corners fade
out, so what the matcher sees is a scattering of fragments. A single outline can
arrive as a dozen separate pieces.

That matters because everything is measured from the middle of a *patch*. If the
patch is a 10x16 fragment of the left edge, its middle is on the left edge, and a
step that clicks slightly below it clicks the wrong thing entirely.

`Join pieces up and down (px)` is the fix. Set it to comfortably more than the
widest gap in the outline, 20 to 40 for a tile border, and the pieces count as
one patch again, whose middle is the middle of the tile. On a test with two tile
borders broken into 48 fragments:

| Join | Patches found | Middle of the first one |
| --- | --- | --- |
| 0 | 48 | 224px away from the tile's middle |
| 20 | 2 | exactly the tile's middle |

The log warns when it sees the pattern:

```
3 patches matched, took the one furthest left.
    If those are pieces of one outline, set 'Join pieces up and down' on this step
```

Once the whole outline is one patch, a following `Click the last thing found`
wants an offset of `0, 0`. An offset was only ever needed to compensate for
landing on a fragment.

### What joining costs

Joining gathers a scatter of specks as readily as it gathers the pieces of a real
outline. From a real run:

```
found RGB(37, 254, 254) - 476 pixels in a 500x110 box, 45 pieces joined
```

Forty-five pieces of about ten pixels each, spread across half the strip,
clicked as though they were one tile. Every limit on the step passed, because
**every one of them is measured on the assembled shape**. That is the whole
point of joining, and it is also what lets joining manufacture a patch out of
noise.

`Ignore pieces smaller than (px)` is the one setting that runs *before* joining.
Real pieces of an outline are hundreds of pixels and specks are tens, so 100
separates them with room to spare and the noise is gone before joining can rescue
it.

| Ignore pieces smaller than | Patch found |
| --- | --- |
| 0 | 700x240, 40 pieces. Specks and outline as one, leftmost is a speck |
| 100 | 360x240, 1 piece. The outline alone |

### Up and down is not sideways

**What breaks an outline up and what sits next to it are different things.**

A tile overlapped by its neighbour shows a top bar with slivers of its sides
below it, pieces stacked above one another, needing a generous reach upward.
Anything else on screen glowing the same color is *beside* it: a lit panel, an
icon, a beam. Every pixel of sideways reach is an invitation to those.

So the two are separate settings. From a real strip, with a lit panel in the
background 40px clear of a tile:

| Reach | Result |
| --- | --- |
| 40 both ways | one 560x310 patch starting at the panel, so `leftmost` with a left-edge anchor clicks the panel |
| 40 up and down, 0 sideways | two patches: the panel alone, and the tile's outline whole at 480x290 |

The outline still comes together, because its slivers join through the bar above
them rather than across to each other. The two sides of one tile are a tile's
width apart and were never going to join sideways anyway.

**Start `Join pieces side to side` at 0.** Raise it only if you can see, in What
matches?, a real piece of your target that is not connecting any other way.

A sequence saved before this setting existed inherits the old distance in both
directions, so it behaves exactly as it did until you change it.

### Size, after joining

`Patch at least this wide` and `Patch at least this tall` are checked *after*
joining, so they judge the whole assembled shape. That is what makes them work
against a background: a beam stays a sliver however many pieces it is joined
from.

Saturation cannot help when a background thing genuinely glows, like a lit beam
or a bright sign. But a beam is not shaped like the thing you want. A tile
highlight is as wide as a tile:

```
  1. 45x306 at 170, 850     3092 pixels
  2. 776x306 at 529, 850   10357 pixels
  3. 31x188 at 1638, 968    3985 pixels
```

Same hue, same saturation, same height, and 45px wide against 776px. What
matches? looks for that split and names the setting that acts on it:

```
These split into two groups by width: 2 up to 45px and 1 from 776px.
Setting 'Patch at least this wide (px)' to 187 would keep the 1 bigger
and drop the 2 smaller.
```

It only says this when the sizes really do fall into two groups.

Set a size filter against what a badly covered target looks like, not a clean
one. A tile in the middle of a row shows only its top bar and two slivers of its
sides, so a minimum height picked from a fully visible tile throws it away
entirely.

### Where it sits beats what color it is

Color is the weakest thing you have. Size and shape are better. **Position is the
best of the lot**, when the thing you want has one.

A row of tiles spreads wider as it grows and each one can sit at its own angle,
so their size, their tilt and the gaps between them all move about. What never
moves is that the row sits along the bottom of the screen. Every tile's glow
reaches the bottom of an area drawn over the row, and a lit panel in the
background does not, whatever color it is.

`Must run off the edge` says so, and anything that does not reach that edge is
dropped and told why:

```
Must run off the edge   it must run off the bottom

Ignored (1):
  500x220 at 100, 30   does not reach the bottom of the area
```

This is the one test that survives a change of background, because it is not
about the background at all.

It is not a substitute for the size limits, though. A vertical beam running the
full height of the screen *does* reach the bottom, so only `Patch at least this
wide` drops it. A panel floating above the row is the right shape but the wrong
place, so only this drops it. Set both.

### When the background is the same color

Hue matching finds a *shade*, and plenty of backgrounds are the same shade as the
thing you want. A blue scene behind a blue highlight is the hard case. It gets
worse with joining switched on, because joining will happily glue a background
streak onto your target and report the middle of the pair:

| Saturation floor | Patch found | Middle |
| --- | --- | --- |
| 90 (default) | 1000x290, streak and outline as one | 80px off the tile |
| 180 | 360x290, the outline alone | exactly right |

**Saturation is what separates them.** A highlight is vivid, and a background of
the same hue is usually washed out towards white or grey. `Min saturation` throws
away the washed-out pixels before anything else happens.

To find the number, press **What matches?**. Each patch is listed with how
saturated it actually is:

```
Would be used, in order (leftmost):
  1. 1000x290 at 100, 10   59913 pixels   middle 600, 155   saturation 120-250
```

A range that wide is the tell. 120 is the background, 250 is the highlight. Set
`Min saturation` between them, 180 here, and look again:

```
  1. 360x290 at 500, 10   26468 pixels   middle 680, 155   saturation 250-250
```

One patch, the outline alone, centred on the tile.

### The order to tune in

Each of these depends on the one before it:

1. **Min saturation**, until only the thing you want is tinted
2. **Ignore pieces smaller than**, to clear the speckle left behind
3. **Join pieces up and down**, to pull the fragments together. Leave **side to
   side** at 0 unless something genuinely needs it
4. **Patch at least this wide / tall**, to drop any streaks that survive
5. **Must run off the edge**, to drop anything in the wrong part of the screen
6. **If several match**, to choose between the real candidates

The first three come first because joining a dirty mask glues the mess together,
and everything after joining is measured on whatever came out of it. Once noise
is inside a patch, no later setting can get it out again.

## When it picks the wrong thing

### Several things glowing at once

A row of tiles can all be highlighted at the same time. `If several match, use`
decides which one Pixie goes for:

| Setting | Which patch |
| --- | --- |
| the biggest one | The largest patch of the color. The default |
| the one furthest left | Lowest x. Right for working along a row in reading order |
| the one furthest right | Highest x |
| the one nearest the top | Lowest y |
| the one nearest the bottom | Highest y |

The biggest patch is whichever glow happens to be brightest or fattest at that
instant, which is why it can look like it picks at random. Set it to `the one
furthest left` and a section that repeats works along the row from the left.

The log says when there was a choice to make:

```
found RGB(37, 254, 254) - 8680 pixels in a 180x250 box, center 640, 900
    - 3 patches matched, took the one furthest left
```

### Two targets that touch

Highlights next to each other can arrive as one patch. Two tiles side by side,
their outlines touching, come back as a single wide box, and the middle of that
box is the gap between the two. No amount of joining or unjoining fixes it,
because at that point the two outlines are genuinely one shape.

`Aim at` is the answer. Every step that clicks something it found can aim at an
edge or a corner instead of the middle, and the offset is applied from there:

| Aim at | Then offset by | Lands on |
| --- | --- | --- |
| the middle of it | 0, 0 | the middle, wrong when two merged |
| its left edge | +90, 0 | the left one, merged or not |

On a real pair of merged outlines 720px wide, the middle lands at 560, exactly
the seam, while the left edge plus 90 lands at 290, well inside the left tile. It
works the same whether the two merged that frame or not, which is what makes it
reliable rather than lucky.

An edge follows the **shape**, not the box around it. On a row of tilted tiles
that is the whole thing: they lean different ways and sit at different heights,
so the box round a merged group belongs to no tile at all.

| | y |
| --- | --- |
| Middle of the box | 240, the left tile's top frame |
| Where the shape meets the left edge | 359, the middle of that tile |

Corners still use the box, because a corner of a shape is not a well defined
thing. Image matches are rectangles, so their box is the truth.

### An intruder joined on

Joining sweeps up *anything* of the same color within reach. A lit panel 50px
from a tile gets pulled in, and then the patch is wider than the tile and its
left edge is the panel's left edge.

Nothing about that patch looks wrong. Sizes are only measured after joining, so
the intruder inherits the outline's height and sails past every minimum you set,
and the only symptom is a click landing somewhere strange. So Pixie counts the
pieces and says so:

```
found RGB(37, 254, 254) - 6848 pixels in a 478x313 box, 2 pieces joined, ...
    that patch is 2 separate pieces joined together, so its left edge belongs
    to whichever piece sits furthest that way, which may not be part of what
    you are after.
```

It only says this when a step aims at an *edge*. Aiming at the middle is barely
affected by a small piece joined on. Aiming at an edge means that piece decides
where the click goes.

To see which piece is the intruder, set `Join pieces up and down` to 0 and press
What matches?. The pieces appear separately and the wrong one is obvious. Then
either tighten `How far off it may be` or raise `Min saturation` until it stops
matching, or shrink the search area so it falls outside.

### A find that is far too small

Every floor on a step is a number somebody had to guess, and the guess only goes
wrong in one direction: too low, so something of roughly the right color slips
through and gets clicked. Nothing about such a find reads as wrong on its own.
"71 pixels" looks like a fact, not a problem.

It only looks wrong beside the other times the same step ran. So Pixie keeps the
sizes each color step has been finding during this run, and says something when
one comes back far smaller than the rest:

```
found RGB(185, 187, 139) - 71 pixels in a 18x8 box, center 950, 797
    that is far smaller than the 12,877 pixels this step usually finds, so it
    is probably something else that happens to be the right color. Raise
    'Smallest patch' from 40 towards 6,438.
```

The step's own history is the yardstick, so there is no threshold to guess at and
it calibrates itself to whatever you are looking for. A step whose finds
legitimately vary, anywhere between 3,566 and 13,622 pixels, is not nagged, and a
stray find does not drag the yardstick down behind it.

### A picture that did not match

"It did not appear" reads the same whether the picture was a hair under the
threshold or nothing like what is on screen, and those want opposite fixes. So
the log says how close it got:

```
finished_banner.png did not appear after 1s
    the best match anywhere in that area scored 0.42, which is nothing like
    it. The picture is of something that is not on screen, or the area is in
    the wrong place.
```

| Score | What it means |
| --- | --- |
| Just under the threshold | Lower `How close a match` a little |
| Around 0.5 to 0.8 | Something like it is there but has changed. Recapture |
| Below 0.5 | Wrong picture, or the search area is in the wrong place |

**Keep template pictures small and away from anything that animates.** A big
capture of a screen with a pulsing glow, a see-through overlay, or a changing
background behind it can never score highly, because most of what is in the
picture is different every frame. A small, solid, high-contrast piece of
interface matches far more reliably than a large region containing it.

## Running it

F9 starts the run and stops it again. It works while the application you are
automating has focus, which is the only time it is any use, so you never have to
go and find Pixie's window.

To stop, any of these, all of which work from another application:

* F9 again
* The Stop button
* F8
* Put the mouse in the top left corner of the screen

All of them are checked between every step and during every wait, so it stops
within about 50ms. Both keys are configurable in Settings, and the start/stop key
can be switched off entirely if it clashes with something.

Pixie minimizes herself when you press Start, so she is not sitting on top of the
thing she is clicking. She keeps running, and the taskbar title counts the
cycles. Untick `Minimize while running` if you would rather watch.

**Leave Dry run ticked the first few times.** It does the full detection and
writes every click it would have sent to the log, without sending any. That is
how you confirm the coordinates are right before anything real happens.

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

If your target is a normal Windows application or a web app, look at pywinauto or
Playwright first. Those find the actual button labelled OK, and none of the above
bothers them.

Pixel matching is the right choice when there is nothing to read but the picture,
which covers anything that draws its own interface: games, Unity and SDL
applications, custom renderers. `tools/check_target.py` prints the window class of
whatever is in the foreground, which tells you which case you are in.

Some fullscreen applications use exclusive fullscreen, which screen capture reads
as a black frame. `check_target.py` detects that too. The fix is usually a setting
in the application: switch it to borderless windowed.

## Development

```
python tools/check_wiring.py   # imports and step wiring, no screen needed
python tests/selftest.py       # detection, color matching, sections, real input
python tests/selftest_gui.py   # every step editor, reordering, save and reload
```

`check_wiring.py` is what CI runs, because it needs no desktop. The other two do,
because they capture the real screen and send real input.

`selftest.py` crops a patch of your actual screen and matches it back, checks hue
matching beats RGB on a synthetic gradient, runs a three section sequence to
confirm each one repeats until its start point fails, checks a click box lands
inside itself and never twice in the same place, and sends real keystrokes and a
real double click to its own window. It skips the input checks rather than firing
stray keystrokes if its test window cannot take focus.

Key identity is checked at the flags rather than by asking a window what
arrived, because a window cannot tell the main Enter from the numpad one. Both
report the same code. `.scratch/check_enter_key_identity.py` listens on the
channel a game reads, for when you want to see it end to end.

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
│   │   ├── mouse.py       movement and clicks
│   │   └── keyboard.py    key presses
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
nobody is looking. So each of these has exactly one home:

| Thing | Lives in | What a test proves about it |
| --- | --- | --- |
| Step types and their fields | `STEP_TYPES` | every type has a `_do_` handler and a full set of defaults |
| Default values for a field | the `Field` declaration | the engine reads them through `_value`, never its own copy |
| Which editor draws a field | `App.FIELD_BUILDERS` | every declared kind has one |
| The "if not found" options | `ON_TIMEOUT_CHOICES` | every option has a branch in `run_cycle`, found by reading the source |
| Where a jump can send the run | `JUMP_TARGETS` | a subset of the above, with the same branches |
| Which menu heading a step sits under | `STEP_GROUPS` | every type appears exactly once, with a hint |
| Labels for dropdown values | `CHOICE_LABELS` | every choice on every field has one |
| Log levels | `engine.LOG_LEVELS` | every level has a color in the GUI |
| Which patch to pick | `screen.PICK_ORDERS` | each order sorts differently from the fallback, and steps agrees |
| Which edge to require | `screen.REACH_SIDES` | every side is one the matcher reports reaching |
| Where the cursor parks | `engine.PARK_LABELS` | `_park_target` branches on every mode |
| Whether a section holds it still | `steps.SECTION_PARK` | all labelled, and `_enter_section` reads it |
| Keys that can be a hotkey | `screen.hotkey_names()` | `key_pressed` accepts every one it offers |
| Mouse buttons | `steps.BUTTONS` | `mouse.click` knows each one |
| Where to aim on a match | `steps.ANCHORS` | no two aim at the same pixel |
| Default values for a field | the `Field` declaration | the engine has no `step.get(key, literal)` restating one |
| What a stored image path means | `paths.resolve` | `tidy_images` decides with it, rather than its own string compare |
| What each setting is called | the `Field` declaration | `tune_color` prints those labels rather than its own |
| Commands printed at you | the code that prints them | every script named in `pixie/` or `tools/` exists |
| Keys Pixie can send | `keyboard.KEYS` | no two fold onto one name, all have plain English, extended flags name real keys |

`check_wiring.py` does all of those except the keyboard, which needs
`selftest.py`.

The rule when adding anything: declare it once, and if a second place needs to
know about it, make `check_wiring.py` prove they agree.
