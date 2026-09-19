"""Per-element delay/gain/polarity math for common subwoofer array topologies.

Reimplements the core steering geometry behind Merlijn van Veen's S.A.D.
(Subwoofer Array Designer) spreadsheet and manual for four topologies,
without the polar/SPL prediction plots. Credit to Merlijn van Veen
(https://www.merlijnvanveen.nl/), and to Mauricio "Magu" Ramirez and Bob
"6o6" McCarthy, S.A.D.'s own credited inspiration. Sub 1 is always the
element closest to the audience ("front"); higher numbers sit further
back, except for Arc / Broadside Steering, which is symmetric about the
array's center -- see arc_steering and sub_positions_centered.
"""
from dataclasses import dataclass
import math

# Cramer (1993), JASA 93(5):2510-2516, "The variation of the specific heat
# ratio and the speed of sound in air with temperature, pressure, humidity,
# and CO2 concentration". Valid 0-30 degC, 75-102 kPa, xw <= 0.06, xc <= 0.01;
# accuracy <=300 ppm within that range.
_CRAMER_A0, _CRAMER_A1, _CRAMER_A2 = 331.5024, 0.603055, -0.000528
_CRAMER_A3, _CRAMER_A4, _CRAMER_A5 = 51.471935, 0.1495874, -0.000782
_CRAMER_A6, _CRAMER_A7, _CRAMER_A8 = -1.82e-7, 3.73e-8, -2.93e-10
_CRAMER_A9, _CRAMER_A10, _CRAMER_A11 = -85.20931, -0.228525, 5.91e-5
_CRAMER_A12, _CRAMER_A13 = -2.835149, -2.15e-13
_CRAMER_A14, _CRAMER_A15 = 29.179762, 0.000486

CO2_MOLE_FRACTION = 0.0004
"""Fixed standard-atmosphere default (~400 ppm) -- CO2 isn't exposed as an
app input; its effect on the result is negligible (well under 0.01 m/s)
at any realistic outdoor concentration."""


def saturation_vapor_pressure_pa(temp_c: float) -> float:
    """Davis (1992) saturation vapor pressure of water in air, Pa."""
    t_k = temp_c + 273.15
    return math.exp(1.2811805e-5 * t_k ** 2 - 1.9509874e-2 * t_k
                     + 34.04926034 - 6.3536311e3 / t_k)


def water_vapor_enhancement_factor(temp_c: float, pressure_pa: float) -> float:
    """Correction for water vapor deviating from ideal-gas behavior in
    air, per Cramer (1993)."""
    return 1.00062 + 3.14e-8 * pressure_pa + 5.6e-7 * temp_c ** 2


def water_vapor_mole_fraction(temp_c: float, pressure_pa: float, relative_humidity_pct: float) -> float:
    """Mole fraction of water vapor in air, xw, from relative humidity."""
    h = max(0.0, min(100.0, relative_humidity_pct)) / 100.0
    psv = saturation_vapor_pressure_pa(temp_c)
    f = water_vapor_enhancement_factor(temp_c, pressure_pa)
    return h * f * psv / pressure_pa


def pressure_at_altitude_pa(altitude_m: float) -> float:
    """Atmospheric pressure at altitude_m above sea level, International
    Standard Atmosphere model. This is elevation only -- it doesn't
    account for day-to-day weather-driven pressure variation."""
    p0, t0, lapse = 101325.0, 288.15, 0.0065
    g, m, r = 9.80665, 0.0289644, 8.3144598
    return p0 * (1.0 - lapse * altitude_m / t0) ** (g * m / (r * lapse))


def speed_of_sound(temp_c: float, relative_humidity_pct: float = 50.0, altitude_m: float = 0.0) -> float:
    """Speed of sound in air, m/s, via the Cramer (1993) equation --
    accounts for temperature, relative humidity, and altitude (through
    the resulting atmospheric pressure)."""
    p = pressure_at_altitude_pa(altitude_m)
    xw = water_vapor_mole_fraction(temp_c, p, relative_humidity_pct)
    xc = CO2_MOLE_FRACTION
    t = temp_c
    return (_CRAMER_A0 + _CRAMER_A1 * t + _CRAMER_A2 * t ** 2
            + (_CRAMER_A3 + _CRAMER_A4 * t + _CRAMER_A5 * t ** 2) * xw
            + (_CRAMER_A6 + _CRAMER_A7 * t + _CRAMER_A8 * t ** 2) * p
            + (_CRAMER_A9 + _CRAMER_A10 * t + _CRAMER_A11 * t ** 2) * xc
            + _CRAMER_A12 * xw ** 2
            + _CRAMER_A13 * p ** 2
            + _CRAMER_A14 * xc ** 2
            + _CRAMER_A15 * xw * p * xc)


