#!/usr/bin/env python3
"""Prepare dialer_config + CRM for a live owner-consent test campaign."""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.crm_db import CRMDatabase
from src.gv_accounts import load_accounts
from src.paths import CONFIG_FILE
from src.phone_utils import clean_phone, fmt_display, fmt_e164
from src.system_profile import effective_requested_slots, system_ram_gb

DEFAULT_XLSX = os.path.join(ROOT, "phones_test.xlsx")


def _load_config() -> dict:
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    example = os.path.join(ROOT, "dialer_config.example.json")
    with open(example, encoding="utf-8") as f:
        return json.load(f)


def _excel_rows(path: str) -> list[dict]:
    df = pd.read_excel(path)
    df.columns = df.columns.astype(str).str.strip()
    phone_col = next(
        (
            c for c in df.columns
            if c.lower() in {"phone", "mobile", "number", "tel", "telephone", "cell", "phone number"}
        ),
        df.columns[0],
    )
    name_col = next((c for c in df.columns if c.lower() in {"name", "contact", "contact name"}), None)
    rows: list[dict] = []
    for _, row in df.iterrows():
        d10 = clean_phone(str(row.get(phone_col, "")))
        if not d10:
            continue
        name = str(row.get(name_col, "")).strip() if name_col else ""
        rows.append({"phone": d10, "name": name or fmt_display(d10)})
    return rows


def main() -> int:
    xlsx = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    if not os.path.isfile(xlsx):
        print(f"Missing Excel list: {xlsx}")
        print("Run: python scripts/prepare_test_dial.py")
        return 1

    accounts = load_accounts()
    if not accounts:
        print("No Google Voice accounts in data/gv_accounts.json")
        return 1

    requested = min(5, len(accounts))
    cfg = _load_config()
    cfg["force_requested_slots"] = True
    cfg["allow_duplicate_gv_accounts"] = True
    cfg["max_concurrent_dials"] = 5
    effective = effective_requested_slots(requested, cfg)
    cfg["dry_run_mode"] = False
    cfg["n_slots"] = effective
    cfg["excel_path"] = xlsx.replace("\\", "/")
    cfg["campaign_excel_path"] = cfg["excel_path"]
    cfg["campaign_contact_idx"] = 0
    cfg["deployment_mode"] = "admin"
    cfg.setdefault("call_timeout", 60)
    cfg.setdefault("cooldown", 6.0)
    cfg.setdefault("dial_stagger_sec", 1.2)
    cfg.setdefault("voicemail_hangup_sec", 4)
    cfg.setdefault("enable_ai_audio", True)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    rows = _excel_rows(xlsx)
    db = CRMDatabase()
    added, skipped = db.import_contacts_from_list(rows)

    print("Live campaign ready")
    print(f"  RAM ~{system_ram_gb():.0f} GB -> {effective} line(s) (requested {requested})")
    print(f"  GV accounts: {len(accounts)}")
    print(f"  Excel: {xlsx}")
    print(f"  CRM import: added {added}, skipped {skipped}")
    print(f"  dry_run_mode: {cfg['dry_run_mode']}")
    print("\nDialable numbers:")
    for row in rows[:20]:
        d10 = clean_phone(row["phone"])
        print(f"  {row.get('name', '')}: {fmt_e164(d10)}")
    if len(rows) > 20:
        print(f"  ... and {len(rows) - 20} more")
    print("\nNext: python autodialer_gui.py")
    print("  Settings -> verify all 4 lines show Ready (Connect account if Google asks for 2FA)")
    print("  Dialer -> Load contacts -> Start dialing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
