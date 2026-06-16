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

from src.webengine_env import configure_webengine_environment

configure_webengine_environment()

from PyQt6.QtCore import QObject, QPoint, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication

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


def _gv_direct_call_url(phone: str) -> str:
    return _gv_dial_url_variants(phone)[0]


def _gv_dial_url_variants(phone: str) -> list[str]:
    """Google Voice dial entry points (official web URL schemes)."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return [GV_CALLS_URL]
    if len(digits) == 10:
        e164 = f"1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        e164 = digits
    else:
        e164 = digits
    return [
        f"{GV_CALLS_URL}?a=nc,%2B{e164}",
        f"https://voice.google.com/dial/+{e164}",
        GV_CALLS_URL,
    ]

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

_JS_CLICK_AT = """
(function(x, y){
  try {
    var el = document.elementFromPoint(x, y);
    if (!el) return 'no_element';
    try { el.scrollIntoView({block:'center', inline:'center'}); } catch(e) {}
    ['pointerdown','mousedown','mouseup','pointerup','click'].forEach(function(type){
      var opts = {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y, button:0};
      var ev = type.indexOf('pointer')===0 && window.PointerEvent
        ? new PointerEvent(type, opts)
        : new MouseEvent(type, opts);
      el.dispatchEvent(ev);
    });
    if (typeof el.click === 'function') el.click();
    return 'clicked';
  } catch(e) { return 'click_error:' + e; }
})(%d, %d);
"""

_JS_READY_FOR_DIAL = """
(function(){
  function vis(el){
    if(!el) return false;
    var s=window.getComputedStyle(el), r=el.getBoundingClientRect();
    return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
  }
  var body=(document.body&&document.body.innerText||'').toLowerCase();
  if(body && body.trim()==='voice') return false;
  var readyText = (
    body.indexOf('latest calls')!==-1 ||
    body.indexOf('enter a name or number')!==-1 ||
    body.indexOf('keypad')!==-1 ||
    body.indexOf('calls')!==-1
  );
  if(!readyText) return false;
  var controls=[
    'button[aria-label*="keypad" i]','button[aria-label*="dialpad" i]',
    'button[aria-label*="new call" i]','button[aria-label*="make a call" i]',
    'input[placeholder*="name" i]','input[placeholder*="number" i]'
  ];
  for(var i=0;i<controls.length;i++){
    var el=document.querySelector(controls[i]);
    if(vis(el)) return true;
  }
  return readyText;
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

  var timerText = '';
  var hasTimer = false;
  var timerSels=['[jsname="pRLmDf"]','.call-duration','[aria-label*="call duration" i]',
    '[data-e2eid="call-timer"]'];
  for(var t=0;t<timerSels.length;t++){
    var el=q(activeRoot, timerSels[t]);
    if(!vis(el)) continue;
    var tx=(el.textContent||el.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
    if(/^(?:\d{1,2}:)?\d{1,2}:\d{2}$/.test(tx) || /^\d{1,2}:\d{2}$/.test(tx)) {
      hasTimer = true;
      timerText = tx;
      break;
    }
  }

  var hasEnabledAnswerControl = false;
  var answerControl = '';
  var ansCtrl=['button[aria-label*="Hold call" i]','button[aria-label*="Mute call" i]',
    'button[aria-label*="Unmute call" i]','button[aria-label*="Transfer" i]'];
  for(var a=0;a<ansCtrl.length;a++){
    var btn=q(activeRoot, ansCtrl[a]);
    if(vis(btn) && !btn.disabled && btn.getAttribute('aria-disabled')!=='true') {
      hasEnabledAnswerControl = true;
      answerControl = ansCtrl[a];
      break;
    }
  }

  // Vicidial-style AMD stage gate: ringing is never voicemail. Only allow
  // machine cues after pickup evidence (timer or enabled in-call controls).
  if((hasRingingText || hasRingingNode) && !hasTimer && !hasEnabledAnswerControl) {
    return out('RINGING', {hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
  }

  // 1. Voicemail — only after answer evidence; detector will confirm it.
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
      return out('VOICEMAIL', {hasVoicemailCue:true, voicemailMatch:vmPhrases[p],
        hasTimer:hasTimer, timerText:timerText,
        hasEnabledAnswerControl:hasEnabledAnswerControl, answerControl:answerControl,
        hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
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
      return out('VOICEMAIL', {hasVoicemailCue:true, voicemailMatch:String(vmPatterns[rp]),
        hasTimer:hasTimer, timerText:timerText,
        hasEnabledAnswerControl:hasEnabledAnswerControl, answerControl:answerControl,
        hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
    }
  }
  var vmSels=['.voicemail-indicator','[data-e2eid="voicemail-record"]',
    '[aria-label*="leave a message" i]','[aria-label*="voicemail" i]',
    '[title*="leave a message" i]','[data-tooltip*="voicemail" i]'];
  for(var v=0;v<vmSels.length;v++){
    var vm=q(activeRoot, vmSels[v]);
    if(vis(vm)) return out('VOICEMAIL', {hasVoicemailCue:true, voicemailMatch:vmSels[v],
      hasTimer:hasTimer, timerText:timerText,
      hasEnabledAnswerControl:hasEnabledAnswerControl, answerControl:answerControl,
      hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
  }

  // 2. Live answer — MM:SS call timer (strict).
  // Some GV panels keep stale "calling" text after pickup, so answer signals
  // must be allowed to override ringing text.
  if(hasTimer) {
    return out('CONNECTED', {hasTimer:true, timerText:timerText, hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
  }

  // 3. Ringing / calling (before pickup). Do this before checking call
  // controls because GV displays disabled controls while still calling.
  if(hasRingingText || hasRingingNode) {
    return out('RINGING', {hasRingingText:hasRingingText, hasRingingNode:hasRingingNode});
  }

  if(hasEnabledAnswerControl) {
    return out('CONNECTED_CTRL', {hasEnabledAnswerControl:true, answerControl:answerControl});
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

_JS_ACTIVE_CALL_PRESENT = """
(function(){
  function vis(el){
    if(!el) return false;
    var s=getComputedStyle(el), r=el.getBoundingClientRect();
    return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
  }
  function qsa(sel){
    var found=[];
    function walk(root){
      try{ found=found.concat(Array.from(root.querySelectorAll(sel))); }catch(e){}
      try{
        Array.from(root.querySelectorAll('*')).forEach(function(n){
          if(n.shadowRoot) walk(n.shadowRoot);
        });
      }catch(e){}
    }
    walk(document);
    return found;
  }
  var hangSels=[
    'button[aria-label*="Hang up" i]',
    'button[aria-label*="End call" i]',
    'button[title*="Hang up" i]',
    'gv-icon-button[icon-name="call_end"]',
    '[data-action="end-call"]'
  ];
  for(var i=0;i<hangSels.length;i++){
    var hang=document.querySelector(hangSels[i]);
    if(vis(hang)) return true;
  }
  var controlSels=[
    'button[aria-label*="Mute" i]',
    'button[aria-label*="Hold" i]',
    'button[aria-label*="Add" i]',
    'button[aria-label*="Message" i]',
    'button[aria-label*="Record" i]'
  ];
  for(var c=0;c<controlSels.length;c++){
    var ctrl=document.querySelector(controlSels[c]);
    if(vis(ctrl)) return true;
  }
  var body=(document.body&&document.body.innerText||'').toLowerCase();
  if(body.indexOf('ringing')!==-1 || body.indexOf('calling')!==-1) return true;
  var timers=qsa('[aria-label*="timer" i], .call-duration, [data-e2eid*="timer"]');
  for(var t=0;t<timers.length;t++){
    if(vis(timers[t])) return true;
  }
  return false;
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


def _js_dial(phone: str, *, click_only: bool = False) -> str:
    """Build the JS dial sequence for a given E.164 phone number."""
    safe = phone.replace("'", "")
    click_only_lit = "true" if click_only else "false"
    return f"""
(function(){{
  var phone='{safe}';
  var clickOnly={click_only_lit};

  function setNativeVal(el,val){{
    try{{
      if(el.isContentEditable || !('value' in el)){{
        el.focus();
        try{{
          var sel=window.getSelection();
          var range=document.createRange();
          range.selectNodeContents(el);
          sel.removeAllRanges();
          sel.addRange(range);
        }}catch(e){{}}
        if(document.execCommand){{
          document.execCommand('delete', false, null);
          document.execCommand('insertText', false, val);
        }}
        if((el.innerText||el.textContent||'')!==val){{
          el.textContent=val;
        }}
        el.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:val}}));
        el.dispatchEvent(new Event('change',{{bubbles:true}}));
        return;
      }}
      var proto=el.tagName==='TEXTAREA'
        ?window.HTMLTextAreaElement.prototype
        :window.HTMLInputElement.prototype;
      var setter=Object.getOwnPropertyDescriptor(proto,'value').set;
      el.focus();
      el.click();
      setter.call(el,'');
      el.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'deleteContentBackward',data:null}}));
      var current='';
      for(var i=0;i<val.length;i++){{
        var ch=val.charAt(i);
        try{{
          el.dispatchEvent(new KeyboardEvent('keydown',{{bubbles:true,cancelable:true,key:ch}}));
          el.dispatchEvent(new InputEvent('beforeinput',{{bubbles:true,cancelable:true,inputType:'insertText',data:ch}}));
        }}catch(e){{}}
        current += ch;
        setter.call(el,current);
        try{{
          el.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:ch}}));
        }}catch(e){{
          el.dispatchEvent(new Event('input',{{bubbles:true}}));
        }}
        try{{
          el.dispatchEvent(new KeyboardEvent('keyup',{{bubbles:true,cancelable:true,key:ch}}));
        }}catch(e){{}}
      }}
      if((el.value||'')!==val) setter.call(el,val);
    }}catch(e){{ el.value=val; }}
    try {{
      el.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:val}}));
    }} catch(e) {{
      el.dispatchEvent(new Event('input',{{bubbles:true}}));
    }}
    el.dispatchEvent(new Event('change',{{bubbles:true}}));
    el.dispatchEvent(new KeyboardEvent('keyup',{{bubbles:true,key:(val||'').slice(-1)||'0'}}));
  }}

  function visible(el){{
    if(!el) return false;
    var r=el.getBoundingClientRect(), s=getComputedStyle(el);
    return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
  }}

  function disabled(el){{
    return !el || el.disabled || el.getAttribute('aria-disabled')==='true' ||
      el.getAttribute('disabled')!==null;
  }}

  function fireClick(el){{
    if(!el) return false;
    try{{
      el.scrollIntoView({{block:'center', inline:'center'}});
    }}catch(e){{}}
    try{{
      ['pointerdown','mousedown','mouseup','pointerup','click'].forEach(function(type){{
        var opts={{bubbles:true,cancelable:true,view:window,button:0,buttons:type.indexOf('down')!==-1?1:0}};
        var ev = type.indexOf('pointer')===0 && window.PointerEvent
          ? new PointerEvent(type, opts)
          : new MouseEvent(type, opts);
        el.dispatchEvent(ev);
      }});
      if(typeof el.click==='function') el.click();
      return true;
    }}catch(e){{
      try{{ el.click(); return true; }}catch(ex){{ return false; }}
    }}
  }}

  function roots(){{
    var out=[document];
    var seen=new Set(out);
    for(var i=0;i<out.length;i++){{
      var root=out[i];
      var nodes=[];
      try{{ nodes=Array.from(root.querySelectorAll('*')); }}catch(e){{}}
      for(var n=0;n<nodes.length;n++){{
        var sr=nodes[n].shadowRoot;
        if(sr && !seen.has(sr)){{
          seen.add(sr);
          out.push(sr);
        }}
      }}
    }}
    return out;
  }}

  function qsa(sel){{
    var found=[];
    roots().forEach(function(root){{
      try{{ found=found.concat(Array.from(root.querySelectorAll(sel))); }}catch(e){{}}
    }});
    return found;
  }}

  function textBits(el){{
    var bits=[];
    if(!el) return '';
    ['aria-label','placeholder','title','name','type','autocomplete','data-e2eid','data-action'].forEach(function(attr){{
      var v=el.getAttribute && el.getAttribute(attr);
      if(v) bits.push(v);
    }});
    var p=el.parentElement;
    for(var i=0;p && i<3;i++,p=p.parentElement){{
      var t=(p.innerText||p.textContent||'').replace(/\\s+/g,' ').trim();
      if(t) bits.push(t.slice(0,160));
    }}
    return bits.join(' ').toLowerCase();
  }}

  function attrBits(el){{
    var bits=[];
    ['aria-label','placeholder','title','name','type','autocomplete','data-e2eid','data-action'].forEach(function(attr){{
      var v=el && el.getAttribute && el.getAttribute(attr);
      if(v) bits.push(v);
    }});
    return bits.join(' ').toLowerCase();
  }}

  function editableValue(el){{
    if(!el) return '';
    if('value' in el) return el.value || '';
    return el.innerText || el.textContent || '';
  }}

  function digitsOf(text){{
    return (text || '').replace(/\\D/g,'');
  }}

  function sameNumber(candidateDigits, wantedDigits){{
    if(!candidateDigits || !wantedDigits) return false;
    if(candidateDigits === wantedDigits) return true;
    var minLen=Math.min(candidateDigits.length, wantedDigits.length);
    if(minLen < 7) return false;
    return candidateDigits.slice(-minLen) === wantedDigits.slice(-minLen) ||
      candidateDigits.slice(-10) === wantedDigits.slice(-10);
  }}

  function findNumberInput(){{
    var inputs=qsa('input,textarea,[contenteditable="true"],[contenteditable=""],[role="textbox"],[role="combobox"]');
    for(var i=0;i<inputs.length;i++){{
      var el=inputs[i];
      if(!visible(el) || disabled(el)) continue;
      var bits=textBits(el);
      var attrs=attrBits(el);
      var tag=(el.tagName||'').toLowerCase();
      var role=(el.getAttribute('role')||'').toLowerCase();
      var type=(el.getAttribute('type')||'').toLowerCase();
      if(type==='hidden' || type==='password' || type==='email') continue;
      if(attrs.indexOf('call as')!==-1 || attrs.indexOf('receiving calls')!==-1) continue;
      if((role==='textbox' || role==='combobox' || el.isContentEditable) &&
         attrs.indexOf('number')===-1 &&
         attrs.indexOf('name')===-1 &&
         attrs.indexOf('phone')===-1) continue;
      if(
        type==='tel' ||
        bits.indexOf('enter a name or number')!==-1 ||
        bits.indexOf('name or number')!==-1 ||
        bits.indexOf('phone number')!==-1 ||
        bits.indexOf('number')!==-1 ||
        (bits.indexOf('name')!==-1 && (tag==='input' || role==='textbox' || role==='combobox'))
      ) return el;
    }}
    return null;
  }}

  function findCallButton(wantedDigits){{
    var buttons=qsa('button,[role="button"],gv-icon-button,[data-action="call"],[role="option"],[role="menuitem"]');
    var input=findNumberInput();
    var wrongNumberButtons=[];
    var disabledMatchingButton=null;
    for(var i=0;i<buttons.length;i++){{
      var btn=buttons[i];
      var aria=(btn.getAttribute('aria-label')||'').toLowerCase();
      var icon=(btn.getAttribute('icon-name')||'').toLowerCase();
      var data=(btn.getAttribute('data-action')||'').toLowerCase();
      var text=(btn.innerText||btn.textContent||'').trim().toLowerCase();
      if(!visible(btn)) continue;
      if(aria.indexOf('end')!==-1 || aria.indexOf('video')!==-1) continue;
      var label=(aria+' '+text+' '+icon+' '+data).replace(/\\s+/g,' ').trim();
      var buttonDigits=digitsOf(label);
      if(buttonDigits && !sameNumber(buttonDigits, wantedDigits)){{
        if(aria.indexOf('call')!==-1 || text==='call' || icon==='call' || data==='call') {{
          wrongNumberButtons.push(buttonDigits);
        }}
        continue;
      }}
      if(disabled(btn)){{
        if(buttonDigits && sameNumber(buttonDigits, wantedDigits)) disabledMatchingButton=btn;
        continue;
      }}
      if(input){{
        var br=btn.getBoundingClientRect(), ir=input.getBoundingClientRect();
        var nearInput=Math.abs((br.top+br.bottom)/2 - (ir.top+ir.bottom)/2) < 180;
        if(!nearInput && text==='call') continue;
      }}
      if(
        aria.indexOf('call +')===0 ||
        aria.indexOf('call')===0 ||
        text==='call' ||
        icon==='call' ||
        data==='call'
      ){{
        return btn;
      }}
    }}
    if(disabledMatchingButton) return {{disabledButton: disabledMatchingButton}};
    if(wrongNumberButtons.length){{
      return {{wrongNumber: wrongNumberButtons[0]}};
    }}
    return null;
  }}

  function clickKeypadDigits(digits){{
    var buttons=qsa('button,[role="button"],gv-icon-button');
    var clicked=0;
    for(var d=0; d<digits.length; d++){{
      var digit=digits.charAt(d);
      var found=null;
      for(var i=0;i<buttons.length;i++){{
        var btn=buttons[i];
        var aria=(btn.getAttribute('aria-label')||'').toLowerCase();
        var text=(btn.innerText||btn.textContent||'').replace(/\\s+/g,' ').trim();
        if(!visible(btn) || disabled(btn)) continue;
        if(text===digit || text.indexOf(digit+' ')===0 ||
           aria.indexOf(\"'\"+digit+\"'\")!==-1 || aria===digit ||
           aria.indexOf(digit)===0) {{
          found=btn;
          break;
        }}
      }}
      if(!found) return false;
      fireClick(found);
      clicked++;
    }}
    return clicked===digits.length;
  }}

  function openDialpadIfNeeded(){{
    if(findNumberInput()) return true;
    var dpSels=['button[aria-label*="keypad" i]','button[aria-label*="dialpad" i]',
                'gv-icon-button[icon-name="phone"]',
                'gv-new-conversation-fab','[data-action="new-call"]',
                'button[aria-label*="new call" i]','button[aria-label*="make a call" i]',
                'button[aria-label*="make" i]'];
    for(var i=0;i<dpSels.length;i++){{
      var btn=qsa(dpSels[i])[0];
      if(btn && visible(btn) && !disabled(btn)){{ fireClick(btn); return false; }}
    }}
    return false;
  }}

  try{{ window.focus(); }}catch(e){{}}
  try{{ window.dispatchEvent(new Event('resize')); }}catch(e){{}}
  openDialpadIfNeeded();
  var inp=findNumberInput();
  if(!inp){{ window.__gvDialStatus='number_input_missing'; return window.__gvDialStatus; }}

  var digits=phone.replace(/\\D/g,'');
  var dialDigits=(digits.length===11 && digits.charAt(0)==='1') ? digits.slice(1) : digits;

  function numberLooksEntered(current){{
    current = (current || '').replace(/\\D/g,'');
    if(current === digits || current === dialDigits) return true;
    if(current.length === 11 && current.charAt(0)==='1' && current.slice(1) === dialDigits) return true;
    return false;
  }}

  function clearIfGarbled(){{
    var current=editableValue(inp).replace(/\\D/g,'');
    if(!current) return current;
    if(current.length > dialDigits.length + 2 ||
       (current.length >= 7 && !numberLooksEntered(current))){{
      setNativeVal(inp,'');
      return '';
    }}
    return current;
  }}

  if(clickOnly){{
    var readyDigits=clearIfGarbled();
    if(!numberLooksEntered(readyDigits)){{
      window.__gvDialStatus='number_not_entered|value='+editableValue(inp).slice(0,40);
      return window.__gvDialStatus;
    }}
  }} else {{
    clearIfGarbled();
    setNativeVal(inp,phone);
    var current=editableValue(inp).replace(/\\D/g,'');
    var numberEntered = numberLooksEntered(current);
    if(!numberEntered){{
      setNativeVal(inp,'');
      if(clickKeypadDigits(dialDigits)){{
        current=editableValue(inp).replace(/\\D/g,'');
        numberEntered = numberLooksEntered(current);
      }}
    }}
    if(!numberEntered){{
      window.__gvDialStatus='number_not_entered|value='+editableValue(inp).slice(0,40);
      return window.__gvDialStatus;
    }}
  }}

  function fallbackToKeypad(){{
    setNativeVal(inp,'');
    var clickedDigits=clickKeypadDigits(dialDigits);
    if(!clickedDigits) return false;
    current=editableValue(inp).replace(/\\D/g,'');
    var inputReflectsDigits = numberLooksEntered(current);
    return inputReflectsDigits;
  }}

  function nativeKeyStatus(reason){{
    try{{
      var ir=inp.getBoundingClientRect();
      var meta=((inp.tagName||'')+' role='+(inp.getAttribute('role')||'')+
        ' aria='+(inp.getAttribute('aria-label')||'')+
        ' ph='+(inp.getAttribute('placeholder')||'')+
        ' value='+editableValue(inp).slice(0,30)).replace(/\\s+/g,' ');
      return 'input_needs_native_keys|reason='+reason+
        '|x='+Math.round(ir.left+Math.max(4, Math.min(ir.width/2, 30)))+
        '|y='+Math.round(ir.top+ir.height/2)+
        '|input='+meta.slice(0,120);
    }}catch(e){{
      return 'call_button_missing';
    }}
  }}

  function nativeKeypadStatus(reason){{
    try{{
      var coords=[];
      var buttons=qsa('button,[role="button"],gv-icon-button');
      for(var d=0; d<dialDigits.length; d++){{
        var digit=dialDigits.charAt(d);
        var found=null;
        for(var i=0;i<buttons.length;i++){{
          var btn=buttons[i];
          var aria=(btn.getAttribute('aria-label')||'').toLowerCase();
          var text=(btn.innerText||btn.textContent||'').replace(/\\s+/g,' ').trim();
          if(!visible(btn) || disabled(btn)) continue;
          if(text===digit || text.indexOf(digit+' ')===0 ||
             aria.indexOf(\"'\"+digit+\"'\")!==-1 || aria===digit ||
             aria.indexOf(digit)===0) {{
            found=btn;
            break;
          }}
        }}
        if(!found) return nativeKeyStatus(reason + '_no_keypad');
        var r=found.getBoundingClientRect();
        coords.push(digit+','+Math.round(r.left+r.width/2)+','+Math.round(r.top+r.height/2));
      }}
      var ir=inp.getBoundingClientRect();
      return 'keypad_needs_native_clicks|reason='+reason+
        '|input='+Math.round(ir.left+Math.max(4, Math.min(ir.width/2, 30)))+','+
          Math.round(ir.top+ir.height/2)+
        '|coords='+coords.join(';');
    }}catch(e){{
      return nativeKeyStatus(reason + '_keypad_error');
    }}
  }}

  var btn=findCallButton(digits);
  if(btn && btn.disabledButton && fallbackToKeypad()){{
    btn=findCallButton(digits);
  }}
  if(btn && btn.disabledButton){{
    window.__gvDialStatus = nativeKeypadStatus('disabled');
    return window.__gvDialStatus;
  }}
  if(btn && btn.wrongNumber){{
    window.__gvDialStatus = 'call_button_wrong_number|wanted='+digits.slice(-10)+'|found='+btn.wrongNumber.slice(-10);
    return window.__gvDialStatus;
  }}
  if(!btn){{
    if(fallbackToKeypad()){{
      btn=findCallButton(digits);
    }}
  }}
  if(!btn){{
    var anyCall=qsa('button,[role="button"],gv-icon-button,[data-action="call"],[role="option"],[role="menuitem"]').filter(function(b){{
      var aria=(b.getAttribute('aria-label')||'').toLowerCase();
      var icon=(b.getAttribute('icon-name')||'').toLowerCase();
      var data=(b.getAttribute('data-action')||'').toLowerCase();
      var text=(b.innerText||b.textContent||'').trim().toLowerCase();
      var buttonDigits=digitsOf(aria+' '+text+' '+icon+' '+data);
      return visible(b) &&
        (!buttonDigits || sameNumber(buttonDigits, digits)) &&
        (aria.indexOf('call')!==-1 || text==='call' || icon==='call' || data==='call');
    }})[0];
    if(anyCall && disabled(anyCall)){{
      window.__gvDialStatus = nativeKeypadStatus('disabled');
      return window.__gvDialStatus;
    }}
    window.__gvDialStatus = nativeKeyStatus('missing');
    return window.__gvDialStatus;
  }}
  if(btn && btn.disabledButton){{
    window.__gvDialStatus = nativeKeypadStatus('disabled');
    return window.__gvDialStatus;
  }}
  if(btn && btn.wrongNumber){{
    window.__gvDialStatus = 'call_button_wrong_number|wanted='+digits.slice(-10)+'|found='+btn.wrongNumber.slice(-10);
    return window.__gvDialStatus;
  }}
  var br=btn.getBoundingClientRect();
  var clickedAria=(btn.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim();
  var clickedText=(btn.innerText||btn.textContent||'').replace(/\\s+/g,' ').trim();
  if(fireClick(btn)) {{
    try{{
      if(inp){{
        inp.focus();
        ['keydown','keypress','keyup'].forEach(function(type){{
          inp.dispatchEvent(new KeyboardEvent(type,{{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}}));
        }});
      }}
    }}catch(e){{}}
    window.__gvDialStatus='call_button_clicked_js|x='+Math.round(br.left+br.width/2)+
      '|y='+Math.round(br.top+br.height/2)+
      '|aria='+clickedAria.slice(0,80)+'|text='+clickedText.slice(0,80);
    return window.__gvDialStatus;
  }}
  window.__gvDialStatus='call_button_ready|x='+Math.round(br.left+br.width/2)+
    '|y='+Math.round(br.top+br.height/2)+
    '|aria='+clickedAria.slice(0,80)+'|text='+clickedText.slice(0,80);
  return window.__gvDialStatus;
}})();
"""


_JS_CLEAR_DIAL_FIELD = """
(function(){
  function visible(el){
    if(!el) return false;
    var r=el.getBoundingClientRect(), s=getComputedStyle(el);
    return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
  }
  function editableValue(el){
    if(!el) return '';
    if('value' in el) return el.value || '';
    return el.innerText || el.textContent || '';
  }
  function roots(){
    var out=[document];
    var seen=new Set(out);
    for(var i=0;i<out.length;i++){
      var nodes=[];
      try{ nodes=Array.from(out[i].querySelectorAll('*')); }catch(e){}
      for(var n=0;n<nodes.length;n++){
        var sr=nodes[n].shadowRoot;
        if(sr && !seen.has(sr)){
          seen.add(sr);
          out.push(sr);
        }
      }
    }
    return out;
  }
  function qsa(sel){
    var found=[];
    roots().forEach(function(root){
      try{ found=found.concat(Array.from(root.querySelectorAll(sel))); }catch(e){}
    });
    return found;
  }
  function setNativeVal(el,val){
    try{
      if(el.isContentEditable || !('value' in el)){
        el.focus();
        if(document.execCommand){
          document.execCommand('selectAll', false, null);
          document.execCommand('delete', false, null);
          if(val) document.execCommand('insertText', false, val);
        }
        if(!val){ el.textContent=''; }
        try{ el.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,cancelable:true,inputType:'deleteContentBackward',data:null})); }catch(e){}
        try{ el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'deleteContentBackward',data:null})); }catch(e){ el.dispatchEvent(new Event('input',{bubbles:true})); }
        el.dispatchEvent(new Event('change',{bubbles:true}));
        return;
      }
      var proto=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;
      var setter=Object.getOwnPropertyDescriptor(proto,'value').set;
      el.focus();
      try{ el.select(); }catch(e){}
      setter.call(el, val || '');
      try{ el.dispatchEvent(new InputEvent('beforeinput',{bubbles:true,cancelable:true,inputType:'deleteContentBackward',data:null})); }catch(e){}
      try{ el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'deleteContentBackward',data:null})); }catch(e){ el.dispatchEvent(new Event('input',{bubbles:true})); }
      el.dispatchEvent(new Event('change',{bubbles:true}));
    }catch(e){ if('value' in el) el.value=val||''; }
  }
  var inputs=qsa('input,textarea,[contenteditable="true"],[contenteditable=""],[role="textbox"],[role="combobox"]');
  var candidate=null;
  for(var i=0;i<inputs.length;i++){
    var el=inputs[i];
    if(!visible(el)) continue;
    var bits=((el.getAttribute('aria-label')||'')+' '+(el.getAttribute('placeholder')||'')+' '+(el.innerText||el.textContent||'')).toLowerCase();
    if(bits.toLowerCase().indexOf('call as')!==-1) continue;
    var valueDigits=editableValue(el).replace(/\\D/g,'');
    if((el.getAttribute('type')||'').toLowerCase()==='tel' ||
       bits.toLowerCase().indexOf('number')!==-1 ||
       bits.toLowerCase().indexOf('name')!==-1 ||
       valueDigits.length > 0){
      candidate=el;
      if(valueDigits.length > 0) break;
    }
  }
  if(candidate){
    setNativeVal(candidate,'');
    var remaining=editableValue(candidate).replace(/\\D/g,'');
    if(!remaining) return 'cleared|value=';
    return 'clear_failed|value='+remaining.slice(0,40);
  }
  return 'no_input';
})();
"""


def _js_retry_start_call(phone: str) -> str:
    """Re-click Call + Enter when the first click did not start the outbound call."""
    safe = phone.replace("'", "")
    return f"""
