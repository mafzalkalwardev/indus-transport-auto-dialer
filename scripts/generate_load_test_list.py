#!/usr/bin/env python3
"""Create phones_load_1000.xlsx for soak testing (cycles test numbers)."""
from __future__ import annotations

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_NUMBERS = [
    ("7855724805", "Test Line 1"),
    ("5126414655", "Test Line 2"),
]

TARGET_COUNT = 1000
OUT = os.path.join(ROOT, "phones_load_1000.xlsx")


def main() -> None:
    rows = []
    i = 0
    while len(rows) < TARGET_COUNT:
        raw, name = TEST_NUMBERS[i % len(TEST_NUMBERS)]
        rows.append({
            "Phone": raw,
            "Name": f"{name} #{len(rows) + 1}",
        })
        i += 1
    df = pd.DataFrame(rows)
    df.to_excel(OUT, index=False)
    print(f"Wrote {len(df)} rows to:\n  {OUT}")
    print("\nUse only numbers you are allowed to dial.")
    print("See docs/LOAD_TEST.md for the full procedure.")


if __name__ == "__main__":
    main()
