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
from src.gv_controller import GVController

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Constants ─────────────────────────────────────────────────────────────────
APP_NAME     = "INDUS TRANSPORTS LLC — Auto Dialer Pro"
WHATSAPP_URL = "https://wa.me/923079670503"
WA_NUMBER    = "+92 307 967 0503"

# ── QSS stylesheets ───────────────────────────────────────────────────────────
DARK_QSS = """
QMainWindow, QDialog, QWidget#root {
    background: #0d1117;
}
QWidget {
    background: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QLabel { color: #e6edf3; background: transparent; }
QLabel#muted  { color: #8b949e; }
QLabel#accent { color: #00e676; }
QLabel#warn   { color: #ffd166; }
QLabel#danger { color: #ff4444; }

QPushButton {
    background: #161b22;
    color: #58a6ff;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
}
QPushButton:hover  { background: #1c2128; border-color: #58a6ff; }
QPushButton:pressed{ background: #0d1117; }
QPushButton:disabled{ color: #484f58; border-color: #21262d; }

QPushButton#green  { color: #00e676; border-color: #00e676; }
QPushButton#green:hover  { background: #0a2010; }
QPushButton#red    { color: #ff4444; border-color: #ff4444; }
QPushButton#red:hover    { background: #200a0a; }
QPushButton#yellow { color: #ffd166; border-color: #ffd166; }
QPushButton#yellow:hover { background: #1a1200; }
QPushButton#purple { color: #c084fc; border-color: #c084fc; }
QPushButton#orange { color: #ff6b35; border-color: #ff6b35; }
QPushButton#wa     { color: #25D366; border-color: #25D366; background: #0d2b1a; }
QPushButton#wa:hover     { background: #0f3820; }

QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #161b22;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QTextEdit:focus { border-color: #58a6ff; }

QTableWidget {
    background: #0d1117;
    color: #e6edf3;
    border: 1px solid #21262d;
    gridline-color: #21262d;
    alternate-background-color: #111820;
    selection-background-color: #1f3a5f;
    outline: none;
}
QTableWidget::item { padding: 4px 8px; }
QHeaderView::section {
    background: #161b22;
    color: #8b949e;
    border: none;
    border-bottom: 1px solid #21262d;
    padding: 6px 8px;
    font-weight: bold;
}

QProgressBar {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    text-align: center;
    color: #e6edf3;
}
QProgressBar::chunk { background: #00e676; border-radius: 3px; }

QScrollBar:vertical {
    background: #0d1117; width: 8px; border: none;
}
QScrollBar::handle:vertical {
    background: #30363d; border-radius: 4px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QTabWidget::pane  { border: 1px solid #30363d; background: #0d1117; }
QTabBar::tab {
    background: #010409; color: #8b949e;
    padding: 9px 20px; border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #00e676;
    border-bottom: 2px solid #00e676;
    background: #161b22;
}
QTabBar::tab:hover { color: #e6edf3; background: #161b22; }

QGroupBox {
    border: 1px solid #30363d;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    color: #58a6ff;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
}

QFrame#hline {
    background: #21262d;
    max-height: 1px;
}

QSplitter::handle { background: #21262d; }
"""

LIGHT_QSS = """
QMainWindow, QDialog, QWidget#root {
    background: #f6f8fa;
}
QWidget {
    background: #f6f8fa;
    color: #24292f;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QLabel { color: #24292f; background: transparent; }
QLabel#muted  { color: #57606a; }
QLabel#accent { color: #1a7f37; }

QPushButton {
    background: #ffffff;
    color: #0969da;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
}
QPushButton:hover  { background: #f3f4f6; border-color: #0969da; }
QPushButton:pressed{ background: #e6e8ea; }
QPushButton:disabled{ color: #8c959f; border-color: #d0d7de; }

QPushButton#green  { color: #1a7f37; border-color: #1a7f37; }
QPushButton#green:hover  { background: #dafbe1; }
QPushButton#red    { color: #cf222e; border-color: #cf222e; }
QPushButton#red:hover    { background: #ffeef0; }
QPushButton#yellow { color: #9a6700; border-color: #d4a72c; }
QPushButton#wa     { color: #128C7E; border-color: #128C7E; background: #e8f5e9; }

QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 5px 8px;
}
QLineEdit:focus { border-color: #0969da; }

QTableWidget {
    background: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    gridline-color: #d0d7de;
    alternate-background-color: #f6f8fa;
    selection-background-color: #ddeeff;
    outline: none;
}
QHeaderView::section {
    background: #f6f8fa;
    color: #57606a;
    border: none;
    border-bottom: 1px solid #d0d7de;
    padding: 6px 8px;
    font-weight: bold;
}

QProgressBar {
    background: #e6e8ea;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    text-align: center;
    color: #24292f;
}
QProgressBar::chunk { background: #1a7f37; border-radius: 3px; }

QTabWidget::pane { border: 1px solid #d0d7de; background: #f6f8fa; }
QTabBar::tab {
    background: #f6f8fa; color: #57606a;
    padding: 9px 20px; border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #1a7f37; border-bottom: 2px solid #1a7f37;
    background: #ffffff;
}
QGroupBox { border: 1px solid #d0d7de; border-radius: 6px;
    margin-top: 10px; padding-top: 8px; color: #0969da; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin;
    subcontrol-position: top left; padding: 0 6px; left: 10px; }
"""

