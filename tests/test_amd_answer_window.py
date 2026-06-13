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
        rms=0.1,
        is_silent=False,
    )
    det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=15.0)
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=15.4)
    assert decision.state == DecisionState.HUMAN
