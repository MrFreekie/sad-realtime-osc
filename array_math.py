"""Per-element delay/gain/polarity math for common subwoofer array topologies.

Reimplements the core steering geometry behind Merlijn van Veen's S.A.D.
(Subwoofer Array Designer) spreadsheet and manual for four topologies,
without the polar/SPL prediction plots. Credit to Merlijn van Veen
(https://www.merlijnvanveen.nl/), and to Mauricio "Magu" Ramirez and Bob
"6o6" McCarthy, S.A.D.'s own credited inspiration. Sub 1 is always the
element closest to the audience ("front"); higher numbers sit further
back, except for Arc / Broadside Steering, which is symmetric about the
array's center -- see arc_steering and sub_positions_centered.

end_fire_arc_hybrid and gradient_arc_hybrid are this app's own extension,
not part of S.A.D.: End-Fire/Gradient front-rear pairs arranged as
arc-steered columns, combining Arc / Broadside Steering's horizontal
pattern control with each column's own front-to-back directivity. No
tutorial ground truth to verify these two against -- see their
docstrings and README.md.

physical_ellipse_layout and the depth_scale parameter on
_arc_column_delays_s / arc_steering / end_fire_arc_hybrid /
gradient_arc_hybrid were inspired by the Ellipse shape option in Rafael
Gomes Pereira's SubArray Vizualizer (BETA1.1d), a separate third-party
freeware calculator -- only its public interface was ever looked at
(its own calculation engine is deliberately hidden/password-protected
by its author), so the actual math here is this app's own derivation,
not a reimplementation. See README.md's Credits section.
"""
from dataclasses import dataclass
import cmath
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


def gradient_pair_delay_ms(transit_ms: float, alpha: float = 0.5) -> float:
    """Rear-element delay for a first-order differential (gradient) pair,
    generalizing the fixed cardioid case to the standard differential-
    microphone-array pattern family E(theta) = alpha + (1-alpha)*cos(theta)
    (theta measured from the front/on-axis direction):

        delay = transit_ms * alpha / (1 - alpha)

    transit_ms is the pair's own acoustic transit time (spacing_m /
    speed_mps, in ms) -- what gradient_cardioid used directly as its fixed
    delay before this generalization. Reversed polarity on the rear
    element (applied by the caller) is what turns this delay into a
    broadband null at theta_null = acos(alpha/(alpha-1)) for any alpha in
    [0, 1) -- verified by direct far-field superposition, not just the
    small-kd differential approximation the alpha formula itself is
    usually derived from (the null condition is exact at every
    frequency). alpha = 0.5 reproduces this app's original fixed cardioid
    exactly (delay = transit_ms, null at 180 deg); alpha = 0 gives a
    delay-free figure-8/dipole pair (null at 90 deg); alpha approaching 1
    approaches omni and needs impractically large delay for a fixed small
    spacing, so the UI keeps alpha below 1. Named presets (hypercardioid
    0.25, supercardioid 0.37, subcardioid 0.75) are standard first-order
    differential-microphone-array values -- see README.md."""
    if alpha >= 1.0:
        raise ValueError("alpha must be < 1.0 (1.0 is the unreachable omni limit)")
    return transit_ms * alpha / (1.0 - alpha)


def gradient_null_angle_deg(alpha: float):
    """Null angle (degrees off the front/on-axis direction) of the
    first-order pattern gradient_pair_delay_ms's alpha parameterizes --
    theta_null = acos(alpha/(alpha-1)), the inverse of
    alpha_from_null_angle_deg. Only defined for alpha in [0, 0.5]: above
    0.5 the pattern is subcardioid-and-wider, with no true null anywhere
    (see gradient_pair_delay_ms) -- returns None there. The null this
    angle describes is a full cone around the pair's own front-back axis
    (symmetric both sides, not one bearing) -- see README.md."""
    if alpha is None or alpha < 0.0 or alpha > 0.5:
        return None
    cos_null = max(-1.0, min(1.0, alpha / (alpha - 1.0)))
    return math.degrees(math.acos(cos_null))


def alpha_from_null_angle_deg(angle_deg: float):
    """Inverse of gradient_null_angle_deg: the alpha that places the
    first-order pattern's null at angle_deg (degrees off the front/
    on-axis direction), for angle_deg in [90, 180] -- the range
    reachable at all (below 90 would need a negative alpha, not a
    physically sensible differential-array weighting). Lets a broadband
    rejection null be aimed directly by angle -- e.g. at a noise-
    sensitive site's bearing off the array's own axis -- instead of via
    the less physically intuitive alpha parameter alone; this is the
    exact same broadband-exact construction as gradient_pair_delay_ms,
    just re-parameterized, not a new or different mechanism. Returns
    None outside [90, 180]."""
    if angle_deg is None or angle_deg < 90.0 or angle_deg > 180.0:
        return None
    cos_theta = math.cos(math.radians(angle_deg))
    denom = cos_theta - 1.0
    if denom == 0.0:
        return 0.0
    # Mathematically always in [0, 0.5] for angle_deg in [90, 180] -- clamp
    # away the floating-point noise that can otherwise push the 90 deg
    # case a hair below 0 (cos(90 deg) isn't exactly 0 in binary float).
    return max(0.0, min(0.5, cos_theta / denom))


