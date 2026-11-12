"""Generate tests/parity_cases.json from the shared Python math.

Each case is a call into array_math (function name + JSON args + kwargs) and
the value it returns today. The desktop app and the web app both run the same
shared/array_math.py, so these cases serve two purposes:

  1. Regression: tests/check_parity.py re-runs every case and fails if any
     result moved. A deliberate math change means regenerating this file and
     reviewing the diff in git, so every number that changed is visible.
  2. Cross-platform: the web app runs the same cases in Pyodide (browser
     Python) to confirm the browser computes identical values.

Run from the repo root:
    python tests/generate_parity_cases.py

Note on expected values: these are a snapshot of the current implementation,
NOT independent ground truth. Ground truth (S.A.D. tutorial numbers, physics
checks) is what the math-verifier agent checks; see realtime_app/README.md.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))

import array_math  # noqa: E402
from parity_common import to_jsonable  # noqa: E402

C = 343.0  # fixed speed of sound so cases don't depend on the weather helpers
WINDOWS = array_math.LEVEL_TAPER_WINDOWS


def case(case_id, fn, *args, **kwargs):
    return {"id": case_id, "fn": fn, "args": list(args), "kwargs": kwargs}


def build_cases():
    cases = []
    add = cases.append

    # --- Speed of sound (Cramer 1993) -------------------------------------
    for t, rh, alt in [(0, 0, 0), (20, 50, 0), (21, 50, 0), (30, 90, 0),
                       (-10, 20, 0), (15, 50, 1500), (25, 70, 3000)]:
        add(case(f"speed_of_sound_{t}C_{rh}rh_{alt}m", "speed_of_sound", t, rh, alt))
    add(case("pressure_at_altitude_2000m", "pressure_at_altitude_pa", 2000))

    # --- Topologies ---------------------------------------------------------
    for n in (1, 2, 4, 7):
        add(case(f"end_fire_n{n}", "end_fire", n, 1.2, C))
    add(case("end_fire_trim", "end_fire", 4, 1.0, C, [0, -1, -2, -3]))

    for pairs in (1, 2, 4):
        for alpha in (0.25, 0.37, 0.5):
            add(case(f"gradient_cardioid_p{pairs}_a{alpha}", "gradient_cardioid",
                     pairs, 1.0, C, alpha=alpha))

    add(case("arc_tutorial_10x0.94_71deg", "arc_steering", 10, 0.94, 71, C))
    for n, ang, steer, ds in [(6, 60, 0, 1.0), (6, 60, 15, 1.0), (8, 90, -20, 1.0),
                              (9, 120, 0, 0.6), (5, 180, 30, 1.0), (12, 45, 0, 1.4)]:
        add(case(f"arc_steering_n{n}_{ang}deg_s{steer}_d{ds}", "arc_steering",
                 n, 1.0, ang, C, steer_deg=steer, depth_scale=ds))
    add(case("arc_virtual_source_6_71_s10", "arc_virtual_source", 6, 0.94, 71, 10))

    for cols, ang, steer in [(1, 0, 0), (4, 60, 0), (5, 90, 20)]:
        add(case(f"end_fire_arc_hybrid_c{cols}_{ang}_s{steer}", "end_fire_arc_hybrid",
                 cols, 1.0, 1.2, ang, C, steer_deg=steer))
        add(case(f"gradient_arc_hybrid_c{cols}_{ang}_s{steer}", "gradient_arc_hybrid",
                 cols, 1.0, 1.0, ang, C, steer_deg=steer, alpha=0.37))

    add(case("physical_horizontal_array_6", "physical_horizontal_array", 6))
    add(case("manual_3", "manual", 3, [0, 1.5, 3.25], [0, -3, -6], [False, True, False]))

    for n, x, y in [(6, 0, 20), (6, 5, 15), (7, -3, 8)]:
        add(case(f"focus_point_n{n}_{x}_{y}", "focus_point", n, 1.0, x, y, C))
        add(case(f"avoid_point_n{n}_{x}_{y}", "avoid_point", n, 1.0, x, y, C))

    # --- Physical layouts -------------------------------------------------
    add(case("physical_arc_layout_tutorial", "physical_arc_layout", 10, 7.29, 70))
    add(case("physical_arc_chord_spacing", "physical_arc_chord_spacing", 8, 7.29, 70))
    for ratio in (1.0, 0.6, 1.5):
        add(case(f"physical_ellipse_layout_r{ratio}", "physical_ellipse_layout", 8, 6.0, 180, ratio))
        add(case(f"progressive_arc_layout_r{ratio}", "progressive_arc_layout", 8, 6.0, 90, ratio))
    add(case("physical_virtual_source", "physical_virtual_source_m", 5.0, 1.2))

    # --- Venue / FAR ------------------------------------------------------
    add(case("forward_aspect_ratio_60", "forward_aspect_ratio", 60))
    add(case("far_from_venue_50x25", "far_from_venue", 50, 25))
    for far in (0.5, 1.0, 2.0, 3.5):
        add(case(f"arc_from_far_{far}", "arc_from_far", far))
        add(case(f"ellipse_ratio_from_far_{far}", "ellipse_ratio_from_far", far))
        add(case(f"angle_from_far_ellipse_{far}", "angle_from_far_ellipse", far))

    # --- Gradient helpers -------------------------------------------------
    for alpha in (0.0, 0.25, 0.37, 0.5):
        add(case(f"gradient_null_angle_{alpha}", "gradient_null_angle_deg", alpha))
    for ang in (90, 109.5, 126, 180):
        add(case(f"alpha_from_null_angle_{ang}", "alpha_from_null_angle_deg", ang))

    # --- Level taper (every window) ---------------------------------------
    for w in WINDOWS:
        add(case(f"level_taper_{w}_n8", "level_taper_db", 8, w, 12.0, None, 30.0))
        add(case(f"level_taper_{w}_n7_steered", "level_taper_db", 7, w, 12.0, 4.5, 26.0))
    add(case("arc_steered_aim_index", "arc_steered_aim_index", 8, 90, 20))
    add(case("taper_onaxis_loss", "taper_onaxis_loss_db", [0, -1.5, -4, -9]))
    add(case("taper_power_loss", "taper_power_loss_db", [0, -1.5, -4, -9]))

    # --- Spacing / alignment / gain helpers ------------------------------
    add(case("freq_at_quarter_wavelength", "freq_at_wavelength_fraction", 1.2, C, 0.25))
    add(case("spacing_at_quarter_wavelength", "spacing_at_wavelength_fraction", 80, C, 0.25))
    for steer in (0, 30, 90):
        add(case(f"grating_lobe_s{steer}", "grating_lobe_max_spacing_m", 100, C, steer))
    add(case("required_group_delay", "required_group_delay_ms", 30.0, 2.5, 28.0, C))
    add(case("delay_samples_96k", "delay_samples", 3.1415, 96000))
    add(case("delay_ms_for_distance", "delay_ms_for_distance", 12.5, C))
    for db in (18, 0, -6, -40, -144, -200):
        add(case(f"gain_db_to_osc_{db}", "gain_db_to_osc", db))
    add(case("floor_bounce_tutorial", "floor_bounce", 8, 25, 1.8, 331.4 + 0.607 * 21))

    return cases


def main():
    cases = build_cases()
    ids = [c["id"] for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"duplicate case ids: {sorted(dupes)}")
    for c in cases:
        fn = getattr(array_math, c["fn"])
        c["expected"] = to_jsonable(fn(*c["args"], **c["kwargs"]))
    out = {
        "_comment": "Generated by tests/generate_parity_cases.py -- do not edit by hand.",
        "cases": cases,
    }
    path = os.path.join(HERE, "parity_cases.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"wrote {len(cases)} cases to {path}")


if __name__ == "__main__":
    main()
