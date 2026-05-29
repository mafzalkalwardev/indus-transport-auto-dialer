"""
Google Voice Selenium browser automation.
Ported from GoogleVoiceAgent-Active/src/google_voice.py.
ALL automation is DOM-based — zero pyautogui.
Persistent Chrome profile keeps login session between runs.
"""
from __future__ import annotations

import ctypes
import os
import re
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, WebDriverException,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
    _WDM = True
except ImportError:
    _WDM = False

from src.call_session import CallSession, CallState

GV_URL = "https://voice.google.com"

# ── Selector banks (tried in order; first visible match wins) ─────────────────
_SEL: dict[str, list[str]] = {
    "login_indicator": [
        '[aria-label="Google Account"]',
        'img[alt="profile photo"]',
        '[data-email]',
        'a[aria-label*="account" i]',
    ],
    "dialpad_open": [
        'button[aria-label*="keypad" i]',
        'button[aria-label*="dialpad" i]',
        "gv-icon-button[icon-name='phone']",
        'button[aria-label*="dial" i]',
        'button[aria-label*="new call" i]',
        "gv-new-conversation-fab",
        '[data-action="new-call"]',
        'button[aria-label*="make" i]',
    ],
    "calls_tab": [
        'a[aria-label="Calls"]',
        'a[role="tab"][aria-label*="Calls" i]',
    ],
    "number_input": [
        'input[aria-label*="number" i]',
        'input[placeholder*="number" i]',
        'input[placeholder*="name or number" i]',
        "input[type='tel']",
    ],
    "call_button": [
        'button[aria-label*="call" i]:not([aria-label*="end" i]):not([aria-label*="video" i])',
        "gv-icon-button[icon-name='call']",
        '[data-action="call"]',
        "button.call-button",
    ],
    "hangup_button": [
        'button[aria-label*="Hang up" i]',
        'button[aria-label*="Hangup" i]',
        'button[aria-label*="End call" i]',
        'button[title*="Hang up" i]',
        'button[title*="End call" i]',
        "gv-icon-button[icon-name='call_end']",
        '[data-action="end-call"]',
        "button.end-call",
    ],
    "call_active": [
        'button[aria-label*="Hang up" i]',
        'button[aria-label*="End call" i]',
        "gv-icon-button[icon-name='call_end']",
    ],
    # Controls visible ONLY after the remote party answers (not during ringing)
    "answered_controls": [
        'button[aria-label*="Hold call" i]',
        'button[aria-label*="Mute call" i]',
        'button[aria-label*="Unmute call" i]',
        'button[aria-label*="Transfer" i]',
        'button[aria-label*="Add a call" i]',
        'button[aria-label*="Record the call" i]',
        'button[aria-label*="Send a message" i]',
    ],
    "call_timer": [
        '[jsname="pRLmDf"]',
        '[aria-label*="call duration" i]',
        ".call-duration",
        "[data-e2eid='call-timer']",
    ],
    "voicemail_cue": [
        ".voicemail-indicator",
        "[data-e2eid='voicemail-record']",
        '[aria-label*="leave a message" i]',
        '[aria-label*="record after" i]',
        '[title*="leave a message" i]',
    ],
    "call_ended_banner": [
        '[aria-label*="Call ended" i]',
        "[data-e2eid='call-ended']",
        ".call-ended",
    ],
}

_VOICEMAIL_PHRASES = [
    "leave a message", "record after the tone", "mailbox is full",
    "not available right now", "please leave", "after the beep",
    "leave a voicemail",
]

_DURATION_RE       = re.compile(r"\b(?:\d{1,2}:)?\d{1,2}:\d{2}\b")
_EXACT_DURATION_RE = re.compile(r"^(?:\d{1,2}:)?\d{1,2}:\d{2}$")
_AM_PM_RE          = re.compile(r"\b(?:am|pm)\b", re.I)


