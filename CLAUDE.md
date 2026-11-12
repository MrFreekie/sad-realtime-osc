# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**S.A.D. Realtime** is a Python desktop application that reimplements the subwoofer array mathematics from Merlijn van Veen's S.A.D. (Subwoofer Array Designer) spreadsheet as a real-time calculator with OSC output. It targets the FOH engineer workflow for L-Acoustics + DirectOut Prodigy/ACE systems.

The app calculates three per-subwoofer values (delay, gain, polarity) for ten array topologies and streams them over OSC as sliders update live. It supports saving/loading projects as `.sadrt` files and includes calibration tools (pre-alignment lookup, group delay solver, floor bounce null calculator).

## Development Commands

```bash
# Install dependencies (desktop app)
pip install -r realtime_app/requirements.txt

# Run the desktop application (works from any folder)
python realtime_app/sad_realtime_osc.py

# Regression check of the shared math (run from repo root)
python tests/check_parity.py

# After an INTENDED math change: regenerate, then review the JSON diff
python tests/generate_parity_cases.py

# Web app: serve the REPO ROOT (not web/), then open http://127.0.0.1:8780/web/
# (also configured as "web" in .claude/launch.json). Port 8765 is used by another local server.
python -m http.server 8780 --bind 127.0.0.1
# Browser parity check: http://127.0.0.1:8780/web/selftest.html must show 115/115

# Current version (both apps) is in shared/version.py:__version__
```

No build step or linter. Both apps run directly from source.

## Two apps, one math source

This repo holds two front ends for the same calculator:

- **Desktop app** (`realtime_app/`): Tkinter + OSC output. The live-show tool.
- **Web app** (`web/`, in progress): plain HTML/JS on GitHub Pages, no OSC, no build step. It runs `shared/array_math.py` in the browser via Pyodide, so there is no JS copy of the math. It is a laptop layout and works offline as a PWA.
  - `web/js/engine.js` loads Pyodide from jsDelivr (pinned version) and mounts the `shared/` files into its virtual filesystem. JS calls math only through `engine.call("<array_math function>", args, kwargs)`, which goes via `web/py/bridge.py` (JSON in, JSON out, structured errors, public `array_math` functions only).
  - `web/sw.js` is the offline service worker. App files are network-first with a 4 s timeout, then cache. The Pyodide runtime is cache-first. **The Pyodide version is pinned in both `engine.js` and `sw.js`; change them together.** If you add a file the web app loads, add it to `SHARED_FILES` in `engine.js` and `APP_FILES` in `sw.js`.
  - The site keeps the repo's folder layout (`web/` beside `shared/` and `tests/`), so relative paths like `../shared/` work the same locally and on Pages.

**Sync rule: every feature or math change lands in both apps in the same change.**
1. Math goes in `shared/array_math.py` only. Never fork or port it into JS.
2. Update both UIs: `realtime_app/sad_realtime_osc.py` and `web/`. A control added to one gets added to the other. The only intentional difference is that the web app has no OSC tab (it has a results table with copy/CSV export instead).
3. `.sadrt` files must round-trip between the apps. If you add a field to `realtime_app/project_io.py`, add it to the web save/load with the same key, canonical SI units, and the same tolerant loading.
4. Add or extend cases in `tests/generate_parity_cases.py` for new math. If existing outputs changed on purpose, regenerate `tests/parity_cases.json` and say in the changelog which cases moved and why.
5. One version number and one `CHANGELOG.md` cover both apps.

**Not published:** the S.A.D. spreadsheets, manuals and SubArray Vizualizer in the repo root are Merlijn van Veen's / third-party reference material. `.gitignore` excludes `*.xlsx`, `*.xlsm`, `*.pdf`; keep it that way.

## Architecture

### Module Structure

- **`sad_realtime_osc.py`** — Tkinter GUI + OSC client. ~1500 lines, four-tab layout (Design / Setup / Alignment / OSC) managing the entire UI state, event handlers, and OSC sending. Entry point. Version and credits live here.

- **`shared/array_math.py`** — Pure math functions, no UI or OSC dependencies, standard library only (must stay that way so it runs under Pyodide). ~1200 lines. Safe to unit-test or reuse. Core topologies implemented here:
  - S.A.D. topologies: `end_fire`, `gradient_cardioid`, `arc_steering`, `physical_horizontal_array`, `manual`
  - This app's extensions: `end_fire_arc_hybrid`, `gradient_arc_hybrid`, `progressive_arc_layout`, `focus_point`, `avoid_point`
  - Ellipse shape variant: `physical_ellipse_layout`
  - Supporting math: speed of sound (Cramer 1993), window tapers (Chebyshev, Taylor, classic windows), acoustic delays, floor bounce nulls, grating-lobe checks, etc.

