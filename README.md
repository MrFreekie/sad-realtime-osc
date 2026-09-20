# S.A.D. Realtime

By [freekieaudio.uk](https://freekieaudio.uk)

A small desktop app that reimplements the delay/gain/polarity math behind
Merlijn van Veen's Subwoofer Array Designer spreadsheet for four array
topologies, plus six of this app's own extensions (two Arc Hybrids, an
Ellipse shape, Progressive Arc, Focus Point, and Avoid Point), without the
polar/SPL prediction plots — just the three per-sub values, updated live
and streamed out over OSC.

**100% vibe coded — use at your own risk, check all calculations before
use.**

## Credits

The array math this app reimplements — End-Fire, Gradient/Cardioid,
Delayed Horizontal Array (Arc), Forward Aspect Ratio — comes from
**Merlijn van Veen**'s S.A.D. (Subwoofer Array Designer) calculator and
its manual: **[merlijnvanveen.nl](https://www.merlijnvanveen.nl/)**
(calculator page: [merlijnvanveen.nl/en/calculators](https://www.merlijnvanveen.nl/en/calculators)).
Every formula here that traces back to S.A.D. was checked against that
manual and, where possible, against its own worked tutorial numbers —
see the topology notes below for specifics.

S.A.D. itself credits **Mauricio "Magu" Ramirez** and **Bob "6o6"
McCarthy** as its inspiration. This app is an independent, from-scratch
reimplementation (no S.A.D. code or spreadsheet formulas were copied)
built for live OSC output rather than the original's polar/SPL
prediction plots — any errors in translation are this app's, not
Merlijn van Veen's.

The **Ellipse** shape (Physical Horizontal Array, Arc / Broadside
Steering, and both Arc Hybrids) and the front/rear-pair-bent-into-an-arc
idea behind the two **Arc Hybrid** topologies were inspired by
**Rafael Gomes Pereira**'s **SubArray Vizualizer** (BETA1.1d) — a
separate, third-party freeware calculator for the pro-audio community,
and others' modifications on it since (the copy consulted here was last
touched by contributor Costantino Pistidda). Only that tool's public
front-sheet interface (input labels, shape dropdown, chart layout) was
ever looked at — its own calculation engine is deliberately hidden and
password-protected by its author to protect his formulas, and none of
it was accessed, extracted, or reproduced here. Every formula behind
Ellipse in this app (`physical_ellipse_layout`, `_arc_column_delays_s`'s
`depth_scale`) was derived independently — see the topology notes below
for each one's own "no tutorial ground truth to verify against" caveat,
same honesty standard as the rest of this app's original extensions.

## Run

```
pip install -r requirements.txt
python sad_realtime_osc.py
```

## Topologies

- **End-Fire** — inline array facing the audience. Sub 1 is front-most.
  Delay increases towards the front so the array reinforces forward and
  cancels rearward.
- **Gradient / Cardioid Pairs** — front/rear pairs. Front: 0 ms, normal
  polarity. Rear: delayed, reversed polarity — the delay (and with it the
  null angle) is set by **Pattern** / **α**, not fixed to the plain
  cardioid case: `rear delay = transit time × α/(1−α)` (`transit time` =
  the pair's own spacing/speed of sound), the standard first-order
  differential-array pattern family `E(θ) = α + (1−α)·cos θ`
  (`gradient_pair_delay_ms` in `array_math.py`). **α = 0.5** (the
  **Cardioid** preset, and this control's default) reproduces the
  original fixed behaviour exactly — broadband null straight behind each
  pair. Other named presets: **Figure-8** (α = 0, null at 90°, no extra
  delay beyond the pair's own spacing), **Hypercardioid** (α = 0.25, null
  at ≈109.5°), **Supercardioid** (α = 0.37, null at ≈126.0°) — the
  standard values from the differential-microphone-array literature.
  Picking a preset fills α; editing α directly resets Pattern to
  "— custom —", same convention as Sub box dimensions' Profile field.
  α is capped below 1.0 — that's the unreachable omni limit, needing
  impractically large delay for a fixed small spacing. The broadband-null
  claim for every α is verified by direct far-field superposition (not
  just the small-kd approximation the α formula is usually derived
  from): the null angle `acos(α/(α−1))` this app's delay construction
  produces matches the literature's target-pattern null angle exactly,
  at every α tested.

  **No Subcardioid preset (α = 0.75).** Unlike the four presets above, it
  has no true null anywhere — just a shallow dip that in the idealized
  small-spacing limit sits about 6 dB down directly behind the pair. That
  figure only holds when the pair's spacing is small relative to the
  wavelength; at this app's own default spacing (1.4 m — itself the
  quarter-wavelength-optimum recommendation for a 60 Hz passband top) the
  real, verified behaviour is far worse: front and rear fully **invert**
  (rear running ~24 dB *louder* than front) right around 50–60 Hz, not
  some edge case far from normal use. The other four presets all degrade
  gracefully with frequency instead — never inverting — because each has
  a genuine structural null holding the pattern in shape at every
  frequency; Subcardioid's shallow, unanchored dip has nothing holding it
  in place as spacing grows relative to wavelength. Still reachable by
  typing α > 0.5 into Pattern α by hand if you understand that trade-off
  — this only removes the one-click preset, not the underlying math.

  A **Null angle (°)** control (90–180°) dials the same null directly by
  bearing instead of via α — pick where the pair's rejection sits (90° =
  Figure-8's side null, through 180° = Cardioid's rear null) and the app
  solves the α that puts it there (`alpha_from_null_angle_deg` /
  `gradient_null_angle_deg` in `array_math.py` — the exact same broadband
  construction, just re-parameterized, not a different or weaker one;
  verified by far-field superposition across the full range, not just
  the four named presets). Fully in sync with Pattern/α: picking a
  Pattern updates Null angle to match; editing Null angle solves for α
  and resets Pattern to custom, same as editing α directly does. No
  angle is reachable below 90° or above a Subcardioid-and-wider α — both
  have no true null to dial, so past α = 0.5 the field simply stops
  updating rather than showing a meaningless number. The null is a full
  **cone around the pair's own front-back axis** — symmetric both sides,
  not one compass bearing — so this dials how far round from the front
  the rejection sits, not left vs. right on its own; see **Gradient Arc
  Hybrid** below for combining it with Steer to bias a rejection zone
  toward one side. A genuinely more robust way to protect a
  noise-sensitive site than Avoid Point's single point-null: this holds
  up across the whole sub passband (broadband, not one design frequency)
  and isn't pinned to a wavelength-fragile exact XY coordinate.
- **Physical Horizontal Array** — S.A.D.'s Setup 1: n elements physically
  placed *and rotated* on a real arc of a given **Radius**, spanning the
  Arc angle. Every element is already equidistant from the arc's centre
  of curvature, so no electronic delay or level compensation is needed —
  Delay is 0 ms and Gain trim is flat for every element, confirmed by
  S.A.D.'s own tutorial (delay and level both exactly 0 throughout).
  Spacing doesn't apply here (it's hidden) — physical spacing between
  elements is a consequence of Radius/Arc/count, not an input. The real
  payload is physical placement: the table's **X (m)** (set-back/depth,
  ≤ 0) and **Rotation (°)** columns, alongside Y (lateral), tell you
  exactly where to place and aim each box (`physical_arc_layout` in
  `array_math.py`). Verified *exact* (not just close) against S.A.D.'s
  own tutorial — 10 elements, 70° arc: element 1 → depth -1.32 m,
  lateral 4.18 m, rotation 35.0°; element 5 → -0.02 m, 0.49 m, 3.9°,
  matching to the tutorial's displayed rounding throughout.

  A **Shape** selector (also on Arc / Broadside Steering and the two Arc
  Hybrids below — see their own entries) picks **Circle** (the above,
  default) or **Ellipse** — this app's own extension, not part of
  S.A.D., with no tutorial ground truth to verify it against. For
  Physical Horizontal Array specifically, Ellipse keeps lateral
  (`radius·sin φ`) and total coverage exactly as the circle would, and
  scales *only* depth by a new **Ellipse ratio**
  (`depth = ratio · radius·(1 − cos φ)`) — ratio = 1.0 reproduces the
  circle exactly; below 1 flattens the bow, above 1 exaggerates it.
  Rotation is fixed at **0°** for Ellipse (not computed) — a true
  ellipse's aim direction is the local tangent, not the parametric
  angle, and per-design this app treats subs as omnidirectional enough
  at these frequencies that it isn't worth tracking for this shape
  (`physical_ellipse_layout` in `array_math.py`). The Sub box dimensions
  collision check switches from the circle's constant-chord formula to
  measuring the actual minimum adjacent-element gap directly
  (`min_adjacent_chord`), since an ellipse's chord isn't constant along
  the array. See **Venue → arc (FAR)** below for how Ellipse links to
  venue Length/Width, including venues the plain circle can't solve.
