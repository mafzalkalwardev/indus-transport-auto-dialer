"""Play a hold prompt to queued live answers.

On Windows the default path uses SAPI text-to-speech to synthesize
"Please wait while we connect your call." Configure ``hold_message_output_device``
in dialer_config.json when using a virtual audio cable so Google Voice sends the
prompt to the callee.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import wave

from src.paths import ROOT

DEFAULT_MESSAGE = "Please wait while we connect your call."
HOLD_WAV = os.path.join(ROOT, "assets", "audio", "please_wait_connect.wav")


class HoldMessagePlayer:
    def __init__(
        self,
        *,
        wav_path: str = "",
        message: str = DEFAULT_MESSAGE,
        output_device: str | int | None = None,
    ) -> None:
        self.wav_path = wav_path or HOLD_WAV
        self.message = message or DEFAULT_MESSAGE
        self.output_device = output_device
        self._lock = threading.Lock()
        self._playing = False

    def set_message(self, message: str) -> None:
        self.message = message or DEFAULT_MESSAGE

    def play(self) -> bool:
        """Play the hold prompt once (non-blocking). Returns True if playback started."""
        with self._lock:
            if self._playing:
                return False
            self._playing = True
        thread = threading.Thread(target=self._play_blocking, daemon=True)
        thread.start()
        return True

    def _play_blocking(self) -> None:
        try:
            path = self._ensure_wav()
            if not path:
                return
            self._play_wav(path)
        finally:
            with self._lock:
                self._playing = False

    def _ensure_wav(self) -> str:
        if os.path.isfile(self.wav_path):
            return self.wav_path
        os.makedirs(os.path.dirname(self.wav_path), exist_ok=True)
        if sys.platform == "win32" and self._synthesize_windows(self.wav_path):
            return self.wav_path
        self._write_fallback_tone(self.wav_path)
        return self.wav_path

    def _synthesize_windows(self, path: str) -> bool:
        text = self.message.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{path.replace(chr(92), '/')}'); "
            f"$s.Speak('{text}'); "
            "$s.Dispose()"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return proc.returncode == 0 and os.path.isfile(path)
        except Exception:
            return False

    def _write_fallback_tone(self, path: str) -> None:
        import math

        sample_rate = 16000
        seconds = 2.4
        samples = []
        for i in range(int(sample_rate * seconds)):
            t = i / sample_rate
            amp = 0.18 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.5 * t))
            freq = 440.0 if int(t * 2) % 2 == 0 else 523.25
            samples.append(amp * math.sin(2 * math.pi * freq * t))
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            frames = bytearray()
            for sample in samples:
                value = int(max(-1.0, min(1.0, sample)) * 32767)
                frames.extend(value.to_bytes(2, byteorder="little", signed=True))
            wf.writeframes(bytes(frames))

    def _play_wav(self, path: str) -> None:
        try:
            import sounddevice as sd  # type: ignore
        except Exception:
            return
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        import numpy as np  # type: ignore

        audio = np.frombuffer(frames, dtype=np.int16).astype("float32") / 32768.0
        if channels > 1:
            audio = audio.reshape(-1, channels)
        device = self.output_device
        if device == "":
            device = None
        sd.play(audio, sample_rate, device=device)
        sd.wait()