def gradient_cardioid(pairs: int, spacing_m: float, speed_mps: float, gain_trim_db=None,
                       alpha: float = 0.5) -> list[SubOutput]:
    """Front/rear differential pairs. Front: 0 delay, normal polarity.
    Rear: delayed per gradient_pair_delay_ms(transit_ms, alpha), reversed
    polarity. alpha = 0.5 (default) is the original fixed cardioid,
    producing a broadband null directly behind each pair; other alpha
    values generalize the pattern to figure-8/hyper/supercardioid/
    subcardioid -- see gradient_pair_delay_ms."""
    n = pairs * 2
    trims = gain_trim_db or [0.0] * n
    transit_ms = (spacing_m / speed_mps) * 1000.0
    delay_ms = gradient_pair_delay_ms(transit_ms, alpha)
    out = []
    for p in range(pairs):
        front_idx, rear_idx = p * 2 + 1, p * 2 + 2
        out.append(SubOutput(front_idx, 0.0, trims[front_idx - 1], False))
        out.append(SubOutput(rear_idx, delay_ms, trims[rear_idx - 1], True))
    return out


def _arc_column_delays_s(n: int, spacing_m: float, angle_deg: float, speed_mps: float,
                          steer_deg: float = 0.0, depth_scale: float = 1.0) -> list[float]:
    """Per-column delay, seconds, for n columns spaced spacing_m apart in a
    straight line, delayed as if positioned on a physical arc spanning
    angle_deg (S.A.D.'s "delayed horizontal array"), optionally aimed
    off-center by steer_deg -- the shared core of arc_steering and the
    two Arc Hybrid topologies (end_fire_arc_hybrid, gradient_arc_hybrid),
    which layer this same column-to-column steering delay on top of each
    column's own internal front/rear delay. See arc_steering's docstring
    for the geometry and verification detail; this is that function's
    math extracted so the hybrids don't have to duplicate it. Always
    zero-referenced (min = 0 s), since a real delay line can't go
    negative.

    depth_scale is Ellipse mode's ratio (see physical_ellipse_layout,
    the same idea applied to a physical placement rather than a virtual
    delay curve): it scales only the curvature term (the sagitta,
    radius*(1-cos phi)), not the steer_depth term -- steering is a plain
    linear ramp across the line regardless of how deep the array's own
    virtual bow is, so it stays unscaled. depth_scale = 1.0 (default)
    reproduces the plain circle exactly."""
    if n <= 1 or (angle_deg <= 0 and steer_deg == 0):
        return [0.0] * n

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
        depth = depth_scale * radius * (1.0 - math.cos(phi)) if radius else 0.0
        x = (i - center) * spacing_m
        steer_depth = -x * math.sin(steer_rad)
        raw_delays_s.append((depth + steer_depth) / speed_mps)

    zero = min(raw_delays_s)
    return [d - zero for d in raw_delays_s]


