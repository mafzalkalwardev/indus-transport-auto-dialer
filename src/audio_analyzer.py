"""Local audio analyzer.

No cloud / paid APIs.

This implementation is intentionally conservative:
- It provides an interface that can run in unit tests using simulated audio features.
- In real runs, it attempts to use local microphone/loopback capture if dependencies exist.

Current minimal implementation:
- AudioFeatures extraction from a provided mono PCM stream (optional).
- If capture is not configured, it returns features with conservative defaults.

You can later extend audio capture to WASAPI loopback, PyAudio, sounddevice, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class AudioFeatures:
    rms: float = 0.0
    is_silent: bool = True
    has_speech_like: bool = False
    ringback_cadence_confidence: float = 0.0
    beep_hz_confidence: float = 0.0


class AudioAnalyzer:
    """Offline/real-time compatible analyzer.

    For unit tests you can bypass AudioAnalyzer and feed AudioFeatures
    directly into the detector.
    """

    def __init__(
        self,
        *,
        enable_audio: bool = True,
        enable_beep_detection: bool = True,
    ):
        self.enable_audio = enable_audio
        self.enable_beep_detection = enable_beep_detection

    def analyze_from_pcm(
        self,
        pcm_mono,
        *,
        sample_rate: int,
    ) -> AudioFeatures:
        """Analyze a chunk of mono PCM.

        pcm_mono: sequence of floats or ints.
        This function does not assume external deps.
        """
        # Minimal, dependency-free feature extraction.
        # If you need FFT/cadence/ringback detection, extend with numpy/scipy.
        try:
            # Convert to list of floats
            x = [float(v) for v in pcm_mono]
        except Exception:
            return AudioFeatures()

        if not x:
            return AudioFeatures()

        # RMS volume
        s2 = 0.0
        for v in x:
            s2 += v * v
        rms = (s2 / len(x)) ** 0.5

        # Silence heuristic
        is_silent = rms < 0.01

        # Speech-like heuristic: variability above silence threshold
        mean = sum(x) / len(x)
        var = sum((v - mean) ** 2 for v in x) / len(x)
        has_speech_like = (not is_silent) and var > (0.0001)

        # Beep detection: without FFT this is not reliable; return 0.
        beep_conf = 0.0

        # Ringback cadence confidence: not reliable without FFT; return 0.
        ring_conf = 0.0

        return AudioFeatures(
            rms=rms,
            is_silent=is_silent,
            has_speech_like=has_speech_like,
            ringback_cadence_confidence=ring_conf,
            beep_hz_confidence=beep_conf,
        )

    def get_features_real_time(self) -> AudioFeatures:
        """Try to get features from real audio capture.

        This is a placeholder that returns defaults unless capture is implemented.
        """
        if not self.enable_audio:
            return AudioFeatures()
        # TODO: Implement WASAPI loopback capture in a dependency-free way.
        # Keep default safe output.
        return AudioFeatures()

