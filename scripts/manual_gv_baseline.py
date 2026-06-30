"""Open one Google Voice line for a manual baseline call.

This script intentionally does not dial. It opens the same embedded
QWebEngine Google Voice profile used by the app, shows it on screen, and
records DOM/audio detector evidence while a human manually places one approved
test call in that window.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
from src.phone_utils import clean_phone, fmt_e164


TERMINAL_STATES = {"CONNECTED", "VOICEMAIL", "BUSY", "ENDED", "ENDED_MANUALLY"}


class ManualGVBaseline:
    def __init__(self, phone: str, timeout: int, report_path: str | None = None) -> None:
        accounts = load_accounts()
        if not accounts:
            raise SystemExit("No Google Voice accounts configured.")
        acct = accounts[0]
        self.phone = phone
        self.timeout = max(20, int(timeout))
        self.report_path = report_path or os.path.join(
            LOGS_DIR,
            "manual_gv_baseline_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json",
        )
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.events: list[dict] = []
        self.detection: list[dict] = []
        self.states: list[dict] = []
        self.final = "PENDING"
        self.ctrl = GVController(
            0,
            profile_dir(str(acct.get("profile", ""))),
            profile_key=str(acct.get("profile", "slot_0")),
            login_email=str(acct.get("email", "")),
            login_password=str(acct.get("password", "")),
            runtime_cfg={
                "allow_os_input": True,
                "call_timeout": self.timeout,
            },
        )
        self.ctrl.log_message.connect(self.on_log)
        self.ctrl.state_changed.connect(self.on_state)
        self.ctrl.detection_update.connect(self.on_detection)

    def log(self, message: str) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        print(f"{stamp} {message}", flush=True)
        self.events.append({"time": stamp, "message": message})

    def start(self) -> None:
        self.ctrl.load()
        self.ctrl.prepare_for_visible_display()
        self.log("Opening visible Google Voice baseline window.")
        self.log(f"Approved test number: {self.phone}")
        self.log("When Google Voice is ready, manually type the number and click Call in the GV window.")
        QTimer.singleShot(3000, lambda: self.wait_for_ready(0))
        QTimer.singleShot((self.timeout + 90) * 1000, self.finish_timeout)

    def wait_for_ready(self, waited: int) -> None:
        if self.ctrl.is_logged_in:
            self.log("Google Voice ready. Manual baseline monitoring started.")
            self.ctrl._active_call = True
            self.ctrl._current_call_phone = self.phone
            self.ctrl._pending_dial_phone = self.phone
            self.ctrl._dial_started_at = time.monotonic()
            self.ctrl._call_clicked_at = 0.0
            self.ctrl._decision_engine.start_call()
            self.ctrl.start_polling()
            return
        if waited >= 60:
            self.final = "LOGIN_REQUIRED"
            self.log("Google Voice did not become ready.")
            self.finish()
            return
        self.log("Waiting for Google Voice readiness...")
        QTimer.singleShot(3000, lambda: self.wait_for_ready(waited + 3))

    def on_log(self, _slot: int, message: str) -> None:
        self.log(f"[GV] {message}")

    def on_state(self, _slot: int, state: str) -> None:
        self.states.append({"time": datetime.now().isoformat(timespec="seconds"), "state": state})
        self.log(f"STATE {state}")
        if state in {"FAILED", "NO_ANSWER"}:
            self.log("Ignoring pre-click terminal state during manual baseline; keep using the GV window.")
            self.ctrl._active_call = True
            self.ctrl._pending_dial_phone = self.phone
            self.ctrl._call_clicked_at = 0.0
            self.ctrl.start_polling()
            return
        if state in TERMINAL_STATES:
            self.final = state
            QTimer.singleShot(1000, self.finish)

    def on_detection(self, _slot: int, debug: dict) -> None:
        self.detection.append(debug)
        fused = str(debug.get("fused_state") or "")
        dom = str(debug.get("dom_state") or "")
        audio = str(debug.get("audio_state") or "")
        reason = str(debug.get("reason") or "")
        print(
            f"[BASELINE] elapsed={debug.get('elapsed')} dom={dom} audio={audio} "
            f"fused={fused} reason={reason}",
            flush=True,
        )

    def finish_timeout(self) -> None:
        if self.final == "PENDING":
            self.final = "TIMEOUT"
            self.log("Manual baseline timed out.")
            self.finish()

    def finish(self) -> None:
        report = {
            "started_at": self.started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "phone": self.phone,
            "final": self.final,
            "states": self.states,
            "detection": self.detection,
            "events": self.events,
        }
        os.makedirs(os.path.dirname(self.report_path), exist_ok=True)
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nReport written: {self.report_path}", flush=True)
        try:
            self.ctrl.hangup()
        except Exception:
            pass
        self.ctrl.shutdown()
        QApplication.instance().quit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual Google Voice baseline test")
    parser.add_argument("number", help="Approved personal/consented test number")
    parser.add_argument("--timeout", type=int, default=75)
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()
    d10 = clean_phone(args.number)
    if not d10:
        raise SystemExit(f"Invalid phone number: {args.number}")
    app = QApplication(sys.argv)
    runner = ManualGVBaseline(
        fmt_e164(d10),
        timeout=args.timeout,
        report_path=args.report_path or None,
    )
    runner.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