- **Arc / Broadside Steering** — S.A.D.'s "delayed horizontal array": n
  elements physically in a straight line, delayed as if positioned on a
  physical arc spanning the Arc angle (0-180°). The delay pattern is
  **symmetric** — 0 ms at the centre element(s), increasing towards both
  edges — not a one-directional ramp. The angular step between adjacent
  elements is `angle/(n-1)`; the implicit arc radius comes from that step
  and Spacing via chord geometry, and each element's delay is the sagitta
  (bow depth) of its own position on that arc, divided by the speed of
  sound (`arc_steering` in `array_math.py`). Checked against S.A.D.'s own
  tutorial (10 elements, 0.94 m spacing, 71° arc → delay 3.77/2.27/1.14/
  0.38/0.00 ms edge to centre, mirrored) to within ~0.07 ms — consistent
  with the tutorial's displayed inputs themselves being rounded. Shows a
  live FAR (Forward Aspect Ratio) readout, `FAR = 1/sin(arc/2)` —
  verified against S.A.D.'s own manual (arc 60° → FAR 2.00, exact).
  **Steer (°)** (-90 to +90, default 0) redirects the whole arc's aim
  off-centre for venues that aren't symmetrical about the array's own
  centreline, without changing the coverage angle (FAR) — it superimposes
  the standard linear delay-steering ramp (`-x·sin(steer)/c`, `x` each
  element's straight-line position relative to centre) on top of the
  arc's own curvature, then re-zeroes the result so the earliest element
  is still 0 ms. Positive steers towards the highest-numbered sub; 0 is
  the default symmetric aim, straight ahead. Works even with Arc angle
  at 0° (pure delay-steering of an otherwise flat line).

  Also has the **Shape** selector: Circle (above) or **Ellipse**. Since
  this topology is physically a straight line either way (only the
  *virtual* curvature used for delay changes), Ellipse ratio scales just
  the sagitta term inside `_arc_column_delays_s` — the electronic
  equivalent of Physical Horizontal Array's `physical_ellipse_layout`,
  same ratio, same effect on the pattern, no placement or rotation to
  touch. Steer's own linear ramp is *not* scaled by Ellipse ratio — it's
  a separate, independent superposition either way (see Steer above).
  Ratio = 1.0 reproduces the plain circle exactly (verified bit-for-bit
  against the tutorial numbers above, same as Circle).
- **End-Fire Arc Hybrid** / **Gradient Arc Hybrid** — this app's own
  extension, not part of S.A.D. itself, so there's no tutorial ground
  truth to verify it against (unlike every topology above). Every
  **column** along the array is a front/rear pair — End-Fire (both
  normal polarity, rear = 0 ms reference, front = + row delay) or
  Gradient (front = 0 ms/normal, rear = + row delay/reversed, same
  **Pattern** / **α** / **Null angle** control as Gradient / Cardioid
  Pairs, including its own row transit time) — and the columns
  themselves are arc-steered exactly like **Arc / Broadside Steering**:
  the same symmetric, Steer-able delay pattern across columns, just
  applied underneath each column's own front/rear offset instead of
  directly to single elements. Because every column shares one Null
  angle *and* the whole array has its own independent **Steer**, the two
  combine into a genuinely useful noise-mitigation tool: Null angle sets
  how far round from the front each column's broadband rejection cone
  sits, Steer biases the array's own aim asymmetrically toward one side
  — together they can point a broad, whole-passband rejection zone
  roughly at a specific site off to one side, far more robustly than
  Avoid Point's single wavelength-fragile point-null (which only cancels
  at one exact XY coordinate and one design frequency's worth of
  precision in practice). Kept strictly **1:1** front:back per column — no
  independent front/back element-count ratio — since without a polar/SPL
  engine there's no way to verify one against, only textbook theory
  (`end_fire_arc_hybrid` / `gradient_arc_hybrid`, and the shared
  `_arc_column_delays_s` core factored out of `arc_steering`, in
  `array_math.py`). **Spacing** is column-to-column (lateral, same role
  as Arc's own Spacing); a separate **Row spacing** field (with its own
  slider, quantized the same 1 mm way) is the front-to-back depth within
  each column, and always shows its own **¼λ** readout next to it —
  Row spacing is rated against ¼ wavelength regardless of the ½λ rule
  used for the column Spacing above, since it's the same End-Fire/
  Gradient-style pair depth as those topologies' own Spacing. Verified only against internal
  consistency: at Row spacing → column delays exactly match plain
  `arc_steering`'s output plus a fixed per-row offset, and a single
  column (n=1) reduces exactly to a plain End-Fire/Gradient pair.
  Level taper, FAR, Steer, the Shape/Ellipse ratio selector (applied to
  the column-to-column curvature, same as Arc / Broadside Steering's
  electronic Ellipse, on top of each column's own front/rear offset),
  and the Venue solver's angle all work the same as Arc / Broadside
  Steering; Sub box dimensions checks **both** axes for these two
  (column spacing vs. box width, row spacing vs. box depth) since real
  boxes sit close on both. **Columns** replaces "Subs"
  as the count label (each column is 2 physical subs); max 24 columns
  (48 subs).
- **Progressive Arc** — same physical model as Physical Horizontal Array
  (real arc of a given **Radius**, spanning the Arc angle; every element
  still equidistant from the center of curvature, so Delay stays fixed
  at 0 and **Rotation** is still the true local aim angle, unlike
  Ellipse above) but with a non-uniform angular step between adjacent
  elements instead of a constant one — a "J-array"-style progressive
  spread. A **Progression** ratio (1.0–8.0, default 1.0) sets the
  center:edge angular-step ratio: 1.0 reproduces Physical Horizontal
  Array exactly (uniform steps, verified against its own tutorial data
  the same way); above 1.0 the center gap(s) widen (tighter curvature
  there) and the edge gaps narrow proportionally (flatter, longer throw
  down the flanks), while total coverage angle — and FAR — stays
  exactly what Arc (°) says (`progressive_arc_layout` in
  `array_math.py`). This app's own extension, not part of S.A.D. — no
  tutorial ground truth to verify the non-uniform case against, only
  the ratio = 1.0 boundary case above. The Sub box dimensions collision
  check uses the same minimum-adjacent-gap measurement as Ellipse,
  since the chord isn't constant here either.
- **Focus Point** ("Destruction Mode") — n elements in a straight line
  (same physical layout as Arc / Broadside Steering — evenly spaced,
  centered on **Spacing**), all delayed so their output arrives at one
  target point (**Focus X** — how far out in front of the line the
  target sits, **Focus Y** — its lateral offset from the line's own
  center, 0 = dead ahead) at the same instant, for maximum constructive
  buildup there. `delay_i = (max distance − distance_i) / c` — near-field
  acoustic focusing, standard beamforming and exact by construction from
  geometry alone (not an approximation, so nothing here needed
  verification against a tutorial the way the other topologies did).
  This app's own extension, not a S.A.D. topology; no Level taper (its
  point is precise phase alignment to the target, not amplitude
  shading — same as End-Fire/Gradient, Gain Trim is a flat manual value
  unless Group level is used).
