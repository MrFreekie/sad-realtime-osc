"""Geometry for the layout plot under the per-sub table (both apps).

Pure drawing data, no math the array depends on: each sub's cabinet
footprint, its aim arrow and a label, in the same X/Y the table shows
(metres). The desktop draws it on a Tk Canvas and the web app as SVG; both
get these numbers from here so the two plots match. Standard library only
(runs under Pyodide).

Frame: positions come in as (depth, lateral, rotation) like the table
builds them, then go to plot X/Y by the X/Y convention -- d&b: X = depth,
Y = lateral; L-Acoustics: X = lateral, Y = depth. X runs left to right and
Y bottom to top.

Aim: rotation 0 faces the audience, which is toward +depth for every
topology (array_math's set-back convention: depth <= 0 behind the front).

Each footprint is the Setup tab's sub box (width across, depth front to
back), centred on the sub's position and turned by its rotation. Subs that
share a position (Gradient pairs are side by side in reality but the table
has no lateral for them) share one label, e.g. "1, 3, 5".
"""

import math

_MIN_SPAN_M = 1.0
_PAD_FRACTION = 0.08


def _r(v):
    return round(v, 4) + 0.0


def _label_text(indices):
    if len(indices) <= 4:
        return ", ".join(str(i) for i in indices)
    return f"{indices[0]}, {indices[1]} … {indices[-1]} ({len(indices)})"


def layout_plot(indices, depth_m, lateral_m, rotation_deg, reversed_flags,
                box_width_m, box_depth_m, dnb):
    """Returns {"subs": [...], "labels": [...], "bounds": {...},
    "forward": [fx, fy]} with every coordinate in plot X/Y metres.

    subs[i]: index, centre [x, y], outline (4 corners, closed by the
    drawer; empty when the box size is 0), aim [[x0, y0], [x1, y1]] from
    the front face outward, reversed (effective polarity).
    bounds: xmin/xmax/ymin/ymax around everything drawn, padded, at least
    1 m each way. forward: unit vector toward the audience at rotation 0.
    """
    w = max(float(box_width_m), 0.0)
    d = max(float(box_depth_m), 0.0)

    def to_plot(dep, lat):
        return (dep, lat) if dnb else (lat, dep)

    subs = []
    xs, ys = [], []
    for k, idx in enumerate(indices):
        dep, lat = float(depth_m[k]), float(lateral_m[k])
        rot = math.radians(float(rotation_deg[k]))
        # forward and sideways unit vectors in (depth, lateral)
        f = (math.cos(rot), math.sin(rot))
        s = (-f[1], f[0])
        corners = []
        if w > 0 and d > 0:
            for a, b in ((0.5, 0.5), (0.5, -0.5), (-0.5, -0.5), (-0.5, 0.5)):
                corners.append(to_plot(dep + f[0] * a * d + s[0] * b * w, lat + f[1] * a * d + s[1] * b * w))
        size = max(w, d) if (w > 0 and d > 0) else 0.5
        front = (dep + f[0] * d / 2, lat + f[1] * d / 2)
        tip = (front[0] + f[0] * size * 0.6, front[1] + f[1] * size * 0.6)
        centre = to_plot(dep, lat)
        aim = [to_plot(*front), to_plot(*tip)]
        for x, y in [centre, *corners, *aim]:
            xs.append(x)
            ys.append(y)
        subs.append({
            "index": int(idx),
            "centre": [_r(centre[0]), _r(centre[1])],
            "outline": [[_r(x), _r(y)] for x, y in corners],
            "aim": [[_r(x), _r(y)] for x, y in aim],
            "reversed": bool(reversed_flags[k]),
        })

    groups = {}
    for sub in subs:
        key = (round(sub["centre"][0], 3), round(sub["centre"][1], 3))
        groups.setdefault(key, []).append(sub["index"])
    labels = [{"x": _r(x), "y": _r(y), "text": _label_text(idx)} for (x, y), idx in groups.items()]

    if not xs:
        xs, ys = [0.0], [0.0]
    bounds = {}
    for axis, vals in (("x", xs), ("y", ys)):
        lo, hi = min(vals), max(vals)
        span = hi - lo
        pad = max(span * _PAD_FRACTION, (_MIN_SPAN_M - span) / 2 if span < _MIN_SPAN_M else 0.0, 0.25)
        bounds[axis + "min"] = _r(lo - pad)
        bounds[axis + "max"] = _r(hi + pad)

    fwd = to_plot(1.0, 0.0)
    return {"subs": subs, "labels": labels, "bounds": bounds, "forward": [fwd[0], fwd[1]]}


def nice_step(span, target_ticks=6):
    """Grid step (1, 2 or 5 x 10^k metres) giving about target_ticks lines
    across span. Both drawers use it so the grids match."""
    if span <= 0:
        return 1.0
    raw = span / max(target_ticks, 1)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag
