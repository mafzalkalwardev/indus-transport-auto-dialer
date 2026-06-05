import pytest

from src.local_call_detector import LocalCallDetector, DetectionConfig, DecisionState


class DummyAudio:
    def __init__(
        self,
        rms=0.1,
        is_silent=False,
        has_speech_like=False,
        ringback_cadence_confidence=0.0,
        beep_hz_confidence=0.0,
        # Optional fields used by the detector (duck-typed)
        speech_duration_seconds=0.0,
        silence_duration_seconds=0.0,
        voicemail_keywords_detected_count=0,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        continuous_greeting_duration_seconds=0.0,
        beep_detected=False,
        busy_tone_cadence_confidence=0.0,
        background_noise_level=None,
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
        self.background_noise_level = rms if background_noise_level is None else background_noise_level
        self.transcript = transcript


def test_audio_speech_like_must_not_start_answer_clock_before_dom_answer():
    """Regression guard: if audio speech-like appears before GV DOM answer controls/timer,
    LocalCallDetector must not treat elapsed time as post-answer.
    """

    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10, voicemail_confirmation_count=1)
    det = LocalCallDetector(cfg)

    # No DOM answer control/timer yet, but audio has speech-like and GV UI says voicemail cue.
    dom = {
        "state": "CONNECTED",  # GV may transiently flip state; but crucially: no timer/answer control
        "hasTimer": False,
        "hasEnabledAnswerControl": False,
        "hasVoicemailCue": True,
    }

    audio = DummyAudio(
        rms=0.2,
        is_silent=False,
        has_speech_like=True,
        speech_duration_seconds=2.0,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        beep_detected=False,
        voicemail_keywords_detected_count=0,
        continuous_greeting_duration_seconds=0.0,
    )

    # If the detector incorrectly starts answer_elapsed_seconds from audio,
    # it could satisfy voicemail gating early.
    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=9)

    assert decision.state != DecisionState.VOICEMAIL.value


def test_dom_voicemail_cue_alone_not_enough_without_audio_confirmation():
    """If only DOM voicemail cue appears but there are no beep/keywords/continuous greeting,
    VOICEMAIL should not be emitted.
    """

    cfg = DetectionConfig(max_ring_seconds=55, answered_pending_seconds=10, voicemail_confirmation_count=1)
    det = LocalCallDetector(cfg)

    dom = {
        "state": "CONNECTED",
        "hasTimer": True,
        "hasEnabledAnswerControl": False,
        "hasVoicemailCue": True,
        # voicemail_match intentionally absent
    }

    audio = DummyAudio(
        rms=0.05,
        is_silent=False,
        has_speech_like=False,
        beep_detected=False,
        beep_hz_confidence=0.0,
        voicemail_keywords_detected_count=0,
        human_greeting_detected=False,
        short_speech_burst_detected=False,
        continuous_greeting_duration_seconds=0.0,
    )

    decision = det.decide(dom_evidence=dom, audio_features=audio, elapsed_seconds=20)

    assert decision.state != DecisionState.VOICEMAIL.value