@dataclass
class SubOutput:
    index: int
    delay_ms: float
    gain_db: float
    polarity_reversed: bool


def end_fire(n: int, spacing_m: float, speed_mps: float, gain_trim_db=None) -> list[SubOutput]:
    """Inline array, all facing the audience. The rearmost element is the
    time reference (0 delay); each element further forward is delayed by
    the propagation time across the elements behind it, so all elements
    arrive in phase toward the audience and cancel toward the rear."""
    trims = gain_trim_db or [0.0] * n
    out = []
    for j in range(1, n + 1):
        delay_s = (n - j) * spacing_m / speed_mps
        out.append(SubOutput(j, delay_s * 1000.0, trims[j - 1], False))
    return out


def gradient_cardioid(pairs: int, spacing_m: float, speed_mps: float, gain_trim_db=None) -> list[SubOutput]:
    """Front/rear cardioid pairs. Front: 0 delay, normal polarity. Rear:
    delayed by the front-to-rear propagation time, reversed polarity.
    Produces a broadband null directly behind each pair."""
    n = pairs * 2
    trims = gain_trim_db or [0.0] * n
    delay_ms = (spacing_m / speed_mps) * 1000.0
    out = []
    for p in range(pairs):
        front_idx, rear_idx = p * 2 + 1, p * 2 + 2
        out.append(SubOutput(front_idx, 0.0, trims[front_idx - 1], False))
        out.append(SubOutput(rear_idx, delay_ms, trims[rear_idx - 1], True))
    return out


def arc_steering(n: int, spacing_m: float, angle_deg: float, speed_mps: float,
                  gain_trim_db=None, steer_deg: float = 0.0) -> list[SubOutput]:
    """S.A.D.'s "delayed horizontal array": n elements physically in a
    straight line, delayed as if positioned on a physical arc spanning
    angle_deg. The pattern is symmetric -- minimum (0 ms) at the center
    element(s), increasing toward both edges -- not a one-directional
    ramp, matching S.A.D.'s own tutorial data (10 elements, 0.94 m
    spacing, 71 deg arc -> delay 3.77/2.27/1.14/0.38/0.00 ms edge to
    center, mirrored) to within ~0.07 ms, consistent with the tutorial's
    displayed inputs themselves being rounded.

    The angular step between adjacent elements is angle_deg/(n-1); the
    implicit arc radius is derived from that step and spacing_m via
    chord geometry (adjacent elements angle_deg/(n-1) apart, spacing_m
    apart on the chord). Each element's delay is then the sagitta
    (depth of bow relative to the center) of its own angular position on
    that arc, divided by the speed of sound.

    steer_deg optionally redirects the whole arc's aim off-center --
    e.g. for a venue that isn't symmetrical about the array's centerline
    -- without changing its coverage angle (FAR). It superimposes the
    standard linear delay-steering ramp (delay_i = -x_i*sin(steer)/c,
    x_i the element's straight-line position relative to center, same
    convention as sub_positions_centered) on top of the arc's own
    curvature; positive steer_deg aims toward the higher-numbered end of
    the array. The combined profile is then re-zeroed so the earliest
    element is still 0 ms, since a real delay line can't go negative."""
    trims = gain_trim_db or [0.0] * n
    if n <= 1 or (angle_deg <= 0 and steer_deg == 0):
        return [SubOutput(i + 1, 0.0, trims[i], False) for i in range(n)]

    center = (n - 1) / 2.0
    if angle_deg > 0:
        d_phi = math.radians(angle_deg) / (n - 1)
        half_step = d_phi / 2.0
        radius = spacing_m / (2.0 * math.sin(half_step)) if math.sin(half_step) != 0 else 0.0
    else:
        d_phi = 0.0
        radius = 0.0

    steer_rad = math.radians(steer_deg)
    raw_delays_s = []
    for i in range(n):
        phi = (i - center) * d_phi
        depth = radius * (1.0 - math.cos(phi)) if radius else 0.0
        x = (i - center) * spacing_m
        steer_depth = -x * math.sin(steer_rad)
        raw_delays_s.append((depth + steer_depth) / speed_mps)

    zero = min(raw_delays_s)
    return [SubOutput(i + 1, (raw_delays_s[i] - zero) * 1000.0, trims[i], False) for i in range(n)]


