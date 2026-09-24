# Matching a glow or a highlight

How to make a color step find the thing you mean and nothing else. Start here
when a step finds the wrong thing, finds nothing, or clicks somewhere strange.

In a hurry? [The order to tune in](#the-order-to-tune-in) is the short version.

## Getting the color right

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

