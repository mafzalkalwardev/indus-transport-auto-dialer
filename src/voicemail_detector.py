"""Voicemail scoring from transcript, timing, and tone evidence."""
from __future__ import annotations

from dataclasses import dataclass, field


VOICEMAIL_KEYWORDS = (
    "leave a message",
    "after the tone",
    "after the beep",
    "at the tone",
    "not available",
    "mailbox",
    "your call has been forwarded",
    "please record your message",
    "voicemail",
)


@dataclass(frozen=True)
class VoicemailDetection:
    candidate: bool
    confidence: float
    factors: list[str] = field(default_factory=list)


class VoicemailDetector:
    def classify(
        self,
        *,
        transcript: str = "",
        answer_elapsed_seconds: float = 0.0,
        continuous_greeting_duration_seconds: float = 0.0,
        voicemail_keywords_detected_count: int = 0,
        beep_detected: bool = False,
        beep_confidence: float = 0.0,
        dom_voicemail: bool = False,
        repeated_machine_pattern: bool = False,
        human_detected: bool = False,
    ) -> VoicemailDetection:
        factors: list[str] = []
        text_keywords = self.keyword_count(transcript)
        keyword_count = max(int(voicemail_keywords_detected_count or 0), text_keywords)

        if continuous_greeting_duration_seconds >= 4.0:
            factors.append("long scripted greeting")
        if keyword_count > 0:
            factors.append("voicemail keyword")
        if beep_detected or beep_confidence >= 0.6:
            factors.append("beep tone")
        if repeated_machine_pattern:
            factors.append("machine-like pattern")
        if dom_voicemail:
            factors.append("DOM voicemail cue")

        confidence = min(1.0, (len(factors) / 2.0) * 0.5)
        if "beep tone" in factors:
            confidence = min(1.0, confidence + 0.35)
        if "voicemail keyword" in factors:
            confidence = min(1.0, confidence + 0.20)
        if human_detected:
            confidence = min(confidence, 0.35)

        candidate = (
            answer_elapsed_seconds >= 7.0
            and not human_detected
            and len(factors) >= 2
            and confidence >= 0.75
        )
        return VoicemailDetection(candidate=candidate, confidence=confidence, factors=factors)

    @staticmethod
    def keyword_count(text: str) -> int:
        lower = (text or "").lower()
        return sum(1 for phrase in VOICEMAIL_KEYWORDS if phrase in lower)
