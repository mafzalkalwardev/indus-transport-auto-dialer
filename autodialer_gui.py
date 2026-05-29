#!/usr/bin/env python3
"""
INDUS TRANSPORTS LLC — Auto Dialer Pro
Full CRM + predictive dialer with login, admin panel, and light/dark mode.
Browser automation via Selenium DOM (no pyautogui).
"""
import os
import json
import threading
import webbrowser
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import pandas as pd

from src.paths        import (LOGO_PNG, LOGO_JPEG, CONFIG_FILE,
                               CHROME_PROFILES_DIR)
from src.crm_db       import CRMDatabase
from src.phone_utils  import clean_phone, fmt_e164, fmt_display
from src.predictive_dialer import PredictiveDialer, SlotStatus
from src.call_session import CallState

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Constants ─────────────────────────────────────────────────────────────────
WHATSAPP_URL = "https://wa.me/923079670503"
WA_NUMBER    = "+92 307 967 0503"
APP_TITLE    = "INDUS TRANSPORTS LLC — Auto Dialer Pro"

DARK_THEME  = "darkly"
LIGHT_THEME = "flatly"

DARK_PAL = dict(
    BG="#0d1117", BG2="#161b22", BG3="#1c2128", HDR="#010409",
    FG="#e6edf3", ACCENT="#00e676", ACCENT2="#58a6ff",
    WARN="#ffd166", DANGER="#ff4444", PURPLE="#c084fc",
    ORANGE="#ff6b35", MUTED="#8b949e", WA="#25D366",
    CARD="#1c2128", BORDER="#30363d",
)
LIGHT_PAL = dict(
    BG="#f6f8fa", BG2="#ffffff", BG3="#f1f3f5", HDR="#24292f",
    FG="#24292f", ACCENT="#1a7f37", ACCENT2="#0969da",
    WARN="#9a6700", DANGER="#cf222e", PURPLE="#8250df",
    ORANGE="#bc4c00", MUTED="#57606a", WA="#128C7E",
    CARD="#ffffff", BORDER="#d0d7de",
)

STATUS_COLORS = {
    SlotStatus.IDLE:      "MUTED",
    SlotStatus.LAUNCHING: "ACCENT2",
    SlotStatus.LOGIN_WAIT:"WARN",
    SlotStatus.DIALING:   "ACCENT2",
    SlotStatus.RINGING:   "WARN",
    SlotStatus.CONNECTED: "ACCENT",
    SlotStatus.VOICEMAIL: "ORANGE",
    SlotStatus.NO_ANSWER: "MUTED",
    SlotStatus.FAILED:    "DANGER",
    SlotStatus.STOPPED:   "MUTED",
}

