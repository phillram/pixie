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
* Indent steps under a check, so a group of actions only runs when that check
  finds what it is looking for
* Tell a match apart from the background by where it sits, not only by its
  color: require it to run off a given edge of the search area

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

Two buttons beside it answer questions a log cannot, by showing you a picture
of your own screen instead of describing one:

* **What matches?** on a step that searches an area for a color: every
  matching pixel tinted, every patch boxed and numbered in the order the step
  would use them, the rejected ones greyed out with the reason, and the
  saturation of each so you can tell a highlight from a background
* **Show the click** on any step that clicks: a crosshair on the exact spot,
  at life size, with the thing it found boxed around it

Show the click runs the step for real and intercepts only the click itself, so
the crosshair is where the click would genuinely go rather than a second guess
at it. A step that clicks whatever was found last has nothing to show on its
own, so the step before it is run first and the window says so. A step that
picks a random spot in a box shows twenty more spots it could equally have
chosen.

Neither writes anything to disk unless you press `Save picture...`.

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

The three panes are separated by dividers you can drag: sequence against
editor, and both against the log. Where you put them is remembered. Which pane
needs to be big depends on what you are doing, so none of them is a fixed
size.

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

**Add step** groups them under these headings, and repeats the short
description beside each name, so you can tell `Click an image` from `Click an
image if it appears` without opening both.

| Step | What it does |
| --- | --- |
| **Structure** | |
| Section divider | Marks the start of a section |
| Note | Does nothing. Somewhere to explain the sequence to yourself |
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

The grouping lives in `STEP_GROUPS` in `pixie/core/steps.py` next to the step
types themselves, and `check_wiring.py` fails if a type is declared without a
place in the menu - since the menu is the only way to create one.

### When something does not turn up

Any step that waits has a `Give up after (s)` and an `If it is not found`.
That pair is worth understanding, because between them they decide how long
Pixie sits doing nothing:

| If it is not found | What happens |
| --- | --- |
| Go back to the very first step of the sequence | The whole script starts again. Everything before this step runs a second time |
| Go back to the first step of this section | Only this section starts again. No other section is touched |
| Skip it and run the next step anyway | Runs the next step as though this one had worked |
| Skip the steps indented under it | Jumps the whole group below it. See Checks that guard a group |
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

### Checks that guard a group

Select a step and press **→** (or Ctrl+Right) to indent it under the step
above. The step above is then a check, and the indented run below it only
runs when that check finds what it is looking for:

```
 1. Look for card back
 2. Is a target wanted?          If it is not found: skip the steps indented under it
     ↳ 3. Click on myself
     ↳ 4. Wait a moment
 5. Select playable card
```

If step 2 finds nothing, 3 and 4 are skipped and the sequence carries on at 5.
If it does find something, they run in order. **←** (Ctrl+Left) takes a step
back out.

This is for the thing that only sometimes happens and needs more than one
action when it does. `Click a color if it appears` already covers the case
where the only action is a single click; indenting is what you want when it is
two clicks, or a click and a pause, or a click and a keystroke.

Without it, the only way to express "sometimes" was to put the actions behind
a step set to restart the section - which deadlocks the moment the thing being
waited for is itself what stops the other steps from finding anything. A
targeting prompt does exactly that: while it is up, no card in hand is
playable, so a card check placed above it restarts the section forever and the
step that would clear the prompt is never reached.

Pixie checks the two halves agree, because an indent that is not actually
guarding anything looks identical to one that is:

```
'Is a target wanted?' has 2 step(s) indented under it, but 'If it is not
found' is not set to 'Skip the steps indented under it' - so they run
whether it finds anything or not.
```

Delete or move a check and its group un-indents itself, rather than being left
looking conditional under whatever fell above it.

One level deep, deliberately. The file stays a flat list with one number per
step, so reordering, sections and the save format are all untouched by it.

`Give up after` is the timeout, and it is the setting that decides how long
Pixie sits doing nothing. It defaults to 30 seconds on a step that waits for
something, and 1 second on an "if it appears" step. Set it to 0 and it waits
forever instead.

