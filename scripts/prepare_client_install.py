#!/usr/bin/env python3
"""CLI: build client-only install folder (run on administrator PC)."""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.client_deploy import export_client_package
from src.paths import CONFIG_FILE


def main() -> None:
    p = argparse.ArgumentParser(
        description="Export agent-only package for a client PC")
    p.add_argument("--name", required=True, help="Client display name")
    p.add_argument("--email", required=True, help="Client login email")
    p.add_argument("--password", required=True, help="Client login password")
    p.add_argument("--output", default=os.path.expanduser("~/Desktop"),
                   help="Parent folder for the package")
    p.add_argument("--no-profiles", action="store_true",
                   help="Do not copy chrome_profiles")
    p.add_argument("--subscription-plan", default="manual",
                   help="Plan label stored in the client database")
    p.add_argument("--subscription-expires-at", default="",
                   help="Expiry date/time, e.g. 2026-07-04 or 2026-07-04 23:59:59")
    p.add_argument("--max-slots", type=int, default=None,
                   help="Maximum live dialing slots for this client, 1-5")
    args = p.parse_args()

    cfg = {}
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)

    pkg = export_client_package(
        args.output,
        args.name,
        args.email,
        args.password,
        cfg,
        copy_voice_profiles=not args.no_profiles,
        subscription_plan=args.subscription_plan,
        subscription_expires_at=args.subscription_expires_at,
        max_slots=args.max_slots,
    )
    print(f"Client package created:\n  {pkg}")
    print("Copy its contents into the app folder on the client PC.")
    print("See CLIENT_SETUP.txt inside the package.")


if __name__ == "__main__":
    main()
