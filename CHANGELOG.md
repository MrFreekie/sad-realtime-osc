# Changelog

All notable changes to S.A.D. Realtime are logged here. Bump `__version__` in
[sad_realtime_osc.py](sad_realtime_osc.py) alongside each entry.

## [0.9.2] - 2026-09-21
Changed: renamed the **Live** tab to **Design**, and split the three-tab
layout (Live / OSC / Setup) into four: **Design** (Array, Topology
options, Level taper, Sub bandwidth, Info, the per-sub table), **Setup**
(Units, DSP clock, Environment, Venue → arc, Sub box dimensions --
venue/system parameters), **Alignment** (Group, Pre-alignment delay
lookup, Sub → tops alignment wizard, Floor bounce null -- the
calibration tasks done once per show, previously mixed into Setup), and
**OSC** (unchanged, now last since it's touched far less often than
Design). Tab order is now Design / Setup / Alignment / OSC.

Fixed: the per-sub table stayed pinned to its row-count-derived size when
the window was enlarged by hand, leaving the extra room as blank
scrollable canvas below it instead of the table using it.
`_build_scroll_tab`'s canvas now stretches its embedded content frame's
height to match whenever the canvas itself is given more room than the
content naturally needs (manual resize), letting the table's existing
`fill="both", expand=True` pack absorb the extra space -- same mechanism
already used for the horizontal stretch, generalized to vertical. Only
ever grows content, never shrinks it below its natural height, so
scrolling still kicks in normally when the window is smaller than the
content needs.

## [0.9.1] - 2026-09-21
Changed: split OSC output out of the Live tab into its own **OSC** tab
(Live / OSC / Setup), rather than sharing Live with Array/Topology
options/Level taper/Sub bandwidth/Info/the per-sub table. OSC output is
reached for constantly during a show same as everything else in the old
Live tab, but doesn't need to compete with the per-sub table for space --
the table is the thing you actually watch while running the show.
`_fit_window_height`'s per-tab canvas sizing (added in 0.9.0) generalizes
to a third tab with no other change needed. Bumped the per-sub table's
scroll cap (`_TABLE_MAX_HEIGHT_PX`) 320 -> 480px, showing more rows
before it needs to scroll now that it's not sharing the tab with OSC
output.

Fixed: the window's minimum height floor was a flat 400px, left over
from when there was only ever one view to size. With three independently-
sized tabs, that floor forced ~150-250px of dead space under a
genuinely short tab (OSC output alone only needs about 150px). Dropped
to `_MIN_WINDOW_HEIGHT = 200`.

## [0.9.0] - 2026-09-21
Fixed: the window could request a size taller than the physical screen,
with no cap and no scrollbar to recover the clipped part --
`_fit_window_height` sized purely from its own requested size
(`winfo_reqwidth`/`reqheight`), never checking `winfo_screenwidth`/
`winfo_screenheight`. On Gradient Arc Hybrid (worst case: 14 stacked
topology-option rows) this reliably overflowed a 1080p display, and
since neither column scrolled, Windows just clipped the bottom --
usually the OSC output panel and/or the tail of the per-sub table, i.e.
the two things most likely to matter mid-show. `_fit_window_height` now
clamps both the window and each tab's content to the real screen size,
falling back to scrolling (same Canvas+Scrollbar pattern the per-sub
table already used) for whatever doesn't fit.

Changed: split the old two-column layout (left column always-visible,
right column always-visible) into a **Live** / **Setup** notebook tab.
Live holds what you touch while working a show (Array, OSC output,
Topology options, Level taper, Sub bandwidth, Info, the per-sub table);
Setup holds the panels configured once per show (Units, DSP clock,
Environment, Venue → arc, Sub box dimensions, Group, Pre-alignment,
Sub → tops alignment wizard, Floor bounce null). Previously both were
stacked/side-by-side and always on screen at once, which is most of why
the window overflowed 1080p in the first place. Also moved OSC output
from dead last in the build order to right under Array -- it's the
single most operationally critical control during a show and doesn't
belong buried under Topology options/Level taper/Sub bandwidth/Info/the
whole per-sub table.

Changed: added Windows per-monitor DPI-awareness
(`SetProcessDpiAwareness`, falling back to the older
`SetProcessDPIAware` on Windows 7/8) so a scaled display (125%/150%,
common on laptops) doesn't compound the screen-size budget above with an
extra layer of OS bitmap-upscaling. No-op on non-Windows platforms.

