"""Regression: voicemail after machine greeting must not TIMEOUT in ANSWERED_PENDING."""

from src.local_call_detector import DetectionConfig, DecisionState, LocalCallDetector


class DummyAudio:
    def __init__(self, **kwargs):
        self.rms = kwargs.get("rms", 0.0)
        self.is_silent = kwargs.get("is_silent", True)
        self.has_speech_like = kwargs.get("has_speech_like", False)
        self.ringback_cadence_confidence = kwargs.get("ringback_cadence_confidence", 0.0)
        self.beep_hz_confidence = kwargs.get("beep_hz_confidence", 0.0)
        self.speech_duration_seconds = kwargs.get("speech_duration_seconds", 0.0)
        self.silence_duration_seconds = kwargs.get("silence_duration_seconds", 0.0)
        self.voicemail_keywords_detected_count = kwargs.get("voicemail_keywords_detected_count", 0)
        self.human_greeting_detected = kwargs.get("human_greeting_detected", False)
        self.short_speech_burst_detected = kwargs.get("short_speech_burst_detected", False)
        self.continuous_greeting_duration_seconds = kwargs.get(
            "continuous_greeting_duration_seconds", 0.0
        )
        self.beep_detected = kwargs.get("beep_detected", False)
        self.busy_tone_cadence_confidence = kwargs.get("busy_tone_cadence_confidence", 0.0)
        self.background_noise_level = kwargs.get("background_noise_level", self.rms)
        self.transcript = kwargs.get("transcript", "")


def _dom_connected_ctrl():
    return {
        "state": "CONNECTED_CTRL",
        "hasTimer": False,
        "hasEnabledAnswerControl": True,
        "hasVoicemailCue": False,
    }


def test_ctrl_only_answer_window_stays_classifiable_after_speech_stops():
    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10)
    det = LocalCallDetector(cfg)
    dom = _dom_connected_ctrl()

    # Brief greeting burst (like a VM robot), then silence — no live audio required to keep classifying.
    det.decide(
        dom_evidence=dom,
        audio_features=DummyAudio(
            has_speech_like=True,
            is_silent=False,
            speech_duration_seconds=0.7,
            ringback_cadence_confidence=0.35,
        ),
        elapsed_seconds=42.0,
    )
    decision = det.decide(
        dom_evidence=dom,
        audio_features=DummyAudio(
            is_silent=True,
            silence_duration_seconds=8.0,
            ringback_cadence_confidence=0.0,
        ),
        elapsed_seconds=52.0,
    )
    assert decision.state == DecisionState.VOICEMAIL.value


def test_amd_classify_timeout_without_human_becomes_voicemail():
    cfg = DetectionConfig(
        max_ring_seconds=55,
        answered_pending_seconds=10,
        answered_pending_safe_min_seconds=5.0,
    )
    det = LocalCallDetector(cfg)
    dom = _dom_connected_ctrl()

    det.decide(
        dom_evidence=dom,
        audio_features=DummyAudio(is_silent=True, silence_duration_seconds=1.0),
        elapsed_seconds=40.0,
    )
    decision = det.decide(
        dom_evidence=dom,
        audio_features=DummyAudio(is_silent=True, silence_duration_seconds=2.0),
        elapsed_seconds=51.0,
    )
    assert decision.state == DecisionState.VOICEMAIL.value
