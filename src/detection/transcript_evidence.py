"""Transcript evidence scoring for call detection."""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .unified_transcript_classifier import UnifiedClassification, classify_transcript


@dataclass
class TranscriptEvidence:
    human_score: float = 0.0
    voicemail_score: float = 0.0
    ivr_score: float = 0.0
    busy_score: float = 0.0
    transcript: str = ""
    classification: str = "unknown"
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)


class TranscriptEvidenceScorer:
    def score(
        self,
        transcript: str | None,
        *,
        duration_seconds: float = 0.0,
        near_silence: bool = False,
    ) -> TranscriptEvidence:
        text = re.sub(r"\s+", " ", (transcript or "")).strip()
        evidence = TranscriptEvidence(transcript=text)
        if not text and not near_silence:
            return evidence

        result: UnifiedClassification = classify_transcript(
            text,
            duration_seconds=duration_seconds,
            near_silence=near_silence,
        )
        evidence.human_score = float(result.human_score or 0.0)
        evidence.voicemail_score = float(result.voicemail_score or 0.0)
        evidence.ivr_score = float(result.ivr_score or 0.0)
        evidence.busy_score = float(result.busy_score or 0.0)
        evidence.classification = result.classification
        evidence.confidence = float(result.confidence or 0.0)

        if result.human_score <= 0 and result.classification in {"human", "human_greeting"}:
            evidence.human_score = max(result.confidence, 0.78)
        if result.voicemail_score <= 0 and result.classification in {"voicemail", "voicemail_greeting"}:
            evidence.voicemail_score = max(result.confidence, 0.9)
        if result.ivr_score <= 0 and result.classification in {"ivr", "call_screening_prompt"}:
            evidence.ivr_score = max(result.confidence, 0.85)

        if evidence.voicemail_score >= 0.65:
            evidence.voicemail_score = max(evidence.voicemail_score, 1.0)
        if evidence.human_score >= 0.65:
            evidence.human_score = max(evidence.human_score, 1.0)
        if evidence.ivr_score >= 0.65:
            evidence.ivr_score = max(evidence.ivr_score, 1.0)

        if result.matched_rules:
            evidence.reasons.append(result.matched_rules[0])
        elif result.reason:
            evidence.reasons.append(result.reason)
        return evidence
