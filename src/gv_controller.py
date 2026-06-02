"""
Google Voice controller — embedded QWebEngineView.
Google Voice runs silently in the background.
No pyautogui, no Selenium, no separate Chrome process.
All control is via JavaScript injection into the embedded browser.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

GV_URL       = "https://voice.google.com"
GV_CALLS_URL = "https://voice.google.com/u/0/calls"

POLL_MS = 800   # state-detection poll interval

# ── JavaScript snippets ───────────────────────────────────────────────────────

_JS_CHECK_LOGIN = """
(function(){
  var url = window.location.href || '';
  var acc = document.querySelector(
    '[aria-label*="Google Account" i], [data-email], img[alt="profile photo"]');
  return (url.indexOf('voice.google.com') !== -1 && !!acc);
})();
"""

_JS_DETECT_STATE = r"""
(function(){
  // 1. Call timer — most reliable proof of CONNECTED
  var timerSels = ['[jsname="pRLmDf"]','.call-duration','[aria-label*="call duration" i]'];
  for(var i=0;i<timerSels.length;i++){
    var el=document.querySelector(timerSels[i]);
    if(el && el.offsetParent && /\d:\d\d/.test(el.textContent)) return 'CONNECTED';
  }
  // 2. Answered controls — only visible after remote party picks up
  var ansCtrl=['button[aria-label*="Hold call" i]','button[aria-label*="Mute call" i]',
               'button[aria-label*="Transfer" i]','button[aria-label*="Add a call" i]'];
  for(var j=0;j<ansCtrl.length;j++){
    var b=document.querySelector(ansCtrl[j]);
    if(b && b.offsetParent) return 'CONNECTED_CTRL';
  }
  // 3. Voicemail cues
  var vmSels=['.voicemail-indicator','[data-e2eid="voicemail-record"]',
              '[aria-label*="leave a message" i]','[title*="leave a message" i]'];
  for(var k=0;k<vmSels.length;k++){
    var v=document.querySelector(vmSels[k]);
    if(v && v.offsetParent) return 'VOICEMAIL';
  }
  var src=(document.body&&document.body.innerText||'').toLowerCase();
  if(src.indexOf('leave a message')!==-1||src.indexOf('record after the tone')!==-1||
     src.indexOf('after the beep')!==-1||src.indexOf('leave a voicemail')!==-1)
    return 'VOICEMAIL';
  // 4. Call-ended banner
  var endedSels=['[aria-label*="Call ended" i]','[data-e2eid="call-ended"]','.call-ended'];
  for(var m=0;m<endedSels.length;m++){
    var e=document.querySelector(endedSels[m]);
    if(e && e.offsetParent) return 'ENDED';
  }
  // 5. Ringing — hangup button visible but no answered controls
  var hangSels=['button[aria-label*="Hang up" i]','button[aria-label*="End call" i]',
                'gv-icon-button[icon-name="call_end"]'];
  for(var n=0;n<hangSels.length;n++){
    var h=document.querySelector(hangSels[n]);
    if(h && h.offsetParent) return 'RINGING';
  }
  return 'IDLE';
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

    def __init__(self, slot_id: int, profile_dir: str, parent: QObject = None,
                 profile_key: str = ""):
        super().__init__(parent)
        self.slot_id     = slot_id
        self.profile_dir = profile_dir
        self._state      = "IDLE"
        self._ctrl_count = 0   # debounce for answered-controls
        self._logged_in  = False

        # ── WebEngine setup ───────────────────────────────────────────────────
        os.makedirs(profile_dir, exist_ok=True)
        cache_dir = os.path.join(profile_dir, "_cache")
        os.makedirs(cache_dir, exist_ok=True)

        key = profile_key or f"slot_{slot_id}"
        key = re.sub(r"[^a-zA-Z0-9_]+", "_", key).strip("_") or f"slot_{slot_id}"
        self._profile = QWebEngineProfile(f"gv_{key}")
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

        self.view = QWebEngineView()
        self.view.setPage(self._page)

        # ── State-poll timer ──────────────────────────────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_MS)
        self._poll_timer.timeout.connect(self._poll_state)

        # ── Login-check timer (runs until logged in) ──────────────────────────
        self._login_timer = QTimer(self)
        self._login_timer.setInterval(2000)
        self._login_timer.timeout.connect(self._check_login)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Navigate to Google Voice. Profile auto-logs in if cookies are present."""
        self._page.load(QUrl(GV_URL))
        self._login_timer.start()
        self._emit_log("Loading Google Voice…")

    def start_polling(self) -> None:
        self._poll_timer.start()

    def stop_polling(self) -> None:
        self._poll_timer.stop()
        self._ctrl_count = 0

    def dial(self, phone: str) -> None:
        self._emit_log(f"Dialing {phone}…")
        self._set_state("DIALING")
        self._page.runJavaScript(_js_dial(phone))
        # Start polling after a short ramp-up
        QTimer.singleShot(4000, self.start_polling)

    def hangup(self) -> None:
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

    # ── Internal ──────────────────────────────────────────────────────────────

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
            self._logged_in = True
            self._login_timer.stop()
            self._emit_log("✅ Google account detected — ready")
            self.login_detected.emit(self.slot_id)

    def _poll_state(self) -> None:
        self._page.runJavaScript(_JS_DETECT_STATE, self._on_poll_result)

    def _on_poll_result(self, raw: str) -> None:
        state = raw or "IDLE"

        # Debounce answered-controls signal (require 2 consecutive polls)
        if state == "CONNECTED_CTRL":
            self._ctrl_count += 1
            state = "CONNECTED" if self._ctrl_count >= 2 else self._state
        else:
            self._ctrl_count = 0

        # Map ENDED back to IDLE after a brief pause
        if state == "ENDED":
            self.stop_polling()
            self._set_state("ENDED")
            QTimer.singleShot(2000, lambda: self._set_state("IDLE"))
            return

        self._set_state(state)

        # Auto-stop polling once a terminal state is reached
        if state in ("VOICEMAIL", "IDLE"):
            self.stop_polling()

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(self.slot_id, state)

    def _emit_log(self, msg: str) -> None:
        self.log_message.emit(self.slot_id, msg)
