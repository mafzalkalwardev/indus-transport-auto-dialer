import pytest

from src.local_call_detector import LocalCallDetector, DetectionConfig, DecisionState


class DummyAudio:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_no_voicemail_while_ringing():
    det = LocalCallDetector(DetectionConfig(decision_stability_window=1))
    dom = {
        "state": "RINGING",
        "hasRingingText": True,
        "hasRingingNode": True,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
    }
    audio = DummyAudio(
        beep_detected=True,
        beep_hz_confidence=0.9,
        has_speech_like=True,
        rms=0.2,
        is_silent=False,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=12.0)
    assert decision.state == DecisionState.RINGING


def test_beep_promotes_voicemail_after_answer():
    det = LocalCallDetector(
        DetectionConfig(
            decision_stability_window=1,
            voicemail_confirmation_count=1,
            voicemail_stability_cycles_required=1,
            voicemail_emit_confidence_threshold=0.5,
        )
    )
    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "hasEnabledAnswerControl": True,
        "hasRingingText": False,
        "hasRingingNode": False,
    }
    audio = DummyAudio(
        beep_detected=True,
        beep_hz_confidence=0.85,
        has_speech_like=False,
        rms=0.05,
        is_silent=False,
        speech_duration_seconds=0.0,
    )
    # Answer evidence at 20s; beep check at 20.5s => answer_elapsed ~0.5s
    det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=20.0)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=20.5)
    assert decision.state == DecisionState.VOICEMAIL


def test_short_hello_promotes_human_in_first_window():
    det = LocalCallDetector(DetectionConfig(decision_stability_window=1, human_first_seconds=5))
    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "hasEnabledAnswerControl": True,
    }
    audio = DummyAudio(
        has_speech_like=True,
        human_greeting_detected=True,
        short_speech_burst_detected=True,
        speech_duration_seconds=0.8,
        vad_confidence=0.5,
        rms=0.1,
        is_silent=False,
    )
    det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=15.0)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=15.4)
    assert decision.state == DecisionState.HUMAN


def test_connected_ctrl_alone_never_promotes_human_even_without_audio_gate():
    det = LocalCallDetector(
        DetectionConfig(
            decision_stability_window=1,
            human_first_seconds=5,
            require_audio_for_human=False,
            enable_audio_detection=False,
        )
    )
    dom = {
        "state": "CONNECTED_CTRL",
        "hasEnabledAnswerControl": True,
        "hasTimer": False,
        "hasRingingText": False,
        "hasRingingNode": False,
    }
    audio = DummyAudio(
        has_speech_like=False,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        speech_duration_seconds=0.0,
        rms=0.00002,
        is_silent=True,
        vad_confidence=0.0,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=3.7)
    assert decision.state != DecisionState.HUMAN


def test_dom_timer_alone_never_promotes_human():
    det = LocalCallDetector(
        DetectionConfig(
            decision_stability_window=1,
            answered_pending_seconds=8,
            require_audio_for_human=True,
        )
    )
    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "hasEnabledAnswerControl": True,
        "hasRingingText": False,
        "hasRingingNode": False,
    }
    audio = DummyAudio(
        has_speech_like=False,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        speech_duration_seconds=0.0,
        rms=0.01,
        is_silent=True,
        vad_confidence=0.0,
    )
    det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=20.0)
    for elapsed in (20.5, 21.0, 22.0, 25.0, 28.5):
        decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=elapsed)
    assert decision.state in {DecisionState.ANSWERED_PENDING, DecisionState.UNKNOWN}
    assert decision.state != DecisionState.HUMAN