def physical_horizontal_array(n: int, gain_trim_db=None) -> list[SubOutput]:
    """S.A.D.'s "physical horizontal array": n elements physically placed
    and rotated on a real arc. Every element is already equidistant from
    the arc's center of curvature, so no electronic delay or level
    compensation is needed -- confirmed by S.A.D.'s own tutorial (delay
    and level both exactly 0 for every element). All that's physically
    real here is where to place and aim each box; see
    physical_arc_layout for that."""
    trims = gain_trim_db or [0.0] * n
    return [SubOutput(i + 1, 0.0, trims[i], False) for i in range(n)]


def physical_arc_layout(n: int, radius_m: float, angle_deg: float):
    """(depth_m, lateral_m, rotation_deg) for each of n elements placed on
    a real arc of radius_m spanning angle_deg, symmetric about the
    center -- element 1 at the most positive lateral position and
    rotation (same sign convention as sub_positions_centered). depth_m is
    <= 0 (set-back relative to the center element(s), which sit at the
    front of the arc). Verified exact against S.A.D.'s own tutorial (10
    elements, 70 deg arc, radius ~7.29 m derived from its lateral column
    -> element 1: depth -1.32 m, lateral 4.18 m, rotation 35.0 deg;
    element 5: -0.02 m, 0.49 m, 3.9 deg -- matches to the tutorial's
    displayed rounding)."""
    if n <= 1 or angle_deg <= 0:
        return [(0.0, 0.0, 0.0) for _ in range(n)]
    d_phi = angle_deg / (n - 1)
    center = (n - 1) / 2.0
    out = []
    for i in range(n):
        phi_deg = (center - i) * d_phi
        phi = math.radians(phi_deg)
        lateral = radius_m * math.sin(phi)
        depth = -radius_m * (1.0 - math.cos(phi))
        out.append((depth, lateral, phi_deg))
    return out


def physical_arc_chord_spacing(n: int, radius_m: float, angle_deg: float):
    """Straight-line (chord) distance between two physically adjacent
    elements on the arc from physical_arc_layout -- the actual physical
    gap the Sub box dimensions collision check needs for Physical
    Horizontal Array, since its elements aren't spaced by the Spacing
    field (that only applies to the straight-line topologies)."""
    if n <= 1:
        return None
    d_phi = angle_deg / (n - 1)
    return 2.0 * radius_m * math.sin(math.radians(d_phi) / 2.0)


def forward_aspect_ratio(angle_deg: float):
    """FAR = 1 / sin(angle/2) -- the depth:width ratio McCarthy/S.A.D. use to
    characterize an arc's coverage angle. Undefined (returns None) at 0 deg."""
    s = math.sin(math.radians(angle_deg) / 2.0)
    return None if s == 0 else 1.0 / s


def far_from_venue(length_m: float, width_m: float):
    """FAR = venue length (throw/depth, front-to-back) / venue width
    (coverage, side-to-side) -- per S.A.D.'s own tutorial: a 25 x 50 m
    audience area (50 m deep, 25 m wide) gives FAR = 50/25 = 2.00."""
    if not width_m or width_m <= 0 or length_m is None:
        return None
    return length_m / width_m


def arc_from_far(far):
    """Inverse of forward_aspect_ratio: arc = 2*asin(1/FAR). None if FAR < 1
    (no single arc angle covers a venue wider than it is deep)."""
    if far is None or far < 1:
        return None
    return math.degrees(2.0 * math.asin(1.0 / far))


def freq_at_wavelength_fraction(distance_m: float, speed_mps: float, fraction: float):
    """Frequency at which `fraction` of a wavelength equals distance_m
    (e.g. fraction=0.5 -> the frequency where spacing = 1/2 wavelength)."""
    if distance_m <= 0:
        return None
    return fraction * speed_mps / distance_m


def spacing_at_wavelength_fraction(freq_hz: float, speed_mps: float, fraction: float):
    """Spacing at which `fraction` of a wavelength equals the period of
    freq_hz -- the S.A.D. rule of thumb: 1/2 wavelength for horizontal
    (arc) arrays, 1/4 wavelength for end-fire and gradient, evaluated at
    the top of the sub's passband."""
    if freq_hz <= 0:
        return None
    return fraction * speed_mps / freq_hz


