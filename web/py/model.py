"""Web app model: every piece of the desktop app's behaviour that isn't
Tkinter, ported to work on a plain JSON state dict.

Runs in the browser under Pyodide. JavaScript keeps no logic of its own:
it sends an action, gets back the new state plus a "view" (every label,
visibility flag and table row the page shows), and renders that.

Each function here mirrors a named method in realtime_app/sad_realtime_osc.py
or realtime_app/project_io.py (noted in its docstring), with the same
rules, rounding and readout text. tests/check_web_model.py drives the real
desktop app and this model with the same inputs and compares the results,
so when you change one, change the other and re-run that check.

State layout = the .sadrt file layout (schema 1) plus a "ui" section for
transient things the desktop keeps in widgets rather than in the file.
"""

import copy
import json
import math
from datetime import datetime, timezone

import array_math as am
import prealign_profiles
import sub_profiles
from version import __version__

SCHEMA_VERSION = 1

# --- Topologies (sad_realtime_osc.TOPOLOGIES / project_io._TOPOLOGY_KEYS) ---
END_FIRE = "end_fire"
GRADIENT = "gradient_cardioid"
PHYSICAL = "physical_horizontal"
ARC = "arc_steering"
EF_HYBRID = "end_fire_arc_hybrid"
GRAD_HYBRID = "gradient_arc_hybrid"
PROGRESSIVE = "progressive_arc"
FOCUS = "focus_point"
AVOID = "avoid_point"
MANUAL = "manual"

TOPOLOGY_LABELS = {
    END_FIRE: "End-Fire",
    GRADIENT: "Gradient / Cardioid Pairs",
    PHYSICAL: "Physical Horizontal Array",
    ARC: "Arc / Broadside Steering",
    EF_HYBRID: "End-Fire Arc Hybrid",
    GRAD_HYBRID: "Gradient Arc Hybrid",
    PROGRESSIVE: "Progressive Arc",
    FOCUS: "Focus Point",
    AVOID: "Avoid Point",
    MANUAL: "Manual",
}
HYBRIDS = (EF_HYBRID, GRAD_HYBRID)
ANGLE_TOPOLOGIES = (ARC, PHYSICAL, PROGRESSIVE) + HYBRIDS
ELLIPSE_TOPOLOGIES = (PHYSICAL, ARC) + HYBRIDS
STEER_TOPOLOGIES = (ARC,) + HYBRIDS
GRADIENT_PATTERN_TOPOLOGIES = (GRADIENT, GRAD_HYBRID)
TAPER_TOPOLOGIES = ANGLE_TOPOLOGIES  # _sync_level_taper's set: Arc, Physical, Progressive, hybrids

CUSTOM_PROFILE = "— custom —"
GRADIENT_PATTERN_ALPHA = {"Figure-8": 0.0, "Hypercardioid": 0.25, "Supercardioid": 0.37, "Cardioid": 0.5}
GRADIENT_PATTERNS = list(GRADIENT_PATTERN_ALPHA)

WAVELENGTH_FRACTION = {END_FIRE: 0.25, GRADIENT: 0.25, ARC: 0.5, EF_HYBRID: 0.5, GRAD_HYBRID: 0.5,
                       FOCUS: 0.5, AVOID: 0.5}

DSP_CLOCK_RATES = {"48 kHz (1 FS)": 48000, "96 kHz (2 FS)": 96000, "192 kHz (4 FS)": 192000}
UNITS = ["m", "cm", "mm"]
XY_DNB, XY_LACOUSTICS = "d&b Mode", "L-Acoustics Mode"
XY_CONVENTIONS = [XY_DNB, XY_LACOUSTICS]

MAX_SUBS = 12
MAX_SUBS_SPATIAL = 48

# path -> (lo, hi, decimals or None). The range a typed or dragged value is
# clamped to, matching the desktop control's own range (or the .sadrt load
# range where the desktop control doesn't clamp typed text), and the
# rounding the desktop applies (lengths: nearest mm).
NUMERIC_FIELDS = {
    "array.spacing_m": (0.001, 100000.0, 3),
    "array.row_spacing_m": (0.001, 100000.0, 3),
    "array.angle_deg": (0.0, 180.0, 1),
    "array.radius_m": (0.001, 100000.0, 3),
    "array.steer_deg": (-90.0, 90.0, 1),
    "array.ellipse_ratio": (0.05, 2.0, 2),
    "array.progression_ratio": (1.0, 8.0, 2),
    "array.focus_x_m": (-100000.0, 100000.0, 3),
    "array.focus_y_m": (-100000.0, 100000.0, 3),
    "array.avoid_x_m": (-100000.0, 100000.0, 3),
    "array.avoid_y_m": (-100000.0, 100000.0, 3),
    "level_taper.max_atten_db": (0.0, 30.0, None),
    "level_taper.sidelobe_db": (10.0, 100.0, None),
    "environment.temp_c": (-10.0, 40.0, None),
    "environment.humidity_pct": (0.0, 100.0, None),
    "environment.altitude_m": (0.0, 5000.0, None),
    "group.delay_ms": (0.0, 1000.0, None),
    "group.level_db": (-40.0, 18.0, None),
    "bandwidth.freq_high_hz": (1.0, 20000.0, None),
    "alignment_wizard.mains_distance_m": (0.0, 100000.0, 3),
    "alignment_wizard.mains_delay_ms": (-100000.0, 100000.0, None),
    "alignment_wizard.sub_distance_m": (0.0, 100000.0, 3),
    "floor_bounce.source_height_m": (0.0, 100000.0, 3),
    "floor_bounce.mic_distance_m": (0.0, 100000.0, 3),
    "floor_bounce.mic_height_m": (0.0, 100000.0, 3),
    "venue.length_m": (0.0, 100000.0, 3),
    "venue.width_m": (0.0, 100000.0, 3),
    "sub_box.width_m": (0.0, 100000.0, 3),
    "sub_box.depth_m": (0.0, 100000.0, 3),
    "sub_box.gap_m": (0.0, 100000.0, 3),
    "sub_box.acoustic_center.offset_m": (0.0, 100000.0, 3),
}

_PROFILES = {name: (w, d) for name, w, d in sub_profiles.load_profiles()}
try:
    _PREALIGN_ENTRIES = prealign_profiles.load_entries()
    _PREALIGN_ERROR = None
except prealign_profiles.PrealignDataError as e:  # shown in place of the panel, like the desktop
    _PREALIGN_ENTRIES = []
    _PREALIGN_ERROR = str(e)
_PREALIGN_MAINS = sorted({e[0] for e in _PREALIGN_ENTRIES})


# --------------------------------------------------------------- helpers --
def _get(state, path):
    node = state
    for key in path.split("."):
        node = node[key]
    return node


def _put(state, path, value):
    keys = path.split(".")
    node = state
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value


def _num(value):
    """+0.0 for -0.0, so readouts never show "-0.00"."""
    return value + 0.0


def _rows_for(topo, count):
    return count * (2 if (topo == GRADIENT or topo in HYBRIDS) else 1)


def _max_count(topo):
    """sad_realtime_osc._clamp_count_for_topology."""
    if topo == GRADIENT:
        return MAX_SUBS // 2
    if topo in HYBRIDS:
        return MAX_SUBS_SPATIAL // 2
    if topo in (PHYSICAL, ARC, MANUAL, PROGRESSIVE, FOCUS, AVOID):
        return MAX_SUBS_SPATIAL
    return MAX_SUBS


def _prealign_subs_for_main(main):
    return [e for e in _PREALIGN_ENTRIES if e[0] == main]


def _prealign_entry(main, sub):
    for e in _PREALIGN_ENTRIES:
        if e[0] == main and e[1] == sub:
            return e
    return None