(function(){{
  var phone='{safe}';
  function vis(el){{
    if(!el) return false;
    var r=el.getBoundingClientRect(), s=getComputedStyle(el);
    return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
  }}
  function fireClick(el){{
    if(!el) return false;
    try{{ el.scrollIntoView({{block:'center'}}); }}catch(e){{}}
    try{{
      if(typeof el.click==='function') el.click();
      el.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true,view:window}}));
      return true;
    }}catch(e){{ return false; }}
  }}
  function digitsOf(t){{ return (t||'').replace(/\\D/g,''); }}
  var wanted=phone.replace(/\\D/g,'');
  var buttons=Array.from(document.querySelectorAll('button,[role="button"],gv-icon-button'));
  var callBtn=null;
  for(var i=0;i<buttons.length;i++){{
    var b=buttons[i];
    if(!vis(b)) continue;
    var aria=(b.getAttribute('aria-label')||'').toLowerCase();
    var text=(b.innerText||b.textContent||'').trim().toLowerCase();
    var icon=(b.getAttribute('icon-name')||'').toLowerCase();
    if(aria.indexOf('call')!==-1 || text==='call' || icon==='call'){{
      var bd=digitsOf(aria+' '+text);
      if(!bd || bd.slice(-10)===wanted.slice(-10)){{ callBtn=b; break; }}
    }}
  }}
  var inp=document.querySelector('input[placeholder*="number" i],input[placeholder*="name" i],[role="combobox"],[contenteditable="true"]');
  if(inp && vis(inp)){{
    inp.focus();
    ['keydown','keypress','keyup'].forEach(function(type){{
      inp.dispatchEvent(new KeyboardEvent(type,{{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}}));
    }});
  }}
  if(callBtn && !callBtn.disabled && callBtn.getAttribute('aria-disabled')!=='true'){{
    fireClick(callBtn);
    var br=callBtn.getBoundingClientRect();
    return 'retry_clicked|x='+Math.round(br.left+br.width/2)+'|y='+Math.round(br.top+br.height/2);
  }}
  return 'retry_no_button';
}})();
"""


# ── GVController ──────────────────────────────────────────────────────────────
class _GVWebEnginePage(QWebEnginePage):
    """Google Voice page wrapper that prevents modal prompts blocking slots."""

    def javaScriptConfirm(self, securityOrigin: QUrl, msg: str) -> bool:
        text = (msg or "").lower()
        if "leave this page" in text or "changes that you made may not be saved" in text:
            return False
        return False

    def javaScriptAlert(self, securityOrigin: QUrl, msg: str) -> None:
        return None


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
                 login_password: str = "", runtime_cfg: dict | None = None):
        super().__init__(parent)
        self.slot_id     = slot_id
        self.profile_dir = profile_dir
        self._state      = "IDLE"
        self._ctrl_count = 0   # debounce for answered-controls
        self._call_state_engine = CallStateEngine()
        self._runtime_cfg = runtime_cfg or self._load_runtime_cfg()
        self._allow_os_input = bool(self._runtime_cfg.get("allow_os_input", False))
        audio_enabled = bool(self._runtime_cfg.get("enable_ai_audio", True))
        amd_mode = str(self._runtime_cfg.get("amd_mode", "heuristic") or "heuristic").lower()
        if amd_mode == "off":
            audio_enabled = False
        self._decision_engine = CallDecisionEngine(
            detector_config=self._detection_config_from_runtime(),
        )
        self._audio_monitor = CallAudioMonitor(
            enabled=audio_enabled,
            device=self._runtime_cfg.get("audio_device") or None,
            parent=self,
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
        self._profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
        self._profile.setPersistentStoragePath(profile_dir)
        self._profile.setCachePath(cache_dir)
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )

        self._page = _GVWebEnginePage(self._profile)
        self._page.featurePermissionRequested.connect(self._grant_permission)
        self._page.setAudioMuted(not audio_enabled)

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
        playback_attr = getattr(
            QWebEngineSettings.WebAttribute,
            "PlaybackRequiresUserGesture",
            None,
        )
        if playback_attr is not None:
            settings.setAttribute(playback_attr, False)

        self.view = QWebEngineView()
        self.view.setPage(self._page)
        self.view.resize(800, 600)
        self.view.setMinimumSize(1, 1)
        if hasattr(self._page, "setViewportSize"):
            try:
                self._page.setViewportSize(QSize(800, 600))
            except Exception:
                pass
        self._page.setBackgroundColor(QColor("#ffffff"))
        self.view.setStyleSheet("background-color: #ffffff;")
        self._load_ok = False
        self._load_retry_count = 0
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
        self._current_call_phone = ""
        self._dial_step_attempts = 0
        self._dial_url_variant = 0
        self._calls_ready_attempts = 0
        self._native_key_attempted = False
        self._native_key_attempts = 0
        self._call_clicked_at = 0.0
        self._amd_answer_at = 0.0
        self._amd_decision_ms = 0
        self._render_w = 800
        self._render_h = 600
        self._whisper_pending = False
        self._whisper_thread = None
        self._min_answer_seconds = 10.0
        self.prepare_for_background_rendering()

    # ── Public API ────────────────────────────────────────────────────────────

    @staticmethod
    def _load_runtime_cfg() -> dict:
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _detection_config_from_runtime(self) -> DetectionConfig:
        amd_mode = str(self._runtime_cfg.get("amd_mode", "heuristic") or "heuristic").lower()
        audio_enabled = bool(self._runtime_cfg.get("enable_ai_audio", False)) and amd_mode != "off"
        max_decision_s = float(self._runtime_cfg.get("amd_max_decision_ms", 2500)) / 1000.0
        analysis_s = float(
            self._runtime_cfg.get(
                "amd_analysis_seconds",
                max(8.0, max_decision_s),
            )
        )
        require_audio_human = bool(self._runtime_cfg.get("amd_require_audio_human", True))
        return DetectionConfig(
            max_ring_seconds=float(self._runtime_cfg.get("call_timeout", 60)),
            enable_audio_detection=audio_enabled,
            enable_beep_detection=amd_mode != "off",
            human_first_seconds=float(self._runtime_cfg.get("amd_human_first_seconds", 5)),
            answered_pending_seconds=analysis_s,
            answered_pending_safe_min_seconds=float(
                self._runtime_cfg.get("amd_safe_window_seconds", 5)
            ),
            require_audio_for_human=require_audio_human and audio_enabled,
            min_human_audio_score=float(
                self._runtime_cfg.get("amd_min_human_audio_score", 0.30)
            ),
        )

    def apply_runtime_cfg(self, runtime_cfg: dict) -> None:
        """Apply dialer settings without recreating the WebEngine view."""
        self._runtime_cfg.update(runtime_cfg or {})
        audio_enabled = bool(self._runtime_cfg.get("enable_ai_audio", False))
        amd_mode = str(self._runtime_cfg.get("amd_mode", "heuristic") or "heuristic").lower()
        if amd_mode == "off":
            audio_enabled = False
        self._decision_engine = CallDecisionEngine(
            detector_config=self._detection_config_from_runtime(),
        )
        self._audio_monitor.set_enabled(audio_enabled)
        if amd_mode == "whisper" and self._whisper_thread is None:
            try:
                from src.detection.whisper_worker import WhisperTranscriptionThread
                self._whisper_thread = WhisperTranscriptionThread(parent=self)
            except Exception:
                self._whisper_thread = None
        elif amd_mode != "whisper" and self._whisper_thread is not None:
            self._whisper_thread.shutdown()
            self._whisper_thread = None
        if self._page_alive():
            self._page.setAudioMuted(not audio_enabled)

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
        if getattr(self, "_audio_monitor", None) is not None:
            self._audio_monitor.shutdown()

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
            try:
                view.setParent(None)
            except Exception:
                pass
            view.deleteLater()
            self.view = None  # type: ignore[assignment]
        profile = getattr(self, "_profile", None)
        if profile is not None:
            try:
                profile.deleteLater()
            except Exception:
                pass
            self._profile = None  # type: ignore[assignment]

    def _page_alive(self) -> bool:
        return self.__dict__.get("_page") is not None

    def _pulse_heartbeat(self) -> None:
        self.heartbeat.emit(self.slot_id)

    def _render_dimensions(self) -> tuple[int, int]:
        w = int(self.__dict__.get("_render_w", 800) or 800)
        h = int(self.__dict__.get("_render_h", 600) or 600)
        page = self.__dict__.get("_page")
        if page is not None and hasattr(page, "viewportSize"):
            try:
                vs = page.viewportSize()
                if vs.width() > 0 and vs.height() > 0:
                    w = max(w, int(vs.width()))
                    h = max(h, int(vs.height()))
            except Exception:
                pass
        view = self.__dict__.get("view")
        if view is not None:
            w = max(w, int(view.width() or 0))
            h = max(h, int(view.height() or 0))
        return max(w, 640), max(h, 480)

    def _set_render_dimensions(self, width: int, height: int) -> None:
        self._render_w = max(640, int(width))
        self._render_h = max(480, int(height))
        if self._page_alive() and hasattr(self.__dict__.get("_page"), "setViewportSize"):
            try:
                self.__dict__["_page"].setViewportSize(QSize(self._render_w, self._render_h))
            except Exception:
                pass

    def prepare_for_visible_display(self) -> None:
        """
        After reparenting from the 1×1 hidden host, force WebEngine to repaint
        and tell Google Voice the tab is visible (needed for audio + UI).
        """
        if not self._page_alive():
            return
        self.view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        self.view.setMinimumSize(640, 480)
        width = max(1024, int(self.view.width() or 0))
        height = max(720, int(self.view.height() or 0))
        self.view.resize(width, height)
        self._set_render_dimensions(width, height)
        if hasattr(self._page, "setViewportSize"):
            try:
                self._page.setViewportSize(QSize(width, height))
            except Exception:
                pass
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
        if muted and self._active_call and bool(self._runtime_cfg.get("enable_ai_audio", True)):
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

    def prepare_for_background_rendering(self) -> None:
        """Keep Google Voice rendered off-screen with a small footprint."""
        max_dim = 16777215
        viewport_w, viewport_h = 1280, 900
        native_w, native_h = 1024, 720
        self.view.setParent(None)
        self.view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        self.view.setWindowFlag(Qt.WindowType.Tool, True)
        self.view.setMinimumSize(1, 1)
        self.view.setMaximumSize(max_dim, max_dim)
        self.view.resize(native_w, native_h)
        self._set_render_dimensions(viewport_w, viewport_h)
        screen = QApplication.primaryScreen()
        if screen is not None:
            rect = screen.availableGeometry()
            self.view.move(rect.x() - native_w - 80, rect.y() + 40)
        else:
            self.view.move(-1200, 40)
        if hasattr(self._page, "setViewportSize"):
            try:
                self._page.setViewportSize(QSize(viewport_w, viewport_h))
            except Exception:
                pass
        self.view.show()
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        self._page.runJavaScript(_JS_REFRESH_LAYOUT)

    def start_polling(self) -> None:
        if self._active_call:
            self._poll_timer.start()

    def stop_polling(self) -> None:
        self._poll_timer.stop()
        self._ctrl_count = 0
        self._vm_count = 0
        self._idle_count = 0
        self._active_call = False
        self._decision_engine.stop_call()

    def retry_dial_if_pending(self) -> None:
        """Retry GV dial after the WebEngine view is resized (e.g. monitor opened)."""
        if not self._active_call or not self._page_alive():
            return
        phone = self._pending_dial_phone or self._current_call_phone
        if not phone:
            return
        if self._state not in {"DIALING", "RINGING", "IDLE"}:
            return
        self._native_key_attempts = 0
        self._native_key_attempted = False
        self._dial_step_attempts = 0
        self._emit_log("Retrying dial with expanded Google Voice viewport…")
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        self._page.runJavaScript(_JS_REFRESH_LAYOUT)
        QTimer.singleShot(300, self._ensure_calls_page_then_dial)

    def dial(self, phone: str) -> None:
        if not self._page_alive():
            return
        self._emit_log(f"Dialing {phone}…")
        self._active_call = True
        self._pending_dial_phone = phone
        self._current_call_phone = phone
        self._dial_step_attempts = 0
        self._dial_url_variant = 0
        self._calls_ready_attempts = 0
        self._native_key_attempted = False
        self._native_key_attempts = 0
        self._dial_started_at = time.monotonic()
        self._vm_count = 0
        self._idle_count = 0
        self._ctrl_count = 0
        self._amd_answer_at = 0.0
        self._amd_decision_ms = 0
        self._whisper_pending = False
        self._decision_engine.start_call()
        if bool(self._runtime_cfg.get("enable_ai_audio", True)):
            self._audio_monitor.prime()
        self._set_state("DIALING")
        if bool(self._runtime_cfg.get("dry_run_mode", False)):
            self._emit_log("Dry-run mode: simulated dial, no Google Voice call placed")
            self._pending_dial_phone = ""
            self._call_clicked_at = time.monotonic()
            QTimer.singleShot(700, self._dry_run_mark_ringing)
            timeout_ms = min(
                int(float(self._runtime_cfg.get("call_timeout", 45)) * 1000),
                8000,
            )
            QTimer.singleShot(max(1800, timeout_ms), self._dry_run_finish_no_answer)
            return
        if audio_enabled := bool(self._runtime_cfg.get("enable_ai_audio", True)):
            self._page.setAudioMuted(False)
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        self._ensure_calls_page_then_dial()
        if self._dial_stuck_timer is not None:
            self._dial_stuck_timer.stop()
        self._dial_stuck_timer = QTimer(self)
        self._dial_stuck_timer.setSingleShot(True)
        self._dial_stuck_timer.setInterval(70000)
        self._dial_stuck_timer.timeout.connect(self._on_dial_stuck)
        self._dial_stuck_timer.start()

    def _dry_run_mark_ringing(self) -> None:
        if self._active_call and self._state == "DIALING":
            self._set_state("RINGING")

    def _dry_run_finish_no_answer(self) -> None:
        if self._active_call and self._state in {"DIALING", "RINGING"}:
            self._active_call = False
            self._set_state("NO_ANSWER")

    def _current_dial_url(self) -> str:
        phone = self._pending_dial_phone or self._current_call_phone
        variants = _gv_dial_url_variants(phone)
        return variants[self._dial_url_variant % len(variants)]

    def _ensure_calls_page_then_dial(self) -> None:
        if not self._active_call or not self._page_alive() or not self._pending_dial_phone:
            return
        url = self._page.url().toString()
        if "voice.google.com" not in url:
            self._emit_log("Opening Google Voice calls page…")
            self._page.load(QUrl(GV_CALLS_URL))
            QTimer.singleShot(2500, self._ensure_calls_page_then_dial)
            return
        if "/calls" not in url and "a=nc" not in url and "/dial/" not in url:
            self._emit_log("Opening Google Voice calls page…")
            self._page.load(QUrl(GV_CALLS_URL))
            QTimer.singleShot(2500, self._ensure_calls_page_then_dial)
            return
        self._page.runJavaScript(_JS_REFRESH_LAYOUT)
        QTimer.singleShot(700, self._dial_step)

    def _dial_step(self, *, click_only: bool = False) -> None:
        if not self._active_call or not self._page_alive() or not self._pending_dial_phone:
            return
        self._dial_step_attempts += 1
        phone = self._pending_dial_phone
        self._page.runJavaScript(
            _js_dial(phone, click_only=click_only),
            self._on_dial_step_result,
        )

    def _on_dial_step_result(self, status: str) -> None:
        if not self._active_call:
            return
        status = status or "unknown"
        status_base = status.split("|", 1)[0]
        self._emit_log(f"Dial UI status: {status}")
        if status.startswith("call_button_clicked_js"):
            if not self._call_button_status_matches_pending(status):
                self._emit_log("Ignoring stale JS call button for a different number")
                self._handle_retryable_dial_status("call_button_wrong_number")
                return
            self._call_clicked_at = time.monotonic()
            self._pending_dial_phone = ""
            QTimer.singleShot(700, lambda s=status: self._retry_native_click_if_no_panel(s))
            QTimer.singleShot(1700, lambda s=status: self._retry_native_click_if_no_panel(s))
            QTimer.singleShot(3500, lambda s=status: self._retry_native_click_if_no_panel(s))
            QTimer.singleShot(800, self._poll_once)
            QTimer.singleShot(1600, self._poll_once)
            QTimer.singleShot(2400, self.start_polling)
            return
        if status.startswith("call_button_ready"):
            if not self._call_button_status_matches_pending(status):
                self._emit_log("Ignoring stale call button for a different number")
                status = "call_button_wrong_number"
                status_base = status
            elif self._click_call_button_from_status(status):
                self._call_clicked_at = time.monotonic()
                self._pending_dial_phone = ""
                self._emit_log("Dial UI status: call_button_clicked")
                QTimer.singleShot(800, self._poll_once)
                QTimer.singleShot(1600, self._poll_once)
                QTimer.singleShot(2400, self.start_polling)
                return
            else:
                status = "call_button_click_failed"
                status_base = status
        if status_base == "enter_pressed_no_call_button":
            self._call_clicked_at = time.monotonic()
            self._pending_dial_phone = ""
            QTimer.singleShot(800, self._poll_once)
            QTimer.singleShot(1600, self._poll_once)
            QTimer.singleShot(2400, self.start_polling)
            return
        if status_base == "input_needs_native_keys":
            if self._type_number_from_status(status):
                QTimer.singleShot(900, lambda: self._dial_step(click_only=True))
                return
            status_base = "call_button_missing"
        if status_base == "keypad_needs_native_clicks":
            if self._click_keypad_from_status(status):
                QTimer.singleShot(900, lambda: self._dial_step(click_only=True))
                return
            status_base = "call_button_missing"
        if status_base in (
            "number_input_missing",
            "number_not_entered",
            "call_button_missing",
            "call_button_disabled",
            "call_button_disabled_for_target",
            "call_button_wrong_number",
        ):
            self._handle_retryable_dial_status(status_base)
            return
        if self._active_call:
            self._emit_log("Dial UI did not accept the number")
            self._active_call = False
            self.stop_polling()
            self._set_state("FAILED")

    def _handle_retryable_dial_status(self, status_base: str) -> None:
        if not self._active_call:
            return
        if not self._page_alive():
            self._set_state("FAILED")
            return

        def after_active_check(active: object) -> None:
            if not self._active_call:
                return
            if bool(active):
                self._emit_log("Call panel is active - switching to call-state polling")
                if not self._call_clicked_at:
                    self._call_clicked_at = time.monotonic()
                self._pending_dial_phone = ""
                QTimer.singleShot(200, self._poll_once)
                QTimer.singleShot(1000, self._poll_once)
                QTimer.singleShot(1800, self.start_polling)
                return

            if (
                status_base in ("call_button_missing", "call_button_disabled")
                and getattr(self, "_native_key_attempted", False)
                and self._dial_url_variant < len(_gv_dial_url_variants(
                    self._pending_dial_phone or self._current_call_phone
                )) - 1
            ):
                self._dial_url_variant += 1
                self._emit_log(
                    f"Native dial field stayed disabled - trying alternate GV URL "
                    f"({self._dial_url_variant + 1})…")
                self._page.load(QUrl(self._current_dial_url()))
                QTimer.singleShot(2500, self._ensure_calls_page_then_dial)
                return

            if status_base in ("number_input_missing", "call_button_wrong_number") and self._dial_step_attempts in (8, 18):
                self._dial_url_variant += 1
                self._emit_log(
                    f"Dialpad did not appear - trying alternate GV URL "
                    f"({self._dial_url_variant + 1})…")
                self._page.load(QUrl(self._current_dial_url()))
                QTimer.singleShot(2500, self._ensure_calls_page_then_dial)
                return
            if self._dial_step_attempts < 30:
                QTimer.singleShot(900, lambda: self._dial_step(click_only=False))
                return

            self._emit_log("Dial UI did not accept the number")
            self._active_call = False
            self.stop_polling()
            self._set_state("FAILED")

        self._page.runJavaScript(_JS_ACTIVE_CALL_PRESENT, after_active_check)

    def _retry_native_click_if_no_panel(self, status: str) -> None:
        if not self._active_call or not self._page_alive():
            return
        phone = self._current_call_phone or self._pending_dial_phone

        def after_active_check(active: object) -> None:
            if not self._active_call or bool(active):
                if bool(active):
                    QTimer.singleShot(400, self.start_polling)
                return
            self._page.runJavaScript(
                _js_retry_start_call(phone),
                self._on_retry_start_call_result,
            )
            if self._click_call_button_from_status(status):
                self._call_clicked_at = time.monotonic()
                self._emit_log("Dial UI status: view_call_click_retry")
            QTimer.singleShot(1200, self._poll_once)

        self._page.runJavaScript(_JS_ACTIVE_CALL_PRESENT, after_active_check)

    def _on_retry_start_call_result(self, result: object) -> None:
        if not self._active_call:
            return
        status = str(result or "")
        if status.startswith("retry_clicked"):
            self._emit_log(f"Dial UI status: {status}")
            if self._click_call_button_from_status(status):
                self._call_clicked_at = time.monotonic()
            QTimer.singleShot(800, self._poll_once)
            QTimer.singleShot(1800, self.start_polling)

    def _type_number_from_status(self, status: str) -> bool:
        if getattr(self, "_native_key_attempts", 0) >= 3:
            self._native_key_attempted = True
            return False
        try:
            mx = re.search(r"(?:^|\|)x=(\d+)", status)
            my = re.search(r"(?:^|\|)y=(-?\d+)", status)
            if not mx or not my:
                return False
            x = int(mx.group(1))
            y = int(my.group(1))
            rw, rh = self._render_dimensions()
            if x < 0 or y < 0 or x > rw or y > rh:
                self._emit_log(
                    f"Dial UI native typing target off-screen ({x},{y}); waiting for dialpad"
                )
                return False
            phone = self._pending_dial_phone or self._current_call_phone
            digits = re.sub(r"\D", "", phone)
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            if not digits:
                return False
            if not self._clear_dial_field_before_native_input(status):
                return False
            self._native_key_attempts = getattr(self, "_native_key_attempts", 0) + 1
            self._native_key_attempted = self._native_key_attempts >= 3
            if not self._click_view_coords(x, y):
                return False
            QTest.keyClick(self.view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClick(self.view, Qt.Key.Key_Backspace)
            QTest.keyClicks(self.view, digits)
            QTest.keyClick(self.view, Qt.Key.Key_Return)
            self._emit_log("Dial UI status: native_number_typed")
            return True
        except Exception as exc:
            self._emit_log(f"Native number typing failed: {exc}")
            return False

    def _click_keypad_from_status(self, status: str) -> bool:
        if getattr(self, "_native_key_attempts", 0) >= 3:
            self._native_key_attempted = True
            return False
        try:
            match = re.search(r"(?:^|\|)coords=([^|]+)", status)
            if not match:
                return False
            items = [item for item in match.group(1).split(";") if item]
            if not items:
                return False
            phone = self._pending_dial_phone or self._current_call_phone
            dial_digits = re.sub(r"\D", "", phone)
            if len(dial_digits) == 11 and dial_digits.startswith("1"):
                dial_digits = dial_digits[1:]
            parsed: list[tuple[str, int, int]] = []
            for item in items:
                parts = item.split(",")
                if len(parts) != 3:
                    return False
                digit, x_raw, y_raw = parts
                if digit != dial_digits[len(parsed)]:
                    self._emit_log(
                        f"Dial UI keypad mismatch at digit {len(parsed)+1}; clearing and retrying"
                    )
                    if self._page_alive():
                        self._page.runJavaScript(_JS_CLEAR_DIAL_FIELD)
                    return False
                x = int(x_raw)
                y = int(y_raw)
                rw, rh = self._render_dimensions()
                if x < 0 or y < 0 or x > rw or y > rh:
                    self._emit_log(
                        f"Dial UI keypad target off-screen ({x},{y}); waiting for dialpad"
                    )
                    return False
                parsed.append((digit, x, y))
            if not self._clear_dial_field_before_native_input(status):
                return False
            self._native_key_attempts = getattr(self, "_native_key_attempts", 0) + 1
            self._native_key_attempted = self._native_key_attempts >= 3
            if self.__dict__.get("_allow_os_input", False):
                if self._type_number_os_from_status(status):
                    return True
            for _digit, x, y in parsed:
                if not self._click_view_coords(x, y):
                    return False
                QTest.qWait(35)
            self._emit_log("Dial UI status: native_keypad_clicked")
            return True
        except Exception as exc:
            self._emit_log(f"Native keypad click failed: {exc}")
            return False

    def _clear_dial_field_before_native_input(self, status: str = "") -> bool:
        """Clear GV's dial field and verify it is empty before native input."""
        if not self._page_alive():
            return False

        def run_clear() -> str:
            done = {"status": ""}

            def _on_clear(result: object) -> None:
                done["status"] = str(result or "")

            self._page.runJavaScript(_JS_CLEAR_DIAL_FIELD, _on_clear)
            QTest.qWait(140)
            return done["status"]

        result = run_clear()
        if result.startswith("cleared|value=") or result == "no_input":
            return True

        match = re.search(r"(?:^|\|)input=(\d+),(-?\d+)", status or "")
        if match:
            x = int(match.group(1))
            y = int(match.group(2))
            rw, rh = self._render_dimensions()
            if 0 <= x <= rw and 0 <= y <= rh and self._click_view_coords(x, y):
                QTest.keyClick(self.view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
                QTest.keyClick(self.view, Qt.Key.Key_Backspace)
                QTest.qWait(80)
                result = run_clear()
                if result.startswith("cleared|value=") or result == "no_input":
                    return True

        self._emit_log(f"Dial UI status: clear_failed_before_input|{result}")
        return False

    def _type_number_os_from_status(self, status: str) -> bool:
        try:
            match = re.search(r"(?:^|\|)input=(\d+),(-?\d+)", status)
            if not match:
                return False
            x = int(match.group(1))
            y = int(match.group(2))
            if x < 0 or y < 0 or x > self.view.width() or y > self.view.height():
                return False
            phone = self._pending_dial_phone or self._current_call_phone
            digits = re.sub(r"\D", "", phone)
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            if not digits:
                return False
            if not self._click_view_coords_os(x, y):
                self._emit_log("OS number typing skipped: input coordinate not clickable")
                return False
            import pyautogui

            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            pyautogui.write(digits, interval=0.02)
            pyautogui.press("enter")
            self._emit_log("Dial UI status: os_number_typed")
            return True
        except Exception as exc:
            self._emit_log(f"OS number typing failed: {exc}")
            return False

    def _call_button_status_matches_pending(self, status: str) -> bool:
        wanted = re.sub(r"\D", "", self._pending_dial_phone or self._current_call_phone)
        if not wanted:
            return True
        label = status
        label = re.sub(r"(?:^|\|)x=\d+", "", label)
        label = re.sub(r"(?:^|\|)y=\d+", "", label)
        label_digits = re.sub(r"\D", "", label)
        if not label_digits:
            return True
        min_len = min(len(wanted), len(label_digits))
        return min_len < 7 or label_digits[-min_len:] == wanted[-min_len:]

    def _click_view_coords(self, x: int, y: int) -> bool:
        """Click inside the WebEngine page at viewport-local JS coordinates."""
        try:
            if x < 0 or y < 0:
                return False
            view = self.__dict__.get("view")
            rw, rh = self._render_dimensions()
            if x > rw or y > rh:
                return False
            vw = int(view.width() or 0) if view is not None else 0
            vh = int(view.height() or 0) if view is not None else 0
            if view is None:
                return False
            click_x = min(x, max(0, (vw or rw) - 2))
            click_y = min(y, max(0, (vh or rh) - 2))
            page = self.__dict__.get("_page")
            if page is not None:
                done = {"ok": False}

                def _on_js_click(result: object) -> None:
                    done["ok"] = str(result or "").startswith("clicked")

                page.runJavaScript(_JS_CLICK_AT % (x, y), _on_js_click)
                QTest.qWait(80)
                if done["ok"]:
                    return True
            view.setFocus()
            view.activateWindow()
            QTest.mouseClick(
                view,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(click_x, click_y),
            )
            if self.__dict__.get("_allow_os_input", False):
                self._click_view_coords_os(click_x, click_y)
            return True
        except Exception as exc:
            self._emit_log(f"View click failed: {exc}")
            return False

    def _click_view_coords_os(self, x: int, y: int) -> bool:
        try:
            try:
                self.view.raise_()
                self.view.activateWindow()
                QApplication.processEvents()
            except Exception:
                pass
            screen_pos = self.view.mapToGlobal(QPoint(x, y))
            gx = int(round(screen_pos.x()))
            gy = int(round(screen_pos.y()))
            import pyautogui

            pyautogui.moveTo(gx, gy, duration=0)
            pyautogui.click(gx, gy)
            return True
        except Exception as exc:
            self._emit_log(f"OS click fallback failed: {exc}")
            return False

    def _click_call_button_from_status(self, status: str) -> bool:
        try:
            mx = re.search(r"(?:^|\|)x=(\d+)", status)
            my = re.search(r"(?:^|\|)y=(-?\d+)", status)
            if not mx or not my:
                return False
            x = int(mx.group(1))
            y = int(my.group(1))
            if not self._click_view_coords(x, y):
                return False
            QTest.keyClick(self.view, Qt.Key.Key_Return)
            return True
        except Exception as exc:
            self._emit_log(f"Dial UI mouse click failed: {exc}")
            return False

    def _on_dial_stuck(self) -> None:
        if self._active_call and self._state == "DIALING":
            self._emit_log("Dial did not progress — marked failed")
            self._active_call = False
            self.stop_polling()
            self._set_state("FAILED")

    def _poll_once(self) -> None:
        if self._active_call:
            self._poll_state()

    def retry_start_call(self) -> None:
        """Re-press Call when the number is entered but the outbound call did not start."""
        if not self._page_alive():
            return
        phone = self._pending_dial_phone or self._current_call_phone
        if not phone:
            return
        if not self._active_call:
            self._active_call = True
        self._pending_dial_phone = phone
        self._current_call_phone = phone
        self._emit_log("Retrying Call button in Google Voice…")
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        self._page.runJavaScript(
            _js_retry_start_call(phone),
            self._on_retry_start_call_result,
        )
        QTimer.singleShot(1500, self._poll_once)

    def hangup(self, *, manual: bool = False) -> None:
        if not self._page_alive():
            return
        self._active_call = False
        self._pending_dial_phone = ""
        self._call_clicked_at = 0.0
        self._amd_answer_at = 0.0
        self._amd_decision_ms = 0
        self._whisper_pending = False
        if self._dial_stuck_timer is not None:
            self._dial_stuck_timer.stop()
        self._page.runJavaScript(_JS_HANGUP, lambda r: self._emit_log(
            f"Hangup: {r}"))
        self.stop_polling()
        if manual:
            self._set_state("ENDED_MANUALLY")
        self._current_call_phone = ""
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
        if self._active_call and self._pending_dial_phone:
            QTimer.singleShot(1000, self._ensure_calls_page_then_dial)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_load_started(self) -> None:
        self._load_ok = False

    def _on_load_finished_page(self, ok: bool) -> None:
        self._load_ok = ok
        self._pulse_heartbeat()
        if not self._page_alive():
            return
        self._page.runJavaScript(_JS_FORCE_VISIBLE)
        if ok:
            self._load_retry_count = 0
            QTimer.singleShot(400, self._try_auto_login)
            QTimer.singleShot(800, self._check_login)
            if self._setup_mode:
                QTimer.singleShot(1200, self._maybe_redirect_signin)
        else:
            self._load_retry_count += 1
            if self._load_retry_count <= 3:
                wait_ms = 1500 * self._load_retry_count
                self._emit_log(
                    f"Page load failed — retry {self._load_retry_count}/3 in "
                    f"{wait_ms // 1000}s…")
                QTimer.singleShot(wait_ms, self._retry_page_load)
            else:
                self._emit_log("Page failed to load — check internet, then Reload")

    def _retry_page_load(self) -> None:
        if not self._page_alive() or self._load_ok:
            return
        if self._setup_mode:
            self._page.load(QUrl(SIGNIN_URL))
        else:
            self._page.load(QUrl(GV_URL))

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
        if not self._active_call or not self._page_alive():
            return
        self._page.runJavaScript(_JS_DETECT_STATE, self._on_poll_result)

    def _on_poll_result(self, raw: object) -> None:
        if not self._active_call:
            return
        if not self._active_call and self._state in {"NO_ANSWER", "ENDED", "ENDED_MANUALLY", "FAILED", "BUSY"}:
            return
        self._pulse_heartbeat()
        decision = self._call_state_engine.classify(raw)
        dom_payload = decision.evidence if isinstance(decision.evidence, dict) else {}
        dom_payload["state"] = decision.state or "IDLE"
        audio_features = self._audio_monitor.last_features
        if self._state in ("RINGING", "ANSWERED_PENDING", "CONNECTED", "DIALING"):
            audio_features = self._audio_monitor.poll()
        elapsed = time.monotonic() - self._dial_started_at if self._dial_started_at else 0.0
        fused = self._decision_engine.update(
            dom_evidence=dom_payload,
            audio_features=audio_features,
            elapsed_seconds=elapsed,
        )
        fused_state = fused.state or decision.state or "IDLE"
        if fused_state in {"HUMAN", "VOICEMAIL"} and self._amd_answer_at > 0 and self._amd_decision_ms <= 0:
            self._amd_decision_ms = int((time.monotonic() - self._amd_answer_at) * 1000)
        if fused_state in {"ANSWERED_PENDING", "HUMAN"} and self._amd_answer_at <= 0:
            if bool(dom_payload.get("hasTimer")) or fused_state == "HUMAN":
                self._amd_answer_at = time.monotonic()
        state = {
            "HUMAN": "CONNECTED",
            "ANSWERED_PENDING": "ANSWERED_PENDING",
        }.get(fused_state, fused_state)

        # Vicidial-style gate: agent UI only after AMD confirms HUMAN, not DOM timer alone.
        if state == "CONNECTED" and fused_state != "HUMAN":
            state = (
                "ANSWERED_PENDING"
                if self._state in {"DIALING", "RINGING", "ANSWERED_PENDING", "CONNECTED"}
                else self._state
            )
        if state == "UNKNOWN" and self._active_call:
            if self._state in {"DIALING", "RINGING", "ANSWERED_PENDING", "CONNECTED"}:
                state = self._state
            else:
                state = "DIALING"
        debug = {
            "phone": self._current_call_phone or self._pending_dial_phone,
            "slot": self.slot_id,
            "elapsed": round(elapsed, 2),
            "dom_state": decision.state,
            "call_text": str(dom_payload.get("callText", ""))[:500],
            "has_ringing_text": bool(dom_payload.get("hasRingingText", False)),
            "has_ringing_node": bool(dom_payload.get("hasRingingNode", False)),
            "has_timer": bool(dom_payload.get("hasTimer", False)),
            "timer_text": str(dom_payload.get("timerText", "")),
            "audio_state": fused.debug.get("audio_state") or self._audio_state_from_features(audio_features),
            "fused_state": fused_state,
            "confidence": round(float(fused.confidence), 3),
            "reason": fused.reason,
            "ui_state": fused.debug.get("ui_state") or fused_state,
            "detection_time_ms": self._amd_decision_ms,
            "rms": float(getattr(audio_features, "rms", 0.0) or 0.0),
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
            "audio_backend_name": getattr(audio_features, "backend_name", ""),
            "audio_reason": getattr(audio_features, "reason", ""),
            "vad_backend": getattr(audio_features, "vad_backend", ""),
            "vad_confidence": float(getattr(audio_features, "vad_confidence", 0.0) or 0.0),
        }
        # Emit detection debug for UI/DB layers.
        self.detection_update.emit(self.slot_id, debug)
        if bool(self._runtime_cfg.get("live_debug_mode", False)):
            self._emit_call_debug(debug)


        if self._active_call and decision.state == "IDLE" and fused_state == "UNKNOWN":
            state = "IDLE"

        if state == "IDLE" and self._active_call:
            if self._state == "CONNECTED":
                self._emit_log("Connected call ended")
                self._active_call = False
                self.stop_polling()
                self._set_state("ENDED")
                return
            if (
                self._state == "DIALING"
                and self._call_clicked_at
                and (time.monotonic() - self._call_clicked_at) >= 12.0
            ):
                self._emit_log("Dial attempt did not open a call panel")
                self._active_call = False
                self.stop_polling()
                self._set_state("FAILED")
                return
            self._idle_count += 1
            idle_reference = self._call_clicked_at or self._dial_started_at
            age = time.monotonic() - idle_reference
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

        # Debounce + ringing-safety for voicemail.
        # Rule: RINGING is NOT voicemail and must not trigger hangup before timeout.
        if state == "VOICEMAIL":
            if self._state in {"DIALING", "RINGING"}:
                # Treat as non-terminal evidence until we have real CONNECTED/PICKUP evidence.
                # Allow it to be re-evaluated, but never promote to VOICEMAIL during ringing.
                state = self._state if self._state != "IDLE" else "RINGING"
                self._vm_count += 1
            else:
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
            if answer_window_ready and self._ctrl_count >= 4 and fused_state == "HUMAN":
                state = "CONNECTED"
            elif self._state in {"ANSWERED_PENDING", "CONNECTED"} or fused_state == "ANSWERED_PENDING":
                state = "ANSWERED_PENDING"
            else:
                state = "RINGING" if self._state != "CONNECTED" else "CONNECTED"
        else:
            self._ctrl_count = 0

        # Safety: GV in-call controls/timer are not human confirmation by themselves.
        if raw_state == "CONNECTED" and fused_state != "HUMAN":
            if self._state in ("RINGING", "DIALING", "ANSWERED_PENDING", "CONNECTED"):
                state = "ANSWERED_PENDING"
            else:
                state = "RINGING" if self._state != "CONNECTED" else "CONNECTED"


        if state == "CONNECTED" and self._state != "CONNECTED":
            self._emit_log("Human pickup confirmed by AMD — connecting agent")

        # Promote DIALING → RINGING when in-call UI appears
        if state == "RINGING" and self._state == "DIALING":
            self._emit_log("Ringing…")
        if state == "ANSWERED_PENDING" and self._state not in {"ANSWERED_PENDING", "CONNECTED"}:
            self._emit_log("Answer detected — AMD classifying (waiting for human audio pattern)…")

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
            "fused_state", "confidence", "reason", "rms", "ringback",
            "speech_duration", "silence_duration", "beep_detected",
            "human_greeting_detected", "voicemail_confirmations",
            "should_hangup", "audio_backend_name", "vad_backend", "vad_confidence",
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