Changed: centralized the field/panel padding that used to be a bare
`padx=5, pady=5` / `padx=10, pady=5` literal repeated at over a hundred
call sites into `FIELD_PAD_X`/`FIELD_PAD_Y`/`PANEL_PAD_X`/`PANEL_PAD_Y`,
tightened slightly to reduce the vertical footprint. Converted the
always-visible per-topology explanatory paragraph (previously a wrapped
label below the per-sub table) into a hover tooltip next to the Topology
dropdown, using the same `_help_icon` pattern every other explanatory
text in this app already uses, instead of permanently eating vertical
space.

## [0.8.2] - 2026-09-20
Fixed: **End-Fire** and **Gradient / Cardioid Pairs** showed their
computed spread position in the wrong per-sub table column under the X/Y
convention feature. Both are front-to-back stacks -- every element
shares one lateral position and spreads only in depth (the README
already said as much: End-Fire's Y is "distance from Sub 1 along the
array", Gradient's is "front/rear depth offset within a pair", and Sub
box dimensions already checks *depth* for both) -- the opposite of every
other computed topology here (Arc, Physical, Progressive, the Arc
Hybrids, Focus/Avoid Point), which are side-by-side lines spread only in
lateral. `_update_table` treated `_compute_positions()`'s result as
always lateral regardless of topology, so in L-Acoustics Mode (Y =
depth) these two showed their depth progression in X instead of Y.
Now routes it to the matching column per topology
(`is_depth_stacked` in `_update_table`, `sad_realtime_osc.py`); verified
against both X/Y conventions and cross-checked that Arc/Physical/Focus/
Avoid/the Arc Hybrids (already correct) didn't regress.

## [0.8.1] - 2026-09-20
Removed the **Subcardioid** preset (α = 0.75) from Pattern. Unlike the
remaining four presets, it has no true null anywhere -- just a shallow
dip that only reaches its textbook ~6 dB figure in the idealized
small-spacing limit. At this app's own default spacing (1.4 m, itself
the ¼λ-optimum recommendation for a 60 Hz passband top), verified
front/rear behaviour is far worse: the pattern fully **inverts** (rear
~24 dB *louder* than front) right around 50-60 Hz -- not an edge case,
the app's own suggested operating point. The other four presets all
degrade gracefully instead of inverting, because each has a genuine
structural null anchoring the pattern at every frequency; Subcardioid's
shallow, unanchored dip has nothing holding it in place as spacing grows
relative to wavelength. Cardioid (α = 0.5) was already this control's
default and stays the default. Still reachable by typing α > 0.5 into
Pattern α by hand -- this removes the one-click preset only, not the
underlying math (`gradient_pair_delay_ms` in `array_math.py` is
unrestricted below α = 1.0, same as before).