# ---------------------------------------------------------------- state --
def default_state():
    """The desktop app's freshly-built state (App.__init__ defaults)."""
    main = _PREALIGN_MAINS[0] if _PREALIGN_MAINS else ""
    subs = _prealign_subs_for_main(main)
    state = {
        "name": "",
        "array": {
            "topology": ARC, "count": 6, "spacing_m": 1.4, "row_spacing_m": 0.7, "angle_deg": 0.0,
            "radius_m": 2.0, "steer_deg": 0.0, "shape": "circle", "ellipse_ratio": 1.0,
            "progression_ratio": 1.0, "focus_x_m": 10.0, "focus_y_m": 0.0, "avoid_x_m": 10.0,
            "avoid_y_m": 0.0, "gradient_pattern": "Cardioid", "gradient_alpha": 0.5,
        },
        "level_taper": {"window": am.LEVEL_TAPER_WINDOWS[0], "max_atten_db": 0.0, "sidelobe_db": 30.0},
        "units": {"length_unit": "m", "delay_display": "ms", "xy_convention": XY_LACOUSTICS},
        "dsp": {"sample_rate_hz": 96000},
        "environment": {"temp_c": 20.0, "humidity_pct": 50.0, "altitude_m": 0.0},
        "group": {
            "delay_ms": 0.0, "inverted": False, "level_db": 0.0, "makeup_db": 0.0,
            "prealign": {"active": False, "contribution_ms": 0.0, "main_system": "", "sub_system": ""},
        },
        "sub_box": {
            "profile": "L-Acoustics KS28 (Horizontal)" if "L-Acoustics KS28 (Horizontal)" in _PROFILES
            else CUSTOM_PROFILE,
            "width_m": 1.340, "depth_m": 0.702, "gap_m": 0.0,
            "acoustic_center": {"enabled": False, "offset_m": 0.30},
        },
        "venue": {"length_m": 50.0, "width_m": 25.0},
        "bandwidth": {"freq_high_hz": 60.0},
        "alignment_wizard": {"mains_distance_m": 0.0, "mains_delay_ms": 0.0, "sub_distance_m": 0.0},
        "floor_bounce": {"source_height_m": 0.0, "mic_distance_m": 0.0, "mic_height_m": 1.2},
        # Not used by the web app (no OSC). Kept so a desktop file opened and
        # re-saved here still carries its OSC target back to the desktop.
        "osc": {"host": "127.0.0.1", "port": 5000, "prefix": "/sad/sub", "live_send": False},
        "manual": {"x_m": [0.0] * 6, "y_m": [0.0] * 6, "gain_db": [0.0] * 6, "reversed": [False] * 6},
        "ui": {
            "null_angle_deg": 180.0,
            "makeup_group_level": 0.0,
            "prealign_main": main,
            "prealign_sub": subs[0][1] if subs else "",
            "prealign_note": "",
        },
    }
    return state


def _resize_manual(state, rows):
    """sad_realtime_osc._rebuild_rows' carried(): typed Manual values
    survive for rows that still exist; new rows start at default."""
    manual = state["manual"]
    for key, default in (("x_m", 0.0), ("y_m", 0.0), ("gain_db", 0.0), ("reversed", False)):
        old = list(manual.get(key) or [])
        manual[key] = [old[i] if i < len(old) else default for i in range(rows)]


def _on_topology_change(state):
    """sad_realtime_osc._on_topology_change: clamp count, rebuild rows."""
    arr = state["array"]
    arr["count"] = min(arr["count"], _max_count(arr["topology"]))
    _resize_manual(state, _rows_for(arr["topology"], arr["count"]))


def _sync_null_angle_from_alpha(state):
    angle = am.gradient_null_angle_deg(state["array"]["gradient_alpha"])
    if angle is not None:
        state["ui"]["null_angle_deg"] = round(angle, 1)


def _drop_stale_makeup(state):
    """sad_realtime_osc._drop_stale_makeup."""
    group = state["group"]
    if group["makeup_db"] != 0.0 and abs(group["level_db"] - state["ui"]["makeup_group_level"]) > 0.005:
        group["makeup_db"] = 0.0


def _set_prealign_note(state, main_sys=None, sub_sys=None, main_ms=None, sub_pol=None):
    """sad_realtime_osc._set_prealign_note."""
    pre = state["group"]["prealign"]
    if not pre["active"]:
        state["ui"]["prealign_note"] = ""
        return
    c = pre["contribution_ms"]
    sign = "+" if c >= 0 else ""
    note = f"includes {sign}{c:.2f} ms pre-alignment ({main_sys} + {sub_sys})"
    if main_ms:
        note += f" — remaining {main_ms:.2f} ms belongs on {main_sys}'s own delay, not controlled here"
    if sub_pol == "negative":
        note += " — ⚠ Sub polarity NEGATIVE: set Group polarity to Inverted yourself, this isn't applied"
    state["ui"]["prealign_note"] = note


# ------------------------------------------------------------- physics --
def speed(state):
    env = state["environment"]
    return am.speed_of_sound(env["temp_c"], env["humidity_pct"], env["altitude_m"])


def _depth_scale(state):
    arr = state["array"]
    if arr["topology"] in ELLIPSE_TOPOLOGIES and arr["shape"] == "ellipse":
        return arr["ellipse_ratio"]
    return 1.0


def _taper(state):
    """sad_realtime_osc._sync_level_taper -> (trims per row, onaxis, power).
    Non-taper topologies: zeros (the desktop's freshly rebuilt trim rows)."""
    arr = state["array"]
    topo, n = arr["topology"], arr["count"]
    rows = _rows_for(topo, n)
    if topo not in TAPER_TOPOLOGIES:
        return [0.0] * rows, None, None
    lt = state["level_taper"]
    center = None
    if topo == ARC or topo in HYBRIDS:
        center = am.arc_steered_aim_index(n, arr["angle_deg"], arr["steer_deg"])
    taper = am.level_taper_db(n, lt["window"], lt["max_atten_db"], center, lt["sidelobe_db"])
    taper = [round(db, 2) + 0.0 for db in taper]
    trims = [0.0] * rows
    for i, db in enumerate(taper):
        for j in ((i * 2, i * 2 + 1) if topo in HYBRIDS else (i,)):
            if j < rows:
                trims[j] = db
    return trims, am.taper_onaxis_loss_db(taper), am.taper_power_loss_db(taper)


def _manual_depth_lateral(state):
    m = state["manual"]
    if state["units"]["xy_convention"] == XY_DNB:
        return m["x_m"], m["y_m"]
    return m["y_m"], m["x_m"]


def compute(state, trims):
    """sad_realtime_osc._compute."""
    arr = state["array"]
    topo, n = arr["topology"], arr["count"]
    c = speed(state)
    if topo == END_FIRE:
        return am.end_fire(n, arr["spacing_m"], c, trims)
    if topo == GRADIENT:
        return am.gradient_cardioid(n, arr["spacing_m"], c, trims, arr["gradient_alpha"])
    if topo == ARC:
        return am.arc_steering(n, arr["spacing_m"], arr["angle_deg"], c, trims, arr["steer_deg"],
                               _depth_scale(state))
    if topo in (PHYSICAL, PROGRESSIVE):
        return am.physical_horizontal_array(n, trims)
    if topo == EF_HYBRID:
        return am.end_fire_arc_hybrid(n, arr["spacing_m"], arr["row_spacing_m"], arr["angle_deg"], c, trims,
                                      arr["steer_deg"], _depth_scale(state))
    if topo == GRAD_HYBRID:
        return am.gradient_arc_hybrid(n, arr["spacing_m"], arr["row_spacing_m"], arr["angle_deg"], c, trims,
                                      arr["steer_deg"], _depth_scale(state), arr["gradient_alpha"])
    if topo == FOCUS:
        return am.focus_point(n, arr["spacing_m"], arr["focus_x_m"], arr["focus_y_m"], c, trims)
    if topo == AVOID:
        return am.avoid_point(n, arr["spacing_m"], arr["avoid_x_m"], arr["avoid_y_m"], c, trims)
    if topo == MANUAL:
        depths, _ = _manual_depth_lateral(state)
        delays = am.delays_from_depth(depths, c)
        return am.manual(n, delays, state["manual"]["gain_db"], state["manual"]["reversed"])
    return []