def arc_steering(n: int, spacing_m: float, angle_deg: float, speed_mps: float,
                  gain_trim_db=None, steer_deg: float = 0.0, depth_scale: float = 1.0) -> list[SubOutput]:
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
    element is still 0 ms, since a real delay line can't go negative.

    depth_scale is Ellipse mode's electronic equivalent of
    physical_ellipse_layout's ratio -- this topology is physically a
    straight line regardless (only the virtual curvature used for delay
    changes), so there's no placement/rotation to touch, just the delay
    curve's depth. 1.0 (default) reproduces the plain circle exactly --
    see _arc_column_delays_s."""
    trims = gain_trim_db or [0.0] * n
    delays_s = _arc_column_delays_s(n, spacing_m, angle_deg, speed_mps, steer_deg, depth_scale)
    return [SubOutput(i + 1, delays_s[i] * 1000.0, trims[i], False) for i in range(n)]


def end_fire_arc_hybrid(n_columns: int, column_spacing_m: float, row_spacing_m: float,
                         angle_deg: float, speed_mps: float, gain_trim_db=None,
                         steer_deg: float = 0.0, depth_scale: float = 1.0) -> list[SubOutput]:
    """Arc / Broadside Steering, but every column is itself a front/rear
    End-Fire pair instead of a single element -- horizontal pattern
    control (arc steering across n_columns, see _arc_column_delays_s)
    combined with each column's own front-to-back directivity (End-Fire's
    forward reinforcement / rear cancellation). Kept 1:1 front:back per
    column -- this app does no polar/SPL prediction, so there's no way to
    verify an asymmetric front:back ratio against, unlike a plotting tool.

    Within a column, the rear element is the 0 ms reference and the front
    element carries an extra row_spacing_m/speed_mps on top -- same
    convention as end_fire's 2-element case -- added to that column's own
    arc-steering delay. Both elements in a column share the column's
    normal polarity (no cardioid null; see gradient_arc_hybrid for that).

    depth_scale is Ellipse mode's electronic depth ratio, same meaning
    and default as arc_steering's -- applied to the column-to-column
    curvature only, not the row_spacing_m front/rear offset.

    Returns 2*n_columns SubOutputs, ordered front/rear per column (odd =
    front, even = rear -- same pairing convention as gradient_cardioid)."""
    n = n_columns * 2
    trims = gain_trim_db or [0.0] * n
    column_delays_s = _arc_column_delays_s(n_columns, column_spacing_m, angle_deg, speed_mps,
                                            steer_deg, depth_scale)
    row_delay_ms = row_spacing_m / speed_mps * 1000.0
    out = []
    for c in range(n_columns):
        front_idx, rear_idx = c * 2 + 1, c * 2 + 2
        base_ms = column_delays_s[c] * 1000.0
        out.append(SubOutput(front_idx, base_ms + row_delay_ms, trims[front_idx - 1], False))
        out.append(SubOutput(rear_idx, base_ms, trims[rear_idx - 1], False))
    return out


def gradient_arc_hybrid(n_columns: int, column_spacing_m: float, row_spacing_m: float,
                         angle_deg: float, speed_mps: float, gain_trim_db=None,
                         steer_deg: float = 0.0, depth_scale: float = 1.0,
                         alpha: float = 0.5) -> list[SubOutput]:
    """Arc / Broadside Steering, but every column is itself a front/rear
    Gradient (cardioid) pair instead of a single element -- horizontal
    pattern control (arc steering across n_columns) combined with each
    column's own broadband rear null (Gradient's front 0 ms/normal
    polarity, rear delayed/reversed). Kept 1:1 per column, same reasoning
    as end_fire_arc_hybrid.

    Within a column, front is the 0 ms/normal-polarity reference and rear
    carries an extra delay on top (gradient_pair_delay_ms(row transit
    time, alpha), reversed polarity -- same convention and same alpha
    generalization as gradient_cardioid's pair) added to that column's
    own arc-steering delay.

    depth_scale is Ellipse mode's electronic depth ratio, same meaning
    and default as arc_steering's -- applied to the column-to-column
    curvature only, not the row_spacing_m front/rear offset.

    Returns 2*n_columns SubOutputs, ordered front/rear per column, same
    convention as end_fire_arc_hybrid."""
    n = n_columns * 2
    trims = gain_trim_db or [0.0] * n
    column_delays_s = _arc_column_delays_s(n_columns, column_spacing_m, angle_deg, speed_mps,
                                            steer_deg, depth_scale)
    row_transit_ms = row_spacing_m / speed_mps * 1000.0
    row_delay_ms = gradient_pair_delay_ms(row_transit_ms, alpha)
    out = []
    for c in range(n_columns):
        front_idx, rear_idx = c * 2 + 1, c * 2 + 2
        base_ms = column_delays_s[c] * 1000.0
        out.append(SubOutput(front_idx, base_ms, trims[front_idx - 1], False))
        out.append(SubOutput(rear_idx, base_ms + row_delay_ms, trims[rear_idx - 1], True))
    return out


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


def min_adjacent_chord(layout) -> float:
    """Smallest straight-line distance between two physically adjacent
    elements in a (depth_m, lateral_m, rotation_deg) layout list -- the
    physical-gap collision check for layouts (Ellipse, Progressive Arc)
    whose element-to-element spacing isn't constant like the plain
    circle's (physical_arc_chord_spacing), so it has to be measured
    directly from the actual placed coordinates instead of derived from
    a single angular step. None for fewer than 2 elements."""
    if len(layout) < 2:
        return None
    return min(
        math.hypot(layout[i + 1][0] - layout[i][0], layout[i + 1][1] - layout[i][1])
        for i in range(len(layout) - 1))


def physical_ellipse_layout(n: int, radius_m: float, angle_deg: float, ratio: float = 1.0):
    """(depth_m, lateral_m, rotation_deg) for each of n elements placed on
    a real ELLIPTICAL arc -- physical_arc_layout generalized with a
    depth-scale ratio (b/a): lateral is unchanged (radius_m·sin phi, same
    as the circle, so the array still spans the same width for a given
    Spacing/Angle/count), and depth is scaled by `ratio` on top of the
    circle's own sagitta (radius_m·(1-cos phi)):

        depth = -ratio * radius_m * (1 - cos phi)

    ratio = 1.0 reproduces physical_arc_layout exactly (a true circle).
    ratio < 1 flattens the bow (shallower than a true circle of that
    radius); ratio > 1 exaggerates it. This app's own extension, not
    part of S.A.D. -- no tutorial ground truth to check it against,
    unlike the plain circle above.

    Rotation is always 0.0 here, unlike physical_arc_layout's phi_deg --
    a true ellipse's aim direction is the local tangent/normal, not the
    parametric angle, and by design this app doesn't compute that (subs
    are treated as omnidirectional enough at these frequencies that aim
    rotation isn't worth tracking for this shape)."""
    if n <= 1 or angle_deg <= 0:
        return [(0.0, 0.0, 0.0) for _ in range(n)]
    d_phi = angle_deg / (n - 1)
    center = (n - 1) / 2.0
    out = []
    for i in range(n):
        phi = math.radians((center - i) * d_phi)
        lateral = radius_m * math.sin(phi)
        depth = -ratio * radius_m * (1.0 - math.cos(phi))
        out.append((depth, lateral, 0.0))
    return out


def ellipse_ratio_from_far(far):
    """Depth-scale ratio (see physical_ellipse_layout) for venue-linked
    Ellipse mode: 1.0 (a full circle-equivalent bow) at FAR >= 1, where
    the plain circle already covers the venue fine -- shrinking
    proportionally to FAR itself below 1 (venue wider than it is deep),
    flattening the bow as the room gets relatively wider, approaching a
    flat line as FAR -> 0. Continuous at FAR = 1 (both branches give
    1.0) and, unlike arc_from_far, always defined for any FAR > 0 -- the
    point of Ellipse mode is exactly to cover the wide/shallow venues
    the plain circle can't (arc_from_far returns None below FAR = 1)."""
    if far is None or far <= 0:
        return None
    return min(1.0, far)


def angle_from_far_ellipse(far):
    """Arc angle for venue-linked Ellipse mode: identical to
    arc_from_far for FAR >= 1 (so Ellipse mode matches the plain circle
    exactly whenever the circle already has an answer), and pinned at
    this app's own 180 degree Angle maximum for FAR < 1, where
    arc_from_far has no solution at all -- a venue wider than it is deep
    needs (up to) the fullest spread this app allows; it's
    ellipse_ratio_from_far's shrinking ratio that actually adapts the
    bow depth to just how wide. Continuous at FAR = 1: arc_from_far(1)
    is already exactly 180 degrees, matching the pinned branch below it."""
    if far is None or far <= 0:
        return None
    if far >= 1.0:
        return arc_from_far(far)
    return 180.0


def progressive_arc_layout(n: int, radius_m: float, angle_deg: float, ratio: float = 1.0):
    """(depth_m, lateral_m, rotation_deg) for n elements on a real
    circular arc of radius_m spanning angle_deg (same physical model as
    physical_arc_layout -- every element is still exactly radius_m from
    one center of curvature, so delay stays 0 for all of them, same as
    physical_horizontal_array), but with a non-uniform angular step
    between adjacent elements instead of physical_arc_layout's constant
    one -- a "J-array"-style progressive spread. This app's own
    extension, not part of S.A.D. -- no tutorial ground truth to check
    it against.

    `ratio` (>= 1.0) is the angular step at the array's center divided
    by the step at its edges: ratio = 1.0 reproduces physical_arc_layout
    exactly (uniform steps); ratio > 1 makes the center step
    progressively larger (tighter curvature there) and the edge steps
    progressively smaller (flatter, longer throw down the flanks) --
    chosen over the opposite direction since a flatter flank throws
    further for the same element count, while the tighter center adds
    near-field pattern control where the audience is already closest.
    The per-gap steps are linearly interpolated between center and edge
    weight and renormalized so they still sum to exactly angle_deg, so
    total coverage angle (and FAR) is unaffected by ratio.

    Rotation is still the local parametric angle (phi_deg), same as
    physical_arc_layout and for the same reason it's valid there: every
    element sits on the one true circle of radius_m, just at a
    non-uniformly chosen angular position on it, so the tangent/normal
    direction is still exactly phi_deg -- unlike the ellipse above,
    there's no shape distortion that would break that equivalence."""
    if n <= 1 or angle_deg <= 0:
        return [(0.0, 0.0, 0.0) for _ in range(n)]
    if n == 2 or ratio <= 1.0:
        return physical_arc_layout(n, radius_m, angle_deg)

    gaps = n - 1
    center_gap = (gaps - 1) / 2.0
    # Per-gap weight: 1.0 at the edges, `ratio` at the center gap(s),
    # linearly interpolated in between by how close each gap is to center.
    half_span = max(center_gap, 1e-9)
    weights = [1.0 + (ratio - 1.0) * (1.0 - abs(g - center_gap) / half_span) for g in range(gaps)]
    total_weight = sum(weights)
    d_phis = [angle_deg * w / total_weight for w in weights]

    # Cumulative angular position of each element, edge to edge, then
    # re-centered so the layout is symmetric about 0 -- same convention
    # as physical_arc_layout (element 1 at the most positive position).
    raw_phi = [0.0]
    for d_phi in d_phis:
        raw_phi.append(raw_phi[-1] + d_phi)
    mid = raw_phi[-1] / 2.0
    phis_deg = [mid - p for p in raw_phi]

    out = []
    for phi_deg in phis_deg:
        phi = math.radians(phi_deg)
        lateral = radius_m * math.sin(phi)
        depth = -radius_m * (1.0 - math.cos(phi))
        out.append((depth, lateral, phi_deg))
    return out


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


def grating_lobe_max_spacing_m(freq_hz: float, speed_mps: float, steer_deg: float = 0.0):
    """Maximum element spacing that keeps a grating lobe out of visible
    space, per the phased-array-antenna criterion

        d < lambda / (1 + |sin(steer_deg)|)

    evaluated at freq_hz (the top of the sub passband) and the array's
    current electronic Steer angle off broadside -- the rigorous,
    steer-dependent counterpart to the fixed 1/2 wavelength rule of thumb
    spacing_at_wavelength_fraction already applies to Arc / Broadside
    Steering (this app's own Steer superimposes exactly the linear
    delay-steering ramp this criterion assumes; see _arc_column_delays_s's
    steer_depth term). At steer_deg = 0 this gives a full wavelength --
    looser than the 1/2 wavelength rule of thumb, which is a
    comb-filtering guideline, not a hard grating-lobe limit -- and
    tightens smoothly as Steer moves off-centre, down to 1/2 wavelength
    at the +/-90 deg extreme. This only accounts for the Steer offset,
    not the additional local curvature of a wide Arc angle itself (a
    curved array's own edge elements have a steeper local delay gradient
    than its center) -- deliberately scoped to Steer alone, the one
    input the existing spacing rule ignored entirely; see README.md."""
    if not freq_hz or freq_hz <= 0 or not speed_mps or speed_mps <= 0:
        return None
    wavelength = speed_mps / freq_hz
    return wavelength / (1.0 + abs(math.sin(math.radians(steer_deg))))


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


def focus_point(n: int, spacing_m: float, focus_x_m: float, focus_y_m: float,
                 speed_mps: float, gain_trim_db=None) -> list[SubOutput]:
    """Near-field acoustic focusing ("Destruction Mode"): n elements in a
    straight line (same physical layout as Arc / Broadside Steering --
    evenly spaced, centered, sub_positions_centered's convention, all at
    depth 0), delayed so every element's contribution arrives at one
    target point (focus_x_m, focus_y_m -- focus_x_m out in front of the
    line, focus_y_m lateral offset from its center) at the same instant,
    for maximum constructive buildup there.

    delay_i = (max_j distance_j - distance_i) / speed_mps -- the element
    closest to the focus point (shortest travel time) is delayed the
    most, since it has to "wait" for the sound from farther elements to
    also arrive; the single farthest element is the 0 ms reference, same
    zero-referencing idea as delays_from_depth. This is standard
    near-field beamforming/focusing, not a S.A.D. topology -- this app's
    own extension, verifiable directly from geometry (no tutorial ground
    truth needed: it's exact by construction, not an approximation)."""
    trims = gain_trim_db or [0.0] * n
    if n <= 0:
        return []
    lateral = sub_positions_centered(n, spacing_m)
    distances = [math.hypot(focus_x_m, focus_y_m - y) for y in lateral]
    max_d = max(distances)
    return [SubOutput(i + 1, (max_d - distances[i]) / speed_mps * 1000.0, trims[i], False)
            for i in range(n)]


def avoid_point(n: int, spacing_m: float, avoid_x_m: float, avoid_y_m: float,
                 speed_mps: float, gain_trim_db=None) -> list[SubOutput]:
    """The destructive twin of focus_point ("Protection Mode"): n elements
    in the identical physical layout (straight line, evenly spaced,
    centered, all at depth 0), delayed by focus_point's own exact
    time-alignment law -- every element's contribution still arrives at
    the target point at the same instant, frequency-independent, exact
    by construction from geometry alone -- but with alternating polarity
    (odd index normal, even index reversed, same convention as
    gradient_cardioid's front/rear pairing) instead of focus_point's
    all-normal polarity, so the aligned arrivals cancel instead of add.

    This is the same "delay-align, then invert half" trick that already
    makes gradient_cardioid's rear null exact at every frequency, not a
    new or different mechanism -- see gradient_pair_delay_ms's docstring
    for the underlying far-field superposition argument (the null
    condition here is even simpler: equal-magnitude opposite-polarity
    contributions arriving at the *same instant* cancel exactly,
    regardless of frequency, with no delay term to solve for).

    For even n this needs no gain correction: n/2 elements normal and
    n/2 reversed, equal amplitude, sum to exactly zero at the target. For
    odd n, the extra unpaired element goes to the normal (odd-index)
    group, so that group is one element larger -- it gets attenuated by
    20*log10(n_reversed/n_normal) dB so both groups' total linear
    amplitude still match exactly. gain_trim_db, if given, is added on
    top of (not instead of) this balancing correction.

    Honesty note, same standard as focus_point's own "exact by
    construction" claim: this is exact in arrival-time/phase terms, not
    an SPL/amplitude-spreading model -- this app has no polar/SPL
    prediction at all, so real cancellation depth at the target also
    depends on each element's actual level actually arriving there
    (near-field distance-spreading differences across a physically
    spread-out array aren't modeled). Treat the target as where the
    array's phase is exactly opposed, not as a guaranteed real-world SPL
    floor -- cross-check a heavy reliance on this against measurement or
    a prediction tool, same advice as the taper cost readout gives for
    heavy tapers."""
    trims = gain_trim_db or [0.0] * n
    if n <= 0:
        return []
    lateral = sub_positions_centered(n, spacing_m)
    distances = [math.hypot(avoid_x_m, avoid_y_m - y) for y in lateral]
    max_d = max(distances)
    delays_ms = [(max_d - d) / speed_mps * 1000.0 for d in distances]

    n_normal = (n + 1) // 2
    n_reversed = n // 2
    balance_db = 20.0 * math.log10(n_reversed / n_normal) if n_reversed > 0 else 0.0

    out = []
    for i in range(n):
        idx = i + 1
        reversed_pol = (idx % 2 == 0)
        correction = 0.0 if reversed_pol else balance_db
        out.append(SubOutput(idx, delays_ms[i], trims[i] + correction, reversed_pol))
    return out


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


def sub_positions_arc_hybrid_lateral(n_columns: int, column_spacing_m: float) -> list[float]:
    """Lateral (Y) position for the Arc Hybrid topologies -- each column's
    centered lateral position (sub_positions_centered), repeated twice
    since the front and rear element of a column share the same lateral
    position, differing only in depth (same reasoning as
    sub_positions_gradient's side-by-side pairing, just centered on the
    array like Arc / Broadside Steering instead of laid out end to end)."""
    out = []
    for y in sub_positions_centered(n_columns, column_spacing_m):
        out.extend([y, y])
    return out


def sub_positions_arc_hybrid_depth(n_columns: int, row_spacing_m: float) -> list[float]:
    """Depth (X) position for the Arc Hybrid topologies -- front row at 0
    (closest to the audience), rear row at -row_spacing_m, repeated per
    column -- same sign convention as End-Fire / Physical Horizontal
    Array's X (<= 0, set-back relative to the front)."""
    out = []
    for _ in range(n_columns):
        out.extend([0.0, -row_spacing_m])
    return out


def array_length(n: int, spacing_m: float) -> float:
    """Total span of a linear (n-1)-gap array, in meters -- S.A.D.'s
    "array length" info-panel value."""
    return max(n - 1, 0) * spacing_m


LEVEL_TAPER_WINDOWS = ["Uniform", "Hann", "Hamming", "Blackman", "Bartlett", "Welch",
                       "Blackman-Harris", "Nuttall", "Flat Top", "Chebyshev", "Taylor"]

PARAMETRIC_TAPER_WINDOWS = ("Chebyshev", "Taylor")
"""Windows that need an extra sidelobe-level (dB) design parameter, unlike
the other LEVEL_TAPER_WINDOWS -- computed as a whole discrete n-point array
(_chebyshev_weights / _taylor_weights) rather than sampled from a
continuous shape function of position like _window_shape's windows, and
mapped to gain trim by a literal 20*log10(w/peak) (level_taper_db) instead
of the linear 0..-max_atten_db remap the other windows use, since their
whole point is that the dB parameter *is* the actual sidelobe level, not
an arbitrary edge-attenuation target."""

_TAYLOR_NBAR = 4
"""Number of nearly-equal-level near-in sidelobes for the Taylor window --
fixed rather than exposed as a second UI parameter (matches SciPy's and
MATLAB's own default), so Taylor only needs the same one sidelobe-level
(dB) control Chebyshev does."""


def _dft_real(seq) -> list[float]:
    """Real part of the DFT of a complex sequence (X[k] = sum_m
    seq[m]*exp(-2j*pi*k*m/n)), by direct summation -- O(n^2), fine for
    this app's element counts (<= 48). No numpy/scipy dependency; used
    only by _chebyshev_weights' frequency-sampling construction."""
    n = len(seq)
    out = []
    for k in range(n):
        s = 0j
        for m in range(n):
            s += seq[m] * cmath.exp(-2j * math.pi * k * m / n)
        out.append(s.real)
    return out


def _chebyshev_weights(n: int, sidelobe_db: float) -> list[float]:
    """Dolph-Chebyshev window, n points, equal-ripple sidelobes
    sidelobe_db below the main lobe -- the standard frequency-sampling
    construction (Dolph 1946): evaluate the Chebyshev polynomial of order
    n-1 on n frequency samples, inverse-DFT back to the element domain,
    normalize to peak 1.0. A pure-Python port of SciPy's
    scipy.signal.windows.chebwin (sym=True case), verified against it by
    reconstructing the array factor and confirming every sidelobe lands
    at exactly -sidelobe_db (e.g. n=16, 30 dB -> every sidelobe peak
    -30.00 dB, to 2 decimal places, across a full +/-90 deg sweep).
    Gives the narrowest possible main lobe for that sidelobe level --
    the reason this taper exists at all; see README.md."""
    if n <= 1:
        return [1.0] * n
    order = n - 1.0
    beta = math.cosh(1.0 / order * math.acosh(10.0 ** (abs(sidelobe_db) / 20.0)))
    p = []
    for k in range(n):
        x = beta * math.cos(math.pi * k / n)
        if x > 1:
            val = math.cosh(order * math.acosh(x))
        elif x < -1:
            val = (2 * (n % 2) - 1) * math.cosh(order * math.acosh(-x))
        else:
            val = math.cos(order * math.acos(x))
        p.append(val)
    if n % 2:
        full = _dft_real(p)
        n2 = (n + 1) // 2
        w_head = full[:n2]
        w = list(reversed(w_head[1:n2])) + w_head
    else:
        p_shifted = [p[k] * cmath.exp(1j * math.pi * k / n) for k in range(n)]
        full = _dft_real(p_shifted)
        n2 = n // 2 + 1
        w_tail = full[1:n2]
        w = list(reversed(w_tail)) + w_tail
    peak = max(w)
    if peak <= 0:
        return [1.0] * n
    return [wi / peak for wi in w]


def _taylor_weights(n: int, sidelobe_db: float, nbar: int = _TAYLOR_NBAR) -> list[float]:
    """Taylor window, n points: approximates Dolph-Chebyshev's constant
    sidelobe_db-down sidelobe level for the nbar near-in sidelobes, then
    lets the pattern taper off further out instead of holding dead level
    all the way to +/-90 deg (Taylor 1955) -- the SAR/radar-community
    successor to Chebyshev, standard wherever a slightly wider main lobe
    is worth trading for less total sidelobe energy. Pure-Python port of
    SciPy's scipy.signal.windows.taylor (sym=True, norm=True); see
    Carrara/Goodman/Majewski, "Spotlight Synthetic Aperture Radar", App.
    D.2 for the reference algorithm."""
    if n <= 1:
        return [1.0] * n
    b = 10.0 ** (sidelobe_db / 20.0)
    a = math.acosh(b) / math.pi
    s2 = nbar ** 2 / (a ** 2 + (nbar - 0.5) ** 2)
    ma = list(range(1, nbar))
    m2 = [m * m for m in ma]
    signs = [1.0 if i % 2 == 0 else -1.0 for i in range(len(ma))]
    f_m = []
    for mi in range(len(ma)):
        numer = signs[mi]
        for mj in range(len(ma)):
            numer *= (1.0 - m2[mi] / s2 / (a ** 2 + (ma[mj] - 0.5) ** 2))
        denom = 1.0
        for mj in range(len(ma)):
            if mj != mi:
                denom *= (1.0 - m2[mi] / m2[mj])
        f_m.append(numer / (2.0 * denom))

    def w_of(x):
        total = 1.0
        for mi, m in enumerate(ma):
            total += 2.0 * f_m[mi] * math.cos(2.0 * math.pi * m * (x - n / 2.0 + 0.5) / n)
        return total

    w = [w_of(float(k)) for k in range(n)]
    center = w_of((n - 1) / 2.0)
    if center == 0:
        return w
    return [wi / center for wi in w]


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


def window_weights(n: int, window: str, sidelobe_db: float = 30.0) -> list[float]:
    """Window shape across n elements, normalized 0-1 with 1 at the
    center element(s) -- for the 9 classic DSP windows (0 at the two
    edge elements, every one but Uniform), sampled from _window_shape's
    continuous formula; for Chebyshev/Taylor (PARAMETRIC_TAPER_WINDOWS),
    computed as a whole discrete n-point array by _chebyshev_weights /
    _taylor_weights instead, using sidelobe_db as their one extra design
    parameter (ignored for every other window). Standard array-theory
    sidelobe-control windows -- same idea as S.A.D.'s "level tapering",
    generalized beyond its original unparameterized set."""
    if window in PARAMETRIC_TAPER_WINDOWS:
        if window == "Chebyshev":
            return _chebyshev_weights(n, sidelobe_db)
        return _taylor_weights(n, sidelobe_db)
    if n <= 1:
        return [1.0] * n
    denom = n - 1
    return [_window_shape(2.0 * k / denom - 1.0, window) for k in range(n)]


def _interp_shape(weights: list[float], u: float) -> float:
    """Piecewise-linear interpolation of a discrete n-point window
    (weights, implicitly sampled at u_k = 2k/(n-1) - 1, k = 0..n-1) at an
    arbitrary position u in [-1, 1] (clamped if outside) -- lets a
    discrete, whole-array-constructed window (Chebyshev/Taylor, which
    have no continuous formula of their own the way _window_shape's
    windows do) be treated as an evaluable shape function the same way
    those are, so steered_window_weights' re-centering can apply to them
    too instead of leaving them un-steered. This is the same honesty
    trade-off arc_steered_aim_index and steered_window_weights already
    make for the other 9 windows -- a reasonable, bounded approximation
    (re-sampling a Chebyshev-optimal array off-center forfeits its exact
    equal-ripple property, same as those windows' own steering was never
    claimed to be optimal either), not a derived or verified result."""
    n = len(weights)
    if n <= 1:
        return weights[0] if weights else 1.0
    u = max(-1.0, min(1.0, u))
    pos = (u + 1.0) / 2.0 * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return weights[lo] * (1.0 - frac) + weights[hi] * frac


def steered_window_weights(n: int, window: str, center_index: float,
                            sidelobe_db: float = 30.0) -> list[float]:
    """Same window shapes as window_weights, but with the peak (u = 0)
    moved to center_index (any real value in [0, n-1], not necessarily
    the array's physical middle or even an integer element) instead of
    always (n-1)/2 -- lets the Level taper follow Arc steering's shifted
    aim point rather than staying pinned to the physical center. Falls
    back to window_weights' own symmetric shape when center_index is
    exactly (n-1)/2 (each side independently re-normalized to still
    reach the window's outer edge value there, same as window_weights).

    Chebyshev/Taylor (PARAMETRIC_TAPER_WINDOWS) use the same left/right
    asymmetric-stretch construction as every other window here, just
    evaluated against _interp_shape's linear interpolation of the plain
    centered n-point array (window_weights) instead of _window_shape's
    continuous formula, since they have no such formula of their own --
    see _interp_shape."""
    if n <= 1:
        return [1.0] * n
    if window in PARAMETRIC_TAPER_WINDOWS:
        base = window_weights(n, window, sidelobe_db)
        shape = lambda u: _interp_shape(base, u)
    else:
        shape = lambda u: _window_shape(u, window)
    left_span = center_index
    right_span = (n - 1) - center_index
    out = []
    for i in range(n):
        if i <= center_index:
            u = (i - center_index) / left_span if left_span > 0 else 0.0
        else:
            u = (i - center_index) / right_span if right_span > 0 else 0.0
        out.append(shape(u))
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


def level_taper_db(n: int, window: str, max_atten_db: float, center_index: float = None,
                    sidelobe_db: float = 30.0) -> list[float]:
    """Per-element gain trim, in dB, for a level taper across n elements.

    For the 9 classic DSP windows: 0 dB at the window's peak, fading to
    -max_atten_db at its minimum, shaped by the chosen window. This
    linearly maps the window's 0-1 amplitude shape onto a
    0..-max_atten_db dB range, rather than taking a literal 20*log10 of
    the window value -- Hann/Blackman reach exactly 0 at the edges, and
    20*log10(0) is -inf, which isn't a usable gain trim. The linear
    mapping keeps the taper bounded and its depth directly set by
    max_atten_db, at the cost of not being a literal amplitude window.
    The peak sits at the array's center element(s) unless center_index is
    given (see steered_window_weights), e.g. to keep the taper following
    Arc steering's shifted aim point.

    For Chebyshev/Taylor (PARAMETRIC_TAPER_WINDOWS): max_atten_db is
    ignored and the trim is instead a literal 20*log10(w/peak) of the
    window's own amplitude weights -- unlike the other 9 windows, these
    never reach exactly 0 for a sane sidelobe_db, so there's no -inf
    problem to work around, and taking the literal dB is the whole
    point: it's what makes the edge elements land at (approximately, and
    for Chebyshev exactly, when centered) -sidelobe_db, the equal-ripple
    sidelobe level the window was designed to give. center_index still
    applies via steered_window_weights' interpolated re-centering (see
    its docstring) -- steering trades away that exact-at-center-position
    guarantee the same way it does for every other window here."""
    if window in PARAMETRIC_TAPER_WINDOWS:
        w = (window_weights(n, window, sidelobe_db) if center_index is None
             else steered_window_weights(n, window, center_index, sidelobe_db))
        peak = max(w) if w else 1.0
        if peak <= 0:
            return [0.0] * n
        return [20.0 * math.log10(max(wi, 1e-9) / peak) for wi in w]
    w = (window_weights(n, window) if center_index is None
         else steered_window_weights(n, window, center_index))
    peak = max(w) if w else 1.0
    if peak <= 0:
        return [0.0] * n
    return [-max_atten_db * (1.0 - wi / peak) for wi in w]


def taper_onaxis_loss_db(gain_trim_db: list[float]) -> float:
    """On-axis SPL change, in dB, from applying gain_trim_db (e.g.
    level_taper_db's output) relative to every element at 0 dB
    (untapered) -- the number that matters most for a real show: a
    correctly steered/delayed array sums its elements *in phase* on
    axis, so the coherent on-axis pressure scales with the mean of the
    LINEAR gains, not their power:

        loss_db = 20*log10( mean(10**(g/20) for g in gain_trim_db) )

    This is the practical cost side of any taper (classic window or
    Chebyshev/Taylor alike) that the pattern-control benefit doesn't
    show up in a simulator's polar plot: every dB of taper depth you
    dial in for sidelobe control is a dB you're not getting back as
    forward SPL, because the attenuated elements are still there,
    still costing you an amplifier channel and a box, contributing less
    toward the front. 0.0 for Uniform / 0 dB max atten (every element
    still at unity)."""
    if not gain_trim_db:
        return 0.0
    lin = [10.0 ** (g / 20.0) for g in gain_trim_db]
    mean_lin = sum(lin) / len(lin)
    if mean_lin <= 0:
        return float("-inf")
    return 20.0 * math.log10(mean_lin)


def taper_power_loss_db(gain_trim_db: list[float]) -> float:
    """Total radiated acoustic power change, in dB, from applying
    gain_trim_db relative to uniform -- the incoherent sum of each
    element's own power (proportional to gain squared), not the
    coherent on-axis sum taper_onaxis_loss_db computes. This is the
    number closer to total amplifier/driver headroom spent rather than
    what a listener on axis actually hears:

        loss_db = 10*log10( mean(10**(g/10) for g in gain_trim_db) )

    Always >= taper_onaxis_loss_db for the same taper, since the mean
    of squared linear gains is never less than the square of their mean
    (variance can't be negative) -- tapering always costs more on-axis
    SPL than it costs total radiated power, because some of an
    untapered element's power would only have gone into sidelobes
    anyway."""
    if not gain_trim_db:
        return 0.0
    lin = [10.0 ** (g / 10.0) for g in gain_trim_db]
    mean_lin = sum(lin) / len(lin)
    if mean_lin <= 0:
        return float("-inf")
    return 10.0 * math.log10(mean_lin)
