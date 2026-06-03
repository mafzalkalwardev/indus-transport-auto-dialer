"""
Google Voice controller — embedded QWebEngineView.
Google Voice runs silently in the background.
No pyautogui, no Selenium, no separate Chrome process.
All control is via JavaScript injection into the embedded browser.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import quote

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

GV_URL       = "https://voice.google.com"
GV_CALLS_URL = "https://voice.google.com/u/0/calls"
from src.gv_accounts import (
    SESSION_MARKER,
    has_session_marker,
    session_marker_path,
)

SIGNIN_URL = (
    "https://accounts.google.com/signin/v2/identifier"
    f"?continue={quote(GV_URL, safe='')}&flowName=GlifWebSignIn"
)

POLL_MS = 1000   # state-detection poll interval (active calls)

_JS_FORCE_VISIBLE = """
(function(){
  try {
    Object.defineProperty(document, 'hidden', {get: function(){ return false; }, configurable: true});
    Object.defineProperty(document, 'visibilityState', {get: function(){ return 'visible'; }, configurable: true});
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('resize'));
  } catch(e) {}
})();
"""

_JS_REFRESH_LAYOUT = """
(function(){
  try {
    window.dispatchEvent(new Event('resize'));
    document.body && document.body.offsetHeight;
  } catch(e) {}
})();
"""

# ── JavaScript snippets ───────────────────────────────────────────────────────

_JS_CHECK_LOGIN = """
(function(){
  var url = window.location.href || '';
  if (url.indexOf('voice.google.com') === -1) return false;
  if (url.indexOf('/signin') !== -1 || url.indexOf('accounts.google.com') !== -1) return false;
  var sels = [
    '[aria-label*="Google Account" i]',
    '[data-email]',
    'img[alt*="profile" i]',
    'a[href*="Sign out" i]',
    'button[aria-label*="Account" i]',
    'gv-account-switcher',
    '[data-ogsr-up]'
  ];
  for (var i = 0; i < sels.length; i++) {
    if (document.querySelector(sels[i])) return true;
  }
  var t = (document.body && document.body.innerText || '').toLowerCase();
  if (t.indexOf('sign in') !== -1 && t.indexOf('google voice') !== -1) return false;
  return document.querySelector('nav, gv-side-panel, [role="navigation"]') !== null;
})();
"""


def write_session_marker(profile_dir: str) -> None:
    os.makedirs(profile_dir, exist_ok=True)
    with open(session_marker_path(profile_dir), "w", encoding="utf-8") as f:
        f.write(datetime.now().isoformat())


_JS_DETECT_STATE = r"""
(function(){
  function vis(el){
    if(!el) return false;
    var s=window.getComputedStyle(el), r=el.getBoundingClientRect();
    return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
  }
  function txt(){
    return (document.body&&document.body.innerText||'').toLowerCase();
  }
  function q(root, sel){
    try { return (root || document).querySelector(sel); } catch(e) { return null; }
  }
  var body=txt();
  var inCall=false;
  var activeRoot=null;
  var hangSels=['button[aria-label*="Hang up" i]','button[aria-label*="End call" i]',
    'button[title*="Hang up" i]','gv-icon-button[icon-name="call_end"]',
    '[data-action="end-call"]','button.end-call'];
  for(var h=0;h<hangSels.length;h++){
    var hang=document.querySelector(hangSels[h]);
    if(vis(hang)){
      inCall=true;
      activeRoot=hang.closest('[role="dialog"],gv-call-panel,gv-call-widget,gv-in-call-panel,.call-panel,.in-call,body')||document.body;
      break;
    }
  }
  if(!inCall) return 'IDLE';
  var callText=((activeRoot&&activeRoot.innerText)||'').toLowerCase();

  // 1. Voicemail — check before ringing/connected (VM also shows hangup)
  var vmPhrases=['leave a message','record after the tone','record your message',
    'after the beep','leave a voicemail','voicemail box','not available to take',
    'cannot take your call',"can't take your call",'at the tone','mailbox is full',
    'forwarded to voicemail','has been forwarded','started recording',
    'person you are calling','reach is not available','no one is available'];
  for(var p=0;p<vmPhrases.length;p++){
    if(callText.indexOf(vmPhrases[p])!==-1) return 'VOICEMAIL';
  }
  var vmSels=['.voicemail-indicator','[data-e2eid="voicemail-record"]',
    '[aria-label*="leave a message" i]','[aria-label*="voicemail" i]',
    '[title*="leave a message" i]','[data-tooltip*="voicemail" i]'];
  for(var v=0;v<vmSels.length;v++){
    var vm=q(activeRoot, vmSels[v]);
    if(vis(vm)) return 'VOICEMAIL';
  }

  // 2. Live answer — MM:SS call timer (strict) or answered-call controls
  var timerSels=['[jsname="pRLmDf"]','.call-duration','[aria-label*="call duration" i]',
    '[data-e2eid="call-timer"]'];
  for(var t=0;t<timerSels.length;t++){
    var el=q(activeRoot, timerSels[t]);
    if(!vis(el)) continue;
    var tx=(el.textContent||el.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
    if(/^(?:\d{1,2}:)?\d{1,2}:\d{2}$/.test(tx)) return 'CONNECTED';
    if(/^\d{1,2}:\d{2}$/.test(tx)) return 'CONNECTED';
  }
  var ansCtrl=['button[aria-label*="Hold call" i]','button[aria-label*="Mute call" i]',
    'button[aria-label*="Unmute call" i]','button[aria-label*="Transfer" i]',
    'button[aria-label*="Add a call" i]','button[aria-label*="Record the call" i]',
    'button[aria-label*="Send a message" i]'];
  for(var a=0;a<ansCtrl.length;a++){
    var btn=q(activeRoot, ansCtrl[a]);
    if(vis(btn)) return 'CONNECTED_CTRL';
  }

  // 3. Call ended
  var endedSels=['[aria-label*="Call ended" i]','[data-e2eid="call-ended"]','.call-ended'];
  for(var e=0;e<endedSels.length;e++){
    var end=q(activeRoot, endedSels[e]);
    if(vis(end)) return 'ENDED';
  }

  // 4. Ringing / calling (before pickup)
  if(callText.indexOf('ringing')!==-1||callText.indexOf('calling')!==-1){
    return 'RINGING';
  }
  var ringSels=['[aria-label*="Ringing" i]','[aria-label*="Calling" i]'];
  for(var r=0;r<ringSels.length;r++){
    var rg=q(activeRoot, ringSels[r]);
    if(vis(rg)) return 'RINGING';
  }

  // In-call but unknown — treat as ringing until timer/VM/controls appear
  return 'RINGING';
})();
"""

_JS_HANGUP = """
(function(){
  var sels=['button[aria-label*="Hang up" i]','button[aria-label*="End call" i]',
            'button[title*="Hang up" i]','gv-icon-button[icon-name="call_end"]',
            '[data-action="end-call"]'];
  for(var i=0;i<sels.length;i++){
    var btn=document.querySelector(sels[i]);
    if(btn){ btn.click(); return 'hung_up'; }
  }
  return 'not_found';
})();
"""


def _js_autofill_login(email: str, password: str) -> str:
    email_js = json.dumps(email)
    password_js = json.dumps(password)
    return f"""
(function(){{
  const email = {email_js};
  const password = {password_js};
  const url = window.location.href || '';

  if (!/accounts\\.google\\.com|signin|ServiceLogin/i.test(url)) {{
    return 'not_login_page';
  }}

  const visible = el => {{
    if (!el) return false;
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' &&
           r.width > 0 && r.height > 0;
  }};

  const setNativeVal = (el, val) => {{
    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    el.focus();
    if (setter) setter.call(el, val); else el.value = val;
    el.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:val}}));
    el.dispatchEvent(new Event('change', {{bubbles:true}}));
    el.dispatchEvent(new KeyboardEvent('keyup', {{bubbles:true, key:'a'}}));
  }};

  const clickNext = () => {{
    const candidates = [
      '#identifierNext button', '#passwordNext button',
      'button[jsname="LgbsSe"]', 'div[role="button"][jsname="LgbsSe"]',
      'button[type="button"]', 'button'
    ];
    for (const sel of candidates) {{
      for (const btn of document.querySelectorAll(sel)) {{
        const txt = (btn.innerText || btn.textContent || '').toLowerCase();
        if (visible(btn) && !btn.disabled &&
            (txt.includes('next') || btn.closest('#identifierNext,#passwordNext'))) {{
          btn.click();
          return true;
        }}
      }}
    }}
    return false;
  }};

  const challengeText = (document.body?.innerText || '').toLowerCase();
  if (challengeText.includes('2-step verification') ||
      challengeText.includes('verify it') ||
      challengeText.includes('couldn\\'t verify') ||
      challengeText.includes('captcha') ||
      challengeText.includes('recovery email')) {{
    return 'security_step_required';
  }}

  const clickUsePassword = () => {{
    const nodes = document.querySelectorAll(
      'button, a, div[role="button"], span[role="link"], li[role="link"]');
    for (const el of nodes) {{
      const t = (el.innerText || el.textContent || '').toLowerCase();
      if (t.includes('enter your password') || t.includes('use your password') ||
          t.includes('use password instead') || t === 'password' ||
          (t.includes('try another way') && !t.includes('passkey'))) {{
        el.click();
        return true;
      }}
    }}
    return false;
  }};

  if (challengeText.includes('passkey') ||
      challengeText.includes('security key') ||
      challengeText.includes('choose a passkey') ||
      challengeText.includes('use your passkey')) {{
    if (clickUsePassword()) return 'use_password_clicked';
    return 'passkey_step_paused';
  }}

  const pass = Array.from(document.querySelectorAll(
    'input[type="password"], input[name="Passwd"]')).find(visible);
  if (pass) {{
    if (!password) return 'password_missing';
    if (pass.value !== password) setNativeVal(pass, password);
    return clickNext() ? 'password_submitted' : 'password_filled';
  }}

  if (challengeText.includes('welcome') && email &&
      challengeText.includes(email.toLowerCase())) {{
    if (!password) return 'password_missing';
    if (clickUsePassword()) return 'use_password_clicked';
    return 'welcome_need_password';
  }}

  const ident = Array.from(document.querySelectorAll(
    'input[type="email"], input[name="identifier"], #identifierId')).find(visible);
  if (ident) {{
    if (!email) return 'email_missing';
    const cur = (ident.value || '').trim().toLowerCase();
    if (cur !== email.toLowerCase()) setNativeVal(ident, email);
    if (cur === email.toLowerCase() && challengeText.includes('welcome')) {{
      return 'welcome_need_password';
    }}
    return clickNext() ? 'email_submitted' : 'email_filled';
  }}

  return 'waiting_for_login_fields';
}})();
"""


def _js_dial(phone: str) -> str:
    """Build the JS dial sequence for a given E.164 phone number."""
    safe = phone.replace("'", "")
    return f"""