def physical_layout(state):
    """sad_realtime_osc._compute_physical_layout -> [(depth, lateral, rotation)]."""
    arr = state["array"]
    topo, n = arr["topology"], arr["count"]
    if topo == MANUAL:
        depths, laterals = _manual_depth_lateral(state)
        return [(d, l, 0.0) for d, l in zip(depths, laterals)]
    if topo in HYBRIDS:
        depths = am.sub_positions_arc_hybrid_depth(n, arr["row_spacing_m"])
        laterals = am.sub_positions_arc_hybrid_lateral(n, arr["spacing_m"])
        return [(d, y, 0.0) for d, y in zip(depths, laterals)]
    if topo == PROGRESSIVE:
        return am.progressive_arc_layout(n, arr["radius_m"], arr["angle_deg"], arr["progression_ratio"])
    if topo != PHYSICAL:
        return [(0.0, 0.0, 0.0)] * _rows_for(topo, n)
    if arr["shape"] == "ellipse":
        return am.physical_ellipse_layout(n, arr["radius_m"], arr["angle_deg"], arr["ellipse_ratio"])
    return am.physical_arc_layout(n, arr["radius_m"], arr["angle_deg"])


def _positions(state):
    """sad_realtime_osc._compute_positions (non-Manual)."""
    arr = state["array"]
    topo, n, spacing = arr["topology"], arr["count"], arr["spacing_m"]
    if topo in (PHYSICAL, PROGRESSIVE):
        return [lateral for _, lateral, _ in physical_layout(state)]
    if topo == GRADIENT:
        return am.sub_positions_gradient(n, spacing)
    if topo in (ARC, FOCUS, AVOID):
        return am.sub_positions_centered(n, spacing)
    if topo in HYBRIDS:
        return am.sub_positions_arc_hybrid_lateral(n, spacing)
    return am.sub_positions(n, spacing)


# --------------------------------------------------------------- actions --
def apply_action(state, action):
    """Returns (new_state, message or None). Every UI event comes through here."""
    state = copy.deepcopy(state)
    kind = action.get("type")
    msg = None
    arr = state["array"]

    if kind == "set":
        path, value = action["path"], action["value"]
        if path in NUMERIC_FIELDS:
            lo, hi, dec = NUMERIC_FIELDS[path]
            value = float(value)
            if not math.isfinite(value):
                return state, "Not a number"
            value = max(lo, min(hi, value))
            if dec is not None:
                value = round(value, dec)
            _put(state, path, _num(value))
            if path in ("sub_box.width_m", "sub_box.depth_m"):
                state["sub_box"]["profile"] = CUSTOM_PROFILE  # _on_dimension_edited
        elif path == "name":
            state["name"] = str(value)
        elif path == "array.count":
            count = int(value)
            arr["count"] = max(1, min(_max_count(arr["topology"]), count))
            _resize_manual(state, _rows_for(arr["topology"], arr["count"]))
        elif path == "array.topology":
            if value in TOPOLOGY_LABELS:
                arr["topology"] = value
                _on_topology_change(state)
        elif path == "array.shape":
            if value in ("circle", "ellipse"):
                arr["shape"] = value
                _on_topology_change(state)
        elif path == "array.gradient_pattern":  # _on_gradient_pattern_change
            arr["gradient_pattern"] = value if value in GRADIENT_PATTERNS else CUSTOM_PROFILE
            if value in GRADIENT_PATTERN_ALPHA:
                arr["gradient_alpha"] = GRADIENT_PATTERN_ALPHA[value]
                _sync_null_angle_from_alpha(state)
        elif path == "array.gradient_alpha":  # _on_gradient_alpha_edited
            arr["gradient_alpha"] = round(max(0.0, min(0.9, float(value))), 3)
            arr["gradient_pattern"] = CUSTOM_PROFILE
            _sync_null_angle_from_alpha(state)
        elif path == "ui.null_angle_deg":  # _on_null_angle_edited
            angle = round(float(value), 1)
            alpha = am.alpha_from_null_angle_deg(angle)
            if alpha is None:
                _sync_null_angle_from_alpha(state)
            else:
                state["ui"]["null_angle_deg"] = angle
                arr["gradient_alpha"] = round(alpha, 4)
                arr["gradient_pattern"] = CUSTOM_PROFILE
        elif path == "level_taper.window":
            if value in am.LEVEL_TAPER_WINDOWS:
                state["level_taper"]["window"] = value
        elif path == "units.length_unit":
            if value in UNITS:
                state["units"]["length_unit"] = value
        elif path == "units.delay_display":
            if value in ("ms", "samples"):
                state["units"]["delay_display"] = value
        elif path == "units.xy_convention":
            if value in XY_CONVENTIONS:
                state["units"]["xy_convention"] = value
        elif path == "dsp.sample_rate_hz":
            if int(value) in DSP_CLOCK_RATES.values():
                state["dsp"]["sample_rate_hz"] = int(value)
        elif path == "group.inverted":
            state["group"]["inverted"] = bool(value)
        elif path == "sub_box.acoustic_center.enabled":
            state["sub_box"]["acoustic_center"]["enabled"] = bool(value)
        elif path == "sub_box.profile":  # _on_profile_change
            if value in _PROFILES:
                state["sub_box"]["profile"] = value
                state["sub_box"]["width_m"], state["sub_box"]["depth_m"] = _PROFILES[value]
            else:
                state["sub_box"]["profile"] = CUSTOM_PROFILE
        else:
            return state, f"Unknown field {path}"

    elif kind == "manual":  # a typed cell in Manual mode's table
        i, field, value = int(action["row"]), action["field"], action["value"]
        rows = len(state["manual"]["x_m"])
        if 0 <= i < rows and field in ("x_m", "y_m", "gain_db", "reversed"):
            if field == "reversed":
                state["manual"][field][i] = bool(value)
            else:
                v = float(value)
                if math.isfinite(v):
                    state["manual"][field][i] = _num(round(v, 3) if field != "gain_db" else v)

    elif kind == "group_distance":  # _on_group_distance_change
        ms = am.delay_ms_for_distance(round(float(action["value"]), 3), speed(state))
        state["group"]["delay_ms"] = round(max(ms, 0.0), 4)

    elif kind == "makeup_apply":  # _apply_makeup_gain
        if arr["topology"] in TAPER_TOPOLOGIES:
            _drop_stale_makeup(state)
            group = state["group"]
            _, onaxis, _ = _taper(state)
            base = group["level_db"] - group["makeup_db"]
            target = round(max(-40.0, min(18.0, base - (onaxis or 0.0))), 2) + 0.0
            group["level_db"] = target
            group["makeup_db"] = target - base
            state["ui"]["makeup_group_level"] = target

    elif kind == "makeup_clear":  # _clear_makeup_gain
        _drop_stale_makeup(state)
        group = state["group"]
        if group["makeup_db"] != 0.0:
            target = round(group["level_db"] - group["makeup_db"], 2) + 0.0
            group["level_db"] = target
            group["makeup_db"] = 0.0
            state["ui"]["makeup_group_level"] = target

    elif kind == "prealign_main":  # _on_prealign_main_change
        state["ui"]["prealign_main"] = action["value"]
        subs = _prealign_subs_for_main(action["value"])
        state["ui"]["prealign_sub"] = subs[0][1] if subs else ""

    elif kind == "prealign_sub":
        state["ui"]["prealign_sub"] = action["value"]

    elif kind == "prealign_use":  # _use_prealign_delay
        entry = _prealign_entry(state["ui"]["prealign_main"], state["ui"]["prealign_sub"])
        if entry is not None:
            main_sys, sub_sys, main_ms, sub_ms, _mp, sub_pol, _mc, _sc, _n = entry
            pre = state["group"]["prealign"]
            delta = sub_ms - pre["contribution_ms"]
            state["group"]["delay_ms"] = round(state["group"]["delay_ms"] + delta, 4)
            pre.update(active=True, contribution_ms=sub_ms, main_system=main_sys, sub_system=sub_sys)
            _set_prealign_note(state, main_sys, sub_sys, main_ms, sub_pol)

    elif kind == "prealign_clear":  # _clear_prealign_delay
        pre = state["group"]["prealign"]
        if pre["active"]:
            state["group"]["delay_ms"] = round(state["group"]["delay_ms"] - pre["contribution_ms"], 4)
            pre.update(active=False, contribution_ms=0.0, main_system="", sub_system="")
            _set_prealign_note(state)

    elif kind in ("set_min_spacing", "set_spacing_gap"):  # _set_min_spacing / _set_spacing_with_gap
        if arr["topology"] not in (PHYSICAL, PROGRESSIVE):
            box_dim, _ = _relevant_box_dimension(state)
            if box_dim is not None:
                gap = state["sub_box"]["gap_m"] if kind == "set_spacing_gap" else 0.0
                arr["spacing_m"] = round(box_dim + gap, 3)

    elif kind == "use_optimum_spacing":  # _use_optimum_spacing
        frac = WAVELENGTH_FRACTION.get(arr["topology"])
        if frac is not None:
            opt = am.spacing_at_wavelength_fraction(state["bandwidth"]["freq_high_hz"], speed(state), frac)
            if opt is not None:
                arr["spacing_m"] = round(opt, 3)

    elif kind == "use_optimum_row_spacing":  # _use_optimum_row_spacing
        opt = am.spacing_at_wavelength_fraction(state["bandwidth"]["freq_high_hz"], speed(state), 0.25)
        if opt is not None:
            arr["row_spacing_m"] = round(opt, 3)

    elif kind == "set_arc_from_venue":  # _set_arc_from_venue
        far, arc = _venue_far_arc(state)
        if _venue_is_ellipse(state):
            arc = am.angle_from_far_ellipse(far)
        if arc is not None:
            if arr["topology"] not in ANGLE_TOPOLOGIES:
                arr["topology"] = ARC
                _on_topology_change(state)
            arr["angle_deg"] = round(min(arc, 180.0), 1)

    elif kind == "use_venue_ellipse":  # _use_venue_ellipse_ratio
        far, _ = _venue_far_arc(state)
        ratio = am.ellipse_ratio_from_far(far)
        if ratio is not None:
            arr["ellipse_ratio"] = round(ratio, 3)

    elif kind == "set_group_from_alignment":  # _set_group_delay_from_alignment
        result = _required_group_delay(state)
        if result is not None:
            state["group"]["delay_ms"] = max(0.0, round(result, 4))

    elif kind == "new":
        state = default_state()

    else:
        return state, f"Unknown action {kind}"

    _drop_stale_makeup(state)  # every _on_change starts with this
    return state, msg


