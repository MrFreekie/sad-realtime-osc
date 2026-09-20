# Changelog

All notable changes to S.A.D. Realtime are logged here. Bump `__version__` in
[sad_realtime_osc.py](sad_realtime_osc.py) alongside each entry.

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
