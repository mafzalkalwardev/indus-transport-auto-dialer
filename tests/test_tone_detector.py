import math

import pytest

from src.detection.tone_detector import detect_tones, goertzel_power


def _sine(freq_hz: float, *, sample_rate: int = 16000, duration: float = 0.5) -> list[float]:
    n = int(sample_rate * duration)
    return [
        math.sin(2.0 * math.pi * freq_hz * i / sample_rate) for i in range(n)
    ]


def test_goertzel_detects_440hz_beep():
    samples = _sine(440.0)
    power = goertzel_power(samples, 16000, 440.0)
    assert power >= 0.55


def test_goertzel_detects_1000hz_beep():
    samples = _sine(1000.0)
    result = detect_tones(samples, sample_rate=16000)
    assert result.beep_detected
    assert result.beep_confidence >= 0.55


def test_silence_not_beep():
    samples = [0.0] * 8000
    result = detect_tones(samples, sample_rate=16000)
    assert not result.beep_detected
    assert result.beep_confidence < 0.3


def test_noise_low_beep_confidence():
    import random

    random.seed(42)
    samples = [random.uniform(-0.05, 0.05) for _ in range(8000)]
    result = detect_tones(samples, sample_rate=16000)
    assert result.beep_confidence < 0.5