- **Avoid Point** ("Protection Mode") — Focus Point's destructive twin:
  identical physical layout and the identical time-alignment delay law
  to one target point (**Avoid X** / **Avoid Y**, same convention as
  Focus X/Y), but **alternating polarity** (odd sub normal, even
  reversed) instead of Focus Point's all-normal — since every element
  now arrives at the target at the *same instant* but half are inverted,
  they cancel instead of add, for an **exact, frequency-independent
  null** at that point (`avoid_point` in `array_math.py`). This is the
  same delay-align-then-invert mechanism that already makes
  Gradient/Cardioid's rear null exact — not a new or different one, just
  applied to a point instead of a direction. For an odd sub count the
  extra unpaired sub's polarity group is automatically attenuated by
  `20·log₁₀(n_reversed/n_normal)` dB (shown as a small negative Gain
  Trim on that group only) so both groups' total level still balance
  exactly regardless of parity. Verified by reconstructing the far-field
  sum at several frequencies for both even and odd counts — every case
  lands at floating-point zero (~1e-15), not merely small. Like Focus
  Point: no Level taper (amplitude shading would unbalance the exact
  cancellation), Gain Trim stays a flat computed value, same physical
  layout/count rules. **Use case**: a specific noise-sensitive location
  (a monitored dB(A) point, a neighbouring property) rather than a broad
  rejection zone — for the latter, a steered cardioid/Arc topology aimed
  with Steer is the more robust real-world tool, since its rejection
  holds across the whole passband and isn't pinned to one exact
  coordinate.

  **Read this before trusting it on a real noise-sensitive show**: the
  null is exact in *arrival-time/phase* terms only — this app has no
  polar/SPL prediction at all, so real-world cancellation depth also
  depends on each element's actual level reaching the target, and
  near-field distance-spreading differences across a physically
  spread-out array aren't modelled here. A wavelength at typical sub
  frequencies is several metres, so the true null is roughly that
  fragile in position too — a small shift in the array, the target, or
  the speed of sound (temperature/humidity/wind) moves it. Treat Avoid X/Y
  as where the array's phase is exactly opposed, not a guaranteed
  real-world silent spot — confirm with measurement or a prediction tool
  before relying on it for a genuinely noise-sensitive application.
- **Manual** — place each sub freely by typing its own **X** (depth,
  front-to-back — larger/less-negative is closer to the audience, same
  sign convention as Physical Horizontal Array's X) and **Y** (lateral,
  informational only). Delay is *derived*, not typed: the rearmost
  placed sub (smallest X) is the 0 ms reference, generalising End-Fire's
  "rearmost = reference" plane-wave logic to arbitrary free 2D placement
  instead of a fixed line (`delays_from_depth` in `array_math.py`) — a
  straight line of subs entered this way reproduces End-Fire's numbers
  exactly. Gain trim and Polarity stay directly editable, same as
  before. This replaces the old version of Manual mode, which let you
  type delay/gain/polarity directly with no geometry behind it at all.
  Spacing doesn't apply here either (each sub is freely placed, not
  spaced along a line) and is hidden, same as Physical Horizontal Array.

Per-sub gain is a manual trim (default 0 dB) on top of the computed
delay/polarity — S.A.D. itself doesn't auto-shade levels for these
topologies either, that's a deliberate per-show choice. For the four
computed topologies the table's **Gain Trim (dB)** column is read-only:
set it via the Level taper panel (Arc / Broadside Steering, Physical
Horizontal Array, Progressive Arc, and the two Arc Hybrids only) or trim
the whole array at once with Group level. Only **Manual** mode lets you
type per-sub trim directly in the table.

