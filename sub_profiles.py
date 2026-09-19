"""Loads named sub box dimension profiles (width/depth in meters) from
sub_profiles.csv, alongside this file. Falls back to a small built-in
default list if the CSV is missing, empty, or unreadable, so the app
still works standalone.
"""
import csv
import os

DEFAULT_PROFILES = [
    ("L-Acoustics KS28 (Horizontal)", 1.340, 0.702),
    ("L-Acoustics KS28 (Vertical)", 0.565, 0.702),
]

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sub_profiles.csv")


def load_profiles(csv_path=CSV_PATH):
    """Returns a list of (name, width_m, depth_m) tuples, read from
    csv_path (columns: name, width_m, depth_m). Rows that fail to parse
    are skipped; if nothing usable is found, returns DEFAULT_PROFILES."""
    if not os.path.exists(csv_path):
        return list(DEFAULT_PROFILES)
    profiles = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    name = (row.get("name") or "").strip()
                    width = float(row["width_m"])
                    depth = float(row["depth_m"])
                except (KeyError, ValueError, TypeError):
                    continue
                if name:
                    profiles.append((name, width, depth))
    except OSError:
        return list(DEFAULT_PROFILES)
    return profiles or list(DEFAULT_PROFILES)