**If a cycle feels slow, this is almost always why.** An optional step whose
image never appears costs its whole timeout on every single pass: two of them
at 3 seconds is 6 seconds of every cycle spent waiting for things that are not
there. The log gives you the number to look for:

```
burst_lightning.png not there after 3s, skipping
main_menu.png did not appear after 30s
```

Either shorten that step's own `Give up after`, or cap the whole section at
once with `Cap every wait in here at (s)` on its divider. The cap only ever
lowers a wait: a step already set to 0.5s keeps its 0.5s.

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

## An outline is not one shape

This is the thing that will bite you, so it is worth understanding before you
build anything around a glowing border.

A highlight around a card or a button is almost never one connected patch of
color. Whatever overlaps it cuts it up, anti-aliasing softens its edges, and
its corners fade out, so what the matcher actually sees is a scattering of
fragments. A single card outline can arrive as a dozen separate pieces.

That matters because everything is measured from the middle of a *patch*. If
the patch is a 10x16 fragment of the left edge, its middle is on the left edge,
and a step that clicks slightly below it clicks the wrong thing entirely.

`Join pieces within (px)` is the fix. Set it to comfortably more than the
widest gap in the outline - 20 to 40 for a card border - and the pieces count
as one patch again, whose middle is the middle of the card. On a test with two
card borders broken into 48 fragments:

| Join | Patches found | Middle of the first one |
| --- | --- | --- |
| 0 | 48 | 224px away from the card's middle |
| 20 | 2 | exactly the card's middle |

The log warns when it sees the pattern:

```
3 patches matched, took the one furthest left.
    If those are pieces of one outline, set 'Join pieces within' on this step
```

Once the whole outline is one patch, a following `Click the last thing found`
wants an offset of `0, 0`: the middle of the outline is already the middle of
the card. An offset was only ever needed to compensate for landing on a
fragment.

### What joining costs

Joining gathers a scatter of anti-aliased specks as readily as it gathers the
pieces of a real outline. From a real run:

```
found RGB(37, 254, 254) - 476 pixels in a 500x110 box, 45 pieces joined
```

Forty-five pieces of about ten pixels each, spread over half the hand, clicked
as though it were a card. Every limit on the step passed: 476 is over the
`Smallest patch` floor of 39, and 500x110 clears both size limits. They all
had to pass, because **every one of them is measured on the assembled shape** -
that is the whole point of joining, and it is also what makes joining able to
manufacture a patch out of noise.

`Ignore pieces smaller than (px)` is the one setting that runs *before*
joining. Real pieces of an outline are hundreds of pixels; specks are tens, so
100 separates them with room to spare and the noise is gone before joining can
rescue it.

| Ignore pieces smaller than | Patch found |
| --- | --- |
| 0 | 700x240, 40 pieces - specks and outline as one, leftmost is a speck |
| 100 | 360x240, 1 piece - the outline alone |

### Up and down is not sideways

Joining reached the same distance in every direction, and that is the wrong
shape for the problem. **What breaks an outline up and what sits next to it
are different things.**

A card overlapped by its neighbour shows a top bar with slivers of its sides
below it - pieces stacked above one another, needing a generous reach upward.
Anything else on screen glowing the same color is *beside* it: a lamp, a lit
prop, a beam. Every pixel of sideways reach is an invitation to those.

So the two are separate settings. From a real hand, with a lit bottle in the
background 40px clear of a card:

| Reach | Result |
| --- | --- |
| 40 both ways | one 560x310 patch starting at the bottle - and `leftmost` with a left-edge anchor then clicks the bottle |
| 40 up and down, 0 sideways | two patches: the bottle alone, and the card's outline whole at 480x290 |

The outline still comes together, because its slivers join through the bar
above them rather than across to each other - the two sides of one card are a
card's width apart and were never going to join sideways anyway.

**Start `Join pieces side to side` at 0.** Raise it only if you can see, in
What matches?, a real piece of your target that is not connecting any other
way.

A sequence saved before this setting existed inherits the old distance in both
directions, so it behaves exactly as it did until you change it.

### Where it sits beats what color it is

