"""Optional faster-whisper integration for early-call transcript snippets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WhisperTranscript:
    text: str
    available: bool
    reason: str = ""


class FasterWhisperTranscriber:
    """Small lazy wrapper around faster-whisper tiny.en.

    The dialer can run without this optional dependency; callers get a clear
    unavailable result instead of an import-time failure.
    """

    def __init__(self, model_name: str = "tiny.en", device: str = "cpu", compute_type: str = "int8"):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model: Any | None = None
        self._load_error = ""

    def transcribe(self, audio: Any, *, sample_rate: int = 16000) -> WhisperTranscript:
        model = self._get_model()
        if model is None:
            return WhisperTranscript("", False, self._load_error or "faster-whisper unavailable")
        try:
            segments, _info = model.transcribe(audio, language="en", vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            return WhisperTranscript(text, True, "")
        except Exception as exc:
            return WhisperTranscript("", False, str(exc))

    def _get_model(self) -> Any | None:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore

            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as exc:
            self._load_error = str(exc)
            self._model = None
        return self._model