## [0.8.0] - 2026-09-20
**Null angle (°)** control for Gradient / Cardioid Pairs and Gradient Arc
Hybrid -- a robust, broadband alternative to Avoid Point for a
noise-sensitive site: dials the pair's already-exact broadband null
directly by bearing (90° through 180° off the pair's own front axis)
instead of only via the less physically intuitive Pattern α. This is not
a new mechanism -- `gradient_null_angle_deg` / `alpha_from_null_angle_deg`
in `array_math.py` just re-parameterize `gradient_pair_delay_ms`'s
existing exact construction (theta_null = acos(alpha/(alpha-1))), so the
null stays exactly as broadband/frequency-independent as Pattern/alpha's
always was. Verified by far-field superposition at every angle across the
full 90-180° range, not just the four named presets -- every case lands
at floating-point zero at every frequency tested, same standard as
Avoid Point's own verification.

Three-way live sync, following the same convention Pattern/alpha already
established: picking a named Pattern sets both alpha and Null angle;
editing Null angle solves for alpha and resets Pattern to custom; editing
alpha directly updates Null angle to match and resets Pattern to custom
(`_sync_null_angle_from_alpha` / `_on_null_angle_edited`). Alpha values
above 0.5 (Subcardioid and wider) have no true null at all, so Null angle
simply stops updating rather than showing a meaningless value -- the
field's own 90-180° range also makes an out-of-range angle unreachable
from that side. No new `.sadrt` field -- entirely derived from the
existing `gradient_alpha`, restored on project load via the same sync
function.

For the two Arc Hybrids specifically, Null angle combines with the
existing array-wide **Steer** control (which shifts the whole array's aim
asymmetrically) to bias a broad rejection zone toward one specific side
of a site, rather than being pinned to a symmetric cone around the
array's own axis -- flagged in the UI help text as the more robust
real-world tool for a genuinely noise-sensitive application than Avoid
Point's single fragile point-null, since it holds up across the whole
sub passband rather than one design frequency and isn't pinned to an
exact, wavelength-fragile XY coordinate.

Fixed in passing: the Pattern combobox itself was still gridded at row 9
-- a leftover from 0.7.0, which moved its label to row 11 to make room
for Avoid Point's own fields but missed updating the combobox's own grid
call to match. Caught while adding Null angle to the same row block, not
by symptom.

## [0.7.0] - 2026-09-20
New topology: **Avoid Point** ("Protection Mode") -- the destructive twin
of Focus Point, for placing an exact broadband null at one XY point (e.g.
a noise-sensitive site). Same physical layout and the same time-alignment
delay law as Focus Point, but with alternating polarity (odd sub normal,
even reversed, `avoid_point` in `array_math.py`) instead of Focus Point's
all-normal polarity, so the aligned arrivals cancel instead of add --
exact at every frequency by construction, the same delay-align-then-invert
mechanism that already makes Gradient/Cardioid's rear null exact, not a
new one. For an odd sub count the extra unpaired sub's polarity group
gets an automatic `20*log10(n_reversed/n_normal)` dB correction so both
groups' total level still balance exactly (visible as a small negative
Gain Trim on that group only). Verified by reconstructing the far-field
sum at several frequencies for both even and odd element counts -- every
case lands at floating-point zero (~1e-15), not merely small. New **Avoid
X** / **Avoid Y** fields (Topology options panel), same controls as Focus
X/Y. Like Focus Point, no Level taper (amplitude shading would unbalance
the exact-cancellation split) and Gain Trim stays a flat computed value.

Honesty note carried into the UI help text and topology note: the null is
exact in arrival-time/phase terms only -- this app has no polar/SPL
prediction, so real-world cancellation depth also depends on each
element's actual level reaching the target (near-field distance-spreading
differences across the array aren't modelled). For a genuinely
noise-sensitive application, cross-check against measurement or a
prediction tool rather than trusting the geometry blind.

New `.sadrt` fields: `array.avoid_x_m`, `array.avoid_y_m`.

## [0.6.0] - 2026-09-20
GUI polish pass -- precision, clutter, and a coordinate convention, plus a
British English pass and site credit:

- **1 mm / 0.1° precision floors**: every length field (Spacing, Radius, box
  dimensions, Group/alignment/venue distances) now quantizes to the nearest
  millimetre on both typed entry and slider drag (`UNIT_DECIMALS`,
  `_make_length_field`'s `commit`, `_on_spacing_slider`/
  `_on_row_spacing_slider`), instead of showing 4 decimal places of whatever
  unit happened to be active -- which meant the same value showed anywhere
  from 0.1 mm to 1 micron of apparent precision depending purely on which
  unit (m/cm/mm) was selected, with the underlying stored value never
  actually rounded. Arc angle gets the same treatment at 0.1°
  (`_labeled_slider`'s new opt-in `decimals` parameter, so Group delay/
  level, Temperature, Humidity, and Altitude are unaffected).
- **Per-sub table cleanup**: dropped the redundant **Gain (0-1 OSC)** column
  (that value still goes out over OSC as `gain`, just no longer duplicated
  in the table); merged **Delay (ms)/(smp)** and **Delay + Group (ms)/(smp)**
  into one column pair with a new **Show delay as** ms/samples toggle in the
  DSP clock panel (`_update_delay_headers`).
- **Gain Trim is read-only** for the four computed topologies -- it was the
  only directly-editable cell in an otherwise read-only row; set it via the
  Level taper panel or Group level instead. Manual mode keeps its editable
  Gain Trim entry, matching its X/Y/Polarity.
- **Array panel split**: everything topology-specific (Arc, Radius, Steer,
  Shape, Ellipse ratio, Row spacing, Progression, Focus X/Y, Pattern/α)
  moved out of "Array" into a new **Topology options** panel that only
  shows the handful of controls the current topology actually uses
  (`_build_topology_options_panel`). Array itself is now a stable Topology/
  Count/Spacing regardless of topology -- Gradient Arc Hybrid no longer
  stacks nine unrelated rows into one box.
