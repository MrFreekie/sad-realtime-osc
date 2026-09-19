# S.A.D. Realtime

A small desktop app that reimplements the delay/gain/polarity math behind
Merlijn van Veen's Subwoofer Array Designer spreadsheet for four array
topologies, without the polar/SPL prediction plots — just the three
per-sub values, updated live and streamed out over OSC.

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
  polarity. Rear: delayed by the pair spacing, reversed polarity. Gives a
  broadband null directly behind each pair.
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
set it via the Level taper panel (Arc / Broadside Steering and Physical
Horizontal Array only) or trim the whole array at once with Group
level. Only **Manual** mode lets you type per-sub trim directly in the
table.

Opens on **Arc / Broadside Steering** by default, with **6** subs and
**1.4 m** Spacing. The
window sizes itself to fit the current content on launch and again
whenever the topology changes — it's still freely resizable by hand
otherwise.

Max sub count depends on topology: **End-Fire** up to 12, **Gradient /
Cardioid Pairs** up to 6 pairs (12 subs), **Physical Horizontal Array**,
**Arc / Broadside Steering** and **Manual** up to 48 — those three place
elements freely rather than stacking them front-to-back, so a much
larger count is still a realistic array (e.g. a long curved festival sub
arc), unlike a 48-deep End-Fire stack or 24-pair Gradient line. The
per-sub table scrolls (mouse wheel, or drag the scrollbar) rather than
growing the window to fit every row — it grows with the row count up to
about a dozen visible rows, then scrolls beyond that.

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

- **Arc / Broadside Steering** / **Physical Horizontal Array** — boxes
  sit side by side, so **width** is checked. For Physical Horizontal
  Array there's no Spacing field to compare against (spacing is a
  consequence of Radius/Arc/count), so this checks the derived chord
  distance between physically adjacent elements instead
  (`physical_arc_chord_spacing` in `array_math.py`).
- **End-Fire** / **Gradient / Cardioid Pairs** — boxes stack front to
  back, so **depth** is checked instead.
- **Manual** — no single spacing applies; shows "n/a", and the two
  buttons below are no-ops (also no-ops for Physical Horizontal Array,
  which has no Spacing field to set).

Reports either `OK — X.XX m clearance` or `⚠ collision: ... > ...`
when the box is larger than the spacing (`spacing_clearance_m` in
`array_math.py` — negative means overlap). This is a straight-line
physical check only, not a full 3D footprint/rigging model.

Two buttons apply the relevant dimension straight to Spacing:

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

## Level taper (Arc / Physical Array only)

Only shown when **Arc / Broadside Steering** or **Physical Horizontal
Array** is active — the two topologies that are genuinely spatial line
arrays, so the only places sidelobe-control windowing applies. Pick a
**Window** — 9 options: Uniform, Hann, Hamming, Blackman, Bartlett
(triangular), Welch, Blackman-Harris, Nuttall, Flat Top — and a **Max
atten (dB)** (default 0 dB, i.e. no taper until you raise it). Every
sub's Gain trim then live-follows the taper as you adjust Window, Max
atten, Subs, Spacing, Arc angle, or Steer — 0 dB at the window's peak,
fading to `-max atten` at its minimum, shaped by the window
(`level_taper_db` / `window_weights` in `array_math.py`). There's no
"Apply" step; it's always in sync, the same way Delay already is for
these topologies. Uniform (or 0 dB) leaves every trim flat.

For **Arc / Broadside Steering**, the taper's peak follows the **Steer**
angle instead of always sitting at the array's physical centre
(`arc_steered_aim_index` in `array_math.py`) — steering the arc off-axis
shifts the least-attenuated element(s) toward the steered side and the
deepest attenuation toward the far edge, the same direction the delay
pattern's own zero point moves. At Steer = 0° it's exactly the old
symmetric window. For **Physical Horizontal Array**, which has no
Steer control, the taper always stays centred.

Flat Top is a known exception to "monotonic taper" — it's an
amplitude-accuracy window with a small ripple near the edges by design
(can dip slightly past `-max atten` there), which is correct behaviour
for that window, not a bug.

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

Only shown when **Arc / Broadside Steering** or **Physical Horizontal
Array** is active, since those are the only topologies with an Arc
angle for FAR to describe — switch topologies via the Array panel first
if you want to use it. "Set arc" always switches to Arc / Broadside
Steering specifically (Physical Horizontal Array also needs a Radius,
which the venue solver doesn't determine).

Enter venue length (throw/depth, front-to-back) and width (coverage,
side-to-side); the panel computes `FAR = length / width` and the arc
angle that FAR implies (`arc = 2·asin(1/FAR)`), then "Set arc" switches
to Arc / Broadside Steering and applies it. Matches S.A.D.'s own tutorial
example exactly: a 50 m deep × 25 m wide venue → FAR 2.00 → arc 60°. A
venue wider than it is deep gives FAR < 1, which has no solution (shown
as "n/a") — no single arc covers that shape.

## Sub bandwidth → optimum spacing

Default **60 Hz**. Enter the top of your sub's passband; the panel computes the spacing at
which that frequency sits at ¼ wavelength (End-Fire/Gradient) or ½
wavelength (Arc) — S.A.D.'s own spacing rule of thumb, based on the
highest frequency since that's where comb filtering from spacing bites
first. "Use" applies it to the Spacing slider.

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

**This is not DirectOut's OSC namespace.** globcon's documented OSC
support is for triggering snapshots/faders/mutes, not confirmed for deep
per-channel delay/gain/polarity writes. Point this at an OSC monitor
(e.g. Protokol) first to see the live stream, then remap the addresses
here once you've confirmed the actual parameter paths Prodigy/ACE expect
(via DirectOut's remote-protocol docs or the globcon OSC implementation
chart) — or use this as the source feeding a lookup/translation layer in
front of the box.

## Files

- `array_math.py` — pure functions, no UI/OSC dependencies. Safe to unit
  test or reuse elsewhere.
- `sad_realtime_osc.py` — Tkinter UI + OSC client.
- `sub_profiles.py` / `sub_profiles.csv` — named sub box dimension
  profiles for the collision check, editable without touching code.
- `prealign_profiles.py` / `prealign_delays.csv` — L-Acoustics factory
  pre-alignment delay values for the Pre-alignment delay lookup panel,
  editable without touching code.