Color is the weakest thing you have. Size and shape are better. **Position is
the best of the lot**, when the thing you want has one.

A hand of cards fans wider as it grows and every card tilts differently, so
their size, their angle and the gaps between them all move about. What never
moves is that a hand sits at the bottom of the screen: every card runs off the
bottom edge. So every card's glow reaches the bottom of an area drawn over the
hand, and a lit prop in the background does not - whatever color it is, and
whatever the playmat behind it looks like.

`Must run off the edge` says so:

```
Must run off the edge   it must run off the bottom
```

Anything that does not reach that edge of the search area is dropped, and says
why:

```
Ignored (1):
  500x220 at 100, 30   does not reach the bottom of the area
```

This is the one test that survives a change of background, because it is not
about the background at all.

It is not a substitute for the size limits, though - the two catch different
things. A vertical beam running the full height of the screen *does* reach the
bottom, so only `Patch at least this wide` drops it. A prop floating above the
hand is the right shape but the wrong place, so only this drops it. Set both.

### What joining costs when the intruder is real

Joining sweeps up *anything* of the same color within reach, not only pieces
of the thing you meant. A lit prop in the background 50px from a card gets
pulled in, and then the patch is wider than the card, and its left edge is the
prop's left edge rather than the card's.

Nothing about that patch looks wrong. Sizes are only measured after joining -
which is the whole point, since fragments are short on their own and tall
together - so the intruder inherits the outline's height and sails past every
minimum you set. The only symptom is a click landing somewhere strange.

So Pixie counts the pieces and says so:

```
found RGB(37, 254, 254) - 6848 pixels in a 478x313 box, 2 pieces joined, ...
    that patch is 2 separate pieces joined together, so its left edge belongs
    to whichever piece sits furthest that way, which may not be part of what
    you are after.
```

It only says this when a step aims at an *edge*. Aiming at the middle of a
patch is barely affected by a small piece joined on; aiming at an edge means
that piece decides where the click goes.

To see which piece is the intruder, set `Join pieces within` to 0 and press
**What matches?**. The pieces appear separately, and the one that is not part
of the thing you want is obvious. Then either tighten `Tolerance` or raise
`Min saturation` until it stops matching at all, or shrink the search area so
it falls outside. Lowering the join below the gap works too, but only if that
still leaves enough to bridge the real gaps in the outline.

## When the background is the same color

Hue matching finds a *shade*, and plenty of backgrounds are the same shade as
the thing you want. A blue spaceship interior behind a blue card highlight is
the hard case: same hue, and the pale parts of it pass the default saturation
floor.

It gets worse with joining switched on, because joining will happily glue a
background streak onto your target and report the middle of the pair. On a
test where a washed-out streak crosses a card outline:

| Saturation floor | Patch found | Middle |
| --- | --- | --- |
| 90 (default) | 1000x290, streak and outline as one | 80px off the card |
| 180 | 360x290, the outline alone | exactly right |

**Saturation is what separates them.** A highlight is vivid; a background of
the same hue is usually washed out towards white or grey. `Min saturation`
throws away the washed-out pixels before anything else happens.

### When the background is the same color *and* just as vivid

Saturation cannot help when the background thing genuinely glows - a lit beam,
a rim light, a neon sign. But a beam is not shaped like the thing you want. A
card highlight is as wide as a card; a beam behind it is a sliver:

```
  1. 45x306 at 1170, 1853    3092 pixels
  2. 776x306 at 1529, 1853  10357 pixels
  3. 31x188 at 2638, 1971    3985 pixels
```

Same hue, same saturation, same height - and 45px wide against 776px. So
**What matches?** looks for that split and names the setting that acts on it:

```
These split into two groups by width: 2 up to 45px and 1 from 776px.
Setting 'Patch at least this wide (px)' to 187 would keep the 1 bigger
and drop the 2 smaller.
```

It only says this when the sizes really do fall into two groups. Patches all
much of a muchness get no advice, because there is none worth giving.

`Patch at least this wide` and `Patch at least this tall` are checked *after*
joining, so they judge the whole assembled shape. That is what makes them
work against a background: a beam stays a sliver however many pieces it is
joined from.

