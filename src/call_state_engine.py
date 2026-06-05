"""Call-state classifier for Google Voice live-slot evidence.

This module keeps the operator-facing state rules out of the browser glue. It
is intentionally conservative: a call is not marked connected while Google
Voice still says Calling/Ringing unless a real call timer is present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


VOICEMAIL_PHRASES = (
    "leave a message",
    "leave your message",
    "leave your name and number",
    "leave your name, number",
    "reason for call",
    "record after the tone",
    "record your message",
    "after the beep",
    "at the tone",
    "after the tone",
    "press pound when finished",
    "press # when finished",
    "leave a voicemail",
    "voicemail box",
    "mailbox is full",
    "your call has been forwarded",
    "forwarded to voicemail",
    "please record your message",
    "please leave your message",
    "please leave a message",
    "please leave a message for",
    "i am not available",
    "i am unavailable",
    "i am not available right now",
    "i'm not available",
    "i'm unavailable",
    "can't come to the phone",
    "cannot come to the phone",
    "i will call you back",
    "i'll call you back",
    "call you back as soon as",
    "you have reached the voicemail",
    "not available to take",
    "cannot take your call",
    "can't take your call",
    "person you are calling is not available",
    "person you are calling is currently unavailable",
    "person you are calling cannot be reached",
    "wireless customer you are calling is not available",
    "subscriber you are trying to reach is not in service",
    "subscriber is not reachable",
    "user is not accepting calls",
    "number you have dialed is not in service",
    "number is temporarily unavailable",
    "number you have reached has been disconnected",
    "number has been disconnected",
    "not in service",
    "out of service",
    "call cannot be completed as dialed",
    "phone you are calling is switched off",
    "please try your call again later",
)

VOICEMAIL_PATTERNS = (
    re.compile(r"hi[, ]+this is .{0,80}(not available|unavailable|leave)", re.I),
    re.compile(r"this is .{0,80}(voicemail|not available|unavailable|leave)", re.I),
    re.compile(r"leave .{0,50}(name|number|message|reason)", re.I),
    re.compile(r"(after|at) the (tone|beep).{0,90}(record|leave|message)", re.I),
    re.compile(r"(record|leave).{0,90}(message|voicemail).{0,90}(tone|beep|pound|#)", re.I),
    re.compile(r"(call|try).{0,40}(again|back).{0,40}(later|soon)", re.I),
)

RINGING_WORDS = ("calling", "ringing", "connecting", "trying to connect")


@dataclass(frozen=True)
class CallStateDecision:
    state: str
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


class CallStateEngine:
    """Classify Google Voice UI/caption evidence into operator states."""

    def classify(self, raw: str | dict[str, Any] | None) -> CallStateDecision:
        if raw is None:
            return CallStateDecision("IDLE", "empty result", {})
        if isinstance(raw, str):
            return CallStateDecision(raw or "IDLE", "legacy string result", {})

        evidence = dict(raw)
        state = str(evidence.get("state") or "IDLE").upper()
        text = self._normalize(str(evidence.get("callText") or ""))

        if self._is_voicemail(text) or evidence.get("hasVoicemailCue"):
            return CallStateDecision("VOICEMAIL", "voicemail phrase/cue", evidence)

        has_ringing = bool(evidence.get("hasRingingText") or evidence.get("hasRingingNode"))
        has_timer = bool(evidence.get("hasTimer"))
        has_enabled_answer_control = bool(evidence.get("hasEnabledAnswerControl"))

        # Google Voice can render disabled transfer/hold/add buttons while it
        # still says Calling. Do not promote that to pickup.
        if has_ringing and not has_timer:
            return CallStateDecision("RINGING", "ringing/calling text still visible", evidence)

        if state == "CONNECTED" and has_timer:
            return CallStateDecision("CONNECTED", "live call timer", evidence)

        if state == "CONNECTED_CTRL":
            if has_enabled_answer_control:
                return CallStateDecision("CONNECTED_CTRL", "enabled answer controls", evidence)
            return CallStateDecision("RINGING", "answer controls are disabled", evidence)

        if state in {"IDLE", "DIALING", "RINGING", "ENDED", "NO_ANSWER", "FAILED"}:
            return CallStateDecision(state, "explicit browser state", evidence)

        if any(word in text for word in RINGING_WORDS):
            return CallStateDecision("RINGING", "ringing text fallback", evidence)
        return CallStateDecision("RINGING", "in-call state without pickup evidence", evidence)

    def _is_voicemail(self, text: str) -> bool:
        if not text:
            return False
        if any(phrase in text for phrase in VOICEMAIL_PHRASES):
            return True
        return any(pattern.search(text) for pattern in VOICEMAIL_PATTERNS)

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\u2019", "'").lower()).strip()
