"""Run a real Google Voice smoke test through the app's GVController.

This script dials a short owner-approved list, watches the same state detector
used by the GUI, and writes a JSON report under logs/.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from glob import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.webengine_env import configure_webengine_environment

configure_webengine_environment()

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton, QVBoxLayout, QWidget

from src.gv_accounts import load_accounts, profile_dir, has_session_marker
from src.gv_controller import GVController
from src.paths import CRM_DB, LOGS_DIR
from src.phone_utils import clean_phone, fmt_e164


DEFAULT_NUMBERS = [
    "+15127616455",
    "+17085681794",
    "+14044651478",
]

TERMINAL_STATES = {"CONNECTED", "VOICEMAIL", "ENDED", "ENDED_MANUALLY", "FAILED", "NO_ANSWER", "BUSY"}
ANSWERED_SUCCESS_STATES = {"ANSWERED_PENDING", "CONNECTED_AUDIO_EVIDENCE"}
LIVE_TEST_CONFIRMATION = "I OWN OR HAVE PERMISSION TO CALL THESE NUMBERS"


def _parse_numbers(values: list[str]) -> list[str]:
    numbers: list[str] = []
    for raw in values:
        d10 = clean_phone(raw)
        if not d10:
            raise SystemExit(f"Invalid phone number: {raw}")
        numbers.append(fmt_e164(d10))
    return numbers


def _load_crm_numbers(limit: int, exclude: set[str] | None = None) -> list[str]:
    import sqlite3

    exclude = exclude or set()
    if not os.path.exists(CRM_DB):
        raise SystemExit(f"CRM database not found: {CRM_DB}")
    numbers: list[str] = []
    with sqlite3.connect(CRM_DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT c.phone
            FROM contacts c
            WHERE c.phone IS NOT NULL
              AND TRIM(c.phone) != ''
              AND NOT EXISTS (
                  SELECT 1 FROM call_records r
                  WHERE r.phone = c.phone
                    AND r.status IN ('ENDED', 'ENDED_MANUALLY', 'HUMAN', 'VOICEMAIL', 'BUSY')
              )
            ORDER BY
              CASE WHEN c.status = 'new' THEN 0 ELSE 1 END,
              CASE WHEN c.last_called IS NULL OR c.last_called = '' THEN 0 ELSE 1 END,
              c.id DESC
            LIMIT ?
            """,
            (max(100, max(1, int(limit)) * 10 + len(exclude)),),
        ).fetchall()
    for row in rows:
        cleaned = clean_phone(str(row["phone"]))
        if cleaned:
            phone = fmt_e164(cleaned)
            if phone not in numbers and phone not in exclude:
                numbers.append(phone)
        if len(numbers) >= limit:
            break
    if not numbers:
        raise SystemExit("No dialable CRM contacts found.")
    return numbers


def _load_excel_numbers(path: str, limit: int) -> list[str]:
    import pandas as pd

    if not os.path.exists(path):
        raise SystemExit(f"Live test phone file not found: {path}")
    df = pd.read_excel(path)
    df.columns = df.columns.astype(str).str.strip()
    phone_col = next(
        (
            col for col in df.columns
            if col.strip().lower() in {
                "phone", "mobile", "number", "tel", "telephone", "cell", "phone number"
            }
        ),
        None,
    )
    if not phone_col:
        raise SystemExit(f"No phone column found in {path}. Columns: {list(df.columns)}")
    numbers: list[str] = []
    for raw in df[phone_col]:
        cleaned = clean_phone(raw)
        if not cleaned:
            continue
        phone = fmt_e164(cleaned)
        if phone not in numbers:
            numbers.append(phone)
        if len(numbers) >= max(1, int(limit)):
            break
    if not numbers:
        raise SystemExit(f"No dialable phone numbers found in {path}")
    return numbers


def _load_recent_report_numbers(hours: float) -> set[str]:
    if hours <= 0:
        return set()
    cutoff = time.time() - (float(hours) * 3600.0)
    numbers: set[str] = set()
    patterns = (
        os.path.join(LOGS_DIR, "live_call_smoke_*.json"),
        os.path.join(LOGS_DIR, "live_call_campaign_*_wave*.json"),
    )
    for pattern in patterns:
        for path in glob(pattern):
            try:
                if os.path.getmtime(path) < cutoff:
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    report = json.load(f)
            except Exception:
                continue
            for raw in report.get("numbers", []):
                cleaned = clean_phone(str(raw))
                if cleaned:
                    numbers.add(fmt_e164(cleaned))
            for rec in report.get("results", []):
                cleaned = clean_phone(str(rec.get("phone", "")))
                if cleaned:
                    numbers.add(fmt_e164(cleaned))
    return numbers


