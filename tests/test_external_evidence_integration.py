import pytest

from src.local_call_detector import LocalCallDetector, DetectionConfig, DecisionState
from src.detection.external_evidence import (
    ExternalEvidence,
    ExternalLabel,
    ProviderHealth,
    ProviderName,
)
from src.detection.external_evidence_mapper import ExternalEvidenceMapper


class DummyAudio:
    def __init__(
        self,
        rms=0.1,
        is_silent=False,
        has_speech_like=False,
        ringback_cadence_confidence=0.0,
        beep_hz_confidence=0.0,
        speech_duration_seconds=0.0,
        silence_duration_seconds=0.0,
        voicemail_keywords_detected_count=0,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        continuous_greeting_duration_seconds=0.0,
        beep_detected=False,
        busy_tone_cadence_confidence=0.0,
        vad_confidence=0.0,
        transcript="",
    ):
        self.rms = rms
        self.is_silent = is_silent
        self.has_speech_like = has_speech_like
        self.ringback_cadence_confidence = ringback_cadence_confidence
        self.beep_hz_confidence = beep_hz_confidence
        self.speech_duration_seconds = speech_duration_seconds
        self.silence_duration_seconds = silence_duration_seconds
        self.voicemail_keywords_detected_count = voicemail_keywords_detected_count
        self.human_greeting_detected = human_greeting_detected
        self.short_speech_burst_detected = short_speech_burst_detected
        self.continuous_greeting_duration_seconds = continuous_greeting_duration_seconds
        self.beep_detected = beep_detected
        self.busy_tone_cadence_confidence = busy_tone_cadence_confidence
        self.vad_confidence = vad_confidence
        self.transcript = transcript


def _make_external(raw_label: str, provider=ProviderName.PROTOTYPE_A, confidence=0.8, transcript="") -> ExternalEvidence:
    return ExternalEvidenceMapper.map_prototype_a(
        raw_label=raw_label,
        confidence=confidence,
        transcript=transcript,
        provider_health="connected",
    )


def test_extension_voicemail_during_ringing_must_not_emit_voicemail():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "RINGING",
        "hasRingingText": True,
        "hasRingingNode": True,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(ringback_cadence_confidence=0.9, is_silent=False)
    ext = _make_external("voicemail_detected", transcript="please leave a message")
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=30, external_evidence=ext)
    assert decision.state != DecisionState.VOICEMAIL.value


def test_extension_human_before_dom_answer_must_not_start_answer_clock():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10, voicemail_confirmation_count=1)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "CONNECTED",
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(rms=0.1, is_silent=False, has_speech_like=False)
    ext = _make_external("human_picked", transcript="hello")
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=9, external_evidence=ext)
    assert decision.state in {
        DecisionState.ANSWERED_PENDING.value,
        DecisionState.RINGING.value,
        DecisionState.UNKNOWN.value,
    }


def test_repeated_voicemail_detected_after_answer_evidence_requires_safe_window_and_confirmation():
    cfg = DetectionConfig(
        max_ring_seconds=55,
        answered_pending_seconds=10,
        answered_pending_safe_min_seconds=5,
        voicemail_confirmation_count=3,
        voicemail_stability_cycles_required=2,
        voicemail_emit_confidence_threshold=0.85,
    )
    det = LocalCallDetector(cfg)
    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(rms=0.05, is_silent=True, has_speech_like=False)
    ext = _make_external("voicemail_detected", transcript="please leave a message after the tone")
    for i in range(5):
        decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=3.0 + i * 0.5, external_evidence=ext)
        assert decision.state != DecisionState.VOICEMAIL.value
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=10.0, external_evidence=ext)
    assert decision.state != DecisionState.VOICEMAIL.value


def test_provider_timeout_disconnect_continues_safely():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "RINGING",
        "hasRingingText": True,
        "hasRingingNode": True,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(ringback_cadence_confidence=0.9, is_silent=False)
    ext = ExternalEvidence(
        provider=ProviderName.PROTOTYPE_A,
        raw_label=ExternalLabel.UNKNOWN.value,
        confidence=0.0,
        provider_health=ProviderHealth.TIMEOUT,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=5, external_evidence=ext)
    assert decision.state == DecisionState.RINGING.value


def test_final_state_emitted_only_once():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=8)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(rms=0.2, is_silent=False, has_speech_like=True, vad_confidence=0.8,
                       human_greeting_detected=True, short_speech_burst_detected=True)
    ext = _make_external("human_picked", transcript="hello")
    d1 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=10, external_evidence=ext)
    d2 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=11, external_evidence=ext)
    d3 = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=12, external_evidence=ext)
    assert d1.state == DecisionState.HUMAN.value
    assert d2.state == DecisionState.HUMAN.value
    assert d3.state == DecisionState.HUMAN.value


def test_extension_says_human_but_no_dom_answer_evidence_stays_pending():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "CONNECTED",
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(rms=0.05, is_silent=True, has_speech_like=False)
    ext = _make_external("human_picked", transcript="hello")
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=10, external_evidence=ext)
    assert decision.state != DecisionState.HUMAN.value


def test_extension_says_busy_but_requires_dom_audio_confirmation():
    cfg = DetectionConfig(max_ring_seconds=55)
    det = LocalCallDetector(cfg)
    dom = {
        "state": "RINGING",
        "hasRingingText": True,
        "hasRingingNode": True,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(ringback_cadence_confidence=0.9, is_silent=False)
    ext = _make_external("busy", confidence=0.8)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=10, external_evidence=ext)
    assert decision.state != DecisionState.BUSY.value
