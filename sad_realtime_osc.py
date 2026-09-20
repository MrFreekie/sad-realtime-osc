"""S.A.D. realtime: live subwoofer array delay/gain/polarity calculator
with OSC output.

The array math (End-Fire, Gradient/Cardioid, Delayed Horizontal Array /
Arc, Forward Aspect Ratio) reimplements Merlijn van Veen's S.A.D.
(Subwoofer Array Designer) calculator and manual -- credit to him, and
to Mauricio "Magu" Ramirez and Bob "6o6" McCarthy, S.A.D.'s own credited
inspiration. https://www.merlijnvanveen.nl/ -- see README.md for details
on what was verified against the original and how. End-Fire Arc Hybrid
and Gradient Arc Hybrid are this app's own extension -- End-Fire/Gradient
pairs arranged as arc-steered columns -- with no S.A.D. tutorial ground
truth of their own; see README.md. The Ellipse shape was inspired by
Rafael Gomes Pereira's SubArray Vizualizer (a separate third-party
tool, public interface only -- see README.md's Credits section), with
its actual math this app's own derivation.

Pick a topology, drag the sliders, watch the three values per sub update
live, and stream them out over OSC as you go. The OSC address layout is a
generic stub (/sad/sub/<n>/delay_ms|gain_db|polarity) -- point it at any
OSC receiver to test, and remap the addresses here to match your own
device's documented OSC namespace.

Run:
    pip install python-osc
    python sad_realtime_osc.py
"""
__version__ = "0.5.0"

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pythonosc.udp_client import SimpleUDPClient

import project_io
from array_math import (
    end_fire, gradient_cardioid, arc_steering, manual, forward_aspect_ratio,
    physical_horizontal_array, physical_arc_layout, physical_arc_chord_spacing, delays_from_depth,
    end_fire_arc_hybrid, gradient_arc_hybrid,
    sub_positions_arc_hybrid_lateral, sub_positions_arc_hybrid_depth,
    physical_ellipse_layout, progressive_arc_layout, min_adjacent_chord,
    ellipse_ratio_from_far, angle_from_far_ellipse, focus_point,
    freq_at_wavelength_fraction, spacing_at_wavelength_fraction, grating_lobe_max_spacing_m,
    far_from_venue, arc_from_far, sub_positions, sub_positions_gradient, sub_positions_centered, array_length,
    gain_db_to_osc, total_delay_ms, effective_polarity, total_gain_db,
    delay_ms_for_distance, distance_for_delay_ms, delay_samples, speed_of_sound,
    required_group_delay_ms, spacing_clearance_m,
    LEVEL_TAPER_WINDOWS, PARAMETRIC_TAPER_WINDOWS, level_taper_db, arc_steered_aim_index,
    taper_onaxis_loss_db, taper_power_loss_db,
)
from sub_profiles import load_profiles
from prealign_profiles import (
    load_entries as load_prealign_entries, CONFIG_LABELS, POLARITY_LABELS, PrealignDataError,
)

CUSTOM_PROFILE = "— custom —"

TOPOLOGIES = ["End-Fire", "Gradient / Cardioid Pairs", "Physical Horizontal Array",
              "Arc / Broadside Steering", "End-Fire Arc Hybrid", "Gradient Arc Hybrid",
              "Progressive Arc", "Focus Point", "Manual"]
(TOPO_END_FIRE, TOPO_GRADIENT, TOPO_PHYSICAL, TOPO_ARC,
 TOPO_EF_ARC_HYBRID, TOPO_GRAD_ARC_HYBRID, TOPO_PROGRESSIVE, TOPO_FOCUS, TOPO_MANUAL) = TOPOLOGIES
ARC_HYBRID_TOPOLOGIES = (TOPO_EF_ARC_HYBRID, TOPO_GRAD_ARC_HYBRID)
# Every topology with an Angle control that means "coverage arc" -- used both
# to show/hide Angle-related panels and to decide whether "Set arc" (Venue ->
# arc) can apply in place or has to switch topology first (see
# _set_arc_from_venue). Kept as one shared set instead of re-deriving the
# condition in both places, since letting them drift apart is exactly the bug
# that made "Set arc" knock you out of an Arc Hybrid topology (fixed in 0.3.1).
ANGLE_TOPOLOGIES = (TOPO_ARC, TOPO_PHYSICAL, TOPO_PROGRESSIVE) + ARC_HYBRID_TOPOLOGIES
# Topologies with a Shape (Circle/Ellipse) selector: Physical Horizontal Array
# (real elliptical placement, physical_ellipse_layout) and Arc / Broadside
# Steering plus both Arc Hybrids (electronic depth_scale on the same virtual
# curvature, _arc_column_delays_s -- they're physically a straight line
# either way, so there's no placement to bend, just the delay curve).
# Progressive Arc is deliberately not included -- its own Progression ratio
# is a different, not-yet-combined generalization of the same circle.
ELLIPSE_TOPOLOGIES = (TOPO_PHYSICAL, TOPO_ARC) + ARC_HYBRID_TOPOLOGIES
# Topologies with a Steer control -- Arc / Broadside Steering and the two Arc
# Hybrids (Physical Horizontal Array, Progressive Arc, and Focus Point have no
# electronic steering concept: their delay is either fixed at 0 or solved for
# a focus point instead). Shared constant for the same reason ANGLE_TOPOLOGIES
# and ELLIPSE_TOPOLOGIES are -- one definition instead of two that could drift
# apart (see ANGLE_TOPOLOGIES' comment for the bug that taught that lesson).
STEER_TOPOLOGIES = (TOPO_ARC,) + ARC_HYBRID_TOPOLOGIES
# Topologies with a front/rear differential (Gradient) pair whose pattern is
# tunable via alpha -- Gradient / Cardioid Pairs itself and Gradient Arc
# Hybrid (End-Fire Arc Hybrid's pairs are same-polarity, not a differential
# pair, so alpha doesn't apply there).
GRADIENT_PATTERN_TOPOLOGIES = (TOPO_GRADIENT, TOPO_GRAD_ARC_HYBRID)

SHAPE_CIRCLE, SHAPE_ELLIPSE = "Circle", "Ellipse"
PHYSICAL_SHAPES = [SHAPE_CIRCLE, SHAPE_ELLIPSE]

# Which physical axis the table's X/Y columns (and Manual mode's typed X/Y
# fields) represent. L-Acoustics (default): Y = depth (into the room),
# X = lateral (across the room). d&b swaps them: X = depth, Y = lateral --
# this app's original convention, before L-Acoustics became the default.
# Purely a labelling/entry convention -- the actual geometry and delay math
# never change, only which column means what.
XY_DNB, XY_LACOUSTICS = "d&b Mode", "L-Acoustics Mode"
XY_CONVENTIONS = [XY_DNB, XY_LACOUSTICS]

# Named first-order differential-array patterns -> alpha (array_math's
# gradient_pair_delay_ms), standard values from the differential-microphone-
# array literature (hypercardioid/supercardioid/cardioid are the commonly
# published exact figures; subcardioid is the conventional cardioid/omni
# midpoint, less rigidly standardized than the other three).
GRADIENT_PATTERN_ALPHA = {
    "Figure-8": 0.0,
    "Hypercardioid": 0.25,
    "Supercardioid": 0.37,
    "Cardioid": 0.5,
    "Subcardioid": 0.75,
}
GRADIENT_PATTERNS = list(GRADIENT_PATTERN_ALPHA)

WAVELENGTH_FRACTION = {
    TOPO_END_FIRE: 0.25,
    TOPO_GRADIENT: 0.25,
    TOPO_ARC: 0.5,
    TOPO_EF_ARC_HYBRID: 0.5,
    TOPO_GRAD_ARC_HYBRID: 0.5,
    TOPO_FOCUS: 0.5,
}

DSP_CLOCK_RATES = {
    "48 kHz (1 FS)": 48000,
    "96 kHz (2 FS)": 96000,
    "192 kHz (4 FS)": 192000,
}
DSP_CLOCKS = list(DSP_CLOCK_RATES.keys())

UNIT_SCALE = {"m": 1.0, "cm": 0.01, "mm": 0.001}
UNIT_INCREMENT = {"m": 0.01, "cm": 1.0, "mm": 10.0}
# Decimal places per unit that resolve to exactly 1 mm -- the smallest
# length increment that means anything physically (cabinet placement).
UNIT_DECIMALS = {"m": 3, "cm": 1, "mm": 0}
UNITS = ["m", "cm", "mm"]

MAX_SUBS = 12
# Physical Horizontal Array / Arc / Manual place elements freely rather than
# stacking them front-to-back, so a much larger count is still a realistic
# array (e.g. a long curved festival sub arc); End-Fire and Gradient stay at
# MAX_SUBS -- deep front-to-back stacks/pairs that large aren't a real
# configuration.
MAX_SUBS_SPATIAL = 48

_TABLE_ROW_HEIGHT_PX = 28
_TABLE_MAX_HEIGHT_PX = 320


