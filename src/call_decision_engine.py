"""CallDecisionEngine is a small wrapper around LocalCallDetector.

In the current codebase, the gv_controller will call LocalCallDetector
for each poll tick.

This engine:
- ensures per-call reset
- manages a stable final outcome emission
- returns a state + confidence + reason each poll

It is kept separate so gv_controller code remains thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .local_call_detector import AudioFeatures, DetectionConfig, LocalCallDetector


@dataclass
class CallDecisionResult:
    state: str
    confidence: float
    reason: str
    debug: Dict[str, Any]


class CallDecisionEngine:
    def __init__(
        self,
        detector: LocalCallDetector | None = None,
        detector_config: DetectionConfig | None = None,
    ):
        self.detector = detector or LocalCallDetector(detector_config)
        self._in_call = False

    def start_call(self) -> None:
        self.detector.reset_for_new_call()
        self._in_call = True

    def stop_call(self) -> None:
        self._in_call = False

    def update(
        self,
        *,
        dom_evidence: Dict[str, Any] | None,
        audio_features: AudioFeatures | Any | None,
        elapsed_seconds: float,
    ) -> CallDecisionResult:
        if not self._in_call:
            self.start_call()
        d = self.detector.decide(
            dom_evidence=dom_evidence,
            audio_features=audio_features,
            elapsed_seconds=elapsed_seconds,
        )
        return CallDecisionResult(
            state=d.state.value,
            confidence=d.confidence,
            reason=d.reason,
            debug=d.debug,
        )