Opens on **Arc / Broadside Steering** by default, with **6** subs and
**1.4 m** Spacing. The
window sizes itself to fit the current content on launch and again
whenever the topology changes — it's still freely resizable by hand
otherwise.

Max sub count depends on topology: **End-Fire** up to 12, **Gradient /
Cardioid Pairs** up to 6 pairs (12 subs), **Physical Horizontal Array**
(either Shape), **Arc / Broadside Steering**, **Progressive Arc**,
**Focus Point**, **Avoid Point**, and **Manual** up to 48, **End-Fire Arc Hybrid** and
**Gradient Arc Hybrid** up to 24 columns (48 subs) — those place
elements freely (or, for the two hybrids, freely by column) rather than
stacking them all front-to-back, so a much larger count is still a
realistic array (e.g. a long curved festival sub arc), unlike a 48-deep
End-Fire stack or 24-pair Gradient line. The per-sub table scrolls (mouse
wheel, or drag the scrollbar) rather than growing the window to fit every
row — it grows with the row count up to about a dozen visible rows, then
scrolls beyond that.

Two-column layout: the **left column** (Array, Level taper, Sub
bandwidth, Info, the per-sub table, then OSC output) holds the panels
you touch while working a show. The **right column** (Units, DSP clock,
Environment, Venue → arc, Sub box dimensions, Group, Pre-alignment,
Sub → tops alignment wizard) holds setup-once panels and stays a fixed
height regardless of sub count, so adding subs no longer makes the whole
window taller — only the table does (up to its own scroll cap, above).

Every panel's explanatory paragraph lives behind a small **?** icon next
to its controls instead of a permanent wrapped block of grey text —
hover it for a tooltip. Keeps the panels compact; nothing about how a
feature works changed, just where the explanation lives.

The per-sub table also shows **Y (m)**, matching S.A.D.'s output sheet
column of the same name (plus **X (m)** and **Rotation (°)**, which are
0 for every topology except Physical Horizontal Array and Manual — see
above/below). For End-Fire, Y is each sub's distance from Sub 1 along
the array (`(i-1) × spacing`). For **Arc / Broadside Steering** it's
**symmetric about the array's centre**, sub 1 at the most positive end
(`sub_positions_centered` in `array_math.py`) — matches S.A.D.'s own
tutorial exactly (n=10, spacing=0.94 m → +4.23, +3.29, +2.35, +1.41,
+0.47, -0.47, -1.41, -2.35, -3.29, -4.23), same reference point the
corrected delay pattern above uses. For Gradient pairs it's the
front/rear depth offset within a pair (0 m / spacing), repeated per pair
since pairs sit side by side at the same depth. For **Manual**, X and Y
are directly editable — see the Manual topology entry above.

## Units

A global **length unit** — m / cm / mm, default m — that every editable
length field in the app (Spacing, box Width/Depth/Gap, and the distance
fields in Group, Sub → tops alignment, and Venue → arc) is typed and
shown in. Everything is still stored and computed in metres internally,
so switching units mid-session just re-renders those fields' displayed
numbers — no math changes, nothing is lost or rounded away. Read-only
result text (Y column, collision/alignment/FAR labels) stays in metres
for now.

Every editable length field is quantized to the nearest **1 mm** the
moment you type a value or drag its slider — the smallest increment
that means anything physically for cabinet placement — shown as 3
decimal places in m, 1 in cm, or a whole number in mm, whichever unit
is active. This is the one case where a number does get rounded: dial
in "1.23456" m and it settles on 1.235 m, in every unit you view it in
afterwards.

## Environment

**Temperature (°C)**, **Relative humidity (%)**, and **Altitude (m)**
together set the speed of sound used everywhere: the per-topology delay
math, the ¼λ/½λ spacing readouts, group delay ↔ distance conversion,
and the Sub → tops alignment wizard. A live **c = ... m/s** readout sits
next to Temperature.

