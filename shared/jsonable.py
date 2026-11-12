"""Convert array_math results into plain JSON-safe values.

Used by the web app's bridge (to hand results to JavaScript) and by the
parity tests (to store and compare results). Standard library only, so it
runs both in desktop Python and in the browser under Pyodide.

Dataclasses become dicts tagged with "_type"; tuples become lists; NaN and
infinities, which JSON can't represent, become {"_float": "nan" | "inf" | "-inf"}.
"""

import dataclasses
import math


def to_jsonable(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        d = {"_type": type(value).__name__}
        d.update({f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)})
        return d
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"_float": "nan"}
        if math.isinf(value):
            return {"_float": "inf" if value > 0 else "-inf"}
        return value
    raise TypeError(f"can't serialise {type(value).__name__}: {value!r}")
