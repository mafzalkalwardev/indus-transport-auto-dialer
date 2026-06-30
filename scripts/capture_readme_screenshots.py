"""Capture README screenshots for light and dark themes."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.webengine_env import configure_webengine_environment

configure_webengine_environment()

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget

from autodialer_gui import LoginPage, MainWindow, _load_cfg
from src.crm_db import CRMDatabase
from src.ui_theme import DEFAULT_THEME, apply_theme

OUT_DIR = os.path.join(ROOT, "docs", "screenshots")

TAB_CAPTURES = [
    ("dialer", 0),
    ("live-calls", 1),
    ("call-logs", 2),
    ("crm", 3),
    ("settings", 4),
    ("administration", 5),
]


def _wait_ms(app: QApplication, ms: int = 400) -> None:
    done = {"ok": False}

    def _finish() -> None:
        done["ok"] = True

    QTimer.singleShot(ms, _finish)
    while not done["ok"]:
        app.processEvents()


def _grab(widget: QWidget, path: str) -> None:
    widget.repaint()
    QApplication.processEvents()
    pix = widget.grab()
    if pix.isNull():
        raise RuntimeError(f"grab failed for {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not pix.save(path, "PNG"):
        raise RuntimeError(f"save failed for {path}")
    print(f"saved {path} ({pix.width()}x{pix.height()})")


def _admin_user(db: CRMDatabase) -> dict:
    users = db.get_all_users()
    for user in users:
        if user.get("role") == "admin":
            return user
    if users:
        return users[0]
    raise RuntimeError("No CRM users found — create an admin account first.")


def _capture_login(app: QApplication, db: CRMDatabase, theme: str) -> None:
    stack = QStackedWidget()
    stack.setWindowTitle("INDUS TRANSPORTS LLC — Auto Dialer")
    stack.resize(1000, 680)
    apply_theme(app, theme)
    page = LoginPage(db, client_mode=False)
    stack.addWidget(page)
    stack.show()
    _wait_ms(app, 500)
    _grab(stack, os.path.join(OUT_DIR, f"login-{theme}.png"))
    stack.close()


def _capture_main(app: QApplication, db: CRMDatabase, cfg: dict, theme: str) -> None:
    cfg = dict(cfg)
    cfg["theme"] = theme
    cfg["dry_run_mode"] = True
    cfg["n_slots"] = 1
    apply_theme(app, theme)

    # Skip Google Voice browser boot — screenshots only need static UI chrome.
    MainWindow._deferred_boot_controllers = lambda self: None  # type: ignore[method-assign]

    win = MainWindow(db, _admin_user(db), cfg)
    win._set_theme(theme)
    win.show()
    _wait_ms(app, 600)

    for slug, index in TAB_CAPTURES:
        if index >= win.tabs.count():
            continue
        win.tabs.setCurrentIndex(index)
        _wait_ms(app, 350)
        _grab(win, os.path.join(OUT_DIR, f"{slug}-{theme}.png"))

    win.close()


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName("IndusTransports Screenshot Capture")

    db = CRMDatabase()
    cfg = _load_cfg()

    for theme in ("light", "dark"):
        print(f"--- {theme} theme ---")
        _capture_login(app, db, theme)
        _capture_main(app, db, cfg, theme)

    manifest = {
        "captured_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "themes": ["light", "dark"],
        "files": sorted(
            f for f in os.listdir(OUT_DIR)
            if f.endswith(".png") and f not in ("login-page.png", "dialer-tab.png")
        ),
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
