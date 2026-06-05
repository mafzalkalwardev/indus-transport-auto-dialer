"""Compatibility wrapper for local call audio capture."""
from __future__ import annotations

from .audio_analyzer import AudioAnalyzer, AudioFeatures


class AudioListener:
    def __init__(self, *, enabled: bool = True, device: int | str | None = None):
        self.analyzer = AudioAnalyzer(enable_audio=enabled, device=device)

    def poll(self) -> AudioFeatures:
        return self.analyzer.get_features_real_time()