GAIN_OSC_SLOPE = 165.0
GAIN_OSC_MAX_DB = 18.0
GAIN_OSC_FLOOR_DB = -144.0
"""Bottom of the usable range (top is GAIN_OSC_MAX_DB, +18 dB). Rounded
from a hardware measurement: dialing in an extreme low value (tested at
-638 dB) clamped to a -143.9 dB readback, not true -inf -- close to the
~144.5 dB noise floor of 24-bit audio, and almost certainly the box's own
finite stand-in for -inf. The pure log curve never actually reaches x=0.0
for any finite dB, so below this floor we clamp directly instead of
following the curve down further than the hardware itself does. (A
0 dB entry reading back ~-0.1 dB is normal step-resolution quantization,
not something the curve needs to account for.)"""


def gain_db_to_osc(gain_db) -> float:
    """dB -> normalized 0.0-1.0 OSC fader value, calibrated to 1.0 = +18 dB,
    ~0.778 = 0 dB (unity): dB = 165*log10(x) + 18, so x = 10^((dB-18)/165).
    None, -inf, or anything at/below the -144 dB floor maps to exactly
    0.0; the result is clamped to [0, 1] above +18 dB."""
    if gain_db is None or gain_db == float("-inf") or gain_db <= GAIN_OSC_FLOOR_DB:
        return 0.0
    x = 10.0 ** ((gain_db - GAIN_OSC_MAX_DB) / GAIN_OSC_SLOPE)
    return max(0.0, min(1.0, x))


def osc_to_gain_db(x: float) -> float:
    """Inverse of gain_db_to_osc. 0.0 maps to the -144 dB floor, matching
    how the real box reports it -- not literal -inf."""
    if x <= 0:
        return GAIN_OSC_FLOOR_DB
    return GAIN_OSC_SLOPE * math.log10(min(1.0, x)) + GAIN_OSC_MAX_DB


def manual(n: int, delays_ms, gains_db, polarities) -> list[SubOutput]:
    return [SubOutput(i + 1, delays_ms[i], gains_db[i], polarities[i]) for i in range(n)]


def delays_from_depth(x_values_m, speed_mps: float) -> list[float]:
    """Per-element delay, ms, for elements freely placed at the given
    depth positions (X: front-to-back, larger/less-negative = closer to
    the audience -- same sign convention as physical_arc_layout's depth).
    Aligns every element as a plane wave arriving from the front: the
    rearmost placed element (min X) is the 0 ms reference, generalizing
    End-Fire's "rearmost = reference" to arbitrary free placement instead
    of a fixed line. Lateral (Y) offset doesn't affect delay in this
    far-field model -- a plane wave arriving square-on has equal phase
    across Y at a given depth."""
    if not x_values_m:
        return []
    min_x = min(x_values_m)
    return [(x - min_x) / speed_mps * 1000.0 for x in x_values_m]


def total_delay_ms(delay_ms: float, group_delay_ms: float) -> float:
    """Per-sub delay plus a uniform group delay applied to the whole array
    -- e.g. aligning the sub array's total delay to the mains."""
    return delay_ms + group_delay_ms


def total_gain_db(gain_db: float, group_level_db: float) -> float:
    """Per-sub gain trim plus a uniform group level applied to the whole
    array -- e.g. trimming the entire sub array relative to the mains."""
    return gain_db + group_level_db


def effective_polarity(polarity_reversed: bool, group_inverted: bool) -> bool:
    """A sub's own topology-computed polarity, flipped again if the group
    polarity toggle is set to Inverted."""
    return polarity_reversed != group_inverted


def delay_ms_for_distance(distance_m: float, speed_mps: float) -> float:
    """Time for sound to travel distance_m, in ms -- lets group delay be
    entered as a physical distance (e.g. the subs sit 15 m closer to FOH
    than the mains) instead of typing milliseconds directly."""
    return distance_m / speed_mps * 1000.0


def distance_for_delay_ms(delay_ms: float, speed_mps: float) -> float:
    """Inverse of delay_ms_for_distance."""
    return delay_ms / 1000.0 * speed_mps


def delay_samples(delay_ms: float, sample_rate_hz: float) -> int:
    """Delay in samples at a given DSP clock rate, rounded to the nearest
    integer sample -- the unit many DSP delay lines are actually set in."""
    return round(delay_ms / 1000.0 * sample_rate_hz)


