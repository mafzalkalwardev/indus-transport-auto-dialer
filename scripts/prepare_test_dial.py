#!/usr/bin/env python3
"""Prepare the owner test numbers for a power-dial run."""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.paths import CONFIG_FILE, ROOT as PROJECT_ROOT
from src.phone_utils import clean_phone, fmt_e164, fmt_display

TEST_NUMBERS = [
    ("15127616455", "Live test 1"),
    ("17085681794", "Live test 2"),
    ("14044651478", "Live test 3"),
]


def main() -> None:
    xlsx = os.path.join(PROJECT_ROOT, "phones_test.xlsx")
    df = pd.DataFrame({"Phone": [n for n, _ in TEST_NUMBERS],
                       "Name": [name for _, name in TEST_NUMBERS]})
    df.to_excel(xlsx, index=False)

    cfg: dict = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    cfg["excel_path"] = xlsx.replace("\\", "/")
    cfg["n_slots"] = len(TEST_NUMBERS)
    cfg.setdefault("call_timeout", 45)
    cfg.setdefault("dial_stagger_sec", 0.8)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    print("Test list written:", xlsx)
    print("dialer_config.json test list and slot count updated.\n")
    for raw, name in TEST_NUMBERS:
        d10 = clean_phone(raw)
        if not d10:
            print(f"  INVALID  {raw}")
            continue
        print(f"  OK  {name}: {fmt_display(d10)}  ({fmt_e164(d10)})")
    print("\nIn the app: Dialer -> Load Test List -> Start Power Dial (3 slots).")
    print("Use only if you own these lines or consent to test calls.")


if __name__ == "__main__":
    main()
