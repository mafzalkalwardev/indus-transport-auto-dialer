"""Client-ready UI themes for FT Solutions Auto Dialer."""

# Human-readable call status labels (not developer jargon)
STATUS_LABELS = {
    "IDLE": "Waiting",
    "LOADING": "Connecting",
    "LOGIN_NEEDED": "Sign-in required",
    "DIALING": "Dialing",
    "RINGING": "Ringing",
    "CONNECTED": "On call",
    "VOICEMAIL": "Voicemail",
    "ENDED": "Call ended",
    "NO_ANSWER": "No answer",
    "FAILED": "Call failed",
    "RECOVERING": "Recovering line",
    "READY": "Ready",
    "SETUP REQUIRED": "Setup required",
}

# Status colors tuned for light backgrounds (readable, professional)
STATUS_COLORS = {
    "IDLE": "#64748b",
    "LOADING": "#2563eb",
    "LOGIN_NEEDED": "#b45309",
    "DIALING": "#2563eb",
    "RINGING": "#b45309",
    "CONNECTED": "#15803d",
    "VOICEMAIL": "#c2410c",
    "ENDED": "#64748b",
    "NO_ANSWER": "#64748b",
    "FAILED": "#dc2626",
    "RECOVERING": "#7c3aed",
    "READY": "#15803d",
    "SETUP REQUIRED": "#b45309",
}

DEFAULT_THEME = "light"


def status_label(state: str) -> str:
    return STATUS_LABELS.get(state, state.replace("_", " ").title())


def status_color(state: str) -> str:
    return STATUS_COLORS.get(state, "#64748b")


