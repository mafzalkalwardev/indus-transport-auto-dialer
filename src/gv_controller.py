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

GV_URL       = "https://voice.google.com/u/0/calls"
GV_CALLS_URL = GV_URL
from src.call_state_engine import CallStateEngine
from src.call_audio_monitor import CallAudioMonitor
from src.call_decision_engine import CallDecisionEngine
from src.local_call_detector import DetectionConfig
from src.gv_accounts import (
    SESSION_MARKER,
    has_session_marker,
    session_marker_path,
)
from src.paths import CONFIG_FILE

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
  function out(state, extra){
    var e = extra || {};
    e.state = state;
    e.callText = e.callText || callText || '';
    e.hasRingingText = !!e.hasRingingText;
    e.hasRingingNode = !!e.hasRingingNode;
    e.hasTimer = !!e.hasTimer;
    e.hasEnabledAnswerControl = !!e.hasEnabledAnswerControl;
    e.hasVoicemailCue = !!e.hasVoicemailCue;
    return e;
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
  var callText='';
  if(!inCall) return out('IDLE', {callText: body});
  callText=((activeRoot&&activeRoot.innerText)||'')
    .toLowerCase()
    .replace(/[’']/g, "'")
    .replace(/\s+/g, ' ')
    .trim();

  // 1. Voicemail — check before ringing/connected (VM also shows hangup)
  var vmPhrases=[
    'leave a message','leave your message','leave your name and number',
    'leave your name, number','reason for call','record after the tone',
    'record your message','after the beep','at the tone','after the tone',
    'press pound when finished','press # when finished','leave a voicemail',
    'voicemail box','mailbox is full','your call has been forwarded',
    'forwarded to voicemail','has been forwarded','started recording',
    'please record your message','please leave your message',
    'please leave a message','please leave a message for',
    'i am not available','i am unavailable','i am not available right now',
    "i'm not available","i'm unavailable","can't come to the phone",
    'cannot come to the phone','i will call you back',"i'll call you back",
    'call you back as soon as','you have reached','you have reached the voicemail',
    'not available to take','cannot take your call',"can't take your call",
    'person you are calling is not available',
    'person you are calling is currently unavailable',
    'person you are calling cannot be reached',
    'wireless customer you are calling is not available',
    'subscriber you are trying to reach is not in service',
    'subscriber is not reachable','reach is not available',
    'user is not accepting calls','no one is available',
    'number you have dialed is not in service',
    'number is temporarily unavailable','temporarily unavailable',
    'number you have reached has been disconnected',
    'number has been disconnected','not in service',
    'out of service','call cannot be completed as dialed',
    'cannot be completed as dialed','phone you are calling is switched off',
    'switched off','please try your call again later'
  ];
  for(var p=0;p<vmPhrases.length;p++){
    if(callText.indexOf(vmPhrases[p])!==-1) {
      return out('VOICEMAIL', {hasVoicemailCue:true, voicemailMatch:vmPhrases[p]});
    }
  }
  var vmPatterns=[
    /hi[, ]+this is .{0,60}(not available|unavailable|leave)/i,
    /this is .{0,60}(voicemail|not available|unavailable|leave)/i,
    /leave .{0,40}(name|number|message|reason)/i,
    /(after|at) the (tone|beep).{0,80}(record|leave|message)/i,
    /(record|leave).{0,80}(message|voicemail).{0,80}(tone|beep|pound|#)/i,
    /(call|try).{0,30}(again|back).{0,30}(later|soon)/i
  ];
  for(var rp=0;rp<vmPatterns.length;rp++){
    if(vmPatterns[rp].test(callText)) {
      return out('VOICEMAIL', {hasVoicemailCue:true, voicemailMatch:String(vmPatterns[rp])});
    }
  }
  var vmSels=['.voicemail-indicator','[data-e2eid="voicemail-record"]',
    '[aria-label*="leave a message" i]','[aria-label*="voicemail" i]',
    '[title*="leave a message" i]','[data-tooltip*="voicemail" i]'];
  for(var v=0;v<vmSels.length;v++){
    var vm=q(activeRoot, vmSels[v]);
    if(vis(vm)) return out('VOICEMAIL', {hasVoicemailCue:true, voicemailMatch:vmSels[v]});
  }

  var hasRingingText = (
    callText.indexOf('ringing')!==-1 || callText.indexOf('calling')!==-1 ||
    callText.indexOf('connecting')!==-1 ||
    callText.indexOf('trying to connect')!==-1
  );
  var hasRingingNode = false;
  var ringSels=['[aria-label*="Ringing" i]','[aria-label*="Calling" i]',
    '[aria-label*="Connecting" i]'];
  for(var r=0;r<ringSels.length;r++){
    var rg=q(activeRoot, ringSels[r]);
    if(vis(rg)) { hasRingingNode = true; break; }
  }

  // 2. Live answer — MM:SS call timer (strict).
  // Some GV panels keep stale "calling" text after pickup, so answer signals
  // must be allowed to override ringing text.
  var timerSels=['[jsname="pRLmDf"]','.call-duration','[aria-label*="call duration" i]',
    '[data-e2eid="call-timer"]'];
  for(var t=0;t<timerSels.length;t++){
    var el=q(activeRoot, timerSels[t]);
    if(!vis(el)) continue;
    var tx=(el.textContent||el.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
    if(/^(?:\d{1,2}:)?\d{1,2}:\d{2}$/.test(tx)) {
      return out('CONNECTED', {hasTimer:true, timerText:tx, hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
    }
    if(/^\d{1,2}:\d{2}$/.test(tx)) {
      return out('CONNECTED', {hasTimer:true, timerText:tx, hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
    }
  }

  // 3. Ringing / calling (before pickup). Do this before checking call
  // controls because GV displays disabled controls while still calling.
  if(hasRingingText || hasRingingNode) {
    return out('RINGING', {hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
  }

  var ansCtrl=['button[aria-label*="Hold call" i]','button[aria-label*="Mute call" i]',
    'button[aria-label*="Unmute call" i]','button[aria-label*="Transfer" i]'];
  for(var a=0;a<ansCtrl.length;a++){
    var btn=q(activeRoot, ansCtrl[a]);
    if(vis(btn) && !btn.disabled && btn.getAttribute('aria-disabled')!=='true') {
      return out('CONNECTED_CTRL', {hasEnabledAnswerControl:true, answerControl:ansCtrl[a]});
    }
  }

  // 4. Call ended
  var endedSels=['[aria-label*="Call ended" i]','[data-e2eid="call-ended"]','.call-ended'];
  for(var e=0;e<endedSels.length;e++){
    var end=q(activeRoot, endedSels[e]);
    if(vis(end)) return out('ENDED', {endedCue:endedSels[e]});
  }

  // In-call but unknown — treat as ringing until timer/VM/controls appear
  return out('RINGING', {hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
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
    ['keydown','keypress','input','keyup','change'].forEach(function(type){{
      el.dispatchEvent(new Event(type,{{bubbles:true}}));
    }});
  }}

  function visible(el){{
    if(!el) return false;
    var r=el.getBoundingClientRect(), s=getComputedStyle(el);
    return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
  }}

  function findNumberInput(){{
    var inputs=Array.from(document.querySelectorAll('input,textarea'));
    for(var i=0;i<inputs.length;i++){{
      var el=inputs[i];
      var aria=(el.getAttribute('aria-label')||'').toLowerCase();
      var ph=(el.getAttribute('placeholder')||'').toLowerCase();
      if(!visible(el) || el.disabled) continue;
      if(aria.indexOf('number')!==-1 || ph.indexOf('number')!==-1 ||
         ph.indexOf('name')!==-1) return el;
    }}
    return null;
  }}

  function findCallButton(){{
    var buttons=Array.from(document.querySelectorAll('button,[role="button"],gv-icon-button'));
    for(var i=0;i<buttons.length;i++){{
      var btn=buttons[i];
      var aria=(btn.getAttribute('aria-label')||'').toLowerCase();
      var text=(btn.innerText||btn.textContent||'').trim().toLowerCase();
      if(!visible(btn) || btn.disabled) continue;
      if(aria.indexOf('end')!==-1 || aria.indexOf('video')!==-1) continue;
      if(aria.indexOf('call +')===0 || (text==='call' && aria.indexOf('call')===0)){{
        return btn;
      }}
    }}
    return null;
  }}

  function openDialpadIfNeeded(){{
    if(findNumberInput()) return true;
    var dpSels=['button[aria-label*="keypad" i]','button[aria-label*="dialpad" i]',
                'gv-new-conversation-fab','[data-action="new-call"]',
                'button[aria-label*="new call" i]','button[aria-label*="make a call" i]'];
    for(var i=0;i<dpSels.length;i++){{
      var btn=document.querySelector(dpSels[i]);
      if(btn && visible(btn) && !btn.disabled){{ btn.click(); return false; }}
    }}
    return false;
  }}

  openDialpadIfNeeded();
  var inp=findNumberInput();
  if(!inp){{ window.__gvDialStatus='number_input_missing'; return window.__gvDialStatus; }}

  setNativeVal(inp,phone);
  var digits=phone.replace(/\\D/g,'');
  var current=(inp.value||'').replace(/\\D/g,'');
  if(current.indexOf(digits)===-1 && digits.indexOf(current)===-1){{
    window.__gvDialStatus='number_not_entered';
    return window.__gvDialStatus;
  }}

  var btn=findCallButton();
  if(!btn){{
    var anyCall=Array.from(document.querySelectorAll('button,[role="button"],gv-icon-button')).filter(function(b){{
      var aria=(b.getAttribute('aria-label')||'').toLowerCase();
      var text=(b.innerText||b.textContent||'').trim().toLowerCase();
      return visible(b) && (aria.indexOf('call')!==-1 || text==='call');
    }})[0];
    window.__gvDialStatus = anyCall && anyCall.disabled ? 'call_button_disabled' : 'call_button_missing';
    return window.__gvDialStatus;
  }}
  btn.click();
  window.__gvDialStatus='call_button_clicked';
  return window.__gvDialStatus;
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

    detection_update = pyqtSignal(int, dict)   # (slot_id, debug)

    def __init__(self, slot_id: int, profile_dir: str, parent: QObject = None,
                 profile_key: str = "", login_email: str = "",
                 login_password: str = ""):
        super().__init__(parent)
        self.slot_id     = slot_id
        self.profile_dir = profile_dir
        self._state      = "IDLE"
        self._ctrl_count = 0   # debounce for answered-controls
        self._call_state_engine = CallStateEngine()
        self._runtime_cfg = self._load_runtime_cfg()
        audio_enabled = bool(self._runtime_cfg.get("enable_ai_audio", True))
        self._decision_engine = CallDecisionEngine(
            detector_config=DetectionConfig(
                max_ring_seconds=float(self._runtime_cfg.get("call_timeout", 60)),
                enable_audio_detection=audio_enabled,
            )
        )
        self._audio_monitor = CallAudioMonitor(
            enabled=audio_enabled,
            device=self._runtime_cfg.get("audio_device", None),
        )
        self._logged_in  = False
        self._login_email = login_email
        self._login_password = login_password
        self._last_login_fill_status = ""
        self._login_required_logged = False

        # ── WebEngine setup ───────────────────────────────────────────────────
        os.makedirs(profile_dir, exist_ok=True)
        cache_dir = os.path.join(profile_dir, f"_cache_{uuid.uuid4().hex[:8]}")
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
        self._page.setAudioMuted(True)

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
        self._pending_dial_phone = ""
        self._dial_step_attempts = 0
        self._call_clicked_at = 0.0
        self._min_answer_seconds = 10.0

    # ── Public API ────────────────────────────────────────────────────────────

    @staticmethod
    def _load_runtime_cfg() -> dict:
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

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

    def set_audio_muted(self, muted: bool) -> None:
        if not self._page_alive():
            return
        self._page.setAudioMuted(muted)

    def load(self, for_setup: bool = False) -> None:
        """Navigate to Google Voice. Profile auto-logs in if cookies are present."""
        if not self._page_alive():
            return
        self._setup_mode = for_setup
        self._load_ok = False
        if for_setup:
            self._redirected_to_signin = False
            self._login_required_logged = False
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
        self._decision_engine.stop_call()

    def dial(self, phone: str) -> None:
        if not self._page_alive():
            return
        self._emit_log(f"Dialing {phone}…")
        self._active_call = True
        self._pending_dial_phone = phone
        self._dial_step_attempts = 0
        self._dial_started_at = time.monotonic()
        self._vm_count = 0
        self._idle_count = 0
        self._ctrl_count = 0
        self._decision_engine.start_call()
        self._set_state("DIALING")
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        self._ensure_calls_page_then_dial()
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

    def _ensure_calls_page_then_dial(self) -> None:
        if not self._page_alive() or not self._pending_dial_phone:
            return
        url = self._page.url().toString()
        if "voice.google.com" not in url or "/calls" not in url:
            self._emit_log("Opening Google Voice calls page…")
            self._page.load(QUrl(GV_CALLS_URL))
            QTimer.singleShot(2500, self._ensure_calls_page_then_dial)
            return
        QTimer.singleShot(700, self._dial_step)

    def _dial_step(self) -> None:
        if not self._page_alive() or not self._pending_dial_phone:
            return
        self._dial_step_attempts += 1
        phone = self._pending_dial_phone
        self._page.runJavaScript(_js_dial(phone), self._on_dial_step_result)

    def _on_dial_step_result(self, status: str) -> None:
        status = status or "unknown"
        self._emit_log(f"Dial UI status: {status}")
        if status == "call_button_clicked":
            self._call_clicked_at = time.monotonic()
            self._pending_dial_phone = ""
            return
        if status in (
            "number_input_missing",
            "number_not_entered",
            "call_button_missing",
            "call_button_disabled",
        ):
            if self._dial_step_attempts < 12 and self._active_call:
                QTimer.singleShot(900, self._dial_step)
                return
        if self._active_call:
            self._emit_log("Dial UI did not accept the number")
            self._active_call = False
            self.stop_polling()
            self._set_state("FAILED")

    def _on_dial_stuck(self) -> None:
        if self._active_call and self._state == "DIALING":
            self._emit_log("Dial did not progress — marked failed")
            self._active_call = False
            self.stop_polling()
            self._set_state("FAILED")

    def _poll_once(self) -> None:
        if self._active_call:
            self._poll_state()

    def hangup(self, *, manual: bool = False) -> None:
        if not self._page_alive():
            return
        self._active_call = False
        self._page.runJavaScript(_JS_HANGUP, lambda r: self._emit_log(
            f"Hangup: {r}"))
        self.stop_polling()
        if manual:
            self._set_state("ENDED_MANUALLY")
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
        elif not logged_in:
            if self._logged_in:
                self._logged_in = False
                self._emit_log("Google Voice sign-in required")
            if not self._login_required_logged:
                self._login_required_logged = True
                self._emit_log("Waiting for Google Voice sign-in")
            if (self._login_email or self._login_password) and not self._redirected_to_signin:
                self._redirected_to_signin = True
                self._emit_log("Opening Google sign-in…")
                self._page.load(QUrl(SIGNIN_URL))

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

    def _on_poll_result(self, raw: object) -> None:
        self._pulse_heartbeat()
        decision = self._call_state_engine.classify(raw)
        dom_payload = decision.evidence if isinstance(decision.evidence, dict) else {}
        dom_payload["state"] = decision.state or "IDLE"
        audio_features = self._audio_monitor.poll()
        elapsed = time.monotonic() - self._dial_started_at if self._dial_started_at else 0.0
        fused = self._decision_engine.update(
            dom_evidence=dom_payload,
            audio_features=audio_features,
            elapsed_seconds=elapsed,
        )
        fused_state = fused.state or decision.state or "IDLE"
        state = {
            "HUMAN": "CONNECTED",
            "ANSWERED_PENDING": "RINGING",
        }.get(fused_state, fused_state)
        debug = {
            "phone": self._pending_dial_phone,
            "slot": self.slot_id,
            "elapsed": round(elapsed, 2),
            "dom_state": decision.state,
            "audio_state": fused.debug.get("audio_state") or self._audio_state_from_features(audio_features),
            "fused_state": fused_state,
            "confidence": round(float(fused.confidence), 3),
            "reason": fused.reason,
            "ringback": float(getattr(audio_features, "ringback_cadence_confidence", 0.0) or 0.0),
            "speech_duration": float(getattr(audio_features, "speech_duration_seconds", 0.0) or 0.0),
            "silence_duration": float(getattr(audio_features, "silence_duration_seconds", 0.0) or 0.0),
            "beep_detected": bool(getattr(audio_features, "beep_detected", False)),
            "human_greeting_detected": bool(getattr(audio_features, "human_greeting_detected", False)),
            "voicemail_confirmations": int(
                fused.debug.get("voicemail_confirmation_count")
                or fused.debug.get("voicemail_confirm_count")
                or 0
            ),
            "should_hangup": fused_state in {"VOICEMAIL", "NO_ANSWER", "BUSY", "FAILED"},
            "audio_backend": getattr(audio_features, "backend_status", "OFF"),
            "audio_reason": getattr(audio_features, "reason", ""),
        }
        self.detection_update.emit(self.slot_id, debug)
        if bool(self._runtime_cfg.get("live_debug_mode", False)):
            self._emit_call_debug(debug)

        if state == "IDLE" and self._active_call:
            if self._state == "CONNECTED":
                self._emit_log("Connected call ended")
                self._active_call = False
                self.stop_polling()
                self._set_state("ENDED")
                return
            self._idle_count += 1
            age = time.monotonic() - self._dial_started_at
            if age < 22.0:
                state = self._state if self._state != "IDLE" else "DIALING"
            else:
                self._emit_log("Call UI disappeared before answer")
                self._active_call = False
                self.stop_polling()
                self._set_state("NO_ANSWER")
                return
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

        raw_state = state
        call_age = (
            time.monotonic() - self._call_clicked_at
            if self._call_clicked_at else 0.0
        )
        answer_window_ready = (
            self._state == "CONNECTED"
            or (self._call_clicked_at and call_age >= self._min_answer_seconds)
        )

        # Debounce answered-controls. Google Voice exposes some controls while
        # still ringing, so require a mature call window and repeated evidence.
        if raw_state == "CONNECTED_CTRL":
            self._ctrl_count += 1
            if answer_window_ready and self._ctrl_count >= 4:
                state = "CONNECTED"
            else:
                state = "RINGING" if self._state != "CONNECTED" else "CONNECTED"
        else:
            self._ctrl_count = 0

        if raw_state == "CONNECTED" and not answer_window_ready and fused_state != "HUMAN":
            state = "RINGING" if self._state != "CONNECTED" else "CONNECTED"

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
        elif state == "BUSY":
            self.stop_polling()
        elif state == "IDLE" and not self._active_call:
            self.stop_polling()

    @staticmethod
    def _audio_state_from_features(features: object) -> str:
        if float(getattr(features, "busy_tone_cadence_confidence", 0.0) or 0.0) >= 0.8:
            return "BUSY"
        if float(getattr(features, "ringback_cadence_confidence", 0.0) or 0.0) >= 0.65:
            return "RINGING"
        if bool(getattr(features, "beep_detected", False)):
            return "BEEP"
        if bool(getattr(features, "has_speech_like", False)):
            return "SPEECH"
        if bool(getattr(features, "is_silent", True)):
            return "SILENCE"
        return "NOISE"

    def _emit_call_debug(self, debug: dict) -> None:
        lines = ["[CALL DEBUG]"]
        for key in (
            "phone", "slot", "elapsed", "dom_state", "audio_state",
            "fused_state", "confidence", "reason", "ringback",
            "speech_duration", "silence_duration", "beep_detected",
            "human_greeting_detected", "voicemail_confirmations",
            "should_hangup",
        ):
            lines.append(f"{key}={debug.get(key)}")
        self._emit_log("\n".join(lines))

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(self.slot_id, state)
            self._pulse_heartbeat()
        if state != "DIALING" and self._dial_stuck_timer is not None:
            self._dial_stuck_timer.stop()

    def _emit_log(self, msg: str) -> None:
        self.log_message.emit(self.slot_id, msg)