- **`project_io.py`** — Save/load `.sadrt` project files (plain JSON). Marshals Tkinter variables to/from disk. Tolerant of missing/out-of-range fields; reports warnings after loading.

- **`shared/sub_profiles.py`** — Wraps `shared/sub_profiles.csv` (sub cabinet dimensions by name). Editable without code changes; falls back to built-in defaults if missing.

- **`shared/prealign_profiles.py`** — Wraps `shared/prealign_delays.csv` (L-Acoustics factory pre-alignment data: Main system + Sub preset → delay offsets + polarity). Editable without code changes; falls back to built-in defaults if missing.

### Design Patterns

- **No UI logic in `array_math.py`**: All user-facing state (slider positions, text fields, OSC on/off) lives in `sad_realtime_osc.py`. `array_math` is a pure library — call a function, get a result.
- **Tkinter variables everywhere**: UI state is held in `tk.DoubleVar()`, `tk.StringVar()`, etc., bound to widgets directly. `project_io` reads/writes these to disk; event callbacks read them to compute new values.
- **Change detection in OSC**: Only values that actually changed are sent over OSC. Each address caches its last-sent value; a slider move that doesn't affect a given sub's delay sends nothing for it. "Send Now" forces a full resend.
- **CSV-driven profiles**: Sub box dimensions and pre-alignment combos live in `.csv` files alongside the `.py` files that parse them. No database, no code edits needed to add a profile.

## Key Design Decisions

### 1. Pure Math Module (`array_math.py`)

Every formula in this app is grounded in either S.A.D.'s own manual (verified against tutorials in the docstrings) or independent derivation. S.A.D. formulas are cited by page or section; extensions (Ellipse, Arc Hybrids, Progressive Arc) note "no tutorial ground truth" for transparency.

When adding or changing topology math:
- Verify against S.A.D.'s manual examples (search for "tutorial" in docstrings)
- Document the source (page number, equation, manual section)
- If it's a new extension, note that it has no verification ground truth

### 2. Acoustic Centre Offset (Correctness Edge Case)

The "acoustic centre offset" (default 0.30 m) corrects sub placement distance in the Sub → tops alignment wizard only — it does *not* touch inter-sub delay/spacing math. This is intentional: a uniform forward shift of every sub changes none of the path-length *differences* between them, only distance to an external reference like FOH. Documented in README.md; don't generalize the offset to all distance calculations without understanding this constraint.

### 3. No SPL/Polar Prediction

This app has no polar/SPL modeling, by design. It outputs three per-sub values (delay, gain, polarity) and the user must verify array behavior in a prediction tool (S.A.D., SubArray Visualizer, etc.) or on a test rig. Level taper (sidelobe windowing) is applied on faith, not verified in-app. When users ask "how does this pattern look," point them to S.A.D. or a third-party predictor, not this app's output.

### 4. Topology-Specific UI Features

- **Gradient/Cardioid Pairs**: Null angle and Pattern (α) controls bi-directionally sync — edit either one and the other updates. Both are grounded in the broadband far-field null formula (`acos(α/(α−1))`), verified by superposition.
- **Arc Hybrids** (End-Fire/Gradient columns + arc steering): Level taper peaks follow Steer angle, not the physical center. Steer = 0° is the old symmetric window; off-centre steering shifts the peak asymmetrically toward the steered side.
- **Avoid Point**: Exact phase cancellation at a target point (frequency-independent). Real-world depth also depends on each element's level reaching the target and near-field spreading. Document this as a "phase-only" null, not a guaranteed silent spot.
- **Ellipse shape**: FAR < 1 (venue wider than deep) has no solution in plain circle math. Shape = Ellipse solves this by pinning Angle at 180° and computing a venue-specific Ellipse ratio independently.

### 5. Save File Format

`.sadrt` files are plain JSON. Every field is stored in canonical SI units (m, ms, dB, Hz, °C) regardless of the display unit selected at the time of save. Loading re-renders in whatever unit is currently active. Enums (topology, window name, DSP rate) use stable internal keys, not display text, so UI relabeling in the future won't break old files. A `schema_version` field allows migrations in future versions.

**"Live send" is never restored from a loaded file** — it's always off after Load. A saved project can come from a different venue than the one currently patched in, so auto-streaming to a stale OSC host would be a footgun mid-show.

### 6. OSC Output Philosophy

Generic stub addresses (`/sad/sub/<n>/delay_ms`, etc.) — **not** a specific device's namespace. Users remap these addresses to match their own receiver's documented OSC spec, or use this app as the source feeding a lookup/translation layer in front of the box. This keeps the app device-agnostic and reusable across different FOH chains.

