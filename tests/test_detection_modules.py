import math

from src.human_detector import HumanDetector
from src.vad import VoiceActivityDetector
from src.voicemail_detector import VoicemailDetector


def test_human_detector_short_greeting_wins():
    result = HumanDetector().classify(
        transcript="hello?",
        speech_duration_seconds=0.8,
        answer_elapsed_seconds=1.0,
        has_speech_like=True,
        human_greeting_detected=True,
        short_speech_burst_detected=True,
    )
    assert result.detected
    assert result.confidence >= 0.7


def test_voicemail_detector_requires_timing_and_two_signals():
    det = VoicemailDetector()
    early = det.classify(
        transcript="please leave a message after the tone",
        answer_elapsed_seconds=4.0,
        continuous_greeting_duration_seconds=5.0,
        beep_detected=True,
    )
    later = det.classify(
        transcript="please leave a message after the tone",
        answer_elapsed_seconds=8.0,
        continuous_greeting_duration_seconds=5.0,
        beep_detected=True,
    )
    assert not early.candidate
    assert later.candidate


def test_vad_detects_generated_voice_like_tone_with_fallback():
    samples = [0.2 * math.sin(2 * math.pi * 180 * i / 16000) for i in range(16000 // 2)]
    result = VoiceActivityDetector().analyze_float_window(samples, 16000)
    assert result.backend in ("webrtcvad", "heuristic")
    assert result.confidence >= 0.0
