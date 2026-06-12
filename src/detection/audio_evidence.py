"""Audio evidence scoring for call detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AudioEvidence:
    answer_detected: bool = False
    ringing_score: float = 0.0
    human_score: float = 0.0
    voicemail_score: float = 0.0
    ivr_score: float = 0.0
    busy_score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


class AudioEvidenceScorer:
    def score(self, features: Any | None) -> AudioEvidence:
        evidence = AudioEvidence()
        if features is None:
            return evidence

        def get(name: str, default: Any = 0.0) -> Any:
            return getattr(features, name, default)

        rms = float(get("rms", 0.0) or 0.0)
        has_speech = bool(get("has_speech_like", False))
        is_silent = bool(get("is_silent", rms < 0.012))
        ring_conf = float(get("ringback_cadence_confidence", 0.0) or 0.0)
        busy_conf = float(get("busy_tone_cadence_confidence", 0.0) or 0.0)
        beep_conf = float(get("beep_hz_confidence", 0.0) or 0.0)
        speech_duration = float(get("speech_duration_seconds", 0.0) or 0.0)
        silence_duration = float(get("silence_duration_seconds", 0.0) or 0.0)
        continuous = float(get("continuous_greeting_duration_seconds", 0.0) or 0.0)
        background = float(get("background_noise_level", rms) or 0.0)

        evidence.raw = {
            "rms": rms,
            "has_speech_like": has_speech,
            "is_silent": is_silent,
            "ringback_cadence_confidence": ring_conf,
            "busy_tone_cadence_confidence": busy_conf,
            "beep_hz_confidence": beep_conf,
            "speech_duration_seconds": speech_duration,
            "silence_duration_seconds": silence_duration,
            "continuous_greeting_duration_seconds": continuous,
            "background_noise_level": background,
            "beep_detected": bool(get("beep_detected", False)),
        }

        evidence.ringing_score = ring_conf
        if ring_conf >= 0.65:
            evidence.reasons.append("ringback cadence")

        evidence.busy_score = busy_conf
        if busy_conf >= 0.8:
            evidence.reasons.append("busy cadence")

        evidence.answer_detected = bool((rms >= 0.025 or has_speech) and ring_conf < 0.65 and busy_conf < 0.8)
        if evidence.answer_detected:
            evidence.reasons.append("remote audio energy")

        if bool(get("human_greeting_detected", False)):
            evidence.human_score = max(evidence.human_score, 0.9)
            evidence.reasons.append("audio human greeting")
        if bool(get("short_speech_burst_detected", False)) or (0.15 <= speech_duration <= 2.5):
            evidence.human_score = max(evidence.human_score, 0.75)
            evidence.reasons.append("short speech burst")
        if background >= 0.08 and silence_duration <= 3.0:
            evidence.human_score = max(evidence.human_score, 0.45)
            evidence.reasons.append("background noise/silence gaps")

        if bool(get("beep_detected", False)) or beep_conf >= 0.6:
            evidence.voicemail_score = max(evidence.voicemail_score, 0.9)
            evidence.reasons.append("beep tone")
        if continuous >= 3.5:
            evidence.voicemail_score = max(evidence.voicemail_score, 0.75)
            evidence.reasons.append("continuous stable greeting")
        return evidence
