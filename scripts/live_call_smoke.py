"""Run a real Google Voice smoke test through the app's GVController.

This script dials a short owner-approved list, watches the same state detector
used by the GUI, and writes a JSON report under logs/.
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

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from src.gv_accounts import load_accounts, profile_dir, has_session_marker
from src.gv_controller import GVController
from src.paths import LOGS_DIR
from src.phone_utils import clean_phone, fmt_e164


DEFAULT_NUMBERS = [
    "+15127616455",
    "+17085681794",
    "+14044651478",
]

TERMINAL_STATES = {"CONNECTED", "VOICEMAIL", "ENDED", "ENDED_MANUALLY", "FAILED", "NO_ANSWER", "BUSY"}


def _parse_numbers(values: list[str]) -> list[str]:
    numbers: list[str] = []
    for raw in values:
        d10 = clean_phone(raw)
        if not d10:
            raise SystemExit(f"Invalid phone number: {raw}")
        numbers.append(fmt_e164(d10))
    return numbers


class LiveCallSmoke:
    def __init__(
        self,
        numbers: list[str],
        call_timeout: int,
        connected_hold: int,
        voicemail_hold: int,
        stagger_ms: int,
    ) -> None:
        self.numbers = numbers
        self.call_timeout = call_timeout
        self.connected_hold = connected_hold
        self.voicemail_hold = voicemail_hold
        self.stagger_ms = stagger_ms
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.accounts = load_accounts()
        self.controllers: list[GVController] = []
        self.results: dict[int, dict] = {}
        self.events: list[dict] = []
        self.pending_hangups: set[int] = set()
        self.finished = False

    def log(self, slot: int | None, message: str) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        prefix = f"[Slot {slot}] " if slot is not None else ""
        print(f"{stamp} {prefix}{message}", flush=True)
        self.events.append({"time": stamp, "slot": slot, "message": message})

    def start(self) -> None:
        if len(self.accounts) < len(self.numbers):
            self.log(
                None,
                f"BLOCKED: {len(self.accounts)} Google Voice account(s) for "
                f"{len(self.numbers)} requested live calls.",
            )
            self.finish()
            return

        for idx, phone in enumerate(self.numbers):
            acct = self.accounts[idx]
            ctrl = GVController(
                idx,
                profile_dir(str(acct.get("profile", ""))),
                profile_key=str(acct.get("profile", f"slot_{idx}")),
                login_email=str(acct.get("email", "")),
                login_password=str(acct.get("password", "")),
            )
            ctrl.state_changed.connect(self.on_state)
            ctrl.login_detected.connect(lambda sid, i=idx: self.log(i, "Google Voice ready"))
            ctrl.log_message.connect(self.on_controller_log)
            ctrl.detection_update.connect(self.on_detection)
            ctrl.load()
            self.controllers.append(ctrl)
            self.results[idx] = {
                "slot": idx,
                "account": acct.get("name") or acct.get("email"),
                "profile": acct.get("profile"),
                "phone": phone,
                "states": [],
                "final": "PENDING",
            }

        QTimer.singleShot(3000, lambda: self.wait_for_ready(0))
        total_ms = (self.call_timeout + self.connected_hold + self.voicemail_hold + 70) * 1000
        QTimer.singleShot(total_ms, self.timeout_remaining)

    def wait_for_ready(self, waited: int) -> None:
        missing = [
            self.results[idx]["account"]
            for idx, ctrl in enumerate(self.controllers)
            if not ctrl.is_logged_in
        ]
        if not missing:
            self.log(None, "Google Voice ready; waiting for call UI to settle")
            QTimer.singleShot(8000, self.begin_dialing)
            return
        if waited >= 60:
            self.log(None, "BLOCKED: Google Voice did not become ready for: " + ", ".join(missing))
            for idx, ctrl in enumerate(self.controllers):
                if not ctrl.is_logged_in:
                    self.results[idx]["final"] = "LOGIN_REQUIRED"
            self.finish()
            return
        self.log(None, "Waiting for Google Voice readiness: " + ", ".join(missing))
        QTimer.singleShot(3000, lambda: self.wait_for_ready(waited + 3))

    def begin_dialing(self) -> None:
        self.log(None, f"Starting live smoke test for {len(self.numbers)} number(s)")
        for idx, phone in enumerate(self.numbers):
            QTimer.singleShot(idx * self.stagger_ms, lambda i=idx, p=phone: self.dial(i, p))

    def dial(self, slot: int, phone: str) -> None:
        self.log(slot, f"Dialing {phone}")
        self.results[slot]["dial_started_at"] = datetime.now().isoformat(timespec="seconds")
        self.controllers[slot].dial(phone)
        QTimer.singleShot(self.call_timeout * 1000, lambda s=slot: self.mark_no_answer(s))

    def on_controller_log(self, slot: int, message: str) -> None:
        self.log(slot, message)

    def on_state(self, slot: int, state: str) -> None:
        rec = self.results.get(slot)
        if rec is None:
            return
        rec["states"].append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "state": state,
        })
        self.log(slot, f"STATE {state}")
        if state == "CONNECTED":
            rec["final"] = "CONNECTED"
            self.schedule_hangup(slot, self.connected_hold, "connected hold complete")
        elif state == "VOICEMAIL":
            rec["final"] = "VOICEMAIL"
            self.schedule_hangup(slot, self.voicemail_hold, "voicemail detected")
        elif state in ("NO_ANSWER", "ENDED", "ENDED_MANUALLY", "FAILED", "BUSY"):
            if rec.get("final") == "PENDING":
                rec["final"] = state
            self.check_done()

    def on_detection(self, slot: int, debug: dict) -> None:
        rec = self.results.get(slot)
        if rec is not None:
            rec.setdefault("detection", []).append(debug)
        print("[CALL DEBUG]", flush=True)
        for key in (
            "phone", "slot", "elapsed", "dom_state", "audio_state",
            "fused_state", "confidence", "reason", "ringback",
            "speech_duration", "silence_duration", "beep_detected",
            "human_greeting_detected", "voicemail_confirmations",
            "should_hangup", "vad_backend", "vad_confidence",
        ):
            print(f"{key}={debug.get(key)}", flush=True)

    def schedule_hangup(self, slot: int, delay_sec: int, reason: str) -> None:
        if slot in self.pending_hangups:
            return
        self.pending_hangups.add(slot)
        QTimer.singleShot(delay_sec * 1000, lambda s=slot, r=reason: self.hangup(s, r))

    def hangup(self, slot: int, reason: str) -> None:
        if self.finished:
            return
        self.log(slot, f"Hangup after {reason}")
        self.controllers[slot].hangup()
        self.check_done()

    def mark_no_answer(self, slot: int) -> None:
        rec = self.results.get(slot)
        if not rec or rec.get("final") != "PENDING":
            return
        state = self.controllers[slot].current_state
        if state in ("DIALING", "RINGING", "IDLE"):
            rec["final"] = "NO_ANSWER"
            self.log(slot, f"NO_ANSWER after {self.call_timeout}s timeout")
            self.controllers[slot].hangup()
            self.check_done()

    def timeout_remaining(self) -> None:
        for slot, rec in self.results.items():
            if rec.get("final") == "PENDING":
                rec["final"] = "TIMEOUT"
                self.log(slot, "TIMEOUT waiting for terminal state")
                self.controllers[slot].hangup()
        self.finish()

    def check_done(self) -> None:
        if self.results and all(r.get("final") != "PENDING" for r in self.results.values()):
            QTimer.singleShot(1500, self.finish)

    def finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        for ctrl in self.controllers:
            try:
                ctrl.shutdown()
            except Exception:
                pass
        report = {
            "started_at": self.started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "numbers": self.numbers,
            "results": list(self.results.values()),
            "events": self.events,
        }
        os.makedirs(LOGS_DIR, exist_ok=True)
        path = os.path.join(
            LOGS_DIR,
            "live_call_smoke_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json",
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written: {path}", flush=True)
        for rec in report["results"]:
            print(f"Slot {rec['slot']}: {rec['phone']} -> {rec['final']}", flush=True)
        QApplication.instance().quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dial approved live test numbers.")
    parser.add_argument("numbers", nargs="*", help="Phone numbers to dial")
    parser.add_argument("--call-timeout", type=int, default=45)
    parser.add_argument("--connected-hold", type=int, default=8)
    parser.add_argument("--voicemail-hold", type=int, default=4)
    parser.add_argument("--stagger-ms", type=int, default=1200)
    args = parser.parse_args()

    numbers = _parse_numbers(args.numbers or DEFAULT_NUMBERS)
    app = QApplication(sys.argv)
    smoke = LiveCallSmoke(
        numbers,
        call_timeout=args.call_timeout,
        connected_hold=args.connected_hold,
        voicemail_hold=args.voicemail_hold,
        stagger_ms=args.stagger_ms,
    )
    QTimer.singleShot(0, smoke.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