# ------------------------------------------------------------ readouts --
def _relevant_box_dimension(state):
    topo = state["array"]["topology"]
    if topo in (ARC, PHYSICAL, PROGRESSIVE, FOCUS, AVOID) or topo in HYBRIDS:
        return state["sub_box"]["width_m"], "width"
    if topo in (END_FIRE, GRADIENT):
        return state["sub_box"]["depth_m"], "depth"
    return None, None


def _clearance_text(spacing, box_dim, dim_name):
    clearance = am.spacing_clearance_m(spacing, box_dim)
    if clearance < 0:
        return f"⚠ {box_dim:.2f} m {dim_name} > {spacing:.2f} m spacing (by {-clearance:.2f} m)"
    return f"OK — {clearance:.2f} m clearance ({dim_name})"


def _collision_text(state):
    """sad_realtime_osc._update_collision_check."""
    arr = state["array"]
    box = state["sub_box"]
    if arr["topology"] in HYBRIDS:
        col = _clearance_text(arr["spacing_m"], box["width_m"], "width")
        row = _clearance_text(arr["row_spacing_m"], box["depth_m"], "depth")
        return f"col: {col}  |  row: {row}"
    box_dim, dim_name = _relevant_box_dimension(state)
    if box_dim is None:
        return "n/a in Manual mode"
    topo = arr["topology"]
    if topo == PHYSICAL and arr["shape"] == "circle":
        spacing = am.physical_arc_chord_spacing(arr["count"], arr["radius_m"], arr["angle_deg"])
    elif topo in (PHYSICAL, PROGRESSIVE):
        spacing = am.min_adjacent_chord(physical_layout(state))
    else:
        spacing = arr["spacing_m"]
    if spacing is None:
        return "-"
    return _clearance_text(spacing, box_dim, dim_name)


def _grating_lobe_text(state):
    steer = state["array"]["steer_deg"]
    d_max = am.grating_lobe_max_spacing_m(state["bandwidth"]["freq_high_hz"], speed(state), steer)
    if d_max is None:
        return "-"
    spacing = state["array"]["spacing_m"]
    margin = d_max - spacing
    if margin < 0:
        return (f"⚠ grating-lobe risk: {spacing:.2f} m spacing > {d_max:.2f} m limit "
                f"at Steer {steer:.0f}° (by {-margin:.2f} m)")
    return f"OK — grating-lobe limit {d_max:.2f} m at Steer {steer:.0f}° ({margin:.2f} m headroom)"


def _venue_far_arc(state):
    far = am.far_from_venue(state["venue"]["length_m"], state["venue"]["width_m"])
    return far, am.arc_from_far(far)


def _venue_is_ellipse(state):
    return state["array"]["topology"] in ELLIPSE_TOPOLOGIES and state["array"]["shape"] == "ellipse"


def _venue_view(state):
    """sad_realtime_osc._update_venue_far."""
    far, arc = _venue_far_arc(state)
    is_ellipse = _venue_is_ellipse(state)
    if far is None:
        text = "FAR: -  arc: -"
    elif arc is None and is_ellipse:
        text = f"FAR: {far:.2f}  arc: {am.angle_from_far_ellipse(far):.1f}°"
    elif arc is None:
        text = f"FAR: {far:.2f}  arc: n/a (wider than deep -- a circle can't; try Shape = Ellipse)"
    else:
        text = f"FAR: {far:.2f}  arc: {arc:.1f}°"
    ratio = am.ellipse_ratio_from_far(far) if is_ellipse else None
    return {
        "far_text": text,
        "can_set_arc": far is not None and (arc is not None or is_ellipse),
        "ellipse_text": f"ellipse ratio: {ratio:.3f}" if ratio is not None else "ellipse ratio: -",
    }


def _sub_distance_to_foh(state):
    d = state["alignment_wizard"]["sub_distance_m"]
    ac = state["sub_box"]["acoustic_center"]
    if ac["enabled"]:
        d -= ac["offset_m"]
    return d


def _required_group_delay(state):
    w = state["alignment_wizard"]
    return am.required_group_delay_ms(w["mains_distance_m"], w["mains_delay_ms"], _sub_distance_to_foh(state),
                                      speed(state))


def _alignment_view(state):
    """sad_realtime_osc._update_alignment_wizard."""
    corrected = ""
    if state["sub_box"]["acoustic_center"]["enabled"]:
        corrected = f"→ acoustic centre corrected: {_sub_distance_to_foh(state):.2f} m"
    result = _required_group_delay(state)
    if result is None:
        text = "required group delay: -"
    elif result < 0:
        text = f"required group delay: {result:.2f} ms (negative — delay the mains instead)"
    else:
        text = f"required group delay: {result:.2f} ms"
    return {"corrected_text": corrected, "result_text": text}