# ── Config helpers ────────────────────────────────────────────────────────────
def _load_cfg() -> dict:
    defaults = {"theme": "dark", "n_slots": 2, "call_timeout": 60,
                "cooldown_min": 2.0, "cooldown_max": 4.0,
                "excel_path": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            for k, v in defaults.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception:
            pass
    return defaults

def _save_cfg(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  ROOT CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════

class DialerApp:
    """Manages login → main-app lifecycle on a single root window."""

    def __init__(self, root: tb.Window):
        self.root  = root
        self.root.title(APP_TITLE)
        self.root.geometry("1140x820")
        self.root.minsize(980, 720)
        self.db    = CRMDatabase()
        self.cfg   = _load_cfg()
        self._frame: tk.Widget | None = None
        self._user: dict | None = None
        self._apply_theme(self.cfg.get("theme", "dark"), boot=True)

        if self.db.needs_admin_setup():
            self._show_admin_setup()
        else:
            self._show_login()

    def _apply_theme(self, name: str, boot: bool = False) -> None:
        theme = DARK_THEME if name == "dark" else LIGHT_THEME
        if boot:
            self.root.style.theme_use(theme)
        else:
            try:
                self.root.style.theme_use(theme)
            except Exception:
                pass
        self.cfg["theme"] = name
        _save_cfg(self.cfg)
        self.pal = DARK_PAL if name == "dark" else LIGHT_PAL

    def _clear(self) -> None:
        if self._frame:
            self._frame.destroy()
            self._frame = None

    def _show_admin_setup(self) -> None:
        self._clear()
        self._frame = AdminSetupFrame(self.root, self, self.db)
        self._frame.pack(fill=BOTH, expand=True)

    def _show_login(self) -> None:
        self._clear()
        self._frame = LoginFrame(self.root, self, self.db)
        self._frame.pack(fill=BOTH, expand=True)

    def after_login(self, user: dict) -> None:
        self._user = user
        self._clear()
        self._frame = MainApp(self.root, self, self.db, user, self.cfg)
        self._frame.pack(fill=BOTH, expand=True)

    def logout(self) -> None:
        self._user = None
        self._show_login()

    def toggle_theme(self) -> None:
        new = "light" if self.cfg.get("theme") == "dark" else "dark"
        self._apply_theme(new)
        messagebox.showinfo(
            "Theme Changed",
            f"Switched to {new.title()} mode.\n"
            "Restart the app for a complete refresh.",
            parent=self.root
        )


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN FIRST-RUN SETUP
# ══════════════════════════════════════════════════════════════════════════════

class AdminSetupFrame(tk.Frame):
    def __init__(self, parent, app: DialerApp, db: CRMDatabase):
        super().__init__(parent, bg=app.pal["BG"])
        self.app = app
        self.db  = db
        p = app.pal
        self._logo = _load_logo(p)

        # Centre card
        card = tk.Frame(self, bg=p["BG2"], bd=0)
        card.place(relx=0.5, rely=0.5, anchor="center")

        if self._logo:
            tk.Label(card, image=self._logo, bg=p["BG2"]).pack(pady=(24, 8))
        tk.Label(card, text="INDUS TRANSPORTS LLC",
                 font=("Segoe UI", 16, "bold"), bg=p["BG2"], fg=p["ACCENT"]
                 ).pack()
        tk.Label(card, text="Create Administrator Account",
                 font=("Segoe UI", 11), bg=p["BG2"], fg=p["MUTED"]
                 ).pack(pady=(4, 20))

        def row(label, show=""):
            tk.Label(card, text=label, font=("Segoe UI", 10),
                     bg=p["BG2"], fg=p["FG"], anchor="w", width=18).pack(
                anchor="w", padx=32)
            e = tk.Entry(card, show=show, font=("Segoe UI", 11),
                         bg=p["BG3"], fg=p["FG"], insertbackground=p["ACCENT"],
                         bd=0, relief="flat", highlightthickness=1,
                         highlightbackground=p["BORDER"], width=30)
            e.pack(padx=32, pady=(2, 10), ipady=5)
            return e

        self.e_name  = row("Full Name")
        self.e_email = row("Email Address")
        self.e_pw    = row("Password", show="•")
        self.e_pw2   = row("Confirm Password", show="•")

        tk.Button(card, text="Create Admin Account",
                  command=self._submit,
                  font=("Segoe UI", 11, "bold"),
                  bg=p["ACCENT"], fg="#000000",
                  activebackground=p["ACCENT2"], cursor="hand2",
                  bd=0, relief="flat", padx=20, pady=10,
                  ).pack(pady=(8, 24))

    def _submit(self):
        name  = self.e_name.get().strip()
        email = self.e_email.get().strip()
        pw    = self.e_pw.get()
        pw2   = self.e_pw2.get()
        if not all([name, email, pw]):
            messagebox.showerror("Missing Fields", "All fields are required.")
            return
        if pw != pw2:
            messagebox.showerror("Password Mismatch", "Passwords do not match.")
            return
        if len(pw) < 8:
            messagebox.showerror("Weak Password", "Password must be 8+ characters.")
            return
        try:
            self.db.create_admin(email, name, pw)
            messagebox.showinfo(
                "Admin Created",
                f"Admin account created!\n\nEmail:    {email}\n\n"
                "Store these credentials securely. This dialog will not appear again."
            )
            self.app._show_login()
        except Exception as e:
            messagebox.showerror("Error", str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN SCREEN
# ══════════════════════════════════════════════════════════════════════════════

class LoginFrame(tk.Frame):
    def __init__(self, parent, app: DialerApp, db: CRMDatabase):
        super().__init__(parent, bg=app.pal["BG"])
        self.app = app
        self.db  = db
        p = app.pal
        self._logo = _load_logo(p)

        card = tk.Frame(self, bg=p["BG2"], bd=0)
        card.place(relx=0.5, rely=0.5, anchor="center")

        if self._logo:
            tk.Label(card, image=self._logo, bg=p["BG2"]).pack(pady=(28, 8))
        tk.Label(card, text="INDUS TRANSPORTS LLC",
                 font=("Segoe UI", 16, "bold"), bg=p["BG2"], fg=p["ACCENT"]
                 ).pack()
        tk.Label(card, text="Auto Dialer Pro — Sign In",
                 font=("Segoe UI", 10), bg=p["BG2"], fg=p["MUTED"]
                 ).pack(pady=(2, 20))

        def row(label, show=""):
            tk.Label(card, text=label, font=("Segoe UI", 10),
                     bg=p["BG2"], fg=p["FG"], anchor="w", width=20).pack(
                anchor="w", padx=36)
            e = tk.Entry(card, show=show, font=("Segoe UI", 12),
                         bg=p["BG3"], fg=p["FG"], insertbackground=p["ACCENT"],
                         bd=0, relief="flat", highlightthickness=1,
                         highlightbackground=p["BORDER"], width=28)
            e.pack(padx=36, pady=(2, 12), ipady=6)
            return e

        self.e_email = row("Email Address")
        self.e_pw    = row("Password", show="•")
        self.e_pw.bind("<Return>", lambda _: self._login())

        tk.Button(card, text="Sign In",
                  command=self._login,
                  font=("Segoe UI", 12, "bold"),
                  bg=p["ACCENT"], fg="#000000",
                  activebackground=p["ACCENT2"], cursor="hand2",
                  bd=0, relief="flat", padx=20, pady=10, width=20,
                  ).pack(pady=(4, 4))

        self.lbl_err = tk.Label(card, text="", font=("Segoe UI", 9),
                                bg=p["BG2"], fg=p["DANGER"])
        self.lbl_err.pack(pady=(0, 16))

        tk.Label(card,
                 text="Contact your administrator for access",
                 font=("Segoe UI", 8), bg=p["BG2"], fg=p["MUTED"]
                 ).pack(pady=(0, 24))

        # Theme toggle at bottom
        tk.Button(self, text="☀ / ☾  Toggle Theme",
                  command=app.toggle_theme,
                  font=("Segoe UI", 8), bg=p["BG"], fg=p["MUTED"],
                  bd=0, relief="flat", cursor="hand2",
                  ).place(relx=1.0, rely=1.0, anchor="se", x=-16, y=-12)

    def _login(self):
        email = self.e_email.get().strip()
        pw    = self.e_pw.get()
        user  = self.db.authenticate(email, pw)
        if user:
            self.app.after_login(user)
        else:
            self.lbl_err.config(text="Incorrect email or password.")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class MainApp(tk.Frame):
    """Full application shell — shown after successful login."""

    def __init__(self, parent, app: DialerApp, db: CRMDatabase,
                 user: dict, cfg: dict):
        super().__init__(parent, bg=app.pal["BG"])
        self.app  = app
        self.db   = db
        self.user = user
        self.cfg  = cfg
        self.p    = app.pal

        # Dialer state
        self.contacts:      list[tuple[str, str]] = []
        self.dialer:        PredictiveDialer | None = None
        self._slot_labels:  dict = {}   # slot_id → {widgets}
        self._all_logs:     list = []

        self._logo_img = _load_logo(self.p)
        self._build_header()
        self._build_tabs()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        h = tk.Frame(self, bg=self.p["HDR"], height=68)
        h.pack(fill=X)
        h.pack_propagate(False)

        left = tk.Frame(h, bg=self.p["HDR"])
        left.pack(side=LEFT, padx=16, pady=8)
        if self._logo_img:
            tk.Label(left, image=self._logo_img,
                     bg=self.p["HDR"]).pack(side=LEFT, padx=(0, 12))
        col = tk.Frame(left, bg=self.p["HDR"])
        col.pack(side=LEFT)
        tk.Label(col, text="INDUS TRANSPORTS LLC",
                 font=("Segoe UI", 14, "bold"),
                 bg=self.p["HDR"], fg=self.p["ACCENT"]).pack(anchor=W)
        tk.Label(col, text="Auto Dialer Pro  •  Google Voice",
                 font=("Segoe UI", 8),
                 bg=self.p["HDR"], fg=self.p["MUTED"]).pack(anchor=W)

        right = tk.Frame(h, bg=self.p["HDR"])
        right.pack(side=RIGHT, padx=16, pady=8)

        tk.Button(right, text="⏻  Logout",
                  command=self._logout,
                  font=("Segoe UI", 9), bg=self.p["HDR"], fg=self.p["MUTED"],
                  bd=0, relief="flat", cursor="hand2", padx=6,
                  ).pack(side=RIGHT, padx=(8, 0))

        tk.Button(right, text="☀/☾",
                  command=self.app.toggle_theme,
                  font=("Segoe UI", 9), bg=self.p["HDR"], fg=self.p["MUTED"],
                  bd=0, relief="flat", cursor="hand2",
                  ).pack(side=RIGHT, padx=4)

        tk.Frame(right, bg=self.p["BORDER"], width=1).pack(
            side=RIGHT, fill=Y, padx=8)

        tk.Button(right, text="💬  WhatsApp Support",
                  command=lambda: webbrowser.open(WHATSAPP_URL),
                  font=("Segoe UI", 9, "bold"), cursor="hand2",
                  bg="#0d2b1a", fg=self.p["WA"],
                  bd=0, relief="flat", padx=8, pady=4,
                  highlightbackground=self.p["WA"], highlightthickness=1,
                  ).pack(side=RIGHT, padx=4)
        tk.Label(right, text=WA_NUMBER,
                 font=("Segoe UI", 8), bg=self.p["HDR"], fg=self.p["WA"],
                 ).pack(side=RIGHT, padx=(0, 4))

        # User badge
        tk.Frame(right, bg=self.p["BORDER"], width=1).pack(
            side=RIGHT, fill=Y, padx=8)
        role_color = self.p["WARN"] if self.user["role"] == "admin" else self.p["ACCENT2"]
        tk.Label(right,
                 text=f"👤 {self.user['name']}  [{self.user['role'].upper()}]",
                 font=("Segoe UI", 9), bg=self.p["HDR"], fg=role_color,
                 ).pack(side=RIGHT)

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self):
        sty = ttk.Style()
        sty.configure("TNotebook",     background=self.p["BG"],  borderwidth=0)
        sty.configure("TNotebook.Tab", background=self.p["HDR"], foreground=self.p["MUTED"],
                      font=("Segoe UI", 10), padding=[14, 6])
        sty.map("TNotebook.Tab",
                background=[("selected", self.p["BG2"])],
                foreground=[("selected", self.p["ACCENT"])])

        nb = ttk.Notebook(self)
        nb.pack(fill=BOTH, expand=True, padx=8, pady=(4, 8))

        tabs = [
            ("  🚀  Dialer",       self._build_dialer_tab),
            ("  📞  Live Calls",   self._build_live_calls_tab),
            ("  📋  Call Logs",    self._build_logs_tab),
            ("  🏢  CRM",          self._build_crm_tab),
            ("  ⚙️  Settings",     self._build_settings_tab),
        ]
        if self.user["role"] == "admin":
            tabs.append(("  👑  Admin", self._build_admin_tab))

        for label, builder in tabs:
            f = tk.Frame(nb, bg=self.p["BG"])
            nb.add(f, text=label)
            builder(f)

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _lf(self, parent, text, fg=None):
        return tk.LabelFrame(parent, text=text,
                              bg=self.p["BG2"], fg=fg or self.p["ACCENT2"],
                              font=("Segoe UI", 9, "bold"), bd=1, relief="groove")

    def _btn(self, parent, text, cmd, color=None, width=None, state=NORMAL):
        color = color or self.p["ACCENT2"]
        kw = dict(text=text, command=cmd,
                  bg=self.p["BG3"], fg=color,
                  activebackground=self.p["BG2"], activeforeground=color,
                  font=("Segoe UI", 10, "bold"), bd=0, relief="flat",
                  highlightbackground=color, highlightthickness=1,
                  cursor="hand2", state=state, padx=10, pady=6)
        if width:
            kw["width"] = width
        return tk.Button(parent, **kw)

    def _log(self, msg: str):
        def _w():
            if not hasattr(self, "console"):
                return
            self.console.configure(state=NORMAL)
            ts = datetime.now().strftime("%H:%M:%S")
            self.console.insert(END, f"[{ts}]  {msg}\n")
            self.console.see(END)
            self.console.configure(state=DISABLED)
        self.after(0, _w)

    def _logout(self):
        if self.dialer and self.dialer.is_running():
            if not messagebox.askyesno(
                    "Active Dialer", "Dialer is running. Stop and logout?"):
                return
            self.dialer.stop()
        self.app.logout()

    # ══════════════════════════════════════════════════════════════════════════
    #  DIALER TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_dialer_tab(self, f: tk.Frame):
        # File picker
        fc = self._lf(f, "  📂  Phone List  (Excel .xlsx / .xls)")
        fc.pack(fill=X, padx=14, pady=(12, 6))
        fc.columnconfigure(0, weight=1)

        self.excel_var = tk.StringVar(value=self.cfg.get("excel_path", ""))
        tk.Entry(fc, textvariable=self.excel_var,
                 bg=self.p["HDR"], fg=self.p["FG"],
                 insertbackground=self.p["ACCENT"],
                 font=("Consolas", 9), bd=0, relief="flat",
                 highlightthickness=1, highlightbackground=self.p["BORDER"],
                 ).grid(row=0, column=0, sticky="ew", padx=(10, 8), pady=10, ipady=5)
        self._btn(fc, "📂 Browse", self._browse, color=self.p["ACCENT2"]
                  ).grid(row=0, column=1, padx=(0, 10), pady=10)

        # Settings
        sc = self._lf(f, "  ⚙️  Dialer Settings")
        sc.pack(fill=X, padx=14, pady=6)

        def lbl(parent, text):
            return tk.Label(parent, text=text, font=("Segoe UI", 10),
                            bg=self.p["BG2"], fg=self.p["FG"])

        lbl(sc, "Simultaneous Slots:").pack(side=LEFT, padx=(12, 4), pady=8)
        self.slots_var = tk.IntVar(value=self.cfg.get("n_slots", 2))
        tk.Spinbox(sc, from_=1, to=5, textvariable=self.slots_var, width=3,
                   font=("Segoe UI", 10), bg=self.p["HDR"], fg=self.p["ACCENT"],
                   buttonbackground=self.p["BG2"],
                   ).pack(side=LEFT, pady=8)

        lbl(sc, "   Call Timeout (sec):").pack(side=LEFT, padx=(16, 4))
        self.timeout_var = tk.IntVar(value=self.cfg.get("call_timeout", 60))
        tk.Spinbox(sc, from_=20, to=120, textvariable=self.timeout_var, width=4,
                   font=("Segoe UI", 10), bg=self.p["HDR"], fg=self.p["ACCENT"],
                   buttonbackground=self.p["BG2"],
                   ).pack(side=LEFT, pady=8)

        lbl(sc, "   Cooldown (sec):").pack(side=LEFT, padx=(16, 4))
        self.cooldown_var = tk.DoubleVar(value=self.cfg.get("cooldown_min", 2.0))
        tk.Spinbox(sc, from_=0, to=30, increment=0.5,
                   textvariable=self.cooldown_var, width=4,
                   font=("Segoe UI", 10), bg=self.p["HDR"], fg=self.p["PURPLE"],
                   buttonbackground=self.p["BG2"],
                   ).pack(side=LEFT, pady=8)

        # Progress
        pc = self._lf(f, "  📊  Progress")
        pc.pack(fill=X, padx=14, pady=6)
        sr = tk.Frame(pc, bg=self.p["BG2"])
        sr.pack(fill=X, padx=10, pady=(8, 4))

        def stat(lbl_text, col):
            tk.Label(sr, text=lbl_text, font=("Segoe UI", 10),
                     bg=self.p["BG2"], fg=self.p["MUTED"]).pack(side=LEFT)
            v = tk.Label(sr, text="—", font=("Segoe UI", 10, "bold"),
                         bg=self.p["BG2"], fg=self.p[col])
            v.pack(side=LEFT, padx=(2, 16))
            return v

        self.lbl_total   = stat("Total:", "ACCENT2")
        self.lbl_done    = stat("Completed:", "ACCENT")
        self.lbl_rem     = stat("Remaining:", "WARN")
        self.lbl_invalid = stat("Invalid:", "ORANGE")

        pb_sty = ttk.Style()
        pb_sty.configure("G.Horizontal.TProgressbar",
                         troughcolor=self.p["HDR"],
                         background=self.p["ACCENT"], thickness=12)
        self.progress = ttk.Progressbar(pc, style="G.Horizontal.TProgressbar",
                                        mode="determinate")
        self.progress.pack(fill=X, padx=10, pady=(0, 10))

        # Buttons
        bf = tk.Frame(f, bg=self.p["BG"])
        bf.pack(fill=X, padx=14, pady=(8, 4))

        self.btn_load  = self._btn(bf, "⬇  Load Numbers",  self._load_numbers, color=self.p["ACCENT2"], width=18)
        self.btn_start = self._btn(bf, "▶  Start Dialer",   self._start_power_dial, color=self.p["ACCENT"],  width=18, state=DISABLED)
        self.btn_stop  = self._btn(bf, "⏹  Stop All",       self._stop_dialer,  color=self.p["DANGER"],  width=14, state=DISABLED)

        for b in (self.btn_load, self.btn_start, self.btn_stop):
            b.pack(side=LEFT, padx=4)

        # Console
        lc = self._lf(f, "  🖥️  Activity Log")
        lc.pack(fill=BOTH, expand=True, padx=14, pady=(6, 10))
        self.console = tk.Text(lc, height=9, font=("Consolas", 9),
                               bg="#050e18" if self.p is DARK_PAL else "#f0f0f0",
                               fg=self.p["ACCENT"],
                               insertbackground=self.p["ACCENT"],
                               bd=0, relief="flat", state=DISABLED,
                               wrap="word", padx=8, pady=6)
        sc2 = tk.Scrollbar(lc, command=self.console.yview,
                           bg=self.p["BG2"])
        self.console.configure(yscrollcommand=sc2.set)
        sc2.pack(side=RIGHT, fill=Y)
        self.console.pack(fill=BOTH, expand=True, padx=(8, 0), pady=8)

    # ══════════════════════════════════════════════════════════════════════════
    #  LIVE CALLS TAB  (predictive dialer panel)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_live_calls_tab(self, f: tk.Frame):
        tk.Label(f, text="Live Call Slots",
                 font=("Segoe UI", 13, "bold"),
                 bg=self.p["BG"], fg=self.p["ACCENT2"]).pack(
            anchor=W, padx=16, pady=(12, 2))
        tk.Label(f,
                 text="When a slot shows CONNECTED, the Chrome window comes to front automatically.\n"
                      "Click  Release Slot  when the agent finishes the conversation.",
                 font=("Segoe UI", 9), bg=self.p["BG"], fg=self.p["MUTED"],
                 justify=LEFT).pack(anchor=W, padx=16, pady=(0, 10))

        # Slot cards container
        self.slots_frame = tk.Frame(f, bg=self.p["BG"])
        self.slots_frame.pack(fill=X, padx=14, pady=4)

        # Build slot cards (default 2; rebuilt on dialer start)
        self._build_slot_cards(self.cfg.get("n_slots", 2))

        # Bottom controls
        bf = tk.Frame(f, bg=self.p["BG"])
        bf.pack(fill=X, padx=14, pady=10)
        self._btn(bf, "▶  Start Power Dial", self._start_power_dial,
                  color=self.p["ACCENT"], width=22).pack(side=LEFT, padx=4)
        self._btn(bf, "⏹  Stop All",         self._stop_dialer,
                  color=self.p["DANGER"], width=14).pack(side=LEFT, padx=4)

    def _build_slot_cards(self, n: int):
        for w in self.slots_frame.winfo_children():
            w.destroy()
        self._slot_labels = {}
        for i in range(n):
            self._slot_labels[i] = self._make_slot_card(self.slots_frame, i)

    def _make_slot_card(self, parent, slot_id: int) -> dict:
        card = tk.Frame(parent, bg=self.p["CARD"],
                        highlightbackground=self.p["BORDER"],
                        highlightthickness=1, padx=12, pady=10)
        card.grid(row=slot_id // 2, column=slot_id % 2,
                  padx=8, pady=6, sticky="ew")
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        def lbl(text, font=None, fg=None):
            l = tk.Label(card, text=text,
                         font=font or ("Segoe UI", 9),
                         bg=self.p["CARD"], fg=fg or self.p["FG"])
            l.pack(anchor=W)
            return l

        title = lbl(f"Slot {slot_id + 1}",
                    font=("Segoe UI", 11, "bold"), fg=self.p["ACCENT2"])
        status_lbl = lbl("● IDLE", font=("Segoe UI", 10, "bold"),
                          fg=self.p["MUTED"])
        phone_lbl  = lbl("—", fg=self.p["MUTED"])
        dur_lbl    = lbl("Duration: —", fg=self.p["MUTED"])

        btn_release = self._btn(card, "Release Slot",
                                lambda sid=slot_id: self._release_slot(sid),
                                color=self.p["ACCENT"], width=14,
                                state=DISABLED)
        btn_release.pack(pady=(6, 0))

        return {"card": card, "status": status_lbl,
                "phone": phone_lbl, "dur": dur_lbl,
                "release_btn": btn_release}

    def _update_slot_card(self, slot_id: int, status: SlotStatus,
                           phone: str, elapsed: str):
        widgets = self._slot_labels.get(slot_id)
        if not widgets:
            return
        color_key = STATUS_COLORS.get(status, "MUTED")
        color = self.p[color_key]
        disp  = fmt_display(phone[2:]) if phone.startswith("+1") and len(phone) == 12 \
            else (phone or "—")
        widgets["status"].config(text=f"● {status.value}", fg=color)
        widgets["phone"].config(text=disp)
        widgets["dur"].config(text=f"Duration: {elapsed}")

        # Flash card background green when connected
        bg = "#0a2010" if status == SlotStatus.CONNECTED and self.p is DARK_PAL \
            else ("#ccffdd" if status == SlotStatus.CONNECTED else self.p["CARD"])
        widgets["card"].config(bg=bg)

        # Enable release button only when connected
        is_connected = status == SlotStatus.CONNECTED
        widgets["release_btn"].config(
            state=NORMAL if is_connected else DISABLED)

    # ══════════════════════════════════════════════════════════════════════════
    #  CALL LOGS TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_logs_tab(self, f: tk.Frame):
        top = tk.Frame(f, bg=self.p["BG"])
        top.pack(fill=X, padx=14, pady=(12, 4))
        tk.Label(top, text="Call History",
                 font=("Segoe UI", 13, "bold"),
                 bg=self.p["BG"], fg=self.p["ACCENT2"]).pack(side=LEFT)

        for txt, cmd, col in [
            ("📤 Export", self._export_logs, self.p["ACCENT"]),
            ("🗑 Clear",  self._clear_logs,  self.p["DANGER"]),
            ("🔄 Refresh", self._refresh_logs, self.p["ACCENT2"]),
        ]:
            self._btn(top, txt, cmd, color=col, width=12).pack(side=RIGHT, padx=3)

        # Stats
        stats = tk.Frame(f, bg=self.p["BG"])
        stats.pack(fill=X, padx=14, pady=4)
        self.log_stat_total  = tk.Label(stats, text="Total: 0",    font=("Segoe UI", 9), bg=self.p["BG"], fg=self.p["ACCENT2"])
        self.log_stat_ended  = tk.Label(stats, text="Ended: 0",    font=("Segoe UI", 9), bg=self.p["BG"], fg=self.p["ACCENT"])
        self.log_stat_vm     = tk.Label(stats, text="Voicemail: 0",font=("Segoe UI", 9), bg=self.p["BG"], fg=self.p["ORANGE"])
        self.log_stat_fail   = tk.Label(stats, text="Failed: 0",   font=("Segoe UI", 9), bg=self.p["BG"], fg=self.p["DANGER"])
        for w in (self.log_stat_total, self.log_stat_ended,
                  self.log_stat_vm, self.log_stat_fail):
            w.pack(side=LEFT, padx=10)

        # Filter bar
        sf = tk.Frame(f, bg=self.p["BG"])
        sf.pack(fill=X, padx=14, pady=(2, 4))
        tk.Label(sf, text="🔍 Filter:", font=("Segoe UI", 9),
                 bg=self.p["BG"], fg=self.p["MUTED"]).pack(side=LEFT)
        self.log_filter = tk.StringVar()
        self.log_filter.trace_add("write", lambda *_: self._apply_log_filter())
        tk.Entry(sf, textvariable=self.log_filter,
                 bg=self.p["HDR"], fg=self.p["FG"],
                 insertbackground=self.p["ACCENT"],
                 font=("Consolas", 9), bd=0, relief="flat",
                 highlightthickness=1, highlightbackground=self.p["BORDER"],
                 width=26).pack(side=LEFT, padx=(6, 16), ipady=4, pady=4)

        self.log_status_filter = tk.StringVar(value="ALL")
        for label, val, col in [
            ("All",       "ALL",       self.p["ACCENT2"]),
            ("Ended",     "ENDED",     self.p["ACCENT"]),
            ("Voicemail", "VOICEMAIL", self.p["ORANGE"]),
            ("No Answer", "NO_ANSWER", self.p["MUTED"]),
            ("Failed",    "FAILED",    self.p["DANGER"]),
        ]:
            tk.Radiobutton(sf, text=label, variable=self.log_status_filter,
                           value=val, command=self._apply_log_filter,
                           bg=self.p["BG"], fg=col,
                           selectcolor=self.p["HDR"],
                           activebackground=self.p["BG"],
                           font=("Segoe UI", 9),
                           ).pack(side=LEFT, padx=3)

        # Treeview
        tf = tk.Frame(f, bg=self.p["BG"])
        tf.pack(fill=BOTH, expand=True, padx=14, pady=(4, 12))

        ts = ttk.Style()
        ts.configure("L.Treeview",
                     background=self.p["HDR"], foreground=self.p["FG"],
                     fieldbackground=self.p["HDR"], rowheight=26,
                     font=("Segoe UI", 9))
        ts.configure("L.Treeview.Heading",
                     background=self.p["BG2"], foreground=self.p["ACCENT2"],
                     font=("Segoe UI", 9, "bold"))
        ts.map("L.Treeview", background=[("selected", "#1e3a5f")])

        sb = tk.Scrollbar(tf, bg=self.p["BG2"])
        sb.pack(side=RIGHT, fill=Y)
        self.log_tree = ttk.Treeview(tf,
                                     columns=("Time", "Phone", "Status", "Duration", "Slot"),
                                     show="headings", style="L.Treeview",
                                     yscrollcommand=sb.set)
        sb.config(command=self.log_tree.yview)
        for col, w in [("Time", 180), ("Phone", 150), ("Status", 120),
                       ("Duration", 100), ("Slot", 60)]:
            self.log_tree.heading(col, text=col)
            self.log_tree.column(col, width=w)

        self.log_tree.tag_configure("ENDED",     background="#0a2010", foreground="#00e676")
        self.log_tree.tag_configure("VOICEMAIL", background="#1a0f00", foreground="#ff6b35")
        self.log_tree.tag_configure("NO_ANSWER", background="#111820", foreground="#8b949e")
        self.log_tree.tag_configure("FAILED",    background="#1a0000", foreground="#ff4444")
        self.log_tree.pack(fill=BOTH, expand=True)
        self._refresh_logs()

    # ══════════════════════════════════════════════════════════════════════════
    #  CRM TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_crm_tab(self, f: tk.Frame):
        top = tk.Frame(f, bg=self.p["BG"])
        top.pack(fill=X, padx=14, pady=(12, 4))
        tk.Label(top, text="Contacts",
                 font=("Segoe UI", 13, "bold"),
                 bg=self.p["BG"], fg=self.p["ACCENT2"]).pack(side=LEFT)
        for txt, cmd, col in [
            ("📥 Import Excel", self._import_contacts, self.p["ACCENT2"]),
            ("+ Add Contact",   self._add_contact,     self.p["ACCENT"]),
            ("🗑 Delete",       self._delete_contact,  self.p["DANGER"]),
            ("🔄 Refresh",      self._refresh_crm,     self.p["MUTED"]),
        ]:
            self._btn(top, txt, cmd, color=col).pack(side=RIGHT, padx=3)

        # Status filter
        sf = tk.Frame(f, bg=self.p["BG"])
        sf.pack(fill=X, padx=14, pady=2)
        tk.Label(sf, text="Status:", font=("Segoe UI", 9),
                 bg=self.p["BG"], fg=self.p["MUTED"]).pack(side=LEFT)
        self.crm_status_filter = tk.StringVar(value="all")
        for label, val in [("All", "all"), ("New", "new"), ("Called", "called"),
                            ("Interested", "interested"),
                            ("Not Interested", "not_interested"),
                            ("Callback", "callback")]:
            tk.Radiobutton(sf, text=label, variable=self.crm_status_filter,
                           value=val, command=self._refresh_crm,
                           bg=self.p["BG"], fg=self.p["FG"],
                           selectcolor=self.p["HDR"],
                           activebackground=self.p["BG"],
                           font=("Segoe UI", 9),
                           ).pack(side=LEFT, padx=3)

        # Treeview
        tf = tk.Frame(f, bg=self.p["BG"])
        tf.pack(fill=BOTH, expand=True, padx=14, pady=(4, 12))
        sb = tk.Scrollbar(tf, bg=self.p["BG2"])
        sb.pack(side=RIGHT, fill=Y)
        self.crm_tree = ttk.Treeview(tf,
                                     columns=("Phone", "Name", "Company",
                                              "Status", "Last Called"),
                                     show="headings", style="L.Treeview",
                                     yscrollcommand=sb.set)
        sb.config(command=self.crm_tree.yview)
        for col, w in [("Phone", 150), ("Name", 140), ("Company", 140),
                       ("Status", 110), ("Last Called", 150)]:
            self.crm_tree.heading(col, text=col)
            self.crm_tree.column(col, width=w)
        self.crm_tree.pack(fill=BOTH, expand=True)
        self._refresh_crm()

    # ══════════════════════════════════════════════════════════════════════════
    #  SETTINGS TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_settings_tab(self, f: tk.Frame):
        tk.Label(f, text="Application Settings",
                 font=("Segoe UI", 13, "bold"),
                 bg=self.p["BG"], fg=self.p["ACCENT"]).pack(
            anchor=W, padx=16, pady=(16, 6))

        # Chrome profiles info
        pc = self._lf(f, "  🌐  Chrome Profiles  (one per dialer slot)")
        pc.pack(fill=X, padx=16, pady=8)
        tk.Label(pc,
                 text=f"Profile directory:  {CHROME_PROFILES_DIR}\n\n"
                      "Each slot uses its own Chrome profile (slot_0, slot_1, …)\n"
                      "which stores a separate Google Voice login session.\n\n"
                      "Setup: launch the dialer, let Chrome open for each slot,\n"
                      "then log into a different Google Voice account in each window.",
                 font=("Segoe UI", 9), bg=self.p["BG2"], fg=self.p["FG"],
                 justify=LEFT).pack(anchor=W, padx=12, pady=10)

        self._btn(pc, "📂 Open Profiles Folder",
                  lambda: os.startfile(CHROME_PROFILES_DIR),
                  color=self.p["ACCENT2"]).pack(anchor=W, padx=12, pady=(0, 12))

        # Theme
        tc = self._lf(f, "  🎨  Appearance")
        tc.pack(fill=X, padx=16, pady=8)
        tr = tk.Frame(tc, bg=self.p["BG2"])
        tr.pack(fill=X, padx=12, pady=10)
        tk.Label(tr, text="Theme:", font=("Segoe UI", 10),
                 bg=self.p["BG2"], fg=self.p["FG"]).pack(side=LEFT, padx=(0, 12))
        self._btn(tr, "☀ Light Mode",
                  lambda: self.app._apply_theme("light") or self.app.toggle_theme.__doc__,
                  color=self.p["WARN"]).pack(side=LEFT, padx=4)
        self._btn(tr, "☾ Dark Mode",
                  lambda: self.app._apply_theme("dark"),
                  color=self.p["ACCENT2"]).pack(side=LEFT, padx=4)
        tk.Label(tr, text="(restart to fully apply)",
                 font=("Segoe UI", 8), bg=self.p["BG2"], fg=self.p["MUTED"]
                 ).pack(side=LEFT, padx=8)

        # Dialer defaults
        dc = self._lf(f, "  ⚙️  Dialer Defaults")
        dc.pack(fill=X, padx=16, pady=8)
        dr = tk.Frame(dc, bg=self.p["BG2"])
        dr.pack(fill=X, padx=12, pady=10)
        tk.Label(dr, text="Default slots:", font=("Segoe UI", 10),
                 bg=self.p["BG2"], fg=self.p["FG"]).pack(side=LEFT)
        self.settings_slots = tk.IntVar(value=self.cfg.get("n_slots", 2))
        tk.Spinbox(dr, from_=1, to=5, textvariable=self.settings_slots, width=3,
                   font=("Segoe UI", 10), bg=self.p["HDR"], fg=self.p["ACCENT"],
                   buttonbackground=self.p["BG2"]).pack(side=LEFT, padx=(4, 16))
        self._btn(dr, "💾 Save Settings",
                  self._save_settings, color=self.p["ACCENT"], width=16
                  ).pack(side=LEFT)

    # ══════════════════════════════════════════════════════════════════════════
    #  ADMIN TAB
    # ══════════════════════════════════════════════════════════════════════════

    def _build_admin_tab(self, f: tk.Frame):
        top = tk.Frame(f, bg=self.p["BG"])
        top.pack(fill=X, padx=14, pady=(12, 4))
        tk.Label(top, text="User Management",
                 font=("Segoe UI", 13, "bold"),
                 bg=self.p["BG"], fg=self.p["WARN"]).pack(side=LEFT)
        for txt, cmd, col in [
            ("+ Create User",   self._admin_create_user,     self.p["ACCENT"]),
            ("🔑 Reset Password", self._admin_reset_pw,      self.p["WARN"]),
            ("🚫 Toggle Active", self._admin_toggle_active,  self.p["ORANGE"]),
            ("🗑 Delete User",   self._admin_delete_user,    self.p["DANGER"]),
            ("🔄 Refresh",       self._admin_refresh_users,  self.p["MUTED"]),
        ]:
            self._btn(top, txt, cmd, color=col).pack(side=RIGHT, padx=3)

        tf = tk.Frame(f, bg=self.p["BG"])
        tf.pack(fill=BOTH, expand=True, padx=14, pady=(6, 12))
        sb = tk.Scrollbar(tf, bg=self.p["BG2"])
        sb.pack(side=RIGHT, fill=Y)
        self.admin_tree = ttk.Treeview(tf,
                                       columns=("ID", "Email", "Name",
                                                "Role", "Active", "Last Login"),
                                       show="headings", style="L.Treeview",
                                       yscrollcommand=sb.set)
        sb.config(command=self.admin_tree.yview)
        for col, w in [("ID", 40), ("Email", 200), ("Name", 140),
                       ("Role", 80), ("Active", 60), ("Last Login", 160)]:
            self.admin_tree.heading(col, text=col)
            self.admin_tree.column(col, width=w)
        self.admin_tree.tag_configure("admin", foreground=self.p["WARN"])
        self.admin_tree.tag_configure("inactive", foreground=self.p["MUTED"])
        self.admin_tree.pack(fill=BOTH, expand=True)
        self._admin_refresh_users()

    # ══════════════════════════════════════════════════════════════════════════
    #  DIALER ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls"), ("All Files", "*.*")])
        if path:
            self.excel_var.set(path)
            self.cfg["excel_path"] = path
            _save_cfg(self.cfg)

    def _load_numbers(self):
        path = self.excel_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("File Not Found", f"File not found:\n{path}")
            return
        try:
            df = pd.read_excel(path)
        except Exception as e:
            messagebox.showerror("Excel Error", f"Cannot read file:\n{e}")
            return

        df.columns = df.columns.str.strip()
        phone_col = None
        for col in df.columns:
            if col.strip().lower() in (
                    "phone", "phone number", "mobile", "number", "tel",
                    "telephone", "cell"):
                phone_col = col
                break

        if phone_col is None:
            messagebox.showerror(
                "Column Not Found",
                f"No phone column.\nColumns found: {list(df.columns)}")
            return

        name_col = next((c for c in df.columns
                        if c.strip().lower() in ("name", "full name",
                                                  "contact name", "client")), None)

        valid, invalid = [], 0
        completed = self.db.get_completed_phones()
        for _, row in df.iterrows():
            raw = row[phone_col]
            d10 = clean_phone(raw)
            if not d10:
                if str(raw).strip().lower() not in ("nan", "none", ""):
                    invalid += 1
                continue
            phone = fmt_e164(d10)
            name  = str(row[name_col]).strip() if name_col else ""
            if name.lower() in ("nan", "none"):
                name = ""
            if phone not in completed:
                valid.append((phone, name))

        if not valid:
            messagebox.showerror("No Valid Numbers",
                                 "No valid undialed US numbers found.")
            return

        self.contacts = valid
        done  = len(completed)
        total = len(valid) + done
        self.lbl_total.config(text=str(total))
        self.lbl_done.config(text=str(done))
        self.lbl_rem.config(text=str(len(valid)))
        self.lbl_invalid.config(text=str(invalid))
        self.progress["value"] = (done / max(total, 1)) * 100
        self._log(f"✅ Loaded {len(valid)} remaining  |  Done: {done}  |  Invalid: {invalid}")
        self.btn_start.config(state=NORMAL)

    def _start_power_dial(self):
        if not self.contacts:
            messagebox.showwarning("No Contacts", "Load an Excel file first.")
            return

        n = self.slots_var.get()
        self._build_slot_cards(n)        # rebuild slot cards in Live Calls tab

        self.cfg.update({
            "n_slots":      n,
            "call_timeout": self.timeout_var.get(),
            "cooldown_min": self.cooldown_var.get(),
            "cooldown_max": self.cooldown_var.get() + 2,
        })
        _save_cfg(self.cfg)

        self.dialer = PredictiveDialer(
            n_slots      = n,
            call_timeout = self.cfg["call_timeout"],
            cooldown_min = self.cfg["cooldown_min"],
            cooldown_max = self.cfg["cooldown_max"],
        )

        def _log_call(slot_id, phone, name, status, duration_s):
            self.db.log_call(self.user["id"], phone, status,
                             contact_name=name, duration_s=duration_s,
                             slot_id=slot_id)
            self.after(0, self._refresh_logs)

        self.dialer._log_call_cb = _log_call

        self.dialer.on_log       = lambda m: self._log(m)
        self.dialer.on_status    = lambda sid, st, ph, el: self.after(
            0, lambda: self._update_slot_card(sid, st, ph, el))
        self.dialer.on_connected = self._on_call_connected
        self.dialer.on_all_done  = lambda: self.after(0, self._on_all_done)

        self.dialer.start(list(self.contacts))
        self.contacts = []

        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
        self._log(f"⚡ Power Dial started — {n} simultaneous slots")

    def _on_call_connected(self, slot_id: int, phone: str, browser):
        display = fmt_display(phone[2:]) if phone.startswith("+1") and len(phone) == 12 \
            else phone
        self.after(0, lambda: messagebox.showinfo(
            "📞  CALL CONNECTED",
            f"Slot {slot_id + 1} — {display}\n\n"
            "The Chrome window has been brought to front.\n"
            "Talk to the contact normally.\n\n"
            "When finished, click  Release Slot  in the Live Calls tab.",
        ))

    def _release_slot(self, slot_id: int):
        if self.dialer:
            self.dialer.release(slot_id)
            self._log(f"[Slot {slot_id}] Agent released — slot continuing…")

    def _stop_dialer(self):
        if self.dialer:
            self.dialer.stop()
        self.btn_stop.config(state=DISABLED)
        self.btn_start.config(state=NORMAL)
        self._log("⛔ Dialer stopped")

    def _on_all_done(self):
        self.btn_stop.config(state=DISABLED)
        self.btn_start.config(state=NORMAL)
        self._log("🎯 All contacts dialed!")
        messagebox.showinfo("Done", "All contacts have been dialed!")

    # ══════════════════════════════════════════════════════════════════════════
    #  LOG ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_logs(self):
        if not hasattr(self, "log_tree"):
            return
        uid = None if self.user["role"] == "admin" else self.user["id"]
        self._all_logs = self.db.get_call_records(user_id=uid)
        self._apply_log_filter()

    def _apply_log_filter(self):
        if not hasattr(self, "log_tree"):
            return
        q   = self.log_filter.get().strip().lower() if hasattr(self, "log_filter") else ""
        sf  = self.log_status_filter.get() if hasattr(self, "log_status_filter") else "ALL"
        filtered = []
        for r in self._all_logs:
            st = r.get("status", "")
            if sf != "ALL" and st != sf:
                continue
            if q and q not in r.get("phone", "").lower() \
               and q not in r.get("timestamp", "").lower() \
               and q not in st.lower():
                continue
            filtered.append(r)

        for item in self.log_tree.get_children():
            self.log_tree.delete(item)
        ended = vm = fail = 0
        for r in self._all_logs:
            st = r.get("status", "")
            if st == "ENDED":    ended += 1
            elif st == "VOICEMAIL": vm += 1
            elif st == "FAILED": fail += 1
        self.log_stat_total.config(text=f"Total: {len(self._all_logs)}")
        self.log_stat_ended.config(text=f"Ended: {ended}")
        self.log_stat_vm.config(text=f"Voicemail: {vm}")
        self.log_stat_fail.config(text=f"Failed: {fail}")

        for r in reversed(filtered):
            st  = r.get("status", "")
            dur = r.get("duration_s", 0) or 0
            self.log_tree.insert("", END,
                                 values=(r.get("timestamp", ""),
                                         r.get("phone", ""),
                                         st,
                                         f"{dur:.0f}s",
                                         f"S{r.get('slot_id', 0)}"),
                                 tags=(st,))

    def _export_logs(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            initialfile=f"IndusTransports_CallLog_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
        if not path or not self._all_logs:
            return
        try:
            import openpyxl
            wb  = openpyxl.Workbook()
            ws  = wb.active
            ws.title = "Call History"
            headers = ["Time", "Phone", "Status", "Duration (s)", "Slot"]
            ws.append(headers)
            from openpyxl.styles import Font, PatternFill
            bold = Font(bold=True, color="FFFFFF")
            fill = PatternFill("solid", fgColor="1a7f37")
            for i, _ in enumerate(headers, 1):
                c = ws.cell(1, i)
                c.font = bold
                c.fill = fill
            for r in self._all_logs:
                ws.append([r.get("timestamp", ""), r.get("phone", ""),
                           r.get("status", ""), r.get("duration_s", 0),
                           r.get("slot_id", 0)])
            wb.save(path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _clear_logs(self):
        if messagebox.askyesno("Clear Logs", "Delete ALL call logs? Cannot be undone."):
            import os as _os
            from src.paths import CALL_LOG_CSV, CRM_DB as _CRM_DB
            # Clear call_records table
            from src.crm_db import CRMDatabase as _DB
            with _DB()._conn() as c:
                c.execute("DELETE FROM call_records")
            if _os.path.exists(CALL_LOG_CSV):
                _os.remove(CALL_LOG_CSV)
            self._all_logs = []
            self._apply_log_filter()
            self._log("🗑 Logs cleared")

    # ══════════════════════════════════════════════════════════════════════════
    #  CRM ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_crm(self):
        if not hasattr(self, "crm_tree"):
            return
        sf = self.crm_status_filter.get() if hasattr(self, "crm_status_filter") else "all"
        contacts = self.db.get_contacts(sf)
        for item in self.crm_tree.get_children():
            self.crm_tree.delete(item)
        for c in contacts:
            self.crm_tree.insert("", END, values=(
                c.get("phone", ""), c.get("name", ""), c.get("company", ""),
                c.get("status", ""), c.get("last_called", "—") or "—"))

    def _import_contacts(self):
        path = filedialog.askopenfilename(
            title="Import Contacts from Excel",
            filetypes=[("Excel Files", "*.xlsx *.xls"), ("All", "*.*")])
        if not path:
            return
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.strip().str.lower()
            rows = []
            for _, row in df.iterrows():
                for col in ("phone", "mobile", "number", "tel"):
                    if col in df.columns:
                        d10 = clean_phone(row[col])
                        if d10:
                            rows.append({
                                "phone":   fmt_e164(d10),
                                "name":    str(row.get("name", "")).strip(),
                                "company": str(row.get("company", "")).strip(),
                                "email":   str(row.get("email", "")).strip(),
                            })
                            break
            added, skipped = self.db.import_contacts_from_list(rows)
            messagebox.showinfo("Import Done",
                                f"Added: {added}  |  Skipped: {skipped}")
            self._refresh_crm()
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    def _add_contact(self):
        phone = simpledialog.askstring("Add Contact", "Phone Number:")
        if not phone:
            return
        d10 = clean_phone(phone)
        if not d10:
            messagebox.showerror("Invalid", "Not a valid US phone number.")
            return
        name = simpledialog.askstring("Add Contact", "Name (optional):") or ""
        self.db.upsert_contact(fmt_e164(d10), name=name)
        self._refresh_crm()

    def _delete_contact(self):
        sel = self.crm_tree.selection()
        if not sel:
            return
        phone = self.crm_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Delete", f"Delete contact {phone}?"):
            self.db.delete_contact(str(phone))
            self._refresh_crm()

    # ══════════════════════════════════════════════════════════════════════════
    #  ADMIN ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _admin_refresh_users(self):
        if not hasattr(self, "admin_tree"):
            return
        for item in self.admin_tree.get_children():
            self.admin_tree.delete(item)
        for u in self.db.get_all_users():
            tag = "admin" if u["role"] == "admin" else \
                  ("inactive" if not u["is_active"] else "")
            self.admin_tree.insert("", END, tags=(tag,),
                                   values=(u["id"], u["email"], u["name"],
                                           u["role"],
                                           "✓" if u["is_active"] else "✗",
                                           u.get("last_login", "—") or "—"))

    def _admin_create_user(self):
        dlg = tk.Toplevel(self)
        dlg.title("Create User")
        dlg.grab_set()
        dlg.configure(bg=self.p["BG2"])
        for label, attr, show in [
            ("Full Name",  "e_name",  ""),
            ("Email",      "e_email", ""),
            ("Password",   "e_pw",    "•"),
        ]:
            tk.Label(dlg, text=label, font=("Segoe UI", 10),
                     bg=self.p["BG2"], fg=self.p["FG"]).pack(padx=24, anchor=W)
            e = tk.Entry(dlg, show=show, font=("Segoe UI", 11),
                         bg=self.p["BG3"], fg=self.p["FG"],
                         bd=0, relief="flat",
                         highlightthickness=1,
                         highlightbackground=self.p["BORDER"],
                         width=28)
            e.pack(padx=24, pady=(2, 10), ipady=5)
            setattr(dlg, attr, e)

        role_var = tk.StringVar(value="agent")
        rr = tk.Frame(dlg, bg=self.p["BG2"])
        rr.pack(padx=24, pady=(0, 8), anchor=W)
        for val in ("agent", "admin"):
            tk.Radiobutton(rr, text=val.title(), variable=role_var, value=val,
                           bg=self.p["BG2"], fg=self.p["FG"],
                           selectcolor=self.p["HDR"],
                           activebackground=self.p["BG2"],
                           font=("Segoe UI", 10),
                           ).pack(side=LEFT, padx=8)

        def _create():
            name  = dlg.e_name.get().strip()
            email = dlg.e_email.get().strip()
            pw    = dlg.e_pw.get()
            if not all([name, email, pw]):
                messagebox.showerror("Error", "All fields required.", parent=dlg)
                return
            if len(pw) < 8:
                messagebox.showerror("Error", "Password must be 8+ characters.",
                                     parent=dlg)
                return
            try:
                self.db.create_user(email, name, pw, role=role_var.get())
                dlg.destroy()
                self._admin_refresh_users()
                messagebox.showinfo("Created",
                                    f"User {email} created.\nRole: {role_var.get()}")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dlg)

        self._btn(dlg, "Create User", _create,
                  color=self.p["ACCENT"], width=20).pack(pady=(4, 20))

    def _admin_reset_pw(self):
        sel = self.admin_tree.selection()
        if not sel:
            return
        uid   = self.admin_tree.item(sel[0])["values"][0]
        email = self.admin_tree.item(sel[0])["values"][1]
        new_pw = simpledialog.askstring(
            "Reset Password", f"New password for {email}:", show="•")
        if not new_pw:
            return
        if len(new_pw) < 8:
            messagebox.showerror("Error", "Password must be 8+ characters.")
            return
        self.db.reset_password(int(uid), new_pw)
        messagebox.showinfo("Done", f"Password reset for {email}.")

    def _admin_toggle_active(self):
        sel = self.admin_tree.selection()
        if not sel:
            return
        uid    = int(self.admin_tree.item(sel[0])["values"][0])
        active = self.admin_tree.item(sel[0])["values"][4] == "✓"
        if uid == self.user["id"]:
            messagebox.showwarning("Error", "Cannot deactivate your own account.")
            return
        self.db.set_user_active(uid, not active)
        self._admin_refresh_users()

    def _admin_delete_user(self):
        sel = self.admin_tree.selection()
        if not sel:
            return
        uid   = int(self.admin_tree.item(sel[0])["values"][0])
        email = self.admin_tree.item(sel[0])["values"][1]
        if uid == self.user["id"]:
            messagebox.showwarning("Error", "Cannot delete your own account.")
            return
        if messagebox.askyesno("Delete User", f"Delete {email}? Cannot be undone."):
            self.db.delete_user(uid)
            self._admin_refresh_users()

    # ── Settings actions ──────────────────────────────────────────────────────

    def _save_settings(self):
        self.cfg["n_slots"] = self.settings_slots.get()
        _save_cfg(self.cfg)
        messagebox.showinfo("Saved", "Settings saved.")


# ── Logo loader ───────────────────────────────────────────────────────────────

def _load_logo(pal: dict):
    if not PIL_OK:
        return None
    for path in (LOGO_PNG, LOGO_JPEG):
        if os.path.exists(path):
            try:
                img = Image.open(path).convert("RGBA")
                img.thumbnail((200, 50), Image.LANCZOS)
                return ImageTk.PhotoImage(img)
            except Exception:
                pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tb.Window(themename=DARK_THEME)
    DialerApp(root)
    root.mainloop()
