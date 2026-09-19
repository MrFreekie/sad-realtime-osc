"""Loads L-Acoustics factory pre-alignment delay values (main system +
subwoofer preset combinations) from prealign_delays.csv, alongside this
file. Falls back to a small built-in default list if the CSV is missing,
empty, or unreadable, so the app still works standalone.

Source: L-Acoustics Drive System Preset Guide owner's manual (EN),
version 29.0 (May 2026), "Pre-alignment delay values" section (p.93),
K1 + K1-SB / SB28 / KS28 tables. These are the offsets L-Acoustics
publishes to add to the factory presets *before* your own geometric
alignment, for enclosures placed at the same physical location -- see
the "Pre-alignment delay lookup" panel's tooltip in the app for how
"Use" applies sub_delay_ms.

Only a small, hand-verified seed set is included (the K1 family) --
the rest of that section spans many more system families (K2, K3,
Kudo, Kara, Kara II, Kiva, X series, A15, Syva, Soka...) but its
multi-column layout didn't survive automated PDF text extraction
cleanly enough to trust unverified. Extend prealign_delays.csv with
more rows as you confirm them directly from the guide -- no code
changes needed.

main_polarity / sub_polarity values (audio-standard wording -- write
whichever spelling you like in the CSV, they all normalize the same way):
    positive  (aliases: normal, +)   -- that system's factory preset
                                         outputs, as a whole, at positive
                                         polarity (this is every row in
                                         the guide checked so far --
                                         included as its own column so a
                                         combo that does need a whole-
                                         system flip has somewhere to
                                         say so, without overloading
                                         *_config)
    negative  (aliases: reversed, -) -- that system's factory preset
                                         outputs, as a whole, at negative
                                         (reversed) polarity
An unrecognized value is NOT silently coerced to a default -- it's a
live-audio-relevant field, so load_entries() raises instead, naming the
offending row, rather than quietly showing "Positive" for a typo you'd
never notice until it mattered on a show.

main_config / sub_config values (a separate, finer-grained note about
polarity handling *inside* a single preset/cluster -- independent of
main_polarity/sub_polarity above):
    standard                  -- no internal element reversal
    cardioid                  -- one enclosure per group reversed
                                  internally by the preset (_C)
    extended_cardioid         -- as above, broadband variant (_Cx)
    noise_control_cardioid    -- cardioid via Noise Control preset (_NC)

This app's single Group polarity switch can't represent "reverse just
one element within the sub cluster", so *_config is informational only
-- it never changes what the app sends.
"""
import csv
import os

DEFAULT_ENTRIES = [
    ("K1", "K1SB_X", 0.0, 0.0, "positive", "positive", "standard", "standard", ""),
    ("K1", "K1SB_60", 6.0, 0.0, "positive", "positive", "standard", "standard", ""),
]

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prealign_delays.csv")

POLARITY_ALIASES = {
    "positive": "positive", "normal": "positive", "+": "positive",
    "negative": "negative", "reversed": "negative", "-": "negative",
}

POLARITY_LABELS = {
    "positive": "Positive (+)",
    "negative": "Negative (−)",
}

CONFIG_LABELS = {
    "standard": "Standard",
    "cardioid": "Cardioid (internal reversal)",
    "extended_cardioid": "Extended cardioid (internal reversal)",
    "noise_control_cardioid": "Noise Control cardioid (internal reversal)",
}


class PrealignDataError(ValueError):
    """A row in prealign_delays.csv has an unrecognized polarity value."""


def _normalize_polarity(raw: str, field: str, main_system: str, sub_system: str) -> str:
    key = (raw or "positive").strip().lower()
    if key == "":
        key = "positive"
    if key not in POLARITY_ALIASES:
        raise PrealignDataError(
            f"prealign_delays.csv: unrecognized {field} {raw!r} for {main_system} + {sub_system} "
            f"-- expected one of {sorted(set(POLARITY_ALIASES))}")
    return POLARITY_ALIASES[key]


def load_entries(csv_path=CSV_PATH):
    """Returns a list of (main_system, sub_system, main_delay_ms,
    sub_delay_ms, main_polarity, sub_polarity, main_config, sub_config,
    notes) tuples, read from csv_path. main_polarity/sub_polarity are
    normalized to "positive"/"negative" (accepting normal/reversed/+/-
    as aliases). Rows with an unrecognized polarity raise
    PrealignDataError rather than being silently coerced -- this is a
    live-audio-relevant field, so a typo should be loud, not swallowed.
    Other malformed rows (missing/non-numeric delay, no system names)
    are skipped. If the file is missing, empty, or unreadable, returns
    DEFAULT_ENTRIES."""
    if not os.path.exists(csv_path):
        return list(DEFAULT_ENTRIES)
    entries = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return list(DEFAULT_ENTRIES)
    for row in rows:
        main_system = (row.get("main_system") or "").strip()
        sub_system = (row.get("sub_system") or "").strip()
        if not main_system or not sub_system:
            continue
        try:
            main_delay_ms = float(row["main_delay_ms"])
            sub_delay_ms = float(row["sub_delay_ms"])
        except (KeyError, ValueError, TypeError):
            continue
        # Polarity is left to raise (PrealignDataError) rather than being
        # caught here -- see the docstring on why an unrecognized value
        # must be loud, not skipped or defaulted.
        main_polarity = _normalize_polarity(row.get("main_polarity"), "main_polarity",
                                             main_system, sub_system)
        sub_polarity = _normalize_polarity(row.get("sub_polarity"), "sub_polarity",
                                            main_system, sub_system)
        main_config = (row.get("main_config") or "standard").strip() or "standard"
        sub_config = (row.get("sub_config") or "standard").strip() or "standard"
        notes = (row.get("notes") or "").strip()
        entries.append((main_system, sub_system, main_delay_ms, sub_delay_ms,
                         main_polarity, sub_polarity, main_config, sub_config, notes))
    return entries or list(DEFAULT_ENTRIES)