- **X/Y convention**: a new selector in Units -- **d&b Mode** (X = depth,
  Y = lateral) or **L-Acoustics Mode** (swapped, default) -- controlling
  which per-sub table column is depth vs lateral, and which of Manual
  mode's typed X/Y fields actually drives the delay calculation
  (`_manual_depth_vars`/`_manual_lateral_vars`). Switching convention
  mid-session re-labels in place without touching any typed Manual
  positions.
- British English spelling and formatting pass across the GUI and README
  (centre, towards, dialled, generalised, metres, em dashes in place of
  `--`).
- Added a freekieaudio.uk credit line and a "100% vibe coded -- use at your
  own risk" disclaimer to the GUI footer and README.

New `.sadrt` field: `units.xy_convention`.

## [0.5.0] - 2026-09-20
Three additions from a beamforming-technology survey against microphone
arrays, steerable loudspeaker columns, and RF phased-array antennas — same
underlying array math, different fields, each already publishing exactly
the piece this app was missing:

- **Chebyshev / Taylor level taper windows**: two more options on the
  existing 9-window **Window** dropdown, the standard antenna-array
  tapers designed to give a *chosen, equal sidelobe level* rather than an
  arbitrary edge attenuation (Dolph 1946 / Taylor 1955) — exactly the gap
  `window_weights`' own docstring used to name ("no Chebyshev/Kaiser/
  Tukey, which need an extra design parameter"). Replace **Max atten
  (dB)** with a new **Sidelobe (dB)** field (default 30, range 10-100)
  when selected; gain trim becomes a literal `20*log10` of the window's
  own weights instead of the other 9 windows' linear remap, so the edge
  elements land at (Chebyshev: exactly; Taylor: approximately) that many
  dB down. Pure-Python ports of `scipy.signal.windows.chebwin`/`.taylor`
  (`_chebyshev_weights`/`_taylor_weights` in `array_math.py`, no new
  dependency — matches this app's existing hand-rolled window set) using
  a manual DFT (`_dft_real`, element counts here are small enough that
  O(n²) is free); verified by reconstructing the array factor and
  confirming every sidelobe lands at exactly the requested dB (n=16,
  30 dB -> every sidelobe -30.00 dB across a full ±90° sweep). Both
  follow Steer the same as the other 9 windows -- `steered_window_
  weights` treats the plain centred n-point array as an interpolated
  shape (`_interp_shape`) and re-centers that, since Chebyshev/Taylor
  have no continuous formula of their own to re-sample the way the
  other 9 windows' `_window_shape` does; re-centering trades away the
  exact equal-ripple property away from center, same honesty trade-off
  `arc_steered_aim_index` already makes for the other windows' own
  steering.
- **Steer-aware grating-lobe spacing limit**: a third readout in Sub
  bandwidth → optimum spacing, shown for Arc / Broadside Steering and
  the two Arc Hybrids, alongside the existing flat ½λ rule of thumb:
  `d < λ / (1 + |sin(Steer)|)`, the phased-array-antenna criterion for
  keeping a spurious lobe out of visible space (`grating_lobe_max_
  spacing_m` in `array_math.py`), evaluated at the same High (Hz) and
  the array's current Steer. Loosest (a full wavelength) at Steer = 0°,
  tightening to exactly ½λ at ±90° -- consistent with (and a rigorous,
  steer-dependent generalization of) the existing rule, which never
  accounted for Steer at all. `OK — ... (... headroom)` / `⚠
  grating-lobe risk: ...`, same phrasing convention as the Sub box
  dimensions collision check. Deliberately scoped to Steer alone, not a
  full grating-lobe model -- doesn't account for a wide Arc angle's own
  additional local curvature.
- **Tunable Gradient/Cardioid pattern**: Gradient / Cardioid Pairs and
  Gradient Arc Hybrid's front/rear pair is no longer a fixed cardioid --
  a new **Pattern** dropdown (Figure-8/Hypercardioid/Supercardioid/
  Cardioid/Subcardioid/"— custom —") plus **Pattern α** slider (0-0.9)
  set the rear element's delay via `transit_ms * α/(1-α)`
  (`gradient_pair_delay_ms` in `array_math.py`), the standard first-order
  differential-array pattern family `E(θ) = α + (1-α)·cos θ`. α = 0.5
  (Cardioid, the default) reproduces the original fixed behaviour
  exactly. Named presets use the standard literature values (0, 0.25,
  0.37, 0.5, 0.75); picking one fills α, editing α resets Pattern to
  custom, same convention as Sub box dimensions' Profile field. Verified
  by direct far-field superposition (not just the small-kd approximation
  the α formula is usually derived from): the null angle this app's
  delay construction produces, `acos(α/(α-1))`, matches the target
  pattern's own null-angle formula exactly at every α tested (e.g.
  hypercardioid α=0.25 -> 109.47°, supercardioid α=0.37 -> 125.97°, both
  exact to the derivation, not just close).
