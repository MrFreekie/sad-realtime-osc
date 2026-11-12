// Help text for the "?" buttons, ported from the desktop app's tooltips
// (realtime_app/sad_realtime_osc.py, _help_icon calls). Keep the two in
// step when either changes. References to OSC are reworded for the web,
// which has no OSC output. The per-topology note comes from the model
// (web/py/model.py topology_note), not from here.

export const HELP = {
  project:
    "Saves every setting -- topology, spacing, environment, group, etc. -- to a .sadrt file (plain JSON) you can " +
    "reload later, hand to another engineer, or open in the desktop app (and vice versa). \"New\" resets everything " +
    "to factory defaults (with a confirmation first). The browser also remembers your last settings on this device, " +
    "so a reloaded tab comes back where you left it.",

  row_spacing:
    "Front-to-back spacing within each column, for the two Arc Hybrid topologies -- the internal End-Fire/Gradient " +
    "pair depth, separate from Spacing above (which is the column-to-column lateral spacing along the arc). Always " +
    "rated against 1/4 wavelength (like End-Fire/Gradient's own Spacing), regardless of the 1/2 wavelength rule used " +
    "for the column Spacing above.",

  steer:
    "Redirects the whole arc's aim off-centre without changing its coverage angle (FAR) -- for venues that aren't " +
    "symmetrical about the array's own centreline. Positive steers toward the lowest-numbered sub (sub 1). 0 = the " +
    "default symmetric aim, straight ahead.",

  ellipse_ratio:
    "Depth-scale ratio for Shape = Ellipse: 1.0 is a true circle (identical to Shape = Circle); below 1 flattens the " +
    "bow, above 1 exaggerates it. For Physical Horizontal Array this scales the real physical placement (Radius stays " +
    "what it is); for Arc / Broadside Steering and the two Arc Hybrids, which are physically a straight line either " +
    "way, it scales the virtual curvature used for delay instead -- same ratio, same effect on the pattern, just " +
    "electronic rather than physical. Rotation is not computed for Ellipse (always 0°, Physical Horizontal Array only " +
    "-- the other three never had rotation to begin with) -- a true ellipse's aim direction is the local tangent, not " +
    "the parametric angle, and this app treats subs as omnidirectional enough at these frequencies that it isn't worth " +
    "tracking for this shape. This app's own extension, not part of S.A.D. -- no tutorial ground truth to verify it " +
    "against.",

  progression:
    "Center:edge angular-step ratio for Progressive Arc -- 1.0 is a uniform circular arc (identical to Physical " +
    "Horizontal Array); above 1 makes the center gap(s) progressively wider (tighter curvature there) and the edge " +
    "gaps progressively narrower (flatter, longer throw down the flanks), while total coverage angle (and FAR) stays " +
    "exactly what Arc (°) says. Rotation is still the true local aim angle here, unlike Ellipse -- every element still " +
    "sits on one real circle of the given Radius, just unevenly spaced along it. This app's own extension, not part of " +
    "S.A.D. -- no tutorial ground truth to verify it against.",

  focus:
    "Focus Point (\"Destruction Mode\") delays every sub so its output arrives at one target point at the same " +
    "instant, for maximum constructive buildup there -- Focus X is how far out in front of the line the target sits, " +
    "Focus Y is its lateral offset from the line's own center (0 = dead ahead). Near-field acoustic focusing, exact by " +
    "construction (not an approximation) -- this app's own extension, not a S.A.D. topology.",

  avoid:
    "Avoid Point (\"Protection Mode\") -- the destructive twin of Focus Point: same time-alignment delay to the target " +
    "(Avoid X out in front, Avoid Y lateral offset from centre), but alternating polarity (odd sub normal, even " +
    "reversed) so the aligned arrivals cancel instead of add -- an exact, frequency-independent null, the same " +
    "delay-align-then-invert trick that already makes Gradient/Cardioid's rear null exact, not a new mechanism. For an " +
    "odd sub count the extra unpaired sub's polarity group is attenuated so both groups' total level still match " +
    "exactly (visible as a small negative Gain Trim on that group). This is exact in arrival-time/phase terms only -- " +
    "this app has no polar/SPL prediction, so real-world cancellation depth also depends on each element's actual " +
    "level reaching the target (distance-spreading differences across the array aren't modelled). Treat the point as " +
    "where the array's phase is exactly opposed, not a guaranteed real-world silent spot -- cross-check a " +
    "noise-sensitive application against measurement.",

  pattern:
    "Front/rear delay ratio for the differential (Gradient) pair, generalizing the fixed cardioid null (α = 0.5, " +
    "straight behind the pair) to the standard first-order pattern family E(θ) = α + (1-α)·cosθ: rear delay = transit " +
    "time × α/(1-α), still reversed polarity. Named presets are the standard values (Figure-8 0, Hypercardioid 0.25, " +
    "Supercardioid 0.37, Cardioid 0.5); editing α directly resets Pattern to \"— custom —\", same as Sub box " +
    "dimensions' Profile field. Capped below 1.0 -- that's the unreachable omni limit, needing impractically large " +
    "delay for a fixed small spacing. No Subcardioid preset (α = 0.75) -- unlike these four, it has no true null " +
    "anywhere, so at real sub spacing across a real passband its shallow, unanchored pattern can fully invert (front " +
    "and rear swap) rather than just losing depth gracefully; still reachable by typing α > 0.5 by hand if you " +
    "understand that trade-off.",

  null_angle:
    "The same broadband null Pattern/α already places, dialled directly by bearing instead: degrees off the pair's " +
    "own front (on-axis) direction, 90° = Figure-8's side null through 180° = Cardioid's rear null. Exact by " +
    "construction, the same delay-align-then-invert mechanism, not a different or weaker one -- verified by far-field " +
    "superposition at every angle in range, not just the named presets. Sets α to match and resets Pattern to " +
    "\"— custom —\", same convention as editing α directly. The null is a full cone around the array's own axis -- " +
    "symmetric both sides, not one compass bearing -- so this dials how far round from the front the rejection sits, " +
    "not left vs. right; for the two Arc Hybrids, combine this with Steer (which shifts the array's own aim " +
    "asymmetrically) to bias a broad rejection zone toward one specific side of a noise-sensitive site, a far more " +
    "robust tool for that than Avoid Point's single fragile point-null. No angle here below 90° or above α = 0.5 " +
    "(Subcardioid and wider) -- neither has a true null to dial; typing a custom α > 0.5 by hand leaves this showing " +
    "its last valid value rather than a meaningless one.",

  taper:
    "Live gain taper, always following each sub's Gain trim -- 0 dB at the window's peak, fading to -max atten at its " +
    "minimum, shaped by the chosen window (11 sidelobe-control windows; Uniform or 0 dB max atten = flat, no taper). " +
    "For the two Arc Hybrid topologies, the taper is computed across columns, not individual subs -- both the front " +
    "and rear sub in a column get that column's trim. For Arc / Broadside Steering and the Arc Hybrids, the peak " +
    "follows the Steer angle instead of always sitting at the array's physical centre -- 0° Steer keeps it centred. " +
    "Flat Top is a known exception to \"monotonic taper\" — it's an amplitude-accuracy window with a small ripple near " +
    "the edges by design, so it can dip slightly past -max atten there; that's correct for Flat Top, not a bug. " +
    "Chebyshev/Taylor replace Max atten with Sidelobe (dB): their gain trim is a literal dB of the window's own " +
    "equal-ripple amplitude shape, not the linear max-atten remap the other 9 windows use, so the edge elements land " +
    "at (Chebyshev: exactly; Taylor: approximately) that many dB down when centred. They follow Steer the same as the " +
    "other 9 windows too, by linearly interpolating the plain centred array -- off-centre this trades away the exact " +
    "equal-ripple guarantee. This app has no polar/SPL prediction, so you won't see the sidelobe reduction visually — " +
    "it's standard array theory applied on faith, not a result verified in-app.",

  taper_cost:
    "The real-world price of this taper, not visible in a polar-prediction plot: on-axis loss is the forward SPL you " +
    "give up because a correctly steered array sums its elements in phase, so on-axis pressure follows the mean of " +
    "the linear gains -- every dB of edge attenuation you dial in for sidelobe control is a dB you don't get back as " +
    "forward level, from a box that's still costing you an amplifier channel and rigging weight. Total power is the " +
    "same idea for the incoherent power sum instead -- closer to overall amplifier/driver headroom spent than to what " +
    "the room hears. Total power loss is always the smaller of the two (less negative). Applies to every window here, " +
    "not just Chebyshev/Taylor. Deep sidelobe targets on a small array can cost several dB of forward level for a " +
    "pattern benefit this app can't show you -- worth cross-checking against a prediction tool before committing a " +
    "show to a heavy taper.",

  makeup:
    "Adds a gain correction to Group level equal to the on-axis taper cost shown above, to win back the forward level " +
    "the taper gave up. Added on top of whatever Group level you already have, tracked separately (see the orange " +
    "note) so clicking again replaces its own previous contribution instead of stacking, and Clear removes exactly " +
    "that amount. It's a snapshot: if you change the taper afterwards, click Makeup Gain again to refresh it. Group " +
    "level is clamped to its -40..+18 dB range. Watch amplifier and DSP headroom -- this raises every sub by that " +
    "amount, including the ones the taper attenuated least.",

  bandwidth:
    "Optimum spacing = fraction of a wavelength at the top of the passband (¼λ for End-Fire/Gradient, ½λ for Arc / " +
    "Broadside Steering and the two Arc Hybrids, applied to their column spacing) — the S.A.D. rule of thumb.",

  row_optimum:
    "Optimum Row spacing for the two Arc Hybrids -- always ¼ wavelength at the same High (Hz) above, the " +
    "End-Fire/Gradient rule, since Row spacing is that same front/rear pair depth inside each column, regardless of " +
    "the ½λ rule used for the column Spacing above.",

  grating:
    "Steer-aware grating-lobe spacing limit: d < λ / (1 + |sin(Steer)|), the phased-array-antenna criterion for " +
    "keeping a spurious lobe out of visible space, evaluated at High (Hz) and the array's current Steer angle -- a " +
    "rigorous, steer-dependent check alongside the ½λ rule of thumb above, which is a comb-filtering guideline that " +
    "doesn't account for Steer at all. Loosest (a full wavelength) at Steer = 0°, tightening smoothly to ½λ at ±90°. " +
    "Only accounts for Steer, not the additional local curvature of a wide Arc angle itself.",

  info:
    "array 1λ = frequency whose wavelength equals the array length (directivity onset). spk dist NNN° = frequency at " +
    "which the element spacing represents that many degrees of phase. S.A.D.'s info panel also shows -6 dB ONAX and " +
    "max angle, which need full polar/SPL summation and are left out here by design.\n\nvirtual source = where the " +
    "sound appears to come from: the point behind the array's centre that the delays (Arc / Arc Hybrids: including " +
    "Steer and Ellipse ratio) or the real arc (Physical / Progressive: its centre of curvature) imitate. 'behind' is " +
    "distance back from the array's centre line; 'off-axis' is sideways toward the sub named. For the electronic " +
    "topologies it is a least-squares fit of a point source to the applied delays, not an exact result -- this app's " +
    "own readout with no S.A.D. ground truth; '(rough fit)' appears when the delays are a poor point-source match " +
    "(wide arc with heavy Steer). Flat line (Arc angle 0): source at infinity. Measured from the array centre; for " +
    "the hybrids, column geometry only (front/rear row offset ignored).",

  units:
    "Applies to every length you enter: Spacing, box Width/Depth/Gap, and the distance fields in Group, Sub → tops, " +
    "and Venue → arc. Everything is still stored and computed in metres internally — this only changes what you type " +
    "and see in those fields. Read-only results (the table's X/Y columns, collision/alignment/FAR text) stay in metres.",

  xy:
    "Which axis is which in the per-sub table's X/Y columns and Manual mode's typed X/Y fields. \"L-Acoustics Mode\" " +
    "(default): Y = depth, into the room (front-to-back); X = lateral, across the room -- matching L-Acoustics' own " +
    "layout tools. \"d&b Mode\": swapped -- X = depth, into the room; Y = lateral, across the room -- this app's " +
    "original convention. Purely a labelling/entry convention -- the underlying geometry and delay math are identical " +
    "either way, only which column means which physical direction changes.",

  dsp:
    "This sample rate is what the per-sub table's Delay and Delay + Group columns convert to when \"Show delay as\" " +
    "is set to samples -- switch it to ms to see the same values as milliseconds instead. The CSV export includes " +
    "both.",

  environment:
    "Sets the speed of sound used everywhere (delay math, wavelength readouts, group delay ↔ distance), via the " +
    "Cramer (1993) equation — temperature, humidity and altitude (through the resulting air pressure), accurate to " +
    "<=300 ppm within 0-30°C / 75-102 kPa. Altitude uses a standard-atmosphere pressure model, not today's actual " +
    "weather.",

  venue:
    "Length = throw/depth (front-to-back), width = coverage (side-to-side). FAR = length / width; \"Set arc\" applies " +
    "the solved Angle to whichever angle-based topology is already active (Arc / Broadside Steering, either Arc " +
    "Hybrid, Physical Horizontal Array, Progressive Arc), or switches to Arc / Broadside Steering first if not. For a " +
    "Shape = Ellipse topology, it solves venues wider than they are deep (FAR < 1) too -- Angle pins at 180° instead " +
    "of the usual arc = 2·asin(1/FAR), which has no solution there (see the Ellipse ratio row below for that case's " +
    "other half).",

  venue_ellipse:
    "Ellipse ratio implied by this venue's proportions -- 1.0 at FAR >= 1 (the plain circle already covers those " +
    "venues fine) shrinking below 1 as the room gets wider than it is deep, continuous with \"Set arc\"'s own Angle = " +
    "180° pin at FAR < 1. Independent of \"Set arc\" -- \"Use\" only ever touches Ellipse ratio, never Angle, so you " +
    "can apply one without the other. Only shown for a Shape = Ellipse topology.",

  box:
    "Pick a profile to fill Width/Depth from a known box, or edit either directly (resets Profile to \"custom\"). " +
    "Width applies to Arc / Broadside Steering, Physical Horizontal Array, Progressive Arc, and Focus/Avoid Point " +
    "(boxes side by side); depth applies to End-Fire and Gradient (boxes front to back). The two Arc Hybrids check " +
    "both: width against Spacing (column-to-column) and depth against Row spacing (front/rear pair). \"Set min " +
    "spacing\" sets Spacing to that dimension exactly (boxes touching); \"Set spacing (+ gap)\" adds the gap value on " +
    "top, for cable/rigging clearance -- both only ever touch Spacing, not Row spacing, and are no-ops for Physical " +
    "Horizontal Array/Progressive Arc, which have no Spacing field. Profiles load from sub_profiles.csv.",

  acoustic_centre:
    "Merlijn van Veen's low-frequency acoustic centre research: a sealed/vented sub's true radiating point may sit " +
    "outside the enclosure, in front of it, below ~100 Hz — not settled physics, but a plausible, documented " +
    "correction. When enabled, this offset is subtracted from \"Sub dist. to FOH\" in the Sub → tops alignment wizard " +
    "(the sub's true acoustic distance is shorter than its cabinet-measured distance by this amount). It does not " +
    "affect inter-sub delay/spacing math — a uniform forward shift of every sub changes none of the path-length " +
    "differences between them, only distance to an external reference like FOH.",

  group:
    "Group delay adds to every sub's Delay to make \"Delay + Group\" — enter it directly in ms or as an equivalent " +
    "distance (e.g. the subs sit this much closer to FOH than the mains); the two stay in sync via the speed of sound " +
    "at the current temperature (Environment panel). Group polarity flips every sub's Polarity on top of whatever the " +
    "topology computed. Group level adds to every sub's Gain trim to make \"Gain + Group\" — e.g. trimming the whole " +
    "sub array relative to the mains without touching each sub's individual trim.",

  prealign:
    "Factory pre-alignment delay offsets from the L-Acoustics Drive System Preset Guide (\"Pre-alignment delay " +
    "values\", p.93) — corrections to add before your own geometric alignment, measured with the enclosures at the " +
    "same physical location. \"Use → Group delay\" ADDS the sub-side value on top of whatever is already in Group " +
    "delay (ms), tracked separately and shown in orange in the Group panel so you always see exactly what this panel " +
    "contributed; \"Clear\" removes only that contribution, leaving any group delay you dialled in by hand untouched. " +
    "Often the sub-side value is 0 ms (the correction lands on the main system instead) — \"Use\" still confirms that " +
    "and the note explains where the remaining delay belongs. The main-side value is shown for reference only — it " +
    "belongs on the main system's own processor, which this app doesn't control. Green Positive (+) / red Negative " +
    "(−) is that system's own factory polarity (\"Use\" never applies this for you — a Negative sub combo adds a ⚠ " +
    "warning to the Group delay note instead, telling you to flip Group polarity to Inverted by hand). A bracketed " +
    "Cardioid/Extended cardioid/Noise Control detail appears only for presets where one enclosure within that " +
    "cluster is reversed internally by the preset itself; always informational. Small seed dataset (K1 family only, " +
    "from prealign_delays.csv).",

  wizard:
    "Distances are measured from each array's reference point (subs: the front row) to FOH / the listening position. " +
    "\"Mains delay\" is whatever electrical delay is already dialled into the mains, if any — 0 if none. Required " +
    "group delay = mains delay + (mains distance − sub distance) / speed of sound (Environment panel temperature). A " +
    "negative result means the subs are already farther from FOH than the mains — delay the mains instead; \"Set " +
    "group delay\" clamps to 0. If Acoustic centre offset is enabled (Sub box dimensions panel), \"Sub dist. to FOH\" " +
    "is corrected by that amount before this calculation — enter the distance to the cabinet as you'd measure it.",

  bounce:
    "The comb filter from a single source's direct sound interfering with its own reflection off a flat floor " +
    "between the source and a listening position (e.g. the FOH mic) -- a different mechanism from this app's own " +
    "array-steering nulls: this is one source against its own floor reflection, using the mirror-image method. Source " +
    "height and FOH mic height are both above the same floor; FOH mic distance is the horizontal distance between " +
    "them. Both heights at 0 means source and mic are both on the floor -- no separate reflection path, so no null. " +
    "\"Null\" is the lowest, deepest notch (path difference = half a wavelength); \"peak\" is where reinforcement " +
    "repeats (path difference = a whole wavelength) -- same comb pattern continues above it. \"bounce\" is the " +
    "reflected path's level relative to direct from distance alone (not floor absorption, which isn't modelled) -- " +
    "how deep the null can actually go. Ported from Merlijn van Veen's floor_bounce_V1.1.xlsx, verified to match its " +
    "own numbers exactly.",

  results:
    "Copy puts the table on the clipboard as tab-separated text (pastes straight into a spreadsheet). Export CSV saves " +
    "it as a file with full precision, delays in both ms and samples, and each sub's effective polarity including " +
    "Group polarity. This is what the desktop app would send over OSC: delay, gain and polarity per sub.",
};
