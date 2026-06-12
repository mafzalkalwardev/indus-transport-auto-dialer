"""Timing evidence scoring for call detection."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TimingEvidence:
    ring_timeout: bool = False
    human_score: float = 0.0
    voicemail_score: float = 0.0
    ivr_score: float = 0.0
    elapsed_seconds: float = 0.0
    answer_elapsed_seconds: float = 0.0
    reasons: list[str] = field(default_factory=list)


class TimingEvidenceScorer:
    def __init__(self, *, max_ring_seconds: float = 55.0):
        self.max_ring_seconds = float(max_ring_seconds)

    def score(
        self,
        *,
        elapsed_seconds: float,
        answer_elapsed_seconds: float = 0.0,
        in_ringing_state: bool = False,
    ) -> TimingEvidence:
        elapsed = max(0.0, float(elapsed_seconds or 0.0))
        answer_elapsed = max(0.0, float(answer_elapsed_seconds or 0.0))
        evidence = TimingEvidence(
            elapsed_seconds=elapsed,
            answer_elapsed_seconds=answer_elapsed,
        )
        if in_ringing_state and elapsed >= self.max_ring_seconds:
            evidence.ring_timeout = True
            evidence.reasons.append("ring timeout")
        if 0.5 <= answer_elapsed <= 4.0:
            evidence.human_score = 0.35
            evidence.reasons.append("early human answer window")
        if answer_elapsed >= 2.0:
            evidence.voicemail_score = 0.25
            evidence.ivr_score = 0.25
            evidence.reasons.append("machine confirmation window")
        return evidence
