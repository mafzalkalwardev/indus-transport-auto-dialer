"""High-level local call-state detection facade.

This module names the real pipeline used by the dialer:

DOM/call-stage evidence + audio listener/VAD + human/voicemail scoring + FSM.
It keeps compatibility with the existing ``LocalCallDetector`` while giving
future work a clear extension point for transcription and trained classifiers.
"""
from __future__ import annotations

from typing import Any

from .local_call_detector import CallDecision, DetectionConfig, LocalCallDetector

try:
    from .detection.external_evidence import ExternalEvidence
except Exception:
    ExternalEvidence = None  # type: ignore[misc,assignment]


class CallStateDetector:
    def __init__(self, config: DetectionConfig | None = None):
        self._detector = LocalCallDetector(config)

    def reset_for_new_call(self) -> None:
        self._detector.reset_for_new_call()

    def update(
        self,
        *,
        dom_evidence: dict[str, Any] | None,
        audio_features: Any | None,
        elapsed_seconds: float,
        external_evidence: "ExternalEvidence | None" = None,
    ) -> CallDecision:
        return self._detector.decide(
            dom_evidence=dom_evidence,
            audio_features=audio_features,
            elapsed_seconds=elapsed_seconds,
            external_evidence=external_evidence,
        )
