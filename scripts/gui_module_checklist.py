"""Headless GUI/module checklist for E2E verification."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CHECKS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}" + (f" — {detail}" if detail else ""), flush=True)


def main() -> int:
    from src.paths import CONFIG_FILE, CRM_DB, DATA_DIR, LOGS_DIR

    record("config_file", os.path.isfile(CONFIG_FILE), CONFIG_FILE)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    record("deployment_mode_admin", cfg.get("deployment_mode") == "admin", str(cfg.get("deployment_mode")))
    record("dry_run_mode_off_for_prod", not bool(cfg.get("dry_run_mode")), str(cfg.get("dry_run_mode")))

    record("crm_database", os.path.isfile(CRM_DB), CRM_DB)
    record("gv_accounts_file", os.path.isfile(os.path.join(DATA_DIR, "gv_accounts.json")))
    record("logs_dir", os.path.isdir(LOGS_DIR))

    from src.crm_db import CRMDatabase

    db = CRMDatabase()
    users = db.get_all_users()
    record("crm_users_exist", len(users) > 0, f"count={len(users)}")
    contacts = db.get_contacts(status_filter="all")[:1]
    record("crm_contacts_accessible", True, f"sample={len(contacts)}")

    from autodialer_gui import ui_display_state, UI_STATE_DISPLAY
    from src.ui_theme import status_label

    for state in ("DIALING", "RINGING", "ANSWERED_PENDING", "HUMAN", "VOICEMAIL", "CLASSIFYING_AUDIO"):
        record(f"ui_label_{state}", bool(status_label(state)), status_label(state))
    record("ui_display_classifying", ui_display_state("CLASSIFYING_AUDIO") == "ANSWERED_PENDING")

    from src.client_deploy import is_client_deployment

    record("admin_deployment", not is_client_deployment(cfg))

    from src.gv_accounts import load_accounts, profile_dir, has_session_marker

    accounts = load_accounts()
    record("gv_accounts_loaded", len(accounts) > 0, f"lines={len(accounts)}")
    signed = sum(1 for a in accounts if has_session_marker(profile_dir(str(a.get("profile") or ""))))
    record("gv_sessions_signed_in", signed > 0, f"signed={signed}/{len(accounts)}")

    from src.pacing.engine import PredictivePacingEngine
    from src.retry_queue import DialRetryQueue
    from src.slot_watchdog import SlotWatchdog

    record("pacing_engine", PredictivePacingEngine() is not None)
    record("retry_queue", DialRetryQueue() is not None)

    import autodialer_gui  # noqa: F401

    record("autodialer_gui_import", True)

    failed = [c for c in CHECKS if not c[1]]
    print(f"\nSummary: {len(CHECKS) - len(failed)}/{len(CHECKS)} passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
