"""Finite state machine for fast, evidence-fused call detection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import time
from typing import Any

from transitions import Machine

from .audio_evidence import AudioEvidence, AudioEvidenceScorer
from .dom_evidence import DomEvidence, DomEvidenceScorer
from .timing_evidence import TimingEvidence, TimingEvidenceScorer
from .transcript_evidence import TranscriptEvidence, TranscriptEvidenceScorer


STATES = [
    "IDLE",
    "DIALING",
    "RINGING",
    "ANSWER_DETECTED",
    "EARLY_ANALYSIS",
    "HUMAN_CANDIDATE",
    "VOICEMAIL_CANDIDATE",
    "IVR_CANDIDATE",
    "HUMAN",
    "VOICEMAIL",
    "IVR",
    "BUSY",
    "NO_ANSWER",
    "FAILED",
    "ENDED",
]

FINAL_STATES = {"HUMAN", "VOICEMAIL", "IVR", "BUSY", "NO_ANSWER", "ENDED"}
PRE_FINAL_STATES = [state for state in STATES if state not in FINAL_STATES]


@dataclass
class CallStateMachineConfig:
    max_ring_seconds: float = 55.0
    human_candidate_threshold: float = 0.30
    voicemail_candidate_threshold: float = 0.30
    ivr_candidate_threshold: float = 0.30
    human_confirm_threshold: float = 0.35
    voicemail_confirm_threshold: float = 0.30
    ivr_confirm_threshold: float = 0.30
    busy_threshold: float = 0.80


class CallStateMachine:
    """Owns call state transitions; evidence modules only update scores."""

    states = STATES

    def __init__(self, config: CallStateMachineConfig | None = None, *, log_path: str | None = None):
        self.config = config or CallStateMachineConfig()
        self.dom_scorer = DomEvidenceScorer()
        self.audio_scorer = AudioEvidenceScorer()
        self.transcript_scorer = TranscriptEvidenceScorer()
        self.timing_scorer = TimingEvidenceScorer(max_ring_seconds=self.config.max_ring_seconds)

        self.dom_evidence = DomEvidence()
        self.audio_evidence = AudioEvidence()
        self.transcript_evidence = TranscriptEvidence()
        self.timing_evidence = TimingEvidence()
        self.last_transcript = ""
        self.state_history: list[dict[str, Any]] = []
        self.last_transition_reason = ""
        self.timestamps: dict[str, float] = {"created_at": time.time()}
        self._answer_started_at: float | None = None
        self._call_started_monotonic: float | None = None
        self._confidence = 0.0
        self.human_score = 0.0
        self.voicemail_score = 0.0
        self.ivr_score = 0.0

        self._logger = self._build_logger(log_path)
        self.machine = Machine(
            model=self,
            states=STATES,
            initial="IDLE",
            auto_transitions=False,
            after_state_change="_record_transition",
            send_event=True,
        )
        self._add_transitions()

    def _add_transitions(self) -> None:
        self.machine.add_transition("start_call", "IDLE", "DIALING")
        self.machine.add_transition("ringing_detected", "DIALING", "RINGING")
        self.machine.add_transition("answer_detected", "RINGING", "ANSWER_DETECTED")
        self.machine.add_transition("begin_analysis", "ANSWER_DETECTED", "EARLY_ANALYSIS")
        self.machine.add_transition("human_candidate", "EARLY_ANALYSIS", "HUMAN_CANDIDATE")
        self.machine.add_transition("voicemail_candidate", "EARLY_ANALYSIS", "VOICEMAIL_CANDIDATE")
        self.machine.add_transition("ivr_candidate", "EARLY_ANALYSIS", "IVR_CANDIDATE")
        self.machine.add_transition("confirm_human", "HUMAN_CANDIDATE", "HUMAN")
        self.machine.add_transition("confirm_voicemail", "VOICEMAIL_CANDIDATE", "VOICEMAIL")
        self.machine.add_transition("confirm_ivr", "IVR_CANDIDATE", "IVR")
        self.machine.add_transition("busy_detected", "RINGING", "BUSY")
        self.machine.add_transition("ring_timeout", "RINGING", "NO_ANSWER")
        self.machine.add_transition("fail_call", PRE_FINAL_STATES, "FAILED")
        self.machine.add_transition("operator_hangup", PRE_FINAL_STATES, "ENDED")

    def reset(self) -> None:
        self.__init__(self.config)

    def update_dom(self, payload: dict[str, Any] | None) -> None:
        self.dom_evidence = self.dom_scorer.score(payload)
        self._recalculate_scores()
        if self.state == "IDLE":
            self._trigger("start_call", "call lifecycle started")
        if self.dom_evidence.failed:
            self._trigger("fail_call", "DOM failure evidence")
            return
        if self.dom_evidence.ended:
            self._trigger("operator_hangup", "DOM/operator hangup evidence")
            return
        if self.dom_evidence.ringing_detected and self.state == "DIALING":
            self._trigger("ringing_detected", "DOM ringing evidence")
        if self.dom_evidence.answer_detected:
            if self.state == "DIALING":
                self._trigger("ringing_detected", "answer evidence after dialing")
            self._mark_answer_detected("DOM answer evidence")
        self._evaluate_candidates()

    def update_audio(self, features: Any | None) -> None:
        self.audio_evidence = self.audio_scorer.score(features)
        self._recalculate_scores()
        if self.state == "RINGING" and self.audio_evidence.busy_score >= self.config.busy_threshold:
            self._trigger("busy_detected", "busy tone cadence detected")
            return
        if self.audio_evidence.answer_detected:
            if self.state == "DIALING":
                self._trigger("ringing_detected", "remote audio after dialing")
            self._mark_answer_detected("remote audio energy")
        self._evaluate_candidates()

    def update_transcript(self, transcript: str | None) -> None:
        if transcript is not None:
            self.last_transcript = transcript
        self.transcript_evidence = self.transcript_scorer.score(transcript)
        self._recalculate_scores()
        self._evaluate_candidates()

    def update_timing(self, *, elapsed_seconds: float | None = None, answer_elapsed_seconds: float | None = None) -> None:
        if elapsed_seconds is None:
            if self._call_started_monotonic is None:
                elapsed_seconds = 0.0
            else:
                elapsed_seconds = time.monotonic() - self._call_started_monotonic
        if answer_elapsed_seconds is None:
            answer_elapsed_seconds = self._answer_elapsed_seconds()
        self.timing_evidence = self.timing_scorer.score(
            elapsed_seconds=float(elapsed_seconds),
            answer_elapsed_seconds=float(answer_elapsed_seconds),
            in_ringing_state=self.state == "RINGING",
        )
        self._recalculate_scores()
        if self.state == "RINGING" and self.timing_evidence.ring_timeout:
            self._trigger("ring_timeout", "ring timeout")
            return
        self._evaluate_candidates()

    def get_current_state(self) -> str:
        return str(self.state)

    def get_confidence(self) -> float:
        return float(self._confidence)

    def get_debug_snapshot(self) -> dict[str, Any]:
        return {
            "current_state": self.get_current_state(),
            "confidence": self.get_confidence(),
            "human_score": self.human_score,
            "voicemail_score": self.voicemail_score,
            "ivr_score": self.ivr_score,
            "last_transcript": self.last_transcript,
            "dom_evidence": self.dom_evidence.__dict__,
            "audio_evidence": self.audio_evidence.__dict__,
            "timing_evidence": self.timing_evidence.__dict__,
            "state_history": list(self.state_history),
            "last_transition_reason": self.last_transition_reason,
            "timestamps": dict(self.timestamps),
        }

    def _mark_answer_detected(self, reason: str) -> None:
        if self._answer_started_at is None:
            self._answer_started_at = time.monotonic()
            self.timestamps["answer_detected_at"] = time.time()
        if self.state == "RINGING":
            self._trigger("answer_detected", reason)
        if self.state == "ANSWER_DETECTED":
            self._trigger("begin_analysis", "begin early evidence analysis")

    def _evaluate_candidates(self) -> None:
        if self.state in FINAL_STATES or self.state in {"IDLE", "DIALING", "RINGING", "ANSWER_DETECTED"}:
            return
        if self.state == "EARLY_ANALYSIS":
            scores = {
                "human": self.human_score,
                "voicemail": self.voicemail_score,
                "ivr": self.ivr_score,
            }
            label, score = max(scores.items(), key=lambda item: item[1])
            if label == "human" and score >= self.config.human_candidate_threshold:
                self._trigger("human_candidate", "human evidence candidate")
                return
            if label == "voicemail" and score >= self.config.voicemail_candidate_threshold:
                self._trigger("voicemail_candidate", "voicemail evidence candidate")
                return
            if label == "ivr" and score >= self.config.ivr_candidate_threshold:
                self._trigger("ivr_candidate", "IVR evidence candidate")
                return
        if self.state == "HUMAN_CANDIDATE" and self.human_score >= self.config.human_confirm_threshold:
            self._trigger("confirm_human", "human confidence threshold exceeded")
        elif (
            self.state == "VOICEMAIL_CANDIDATE"
            and self.voicemail_score >= self.config.voicemail_confirm_threshold
            and self.human_score < self.config.human_confirm_threshold
        ):
            self._trigger("confirm_voicemail", "voicemail confidence threshold exceeded")
        elif self.state == "IVR_CANDIDATE" and self.ivr_score >= self.config.ivr_confirm_threshold:
            self._trigger("confirm_ivr", "IVR confidence threshold exceeded")

    def _recalculate_scores(self) -> None:
        self.human_score = self._weighted(
            self.dom_evidence.human_score,
            self.audio_evidence.human_score,
            self.transcript_evidence.human_score,
            self.timing_evidence.human_score,
        )
        self.voicemail_score = self._weighted(
            self.dom_evidence.voicemail_score,
            self.audio_evidence.voicemail_score,
            self.transcript_evidence.voicemail_score,
            self.timing_evidence.voicemail_score,
        )
        self.ivr_score = self._weighted(
            self.dom_evidence.ivr_score,
            self.audio_evidence.ivr_score,
            self.transcript_evidence.ivr_score,
            self.timing_evidence.ivr_score,
        )
        self._confidence = max(
            self.human_score,
            self.voicemail_score,
            self.ivr_score,
            self.audio_evidence.busy_score,
        )

    @staticmethod
    def _weighted(dom: float, audio: float, transcript: float, timing: float) -> float:
        return round(max(0.0, min(1.0, dom * 0.40 + audio * 0.20 + transcript * 0.30 + timing * 0.10)), 4)

    def _trigger(self, trigger_name: str, reason: str) -> bool:
        if self.state in FINAL_STATES:
            return False
        self.last_transition_reason = reason
        try:
            return bool(getattr(self, trigger_name)())
        except Exception:
            return False

    def _record_transition(self, event: Any) -> None:
        previous = event.transition.source
        new = event.transition.dest
        now = time.time()
        entry = {
            "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "previous_state": previous,
            "new_state": new,
            "reason": self.last_transition_reason,
            "confidence": self.get_confidence(),
            "dom_evidence": self.dom_evidence.__dict__,
            "audio_evidence": self.audio_evidence.__dict__,
            "transcript": self.last_transcript,
            "final_decision": new if new in FINAL_STATES else "",
        }
        self.timestamps[f"{new.lower()}_at"] = now
        self.state_history.append(entry)
        self._logger.info("%s", entry)

    def _answer_elapsed_seconds(self) -> float:
        if self._answer_started_at is None:
            return 0.0
        return max(0.0, time.monotonic() - self._answer_started_at)

    @staticmethod
    def _build_logger(log_path: str | None) -> logging.Logger:
        path = log_path or os.path.join("logs", "call_state_machine.log")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        logger = logging.getLogger(f"call_state_machine.{id(path)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.FileHandler(path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        return logger
