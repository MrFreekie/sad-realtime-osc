"""Save/load S.A.D. Realtime project files (.sadrt -- plain JSON).

Everything is stored in canonical SI units (metres, ms, dB, Hz, degC),
same as the app computes internally, regardless of the display unit the
user has selected. Enum-like fields (topology, DSP clock, group polarity)
are stored as stable internal keys rather than the UI's display strings,
so relabeling a combobox in a future version can't break old save files.

Every field is read with .get(..., default) so a file from an older app
version (missing newer keys) loads with today's defaults for whatever
it doesn't have, and a file from a newer app version (extra keys we
don't recognize yet) simply has those keys ignored. Unrecognized enum
values and out-of-range numbers fall back to a default rather than
raising -- apply_project_dict returns a list of warnings for anything
that didn't load cleanly instead of crashing or losing the caller's
current state.
"""
import json
from datetime import datetime, timezone

SCHEMA_VERSION = 1
FILE_EXTENSION = ".sadrt"

# TOPOLOGIES / TOPO_* constants live in sad_realtime_osc.py, which imports
# this module -- importing them back here would be circular, so topology
# key mapping is built from the same literal display strings, passed in by
# the caller (build_project_dict / apply_project_dict take the app, which
# already holds these strings on its widgets/vars).
_TOPOLOGY_KEYS = {
    "End-Fire": "end_fire",
    "Gradient / Cardioid Pairs": "gradient_cardioid",
    "Physical Horizontal Array": "physical_horizontal",
    "Arc / Broadside Steering": "arc_steering",
    "End-Fire Arc Hybrid": "end_fire_arc_hybrid",
    "Gradient Arc Hybrid": "gradient_arc_hybrid",
    "Progressive Arc": "progressive_arc",
    "Focus Point": "focus_point",
    "Manual": "manual",
}
_TOPOLOGY_FROM_KEY = {v: k for k, v in _TOPOLOGY_KEYS.items()}


def _clamp(value, lo, hi, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default, True
    if value < lo or value > hi:
        return max(lo, min(hi, value)), True
    return value, False


def build_project_dict(app) -> dict:
    from sad_realtime_osc import __version__
    n = len(app.manual_x_vars)

    return {
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name": app.project_name.get(),
        "array": {
            "topology": _TOPOLOGY_KEYS.get(app.topology.get(), "arc_steering"),
            "count": app.count.get(),
            "spacing_m": app.spacing.get(),
            "row_spacing_m": app.row_spacing.get(),
            "angle_deg": app.angle.get(),
            "radius_m": app.radius.get(),
            "steer_deg": app.steer.get(),
            "shape": "ellipse" if app.shape.get() == "Ellipse" else "circle",
            "ellipse_ratio": app.ellipse_ratio.get(),
            "progression_ratio": app.progression_ratio.get(),
            "focus_x_m": app.focus_x.get(),
            "focus_y_m": app.focus_y.get(),
        },
        "level_taper": {
            "window": app.taper_window.get(),
            "max_atten_db": app.taper_max_atten.get(),
        },
        "units": {
            "length_unit": app.unit.get(),
            "delay_display": app.delay_unit.get(),
        },
        "dsp": {
            "sample_rate_hz": app._dsp_sample_rate(),
        },
        "environment": {
            "temp_c": app.temp_c.get(),
            "humidity_pct": app.humidity.get(),
            "altitude_m": app.altitude.get(),
        },
        "group": {
            "delay_ms": app.group_delay.get(),
            "inverted": app._group_inverted(),
            "level_db": app.group_level.get(),
            "prealign": {
                "active": app.prealign_active,
                "contribution_ms": app.prealign_contribution_ms,
                "main_system": app.prealign_main.get() if app.prealign_active and hasattr(app, "prealign_main") else "",
                "sub_system": app.prealign_sub.get() if app.prealign_active and hasattr(app, "prealign_main") else "",
            },
        },
        "sub_box": {
            "profile": app.sub_profile.get(),
            "width_m": app.box_width.get(),
            "depth_m": app.box_depth.get(),
            "gap_m": app.cabinet_gap.get(),
            "acoustic_center": {
                "enabled": app.acoustic_center_enabled.get(),
                "offset_m": app.acoustic_center_offset.get(),
            },
        },
        "venue": {
            "length_m": app.venue_length.get(),
            "width_m": app.venue_width.get(),
        },
        "bandwidth": {
            "freq_high_hz": app.freq_high.get(),
        },
        "alignment_wizard": {
            "mains_distance_m": app.align_mains_distance.get(),
            "mains_delay_ms": app.align_mains_delay.get(),
            "sub_distance_m": app.align_sub_distance.get(),
        },
        "osc": {
            "host": app.osc_host.get(),
            "port": app.osc_port.get(),
            "prefix": app.osc_prefix.get(),
            "live_send": app.live_send.get(),
        },
        "manual": {
            "x_m": [v.get() for v in app.manual_x_vars[:n]],
            "y_m": [v.get() for v in app.manual_y_vars[:n]],
            "gain_db": [v.get() for v in app.manual_gain_vars[:n]],
            "reversed": [v.get() for v in app.manual_pol_vars[:n]],
        },
    }


def default_project_dict() -> dict:
    """Factory defaults for a fresh project -- the same values `App.__init__`
    and its panel builders set up on first launch. Used by the "New" button
    (fed through apply_project_dict, same as loading a file) so a full reset
    goes through one tolerant code path instead of a second reset
    implementation that could drift out of sync with it."""
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "",
        "array": {
            "topology": "arc_steering",
            "count": 6,
            "spacing_m": 1.4,
            "row_spacing_m": 0.7,
            "angle_deg": 0.0,
            "radius_m": 2.0,
            "steer_deg": 0.0,
            "shape": "circle",
            "ellipse_ratio": 1.0,
            "progression_ratio": 1.0,
            "focus_x_m": 10.0,
            "focus_y_m": 0.0,
        },
        "level_taper": {"window": "Uniform", "max_atten_db": 0.0},
        "units": {"length_unit": "m", "delay_display": "ms"},
        "dsp": {"sample_rate_hz": 96000},
        "environment": {"temp_c": 20.0, "humidity_pct": 50.0, "altitude_m": 0.0},
        "group": {
            "delay_ms": 0.0,
            "inverted": False,
            "level_db": 0.0,
            "prealign": {"active": False, "contribution_ms": 0.0, "main_system": "", "sub_system": ""},
        },
        "sub_box": {
            "profile": "L-Acoustics KS28 (Horizontal)",
            "width_m": 1.340,
            "depth_m": 0.702,
            "gap_m": 0.0,
            "acoustic_center": {"enabled": False, "offset_m": 0.30},
        },
        "venue": {"length_m": 50.0, "width_m": 25.0},
        "bandwidth": {"freq_high_hz": 60.0},
        "alignment_wizard": {"mains_distance_m": 0.0, "mains_delay_ms": 0.0, "sub_distance_m": 0.0},
        "osc": {"host": "127.0.0.1", "port": 5000, "prefix": "/sad/sub", "live_send": False},
        "manual": {"x_m": [], "y_m": [], "gain_db": [], "reversed": []},
    }