The `gain` value is normalized 0.0–1.0 from `gain_db` via a logarithmic taper calibrated to three points: 1.0 = +18 dB, ~0.778 = 0 dB, 0.0 = -144 dB (formula in `array_math.py:gain_db_to_osc`). This is **not** any device's actual curve — it's a plausible middle ground. Adjust the calibration points if a specific device's fader response differs.

## Important Context for Changes

### User Profile

The user is a FOH audio engineer with deep L-Acoustics + DirectOut Prodigy/ACE knowledge. They designed this app to avoid manual spreadsheet calculations on a show day. Feedback about precision, OSC mapping, and real-world deployment is authoritative — if the app says "approximate" and the user has production data contradicting it, that data wins.

### Approximations & Caveats

The app includes several documented approximations:
- **Dolph/Taylor window steering**: Re-sampling a Chebyshev-optimal array off-centre loses the exact equal-ripple guarantee (noted in docstring).
- **Grating lobe check**: Only accounts for Steer, not the additional curvature from a wide Arc angle (noted in README.md).
- **Speed of sound**: Uses Cramer (1993), accurate to ≤300 ppm within 0–30°C, 75–102 kPa. CO2 is fixed at ~400 ppm (negligible effect). Document if this matters for a specific use case.
- **Avoid Point null**: Exact in phase/arrival-time only. Real-world depth depends on level reaching the target and near-field spreading (both outside this app's scope).

When changes affect these approximations, verify against S.A.D. or the cited literature, update docstrings, and note any impact on precision.

### Calibration Data Files

- **`sub_profiles.csv`**: cabinet dimensions (name, width_m, depth_m). Add rows freely; no code needed.
- **`prealign_delays.csv`**: L-Acoustics pre-alignment combos (main system + sub preset → delay + polarity + config). Hand-verified against the Drive System Preset Guide (currently K1 family only; extend as verified). `sub_polarity` on non-K1 rows is deliberately overridden to negative; see notes column.

Both files have Python wrappers that fall back to built-in defaults if the CSV is missing or unparseable, so the app still runs standalone.

## Testing & Verification

`tests/check_parity.py` re-runs 115 snapshot cases against `shared/array_math.py` and fails if any output moved. It catches regressions and (later) browser/desktop drift, but the snapshot is not ground truth. Correctness against S.A.D. is checked by the math-verifier agent and manually:
- **New topologies**: Check against S.A.D.'s own tutorial (see realtime_app/README.md for which topologies are verified, which aren't).
- **Gain/OSC curves**: Tested against hardware (DirectOut Prodigy/ACE) — values read back match sent values to within ~0.1 dB quantization noise.
- **Speed of sound**: Verified against Cramer (1993) paper; matches Cramer's table to within ±1 ppm.
- **Window tapers**: Chebyshev and Taylor verified by reconstructing array factor and confirming sidelobe level matches requested dB.

Before shipping a topology change, create a simple test case in S.A.D., note the expected values, and verify this app's output matches to within rounding.

## File Naming & Structure

- `shared/`: used by both apps
  - Core math: `array_math.py` (no UI/OSC imports, stdlib only)
  - Profiles: `sub_profiles.py` + `sub_profiles.csv`, `prealign_profiles.py` + `prealign_delays.csv`
- `realtime_app/`: desktop app
  - Entry point: `sad_realtime_osc.py` (adds `../shared` to `sys.path`, imports `__version__` from `shared/version.py`)
  - Project save/load: `project_io.py` (reads/writes Tkinter variables)
  - Changelog: `CHANGELOG.md` (covers both apps; keep in step with `shared/version.py`)
  - Docs: `README.md` (comprehensive user guide)
- `web/`: browser app (GitHub Pages). `index.html` + `js/app.js` (UI), `js/engine.js` + `py/bridge.py` (Pyodide bridge), `selftest.html` (in-browser parity run), `sw.js` + `manifest.webmanifest` (offline PWA). Design/Setup/Alignment tabs are skeletons; the Design tab currently has only an End-Fire engine preview.
- `shared/version.py` (one version for both apps) and `shared/jsonable.py` (result → JSON, used by the bridge and the parity tests)
- `tests/`: `parity_cases.json` + generator/checker; `parity_common.py` is stdlib-only so it can also run under Pyodide

The repo root also holds S.A.D. spreadsheets and reference material for the math. They are git-ignored and never published.

Version bumps: update `__version__` in `shared/version.py` (both apps read it) and add a changelog entry. No tagging or release process yet.