### Sampling a color properly

One pixel is a poor sample of a glow. Its edges are washed out and its middle
is nearly white, so whichever pixel you happen to land on decides everything -
land on the pale fringe and the step will never match the thing you meant.

`Sample an area...`, beside the color picker, drags a box instead and works
the settings out from what is in it: the color, the tolerance, and the
saturation and brightness floors. It reports how much of what you dragged over
those settings would match, and tells you when the color is flat enough that
RGB matching would do just as well.

`python tools/tune_color.py` does the same from a terminal, using the same
code, for when you want the numbers without opening the window.

### Finding the number

Guessing at it is miserable, so press **What matches?** next to Test this
step. Pixie hides, photographs the search area, and shows it back to you with
every matching pixel tinted magenta, each patch boxed, and the ones it would
reject greyed out. Each patch is listed with how saturated it actually is:

```
Would be used, in order (leftmost):
  1. 1000x290 at 100, 10   59913 pixels   middle 600, 155   saturation 120-250
```

Nothing is written to disk. The picture only exists in that window until you
close it, and there is a `Save picture...` button if you want to keep one to
compare against another attempt.

A range that wide is the tell: 120 is the background, 250 is the highlight.
Set `Min saturation` between them - 180 here - and look again. Now it reads:

```
  1. 360x290 at 500, 10   26468 pixels   middle 680, 155   saturation 250-250
```

One patch, the outline alone, centred on the card.

A size filter is the **last** thing to set, and set it against what a badly
covered target looks like, not a clean one. A card in the middle of a fan
shows only its top bar and two slivers of its sides - the rest is behind its
neighbours - so a minimum height picked from a fully visible card will throw
it away entirely. Get the join right first, so the pieces are one shape, then
measure.

Work in this order, because each step depends on the one before:

1. **Min saturation** until only the thing you want is tinted
2. **Ignore pieces smaller than** to clear the speckle left behind
3. **Join pieces up and down** to pull that thing's fragments together,
   leaving **side to side** at 0 unless something genuinely needs it
4. **Patch at least this wide / tall** to drop any streaks that survive
5. **Must run off the edge** to drop anything in the wrong part of the screen
6. **If several match** to choose between the real candidates

The first three come before the rest because joining a dirty mask glues the
mess together, and everything after joining is measured on whatever came out
of it. Once noise is inside a patch, no later setting can get it out again.

## Two targets that touch

Highlights next to each other can arrive as one patch. Two playable cards
side by side in a hand, their outlines touching, come back as a single wide
box - and the middle of that box is the gap between the two cards. No amount
of joining or unjoining fixes it, because at that point the two outlines are
genuinely one shape.

`Aim at` is the answer. Every step that clicks something it found can aim at
an edge or a corner instead of the middle, and the offset is applied from
there:

| Aim at | Then offset by | Lands on |
| --- | --- | --- |
| the middle of it | 0, 0 | the middle - wrong when two merged |
| its left edge | +90, 0 | the left one, merged or not |

On a real pair of merged card outlines 720px wide, the middle lands at 560 -
exactly the seam - while the left edge plus 90 lands at 290, well inside the
left card. It works the same whether the cards merged that frame or not,
which is what makes it reliable rather than lucky.

An edge follows the **shape**, not the box around it. That distinction is the
whole thing on a fan of cards: they lean different ways and sit at different
heights, so the box round a merged group belongs to no card at all - its top
edge comes from the highest card, its left edge from the lowest. Aiming at
"the left edge" measures where the shape actually crosses that edge, so it
lands on the card that is really there:

| | y |
| --- | --- |
| Middle of the box | 240 - the left card's top frame |
| Where the shape meets the left edge | 359 - the middle of that card |

Corners still use the box, because a corner of a shape is not a well defined
thing. Image matches are rectangles, so their box is the truth and there is
nothing to follow.

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

Switching off every step in a section leaves nothing to run and nothing to end
it, so Pixie says so before the run starts and moves past it during one rather
than going round it forever in silence.

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
