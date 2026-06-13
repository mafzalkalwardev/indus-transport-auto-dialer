"""Background whisper transcription tier for ambiguous AMD cases."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot, QMetaObject

from src.detection.whisper_transcriber import FasterWhisperTranscriber, WhisperTranscript


class WhisperTranscriptionWorker(QObject):
    finished = pyqtSignal(object)

    def __init__(self, transcriber: FasterWhisperTranscriber):
        super().__init__()
        self._transcriber = transcriber

    @pyqtSlot(object, int)
    def transcribe(self, pcm, sample_rate: int) -> None:
        try:
            result = self._transcriber.transcribe(pcm, sample_rate=sample_rate)
        except Exception as exc:
            result = WhisperTranscript("", False, str(exc))
        self.finished.emit(result)


class WhisperTranscriptionThread:
    """Lazy QThread wrapper — only started when amd_mode=whisper."""

    def __init__(self, parent: QObject | None = None):
        self._transcriber = FasterWhisperTranscriber()
        self._thread = QThread(parent)
        self._worker = WhisperTranscriptionWorker(self._transcriber)
        self._worker.moveToThread(self._thread)
        self._thread.start()

    def submit(self, pcm, *, sample_rate: int, callback) -> None:
        self._worker.finished.connect(callback, type=Qt.ConnectionType.SingleShotConnection)
        QMetaObject.invokeMethod(
            self._worker,
            "transcribe",
            Qt.ConnectionType.QueuedConnection,
            pcm,
            sample_rate,
        )

    def shutdown(self) -> None:
        self._thread.quit()
        self._thread.wait(1500)
