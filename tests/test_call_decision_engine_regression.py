from src.call_decision_engine import CallDecisionEngine
from src.local_call_detector import DetectionConfig


class DummyAudio:
    def __init__(self, **kwargs):
        self.rms = kwargs.get("rms", 0.02)
        self.is_silent = kwargs.get("is_silent", False)
        self.has_speech_like = kwargs.get("has_speech_like", False)
        self.ringback_cadence_confidence = kwargs.get("ringback_cadence_confidence", 0.0)
        self.beep_hz_confidence = kwargs.get("beep_hz_confidence", 0.0)
        self.speech_duration_seconds = kwargs.get("speech_duration_seconds", 0.0)
        self.silence_duration_seconds = kwargs.get("silence_duration_seconds", 0.0)
        self.voicemail_keywords_detected_count = kwargs.get("voicemail_keywords_detected_count", 0)
        self.human_greeting_detected = kwargs.get("human_greeting_detected", False)
        self.short_speech_burst_detected = kwargs.get("short_speech_burst_detected", False)
        self.continuous_greeting_duration_seconds = kwargs.get("continuous_greeting_duration_seconds", 0.0)
        self.beep_detected = kwargs.get("beep_detected", False)
        self.busy_tone_cadence_confidence = kwargs.get("busy_tone_cadence_confidence", 0.0)
        self.background_noise_level = kwargs.get("background_noise_level", 0.0)
        self.transcript = kwargs.get("transcript", "")


def test_engine_uses_hardened_detector_not_eager_fsm_for_voicemail():
    engine = CallDecisionEngine(
        detector_config=DetectionConfig(
            voicemail_confirmation_count=3,
            voicemail_stability_cycles_required=2,
            decision_stability_window=1,
        )
    )
    engine.start_call()
    dom = {
        "state": "CONNECTED",
        "callText": "please leave a message after the tone",
        "hasTimer": True,
        "hasEnabledAnswerControl": False,
        "hasVoicemailCue": True,
        "voicemailMatch": "please leave a message",
    }
    audio = DummyAudio(
        continuous_greeting_duration_seconds=8.0,
        beep_detected=True,
        beep_hz_confidence=0.8,
    )

    first = engine.update(dom_evidence=dom, audio_features=audio, elapsed_seconds=8)
    second = engine.update(dom_evidence=dom, audio_features=audio, elapsed_seconds=15)
    third = engine.update(dom_evidence=dom, audio_features=audio, elapsed_seconds=16)
    fourth = engine.update(dom_evidence=dom, audio_features=audio, elapsed_seconds=17)

    assert first.state == "ANSWERED_PENDING"
    assert second.state == "ANSWERED_PENDING"
    assert third.state == "ANSWERED_PENDING"
    assert fourth.state == "VOICEMAIL"


def test_engine_keeps_ringing_until_ring_timeout():
    engine = CallDecisionEngine(
        detector_config=DetectionConfig(max_ring_seconds=55, decision_stability_window=1)
    )
    engine.start_call()
    dom = {
        "state": "RINGING",
        "callText": "calling please leave a message after the tone",
        "hasRingingText": True,
        "hasRingingNode": True,
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
        "hasVoicemailCue": True,
    }
    audio = DummyAudio(ringback_cadence_confidence=0.9)

    ringing = engine.update(dom_evidence=dom, audio_features=audio, elapsed_seconds=40)
    timeout = engine.update(dom_evidence=dom, audio_features=audio, elapsed_seconds=56)

    assert ringing.state == "RINGING"
    assert timeout.state == "NO_ANSWER"
