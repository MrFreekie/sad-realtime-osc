"""Helpers shared by the parity generator and checker.

Kept free of anything but the standard library so the same file can run
under Pyodide in the browser (web/selftest.html). Expects shared/ on
sys.path, for jsonable.
"""

import math

from jsonable import to_jsonable  # noqa: F401  (re-exported for callers)

REL_TOL = 1e-9
ABS_TOL = 1e-9


def run_cases(array_math, cases):
    """Re-run parity cases; returns a list of (case_id, [mismatch, ...])."""
    failures = []
    for c in cases:
        try:
            fn = getattr(array_math, c["fn"])
            actual = to_jsonable(fn(*c["args"], **c["kwargs"]))
        except Exception as e:  # report and keep going
            failures.append((c["id"], [f"raised {type(e).__name__}: {e}"]))
            continue
        diffs = compare(c["expected"], actual)
        if diffs:
            failures.append((c["id"], diffs))
    return failures


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
