"""S.A.D. realtime: live subwoofer array delay/gain/polarity calculator
with OSC output.

The array math (End-Fire, Gradient/Cardioid, Delayed Horizontal Array /
Arc, Forward Aspect Ratio) reimplements Merlijn van Veen's S.A.D.
(Subwoofer Array Designer) calculator and manual -- credit to him, and
to Mauricio "Magu" Ramirez and Bob "6o6" McCarthy, S.A.D.'s own credited
inspiration. https://www.merlijnvanveen.nl/ -- see README.md for details
on what was verified against the original and how.

Pick a topology, drag the sliders, watch the three values per sub update
live, and stream them out over OSC as you go. The OSC address layout is a
generic stub (/sad/sub/<n>/delay_ms|gain_db|polarity) -- point it at any
OSC receiver to test. DirectOut globcon's own OSC namespace for deep
per-channel parameters isn't publicly documented, so remap the addresses
here once that's confirmed for your Prodigy/ACE setup.

Run:
    pip install python-osc
    python sad_realtime_osc.py
"""
__version__ = "0.1.0"

import tkinter as tk
from tkinter import ttk

from pythonosc.udp_client import SimpleUDPClient

from array_math import (
    end_fire, gradient_cardioid, arc_steering, manual, forward_aspect_ratio,
    physical_horizontal_array, physical_arc_layout, physical_arc_chord_spacing, delays_from_depth,
    freq_at_wavelength_fraction, spacing_at_wavelength_fraction,
    far_from_venue, arc_from_far, sub_positions, sub_positions_gradient, sub_positions_centered, array_length,
    gain_db_to_osc, total_delay_ms, effective_polarity, total_gain_db,
    delay_ms_for_distance, distance_for_delay_ms, delay_samples, speed_of_sound,
    required_group_delay_ms, spacing_clearance_m,
    LEVEL_TAPER_WINDOWS, level_taper_db, arc_steered_aim_index,
)
from sub_profiles import load_profiles
from prealign_profiles import (
    load_entries as load_prealign_entries, CONFIG_LABELS, POLARITY_LABELS, PrealignDataError,
)

CUSTOM_PROFILE = "— custom —"

TOPOLOGIES = ["End-Fire", "Gradient / Cardioid Pairs", "Physical Horizontal Array",
              "Arc / Broadside Steering", "Manual"]
TOPO_END_FIRE, TOPO_GRADIENT, TOPO_PHYSICAL, TOPO_ARC, TOPO_MANUAL = TOPOLOGIES