(function(){{
  var phone='{safe}';

  function setNativeVal(el,val){{
    try{{
      var proto=el.tagName==='TEXTAREA'
        ?window.HTMLTextAreaElement.prototype
        :window.HTMLInputElement.prototype;
      var setter=Object.getOwnPropertyDescriptor(proto,'value').set;
      el.focus(); setter.call(el,val);
    }}catch(e){{ el.value=val; }}
    el.dispatchEvent(new Event('input',{{bubbles:true}}));
    el.dispatchEvent(new Event('change',{{bubbles:true}}));
  }}

  function tryCall(){{
    var sels=['button[aria-label*="call" i]:not([aria-label*="end" i]):not([aria-label*="video" i])',
              'gv-icon-button[icon-name="call"]','[data-action="call"]'];
    for(var i=0;i<sels.length;i++){{
      var btn=document.querySelector(sels[i]);
      if(btn&&!btn.disabled){{ btn.click(); return; }}
    }}
    // fallback: Enter key on input
    var inp=document.querySelector('input[aria-label*="number" i],input[placeholder*="number" i]');
    if(inp) inp.dispatchEvent(new KeyboardEvent('keydown',{{key:'Enter',keyCode:13,bubbles:true}}));
  }}

  function fillAndCall(){{
    var inp=document.querySelector('input[aria-label*="number" i],input[placeholder*="number" i]');
    if(!inp){{ setTimeout(fillAndCall,800); return; }}
    setNativeVal(inp,phone);
    setTimeout(tryCall,700);
  }}

  function openDialpad(){{
    var inp=document.querySelector('input[aria-label*="number" i],input[placeholder*="number" i]');
    if(inp){{ fillAndCall(); return; }}
    var dpSels=['button[aria-label*="keypad" i]','button[aria-label*="dialpad" i]',
                'gv-new-conversation-fab','[data-action="new-call"]',
                'button[aria-label*="new call" i]'];
    for(var i=0;i<dpSels.length;i++){{
      var btn=document.querySelector(dpSels[i]);
      if(btn){{ btn.click(); setTimeout(fillAndCall,1200); return; }}
    }}
    setTimeout(openDialpad,1000);
  }}

  // Ensure we are on the calls page
  if(window.location.pathname.indexOf('/calls')===-1){{
    window.location.href='https://voice.google.com/u/0/calls';
    setTimeout(openDialpad,3000);
  }} else {{
    openDialpad();
  }}
}})();
"""


# ── GVController ──────────────────────────────────────────────────────────────

class GVController(QObject):
    """
    Manages one embedded Google Voice browser instance.
    All automation via JavaScript — zero screen coordinates.
    Profile is persistent — login survives app restarts.
    """

    # ── Signals ───────────────────────────────────────────────────────────────
    state_changed    = pyqtSignal(int, str)   # (slot_id, state)
    login_detected   = pyqtSignal(int)         # slot_id
    log_message      = pyqtSignal(int, str)    # (slot_id, msg)
    heartbeat        = pyqtSignal(int)         # slot_id — poll / page alive

    def __init__(self, slot_id: int, profile_dir: str, parent: QObject = None,
                 profile_key: str = "", login_email: str = "",
                 login_password: str = ""):
        super().__init__(parent)
        self.slot_id     = slot_id
        self.profile_dir = profile_dir
        self._state      = "IDLE"
        self._ctrl_count = 0   # debounce for answered-controls
        self._logged_in  = False
        self._login_email = login_email
        self._login_password = login_password
        self._last_login_fill_status = ""

        # ── WebEngine setup ───────────────────────────────────────────────────
        os.makedirs(profile_dir, exist_ok=True)
        cache_dir = os.path.join(profile_dir, "_cache")
        os.makedirs(cache_dir, exist_ok=True)

        key = profile_key or f"slot_{slot_id}"
        key = re.sub(r"[^a-zA-Z0-9_]+", "_", key).strip("_") or f"slot_{slot_id}"
        # Unique in-process name; cookies/session live in profile_dir on disk.
        self._profile = QWebEngineProfile(f"gv_{key}_{uuid.uuid4().hex[:8]}")
        self._profile.setPersistentStoragePath(profile_dir)
        self._profile.setCachePath(cache_dir)
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )

        self._page = QWebEnginePage(self._profile)
        self._page.featurePermissionRequested.connect(self._grant_permission)

        # Disable JS console noise appearing in our log
        self._page.javaScriptConsoleMessage = lambda *_: None

        settings = self._page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)

        self.view = QWebEngineView()
        self.view.setPage(self._page)
        self._page.setBackgroundColor(QColor("#ffffff"))
        self.view.setStyleSheet("background-color: #ffffff;")
        self._load_ok = False
        self._page.loadStarted.connect(self._on_load_started)
        self._page.loadFinished.connect(self._on_load_finished_page)
        if has_session_marker(profile_dir):
            self._logged_in = True

        # ── State-poll timer ──────────────────────────────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_MS)
        self._poll_timer.timeout.connect(self._poll_state)

        # ── Login-check timer (runs until logged in) ──────────────────────────
        self._login_timer = QTimer(self)
        self._login_timer.setInterval(2000)
        self._login_timer.timeout.connect(self._check_login)

        self._login_fill_timer = QTimer(self)
        self._login_fill_timer.setInterval(1200)
        self._login_fill_timer.timeout.connect(self._try_auto_login)

        self._setup_mode = False
        self._redirected_to_signin = False
        self._autofill_paused = False
        self._email_step_done = False
        self._vm_count = 0
        self._idle_count = 0
        self._active_call = False
        self._dial_started_at = 0.0
        self._dial_stuck_timer: QTimer | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def clear_http_cache(self) -> None:
        """Reduce WebEngine disk/memory pressure between long campaigns."""
        if getattr(self, "_page", None) is None:
            return
        try:
            self._profile.clearHttpCache()
        except Exception:
            pass

    def shutdown(self) -> None:
        """
        Stop timers and destroy page before view/profile so Qt does not warn:
        'Release of profile requested but WebEnginePage still not deleted'.
        """
        self._poll_timer.stop()
        self._login_timer.stop()
        self._login_fill_timer.stop()
        if self._dial_stuck_timer is not None:
            self._dial_stuck_timer.stop()
            self._dial_stuck_timer = None
        self._active_call = False

        page = getattr(self, "_page", None)
        view = getattr(self, "view", None)
        if view is not None:
            try:
                view.setPage(None)
            except Exception:
                pass
        if page is not None:
            page.deleteLater()
            self._page = None  # type: ignore[assignment]
        if view is not None:
            view.deleteLater()
            self.view = None  # type: ignore[assignment]

    def _page_alive(self) -> bool:
        return getattr(self, "_page", None) is not None

    def _pulse_heartbeat(self) -> None:
        self.heartbeat.emit(self.slot_id)

    def prepare_for_visible_display(self) -> None:
        """
        After reparenting from the 1×1 hidden host, force WebEngine to repaint
        and tell Google Voice the tab is visible (needed for audio + UI).
        """
        if not self._page_alive():
            return
        self.view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        self.view.show()
        self.view.updateGeometry()
        self.view.repaint()
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        QTimer.singleShot(80, lambda: self._page.runJavaScript(_JS_FORCE_VISIBLE))
        QTimer.singleShot(200, lambda: self._page.runJavaScript(_JS_REFRESH_LAYOUT))
        QTimer.singleShot(400, lambda: self.view.repaint())

    def load(self, for_setup: bool = False) -> None:
        """Navigate to Google Voice. Profile auto-logs in if cookies are present."""
        if not self._page_alive():
            return
        self._setup_mode = for_setup
        self._load_ok = False
        if for_setup:
            self._redirected_to_signin = False
            self._autofill_paused = False
            self._email_step_done = False
            self._last_login_fill_status = ""
            self._page.load(QUrl(SIGNIN_URL))
            self._emit_log("Opening Google sign-in…")
        else:
            self._page.load(QUrl(GV_URL))
            self._emit_log("Loading Google Voice…")
        self._login_timer.start()
        self._schedule_autofill()

    def load_setup_signin(self) -> None:
        """Open Google sign-in directly (setup wizard)."""
        self.load(for_setup=True)

    def set_login_credentials(self, email: str = "", password: str = "") -> None:
        self._login_email = email
        self._login_password = password
        self._last_login_fill_status = ""
        self._autofill_paused = False
        if email or password:
            self._schedule_autofill()

    def _schedule_autofill(self) -> None:
        if not (self._login_email or self._login_password):
            return
        if not self._login_fill_timer.isActive():
            self._login_fill_timer.start()

    def _pause_autofill(self, seconds: float = 0) -> None:
        self._login_fill_timer.stop()
        if seconds > 0 and not self._logged_in:
            QTimer.singleShot(int(seconds * 1000), self._schedule_autofill)

    def _stop_autofill(self) -> None:
        self._autofill_paused = True
        self._login_fill_timer.stop()

    def start_polling(self) -> None:
        self._poll_timer.start()

    def stop_polling(self) -> None:
        self._poll_timer.stop()
        self._ctrl_count = 0
        self._vm_count = 0
        self._idle_count = 0
        self._active_call = False

    def dial(self, phone: str) -> None:
        if not self._page_alive():
            return
        self._emit_log(f"Dialing {phone}…")
        self._active_call = True
        self._dial_started_at = time.monotonic()
        self._vm_count = 0
        self._idle_count = 0
        self._ctrl_count = 0
        self._set_state("DIALING")
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        self._page.runJavaScript(_js_dial(phone))
        # Poll early and often while headless (DOM still updates)
        QTimer.singleShot(800, self._poll_once)
        QTimer.singleShot(1600, self._poll_once)
        QTimer.singleShot(2400, self.start_polling)
        if self._dial_stuck_timer is not None:
            self._dial_stuck_timer.stop()
        self._dial_stuck_timer = QTimer(self)
        self._dial_stuck_timer.setSingleShot(True)
        self._dial_stuck_timer.setInterval(35000)
        self._dial_stuck_timer.timeout.connect(self._on_dial_stuck)
        self._dial_stuck_timer.start()

    def _on_dial_stuck(self) -> None:
        if self._active_call and self._state == "DIALING":
            self._emit_log("Dial did not progress — marked failed")
            self._active_call = False
            self.stop_polling()
            self._set_state("FAILED")

    def _poll_once(self) -> None:
        if self._active_call:
            self._poll_state()

    def hangup(self) -> None:
        if not self._page_alive():
            return
        self._active_call = False
        self._page.runJavaScript(_JS_HANGUP, lambda r: self._emit_log(
            f"Hangup: {r}"))
        self.stop_polling()
        QTimer.singleShot(1000, lambda: self._set_state("IDLE"))

    def run_js(self, js: str,
               callback: Optional[Callable] = None) -> None:
        if callback:
            self._page.runJavaScript(js, callback)
        else:
            self._page.runJavaScript(js)

    @property
    def current_state(self) -> str:
        return self._state

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    def is_session_ready(self) -> bool:
        return self._logged_in or has_session_marker(self.profile_dir)

    def mark_logged_in(self) -> None:
        """Persist login success for this profile (survives controller recreation)."""
        self._logged_in = True
        write_session_marker(self.profile_dir)
        self._login_timer.stop()
        self._login_fill_timer.stop()
        self._stop_autofill()
        self._emit_log("Google Voice session saved")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_load_started(self) -> None:
        self._load_ok = False

    def _on_load_finished_page(self, ok: bool) -> None:
        self._load_ok = ok
        self._pulse_heartbeat()
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        if ok:
            QTimer.singleShot(400, self._try_auto_login)
            QTimer.singleShot(800, self._check_login)
            if self._setup_mode:
                QTimer.singleShot(1200, self._maybe_redirect_signin)
        else:
            self._emit_log("Page failed to load — click Reload")

    def _grant_permission(self, url, feature) -> None:
        """Auto-grant mic + camera permissions so GV calls work."""
        self._page.setFeaturePermission(
            url, feature,
            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
        )

    def _check_login(self) -> None:
        self._page.runJavaScript(_JS_CHECK_LOGIN, self._on_login_check)

    def _on_login_check(self, logged_in: bool) -> None:
        if logged_in and not self._logged_in:
            self.mark_logged_in()
            self._emit_log("Google account detected — ready")
            self.login_detected.emit(self.slot_id)

    def _try_auto_login(self) -> None:
        if (self._logged_in or self._autofill_paused
                or not (self._login_email or self._login_password)):
            return
        self._page.runJavaScript(
            _js_autofill_login(self._login_email, self._login_password),
            self._on_auto_login_result,
        )

    def _on_auto_login_result(self, status: str) -> None:
        if not status:
            return
        if status == self._last_login_fill_status:
            return
        self._last_login_fill_status = status
        if status == "not_login_page" and self._setup_mode:
            self._maybe_redirect_signin()
            return
        if status == "email_submitted":
            self._email_step_done = True
            self._emit_log("Email submitted — waiting for password step…")
            self._pause_autofill(3.5)
        elif status == "password_submitted":
            self._emit_log("Password submitted — finishing sign-in…")
            self._pause_autofill(5.0)
        elif status == "password_filled":
            self._emit_log("Password filled — click Next if needed")
            self._pause_autofill(2.0)
        elif status == "use_password_clicked":
            self._emit_log("Switched to password sign-in…")
            self._pause_autofill(2.5)
        elif status == "welcome_need_password":
            if self._login_password:
                self._emit_log("Use password sign-in — trying password option…")
                self._pause_autofill(2.0)
            else:
                self._emit_log("Password required — enter it below and click Apply")
                self._stop_autofill()
        elif status in ("passkey_step_paused", "security_step_required"):
            self._emit_log(
                "Complete sign-in manually in the browser (passkey / 2FA / CAPTCHA)."
            )
            self._stop_autofill()
        elif status in ("password_missing", "email_missing"):
            self._emit_log(
                f"Need saved {'password' if status == 'password_missing' else 'email'} "
                "— use the field below, then Apply."
            )
            self._stop_autofill()
        elif status == "waiting_for_login_fields" and self._setup_mode:
            if not self._email_step_done:
                self._maybe_redirect_signin()

    _JS_NEEDS_SIGNIN = """