def select_smoke_numbers(args: argparse.Namespace, account_count: int) -> list[str]:
    if getattr(args, "live_test_live_test", False):
        path = getattr(args, "live_test_file", "") or os.path.join(ROOT, "phones_test.xlsx")
        return _load_excel_numbers(path, int(getattr(args, "live_test_limit", 45) or 45))
    if args.numbers:
        return _parse_numbers(args.numbers)
    if args.from_crm:
        limit = args.crm_limit or max(1, account_count)
        return _load_crm_numbers(limit)
    return _parse_numbers(DEFAULT_NUMBERS)


def distinct_line_count(accounts: list[dict], requested: int) -> int:
    return len({
        str(acct.get("email") or acct.get("profile") or "").strip().lower()
        for acct in accounts[:requested]
        if str(acct.get("email") or acct.get("profile") or "").strip()
    })


class LiveCallSmoke:
    def __init__(
        self,
        numbers: list[str],
        call_timeout: int,
        connected_hold: int,
        voicemail_hold: int,
        stagger_ms: int,
        report_path: str | None = None,
        print_debug: bool = True,
        visible: bool = False,
        max_parallel: int | None = None,
        rate_limit_sec: float = 1.2,
        stop_on_failure: bool = False,
        manual_connect_confirmation: bool = False,
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
        self.active_by_slot: dict[int, int] = {}
        self.next_number_idx = 0
        self.events: list[dict] = []
        self.pending_hangups: set[int] = set()
        self.finished = False
        self.report_path = report_path
        self.print_debug = print_debug
        self.visible = visible
        self.max_parallel = max(1, int(max_parallel or len(numbers) or 1))
        self.rate_limit_sec = max(1.0, float(rate_limit_sec or 1.2))
        self.stop_requested = False
        self.stop_on_failure = bool(stop_on_failure)
        self.manual_connect_confirmation = bool(manual_connect_confirmation)

    def log(self, slot: int | None, message: str) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        prefix = f"[Slot {slot}] " if slot is not None else ""
        print(f"{stamp} {prefix}{message}", flush=True)
        self.events.append({"time": stamp, "slot": slot, "message": message})

    def start(self) -> None:
        line_count = min(len(self.numbers), len(self.accounts), self.max_parallel)
        if line_count <= 0:
            self.log(
                None,
                "BLOCKED: no Google Voice accounts configured for live testing.",
            )
            self.finish()
            return
        distinct_lines = distinct_line_count(self.accounts, line_count)
        if distinct_lines < line_count:
            self.log(
                None,
                f"BLOCKED: {distinct_lines} distinct Google Voice line(s) for "
                f"{line_count} requested concurrent live calls.",
            )
            self.log(None, "Use one signed-in Google Voice account/email per realtime slot.")
            self.finish()
            return

        for idx in range(line_count):
            acct = self.accounts[idx]
            ctrl = GVController(
                idx,
                profile_dir(str(acct.get("profile", ""))),
                profile_key=str(acct.get("profile", f"slot_{idx}")),
                login_email=str(acct.get("email", "")),
                login_password=str(acct.get("password", "")),
                runtime_cfg={
                    "call_timeout": self.call_timeout,
                    "allow_os_input": bool(self.visible),
                },
            )
            ctrl.state_changed.connect(self.on_state)
            ctrl.login_detected.connect(lambda sid, i=idx: self.log(i, "Google Voice ready"))
            ctrl.log_message.connect(self.on_controller_log)
            ctrl.detection_update.connect(self.on_detection)
            ctrl.load()
            if self.visible:
                ctrl.prepare_for_visible_display()
            else:
                ctrl.prepare_for_background_rendering()
            self.controllers.append(ctrl)

        QTimer.singleShot(3000, lambda: self.wait_for_ready(0))
        waves = max(1, (len(self.numbers) + line_count - 1) // line_count)
        total_ms = int((self.call_timeout + self.connected_hold + self.voicemail_hold + 70) * waves * 1000)
        QTimer.singleShot(total_ms, self.timeout_remaining)

    def wait_for_ready(self, waited: int) -> None:
        missing = [
            self.accounts[idx].get("name") or self.accounts[idx].get("email") or f"Slot {idx}"
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
        for idx, _ctrl in enumerate(self.controllers):
            QTimer.singleShot(idx * self.stagger_ms, lambda i=idx: self.assign_next(i))

    def assign_next(self, slot: int) -> None:
        if self.finished or self.stop_requested or slot in self.active_by_slot:
            return
        if self.next_number_idx >= len(self.numbers):
            self.check_done()
            return
        call_id = self.next_number_idx
        self.next_number_idx += 1
        phone = self.numbers[call_id]
        acct = self.accounts[slot]
        self.results[call_id] = {
            "slot": slot,
            "account": acct.get("name") or acct.get("email"),
            "profile": acct.get("profile"),
            "phone": phone,
            "states": [],
            "final": "PENDING",
        }
        self.active_by_slot[slot] = call_id
        self.dial(slot, call_id, phone)

    def dial(self, slot: int, call_id: int, phone: str) -> None:
        self.log(slot, f"Dial attempt started: {phone}")
        self.results[call_id]["dial_started_at"] = datetime.now().isoformat(timespec="seconds")
        try:
            self.controllers[slot].dial(phone)
        except Exception:
            self.results[call_id]["final"] = "FAILED"
            tb = traceback.format_exc()
            self.results[call_id]["exception_traceback"] = tb
            self.log(slot, "FAILED: exception while starting dial\n" + tb)
            self.active_by_slot.pop(slot, None)
            QTimer.singleShot(int(self.rate_limit_sec * 1000), lambda s=slot: self.assign_next(s))
            return
        QTimer.singleShot(
            (self.call_timeout + 35) * 1000,
            lambda s=slot, c=call_id: self.mark_pre_dial_timeout(s, c),
        )

    def on_controller_log(self, slot: int, message: str) -> None:
        self.log(slot, message)
        call_id = self.active_by_slot.get(slot)
        rec = self.results.get(call_id) if call_id is not None else None
        if rec is None:
            return
        if "Dial UI status: call_button_clicked" in message and not rec.get("call_clicked_at"):
            rec["call_clicked_at"] = datetime.now().isoformat(timespec="seconds")
            QTimer.singleShot(
                self.call_timeout * 1000,
                lambda s=slot, c=call_id: self.mark_no_answer(s, c),
            )

    def on_state(self, slot: int, state: str) -> None:
        call_id = self.active_by_slot.get(slot)
        if call_id is None:
            return
        rec = self.results.get(call_id)
        if rec is None:
            return
        rec["states"].append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "state": state,
        })
        status = {
            "RINGING": "ringing",
            "ANSWERED_PENDING": "on-call",
            "CONNECTED_AUDIO_EVIDENCE": "on-call",
            "CONNECTED": "on-call",
            "VOICEMAIL": "voicemail",
            "FAILED": "failed",
        }.get(state, state.lower())
        self.log(slot, f"STATE {state} ({status})")
        if state == "CONNECTED":
            rec["final"] = "CONNECTED"
            self.schedule_hangup(slot, self.connected_hold, "connected hold complete")
        elif state in ANSWERED_SUCCESS_STATES:
            if rec.get("final") == "PENDING":
                rec["final"] = state
                self.schedule_hangup(slot, self.connected_hold, "answered hold complete")
        elif state == "VOICEMAIL":
            rec["final"] = "VOICEMAIL"
            self.schedule_hangup(slot, self.voicemail_hold, "voicemail detected")
        elif state in ("NO_ANSWER", "ENDED", "ENDED_MANUALLY", "FAILED", "BUSY"):
            if (
                state in {"NO_ANSWER", "FAILED"}
                and rec.get("final") == "PENDING"
                and self._confirm_connected_manually(slot, rec)
            ):
                self.controllers[slot].hangup()
                self.release_slot(slot)
                return
            if rec.get("final") == "PENDING":
                rec["final"] = state
            if self.stop_on_failure and state == "FAILED":
                self.stop_requested = True
                self.log(None, "Stopping guarded live test after first failed dial")
            self.release_slot(slot)

    def on_detection(self, slot: int, debug: dict) -> None:
        call_id = self.active_by_slot.get(slot)
        rec = self.results.get(call_id) if call_id is not None else None
        if rec is not None:
            rec.setdefault("detection", []).append(debug)
        if not self.print_debug:
            return
        print("[CALL DEBUG]", flush=True)
        for key in (
            "phone", "slot", "elapsed", "dom_state", "audio_state",
            "fused_state", "confidence", "reason", "rms", "ringback",
            "detection_time_ms", "ui_state",
            "speech_duration", "silence_duration", "beep_detected",
            "human_greeting_detected", "voicemail_confirmations",
            "should_hangup", "audio_backend_name", "vad_backend", "vad_confidence",
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
        self.release_slot(slot)

    def mark_no_answer(self, slot: int, call_id: int) -> None:
        if self.active_by_slot.get(slot) != call_id:
            return
        rec = self.results.get(call_id)
        if not rec or rec.get("final") != "PENDING":
            return
        if not rec.get("call_clicked_at"):
            return
        state = self.controllers[slot].current_state
        if state in ANSWERED_SUCCESS_STATES:
            rec["final"] = state
            self.log(slot, f"{state} after answer evidence")
            self.controllers[slot].hangup()
            self.release_slot(slot)
            return
        if self._confirm_connected_manually(slot, rec):
            self.controllers[slot].hangup()
            self.release_slot(slot)
            return
        if state in ("DIALING", "RINGING", "IDLE", "UNKNOWN"):
            rec["final"] = "NO_ANSWER"
            self.log(slot, f"NO_ANSWER after {self.call_timeout}s timeout")
            self.controllers[slot].hangup()
            self.release_slot(slot)

    def _confirm_connected_manually(self, slot: int, rec: dict) -> bool:
        if not (self.visible and self.manual_connect_confirmation):
            return False
        if not rec.get("call_clicked_at"):
            return False
        reply = QMessageBox.question(
            None,
            "Live call confirmation",
            "Did the call connect on your phone? yes/no",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            rec["final"] = "CONNECTED_MANUAL_CONFIRMATION"
            rec["manual_confirmation_at"] = datetime.now().isoformat(timespec="seconds")
            self.log(slot, "CONNECTED by manual confirmation")
            return True
        rec["manual_confirmation_at"] = datetime.now().isoformat(timespec="seconds")
        rec["manual_confirmation"] = "no"
        return False

    def mark_pre_dial_timeout(self, slot: int, call_id: int) -> None:
        if self.active_by_slot.get(slot) != call_id:
            return
        rec = self.results.get(call_id)
        if not rec or rec.get("final") != "PENDING" or rec.get("call_clicked_at"):
            return
        rec["final"] = "FAILED"
        rec["failure_reason"] = "pre_dial_timeout_no_call_button_click"
        self.log(slot, "FAILED: Google Voice did not become ready before live dial")
        self.controllers[slot].hangup()
        if self.stop_on_failure:
            self.stop_requested = True
            self.log(None, "Stopping guarded live test after first failed dial")
        self.release_slot(slot)

    def release_slot(self, slot: int) -> None:
        self.active_by_slot.pop(slot, None)
        if self.stop_requested:
            self.check_done()
            return
        QTimer.singleShot(int(self.rate_limit_sec * 1000), lambda s=slot: self.assign_next(s))
        self.check_done()

    def timeout_remaining(self) -> None:
        for slot, call_id in list(self.active_by_slot.items()):
            rec = self.results.get(call_id)
            if not rec:
                continue
            if rec.get("final") == "PENDING":
                rec["final"] = "TIMEOUT"
                self.log(slot, "TIMEOUT waiting for terminal state")
                self.controllers[slot].hangup()
        self.active_by_slot.clear()
        self.finish()

    def check_done(self) -> None:
        if (
            self.results
            and self.next_number_idx >= len(self.numbers)
            and not self.active_by_slot
            and all(r.get("final") != "PENDING" for r in self.results.values())
        ):
            QTimer.singleShot(1500, self.finish)

    def emergency_stop(self) -> None:
        if self.finished:
            return
        self.stop_requested = True
        self.log(None, "EMERGENCY STOP requested")
        for slot, call_id in list(self.active_by_slot.items()):
            rec = self.results.get(call_id)
            if rec and rec.get("final") == "PENDING":
                rec["final"] = "STOPPED"
            try:
                self.controllers[slot].hangup()
            except Exception:
                self.log(slot, "Exception during emergency hangup\n" + traceback.format_exc())
        self.active_by_slot.clear()
        self.finish()

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
        path = self.report_path or os.path.join(
            LOGS_DIR,
            "live_call_smoke_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json",
        )
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written: {path}", flush=True)
        for rec in report["results"]:
            print(f"Slot {rec['slot']}: {rec['phone']} -> {rec['final']}", flush=True)
        QApplication.instance().quit()


class EmergencyStopPanel(QWidget):
    def __init__(self, smoke: LiveCallSmoke) -> None:
        super().__init__()
        self.setWindowTitle("Live Test Emergency Stop")
        layout = QVBoxLayout(self)
        btn = QPushButton("EMERGENCY STOP")
        btn.setMinimumHeight(80)
        btn.clicked.connect(smoke.emergency_stop)
        layout.addWidget(btn)


def _run_crm_campaign(args: argparse.Namespace, accounts: list[dict]) -> int:
    if not accounts:
        print("BLOCKED: no Google Voice accounts configured.", flush=True)
        return 2
    batch_size = max(1, min(len(accounts), int(args.crm_batch_size or len(accounts))))
    max_attempts = int(args.max_attempts or 0)
    target_voicemail = int(args.target_voicemails or 0)
    target_live = int(args.target_live or 0)
    if max_attempts <= 0:
        max_attempts = max(20, (target_voicemail + target_live) * 4)

    skipped_recent = _load_recent_report_numbers(float(args.skip_recent_hours or 0))
    attempted: set[str] = set(skipped_recent)
    campaign_attempts = 0
    voicemail_count = 0
    live_count = 0
    final_counts: dict[str, int] = {}
    reports: list[str] = []
    started = datetime.now().strftime("%Y%m%d_%H%M%S")
    wave = 0

    print(
        "Starting CRM campaign: "
        f"target_voicemails={target_voicemail}, target_live={target_live}, "
        f"max_attempts={max_attempts}, batch_size={batch_size}",
        flush=True,
    )

    while campaign_attempts < max_attempts and (
        voicemail_count < target_voicemail or live_count < target_live
    ):
        remaining = max_attempts - campaign_attempts
        numbers = _load_crm_numbers(min(batch_size, remaining), attempted)
        wave += 1
        attempted.update(numbers)
        campaign_attempts += len(numbers)
        report_path = os.path.join(LOGS_DIR, f"live_call_campaign_{started}_wave{wave:02d}.json")
        cmd = [
            sys.executable,
            os.path.abspath(__file__),
            *numbers,
            "--call-timeout",
            str(args.call_timeout),
            "--connected-hold",
            str(args.connected_hold),
            "--voicemail-hold",
            str(args.voicemail_hold),
            "--stagger-ms",
            str(args.stagger_ms),
            "--report-path",
            report_path,
        ]
        if not args.print_debug:
            cmd.append("--quiet-debug")
        print(f"\nWave {wave}: dialing {', '.join(numbers)}", flush=True)
        proc = subprocess.run(cmd, cwd=ROOT)
        if proc.returncode != 0 and not os.path.exists(report_path):
            print(f"Wave {wave} failed with exit code {proc.returncode}", flush=True)
            return proc.returncode
        if proc.returncode != 0:
            print(
                f"Wave {wave} exited with {proc.returncode} after writing a report; continuing.",
                flush=True,
            )
        reports.append(report_path)
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        for rec in report.get("results", []):
            final = str(rec.get("final") or "UNKNOWN")
            final_counts[final] = final_counts.get(final, 0) + 1
            if final == "VOICEMAIL":
                voicemail_count += 1
            elif final in {"CONNECTED", "HUMAN", "ANSWERED_PENDING", "CONNECTED_AUDIO_EVIDENCE", "CONNECTED_MANUAL_CONFIRMATION"}:
                live_count += 1
        print(
            f"Campaign progress: voicemails={voicemail_count}/{target_voicemail}, "
            f"live={live_count}/{target_live}, attempts={campaign_attempts}/{max_attempts}, "
            f"final_counts={final_counts}",
            flush=True,
        )

    summary = {
        "started_at": started,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "target_voicemails": target_voicemail,
        "target_live": target_live,
        "voicemail_count": voicemail_count,
        "live_count": live_count,
        "attempts": campaign_attempts,
        "max_attempts": max_attempts,
        "skipped_recent": len(skipped_recent),
        "final_counts": final_counts,
        "reports": reports,
    }
    summary_path = os.path.join(LOGS_DIR, f"live_call_campaign_{started}_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nCampaign summary written: {summary_path}", flush=True)
    print(
        f"Final campaign result: voicemails={voicemail_count}/{target_voicemail}, "
        f"live={live_count}/{target_live}, attempts={campaign_attempts}/{max_attempts}",
        flush=True,
    )
    return 0 if voicemail_count >= target_voicemail and live_count >= target_live else 1


def main() -> None:
    def _excepthook(exc_type, exc, tb):
        print("UNHANDLED EXCEPTION", file=sys.stderr, flush=True)
        traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = _excepthook
    parser = argparse.ArgumentParser(description="Dial approved live test numbers.")
    parser.add_argument("numbers", nargs="*", help="Phone numbers to dial")
    parser.add_argument("--from-crm", action="store_true", help="Load test numbers from CRM contacts")
    parser.add_argument("--crm-limit", type=int, default=0, help="CRM numbers to load; default is GV account count")
    parser.add_argument("--crm-batch-size", type=int, default=0, help="CRM campaign wave size; default is GV account count")
    parser.add_argument("--target-voicemails", type=int, default=0, help="Run CRM waves until this many voicemails are confirmed")
    parser.add_argument("--target-live", type=int, default=0, help="Run CRM waves until this many connected live calls are confirmed")
    parser.add_argument("--max-attempts", type=int, default=0, help="Maximum CRM campaign calls before stopping")
    parser.add_argument("--skip-recent-hours", type=float, default=12.0, help="Skip numbers already live-smoked recently")
    parser.add_argument("--report-path", default="", help="Write this wave's report to a fixed path")
    parser.add_argument("--quiet-debug", action="store_true", help="Store detection debug in JSON without printing every poll")
    parser.add_argument("--print-debug", action="store_true", help="Print every child wave detection debug block during CRM campaigns")
    parser.add_argument("--visible", action="store_true", help="Show the WebEngine slot while running the live smoke test")
    parser.add_argument("--live-test-live-test", action="store_true", help="Guarded live test mode: load phones_test.xlsx and require owner/permission confirmation")
    parser.add_argument("--live-test-file", default=os.path.join(ROOT, "phones_test.xlsx"), help="Excel file for guarded live tests")
    parser.add_argument("--live-test-limit", type=int, default=45, help="Numbers to load for guarded live tests; default 45")
    parser.add_argument("--confirm-live-test", default="", help="Must equal the live-test consent phrase to skip interactive prompt")
    parser.add_argument("--rate-limit-sec", type=float, default=6.0, help="Minimum delay before each line dials its next live-test number")
    parser.add_argument("--max-parallel", type=int, default=1, help="Maximum concurrent live-test lines")
    parser.add_argument("--call-timeout", type=int, default=45)
    parser.add_argument("--connected-hold", type=int, default=8)
    parser.add_argument("--voicemail-hold", type=int, default=4)
    parser.add_argument("--stagger-ms", type=int, default=1200)
    args = parser.parse_args()

    if args.live_test_live_test:
        args.live_test_limit = max(1, int(args.live_test_limit or 45))
        if not args.confirm_live_test:
            print("LIVE TEST MODE will place real calls from phones_test.xlsx.", flush=True)
            print(f"Default guarded batch size is 45; this run will load {args.live_test_limit}.", flush=True)
            print(f"Type exactly: {LIVE_TEST_CONFIRMATION}", flush=True)
            args.confirm_live_test = input("Confirmation: ").strip()
        if args.confirm_live_test != LIVE_TEST_CONFIRMATION:
            raise SystemExit("Live test confirmation failed; no calls placed.")
        args.stagger_ms = max(args.stagger_ms, int(float(args.rate_limit_sec) * 1000))

    accounts = load_accounts()
    if args.target_voicemails or args.target_live:
        raise SystemExit(_run_crm_campaign(args, accounts))

    numbers = select_smoke_numbers(args, len(accounts))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(lambda: print("QApplication aboutToQuit", flush=True))
    smoke = LiveCallSmoke(
        numbers,
        call_timeout=args.call_timeout,
        connected_hold=args.connected_hold,
        voicemail_hold=args.voicemail_hold,
        stagger_ms=args.stagger_ms,
        report_path=args.report_path or None,
        print_debug=not args.quiet_debug,
        visible=bool(args.visible),
        max_parallel=args.max_parallel if args.live_test_live_test else len(numbers),
        rate_limit_sec=args.rate_limit_sec if args.live_test_live_test else max(1.0, args.stagger_ms / 1000.0),
        stop_on_failure=bool(args.live_test_live_test),
        manual_connect_confirmation=bool(args.visible),
    )
    panel = EmergencyStopPanel(smoke) if args.live_test_live_test else None
    if panel is not None:
        panel.show()
    QTimer.singleShot(0, smoke.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