# ── Primary theme: clean light UI for client delivery ─────────────────────────
LIGHT_QSS = """
QMainWindow, QDialog {
    background-color: #eef1f6;
}
QWidget {
    background-color: #eef1f6;
    color: #1e293b;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
}
QWidget#appHeader {
    background-color: #ffffff;
    border-bottom: 1px solid #d8dee9;
}
QWidget#gvSetupDialog, QWidget#loginPage, QWidget#loginCard {
    background-color: #ffffff;
}
QFrame#loginCard {
    background-color: #ffffff;
    border: 1px solid #d8dee9;
    border-radius: 16px;
    padding: 8px;
}
QLabel { color: #1e293b; background: transparent; }
QLabel#brandName {
    color: #1e3a5f;
    font-size: 16pt;
    font-weight: 700;
}
QLabel#brandTagline {
    color: #64748b;
    font-size: 9.5pt;
}
QLabel#headerUser { color: #475569; font-size: 10pt; }
QLabel#muted  { color: #64748b; }
QLabel#accent { color: #1d4ed8; font-weight: 600; }
QLabel#warn   { color: #b45309; }
QLabel#danger { color: #dc2626; }
QLabel#heroTitle {
    color: #1e3a5f;
    font-size: 14pt;
    font-weight: 700;
}
QLabel#statusPill {
    background-color: #f1f5f9;
    border: 1px solid #d8dee9;
    border-radius: 8px;
    padding: 8px 14px;
    color: #475569;
}

QPushButton {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #c5cdd8;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 600;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #f8fafc;
    border-color: #94a3b8;
}
QPushButton:pressed { background-color: #e2e8f0; }
QPushButton:disabled {
    color: #94a3b8;
    background-color: #f1f5f9;
    border-color: #e2e8f0;
}

QPushButton#green, QPushButton#primary {
    background-color: #1d4ed8;
    color: #ffffff;
    border: 1px solid #1e40af;
}
QPushButton#green:hover, QPushButton#primary:hover {
    background-color: #2563eb;
    border-color: #1d4ed8;
}
QPushButton#red {
    background-color: #ffffff;
    color: #b91c1c;
    border: 1px solid #fecaca;
}
QPushButton#red:hover {
    background-color: #fef2f2;
    border-color: #f87171;
}
QPushButton#yellow, QPushButton#secondary {
    background-color: #ffffff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
}
QPushButton#yellow:hover, QPushButton#secondary:hover {
    background-color: #eff6ff;
}
QPushButton#wa {
    background-color: #f0fdf4;
    color: #166534;
    border: 1px solid #bbf7d0;
}
QPushButton#wa:hover { background-color: #dcfce7; }
QPushButton#ghost {
    background: transparent;
    border: 1px solid transparent;
    color: #64748b;
}
QPushButton#ghost:hover {
    background: #f1f5f9;
    border-color: #e2e8f0;
}

QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #c5cdd8;
    border-radius: 8px;
    padding: 9px 12px;
    selection-background-color: #bfdbfe;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #3b82f6;
}

QTableWidget {
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #d8dee9;
    border-radius: 10px;
    gridline-color: #e8ecf2;
    alternate-background-color: #f8fafc;
    selection-background-color: #dbeafe;
    selection-color: #1e293b;
}
QTableWidget::item { padding: 8px 10px; }
QHeaderView::section {
    background-color: #f8fafc;
    color: #475569;
    border: none;
    border-bottom: 1px solid #d8dee9;
    padding: 10px 12px;
    font-weight: 600;
}

QProgressBar {
    background-color: #e2e8f0;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #475569;
    min-height: 10px;
}
QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 6px;
}

QTabWidget::pane {
    border: 1px solid #d8dee9;
    border-radius: 0 0 12px 12px;
    background: #eef1f6;
    top: -1px;
}
QTabBar::tab {
    background: #e8ecf2;
    color: #64748b;
    padding: 12px 24px;
    margin-right: 2px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1d4ed8;
    border-bottom: 3px solid #2563eb;
}
QTabBar::tab:hover:!selected {
    background: #f1f5f9;
    color: #334155;
}

QGroupBox {
    border: 1px solid #d8dee9;
    border-radius: 12px;
    margin-top: 16px;
    padding: 20px 16px 16px 16px;
    background-color: #ffffff;
    font-weight: 600;
    color: #475569;
}
QGroupBox[connected="true"] {
    background-color: #f0fdf4;
    border-color: #86efac;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #1e3a5f;
}
QGroupBox#slotCard {
    background-color: #ffffff;
    border: 1px solid #d8dee9;
    border-radius: 14px;
    padding: 14px;
    margin-top: 4px;
}
QGroupBox#slotCard QPushButton {
    padding: 8px 12px;
    min-height: 34px;
}

QFrame#browserFrame {
    background-color: #ffffff;
    border: 1px solid #c5cdd8;
    border-radius: 10px;
}
QFrame#hline {
    background: #d8dee9;
    max-height: 1px;
}

QTextEdit#console {
    background-color: #f8fafc;
    color: #334155;
    border: 1px solid #d8dee9;
    border-radius: 8px;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9.5pt;
}
QStatusBar {
    background: #ffffff;
    color: #64748b;
    border-top: 1px solid #d8dee9;
}
QScrollBar:vertical {
    background: #eef1f6;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #c5cdd8;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

# Optional dark mode — subdued, not neon/terminal
DARK_QSS = """
QMainWindow, QDialog { background-color: #1a2332; }
QWidget {
    background-color: #1a2332;
    color: #e8ecf2;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QWidget#appHeader {
    background-color: #232f42;
    border-bottom: 1px solid #364357;
}
QLabel#brandName { color: #93c5fd; font-size: 16pt; font-weight: 700; }
QLabel#brandTagline { color: #94a3b8; }
QLabel#muted { color: #94a3b8; }
QLabel#accent { color: #93c5fd; }
QPushButton {
    background-color: #2a3649;
    color: #e8ecf2;
    border: 1px solid #425168;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
}
QPushButton:hover { background-color: #334155; }
QPushButton#green, QPushButton#primary {
    background-color: #2563eb;
    color: #ffffff;
    border-color: #1d4ed8;
}
QPushButton#red {
    background-color: #2a3649;
    color: #fca5a5;
    border-color: #7f1d1d;
}
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #232f42;
    color: #f1f5f9;
    border: 1px solid #425168;
    border-radius: 8px;
    padding: 9px 12px;
}
QGroupBox {
    background-color: #232f42;
    border: 1px solid #364357;
    border-radius: 12px;
    margin-top: 14px;
    padding: 16px;
    color: #94a3b8;
}
QGroupBox::title { color: #93c5fd; }
QTabWidget::pane { border: 1px solid #364357; background: #1a2332; }
QTabBar::tab {
    background: #232f42;
    color: #94a3b8;
    padding: 12px 22px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #1a2332;
    color: #93c5fd;
    border-bottom: 3px solid #3b82f6;
}
QTableWidget {
    background-color: #232f42;
    border: 1px solid #364357;
    border-radius: 10px;
    gridline-color: #364357;
    alternate-background-color: #1e293b;
}
QHeaderView::section {
    background-color: #2a3649;
    color: #94a3b8;
    border-bottom: 1px solid #364357;
    padding: 10px;
}
QTextEdit#console {
    background-color: #232f42;
    color: #cbd5e1;
    border: 1px solid #364357;
    border-radius: 8px;
}
QGroupBox#slotCard {
    background-color: #232f42;
    border: 1px solid #364357;
    border-radius: 14px;
    padding: 14px;
}
QGroupBox#slotCard QPushButton {
    padding: 8px 12px;
    min-height: 34px;
}
QGroupBox#slotCard QPushButton#red {
    background-color: #450a0a;
    color: #fecaca;
    border: 1px solid #991b1b;
}
QGroupBox#slotCard QPushButton#red:hover {
    background-color: #7f1d1d;
}
QGroupBox#slotCard QPushButton#secondary {
    background-color: #2a3649;
    color: #e2e8f0;
    border: 1px solid #475569;
}
QPushButton#ghost {
    color: #cbd5e1;
    min-width: 100px;
}
QStatusBar {
    background: #232f42;
    color: #94a3b8;
    border-top: 1px solid #364357;
}
QFrame#browserFrame {
    background: #ffffff;
    border: 1px solid #425168;
    border-radius: 10px;
}
QProgressBar { background: #2a3649; border-radius: 6px; }
QProgressBar::chunk { background: #3b82f6; border-radius: 6px; }
"""
