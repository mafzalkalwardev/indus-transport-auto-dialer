"""Voice activity detection helpers for local call audio.

The detector prefers ``webrtcvad`` when it is installed. If it is not present,
it falls back to a conservative RMS/zero-crossing heuristic so the dialer keeps
working without a native dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class VADResult:
    is_voice: bool
    confidence: float
    backend: str
    reason: str


class VoiceActivityDetector:
    def __init__(self, aggressiveness: int = 2):
        self.aggressiveness = max(0, min(3, int(aggressiveness)))
        try:
            import webrtcvad  # type: ignore

            self._vad = webrtcvad.Vad(self.aggressiveness)
            self.backend = "webrtcvad"
        except Exception:
            self._vad = None
            self.backend = "heuristic"

    def analyze_float_window(self, samples: list[float], sample_rate: int) -> VADResult:
        if not samples:
            return VADResult(False, 0.0, self.backend, "empty audio window")
        if self._vad is not None and sample_rate in (8000, 16000, 32000, 48000):
            return self._analyze_webrtcvad(samples, sample_rate)
        return self._analyze_heuristic(samples)

    def _analyze_webrtcvad(self, samples: list[float], sample_rate: int) -> VADResult:
        frame_ms = 30
        frame_len = int(sample_rate * frame_ms / 1000)
        if frame_len <= 0:
            return self._analyze_heuristic(samples)
        voiced = 0
        total = 0
        for start in range(0, len(samples) - frame_len + 1, frame_len):
            frame = samples[start:start + frame_len]
            pcm = self._float_to_pcm16(frame)
            try:
                if self._vad.is_speech(pcm, sample_rate):
                    voiced += 1
                total += 1
            except Exception:
                return self._analyze_heuristic(samples)
        if total == 0:
            return self._analyze_heuristic(samples)
        confidence = voiced / total
        return VADResult(
            is_voice=confidence >= 0.35,
            confidence=confidence,
            backend="webrtcvad",
            reason=f"voiced_frames={voiced}/{total}",
        )

    @staticmethod
    def _float_to_pcm16(samples: list[float]) -> bytes:
        clipped = [max(-1.0, min(1.0, float(v))) for v in samples]
        return struct.pack("<" + "h" * len(clipped), *[int(v * 32767) for v in clipped])

    @staticmethod
    def _analyze_heuristic(samples: list[float]) -> VADResult:
        rms = (sum(v * v for v in samples) / len(samples)) ** 0.5
        mean = sum(samples) / len(samples)
        var = sum((v - mean) ** 2 for v in samples) / len(samples)
        crossings = 0
        prev = samples[0]
        for cur in samples[1:]:
            if (prev < 0 <= cur) or (prev >= 0 > cur):
                crossings += 1
            prev = cur
        zcr = crossings / max(1, len(samples) - 1)
        voice_like = rms >= 0.012 and var > 0.00005 and 0.015 <= zcr <= 0.23
        confidence = min(1.0, max(0.0, (rms * 4.0) + (0.35 if voice_like else 0.0)))
        return VADResult(
            is_voice=voice_like,
            confidence=confidence,
            backend="heuristic",
            reason=f"rms={rms:.4f};zcr={zcr:.3f}",
        )
