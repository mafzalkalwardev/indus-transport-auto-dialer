#!/usr/bin/env python3
"""
INDUS TRANSPORTS LLC — Auto Dialer Pro
Google Voice runs silently inside an embedded browser.
Agents see only our branded interface — Google Voice is never visible.
"""
import os
import sys
import json
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QLineEdit, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QSpinBox, QDoubleSpinBox, QFileDialog, QMessageBox,
    QTextEdit, QFrame, QProgressBar, QScrollArea, QSizePolicy,
    QTabWidget, QSplitter, QGroupBox, QRadioButton, QButtonGroup,
    QFormLayout, QAbstractItemView, QSystemTrayIcon, QMenu,
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QUrl, pyqtSignal, QThread, QObject,
)
from PyQt6.QtGui import (
    QColor, QPalette, QFont, QIcon, QPixmap, QAction, QFontDatabase,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

import pandas as pd

from src.paths       import (LOGO_PNG, LOGO_JPEG, CONFIG_FILE,
                              CHROME_PROFILES_DIR, LOGS_DIR)
from src.crm_db      import CRMDatabase
from src.phone_utils import clean_phone, fmt_e164, fmt_display
from src.gv_controller import (
    GVController,
    has_session_marker,
    write_session_marker,
)
from src.ui_theme import (
    DARK_QSS, LIGHT_QSS, DEFAULT_THEME,
    status_label, status_color,
)
from src.gv_accounts import (
    load_accounts as load_gv_accounts,
    save_accounts as save_gv_accounts,
    make_profile_name,
    profile_dir as gv_profile_dir,
)

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Constants ─────────────────────────────────────────────────────────────────
APP_NAME     = "INDUS TRANSPORTS LLC — Auto Dialer Pro"
WHATSAPP_URL = "https://wa.me/923079670503"
WA_NUMBER    = "+92 307 967 0503"

# ── Config ────────────────────────────────────────────────────────────────────
def _load_cfg() -> dict:
    defaults = {"theme": DEFAULT_THEME, "n_slots": 2, "call_timeout": 60,
                "cooldown": 3.0, "voicemail_hangup_sec": 3,
                "excel_path": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                d = json.load(f)
            for k, v in defaults.items():
                if k not in d:
                    d[k] = v
            return d
        except Exception:
            pass
    return defaults

def _save_cfg(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

# ── Helpers ───────────────────────────────────────────────────────────────────
def _icon() -> QIcon:
    for path in (LOGO_PNG, LOGO_JPEG):
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()

def _pixmap(h: int = 48) -> QPixmap | None:
    for path in (LOGO_PNG, LOGO_JPEG):
        if os.path.exists(path):
            px = QPixmap(path)
            if not px.isNull():
                return px.scaledToHeight(h, Qt.TransformationMode.SmoothTransformation)
    return None

def _btn(text: str, obj_name: str = "", parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    if obj_name:
        b.setObjectName(obj_name)
    return b

def _label(text: str, obj_name: str = "", bold: bool = False,
           size: int = 0, parent=None) -> QLabel:
    lbl = QLabel(text, parent)
    if obj_name:
        lbl.setObjectName(obj_name)
    if bold or size:
        f = lbl.font()
        if bold:
            f.setBold(True)
        if size:
            f.setPointSize(size)
        lbl.setFont(f)
    return lbl

def _hline() -> QFrame:
    line = QFrame()
    line.setObjectName("hline")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


# ══════════════════════════════════════════════════════════════════════════════
#  SLOT CARD WIDGET
# ══════════════════════════════════════════════════════════════════════════════

class SlotCard(QGroupBox):
    next_clicked = pyqtSignal(int)
    cut_clicked = pyqtSignal(int)

    def __init__(self, slot_id: int, parent=None):
        super().__init__(f"Line {slot_id + 1}", parent)
        self.setObjectName("slotCard")
        self.slot_id = slot_id
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self._current_state = "IDLE"
        self._gv_ready = False
        self.lbl_status = _label("Setup required", bold=True)
        self._apply_status_style("SETUP REQUIRED")
        lay.addWidget(self.lbl_status)

        self.lbl_phone = _label("No active number", "muted")
        lay.addWidget(self.lbl_phone)

        self.lbl_dur = _label("Call time: —", "muted")
        lay.addWidget(self.lbl_dur)

        btn_row = QHBoxLayout()
        self.btn_next = _btn("Next number", "green")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(lambda: self.next_clicked.emit(self.slot_id))
        btn_row.addWidget(self.btn_next)

        self.btn_cut = _btn("End call", "red")
        self.btn_cut.setEnabled(False)
        self.btn_cut.clicked.connect(lambda: self.cut_clicked.emit(self.slot_id))
        btn_row.addWidget(self.btn_cut)
        lay.addLayout(btn_row)

    def _apply_status_style(self, key: str) -> None:
        c = status_color(key)
        self.lbl_status.setStyleSheet(
            f"color: {c}; font-weight: 600; font-size: 11pt;")

    def update_state(self, state: str, phone: str = "", elapsed: str = ""):
        self._current_state = state
        self.lbl_status.setText(status_label(state))
        self._apply_status_style(state)
        self.lbl_phone.setText(phone if phone else "No active number")
        self.lbl_dur.setText(
            f"Call time: {elapsed}" if elapsed else "Call time: —")
        active = state in ("DIALING", "RINGING", "CONNECTED", "VOICEMAIL")
        self.btn_next.setEnabled(active)
        self.btn_cut.setEnabled(active)

        self.setProperty("connected", state == "CONNECTED")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_gv_login_ready(self, ready: bool) -> None:
        self._gv_ready = ready
        if getattr(self, "_current_state", "IDLE") != "IDLE":
            return
        key = "READY" if ready else "SETUP REQUIRED"
        self.lbl_status.setText(status_label(key))
        self._apply_status_style(key)


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN SETUP PAGE
# ══════════════════════════════════════════════════════════════════════════════

class AdminSetupPage(QWidget):
    done = pyqtSignal()

    def __init__(self, db: CRMDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo
        px = _pixmap(64)
        if px:
            lbl_logo = QLabel()
            lbl_logo.setPixmap(px)
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl_logo)

        lay.addWidget(_label("INDUS TRANSPORTS LLC", bold=True, size=16,
                              parent=self))
        lay.addWidget(_label("Create your Administrator account to get started",
                              "muted", parent=self))
        lay.addSpacing(20)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.e_name  = QLineEdit(); self.e_name.setPlaceholderText("Full name")
        self.e_email = QLineEdit(); self.e_email.setPlaceholderText("admin@company.com")
        self.e_pw    = QLineEdit(); self.e_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pw.setPlaceholderText("Min. 8 characters")
        self.e_pw2   = QLineEdit(); self.e_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pw2.setPlaceholderText("Repeat password")
        for w in (self.e_name, self.e_email, self.e_pw, self.e_pw2):
            w.setMinimumWidth(300)
        form.addRow("Full Name:", self.e_name)
        form.addRow("Email:",     self.e_email)
        form.addRow("Password:",  self.e_pw)
        form.addRow("Confirm:",   self.e_pw2)
        lay.addLayout(form)
        lay.addSpacing(16)

        btn = _btn("Create Admin Account", "green")
        btn.setMinimumWidth(240)
        btn.clicked.connect(self._submit)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _submit(self):
        name  = self.e_name.get() if hasattr(self.e_name, 'get') else self.e_name.text().strip()
        email = self.e_email.text().strip()
        pw    = self.e_pw.text()
        pw2   = self.e_pw2.text()
        if not all([name, email, pw]):
            QMessageBox.warning(self, "Missing Fields", "All fields are required.")
            return
        if pw != pw2:
            QMessageBox.warning(self, "Mismatch", "Passwords do not match.")
            return
        if len(pw) < 8:
            QMessageBox.warning(self, "Weak Password", "Use at least 8 characters.")
            return
        try:
            self.db.create_admin(email, name, pw)
            QMessageBox.information(
                self, "Account Created",
                f"Admin account created!\n\nEmail: {email}\n\n"
                "Keep these credentials secure. This setup will not appear again."
            )
            self.done.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN PAGE
# ══════════════════════════════════════════════════════════════════════════════

class LoginPage(QWidget):
    login_success = pyqtSignal(dict)

    def __init__(self, db: CRMDatabase, parent=None):
        super().__init__(parent)
        self.setObjectName("loginPage")
        self.db = db
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setFixedWidth(420)
        lay = QVBoxLayout(card)
        lay.setSpacing(12)
        lay.setContentsMargins(36, 32, 36, 32)

        px = _pixmap(64)
        if px:
            lbl = QLabel()
            lbl.setPixmap(px)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)
            lay.addSpacing(4)

        lay.addWidget(_label("Indus Transports", "brandName", bold=True, size=16))
        lay.addWidget(_label("Sign in to your dialer account", "muted"))
        lay.addSpacing(16)

        self.e_email = QLineEdit()
        self.e_email.setPlaceholderText("Work email")
        lay.addWidget(self.e_email)
        self.e_pw = QLineEdit()
        self.e_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pw.setPlaceholderText("Password")
        self.e_pw.returnPressed.connect(self._login)
        lay.addWidget(self.e_pw)
        lay.addSpacing(8)

        self.lbl_err = _label("", "danger")
        lay.addWidget(self.lbl_err, alignment=Qt.AlignmentFlag.AlignCenter)

        btn = _btn("Sign in", "primary")
        btn.setMinimumHeight(42)
        btn.clicked.connect(self._login)
        lay.addWidget(btn)
        lay.addSpacing(8)

        lay.addWidget(
            _label("Need access? Contact your administrator.", "muted"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        outer.addWidget(card)

    def _login(self):
        user = self.db.authenticate(self.e_email.text().strip(),
                                    self.e_pw.text())
        if user:
            self.login_success.emit(user)
        else:
            self.lbl_err.setText("Incorrect email or password.")


# ══════════════════════════════════════════════════════════════════════════════
#  GV SETUP DIALOG  (shown when profile not yet logged in)
# ══════════════════════════════════════════════════════════════════════════════

class GVSetupDialog(QDialog):
    """Shows the embedded browser so user can log into Google Voice."""

    login_succeeded = pyqtSignal()

    def __init__(self, controller: GVController, account_label: str,
                 profile_dir: str, login_email: str = "",
                 on_password_saved=None, parent=None):
        super().__init__(parent)
        self.setObjectName("gvSetupDialog")
        self.controller = controller
        self._on_password_saved = on_password_saved
        self._login_email = login_email
        self._profile_dir = profile_dir
        self.setWindowTitle(f"Google Voice — {account_label}")
        self.setMinimumSize(960, 740)
        self.resize(980, 760)

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 18, 20, 18)

        lay.addWidget(_label(f"Connect {account_label}", "heroTitle"))
        sub = _label(
            "Sign in once below. Your session stays on this computer so you can "
            "dial without signing in again.",
            "muted",
        )
        sub.setWordWrap(True)
        lay.addWidget(sub)

        cred_row = QHBoxLayout()
        cred_row.addWidget(_label("Password", "muted"))
        self.e_password = QLineEdit()
        self.e_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_password.setPlaceholderText("Google account password")
        if controller._login_password:
            self.e_password.setText(controller._login_password)
        cred_row.addWidget(self.e_password, stretch=1)
        apply_btn = _btn("Apply & sign in", "green")
        apply_btn.clicked.connect(self._apply_password)
        cred_row.addWidget(apply_btn)
        lay.addLayout(cred_row)

        if login_email:
            lay.addWidget(_label(f"Email: {login_email}", "accent"))

        self.load_bar = QProgressBar()
        self.load_bar.setRange(0, 0)
        self.load_bar.setTextVisible(False)
        self.load_bar.setFixedHeight(4)
        lay.addWidget(self.load_bar)

        self.lbl_status = _label("Preparing sign-in page…", "statusPill")
        self.lbl_status.setObjectName("statusPill")
        lay.addWidget(self.lbl_status)

        self.browser_frame = QFrame()
        self.browser_frame.setObjectName("browserFrame")
        self.browser_frame.setMinimumHeight(420)
        flay = QVBoxLayout(self.browser_frame)
        flay.setContentsMargins(0, 0, 0, 0)
        flay.addWidget(controller.view)
        lay.addWidget(self.browser_frame, stretch=1)

        btn_row = QHBoxLayout()
        reload_btn = _btn("Reload", "")
        reload_btn.clicked.connect(self._reload_signin)
        open_btn = _btn("Profile folder", "")
        open_btn.clicked.connect(self._open_profile)
        btn_row.addWidget(reload_btn)
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        btn_done = _btn("I'm signed in — continue", "primary")
        btn_done.clicked.connect(self._confirm_login)
        lay.addWidget(btn_done)

        def on_log(_sid: int, msg: str) -> None:
            self.lbl_status.setText(msg)
            if "failed" not in msg.lower():
                self.load_bar.setRange(0, 1)
                self.load_bar.setValue(1)

        def on_login(_sid: int) -> None:
            self.controller.mark_logged_in()
            self.lbl_status.setText("Signed in — saving session…")
            self.login_succeeded.emit()
            QTimer.singleShot(700, self.accept)

        controller.log_message.connect(on_log)
        controller.login_detected.connect(on_login)
        controller._page.loadProgress.connect(self._on_load_progress)

        QTimer.singleShot(50, self._start_signin)

    def _start_signin(self) -> None:
        self.load_bar.setRange(0, 0)
        if self.controller._login_password:
            self.controller.load(for_setup=True)
        else:
            self.lbl_status.setText(
                "Enter password above, then click Apply & sign in.")

    def _reload_signin(self) -> None:
        self.load_bar.setRange(0, 0)
        self.lbl_status.setText("Reloading sign-in page…")
        self.controller.load(for_setup=True)

    def _open_profile(self) -> None:
        os.makedirs(self._profile_dir, exist_ok=True)
        os.startfile(self._profile_dir)

    def _on_load_progress(self, pct: int) -> None:
        if pct >= 100:
            self.load_bar.setRange(0, 1)
            self.load_bar.setValue(1)
            self.lbl_status.setText("Complete sign-in in the window below")

    def _apply_password(self) -> None:
        pw = self.e_password.text().strip()
        if not pw:
            self.lbl_status.setText("Enter your Google password first.")
            return
        if self._on_password_saved:
            self._on_password_saved(pw)
        self.controller.set_login_credentials(
            self._login_email or self.controller._login_email, pw)
        self.controller._autofill_paused = False
        self.controller._email_step_done = False
        self.controller._last_login_fill_status = ""
        self.load_bar.setRange(0, 0)
        self.lbl_status.setText("Signing in automatically…")
        self.controller.load(for_setup=True)

    def _confirm_login(self) -> None:
        self.controller.mark_logged_in()
        self.accept()

    def accept(self) -> None:
        if not self.controller.is_session_ready():
            self.controller.mark_logged_in()
        super().accept()


# ══════════════════════════════════════════════════════════════════════════════
#  CREATE USER DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class CreateUserDialog(QDialog):
    def __init__(self, db: CRMDatabase, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Create User Account")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.e_name  = QLineEdit(); self.e_name.setPlaceholderText("Full name")
        self.e_email = QLineEdit(); self.e_email.setPlaceholderText("user@company.com")
        self.e_pw    = QLineEdit(); self.e_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pw.setPlaceholderText("Min. 8 characters")
        self.role_combo = QComboBox()
        self.role_combo.addItems(["agent", "admin"])
        form.addRow("Name:",     self.e_name)
        form.addRow("Email:",    self.e_email)
        form.addRow("Password:", self.e_pw)
        form.addRow("Role:",     self.role_combo)
        lay.addLayout(form)
        lay.addSpacing(12)

        btn = _btn("Create User", "green")
        btn.clicked.connect(self._create)
        lay.addWidget(btn)

    def _create(self):
        name  = self.e_name.text().strip()
        email = self.e_email.text().strip()
        pw    = self.e_pw.text()
        role  = self.role_combo.currentText()
        if not all([name, email, pw]):
            QMessageBox.warning(self, "Error", "All fields required.")
            return
        if len(pw) < 8:
            QMessageBox.warning(self, "Error", "Password must be 8+ characters.")
            return
        try:
            self.db.create_user(email, name, pw, role=role)
            QMessageBox.information(
                self, "Created",
                f"User {email} created.\nRole: {role}\n\n"
                f"They can log in with:\n  Email: {email}\n  Password: (as set)"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION WINDOW
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):

    def __init__(self, db: CRMDatabase, user: dict, cfg: dict):
        super().__init__()
        self.db   = db
        self.user = user
        self.cfg  = cfg

        self.setWindowTitle("Indus Transports — Auto Dialer")
        self.setWindowIcon(_icon())
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        # ── Dialer state ──────────────────────────────────────────────────────
        self._controllers: list[GVController] = []
        self._contacts:    list[tuple[str, str]] = []
        self._contact_idx: int = 0
        self._running:     bool = False
        self._slot_start:  dict[int, float] = {}
        self._slot_phone:  dict[int, str]   = {}
        self._all_logs:    list = []
        self._gv_accounts: list[dict] = load_gv_accounts()

        # ── Timers ────────────────────────────────────────────────────────────
        self._dial_timer   = QTimer(self)    # fires to assign next number to free slot
        self._dial_timer.setInterval(1500)
        self._dial_timer.timeout.connect(self._assign_pending_calls)

        self._elapsed_timer = QTimer(self)   # updates elapsed display on slot cards
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        # ── Build UI ──────────────────────────────────────────────────────────
        self._build_hidden_browser_container()
        self._build_header()
        self._build_tabs()
        self._build_status_bar()

        # ── Boot controllers ──────────────────────────────────────────────────
        self._init_controllers(cfg.get("n_slots", 2))

    # ── Hidden browser container ──────────────────────────────────────────────

    def _build_hidden_browser_container(self):
        """
        All QWebEngineViews live here — hidden from the agent.
        Size 1×1 so they are technically in the layout (needed for WebRTC audio)
        but invisible to the user.
        """
        self._browser_host = QWidget(self)
        self._browser_host.setMaximumSize(1, 1)
        self._browser_layout = QHBoxLayout(self._browser_host)
        self._browser_layout.setContentsMargins(0, 0, 0, 0)

    def _show_browser_for_setup(self, view: QWebEngineView) -> None:
        """Expand embedded browser for visible login in GVSetupDialog."""
        if view.parent() is self._browser_host:
            self._browser_layout.removeWidget(view)
        view.setParent(None)
        max_dim = 16777215
        view.setMinimumSize(800, 480)
        view.setMaximumSize(max_dim, max_dim)
        view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view.show()

    def _hide_browser_after_setup(self, view: QWebEngineView) -> None:
        """Return embedded browser to hidden 1×1 host after login setup."""
        view.setParent(self._browser_host)
        view.setMinimumSize(0, 0)
        view.setMaximumSize(1, 1)
        view.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._browser_layout.addWidget(view)

    def _refresh_slot_login_badges(self) -> None:
        if not hasattr(self, "_slot_cards"):
            return
        for ctrl in self._controllers:
            sid = ctrl.slot_id
            if sid in self._slot_cards:
                self._slot_cards[sid].set_gv_login_ready(ctrl.is_session_ready())

    def _account_session_ready(self, acct: dict) -> bool:
        target = gv_profile_dir(acct["profile"])
        if has_session_marker(target):
            return True
        for ctrl in self._controllers:
            if os.path.abspath(ctrl.profile_dir) == os.path.abspath(target):
                if ctrl.is_session_ready():
                    return True
                ctrl._check_login()
        return has_session_marker(target)

    def _dialing_login_ok(self) -> tuple[bool, str]:
        if not self._gv_accounts:
            return False, (
                "Add at least one Google Voice account in Settings, then use "
                "Login / Setup Selected.")
        n = self.spin_slots.value()
        missing: list[str] = []
        for i in range(n):
            acct = self._slot_account(i)
            if not acct:
                continue
            if not self._account_session_ready(acct):
                missing.append(acct.get("name") or acct.get("email", f"Slot {i+1}"))
        if missing:
            return False, (
                "Google Voice is not ready for:\n• "
                + "\n• ".join(missing)
                + "\n\nOpen Settings → Login / Setup Selected and complete sign-in once.")
        return True, ""

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = QWidget()
        hdr.setObjectName("appHeader")
        hdr.setFixedHeight(76)
        h = QHBoxLayout(hdr)
        h.setContentsMargins(20, 10, 20, 10)

        # Logo + name
        left = QHBoxLayout()
        px = _pixmap(52)
        if px:
            lbl_logo = QLabel()
            lbl_logo.setPixmap(px)
            lbl_logo.setStyleSheet("background: transparent;")
            left.addWidget(lbl_logo)
            left.addSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        name_lbl = _label("INDUS TRANSPORTS", bold=True, size=14)
        name_lbl.setObjectName("brandName")
        sub_lbl = _label("Auto Dialer Pro", "brandTagline")
        sub_lbl.setObjectName("brandTagline")
        col.addWidget(name_lbl)
        col.addWidget(sub_lbl)
        left.addLayout(col)
        h.addLayout(left)
        h.addStretch()

        # Right side
        right = QHBoxLayout()
        right.setSpacing(10)

        # User badge
        role_name = "Administrator" if self.user["role"] == "admin" else "Agent"
        user_lbl = QLabel(
            f'<span style="color:#1e293b;"><b>{self.user["name"]}</b></span>'
            f' &nbsp;·&nbsp; <span style="color:#64748b;">{role_name}</span>'
        )
        user_lbl.setObjectName("headerUser")
        right.addWidget(user_lbl)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        right.addWidget(div)

        wa_btn = _btn("Support", "wa")
        import webbrowser as _wb
        wa_btn.setToolTip(WA_NUMBER)
        wa_btn.clicked.connect(lambda: _wb.open(WHATSAPP_URL))
        right.addWidget(wa_btn)

        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.VLine)
        right.addWidget(div2)

        self._theme_btn = _btn("Dark mode", "ghost")
        self._theme_btn.setFixedWidth(92)
        self._theme_btn.clicked.connect(self._toggle_theme)
        if self.cfg.get("theme", DEFAULT_THEME) == "light":
            self._theme_btn.setText("Dark mode")
        else:
            self._theme_btn.setText("Light mode")
        right.addWidget(self._theme_btn)

        logout_btn = _btn("Sign out", "ghost")
        logout_btn.clicked.connect(self._logout)
        right.addWidget(logout_btn)

        h.addLayout(right)

        # Central widget holds header + tabs
        central = QWidget()
        self.setCentralWidget(central)
        vlay = QVBoxLayout(central)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)
        vlay.addWidget(self._browser_host)  # 1×1 hidden browsers
        vlay.addWidget(hdr)
        self._main_vlay = vlay  # tabs will be added next

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_dialer = QWidget()
        self.tab_live   = QWidget()
        self.tab_logs   = QWidget()
        self.tab_crm    = QWidget()
        self.tab_settings = QWidget()

        self.tabs.addTab(self.tab_dialer,   "  Dialer  ")
        self.tabs.addTab(self.tab_live,     "  Live Calls  ")
        self.tabs.addTab(self.tab_logs,     "  Call Logs  ")
        self.tabs.addTab(self.tab_crm,      "  CRM  ")
        self.tabs.addTab(self.tab_settings, "  Settings  ")

        if self.user["role"] == "admin":
            self.tab_admin = QWidget()
            self.tabs.addTab(self.tab_admin, "  Administration  ")
            self._build_admin_tab()

        self._main_vlay.addWidget(self.tabs)

        self._build_dialer_tab()
        self._build_live_tab()
        self._build_logs_tab()
        self._build_crm_tab()
        self._build_settings_tab()

    def _build_status_bar(self):
        self.statusBar().showMessage("Ready")

    # ══════════════════════════════════════════════════════════════════════════
    #  DIALER TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_dialer_tab(self):
        lay = QVBoxLayout(self.tab_dialer)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 14, 16, 14)

        # File picker
        grp_file = QGroupBox("Contact list")
        flay = QHBoxLayout(grp_file)
        self.excel_input = QLineEdit(self.cfg.get("excel_path", ""))
        self.excel_input.setPlaceholderText("Choose an Excel file with phone numbers")
        self.excel_input.setReadOnly(True)
        flay.addWidget(self.excel_input)
        browse_btn = _btn("Browse…", "secondary")
        browse_btn.clicked.connect(self._browse)
        flay.addWidget(browse_btn)
        load_btn = _btn("Load contacts", "green")
        load_btn.clicked.connect(self._load_numbers)
        flay.addWidget(load_btn)
        test_btn = _btn("Sample list", "secondary")
        test_btn.setToolTip("Load the built-in test contact list")
        test_btn.clicked.connect(self._load_test_numbers)
        flay.addWidget(test_btn)
        lay.addWidget(grp_file)

        grp_settings = QGroupBox("Dialing options")
        slay = QHBoxLayout(grp_settings)
        slay.addWidget(QLabel("Lines at once:"))
        self.spin_slots = QSpinBox()
        self.spin_slots.setRange(1, 5)
        self.spin_slots.setValue(self.cfg.get("n_slots", 2))
        slay.addWidget(self.spin_slots)
        slay.addSpacing(20)
        slay.addWidget(QLabel("Call Timeout (sec):"))
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(20, 180)
        self.spin_timeout.setValue(self.cfg.get("call_timeout", 60))
        slay.addWidget(self.spin_timeout)
        slay.addSpacing(20)
        slay.addWidget(QLabel("Cooldown between calls (sec):"))
        self.spin_cooldown = QDoubleSpinBox()
        self.spin_cooldown.setRange(0, 30)
        self.spin_cooldown.setSingleStep(0.5)
        self.spin_cooldown.setValue(self.cfg.get("cooldown", 3.0))
        slay.addWidget(self.spin_cooldown)
        slay.addSpacing(20)
        slay.addWidget(QLabel("Voicemail hangup (sec):"))
        self.spin_vm_hangup = QSpinBox()
        self.spin_vm_hangup.setRange(1, 15)
        self.spin_vm_hangup.setValue(int(self.cfg.get("voicemail_hangup_sec", 3)))
        slay.addWidget(self.spin_vm_hangup)
        slay.addStretch()
        lay.addWidget(grp_settings)

        # Progress
        grp_prog = QGroupBox("Campaign progress")
        play = QVBoxLayout(grp_prog)
        stat_row = QHBoxLayout()
        self.lbl_total   = _label("Total: —",     bold=True)
        self.lbl_done    = _label("Completed: —", bold=True)
        self.lbl_rem     = _label("Remaining: —", bold=True)
        self.lbl_invalid = _label("Invalid: —",   bold=True)
        for w in (self.lbl_total, self.lbl_done, self.lbl_rem, self.lbl_invalid):
            stat_row.addWidget(w)
            stat_row.addSpacing(20)
        stat_row.addStretch()
        play.addLayout(stat_row)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        play.addWidget(self.progress)
        lay.addWidget(grp_prog)

        # Control buttons
        btn_row = QHBoxLayout()
        self.btn_start = _btn("Start dialing", "primary")
        self.btn_start.setEnabled(False)
        self.btn_start.setMinimumHeight(44)
        self.btn_start.clicked.connect(self._start_dialing)
        self.btn_stop  = _btn("Stop", "red")
        self.btn_stop.setMinimumHeight(44)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_dialing)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Activity log
        grp_log = QGroupBox("Activity")
        llay = QVBoxLayout(grp_log)
        self.console = QTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(140)
        llay.addWidget(self.console)
        lay.addWidget(grp_log, stretch=1)

    # ══════════════════════════════════════════════════════════════════════════
    #  LIVE CALLS TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_live_tab(self):
        lay = QVBoxLayout(self.tab_live)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 14, 16, 14)

        info = _label(
            "Your calls run through Google Voice in the background. "
            "Each line shows live status. When someone answers, the card highlights "
            "and you can talk, then choose Next number or End call.",
            "muted"
        )
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addWidget(_hline())

        # Slot cards grid
        self._cards_widget = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_widget)
        self._cards_layout.setSpacing(12)
        self._rebuild_slot_cards(self.cfg.get("n_slots", 2))
        lay.addWidget(self._cards_widget)
        lay.addStretch()

        # Bottom controls
        lay.addWidget(_hline())
        brow = QHBoxLayout()
        btn_start2 = _btn("Start dialing", "primary")
        btn_start2.clicked.connect(self._start_dialing)
        btn_stop2  = _btn("Stop", "red")
        btn_stop2.clicked.connect(self._stop_dialing)
        brow.addWidget(btn_start2)
        brow.addWidget(btn_stop2)
        brow.addStretch()
        lay.addLayout(brow)

    def _rebuild_slot_cards(self, n: int):
        # Clear existing
        while self._cards_layout.count():
            w = self._cards_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._slot_cards: dict[int, SlotCard] = {}
        for i in range(n):
            card = SlotCard(i)
            card.setTitle(f"  Slot {i + 1} - {self._slot_label(i)}")
            card.next_clicked.connect(self._next_call)
            card.cut_clicked.connect(self._cut_call)
            self._cards_layout.addWidget(card)
            self._slot_cards[i] = card
        self._cards_layout.addStretch()

    # ══════════════════════════════════════════════════════════════════════════
    #  CALL LOGS TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_logs_tab(self):
        lay = QVBoxLayout(self.tab_logs)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 14, 16, 14)

        # Top row
        top = QHBoxLayout()
        top.addWidget(_label("Call History", bold=True, size=12))
        top.addStretch()
        for txt, fn, nm in [
            ("📤  Export", self._export_logs, "green"),
            ("🗑  Clear",   self._clear_logs,  "red"),
            ("🔄  Refresh", self._refresh_logs, ""),
        ]:
            b = _btn(txt, nm); b.clicked.connect(fn); top.addWidget(b)
        lay.addLayout(top)

        # Stat labels
        stat_row = QHBoxLayout()
        self.log_total = _label("Total: 0")
        self.log_ended = _label("Ended: 0")
        self.log_vm    = _label("Voicemail: 0")
        self.log_fail  = _label("Failed: 0")
        for w in (self.log_total, self.log_ended, self.log_vm, self.log_fail):
            stat_row.addWidget(w); stat_row.addSpacing(16)
        stat_row.addStretch()
        lay.addLayout(stat_row)

        # Filter bar
        frow = QHBoxLayout()
        frow.addWidget(QLabel("🔍 Filter:"))
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("phone, status, date…")
        self.log_search.setMaximumWidth(240)
        self.log_search.textChanged.connect(self._apply_log_filter)
        frow.addWidget(self.log_search)
        frow.addSpacing(10)
        self.log_status_combo = QComboBox()
        self.log_status_combo.addItems(
            ["All Statuses", "ENDED", "VOICEMAIL", "NO_ANSWER", "FAILED"])
        self.log_status_combo.currentTextChanged.connect(self._apply_log_filter)
        frow.addWidget(self.log_status_combo)
        frow.addStretch()
        lay.addLayout(frow)

        # Table
        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(
            ["Time", "Phone", "Status", "Duration", "Slot"])
        self.log_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.verticalHeader().setVisible(False)
        lay.addWidget(self.log_table, stretch=1)
        self._refresh_logs()

    # ══════════════════════════════════════════════════════════════════════════
    #  CRM TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_crm_tab(self):
        lay = QVBoxLayout(self.tab_crm)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 14, 16, 14)

        top = QHBoxLayout()
        top.addWidget(_label("Contacts", bold=True, size=12))
        top.addStretch()
        for txt, fn, nm in [
            ("📥  Import Excel", self._import_contacts, ""),
            ("+ Add",           self._add_contact,      "green"),
            ("🗑  Delete",       self._delete_contact,   "red"),
            ("🔄  Refresh",      self._refresh_crm,      ""),
        ]:
            b = _btn(txt, nm); b.clicked.connect(fn); top.addWidget(b)
        lay.addLayout(top)

        # Status filter
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Status:"))
        self.crm_status = QComboBox()
        self.crm_status.addItems(
            ["all", "new", "called", "interested", "not_interested", "callback"])
        self.crm_status.currentTextChanged.connect(self._refresh_crm)
        frow.addWidget(self.crm_status)
        frow.addStretch()
        lay.addLayout(frow)

        self.crm_table = QTableWidget(0, 5)
        self.crm_table.setHorizontalHeaderLabels(
            ["Phone", "Name", "Company", "Status", "Last Called"])
        self.crm_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.crm_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.crm_table.setAlternatingRowColors(True)
        self.crm_table.verticalHeader().setVisible(False)
        lay.addWidget(self.crm_table, stretch=1)
        self._refresh_crm()

    # ══════════════════════════════════════════════════════════════════════════
    #  SETTINGS TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_settings_tab(self):
        lay = QVBoxLayout(self.tab_settings)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 14, 16, 14)

        # Browser profiles
        grp_b = QGroupBox("Voice connection profiles")
        blay = QVBoxLayout(grp_b)
        blay.addWidget(QLabel(
            "Each Google Voice account keeps its own secure sign-in on this computer.\n"
            "Use Connect account to sign in once; the app remembers your session for dialing."
        ))
        open_btn = _btn("Open storage folder", "secondary")
        open_btn.clicked.connect(lambda: os.startfile(CHROME_PROFILES_DIR))
        blay.addWidget(open_btn)
        lay.addWidget(grp_b)

        # Google Voice accounts
        grp_a = QGroupBox("Google Voice accounts")
        alay = QVBoxLayout(grp_a)
        alay.addWidget(QLabel(
            "Link each Google Voice line your team uses. Passwords are stored only "
            "on this PC to automate sign-in."
        ))
        self.gv_accounts_table = QTableWidget(0, 5)
        self.gv_accounts_table.setHorizontalHeaderLabels(
            ["Priority", "Name", "Email", "Password", "Profile"])
        self.gv_accounts_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.gv_accounts_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.gv_accounts_table.setAlternatingRowColors(True)
        self.gv_accounts_table.verticalHeader().setVisible(False)
        alay.addWidget(self.gv_accounts_table)

        acct_buttons = QHBoxLayout()
        for txt, fn, nm in [
            ("Add account", self._gv_add_account, "green"),
            ("Connect account", self._gv_setup_selected, "primary"),
            ("Move up", self._gv_move_up, "secondary"),
            ("Move down", self._gv_move_down, "secondary"),
            ("Duplicate", self._gv_duplicate_selected, "secondary"),
            ("Remove", self._gv_remove_selected, "red"),
            ("Refresh", self._refresh_gv_accounts, "secondary"),
        ]:
            b = _btn(txt, nm)
            b.clicked.connect(fn)
            acct_buttons.addWidget(b)
        acct_buttons.addStretch()
        alay.addLayout(acct_buttons)
        lay.addWidget(grp_a, stretch=1)
        self._refresh_gv_accounts()

        # Appearance
        grp_t = QGroupBox("Appearance")
        tlay = QHBoxLayout(grp_t)
        dark_btn = _btn("Dark", "secondary")
        light_btn = _btn("Light", "secondary")
        dark_btn.clicked.connect(lambda: self._set_theme("dark"))
        light_btn.clicked.connect(lambda: self._set_theme("light"))
        tlay.addWidget(dark_btn)
        tlay.addWidget(light_btn)
        tlay.addWidget(QLabel("Changes apply immediately."))
        tlay.addStretch()
        lay.addWidget(grp_t)

        grp_d = QGroupBox("General")
        dlay = QHBoxLayout(grp_d)
        dlay.addWidget(QLabel("Default lines:"))
        self.settings_slots = QSpinBox()
        self.settings_slots.setRange(1, 5)
        self.settings_slots.setValue(self.cfg.get("n_slots", 2))
        dlay.addWidget(self.settings_slots)
        save_btn = _btn("Save settings", "green")
        save_btn.clicked.connect(self._save_settings)
        dlay.addWidget(save_btn)
        dlay.addStretch()
        lay.addWidget(grp_d)
        lay.addStretch()

    # ══════════════════════════════════════════════════════════════════════════
    #  ADMIN TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_admin_tab(self):
        lay = QVBoxLayout(self.tab_admin)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 14, 16, 14)

        top = QHBoxLayout()
        top.addWidget(_label("User Management", bold=True, size=12))
        top.addStretch()
        for txt, fn, nm in [
            ("+ Create User",     self._admin_create,         "green"),
            ("🔑  Reset Password", self._admin_reset_pw,       "yellow"),
            ("🚫  Toggle Active",  self._admin_toggle_active,  "orange"),
            ("🗑  Delete User",    self._admin_delete,         "red"),
            ("🔄  Refresh",        self._admin_refresh,        ""),
        ]:
            b = _btn(txt, nm); b.clicked.connect(fn); top.addWidget(b)
        lay.addLayout(top)

        self.admin_table = QTableWidget(0, 6)
        self.admin_table.setHorizontalHeaderLabels(
            ["ID", "Email", "Name", "Role", "Active", "Last Login"])
        self.admin_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.admin_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.admin_table.setAlternatingRowColors(True)
        self.admin_table.verticalHeader().setVisible(False)
        lay.addWidget(self.admin_table, stretch=1)
        self._admin_refresh()

    # ══════════════════════════════════════════════════════════════════════════
    #  GOOGLE VOICE ACCOUNTS
    # ══════════════════════════════════════════════════════════════════════════

    def _slot_account(self, slot_id: int) -> dict | None:
        if 0 <= slot_id < len(self._gv_accounts):
            return self._gv_accounts[slot_id]
        return None

    def _slot_label(self, slot_id: int) -> str:
        acct = self._slot_account(slot_id)
        if acct:
            return acct.get("name") or acct.get("email") or f"Slot {slot_id + 1}"
        return f"Slot {slot_id + 1}"

    def _selected_gv_account_index(self) -> int:
        if not hasattr(self, "gv_accounts_table"):
            return -1
        row = self.gv_accounts_table.currentRow()
        return row if 0 <= row < len(self._gv_accounts) else -1

    def _refresh_gv_accounts(self):
        self._gv_accounts = load_gv_accounts()
        if not hasattr(self, "gv_accounts_table"):
            return
        self.gv_accounts_table.setRowCount(0)
        for idx, acct in enumerate(self._gv_accounts, start=1):
            row = self.gv_accounts_table.rowCount()
            self.gv_accounts_table.insertRow(row)
            vals = [
                str(idx),
                acct.get("name", ""),
                acct.get("email", ""),
                "Saved" if acct.get("password") else "Manual",
                acct.get("profile", ""),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.gv_accounts_table.setItem(row, col, item)
        self._refresh_slot_titles()

    def _refresh_slot_titles(self):
        if not hasattr(self, "_slot_cards"):
            return
        for sid, card in self._slot_cards.items():
            card.setTitle(f"  {self._slot_label(sid)}")

    def _gv_add_account(self):
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Add Google Voice Account",
                                        "Name / label:")
        if not ok or not name.strip():
            return
        email, ok = QInputDialog.getText(self, "Add Google Voice Account",
                                         "Google Voice email:")
        if not ok or not email.strip():
            return
        password, ok = QInputDialog.getText(
            self, "Add Google Voice Account",
            "Google password (saved only in local ignored data/gv_accounts.json):",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        notes, _ = QInputDialog.getText(self, "Add Google Voice Account",
                                        "Notes (optional):")

        existing = {a.get("profile", "") for a in self._gv_accounts}
        acct = {
            "name": name.strip(),
            "email": email.strip().lower(),
            "password": password,
            "profile": make_profile_name(name, email, existing),
            "notes": notes.strip(),
        }
        self._gv_accounts.append(acct)
        save_gv_accounts(self._gv_accounts)
        self._refresh_gv_accounts()
        self._log(f"Google Voice account added: {acct['name']}")

        if not self._running:
            self._init_controllers(self.spin_slots.value())

        if QMessageBox.question(
            self, "Setup Login",
            "Open this account now so you can log in to Google Voice?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.gv_accounts_table.selectRow(len(self._gv_accounts) - 1)
            self._gv_setup_selected()

    def _gv_move_up(self):
        idx = self._selected_gv_account_index()
        if idx <= 0:
            return
        self._gv_accounts[idx - 1], self._gv_accounts[idx] = (
            self._gv_accounts[idx], self._gv_accounts[idx - 1])
        save_gv_accounts(self._gv_accounts)
        self._refresh_gv_accounts()
        self.gv_accounts_table.selectRow(idx - 1)
        if not self._running:
            self._init_controllers(self.spin_slots.value())

    def _gv_move_down(self):
        idx = self._selected_gv_account_index()
        if idx < 0 or idx >= len(self._gv_accounts) - 1:
            return
        self._gv_accounts[idx + 1], self._gv_accounts[idx] = (
            self._gv_accounts[idx], self._gv_accounts[idx + 1])
        save_gv_accounts(self._gv_accounts)
        self._refresh_gv_accounts()
        self.gv_accounts_table.selectRow(idx + 1)
        if not self._running:
            self._init_controllers(self.spin_slots.value())

    def _gv_duplicate_selected(self):
        idx = self._selected_gv_account_index()
        if idx < 0:
            QMessageBox.warning(self, "Select Account", "Select an account first.")
            return
        src = self._gv_accounts[idx]
        existing = {a.get("profile", "") for a in self._gv_accounts}
        copy = dict(src)
        copy["name"] = f"{src.get('name', 'Account')} Copy"
        copy["profile"] = make_profile_name(copy["name"], src.get("email", ""), existing)
        self._gv_accounts.insert(idx + 1, copy)
        save_gv_accounts(self._gv_accounts)
        self._refresh_gv_accounts()
        self.gv_accounts_table.selectRow(idx + 1)
        if not self._running:
            self._init_controllers(self.spin_slots.value())

    def _gv_remove_selected(self):
        idx = self._selected_gv_account_index()
        if idx < 0:
            QMessageBox.warning(self, "Select Account", "Select an account first.")
            return
        acct = self._gv_accounts[idx]
        if QMessageBox.question(
            self, "Remove Account",
            f"Remove {acct.get('name', 'this account')} from the app?\n\n"
            "The saved browser profile folder is left on disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._gv_accounts.pop(idx)
        save_gv_accounts(self._gv_accounts)
        self._refresh_gv_accounts()
        if not self._running:
            self._init_controllers(self.spin_slots.value())

    def _gv_setup_selected(self):
        idx = self._selected_gv_account_index()
        if idx < 0:
            QMessageBox.warning(self, "Select Account", "Select an account first.")
            return
        acct = self._gv_accounts[idx]
        target_dir = gv_profile_dir(acct["profile"])

        ctrl = next(
            (c for c in self._controllers
             if os.path.abspath(c.profile_dir) == os.path.abspath(target_dir)),
            None
        )
        created_temp = False
        if ctrl is None:
            ctrl = GVController(
                idx,
                target_dir,
                parent=self,
                profile_key=acct["profile"],
                login_email=acct.get("email", ""),
                login_password=acct.get("password", ""),
            )
            ctrl.login_detected.connect(self._on_slot_login)
            ctrl.log_message.connect(self._on_slot_log)
            created_temp = True
        else:
            ctrl.set_login_credentials(
                acct.get("email", ""),
                acct.get("password", ""),
            )

        acct_label = acct.get("name") or acct.get("email", "Account")

        def _save_password(pw: str) -> None:
            self._gv_accounts[idx]["password"] = pw
            save_gv_accounts(self._gv_accounts)
            acct["password"] = pw
            self._refresh_gv_accounts()
            ctrl.set_login_credentials(acct.get("email", ""), pw)

        self._show_browser_for_setup(ctrl.view)
        dlg = GVSetupDialog(
            ctrl,
            acct_label,
            target_dir,
            login_email=acct.get("email", ""),
            on_password_saved=_save_password,
            parent=self,
        )
        dlg.exec()

        if ctrl.is_session_ready() or has_session_marker(target_dir):
            write_session_marker(target_dir)

        if created_temp:
            ctrl.view.setParent(None)
            ctrl.view.deleteLater()
        else:
            self._hide_browser_after_setup(ctrl.view)

        if not self._running:
            self._init_controllers(self.spin_slots.value())
        else:
            for c in self._controllers:
                if os.path.abspath(c.profile_dir) == os.path.abspath(target_dir):
                    c.mark_logged_in()
                    c.load()

        self._refresh_slot_login_badges()
        self._log(f"Login setup checked for {acct.get('name', acct['email'])}")

        if has_session_marker(target_dir) or ctrl.is_session_ready():
            QMessageBox.information(
                self,
                "Ready to dial",
                f"{acct_label} is connected to Google Voice.\n\n"
                "You can start power dialing — no need to sign in again.",
            )
            if hasattr(self, "tabs"):
                self.tabs.setCurrentWidget(self.tab_live)

    # ══════════════════════════════════════════════════════════════════════════
    #  CONTROLLER INIT
    # ══════════════════════════════════════════════════════════════════════════

    def _init_controllers(self, n: int):
        # Remove old controllers
        for ctrl in self._controllers:
            ctrl.view.setParent(None)
            ctrl.view.deleteLater()
        self._controllers.clear()

        for i in range(n):
            acct = self._slot_account(i)
            if acct:
                profile_name = acct["profile"]
                profile_dir = gv_profile_dir(profile_name)
                login_email = acct.get("email", "")
                login_password = acct.get("password", "")
            else:
                profile_name = f"slot_{i}"
                profile_dir = os.path.join(CHROME_PROFILES_DIR, profile_name)
                login_email = ""
                login_password = ""
            ctrl = GVController(i, profile_dir, parent=self,
                                profile_key=profile_name,
                                login_email=login_email,
                                login_password=login_password)
            ctrl.state_changed.connect(self._on_slot_state)
            ctrl.login_detected.connect(self._on_slot_login)
            ctrl.log_message.connect(self._on_slot_log)
            ctrl.view.setParent(self._browser_host)
            ctrl.view.setMaximumSize(1, 1)   # hidden but alive
            self._browser_layout.addWidget(ctrl.view)
            self._controllers.append(ctrl)
            ctrl.load()
            if has_session_marker(profile_dir):
                ctrl.mark_logged_in()
            else:
                QTimer.singleShot(2000, ctrl._check_login)
        self._refresh_slot_login_badges()

    # ══════════════════════════════════════════════════════════════════════════
    #  DIALING LOGIC
    # ══════════════════════════════════════════════════════════════════════════

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "",
            "Excel Files (*.xlsx *.xls);;All Files (*)")
        if path:
            self.excel_input.setText(path)
            self.cfg["excel_path"] = path
            _save_cfg(self.cfg)

    def _load_test_numbers(self):
        """Load built-in owner test list (phones_test.xlsx in project root)."""
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "phones_test.xlsx")
        if not os.path.exists(path):
            QMessageBox.warning(
                self, "Test List Missing",
                f"Run once:\n  python scripts/prepare_test_dial.py\n\n"
                f"Expected file:\n{path}")
            return
        self.excel_input.setText(path)
        self.cfg["excel_path"] = path.replace("\\", "/")
        _save_cfg(self.cfg)
        self._load_numbers()

    def _load_numbers(self):
        path = self.excel_input.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.critical(self, "File Not Found",
                                 f"File not found:\n{path}")
            return
        try:
            df = pd.read_excel(path)
        except Exception as e:
            QMessageBox.critical(self, "Excel Error", str(e))
            return

        df.columns = df.columns.str.strip()
        phone_col = None
        for col in df.columns:
            if col.strip().lower() in ("phone", "mobile", "number",
                                        "tel", "telephone", "cell",
                                        "phone number"):
                phone_col = col; break
        if not phone_col:
            QMessageBox.critical(
                self, "Column Not Found",
                f"No phone column.\nColumns: {list(df.columns)}")
            return

        name_col = next((c for c in df.columns
                         if c.strip().lower() in ("name", "full name",
                                                   "contact name")), None)
        completed = self.db.get_completed_phones()
        valid, invalid = [], 0

        for _, row in df.iterrows():
            d10 = clean_phone(row[phone_col])
            if not d10:
                s = str(row[phone_col]).strip()
                if s.lower() not in ("nan", "none", ""):
                    invalid += 1
                continue
            phone = fmt_e164(d10)
            name  = ""
            if name_col:
                name = str(row[name_col]).strip()
                if name.lower() in ("nan", "none"):
                    name = ""
            if phone not in completed:
                valid.append((phone, name))

        if not valid:
            QMessageBox.warning(self, "No Numbers",
                                "No valid undialed numbers found.")
            return

        self._contacts    = valid
        self._contact_idx = 0
        done  = len(completed)
        total = len(valid) + done

        self.lbl_total.setText(f"Total: {total}")
        self.lbl_done.setText(f"Completed: {done}")
        self.lbl_rem.setText(f"Remaining: {len(valid)}")
        self.lbl_invalid.setText(f"Invalid: {invalid}")
        self.progress.setMaximum(total)
        self.progress.setValue(done)

        self._log(
            f"Loaded {len(valid)} contacts (completed: {done}, invalid: {invalid})")
        self.btn_start.setEnabled(True)

    def _start_dialing(self):
        if not self._contacts:
            QMessageBox.warning(self, "No Contacts", "Load numbers first.")
            return

        ok, msg = self._dialing_login_ok()
        if not ok:
            QMessageBox.warning(self, "Google Voice Not Ready", msg)
            return

        n = self.spin_slots.value()
        self.cfg.update({
            "n_slots": n,
            "call_timeout": self.spin_timeout.value(),
            "cooldown":     self.spin_cooldown.value(),
            "voicemail_hangup_sec": self.spin_vm_hangup.value(),
        })
        _save_cfg(self.cfg)

        # Re-init controllers if slot count changed
        if len(self._controllers) != n:
            self._init_controllers(n)
            self._rebuild_slot_cards(n)

        self._running      = True
        self._contact_idx  = 0
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.statusBar().showMessage("Dialing in progress…")
        self._log(f"Dialing started — {n} line(s) active")

        self._dial_timer.start()
        self._elapsed_timer.start()
        self._assign_pending_calls()

    def _stop_dialing(self):
        self._running = False
        self._dial_timer.stop()
        self._elapsed_timer.stop()
        for ctrl in self._controllers:
            ctrl.stop_polling()
            try:
                ctrl.hangup()
            except Exception:
                pass
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.statusBar().showMessage("Dialing stopped")
        self._log("Dialing stopped")

    def _assign_pending_calls(self):
        """Called by QTimer — assign the next number to each idle slot."""
        if not self._running:
            return
        for ctrl in self._controllers:
            if (ctrl.current_state in ("IDLE", "ENDED")
                    and self._contact_idx < len(self._contacts)):
                phone, name = self._contacts[self._contact_idx]
                self._contact_idx += 1
                self._slot_phone[ctrl.slot_id] = phone
                self._slot_start[ctrl.slot_id] = _now()
                self._update_card(ctrl.slot_id, "DIALING", phone)
                self._log(f"[Slot {ctrl.slot_id}] 📞 Dialing {phone}…")
                ctrl.dial(phone)
                timeout_ms = int(self.cfg.get("call_timeout", 60) * 1000)
                started_at = self._slot_start[ctrl.slot_id]
                QTimer.singleShot(
                    timeout_ms,
                    lambda sid=ctrl.slot_id, p=phone, st=started_at:
                    self._timeout_call(sid, p, st)
                )

        # All done?
        if self._contact_idx >= len(self._contacts):
            all_idle = all(c.current_state in ("IDLE", "ENDED", "VOICEMAIL",
                                                "NO_ANSWER", "FAILED")
                           for c in self._controllers)
            if all_idle:
                self._dial_timer.stop()
                self._elapsed_timer.stop()
                self._on_all_done()

    def _release_slot(self, slot_id: int):
        self._next_call(slot_id)

    def _cut_call(self, slot_id: int):
        """Hang up the current backend Google Voice call from our UI."""
        ctrl = self._get_ctrl(slot_id)
        phone = self._slot_phone.get(slot_id, "")
        state = ctrl.current_state if ctrl else "IDLE"
        if ctrl:
            ctrl.hangup()
            self._log(f"[Slot {slot_id}] Cut call")
        if phone:
            status = "ENDED" if state == "CONNECTED" else "NO_ANSWER"
            self.db.log_call(self.user["id"], phone, status, slot_id=slot_id)
            self._refresh_logs()
        self._slot_phone.pop(slot_id, None)
        self._slot_start.pop(slot_id, None)
        self._update_card(slot_id, "IDLE", "")

    def _next_call(self, slot_id: int):
        """Cut the current call and immediately assign the next queued number."""
        self._cut_call(slot_id)
        self._log(f"[Slot {slot_id}] Moving to next call")
        if self._running:
            QTimer.singleShot(250, self._assign_pending_calls)

    def _voicemail_hangup_and_next(self, slot_id: int) -> None:
        """Hang up voicemail and advance the power dialer queue."""
        ctrl = self._get_ctrl(slot_id)
        if ctrl and ctrl.current_state == "VOICEMAIL":
            ctrl.hangup()
        self._slot_phone.pop(slot_id, None)
        self._slot_start.pop(slot_id, None)
        self._update_card(slot_id, "IDLE", "")
        self._log(f"[Slot {slot_id}] Voicemail handled — next number")
        if self._running:
            QTimer.singleShot(300, self._assign_pending_calls)

    def _timeout_call(self, slot_id: int, phone: str, started_at: float):
        """Auto-cut an unanswered call once the configured timeout expires."""
        ctrl = self._get_ctrl(slot_id)
        if not ctrl:
            return
        if self._slot_phone.get(slot_id) != phone:
            return
        if self._slot_start.get(slot_id) != started_at:
            return
        if ctrl.current_state in ("DIALING", "RINGING"):
            self._log(f"[Slot {slot_id}] Timeout reached - cutting call")
            self._cut_call(slot_id)
            if self._running:
                QTimer.singleShot(250, self._assign_pending_calls)

    def _on_all_done(self):
        self._running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.statusBar().showMessage("Campaign complete")
        self._log("All contacts in this list have been dialed.")
        QMessageBox.information(self, "Done", "All contacts have been dialed!")

    # ── Slot state handling ───────────────────────────────────────────────────

    def _on_slot_state(self, slot_id: int, state: str):
        phone = self._slot_phone.get(slot_id, "")
        disp  = fmt_display(phone[2:]) if phone.startswith("+1") and len(phone) == 12 \
            else phone
        self._update_card(slot_id, state, phone)
        self._log(f"[Slot {slot_id}] → {state}  {disp}")

        if state == "CONNECTED":
            self.statusBar().showMessage(
                f"Live call — Line {slot_id + 1}: {disp}")
            self.tabs.setCurrentWidget(self.tab_live)
        elif state == "VOICEMAIL":
            vm_sec = int(self.cfg.get("voicemail_hangup_sec", 3))
            self._log(
                f"[Slot {slot_id}] 📭 Voicemail — auto-hangup in {vm_sec}s, then next number")
            self.db.log_call(self.user["id"], phone, "VOICEMAIL", slot_id=slot_id)
            self._refresh_logs()
            QTimer.singleShot(
                vm_sec * 1000,
                lambda sid=slot_id: self._voicemail_hangup_and_next(sid),
            )
        elif state in ("ENDED", "IDLE", "NO_ANSWER"):
            if state != "IDLE":
                self.db.log_call(self.user["id"], phone,
                                 "ENDED" if state == "ENDED" else "NO_ANSWER",
                                 slot_id=slot_id)
                self._refresh_logs()

    def _on_slot_login(self, slot_id: int):
        ctrl = self._get_ctrl(slot_id)
        if ctrl:
            ctrl.mark_logged_in()
        self._log(f"[Slot {slot_id}] Google Voice ready")
        self._update_card(slot_id, "IDLE", "")
        self._refresh_slot_login_badges()

    def _on_slot_log(self, slot_id: int, msg: str):
        self._log(f"[Slot {slot_id}] {msg}")

    def _update_card(self, slot_id: int, state: str, phone: str):
        if hasattr(self, "_slot_cards") and slot_id in self._slot_cards:
            elapsed = ""
            if slot_id in self._slot_start and state not in ("IDLE", "ENDED"):
                s = int(_now() - self._slot_start[slot_id])
                elapsed = f"{s//60:02d}:{s%60:02d}"
            disp = fmt_display(phone[2:]) if phone.startswith("+1") and len(phone)==12 \
                else phone
            self._slot_cards[slot_id].update_state(state, disp, elapsed)

    def _tick_elapsed(self):
        for ctrl in self._controllers:
            sid = ctrl.slot_id
            if ctrl.current_state not in ("IDLE", "ENDED", "FAILED"):
                self._update_card(sid, ctrl.current_state,
                                  self._slot_phone.get(sid, ""))

    def _get_ctrl(self, slot_id: int) -> GVController | None:
        for c in self._controllers:
            if c.slot_id == slot_id:
                return c
        return None

    # ── Logs ─────────────────────────────────────────────────────────────────

    def _refresh_logs(self):
        uid = None if self.user["role"] == "admin" else self.user["id"]
        self._all_logs = self.db.get_call_records(user_id=uid)
        self._apply_log_filter()

    def _apply_log_filter(self):
        q  = self.log_search.text().strip().lower() if hasattr(self, "log_search") else ""
        sf = self.log_status_combo.currentText() if hasattr(self, "log_status_combo") else "All Statuses"
        filtered = []
        for r in self._all_logs:
            st = r.get("status", "")
            if sf != "All Statuses" and st != sf:
                continue
            if q and q not in r.get("phone", "").lower() \
               and q not in st.lower() \
               and q not in r.get("timestamp", "").lower():
                continue
            filtered.append(r)

        ended = vm = fail = 0
        for r in self._all_logs:
            st = r.get("status", "")
            if st == "ENDED":       ended += 1
            elif st == "VOICEMAIL": vm    += 1
            elif st == "FAILED":    fail  += 1
        self.log_total.setText(f"Total: {len(self._all_logs)}")
        self.log_ended.setText(f"Ended: {ended}")
        self.log_vm.setText(f"Voicemail: {vm}")
        self.log_fail.setText(f"Failed: {fail}")

        self.log_table.setRowCount(0)
        STATUS_COLORS_DARK = {
            "ENDED":     "#00e676",
            "VOICEMAIL": "#ff6b35",
            "NO_ANSWER": "#8b949e",
            "FAILED":    "#ff4444",
        }
        for r in reversed(filtered):
            row = self.log_table.rowCount()
            self.log_table.insertRow(row)
            st  = r.get("status", "")
            dur = r.get("duration_s", 0) or 0
            vals = [r.get("timestamp",""), r.get("phone",""),
                    st, f"{dur:.0f}s", f"S{r.get('slot_id',0)}"]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if st in STATUS_COLORS_DARK:
                    item.setForeground(QColor(STATUS_COLORS_DARK[st]))
                self.log_table.setItem(row, col, item)

    def _export_logs(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs",
            f"IndusTransports_CallLog_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path or not self._all_logs:
            return
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
            wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Call History"
            headers = ["Time", "Phone", "Status", "Duration (s)", "Slot"]
            ws.append(headers)
            hdr_fill = PatternFill("solid", fgColor="1A7F37")
            hdr_font = Font(bold=True, color="FFFFFF")
            for c in range(1, len(headers)+1):
                ws.cell(1, c).fill = hdr_fill
                ws.cell(1, c).font = hdr_font
            fill_map = {
                "ENDED":     PatternFill("solid", fgColor="0A2010"),
                "VOICEMAIL": PatternFill("solid", fgColor="1A0F00"),
                "NO_ANSWER": PatternFill("solid", fgColor="111820"),
                "FAILED":    PatternFill("solid", fgColor="1A0000"),
            }
            for r in self._all_logs:
                ws.append([r.get("timestamp",""), r.get("phone",""),
                           r.get("status",""), r.get("duration_s",0),
                           r.get("slot_id",0)])
                st = r.get("status","")
                if st in fill_map:
                    for c in range(1, len(headers)+1):
                        ws.cell(ws.max_row, c).fill = fill_map[st]
            wb.save(path)
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _clear_logs(self):
        if QMessageBox.question(
                self, "Clear Logs", "Delete ALL call logs?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            try:
                with self.db._conn() as c:
                    c.execute("DELETE FROM call_records")
                from src.paths import CALL_LOG_CSV
                if os.path.exists(CALL_LOG_CSV):
                    os.remove(CALL_LOG_CSV)
            except Exception:
                pass
            self._all_logs = []
            self._apply_log_filter()
            self._log("🗑 Logs cleared")

    # ── CRM ───────────────────────────────────────────────────────────────────

    def _refresh_crm(self):
        if not hasattr(self, "crm_table"):
            return
        sf = self.crm_status.currentText() if hasattr(self, "crm_status") else "all"
        rows = self.db.get_contacts(sf)
        self.crm_table.setRowCount(0)
        for r in rows:
            row = self.crm_table.rowCount()
            self.crm_table.insertRow(row)
            for col, key in enumerate(("phone","name","company","status","last_called")):
                val = str(r.get(key,"") or "—")
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.crm_table.setItem(row, col, item)

    def _import_contacts(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Contacts", "",
            "Excel Files (*.xlsx *.xls);;All Files (*)")
        if not path:
            return
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip().str.lower()
            rows = []
            for _, r in df.iterrows():
                for col in ("phone","mobile","number","tel"):
                    if col in df.columns:
                        d10 = clean_phone(r[col])
                        if d10:
                            rows.append({
                                "phone":   fmt_e164(d10),
                                "name":    str(r.get("name","")).strip(),
                                "company": str(r.get("company","")).strip(),
                                "email":   str(r.get("email","")).strip(),
                            })
                            break
            added, skipped = self.db.import_contacts_from_list(rows)
            QMessageBox.information(
                self, "Import Done",
                f"Added: {added}  |  Skipped: {skipped}")
            self._refresh_crm()
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _add_contact(self):
        from PyQt6.QtWidgets import QInputDialog
        phone, ok = QInputDialog.getText(self, "Add Contact", "Phone Number:")
        if not ok or not phone:
            return
        d10 = clean_phone(phone)
        if not d10:
            QMessageBox.warning(self, "Invalid", "Not a valid US phone number.")
            return
        name, _ = QInputDialog.getText(self, "Add Contact", "Name (optional):")
        self.db.upsert_contact(fmt_e164(d10), name=name.strip())
        self._refresh_crm()

    def _delete_contact(self):
        row = self.crm_table.currentRow()
        if row < 0:
            return
        phone = self.crm_table.item(row, 0).text()
        if QMessageBox.question(
                self, "Delete", f"Delete {phone}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_contact(phone)
            self._refresh_crm()

    # ── Admin ─────────────────────────────────────────────────────────────────

    def _admin_refresh(self):
        if not hasattr(self, "admin_table"):
            return
        self.admin_table.setRowCount(0)
        for u in self.db.get_all_users():
            row = self.admin_table.rowCount()
            self.admin_table.insertRow(row)
            vals = [str(u["id"]), u["email"], u["name"], u["role"],
                    "✓" if u["is_active"] else "✗",
                    u.get("last_login","—") or "—"]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if u["role"] == "admin":
                    item.setForeground(QColor("#ffd166"))
                elif not u["is_active"]:
                    item.setForeground(QColor("#8b949e"))
                self.admin_table.setItem(row, col, item)

    def _admin_create(self):
        dlg = CreateUserDialog(self.db, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._admin_refresh()

    def _admin_reset_pw(self):
        row = self.admin_table.currentRow()
        if row < 0:
            return
        uid   = int(self.admin_table.item(row, 0).text())
        email = self.admin_table.item(row, 1).text()
        from PyQt6.QtWidgets import QInputDialog
        pw, ok = QInputDialog.getText(self, "Reset Password",
                                      f"New password for {email}:",
                                      QLineEdit.EchoMode.Password)
        if ok and pw:
            if len(pw) < 8:
                QMessageBox.warning(self,"Error","Min 8 characters.")
                return
            self.db.reset_password(uid, pw)
            QMessageBox.information(self, "Done", f"Password reset for {email}.")

    def _admin_toggle_active(self):
        row = self.admin_table.currentRow()
        if row < 0:
            return
        uid    = int(self.admin_table.item(row, 0).text())
        active = self.admin_table.item(row, 4).text() == "✓"
        if uid == self.user["id"]:
            QMessageBox.warning(self, "Error", "Cannot deactivate yourself.")
            return
        self.db.set_user_active(uid, not active)
        self._admin_refresh()

    def _admin_delete(self):
        row = self.admin_table.currentRow()
        if row < 0:
            return
        uid   = int(self.admin_table.item(row, 0).text())
        email = self.admin_table.item(row, 1).text()
        if uid == self.user["id"]:
            QMessageBox.warning(self, "Error", "Cannot delete yourself.")
            return
        if QMessageBox.question(
                self, "Delete User", f"Delete {email}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_user(uid)
            self._admin_refresh()

    # ── Theme / settings ──────────────────────────────────────────────────────

    def _toggle_theme(self):
        current = self.cfg.get("theme", "dark")
        self._set_theme("light" if current == "dark" else "dark")

    def _set_theme(self, name: str):
        self.cfg["theme"] = name
        _save_cfg(self.cfg)
        QApplication.instance().setStyleSheet(
            DARK_QSS if name == "dark" else LIGHT_QSS)
        self._theme_btn.setText(
            "Light mode" if name == "dark" else "Dark mode")

    def _save_settings(self):
        self.cfg["n_slots"] = self.settings_slots.value()
        _save_cfg(self.cfg)
        QMessageBox.information(self, "Saved", "Settings saved.")

    # ── Utility ───────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        if hasattr(self, "console"):
            ts = datetime.now().strftime("%H:%M:%S")
            self.console.append(f"[{ts}]  {msg}")

    def _logout(self):
        if self._running:
            if QMessageBox.question(
                    self, "Logout", "Dialer is running. Stop and logout?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
            self._stop_dialing()
        self.close()
        self._app_ref.show_login()

    def set_app_ref(self, app: "DialerApp"):
        self._app_ref = app


# ══════════════════════════════════════════════════════════════════════════════
#  ROOT CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════

class DialerApp:
    def __init__(self):
        self.db  = CRMDatabase()
        self.cfg = _load_cfg()
        self._main_win: MainWindow | None = None
        self._stack = QStackedWidget()
        self._stack.setWindowTitle(APP_NAME)
        self._stack.setWindowIcon(_icon())
        self._stack.resize(1000, 680)

        theme = self.cfg.get("theme", DEFAULT_THEME)
        QApplication.instance().setStyleSheet(
            DARK_QSS if theme == "dark" else LIGHT_QSS)

        if self.db.needs_admin_setup():
            self._show_admin_setup()
        else:
            self._show_login()

        self._stack.show()

    def _show_admin_setup(self):
        page = AdminSetupPage(self.db)
        page.done.connect(self._show_login)
        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)

    def _show_login(self):
        page = LoginPage(self.db)
        page.login_success.connect(self._on_login)
        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)

    def _on_login(self, user: dict):
        self._stack.hide()
        win = MainWindow(self.db, user, self.cfg)
        win.set_app_ref(self)
        self._main_win = win
        win.show()

    def show_login(self):
        if self._main_win:
            self._main_win = None
        self._stack.resize(1000, 680)
        self._show_login()
        self._stack.show()


# ── Utility ───────────────────────────────────────────────────────────────────
import time as _time
def _now() -> float:
    return _time.time()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # WebEngine: disable GPU on Windows to avoid blank white login pages
    _we_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--disable-gpu" not in _we_flags:
        _we_flags = f"{_we_flags} --disable-gpu".strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _we_flags or "--disable-gpu"
    os.environ.setdefault("QT_LOGGING_RULES",
                          "*.debug=false;qt.webenginecontext*=false")

    app = QApplication(sys.argv)
    app.setApplicationName("IndusTransports AutoDialer")
    app.setOrganizationName("Indus Transports LLC")

    dialer = DialerApp()
    sys.exit(app.exec())
