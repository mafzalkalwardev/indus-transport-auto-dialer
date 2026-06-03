"""Build a client-only install folder (agent login, no admin setup)."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime

from src.crm_db import _hash_password
from src.paths import ROOT, CHROME_PROFILES_DIR, DATA_DIR, LOGS_DIR


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT    UNIQUE NOT NULL,
            name          TEXT    NOT NULL,
            password_hash TEXT    NOT NULL,
            role          TEXT    DEFAULT 'agent',
            is_active     INTEGER DEFAULT 1,
            subscription_plan TEXT DEFAULT 'manual',
            subscription_expires_at TEXT DEFAULT '',
            max_slots     INTEGER DEFAULT 1,
            created_at    TEXT,
            last_login    TEXT
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT UNIQUE NOT NULL,
            name        TEXT DEFAULT '',
            company     TEXT DEFAULT '',
            email       TEXT DEFAULT '',
            notes       TEXT DEFAULT '',
            status      TEXT DEFAULT 'new',
            last_called TEXT,
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS call_records (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            phone        TEXT,
            contact_name TEXT DEFAULT '',
            status       TEXT,
            duration_s   REAL DEFAULT 0,
            slot_id      INTEGER DEFAULT 0,
            session_id   TEXT DEFAULT '',
            timestamp    TEXT
        );
    """)


def create_agent_only_database(db_path: str, email: str, name: str,
                               password: str, subscription_plan: str = "manual",
                               subscription_expires_at: str = "",
                               max_slots: int = 1) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        _init_schema(conn)
        conn.execute(
            "INSERT INTO users "
            "(email, name, password_hash, role, subscription_plan, "
            "subscription_expires_at, max_slots, created_at) "
            "VALUES (?, ?, ?, 'agent', ?, ?, ?, ?)",
            (
                email.lower().strip(),
                name.strip(),
                _hash_password(password),
                subscription_plan,
                subscription_expires_at,
                int(max_slots),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def export_client_package(
    output_dir: str,
    client_name: str,
    client_email: str,
    client_password: str,
    admin_cfg: dict,
    copy_voice_profiles: bool = True,
    subscription_plan: str = "manual",
    subscription_expires_at: str = "",
    max_slots: int | None = None,
) -> str:
    """
    Write a folder to copy onto the client's PC.
    Contains agent-only login, voice profiles, and client deployment flag.
    Returns path to the package root.
    """
    pkg = os.path.join(output_dir, "IndusTransports_AutoDialer_Client")
    if os.path.isdir(pkg):
        shutil.rmtree(pkg, ignore_errors=True)
    os.makedirs(pkg, exist_ok=True)

    logs_dir = os.path.join(pkg, "logs")
    data_dir = os.path.join(pkg, "data")
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    create_agent_only_database(
        os.path.join(logs_dir, "crm.sqlite3"),
        client_email,
        client_name,
        client_password,
        subscription_plan=subscription_plan,
        subscription_expires_at=subscription_expires_at,
        max_slots=max_slots or int(admin_cfg.get("n_slots", 1)),
    )

    cfg = {
        k: admin_cfg.get(k, v)
        for k, v in {
            "theme": "light",
            "n_slots": 1,
            "call_timeout": 60,
            "cooldown": 3.0,
            "voicemail_hangup_sec": 3,
            "excel_path": "",
            "deployment_mode": "client",
        }.items()
    }
    cfg["deployment_mode"] = "client"
    if max_slots is not None:
        cfg["n_slots"] = max(1, min(int(max_slots), int(cfg.get("n_slots", 1))))
    with open(os.path.join(pkg, "dialer_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    src_gv = os.path.join(DATA_DIR, "gv_accounts.json")
    if os.path.isfile(src_gv):
        shutil.copy2(src_gv, os.path.join(data_dir, "gv_accounts.json"))

    if copy_voice_profiles and os.path.isdir(CHROME_PROFILES_DIR):
        dst_profiles = os.path.join(pkg, "chrome_profiles")
        shutil.copytree(
            CHROME_PROFILES_DIR,
            dst_profiles,
            ignore=shutil.ignore_patterns("*.lock", "LOCK", "LOCKFILE"),
            dirs_exist_ok=True,
        )

    readme = f"""Indus Transports Auto Dialer — Client workstation
=====================================================

INSTALL ON CLIENT PC
--------------------
1. Install the same Auto Dialer app (Python or EXE) into a folder, e.g.:
   C:\\IndusTransports\\AutoDialer

2. Copy ALL files from this package INTO that folder (merge/replace):
   - dialer_config.json
   - logs\\
   - data\\
   - chrome_profiles\\

3. Run the app. The client will see ONLY a sign-in screen (no admin setup).

CLIENT LOGIN (give these to your client only)
---------------------------------------------
Name:     {client_name}
Email:    {client_email}
Password: (the password you chose when creating this package)
Plan:     {subscription_plan}
Expires:  {subscription_expires_at or 'No local expiry'}
Max slots: {max_slots or int(admin_cfg.get("n_slots", 1))}

The client cannot create administrators or change Google Voice lines.

SUPPORT
-------
Configured by your administrator on {datetime.now().strftime("%Y-%m-%d")}.
"""
    with open(os.path.join(pkg, "CLIENT_SETUP.txt"), "w", encoding="utf-8") as f:
        f.write(readme)

    return pkg


def is_client_deployment(cfg: dict) -> bool:
    return str(cfg.get("deployment_mode", "admin")).lower() == "client"