- **Taper cost readout**: a live `taper cost: X.XX dB on-axis, Y.YY dB
  total power (vs. uniform)` line under the Level taper panel, for every
  window (not just Chebyshev/Taylor) -- sidelobe control has a real SPL
  price a prediction plot doesn't show as a line item. On-axis loss
  follows the mean of the *linear* gains (`taper_onaxis_loss_db` in
  `array_math.py`), since a correctly steered array sums in phase on
  axis; total power follows the mean of the *squared* gains
  (`taper_power_loss_db`), always the smaller (less negative) of the two
  since on-axis coherent summation is hurt by tapering more than raw
  radiated power is.

New `.sadrt` fields: `array.gradient_pattern`, `array.gradient_alpha`,
`level_taper.sidelobe_db`.

## [0.4.2] - 2026-09-20
Fixed: the Array panel's FAR readout only refreshed when Angle changed on Arc
/ Broadside Steering specifically -- stale (or stuck at the initial "FAR: -")
on Physical Horizontal Array, Progressive Arc, and both Arc Hybrids, even
though the label itself has shown for all of `ANGLE_TOPOLOGIES` since those
topologies gained an Angle control. FAR is a pure function of Angle
regardless of topology, so the update now runs for the whole set instead of
just `TOPO_ARC`.

## [0.4.1] - 2026-09-20
Ellipse Shape is no longer Physical Horizontal Array-only: **Arc / Broadside
Steering** and both **Arc Hybrids** now have it too. Since those three are
physically a straight line either way, Ellipse ratio scales the *virtual*
curvature used for delay (`_arc_column_delays_s`'s sagitta term, now takes a
`depth_scale` parameter threaded through `arc_steering`, `end_fire_arc_hybrid`,
`gradient_arc_hybrid`) instead of a real physical placement -- same ratio,
same effect on the pattern, no placement/rotation to touch. `depth_scale =
1.0` reproduces each topology's existing circle math exactly (verified
bit-for-bit). Steer's own linear ramp is deliberately *not* scaled by Ellipse
ratio -- it's an independent superposition regardless of curvature depth.

Venue → arc (FAR) gains a second, independent action: an **"ellipse ratio: X"
+ "Use"** row (`ellipse_ratio_from_far`) alongside the existing "Set arc".
The two are now fully decoupled -- "Set arc" only ever touches Angle, "Use"
only ever touches Ellipse ratio -- so either can be applied without the
other, instead of "Set arc" silently doing both at once (how the FAR < 1
Ellipse case worked in 0.4.0, Physical Horizontal Array only). New
`ELLIPSE_TOPOLOGIES` set (Physical Horizontal Array, Arc / Broadside
Steering, both Arc Hybrids) drives the Shape/Ellipse ratio controls'
visibility across all four the same way `ANGLE_TOPOLOGIES` already does for
Angle-related panels.

## [0.4.0] - 2026-09-20
Three more array-shape extensions (none part of S.A.D., all this app's own,
no polar/SPL prediction to verify any of them against beyond the ratio=1.0/
uniform boundary cases that do reduce exactly to existing verified math):

- **Ellipse shape** for Physical Horizontal Array: a new Shape selector
  (Circle/Ellipse) scales *only* depth by a new Ellipse ratio
  (`physical_ellipse_layout` in `array_math.py`), keeping lateral spread and
  coverage angle unchanged; ratio = 1.0 reproduces the existing circle
  exactly. Rotation is fixed at 0° for Ellipse (not computed -- subs treated
  as omnidirectional enough at these frequencies to skip the true
  tangent-direction math). Linked to venue Length/Width via `angle_from_far_
  ellipse` / `ellipse_ratio_from_far`, which -- unlike the circle's own
  `arc_from_far` -- are defined for FAR < 1 too (a venue wider than it is
  deep): Angle pins at 180°, Ellipse ratio flattens instead, continuous with
  the circle's own FAR = 1 answer.
