"""Cross-check the web app's model (web/py/model.py) against the real
desktop app (realtime_app/sad_realtime_osc.py), headlessly.

For each scenario, both apps get the same settings and the same button
presses; then every per-sub table value and every readout label the
desktop shows is compared with the web model's view, and both apps'
saved .sadrt files are compared too (so files round-trip both ways).

Run from the repo root (needs Tk, i.e. a desktop session):
    python tests/check_web_model.py

There are no known differences: the three desktop quirks this check first
found (Gain Trim column, "-0.00" readouts, pre-align preset relabelled on
save) were fixed in the desktop app, so everything is compared exactly.
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "realtime_app"))
sys.path.insert(0, os.path.join(ROOT, "web", "py"))

import sad_realtime_osc as desk  # noqa: E402  (adds shared/ to sys.path)
import project_io  # noqa: E402
import model  # noqa: E402

failures = []


def check(scenario, what, desktop, web):
    if desktop != web:
        failures.append(f"[{scenario}] {what}:\n      desktop: {desktop!r}\n      web:     {web!r}")


def text(widget):
    return widget.cget("text")


def compare_views(name, app, state):
    app.update_idletasks()
    v = model.view(state)
    topo = state["array"]["topology"]
    show = v["show"]

    check(name, "count label", text(app.count_label), v["count_label"])
    check(name, "topology note", app.topology_note_icon.tooltip.text, v["topology_note"])
    check(name, "speed", text(app.speed_of_sound_label), v["speed_text"])
    check(name, "collision", text(app.collision_label), v["collision_text"])
    check(name, "alignment corrected", text(app.align_corrected_label), v["alignment"]["corrected_text"])
    check(name, "alignment result", text(app.align_result_label), v["alignment"]["result_text"])
    check(name, "floor bounce", text(app.bounce_result_label), v["bounce_text"])
    check(name, "group distance", round(app.group_delay_m.get(), 3), v["group_distance_m"])
    check(name, "makeup note", app.makeup_note_var.get(), v["makeup_text"])
    check(name, "prealign note", app.prealign_note_var.get(), state["ui"]["prealign_note"])
    check(name, "venue FAR", text(app.venue_far_label), v["venue"]["far_text"])
    check(name, "set arc enabled", str(app.set_arc_btn.cget("state")) == "normal", v["venue"]["can_set_arc"])
    if show["ellipse"]:
        check(name, "venue ellipse", text(app.venue_ellipse_label), v["venue"]["ellipse_text"])
    check(name, "wavelength", text(app.wavelength_label), v["wavelength_text"])
    check(name, "optimum", text(app.optimum_label), v["optimum_text"])
    if show["row_spacing"]:
        check(name, "row wavelength", text(app.row_wavelength_label), v["row_wavelength_text"])
        check(name, "row optimum", text(app.row_optimum_label), v["row_optimum_text"])
    if show["steer"]:
        check(name, "grating lobe", text(app.grating_lobe_label), v["grating_lobe_text"])
    if show["angle"]:
        check(name, "FAR", text(app.far_label), v["far_text"])
    if show["taper"]:
        check(name, "taper cost", text(app.taper_cost_label), v["taper_cost_text"])
    info = v["info"]
    for label, key in ((app.info_length_label, "length_text"), (app.info_1l_label, "one_lambda_text"),
                       (app.info_180_label, "d180_text"), (app.info_240_label, "d240_text"),
                       (app.info_360_label, "d360_text"), (app.info_virtual_label, "virtual_text")):
        check(name, key, text(label), info[key])
    if v["prealign"].get("main_text"):
        check(name, "prealign main", text(app.prealign_main_label), v["prealign"]["main_text"])
        check(name, "prealign sub", text(app.prealign_sub_label), v["prealign"]["sub_text"])
    check(name, "null angle", round(app.null_angle.get(), 4), round(state["ui"]["null_angle_deg"], 4))

    # Per-sub table
    subs = app._compute()
    rows = v["table"]["rows"]
    check(name, "error", subs is None, v["error"] is not None)
    if subs is None:
        return
    check(name, "row count", len(subs), len(rows))
    is_manual = topo == model.MANUAL
    for i, (s, r) in enumerate(zip(subs, rows)):
        t = r["text"]
        if not is_manual:
            check(name, f"sub {i+1} Y", text(app.y_labels[i]), t["y"])
            check(name, f"sub {i+1} X", text(app.x_labels[i]), t["x"])
            check(name, f"sub {i+1} polarity", text(app.pol_widgets[i]), t["polarity"])
            check(name, f"sub {i+1} gain trim", text(app.gain_widgets[i]), t["gain"])
        check(name, f"sub {i+1} rotation", text(app.rotation_labels[i]), t["rotation"])
        check(name, f"sub {i+1} delay", text(app.delay_labels[i]), t["delay"])
        check(name, f"sub {i+1} delay+group", text(app.total_delay_labels[i]), t["delay_total"])
        check(name, f"sub {i+1} gain+group", text(app.total_gain_labels[i]), t["gain_total"])
        check(name, f"sub {i+1} gain (math)", f"{s.gain_db + 0.0:.2f}", t["gain"])
        check(name, f"sub {i+1} delay ms (exact)", s.delay_ms, r["delay_ms"])


def comparable(project):
    p = copy.deepcopy(project)
    for key in ("saved_at", "app_version"):
        p.pop(key, None)
    return json.loads(json.dumps(p))


def compare_files(name, app, state):
    check(name, ".sadrt contents", comparable(project_io.build_project_dict(app)),
          comparable(model.to_project(state)))


def load_into_desktop(app, state):
    warnings = project_io.apply_project_dict(app, model.to_project(state))
    # The web model's transient prealign selection isn't in the file; mirror it.
    if hasattr(app, "prealign_main") and state["ui"]["prealign_main"]:
        app.prealign_main.set(state["ui"]["prealign_main"])
        app._on_prealign_main_change()
        app.prealign_sub.set(state["ui"]["prealign_sub"])
        app._update_prealign_readout()
    return warnings


def run(state, actions):
    for a in actions:
        state, _ = model.apply_action(state, a)
    return state


def S(path, value):
    return {"type": "set", "path": path, "value": value}


# --- scenarios: settings only (pushed to the desktop via its own loader) ---
SETTINGS = []
for topo in model.TOPOLOGY_LABELS:
    for count in (1, 2, 5, 8):
        SETTINGS.append((f"{topo} n={count}", [S("array.topology", topo), S("array.count", count),
                                                S("array.angle_deg", 75), S("array.steer_deg", 12)]))
for topo in model.ELLIPSE_TOPOLOGIES:
    SETTINGS.append((f"{topo} ellipse", [S("array.topology", topo), S("array.shape", "ellipse"),
                                         S("array.ellipse_ratio", 0.6), S("array.angle_deg", 140),
                                         S("venue.width_m", 60)]))
for window in model.am.LEVEL_TAPER_WINDOWS:
    SETTINGS.append((f"taper {window}", [S("array.topology", "arc_steering"), S("array.count", 9),
                                         S("array.angle_deg", 90), S("array.steer_deg", -20),
                                         S("level_taper.window", window), S("level_taper.max_atten_db", 9),
                                         S("level_taper.sidelobe_db", 35)]))
SETTINGS += [
    ("hybrid taper", [S("array.topology", "gradient_arc_hybrid"), S("array.count", 5),
                      S("array.angle_deg", 60), S("level_taper.window", "Hann"),
                      S("level_taper.max_atten_db", 6), S("array.gradient_pattern", "Supercardioid")]),
    ("progressive", [S("array.topology", "progressive_arc"), S("array.count", 8), S("array.radius_m", 6),
                     S("array.angle_deg", 100), S("array.progression_ratio", 2.5)]),
    ("physical", [S("array.topology", "physical_horizontal"), S("array.count", 10), S("array.radius_m", 7.29),
                  S("array.angle_deg", 70)]),
    ("gradient alpha", [S("array.topology", "gradient_cardioid"), S("array.count", 3),
                        S("array.gradient_alpha", 0.3)]),
    ("gradient null angle", [S("array.topology", "gradient_cardioid"), S("ui.null_angle_deg", 120)]),
    ("samples + group", [S("array.topology", "end_fire"), S("units.delay_display", "samples"),
                         S("dsp.sample_rate_hz", 48000), S("group.delay_ms", 12.5), S("group.level_db", -3),
                         S("group.inverted", True)]),
    ("d&b manual", [S("array.topology", "manual"), S("array.count", 4), S("units.xy_convention", "d&b Mode"),
                    {"type": "manual", "row": 0, "field": "x_m", "value": -1.2},
                    {"type": "manual", "row": 1, "field": "y_m", "value": 2.5},
                    {"type": "manual", "row": 2, "field": "gain_db", "value": -4},
                    {"type": "manual", "row": 3, "field": "reversed", "value": True}]),
    ("lacoustics manual", [S("array.topology", "manual"), S("array.count", 3),
                           {"type": "manual", "row": 0, "field": "y_m", "value": -0.9},
                           {"type": "manual", "row": 2, "field": "x_m", "value": 3.0}]),
    ("environment", [S("environment.temp_c", 31), S("environment.humidity_pct", 80),
                     S("environment.altitude_m", 1500), S("bandwidth.freq_high_hz", 90)]),
    ("alignment + bounce", [S("alignment_wizard.mains_distance_m", 30), S("alignment_wizard.mains_delay_ms", 2),
                            S("alignment_wizard.sub_distance_m", 27), S("sub_box.acoustic_center.enabled", True),
                            S("floor_bounce.source_height_m", 8), S("floor_bounce.mic_distance_m", 25),
                            S("floor_bounce.mic_height_m", 1.8)]),
    ("negative alignment", [S("alignment_wizard.mains_distance_m", 20),
                            S("alignment_wizard.sub_distance_m", 28)]),
    ("collision warn", [S("array.topology", "end_fire"), S("array.spacing_m", 0.5)]),
    ("custom box", [S("sub_box.width_m", 0.9), S("sub_box.gap_m", 0.05)]),
    ("venue wide circle", [S("venue.length_m", 20), S("venue.width_m", 40)]),
    ("focus/avoid", [S("array.topology", "avoid_point"), S("array.count", 5), S("array.avoid_x_m", 6),
                     S("array.avoid_y_m", -3)]),
    ("units cm", [S("units.length_unit", "cm"), S("name", "Main stage")]),
]

# --- scenarios: button presses, done on both apps ---------------------------
ACTIONS = [
    ("makeup apply", [S("array.count", 8), S("array.angle_deg", 60), S("level_taper.window", "Hann"),
                      S("level_taper.max_atten_db", 10)],
     [{"type": "makeup_apply"}], lambda a: a._apply_makeup_gain()),
    ("makeup apply twice then clear", [S("array.count", 8), S("level_taper.window", "Blackman"),
                                       S("level_taper.max_atten_db", 12), S("group.level_db", 2)],
     [{"type": "makeup_apply"}, {"type": "makeup_apply"}, {"type": "makeup_clear"}],
     lambda a: (a._apply_makeup_gain(), a._apply_makeup_gain(), a._clear_makeup_gain())),
    ("prealign use", [S("group.delay_ms", 3)],
     [{"type": "prealign_use"}], lambda a: a._use_prealign_delay()),
    ("prealign use + clear", [],
     [{"type": "prealign_use"}, {"type": "prealign_clear"}],
     lambda a: (a._use_prealign_delay(), a._clear_prealign_delay())),
    # Saved preset names must be the ones Use applied, not the dropdowns' later state.
    ("prealign use then change preset", [],
     [{"type": "prealign_sub", "value": "K1SB_60"}, {"type": "prealign_use"},
      {"type": "prealign_sub", "value": "K1SB_X"}],
     lambda a: (a.prealign_sub.set("K1SB_60"), a._update_prealign_readout(), a._use_prealign_delay(),
                a.prealign_sub.set("K1SB_X"), a._update_prealign_readout())),
    ("set min spacing", [S("array.topology", "end_fire")],
     [{"type": "set_min_spacing"}], lambda a: a._set_min_spacing()),
    ("set spacing + gap", [S("sub_box.gap_m", 0.1)],
     [{"type": "set_spacing_gap"}], lambda a: a._set_spacing_with_gap()),
    ("use optimum", [S("array.topology", "gradient_cardioid"), S("bandwidth.freq_high_hz", 80)],
     [{"type": "use_optimum_spacing"}], lambda a: a._use_optimum_spacing()),
    ("use optimum row", [S("array.topology", "end_fire_arc_hybrid")],
     [{"type": "use_optimum_row_spacing"}], lambda a: a._use_optimum_row_spacing()),
    ("set arc from end-fire", [S("array.topology", "end_fire")],
     [{"type": "set_arc_from_venue"}], lambda a: a._set_arc_from_venue()),
    ("set arc ellipse wide", [S("array.topology", "arc_steering"), S("array.shape", "ellipse"),
                              S("venue.width_m", 70)],
     [{"type": "set_arc_from_venue"}, {"type": "use_venue_ellipse"}],
     lambda a: (a._set_arc_from_venue(), a._use_venue_ellipse_ratio())),
    ("alignment set", [S("alignment_wizard.mains_distance_m", 35), S("alignment_wizard.sub_distance_m", 30)],
     [{"type": "set_group_from_alignment"}], lambda a: a._set_group_delay_from_alignment()),
]


def fresh_app_matching(state):
    app = desk.App()
    app.withdraw()
    load_into_desktop(app, state)
    return app


def main():
    base = model.default_state()

    # 0. Defaults match the desktop's freshly built app.
    app = desk.App()
    app.withdraw()
    compare_files("defaults", app, base)
    compare_views("defaults", app, base)

    # 1. Settings scenarios
    for name, actions in SETTINGS:
        state = run(base, actions)
        warnings = load_into_desktop(app, state)
        check(name, "load warnings (web file -> desktop)", warnings, [])
        compare_views(name, app, state)
        compare_files(name, app, state)
        # desktop file -> web model -> identical file
        back, w2 = model.from_project(base, project_io.build_project_dict(app))
        check(name, "load warnings (desktop file -> web)", w2, [])
        check(name, "round trip desktop -> web", comparable(project_io.build_project_dict(app)),
              comparable(model.to_project(back)))
    app.destroy()

    # 2. Button presses
    for name, setup, web_actions, desk_call in ACTIONS:
        state = run(base, setup)
        app = fresh_app_matching(state)
        desk_call(app)
        state = run(state, web_actions)
        compare_views(name, app, state)
        compare_files(name, app, state)
        app.destroy()

    # 3. Tolerant loading: same warnings for a messy file
    messy = {"schema_version": 9, "array": {"topology": "nope", "count": 99, "angle_deg": 500, "steer_deg": "x"},
             "level_taper": {"window": "Kaiser"}, "units": {"length_unit": "ft"}, "dsp": {"sample_rate_hz": 44100},
             "environment": {"temp_c": 99}, "group": {"level_db": 40, "prealign": {"active": True,
             "main_system": "ZZ", "sub_system": "YY", "contribution_ms": 1.5}}}
    app = desk.App()
    app.withdraw()
    dw = project_io.apply_project_dict(app, copy.deepcopy(messy))
    state, ww = model.from_project(base, copy.deepcopy(messy))
    check("messy file", "warnings", dw, ww)
    desk_file, web_file = comparable(project_io.build_project_dict(app)), comparable(model.to_project(state))
    for who, f in (("desktop", desk_file), ("web", web_file)):
        pre = f["group"]["prealign"]
        check("messy file", f"{who} keeps the file's missing preset names",
              ("ZZ", "YY"), (pre["main_system"], pre["sub_system"]))
    check("messy file", ".sadrt contents", desk_file, web_file)
    compare_views("messy file", app, state)
    app.destroy()

    total = len(SETTINGS) + len(ACTIONS) + 2
    if failures:
        print("\n".join(failures[:60]))
        if len(failures) > 60:
            print(f"... {len(failures) - 60} more")
        print(f"\nFAILED: {len(failures)} mismatches across {total} scenarios")
        sys.exit(1)
    print(f"web model matches desktop app: {total} scenarios, all values and readouts identical")


if __name__ == "__main__":
    main()
