"""Per-slot audio features for call detection — capture runs off the UI thread."""
from __future__ import annotations

from dataclasses import asdict

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot, QMetaObject

from .audio_analyzer import AudioAnalyzer, AudioFeatures


class _AudioCaptureWorker(QObject):
    capture_done = pyqtSignal(object)

    def __init__(self, analyzer: AudioAnalyzer):
        super().__init__()
        self._analyzer = analyzer

    @pyqtSlot()
    def capture(self) -> None:
        try:
            features = self._analyzer.get_features_real_time()
        except Exception as exc:
            features = AudioFeatures(
                backend_status="NO_BACKEND",
                reason=f"capture error: {exc}",
            )
        self.capture_done.emit(features)


class CallAudioMonitor:
    def __init__(
        self,
        *,
        enabled: bool = True,
        device: int | str | None = None,
        parent: QObject | None = None,
    ):
        self.enabled = bool(enabled)
        self.analyzer = AudioAnalyzer(enable_audio=self.enabled, device=device)
        self.last_features = AudioFeatures(
            backend_status="OFF" if not enabled else "UNKNOWN",
        )
        self._inflight = False
        self._thread: QThread | None = None
        self._worker: _AudioCaptureWorker | None = None
        if self.enabled:
            self._thread = QThread(parent)
            self._worker = _AudioCaptureWorker(self.analyzer)
            self._worker.moveToThread(self._thread)
            self._worker.capture_done.connect(self._on_capture_done)
            self._thread.start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.analyzer.enable_audio = self.enabled
        if not self.enabled:
            self.last_features = AudioFeatures(
                backend_status="OFF",
                reason="audio disabled",
            )

    def _on_capture_done(self, features: AudioFeatures) -> None:
        self.last_features = features
        self._inflight = False

    def poll(self) -> AudioFeatures:
        if not self.enabled or self._worker is None:
            return self.last_features
        if self._inflight:
            return self.last_features
        self._inflight = True
        QMetaObject.invokeMethod(
            self._worker,
            "capture",
            Qt.ConnectionType.QueuedConnection,
        )
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

    def shutdown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(1500)
            self._thread = None
            self._worker = None