def _bounce_text(state):
    """sad_realtime_osc._update_floor_bounce."""
    b = state["floor_bounce"]
    try:
        r = am.floor_bounce(b["source_height_m"], b["mic_distance_m"], b["mic_height_m"], speed(state))
    except ValueError:
        return "null: -"
    if r.null_hz is None:
        return "null: none (source and mic both at floor level -- no separate reflection path)"
    return (f"null: {r.null_hz:.1f} Hz  (peak {r.peak_hz:.1f} Hz, "
            f"path diff {r.path_diff_m:.3f} m, bounce {r.bounce_level_db:.1f} dB down)")


def _wavelength_view(state):
    """sad_realtime_osc._update_wavelength_readouts."""
    arr = state["array"]
    c = speed(state)
    f_high = state["bandwidth"]["freq_high_hz"]
    frac = WAVELENGTH_FRACTION.get(arr["topology"])
    label = "¼λ" if frac == 0.25 else "½λ" if frac == 0.5 else None
    out = {}
    if frac is None:
        out["wavelength_text"] = "n/a"
        out["optimum_text"] = "optimum spacing: n/a"
        out["optimum_enabled"] = False
    else:
        f = am.freq_at_wavelength_fraction(arr["spacing_m"], c, frac)
        out["wavelength_text"] = f"{label}: {f:.1f} Hz" if f else "-"
        opt = am.spacing_at_wavelength_fraction(f_high, c, frac)
        out["optimum_text"] = f"optimum spacing ({label}): {opt:.3f} m" if opt else "optimum spacing: -"
        out["optimum_enabled"] = True
    f_row = am.freq_at_wavelength_fraction(arr["row_spacing_m"], c, 0.25)
    out["row_wavelength_text"] = f"¼λ: {f_row:.1f} Hz" if f_row else "-"
    row_opt = am.spacing_at_wavelength_fraction(f_high, c, 0.25)
    out["row_optimum_text"] = (f"optimum row spacing (¼λ): {row_opt:.3f} m" if row_opt
                               else "optimum row spacing: -")
    out["grating_lobe_text"] = _grating_lobe_text(state)
    return out


def _info_view(state):
    """sad_realtime_osc._update_info_panel / _update_virtual_source_label."""
    arr = state["array"]
    topo, n, spacing = arr["topology"], arr["count"], arr["spacing_m"]
    c = speed(state)
    is_gradient = topo == GRADIENT
    length = spacing if is_gradient else am.array_length(n, spacing)
    out = {"length_text": f"{'pair depth' if is_gradient else 'array length'}: {length:.2f} m"}
    f_1l = am.freq_at_wavelength_fraction(length, c, 1.0)
    out["one_lambda_text"] = f"array 1λ: {f_1l:.0f} Hz" if f_1l else "array 1λ: -"
    for key, frac, deg in (("d180_text", 0.5, 180), ("d240_text", 2.0 / 3.0, 240), ("d360_text", 1.0, 360)):
        f = am.freq_at_wavelength_fraction(spacing, c, frac)
        out[key] = f"spk dist {deg}°: {f:.0f} Hz" if f else f"spk dist {deg}°: -"

    text = "virtual source: n/a (no arc in this topology)"
    if topo in (ARC, EF_HYBRID, GRAD_HYBRID):
        result = am.arc_virtual_source(n, spacing, arr["angle_deg"], arr["steer_deg"], _depth_scale(state))
        unit = "column" if topo in HYBRIDS else "sub"
    elif topo in (PHYSICAL, PROGRESSIVE):
        behind = am.physical_virtual_source_m(arr["radius_m"], _depth_scale(state))
        result = None if behind is None else (behind, 0.0, 0.0)
        unit = "sub"
    else:
        result = False
    if result is None:
        text = ("virtual source: at infinity (Radius is 0)" if topo in (PHYSICAL, PROGRESSIVE)
                else "virtual source: at infinity (flat line, Arc angle 0°)")
    elif result is not False:
        behind, offset, rms = result
        aperture = max((n - 1) * spacing, 0.001)
        if behind > 500.0 or abs(offset) > 500.0:
            text = "virtual source: at infinity (delays are close to a plane wave)"
        elif behind <= 0.05 or rms > 0.25 * aperture:
            text = "virtual source: no reliable point-source fit (arc/Steer too extreme)"
        else:
            side = ("on-axis" if abs(offset) < 0.005 else
                    f"{abs(offset):.2f} m off-axis toward {unit} {n if offset > 0 else 1} end")
            rough = " (rough fit)" if rms > 0.05 * behind else ""
            text = f"virtual source: {behind:.2f} m behind array centre, {side}{rough}"
    out["virtual_text"] = text
    return out


def _prealign_view(state):
    """sad_realtime_osc._update_prealign_readout."""
    if _PREALIGN_ERROR:
        return {"error": f"⚠ prealign_delays.csv error:\n{_PREALIGN_ERROR}"}
    main = state["ui"]["prealign_main"]
    out = {
        "mains": _PREALIGN_MAINS,
        "subs": [e[1] for e in _prealign_subs_for_main(main)],
        "main": main,
        "sub": state["ui"]["prealign_sub"],
        "main_text": "Main: -", "main_polarity": None,
        "sub_text": "Sub: -", "sub_polarity": None,
    }
    entry = _prealign_entry(main, state["ui"]["prealign_sub"])
    if entry is not None:
        main_sys, sub_sys, main_ms, sub_ms, main_pol, sub_pol, main_cfg, sub_cfg, _ = entry
        labels, cfgs = prealign_profiles.POLARITY_LABELS, prealign_profiles.CONFIG_LABELS
        main_suffix = f", {cfgs.get(main_cfg, main_cfg)}" if main_cfg != "standard" else ""
        sub_suffix = f", {cfgs.get(sub_cfg, sub_cfg)}" if sub_cfg != "standard" else ""
        out["main_text"] = f"Main: {main_sys} = {main_ms:.2f} ms  [{labels.get(main_pol, main_pol)}{main_suffix}]"
        out["sub_text"] = f"Sub: {sub_sys} = {sub_ms:.2f} ms  [{labels.get(sub_pol, sub_pol)}{sub_suffix}]"
        out["main_polarity"], out["sub_polarity"] = main_pol, sub_pol
    return out


