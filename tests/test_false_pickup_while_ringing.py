"""Regression: false pickup while still ringing (mute-only GV controls + ringback)."""
from src.call_decision_engine import CallDecisionEngine
from src.call_state_engine import CallStateEngine
from src.local_call_detector import DetectionConfig, LocalCallDetector


class DummyAudio:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_answer_control_js_requires_hold_not_mute():
    from src.gv_controller import _JS_DETECT_STATE

    assert 'button[aria-label*="Mute call" i]' not in _JS_DETECT_STATE
    assert 'button[aria-label*="Hold call" i]' in _JS_DETECT_STATE


def test_call_state_engine_connected_ctrl_without_enabled_control_stays_ringing():
    engine = CallStateEngine()
    decision = engine.classify(
        {
            "state": "CONNECTED_CTRL",
            "callText": "phone_forwarded transfer pause hold dialpad keypad mic_off mute call_end",
            "hasEnabledAnswerControl": False,
            "hasTimer": False,
            "hasRingingText": False,
            "hasRingingNode": False,
        }
    )
    assert decision.state == "RINGING"


def test_ringback_and_speech_during_ringing_not_answered_pending():
    det = LocalCallDetector(DetectionConfig(decision_stability_window=1))
    dom = {
        "state": "CONNECTED_CTRL",
        "hasEnabledAnswerControl": False,
        "hasTimer": False,
        "hasRingingText": False,
        "hasRingingNode": False,
        "hasVoicemailCue": False,
    }
    audio = DummyAudio(
        rms=0.09,
        is_silent=False,
        has_speech_like=True,
        ringback_cadence_confidence=0.35,
        speech_duration_seconds=0.7,
        vad_confidence=0.5,
    )
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=17.0)
    assert decision.state.value == "RINGING"


def test_engine_ringback_speech_while_ringing_stays_ringing():
    engine = CallDecisionEngine(detector_config=DetectionConfig(decision_stability_window=1))
    engine.start_call()
    engine.update(
        dom_evidence={"state": "RINGING", "hasRingingText": True},
        audio_features=DummyAudio(is_silent=True),
        elapsed_seconds=8.0,
    )
    dom = {
        "state": "CONNECTED_CTRL",
        "hasEnabledAnswerControl": False,
        "hasTimer": False,
        "hasRingingText": False,
        "hasRingingNode": False,
    }
    audio = DummyAudio(
        has_speech_like=True,
        is_silent=False,
        ringback_cadence_confidence=0.35,
        speech_duration_seconds=0.7,
        vad_confidence=0.5,
    )
    decision = engine.update(dom_evidence=dom, audio_features=audio, elapsed_seconds=17.0)
    assert decision.state == "RINGING"
