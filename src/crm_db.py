"""
SQLite CRM database + PBKDF2-SHA256 authentication.
No third-party auth libraries required.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime
from typing import Optional

from src.paths import CRM_DB, CALL_LOG_CSV


# ── Password hashing (PBKDF2-SHA256, 260_000 iterations) ─────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    dk   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ── Database ──────────────────────────────────────────────────────────────────

class CRMDatabase:
    """Thread-safe SQLite wrapper."""

    def __init__(self):
        self._path = CRM_DB
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    email         TEXT    UNIQUE NOT NULL,
                    name          TEXT    NOT NULL,
                    password_hash TEXT    NOT NULL,
                    role          TEXT    DEFAULT 'agent',
                    is_active     INTEGER DEFAULT 1,
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

    # ── Admin setup ───────────────────────────────────────────────────────────

    def needs_admin_setup(self) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()
            return row[0] == 0

    def has_any_user(self) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) FROM users").fetchone()
            return row[0] > 0

    def create_admin(self, email: str, name: str, password: str) -> dict:
        pw_hash = _hash_password(password)
        with self._conn() as c:
            c.execute(
                "INSERT INTO users (email, name, password_hash, role, created_at) "
                "VALUES (?, ?, ?, 'admin', ?)",
                (email.lower().strip(), name, pw_hash,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        return {"email": email, "name": name, "role": "admin"}

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self, email: str, password: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM users WHERE email=? AND is_active=1",
                (email.lower().strip(),)
            ).fetchone()
        if row and _verify_password(password, row["password_hash"]):
            self._touch_login(row["id"])
            return dict(row)
        return None

    def _touch_login(self, user_id: int) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE users SET last_login=? WHERE id=?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id)
            )

    # ── User management (admin) ───────────────────────────────────────────────

    def create_user(self, email: str, name: str, password: str,
                    role: str = "agent") -> dict:
        pw_hash = _hash_password(password)
        with self._conn() as c:
            c.execute(
                "INSERT INTO users (email, name, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (email.lower().strip(), name, pw_hash, role,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        return {"email": email, "name": name, "role": role}

    def get_all_users(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in
                    c.execute("SELECT id,email,name,role,is_active,last_login "
                               "FROM users ORDER BY id").fetchall()]

    def set_user_active(self, user_id: int, active: bool) -> None:
        with self._conn() as c:
            c.execute("UPDATE users SET is_active=? WHERE id=?",
                      (1 if active else 0, user_id))

    def reset_password(self, user_id: int, new_password: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE users SET password_hash=? WHERE id=?",
                      (_hash_password(new_password), user_id))

    def delete_user(self, user_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM users WHERE id=?", (user_id,))

    # ── Contacts ──────────────────────────────────────────────────────────────

    def get_contacts(self, status_filter: str = "all") -> list[dict]:
        with self._conn() as c:
            if status_filter == "all":
                rows = c.execute(
                    "SELECT * FROM contacts ORDER BY id DESC").fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM contacts WHERE status=? ORDER BY id DESC",
                    (status_filter,)).fetchall()
        return [dict(r) for r in rows]

    def upsert_contact(self, phone: str, name: str = "", company: str = "",
                       email: str = "", notes: str = "",
                       status: str = "new") -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as c:
            c.execute(
                "INSERT INTO contacts (phone,name,company,email,notes,status,created_at) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(phone) DO UPDATE SET "
                "name=excluded.name, company=excluded.company, "
                "email=excluded.email, notes=excluded.notes, status=excluded.status",
                (phone, name, company, email, notes, status, now)
            )

    def update_contact_status(self, phone: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE contacts SET status=?, last_called=? WHERE phone=?",
                      (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone))

    def delete_contact(self, phone: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM contacts WHERE phone=?", (phone,))

    def import_contacts_from_list(self, rows: list[dict]) -> tuple[int, int]:
        added = skipped = 0
        for r in rows:
            try:
                self.upsert_contact(
                    phone=r.get("phone", ""),
                    name=r.get("name", ""),
                    company=r.get("company", ""),
                    email=r.get("email", ""),
                )
                added += 1
            except Exception:
                skipped += 1
        return added, skipped

    # ── Call records ──────────────────────────────────────────────────────────

    def log_call(self, user_id: int, phone: str, status: str,
                 contact_name: str = "", duration_s: float = 0.0,
                 slot_id: int = 0) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as c:
            c.execute(
                "INSERT INTO call_records "
                "(user_id,phone,contact_name,status,duration_s,slot_id,timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (user_id, phone, contact_name, status, duration_s, slot_id, now)
            )
        # Also write to CSV for compatibility
        self._append_csv(now, phone, status)

    def _append_csv(self, ts: str, phone: str, status: str) -> None:
        exists = os.path.isfile(CALL_LOG_CSV)
        try:
            with open(CALL_LOG_CSV, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if not exists:
                    w.writerow(["Time", "Phone", "Status"])
                w.writerow([ts, phone, status])
        except Exception:
            pass

    def get_call_records(self, user_id: Optional[int] = None,
                         limit: int = 500) -> list[dict]:
        with self._conn() as c:
            if user_id:
                rows = c.execute(
                    "SELECT * FROM call_records WHERE user_id=? "
                    "ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM call_records ORDER BY id DESC LIMIT ?",
                    (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_completed_phones(self) -> set[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT DISTINCT phone FROM call_records WHERE status='ENDED'"
            ).fetchall()
        return {r["phone"] for r in rows}