def required_group_delay_ms(mains_distance_m: float, mains_delay_ms: float,
                             sub_distance_m: float, speed_mps: float) -> float:
    """Group delay that makes the sub array's arrival at FOH match the
    mains array's arrival at FOH, given each array's distance to FOH (from
    its own reference point -- for subs, the front row) and whatever
    electrical delay is already applied to the mains.

    arrival time = electrical delay + distance / speed of sound, so
    solving mains_delay + mains_distance/c = group_delay + sub_distance/c
    for group_delay gives:

        group_delay = mains_delay + (mains_distance - sub_distance) / c

    A negative result means the subs are already farther from FOH than
    the mains -- there's no positive sub delay that fixes that; the mains
    would need delaying instead."""
    return mains_delay_ms + (mains_distance_m - sub_distance_m) / speed_mps * 1000.0


def spacing_clearance_m(spacing_m: float, box_dimension_m: float) -> float:
    """Physical clearance between adjacent boxes along the array axis:
    spacing minus the box's own dimension on that axis (width for a
    side-by-side arc/broadside line, depth for a front-to-back end-fire
    or gradient stack). Positive = gap between boxes, negative = they'd
    physically overlap at that spacing."""
    return spacing_m - box_dimension_m


def sub_positions(n: int, spacing_m: float) -> list[float]:
    """Distance of each of n inline elements from element 1, in meters --
    the S.A.D. output sheet's "y" column for a straight array."""
    return [i * spacing_m for i in range(n)]


def sub_positions_centered(n: int, spacing_m: float) -> list[float]:
    """Position of each of n inline elements relative to the array's own
    center, in meters -- symmetric about 0, sub 1 at the most positive
    end. This is the "delayed horizontal array" (Arc) convention: matches
    S.A.D.'s own tutorial output sheet, e.g. n=10, spacing=0.94 m gives
    +4.23, +3.29, +2.35, +1.41, +0.47, -0.47, -1.41, -2.35, -3.29, -4.23
    (evenly spaced by spacing_m throughout, symmetric about 0)."""
    center = (n - 1) / 2.0
    return [(center - i) * spacing_m for i in range(n)]


def sub_positions_gradient(pairs: int, spacing_m: float) -> list[float]:
    """Front/rear depth offset per pair: front=0, rear=spacing_m -- same
    number for every pair, since pairs sit side by side at the same depth."""
    out = []
    for _ in range(pairs):
        out.extend([0.0, spacing_m])
    return out


def array_length(n: int, spacing_m: float) -> float:
    """Total span of a linear (n-1)-gap array, in meters -- S.A.D.'s
    "array length" info-panel value."""
    return max(n - 1, 0) * spacing_m


LEVEL_TAPER_WINDOWS = ["Uniform", "Hann", "Hamming", "Blackman", "Bartlett", "Welch",
                       "Blackman-Harris", "Nuttall", "Flat Top"]


def _window_shape(u: float, window: str) -> float:
    """Classic DSP window shapes, as a function of position u in [-1, 1]
    (0 = the window's peak, +/-1 = its outer edge) rather than a discrete
    index -- algebraically identical to the textbook index-based formulas
    (window_weights uses these at u = 2k/(n-1) - 1, the array's evenly
    spaced element positions), but usable at an arbitrary, not
    necessarily evenly-spaced or centered, position -- needed to re-center
    the window off the array's physical middle for steered_window_weights."""
    if window == "Uniform":
        return 1.0
    if window == "Hann":
        return 0.5 + 0.5 * math.cos(math.pi * u)
    if window == "Hamming":
        return 0.54 + 0.46 * math.cos(math.pi * u)
    if window == "Blackman":
        return 0.42 + 0.5 * math.cos(math.pi * u) + 0.08 * math.cos(2 * math.pi * u)
    if window == "Bartlett":
        return 1.0 - abs(u)
    if window == "Welch":
        return 1.0 - u * u
    if window == "Blackman-Harris":
        a0, a1, a2, a3 = 0.35875, 0.48829, 0.14128, 0.01168
        return a0 + a1 * math.cos(math.pi * u) + a2 * math.cos(2 * math.pi * u) + a3 * math.cos(3 * math.pi * u)
    if window == "Nuttall":
        a0, a1, a2, a3 = 0.355768, 0.487396, 0.144232, 0.012604
        return a0 + a1 * math.cos(math.pi * u) + a2 * math.cos(2 * math.pi * u) + a3 * math.cos(3 * math.pi * u)
    if window == "Flat Top":
        a0, a1, a2, a3, a4 = 0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368
        return (a0 + a1 * math.cos(math.pi * u) + a2 * math.cos(2 * math.pi * u)
                + a3 * math.cos(3 * math.pi * u) + a4 * math.cos(4 * math.pi * u))
    raise ValueError(f"unknown window: {window!r}")


