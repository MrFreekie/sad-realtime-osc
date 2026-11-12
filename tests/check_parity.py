"""Re-run every case in tests/parity_cases.json against shared/array_math.py.

Exits non-zero if any result differs from the stored value. Run from the
repo root:
    python tests/check_parity.py

If you changed the math on purpose, regenerate with
tests/generate_parity_cases.py and review the JSON diff before committing.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))

import array_math  # noqa: E402
from parity_common import run_cases  # noqa: E402


def main():
    with open(os.path.join(HERE, "parity_cases.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    failures = run_cases(array_math, cases)
    for case_id, diffs in failures:
        print(f"FAIL {case_id}")
        for d in diffs[:5]:
            print(f"    {d}")
        if len(diffs) > 5:
            print(f"    ... {len(diffs) - 5} more")
    print(f"{len(cases) - len(failures)}/{len(cases)} parity cases passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
