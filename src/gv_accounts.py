"""Google Voice account registry.

Labels, emails, optional passwords, notes, and local profile folder names are
stored in an ignored local JSON file. Google's logged-in session remains inside
the persistent browser profile.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

from src.paths import DATA_DIR, CHROME_PROFILES_DIR

SESSION_MARKER = ".gv_session_ok"


def session_marker_path(profile_dir_path: str) -> str:
    return os.path.join(profile_dir_path, SESSION_MARKER)


def has_session_marker(profile_dir_path: str) -> bool:
    return os.path.isfile(session_marker_path(profile_dir_path))


GV_ACCOUNTS_FILE = os.path.join(DATA_DIR, "gv_accounts.json")


def _slug(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return base or "google_voice"


def make_profile_name(name: str, email: str, existing: set[str] | None = None) -> str:
    existing = existing or set()
    base = _slug(email or name)
    candidate = base
    i = 2
    while candidate in existing:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


def profile_dir(profile_name: str) -> str:
    return os.path.join(CHROME_PROFILES_DIR, profile_name)


def load_accounts() -> list[dict[str, Any]]:
    if not os.path.exists(GV_ACCOUNTS_FILE):
        return []
    try:
        with open(GV_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    accounts: list[dict[str, Any]] = []
    existing: set[str] = set()
    changed = False
    for raw in data:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        email = str(raw.get("email", "")).strip().lower()
        if not name and email:
            name = email.split("@", 1)[0]
        if not name or not email:
            continue
        profile = str(raw.get("profile", "")).strip()
        if not profile:
            profile = make_profile_name(name, email, existing)
            changed = True
        existing.add(profile)
        accounts.append({
            "name": name,
            "email": email,
            "password": str(raw.get("password", "")),
            "profile": profile,
            "notes": str(raw.get("notes", "")).strip(),
        })
    if changed:
        save_accounts(accounts)
    return accounts


def save_accounts(accounts: list[dict[str, Any]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(GV_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2)


def clone_profile_folder(src_profile: str, dst_profile: str) -> bool:
    """
    Copy a logged-in browser profile so duplicates keep the same Google session.
    """
    src = profile_dir(src_profile)
    dst = profile_dir(dst_profile)
    if not os.path.isdir(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    try:
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns("*.lock", "LOCK", "LOCKFILE"),
        )
        if os.path.isfile(session_marker_path(src)):
            open(session_marker_path(dst), "w", encoding="utf-8").close()
        return True
    except Exception:
        return False
