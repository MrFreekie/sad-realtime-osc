"""Helpers shared by the parity generator and checker.

Kept free of anything but the standard library so the same file can run
under Pyodide in the browser.
"""

import dataclasses
import math

REL_TOL = 1e-9
ABS_TOL = 1e-9


def to_jsonable(value):
    """Convert array_math results to plain JSON (no NaN/inf, which JSON lacks)."""
    if dataclasses.is_dataclass(value):
        d = {"_type": type(value).__name__}
        d.update({f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)})
        return d
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"_float": "nan"}
        if math.isinf(value):
            return {"_float": "inf" if value > 0 else "-inf"}
        return value
    raise TypeError(f"can't serialise {type(value).__name__}: {value!r}")


def compare(expected, actual, path="result"):
    """Return a list of mismatch strings (empty if equal within tolerance)."""
    if isinstance(expected, dict) and "_float" in expected:
        ok = isinstance(actual, dict) and actual.get("_float") == expected["_float"]
        return [] if ok else [f"{path}: expected {expected['_float']}, got {actual!r}"]
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            return [f"{path}: expected keys {sorted(expected)}, got {actual!r}"]
        out = []
        for k in expected:
            out += compare(expected[k], actual[k], f"{path}.{k}")
        return out
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return [f"{path}: expected list of {len(expected)}, got {actual!r}"]
        out = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            out += compare(e, a, f"{path}[{i}]")
        return out
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]
    if isinstance(expected, (int, float)):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return [f"{path}: expected {expected!r}, got {actual!r}"]
        if math.isclose(expected, actual, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            return []
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return [f"{path}: unexpected expected-value type {type(expected).__name__}"]