def save_project(app, path) -> None:
    data = build_project_dict(app)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_project(path) -> dict:
    """Reads and JSON-parses the file. Raises OSError/json.JSONDecodeError
    on failure -- the caller shows those to the user without touching the
    app's current state, since a failed load shouldn't discard what's
    already on screen."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def apply_project_dict(app, data: dict) -> list[str]:
    """Pushes `data` into the app's widgets/vars, clamping and falling back
    to current defaults for anything missing, unrecognized, or out of
    range. Returns a list of human-readable warnings (empty if everything
    matched cleanly). Never raises for a malformed-but-parseable dict --
    that's the whole point of a tolerant load path."""
    warnings = []

    def section(key):
        v = data.get(key)
        return v if isinstance(v, dict) else {}

    schema_version = data.get("schema_version")
    if isinstance(schema_version, int) and schema_version > SCHEMA_VERSION:
        warnings.append(
            f"File was saved with a newer project format (schema {schema_version}, "
            f"this app understands {SCHEMA_VERSION}) -- some settings may not load.")

    app.project_name.set(str(data.get("name", "")))

    array = section("array")
    topo_key = array.get("topology", "arc_steering")
    topo_label = _TOPOLOGY_FROM_KEY.get(topo_key)
    if topo_label is None:
        warnings.append(f"Unknown topology '{topo_key}' -- kept current topology.")
        topo_label = app.topology.get()
    app.topology.set(topo_label)

    try:
        app.count.set(int(array.get("count", app.count.get())))
    except (TypeError, ValueError):
        warnings.append("Invalid sub count -- kept current value.")

    for var, key, lo, hi in (
        (app.spacing, "spacing_m", 0.001, 100000.0),
        (app.row_spacing, "row_spacing_m", 0.001, 100000.0),
        (app.angle, "angle_deg", 0.0, 180.0),
        (app.radius, "radius_m", 0.001, 100000.0),
        (app.steer, "steer_deg", -90.0, 90.0),
        (app.ellipse_ratio, "ellipse_ratio", 0.05, 2.0),
        (app.progression_ratio, "progression_ratio", 1.0, 8.0),
        (app.focus_x, "focus_x_m", -100000.0, 100000.0),
        (app.focus_y, "focus_y_m", -100000.0, 100000.0),
    ):
        if key in array:
            value, clamped = _clamp(array[key], lo, hi, var.get())
            var.set(value)
            if clamped:
                warnings.append(f"'{key}' out of range -- clamped to {value}.")

    shape = array.get("shape", "circle")
    if shape not in ("circle", "ellipse"):
        warnings.append(f"Unknown Physical Horizontal Array shape '{shape}' -- kept current shape.")
        shape = "circle" if app.shape.get() == "Circle" else "ellipse"
    app.shape.set("Ellipse" if shape == "ellipse" else "Circle")

    # Rebuild the per-sub rows for the newly-set topology/count *before*
    # restoring manual per-sub data below, since _on_topology_change wipes
    # and resizes manual_x_vars/manual_y_vars/etc. to match.
    app._on_topology_change()
    if array.get("count") is not None and app.count.get() != array.get("count"):
        warnings.append(
            f"Sub count clamped to {app.count.get()} (max for this topology).")

    taper = section("level_taper")
    from array_math import LEVEL_TAPER_WINDOWS
    window = taper.get("window", app.taper_window.get())
    if window not in LEVEL_TAPER_WINDOWS:
        warnings.append(f"Unknown level taper window '{window}' -- kept current window.")
        window = app.taper_window.get()
    app.taper_window.set(window)
    if "max_atten_db" in taper:
        value, clamped = _clamp(taper["max_atten_db"], 0.0, 30.0, app.taper_max_atten.get())
        app.taper_max_atten.set(value)
        if clamped:
            warnings.append("Level taper max atten out of range -- clamped.")

    units = section("units")
    unit = units.get("length_unit", app.unit.get())
    if unit not in ("m", "cm", "mm"):
        warnings.append(f"Unknown length unit '{unit}' -- kept current unit.")
        unit = app.unit.get()
    app.unit.set(unit)
    delay_display = units.get("delay_display", app.delay_unit.get())
    if delay_display not in ("ms", "samples"):
        warnings.append(f"Unknown delay display '{delay_display}' -- kept current.")
        delay_display = app.delay_unit.get()
    app.delay_unit.set(delay_display)

    dsp = section("dsp")
    if "sample_rate_hz" in dsp:
        from sad_realtime_osc import DSP_CLOCK_RATES
        rate = dsp["sample_rate_hz"]
        match = next((label for label, hz in DSP_CLOCK_RATES.items() if hz == rate), None)
        if match is None:
            warnings.append(f"Unknown DSP sample rate {rate} Hz -- kept current clock.")
        else:
            app.dsp_clock.set(match)

    env = section("environment")
    for var, key, lo, hi in (
        (app.temp_c, "temp_c", -50.0, 60.0),
        (app.humidity, "humidity_pct", 0.0, 100.0),
        (app.altitude, "altitude_m", 0.0, 9000.0),
    ):
        if key in env:
            value, clamped = _clamp(env[key], lo, hi, var.get())
            var.set(value)
            if clamped:
                warnings.append(f"'{key}' out of range -- clamped to {value}.")

    group = section("group")
    if "delay_ms" in group:
        try:
            app.group_delay.set(float(group["delay_ms"]))
        except (TypeError, ValueError):
            warnings.append("Invalid group delay -- kept current value.")
    app.group_polarity.set("Inverted" if group.get("inverted") else "Normal")
    if "level_db" in group:
        value, clamped = _clamp(group["level_db"], -40.0, 18.0, app.group_level.get())
        app.group_level.set(value)
        if clamped:
            warnings.append("Group level out of range -- clamped.")

    prealign = group.get("prealign") if isinstance(group.get("prealign"), dict) else {}
    app.prealign_active = bool(prealign.get("active", False))
    try:
        app.prealign_contribution_ms = float(prealign.get("contribution_ms", 0.0))
    except (TypeError, ValueError):
        app.prealign_contribution_ms = 0.0
    main_system = prealign.get("main_system", "")
    sub_system = prealign.get("sub_system", "")
    if app.prealign_active and main_system:
        found_entry = None
        if hasattr(app, "prealign_main"):
            entries = getattr(app, "prealign_entries", [])
            if any(e[0] == main_system for e in entries):
                app.prealign_main.set(main_system)
                app._on_prealign_main_change()
                if any(e[0] == main_system and e[1] == sub_system for e in entries):
                    app.prealign_sub.set(sub_system)
            app._update_prealign_readout()
            entry = app._current_prealign_entry()
            if entry is not None and entry[0] == main_system and entry[1] == sub_system:
                found_entry = entry
        if found_entry is not None:
            _, _, main_ms, _sub_ms, _main_pol, sub_pol, *_ = found_entry
            app._set_prealign_note(main_system, sub_system, main_ms, sub_pol)
        else:
            warnings.append(
                f"Pre-align preset '{main_system}' + '{sub_system}' no longer found -- "
                "delay value kept, but the panel can't show its detail.")
            sign = "+" if app.prealign_contribution_ms >= 0 else ""
            app.prealign_note_var.set(
                f"includes {sign}{app.prealign_contribution_ms:.2f} ms pre-alignment "
                f"({main_system} + {sub_system}) [preset not found]")
    else:
        app.prealign_note_var.set("")

    sub_box = section("sub_box")
    if "width_m" in sub_box:
        try:
            app.box_width.set(float(sub_box["width_m"]))
        except (TypeError, ValueError):
            warnings.append("Invalid sub box width -- kept current value.")
    if "depth_m" in sub_box:
        try:
            app.box_depth.set(float(sub_box["depth_m"]))
        except (TypeError, ValueError):
            warnings.append("Invalid sub box depth -- kept current value.")
    if "gap_m" in sub_box:
        try:
            app.cabinet_gap.set(float(sub_box["gap_m"]))
        except (TypeError, ValueError):
            warnings.append("Invalid cabinet gap -- kept current value.")
    profile = sub_box.get("profile", "")
    from sad_realtime_osc import CUSTOM_PROFILE
    app.sub_profile.set(profile if profile in app.sub_profiles else CUSTOM_PROFILE)
    ac = sub_box.get("acoustic_center") if isinstance(sub_box.get("acoustic_center"), dict) else {}
    if "enabled" in ac:
        app.acoustic_center_enabled.set(bool(ac["enabled"]))
    if "offset_m" in ac:
        try:
            app.acoustic_center_offset.set(float(ac["offset_m"]))
        except (TypeError, ValueError):
            warnings.append("Invalid acoustic centre offset -- kept current value.")

    venue = section("venue")
    if "length_m" in venue:
        try:
            app.venue_length.set(float(venue["length_m"]))
        except (TypeError, ValueError):
            warnings.append("Invalid venue length -- kept current value.")
    if "width_m" in venue:
        try:
            app.venue_width.set(float(venue["width_m"]))
        except (TypeError, ValueError):
            warnings.append("Invalid venue width -- kept current value.")

    bandwidth = section("bandwidth")
    if "freq_high_hz" in bandwidth:
        value, clamped = _clamp(bandwidth["freq_high_hz"], 1.0, 20000.0, app.freq_high.get())
        app.freq_high.set(value)
        if clamped:
            warnings.append("Sub bandwidth high frequency out of range -- clamped.")

    align = section("alignment_wizard")
    for var, key in (
        (app.align_mains_distance, "mains_distance_m"),
        (app.align_mains_delay, "mains_delay_ms"),
        (app.align_sub_distance, "sub_distance_m"),
    ):
        if key in align:
            try:
                var.set(float(align[key]))
            except (TypeError, ValueError):
                warnings.append(f"Invalid alignment wizard '{key}' -- kept current value.")

    osc = section("osc")
    if "host" in osc:
        app.osc_host.set(str(osc["host"]))
    if "port" in osc:
        try:
            app.osc_port.set(int(osc["port"]))
        except (TypeError, ValueError):
            warnings.append("Invalid OSC port -- kept current value.")
    if "prefix" in osc:
        app.osc_prefix.set(str(osc["prefix"]))
    # Live send is deliberately never restored from a file -- a loaded
    # project could be from a different venue/network, and auto-streaming
    # OSC to a stale host on open is a live-show footgun. Always starts
    # off; re-enable by hand once the OSC panel is verified.
    app.live_send.set(False)

    manual = section("manual")
    n = len(app.manual_x_vars)
    for vars_list, key, clamp_range in (
        (app.manual_x_vars, "x_m", None),
        (app.manual_y_vars, "y_m", None),
        (app.manual_gain_vars, "gain_db", None),
    ):
        values = manual.get(key)
        if isinstance(values, list):
            for i in range(min(n, len(values))):
                try:
                    vars_list[i].set(float(values[i]))
                except (TypeError, ValueError):
                    pass
    reversed_values = manual.get("reversed")
    if isinstance(reversed_values, list):
        for i in range(min(n, len(reversed_values))):
            app.manual_pol_vars[i].set(bool(reversed_values[i]))

    app._refresh_unit_displays()
    app._update_venue_far()
    app._on_change()
    app._fit_window_height()

    return warnings