# ── Config ────────────────────────────────────────────────────────────────────
def _load_cfg() -> dict:
    defaults = {"theme": "dark", "n_slots": 2, "call_timeout": 60,
                "cooldown": 3.0, "excel_path": ""}
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
    release_clicked = pyqtSignal(int)

    STATE_COLORS = {
        "IDLE":         "#8b949e",
        "LOADING":      "#58a6ff",
        "LOGIN_NEEDED": "#ffd166",
        "DIALING":      "#58a6ff",
        "RINGING":      "#ffd166",
        "CONNECTED":    "#00e676",
        "VOICEMAIL":    "#ff6b35",
        "ENDED":        "#8b949e",
        "NO_ANSWER":    "#8b949e",
        "FAILED":       "#ff4444",
    }

    def __init__(self, slot_id: int, parent=None):
        super().__init__(f"  Slot {slot_id + 1}", parent)
        self.slot_id = slot_id
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        self.lbl_status = _label("● IDLE", bold=True)
        self.lbl_status.setStyleSheet("color: #8b949e;")
        lay.addWidget(self.lbl_status)

        self.lbl_phone = _label("—", "muted")
        lay.addWidget(self.lbl_phone)

        self.lbl_dur = _label("Duration: —", "muted")
        lay.addWidget(self.lbl_dur)

        self.btn_release = _btn("Release Slot", "green")
        self.btn_release.setEnabled(False)
        self.btn_release.clicked.connect(lambda: self.release_clicked.emit(self.slot_id))
        lay.addWidget(self.btn_release)

    def update_state(self, state: str, phone: str = "", elapsed: str = ""):
        color = self.STATE_COLORS.get(state, "#8b949e")
        self.lbl_status.setText(f"● {state}")
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.lbl_phone.setText(phone or "—")
        self.lbl_dur.setText(f"Duration: {elapsed or '—'}")
        connected = state == "CONNECTED"
        self.btn_release.setEnabled(connected)

        # Flash background green when connected
        if connected:
            self.setStyleSheet("QGroupBox { background: #0a2010; border-color: #00e676; }")
        else:
            self.setStyleSheet("")


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
        self.db = db
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        px = _pixmap(72)
        if px:
            lbl = QLabel()
            lbl.setPixmap(px)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)
            lay.addSpacing(8)

        lay.addWidget(_label("INDUS TRANSPORTS LLC", bold=True, size=17,
                              parent=self))
        lay.addWidget(_label("Auto Dialer Pro  •  Sign In",
                              "muted", parent=self))
        lay.addSpacing(24)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.e_email = QLineEdit()
        self.e_email.setPlaceholderText("Email address")
        self.e_pw = QLineEdit()
        self.e_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pw.setPlaceholderText("Password")
        self.e_pw.returnPressed.connect(self._login)
        for w in (self.e_email, self.e_pw):
            w.setMinimumWidth(300)
        form.addRow("Email:",    self.e_email)
        form.addRow("Password:", self.e_pw)
        lay.addLayout(form)
        lay.addSpacing(12)

        self.lbl_err = _label("", "danger")
        lay.addWidget(self.lbl_err, alignment=Qt.AlignmentFlag.AlignCenter)

        btn = _btn("Sign In", "green")
        btn.setMinimumWidth(240)
        btn.clicked.connect(self._login)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(12)

        lay.addWidget(_label("Contact your administrator for access", "muted",
                              parent=self))

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

    def __init__(self, controller: GVController, slot_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"Google Voice Login — Slot {slot_id + 1}")
        self.setMinimumSize(900, 660)
        self.controller = controller

        lay = QVBoxLayout(self)

        info = QLabel(
            f"<b>Log in to your Google account below (Slot {slot_id + 1}).</b><br>"
            "Once logged in, the browser will be hidden. "
            "Your login is saved permanently — you won't see this again."
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        lay.addWidget(controller.view)

        btn_done = _btn("✅  I'm Logged In — Continue", "green")
        btn_done.clicked.connect(self.accept)
        lay.addWidget(btn_done)

        controller.load()


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

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_icon())
        self.resize(1200, 860)

        # ── Dialer state ──────────────────────────────────────────────────────
        self._controllers: list[GVController] = []
        self._contacts:    list[tuple[str, str]] = []
        self._contact_idx: int = 0
        self._running:     bool = False
        self._slot_start:  dict[int, float] = {}
        self._slot_phone:  dict[int, str]   = {}
        self._all_logs:    list = []

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

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = QWidget()
        hdr.setObjectName("header")
        hdr.setStyleSheet(
            "QWidget#header { background: #010409; border-bottom: 1px solid #21262d; }"
        )
        hdr.setFixedHeight(66)
        h = QHBoxLayout(hdr)
        h.setContentsMargins(16, 8, 16, 8)

        # Logo + name
        left = QHBoxLayout()
        px = _pixmap(48)
        if px:
            lbl_logo = QLabel()
            lbl_logo.setPixmap(px)
            lbl_logo.setStyleSheet("background: transparent;")
            left.addWidget(lbl_logo)
            left.addSpacing(10)
        col = QVBoxLayout()
        name_lbl = _label("INDUS TRANSPORTS LLC", bold=True, size=13)
        name_lbl.setStyleSheet("color: #00e676; background: transparent;")
        sub_lbl  = _label("Auto Dialer Pro  •  Google Voice", "muted")
        sub_lbl.setStyleSheet("background: transparent;")
        col.addWidget(name_lbl)
        col.addWidget(sub_lbl)
        left.addLayout(col)
        h.addLayout(left)
        h.addStretch()

        # Right side
        right = QHBoxLayout()
        right.setSpacing(10)

        # User badge
        role_color = "#ffd166" if self.user["role"] == "admin" else "#58a6ff"
        user_lbl = QLabel(
            f'👤 <b>{self.user["name"]}</b>  '
            f'<span style="color:{role_color};">[{self.user["role"].upper()}]</span>'
        )
        user_lbl.setStyleSheet("background: transparent; color: #e6edf3;")
        right.addWidget(user_lbl)

        # Divider
        div = QFrame(); div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("color: #21262d;")
        right.addWidget(div)

        # WhatsApp
        wa_btn = _btn(f"💬  {WA_NUMBER}", "wa")
        import webbrowser as _wb
        wa_btn.clicked.connect(lambda: _wb.open(WHATSAPP_URL))
        right.addWidget(wa_btn)

        # Divider
        div2 = QFrame(); div2.setFrameShape(QFrame.Shape.VLine)
        div2.setStyleSheet("color: #21262d;")
        right.addWidget(div2)

        # Theme toggle
        self._theme_btn = _btn("☾ Dark", "yellow")
        self._theme_btn.setFixedWidth(90)
        self._theme_btn.clicked.connect(self._toggle_theme)
        right.addWidget(self._theme_btn)

        # Logout
        logout_btn = _btn("⏻ Logout", "red")
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

        self.tabs.addTab(self.tab_dialer,   "  🚀  Dialer  ")
        self.tabs.addTab(self.tab_live,     "  📞  Live Calls  ")
        self.tabs.addTab(self.tab_logs,     "  📋  Call Logs  ")
        self.tabs.addTab(self.tab_crm,      "  🏢  CRM  ")
        self.tabs.addTab(self.tab_settings, "  ⚙️  Settings  ")

        if self.user["role"] == "admin":
            self.tab_admin = QWidget()
            self.tabs.addTab(self.tab_admin, "  👑  Admin  ")
            self._build_admin_tab()

        self._main_vlay.addWidget(self.tabs)

        self._build_dialer_tab()
        self._build_live_tab()
        self._build_logs_tab()
        self._build_crm_tab()
        self._build_settings_tab()

    def _build_status_bar(self):
        self.statusBar().setStyleSheet(
            "QStatusBar { background: #010409; color: #8b949e; "
            "border-top: 1px solid #21262d; }"
        )
        self.statusBar().showMessage("● Ready")

    # ══════════════════════════════════════════════════════════════════════════
    #  DIALER TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_dialer_tab(self):
        lay = QVBoxLayout(self.tab_dialer)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 14, 16, 14)

        # File picker
        grp_file = QGroupBox("  📂  Phone List (Excel)")
        flay = QHBoxLayout(grp_file)
        self.excel_input = QLineEdit(self.cfg.get("excel_path", ""))
        self.excel_input.setPlaceholderText("Select Excel file with phone numbers…")
        self.excel_input.setReadOnly(True)
        flay.addWidget(self.excel_input)
        browse_btn = _btn("📂  Browse")
        browse_btn.clicked.connect(self._browse)
        flay.addWidget(browse_btn)
        load_btn = _btn("⬇  Load Numbers", "green")
        load_btn.clicked.connect(self._load_numbers)
        flay.addWidget(load_btn)
        lay.addWidget(grp_file)

        # Settings row
        grp_settings = QGroupBox("  ⚙️  Call Settings")
        slay = QHBoxLayout(grp_settings)
        slay.addWidget(QLabel("Simultaneous Slots:"))
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
        slay.addStretch()
        lay.addWidget(grp_settings)

        # Progress
        grp_prog = QGroupBox("  📊  Progress")
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
        self.btn_start = _btn("▶  Start Power Dial", "green")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._start_dialing)
        self.btn_stop  = _btn("⏹  Stop All", "red")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_dialing)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Activity log
        grp_log = QGroupBox("  🖥️  Activity Log")
        llay = QVBoxLayout(grp_log)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 9))
        self.console.setStyleSheet(
            "QTextEdit { background: #050e18; color: #00e676; border: none; }")
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
            "Google Voice runs silently in the background — the agent only sees this panel.\n"
            "When a call connects, the slot card turns green. Click  Release Slot  "
            "when finished.",
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
        btn_start2 = _btn("▶  Start Power Dial", "green")
        btn_start2.clicked.connect(self._start_dialing)
        btn_stop2  = _btn("⏹  Stop All", "red")
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
            card.release_clicked.connect(self._release_slot)
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
        grp_b = QGroupBox("  🌐  Embedded Browser Profiles")
        blay = QVBoxLayout(grp_b)
        blay.addWidget(QLabel(
            f"Profile storage:  {CHROME_PROFILES_DIR}\n\n"
            "Each dialer slot uses its own profile directory (slot_0, slot_1 …)\n"
            "storing a separate Google Voice login session.\n\n"
            "On first launch a setup dialog will open for each slot so you can\n"
            "log into a different Google Voice account per slot.\n"
            "After that, profiles persist and login is automatic."
        ))
        open_btn = _btn("📂  Open Profiles Folder")
        open_btn.clicked.connect(lambda: os.startfile(CHROME_PROFILES_DIR))
        blay.addWidget(open_btn)
        lay.addWidget(grp_b)

        # Appearance
        grp_t = QGroupBox("  🎨  Theme")
        tlay = QHBoxLayout(grp_t)
        dark_btn  = _btn("☾  Dark Mode",  "")
        light_btn = _btn("☀  Light Mode", "yellow")
        dark_btn.clicked.connect(lambda: self._set_theme("dark"))
        light_btn.clicked.connect(lambda: self._set_theme("light"))
        tlay.addWidget(dark_btn); tlay.addWidget(light_btn)
        tlay.addWidget(QLabel("  (restart app to fully apply)"))
        tlay.addStretch()
        lay.addWidget(grp_t)

        # Save defaults
        grp_d = QGroupBox("  ⚙️  Defaults")
        dlay = QHBoxLayout(grp_d)
        dlay.addWidget(QLabel("Default slots:"))
        self.settings_slots = QSpinBox()
        self.settings_slots.setRange(1, 5)
        self.settings_slots.setValue(self.cfg.get("n_slots", 2))
        dlay.addWidget(self.settings_slots)
        save_btn = _btn("💾  Save", "green")
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
    #  CONTROLLER INIT
    # ══════════════════════════════════════════════════════════════════════════

    def _init_controllers(self, n: int):
        # Remove old controllers
        for ctrl in self._controllers:
            ctrl.view.setParent(None)
        self._controllers.clear()

        for i in range(n):
            profile_dir = os.path.join(CHROME_PROFILES_DIR, f"slot_{i}")
            ctrl = GVController(i, profile_dir, parent=self)
            ctrl.state_changed.connect(self._on_slot_state)
            ctrl.login_detected.connect(self._on_slot_login)
            ctrl.log_message.connect(self._on_slot_log)
            ctrl.view.setParent(self._browser_host)
            ctrl.view.setMaximumSize(1, 1)   # hidden but alive
            self._browser_layout.addWidget(ctrl.view)
            self._controllers.append(ctrl)
            ctrl.load()   # load GV; if logged in already → no user action needed

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

        self._log(f"✅ Loaded {len(valid)} numbers  |  Done: {done}  |  Invalid: {invalid}")
        self.btn_start.setEnabled(True)

    def _start_dialing(self):
        if not self._contacts:
            QMessageBox.warning(self, "No Contacts", "Load numbers first.")
            return

        n = self.spin_slots.value()
        self.cfg.update({
            "n_slots": n,
            "call_timeout": self.spin_timeout.value(),
            "cooldown":     self.spin_cooldown.value(),
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
        self.statusBar().showMessage("● Power Dialing active…")
        self._log(f"⚡ Power Dial started — {n} slots")

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
        self.statusBar().showMessage("● Stopped")
        self._log("⛔ Dialer stopped")

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
        """Agent finished — hang up and continue dialing."""
        ctrl = self._get_ctrl(slot_id)
        if ctrl:
            ctrl.hangup()
            self._log(f"[Slot {slot_id}] Agent released — continuing…")
            self.db.log_call(self.user["id"],
                             self._slot_phone.get(slot_id, ""),
                             "ENDED", slot_id=slot_id)
            self._refresh_logs()
        self._update_card(slot_id, "IDLE", "")

    def _on_all_done(self):
        self._running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.statusBar().showMessage("● All contacts dialed")
        self._log("🎯 All contacts dialed!")
        QMessageBox.information(self, "Done", "All contacts have been dialed!")

    # ── Slot state handling ───────────────────────────────────────────────────

    def _on_slot_state(self, slot_id: int, state: str):
        phone = self._slot_phone.get(slot_id, "")
        disp  = fmt_display(phone[2:]) if phone.startswith("+1") and len(phone) == 12 \
            else phone
        self._update_card(slot_id, state, phone)
        self._log(f"[Slot {slot_id}] → {state}  {disp}")

        if state == "CONNECTED":
            self.statusBar().showMessage(f"● CONNECTED  Slot {slot_id + 1}: {disp}")
            QMessageBox.information(
                self, "📞  CALL CONNECTED",
                f"Slot {slot_id + 1}  —  {disp}\n\n"
                "Google Voice is connected in the background.\n"
                "Your microphone and speakers are active now.\n\n"
                "Talk to the contact, then click  Release Slot."
            )
        elif state == "VOICEMAIL":
            self._log(f"[Slot {slot_id}] 📭 Voicemail — auto-hanging up in 2s")
            self.db.log_call(self.user["id"], phone, "VOICEMAIL", slot_id=slot_id)
            QTimer.singleShot(2000, lambda: self._get_ctrl(slot_id) and
                              self._get_ctrl(slot_id).hangup())
            self._refresh_logs()
        elif state in ("ENDED", "IDLE", "NO_ANSWER"):
            if state != "IDLE":
                self.db.log_call(self.user["id"], phone,
                                 "ENDED" if state == "ENDED" else "NO_ANSWER",
                                 slot_id=slot_id)
                self._refresh_logs()

    def _on_slot_login(self, slot_id: int):
        self._log(f"[Slot {slot_id}] ✅ Google account logged in")
        self._update_card(slot_id, "IDLE", "")

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
        self._theme_btn.setText("☀ Light" if name == "dark" else "☾ Dark")

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

        theme = self.cfg.get("theme", "dark")
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
    # Required before QApplication for WebEngine on some systems
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                          "--disable-logging --log-level=3")
    os.environ.setdefault("QT_LOGGING_RULES",
                          "*.debug=false;qt.webenginecontext*=false")

    app = QApplication(sys.argv)
    app.setApplicationName("IndusTransports AutoDialer")
    app.setOrganizationName("Indus Transports LLC")

    dialer = DialerApp()
    sys.exit(app.exec())
