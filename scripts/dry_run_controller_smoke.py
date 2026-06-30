"""Automated dry-run smoke: GVController without placing real calls."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.webengine_env import configure_webengine_environment

configure_webengine_environment()

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from src.gv_accounts import load_accounts, profile_dir
from src.gv_controller import GVController
from src.paths import LOGS_DIR


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    accounts = load_accounts()
    if not accounts:
        print("No GV accounts; using synthetic profile for dry-run", flush=True)
        prof = os.path.join(ROOT, "chrome_profiles", "_dry_run_smoke")
        os.makedirs(prof, exist_ok=True)
        account = {"email": "dry-run@test", "profile": "_dry_run_smoke"}
    else:
        account = accounts[0]
        prof = profile_dir(str(account.get("profile") or "slot_0"))

    states: list[dict] = []
    done = {"ok": False}

    runtime_cfg = {"dry_run_mode": True, "enable_ai_audio": False, "call_timeout": 8}

    ctrl = GVController(
        slot_id=0,
        profile_dir=prof,
        profile_key=str(account.get("profile") or "dry_run"),
        login_email=str(account.get("email") or ""),
        login_password=str(account.get("password") or ""),
        runtime_cfg=runtime_cfg,
    )

    def on_state(slot: int, state: str) -> None:
        states.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "state": state,
        })
        print(f"[Slot {slot}] -> {state}", flush=True)
        if state in {"NO_ANSWER", "FAILED", "ENDED", "HUMAN", "VOICEMAIL", "BUSY"}:
            done["ok"] = True
            QTimer.singleShot(200, app.quit)

    ctrl.state_changed.connect(on_state)
    ctrl.dial("+15551234567")

    QTimer.singleShot(15000, app.quit)
    app.exec()

    report = {
        "started_at": states[0]["time"] if states else datetime.now().isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "dry_run_controller",
        "states": states,
        "pass": done["ok"] and any(s["state"] == "RINGING" for s in states),
    }
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, f"dry_run_smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Report: {path}", flush=True)
    print(f"PASS={report['pass']}", flush=True)
    try:
        ctrl.shutdown()
    except Exception:
        pass
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