(function(){
  var url = window.location.href || '';
  if (/voice\\.google\\.com/i.test(url)) {
    var acc = document.querySelector(
      '[aria-label*="Google Account" i], [data-email], img[alt="profile photo"]');
    if (!acc) return true;
    return false;
  }
  if (!/accounts\\.google\\.com|signin|ServiceLogin/i.test(url)) return true;
  return false;
})();
"""

    def _maybe_redirect_signin(self) -> None:
        if self._logged_in or self._redirected_to_signin or not self._setup_mode:
            return
        self._page.runJavaScript(self._JS_NEEDS_SIGNIN, self._on_needs_signin)

    def _on_needs_signin(self, needs: bool) -> None:
        if not needs or self._logged_in or self._redirected_to_signin:
            return
        self._redirected_to_signin = True
        self._emit_log("Opening Google sign-in page…")
        self._page.load(QUrl("https://accounts.google.com/"))

    def _poll_state(self) -> None:
        if not self._page_alive():
            return
        self._page.runJavaScript(_JS_DETECT_STATE, self._on_poll_result)

    def _on_poll_result(self, raw: str) -> None:
        self._pulse_heartbeat()
        state = raw or "IDLE"

        if state == "IDLE" and self._active_call:
            self._idle_count += 1
            age = time.monotonic() - self._dial_started_at
            if age < 6.0 or self._idle_count < 3:
                state = self._state if self._state != "IDLE" else "DIALING"
            else:
                self._emit_log("Call UI disappeared before answer")
        else:
            self._idle_count = 0

        # Debounce voicemail (avoid false positive while ringing)
        if state == "VOICEMAIL":
            self._vm_count += 1
            if self._vm_count < 2:
                state = self._state if self._state != "IDLE" else "RINGING"
            else:
                self._emit_log("Voicemail detected")
        else:
            self._vm_count = 0

        # Debounce answered-controls (require 2 consecutive polls)
        if state == "CONNECTED_CTRL":
            self._ctrl_count += 1
            state = "CONNECTED" if self._ctrl_count >= 2 else self._state
        else:
            self._ctrl_count = 0

        if state == "CONNECTED" and self._state != "CONNECTED":
            self._emit_log("Live answer detected — person answered")

        # Promote DIALING → RINGING when in-call UI appears
        if state == "RINGING" and self._state == "DIALING":
            self._emit_log("Ringing…")

        # Map ENDED back to IDLE after a brief pause
        if state == "ENDED":
            self.stop_polling()
            self._set_state("ENDED")
            QTimer.singleShot(2000, lambda: self._set_state("IDLE"))
            return

        self._set_state(state)

        # Auto-stop polling once a terminal state is reached
        if state == "VOICEMAIL":
            self.stop_polling()
        elif state == "IDLE" and not self._active_call:
            self.stop_polling()

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(self.slot_id, state)
            self._pulse_heartbeat()
        if state != "DIALING" and self._dial_stuck_timer is not None:
            self._dial_stuck_timer.stop()

    def _emit_log(self, msg: str) -> None:
        self.log_message.emit(self.slot_id, msg)
