"""Local real-time call-state detector.

This module is a pure local decision system that fuses:
- DOM evidence (structured dict from gv_controller JS polling)
- audio features (from audio_analyzer)
- elapsed call time

It outputs:
- decision state
- confidence
- reason

Design goals:
- Avoid rapid state flipping (debounce + confirmation)
- Use strong evidence when available (e.g., DOM timer) but not exclusively
- Never mark VOICEMAIL while still ringing
- Only produce final outcome once per call lifecycle

No network calls, no paid APIs, no cloud dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .human_detector import HumanDetector
from .voicemail_detector import VoicemailDetector

try:
    from .external_evidence import ExternalEvidence
except Exception:
    ExternalEvidence = None  # type: ignore[misc,assignment]


class DecisionState(str, Enum):
    IDLE = "IDLE"
    DIALING = "DIALING"
    RINGING = "RINGING"
    ANSWERED_PENDING = "ANSWERED_PENDING"
    CONNECTED_AUDIO_EVIDENCE = "CONNECTED_AUDIO_EVIDENCE"
    HUMAN = "HUMAN"
    VOICEMAIL = "VOICEMAIL"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    ENDED_MANUALLY = "ENDED_MANUALLY"
    ENDED = "ENDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


STATE_PRIORITY: Dict[DecisionState, int] = {
    DecisionState.HUMAN: 100,
    DecisionState.CONNECTED_AUDIO_EVIDENCE: 90,
    DecisionState.VOICEMAIL: 80,
    DecisionState.RINGING: 70,
    DecisionState.DIALING: 60,
    DecisionState.UNKNOWN: 50,
    DecisionState.FAILED: 10,
}


_DEBOUNCE_BYPASS = frozenset({
    DecisionState.HUMAN,
    DecisionState.ANSWERED_PENDING,
    DecisionState.CONNECTED_AUDIO_EVIDENCE,
    DecisionState.FAILED,
    DecisionState.ENDED,
    DecisionState.ENDED_MANUALLY,
    DecisionState.BUSY,
    DecisionState.NO_ANSWER,
})


@dataclass
class DetectionConfig:
    # Time windows (seconds)
    max_ring_seconds: float = 55.0

    # Analyze after answer before finalizing.
    answered_pending_seconds: float = 10.0

    # New: safe window after answer evidence appears.
    # Never classify VOICEMAIL (or force hangup) in this window.
    answered_pending_safe_min_seconds: float = 5.0

    # New: human-first window after answer.
    human_first_seconds: float = 5.0

    # Beep tone triggers immediate VM after this many seconds post-answer.
    beep_immediate_vm_seconds: float = 0.3

    # Human/voicemail heuristic thresholds.
    human_short_speech_max_duration_seconds: float = 2.5

    voicemail_min_answer_elapsed_seconds: float = 7.0

    # Confirmation counts
    voicemail_confirmation_count: int = 3

    # Confidence thresholds
    ringing_confidence_threshold: float = 0.65
    human_confidence_threshold: float = 0.70

    # New: voicemail is only emitted when very confident.
    voicemail_confidence_threshold: float = 0.75
    voicemail_emit_confidence_threshold: float = 0.85

    # Final gating before emitting VOICEMAIL.
    voicemail_stability_cycles_required: int = 2

    # Features toggles
    enable_audio_detection: bool = True
    enable_beep_detection: bool = True

    # Vicidial-style gate: never promote HUMAN from DOM timer/controls alone.
    require_audio_for_human: bool = True
    min_human_audio_score: float = 0.30

    # Debounce
    min_state_hold_seconds: float = 2.0
    decision_stability_window: int = 3  # require same raw decision N polls



@dataclass
class CallDecision:
    state: DecisionState
    confidence: float
    reason: str
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HybridDetectionResult:
    """Public detector facade result for audio + DOM + previous-state fusion."""

    state: DecisionState
    confidence: float
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass
class Evidence:
    """Structure expected from gv_controller JS."""

    state: str = "IDLE"  # raw DOM state from JS engine
    callText: str = ""
    hasRingingText: bool = False
    hasRingingNode: bool = False
    hasTimer: bool = False
    hasEnabledAnswerControl: bool = False
    hasVoicemailCue: bool = False
    timerText: str = ""

    voicemail_match: Optional[str] = None

    # Optional fields
    hasEnabledHoldButton: bool = False
    hasEnabledMuteButton: bool = False

    @staticmethod
    def from_dom(dom: Dict[str, Any] | None) -> "Evidence":
        dom = dom or {}
        def pick(*keys: str, default: Any = None) -> Any:
            for key in keys:
                if key in dom:
                    return dom.get(key)
            return default

        return Evidence(
            state=str(pick("state", default="IDLE") or "IDLE"),
            callText=str(pick("callText", "call_text", default="") or ""),
            hasRingingText=bool(pick("hasRingingText", "has_ringing_text", default=False)),
            hasRingingNode=bool(pick("hasRingingNode", "has_ringing_node", default=False)),
            hasTimer=bool(pick("hasTimer", "has_timer", default=False)),
            hasEnabledAnswerControl=bool(
                pick("hasEnabledAnswerControl", "has_enabled_answer_control", default=False)
            ),
            hasVoicemailCue=bool(pick("hasVoicemailCue", "has_voicemail_cue", default=False)),
            timerText=str(pick("timerText", "timer_text", default="") or ""),
            voicemail_match=pick("voicemailMatch", "voicemail_match", default=None),
        )


@dataclass
class AudioFeatures:
    """Subset required by LocalCallDetector.

    This is intentionally duplicated from audio_analyzer for typing independence.
    In practice, audio_analyzer.AudioFeatures will be duck-typed.
    """

    rms: float = 0.0
    is_silent: bool = True
    has_speech_like: bool = False
    ringback_cadence_confidence: float = 0.0
    beep_hz_confidence: float = 0.0


class LocalCallDetector:
    """Fusion detector + finite state machine."""

    def __init__(self, config: DetectionConfig | None = None):
        self.config = config or DetectionConfig()
        self._history: List[Tuple[float, DecisionState, float, str]] = []
        self._current_state: DecisionState = DecisionState.IDLE
        self._last_raw_state: DecisionState = DecisionState.UNKNOWN
        self._state_entered_at: Optional[float] = None
        self._last_decision_time: Optional[float] = None
        self._stable_raw_count: int = 0
        self._voicemail_confirm_count: int = 0
        self._final_emitted: Optional[DecisionState] = None
        self._human_locked: bool = False

        # Answer timeline bookkeeping (relative to decide() elapsed_seconds)
        self._answer_detected_elapsed_seconds: Optional[float] = None

        # Voicemail stability gating
        self._voicemail_stable_cycles: int = 0
        self._human_detector = HumanDetector()
        self._voicemail_detector = VoicemailDetector()
        self._connected_audio_locked: bool = False

    def _human_audio_score(
        self,
        *,
        has_speech_like: bool,
        speech_duration_seconds: float,
        human_greeting_detected: bool,
        short_speech_burst_detected: bool,
        vad_confidence: float,
        transcript: str,
    ) -> float:
        score = 0.0
        if human_greeting_detected or self._human_detector.has_human_keyword(transcript):
            score += 0.45
        if short_speech_burst_detected:
            score += 0.35
        if has_speech_like and 0.15 <= speech_duration_seconds <= self.config.human_short_speech_max_duration_seconds:
            score += 0.25
        if vad_confidence >= 0.70:
            score += 0.35
        elif vad_confidence >= 0.45:
            score += 0.15
        return min(1.0, score)

    def _has_human_speech_evidence(
        self,
        *,
        human_greeting_detected: bool,
        short_speech_burst_detected: bool,
        transcript: str,
    ) -> bool:
        return bool(
            human_greeting_detected
            or short_speech_burst_detected
            or self._human_detector.has_human_keyword(transcript)
        )

    def _passes_human_audio_gate(
        self,
        *,
        has_speech_like: bool,
        speech_duration_seconds: float,
        human_greeting_detected: bool,
        short_speech_burst_detected: bool,
        vad_confidence: float,
        transcript: str,
    ) -> bool:
        if not self.config.require_audio_for_human:
            return True
        if not self.config.enable_audio_detection:
            return False
        return (
            self._human_audio_score(
                has_speech_like=has_speech_like,
                speech_duration_seconds=speech_duration_seconds,
                human_greeting_detected=human_greeting_detected,
                short_speech_burst_detected=short_speech_burst_detected,
                vad_confidence=vad_confidence,
                transcript=transcript,
            )
            >= self.config.min_human_audio_score
        )

    def reset_for_new_call(self) -> None:
        self._history.clear()
        self._current_state = DecisionState.IDLE
        self._last_raw_state = DecisionState.UNKNOWN
        self._state_entered_at = None
        self._last_decision_time = None
        self._stable_raw_count = 0
        self._voicemail_confirm_count = 0
        self._final_emitted = None
        self._human_locked = False
        self._connected_audio_locked = False

        self._answer_detected_elapsed_seconds = None
        self._voicemail_stable_cycles = 0

    def detect(
        self,
        audio_chunk: AudioFeatures | Any | Dict[str, Any] | None,
        dom_state: Dict[str, Any] | None,
        previous_state: DecisionState | str | Dict[str, Any] | None,
    ) -> HybridDetectionResult:
        """Fuse one audio/DOM tick into a priority-ranked detection result.

        ``audio_chunk`` is intentionally duck-typed: callers may pass the
        existing AudioFeatures object, a dict of audio feature fields, or None.
        ``previous_state`` may be a state string or a dict containing
        ``elapsed_seconds`` and ``state`` for offline tools/tests.
        """
        elapsed_seconds = 0.0
        previous_state_value = previous_state
        if isinstance(previous_state, dict):
            elapsed_seconds = float(previous_state.get("elapsed_seconds", 0.0) or 0.0)
            previous_state_value = previous_state.get("state")

        decision = self.decide(
            dom_evidence=dom_state,
            audio_features=self._coerce_audio_features(audio_chunk),
            elapsed_seconds=elapsed_seconds,
        )
        evidence = {
            **decision.debug,
            "previous_state": str(previous_state_value or ""),
            "dom_state": str((dom_state or {}).get("state") or ""),
        }
        priority = STATE_PRIORITY.get(decision.state, 0)
        return HybridDetectionResult(
            state=decision.state,
            confidence=decision.confidence,
            reason=decision.reason,
            evidence=evidence,
            priority=priority,
        )

    @staticmethod
    def _coerce_audio_features(audio_chunk: AudioFeatures | Any | Dict[str, Any] | None) -> AudioFeatures | Any:
        if audio_chunk is None:
            return AudioFeatures()
        if isinstance(audio_chunk, dict):
            features = AudioFeatures()
            for key, value in audio_chunk.items():
                setattr(features, key, value)
            return features
        return audio_chunk

    @staticmethod
    def _priority(state: DecisionState) -> int:
        return STATE_PRIORITY.get(state, 0)

    def decide(
        self,
        *,
        dom_evidence: Dict[str, Any] | None,
        audio_features: AudioFeatures | Any | None,
        elapsed_seconds: float,
        external_evidence: "ExternalEvidence | None" = None,
    ) -> CallDecision:
        """Make a decision.

        elapsed_seconds:
          - time since dial click for that slot.
          - Use 0 for unknown.

        external_evidence:
          - Optional normalized evidence from Chrome extension prototypes.
          - Evidence-only: never bypasses DOM-first answer timer,
            voicemail safe window, or human audio gate.
        """

        evidence = Evidence.from_dom(dom_evidence)
        af = audio_features or AudioFeatures()

        if ExternalEvidence is not None and external_evidence is not None:
            try:
                from .external_evidence_mapper import ExternalEvidenceMapper
                af = ExternalEvidenceMapper.merge_into_audio_features(af, external_evidence)
            except Exception:
                pass

        # Track when we first see answer evidence.
        # Critical: do NOT start the answer clock purely from audio "speech-like".
        # In real campaigns, some audio can appear briefly before GV updates the DOM
        # (or when UI/slots are transitioning), which causes early VOICEMAIL gating.
        dom_state0 = evidence.state.upper()
        timer_evidence0 = bool(getattr(evidence, "hasTimer", False)) or dom_state0 == "CONNECTED"
        ctrl_evidence0 = bool(getattr(evidence, "hasEnabledAnswerControl", False)) or dom_state0 == "CONNECTED_CTRL"
        has_speech_like0 = bool(getattr(af, "has_speech_like", False))
        is_silent0 = bool(getattr(af, "is_silent", False))

        # DOM-first answer evidence. Audio can influence HUMAN/VOICEMAIL later,
        # but must not start answer_elapsed_seconds unless DOM also indicates answer stage.
        dom_answer_evidence_now = timer_evidence0 or ctrl_evidence0
        if dom_answer_evidence_now and self._answer_detected_elapsed_seconds is None:
            self._answer_detected_elapsed_seconds = float(elapsed_seconds)


        answer_elapsed_seconds = 0.0
        if self._answer_detected_elapsed_seconds is not None:
            answer_elapsed_seconds = max(0.0, float(elapsed_seconds) - float(self._answer_detected_elapsed_seconds))


        # Pull audio feature values via attribute access.
        def _get(attr: str, default: Any = None):
            return getattr(af, attr, default)

        rms = float(_get("rms", 0.0) or 0.0)
        is_silent = bool(_get("is_silent", False))
        has_speech_like = bool(_get("has_speech_like", False))
        ring_cad = float(_get("ringback_cadence_confidence", 0.0) or 0.0)
        beep_conf = float(_get("beep_hz_confidence", 0.0) or 0.0)
        busy_conf = float(_get("busy_tone_cadence_confidence", 0.0) or 0.0)
        speech_duration_seconds = float(_get("speech_duration_seconds", 0.0) or 0.0)
        silence_duration_seconds = float(_get("silence_duration_seconds", 0.0) or 0.0)
        human_greeting_detected = bool(_get("human_greeting_detected", False) or False)
        short_speech_burst_detected = bool(_get("short_speech_burst_detected", False) or False)
        beep_detected = bool(_get("beep_detected", False) or False)
        vad_confidence = float(_get("vad_confidence", 0.0) or 0.0)
        transcript = str(_get("transcript", "") or "")
        voicemail_phrase_seen = (
            self._voicemail_detector.keyword_count(transcript) > 0
            or self._voicemail_detector.keyword_count(evidence.callText) > 0
        )

        dom_state = evidence.state.upper()

        if dom_state in ("ENDED_MANUALLY", "MANUAL_ENDED"):
            self._emit(DecisionState.ENDED_MANUALLY, 0.95, "manual hangup/end requested", dom_state=dom_state)
            return self._build(DecisionState.ENDED_MANUALLY, 0.95, "manual hangup/end requested", dom_state=dom_state)

        # 2) ENDED when DOM says ended.
        if dom_state == "ENDED":
            self._emit(DecisionState.ENDED, 0.9, "dom indicates ended")
            return self._build(DecisionState.ENDED, 0.9, "dom indicates ended")

        if self._human_locked:
            if (
                dom_state in ("IDLE", "FAILED", "ENDED")
                and not timer_evidence0
                and not ctrl_evidence0
                and not has_speech_like0
            ):
                self._human_locked = False
                self._current_state = DecisionState.IDLE
            else:
                return CallDecision(
                    state=DecisionState.HUMAN,
                    confidence=1.0,
                    reason="human pickup locked",
                    debug={"human_locked": True},
                )

        if self._final_emitted is not None:
            # Once final outcome is emitted, keep stable unless the DOM says the call ended.
            return CallDecision(
                state=self._final_emitted,
                confidence=1.0,
                reason="final outcome already emitted",
                debug={"final": self._final_emitted.value},
            )

        if self._current_state == DecisionState.HUMAN:
            return self._build(DecisionState.HUMAN, 0.95, "human pickup already detected")

        if self._connected_audio_locked:
            if (
                not voicemail_phrase_seen
                and self._passes_human_audio_gate(
                    has_speech_like=has_speech_like,
                    speech_duration_seconds=speech_duration_seconds,
                    human_greeting_detected=human_greeting_detected,
                    short_speech_burst_detected=short_speech_burst_detected,
                    vad_confidence=vad_confidence,
                    transcript=transcript,
                )
            ):
                self._emit(
                    DecisionState.HUMAN,
                    0.96,
                    "human speech confirmed after connected audio evidence",
                    connected_audio_locked=True,
                )
                return self._build(
                    DecisionState.HUMAN,
                    0.96,
                    "human speech confirmed after connected audio evidence",
                    connected_audio_locked=True,
                )
            return self._build(
                DecisionState.CONNECTED_AUDIO_EVIDENCE,
                0.95,
                "connected audio evidence locked",
                connected_audio_locked=True,
            )

        # 1) FAILED is reserved for technical errors and cannot override connected evidence.
        if dom_state in ("FAILED", "ERROR", "BROWSER_CRASH"):
            self._emit(DecisionState.FAILED, 0.95, "dom indicates failure", dom_state=dom_state)
            return self._build(DecisionState.FAILED, 0.95, "dom indicates failure", dom_state=dom_state)

        # 3) DIALING
        if elapsed_seconds <= 1.0 and dom_state in ("IDLE", "DIALING"):
            return self._transition(DecisionState.DIALING, 0.45, "initial dialing window")

        # Ringing evidence
        dom_ringing = bool(evidence.hasRingingText or evidence.hasRingingNode or dom_state == "RINGING")
        audio_ringing = (
            self.config.enable_audio_detection and ring_cad >= self.config.ringing_confidence_threshold
        )
        ringing_conf = 0.0
        if dom_ringing:
            ringing_conf += 0.5
        if self.config.enable_audio_detection and audio_ringing:
            ringing_conf += 0.5

        if self.config.enable_audio_detection and busy_conf >= 0.8 and elapsed_seconds >= 2.0:
            self._emit(DecisionState.BUSY, 0.9, "busy tone cadence detected")
            return self._build(
                DecisionState.BUSY,
                0.9,
                "busy tone cadence detected",
                busy_tone_cadence_confidence=busy_conf,
            )

        # Some Google Voice sessions keep stale "calling/ringing" text in the
        # page after pickup, especially when the active-call panel is not
        # exposed with a timer. Once this detector has already reached RINGING
        # for an active controller call, allow a short human-speech burst with
        # weak ringback/beep evidence to mark audio-based pickup. Keep it
        # pending instead of HUMAN so voicemail logic is not bypassed too early.
        post_ringing_audio_pickup = (
            self._current_state == DecisionState.RINGING
            and elapsed_seconds >= 6.0
            and self.config.enable_audio_detection
            and has_speech_like
            and not is_silent
            and ring_cad < self.config.ringing_confidence_threshold
            and busy_conf < 0.8
            and beep_conf < 0.55
            and not beep_detected
            and not voicemail_phrase_seen
            and self._passes_human_audio_gate(
                has_speech_like=has_speech_like,
                speech_duration_seconds=speech_duration_seconds,
                human_greeting_detected=human_greeting_detected,
                short_speech_burst_detected=short_speech_burst_detected,
                vad_confidence=vad_confidence,
                transcript=transcript,
            )
        )
        if post_ringing_audio_pickup:
            if self._answer_detected_elapsed_seconds is None:
                self._answer_detected_elapsed_seconds = float(elapsed_seconds)
            human_after_ringing = (
                timer_evidence0
                or ctrl_evidence0
                or human_greeting_detected
                or self._human_detector.has_human_keyword(transcript)
            )
            pickup_state = DecisionState.HUMAN if human_after_ringing else DecisionState.CONNECTED_AUDIO_EVIDENCE
            reason = (
                "human detected from post-ringing speech"
                if human_after_ringing
                else "post-ringing speech pickup detected despite stale GV ringing text"
            )
            return self._transition(
                pickup_state,
                0.94 if human_after_ringing else 0.82,
                reason,
                audio_state=self._audio_state(
                    has_speech_like=has_speech_like,
                    ring_cad=ring_cad,
                    beep_conf=beep_conf,
                    busy_conf=busy_conf,
                    is_silent=is_silent,
                ),
                speech_duration=speech_duration_seconds,
                vad_confidence=vad_confidence,
                ringback_detected=False,
                human_detected=human_after_ringing,
            )

        # While ringing, never consider voicemail.
        if ringing_conf >= self.config.ringing_confidence_threshold or dom_ringing:
            # Determine if max ring exceeded.
            if elapsed_seconds >= self.config.max_ring_seconds:
                self._emit(DecisionState.NO_ANSWER, 0.7, "max ring timeout reached")
                return self._build(DecisionState.NO_ANSWER, 0.7, "max ring timeout reached")

            return self._transition(DecisionState.RINGING, min(0.95, max(ringing_conf, 0.55)), "ring evidence")

        # If not confidently ringing, we expect answer/voicemail checks.

        # Answered pending evidence:
        timer_evidence = bool(evidence.hasTimer) or dom_state == "CONNECTED"
        ctrl_evidence = bool(evidence.hasEnabledAnswerControl) or dom_state == "CONNECTED_CTRL"
        audio_answer_like = (
            self.config.enable_audio_detection and has_speech_like and not is_silent
        )

        answered_pending_conf = 0.0
        if timer_evidence:
            answered_pending_conf += 0.5
        if ctrl_evidence:
            answered_pending_conf += 0.2 if dom_state == "CONNECTED_CTRL" else 0.15
        if audio_answer_like:
            answered_pending_conf += 0.25

        # Audio features that may be populated by analyzer / tests (duck-typed).
        voicemail_keywords_detected_count = int(_get("voicemail_keywords_detected_count", 0) or 0)
        dom_voicemail_keywords = self._voicemail_detector.keyword_count(evidence.callText)
        if dom_voicemail_keywords:
            voicemail_keywords_detected_count = max(
                voicemail_keywords_detected_count,
                dom_voicemail_keywords,
            )
        continuous_greeting_duration_seconds = float(_get("continuous_greeting_duration_seconds", 0.0) or 0.0)
        background_noise_level = float(_get("background_noise_level", rms) or 0.0)

        can_classify_answer = bool(
            timer_evidence or (ctrl_evidence and audio_answer_like)
        )

        # Start pending window if evidence suggests answer has happened.
        if can_classify_answer and answered_pending_conf >= 0.35:
            current_debug_base = {
                "current_state": self._current_state.value,
                "candidate_state": "ANSWERED_PENDING",
                "debug_confidence": max(0.45, min(0.9, answered_pending_conf)),
                "debug_reason": "answered evidence detected",
                "speech_duration": speech_duration_seconds,
                "silence_duration": silence_duration_seconds,
                "ringback_detected": dom_ringing or (ring_cad >= self.config.ringing_confidence_threshold),
                    "beep_detected": beep_detected or (beep_conf >= 0.5),
                    "audio_state": self._audio_state(
                        has_speech_like=has_speech_like,
                        ring_cad=ring_cad,
                        beep_conf=beep_conf,
                        busy_conf=busy_conf,
                        is_silent=is_silent,
                    ),
                "human_greeting_detected": human_greeting_detected,
                "voicemail_confirmation_count": self._voicemail_confirm_count,
            }

            # 1) ANSWERED_PENDING safe window: never classify VOICEMAIL during first 5 seconds after answer evidence.
            if answer_elapsed_seconds < self.config.answered_pending_safe_min_seconds:
                if (
                    self.config.enable_beep_detection
                    and (beep_detected or beep_conf >= 0.55)
                    and answer_elapsed_seconds > self.config.beep_immediate_vm_seconds
                    and not human_greeting_detected
                    and not short_speech_burst_detected
                ):
                    vm_conf = min(0.98, max(0.88, beep_conf + 0.15))
                    return self._transition(
                        DecisionState.VOICEMAIL,
                        vm_conf,
                        "beep tone detected — immediate voicemail",
                        **{**current_debug_base, "ui_state": "CLASSIFYING"},
                    )

                vad_confidence = float(_get("vad_confidence", 0.0) or 0.0)
                audio_gate_ok = self._passes_human_audio_gate(
                    has_speech_like=has_speech_like,
                    speech_duration_seconds=speech_duration_seconds,
                    human_greeting_detected=human_greeting_detected,
                    short_speech_burst_detected=short_speech_burst_detected,
                    vad_confidence=vad_confidence,
                    transcript=transcript,
                )
                if (
                    answer_elapsed_seconds <= self.config.human_first_seconds
                    and has_speech_like
                    and not is_silent
                    and audio_gate_ok
                    and self._has_human_speech_evidence(
                        human_greeting_detected=human_greeting_detected,
                        short_speech_burst_detected=short_speech_burst_detected,
                        transcript=transcript,
                    )
                ):
                    human_conf = min(0.98, max(answered_pending_conf, self.config.human_confidence_threshold) + 0.25)
                    return self._transition(
                        DecisionState.HUMAN,
                        human_conf,
                        "human-first: audio human pattern during pending safe window",
                        **current_debug_base,
                    )

                return self._transition(
                    DecisionState.ANSWERED_PENDING,
                    min(0.9, max(answered_pending_conf, 0.45)),
                    "answered pending safe window (no voicemail allowed yet)",
                    **{**current_debug_base, "ui_state": "CLASSIFYING"},
                )

            # Fast beep path after safe window starts.
            if (
                self.config.enable_beep_detection
                and (beep_detected or beep_conf >= 0.55)
                and answer_elapsed_seconds > self.config.beep_immediate_vm_seconds
                and not human_greeting_detected
                and not short_speech_burst_detected
            ):
                vm_conf = min(0.98, max(0.88, beep_conf + 0.15))
                return self._transition(
                    DecisionState.VOICEMAIL,
                    vm_conf,
                    "beep tone detected — immediate voicemail",
                    **{**current_debug_base, "ui_state": "CLASSIFYING"},
                )

            # 3) After safe window, promote HUMAN only with audio human pattern.
            vad_confidence = float(_get("vad_confidence", 0.0) or 0.0)
            if (
                has_speech_like
                and not is_silent
                and self._passes_human_audio_gate(
                    has_speech_like=has_speech_like,
                    speech_duration_seconds=speech_duration_seconds,
                    human_greeting_detected=human_greeting_detected,
                    short_speech_burst_detected=short_speech_burst_detected,
                    vad_confidence=vad_confidence,
                    transcript=transcript,
                )
                and self._has_human_speech_evidence(
                    human_greeting_detected=human_greeting_detected,
                    short_speech_burst_detected=short_speech_burst_detected,
                    transcript=transcript,
                )
            ):
                human_conf = min(0.98, max(answered_pending_conf, self.config.human_confidence_threshold) + 0.2)
                return self._transition(
                    DecisionState.HUMAN,
                    human_conf,
                    "audio human pattern confirmed after safe window",
                    **current_debug_base,
                )

            # 4) Background noise handling: keep pending and wait for confirmation.
            background_noise_high = (background_noise_level > 0.15 or rms > 0.15) and not human_greeting_detected and not has_speech_like
            if background_noise_high:
                return self._transition(
                    DecisionState.ANSWERED_PENDING,
                    0.55,
                    "background noise detected, waiting for confirmation",
                    **current_debug_base,
                )

            # Otherwise run strict human-vs-voicemail classification.
            return self._classify_human_or_voicemail(
                evidence=evidence,
                audio=(
                    rms,
                    is_silent,
                    has_speech_like,
                    ring_cad,
                    beep_conf,
                    beep_detected,
                    speech_duration_seconds,
                    silence_duration_seconds,
                    voicemail_keywords_detected_count,
                    human_greeting_detected,
                    short_speech_burst_detected,
                    continuous_greeting_duration_seconds,
                    background_noise_level,
                    transcript,
                    float(_get("vad_confidence", 0.0) or 0.0),
                ),
                answer_elapsed_seconds=answer_elapsed_seconds,
                debug_base=current_debug_base,
            )




        # DOM voicemail cue alone is not enough (and must not happen while ringing).
        # If DOM claims VOICEMAIL without ringing evidence, we still require pending window confirmation.
        if evidence.hasVoicemailCue:
            return self._transition(
                DecisionState.ANSWERED_PENDING,
                0.45,
                "voicemail cue seen but waiting for pending confirmation",
            )

        # Default fallback.
        return self._transition(DecisionState.UNKNOWN, 0.2, "insufficient evidence")

    @staticmethod
    def _audio_state(
        *,
        has_speech_like: bool,
        ring_cad: float,
        beep_conf: float,
        busy_conf: float,
        is_silent: bool,
    ) -> str:
        if busy_conf >= 0.8:
            return "BUSY"
        if ring_cad >= 0.65:
            return "RINGING"
        if beep_conf >= 0.6:
            return "BEEP"
        if has_speech_like:
            return "SPEECH"
        if is_silent:
            return "SILENCE"
        return "NOISE"

    def _classify_human_or_voicemail(
        self,
        *,
        evidence: Evidence,
        audio: Tuple[Any, ...],
        answer_elapsed_seconds: float,
        debug_base: Optional[Dict[str, Any]] = None,
    ) -> CallDecision:
        (
            rms,
            is_silent,
            has_speech_like,
            _ring_cad,
            beep_conf,
            beep_detected,
            speech_duration_seconds,
            silence_duration_seconds,
            voicemail_keywords_detected_count,
            human_greeting_detected,
            short_speech_burst_detected,
            continuous_greeting_duration_seconds,
            background_noise_level,
            transcript,
            vad_confidence,
        ) = audio

        debug_base = debug_base or {}
        human_detection = self._human_detector.classify(
            transcript=transcript,
            speech_duration_seconds=speech_duration_seconds,
            silence_duration_seconds=silence_duration_seconds,
            answer_elapsed_seconds=answer_elapsed_seconds,
            has_speech_like=has_speech_like,
            background_noise_level=background_noise_level,
            human_greeting_detected=human_greeting_detected,
            short_speech_burst_detected=short_speech_burst_detected,
        )

        human_audio_score = self._human_audio_score(
            has_speech_like=has_speech_like,
            speech_duration_seconds=speech_duration_seconds,
            human_greeting_detected=human_greeting_detected,
            short_speech_burst_detected=short_speech_burst_detected,
            vad_confidence=vad_confidence,
            transcript=transcript,
        )
        audio_gate_ok = self._passes_human_audio_gate(
            has_speech_like=has_speech_like,
            speech_duration_seconds=speech_duration_seconds,
            human_greeting_detected=human_greeting_detected,
            short_speech_burst_detected=short_speech_burst_detected,
            vad_confidence=vad_confidence,
            transcript=transcript,
        )

        human_conf = 0.0
        if human_greeting_detected:
            human_conf += 0.35
        elif short_speech_burst_detected and speech_duration_seconds > 0.0:
            human_conf += 0.25
        elif self.config.enable_audio_detection and has_speech_like:
            human_conf += 0.15
        human_conf = max(human_conf, human_detection.confidence)

        # Voicemail confirmation rule: 2-of-5 factors + strict gating.
        factors_true = 0

        # 1) continuous greeting speech longer than 4 seconds
        f_continuous = continuous_greeting_duration_seconds >= 4.0
        factors_true += int(f_continuous)

        # 2) voicemail keywords detected
        f_keywords = voicemail_keywords_detected_count >= 1
        factors_true += int(f_keywords)

        # 3) beep tone detected around 900–1100Hz
        # If only beep_hz_confidence exists, treat beep_detected as already validated by analyzer.
        f_beep = bool(beep_detected) or (self.config.enable_beep_detection and beep_conf >= 0.55)
        factors_true += int(f_beep)

        # 4) repeated machine greeting pattern
        # We don't have a dedicated pattern detector in this module; approximate with DOM voicemail cue.
        f_repeated_pattern = bool(evidence.hasVoicemailCue)
        factors_true += int(f_repeated_pattern)

        # 5) DOM clearly shows voicemail
        f_dom_voicemail = bool(evidence.hasVoicemailCue) or bool(evidence.voicemail_match)
        factors_true += int(f_dom_voicemail)
        vm_detection = self._voicemail_detector.classify(
            transcript=transcript,
            answer_elapsed_seconds=answer_elapsed_seconds,
            continuous_greeting_duration_seconds=continuous_greeting_duration_seconds,
            voicemail_keywords_detected_count=voicemail_keywords_detected_count,
            beep_detected=beep_detected,
            beep_confidence=beep_conf,
            dom_voicemail=f_dom_voicemail,
            repeated_machine_pattern=bool(evidence.hasVoicemailCue),
            human_detected=human_detection.detected,
        )

        # No human greeting detected gate
        no_human_greeting_detected = not human_greeting_detected

        # Compute voicemail_score (bounded to [0,1])
        factor_score = min(1.0, factors_true / 2.0 * 0.5)  # 2 factors => 0.5, 4 factors => 1.0-ish
        voicemail_score = 0.0
        voicemail_score += factor_score * 0.6
        voicemail_score += (0.4 if (f_beep and beep_conf >= 0.5) else 0.0)
        if evidence.hasVoicemailCue:
            voicemail_score = min(1.0, voicemail_score + 0.15)
        voicemail_score = max(voicemail_score, vm_detection.confidence)

        candidate_voicemail = (
            vm_detection.candidate
            and answer_elapsed_seconds >= self.config.voicemail_min_answer_elapsed_seconds
            and no_human_greeting_detected
            and factors_true >= 2
            and voicemail_score >= self.config.voicemail_confidence_threshold
        )

        if candidate_voicemail:
            self._voicemail_confirm_count += 1
            self._voicemail_stable_cycles += 1
        else:
            self._voicemail_confirm_count = max(0, self._voicemail_confirm_count - 1)
            self._voicemail_stable_cycles = 0

        # Strict emit VOICEMAIL only when all gating passes.
        can_emit_voicemail = (
            self._voicemail_confirm_count >= self.config.voicemail_confirmation_count
            and self._voicemail_stable_cycles >= self.config.voicemail_stability_cycles_required
            and voicemail_score >= self.config.voicemail_emit_confidence_threshold
            and answer_elapsed_seconds >= 7.0
        )

        decision_debug = {
            **debug_base,
            "candidate_state": "VOICEMAIL" if candidate_voicemail else "HUMAN_OR_PENDING",
            "debug_confidence": float(max(human_conf, voicemail_score)),
            "debug_reason": "",
            "speech_duration": speech_duration_seconds,
            "silence_duration": silence_duration_seconds,
            "beep_detected": bool(beep_detected),
            "human_greeting_detected": bool(human_greeting_detected),
            "human_audio_score": human_audio_score,
            "audio_gate_ok": audio_gate_ok,
            "human_reasons": human_detection.reasons,
            "voicemail_confirmation_count": self._voicemail_confirm_count,
            "voicemail_score": voicemail_score,
            "voicemail_factors": vm_detection.factors,
            "factors_true": factors_true,
            "factor_continuous_greeting": f_continuous,
            "factor_keywords": f_keywords,
            "factor_beep": f_beep,
            "factor_repeated_pattern": f_repeated_pattern,
            "factor_dom_voicemail": f_dom_voicemail,
        }

        if can_emit_voicemail:
            reason = "voicemail confirmed: strong 2-of-5 factors + confidence + stability"
            decision_debug["debug_reason"] = reason
            self._emit(DecisionState.VOICEMAIL, min(0.99, voicemail_score), reason, **decision_debug)
            return self._build(
                DecisionState.VOICEMAIL,
                min(0.99, voicemail_score),
                reason,
                **decision_debug,
                voicemail_conf=voicemail_score,
            )

        if (
            self.config.enable_beep_detection
            and f_beep
            and answer_elapsed_seconds >= max(1.0, self.config.beep_immediate_vm_seconds)
            and not human_greeting_detected
            and not self._human_detector.has_human_keyword(transcript)
        ):
            reason = "beep tone after answer — voicemail"
            decision_debug["debug_reason"] = reason
            self._emit(DecisionState.VOICEMAIL, min(0.95, max(0.85, voicemail_score, beep_conf)), reason, **decision_debug)
            return self._build(
                DecisionState.VOICEMAIL,
                min(0.95, max(0.85, voicemail_score, beep_conf)),
                reason,
                **decision_debug,
                voicemail_conf=voicemail_score,
            )

        if (
            continuous_greeting_duration_seconds >= 3.5
            and answer_elapsed_seconds >= 4.0
            and not self._has_human_speech_evidence(
                human_greeting_detected=human_greeting_detected,
                short_speech_burst_detected=short_speech_burst_detected,
                transcript=transcript,
            )
        ):
            reason = "long greeting without human keywords — voicemail"
            decision_debug["debug_reason"] = reason
            self._emit(DecisionState.VOICEMAIL, 0.88, reason, **decision_debug)
            return self._build(
                DecisionState.VOICEMAIL,
                0.88,
                reason,
                **decision_debug,
                voicemail_conf=0.88,
            )

        # Human wins only when audio gate passes and speech sounds like a live pickup.
        if (
            audio_gate_ok
            and human_conf >= self.config.human_confidence_threshold
            and self._has_human_speech_evidence(
                human_greeting_detected=human_greeting_detected,
                short_speech_burst_detected=short_speech_burst_detected,
                transcript=transcript,
            )
        ):
            reason = "human confidence threshold met"
            decision_debug["debug_reason"] = reason
            self._emit(DecisionState.HUMAN, min(0.98, human_conf), reason, **decision_debug)
            return self._build(
                DecisionState.HUMAN,
                min(0.98, human_conf),
                reason,
                **decision_debug,
                human_conf=human_conf,
            )

        # Otherwise keep pending.
        fallback = DecisionState.ANSWERED_PENDING
        reason = "awaiting more evidence for final classification"
        decision_debug["debug_reason"] = reason
        return self._build(
            fallback,
            max(0.3, min(0.75, max(human_conf, voicemail_score))),
            reason,
            **decision_debug,
            human_conf=human_conf,
            voicemail_conf=voicemail_score,
            voicemail_confirm_count=self._voicemail_confirm_count,
        )


    def _transition(self, state: DecisionState, confidence: float, reason: str, **debug: Any) -> CallDecision:
        now_state = state

        # raw debounce: require same raw decision N times
        raw = now_state
        if raw == self._last_raw_state:
            self._stable_raw_count += 1
        else:
            self._stable_raw_count = 1
            self._last_raw_state = raw

        if self._state_entered_at is None:
            self._state_entered_at = 0.0

        if state in _DEBOUNCE_BYPASS:
            if state == DecisionState.HUMAN:
                self._human_locked = True
            if state == DecisionState.CONNECTED_AUDIO_EVIDENCE:
                self._connected_audio_locked = True
            self._current_state = state
            self._history.append((0.0, state, confidence, reason))
            return self._build(state, confidence, reason, **debug)

        # Debounce: only hold if we already have a meaningful previous state.
        immediate_states = {
            DecisionState.ANSWERED_PENDING,
            DecisionState.CONNECTED_AUDIO_EVIDENCE,
            DecisionState.HUMAN,
        }
        if (
            self._stable_raw_count < self.config.decision_stability_window
            and state != self._current_state
            and state not in immediate_states
        ):
            if self._current_state != DecisionState.IDLE:
                return self._build(self._current_state, 0.3, reason=reason, debug={"debounce": True, **debug})

        self._current_state = state
        if state == DecisionState.CONNECTED_AUDIO_EVIDENCE:
            self._connected_audio_locked = True
        self._history.append((0.0, state, confidence, reason))
        return self._build(state, confidence, reason, **debug)

    def _emit(self, final_state: DecisionState, confidence: float, reason: str, **debug: Any) -> None:
        self._final_emitted = final_state
        if final_state == DecisionState.HUMAN:
            self._human_locked = True
        if final_state == DecisionState.CONNECTED_AUDIO_EVIDENCE:
            self._connected_audio_locked = True
        self._current_state = final_state
        self._history.append((0.0, final_state, confidence, reason))

    def _build(self, state: DecisionState, confidence: float, reason: str, **debug: Any) -> CallDecision:
        self._last_decision_time = 0.0
        return CallDecision(state=state, confidence=float(confidence), reason=reason, debug=debug)

