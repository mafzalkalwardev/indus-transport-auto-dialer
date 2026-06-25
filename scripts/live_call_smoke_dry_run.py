"""Dry-run smoke test that simulates the call pipeline without placing real calls."""
from __future__ import annotations

import argparse
import json
import os
import sys
import random
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.paths import LOGS_DIR


def simulate_call(phone: str, dry_run_delay: float = 1.5) -> dict:
    """Simulate one call through the full state pipeline."""
    states = [
        {"time": datetime.now().isoformat(timespec="seconds"), "state": "DIALING"},
        {"time": datetime.now().isoformat(timespec="seconds"), "state": "RINGING"},
    ]
    # Random terminal state: NO_ANSWER (60%), VOICEMAIL (25%), CONNECTED (15%)
    roll = random.random()
    if roll < 0.60:
        final = "NO_ANSWER"
        states.append({"time": datetime.now().isoformat(timespec="seconds"), "state": "NO_ANSWER"})
    elif roll < 0.85:
        final = "VOICEMAIL"
        states.extend([
            {"time": datetime.now().isoformat(timespec="seconds"), "state": "ANSWERED_PENDING"},
            {"time": datetime.now().isoformat(timespec="seconds"), "state": "VOICEMAIL"},
        ])
    else:
        final = "CONNECTED"
        states.extend([
            {"time": datetime.now().isoformat(timespec="seconds"), "state": "ANSWERED_PENDING"},
            {"time": datetime.now().isoformat(timespec="seconds"), "state": "CONNECTED"},
        ])

    result = {
        "phone": phone,
        "slot": 0,
        "account": "dry-run-simulator",
        "profile": "dry-run",
        "final": final,
        "states": states,
        "external_detector_enabled": False,
        "external_detector_mode": None,
        "external_evidence": [],
        "detector_reason": "simulated dry-run",
        "detector_confidence": 1.0,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate smoke test without placing calls")
    parser.add_argument("numbers", nargs="*", help="Phone numbers to simulate")
    parser.add_argument("--dry-run", action="store_true", help="Enable dry-run mode (no real calls)")
    parser.add_argument("--crm-limit", type=int, default=0, help="Load N contacts from CRM")
    parser.add_argument("--call-timeout", type=int, default=45)
    parser.add_argument("--report-path", default="", help="Fixed report path")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN] No calls will be placed.", flush=True)

    numbers = args.numbers or ["+15551234567", "+15559876543"]
    if args.crm_limit and not args.numbers:
        import sqlite3
        crm_db = os.path.join(ROOT, "logs", "crm.sqlite3")
        if os.path.exists(crm_db):
            with sqlite3.connect(crm_db) as con:
                con.row_factory = sqlite3.Row
                rows = con.execute(
                    "SELECT phone FROM contacts WHERE phone IS NOT NULL AND TRIM(phone) != '' LIMIT ?",
                    (max(1, args.crm_limit),),
                ).fetchall()
                numbers = [str(r["phone"]) for r in rows] or numbers

    started_at = datetime.now().isoformat(timespec="seconds")
    results = [simulate_call(p) for p in numbers]

    report = {
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "dry-run",
        "numbers": numbers,
        "results": results,
        "events": [{"time": started_at, "message": "Dry-run simulation complete"}],
    }

    os.makedirs(LOGS_DIR, exist_ok=True)
    report_path = args.report_path or os.path.join(
        LOGS_DIR,
        "live_call_smoke_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json",
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Dry-run report: {report_path}", flush=True)
    for rec in results:
        print(f"  {rec['phone']} -> {rec['final']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())