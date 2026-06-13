"""Voicemail beep and SIT tone detection via Goertzel (no scipy required)."""
from __future__ import annotations

import math
from dataclasses import dataclass


BEEP_FREQUENCIES_HZ = (440.0, 1000.0)
SIT_FREQUENCIES_HZ = (913.0, 1370.0, 1776.0)


@dataclass(frozen=True)
class ToneDetectionResult:
    beep_detected: bool
    beep_confidence: float
    beep_frequency_hz: float
    sit_detected: bool
    sit_confidence: float
    dominant_tone_hz: float


def goertzel_power(samples: list[float], sample_rate: int, target_hz: float) -> float:
    """Normalized tone power at target_hz in [0, 1]."""
    if not samples or sample_rate <= 0 or target_hz <= 0:
        return 0.0
    n = len(samples)
    k = int(0.5 + (n * target_hz / sample_rate))
    omega = (2.0 * math.pi * k) / n
    coeff = 2.0 * math.cos(omega)
    q0 = q1 = q2 = 0.0
    for sample in samples:
        q0 = coeff * q1 - q2 + sample
        q2 = q1
        q1 = q0
    power = q1 * q1 + q2 * q2 - coeff * q1 * q2
    total = sum(s * s for s in samples) + 1e-9
    return max(0.0, min(1.0, power / (total * n) * 12.0))


def detect_tones(
    samples: list[float],
    *,
    sample_rate: int,
    beep_threshold: float = 0.55,
    sit_threshold: float = 0.45,
) -> ToneDetectionResult:
    """Detect voicemail beep (440/1000 Hz) and basic SIT multi-tone patterns."""
    if not samples:
        return ToneDetectionResult(False, 0.0, 0.0, False, 0.0, 0.0)

    beep_scores = {
        hz: goertzel_power(samples, sample_rate, hz) for hz in BEEP_FREQUENCIES_HZ
    }
    best_beep_hz = max(beep_scores, key=beep_scores.get)
    beep_conf = beep_scores[best_beep_hz]

    sit_scores = {
        hz: goertzel_power(samples, sample_rate, hz) for hz in SIT_FREQUENCIES_HZ
    }
    sit_avg = sum(sit_scores.values()) / len(sit_scores)
    sit_min = min(sit_scores.values())
    # SIT: multiple frequencies present with similar energy
    sit_detected = sit_avg >= sit_threshold and sit_min >= sit_threshold * 0.5
    sit_conf = sit_avg if sit_detected else 0.0

    all_hz = list(BEEP_FREQUENCIES_HZ) + list(SIT_FREQUENCIES_HZ)
    dominant_hz = max(all_hz, key=lambda hz: goertzel_power(samples, sample_rate, hz))

    return ToneDetectionResult(
        beep_detected=beep_conf >= beep_threshold,
        beep_confidence=beep_conf,
        beep_frequency_hz=best_beep_hz if beep_conf >= beep_threshold else 0.0,
        sit_detected=sit_detected,
        sit_confidence=sit_conf,
        dominant_tone_hz=dominant_hz,
    )