def _js_click(driver, element) -> None:
    try:
        driver.execute_script("arguments[0].click();", element)
    except Exception:
        element.click()


class GoogleVoiceBrowser:
    """
    Single Chrome instance bound to one persistent profile.
    All interaction uses DOM selectors — no screen coordinates.
    """

    def __init__(self, profile_dir: str, headless: bool = False):
        self.profile_dir = profile_dir
        self.headless    = headless
        self.driver: Optional[webdriver.Chrome] = None
        self._window_title: str = ""

    # ── Launch / teardown ─────────────────────────────────────────────────────

    def launch(self) -> bool:
        os.makedirs(self.profile_dir, exist_ok=True)
        opts = Options()
        opts.add_argument(f"--user-data-dir={self.profile_dir}")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_experimental_option("prefs", {
            "profile.default_content_setting_values.media_stream_mic": 1,
            "profile.default_content_setting_values.notifications": 2,
        })
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--blink-settings=imagesEnabled=false")
        opts.add_argument("--disable-dev-shm-usage")
        if self.headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--disable-gpu")
        try:
            if _WDM:
                svc = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=svc, options=opts)
            else:
                self.driver = webdriver.Chrome(options=opts)
            self.driver.execute_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            self.driver.get(GV_URL)
            time.sleep(3)
            return True
        except Exception:
            return False

    def quit(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # ── Window focus (OS-level, brings Chrome to foreground) ─────────────────

    def focus_window(self) -> bool:
        if not self.driver:
            return False
        # Step 1: Selenium switch + JS focus
        try:
            self.driver.switch_to.window(self.driver.current_window_handle)
            self.driver.execute_script("window.focus();")
            self.driver.maximize_window()
        except Exception:
            pass
        # Step 2: Windows API via ctypes
        try:
            title = self.driver.title or self._window_title
            if title:
                hwnd = ctypes.windll.user32.FindWindowW(None, title)
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    return True
        except Exception:
            pass
        # Step 3: pygetwindow fallback
        try:
            import pygetwindow as gw
            for frag in ("Google Voice", "voice.google.com"):
                wins = gw.getWindowsWithTitle(frag)
                if wins:
                    wins[0].activate()
                    return True
        except Exception:
            pass
        return False

    # ── Login detection ───────────────────────────────────────────────────────

    def is_logged_in(self) -> bool:
        if not self.driver:
            return False
        try:
            if "voice.google.com" not in (self.driver.current_url or ""):
                return False
            return self._find_first("login_indicator", timeout=4) is not None
        except WebDriverException:
            return False

    def wait_for_manual_login(self, timeout: int = 300,
                               status_cb=None) -> bool:
        """
        Polls until logged in. status_cb(msg) called every 5s if provided.
        User must log in manually in the browser window.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_logged_in():
                return True
            if status_cb:
                remaining = int(deadline - time.time())
                status_cb(f"Waiting for Google login… {remaining}s remaining")
            time.sleep(2)
        return False

    # ── Internal DOM helpers ──────────────────────────────────────────────────

    def _find_first(self, group: str, timeout: float = 5.0):
        selectors = _SEL.get(group, [])
        deadline  = time.time() + timeout
        while time.time() < deadline:
            for sel in selectors:
                try:
                    for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                        if el.is_displayed():
                            return el
                except (NoSuchElementException, WebDriverException):
                    pass
            time.sleep(0.3)
        return None

    def _click_first(self, group: str, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for sel in _SEL.get(group, []):
                try:
                    for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                        if el.is_displayed() and el.is_enabled():
                            _js_click(self.driver, el)
                            return True
                except WebDriverException:
                    continue
            time.sleep(0.3)
        return False

    def _any_present(self, group: str) -> bool:
        for sel in _SEL.get(group, []):
            try:
                if any(e.is_displayed()
                       for e in self.driver.find_elements(By.CSS_SELECTOR, sel)):
                    return True
            except WebDriverException:
                pass
        return False

    def _set_input_value(self, element, value: str) -> None:
        self.driver.execute_script(
            """
            const el=arguments[0],val=arguments[1];
            const proto=el.tagName==='TEXTAREA'
              ?window.HTMLTextAreaElement.prototype
              :window.HTMLInputElement.prototype;
            const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;
            el.focus();
            if(setter){setter.call(el,val);}else{el.value=val;}
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
            """, element, value
        )

    def _open_calls_page(self) -> bool:
        try:
            if "/calls" in (self.driver.current_url or ""):
                return True
        except WebDriverException:
            return False
        if self._click_first("calls_tab", timeout=5):
            time.sleep(2.0)
            return True
        try:
            self.driver.get(f"{GV_URL}/u/0/calls")
            time.sleep(3.0)
            return "/calls" in (self.driver.current_url or "")
        except WebDriverException:
            return False

    # ── Call state detection helpers ──────────────────────────────────────────

    def _answered_controls_present(self) -> tuple[bool, list[str]]:
        found: list[str] = []
        for sel in _SEL.get("answered_controls", []):
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    if not el.is_displayed():
                        continue
                    label = (
                        el.get_attribute("aria-label") or
                        el.get_attribute("title") or
                        getattr(el, "text", "") or ""
                    ).strip()
                    if label:
                        found.append(label)
            except WebDriverException:
                continue
        return bool(found), found

    def _call_timer_present(self) -> bool:
        for sel in _SEL.get("call_timer", []):
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    if not el.is_displayed():
                        continue
                    parts = (
                        getattr(el, "text", ""),
                        el.get_attribute("aria-label") or "",
                        el.get_attribute("title") or "",
                    )
                    text = " ".join(p for p in parts if p)
                    if _DURATION_RE.search(text):
                        return True
            except WebDriverException:
                continue
        # JS fallback: look for MM:SS near hangup button
        if self._any_present("call_active"):
            try:
                texts = self.driver.execute_script(
                    r"""
                    const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();
                    return s.visibility!=='hidden'&&s.display!=='none'&&r.width>0&&r.height>0;};
                    const res=[];
                    for(const e of document.querySelectorAll('body *')){
                      if(!vis(e))continue;
                      if(['SCRIPT','STYLE','BUTTON','A','INPUT'].includes(e.tagName))continue;
                      const t=(e.children.length===0?e.textContent:'').replace(/\s+/g,' ').trim();
                      if(/^(?:\d{1,2}:)?\d{1,2}:\d{2}$/.test(t))res.push(t);
                    }return res;
                    """
                )
                for t in (texts or []):
                    if _EXACT_DURATION_RE.match(str(t)) and not _AM_PM_RE.search(str(t)):
                        return True
            except WebDriverException:
                pass
        return False

    def _voicemail_present(self) -> bool:
        for sel in _SEL.get("voicemail_cue", []):
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    if not el.is_displayed():
                        continue
                    parts = (
                        getattr(el, "text", ""),
                        el.get_attribute("aria-label") or "",
                        el.get_attribute("title") or "",
                    )
                    text = " ".join(p for p in parts if p).lower()
                    if any(ph in text for ph in
                           ("leave a message", "record after", "after the beep",
                            "voicemail-record", "voicemail-indicator")):
                        return True
            except WebDriverException:
                continue
        try:
            src = self.driver.page_source.lower()
            return any(ph in src for ph in _VOICEMAIL_PHRASES)
        except WebDriverException:
            return False

    # ── Dialing ───────────────────────────────────────────────────────────────

    def dial(self, phone: str) -> bool:
        """
        Dial a number using Google Voice DOM.
        Returns True if the call button was successfully clicked.
        """
        if not self.driver:
            return False
        try:
            self.driver.switch_to.window(self.driver.current_window_handle)
            self.driver.execute_script("window.focus();")
        except WebDriverException:
            return False

        if not self._open_calls_page():
            return False

        opened = self._find_first("number_input", timeout=2) is not None
        if not opened:
            opened = self._click_first("dialpad_open", timeout=6)
            if opened:
                time.sleep(1.2)

        if not opened:
            return False

        inp = self._find_first("number_input", timeout=8)
        if inp is None:
            return False

        try:
            _js_click(self.driver, inp)
            inp.send_keys(Keys.CONTROL + "a")
            inp.send_keys(Keys.DELETE)
            time.sleep(0.2)
            inp.send_keys(phone)
        except WebDriverException:
            try:
                self._set_input_value(inp, phone)
            except WebDriverException:
                return False

        time.sleep(0.8)
        called = self._click_first("call_button", timeout=8)
        if called:
            time.sleep(2)
            return True
        try:
            inp.send_keys(Keys.RETURN)
            time.sleep(2)
            return True
        except WebDriverException:
            return False

    # ── Call state detection ──────────────────────────────────────────────────

    def detect_call_state(
        self,
        session: CallSession,
        timeout: float = 90.0,
        poll_interval: float = 0.75,
        confirm_polls: int = 2,
    ) -> CallState:
        """
        Poll DOM until a definitive call state is reached or timeout.
        Uses 5-signal hierarchy from GoogleVoiceAgent-Active.
        Returns final CallState.
        """
        if not self.driver:
            session.transition(CallState.FAILED, "browser not running")
            return CallState.FAILED

        if session.state == CallState.DIALING:
            session.transition(CallState.RINGING, "dialing confirmed, polling")

        deadline         = time.time() + timeout
        ctrl_consecutive = 0

        while time.time() < deadline:
            # Signal 1: Call timer (MM:SS) — most reliable
            if self._call_timer_present():
                if session.state == CallState.RINGING:
                    session.transition(CallState.CONNECTED, "call timer visible")
                return CallState.CONNECTED

            # Signal 2: Answered controls (Hold/Mute/Transfer) with debounce
            ctrl_ok, ctrl_labels = self._answered_controls_present()
            if ctrl_ok:
                ctrl_consecutive += 1
                if ctrl_consecutive >= confirm_polls:
                    if session.state == CallState.RINGING:
                        session.transition(
                            CallState.CONNECTED,
                            f"answered controls ({ctrl_consecutive}x): "
                            + ", ".join(ctrl_labels[:3])
                        )
                    return CallState.CONNECTED
            else:
                ctrl_consecutive = 0

            # Signal 3: Voicemail cues
            if self._voicemail_present():
                if not session.is_terminal():
                    session.transition(CallState.VOICEMAIL, "voicemail detected")
                return CallState.VOICEMAIL

            # Signal 4: Call-ended banner
            if self._any_present("call_ended_banner"):
                if not session.is_terminal():
                    session.transition(CallState.ENDED, "call-ended banner")
                return CallState.ENDED

            # Signal 5: Hangup button vanished while connected
            if (session.state == CallState.CONNECTED
                    and not self._any_present("call_active")):
                session.transition(CallState.ENDED, "hangup button vanished")
                return CallState.ENDED

            time.sleep(poll_interval)

        if not session.is_terminal():
            session.transition(CallState.FAILED, "state detection timeout")
        return CallState.FAILED

    # ── Hangup ────────────────────────────────────────────────────────────────

    def hangup(self) -> bool:
        if not self.driver:
            return False
        try:
            self.driver.switch_to.window(self.driver.current_window_handle)
        except WebDriverException:
            return False

        wait = WebDriverWait(self.driver, 8)
        for sel in _SEL["hangup_button"]:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                _js_click(self.driver, btn)
                time.sleep(1)
                return True
            except (TimeoutException, WebDriverException):
                continue
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
            return True
        except WebDriverException:
            return False

    def is_call_active(self) -> bool:
        return self._any_present("call_active")
