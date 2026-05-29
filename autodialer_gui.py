#!/usr/bin/env python3
"""
INDUS TRANSPORTS LLC — Auto Dialer Pro
Google Voice browser automation with DOM fallback + pyautogui.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import pandas as pd
import pyautogui
import time
import random
import re
import webbrowser
from datetime import datetime
from pynput import keyboard, mouse
import csv
import os
import json
import threading

# ── Optional PIL for logo display ─────────────────────────────────
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── Optional clipboard paste (faster than char-by-char typing) ────
try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════
#  PHONE UTILS
# ══════════════════════════════════════════════════════════════════

def clean_phone(raw):
    """
    Extract 10-digit US number from many formats.
    Handles: +1XXXXXXXXXX, (XXX)XXX-XXXX, XXX.XXX.XXXX, XXXXXXXXXX
    Returns 10-digit string or None.
    """
    s = str(raw).strip()
    if not s or s.lower() in ('nan', 'none', ''):
        return None
    digits = re.sub(r'\D', '', s)
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]
    if len(digits) != 10:
        return None
    if digits[0] in ('0', '1'):      # invalid area code
        return None
    if digits[3] in ('0', '1'):      # invalid exchange code
        return None
    return digits


def fmt_e164(d10):
    return f"+1{d10}"


# ══════════════════════════════════════════════════════════════════
#  BROWSER AUTOMATION  (Selenium DOM — optional, graceful fallback)
# ══════════════════════════════════════════════════════════════════

class BrowserAutomation:
    """
    Connects to an existing Chrome session via remote-debugging.
    User must log into Google Voice manually first.
    This class never bypasses login, CAPTCHA, or 2FA.
    """

    def __init__(self):
        self.driver    = None
        self.connected = False
        self._ok       = False
        try:
            from selenium.webdriver.chrome.options import Options as _Opts
            from selenium import webdriver as _wd
            self._Opts      = _Opts
            self._webdriver = _wd
            self._ok        = True
        except ImportError:
            pass

    def connect(self, port=9222):
        if not self._ok:
            return False, "selenium not installed — run: pip install selenium"
        try:
            opts = self._Opts()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            self.driver    = self._webdriver.Chrome(options=opts)
            self.connected = True
            return True, "Connected"
        except Exception as e:
            self.driver    = None
            self.connected = False
            return False, str(e)

    def focus_window(self):
        try:
            import pygetwindow as gw
            for frag in ('Google Voice', 'voice.google.com'):
                wins = gw.getWindowsWithTitle(frag)
                if wins:
                    wins[0].activate()
                    time.sleep(0.25)
                    return True
        except Exception:
            pass
        return False

    def dial(self, number_e164):
        if not self.connected or not self.driver:
            return False
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            wait = WebDriverWait(self.driver, 3)
            inp  = None
            for sel in [
                'input[placeholder="Enter a number"]',
                'input[aria-label*="number" i]',
                'input[aria-label*="Enter" i]',
            ]:
                try:
                    inp = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                    break
                except Exception:
                    pass
            if not inp:
                return False
            inp.clear()
            inp.send_keys(number_e164)
            time.sleep(0.3)
            for sel in [
                'button[aria-label*="Call" i]',
                'button[aria-label*="Dial" i]',
                '[jsaction*="dial"]',
            ]:
                try:
                    self.driver.find_element(By.CSS_SELECTOR, sel).click()
                    return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def hangup(self):
        if not self.connected or not self.driver:
            return False
        try:
            from selenium.webdriver.common.by import By
            for sel in [
                'button[aria-label*="End call" i]',
                'button[aria-label*="Hang up" i]',
                'button[aria-label*="hangup" i]',
            ]:
                try:
                    self.driver.find_element(By.CSS_SELECTOR, sel).click()
                    return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def disconnect(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver    = None
        self.connected = False


# ══════════════════════════════════════════════════════════════════
#  CONFIG & LOGGING
# ══════════════════════════════════════════════════════════════════

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "dialer_config.json")
LOG_FILE    = os.path.join(BASE_DIR, "call_logs.csv")
LOGO_PNG    = os.path.join(BASE_DIR, "Indus_Transports_LLC__1_-removebg-preview (1).png")
LOGO_JPEG   = os.path.join(BASE_DIR, "Indus Transports LLC (1).jpeg")

WHATSAPP_URL = "https://wa.me/923079670503"
WA_NUMBER    = "+92 307 967 0503"
TYPE_DELAY   = 0.04

pyautogui.FAILSAFE = True

DEFAULT_CONFIG = {
    "number_field":      [1514, 315],
    "call_button":       [1848, 309],
    "end_call_button":   [1693, 934],
    "excel_path":        "",
    "initial_delay":     5,
    "autocut_duration":  10,
    "browser_mode":      False,
    "chrome_debug_port": 9222,
}

COMPLETED_STATUSES = {"ENDED"}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as fh:
                cfg = json.load(fh)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception as e:
        print(f"[WARN] save_config: {e}")


def log_call(number, status):
    try:
        exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if not exists:
                w.writerow(["Time", "Phone", "Status"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), number, status])
    except Exception as e:
        print(f"[WARN] log_call: {e}")


def get_completed_numbers():
    if not os.path.exists(LOG_FILE):
        return set()
    done = set()
    try:
        with open(LOG_FILE, mode='r', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                if row.get("Status") in COMPLETED_STATUSES:
                    done.add(row["Phone"])
    except Exception:
        pass
    return done


def load_call_logs():
    logs = []
    if not os.path.exists(LOG_FILE):
        return logs
    try:
        with open(LOG_FILE, mode='r', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                logs.append(row)
    except Exception:
        pass
    return logs


# ══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════

class AutoDialerApp:

    # ── palette ───────────────────────────────────────────────────
    BG      = "#0d1117"
    BG2     = "#161b22"
    BG3     = "#1c2128"
    HDR     = "#010409"
    FG      = "#e6edf3"
    ACCENT  = "#00e676"
    ACCENT2 = "#58a6ff"
    WARN    = "#ffd166"
    DANGER  = "#ff4444"
    PURPLE  = "#c084fc"
    ORANGE  = "#ff6b35"
    GREEN_WA = "#25D366"
    MUTED   = "#8b949e"

    FONT      = ("Segoe UI", 10)
    FONT_B    = ("Segoe UI", 10, "bold")
    FONT_LG   = ("Segoe UI", 13, "bold")
    FONT_XL   = ("Segoe UI", 17, "bold")
    FONT_SM   = ("Segoe UI", 9)
    FONT_MONO = ("Consolas", 9)

    def __init__(self, root):
        self.root = root
        self.root.title("INDUS TRANSPORTS LLC — Auto Dialer Pro")
        self.root.geometry("1100x800")
        self.root.minsize(960, 700)
        self.root.configure(bg=self.BG)

        self.config        = load_config()
        self.browser       = BrowserAutomation()
        self.contacts      = []
        self.current_index = 0
        self.call_active   = False
        self.running       = False
        self.listener      = None
        self.coord_target  = None
        self.mouse_listener = None
        self._all_logs     = []

        self._logo_img = self._load_logo()
        self._build_ui()
        self._load_logs_table()

    # ── logo ──────────────────────────────────────────────────────
    def _load_logo(self):
        if not PIL_AVAILABLE:
            return None
        for path in [LOGO_PNG, LOGO_JPEG]:
            if os.path.exists(path):
                try:
                    img = Image.open(path).convert("RGBA")
                    img.thumbnail((220, 52), Image.LANCZOS)
                    return ImageTk.PhotoImage(img)
                except Exception:
                    pass
        return None

    # ── helpers ───────────────────────────────────────────────────
    def _lf(self, parent, text, fg=None):
        return tk.LabelFrame(
            parent, text=text,
            bg=self.BG2, fg=fg or self.ACCENT2,
            font=("Segoe UI", 9, "bold"),
            bd=1, relief="groove",
        )

    def _btn(self, parent, text, command, color=None, width=None, state=NORMAL):
        color = color or self.ACCENT2
        kw = dict(
            text=text, command=command,
            bg=self.BG3, fg=color,
            activebackground="#1c3040", activeforeground=color,
            font=self.FONT_B, bd=0, relief="flat",
            highlightbackground=color, highlightthickness=1,
            cursor="hand2", state=state, padx=12, pady=6,
        )
        if width:
            kw["width"] = width
        return tk.Button(parent, **kw)

    def _label(self, parent, text, font=None, fg=None, bg=None):
        return tk.Label(parent,
                        text=text,
                        font=font or self.FONT,
                        fg=fg or self.FG,
                        bg=bg or self.BG2)

    # ══════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._build_header()
        self._build_tabs()

    # ── header ────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self.root, bg=self.HDR, height=70)
        hdr.pack(fill=X)
        hdr.pack_propagate(False)

        # left: logo + company name
        left = tk.Frame(hdr, bg=self.HDR)
        left.pack(side=LEFT, padx=18, pady=8)

        if self._logo_img:
            tk.Label(left, image=self._logo_img, bg=self.HDR,
                     cursor="arrow").pack(side=LEFT, padx=(0, 14))

        title_col = tk.Frame(left, bg=self.HDR)
        title_col.pack(side=LEFT)
        tk.Label(title_col, text="INDUS TRANSPORTS LLC",
                 font=("Segoe UI", 15, "bold"),
                 bg=self.HDR, fg=self.ACCENT).pack(anchor=W)
        tk.Label(title_col, text="Auto Dialer Pro  •  Google Voice Edition",
                 font=("Segoe UI", 9),
                 bg=self.HDR, fg=self.MUTED).pack(anchor=W)

        # right: status + whatsapp
        right = tk.Frame(hdr, bg=self.HDR)
        right.pack(side=RIGHT, padx=18, pady=8)

        self.status_badge = tk.Label(right, text="● IDLE",
                                     font=("Segoe UI", 10, "bold"),
                                     bg=self.HDR, fg=self.MUTED)
        self.status_badge.pack(side=RIGHT, padx=(16, 0))

        tk.Frame(right, bg=self.MUTED, width=1).pack(side=RIGHT, fill=Y, padx=12)

        wa_col = tk.Frame(right, bg=self.HDR)
        wa_col.pack(side=RIGHT)
        tk.Button(wa_col,
                  text="💬  WhatsApp Help & Support",
                  command=lambda: webbrowser.open(WHATSAPP_URL),
                  bg="#0d2b1a", fg=self.GREEN_WA,
                  activebackground="#1a3d25", activeforeground=self.GREEN_WA,
                  font=("Segoe UI", 9, "bold"),
                  bd=0, relief="flat",
                  highlightbackground=self.GREEN_WA, highlightthickness=1,
                  cursor="hand2", padx=10, pady=4,
                  ).pack(anchor=E)
        tk.Label(wa_col, text=WA_NUMBER,
                 font=("Segoe UI", 8),
                 bg=self.HDR, fg=self.GREEN_WA).pack(anchor=E, pady=(2, 0))

    # ── tabs ──────────────────────────────────────────────────────
    def _build_tabs(self):
        sty = ttk.Style()
        sty.theme_use("clam")
        sty.configure("TNotebook",     background=self.BG,  borderwidth=0)
        sty.configure("TNotebook.Tab", background=self.HDR, foreground=self.MUTED,
                      font=("Segoe UI", 10), padding=[16, 7])
        sty.map("TNotebook.Tab",
                background=[("selected", self.BG2)],
                foreground=[("selected", self.ACCENT)])

        nb = ttk.Notebook(self.root)
        nb.pack(fill=BOTH, expand=True, padx=10, pady=(6, 10))

        self.tab_dialer = tk.Frame(nb, bg=self.BG)
        self.tab_coords = tk.Frame(nb, bg=self.BG)
        self.tab_logs   = tk.Frame(nb, bg=self.BG)

        nb.add(self.tab_dialer, text="  🚀  Dialer  ")
        nb.add(self.tab_coords, text="  🎯  Coordinates  ")
        nb.add(self.tab_logs,   text="  📋  Call Logs  ")

        self._build_dialer_tab()
        self._build_coords_tab()
        self._build_logs_tab()

    # ══════════════════════════════════════════════════════════════
    #  DIALER TAB
    # ══════════════════════════════════════════════════════════════

    def _build_dialer_tab(self):
        f = self.tab_dialer

        # File picker
        fc = self._lf(f, "  📂  Phone List  (Excel .xlsx / .xls)", fg=self.ACCENT2)
        fc.pack(fill=X, padx=16, pady=(14, 6))
        fc.columnconfigure(0, weight=1)

        self.excel_var = tk.StringVar(value=self.config.get("excel_path", ""))
        tk.Entry(fc, textvariable=self.excel_var,
                 bg=self.HDR, fg=self.FG, insertbackground=self.ACCENT,
                 font=self.FONT_MONO, bd=0, relief="flat",
                 highlightthickness=1, highlightbackground=self.MUTED,
                 ).grid(row=0, column=0, sticky="ew", padx=(10, 8), pady=10, ipady=5)
        self._btn(fc, "📂  Browse", self._browse_file,
                  color=self.ACCENT2).grid(row=0, column=1, padx=(0, 10), pady=10)

        # Settings
        sc = self._lf(f, "  ⚙️  Settings")
        sc.pack(fill=X, padx=16, pady=6)

        tk.Label(sc, text="Start Delay (sec):", font=self.FONT,
                 bg=self.BG2, fg=self.FG).pack(side=LEFT, padx=(12, 4), pady=8)
        self.delay_var = tk.IntVar(value=self.config.get("initial_delay", 5))
        tk.Spinbox(sc, from_=2, to=30, textvariable=self.delay_var, width=4,
                   font=self.FONT, bg=self.HDR, fg=self.ACCENT,
                   buttonbackground=self.BG2, insertbackground=self.ACCENT,
                   ).pack(side=LEFT, pady=8)

        tk.Label(sc, text="   Auto-Cut Duration (sec):", font=self.FONT,
                 bg=self.BG2, fg=self.FG).pack(side=LEFT, padx=(18, 4))
        self.autocut_var = tk.IntVar(value=self.config.get("autocut_duration", 10))
        tk.Spinbox(sc, from_=5, to=300, textvariable=self.autocut_var, width=4,
                   font=self.FONT, bg=self.HDR, fg=self.PURPLE,
                   buttonbackground=self.BG2, insertbackground=self.PURPLE,
                   ).pack(side=LEFT, pady=8)
        tk.Label(sc, text="(auto-cut only)", font=self.FONT_SM,
                 bg=self.BG2, fg=self.MUTED).pack(side=LEFT, padx=(4, 20))

        self.browser_mode_var = tk.BooleanVar(value=self.config.get("browser_mode", False))
        tk.Checkbutton(sc,
                       text="🌐  Browser DOM Mode (Selenium)",
                       variable=self.browser_mode_var,
                       command=self._on_browser_mode_toggle,
                       bg=self.BG2, fg=self.ACCENT2,
                       selectcolor=self.HDR, activebackground=self.BG2,
                       font=self.FONT, padx=6,
                       ).pack(side=LEFT)

        # Progress
        pc = self._lf(f, "  📊  Progress", fg=self.ACCENT2)
        pc.pack(fill=X, padx=16, pady=6)

        sr = tk.Frame(pc, bg=self.BG2)
        sr.pack(fill=X, padx=10, pady=(8, 4))

        def stat(lbl, col):
            tk.Label(sr, text=lbl, font=self.FONT, bg=self.BG2, fg=self.MUTED).pack(side=LEFT)
            v = tk.Label(sr, text="—", font=self.FONT_B, bg=self.BG2, fg=col)
            v.pack(side=LEFT, padx=(2, 16))
            return v

        self.lbl_total     = stat("Total:",     self.ACCENT2)
        self.lbl_done      = stat("Completed:", self.ACCENT)
        self.lbl_remaining = stat("Remaining:", self.WARN)
        self.lbl_skipped   = stat("Invalid:",   self.ORANGE)

        ps = ttk.Style()
        ps.configure("G.Horizontal.TProgressbar",
                     troughcolor=self.HDR, background=self.ACCENT, thickness=14)
        self.progress_bar = ttk.Progressbar(pc,
                                            style="G.Horizontal.TProgressbar",
                                            mode="determinate")
        self.progress_bar.pack(fill=X, padx=10, pady=(0, 10))

        # Current call
        cc = self._lf(f, "  📞  Current Call", fg=self.WARN)
        cc.pack(fill=X, padx=16, pady=6)
        self.lbl_current = tk.Label(cc, text="No active call",
                                    font=("Segoe UI", 13, "bold"),
                                    bg=self.BG2, fg=self.WARN)
        self.lbl_current.pack(pady=10)

        # Control buttons
        bf = tk.Frame(f, bg=self.BG)
        bf.pack(fill=X, padx=16, pady=(10, 4))

        self.btn_load  = self._btn(bf, "⬇  Load Numbers",  self._load_numbers,  color=self.ACCENT2, width=18)
        self.btn_start = self._btn(bf, "▶  Start Dialer",   self._start_dialer,  color=self.ACCENT,  width=18, state=DISABLED)
        self.btn_next  = self._btn(bf, "⏭  Next Call [X]",  self._manual_next,   color=self.WARN,    width=18, state=DISABLED)
        self.btn_stop  = self._btn(bf, "⏹  Stop",           self._stop_dialer,   color=self.DANGER,  width=12, state=DISABLED)

        for b in (self.btn_load, self.btn_start, self.btn_next, self.btn_stop):
            b.pack(side=LEFT, padx=4)

        # Auto-Cut row
        bf2 = tk.Frame(f, bg=self.BG)
        bf2.pack(fill=X, padx=16, pady=(0, 4))
        tk.Frame(bf2, bg=self.MUTED, height=1).pack(fill=X, pady=(2, 6))
        tk.Label(bf2, text="🤖  Auto-Cut Mode:", font=self.FONT_B,
                 bg=self.BG, fg=self.PURPLE).pack(side=LEFT, padx=(4, 8))
        self.btn_autocut = self._btn(
            bf2, "⚡  Start Auto-Cut  (dial → wait → hangup → repeat)",
            self._start_autocut, color=self.PURPLE, width=50, state=DISABLED
        )
        self.btn_autocut.pack(side=LEFT, padx=4)

        # Activity console
        lc = self._lf(f, "  🖥️  Activity Log")
        lc.pack(fill=BOTH, expand=True, padx=16, pady=(6, 10))
        self.console = tk.Text(
            lc, height=8, font=self.FONT_MONO,
            bg="#050e18", fg=self.ACCENT,
            insertbackground=self.ACCENT,
            bd=0, relief="flat", state=DISABLED,
            wrap="word", padx=8, pady=6,
        )
        cs = tk.Scrollbar(lc, command=self.console.yview,
                          bg=self.BG2, troughcolor=self.HDR)
        self.console.configure(yscrollcommand=cs.set)
        cs.pack(side=RIGHT, fill=Y)
        self.console.pack(fill=BOTH, expand=True, padx=(8, 0), pady=8)

    # ══════════════════════════════════════════════════════════════
    #  COORDINATES TAB
    # ══════════════════════════════════════════════════════════════

    def _build_coords_tab(self):
        f = self.tab_coords

        tk.Label(f, text="Screen Coordinate Setup",
                 font=self.FONT_XL, bg=self.BG, fg=self.ACCENT).pack(pady=(20, 4))
        tk.Label(f,
                 text="Click  🎯 Pick  then click the matching element on your Google Voice screen.",
                 font=self.FONT_SM, bg=self.BG, fg=self.MUTED).pack(pady=(0, 10))

        # Browser connect panel
        bc = self._lf(f, "  🌐  Browser DOM Mode  (Selenium — optional)", fg=self.ACCENT2)
        bc.pack(fill=X, padx=50, pady=(0, 10))

        br = tk.Frame(bc, bg=self.BG2)
        br.pack(fill=X, padx=12, pady=8)

        tk.Label(br, text="Chrome Debug Port:", font=self.FONT,
                 bg=self.BG2, fg=self.FG).pack(side=LEFT)
        self.port_var = tk.IntVar(value=self.config.get("chrome_debug_port", 9222))
        tk.Spinbox(br, from_=1024, to=65535, textvariable=self.port_var, width=6,
                   font=self.FONT, bg=self.HDR, fg=self.ACCENT2,
                   buttonbackground=self.BG2).pack(side=LEFT, padx=(6, 16))
        self._btn(br, "🔌  Connect to Chrome",
                  self._connect_browser, color=self.ACCENT2, width=22).pack(side=LEFT)
        self.browser_status = tk.Label(br, text="Not connected",
                                       font=self.FONT, bg=self.BG2, fg=self.MUTED)
        self.browser_status.pack(side=LEFT, padx=12)

        tk.Label(bc,
                 text="How to enable: launch Chrome with --remote-debugging-port=9222\n"
                      "Then log into Google Voice normally.  This app will NOT bypass login or security.",
                 font=("Segoe UI", 8), bg=self.BG2, fg=self.MUTED, justify=LEFT,
                 ).pack(anchor=W, padx=12, pady=(0, 8))

        # Coordinates grid
        cc = self._lf(f, "  🖱️  Coordinate Settings  (used when Browser DOM Mode is OFF)",
                      fg=self.ACCENT2)
        cc.pack(fill=X, padx=50, pady=6)
        cc.columnconfigure(1, weight=1)

        fields = [
            ("number_field",    "📱  Number Input Field",  "Where the phone number is typed"),
            ("call_button",     "📞  Call / Dial Button",  "Button that starts the call"),
            ("end_call_button", "🔴  End Call Button",     "Button that hangs up the call"),
        ]
        self.coord_vars = {}
        for i, (key, label, hint) in enumerate(fields):
            tk.Label(cc, text=label, font=self.FONT_B,
                     bg=self.BG2, fg=self.FG).grid(row=i, column=0, sticky=W,
                                                    pady=10, padx=(12, 8))
            x_var = tk.IntVar(value=self.config[key][0])
            y_var = tk.IntVar(value=self.config[key][1])
            self.coord_vars[key] = (x_var, y_var)

            cf2 = tk.Frame(cc, bg=self.BG2)
            cf2.grid(row=i, column=1, sticky=W, pady=6)
            for lbl_txt, var in [("X:", x_var), ("Y:", y_var)]:
                tk.Label(cf2, text=lbl_txt, font=self.FONT,
                         bg=self.BG2, fg=self.MUTED).pack(side=LEFT)
                tk.Entry(cf2, textvariable=var, width=7,
                         font=("Consolas", 11, "bold"),
                         bg=self.HDR, fg=self.ACCENT,
                         insertbackground=self.ACCENT,
                         relief="flat", bd=0,
                         highlightthickness=1, highlightbackground=self.MUTED,
                         ).pack(side=LEFT, padx=(2, 12), ipady=4)

            self._btn(cc, "🎯 Pick",
                      lambda k=key: self._pick_coordinate(k),
                      color=self.WARN, width=10).grid(row=i, column=2, padx=10)
            tk.Label(cc, text=hint, font=self.FONT_SM,
                     bg=self.BG2, fg=self.MUTED).grid(row=i, column=3,
                                                       sticky=W, padx=(8, 12))

        self.coord_status = tk.Label(f, text="",
                                     font=self.FONT_B, bg=self.BG, fg=self.WARN)
        self.coord_status.pack(pady=8)

        self._btn(f, "💾  Save All Settings", self._save_coords,
                  color=self.ACCENT, width=24).pack(pady=(4, 6))

        # Test movement
        tc = self._lf(f, "  🧪  Test Mouse Position")
        tc.pack(fill=X, padx=50, pady=(12, 6))
        tk.Label(tc,
                 text="Moves mouse to position (does NOT click) — visual verification only.",
                 font=self.FONT_SM, bg=self.BG2, fg=self.MUTED,
                 ).pack(anchor=W, padx=10, pady=(8, 4))
        tr = tk.Frame(tc, bg=self.BG2)
        tr.pack(pady=8)
        for key, lbl in [("number_field", "Number Field"),
                         ("call_button",  "Call Button"),
                         ("end_call_button", "End Call")]:
            self._btn(tr, f"→ {lbl}",
                      lambda k=key: self._test_move(k),
                      color=self.ACCENT2, width=16).pack(side=LEFT, padx=6)

    # ══════════════════════════════════════════════════════════════
    #  LOGS TAB
    # ══════════════════════════════════════════════════════════════

    def _build_logs_tab(self):
        f = self.tab_logs

        top = tk.Frame(f, bg=self.BG)
        top.pack(fill=X, padx=16, pady=(12, 4))
        tk.Label(top, text="Call History",
                 font=self.FONT_LG, bg=self.BG, fg=self.ACCENT2).pack(side=LEFT)
        for txt, cmd, col in [
            ("📤  Export CSV", self._export_logs,    self.ACCENT),
            ("🗑  Clear Logs", self._clear_logs,      self.DANGER),
            ("🔄  Refresh",    self._load_logs_table, self.ACCENT2),
        ]:
            self._btn(top, txt, cmd, color=col, width=14).pack(side=RIGHT, padx=4)

        # Stats
        stats = tk.Frame(f, bg=self.BG)
        stats.pack(fill=X, padx=16, pady=4)
        self.lbl_log_total   = tk.Label(stats, text="Total: 0",     font=self.FONT, bg=self.BG, fg=self.ACCENT2)
        self.lbl_log_ended   = tk.Label(stats, text="Completed: 0", font=self.FONT, bg=self.BG, fg=self.ACCENT)
        self.lbl_log_skipped = tk.Label(stats, text="Skipped: 0",   font=self.FONT, bg=self.BG, fg=self.ORANGE)
        self.lbl_log_failed  = tk.Label(stats, text="Failed: 0",    font=self.FONT, bg=self.BG, fg=self.DANGER)
        for w in (self.lbl_log_total, self.lbl_log_ended,
                  self.lbl_log_skipped, self.lbl_log_failed):
            w.pack(side=LEFT, padx=10)

        # Search bar + status filter
        sf = tk.Frame(f, bg=self.BG)
        sf.pack(fill=X, padx=16, pady=(4, 2))
        tk.Label(sf, text="🔍  Filter:", font=self.FONT,
                 bg=self.BG, fg=self.MUTED).pack(side=LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._apply_log_filter())
        tk.Entry(sf, textvariable=self.filter_var,
                 bg=self.HDR, fg=self.FG, insertbackground=self.ACCENT,
                 font=self.FONT_MONO, bd=0, relief="flat",
                 highlightthickness=1, highlightbackground=self.MUTED,
                 width=28,
                 ).pack(side=LEFT, padx=(6, 16), ipady=4, pady=4)

        self.status_filter = tk.StringVar(value="ALL")
        for label, val, color in [
            ("All",              "ALL",             self.ACCENT2),
            ("Completed",        "ENDED",           self.ACCENT),
            ("Skipped/Invalid",  "SKIPPED_INVALID", self.ORANGE),
            ("Failed",           "FAILED",          self.DANGER),
            ("Stopped",          "STOPPED",         self.MUTED),
        ]:
            tk.Radiobutton(sf, text=label, variable=self.status_filter,
                           value=val, command=self._apply_log_filter,
                           bg=self.BG, fg=color, selectcolor=self.HDR,
                           activebackground=self.BG,
                           font=self.FONT_SM,
                           ).pack(side=LEFT, padx=4)

        # Treeview
        tf = tk.Frame(f, bg=self.BG)
        tf.pack(fill=BOTH, expand=True, padx=16, pady=(4, 12))

        ts = ttk.Style()
        ts.configure("dark.Treeview",
                     background=self.HDR, foreground=self.FG,
                     fieldbackground=self.HDR, rowheight=26, font=self.FONT)
        ts.configure("dark.Treeview.Heading",
                     background=self.BG2, foreground=self.ACCENT2, font=self.FONT_B)
        ts.map("dark.Treeview", background=[("selected", "#1e3a5f")])

        sb = tk.Scrollbar(tf, bg=self.BG2, troughcolor=self.HDR)
        sb.pack(side=RIGHT, fill=Y)
        self.log_tree = ttk.Treeview(tf,
                                     columns=("Time", "Phone", "Status"),
                                     show="headings",
                                     style="dark.Treeview",
                                     yscrollcommand=sb.set)
        sb.config(command=self.log_tree.yview)
        for col, w in [("Time", 200), ("Phone", 160), ("Status", 150)]:
            self.log_tree.heading(col, text=col)
            self.log_tree.column(col, width=w)

        self.log_tree.tag_configure("ENDED",           background="#0a2010", foreground="#00e676")
        self.log_tree.tag_configure("STARTED",         background="#1a1600", foreground="#ffd166")
        self.log_tree.tag_configure("SKIPPED_INVALID", background="#1a0f00", foreground="#ff6b35")
        self.log_tree.tag_configure("FAILED",          background="#1a0000", foreground="#ff4444")
        self.log_tree.tag_configure("STOPPED",         background="#111820", foreground="#8b949e")
        self.log_tree.pack(fill=BOTH, expand=True)

    # ══════════════════════════════════════════════════════════════
    #  COORDINATE PICKER
    # ══════════════════════════════════════════════════════════════

    def _pick_coordinate(self, key):
        self.coord_target = key
        self.coord_status.config(
            text=f"⏳  Minimizing… click the target on screen  (picking: {key})",
            fg=self.WARN)
        self.root.after(800, self._start_mouse_listener)

    def _start_mouse_listener(self):
        self.root.iconify()
        def on_click(x, y, button, pressed):
            if pressed:
                key = self.coord_target
                if key:
                    self.coord_vars[key][0].set(int(x))
                    self.coord_vars[key][1].set(int(y))
                    self.root.after(0, lambda: self.coord_status.config(
                        text=f"✅  Captured '{key}':  X={int(x)},  Y={int(y)}",
                        fg=self.ACCENT))
                    self.root.after(300, self.root.deiconify)
                return False
        self.mouse_listener = mouse.Listener(on_click=on_click)
        self.mouse_listener.start()

    def _test_move(self, key):
        x = self.coord_vars[key][0].get()
        y = self.coord_vars[key][1].get()
        pyautogui.moveTo(x, y, duration=0.4)
        self.coord_status.config(text=f"🖱️  Mouse moved to ({x}, {y})", fg=self.ACCENT2)

    def _save_coords(self):
        for key, (x_var, y_var) in self.coord_vars.items():
            self.config[key] = [x_var.get(), y_var.get()]
        self.config["initial_delay"]      = self.delay_var.get()
        self.config["autocut_duration"]   = self.autocut_var.get()
        self.config["excel_path"]         = self.excel_var.get()
        self.config["browser_mode"]       = self.browser_mode_var.get()
        self.config["chrome_debug_port"]  = self.port_var.get()
        save_config(self.config)
        self.coord_status.config(text="✅  All settings saved!", fg=self.ACCENT)
        messagebox.showinfo("Saved", "✅ Settings saved to dialer_config.json")

    def _connect_browser(self):
        port = self.port_var.get()
        self.browser_status.config(text="Connecting…", fg=self.WARN)
        self.root.update()
        ok, msg = self.browser.connect(port=port)
        if ok:
            self.browser_status.config(text=f"✅  Connected (port {port})", fg=self.ACCENT)
            self._log(f"🌐 Browser DOM connected on port {port}")
        else:
            self.browser_status.config(text=f"❌  {msg[:55]}", fg=self.DANGER)
            self._log(f"⚠️ Browser connect failed: {msg}")

    def _on_browser_mode_toggle(self):
        self.config["browser_mode"] = self.browser_mode_var.get()
        mode = "DOM/Selenium" if self.browser_mode_var.get() else "pyautogui (coordinates)"
        self._log(f"🔄 Automation mode: {mode}")

    # ══════════════════════════════════════════════════════════════
    #  FILE & NUMBER LOADING
    # ══════════════════════════════════════════════════════════════

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls"), ("All Files", "*.*")]
        )
        if path:
            self.excel_var.set(path)
            self.config["excel_path"] = path

    def _load_numbers(self):
        path = self.excel_var.get().strip()
        if not path:
            messagebox.showerror("No File", "Please select an Excel file first.")
            return
        if not os.path.exists(path):
            messagebox.showerror("File Not Found", f"File not found:\n{path}")
            return

        try:
            df = pd.read_excel(path)
        except Exception as e:
            messagebox.showerror("Excel Error", f"Cannot read file:\n{e}")
            return

        df.columns = df.columns.str.strip()
        phone_col  = None
        candidates = ['Phone', 'phone', 'PHONE', 'Phone Number', 'phone_number',
                      'Mobile', 'mobile', 'Number', 'number', 'Tel', 'tel',
                      'Telephone', 'Cell', 'cell']
        for col in df.columns:
            if col.strip() in candidates:
                phone_col = col
                break

        if phone_col is None:
            messagebox.showerror(
                "Column Not Found",
                f"No phone column found.\n\n"
                f"Available columns:\n  {list(df.columns)}\n\n"
                f"Rename your column to one of:\n"
                f"  Phone, Mobile, Number, Tel"
            )
            return

        raw_values     = df[phone_col].tolist()
        valid_numbers  = []
        invalid_count  = 0

        for raw in raw_values:
            cleaned = clean_phone(raw)
            if cleaned:
                valid_numbers.append(cleaned)
            else:
                s = str(raw).strip()
                if s and s.lower() not in ('nan', 'none', ''):
                    invalid_count += 1
                    log_call(s, "SKIPPED_INVALID")

        if not valid_numbers:
            messagebox.showerror(
                "No Valid Numbers",
                f"No valid US 10-digit numbers found.\n"
                f"Invalid/skipped entries: {invalid_count}\n\n"
                f"Supported formats:\n"
                f"  10 digits, +1XXXXXXXXXX, (XXX) XXX-XXXX, XXX-XXX-XXXX"
            )
            return

        if invalid_count:
            self._log(f"⚠️  Skipped {invalid_count} invalid entries (logged as SKIPPED_INVALID)")

        completed = get_completed_numbers()
        self.contacts = [
            p for p in valid_numbers
            if fmt_e164(p) not in completed and p not in completed
        ]
        self.current_index = 0

        total  = len(valid_numbers)
        done   = total - len(self.contacts)
        rem    = len(self.contacts)

        self.lbl_total.config(text=str(total))
        self.lbl_done.config(text=str(done))
        self.lbl_remaining.config(text=str(rem))
        self.lbl_skipped.config(text=str(invalid_count))
        self._update_progress(done, total)
        self._log(
            f"✅  Loaded {total} valid  |  Done: {done}  |  "
            f"Remaining: {rem}  |  Invalid: {invalid_count}"
        )
        self._load_logs_table()

        if rem == 0:
            messagebox.showinfo("All Done",
                                "All numbers in this file are already completed!")
        else:
            self.btn_start.config(state=NORMAL)
            self.btn_autocut.config(state=NORMAL)

    # ══════════════════════════════════════════════════════════════
    #  DIALER CORE
    # ══════════════════════════════════════════════════════════════

    def _start_dialer(self):
        if not self.contacts:
            messagebox.showwarning("No Contacts", "Load an Excel file first.")
            return
        self.config["initial_delay"] = self.delay_var.get()
        self.config["excel_path"]    = self.excel_var.get()
        save_config(self.config)
        self.running = True
        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
        self.btn_next.config(state=NORMAL)
        self._set_status("STARTING", self.WARN)
        threading.Thread(target=self._dialer_thread, daemon=True).start()

    def _dialer_thread(self):
        delay = self.config.get("initial_delay", 5)
        self._log(f"🚀  Starting in {delay}s — switch to Google Voice now!")
        for i in range(delay, 0, -1):
            self._log(f"   ⏳ {i}…")
            time.sleep(1)
        if not self.running:
            return
        self._make_call(self.contacts[self.current_index])
        self._set_status("ACTIVE", self.ACCENT)

        def on_press(key):
            try:
                if hasattr(key, 'char') and key.char and key.char.lower() == 'x' and self.running:
                    self._log("⌨️  X pressed → Hangup + Next")
                    threading.Thread(target=self._hangup_and_next, daemon=True).start()
            except AttributeError:
                pass
            if key == keyboard.Key.esc:
                self._stop_dialer()
                return False

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.start()
        self.listener.join()

    def _make_call(self, number):
        formatted = fmt_e164(number) if len(number) == 10 else number
        self._log(f"📞  Dialing {formatted} …")
        self.root.after(0, lambda: self.lbl_current.config(text=f"Calling: {formatted}"))

        try:
            # Browser DOM path
            if self.browser_mode_var.get() and self.browser.connected:
                self.browser.focus_window()
                time.sleep(0.3)
                if self.browser.dial(formatted):
                    self.call_active = True
                    log_call(formatted, "STARTED")
                    self._log(f"✅  Call started via DOM: {formatted}")
                    return
                self._log("⚠️  DOM dial failed — falling back to pyautogui")

            # pyautogui path
            cfg = self.config
            nx, ny = cfg["number_field"]
            pyautogui.click(nx, ny, clicks=2)
            time.sleep(random.uniform(0.2, 0.4))
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('backspace')
            time.sleep(random.uniform(0.15, 0.3))

            if CLIPBOARD_AVAILABLE:
                pyperclip.copy(formatted)
                pyautogui.hotkey('ctrl', 'v')
            else:
                pyautogui.write(formatted, interval=TYPE_DELAY)

            time.sleep(random.uniform(0.2, 0.35))
            cx, cy = cfg["call_button"]
            pyautogui.click(cx, cy, clicks=2)

            self.call_active = True
            log_call(formatted, "STARTED")
            self._log(f"✅  Call started: {formatted}")

        except Exception as e:
            self._log(f"❌  Call failed: {formatted} — {e}")
            log_call(formatted, "FAILED")

    def _hangup_call(self):
        if not self.call_active:
            return
        try:
            if self.browser_mode_var.get() and self.browser.connected:
                if self.browser.hangup():
                    self.call_active = False
                    self._log("📴  Call ended via DOM")
                    return
                self._log("⚠️  DOM hangup failed — falling back to pyautogui")
            ex, ey = self.config["end_call_button"]
            pyautogui.click(ex, ey)
            time.sleep(0.7)
            self.call_active = False
            self._log("📴  Call ended")
        except Exception as e:
            self._log(f"⚠️  Hangup error: {e}")
            self.call_active = False

    def _hangup_and_next(self):
        if self.current_index >= len(self.contacts):
            return
        prev      = self.contacts[self.current_index]
        formatted = fmt_e164(prev)
        self._hangup_call()
        log_call(formatted, "ENDED")
        self._log(f"📝  Logged ENDED: {formatted}")
        self.current_index += 1
        self._refresh_progress()
        self.root.after(0, self._load_logs_table)

        if self.current_index >= len(self.contacts):
            self._log("🎯  All calls completed!")
            self.root.after(0, lambda: self.lbl_current.config(text="✅  All calls done!"))
            self._set_status("DONE", self.ACCENT)
            self.root.after(500, self._on_all_done)
            return
        self._make_call(self.contacts[self.current_index])

    def _refresh_progress(self):
        total  = len(self.contacts)
        done_n = len(get_completed_numbers())
        rem    = max(total - self.current_index, 0)
        self.root.after(0, lambda: self.lbl_done.config(text=str(done_n)))
        self.root.after(0, lambda: self.lbl_remaining.config(text=str(rem)))
        self._update_progress(self.current_index, total)

    def _manual_next(self):
        if not self.running:
            return
        threading.Thread(target=self._hangup_and_next, daemon=True).start()

    def _stop_dialer(self):
        if self.call_active and self.current_index < len(self.contacts):
            try:
                self._hangup_call()
            except Exception:
                pass
            log_call(fmt_e164(self.contacts[self.current_index]), "STOPPED")
        self.running     = False
        self.call_active = False
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.root.after(0, lambda: self.btn_start.config(state=NORMAL))
        self.root.after(0, lambda: self.btn_stop.config(state=DISABLED))
        self.root.after(0, lambda: self.btn_next.config(state=DISABLED))
        self.root.after(0, lambda: self.btn_autocut.config(state=NORMAL))
        self.root.after(0, lambda: self.lbl_current.config(text="Stopped"))
        self._set_status("IDLE", self.MUTED)
        self._log("⛔  Dialer stopped")
        self.root.after(300, self._load_logs_table)

    # ══════════════════════════════════════════════════════════════
    #  AUTO-CUT MODE
    # ══════════════════════════════════════════════════════════════

    def _start_autocut(self):
        if not self.contacts:
            messagebox.showwarning("No Contacts", "Load an Excel file first.")
            return
        duration = self.autocut_var.get()
        self.config["initial_delay"]    = self.delay_var.get()
        self.config["autocut_duration"] = duration
        self.config["excel_path"]       = self.excel_var.get()
        save_config(self.config)
        self.running = True
        self.btn_start.config(state=DISABLED)
        self.btn_autocut.config(state=DISABLED)
        self.btn_next.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
        self._set_status("AUTO-CUT", self.PURPLE)
        self._log(f"⚡  Auto-Cut mode started — {duration}s per call, fully automatic")
        threading.Thread(target=self._autocut_thread, daemon=True).start()

    def _autocut_thread(self):
        delay    = self.config.get("initial_delay", 5)
        duration = self.config.get("autocut_duration", 10)
        self._log(f"🚀  Starting in {delay}s — switch to Google Voice now!")
        for i in range(delay, 0, -1):
            self._log(f"   ⏳ {i}…")
            time.sleep(1)
            if not self.running:
                return

        total = len(self.contacts)
        while self.running and self.current_index < total:
            number    = self.contacts[self.current_index]
            formatted = fmt_e164(number)

            try:
                self._make_call(number)
            except Exception as e:
                self._log(f"❌  Auto-cut call error: {e}")
                log_call(formatted, "FAILED")
                self.current_index += 1
                self._refresh_progress()
                continue

            for remaining in range(duration, 0, -1):
                if not self.running:
                    break
                self.root.after(0, lambda r=remaining, fmt=formatted:
                    self.lbl_current.config(
                        text=f"⚡  Auto-Cut  {fmt}  ─  hanging up in {r}s"))
                time.sleep(1)

            if not self.running:
                break

            try:
                if self.browser_mode_var.get() and self.browser.connected:
                    if not self.browser.hangup():
                        raise Exception("DOM hangup failed")
                else:
                    ex, ey = self.config["end_call_button"]
                    pyautogui.click(ex, ey)
                    pyautogui.click(ex, ey)
                    time.sleep(0.3)
                    pyautogui.press('esc')
            except Exception as e:
                self._log(f"⚠️  Hangup error in auto-cut: {e}")

            self.call_active = False
            log_call(formatted, "ENDED")
            self._log(f"🔴  Auto-cut: {formatted} hung up after {duration}s")
            self.current_index += 1
            self._refresh_progress()
            self.root.after(0, self._load_logs_table)

            if self.running and self.current_index < total:
                cooldown = random.uniform(2, 4)
                self._log(f"   ⏸  Cooldown {cooldown:.1f}s…")
                time.sleep(cooldown)

        if self.running:
            self._log("🎯  Auto-Cut: all calls completed!")
            self.root.after(0, lambda: self.lbl_current.config(text="✅  All auto-cut calls done!"))
            self._set_status("DONE", self.ACCENT)
            self.root.after(500, self._on_all_done)
        else:
            self.root.after(0, lambda: self.lbl_current.config(text="Stopped"))

    def _on_all_done(self):
        self.running = False
        self.root.after(0, lambda: self.btn_start.config(state=NORMAL))
        self.root.after(0, lambda: self.btn_stop.config(state=DISABLED))
        self.root.after(0, lambda: self.btn_next.config(state=DISABLED))
        self.root.after(0, lambda: self.btn_autocut.config(state=NORMAL))
        self._load_logs_table()
        answer = messagebox.askyesnocancel(
            "All Calls Completed!",
            "All phone numbers have been dialed!\n\n"
            "YES    → Load a new Excel file\n"
            "NO     → Repeat the same list from the top\n"
            "CANCEL → Exit the application"
        )
        if answer is True:
            self._browse_file()
            self._load_numbers()
        elif answer is False:
            self._log("🔄  Repeating same list from the top…")
            self.current_index = 0
            self.lbl_remaining.config(text=str(len(self.contacts)))
            self.btn_start.config(state=NORMAL)
        else:
            self.root.quit()

    # ══════════════════════════════════════════════════════════════
    #  LOGS
    # ══════════════════════════════════════════════════════════════

    def _load_logs_table(self):
        self._all_logs = load_call_logs()
        self._apply_log_filter()

    def _apply_log_filter(self):
        query  = self.filter_var.get().strip().lower() if hasattr(self, 'filter_var') else ""
        status = self.status_filter.get()             if hasattr(self, 'status_filter') else "ALL"

        filtered = []
        for row in self._all_logs:
            st = row.get("Status", "")
            if status != "ALL" and st != status:
                continue
            if query and (
                query not in row.get("Phone", "").lower() and
                query not in row.get("Time",  "").lower() and
                query not in st.lower()
            ):
                continue
            filtered.append(row)

        for item in self.log_tree.get_children():
            self.log_tree.delete(item)

        ended   = sum(1 for r in self._all_logs if r.get("Status") == "ENDED")
        skipped = sum(1 for r in self._all_logs if r.get("Status") == "SKIPPED_INVALID")
        failed  = sum(1 for r in self._all_logs if r.get("Status") == "FAILED")

        self.root.after(0, lambda: self.lbl_log_total.config(
            text=f"Total: {len(self._all_logs)}"))
        self.root.after(0, lambda: self.lbl_log_ended.config(
            text=f"Completed: {ended}"))
        self.root.after(0, lambda: self.lbl_log_skipped.config(
            text=f"Skipped: {skipped}"))
        self.root.after(0, lambda: self.lbl_log_failed.config(
            text=f"Failed: {failed}"))

        for row in reversed(filtered):
            tag = row.get("Status", "")
            self.log_tree.insert("", END,
                                 values=(row.get("Time", ""),
                                         row.get("Phone", ""),
                                         tag),
                                 tags=(tag,))

    def _clear_logs(self):
        if messagebox.askyesno("Clear Logs",
                               "Delete ALL call logs?\nThis cannot be undone."):
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
            self._all_logs = []
            self._load_logs_table()
            self._log("🗑  Logs cleared")

    def _export_logs(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="call_logs_export.csv"
        )
        if path and os.path.exists(LOG_FILE):
            import shutil
            shutil.copy(LOG_FILE, path)
            messagebox.showinfo("Exported", f"Logs exported to:\n{path}")

    # ══════════════════════════════════════════════════════════════
    #  UTILITY
    # ══════════════════════════════════════════════════════════════

    def _log(self, msg):
        def _write():
            self.console.configure(state=NORMAL)
            ts = datetime.now().strftime("%H:%M:%S")
            self.console.insert(END, f"[{ts}]  {msg}\n")
            self.console.see(END)
            self.console.configure(state=DISABLED)
        self.root.after(0, _write)

    def _set_status(self, text, color):
        self.root.after(0, lambda: self.status_badge.config(
            text=f"● {text}", fg=color))

    def _update_progress(self, done, total):
        if total > 0:
            pct = (done / total) * 100
            self.root.after(0, lambda: self.progress_bar.configure(value=pct))


# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tb.Window(themename="darkly")
    app  = AutoDialerApp(root)
    root.mainloop()
