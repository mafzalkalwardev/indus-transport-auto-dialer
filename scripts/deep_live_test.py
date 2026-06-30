#!/usr/bin/env python3
"""Sustained headless live dial test — fresh CRM numbers, no repeats."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.webengine_env import configure_webengine_environment

configure_webengine_environment()

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from scripts.live_call_smoke import (
    LIVE_TEST_CONFIRMATION,
    LiveCallSmoke,
    _load_crm_numbers,
    _load_excel_numbers,
    load_all_report_dialed_numbers,
)
from src.gv_accounts import (
    clone_profile_folder,
    has_session_marker,
    load_accounts,
    make_profile_name,
    profile_dir,
)
from src.paths import LOGS_DIR

CONSENT = LIVE_TEST_CONFIRMATION

PREFERRED_EMAILS = (
    "johnson@faiq.info",
    "barry@faiq.info",
    "shared@faiq.info",
    "louis@faiq.info",
)

CLONE_SOURCE_EMAILS = (
    "johnson@faiq.info",
    "barry@faiq.info",
)


def expand_accounts_for_parallel(
    accounts: list[dict],
    parallel: int,
    *,
    allow_duplicates: bool,
) -> list[dict]:
    """Pick signed-in GV lines; clone profiles to reach *parallel* slots."""
    ready: list[dict] = []
    for acct in accounts:
        prof = str(acct.get("profile") or "").strip()
        if prof and has_session_marker(profile_dir(prof)):
            ready.append(dict(acct))

    def sort_key(a: dict) -> tuple[int, str]:
        email = str(a.get("email") or "").strip().lower()
        try:
            rank = PREFERRED_EMAILS.index(email)
        except ValueError:
            rank = len(PREFERRED_EMAILS)
        return rank, email

    ready.sort(key=sort_key)

    if parallel >= 3:
        stable = [
            a for a in ready
            if str(a.get("email", "")).lower() in CLONE_SOURCE_EMAILS
        ]
        if len(stable) >= 2:
            ready = stable

    if not ready:
        return []

    if len(ready) >= parallel:
        return ready[:parallel]
    if not allow_duplicates:
        return ready

    expanded = list(ready)
    existing_profiles = {str(a.get("profile") or "") for a in accounts}
    clone_sources = [
        a for a in ready
        if str(a.get("email", "")).lower() in CLONE_SOURCE_EMAILS
    ]
    if not clone_sources:
        clone_sources = ready[:2] or ready

    idx = 0
    while len(expanded) < parallel:
        src = clone_sources[idx % len(clone_sources)]
        idx += 1
        dst_profile = make_profile_name(
            f"{src.get('profile', 'gv')}_dup{len(expanded)}",
            str(src.get("email") or src.get("name") or "gv"),
            existing_profiles,
        )
        if not clone_profile_folder(str(src.get("profile") or ""), dst_profile):
            break
        existing_profiles.add(dst_profile)
        expanded.append({
            **src,
            "profile": dst_profile,
            "name": f"{src.get('name') or src.get('email')} #{len(expanded)}",
        })

    return expanded[:parallel]


class CrmSustainedLiveTest(LiveCallSmoke):
    """Dial fresh CRM numbers for min_duration_sec — never reuse a number."""

    def __init__(
        self,
        min_duration_sec: int,
        *,
        crm_batch_size: int,
        exclude: set[str],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.min_duration_sec = max(60, int(min_duration_sec))
        self.crm_batch_size = max(5, int(crm_batch_size))
        self.exclude = set(exclude)
        self.attempted = set(exclude)
        self._t0 = time.monotonic()
        self._call_seq = 0
        self._slot_active_since: dict[int, float] = {}

    def _elapsed(self) -> float:
        return time.monotonic() - self._t0

    def _should_continue(self) -> bool:
        return self._elapsed() < self.min_duration_sec

    def _refill_numbers(self) -> bool:
        need = max(self.crm_batch_size, self.max_parallel * 2)
        try:
            batch = _load_crm_numbers(need, self.attempted | self.exclude)
        except SystemExit:
            self.log(None, "No more unused CRM numbers available")
            return False
        if not batch:
            self.log(None, "CRM returned no fresh numbers")
            return False
        self.numbers.extend(batch)
        self.attempted.update(batch)
        self.log(
            None,
            f"Loaded {len(batch)} fresh CRM number(s) "
            f"({len(self.attempted)} attempted total, {len(self.numbers) - self.next_number_idx} queued)",
        )
        return True

    def start(self) -> None:
        super().start()
        kill_ms = int((self.min_duration_sec + 240) * 1000)
        QTimer.singleShot(kill_ms, self._sustained_timeout)
        QTimer.singleShot(15000, self._watch_stuck_slots)

    def _sustained_timeout(self) -> None:
        if self._should_continue():
            return
        self.timeout_remaining()

    def _watch_stuck_slots(self) -> None:
        if self.finished:
            return
        now = time.monotonic()
        for slot, call_id in list(self.active_by_slot.items()):
            since = self._slot_active_since.get(slot, now)
            if now - since < 90:
                continue
            rec = self.results.get(call_id, {})
            self.log(
                slot,
                f"Stuck call watchdog — forcing hangup after {int(now - since)}s "
                f"(final={rec.get('final', 'PENDING')})",
            )
            try:
                self.controllers[slot].hangup()
            except Exception:
                pass
            if rec.get("final") == "PENDING":
                rec["final"] = "STUCK_RECOVERED"
            self.release_slot(slot)
        if not self.finished:
            QTimer.singleShot(15000, self._watch_stuck_slots)

    def begin_dialing(self) -> None:
        self.log(
            None,
            f"CRM sustained test: {len(self.numbers)} number(s) queued, "
            f"{self.max_parallel} parallel line(s), "
            f"target runtime >= {self.min_duration_sec // 60} min "
            f"({self.min_duration_sec}s), unique-only=True",
        )
        super().begin_dialing()

    def assign_next(self, slot: int) -> None:
        if self.finished or self.stop_requested or slot in self.active_by_slot:
            return

        if self.next_number_idx >= len(self.numbers):
            if self._should_continue():
                if not self._refill_numbers():
                    if not self.active_by_slot:
                        self.check_done()
                    return
            elif not self.active_by_slot:
                self.check_done()
                return
            else:
                return

        if self.next_number_idx >= len(self.numbers):
            return

        call_id = self._call_seq
        self._call_seq += 1
        phone = self.numbers[self.next_number_idx]
        self.next_number_idx += 1
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
        self._slot_active_since[slot] = time.monotonic()
        self.dial(slot, call_id, phone)

    def release_slot(self, slot: int) -> None:
        self._slot_active_since.pop(slot, None)
        super().release_slot(slot)

    def check_done(self) -> None:
        if self._should_continue():
            if not self.active_by_slot and self.next_number_idx >= len(self.numbers):
                self._refill_numbers()
            return
        if (
            self.results
            and not self.active_by_slot
            and all(r.get("final") != "PENDING" for r in self.results.values())
        ):
            QTimer.singleShot(1500, self.finish)

    def finish(self) -> None:
        if self.finished:
            return
        elapsed = self._elapsed()
        unique = len({r.get("phone") for r in self.results.values()})
        self.log(
            None,
            f"Sustained test complete — {elapsed:.0f}s elapsed, "
            f"{len(self.results)} calls, {unique} unique numbers",
        )
        super().finish()


class SustainedLiveTest(CrmSustainedLiveTest):
    """Legacy excel cycler — kept for backward compatibility."""

    def assign_next(self, slot: int) -> None:
        if self.finished or self.stop_requested or slot in self.active_by_slot:
            return
        if self.next_number_idx >= len(self.numbers):
            if self._should_continue():
                self.next_number_idx = 0
                self.log(
                    None,
                    f"Cycle repeat — {self._elapsed():.0f}s / {self.min_duration_sec}s elapsed",
                )
            elif not self.active_by_slot:
                self.check_done()
                return
            else:
                return
        call_id = self._call_seq
        self._call_seq += 1
        phone = self.numbers[self.next_number_idx]
        self.next_number_idx += 1
        acct = self.accounts[slot]
        self.results[call_id] = {
            "slot": slot,
            "cycle": 1,
            "account": acct.get("name") or acct.get("email"),
            "profile": acct.get("profile"),
            "phone": phone,
            "states": [],
            "final": "PENDING",
        }
        self.active_by_slot[slot] = call_id
        self._slot_active_since[slot] = time.monotonic()
        self.dial(slot, call_id, phone)


def run_pytest() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def build_summary(report_path: str, pytest_rc: int, pytest_out: str, *, parallel: int = 1) -> dict:
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    results = report.get("results", [])
    finals = Counter(str(r.get("final") or "UNKNOWN") for r in results)
    phones = [str(r.get("phone") or "") for r in results]
    by_phone: dict[str, list[str]] = {}
    for r in results:
        by_phone.setdefault(r.get("phone", "?"), []).append(str(r.get("final")))

    humanish = sum(
        finals.get(k, 0)
        for k in (
            "HUMAN", "CONNECTED", "CONNECTED_AUDIO_EVIDENCE",
            "CONNECTED_MANUAL_CONFIRMATION", "ANSWERED_PENDING",
        )
    )
    failed = finals.get("FAILED", 0) + finals.get("TIMEOUT", 0) + finals.get("LOGIN_REQUIRED", 0)
    duplicate_dials = len(phones) - len({p for p in phones if p})

    started = report.get("started_at", "")
    finished = report.get("finished_at", "")
    duration_sec = 0
    try:
        t0 = datetime.fromisoformat(started)
        t1 = datetime.fromisoformat(finished)
        duration_sec = int((t1 - t0).total_seconds())
    except Exception:
        pass

    parallel = int(report.get("max_parallel") or parallel)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "pytest_exit_code": pytest_rc,
        "pytest_summary": pytest_out.splitlines()[-1] if pytest_out else "",
        "live_report": report_path,
        "duration_sec": duration_sec,
        "duration_min": round(duration_sec / 60, 1),
        "total_calls": len(results),
        "unique_numbers": len(set(phones)),
        "duplicate_dials": duplicate_dials,
        "max_parallel": parallel,
        "outcome_counts": dict(finals),
        "human_or_connected": humanish,
        "failures": failed,
        "by_phone": by_phone,
        "accounts_used": sorted({r.get("account") for r in results if r.get("account")}),
        "verdict": _verdict(
            pytest_rc,
            len(results),
            duration_sec,
            failed,
            finals,
            duplicate_dials,
            parallel,
            sequential_gate=bool(report.get("sequential_gate")),
            min_duration_sec=int(report.get("min_duration_sec") or 300),
        ),
    }


def _verdict(
    pytest_rc: int,
    calls: int,
    duration_sec: int,
    failed: int,
    finals: Counter,
    duplicate_dials: int,
    parallel: int,
    *,
    sequential_gate: bool = False,
    min_duration_sec: int = 300,
) -> str:
    if pytest_rc != 0:
        return "FAIL — unit tests did not all pass"
    if finals.get("LOGIN_REQUIRED", 0) > 0 or finals.get("GV_PAGE_BLANK", 0) > 0:
        return "FAIL — one or more Google Voice lines were not signed in"
    if duplicate_dials > 0:
        return f"FAIL — {duplicate_dials} duplicate number(s) were dialed"
    if sequential_gate:
        min_calls = max(5, parallel)
    else:
        min_calls = max(8, parallel * 2)
    if calls < min_calls:
        return f"FAIL — too few live calls completed ({calls} < {min_calls})"
    if duration_sec < min_duration_sec:
        return f"PARTIAL — live run was only {duration_sec}s (target {min_duration_sec}s+)"
    if failed > calls * 0.3:
        return "FAIL — high dial failure rate"
    if finals.get("FAILED", 0) > 0:
        return "WARN — some dials failed; review logs"
    return "PASS — sustained CRM live test with unique numbers"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep sustained headless live dial test")
    parser.add_argument("--min-minutes", type=float, default=5.0, help="Minimum continuous dial time")
    parser.add_argument("--max-parallel", type=int, default=3, help="Concurrent GV lines (3 recommended on 8 GB PCs)")
    parser.add_argument("--from-crm", dest="from_crm", action="store_true", default=True,
                        help="Use fresh CRM numbers (default)")
    parser.add_argument("--from-excel", dest="from_crm", action="store_false",
                        help="Use phones_test.xlsx and cycle numbers")
    parser.add_argument("--crm-batch-size", type=int, default=25, help="CRM numbers to prefetch per refill")
    parser.add_argument("--live-test-file", default=os.path.join(ROOT, "phones_test.xlsx"))
    parser.add_argument("--call-timeout", type=int, default=55)
    parser.add_argument("--rate-limit-sec", type=float, default=4.0)
    parser.add_argument("--allow-duplicate-lines", action="store_true", default=True,
                        help="Clone GV profiles to fill parallel slots (default on)")
    parser.add_argument("--force-parallel-dial", action="store_true",
                        help="Dial all lines at once (may crash WebEngine on Windows)")
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--confirm", default="", help="Consent phrase for live calls")
    args = parser.parse_args()

    if args.confirm != CONSENT:
        print(f"Live calls require: --confirm \"{CONSENT}\"", flush=True)
        return 2

    raw_accounts = load_accounts()
    if not raw_accounts:
        print("BLOCKED: no Google Voice accounts configured.", flush=True)
        return 2

    parallel = max(1, int(args.max_parallel))
    test_accounts = expand_accounts_for_parallel(
        raw_accounts,
        parallel,
        allow_duplicates=bool(args.allow_duplicate_lines),
    )
    if len(test_accounts) < parallel:
        print(
            f"BLOCKED: need {parallel} signed-in GV line(s), have {len(test_accounts)}.",
            flush=True,
        )
        print("Sign in via Settings or use --max-parallel with fewer lines.", flush=True)
        return 2

    print(
        f"Using {len(test_accounts)} GV line(s): "
        + ", ".join(f"{a.get('name')} ({a.get('email')})" for a in test_accounts),
        flush=True,
    )

    pytest_rc, pytest_out = 0, "skipped"
    if not args.skip_pytest:
        print("=== Phase 1: unit tests ===", flush=True)
        pytest_rc, pytest_out = run_pytest()
        print(pytest_out or "(no pytest output)", flush=True)
        if pytest_rc != 0:
            print("Unit tests failed — aborting live phase.", flush=True)
            return pytest_rc

    exclude = load_all_report_dialed_numbers()
    print(f"Excluding {len(exclude)} previously dialed number(s) from reports/CRM pool", flush=True)

    min_sec = int(args.min_minutes * 60)
    initial_batch = max(parallel * 3, args.crm_batch_size)

    if args.from_crm:
        numbers = _load_crm_numbers(initial_batch, exclude)
        print(f"Initial CRM batch: {len(numbers)} fresh number(s)", flush=True)
        test_cls = CrmSustainedLiveTest
        extra_kw = {"crm_batch_size": args.crm_batch_size, "exclude": exclude}
    else:
        numbers = _load_excel_numbers(args.live_test_file, limit=100)
        test_cls = SustainedLiveTest
        extra_kw = {"crm_batch_size": args.crm_batch_size, "exclude": exclude}

    print(f"\n=== Phase 2: sustained headless live calls ({args.min_minutes} min target) ===", flush=True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    report_path = os.path.join(
        LOGS_DIR,
        f"deep_live_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    smoke = test_cls(
        min_duration_sec=min_sec,
        numbers=numbers,
        call_timeout=args.call_timeout,
        connected_hold=6,
        voicemail_hold=4,
        stagger_ms=int(args.rate_limit_sec * 1000),
        report_path=report_path,
        print_debug=False,
        visible=False,
        max_parallel=parallel,
        rate_limit_sec=args.rate_limit_sec,
        stop_on_failure=False,
        allow_duplicate_lines=bool(args.allow_duplicate_lines),
        accounts=test_accounts,
        parallel_dial=bool(args.force_parallel_dial),
        **extra_kw,
    )
    QTimer.singleShot(0, smoke.start)
    app.exec()

    summary_path = report_path.replace(".json", "_summary.json")
    summary = build_summary(report_path, pytest_rc, pytest_out, parallel=parallel)
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    report["max_parallel"] = parallel
    report["unique_only"] = bool(args.from_crm)
    report["excluded_prior_numbers"] = len(exclude)
    report["min_duration_sec"] = min_sec
    report["sequential_gate"] = parallel > 1 and not args.force_parallel_dial
    report["parallel_dial"] = bool(args.force_parallel_dial)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== DEEP TEST SUMMARY ===", flush=True)
    print(f"Verdict: {summary['verdict']}", flush=True)
    print(f"Duration: {summary['duration_min']} min ({summary['duration_sec']}s)", flush=True)
    print(f"Total calls: {summary['total_calls']} ({summary['unique_numbers']} unique numbers)", flush=True)
    print(f"Parallel lines: {summary['max_parallel']}", flush=True)
    print(f"Outcomes: {summary['outcome_counts']}", flush=True)
    print(f"Human/connected: {summary['human_or_connected']}", flush=True)
    print(f"Report: {report_path}", flush=True)
    print(f"Summary: {summary_path}", flush=True)

    return 0 if summary["verdict"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
