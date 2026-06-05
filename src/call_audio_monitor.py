"""
Live call-audio monitor.

Captures the audio coming out of one Google Voice line (system speaker
loopback) in a background thread, runs it through the trained
``CallProgressClassifier`` every ~0.5 s and emits a state hint that
``GVController`` fuses with its DOM detection.

Audio capture is **best-effort**: it tries the ``soundcard`` library
(cross-platform speaker loopback), then ``sounddevice`` (default input).
If neither backend / device is available the monitor stays disabled and the
app silently falls back to the (hardened) DOM-only detection — so this never
breaks dialing.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from src.call_audio_ai import (
    SAMPLE_RATE,
    WINDOW_SEC,
    CallProgressClassifier,
    CPAResult,
)


def _try_import_backend():
    """Return ("soundcard"|"sounddevice"|None, module)."""
    try:
        import soundcard  # type: ignore
        return "soundcard", soundcard
    except Exception:
        pass
    try:
        import sounddevice  # type: ignore
        return "sounddevice", sounddevice
    except Exception:
        pass
    return None, None


class CallAudioMonitor(QObject):
    """Per-line audio classifier. One instance per dialer slot."""

    # (slot_id, label, app_state, confidence)
    result_ready = pyqtSignal(int, str, str, float)

    _shared_clf: Optional[CallProgressClassifier] = None

    def __init__(self, slot_id: int, parent: QObject | None = None,
                 hop_sec: float = 0.5):
        super().__init__(parent)
        self.slot_id = slot_id
        self.hop_sec = hop_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last: Optional[CPAResult] = None

        if CallAudioMonitor._shared_clf is None:
            CallAudioMonitor._shared_clf = CallProgressClassifier()
        self._clf = CallAudioMonitor._shared_clf

        self._backend_name, self._backend = _try_import_backend()

    @property
    def available(self) -> bool:
        return self._backend is not None

    @property
    def last_result(self) -> Optional[CPAResult]:
        return self._last

    def start(self) -> None:
        if self._running or not self.available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._last = None

    # ── capture backends ──────────────────────────────────────────────────────
    def _record_window_soundcard(self) -> Optional[np.ndarray]:
        sc = self._backend
        try:
            spk = sc.default_speaker()
            mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
            n = int(WINDOW_SEC * SAMPLE_RATE)
            with mic.recorder(samplerate=SAMPLE_RATE, channels=1) as rec:
                data = rec.record(numframes=n)
            return np.asarray(data, dtype=np.float64).reshape(-1)
        except Exception:
            return None

    def _record_window_sounddevice(self) -> Optional[np.ndarray]:
        sd = self._backend
        try:
            n = int(WINDOW_SEC * SAMPLE_RATE)
            data = sd.rec(n, samplerate=SAMPLE_RATE, channels=1, dtype="float64")
            sd.wait()
            return np.asarray(data, dtype=np.float64).reshape(-1)
        except Exception:
            return None

    def _record_window(self) -> Optional[np.ndarray]:
        if self._backend_name == "soundcard":
            return self._record_window_soundcard()
        if self._backend_name == "sounddevice":
            return self._record_window_sounddevice()
        return None

    # ── loop ───────────────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while self._running:
            window = self._record_window()
            if window is None or window.size == 0:
                time.sleep(self.hop_sec)
                continue
            try:
                res = self._clf.classify(window, SAMPLE_RATE)
            except Exception:
                time.sleep(self.hop_sec)
                continue
            self._last = res
            self.result_ready.emit(
                self.slot_id, res.label, res.state, float(res.confidence))
            time.sleep(self.hop_sec)