Speed of sound uses the [Cramer (1993)](https://pubs.aip.org/asa/jasa/article-abstract/93/5/2510/965010)
equation — accurate to ≤300 ppm within its validated range (0-30°C,
75-102 kPa) — instead of the old `331.3 + 0.606 × °C` linear
approximation, which ignored humidity and altitude entirely. Humidity
enters via water vapor mole fraction (Davis 1992 saturation-vapor-pressure
model); altitude converts to atmospheric pressure via the International
Standard Atmosphere model (elevation only — not today's actual weather).
CO2 concentration is fixed at a standard-atmosphere default (~400 ppm,
not exposed as an input) since its effect is negligible at any realistic
outdoor level. See `speed_of_sound` and its helpers in `array_math.py`.

## DSP clock

Its own box, default **96 kHz (2 FS)**: **48 kHz / 96 kHz / 192 kHz**
(1/2/4 FS) — the sample rate used to convert delay to samples
(`round(delay_ms / 1000 * sample_rate)`), since DSP delay lines are
often actually set in samples, not milliseconds.

A second control, **Show delay as** (ms / samples), switches what the
per-sub table's **Delay** and **Delay + Group** columns display —
one pair of columns showing either unit, rather than a separate column
for each, so the table doesn't carry both at once. This is a display
choice only: what actually goes out over OSC always carries `delay_ms`
and `delay_total_ms` in milliseconds regardless of this setting.

## Sub box dimensions

Checks whether adjacent sub boxes can physically fit at the current
Spacing. Pick a **Profile** (a named box that fills in Width/Depth
together) or set **Width** / **Depth** directly with the up/down-arrow
number boxes — editing either drops Profile back to "custom". Which
dimension is checked depends on the active topology:

- **Arc / Broadside Steering** / **Focus Point** / **Avoid Point** — boxes
  sit side by side, so **width** is checked against **Spacing** directly.
- **Physical Horizontal Array (Circle)** — **width**, checked against
  the derived constant chord distance between physically adjacent
  elements (`physical_arc_chord_spacing` in `array_math.py`), since
  there's no Spacing field (spacing is a consequence of Radius/Arc/
  count).
- **Physical Horizontal Array (Ellipse)** / **Progressive Arc** —
  **width**, but against the *minimum* adjacent-element gap measured
  directly from the actual placed layout (`min_adjacent_chord`), since
  neither shape has a constant chord along the array the way the plain
  circle does.
- **End-Fire** / **Gradient / Cardioid Pairs** — boxes stack front to
  back, so **depth** is checked instead.
- **End-Fire Arc Hybrid** / **Gradient Arc Hybrid** — both axes at once,
  independently: **width** against **Spacing** (column-to-column, boxes
  side by side) and **depth** against **Row spacing** (front/rear pair,
  boxes front to back). Shown as two clearances side by side instead of
  one, since either axis can collide independently of the other.
- **Manual** — no single spacing applies; shows "n/a", and the two
  buttons below are no-ops (also no-ops for Physical Horizontal Array
  and Progressive Arc, neither of which has a Spacing field to set).

Reports either `OK — X.XX m clearance` or `⚠ ... > ...`
when the box is larger than the spacing (`spacing_clearance_m` in
`array_math.py` — negative means overlap). This is a straight-line
physical check only, not a full 3D footprint/rigging model.

Two buttons apply the relevant dimension straight to Spacing (for the
two Arc Hybrids, this only ever sets Spacing — the column axis — never
Row spacing, which stays a manual field; no-ops for Physical Horizontal
Array/Progressive Arc, same reasoning as above):

- **Set min spacing** — Spacing = box dimension exactly (boxes
  touching, zero gap).
- **Gap between cabinets** + **Set spacing (+ gap)** — Spacing = box
  dimension + a gap you set, for cable runs, rigging hardware, or just
  breathing room between cabinets.

### Sub profiles (`sub_profiles.csv`)

Named box dimensions live in `sub_profiles.csv`, next to the app —
columns `name,width_m,depth_m`. Add a row to add a profile; no code
changes needed. If the file is missing, empty, or a row fails to parse,
`sub_profiles.py` falls back to a small built-in default list (currently
just the two KS28 orientations) so the app still runs standalone.

Ships with:

```
name,width_m,depth_m
L-Acoustics KS28 (Horizontal),1.340,0.702
L-Acoustics KS28 (Vertical),0.565,0.702
L-Acoustics KS28 (2x Vertical),1.13,0.702
L-Acoustics KS28 (3x Vertical),1.695,0.702
L-Acoustics KS28 (4x Vertical),2.26,0.702
```

### Acoustic centre offset

Off by default. Merlijn van Veen's low-frequency acoustic centre
research holds that a sealed/vented sub's true radiating point can sit
outside the enclosure, in front of it, below ~100 Hz — not settled
physics (he says so himself), but a documented, plausible correction.
When enabled, the offset (default 0.30 m / "+30cm") is subtracted from
**Sub dist. to FOH** in the Sub → tops alignment wizard below, before
that calculation runs — enter the distance to the cabinet the way you'd
actually measure it, the app applies the correction. It does **not**
touch inter-sub delay/spacing math anywhere else: a uniform forward
shift of every sub in an array changes none of the path-length
*differences* between them, only distance to an external reference like
FOH.

The checkbox and offset field live here, in Sub box dimensions, but
their effect shows up in the Sub → tops alignment wizard panel below —
when enabled, a **"→ acoustic centre corrected: X.XX m"** line appears
right next to **Sub dist. to FOH**, so you can see the corrected value
being used without having to infer it from the final result changing.

## Group (applied to all subs)

- **Group delay (ms)** — a single offset added to every sub's delay, e.g.
  to align the whole sub array's arrival time to the mains. The per-sub
  table's **Delay (ms)** column stays the raw topology-computed value;
  a new **Delay + Group (ms)** column shows the total. Works in Manual
  mode too, on top of whatever delay you typed per sub.
- **Distance (m)** — the same group delay, entered (or read) as a
  physical distance instead of milliseconds — e.g. "the subs sit 15 m
  closer to FOH than the mains." The two fields stay in sync via the
  speed of sound at the current Temperature (Environment panel), both
  ways: edit either one and the other updates, and changing Temperature
  re-solves the distance for the delay you already have.
- **Group polarity** (Normal / Inverted) — flips every sub's polarity at
  once, on top of whatever the topology (or, in Manual mode, you)
  already set. The per-sub table's **Polarity** column shows the final
  effective value. In Manual mode the per-sub Reversed checkboxes stay
  showing your raw entry (so toggling the group switch doesn't silently
  rewrite what you typed); the group flip is still applied at send time.
- **Group level (dB)** — a single gain offset added to every sub's Gain
  trim, e.g. trimming the whole sub array relative to the mains without
  touching each sub's individual trim. The per-sub table's **Gain Trim
  (dB)** column stays the raw per-sub value; a new **Gain + Group (dB)**
  column shows the total, and that total (not the raw trim) is what the
  OSC `gain` decimal reflects — it's the actual value meant for
  hardware, same reasoning as Delay + Group.

These only affect the **+ Group** columns, the **Polarity** column (for
the three computed topologies), and what actually goes out over OSC
(`delay_total_ms`, `gain_total_db`, `gain`, and `polarity` below) — they
never change the underlying per-sub
`delay_ms` / `gain_db` topology math.

## Pre-alignment delay lookup

Looks up L-Acoustics' own factory pre-alignment delay offsets — from the
Drive System Preset Guide's **"Pre-alignment delay values"** section
(p.93) — for a **Main system** + **Sub preset** combination, and lets
you apply the sub-side value to Group delay with one click instead of
re-typing it.

Pick a Main system and Sub preset; the panel shows both sides of that
combo's factory offset, e.g. **Main: K1 = 6.00 ms [Positive (+)]** and
**Sub: KS28_60_C = 0.00 ms [Negative (−), Cardioid (internal reversal)]**.
**"Use → Group delay"** *adds* the Sub-side value on top of whatever is
already in Group delay above — tracked separately, not just merged in
silently: an orange note appears next to **Group delay (ms)** in the
Group panel reading `includes +X.XX ms pre-alignment (Main + Sub)`, so
it stays obvious this contribution is layered on top of anything you
dialled in by hand. **"Clear"** removes exactly that contribution,
leaving the rest of Group delay untouched. Switching to a different
combo and clicking Use again replaces the previous contribution rather
than stacking on top of it.

Often the Sub-side value is **0 ms** — most of these combos put the
correction on the Main system's own delay instead, not the subs. "Use"
still confirms this rather than looking like a no-op: the note explains
how much delay remains and that it belongs on the main system's own
processor, which this app doesn't control (this app only outputs
subwoofer OSC messages).

Two separate coloured indicators, one per system:

