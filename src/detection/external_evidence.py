"""Canonical external evidence model from Chrome extension prototypes."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ProviderName(str, Enum):
    PROTOTYPE_A = "prototype_a"
    PROTOTYPE_B = "prototype_b"


class ProviderHealth(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNKNOWN = "unknown"


class ExternalLabel(str, Enum):
    UNKNOWN = "unknown"
    UNKNOWN_OR_SILENCE = "unknown_or_silence"
    STILL_RINGING = "still_ringing"
    HUMAN_PICKED = "human_picked"
    VOICEMAIL_DETECTED = "voicemail_detected"
    CALL_SCREENING_PROMPT = "call_screening_prompt"
    BUSY_OR_FAILED = "busy_or_failed"
    ENDED = "ended"
    NO_ANSWER = "no_answer"
    HUMAN = "human"
    VOICEMAIL = "voicemail"
    BUSY = "busy"
    DISCONNECTED_OR_FAILED = "disconnected_or_failed"


@dataclass
class ExternalEvidence:
    provider: ProviderName
    call_id: Optional[str] = None
    line_id: Optional[str] = None
    raw_label: str = ExternalLabel.UNKNOWN.value
    confidence: float = 0.0
    transcript: str = ""
    timestamp: float = 0.0
    latency_ms: float = 0.0
    provider_health: ProviderHealth = ProviderHealth.UNKNOWN
    diagnostic_reason: str = ""
    pre_answer: bool = False
    post_answer: bool = False
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return self.provider_health == ProviderHealth.CONNECTED and self.confidence > 0.0

    def is_human_like(self) -> bool:
        return self.raw_label in {
            ExternalLabel.HUMAN_PICKED.value,
            ExternalLabel.HUMAN.value,
        }

    def is_voicemail_like(self) -> bool:
        return self.raw_label in {
            ExternalLabel.VOICEMAIL_DETECTED.value,
            ExternalLabel.VOICEMAIL.value,
        }

    def is_busy_like(self) -> bool:
        return self.raw_label in {
            ExternalLabel.BUSY_OR_FAILED.value,
            ExternalLabel.BUSY.value,
        }

    def is_ringing_like(self) -> bool:
        return self.raw_label == ExternalLabel.STILL_RINGING.value

    def is_ivr_like(self) -> bool:
        return self.raw_label == ExternalLabel.CALL_SCREENING_PROMPT.value

    def is_diagnostic_only(self) -> bool:
        return self.raw_label in {
            ExternalLabel.UNKNOWN.value,
            ExternalLabel.UNKNOWN_OR_SILENCE.value,
            ExternalLabel.NO_ANSWER.value,
            ExternalLabel.ENDED.value,
            ExternalLabel.DISCONNECTED_OR_FAILED.value,
        }