WAVELENGTH_FRACTION = {
    TOPO_END_FIRE: 0.25,
    TOPO_GRADIENT: 0.25,
    TOPO_ARC: 0.5,
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

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        self.left_col = ttk.Frame(self)
        self.left_col.grid(row=0, column=0, sticky="nsew")
        self.right_col = ttk.Frame(self)
        self.right_col.grid(row=0, column=1, sticky="new")

        # left column: primary/frequently-used controls + the per-sub table
        self._build_controls()
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
            row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))

        self._on_topology_change()
        self._update_venue_far()
        self._fit_window_height()

    def _fit_window_height(self):
        self.update_idletasks()
        width = max(self.winfo_width(), self.winfo_reqwidth())
        height = max(self.winfo_reqheight(), 400)
        self.geometry(f"{width}x{height}")
        self.minsize(self.winfo_reqwidth(), 400)

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

        self.angle = tk.DoubleVar(value=0.0)
        self.angle_label, self.angle_spin, self.angle_slider = self._labeled_slider(
            frm, "Arc (°)", self.angle, 0.0, 180.0, row=3, increment=1.0, decimals=1)

        self.far_label = ttk.Label(frm, text="FAR: -", width=12)
        self.far_label.grid(row=3, column=3, sticky="w", padx=5, pady=5)

        self.radius_label = ttk.Label(frm, text="Radius")
        self.radius_label.grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.radius = tk.DoubleVar(value=2.0)
        self.radius_spin = self._make_length_field(frm, self.radius, row=4, col=1)

        self.steer = tk.DoubleVar(value=0.0)
        self.steer_label, self.steer_spin, self.steer_slider = self._labeled_slider(
            frm, "Steer (°)", self.steer, -90.0, 90.0, row=5, increment=1.0, decimals=1)
        self.steer_help = self._help_icon(
            frm, row=5, col=3,
            text="Redirects the whole arc's aim off-centre without changing its coverage "
                 "angle (FAR) -- for venues that aren't symmetrical about the array's own "
                 "centreline. Positive steers toward the highest-numbered sub. 0 = the "
                 "default symmetric aim, straight ahead.")

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

    def _labeled_slider(self, parent, text, var, lo, hi, row, increment=0.1, decimals=None):
        label = ttk.Label(parent, text=text)
        label.grid(row=row, column=0, sticky="w", padx=5, pady=5)

        def quantize():
            if decimals is not None:
                try:
                    var.set(round(var.get(), decimals))
                except tk.TclError:
                    return
            self._on_change()

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
            self._on_change()

        slider = ttk.Scale(parent, from_=lo, to=hi, orient="horizontal", variable=var,
                            command=on_slide)
        slider.grid(row=row, column=2, sticky="ew", padx=5, pady=5)
        return label, spin, slider

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
        frm = ttk.LabelFrame(self.left_col, text="Level taper (Arc / Physical Array only)")
        frm.pack(fill="x", padx=10, pady=5)
        self.taper_frame = frm

        ttk.Label(frm, text="Window").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.taper_window = tk.StringVar(value=LEVEL_TAPER_WINDOWS[0])
        window_cb = ttk.Combobox(frm, textvariable=self.taper_window, values=LEVEL_TAPER_WINDOWS,
                                  state="readonly", width=10)
        window_cb.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        window_cb.bind("<<ComboboxSelected>>", lambda e: self._on_change())

        ttk.Label(frm, text="Max atten (dB)").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.taper_max_atten = tk.DoubleVar(value=0.0)
        atten_spin = ttk.Spinbox(frm, from_=0.0, to=30.0, increment=0.5,
                                  textvariable=self.taper_max_atten, width=6, command=self._on_change)
        atten_spin.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        atten_spin.bind("<Return>", lambda e: self._on_change())
        atten_spin.bind("<FocusOut>", lambda e: self._on_change())

        self._help_icon(frm, row=0, col=4,
                         text="Live gain taper, always following each sub's Gain trim -- 0 dB at the "
                              "window's peak, fading to -max atten at its minimum, shaped by the chosen "
                              "window (9 classic sidelobe-control windows; Uniform or 0 dB = flat, no "
                              "taper). For Arc / Broadside Steering, the peak follows the Steer angle "
                              "(arc_steered_aim_index) instead of always sitting at the array's physical "
                              "centre -- 0° Steer keeps it centred as before. Flat Top is a known exception "
                              "to \"monotonic taper\" — it's an amplitude-accuracy window with a small "
                              "ripple near the edges by design, so it can dip slightly past -max atten "
                              "there; that's correct for Flat Top, not a bug. This app has no polar/SPL "
                              "prediction, so you won't see the sidelobe reduction visually — it's standard "
                              "array theory applied on faith, not a result verified in-app.")

    def _sync_level_taper(self):
        """Keeps Gain trim live-following the Level taper window for Arc /
        Physical Horizontal Array, the same way Delay is always live for
        those topologies -- no separate "Apply" step. For Arc, the taper's
        peak follows Steer's shifted aim point instead of staying pinned
        to the array's physical centre."""
        topo = self.topology.get()
        if topo not in (TOPO_ARC, TOPO_PHYSICAL):
            return
        try:
            n = self.count.get()
            window = self.taper_window.get()
            max_atten = self.taper_max_atten.get()
        except tk.TclError:
            return
        center_index = None
        if topo == TOPO_ARC:
            try:
                center_index = arc_steered_aim_index(n, self.angle.get(), self.steer.get())
            except tk.TclError:
                center_index = None
        try:
            taper = level_taper_db(n, window, max_atten, center_index)
        except ValueError:
            return
        for i, db in enumerate(taper):
            if i < len(self.trim_vars):
                self.trim_vars[i].set(round(db, 2))

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
                              "(resets Profile to \"custom\"). Width applies to Arc / Broadside Steering "
                              "(boxes side by side); depth applies to End-Fire and Gradient (boxes front to "
                              "back). \"Set min spacing\" sets Spacing to that dimension exactly (boxes "
                              "touching); \"Set spacing (+ gap)\" adds the gap value on top, for "
                              "cable/rigging clearance. Profiles load from sub_profiles.csv.")

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
        topology's spacing axis uses, or (None, None) in Manual mode."""
        topo = self.topology.get()
        if topo in (TOPO_ARC, TOPO_PHYSICAL):
            return self.box_width.get(), "width"
        if topo in (TOPO_END_FIRE, TOPO_GRADIENT):
            return self.box_depth.get(), "depth"
        return None, None

    def _effective_spacing_m(self):
        """Spacing the collision check compares against: the Spacing
        field for topologies that use it, or the derived chord spacing
        between adjacent elements for Physical Horizontal Array (which
        has no Spacing input of its own)."""
        if self.topology.get() == TOPO_PHYSICAL:
            return physical_arc_chord_spacing(self.count.get(), self.radius.get(), self.angle.get())
        return self.spacing.get()

    def _update_collision_check(self):
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
        clearance = spacing_clearance_m(spacing, box_dim)
        if clearance < 0:
            self.collision_label.config(
                text=f"⚠ collision: {box_dim:.2f} m {dim_name} > {spacing:.2f} m spacing "
                     f"(by {-clearance:.2f} m)")
        else:
            self.collision_label.config(text=f"OK — {clearance:.2f} m clearance ({dim_name})")

    def _set_min_spacing(self):
        if self.topology.get() == TOPO_PHYSICAL:
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
        if self.topology.get() == TOPO_PHYSICAL:
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
                              "FAR = length / width; \"Set arc\" solves arc = 2·asin(1/FAR) and switches "
                              "to Arc / Broadside Steering.")

    def _venue_far_arc(self):
        try:
            far = far_from_venue(self.venue_length.get(), self.venue_width.get())
        except tk.TclError:
            return None, None
        return far, arc_from_far(far)

    def _update_venue_far(self):
        far, arc = self._venue_far_arc()
        if far is None:
            self.venue_far_label.config(text="FAR: -  arc: -")
        elif arc is None:
            self.venue_far_label.config(text=f"FAR: {far:.2f}  arc: n/a")
        else:
            self.venue_far_label.config(text=f"FAR: {far:.2f}  arc: {arc:.1f}°")

    def _set_arc_from_venue(self):
        _, arc = self._venue_far_arc()
        if arc is None:
            return
        self.topology.set(TOPO_ARC)
        self._on_topology_change()
        self.angle.set(round(min(arc, 180.0), 1))
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
                              "(¼λ for end-fire/gradient, ½λ for arc steering) — the S.A.D. rule of thumb.")

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
        uses_angle = is_arc or is_physical

        self._set_widgets_visible(
            (self.angle_label, self.angle_spin, self.angle_slider, self.far_label), uses_angle)
        self._set_widgets_visible((self.radius_label, self.radius_spin), is_physical)
        self._set_widgets_visible(
            (self.steer_label, self.steer_spin, self.steer_slider, self.steer_help), is_arc)
        self._set_widgets_visible(
            (self.spacing_label, self.spacing_spin, self.spacing_slider, self.wavelength_label),
            not (is_physical or is_manual))
        if uses_angle:
            self.venue_frame.pack(fill="x", padx=10, pady=5, before=self.dimensions_frame)
            self.taper_frame.pack(fill="x", padx=10, pady=5, before=self.bandwidth_frame)
        else:
            self.venue_frame.pack_forget()
            self.taper_frame.pack_forget()
        self.count_label.config(text="Pairs" if is_gradient else "Subs")
        if is_gradient:
            max_count = MAX_SUBS // 2
        elif is_physical or is_arc or is_manual:
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
                                         "real output here is the physical layout in the X/Y/Rotation columns.",
            TOPO_ARC: "Sub 1..N along a line, all normal polarity. Delay is symmetric — "
                                        "0 ms at the centre element(s), increasing towards both edges — as if "
                                        "the line were physically bowed into an arc spanning the Arc angle "
                                        "(S.A.D.'s \"delayed horizontal array\"). FAR (Forward Aspect Ratio) "
                                        "= 1/sin(arc/2), the depth:width ratio for that coverage angle. Steer "
                                        "redirects the whole arc off-centre for asymmetrical venues, without "
                                        "changing the coverage angle.",
            TOPO_MANUAL: "Place each sub freely: type X (depth, front-to-back — larger/less-negative is closer "
                     "to the audience) and Y (lateral, informational only) directly. Delay is derived, not "
                     "typed — the rearmost placed sub (smallest X) is the 0 ms reference, same plane-wave-"
                     "towards-the-audience logic as End-Fire, generalised to free 2D placement. Gain trim and "
                     "Polarity stay directly editable.",
        }
        self.note.config(text=notes[topo])

        n = self.count.get() * (2 if is_gradient else 1)
        self._rebuild_rows(n, editable_all=is_manual)
        self._on_change()
        self._fit_window_height()

    def _on_count_change(self):
        self._on_topology_change()

    def _on_change(self, *_):
        self._update_speed_of_sound()
        self._sync_group_distance_from_delay()
        self._refresh_unit_displays()
        self._update_alignment_wizard()
        self._update_collision_check()
        self._sync_level_taper()
        subs = self._compute()
        self._update_table(subs)
        if self.topology.get() == TOPO_ARC:
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

    def _compute(self):
        topo = self.topology.get()
        try:
            trims = [v.get() for v in self.trim_vars]
            if topo == TOPO_END_FIRE:
                return end_fire(self.count.get(), self.spacing.get(), self._speed_of_sound(), trims)
            if topo == TOPO_GRADIENT:
                return gradient_cardioid(self.count.get(), self.spacing.get(), self._speed_of_sound(), trims)
            if topo == TOPO_ARC:
                return arc_steering(self.count.get(), self.spacing.get(), self.angle.get(), self._speed_of_sound(),
                                     trims, self.steer.get())
            if topo == TOPO_PHYSICAL:
                return physical_horizontal_array(self.count.get(), trims)
            if topo == TOPO_MANUAL:
                n = self.count.get()
                xs = [v.get() for v in self.manual_x_vars]
                gains = [v.get() for v in self.manual_gain_vars]
                pols = [v.get() for v in self.manual_pol_vars]
                delays = delays_from_depth(xs, self._speed_of_sound())
                return manual(n, delays, gains, pols)
        except (tk.TclError, ValueError):
            return []
        return []

    def _compute_positions(self):
        topo = self.topology.get()
        if topo == TOPO_PHYSICAL:
            return [lateral for _, lateral, _ in self._compute_physical_layout()]
        if topo == TOPO_MANUAL:
            try:
                return [v.get() for v in self.manual_y_vars]
            except tk.TclError:
                return []
        try:
            spacing = self.spacing.get()
        except tk.TclError:
            return []
        if topo == TOPO_GRADIENT:
            return sub_positions_gradient(self.count.get(), spacing)
        if topo == TOPO_ARC:
            return sub_positions_centered(self.count.get(), spacing)
        return sub_positions(self.count.get(), spacing)

    def _compute_physical_layout(self):
        """(depth, lateral, rotation) per sub -- real geometry for
        Physical Horizontal Array and Manual (from free X/Y placement,
        rotation always 0 -- no directivity model), (0, 0, 0) for every
        other topology."""
        try:
            n = self.count.get()
        except tk.TclError:
            return []
        topo = self.topology.get()
        if topo == TOPO_MANUAL:
            try:
                return [(x.get(), y.get(), 0.0) for x, y in zip(self.manual_x_vars, self.manual_y_vars)]
            except tk.TclError:
                return [(0.0, 0.0, 0.0)] * n
        if topo != TOPO_PHYSICAL:
            if topo == TOPO_GRADIENT:
                n *= 2
            return [(0.0, 0.0, 0.0)] * n
        try:
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
        # (and .config(text=...) on an Entry would raise anyway).
        if not is_manual:
            positions = self._compute_positions()
            for i, y in enumerate(positions):
                if i < len(self.y_labels):
                    self.y_labels[i].config(text=f"{y:.2f}")

        layout = self._compute_physical_layout()
        for i, (depth, _lateral, rotation) in enumerate(layout):
            if not is_manual and i < len(self.x_labels):
                self.x_labels[i].config(text=f"{depth:.2f}")
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