def window_weights(n: int, window: str) -> list[float]:
    """Classic DSP window shape across n elements, normalized 0-1 with 1
    at the center element(s) and (for every window but Uniform) 0 at the
    two edge elements. Standard array-theory sidelobe-control windows --
    same idea as S.A.D.'s "level tapering", just a smaller, unparameterized
    set (no Chebyshev/Kaiser/Tukey, which need an extra design parameter)."""
    if n <= 1:
        return [1.0] * n
    denom = n - 1
    return [_window_shape(2.0 * k / denom - 1.0, window) for k in range(n)]


def steered_window_weights(n: int, window: str, center_index: float) -> list[float]:
    """Same window shapes as window_weights, but with the peak (u = 0)
    moved to center_index (any real value in [0, n-1], not necessarily
    the array's physical middle or even an integer element) instead of
    always (n-1)/2 -- lets the Level taper follow Arc steering's shifted
    aim point rather than staying pinned to the physical center. Falls
    back to window_weights' own symmetric shape when center_index is
    exactly (n-1)/2 (each side independently re-normalized to still
    reach the window's outer edge value there, same as window_weights)."""
    if n <= 1:
        return [1.0] * n
    left_span = center_index
    right_span = (n - 1) - center_index
    out = []
    for i in range(n):
        if i <= center_index:
            u = (i - center_index) / left_span if left_span > 0 else 0.0
        else:
            u = (i - center_index) / right_span if right_span > 0 else 0.0
        out.append(_window_shape(u, window))
    return out


def arc_steered_aim_index(n: int, angle_deg: float, steer_deg: float) -> float:
    """Continuous element index (0..n-1) of Arc steering's aim point --
    approximately where the minimum per-element delay falls once
    steer_deg is applied on top of the arc's own curvature (see
    arc_steering) -- used to re-center the Level taper window there via
    steered_window_weights instead of always the array's physical
    middle. Exact at steer_deg == 0 (returns the physical center,
    (n-1)/2) and at the physical edges (|steer_deg| >= angle_deg/2, where
    it returns index 0 or n-1 exactly); linear in the angular domain in
    between, which is a close but not exact match to the true
    (sine-weighted) optimum for a coarsely spaced array -- there's no
    reference to verify an exact formula against, so this is a
    reasonable, bounded approximation rather than a derived result."""
    center = (n - 1) / 2.0
    if n <= 1:
        return center
    if angle_deg <= 0:
        if steer_deg > 0:
            return float(n - 1)
        if steer_deg < 0:
            return 0.0
        return center
    d_phi = math.radians(angle_deg) / (n - 1)
    half_angle = math.radians(angle_deg) / 2.0
    phi_star = max(-half_angle, min(half_angle, math.radians(steer_deg)))
    return center + phi_star / d_phi


def level_taper_db(n: int, window: str, max_atten_db: float, center_index: float = None) -> list[float]:
    """Per-element gain trim, in dB, for a level taper across n elements:
    0 dB at the window's peak, fading to -max_atten_db at its minimum,
    shaped by the chosen window. The peak sits at the array's center
    element(s) unless center_index is given (see steered_window_weights),
    e.g. to keep the taper following Arc steering's shifted aim point.

    This linearly maps the window's 0-1 amplitude shape onto a
    0..-max_atten_db dB range, rather than taking a literal 20*log10 of
    the window value -- Hann/Blackman reach exactly 0 at the edges, and
    20*log10(0) is -inf, which isn't a usable gain trim. The linear
    mapping keeps the taper bounded and its depth directly set by
    max_atten_db, at the cost of not being a literal amplitude window."""
    w = (window_weights(n, window) if center_index is None
         else steered_window_weights(n, window, center_index))
    peak = max(w) if w else 1.0
    if peak <= 0:
        return [0.0] * n
    return [-max_atten_db * (1.0 - wi / peak) for wi in w]