def topology_note(state):
    """sad_realtime_osc._topology_note / _manual_note_text (same text)."""
    topo = state["array"]["topology"]
    if topo == MANUAL:
        dnb = state["units"]["xy_convention"] == XY_DNB
        depth_col, lateral_col = ("X", "Y") if dnb else ("Y", "X")
        return (f"Place each sub freely: type {depth_col} (depth, front-to-back — larger/less-negative is "
                f"closer to the audience) and {lateral_col} (lateral, informational only) directly. Delay is "
                f"derived, not typed — the rearmost placed sub (smallest {depth_col}) is the 0 ms reference, "
                "same plane-wave-towards-the-audience logic as End-Fire, generalised to free 2D placement. "
                "Gain trim and Polarity stay directly editable.")
    is_ellipse = topo in ELLIPSE_TOPOLOGIES and state["array"]["shape"] == "ellipse"
    notes = {
        END_FIRE: "Sub 1 = front (faces audience), highest number = rearmost. All normal polarity; "
                  "delay increases towards the front so the array reinforces forward and cancels rearward.",
        GRADIENT: "Each pair = odd sub (front, normal, 0 ms) + even sub (rear, "
                  "reversed polarity, delayed by the pair spacing). Produces a broadband "
                  "null directly behind each pair.",
        PHYSICAL: "Sub 1..N physically placed and rotated on a real arc of the given "
                  "Radius spanning the Arc angle (S.A.D.'s \"physical horizontal "
                  "array\") — Spacing doesn't apply, it's a consequence of Radius/Arc/"
                  "count. Every element is already equidistant from the arc's centre, "
                  "so delay is fixed at 0 by design; gain trim defaults to 0 but can "
                  "still be tapered (Level taper panel below) for sidelobe control. The "
                  "real output here is the physical layout in the X/Y/Rotation columns."
                  + (" Shape = Ellipse scales depth only (lateral and total coverage "
                     "unchanged) by Ellipse ratio -- this app's own extension, not part "
                     "of S.A.D.; Rotation is fixed at 0° for this shape (not computed)."
                     if is_ellipse else ""),
        ARC: "Sub 1..N along a line, all normal polarity. Delay is symmetric — "
             "0 ms at the centre element(s), increasing towards both edges — as if "
             "the line were physically bowed into an arc spanning the Arc angle "
             "(S.A.D.'s \"delayed horizontal array\"). FAR (Forward Aspect Ratio) "
             "= 1/sin(arc/2), the depth:width ratio for that coverage angle. Steer "
             "redirects the whole arc off-centre for asymmetrical venues, without "
             "changing the coverage angle.",
        EF_HYBRID: "Each column = a front/rear End-Fire pair (1:1), and the columns themselves "
                   "are arc-steered like Arc / Broadside Steering. Within a column: rear = 0 ms reference, "
                   "front = + Row spacing/speed of sound, both normal polarity. Column-to-column delay is "
                   "the same symmetric arc-steering pattern as Arc / Broadside Steering, added underneath "
                   "each column's own front/rear offset. Spacing = column-to-column (lateral); Row spacing "
                   "= front-to-back depth within a column.",
        GRAD_HYBRID: "Each column = a front/rear Gradient (cardioid) pair (1:1), and the columns "
                     "themselves are arc-steered like Arc / Broadside Steering. Within a column: front = 0 ms, "
                     "normal polarity; rear = + Row spacing/speed of sound, reversed polarity — the same "
                     "broadband rear null as Gradient / Cardioid Pairs, per column. Column-to-column delay is "
                     "the same symmetric arc-steering pattern as Arc / Broadside Steering, added underneath "
                     "each column's own front/rear offset. Spacing = column-to-column (lateral); Row spacing "
                     "= front-to-back depth within a column.",
        PROGRESSIVE: "Same physical model as Physical Horizontal Array (every element equidistant "
                     "from one center of curvature on a real arc of the given Radius, so delay stays fixed "
                     "at 0 and Rotation is the true local aim angle) but with a non-uniform angular step "
                     "between adjacent elements instead of a constant one -- Progression sets the center:edge "
                     "(needs 4+ elements) step ratio (1.0 = uniform, identical to Physical Horizontal Array). "
                     "Above 1.0 the center gap(s) widen and the edge gaps narrow, so total coverage angle "
                     "(and FAR) is unchanged. This app's own extension, not part of S.A.D.",
        FOCUS: "\"Destruction Mode\": elements in a straight line (same physical layout as Arc / "
               "Broadside Steering), all delayed so their output arrives at one target point (Focus X/Y) "
               "at the same instant, for maximum constructive buildup there. Near-field acoustic "
               "focusing -- exact by construction from geometry alone, not an approximation. This app's "
               "own extension, not a S.A.D. topology.",
        AVOID: "\"Protection Mode\": Focus Point's destructive twin -- same physical layout and "
               "same time-alignment delay to one target point (Avoid X/Y), but alternating polarity "
               "(odd sub normal, even reversed) so the aligned arrivals cancel instead of add. Exact, "
               "frequency-independent null at that point by construction -- the same delay-align-then-"
               "invert trick already behind Gradient/Cardioid's rear null, not a new mechanism. No "
               "polar/SPL prediction here either, so this is a phase-cancellation guarantee, not a "
               "measured-quiet guarantee -- for a genuinely noise-sensitive site, confirm with a "
               "prediction tool or measurement rather than trusting the geometry blind. This app's own "
               "extension, not a S.A.D. topology.",
    }
    return notes[topo]


def _table(state, subs, trims):
    """sad_realtime_osc._update_table, as data. Gain Trim shows each sub's
    computed gain (s.gain_db): the desktop shows the taper value here, which
    misses Avoid Point's odd-count balance correction -- see CHANGELOG."""
    arr = state["array"]
    topo = arr["topology"]
    rows = len(subs)
    is_manual = topo == MANUAL
    dnb = state["units"]["xy_convention"] == XY_DNB
    depth = [0.0] * rows
    lateral = [0.0] * rows
    rotation = [0.0] * rows
    layout = physical_layout(state)
    if is_manual:
        d, l = _manual_depth_lateral(state)
        depth, lateral = list(d[:rows]), list(l[:rows])
    else:
        positions = _positions(state)
        if topo in (END_FIRE, GRADIENT):
            for i, p in enumerate(positions[:rows]):
                depth[i] = p
        else:
            for i, p in enumerate(positions[:rows]):
                lateral[i] = p
            for i, (dd, _l, _r) in enumerate(layout[:rows]):
                depth[i] = dd
    for i, (_d, _l, r) in enumerate(layout[:rows]):
        rotation[i] = r

    group = state["group"]
    rate = state["dsp"]["sample_rate_hz"]
    samples = state["units"]["delay_display"] == "samples"
    unit = "smp" if samples else "ms"
    out_rows = []
    for i, s in enumerate(subs):
        total_ms = am.total_delay_ms(s.delay_ms, group["delay_ms"])
        total_gain = am.total_gain_db(s.gain_db, group["level_db"])
        eff = am.effective_polarity(s.polarity_reversed, group["inverted"])
        x, y = (depth[i], lateral[i]) if dnb else (lateral[i], depth[i])
        out_rows.append({
            "index": s.index,
            "x_m": _num(x), "y_m": _num(y), "depth_m": _num(depth[i]), "lateral_m": _num(lateral[i]),
            "rotation_deg": _num(rotation[i]),
            "delay_ms": s.delay_ms, "delay_total_ms": total_ms,
            "delay_samples": am.delay_samples(s.delay_ms, rate),
            "delay_total_samples": am.delay_samples(total_ms, rate),
            "gain_db": s.gain_db, "gain_total_db": total_gain,
            "polarity_reversed": eff,
            "manual_reversed": bool(state["manual"]["reversed"][i]) if is_manual else None,
            "text": {
                "x": f"{_num(x):.2f}", "y": f"{_num(y):.2f}",
                "rotation": f"{_num(rotation[i]):.1f}",
                "delay": str(am.delay_samples(s.delay_ms, rate)) if samples else f"{s.delay_ms:.2f}",
                "delay_total": str(am.delay_samples(total_ms, rate)) if samples else f"{total_ms:.2f}",
                "gain": f"{_num(s.gain_db):.2f}",
                "gain_total": f"{_num(total_gain):.2f}",
                "polarity": "Reversed" if eff else "Normal",
            },
        })
    return {"unit": unit, "editable": is_manual, "rows": out_rows}


