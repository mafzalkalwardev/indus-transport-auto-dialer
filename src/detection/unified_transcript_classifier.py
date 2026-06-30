"""Unified transcript classification from Prototype A + B extension rules."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


VOICEMAIL_PHRASES = [
    "your call has been forwarded",
    "please leave your message",
    "leave a message",
    "leave your message",
    "record your message",
    "voice message system",
    "mailbox",
    "mailbox is full",
    "not available",
    "not available to take your call",
    "unavailable",
    "the person you are trying to reach",
    "has not set up voicemail",
    "automatic voice message system",
    "you have reached",
    "you've reached",
    "please record",
    "when you are finished",
    "after the tone",
    "at the tone",
    "after the beep",
    "at the beep",
    "voicemail",
]

VOICEMAIL_TONE_CONTEXT = [
    "leave a message",
    "record your message",
    "mailbox",
    "voice message system",
    "not available",
    "unavailable",
    "the person you are trying to reach",
]

CALL_SCREENING_PHRASES = [
    "state your name",
    "please state your name",
    "say your name",
    "google voice will try to connect you",
    "try to connect you",
    "after the tone and google voice will try to connect you",
]

HUMAN_GREETINGS = [
    "hello",
    "hello?",
    "hi",
    "yes",
    "yeah",
    "who is this",
    "speaking",
    "good morning",
    "good afternoon",
    "good evening",
    "assalamualaikum",
]

DISCONNECTED_PHRASES = [
    "not in service",
    "temporarily unavailable",
    "subscriber is not available",
]

CARRIER_PHRASES = [
    "the number you have dialed",
    "cannot be completed",
    "call cannot be completed",
    "couldn't complete your call",
    "could not complete your call",
    "we couldn't complete",
    "unable to connect",
    "not able to connect",
]

BUSY_PHRASES = [
    "busy",
    "line is busy",
]

IVR_PHRASES = [
    "press 1",
    "press 2",
    "for sales",
    "for support",
    "menu",
    "representative",
    "for english",
]


@dataclass
class UnifiedClassification:
    classification: str = "unknown"
    confidence: float = 0.0
    human_score: float = 0.0
    voicemail_score: float = 0.0
    ivr_score: float = 0.0
    busy_score: float = 0.0
    matched_rules: list[str] = field(default_factory=list)
    reason: str = ""


def normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^\w\s']", " ", (text or "").lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _find_matches(normalized: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if phrase in normalized]


def classify_transcript(
    transcript: str,
    *,
    duration_seconds: float = 0.0,
    near_silence: bool = False,
) -> UnifiedClassification:
    normalized = normalize_text(transcript)
    if duration_seconds > 0 and duration_seconds < 2:
        return UnifiedClassification(
            classification="disconnected_or_failed",
            confidence=0.74,
            matched_rules=["recording_less_than_2_seconds"],
            reason="Very short audio window",
        )

    if near_silence and not normalized:
        return UnifiedClassification(
            classification="unknown_or_silence",
            confidence=0.7,
            matched_rules=["near_silence"],
            reason="Near silence with no transcript",
        )

    if not normalized:
        return UnifiedClassification(
            classification="unknown",
            confidence=0.25,
            reason="Empty transcript",
        )

    screening = _find_matches(normalized, CALL_SCREENING_PHRASES)
    if screening:
        return UnifiedClassification(
            classification="call_screening_prompt",
            confidence=0.94,
            ivr_score=0.85,
            matched_rules=screening,
            reason=f"Call screening phrase: {screening[0]}",
        )

    for phrase in VOICEMAIL_PHRASES:
        if phrase in normalized:
            conf = min(0.98, 0.82 + 0.05)
            return UnifiedClassification(
                classification="voicemail",
                confidence=conf,
                voicemail_score=conf,
                matched_rules=[phrase],
                reason=f"Voicemail phrase: {phrase}",
            )

    tone_hit = any(
        token in normalized
        for token in ("after the tone", "at the tone", "after the beep", "at the beep")
    )
    if tone_hit:
        for phrase in VOICEMAIL_TONE_CONTEXT:
            if phrase in normalized:
                conf = 0.9
                return UnifiedClassification(
                    classification="voicemail",
                    confidence=conf,
                    voicemail_score=conf,
                    matched_rules=[f"tone + {phrase}"],
                    reason=f"Tone context voicemail: {phrase}",
                )

    for group, phrases, label, busy_score in (
        ("disconnected", DISCONNECTED_PHRASES, "disconnected_or_failed", 0.0),
        ("carrier", CARRIER_PHRASES, "disconnected_or_failed", 0.0),
        ("busy", BUSY_PHRASES, "busy", 0.9),
        ("ivr", IVR_PHRASES, "ivr", 0.0),
    ):
        matches = _find_matches(normalized, phrases)
        if matches:
            result = UnifiedClassification(
                classification=label,
                confidence=min(0.98, 0.82 + len(matches) * 0.05),
                matched_rules=matches,
                reason=f"{group} phrase: {matches[0]}",
            )
            if label == "busy":
                result.busy_score = busy_score
            elif label == "ivr":
                result.ivr_score = result.confidence
            return result

    words = normalized.split()
    human_matches = _find_matches(normalized, HUMAN_GREETINGS)
    if human_matches and len(words) < 8:
        conf = 0.78 if len(words) <= 3 else 0.68
        return UnifiedClassification(
            classification="human",
            confidence=conf,
            human_score=conf,
            matched_rules=human_matches,
            reason=f"Human greeting: {human_matches[0]}",
        )

    return UnifiedClassification(
        classification="unknown",
        confidence=0.35,
        reason="No decisive AMD phrase found",
    )


def classification_to_external_label(classification: str) -> str:
    mapping = {
        "human": "human_picked",
        "human_greeting": "human_picked",
        "voicemail": "voicemail_detected",
        "voicemail_greeting": "voicemail_detected",
        "call_screening_prompt": "call_screening_prompt",
        "busy": "busy_or_failed",
        "disconnected_or_failed": "busy_or_failed",
        "ivr": "call_screening_prompt",
        "unknown_or_silence": "unknown_or_silence",
    }
    return mapping.get(classification, classification or "unknown")
