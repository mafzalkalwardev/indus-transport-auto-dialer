"""Small per-slot wrapper around local audio capture."""
from __future__ import annotations

from dataclasses import asdict

from .audio_analyzer import AudioAnalyzer, AudioFeatures


class CallAudioMonitor:
    def __init__(self, *, enabled: bool = True, device: int | str | None = None):
        self.enabled = bool(enabled)
        self.analyzer = AudioAnalyzer(enable_audio=self.enabled, device=device)
        self.last_features = AudioFeatures(backend_status="OFF" if not enabled else "UNKNOWN")

    def poll(self) -> AudioFeatures:
        self.last_features = self.analyzer.get_features_real_time()
        return self.last_features

    def status_label(self) -> str:
        status = self.last_features.backend_status
        if status == "ON":
            return "AI Audio: ON"
        if status == "NO_BACKEND":
            return "AI Audio: NO BACKEND"
        return "AI Audio: OFF"

    def debug_dict(self) -> dict:
        return asdict(self.last_features)
