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


class DecisionState(str, Enum):
    IDLE = "IDLE"
    DIALING = "DIALING"
    RINGING = "RINGING"
    ANSWERED_PENDING = "ANSWERED_PENDING"
    HUMAN = "HUMAN"
    VOICEMAIL = "VOICEMAIL"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    ENDED_MANUALLY = "ENDED_MANUALLY"
    ENDED = "ENDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


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
        return Evidence(
            state=str(dom.get("state") or "IDLE"),
            callText=str(dom.get("callText") or ""),
            hasRingingText=bool(dom.get("hasRingingText")),
            hasRingingNode=bool(dom.get("hasRingingNode")),
            hasTimer=bool(dom.get("hasTimer")),
            hasEnabledAnswerControl=bool(dom.get("hasEnabledAnswerControl")),
            hasVoicemailCue=bool(dom.get("hasVoicemailCue")),
            timerText=str(dom.get("timerText") or ""),
            voicemail_match=dom.get("voicemailMatch") or dom.get("voicemailMatch"),
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

        # Answer timeline bookkeeping (relative to decide() elapsed_seconds)
        self._answer_detected_elapsed_seconds: Optional[float] = None

        # Voicemail stability gating
        self._voicemail_stable_cycles: int = 0
        self._human_detector = HumanDetector()
        self._voicemail_detector = VoicemailDetector()

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
        if vad_confidence >= 0.45:
            score += 0.15
        return min(1.0, score)

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

        self._answer_detected_elapsed_seconds = None
        self._voicemail_stable_cycles = 0


    def decide(
        self,
        *,
        dom_evidence: Dict[str, Any] | None,
        audio_features: AudioFeatures | Any | None,
        elapsed_seconds: float,
    ) -> CallDecision:
        """Make a decision.

        elapsed_seconds:
          - time since dial click for that slot.
          - Use 0 for unknown.
        """

        if self._final_emitted is not None:
            # Once final outcome is emitted, keep stable.
            return CallDecision(
                state=self._final_emitted,
                confidence=1.0,
                reason="final outcome already emitted",
                debug={"final": self._final_emitted.value},
            )

        evidence = Evidence.from_dom(dom_evidence)
        af = audio_features or AudioFeatures()

        # Track when we first see answer evidence.
        # Critical: do NOT start the answer clock purely from audio "speech-like".
        # In real campaigns, some audio can appear briefly before GV updates the DOM
        # (or when UI/slots are transitioning), which causes early VOICEMAIL gating.
        timer_evidence0 = bool(getattr(evidence, "hasTimer", False))
        ctrl_evidence0 = bool(getattr(evidence, "hasEnabledAnswerControl", False))
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

        dom_state = evidence.state.upper()

        # 1) FAILED is reserved for technical errors; dom_state should reflect errors.
        if dom_state in ("FAILED", "ERROR", "BROWSER_CRASH"):
            self._emit(DecisionState.FAILED, 0.95, "dom indicates failure", dom_state=dom_state)
            return self._build(DecisionState.FAILED, 0.95, "dom indicates failure", dom_state=dom_state)

        if dom_state in ("ENDED_MANUALLY", "MANUAL_ENDED"):
            self._emit(DecisionState.ENDED_MANUALLY, 0.95, "manual hangup/end requested", dom_state=dom_state)
            return self._build(DecisionState.ENDED_MANUALLY, 0.95, "manual hangup/end requested", dom_state=dom_state)

        # 2) ENDED when DOM says ended.
        if dom_state == "ENDED":
            self._emit(DecisionState.ENDED, 0.9, "dom indicates ended")
            return self._build(DecisionState.ENDED, 0.9, "dom indicates ended")

        if self._current_state == DecisionState.HUMAN:
            return self._build(DecisionState.HUMAN, 0.95, "human pickup already detected")

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

        # While ringing, never consider voicemail.
        if ringing_conf >= self.config.ringing_confidence_threshold or dom_ringing:
            # Determine if max ring exceeded.
            if elapsed_seconds >= self.config.max_ring_seconds:
                self._emit(DecisionState.NO_ANSWER, 0.7, "max ring timeout reached")
                return self._build(DecisionState.NO_ANSWER, 0.7, "max ring timeout reached")

            return self._transition(DecisionState.RINGING, min(0.95, max(ringing_conf, 0.55)), "ring evidence")

        # If not confidently ringing, we expect answer/voicemail checks.

        # Answered pending evidence:
        timer_evidence = bool(evidence.hasTimer)
        ctrl_evidence = bool(evidence.hasEnabledAnswerControl)
        audio_answer_like = (
            self.config.enable_audio_detection and has_speech_like and not is_silent
        )

        answered_pending_conf = 0.0
        if timer_evidence:
            answered_pending_conf += 0.45
        if ctrl_evidence:
            answered_pending_conf += 0.25
        if audio_answer_like:
            answered_pending_conf += 0.3

        # Audio features that may be populated by analyzer / tests (duck-typed).
        speech_duration_seconds = float(_get("speech_duration_seconds", 0.0) or 0.0)
        silence_duration_seconds = float(_get("silence_duration_seconds", 0.0) or 0.0)
        voicemail_keywords_detected_count = int(_get("voicemail_keywords_detected_count", 0) or 0)
        dom_voicemail_keywords = self._voicemail_detector.keyword_count(evidence.callText)
        if dom_voicemail_keywords:
            voicemail_keywords_detected_count = max(
                voicemail_keywords_detected_count,
                dom_voicemail_keywords,
            )
        human_greeting_detected = bool(_get("human_greeting_detected", False) or False)
        short_speech_burst_detected = bool(_get("short_speech_burst_detected", False) or False)
        continuous_greeting_duration_seconds = float(_get("continuous_greeting_duration_seconds", 0.0) or 0.0)
        beep_detected = bool(_get("beep_detected", False) or False)
        background_noise_level = float(_get("background_noise_level", rms) or 0.0)
        transcript = str(_get("transcript", "") or "")

        # Start pending window if evidence suggests answer has happened.
        if answered_pending_conf >= 0.4:
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
                    and audio_gate_ok
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
            if self._passes_human_audio_gate(
                has_speech_like=has_speech_like,
                speech_duration_seconds=speech_duration_seconds,
                human_greeting_detected=human_greeting_detected,
                short_speech_burst_detected=short_speech_burst_detected,
                vad_confidence=vad_confidence,
                transcript=transcript,
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

        no_machine_signal = (
            not f_continuous
            and not f_keywords
            and not f_beep
            and not f_repeated_pattern
            and not f_dom_voicemail
        )

        # After analysis window: stay pending if no audio human pattern (no DOM-only fallback).
        if (
            answer_elapsed_seconds >= self.config.answered_pending_seconds
            and audio_gate_ok
            and no_machine_signal
        ):
            reason = "analysis window complete with audio human pattern and no machine signals"
            decision_debug["debug_reason"] = reason
            self._emit(DecisionState.HUMAN, max(0.85, human_conf, human_audio_score), reason, **decision_debug)
            return self._build(
                DecisionState.HUMAN,
                max(0.85, human_conf, human_audio_score),
                reason,
                **decision_debug,
                human_conf=human_conf,
                human_audio_score=human_audio_score,
            )

        # Human wins only when audio gate passes.
        if audio_gate_ok and human_conf >= self.config.human_confidence_threshold:
            reason = "human confidence threshold met (human-first)"
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

        # Debounce: only hold if we already have a meaningful previous state.
        if self._stable_raw_count < self.config.decision_stability_window and state != self._current_state:
            if self._current_state != DecisionState.IDLE:
                return self._build(self._current_state, 0.3, reason=reason, debug={"debounce": True, **debug})

        self._current_state = state
        self._history.append((0.0, state, confidence, reason))
        return self._build(state, confidence, reason, **debug)

    def _emit(self, final_state: DecisionState, confidence: float, reason: str, **debug: Any) -> None:
        if final_state != DecisionState.HUMAN:
            self._final_emitted = final_state
        self._current_state = final_state
        self._history.append((0.0, final_state, confidence, reason))

    def _build(self, state: DecisionState, confidence: float, reason: str, **debug: Any) -> CallDecision:
        self._last_decision_time = 0.0
        return CallDecision(state=state, confidence=float(confidence), reason=reason, debug=debug)

