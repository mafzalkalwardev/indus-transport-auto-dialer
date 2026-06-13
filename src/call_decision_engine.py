"""CallDecisionEngine is a small wrapper around the call detection FSM.

In the current codebase, the gv_controller calls this engine for each poll tick.

This engine:
- ensures per-call reset
- manages a stable final outcome emission
- returns a state + confidence + reason each poll

It is kept separate so gv_controller code remains thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .detection.call_state_machine import CallStateMachine, CallStateMachineConfig
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
        cfg = detector_config or DetectionConfig()
        self.state_machine = CallStateMachine(
            CallStateMachineConfig(max_ring_seconds=float(cfg.max_ring_seconds))
        )
        self._in_call = False

    def start_call(self) -> None:
        self.detector.reset_for_new_call()
        self.state_machine = CallStateMachine(self.state_machine.config)
        self.state_machine.start_call()
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
        detector_decision = self.detector.decide(
            dom_evidence=dom_evidence,
            audio_features=audio_features,
            elapsed_seconds=elapsed_seconds,
        )
        self.state_machine.update_dom(dom_evidence)
        self.state_machine.update_audio(audio_features)
        transcript = str(getattr(audio_features, "transcript", "") or "")
        if not transcript and dom_evidence:
            transcript = str(dom_evidence.get("callText") or "")
        if transcript:
            self.state_machine.update_transcript(transcript)
        self.state_machine.update_timing(elapsed_seconds=elapsed_seconds)

        snapshot = self.state_machine.get_debug_snapshot()
        fsm_state = self.state_machine.get_current_state()
        detector_state = str(detector_decision.state.value)
        state = self._compat_state(detector_state)
        reason = str(detector_decision.reason or snapshot.get("last_transition_reason") or "collecting evidence")
        return CallDecisionResult(
            state=state,
            confidence=float(detector_decision.confidence),
            reason=reason,
            debug={
                **snapshot,
                **detector_decision.debug,
                "fsm_state": fsm_state,
                "detector_state": detector_state,
                "candidate_state": detector_decision.debug.get("candidate_state", detector_state),
                "audio_state": self._audio_state(audio_features),
                "fsm_confidence": snapshot.get("confidence", 0.0),
                "voicemail_score": detector_decision.debug.get(
                    "voicemail_score",
                    detector_decision.debug.get("voicemail_conf", snapshot.get("voicemail_score", 0.0)),
                ),
                "human_conf": detector_decision.debug.get("human_conf", snapshot.get("human_score", 0.0)),
                "voicemail_conf": detector_decision.debug.get(
                    "voicemail_conf",
                    snapshot.get("voicemail_score", 0.0),
                ),
            },
        )

    @staticmethod
    def _compat_state(state: str) -> str:
        if state in {"ANSWER_DETECTED", "EARLY_ANALYSIS", "HUMAN_CANDIDATE", "VOICEMAIL_CANDIDATE", "IVR_CANDIDATE"}:
            return "ANSWERED_PENDING"
        return state

    @staticmethod
    def _audio_state(audio_features: AudioFeatures | Any | None) -> str:
        if audio_features is None:
            return "OFF"
        if float(getattr(audio_features, "busy_tone_cadence_confidence", 0.0) or 0.0) >= 0.8:
            return "BUSY"
        if float(getattr(audio_features, "ringback_cadence_confidence", 0.0) or 0.0) >= 0.65:
            return "RINGING"
        if bool(getattr(audio_features, "beep_detected", False)):
            return "BEEP"
        if bool(getattr(audio_features, "has_speech_like", False)):
            return "SPEECH"
        if bool(getattr(audio_features, "is_silent", True)):
            return "SILENCE"
        return "NOISE"