def view(state):
    """Everything the page shows for `state` (sad_realtime_osc._on_change)."""
    arr = state["array"]
    topo = arr["topology"]
    is_hybrid = topo in HYBRIDS
    is_ellipse_capable = topo in ELLIPSE_TOPOLOGIES
    is_ellipse = is_ellipse_capable and arr["shape"] == "ellipse"
    uses_angle = topo in ANGLE_TOPOLOGIES
    uses_steer = topo in STEER_TOPOLOGIES
    uses_radius = topo in (PHYSICAL, PROGRESSIVE)
    no_spacing = topo in (PHYSICAL, MANUAL, PROGRESSIVE)
    uses_pattern = topo in GRADIENT_PATTERN_TOPOLOGIES
    c = speed(state)

    v = {
        "version": __version__,
        "show": {
            "angle": uses_angle, "radius": uses_radius, "steer": uses_steer, "spacing": not no_spacing,
            "row_spacing": is_hybrid, "shape": is_ellipse_capable, "ellipse": is_ellipse,
            "progression": topo == PROGRESSIVE, "focus": topo == FOCUS, "avoid": topo == AVOID,
            "pattern": uses_pattern, "taper": uses_angle, "venue": uses_angle,
            "topology_options": (uses_angle or uses_radius or uses_steer or is_hybrid or is_ellipse_capable
                                 or topo in (PROGRESSIVE, FOCUS, AVOID) or uses_pattern),
            "parametric_taper": state["level_taper"]["window"] in am.PARAMETRIC_TAPER_WINDOWS,
        },
        "count_label": "Columns" if is_hybrid else "Pairs" if topo == GRADIENT else "Subs",
        "count_max": _max_count(topo),
        "topology_note": topology_note(state),
        "speed_text": f"c = {c:.2f} m/s",
        "group_distance_m": round(am.distance_for_delay_ms(state["group"]["delay_ms"], c), 3),
        "collision_text": _collision_text(state),
        "venue": _venue_view(state),
        "alignment": _alignment_view(state),
        "bounce_text": _bounce_text(state),
        "info": _info_view(state),
        "prealign": _prealign_view(state),
        "profiles": list(_PROFILES),
        "error": None,
    }
    v.update(_wavelength_view(state))
    far = am.forward_aspect_ratio(arr["angle_deg"])
    v["far_text"] = f"FAR: {far:.2f}" if far is not None else "FAR: ∞"

    makeup = state["group"]["makeup_db"]
    v["makeup_text"] = ("" if abs(makeup) < 0.005 else
                        f"includes {'+' if makeup >= 0 else ''}{makeup:.2f} dB makeup in Group level")

    try:
        trims, onaxis, power = _taper(state)
        v["taper_cost_text"] = ("taper cost: -" if onaxis is None else
                                f"taper cost: {onaxis:.2f} dB on-axis, {power:.2f} dB total power (vs. uniform)")
        subs = compute(state, trims)
        v["table"] = _table(state, subs, trims)
    except (ValueError, IndexError) as e:
        v["taper_cost_text"] = "taper cost: -"
        v["table"] = {"unit": "ms", "editable": topo == MANUAL, "rows": []}
        v["error"] = str(e)
    return v


# --------------------------------------------------------------- .sadrt --
def to_project(state):
    """project_io.build_project_dict."""
    data = {k: copy.deepcopy(v) for k, v in state.items() if k != "ui"}
    pre = data["group"]["prealign"]
    if not pre["active"]:
        pre["main_system"] = pre["sub_system"] = ""
    data["osc"]["live_send"] = False
    rows = len(state["manual"]["x_m"])
    for key in ("x_m", "y_m", "gain_db", "reversed"):
        data["manual"][key] = list(state["manual"][key][:rows])
    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **data,
    }


