"""DOM evidence scoring for call detection.

This module does not change call state. It only translates Google Voice DOM
payloads into normalized evidence scores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DomEvidence:
    answer_detected: bool = False
    ringing_detected: bool = False
    ended: bool = False
    failed: bool = False
    human_score: float = 0.0
    voicemail_score: float = 0.0
    ivr_score: float = 0.0
    busy_score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


class DomEvidenceScorer:
    def score(self, payload: dict[str, Any] | None) -> DomEvidence:
        raw = dict(payload or {})
        state = str(raw.get("state") or "IDLE").upper()
        text = str(raw.get("callText") or "").lower()
        evidence = DomEvidence(raw=raw)

        evidence.ringing_detected = bool(
            raw.get("hasRingingText")
            or raw.get("hasRingingNode")
            or state == "RINGING"
        )
        if evidence.ringing_detected:
            evidence.reasons.append("DOM ringing/calling text")

        evidence.answer_detected = bool(
            raw.get("hasTimer")
            or raw.get("hasEnabledHoldButton")
            or raw.get("hasEnabledMuteButton")
            or raw.get("hasEnabledAnswerControl")
            or state in {"CONNECTED", "CONNECTED_CTRL", "ANSWERED", "HUMAN"}
        )
        if evidence.answer_detected:
            evidence.human_score = max(evidence.human_score, 0.45)
            evidence.reasons.append("DOM answer controls/timer")

        if raw.get("hasVoicemailCue") and evidence.answer_detected:
            evidence.voicemail_score = max(evidence.voicemail_score, 0.75)
            evidence.reasons.append("DOM voicemail cue after answer")

        if any(phrase in text for phrase in ("press 1", "press 2", "for sales", "for support")):
            evidence.ivr_score = max(evidence.ivr_score, 0.7)
            evidence.reasons.append("DOM IVR text")

        evidence.ended = state in {"ENDED", "ENDED_MANUALLY", "MANUAL_ENDED"}
        evidence.failed = state in {"FAILED", "ERROR", "BROWSER_CRASH"}
        return evidence