class Tooltip:
    """Small popup showing `text` while the cursor is over `widget`."""

    def __init__(self, widget, text, wraplength=360):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#ffffe0",
                 relief="solid", borderwidth=1, wraplength=self.wraplength,
                 font=("Segoe UI", 8)).pack(ipadx=4, ipady=2)

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"S.A.D. Realtime v{__version__}")
        self.resizable(True, True)

        self.osc_client = None
        self._last_sent = {}
        self.trim_vars = []
        self.manual_x_vars = []
        self.manual_y_vars = []
        self.manual_gain_vars = []
        self.manual_pol_vars = []
        self.row_widgets = []
        self._length_fields = []
        self.unit = tk.StringVar(value="m")
        self.prealign_contribution_ms = 0.0
        self.prealign_active = False
        self.prealign_note_var = tk.StringVar(value="")
        self.project_name = tk.StringVar(value="")
        self.project_path = None
        self.project_status_var = tk.StringVar(value="unsaved project")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        self.left_col = ttk.Frame(self)
        self.left_col.grid(row=0, column=0, sticky="nsew")
        self.right_col = ttk.Frame(self)
        self.right_col.grid(row=0, column=1, sticky="new")

        # left column: primary/frequently-used controls + the per-sub table
        self._build_project_panel()
        self._build_controls()
        self._build_topology_options_panel()
        self._build_taper_panel()
        self._build_bandwidth_panel()
        self._build_info_panel()
        self._build_table()
        self._build_osc_panel()

        # right column: setup-once / ancillary panels
        self._build_units_panel()
        self._build_clock_panel()
        self._build_environment_panel()
        self._build_venue_panel()
        self._build_dimensions_panel()
        self._build_group_panel()
        self._build_prealign_panel()
        self._build_alignment_panel()

        ttk.Label(self, text="Array math from Merlijn van Veen's S.A.D. (Subwoofer Array Designer) — "
                              "merlijnvanveen.nl", foreground="#888", font=("Segoe UI", 8)).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 0))
        ttk.Label(self, text="S.A.D. Realtime — freekieaudio.uk", foreground="#888",
                  font=("Segoe UI", 8)).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))
        ttk.Label(self, text="100% vibe coded — use at your own risk, check all calculations before use.",
                  foreground="#a03030", font=("Segoe UI", 8, "bold")).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

        self._on_topology_change()
        self._update_venue_far()
        self._fit_window_height()

    def _fit_window_height(self):
        self.update_idletasks()
        width = max(self.winfo_width(), self.winfo_reqwidth())
        height = max(self.winfo_reqheight(), 400)
        self.geometry(f"{width}x{height}")
        self.minsize(self.winfo_reqwidth(), 400)

    # -------------------------------------------------------------- project --
    def _build_project_panel(self):
        frm = ttk.LabelFrame(self.left_col, text="Project")
        frm.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(frm, text="Name / notes").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        name_entry = ttk.Entry(frm, textvariable=self.project_name, width=32)
        name_entry.grid(row=0, column=1, columnspan=3, sticky="we", padx=5, pady=5)

        ttk.Button(frm, text="New", command=self._new_project).grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Button(frm, text="Save", command=self._save_project).grid(row=1, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(frm, text="Save As...", command=self._save_project_as).grid(
            row=1, column=2, sticky="w", padx=5, pady=5)
        ttk.Button(frm, text="Load...", command=self._load_project).grid(
            row=1, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(frm, textvariable=self.project_status_var, foreground="#666").grid(
            row=1, column=4, sticky="w", padx=5, pady=5)

        self._help_icon(frm, row=0, col=4,
                         text=f"Saves every setting on this screen -- topology, spacing, environment, group, "
                              f"OSC target, etc. -- to a {project_io.FILE_EXTENSION} file (plain JSON) you can "
                              f"reload later or hand to another engineer. \"New\" resets everything to factory "
                              f"defaults (with a confirmation first) -- use it to clear out a loaded show before "
                              f"starting a fresh one, without restarting the app. \"Live send\" is never restored "
                              f"from a loaded file even if it was on when saved, and \"New\" always turns it off "
                              f"too -- re-enable it by hand once you've checked the OSC host/port are correct "
                              f"for this rig, since a stale saved target could otherwise start streaming to the "
                              f"wrong place the moment a file opens.")

        frm.grid_columnconfigure(5, weight=1)

    def _new_project(self):
        if not messagebox.askyesno(
                "New project", "Reset every setting to defaults? Anything unsaved will be lost."):
            return
        project_io.apply_project_dict(self, project_io.default_project_dict())
        self.project_path = None
        self.project_status_var.set("unsaved project")

    def _save_project(self):
        if self.project_path is None:
            self._save_project_as()
            return
        self._write_project(self.project_path)

    def _save_project_as(self):
        path = filedialog.asksaveasfilename(
            defaultextension=project_io.FILE_EXTENSION,
            filetypes=[("S.A.D. Realtime project", f"*{project_io.FILE_EXTENSION}"), ("All files", "*.*")],
            initialfile=(self.project_name.get() or "show") + project_io.FILE_EXTENSION,
        )
        if not path:
            return
        self._write_project(path)

    def _write_project(self, path):
        try:
            project_io.save_project(self, path)
        except OSError as e:
            messagebox.showerror("Save failed", f"Couldn't save project:\n{e}")
            return
        self.project_path = path
        self.project_status_var.set(f"saved: {os.path.basename(path)}")

    def _load_project(self):
        path = filedialog.askopenfilename(
            filetypes=[("S.A.D. Realtime project", f"*{project_io.FILE_EXTENSION}"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = project_io.load_project(path)
        except (OSError, ValueError) as e:
            messagebox.showerror("Load failed", f"Couldn't read project file:\n{e}")
            return
        try:
            warnings = project_io.apply_project_dict(self, data)
        except Exception as e:
            messagebox.showerror(
                "Load failed",
                f"Project file was read but couldn't be applied:\n{e}\n\n"
                "The app's current settings were left unchanged.")
            return
        self.project_path = path
        self.project_status_var.set(f"loaded: {os.path.basename(path)}")
        if warnings:
            messagebox.showwarning(
                "Loaded with warnings",
                "Project loaded, but some values needed fixing up:\n\n" + "\n".join(f"- {w}" for w in warnings))

    # ---------------------------------------------------------- controls --
    def _build_controls(self):
        frm = ttk.LabelFrame(self.left_col, text="Array")
        frm.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(frm, text="Topology").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.topology = tk.StringVar(value=TOPO_ARC)
        cb = ttk.Combobox(frm, textvariable=self.topology, values=TOPOLOGIES, state="readonly", width=26)
        cb.grid(row=0, column=1, columnspan=3, sticky="w", padx=5, pady=5)
        cb.bind("<<ComboboxSelected>>", lambda e: self._on_topology_change())

        self.count_label = ttk.Label(frm, text="Subs")
        self.count_label.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.count = tk.IntVar(value=6)
        self.count_spin = ttk.Spinbox(frm, from_=1, to=MAX_SUBS, textvariable=self.count, width=5,
                                       command=self._on_count_change)
        self.count_spin.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.count_spin.bind("<Return>", lambda e: self._on_count_change())
        self.count_spin.bind("<FocusOut>", lambda e: self._on_count_change())

        self.spacing_label = ttk.Label(frm, text="Spacing")
        self.spacing_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.spacing = tk.DoubleVar(value=1.4)
        self.spacing_spin = self._make_length_field(frm, self.spacing, row=2, col=1)
        self.spacing_slider = ttk.Scale(frm, from_=0.1, to=5.0, orient="horizontal", variable=self.spacing,
                                         command=self._on_spacing_slider)
        self.spacing_slider.grid(row=2, column=2, sticky="ew", padx=5, pady=5)
        self.wavelength_label = ttk.Label(frm, text="", width=16)
        self.wavelength_label.grid(row=2, column=3, sticky="w", padx=5, pady=5)

        frm.grid_columnconfigure(2, weight=1)

    # ------------------------------------------------------- topology opts --
    def _build_topology_options_panel(self):
        """Everything that only some topologies use (arc/steer/shape/hybrid
        row spacing/progression/focus/gradient pattern), split out of Array
        so that panel stays a stable 3 rows and this one carries the growth
        -- was previously the two panels crammed together, which meant a
        topology like Gradient Arc Hybrid stacked nine unrelated rows into
        one "Array" box."""
        frm = ttk.LabelFrame(self.left_col, text="Topology options")
        frm.pack(fill="x", padx=10, pady=5)
        self.topology_options_frame = frm

        self.row_spacing_label = ttk.Label(frm, text="Row spacing")
        self.row_spacing_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.row_spacing = tk.DoubleVar(value=0.7)
        self.row_spacing_spin = self._make_length_field(frm, self.row_spacing, row=0, col=1)
        self.row_spacing_slider = ttk.Scale(frm, from_=0.1, to=5.0, orient="horizontal", variable=self.row_spacing,
                                             command=self._on_row_spacing_slider)
        self.row_spacing_slider.grid(row=0, column=2, sticky="ew", padx=5, pady=5)
        self.row_wavelength_label = ttk.Label(frm, text="", width=16)
        self.row_wavelength_label.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self.row_spacing_help = self._help_icon(
            frm, row=0, col=4,
            text="Front-to-back spacing within each column, for the two Arc Hybrid "
                 "topologies -- the internal End-Fire/Gradient pair depth, separate from "
                 "Spacing above (which is the column-to-column lateral spacing along the "
                 "arc). Always rated against 1/4 wavelength (like End-Fire/Gradient's own "
                 "Spacing), regardless of the 1/2 wavelength rule used for the column "
                 "Spacing above.")

        self.angle = tk.DoubleVar(value=0.0)
        self.angle_label, self.angle_spin, self.angle_slider = self._labeled_slider(
            frm, "Arc (°)", self.angle, 0.0, 180.0, row=1, increment=1.0, decimals=1)

        self.far_label = ttk.Label(frm, text="FAR: -", width=12)
        self.far_label.grid(row=1, column=3, sticky="w", padx=5, pady=5)

        self.radius_label = ttk.Label(frm, text="Radius")
        self.radius_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.radius = tk.DoubleVar(value=2.0)
        self.radius_spin = self._make_length_field(frm, self.radius, row=2, col=1)

        self.steer = tk.DoubleVar(value=0.0)
        self.steer_label, self.steer_spin, self.steer_slider = self._labeled_slider(
            frm, "Steer (°)", self.steer, -90.0, 90.0, row=3, increment=1.0, decimals=1)
        self.steer_help = self._help_icon(
            frm, row=3, col=3,
            text="Redirects the whole arc's aim off-centre without changing its coverage "
                 "angle (FAR) -- for venues that aren't symmetrical about the array's own "
                 "centreline. Positive steers toward the highest-numbered sub. 0 = the "
                 "default symmetric aim, straight ahead.")

        self.shape_label = ttk.Label(frm, text="Shape")
        self.shape_label.grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.shape = tk.StringVar(value=SHAPE_CIRCLE)
        self.shape_cb = ttk.Combobox(frm, textvariable=self.shape, values=PHYSICAL_SHAPES,
                                      state="readonly", width=10)
        self.shape_cb.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        self.shape_cb.bind("<<ComboboxSelected>>", lambda e: self._on_shape_change())

        self.ellipse_ratio = tk.DoubleVar(value=1.0)
        self.ellipse_ratio_label, self.ellipse_ratio_spin, self.ellipse_ratio_slider = self._labeled_slider(
            frm, "Ellipse ratio", self.ellipse_ratio, 0.05, 2.0, row=5, increment=0.05, decimals=2)
        self.ellipse_ratio_help = self._help_icon(
            frm, row=5, col=3,
            text="Depth-scale ratio for Shape = Ellipse: 1.0 is a true circle (identical to "
                 "Shape = Circle); below 1 flattens the bow, above 1 exaggerates it. For "
                 "Physical Horizontal Array this scales the real physical placement (Radius "
                 "stays what it is); for Arc / Broadside Steering and the two Arc Hybrids, "
                 "which are physically a straight line either way, it scales the virtual "
                 "curvature used for delay instead -- same ratio, same effect on the pattern, "
                 "just electronic rather than physical. Rotation is not computed for Ellipse "
                 "(always 0°, Physical Horizontal Array only -- the other three never had "
                 "rotation to begin with) -- a true ellipse's aim direction is the local "
                 "tangent, not the parametric angle, and this app treats subs as "
                 "omnidirectional enough at these frequencies that it isn't worth tracking "
                 "for this shape. This app's own extension, not part of S.A.D. -- no "
                 "tutorial ground truth to verify it against.")

        self.progression_ratio = tk.DoubleVar(value=1.0)
        self.progression_label, self.progression_spin, self.progression_slider = self._labeled_slider(
            frm, "Progression", self.progression_ratio, 1.0, 8.0, row=6, increment=0.1, decimals=2)
        self.progression_help = self._help_icon(
            frm, row=6, col=3,
            text="Center:edge angular-step ratio for Progressive Arc -- 1.0 is a uniform "
                 "circular arc (identical to Physical Horizontal Array); above 1 makes the "
                 "center gap(s) progressively wider (tighter curvature there) and the edge "
                 "gaps progressively narrower (flatter, longer throw down the flanks), while "
                 "total coverage angle (and FAR) stays exactly what Arc (°) says. Rotation is "
                 "still the true local aim angle here, unlike Ellipse -- every element still "
                 "sits on one real circle of the given Radius, just unevenly spaced along it. "
                 "This app's own extension, not part of S.A.D. -- no tutorial ground truth to "
                 "verify it against.")

        self.focus_x_label = ttk.Label(frm, text="Focus X")
        self.focus_x_label.grid(row=7, column=0, sticky="w", padx=5, pady=5)
        self.focus_x = tk.DoubleVar(value=10.0)
        self.focus_x_spin = self._make_length_field(frm, self.focus_x, row=7, col=1)

        self.focus_y_label = ttk.Label(frm, text="Focus Y")
        self.focus_y_label.grid(row=8, column=0, sticky="w", padx=5, pady=5)
        self.focus_y = tk.DoubleVar(value=0.0)
        self.focus_y_spin = self._make_length_field(frm, self.focus_y, row=8, col=1)
        self.focus_help = self._help_icon(
            frm, row=8, col=3,
            text="Focus Point (\"Destruction Mode\") delays every sub so its output arrives "
                 "at one target point at the same instant, for maximum constructive buildup "
                 "there -- Focus X is how far out in front of the line the target sits, "
                 "Focus Y is its lateral offset from the line's own center (0 = dead ahead). "
                 "Near-field acoustic focusing, exact by construction (not an approximation) "
                 "-- this app's own extension, not a S.A.D. topology.")

        self.pattern_label = ttk.Label(frm, text="Pattern")
        self.pattern_label.grid(row=9, column=0, sticky="w", padx=5, pady=5)
        self.gradient_pattern = tk.StringVar(value="Cardioid")
        self.pattern_cb = ttk.Combobox(frm, textvariable=self.gradient_pattern,
                                        values=GRADIENT_PATTERNS + [CUSTOM_PROFILE],
                                        state="readonly", width=13)
        self.pattern_cb.grid(row=9, column=1, sticky="w", padx=5, pady=5)
        self.pattern_cb.bind("<<ComboboxSelected>>", self._on_gradient_pattern_change)

        self.gradient_alpha = tk.DoubleVar(value=0.5)
        self.alpha_label, self.alpha_spin, self.alpha_slider = self._labeled_slider(
            frm, "Pattern α", self.gradient_alpha, 0.0, 0.9, row=10, increment=0.01,
            decimals=3, on_commit=self._on_gradient_alpha_edited)
        self.pattern_help = self._help_icon(
            frm, row=10, col=3,
            text="Front/rear delay ratio for the differential (Gradient) pair, generalizing "
                 "the fixed cardioid null (α = 0.5, straight behind the pair) to the standard "
                 "first-order pattern family E(θ) = α + (1-α)·cosθ: rear delay = transit time × "
                 "α/(1-α), still reversed polarity. Named presets are the standard values "
                 "(Figure-8 0, Hypercardioid 0.25, Supercardioid 0.37, Cardioid 0.5, Subcardioid "
                 "0.75); editing α directly resets Pattern to \"— custom —\", same as Sub box "
                 "dimensions' Profile field. Capped below 1.0 -- that's the unreachable omni "
                 "limit, needing impractically large delay for a fixed small spacing.")

        frm.grid_columnconfigure(2, weight=1)

    def _on_spacing_slider(self, value):
        """ttk.Scale has no snap-to-step option, so dragging it would otherwise
        write arbitrary sub-mm floats straight into Spacing -- quantize to the
        same 1 mm floor the typed field enforces."""
        try:
            self.spacing.set(round(float(value), 3))
        except (tk.TclError, ValueError):
            pass
        self._on_change()

    def _on_row_spacing_slider(self, value):
        """Same quantize-on-drag reasoning as _on_spacing_slider, for Row
        spacing's slider."""
        try:
            self.row_spacing.set(round(float(value), 3))
        except (tk.TclError, ValueError):
            pass
        self._on_change()

    def _labeled_slider(self, parent, text, var, lo, hi, row, increment=0.1, decimals=None,
                         on_commit=None):
        label = ttk.Label(parent, text=text)
        label.grid(row=row, column=0, sticky="w", padx=5, pady=5)
        commit = on_commit or self._on_change

        def quantize():
            if decimals is not None:
                try:
                    var.set(round(var.get(), decimals))
                except tk.TclError:
                    return
            commit()

        spin = ttk.Spinbox(parent, from_=lo, to=hi, increment=increment, textvariable=var, width=8,
                            command=quantize)
        spin.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        spin.bind("<Return>", lambda e: quantize())
        spin.bind("<FocusOut>", lambda e: quantize())

        def on_slide(v):
            if decimals is not None:
                try:
                    var.set(round(float(v), decimals))
                except (tk.TclError, ValueError):
                    pass
            commit()

        slider = ttk.Scale(parent, from_=lo, to=hi, orient="horizontal", variable=var,
                            command=on_slide)
        slider.grid(row=row, column=2, sticky="ew", padx=5, pady=5)
        return label, spin, slider

    def _on_gradient_pattern_change(self, *_):
        """Picking a named Pattern sets alpha to that preset's value, same
        "dropdown fills a field, the field stays independently editable"
        convention as Sub box dimensions' Profile -> Width/Depth."""
        name = self.gradient_pattern.get()
        if name == CUSTOM_PROFILE:
            return
        self.gradient_alpha.set(GRADIENT_PATTERN_ALPHA[name])
        self._on_change()

    def _on_gradient_alpha_edited(self):
        """Hand-editing alpha (spin or slider) resets Pattern to custom,
        same convention as Sub box dimensions' _on_dimension_edited."""
        self.gradient_pattern.set(CUSTOM_PROFILE)
        self._on_change()

    @staticmethod
    def _set_widgets_visible(widgets, visible):
        """Shows/hides `widgets` via grid()/grid_remove(), preserving each
        widget's original grid position (grid_remove keeps it cached)."""
        for w in widgets:
            w.grid() if visible else w.grid_remove()

    @staticmethod
    def _bind_live_edit(widget, callback):
        """Runs `callback` as the user types (KeyRelease) and when the
        field loses focus (FocusOut) -- the pair every plain Entry in
        this app uses to react to typed input."""
        widget.bind("<KeyRelease>", lambda e: callback())
        widget.bind("<FocusOut>", lambda e: callback())

    def _help_icon(self, parent, row, col, text, columnspan=1):
        """A small '?' that shows `text` as a tooltip on hover, instead of
        a permanent wrapped paragraph eating vertical space."""
        lbl = ttk.Label(parent, text=" ? ", foreground="#666", relief="ridge", borderwidth=1,
                         cursor="question_arrow")
        lbl.grid(row=row, column=col, columnspan=columnspan, sticky="w", padx=5, pady=5)
        Tooltip(lbl, text)
        return lbl

    # --------------------------------------------------------------- taper --
    def _build_taper_panel(self):
        frm = ttk.LabelFrame(self.left_col, text="Level taper (Arc / Physical / Progressive / Hybrids only)")
        frm.pack(fill="x", padx=10, pady=5)
        self.taper_frame = frm

        ttk.Label(frm, text="Window").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.taper_window = tk.StringVar(value=LEVEL_TAPER_WINDOWS[0])
        window_cb = ttk.Combobox(frm, textvariable=self.taper_window, values=LEVEL_TAPER_WINDOWS,
                                  state="readonly", width=10)
        window_cb.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        window_cb.bind("<<ComboboxSelected>>", lambda e: self._on_taper_window_change())

        self.atten_label = ttk.Label(frm, text="Max atten (dB)")
        self.atten_label.grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.taper_max_atten = tk.DoubleVar(value=0.0)
        self.atten_spin = ttk.Spinbox(frm, from_=0.0, to=30.0, increment=0.5,
                                       textvariable=self.taper_max_atten, width=6, command=self._on_change)
        self.atten_spin.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self.atten_spin.bind("<Return>", lambda e: self._on_change())
        self.atten_spin.bind("<FocusOut>", lambda e: self._on_change())

        self.sidelobe_label = ttk.Label(frm, text="Sidelobe (dB)")
        self.sidelobe_label.grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.taper_sidelobe_db = tk.DoubleVar(value=30.0)
        self.sidelobe_spin = ttk.Spinbox(frm, from_=10.0, to=100.0, increment=1.0,
                                          textvariable=self.taper_sidelobe_db, width=6, command=self._on_change)
        self.sidelobe_spin.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self.sidelobe_spin.bind("<Return>", lambda e: self._on_change())
        self.sidelobe_spin.bind("<FocusOut>", lambda e: self._on_change())

        self._help_icon(frm, row=0, col=4,
                         text="Live gain taper, always following each sub's Gain trim -- 0 dB at the "
                              "window's peak, fading to -max atten at its minimum, shaped by the chosen "
                              "window (11 sidelobe-control windows; Uniform or 0 dB max atten = flat, no "
                              "taper). For the two Arc Hybrid topologies, the taper is computed across "
                              "columns, not individual subs -- both the front and rear sub in a column get "
                              "that column's trim. For Arc / Broadside Steering and the Arc Hybrids, the peak "
                              "follows the Steer angle (arc_steered_aim_index) instead of always sitting at "
                              "the array's physical centre -- 0° Steer keeps it centred as before. Flat Top "
                              "is a known exception "
                              "to \"monotonic taper\" — it's an amplitude-accuracy window with a small "
                              "ripple near the edges by design, so it can dip slightly past -max atten "
                              "there; that's correct for Flat Top, not a bug. Chebyshev/Taylor replace Max "
                              "atten with Sidelobe (dB): their gain trim is a literal dB of the window's own "
                              "equal-ripple amplitude shape, not the linear max-atten remap the other 9 "
                              "windows use, so the edge elements land at (Chebyshev: exactly; Taylor: "
                              "approximately) that many dB down when centred. They follow Steer the same as "
                              "the other 9 windows too, by linearly interpolating the plain centred array "
                              "instead of re-sampling a continuous formula (they have none) -- off-centre "
                              "this trades away the exact equal-ripple guarantee, same trade-off Steer's "
                              "aim-point approximation already makes for every other window. This "
                              "app has no polar/SPL prediction, so you won't see the sidelobe reduction "
                              "visually — it's standard array theory applied on faith, not a result verified "
                              "in-app.")

        is_parametric = self.taper_window.get() in PARAMETRIC_TAPER_WINDOWS
        self._set_widgets_visible((self.sidelobe_label, self.sidelobe_spin), is_parametric)
        self._set_widgets_visible((self.atten_label, self.atten_spin), not is_parametric)

        self.taper_cost_label = ttk.Label(frm, text="taper cost: -", width=48)
        self.taper_cost_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        self._help_icon(
            frm, row=1, col=4,
            text="The real-world price of this taper, not visible in a polar-prediction plot: "
                 "on-axis loss is the forward SPL you give up because a correctly steered array sums "
                 "its elements in phase, so on-axis pressure follows the *mean of the linear gains* "
                 "(taper_onaxis_loss_db in array_math.py) -- every dB of edge attenuation you dial in "
                 "for sidelobe control is a dB you don't get back as forward level, from a box that's "
                 "still costing you an amplifier channel and rigging weight. Total power is the same "
                 "idea for the incoherent power sum instead (taper_power_loss_db) -- closer to overall "
                 "amplifier/driver headroom spent than to what the room hears. Total power loss is "
                 "always the smaller of the two (less negative), since on-axis coherent summation is "
                 "hurt by tapering more than raw radiated power is. Applies to every window here, not "
                 "just Chebyshev/Taylor -- a deep Hann/Blackman taper costs the same way. Deep "
                 "sidelobe targets on a small array can cost several dB of forward level for a pattern "
                 "benefit this app can't show you (no polar/SPL prediction) -- worth cross-checking "
                 "against a prediction tool before committing a show to a heavy taper.")

    def _on_taper_window_change(self):
        """Chebyshev/Taylor need a Sidelobe (dB) parameter instead of Max
        atten -- swap which one shows in that grid cell before re-syncing
        the taper, same "show one of two mutually exclusive controls"
        pattern as Shape's Circle/Ellipse fields elsewhere in this app."""
        is_parametric = self.taper_window.get() in PARAMETRIC_TAPER_WINDOWS
        self._set_widgets_visible((self.sidelobe_label, self.sidelobe_spin), is_parametric)
        self._set_widgets_visible((self.atten_label, self.atten_spin), not is_parametric)
        self._on_change()

    def _sync_level_taper(self):
        """Keeps Gain trim live-following the Level taper window for Arc /
        Physical Horizontal Array / Progressive Arc / the two Arc
        Hybrids, the same way Delay is always live for those topologies
        -- no separate "Apply" step. For Arc and the Arc Hybrids, the
        taper's peak follows Steer's shifted aim point instead of
        staying pinned to the array's physical centre (Physical and
        Progressive have no Steer, so they always stay centred). For the
        Arc Hybrids, the window is computed across columns (n = Columns,
        not total subs) and both the front and rear sub in a column get
        that column's trim."""
        topo = self.topology.get()
        is_hybrid = topo in ARC_HYBRID_TOPOLOGIES
        if topo not in (TOPO_ARC, TOPO_PHYSICAL, TOPO_PROGRESSIVE) and not is_hybrid:
            return
        try:
            n = self.count.get()
            window = self.taper_window.get()
            max_atten = self.taper_max_atten.get()
            sidelobe_db = self.taper_sidelobe_db.get()
        except tk.TclError:
            return
        center_index = None
        if topo == TOPO_ARC or is_hybrid:
            try:
                center_index = arc_steered_aim_index(n, self.angle.get(), self.steer.get())
            except tk.TclError:
                center_index = None
        try:
            taper = level_taper_db(n, window, max_atten, center_index, sidelobe_db)
        except ValueError:
            return
        for i, db in enumerate(taper):
            targets = (i * 2, i * 2 + 1) if is_hybrid else (i,)
            for j in targets:
                if j < len(self.trim_vars):
                    self.trim_vars[j].set(round(db, 2))
        onaxis = taper_onaxis_loss_db(taper)
        power = taper_power_loss_db(taper)
        self.taper_cost_label.config(
            text=f"taper cost: {onaxis:.2f} dB on-axis, {power:.2f} dB total power (vs. uniform)")

    # --------------------------------------------------------------- units --
    def _build_units_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="Units")
        frm.pack(fill="x", padx=10, pady=5)

        ttk.Label(frm, text="Length unit").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        unit_cb = ttk.Combobox(frm, textvariable=self.unit, values=UNITS, state="readonly", width=6)
        unit_cb.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        unit_cb.bind("<<ComboboxSelected>>", lambda e: self._on_unit_change())

        self._help_icon(frm, row=0, col=2,
                         text="Applies to every length you enter: Spacing, box Width/Depth/Gap, and the "
                              "distance fields in Group, Sub → tops, and Venue → arc. Everything is still "
                              "stored and computed in metres internally — this only changes what you type "
                              "and see in those fields. Read-only results (Y column, collision/alignment/FAR "
                              "text) stay in metres.")

        ttk.Label(frm, text="X/Y convention").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.xy_convention = tk.StringVar(value=XY_LACOUSTICS)
        xy_cb = ttk.Combobox(frm, textvariable=self.xy_convention, values=XY_CONVENTIONS,
                              state="readonly", width=14)
        xy_cb.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        xy_cb.bind("<<ComboboxSelected>>", lambda e: self._on_change())

        self._help_icon(frm, row=1, col=2,
                         text=f"Which axis is which in the per-sub table's X/Y columns and Manual mode's "
                              f"typed X/Y fields. \"{XY_LACOUSTICS}\" (default): Y = depth, into the room "
                              f"(front-to-back); X = lateral, across the room -- matching L-Acoustics' own "
                              f"layout tools. \"{XY_DNB}\": swapped -- X = depth, into the room; Y = lateral, "
                              f"across the room -- this app's original convention. Purely a labelling/entry "
                              f"convention -- the underlying geometry and delay math are identical either "
                              f"way, only which column means which physical direction changes.")

    def _dnb_mode(self) -> bool:
        return self.xy_convention.get() == XY_DNB

    def _manual_depth_vars(self):
        """Whichever of manual_x_vars/manual_y_vars currently represents
        depth (front-to-back, into the room), per the X/Y convention."""
        return self.manual_x_vars if self._dnb_mode() else self.manual_y_vars

    def _manual_lateral_vars(self):
        """Whichever of manual_x_vars/manual_y_vars currently represents
        lateral (side-to-side, across the room), per the X/Y convention."""
        return self.manual_y_vars if self._dnb_mode() else self.manual_x_vars

    def _manual_note_text(self):
        depth_col, lateral_col = ("X", "Y") if self._dnb_mode() else ("Y", "X")
        return (f"Place each sub freely: type {depth_col} (depth, front-to-back — larger/less-negative is "
                f"closer to the audience) and {lateral_col} (lateral, informational only) directly. Delay is "
                f"derived, not typed — the rearmost placed sub (smallest {depth_col}) is the 0 ms reference, "
                "same plane-wave-towards-the-audience logic as End-Fire, generalised to free 2D placement. "
                "Gain trim and Polarity stay directly editable.")

    def _on_unit_change(self):
        self._refresh_unit_displays()
        self._on_change()

    def _make_length_field(self, parent, meters_var, row, col, on_commit=None, width=8):
        """Spinbox with up/down arrows showing meters_var converted to the
        globally selected unit; edits convert back and write meters_var
        (the canonical value every calculation uses). Registered so
        switching units rescales the display without touching meters_var."""
        display_var = tk.DoubleVar()
        spin = ttk.Spinbox(parent, textvariable=display_var, width=width, from_=0.0, to=100000.0, increment=1.0)
        spin.grid(row=row, column=col, sticky="w", padx=5, pady=5)

        def commit(*_):
            scale = UNIT_SCALE[self.unit.get()]
            try:
                # Quantize to the nearest mm regardless of the entry unit, so typing
                # e.g. "1.23456" doesn't smuggle sub-mm precision past the display.
                meters_var.set(round(display_var.get() * scale, 3))
            except tk.TclError:
                return
            self._refresh_unit_displays()
            (on_commit or self._on_change)()

        spin.config(command=commit)
        self._bind_live_edit(spin, commit)
        self._length_fields.append((meters_var, display_var, spin))
        return spin

    def _refresh_unit_displays(self):
        unit = self.unit.get()
        scale = UNIT_SCALE[unit]
        incr = UNIT_INCREMENT[unit]
        decimals = UNIT_DECIMALS[unit]
        for meters_var, display_var, spin in self._length_fields:
            try:
                display_var.set(round(meters_var.get() / scale, decimals))
            except tk.TclError:
                pass
            spin.config(increment=incr)

    # -------------------------------------------------------------- group --
    def _build_group_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="Group (applied to all subs)")
        frm.pack(fill="x", padx=10, pady=5)

        self.group_delay = tk.DoubleVar(value=0.0)
        self._labeled_slider(frm, "Group delay (ms)", self.group_delay, 0.0, 1000.0, row=0, increment=0.1)

        ttk.Label(frm, text="Distance").grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self.group_delay_m = tk.DoubleVar(value=0.0)
        self._make_length_field(frm, self.group_delay_m, row=0, col=4, on_commit=self._on_group_distance_change)

        ttk.Label(frm, text="Group polarity").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.group_polarity = tk.StringVar(value="Normal")
        pol_cb = ttk.Combobox(frm, textvariable=self.group_polarity, values=["Normal", "Inverted"],
                               state="readonly", width=10)
        pol_cb.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        pol_cb.bind("<<ComboboxSelected>>", lambda e: self._on_change())

        self.group_level = tk.DoubleVar(value=0.0)
        self._labeled_slider(frm, "Group level (dB)", self.group_level, -40.0, 18.0, row=2, increment=0.1)

        self._help_icon(frm, row=2, col=3,
                         text="Group delay adds to every sub's Delay to make \"Delay + Group\" — enter it "
                              "directly in ms or as an equivalent distance (e.g. the subs sit this much "
                              "closer to FOH than the mains); the two stay in sync via the speed of sound at "
                              "the current temperature (Environment panel). Group polarity flips every sub's "
                              "Polarity (and the OSC polarity value) on top of whatever the topology computed. "
                              "Group level adds to every sub's Gain trim to make \"Gain + Group\", and is what "
                              "the OSC gain/gain_total_db values reflect — e.g. trimming the whole sub array "
                              "relative to the mains without touching each sub's individual trim.")

        ttk.Label(frm, textvariable=self.prealign_note_var, foreground="#c60", font=("Segoe UI", 8)).grid(
            row=3, column=0, columnspan=5, sticky="w", padx=5, pady=(0, 5))

        frm.grid_columnconfigure(2, weight=1)

    def _group_inverted(self) -> bool:
        return self.group_polarity.get() == "Inverted"

    def _sync_group_distance_from_delay(self):
        try:
            d = distance_for_delay_ms(self.group_delay.get(), self._speed_of_sound())
        except tk.TclError:
            return
        self.group_delay_m.set(round(d, 3))

    def _on_group_distance_change(self, *_):
        try:
            ms = delay_ms_for_distance(self.group_delay_m.get(), self._speed_of_sound())
        except tk.TclError:
            return
        self.group_delay.set(round(ms, 4))
        self._on_change()

    # ---------------------------------------------------- pre-alignment --
    def _build_prealign_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="Pre-alignment delay lookup")
        frm.pack(fill="x", padx=10, pady=5)

        try:
            self.prealign_entries = load_prealign_entries()
        except PrealignDataError as e:
            # A bad polarity value in the CSV must be loud (see
            # prealign_profiles.py's docstring), but loud shouldn't mean
            # "crash the whole app before a show" -- show the error in
            # place of the controls instead, and leave the rest of the
            # app usable.
            self.prealign_entries = []
            ttk.Label(frm, text=f"⚠ prealign_delays.csv error:\n{e}", foreground="#c33",
                      wraplength=340, justify="left").pack(fill="x", padx=5, pady=5)
            return

        main_systems = sorted({e[0] for e in self.prealign_entries})

        ttk.Label(frm, text="Main system").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.prealign_main = tk.StringVar(value=main_systems[0] if main_systems else "")
        main_cb = ttk.Combobox(frm, textvariable=self.prealign_main, values=main_systems,
                                state="readonly", width=12)
        main_cb.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        main_cb.bind("<<ComboboxSelected>>", lambda e: self._on_prealign_main_change())

        ttk.Label(frm, text="Sub preset").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.prealign_sub = tk.StringVar()
        self.prealign_sub_cb = ttk.Combobox(frm, textvariable=self.prealign_sub, state="readonly", width=18)
        self.prealign_sub_cb.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self.prealign_sub_cb.bind("<<ComboboxSelected>>", lambda e: self._update_prealign_readout())

        self.prealign_main_label = ttk.Label(frm, text="Main: -", width=24)
        self.prealign_main_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        self.prealign_sub_label = ttk.Label(frm, text="Sub: -", width=38)
        self.prealign_sub_label.grid(row=1, column=2, columnspan=2, sticky="w", padx=5, pady=2)

        self.prealign_use_btn = ttk.Button(frm, text="Use → Group delay", command=self._use_prealign_delay)
        self.prealign_use_btn.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.prealign_clear_btn = ttk.Button(frm, text="Clear", command=self._clear_prealign_delay)
        self.prealign_clear_btn.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        self._help_icon(frm, row=2, col=2, columnspan=2,
                         text="Factory pre-alignment delay offsets from the L-Acoustics Drive System Preset "
                              "Guide (\"Pre-alignment delay values\", p.93) — corrections to add before your "
                              "own geometric alignment, measured with the enclosures at the same physical "
                              "location. \"Use → Group delay\" ADDS the sub-side value on top of whatever is "
                              "already in Group delay (ms) below, tracked separately and shown in orange "
                              "next to Group delay above (\"includes +X ms pre-alignment...\") so you always "
                              "see exactly what this panel contributed; \"Clear\" removes only that "
                              "contribution, leaving any group delay you dialled in by hand untouched. Often "
                              "the sub-side value is 0 ms (the correction lands on the main system instead) "
                              "— \"Use\" still confirms that and the note explains where the remaining delay "
                              "belongs. The main-side value is shown for reference "
                              "only — it belongs on the main system's own processor, which this app doesn't "
                              "control. Two separate coloured tags: green Positive (+) / red Negative (−) is "
                              "that system's own factory polarity — the obvious pass/fail signal, straight "
                              "from the CSV's main_polarity/sub_polarity columns (\"Use\" never applies this "
                              "for you — a Negative sub combo adds a ⚠ warning to the Group delay note "
                              "instead, telling you to flip Group polarity to Inverted by hand). A second, "
                              "bracketed detail — Cardioid/Extended cardioid/Noise Control — appears only for "
                              "presets where one enclosure *within* that cluster is reversed internally by "
                              "the preset itself; independent of the polarity tag, and always informational, "
                              "since this app's single Group polarity switch can't represent reversing just "
                              "one element inside the sub cluster. Small seed dataset (K1 family only, from "
                              "prealign_delays.csv) — extend the CSV with more combos as you confirm them "
                              "from the guide.")

        self._on_prealign_main_change()

    def _prealign_subs_for_main(self, main_system):
        return [e for e in self.prealign_entries if e[0] == main_system]

    def _on_prealign_main_change(self):
        entries = self._prealign_subs_for_main(self.prealign_main.get())
        subs = [e[1] for e in entries]
        self.prealign_sub_cb.config(values=subs)
        self.prealign_sub.set(subs[0] if subs else "")
        self._update_prealign_readout()

    def _current_prealign_entry(self):
        for e in self.prealign_entries:
            if e[0] == self.prealign_main.get() and e[1] == self.prealign_sub.get():
                return e
        return None

    @staticmethod
    def _prealign_polarity_color(polarity: str) -> str:
        return "#c33" if polarity == "negative" else "#0a6"

    def _update_prealign_readout(self):
        entry = self._current_prealign_entry()
        if entry is None:
            self.prealign_main_label.config(text="Main: -", foreground="black")
            self.prealign_sub_label.config(text="Sub: -", foreground="black")
            return
        main_sys, sub_sys, main_ms, sub_ms, main_pol, sub_pol, main_config, sub_config, _notes = entry
        main_pol_tag = POLARITY_LABELS.get(main_pol, main_pol)
        sub_pol_tag = POLARITY_LABELS.get(sub_pol, sub_pol)
        # Polarity (Positive/Negative) drives the colour -- that's the obvious
        # pass/fail signal. Config (cardioid variant) is a secondary detail,
        # appended only when it's not the plain "standard" case.
        main_suffix = f", {CONFIG_LABELS.get(main_config, main_config)}" if main_config != "standard" else ""
        sub_suffix = f", {CONFIG_LABELS.get(sub_config, sub_config)}" if sub_config != "standard" else ""
        self.prealign_main_label.config(
            text=f"Main: {main_sys} = {main_ms:.2f} ms  [{main_pol_tag}{main_suffix}]",
            foreground=self._prealign_polarity_color(main_pol))
        self.prealign_sub_label.config(
            text=f"Sub: {sub_sys} = {sub_ms:.2f} ms  [{sub_pol_tag}{sub_suffix}]",
            foreground=self._prealign_polarity_color(sub_pol))

    def _set_prealign_note(self, main_sys=None, sub_sys=None, main_ms=None, sub_pol=None):
        if not self.prealign_active:
            self.prealign_note_var.set("")
            return
        sign = "+" if self.prealign_contribution_ms >= 0 else ""
        note = f"includes {sign}{self.prealign_contribution_ms:.2f} ms pre-alignment ({main_sys} + {sub_sys})"
        if main_ms:
            # Most of the time the correction lands on the main system, not the
            # subs -- say so explicitly rather than letting a 0.00 ms line here
            # read as "the Use click did nothing".
            note += f" — remaining {main_ms:.2f} ms belongs on {main_sys}'s own delay, not controlled here"
        if sub_pol == "negative":
            # "Use" only ever writes delay -- it never touches Group polarity,
            # so a sub-side Negative combo needs a loud, separate reminder or
            # it's silently missed.
            note += " — ⚠ Sub polarity NEGATIVE: set Group polarity to Inverted yourself, this isn't applied"
        self.prealign_note_var.set(note)

    def _use_prealign_delay(self):
        entry = self._current_prealign_entry()
        if entry is None:
            return
        main_sys, sub_sys, main_ms, sub_ms, _main_pol, sub_pol, _main_config, _sub_config, _notes = entry
        delta = sub_ms - self.prealign_contribution_ms
        try:
            self.group_delay.set(round(self.group_delay.get() + delta, 4))
        except tk.TclError:
            return
        self.prealign_contribution_ms = sub_ms
        self.prealign_active = True
        self._set_prealign_note(main_sys, sub_sys, main_ms, sub_pol)
        self._on_change()

    def _clear_prealign_delay(self):
        if not self.prealign_active:
            return
        try:
            self.group_delay.set(round(self.group_delay.get() - self.prealign_contribution_ms, 4))
        except tk.TclError:
            pass
        self.prealign_contribution_ms = 0.0
        self.prealign_active = False
        self._set_prealign_note()
        self._on_change()

    def _dsp_sample_rate(self) -> int:
        return DSP_CLOCK_RATES[self.dsp_clock.get()]

    # --------------------------------------------------------- alignment --
    def _build_alignment_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="Sub → tops alignment wizard")
        frm.pack(fill="x", padx=10, pady=5)

        ttk.Label(frm, text="Mains dist. to FOH").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.align_mains_distance = tk.DoubleVar(value=0.0)
        self._make_length_field(frm, self.align_mains_distance, row=0, col=1,
                                 on_commit=self._update_alignment_wizard)

        ttk.Label(frm, text="Mains delay (ms)").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.align_mains_delay = tk.DoubleVar(value=0.0)
        e2 = ttk.Entry(frm, textvariable=self.align_mains_delay, width=10)
        e2.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self._bind_live_edit(e2, self._update_alignment_wizard)

        ttk.Label(frm, text="Sub dist. to FOH").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.align_sub_distance = tk.DoubleVar(value=0.0)
        self._make_length_field(frm, self.align_sub_distance, row=1, col=1,
                                 on_commit=self._update_alignment_wizard)

        self.align_corrected_label = ttk.Label(frm, text="", width=28)
        self.align_corrected_label.grid(row=1, column=2, columnspan=2, sticky="w", padx=5, pady=5)

        self.align_result_label = ttk.Label(frm, text="required group delay: -", width=42)
        self.align_result_label.grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        self.align_set_btn = ttk.Button(frm, text="Set group delay", command=self._set_group_delay_from_alignment)
        self.align_set_btn.grid(row=3, column=0, sticky="w", padx=5, pady=5)

        self._help_icon(frm, row=3, col=1,
                         text="Distances are measured from each array's reference point (subs: the front "
                              "row) to FOH / the listening position. \"Mains delay\" is whatever electrical "
                              "delay is already dialled into the mains, if any — 0 if none. Required group "
                              "delay = mains delay + (mains distance − sub distance) / speed of sound "
                              "(Environment panel temperature). A negative result means the subs are already "
                              "farther from FOH than the mains — delay the mains instead; \"Set group "
                              "delay\" clamps to 0. If Acoustic centre offset is enabled (Sub box dimensions "
                              "panel), \"Sub dist. to FOH\" is corrected by that amount before this "
                              "calculation — enter the distance to the cabinet as you'd measure it.")

        frm.grid_columnconfigure(4, weight=1)

    def _required_group_delay(self):
        try:
            return required_group_delay_ms(
                self.align_mains_distance.get(), self.align_mains_delay.get(),
                self._sub_distance_to_foh(), self._speed_of_sound())
        except tk.TclError:
            return None

    def _update_alignment_wizard(self):
        try:
            if self.acoustic_center_enabled.get():
                corrected = self._sub_distance_to_foh()
                self.align_corrected_label.config(text=f"→ acoustic centre corrected: {corrected:.2f} m")
            else:
                self.align_corrected_label.config(text="")
        except tk.TclError:
            self.align_corrected_label.config(text="")

        result = self._required_group_delay()
        if result is None:
            self.align_result_label.config(text="required group delay: -")
        elif result < 0:
            self.align_result_label.config(
                text=f"required group delay: {result:.2f} ms (negative — delay the mains instead)")
        else:
            self.align_result_label.config(text=f"required group delay: {result:.2f} ms")

    def _set_group_delay_from_alignment(self):
        result = self._required_group_delay()
        if result is None:
            return
        self.group_delay.set(max(0.0, round(result, 4)))
        self._on_change()

    # -------------------------------------------------------- environment --
    def _build_environment_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="Environment")
        frm.pack(fill="x", padx=10, pady=5)

        self.temp_c = tk.DoubleVar(value=20.0)
        self._labeled_slider(frm, "Temperature (°C)", self.temp_c, -10.0, 40.0, row=0, increment=0.5)

        self.speed_of_sound_label = ttk.Label(frm, text="", width=14)
        self.speed_of_sound_label.grid(row=0, column=3, sticky="w", padx=5, pady=5)

        self.humidity = tk.DoubleVar(value=50.0)
        self._labeled_slider(frm, "Relative humidity (%)", self.humidity, 0.0, 100.0, row=1, increment=1.0)

        self.altitude = tk.DoubleVar(value=0.0)
        self._labeled_slider(frm, "Altitude (m)", self.altitude, 0.0, 5000.0, row=2, increment=10.0)

        self._help_icon(frm, row=0, col=4,
                         text="Sets the speed of sound used everywhere (delay math, wavelength readouts, "
                              "group delay ↔ distance), via the Cramer (1993) equation — temperature, "
                              "humidity and altitude (through the resulting air pressure), accurate to "
                              "<=300 ppm within 0-30°C / 75-102 kPa. Altitude uses a standard-atmosphere "
                              "pressure model, not today's actual weather.")

        frm.grid_columnconfigure(2, weight=1)

    def _speed_of_sound(self) -> float:
        return speed_of_sound(self.temp_c.get(), self.humidity.get(), self.altitude.get())

    def _update_speed_of_sound(self):
        try:
            c = self._speed_of_sound()
        except tk.TclError:
            return
        self.speed_of_sound_label.config(text=f"c = {c:.2f} m/s")

    # ------------------------------------------------------------- clock --
    def _build_clock_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="DSP clock")
        frm.pack(fill="x", padx=10, pady=5)

        self.dsp_clock = tk.StringVar(value="96 kHz (2 FS)")
        clock_cb = ttk.Combobox(frm, textvariable=self.dsp_clock, values=DSP_CLOCKS, state="readonly", width=14)
        clock_cb.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        clock_cb.bind("<<ComboboxSelected>>", lambda e: self._on_change())

        ttk.Label(frm, text="Show delay as").grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self.delay_unit = tk.StringVar(value="ms")
        delay_unit_cb = ttk.Combobox(frm, textvariable=self.delay_unit, values=["ms", "samples"],
                                      state="readonly", width=8)
        delay_unit_cb.grid(row=0, column=2, sticky="w", padx=5, pady=5)
        delay_unit_cb.bind("<<ComboboxSelected>>", lambda e: self._on_change())

        self._help_icon(frm, row=0, col=3,
                         text="This sample rate is what the per-sub table's Delay and Delay + Group columns "
                              "convert to when \"Show delay as\" is set to samples -- switch it to ms to see "
                              "the same values as milliseconds instead. Doesn't affect anything actually sent "
                              "over OSC, which always carries ms regardless of this display choice.")

    # --------------------------------------------------------- dimensions --
    def _build_dimensions_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="Sub box dimensions")
        frm.pack(fill="x", padx=10, pady=5)
        self.dimensions_frame = frm

        self.sub_profiles = {name: (w, d) for name, w, d in load_profiles()}

        ttk.Label(frm, text="Profile").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        default_profile = "L-Acoustics KS28 (Horizontal)" if "L-Acoustics KS28 (Horizontal)" in \
            self.sub_profiles else CUSTOM_PROFILE
        self.sub_profile = tk.StringVar(value=default_profile)
        profile_cb = ttk.Combobox(frm, textvariable=self.sub_profile,
                                   values=[CUSTOM_PROFILE] + list(self.sub_profiles), state="readonly", width=28)
        profile_cb.grid(row=0, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        profile_cb.bind("<<ComboboxSelected>>", self._on_profile_change)

        self._help_icon(frm, row=0, col=3,
                         text="Pick a profile to fill Width/Depth from a known box, or edit either directly "
                              "(resets Profile to \"custom\"). Width applies to Arc / Broadside Steering, "
                              "Physical Horizontal Array, Progressive Arc, and Focus Point (boxes side by "
                              "side); depth applies to End-Fire and Gradient (boxes front to back). The two "
                              "Arc Hybrids check both: width against Spacing (column-to-column) and depth "
                              "against Row spacing (front/rear pair). \"Set min spacing\" sets Spacing to that "
                              "dimension exactly (boxes touching); \"Set spacing (+ gap)\" adds the gap value "
                              "on top, for cable/rigging clearance -- both only ever touch Spacing, not Row "
                              "spacing, and are no-ops for Physical Horizontal Array/Progressive Arc, which "
                              "have no Spacing field. Profiles load from sub_profiles.csv.")

        ttk.Label(frm, text="Width").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.box_width = tk.DoubleVar(value=1.340)
        self._make_length_field(frm, self.box_width, row=1, col=1, on_commit=self._on_dimension_edited)

        ttk.Label(frm, text="Depth").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.box_depth = tk.DoubleVar(value=0.702)
        self._make_length_field(frm, self.box_depth, row=2, col=1, on_commit=self._on_dimension_edited)

        ttk.Label(frm, text="Gap between cabinets").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.cabinet_gap = tk.DoubleVar(value=0.0)
        self._make_length_field(frm, self.cabinet_gap, row=3, col=1, on_commit=self._on_change)

        self.collision_label = ttk.Label(frm, text="-", width=32)
        self.collision_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.set_min_spacing_btn = ttk.Button(frm, text="Set min spacing", command=self._set_min_spacing)
        self.set_min_spacing_btn.grid(row=1, column=2, sticky="w", padx=5, pady=5)

        self.set_spacing_gap_btn = ttk.Button(frm, text="Set spacing (+ gap)", command=self._set_spacing_with_gap)
        self.set_spacing_gap_btn.grid(row=3, column=2, sticky="w", padx=5, pady=5)

        self.acoustic_center_enabled = tk.BooleanVar(value=False)
        ac_chk = ttk.Checkbutton(frm, text="Acoustic centre offset", variable=self.acoustic_center_enabled,
                                  command=self._on_change)
        ac_chk.grid(row=5, column=0, sticky="w", padx=5, pady=5)
        self.acoustic_center_offset = tk.DoubleVar(value=0.30)
        self._make_length_field(frm, self.acoustic_center_offset, row=5, col=1, on_commit=self._on_change)

        self._help_icon(frm, row=5, col=2,
                         text="Merlijn van Veen's low-frequency acoustic centre research: a sealed/vented "
                              "sub's true radiating point may sit outside the enclosure, in front of it, "
                              "below ~100 Hz — not settled physics, but a plausible, documented correction. "
                              "When enabled, this offset is subtracted from \"Sub dist. to FOH\" in the Sub → "
                              "tops alignment wizard below (the sub's true acoustic distance is shorter than "
                              "its cabinet-measured distance by this amount). It does not affect inter-sub "
                              "delay/spacing math — a uniform forward shift of every sub changes none of the "
                              "path-length *differences* between them, only distance to an external "
                              "reference like FOH.")

    def _sub_distance_to_foh(self) -> float:
        """align_sub_distance, corrected for acoustic center offset if enabled."""
        d = self.align_sub_distance.get()
        if self.acoustic_center_enabled.get():
            d -= self.acoustic_center_offset.get()
        return d

    def _on_profile_change(self, *_):
        name = self.sub_profile.get()
        if name == CUSTOM_PROFILE:
            return
        width, depth = self.sub_profiles[name]
        self.box_width.set(width)
        self.box_depth.set(depth)
        self._refresh_unit_displays()
        self._on_change()

    def _on_dimension_edited(self):
        self.sub_profile.set(CUSTOM_PROFILE)
        self._on_change()

    def _relevant_box_dimension(self):
        """(dimension_m, name) for whichever box dimension the active
        topology's spacing axis uses, or (None, None) in Manual mode. For
        the two Arc Hybrid topologies this is the column (width) axis
        only -- see _update_collision_check for the row (depth) axis
        check, which those two also need and the other topologies don't."""
        topo = self.topology.get()
        if topo in (TOPO_ARC, TOPO_PHYSICAL, TOPO_PROGRESSIVE, TOPO_FOCUS) or topo in ARC_HYBRID_TOPOLOGIES:
            return self.box_width.get(), "width"
        if topo in (TOPO_END_FIRE, TOPO_GRADIENT):
            return self.box_depth.get(), "depth"
        return None, None

    def _effective_spacing_m(self):
        """Spacing the collision check compares against: the Spacing
        field for topologies that use it, or the smallest adjacent-element
        gap for the topologies that place elements on a curve instead
        (Physical Horizontal Array, Progressive Arc), which have no
        Spacing input of their own. Physical Horizontal Array's plain
        Circle shape uses the exact constant-chord formula (verified
        against S.A.D.'s tutorial); Ellipse and Progressive Arc don't have
        a constant chord (the gap varies along the array), so they measure
        the actual placed layout directly and take its minimum -- the
        worst-case gap is what a collision check needs."""
        topo = self.topology.get()
        if topo == TOPO_PHYSICAL and self.shape.get() == SHAPE_CIRCLE:
            return physical_arc_chord_spacing(self.count.get(), self.radius.get(), self.angle.get())
        if topo in (TOPO_PHYSICAL, TOPO_PROGRESSIVE):
            return min_adjacent_chord(self._compute_physical_layout())
        return self.spacing.get()

    @staticmethod
    def _clearance_text(spacing, box_dim, dim_name):
        clearance = spacing_clearance_m(spacing, box_dim)
        if clearance < 0:
            return f"⚠ {box_dim:.2f} m {dim_name} > {spacing:.2f} m spacing (by {-clearance:.2f} m)"
        return f"OK — {clearance:.2f} m clearance ({dim_name})"

    def _grating_lobe_text(self):
        try:
            steer = self.steer.get()
            d_max = grating_lobe_max_spacing_m(self.freq_high.get(), self._speed_of_sound(), steer)
            spacing = self.spacing.get()
        except tk.TclError:
            return "-"
        if d_max is None:
            return "-"
        margin = d_max - spacing
        if margin < 0:
            return (f"⚠ grating-lobe risk: {spacing:.2f} m spacing > {d_max:.2f} m limit "
                    f"at Steer {steer:.0f}° (by {-margin:.2f} m)")
        return f"OK — grating-lobe limit {d_max:.2f} m at Steer {steer:.0f}° ({margin:.2f} m headroom)"

    def _update_collision_check(self):
        if self.topology.get() in ARC_HYBRID_TOPOLOGIES:
            # Two independent physical checks here, not one: column spacing
            # (boxes side by side, like Arc) and row spacing (front/rear
            # pair depth, like End-Fire/Gradient) both need clearance.
            try:
                col_text = self._clearance_text(self.spacing.get(), self.box_width.get(), "width")
                row_text = self._clearance_text(self.row_spacing.get(), self.box_depth.get(), "depth")
            except tk.TclError:
                self.collision_label.config(text="-")
                return
            self.collision_label.config(text=f"col: {col_text}  |  row: {row_text}")
            return
        try:
            box_dim, dim_name = self._relevant_box_dimension()
        except tk.TclError:
            self.collision_label.config(text="-")
            return
        if box_dim is None:
            self.collision_label.config(text="n/a in Manual mode")
            return
        try:
            spacing = self._effective_spacing_m()
        except tk.TclError:
            self.collision_label.config(text="-")
            return
        if spacing is None:
            self.collision_label.config(text="-")
            return
        self.collision_label.config(text=self._clearance_text(spacing, box_dim, dim_name))

    def _set_min_spacing(self):
        if self.topology.get() in (TOPO_PHYSICAL, TOPO_PROGRESSIVE):
            return  # no Spacing field to set -- spacing is a consequence of Radius/Arc/count here
        try:
            box_dim, _ = self._relevant_box_dimension()
        except tk.TclError:
            return
        if box_dim is None:
            return
        self.spacing.set(round(box_dim, 3))
        self._refresh_unit_displays()
        self._on_change()

    def _set_spacing_with_gap(self):
        if self.topology.get() in (TOPO_PHYSICAL, TOPO_PROGRESSIVE):
            return
        try:
            box_dim, _ = self._relevant_box_dimension()
            gap = self.cabinet_gap.get()
        except tk.TclError:
            return
        if box_dim is None:
            return
        self.spacing.set(round(box_dim + gap, 3))
        self._refresh_unit_displays()
        self._on_change()

    # -------------------------------------------------------------- venue --
    def _build_venue_panel(self):
        frm = ttk.LabelFrame(self.right_col, text="Venue → arc (FAR)")
        frm.pack(fill="x", padx=10, pady=5)
        self.venue_frame = frm

        ttk.Label(frm, text="Length").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.venue_length = tk.DoubleVar(value=50.0)
        self._make_length_field(frm, self.venue_length, row=0, col=1, on_commit=self._update_venue_far, width=8)

        ttk.Label(frm, text="Width").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.venue_width = tk.DoubleVar(value=25.0)
        self._make_length_field(frm, self.venue_width, row=0, col=3, on_commit=self._update_venue_far, width=8)

        self.venue_far_label = ttk.Label(frm, text="FAR: -  arc: -", width=22)
        self.venue_far_label.grid(row=0, column=4, sticky="w", padx=5, pady=5)

        self.set_arc_btn = ttk.Button(frm, text="Set arc", command=self._set_arc_from_venue)
        self.set_arc_btn.grid(row=0, column=5, sticky="w", padx=5, pady=5)

        self._help_icon(frm, row=0, col=6,
                         text="Length = throw/depth (front-to-back), width = coverage (side-to-side). "
                              "FAR = length / width; \"Set arc\" applies the solved Angle to whichever "
                              "angle-based topology is already active (Arc / Broadside Steering, either Arc "
                              "Hybrid, Physical Horizontal Array, Progressive Arc), or switches to Arc / "
                              "Broadside Steering first if not (End-Fire, Gradient, Focus Point, or Manual, "
                              "none of which have an Angle that means the same thing). For a Shape = Ellipse "
                              "topology, it solves venues wider than they are deep (FAR < 1) too -- Angle "
                              "pins at 180° instead of the usual arc = 2·asin(1/FAR), which has no solution "
                              "there (see the Ellipse ratio row below for that case's other half).")

        self.venue_ellipse_label = ttk.Label(frm, text="ellipse ratio: -", width=22)
        self.venue_ellipse_label.grid(row=1, column=4, sticky="w", padx=5, pady=5)

        self.use_venue_ellipse_btn = ttk.Button(frm, text="Use", command=self._use_venue_ellipse_ratio)
        self.use_venue_ellipse_btn.grid(row=1, column=5, sticky="w", padx=5, pady=5)

        self.venue_ellipse_help = self._help_icon(
            frm, row=1, col=6,
            text="Ellipse ratio implied by this venue's proportions (ellipse_ratio_from_far in "
                 "array_math.py) -- 1.0 at FAR >= 1 (the plain circle already covers those "
                 "venues fine) shrinking below 1 as the room gets wider than it is deep, "
                 "continuous with \"Set arc\"'s own Angle = 180° pin at FAR < 1. Independent "
                 "of \"Set arc\" -- \"Use\" only ever touches Ellipse ratio, never Angle, so "
                 "you can apply one without the other. Only shown for a Shape = Ellipse "
                 "topology (Physical Horizontal Array, Arc / Broadside Steering, or either "
                 "Arc Hybrid).")

    def _venue_far_arc(self):
        try:
            far = far_from_venue(self.venue_length.get(), self.venue_width.get())
        except tk.TclError:
            return None, None
        return far, arc_from_far(far)

    def _venue_is_ellipse(self) -> bool:
        return self.topology.get() in ELLIPSE_TOPOLOGIES and self.shape.get() == SHAPE_ELLIPSE

    def _update_venue_far(self):
        far, arc = self._venue_far_arc()
        is_ellipse = self._venue_is_ellipse()
        if far is None:
            self.venue_far_label.config(text="FAR: -  arc: -")
        elif arc is None and is_ellipse:
            # The plain circle has no solution below FAR = 1, but Ellipse mode
            # does (angle pins at 180 deg, Ellipse ratio flattens instead) --
            # show that instead of a bare "n/a" here, or this label would
            # contradict what "Set arc" is about to actually do.
            ellipse_arc = angle_from_far_ellipse(far)
            self.venue_far_label.config(text=f"FAR: {far:.2f}  arc: {ellipse_arc:.1f}°")
        elif arc is None:
            self.venue_far_label.config(text=f"FAR: {far:.2f}  arc: n/a")
        else:
            self.venue_far_label.config(text=f"FAR: {far:.2f}  arc: {arc:.1f}°")

        if is_ellipse:
            ratio = ellipse_ratio_from_far(far)
            self.venue_ellipse_label.config(
                text=f"ellipse ratio: {ratio:.3f}" if ratio is not None else "ellipse ratio: -")

    def _set_arc_from_venue(self):
        """Applies the venue-solved arc angle to whichever topology is
        already active, if that topology's Angle means an actual
        coverage arc (ANGLE_TOPOLOGIES: Arc / Broadside Steering, either
        Arc Hybrid, Physical Horizontal Array, Progressive Arc). Only
        topology-switches (to Arc / Broadside Steering, the old default)
        when starting from something with no Angle at all (End-Fire,
        Gradient, Focus Point, Manual). This used to always force Arc /
        Broadside Steering unconditionally, which silently discarded an
        Arc Hybrid selection (and its Row spacing) every time -- fixed
        so "Set arc" no longer knocks you out of a topology you were
        already on, Physical Horizontal Array and Progressive Arc
        included (both also need their own Radius, but that's a
        separate, already-set field -- no reason to abandon them for it).

        Only ever touches Angle -- for a Shape = Ellipse topology, it
        uses angle_from_far_ellipse instead of the plain circle's
        arc_from_far so it still has an answer for FAR < 1 (a venue
        wider than it is deep, where the circle has none), but Ellipse
        ratio itself is a separate action -- see "Use" below -- so the
        two can be applied independently (e.g. dial in Angle by hand but
        still want the venue-implied ratio, or vice versa)."""
        far, arc = self._venue_far_arc()
        if self._venue_is_ellipse():
            arc = angle_from_far_ellipse(far)
        if arc is None:
            return
        if self.topology.get() not in ANGLE_TOPOLOGIES:
            self.topology.set(TOPO_ARC)
            self._on_topology_change()
        self.angle.set(round(min(arc, 180.0), 1))
        self._on_change()

    def _use_venue_ellipse_ratio(self):
        """Applies the venue-solved Ellipse ratio (ellipse_ratio_from_far)
        to whichever Ellipse-capable topology is active, independently of
        "Set arc" above -- see its docstring for why they're separate."""
        far, _ = self._venue_far_arc()
        ratio = ellipse_ratio_from_far(far)
        if ratio is None:
            return
        self.ellipse_ratio.set(round(ratio, 3))
        self._on_change()

    # --------------------------------------------------------- bandwidth --
    def _build_bandwidth_panel(self):
        frm = ttk.LabelFrame(self.left_col, text="Sub bandwidth → optimum spacing")
        frm.pack(fill="x", padx=10, pady=5)
        self.bandwidth_frame = frm

        ttk.Label(frm, text="High (Hz)").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.freq_high = tk.DoubleVar(value=60.0)
        e_high = ttk.Entry(frm, textvariable=self.freq_high, width=8)
        e_high.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self._bind_live_edit(e_high, self._on_change)

        self.optimum_label = ttk.Label(frm, text="optimum spacing: -", width=22)
        self.optimum_label.grid(row=0, column=2, sticky="w", padx=5, pady=5)

        self.use_optimum_btn = ttk.Button(frm, text="Use", command=self._use_optimum_spacing)
        self.use_optimum_btn.grid(row=0, column=3, sticky="w", padx=5, pady=5)

        self._help_icon(frm, row=0, col=4,
                         text="Optimum spacing = fraction of a wavelength at the top of the passband "
                              "(¼λ for End-Fire/Gradient, ½λ for Arc / Broadside Steering and the two Arc "
                              "Hybrids, applied to their column spacing) — the S.A.D. rule of thumb.")

        self.row_optimum_label = ttk.Label(frm, text="optimum row spacing (¼λ): -", width=28)
        self.row_optimum_label.grid(row=1, column=2, sticky="w", padx=5, pady=5)

        self.use_row_optimum_btn = ttk.Button(frm, text="Use", command=self._use_optimum_row_spacing)
        self.use_row_optimum_btn.grid(row=1, column=3, sticky="w", padx=5, pady=5)

        self.row_optimum_help = self._help_icon(
            frm, row=1, col=4,
            text="Optimum Row spacing for the two Arc Hybrids -- always ¼ wavelength at the same "
                 "High (Hz) above, the End-Fire/Gradient rule, since Row spacing is that same "
                 "front/rear pair depth inside each column, regardless of the ½λ rule used for "
                 "the column Spacing above.")

        self.grating_lobe_label = ttk.Label(frm, text="-", width=58)
        self.grating_lobe_label.grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        self.grating_lobe_help = self._help_icon(
            frm, row=2, col=4,
            text="Steer-aware grating-lobe spacing limit: d < λ / (1 + |sin(Steer)|), the phased-"
                 "array-antenna criterion for keeping a spurious lobe out of visible space, evaluated "
                 "at High (Hz) and the array's current Steer angle -- a rigorous, steer-dependent "
                 "check alongside the ½λ rule of thumb above, which is a comb-filtering guideline "
                 "that doesn't account for Steer at all. Loosest (a full wavelength) at Steer = 0°, "
                 "tightening smoothly to ½λ at ±90°. Only accounts for Steer, not the additional "
                 "local curvature of a wide Arc angle itself -- shown for Arc / Broadside Steering and "
                 "the two Arc Hybrids, the topologies with a Steer control.")

    def _wavelength_fraction(self):
        return WAVELENGTH_FRACTION.get(self.topology.get())

    def _use_optimum_spacing(self):
        frac = self._wavelength_fraction()
        if frac is None:
            return
        try:
            opt = spacing_at_wavelength_fraction(self.freq_high.get(), self._speed_of_sound(), frac)
        except tk.TclError:
            return
        if opt is not None:
            self.spacing.set(round(opt, 3))
            self._on_change()

    def _use_optimum_row_spacing(self):
        """Row spacing is always the End-Fire/Gradient-style front/rear pair
        depth inside a column, regardless of the topology's own column
        Spacing rule (½λ for the Arc Hybrids) -- so this is always ¼λ,
        not looked up via WAVELENGTH_FRACTION/_wavelength_fraction like
        _use_optimum_spacing above."""
        try:
            opt = spacing_at_wavelength_fraction(self.freq_high.get(), self._speed_of_sound(), 0.25)
        except tk.TclError:
            return
        if opt is not None:
            self.row_spacing.set(round(opt, 3))
            self._on_change()

    # -------------------------------------------------------------- info --
    def _build_info_panel(self):
        frm = ttk.LabelFrame(self.left_col, text="Info")
        frm.pack(fill="x", padx=10, pady=5)

        self.info_length_label = ttk.Label(frm, text="array length: -", width=20)
        self.info_length_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.info_1l_label = ttk.Label(frm, text="array 1λ: -", width=16)
        self.info_1l_label.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self.info_180_label = ttk.Label(frm, text="spk dist 180°: -", width=18)
        self.info_180_label.grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.info_240_label = ttk.Label(frm, text="spk dist 240°: -", width=18)
        self.info_240_label.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self.info_360_label = ttk.Label(frm, text="spk dist 360°: -", width=18)
        self.info_360_label.grid(row=0, column=4, sticky="w", padx=5, pady=5)

        self._help_icon(frm, row=0, col=5,
                         text="array 1λ = frequency whose wavelength equals the array length (directivity "
                              "onset). spk dist NNN° = frequency at which the element spacing represents "
                              "that many degrees of phase. S.A.D.'s info panel also shows -6 dB ONAX and max "
                              "angle, which need full polar/SPL summation and are left out here by design.")

    def _update_info_panel(self):
        topo = self.topology.get()
        try:
            n = self.count.get()
            spacing = self.spacing.get()
            speed = self._speed_of_sound()
        except tk.TclError:
            return
        is_gradient = topo == TOPO_GRADIENT
        length = spacing if is_gradient else array_length(n, spacing)
        length_label = "pair depth" if is_gradient else "array length"
        self.info_length_label.config(text=f"{length_label}: {length:.2f} m")

        f_1l = freq_at_wavelength_fraction(length, speed, 1.0)
        self.info_1l_label.config(text=f"array 1λ: {f_1l:.0f} Hz" if f_1l else "array 1λ: -")

        f_180 = freq_at_wavelength_fraction(spacing, speed, 0.5)
        f_240 = freq_at_wavelength_fraction(spacing, speed, 2.0 / 3.0)
        f_360 = freq_at_wavelength_fraction(spacing, speed, 1.0)
        self.info_180_label.config(text=f"spk dist 180°: {f_180:.0f} Hz" if f_180 else "spk dist 180°: -")
        self.info_240_label.config(text=f"spk dist 240°: {f_240:.0f} Hz" if f_240 else "spk dist 240°: -")
        self.info_360_label.config(text=f"spk dist 360°: {f_360:.0f} Hz" if f_360 else "spk dist 360°: -")

    # ---------------------------------------------------------------- osc --
    def _build_osc_panel(self):
        frm = ttk.LabelFrame(self.left_col, text="OSC output")
        frm.pack(fill="x", padx=10, pady=5)

        ttk.Label(frm, text="Host").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.osc_host = tk.StringVar(value="127.0.0.1")
        ttk.Entry(frm, textvariable=self.osc_host, width=16).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frm, text="Port").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.osc_port = tk.IntVar(value=5000)
        ttk.Entry(frm, textvariable=self.osc_port, width=8).grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frm, text="Address prefix").grid(row=0, column=4, sticky="w", padx=5, pady=5)
        self.osc_prefix = tk.StringVar(value="/sad/sub")
        ttk.Entry(frm, textvariable=self.osc_prefix, width=14).grid(row=0, column=5, padx=5, pady=5)

        self.live_send = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Live send", variable=self.live_send,
                         command=self._apply_osc_settings).grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Button(frm, text="Apply / Reconnect", command=self._apply_osc_settings).grid(
            row=1, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Button(frm, text="Send Now", command=self._send_now).grid(
            row=1, column=3, sticky="w", padx=5, pady=5)

        self.osc_status = tk.StringVar(value="not connected")
        ttk.Label(frm, textvariable=self.osc_status, foreground="#666").grid(
            row=1, column=4, columnspan=2, sticky="w", padx=5, pady=5)

    def _apply_osc_settings(self):
        try:
            self.osc_client = SimpleUDPClient(self.osc_host.get(), int(self.osc_port.get()))
            self._last_sent = {}  # new target -- send full state again, not just deltas
            self.osc_status.set(f"ready → {self.osc_host.get()}:{self.osc_port.get()}")
        except Exception as e:
            self.osc_client = None
            self.osc_status.set(f"error: {e}")

    def _send_now(self):
        if self.osc_client is None:
            self._apply_osc_settings()
        self._send_osc(self._compute(), force=True)

    def _send_osc(self, subs, force=False):
        if self.osc_client is None:
            return
        try:
            prefix = self.osc_prefix.get().rstrip("/")
            group_delay = self.group_delay.get()
            group_level = self.group_level.get()
            group_inverted = self._group_inverted()
            sent = 0
            total = 0
            for s in subs:
                total_gain = total_gain_db(s.gain_db, group_level)
                for suffix, value in (
                    ("delay_ms", round(float(s.delay_ms), 6)),
                    ("delay_total_ms", round(total_delay_ms(s.delay_ms, group_delay), 6)),
                    ("gain_db", round(float(s.gain_db), 6)),
                    ("gain_total_db", round(total_gain, 6)),
                    ("gain", round(gain_db_to_osc(total_gain), 6)),
                    ("polarity", int(effective_polarity(s.polarity_reversed, group_inverted))),
                ):
                    total += 1
                    address = f"{prefix}/{s.index}/{suffix}"
                    if force or self._last_sent.get(address) != value:
                        self.osc_client.send_message(address, value)
                        self._last_sent[address] = value
                        sent += 1
            self.osc_status.set(f"sent {sent}/{total} values @ {self.osc_host.get()}:{self.osc_port.get()}")
        except Exception as e:
            self.osc_status.set(f"send error: {e}")

    # -------------------------------------------------------------- table --
    def _build_table(self):
        outer = ttk.LabelFrame(self.left_col, text="Per-sub output")
        outer.pack(fill="both", expand=True, padx=10, pady=5)

        # A plain Frame doesn't scroll -- up to 48 subs (Physical / Arc /
        # Manual) won't all fit on screen at once, so the row grid lives
        # inside a Canvas+Scrollbar instead, growing the window only up to
        # a cap (_TABLE_MAX_HEIGHT_PX) and scrolling beyond that.
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.table_canvas = canvas

        frm = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=frm, anchor="nw")
        frm.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width=e.width))

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        header = ["Sub", "Y (m)", "X (m)", "Rotation (°)", "Delay (ms)", "Delay + Group (ms)",
                   "Gain Trim (dB)", "Gain + Group (dB)", "Polarity"]
        header_labels = []
        for c, h in enumerate(header):
            lbl = ttk.Label(frm, text=h, font=("Segoe UI", 9, "bold"))
            lbl.grid(row=0, column=c, padx=5, pady=3, sticky="w")
            header_labels.append(lbl)
        self.delay_header_lbl = header_labels[4]
        self.total_delay_header_lbl = header_labels[5]

        self.table_frame = frm
        self.note = ttk.Label(self.left_col, text="", foreground="#666", wraplength=680, justify="left")
        self.note.pack(fill="x", padx=12, pady=(0, 10))

    def _rebuild_rows(self, n, editable_all=False):
        for w in self.row_widgets:
            for widget in w:
                widget.destroy()
        self.row_widgets.clear()
        self.trim_vars = [tk.DoubleVar(value=0.0) for _ in range(n)]
        self.manual_x_vars = [tk.DoubleVar(value=0.0) for _ in range(n)]
        self.manual_y_vars = [tk.DoubleVar(value=0.0) for _ in range(n)]
        self.manual_gain_vars = [tk.DoubleVar(value=0.0) for _ in range(n)]
        self.manual_pol_vars = [tk.BooleanVar(value=False) for _ in range(n)]
        self.y_labels = []
        self.x_labels = []
        self.rotation_labels = []
        self.delay_labels = []
        self.total_delay_labels = []
        self.gain_widgets = []
        self.total_gain_labels = []
        self.pol_widgets = []

        for i in range(n):
            r = i + 1
            idx_lbl = ttk.Label(self.table_frame, text=str(r))
            idx_lbl.grid(row=r, column=0, padx=5, pady=2, sticky="w")

            if editable_all:
                y_widget = ttk.Entry(self.table_frame, textvariable=self.manual_y_vars[i], width=8)
                y_widget.bind("<KeyRelease>", lambda e: self._on_change())
                x_widget = ttk.Entry(self.table_frame, textvariable=self.manual_x_vars[i], width=8)
                x_widget.bind("<KeyRelease>", lambda e: self._on_change())
            else:
                y_widget = ttk.Label(self.table_frame, text="0.00")
                x_widget = ttk.Label(self.table_frame, text="0.00")
            y_widget.grid(row=r, column=1, padx=5, pady=2, sticky="w")
            x_widget.grid(row=r, column=2, padx=5, pady=2, sticky="w")
            self.y_labels.append(y_widget)
            self.x_labels.append(x_widget)

            rot_lbl = ttk.Label(self.table_frame, text="0.0")
            rot_lbl.grid(row=r, column=3, padx=5, pady=2, sticky="w")
            self.rotation_labels.append(rot_lbl)

            delay_lbl = ttk.Label(self.table_frame, text="0.00")
            delay_lbl.grid(row=r, column=4, padx=5, pady=2, sticky="w")
            self.delay_labels.append(delay_lbl)

            total_delay_lbl = ttk.Label(self.table_frame, text="0.00")
            total_delay_lbl.grid(row=r, column=5, padx=5, pady=2, sticky="w")
            self.total_delay_labels.append(total_delay_lbl)

            if editable_all:
                gain_widget = ttk.Entry(self.table_frame, textvariable=self.manual_gain_vars[i], width=10)
                gain_widget.bind("<KeyRelease>", lambda e: self._on_change())
            else:
                # Read-only here -- for the computed topologies, trim is set via the
                # Level taper panel's "Apply to Gain trim", not typed in the table.
                gain_widget = ttk.Label(self.table_frame, text="0.00")
            gain_widget.grid(row=r, column=6, padx=5, pady=2, sticky="w")
            self.gain_widgets.append(gain_widget)

            total_gain_lbl = ttk.Label(self.table_frame, text="0.00")
            total_gain_lbl.grid(row=r, column=7, padx=5, pady=2, sticky="w")
            self.total_gain_labels.append(total_gain_lbl)

            if editable_all:
                pol_widget = ttk.Checkbutton(self.table_frame, text="Reversed", variable=self.manual_pol_vars[i],
                                              command=self._on_change)
            else:
                pol_widget = ttk.Label(self.table_frame, text="Normal")
            pol_widget.grid(row=r, column=8, padx=5, pady=2, sticky="w")
            self.pol_widgets.append(pol_widget)

            self.row_widgets.append(
                [idx_lbl, y_widget, x_widget, rot_lbl, delay_lbl, total_delay_lbl,
                 gain_widget, total_gain_lbl, pol_widget])

        # Grow the visible table with the row count, same as before there was
        # a scrollbar, up to a cap -- beyond that it scrolls instead of the
        # window growing to fit every one of up to 48 subs.
        wanted_px = (n + 1) * _TABLE_ROW_HEIGHT_PX
        self.table_canvas.configure(height=min(wanted_px, _TABLE_MAX_HEIGHT_PX))

    # ------------------------------------------------------------- events --
    def _on_topology_change(self):
        topo = self.topology.get()
        is_manual = topo == TOPO_MANUAL
        is_arc = topo == TOPO_ARC
        is_physical = topo == TOPO_PHYSICAL
        is_gradient = topo == TOPO_GRADIENT
        is_hybrid = topo in ARC_HYBRID_TOPOLOGIES
        is_progressive = topo == TOPO_PROGRESSIVE
        is_focus = topo == TOPO_FOCUS
        is_ellipse_capable = topo in ELLIPSE_TOPOLOGIES
        is_ellipse = is_ellipse_capable and self.shape.get() == SHAPE_ELLIPSE
        uses_angle = topo in ANGLE_TOPOLOGIES
        uses_steer = topo in STEER_TOPOLOGIES
        uses_radius = is_physical or is_progressive
        no_spacing = is_physical or is_manual or is_progressive
        uses_gradient_pattern = topo in GRADIENT_PATTERN_TOPOLOGIES

        self._set_widgets_visible(
            (self.angle_label, self.angle_spin, self.angle_slider, self.far_label), uses_angle)
        self._set_widgets_visible((self.radius_label, self.radius_spin), uses_radius)
        self._set_widgets_visible(
            (self.steer_label, self.steer_spin, self.steer_slider, self.steer_help), uses_steer)
        self._set_widgets_visible((self.grating_lobe_label, self.grating_lobe_help), uses_steer)
        self._set_widgets_visible(
            (self.spacing_label, self.spacing_spin, self.spacing_slider, self.wavelength_label),
            not no_spacing)
        self._set_widgets_visible(
            (self.row_spacing_label, self.row_spacing_spin, self.row_spacing_slider,
             self.row_wavelength_label, self.row_spacing_help), is_hybrid)
        self._set_widgets_visible(
            (self.row_optimum_label, self.use_row_optimum_btn, self.row_optimum_help), is_hybrid)
        self._set_widgets_visible((self.shape_label, self.shape_cb), is_ellipse_capable)
        self._set_widgets_visible(
            (self.ellipse_ratio_label, self.ellipse_ratio_spin, self.ellipse_ratio_slider,
             self.ellipse_ratio_help), is_ellipse)
        self._set_widgets_visible(
            (self.venue_ellipse_label, self.use_venue_ellipse_btn, self.venue_ellipse_help), is_ellipse)
        self._set_widgets_visible(
            (self.progression_label, self.progression_spin, self.progression_slider,
             self.progression_help), is_progressive)
        self._set_widgets_visible(
            (self.focus_x_label, self.focus_x_spin, self.focus_y_label, self.focus_y_spin,
             self.focus_help), is_focus)
        self._set_widgets_visible(
            (self.pattern_label, self.pattern_cb, self.alpha_label, self.alpha_spin,
             self.alpha_slider, self.pattern_help), uses_gradient_pattern)
        has_topology_options = (uses_angle or uses_radius or uses_steer or is_hybrid
                                 or is_ellipse_capable or is_progressive or is_focus
                                 or uses_gradient_pattern)
        if has_topology_options:
            self.topology_options_frame.pack(fill="x", padx=10, pady=5, after=self.spacing_label.master)
        else:
            self.topology_options_frame.pack_forget()
        if uses_angle:
            self.venue_frame.pack(fill="x", padx=10, pady=5, before=self.dimensions_frame)
            self.taper_frame.pack(fill="x", padx=10, pady=5, before=self.bandwidth_frame)
        else:
            self.venue_frame.pack_forget()
            self.taper_frame.pack_forget()
        self.count_label.config(text="Columns" if is_hybrid else "Pairs" if is_gradient else "Subs")
        if is_gradient:
            max_count = MAX_SUBS // 2
        elif is_hybrid:
            max_count = MAX_SUBS_SPATIAL // 2
        elif is_physical or is_arc or is_manual or is_progressive or is_focus:
            max_count = MAX_SUBS_SPATIAL
        else:
            max_count = MAX_SUBS
        self.count_spin.config(to=max_count)
        if self.count.get() > max_count:
            self.count.set(max_count)

        notes = {
            TOPO_END_FIRE: "Sub 1 = front (faces audience), highest number = rearmost. All normal polarity; "
                        "delay increases towards the front so the array reinforces forward and cancels rearward.",
            TOPO_GRADIENT: "Each pair = odd sub (front, normal, 0 ms) + even sub (rear, "
                                         "reversed polarity, delayed by the pair spacing). Produces a broadband "
                                         "null directly behind each pair.",
            TOPO_PHYSICAL: "Sub 1..N physically placed and rotated on a real arc of the given "
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
            TOPO_ARC: "Sub 1..N along a line, all normal polarity. Delay is symmetric — "
                                        "0 ms at the centre element(s), increasing towards both edges — as if "
                                        "the line were physically bowed into an arc spanning the Arc angle "
                                        "(S.A.D.'s \"delayed horizontal array\"). FAR (Forward Aspect Ratio) "
                                        "= 1/sin(arc/2), the depth:width ratio for that coverage angle. Steer "
                                        "redirects the whole arc off-centre for asymmetrical venues, without "
                                        "changing the coverage angle.",
            TOPO_EF_ARC_HYBRID: "Each column = a front/rear End-Fire pair (1:1), and the columns themselves "
                     "are arc-steered like Arc / Broadside Steering. Within a column: rear = 0 ms reference, "
                     "front = + Row spacing/speed of sound, both normal polarity. Column-to-column delay is "
                     "the same symmetric arc-steering pattern as Arc / Broadside Steering, added underneath "
                     "each column's own front/rear offset. Spacing = column-to-column (lateral); Row spacing "
                     "= front-to-back depth within a column.",
            TOPO_GRAD_ARC_HYBRID: "Each column = a front/rear Gradient (cardioid) pair (1:1), and the columns "
                     "themselves are arc-steered like Arc / Broadside Steering. Within a column: front = 0 ms, "
                     "normal polarity; rear = + Row spacing/speed of sound, reversed polarity — the same "
                     "broadband rear null as Gradient / Cardioid Pairs, per column. Column-to-column delay is "
                     "the same symmetric arc-steering pattern as Arc / Broadside Steering, added underneath "
                     "each column's own front/rear offset. Spacing = column-to-column (lateral); Row spacing "
                     "= front-to-back depth within a column.",
            TOPO_PROGRESSIVE: "Same physical model as Physical Horizontal Array (every element equidistant "
                     "from one center of curvature on a real arc of the given Radius, so delay stays fixed "
                     "at 0 and Rotation is the true local aim angle) but with a non-uniform angular step "
                     "between adjacent elements instead of a constant one -- Progression sets the center:edge "
                     "step ratio (1.0 = uniform, identical to Physical Horizontal Array). Above 1.0 the center "
                     "gap(s) widen and the edge gaps narrow, so total coverage angle (and FAR) is unchanged. "
                     "This app's own extension, not part of S.A.D.",
            TOPO_FOCUS: "\"Destruction Mode\": elements in a straight line (same physical layout as Arc / "
                     "Broadside Steering), all delayed so their output arrives at one target point (Focus X/Y) "
                     "at the same instant, for maximum constructive buildup there. Near-field acoustic "
                     "focusing -- exact by construction from geometry alone, not an approximation. This app's "
                     "own extension, not a S.A.D. topology.",
            TOPO_MANUAL: self._manual_note_text(),
        }
        self.note.config(text=notes[topo])

        n = self.count.get() * (2 if (is_gradient or is_hybrid) else 1)
        self._rebuild_rows(n, editable_all=is_manual)
        self._update_venue_far()  # its "arc" readout depends on topology/Shape now (Ellipse's FAR<1 case)
        self._on_change()
        self._fit_window_height()

    def _on_count_change(self):
        self._on_topology_change()

    def _on_shape_change(self):
        """Shape (Circle/Ellipse -- Physical Horizontal Array, Arc /
        Broadside Steering, or either Arc Hybrid) changes which layout/
        delay function is used and the note text -- _on_topology_change
        already branches on it (is_ellipse), so re-running it is the
        simplest way to refresh everything in sync."""
        self._on_topology_change()

    def _on_change(self, *_):
        if self.topology.get() == TOPO_MANUAL:
            # X/Y convention can flip which column is depth without a topology
            # change firing (no _on_topology_change(), which would blow away
            # typed manual positions) -- keep the note's column letters in sync.
            self.note.config(text=self._manual_note_text())
        self._update_speed_of_sound()
        self._sync_group_distance_from_delay()
        self._refresh_unit_displays()
        self._update_alignment_wizard()
        self._update_collision_check()
        self._sync_level_taper()
        subs = self._compute()
        self._update_table(subs)
        if self.topology.get() in ANGLE_TOPOLOGIES:
            # FAR is a pure function of Angle regardless of topology, but this
            # readout used to only refresh for TOPO_ARC specifically -- stale
            # (or blank) on Physical Horizontal Array, Progressive Arc, and
            # both Arc Hybrids ever since the FAR label itself was extended to
            # show for all of ANGLE_TOPOLOGIES, not just Arc / Broadside Steering.
            far = forward_aspect_ratio(self.angle.get())
            self.far_label.config(text=f"FAR: {far:.2f}" if far is not None else "FAR: ∞")
        self._update_wavelength_readouts()
        self._update_info_panel()
        if self.live_send.get():
            if self.osc_client is None:
                self._apply_osc_settings()
            self._send_osc(subs)

    def _update_wavelength_readouts(self):
        frac = self._wavelength_fraction()
        label = "¼λ" if frac == 0.25 else "½λ" if frac == 0.5 else None

        if frac is None:
            self.wavelength_label.config(text="n/a")
        else:
            try:
                f = freq_at_wavelength_fraction(self.spacing.get(), self._speed_of_sound(), frac)
            except tk.TclError:
                f = None
            self.wavelength_label.config(text=f"{label}: {f:.1f} Hz" if f else "-")

        if frac is None:
            self.optimum_label.config(text="optimum spacing: n/a")
            self.use_optimum_btn.config(state="disabled")
        else:
            try:
                opt = spacing_at_wavelength_fraction(self.freq_high.get(), self._speed_of_sound(), frac)
            except tk.TclError:
                opt = None
            self.optimum_label.config(text=f"optimum spacing ({label}): {opt:.3f} m" if opt else "optimum spacing: -")
            self.use_optimum_btn.config(state="normal")

        if self.topology.get() in ARC_HYBRID_TOPOLOGIES:
            try:
                f_row = freq_at_wavelength_fraction(self.row_spacing.get(), self._speed_of_sound(), 0.25)
            except tk.TclError:
                f_row = None
            self.row_wavelength_label.config(text=f"¼λ: {f_row:.1f} Hz" if f_row else "-")

            try:
                row_opt = spacing_at_wavelength_fraction(self.freq_high.get(), self._speed_of_sound(), 0.25)
            except tk.TclError:
                row_opt = None
            self.row_optimum_label.config(
                text=f"optimum row spacing (¼λ): {row_opt:.3f} m" if row_opt else "optimum row spacing: -")

        if self.topology.get() in STEER_TOPOLOGIES:
            self.grating_lobe_label.config(text=self._grating_lobe_text())

    def _ellipse_depth_scale(self) -> float:
        """1.0 (a plain circle) unless the active topology is
        Ellipse-capable and Shape = Ellipse is actually selected --
        shared by every ELLIPSE_TOPOLOGIES compute() branch."""
        if self.topology.get() in ELLIPSE_TOPOLOGIES and self.shape.get() == SHAPE_ELLIPSE:
            return self.ellipse_ratio.get()
        return 1.0

    def _compute(self):
        topo = self.topology.get()
        try:
            trims = [v.get() for v in self.trim_vars]
            if topo == TOPO_END_FIRE:
                return end_fire(self.count.get(), self.spacing.get(), self._speed_of_sound(), trims)
            if topo == TOPO_GRADIENT:
                return gradient_cardioid(self.count.get(), self.spacing.get(), self._speed_of_sound(), trims,
                                          self.gradient_alpha.get())
            if topo == TOPO_ARC:
                return arc_steering(self.count.get(), self.spacing.get(), self.angle.get(), self._speed_of_sound(),
                                     trims, self.steer.get(), self._ellipse_depth_scale())
            if topo == TOPO_PHYSICAL:
                return physical_horizontal_array(self.count.get(), trims)
            if topo == TOPO_EF_ARC_HYBRID:
                return end_fire_arc_hybrid(self.count.get(), self.spacing.get(), self.row_spacing.get(),
                                            self.angle.get(), self._speed_of_sound(), trims, self.steer.get(),
                                            self._ellipse_depth_scale())
            if topo == TOPO_GRAD_ARC_HYBRID:
                return gradient_arc_hybrid(self.count.get(), self.spacing.get(), self.row_spacing.get(),
                                            self.angle.get(), self._speed_of_sound(), trims, self.steer.get(),
                                            self._ellipse_depth_scale(), self.gradient_alpha.get())
            if topo == TOPO_PROGRESSIVE:
                # Every element is still exactly Radius from one center of
                # curvature (see progressive_arc_layout) -- same physics as
                # Physical Horizontal Array, so the same zero-delay function
                # applies regardless of the angular progression.
                return physical_horizontal_array(self.count.get(), trims)
            if topo == TOPO_FOCUS:
                return focus_point(self.count.get(), self.spacing.get(), self.focus_x.get(), self.focus_y.get(),
                                    self._speed_of_sound(), trims)
            if topo == TOPO_MANUAL:
                n = self.count.get()
                depths = [v.get() for v in self._manual_depth_vars()]
                gains = [v.get() for v in self.manual_gain_vars]
                pols = [v.get() for v in self.manual_pol_vars]
                delays = delays_from_depth(depths, self._speed_of_sound())
                return manual(n, delays, gains, pols)
        except (tk.TclError, ValueError):
            return []
        return []

    def _compute_positions(self):
        topo = self.topology.get()
        if topo in (TOPO_PHYSICAL, TOPO_PROGRESSIVE):
            return [lateral for _, lateral, _ in self._compute_physical_layout()]
        if topo == TOPO_MANUAL:
            try:
                return [v.get() for v in self._manual_lateral_vars()]
            except tk.TclError:
                return []
        try:
            spacing = self.spacing.get()
        except tk.TclError:
            return []
        if topo == TOPO_GRADIENT:
            return sub_positions_gradient(self.count.get(), spacing)
        if topo == TOPO_ARC or topo == TOPO_FOCUS:
            return sub_positions_centered(self.count.get(), spacing)
        if topo in ARC_HYBRID_TOPOLOGIES:
            return sub_positions_arc_hybrid_lateral(self.count.get(), spacing)
        return sub_positions(self.count.get(), spacing)

    def _compute_physical_layout(self):
        """(depth, lateral, rotation) per sub -- real geometry for
        Physical Horizontal Array (Circle or Ellipse Shape) and
        Progressive Arc (all via array_math's layout functions),
        Manual (from free X/Y placement, rotation always 0 -- no
        directivity model), the Arc Hybrids (front/rear depth per
        column, rotation always 0 -- physically a straight line, only
        electronically arc-steered, same as Arc / Broadside Steering),
        (0, 0, 0) for every other topology."""
        try:
            n = self.count.get()
        except tk.TclError:
            return []
        topo = self.topology.get()
        if topo == TOPO_MANUAL:
            try:
                return [(d.get(), l.get(), 0.0)
                        for d, l in zip(self._manual_depth_vars(), self._manual_lateral_vars())]
            except tk.TclError:
                return [(0.0, 0.0, 0.0)] * n
        if topo in ARC_HYBRID_TOPOLOGIES:
            try:
                depths = sub_positions_arc_hybrid_depth(n, self.row_spacing.get())
                laterals = sub_positions_arc_hybrid_lateral(n, self.spacing.get())
            except tk.TclError:
                return [(0.0, 0.0, 0.0)] * (n * 2)
            return [(d, y, 0.0) for d, y in zip(depths, laterals)]
        if topo == TOPO_PROGRESSIVE:
            try:
                return progressive_arc_layout(n, self.radius.get(), self.angle.get(), self.progression_ratio.get())
            except tk.TclError:
                return [(0.0, 0.0, 0.0)] * n
        if topo != TOPO_PHYSICAL:
            if topo == TOPO_GRADIENT:
                n *= 2
            return [(0.0, 0.0, 0.0)] * n
        try:
            if self.shape.get() == SHAPE_ELLIPSE:
                return physical_ellipse_layout(n, self.radius.get(), self.angle.get(), self.ellipse_ratio.get())
            return physical_arc_layout(n, self.radius.get(), self.angle.get())
        except tk.TclError:
            return [(0.0, 0.0, 0.0)] * n

    def _update_delay_headers(self):
        unit_label = "smp" if self.delay_unit.get() == "samples" else "ms"
        self.delay_header_lbl.config(text=f"Delay ({unit_label})")
        self.total_delay_header_lbl.config(text=f"Delay + Group ({unit_label})")

    def _update_table(self, subs):
        self._update_delay_headers()
        is_manual = self.topology.get() == TOPO_MANUAL

        # Manual's Y/X are live Entries bound to manual_y_vars/manual_x_vars --
        # they already show exactly what was typed, no push update needed
        # (and .config(text=...) on an Entry would raise anyway). Which label
        # list gets depth vs lateral depends on the X/Y convention (d&b:
        # X = depth, Y = lateral; L-Acoustics: swapped).
        depth_labels = self.x_labels if self._dnb_mode() else self.y_labels
        lateral_labels = self.y_labels if self._dnb_mode() else self.x_labels
        if not is_manual:
            positions = self._compute_positions()
            for i, lateral in enumerate(positions):
                if i < len(lateral_labels):
                    lateral_labels[i].config(text=f"{lateral:.2f}")

        layout = self._compute_physical_layout()
        for i, (depth, _lateral, rotation) in enumerate(layout):
            if not is_manual and i < len(depth_labels):
                depth_labels[i].config(text=f"{depth:.2f}")
            if i < len(self.rotation_labels):
                self.rotation_labels[i].config(text=f"{rotation:.1f}")

        try:
            group_delay = self.group_delay.get()
        except tk.TclError:
            group_delay = 0.0
        try:
            group_level = self.group_level.get()
        except tk.TclError:
            group_level = 0.0
        sample_rate = self._dsp_sample_rate()
        show_samples = self.delay_unit.get() == "samples"

        # Manual's Gain Trim is a live Entry bound to manual_gain_vars -- already
        # shows exactly what was typed, no push update needed (same reasoning as
        # Y/X above; .config(text=...) on an Entry would raise anyway).
        if not is_manual:
            for i in range(len(subs)):
                if i < len(self.gain_widgets) and i < len(self.trim_vars):
                    self.gain_widgets[i].config(text=f"{self.trim_vars[i].get():.2f}")

        for i, s in enumerate(subs):
            total_gain = total_gain_db(s.gain_db, group_level)
            if i < len(self.total_gain_labels):
                self.total_gain_labels[i].config(text=f"{total_gain:.2f}")
            total_ms = total_delay_ms(s.delay_ms, group_delay)
            if i < len(self.total_delay_labels):
                if show_samples:
                    self.total_delay_labels[i].config(text=str(delay_samples(total_ms, sample_rate)))
                else:
                    self.total_delay_labels[i].config(text=f"{total_ms:.2f}")

        for i, s in enumerate(subs):
            if i < len(self.delay_labels):
                if show_samples:
                    self.delay_labels[i].config(text=str(delay_samples(s.delay_ms, sample_rate)))
                else:
                    self.delay_labels[i].config(text=f"{s.delay_ms:.2f}")

        if is_manual:
            return  # Manual's Polarity is a live Checkbutton, not a status label -- no text push
        group_inverted = self._group_inverted()
        for i, s in enumerate(subs):
            if i < len(self.delay_labels):
                eff_pol = effective_polarity(s.polarity_reversed, group_inverted)
                self.pol_widgets[i].config(text="Reversed" if eff_pol else "Normal")


if __name__ == "__main__":
    App().mainloop()