def _clamp(value, lo, hi, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default, "invalid"
    if not math.isfinite(value):
        return default, "invalid"
    if value < lo or value > hi:
        return max(lo, min(hi, value)), "clamped"
    return value, None


def _clamp_warning(label, problem, value):
    if problem == "clamped":
        return f"{label} out of range -- clamped to {value}."
    if problem == "invalid":
        return f"{label} isn't a valid number -- kept current value ({value})."
    return None


def from_project(state, data):
    """project_io.apply_project_dict: returns (new_state, warnings). Same
    tolerant rules and warning text as the desktop."""
    s = copy.deepcopy(state)
    warnings = []
    if not isinstance(data, dict):
        raise ValueError("not a project file (expected a JSON object)")

    def section(key):
        v = data.get(key)
        return v if isinstance(v, dict) else {}

    schema_version = data.get("schema_version")
    if isinstance(schema_version, int) and schema_version > SCHEMA_VERSION:
        warnings.append(
            f"File was saved with a newer project format (schema {schema_version}, "
            f"this app understands {SCHEMA_VERSION}) -- some settings may not load.")

    s["name"] = str(data.get("name", ""))

    arr_in, arr = section("array"), s["array"]
    topo_key = arr_in.get("topology", "arc_steering")
    if topo_key not in TOPOLOGY_LABELS:
        warnings.append(f"Unknown topology '{topo_key}' -- kept current topology.")
        topo_key = arr["topology"]
    arr["topology"] = topo_key

    file_count = None
    try:
        raw_count = int(arr_in.get("count", arr["count"]))
    except (TypeError, ValueError):
        warnings.append("Invalid sub count -- kept current value.")
    else:
        arr["count"] = max(1, min(MAX_SUBS_SPATIAL, raw_count))
        if arr_in.get("count") is not None:
            file_count = raw_count

    for key, lo, hi in (
        ("spacing_m", 0.001, 100000.0), ("row_spacing_m", 0.001, 100000.0), ("angle_deg", 0.0, 180.0),
        ("radius_m", 0.001, 100000.0), ("steer_deg", -90.0, 90.0), ("ellipse_ratio", 0.05, 2.0),
        ("progression_ratio", 1.0, 8.0), ("focus_x_m", -100000.0, 100000.0),
        ("focus_y_m", -100000.0, 100000.0), ("avoid_x_m", -100000.0, 100000.0),
        ("avoid_y_m", -100000.0, 100000.0), ("gradient_alpha", 0.0, 0.9),
    ):
        if key in arr_in:
            value, problem = _clamp(arr_in[key], lo, hi, arr[key])
            arr[key] = value
            if problem:
                warnings.append(_clamp_warning(f"'{key}'", problem, value))

    pattern = arr_in.get("gradient_pattern", arr["gradient_pattern"])
    arr["gradient_pattern"] = pattern if pattern in GRADIENT_PATTERNS else CUSTOM_PROFILE
    _sync_null_angle_from_alpha(s)

    shape = arr_in.get("shape", "circle")
    if shape not in ("circle", "ellipse"):
        warnings.append(f"Unknown Physical Horizontal Array shape '{shape}' -- kept current shape.")
        shape = arr["shape"]
    arr["shape"] = shape

    _on_topology_change(s)
    if file_count is not None and arr["count"] != file_count:
        warnings.append(
            f"Sub count {file_count} in the file isn't possible for this topology -- using {arr['count']}.")

    taper_in, taper = section("level_taper"), s["level_taper"]
    window = taper_in.get("window", taper["window"])
    if window not in am.LEVEL_TAPER_WINDOWS:
        warnings.append(f"Unknown level taper window '{window}' -- kept current window.")
        window = taper["window"]
    taper["window"] = window
    for key, lo, hi, label in (("max_atten_db", 0.0, 30.0, "Level taper max atten"),
                               ("sidelobe_db", 10.0, 100.0, "Level taper sidelobe level")):
        if key in taper_in:
            value, problem = _clamp(taper_in[key], lo, hi, taper[key])
            taper[key] = value
            if problem:
                warnings.append(_clamp_warning(label, problem, value))

    units_in, units = section("units"), s["units"]
    unit = units_in.get("length_unit", units["length_unit"])
    if unit not in UNITS:
        warnings.append(f"Unknown length unit '{unit}' -- kept current unit.")
        unit = units["length_unit"]
    units["length_unit"] = unit
    delay_display = units_in.get("delay_display", units["delay_display"])
    if delay_display not in ("ms", "samples"):
        warnings.append(f"Unknown delay display '{delay_display}' -- kept current.")
        delay_display = units["delay_display"]
    units["delay_display"] = delay_display
    xy = units_in.get("xy_convention", units["xy_convention"])
    if xy not in XY_CONVENTIONS:
        warnings.append(f"Unknown X/Y convention '{xy}' -- kept current.")
        xy = units["xy_convention"]
    units["xy_convention"] = xy

    dsp = section("dsp")
    if "sample_rate_hz" in dsp:
        rate = dsp["sample_rate_hz"]
        if rate in DSP_CLOCK_RATES.values() and not isinstance(rate, bool):
            s["dsp"]["sample_rate_hz"] = int(rate)
        else:
            warnings.append(f"Unknown DSP sample rate {rate} Hz -- kept current clock.")

    env_in, env = section("environment"), s["environment"]
    for key, lo, hi in (("temp_c", -50.0, 60.0), ("humidity_pct", 0.0, 100.0), ("altitude_m", 0.0, 9000.0)):
        if key in env_in:
            value, problem = _clamp(env_in[key], lo, hi, env[key])
            env[key] = value
            if problem:
                warnings.append(_clamp_warning(f"'{key}'", problem, value))

    group_in, group = section("group"), s["group"]
    if "delay_ms" in group_in:
        try:
            group["delay_ms"] = float(group_in["delay_ms"])
        except (TypeError, ValueError):
            warnings.append("Invalid group delay -- kept current value.")
    group["inverted"] = bool(group_in.get("inverted"))
    if "level_db" in group_in:
        value, problem = _clamp(group_in["level_db"], -40.0, 18.0, group["level_db"])
        group["level_db"] = value
        if problem:
            warnings.append(_clamp_warning("Group level", problem, value))
    try:
        group["makeup_db"] = float(group_in.get("makeup_db", 0.0))
    except (TypeError, ValueError):
        group["makeup_db"] = 0.0
    s["ui"]["makeup_group_level"] = group["level_db"]

    pre_in = group_in.get("prealign") if isinstance(group_in.get("prealign"), dict) else {}
    pre = group["prealign"]
    pre["active"] = bool(pre_in.get("active", False))
    try:
        pre["contribution_ms"] = float(pre_in.get("contribution_ms", 0.0))
    except (TypeError, ValueError):
        pre["contribution_ms"] = 0.0
    main_system = pre_in.get("main_system", "")
    sub_system = pre_in.get("sub_system", "")
    if not isinstance(main_system, str):
        main_system = ""
    if not isinstance(sub_system, str):
        sub_system = ""
    pre["main_system"], pre["sub_system"] = (main_system, sub_system) if pre["active"] else ("", "")
    if pre["active"] and main_system:
        if any(e[0] == main_system for e in _PREALIGN_ENTRIES):
            s["ui"]["prealign_main"] = main_system
            subs = _prealign_subs_for_main(main_system)
            s["ui"]["prealign_sub"] = subs[0][1] if subs else ""
            if any(e[1] == sub_system for e in subs):
                s["ui"]["prealign_sub"] = sub_system
        entry = _prealign_entry(main_system, sub_system)
        if entry is not None and s["ui"]["prealign_main"] == main_system and s["ui"]["prealign_sub"] == sub_system:
            _set_prealign_note(s, main_system, sub_system, entry[2], entry[5])
        else:
            warnings.append(
                f"Pre-align preset '{main_system}' + '{sub_system}' no longer found -- "
                "delay value kept, but the panel can't show its detail.")
            c = pre["contribution_ms"]
            sign = "+" if c >= 0 else ""
            s["ui"]["prealign_note"] = (f"includes {sign}{c:.2f} ms pre-alignment "
                                        f"({main_system} + {sub_system}) [preset not found]")
    else:
        s["ui"]["prealign_note"] = ""

    box_in, box = section("sub_box"), s["sub_box"]
    for key, label in (("width_m", "sub box width"), ("depth_m", "sub box depth"), ("gap_m", "cabinet gap")):
        if key in box_in:
            try:
                box[key] = float(box_in[key])
            except (TypeError, ValueError):
                warnings.append(f"Invalid {label} -- kept current value.")
    profile = box_in.get("profile", "")
    box["profile"] = profile if profile in _PROFILES else CUSTOM_PROFILE
    ac_in = box_in.get("acoustic_center") if isinstance(box_in.get("acoustic_center"), dict) else {}
    if "enabled" in ac_in:
        box["acoustic_center"]["enabled"] = bool(ac_in["enabled"])
    if "offset_m" in ac_in:
        try:
            box["acoustic_center"]["offset_m"] = float(ac_in["offset_m"])
        except (TypeError, ValueError):
            warnings.append("Invalid acoustic centre offset -- kept current value.")

    venue_in = section("venue")
    for key, label in (("length_m", "venue length"), ("width_m", "venue width")):
        if key in venue_in:
            try:
                s["venue"][key] = float(venue_in[key])
            except (TypeError, ValueError):
                warnings.append(f"Invalid {label} -- kept current value.")

    bw_in = section("bandwidth")
    if "freq_high_hz" in bw_in:
        value, problem = _clamp(bw_in["freq_high_hz"], 1.0, 20000.0, s["bandwidth"]["freq_high_hz"])
        s["bandwidth"]["freq_high_hz"] = value
        if problem:
            warnings.append(_clamp_warning("Sub bandwidth high frequency", problem, value))

    align_in = section("alignment_wizard")
    for key in ("mains_distance_m", "mains_delay_ms", "sub_distance_m"):
        if key in align_in:
            try:
                s["alignment_wizard"][key] = float(align_in[key])
            except (TypeError, ValueError):
                warnings.append(f"Invalid alignment wizard '{key}' -- kept current value.")

    bounce_in = section("floor_bounce")
    for key in ("source_height_m", "mic_distance_m", "mic_height_m"):
        if key in bounce_in:
            value, problem = _clamp(bounce_in[key], 0.0, 100000.0, s["floor_bounce"][key])
            s["floor_bounce"][key] = value
            if problem:
                warnings.append(_clamp_warning(f"Floor bounce '{key}'", problem, value))

    osc_in = section("osc")
    if "host" in osc_in:
        s["osc"]["host"] = str(osc_in["host"])
    if "port" in osc_in:
        try:
            s["osc"]["port"] = int(osc_in["port"])
        except (TypeError, ValueError):
            warnings.append("Invalid OSC port -- kept current value.")
    if "prefix" in osc_in:
        s["osc"]["prefix"] = str(osc_in["prefix"])
    s["osc"]["live_send"] = False

    manual_in = section("manual")
    rows = len(s["manual"]["x_m"])
    s["manual"] = {"x_m": [0.0] * rows, "y_m": [0.0] * rows, "gain_db": [0.0] * rows, "reversed": [False] * rows}
    for key in ("x_m", "y_m", "gain_db"):
        values = manual_in.get(key)
        if isinstance(values, list):
            for i in range(min(rows, len(values))):
                try:
                    s["manual"][key][i] = float(values[i])
                except (TypeError, ValueError):
                    pass
    rev = manual_in.get("reversed")
    if isinstance(rev, list):
        for i in range(min(rows, len(rev))):
            s["manual"]["reversed"][i] = bool(rev[i])

    _drop_stale_makeup(s)
    return s, warnings


# ------------------------------------------------------------ JS entry --
def _response(state, extra=None):
    out = {"state": state, "view": view(state)}
    if extra:
        out.update(extra)
    return json.dumps(out, allow_nan=False)


def init():
    return _response(default_state(), {"topologies": TOPOLOGY_LABELS, "windows": am.LEVEL_TAPER_WINDOWS,
                                       "patterns": GRADIENT_PATTERNS, "custom": CUSTOM_PROFILE,
                                       "dsp_rates": DSP_CLOCK_RATES, "xy_conventions": XY_CONVENTIONS})


def dispatch(state_json, action_json):
    state, msg = apply_action(json.loads(state_json), json.loads(action_json))
    return _response(state, {"message": msg})


def save(state_json):
    return json.dumps(to_project(json.loads(state_json)), indent=2, allow_nan=False)


def load(state_json, file_text):
    try:
        data = json.loads(file_text)
        state, warnings = from_project(json.loads(state_json), data)
    except (ValueError, TypeError) as e:
        return json.dumps({"error": f"Couldn't read project file: {e}"})
    return _response(state, {"warnings": warnings})