- **Polarity tag** — green **Positive (+)** / red **Negative (−)**,
  straight from the guide's `main_polarity`/`sub_polarity` columns
  (audio-standard wording — write `positive`/`negative` in the CSV, or
  the older `normal`/`reversed`/`+`/`-` spellings, all accepted as
  synonyms). This is the obvious pass/fail signal. "Use" only ever
  writes delay — if a Sub-side combo is Negative, the Group-delay note
  also grows a **⚠ Sub polarity NEGATIVE** warning telling you to flip
  **Group polarity** to Inverted yourself, since this app doesn't do it
  for you. An unrecognized polarity value isn't silently defaulted —
  this is a live-audio-relevant field, so a typo shows up as a red error
  message in place of the panel's controls instead of quietly passing
  as Positive.
- **Config detail** (in brackets after the polarity tag, only shown
  when not "Standard") — Cardioid / Extended cardioid / Noise Control
  cardioid, meaning one enclosure *within* that preset's own cluster is
  reversed internally (how L-Acoustics gets the null pattern). This is
  independent of the polarity tag above and always informational — this
  app's single Group polarity switch can't represent "reverse just one
  element inside the sub cluster".

### Pre-alignment data (`prealign_delays.csv`)

Combos live in `prealign_delays.csv`, next to the app — columns
`main_system,sub_system,main_delay_ms,sub_delay_ms,main_polarity,
sub_polarity,main_config,sub_config,notes` (`*_polarity` is
`positive`/`negative`, aliases `normal`/`reversed`/`+`/`-` also
accepted; `*_config` is `standard`/`cardioid`/`extended_cardioid`/
`noise_control_cardioid`). Add a row to add a
combo; no code changes needed. If the file is missing, empty, or a row
fails to parse, `prealign_profiles.py` falls back to a small built-in
default.

**Note on the seeded data:** `sub_polarity` is `negative` for the seven
non-`K1SB_X`/`K1SB_60` rows — that's a deliberate override, not what the
guide's factory preset tables show (they read `+`/positive at the
whole-preset level for all of these; each row's `notes` column says so).
Each of those rows shows red **Negative (−)** and triggers the ⚠ warning
described above accordingly.

**Currently only the K1 family is seeded** (`K1` + `K1SB_X` / `K1SB_60`
/ `K1SB_100_NC` / `SB28_60` / `SB28_60_C` / `SB28_60_Cx` / `KS28_60` /
`KS28_60_C` / `KS28_60_Cx`), hand-verified against the guide. The
"Pre-alignment delay values" section covers many more system families
(K2, K3, Kudo, Kara, Kara II, Kiva, X series, A15, Syva, Soka...), but
that section's multi-column table layout didn't survive automated PDF
text extraction reliably enough to trust unverified — extend the CSV
with more rows as you confirm them directly from the guide.

## Sub → tops alignment wizard

Back-solves the group delay needed to time-align the sub array to the
mains, instead of doing the arithmetic by hand. Enter the mains'
distance to FOH, the mains' own already-applied delay (0 if none), and
the sub array's distance to FOH (measured from its front row, per the
Y column above); it computes

```
required group delay = mains delay + (mains distance − sub distance) / speed of sound
```

live, and "Set group delay" applies it to the Group panel above (which
then also updates the linked Distance field, since it's the same
variable). A negative result means the subs are already farther from
FOH than the mains — there's no positive sub delay that fixes that, the
mains need delaying instead — so "Set group delay" clamps to 0 in that
case rather than applying a negative number.

## Level taper (Arc / Physical / Progressive / Arc Hybrids only)

Only shown when **Arc / Broadside Steering**, **Physical Horizontal
Array**, **Progressive Arc**, **End-Fire Arc Hybrid**, or **Gradient Arc
Hybrid** is active —
the topologies that are genuinely spatial line arrays, so the only
places sidelobe-control windowing applies (**Focus Point** and **Avoid
Point** are also spatial, but their point is precise phase alignment to
a target, not amplitude shading — Avoid Point's exact cancellation
specifically *depends* on not being disturbed by an independent taper —
so both are deliberately excluded, same as End-Fire/Gradient). Pick a
**Window** — 9
options: Uniform, Hann, Hamming, Blackman, Bartlett (triangular), Welch,
Blackman-Harris, Nuttall, Flat Top, **Chebyshev**, **Taylor** — and,
for the first 9, a **Max atten (dB)** (default 0 dB, i.e. no taper until
you raise it). Every sub's Gain trim then live-follows the taper as you
adjust Window, Max atten, Subs/Columns, Spacing, Arc angle, or Steer —
0 dB at the window's peak, fading to `-max atten` at its minimum, shaped
by the window (`level_taper_db` / `window_weights` in `array_math.py`).
There's no "Apply" step; it's always in sync, the same way Delay already
is for these topologies. Uniform (or 0 dB) leaves every trim flat.