- **Progressive Arc**: same physical model as Physical Horizontal Array
  (every element on one real circle, so Delay stays 0 and Rotation is the
  true local angle) but with a non-uniform angular step between adjacent
  elements -- a "J-array" spread. New Progression ratio (center:edge step
  ratio, 1.0-8.0) `progressive_arc_layout`; ratio = 1.0 reproduces Physical
  Horizontal Array exactly. Collision check and Level taper extended to
  cover it (always centered, no Steer, like Physical).
- **Focus Point** ("Destruction Mode"): elements in a straight line, delayed
  so their output converges on one target point (Focus X/Y) at the same
  instant -- standard near-field acoustic focusing, exact by construction
  (`focus_point` in `array_math.py`).

Also: `_set_arc_from_venue`'s "stays in place vs. switches to Arc / Broadside
Steering" rule is now driven by one shared `ANGLE_TOPOLOGIES` set (also used
for the Angle/FAR/taper panels' visibility) instead of a separately
maintained condition -- Physical Horizontal Array and the new Progressive Arc
now also stay in place when you press "Set arc" (previously only Arc /
Broadside Steering and the two Hybrids did; Physical used to get knocked back
to Arc / Broadside the same way the Hybrids did before the 0.3.1 fix).

New `.sadrt` fields: `shape`, `ellipse_ratio`, `progression_ratio`,
`focus_x_m`, `focus_y_m`, plus two new topology keys.

## [0.3.1] - 2026-09-20
Fixed: "Set arc" (Venue → arc panel) unconditionally forced the topology to
plain Arc / Broadside Steering, silently knocking you out of an Arc Hybrid
topology (and its Row spacing) every time you used it. Now it only
topology-switches when starting from something whose Angle doesn't mean the
same thing (Physical Horizontal Array, End-Fire, Gradient, Manual) --
starting from Arc / Broadside Steering or either Arc Hybrid, it applies the
solved angle in place. See `_set_arc_from_venue` in `sad_realtime_osc.py`.

## [0.3.0] - 2026-09-20
Two new topologies, this app's own extension (not from S.A.D.): **End-Fire Arc
Hybrid** and **Gradient Arc Hybrid**. Each column is a 1:1 front/rear
End-Fire or Gradient pair, and the columns themselves are arc-steered exactly
like Arc / Broadside Steering (same symmetric, Steer-able delay pattern,
factored out into `_arc_column_delays_s` in `array_math.py` and shared with
`arc_steering`). New **Row spacing** field with its own slider (front-to-back
depth within a column, separate from the existing Spacing field, which
becomes column-to-column) and a live **¼λ** readout next to it. Level taper,
FAR, Steer, and the Venue solver's angle all carry over from Arc / Broadside
Steering; Sub box dimensions now checks both axes (column spacing vs. width,
row spacing vs. depth) for these two. Count label becomes "Columns"; max 24
columns (48 subs). Sub bandwidth panel gains an **optimum row spacing (¼λ)**
row with its own "Use" button, always ¼ wavelength regardless of the ½λ rule
the column Spacing row uses for these two topologies. Persisted in `.sadrt`
project files (`row_spacing_m`, two new topology keys). See
`end_fire_arc_hybrid` / `gradient_arc_hybrid` in `array_math.py` and the
Topologies section of README.md.

## [0.2.1] - 2026-09-19
"New" button in the Project panel resets every setting to factory defaults
(with a confirmation prompt) -- turns off Live send too, same as Load. Goes
through the same tolerant `apply_project_dict` path as loading a file
(`project_io.default_project_dict()`), so there's one reset implementation,
not two that could drift apart.

## [0.2.0] - 2026-09-19
Save/load project files (`.sadrt`, plain JSON) via a new **Project** panel:
Name/notes field, Save / Save As / Load. Persists every setting on screen
(array, taper, environment, group, sub box, venue, alignment wizard, OSC
target, per-sub Manual data). "Live send" is never restored from a loaded
file -- always starts off, so opening a project can't immediately stream OSC
to a stale host. Tolerant loader: missing fields fall back to current
defaults, unrecognized/out-of-range values are clamped or ignored with a
warning dialog rather than crashing. See `project_io.py`.

## [0.1.0] - 2026-09-19
Baseline: End-Fire, Gradient/Cardioid, Physical Horizontal Array, Arc/Broadside
Steering, and Manual topologies with live OSC output, sub profiles, and
pre-align delay import.
