"""Transcript evidence scoring for call detection."""
from __future__ import annotations

from dataclasses import dataclass, field
import re


HUMAN_PHRASES = (
    "hello",
    "yeah",
    "yes",
    "who is this",
    "good morning",
    "good afternoon",
    "speaking",
)

VOICEMAIL_PHRASES = (
    "leave your message",
    "leave a message",
    "after the tone",
    "after the beep",
    "mailbox",
    "record your message",
    "not available",
    "your call has been forwarded",
    "please leave a message",
    "voicemail",
)

IVR_PHRASES = (
    "press 1",
    "press 2",
    "for sales",
    "for support",
    "menu",
    "representative",
    "for english",
)


@dataclass
class TranscriptEvidence:
    human_score: float = 0.0
    voicemail_score: float = 0.0
    ivr_score: float = 0.0
    transcript: str = ""
    reasons: list[str] = field(default_factory=list)


class TranscriptEvidenceScorer:
    def score(self, transcript: str | None) -> TranscriptEvidence:
        text = re.sub(r"\s+", " ", (transcript or "").lower()).strip()
        evidence = TranscriptEvidence(transcript=transcript or "")
        if not text:
            return evidence

        if any(self._contains_phrase(text, phrase) for phrase in HUMAN_PHRASES):
            evidence.human_score = 1.0
            evidence.reasons.append("human phrase")
        if any(phrase in text for phrase in VOICEMAIL_PHRASES):
            evidence.voicemail_score = 1.0
            evidence.reasons.append("voicemail phrase")
        if any(phrase in text for phrase in IVR_PHRASES):
            evidence.ivr_score = 1.0
            evidence.reasons.append("IVR phrase")
        return evidence

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        return bool(re.search(rf"\b{re.escape(phrase)}\b", text, re.I))