**Chebyshev** and **Taylor** replace Max atten with a **Sidelobe (dB)**
field (default 30 dB, range 10–100) instead: these two are the standard
antenna/phased-array tapers Dolph (Chebyshev, 1946) and Taylor (1955)
designed specifically to *give the array a real, chosen sidelobe level*,
not just shade the edges by an arbitrary amount, so their gain trim is a
literal `20·log10(w/peak)` of the window's own amplitude weights
(`_chebyshev_weights` / `_taylor_weights` in `array_math.py`, pure-Python
ports of SciPy's `chebwin`/`taylor`, verified by reconstructing the array
factor and confirming equal-ripple sidelobes land at exactly the
requested dB) rather than the linear Max-atten remap the other 9 windows
use. Chebyshev gives the narrowest possible main lobe for that sidelobe
level, holding every sidelobe at exactly the same level out to ±90°;
Taylor approximates that near the main lobe (over a fixed 4 near-in
sidelobes) but tapers off further out, the SAR/radar-community's usual
compromise pick. Both **follow Steer the same as the other 9 windows**
— see below — even though they have no continuous formula of their own
to re-sample off-centre: `steered_window_weights` instead linearly
interpolates the plain centred n-point array (`_interp_shape`) and
re-centres that, the same asymmetric-stretch trick used for every other
window here. Off-centre this trades away the exact equal-ripple
guarantee (re-sampling a Chebyshev-optimal array away from its own
centre isn't optimal any more either) — the same honesty trade-off
`arc_steered_aim_index` already makes for the other 9 windows' own
steering, not a new one.

For the two Arc Hybrids, the window is computed across **columns**, not
individual subs — both the front and rear sub in a column get that
column's trim, since the taper is shaping the horizontal (arc) pattern,
not the front/rear pair inside it.

For **Arc / Broadside Steering** and the two Arc Hybrids, the taper's
peak follows the **Steer** angle instead of always sitting at the
array's physical centre (`arc_steered_aim_index` in `array_math.py`) —
steering the arc off-axis shifts the least-attenuated element(s) toward
the steered side and the deepest attenuation toward the far edge, the
same direction the delay pattern's own zero point moves. At Steer = 0°
it's exactly the old symmetric window. **Physical Horizontal Array** and
**Progressive Arc** have no Steer control, so the taper always stays
centred for both regardless of Window.

Flat Top is a known exception to "monotonic taper" — it's an
amplitude-accuracy window with a small ripple near the edges by design
(can dip slightly past `-max atten` there), which is correct behaviour
for that window, not a bug.

A live **taper cost** readout — `taper cost: X.XX dB on-axis, Y.YY dB
total power (vs. uniform)` — shows the real-world price of whatever
taper is currently active, for every window, not just Chebyshev/Taylor.
Sidelobe control in a prediction plot doesn't show up as a line-item
cost, but it isn't free: **on-axis loss** is the forward SPL given up
because a correctly steered array sums its elements *in phase*, so
on-axis pressure follows the mean of the *linear* gains
(`taper_onaxis_loss_db` in `array_math.py`) — every dB of edge
attenuation dialled in for sidelobe control is a dB not coming back as
forward level, from a box still costing an amplifier channel and
rigging weight. **Total power** is the same idea for the incoherent
power sum instead (`taper_power_loss_db`) — closer to overall
amplifier/driver headroom spent than to what the room hears, and always
the smaller (less negative) of the two, since on-axis coherent summation
is hurt by tapering more than raw radiated power is. A deep sidelobe
target on a small array can cost several dB of forward level for a
pattern benefit this app has no way to show (no polar/SPL prediction)
— worth cross-checking a heavy taper against a prediction tool before
committing a show to it.

The Gain Trim column is read-only for these topologies — the taper
(plus Group level for a uniform offset) is the only way to shape it.
**This app has no polar/SPL prediction**, so you won't see the sidelobe
reduction a taper is supposed to buy you — this applies textbook array
theory on faith, not a result verified in-app. The Steer-following
behaviour is an original extension with no S.A.D./spreadsheet ground
truth to check it against either — it's a reasonable, bounded
approximation, not a derived or verified result. If that turns out to
matter, the next step would be a minimal polar preview rather than
trusting the taper blind.

## Venue → arc (FAR)

Only shown for the angle-based topologies — **Arc / Broadside
Steering**, **Physical Horizontal Array**, **Progressive Arc**, or
either **Arc Hybrid** — since those are the only ones with an Arc angle
for FAR to describe; switch topologies via the Array panel first if you
want to use it. "Set arc" applies the solved angle to the **current**
topology's Angle whenever it's already one of those five — it does
**not** switch you away from whichever one you were already on (Radius,
Row spacing, Progression, etc. are all separate fields it leaves alone).
It only switches topology (to Arc / Broadside Steering, same as before)
when starting from something with no Angle at all: End-Fire, Gradient,
Focus Point, Avoid Point, or Manual.

Enter venue length (throw/depth, front-to-back) and width (coverage,
side-to-side); the panel computes `FAR = length / width` and the arc
angle that FAR implies (`arc = 2·asin(1/FAR)`), then "Set arc" applies
it as above. Matches S.A.D.'s own tutorial example exactly: a 50 m deep
× 25 m wide venue → FAR 2.00 → arc 60°.

A venue wider than it is deep gives **FAR < 1**, which the plain circle
formula has no solution for at all (shown as "arc: n/a") — no single
circular arc covers that shape. **Shape = Ellipse is the exception**
(on any of its four topologies: Physical Horizontal Array, Arc /
Broadside Steering, or either Arc Hybrid): for FAR < 1, "Set arc" pins
Angle at this app's 180° maximum instead of "n/a" (`angle_from_far_
ellipse` in `array_math.py`), continuous with the circle's own FAR = 1
answer, which is also exactly 180°.

A second row, shown only for a Shape = Ellipse topology, handles
**Ellipse ratio** as its own separate action: "ellipse ratio: X.XXX"
(`ellipse_ratio_from_far` — 1.0 at FAR ≥ 1, shrinking below 1 as the
venue gets wider than it is deep, continuous with the Angle pin above
at FAR = 1) with its own **"Use"** button. It's deliberately independent
of "Set arc" — one touches Angle, the other Ellipse ratio, so you can
apply either without the other (e.g. dial in Angle by hand for a
specific stage constraint, but still want the venue-implied ratio, or
vice versa). This is the actual payoff of adding Ellipse: it solves
venue shapes the circle can't, not just a cosmetic depth-scale slider.

## Sub bandwidth → optimum spacing

Default **60 Hz**. Enter the top of your sub's passband; the panel computes the spacing at
which that frequency sits at ¼ wavelength (End-Fire/Gradient) or ½
wavelength (Arc, the two Arc Hybrids' column Spacing, Focus Point, and
Avoid Point) — S.A.D.'s own spacing rule of thumb, based on the
highest frequency since that's where comb filtering from spacing bites
first. "Use" applies it to the Spacing slider. Physical Horizontal Array
and Progressive Arc have no Spacing field, so this shows "n/a" for both,
same as before.

For the two Arc Hybrids, a second row — **optimum row spacing (¼λ)** —
computes the same rule for **Row spacing** instead, always at ¼
wavelength (the End-Fire/Gradient rule, since Row spacing is that same
front/rear pair depth) off the same High (Hz) field above, regardless of
the ½λ rule the column Spacing row above uses for these two topologies.
Its own "Use" applies it to Row spacing. Only shown when an Arc Hybrid
topology is active.

A third row, shown only for **Arc / Broadside Steering** and the two Arc
Hybrids (the topologies with a **Steer** control), reports a
**steer-aware grating-lobe spacing limit** alongside the ½λ rule of
thumb above: `d < λ / (1 + |sin(Steer)|)`, the phased-array-antenna
criterion for keeping a spurious lobe out of visible space
(`grating_lobe_max_spacing_m` in `array_math.py`), evaluated at the same
High (Hz) field and the array's current Steer angle. Unlike the ½λ rule
— a comb-filtering guideline that's the same number regardless of Steer
— this one tightens as Steer moves off-centre: a full wavelength at
Steer = 0° (looser than ½λ), narrowing smoothly to exactly ½λ at the
±90° extreme, matching RF phased-array theory's own broadside/end-fire
bounds. Reports `OK — grating-lobe limit X.XX m at Steer Y° (Z.ZZ m
headroom)` or `⚠ grating-lobe risk: ... > ... limit ...`, same
OK/⚠ phrasing as the Sub box dimensions collision check. Deliberately
scoped to Steer alone — it doesn't account for the additional local
curvature a wide Arc angle itself adds (a curved array's own edge
elements see a steeper local delay gradient than the centre does),
which would need a per-element rather than one-number check; this is
the one input (Steer) the existing ½λ/¼λ rule ignored entirely, not a
full grating-lobe model.

## Info

Mirrors the straightforward part of S.A.D.'s own "Info" panel: array
length (`(n-1) × spacing`, or pair depth for Gradient), array 1λ (the
frequency whose wavelength equals the array length — directivity onset),
and spk dist 180°/240°/360° (the frequencies at which the element spacing
represents that many degrees of phase — 360° is S.A.D.'s lateral
summation limit, ⅔ of it, 240°, is its usable-bandwidth limit). S.A.D.'s
panel also shows -6 dB ONAX and max angle, which need full polar/SPL
summation modelling; left out here on purpose, same as the prediction
plots.

## OSC output

Generic stub addresses, one message per value per sub:

```
<prefix>/<sub index>/delay_ms       float, raw topology delay (reference/debug)
<prefix>/<sub index>/delay_total_ms float, delay_ms + group delay
<prefix>/<sub index>/gain_db        float, raw dB (reference/debug)
<prefix>/<sub index>/gain_total_db  float, gain_db + group level (reference/debug)
<prefix>/<sub index>/gain           float 0.0-1.0, normalised fader value, from gain_total_db
<prefix>/<sub index>/polarity       int (0 = normal, 1 = reversed), after group polarity
```

Default prefix is `/sad/sub`, host `127.0.0.1`, port `5000` — all
editable in the OSC panel. Check "Live send" to fire messages on every
slider move / edit, or use "Send Now" for a one-shot.

**Only values that actually changed are sent.** Each address's last-sent
value is cached; a slider move that doesn't change a given sub's delay
(e.g. dragging Spacing while Arc angle is 0°, where delay is 0
regardless of spacing) sends nothing for it. "Send Now" and
"Apply / Reconnect" both force a full resend of every value, so a fresh
target always gets the complete current state rather than only future
deltas.

`gain` is `gain_db` run through a logarithmic taper calibrated to three
points: 1.0 = +18 dB (top), ~0.778 = 0 dB (unity), 0.0 = -144 dB (bottom)
— `dB = 165·log10(x) + 18`, i.e. `x = 10^((dB-18)/165)`, floored to
exactly 0.0 at or below -144 dB rather than following the curve towards
true -inf. -144 is rounded from a hardware measurement, not assumed:
dialling in an extreme low value (tested at -638 dB) read back as -143.9
dB, not -inf — close to the ~144.5 dB noise floor of 24-bit audio, and
almost certainly the box's own finite stand-in for -inf. (A 0 dB entry
reading back ~-0.1 dB is normal step-resolution quantisation and doesn't affect
the curve.) See `gain_db_to_osc` / `osc_to_gain_db` in `array_math.py`.

**This is not any specific device's OSC namespace.** These are generic
stub addresses — remap them here to match the actual parameter paths
your target device expects, per its own remote-protocol documentation,
or use this as the source feeding a lookup/translation layer in front
of the box.

## Project (save / load)

**New**, **Save**, **Save As...**, **Load...**, plus a free-text
**Name / notes** field (e.g. venue + date), in the Project panel at the
top of the left column.

**New** resets every setting on screen to factory defaults — same
confirmation-then-full-reset shape as Load, just with built-in defaults
instead of a file (`project_io.default_project_dict()`, pushed through the
same `apply_project_dict` used by Load, so there's one reset code path).
Asks to confirm first, since anything unsaved is discarded. Turns off Live
send and clears the current file path/name, same as opening a blank
project would.

**Save** / **Save As...** save every setting on screen — array/topology, level taper,
units, DSP clock, environment, group (including pre-alignment tracking),
sub box dimensions, venue, bandwidth, the sub → tops alignment wizard, OSC
target, and per-sub Manual placement — to a **`.sadrt`** file (plain JSON,
see `project_io.py`).

Everything is stored in canonical SI units (m/ms/dB/Hz/°C) regardless of
the currently displayed length unit — loading a file re-renders the
display in whatever unit is currently selected, same as changing the Units
dropdown does. Enum-like fields (topology, DSP clock, group polarity) are
stored as stable internal keys rather than the combobox's display text, so
relabeling a dropdown in a future version can't silently break older save
files.

**"Live send" is never restored from a loaded file**, even if it was
checked when saved — it's always off after Load, and has to be re-enabled
by hand. A saved project can come from a different venue/network than the
one currently patched in, so auto-streaming OSC to a stale host the moment
a file opens would be a real footgun mid-show; re-checking the box after
verifying Host/Port in the OSC panel is the deliberate extra step.

Loading is tolerant rather than strict: a field missing from an older save
file just keeps today's default; an out-of-range number (e.g. a
hand-edited file) is clamped to the nearest valid value; an unrecognized
topology, taper window, unit, or DSP sample rate falls back to whatever is
currently selected instead of crashing. Anything that needed fixing up
this way is reported in a single warning dialog after the load completes
— the file still loads, you just get told what didn't match cleanly. A
file that can't be parsed as JSON at all, or a newer/corrupt file that
fails while being applied, leaves the app's current on-screen state
untouched rather than half-overwriting it.

A `schema_version` field in the file lets a future format change apply
migrations rather than break old saves; opening a file saved by a newer
app version than the one running shows a warning that some settings may
not have loaded.

## Files

- `array_math.py` — pure functions, no UI/OSC dependencies. Safe to unit
  test or reuse elsewhere.
- `sad_realtime_osc.py` — Tkinter UI + OSC client.
- `sub_profiles.py` / `sub_profiles.csv` — named sub box dimension
  profiles for the collision check, editable without touching code.
- `prealign_profiles.py` / `prealign_delays.csv` — L-Acoustics factory
  pre-alignment delay values for the Pre-alignment delay lookup panel,
  editable without touching code.
- `project_io.py` — save/load `.sadrt` project files (see Project section
  above). No UI dependency of its own beyond reading/writing the App's
  Tkinter variables.
