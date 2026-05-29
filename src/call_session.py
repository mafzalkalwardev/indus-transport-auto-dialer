"""
Call state machine — ported from GoogleVoiceAgent-Active/src/call_session.py.
Tracks state transitions for a single outbound call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CallState(Enum):
    IDLE      = "IDLE"
    DIALING   = "DIALING"
    RINGING   = "RINGING"
    CONNECTED = "CONNECTED"
    VOICEMAIL = "VOICEMAIL"
    ENDED     = "ENDED"
    FAILED    = "FAILED"


_ALLOWED: dict[CallState, set[CallState]] = {
    CallState.IDLE:      {CallState.DIALING, CallState.FAILED},
    CallState.DIALING:   {CallState.RINGING, CallState.CONNECTED,
                          CallState.VOICEMAIL, CallState.ENDED, CallState.FAILED},
    CallState.RINGING:   {CallState.CONNECTED, CallState.VOICEMAIL,
                          CallState.ENDED, CallState.FAILED},
    CallState.CONNECTED: {CallState.VOICEMAIL, CallState.ENDED, CallState.FAILED},
    CallState.VOICEMAIL: {CallState.ENDED, CallState.FAILED},
    CallState.ENDED:     set(),
    CallState.FAILED:    set(),
}


@dataclass
class CallSession:
    phone:        str
    contact_name: str = ""
    state:        CallState = CallState.IDLE
    started_at:   Optional[datetime] = None
    connected_at: Optional[datetime] = None
    ended_at:     Optional[datetime] = None
    outcome:      str = ""
    notes:        list[str] = field(default_factory=list)

    def transition(self, new_state: CallState, note: str = "") -> None:
        allowed = _ALLOWED.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal transition {self.state.value} → {new_state.value}"
            )
        now = datetime.now()
        if new_state == CallState.DIALING:
            self.started_at = now
        elif new_state == CallState.CONNECTED and self.connected_at is None:
            self.connected_at = now
        elif new_state in (CallState.ENDED, CallState.FAILED) and self.ended_at is None:
            self.ended_at = now
        self.state = new_state
        if note:
            self.notes.append(note)

    def is_terminal(self) -> bool:
        return self.state in (CallState.ENDED, CallState.FAILED)

    def connected_duration_s(self) -> Optional[float]:
        if self.connected_at and self.ended_at:
            return (self.ended_at - self.connected_at).total_seconds()
        return None

    def total_duration_s(self) -> Optional[float]:
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
