# Changelog

All notable changes to S.A.D. Realtime are logged here. Bump `__version__` in
[sad_realtime_osc.py](sad_realtime_osc.py) alongside each entry.

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
