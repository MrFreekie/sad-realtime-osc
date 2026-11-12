"""Python side of the browser bridge (runs under Pyodide).

JavaScript calls these functions with JSON strings and gets JSON strings
back, so no Python objects leak into JS and every result goes through the
same to_jsonable() the parity tests use. Errors come back as
{"error": ..., "type": ...} instead of raising, so the JS side gets a
clean message rather than a PythonError with a traceback.

Only public array_math functions can be called -- nothing else in the
Python environment is reachable by name from JS.
"""

import json

import array_math
import prealign_profiles
import sub_profiles
from jsonable import to_jsonable
from version import __version__

_CALLABLE = {
    name for name in dir(array_math)
    if not name.startswith("_") and callable(getattr(array_math, name))
    and getattr(getattr(array_math, name), "__module__", None) == "array_math"
}


def _ok(value):
    return json.dumps({"ok": to_jsonable(value)}, allow_nan=False)


def _err(e):
    return json.dumps({"error": str(e), "type": type(e).__name__})


def call(fn_name, args_json="[]", kwargs_json="{}"):
    if fn_name not in _CALLABLE:
        return _err(NameError(f"array_math has no public function {fn_name!r}"))
    try:
        args = json.loads(args_json)
        kwargs = json.loads(kwargs_json)
        return _ok(getattr(array_math, fn_name)(*args, **kwargs))
    except Exception as e:  # surfaced to JS as a structured error
        return _err(e)


def info():
    import sys
    return _ok({
        "version": __version__,
        "python": sys.version.split()[0],
        "functions": sorted(_CALLABLE),
        "level_taper_windows": list(array_math.LEVEL_TAPER_WINDOWS),
        "parametric_taper_windows": list(array_math.PARAMETRIC_TAPER_WINDOWS),
        "gain_osc_floor_db": array_math.GAIN_OSC_FLOOR_DB,
        "max_arc_angle_deg": array_math.MAX_ARC_ANGLE_DEG,
    })


def sub_profile_list():
    return _ok([{"name": n, "width_m": w, "depth_m": d} for n, w, d in sub_profiles.load_profiles()])


def prealign_data():
    try:
        entries = prealign_profiles.load_entries()
    except prealign_profiles.PrealignDataError as e:
        return _err(e)
    fields = ("main_system", "sub_system", "main_delay_ms", "sub_delay_ms", "main_polarity",
              "sub_polarity", "main_config", "sub_config", "notes")
    return _ok({
        "entries": [dict(zip(fields, row)) for row in entries],
        "config_labels": prealign_profiles.CONFIG_LABELS,
        "polarity_labels": prealign_profiles.POLARITY_LABELS,
    })
