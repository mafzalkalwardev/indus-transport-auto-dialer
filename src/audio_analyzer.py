"""Local Windows audio feature extraction for call detection.

The analyzer never calls cloud services. In live mode it attempts to capture
browser output through ``sounddevice`` WASAPI loopback on Windows. If the
backend is unavailable, callers get a clear ``NO_BACKEND`` status and safe
silent features so DOM detection can continue.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import time
from typing import Any

from .detection.tone_detector import detect_tones
from .vad import VoiceActivityDetector


@dataclass
class AudioFeatures:
    rms: float = 0.0
    is_silent: bool = True
    has_speech_like: bool = False
    ringback_cadence_confidence: float = 0.0
    beep_hz_confidence: float = 0.0
    silence_duration_seconds: float = 0.0
    speech_duration_seconds: float = 0.0
    continuous_greeting_duration_seconds: float = 0.0
    short_speech_burst_detected: bool = False
    human_greeting_detected: bool = False
    voicemail_keywords_detected_count: int = 0
    background_noise_level: float = 0.0
    busy_tone_cadence_confidence: float = 0.0
    beep_detected: bool = False
    confidence: float = 0.0
    reason: str = "audio disabled"
    backend_status: str = "OFF"
    backend_name: str = ""
    vad_backend: str = ""
    vad_confidence: float = 0.0


class AudioAnalyzer:
    """Analyze provided PCM or live loopback audio chunks."""

    def __init__(
        self,
        *,
        enable_audio: bool = True,
        enable_beep_detection: bool = True,
        device: int | str | None = None,
        sample_rate: int = 16000,
        chunk_seconds: float = 0.25,
    ):
        self.enable_audio = enable_audio
        self.enable_beep_detection = enable_beep_detection
        self.device = device
        self.sample_rate = int(sample_rate)
        self.chunk_seconds = float(chunk_seconds)
        self.backend_status = "OFF" if not enable_audio else "UNKNOWN"
        self.backend_name = ""
        self._last_voice_at: float | None = None
        self._speech_started_at: float | None = None
        self._recent_rms: list[float] = []
        self._recent_voice: list[bool] = []
        self._backend_error = ""
        self._vad = VoiceActivityDetector()
        self._last_capture_at = 0.0
        self._cached_features: AudioFeatures | None = None
        self._capture_failures = 0
        self._disabled_until = 0.0
        self._last_pcm: list[float] = []

    def analyze_from_pcm(
        self,
        pcm_mono,
        *,
        sample_rate: int,
        transcript: str = "",
    ) -> AudioFeatures:
        try:
            x = [float(v) for v in pcm_mono]
        except Exception:
            return self._features(reason="invalid pcm")

        if not x:
            return self._features(reason="empty pcm")

        # Normalize int16-like samples when callers pass raw audio.
        peak = max(abs(v) for v in x) or 1.0
        if peak > 2.0:
            x = [v / 32768.0 for v in x]

        self._last_pcm = x[-8000:]

        rms = math.sqrt(sum(v * v for v in x) / len(x))
        mean = sum(x) / len(x)
        var = sum((v - mean) ** 2 for v in x) / len(x)
        zero_crossings = 0
        prev = x[0]
        for cur in x[1:]:
            if (prev < 0 <= cur) or (prev >= 0 > cur):
                zero_crossings += 1
            prev = cur
        zcr = zero_crossings / max(1, len(x) - 1)

        is_silent = rms < 0.012
        heuristic_speech_like = (not is_silent) and 0.015 <= zcr <= 0.23 and var > 0.00005
        vad = self._vad.analyze_float_window(x, sample_rate)
        has_speech_like = vad.is_voice or heuristic_speech_like
        now = time.monotonic()
        if has_speech_like:
            if self._speech_started_at is None:
                self._speech_started_at = now
            self._last_voice_at = now
        elif self._last_voice_at and (now - self._last_voice_at) > 0.9:
            self._speech_started_at = None

        speech_duration = (
            max(0.0, now - self._speech_started_at)
            if self._speech_started_at is not None else 0.0
        )
        silence_duration = (
            max(0.0, now - self._last_voice_at)
            if self._last_voice_at is not None and not has_speech_like else 0.0
        )

        self._recent_rms = (self._recent_rms + [rms])[-12:]
        self._recent_voice = (self._recent_voice + [has_speech_like])[-12:]
        ring_conf = self._cadence_confidence(target_voice=False)
        busy_conf = self._busy_confidence()
        tone = (
            detect_tones(x, sample_rate=sample_rate)
            if self.enable_beep_detection
            else None
        )
        beep_conf = tone.beep_confidence if tone else 0.0
        sit_conf = tone.sit_confidence if tone else 0.0
        greeting = self._has_human_greeting(transcript)
        short_burst = 0.15 <= speech_duration <= 2.5 and has_speech_like
        vm_keywords = self._voicemail_keyword_count(transcript)
        conf = max(rms, ring_conf, busy_conf, beep_conf, vad.confidence, 0.65 if has_speech_like else 0.0)

        reason_parts = []
        if has_speech_like:
            reason_parts.append("speech-like audio")
        if ring_conf >= 0.65:
            reason_parts.append("ringback cadence")
        if busy_conf >= 0.75:
            reason_parts.append("busy cadence")
        if tone and tone.sit_detected:
            reason_parts.append("SIT tone pattern")
        if beep_conf >= 0.55:
            freq = int(tone.beep_frequency_hz) if tone and tone.beep_frequency_hz else 1000
            reason_parts.append(f"{freq}Hz beep")
        if not reason_parts:
            reason_parts.append("silence/noise")

        return AudioFeatures(
            rms=rms,
            is_silent=is_silent,
            has_speech_like=has_speech_like,
            ringback_cadence_confidence=ring_conf,
            beep_hz_confidence=beep_conf,
            silence_duration_seconds=silence_duration,
            speech_duration_seconds=speech_duration,
            continuous_greeting_duration_seconds=speech_duration if has_speech_like else 0.0,
            short_speech_burst_detected=short_burst,
            human_greeting_detected=greeting,
            voicemail_keywords_detected_count=vm_keywords,
            background_noise_level=max(0.0, rms - (0.08 if has_speech_like else 0.0)),
            busy_tone_cadence_confidence=busy_conf,
            beep_detected=bool(tone and (tone.beep_detected or tone.sit_detected)),
            confidence=min(1.0, conf),
            reason=", ".join(reason_parts),
            backend_status=self.backend_status,
            backend_name=self.backend_name,
            vad_backend=vad.backend,
            vad_confidence=vad.confidence,
        )

    def get_features_real_time(self) -> AudioFeatures:
        if not self.enable_audio:
            self.backend_status = "OFF"
            return self._features(reason="audio disabled", backend_status="OFF")

        now = time.monotonic()
        if now < self._disabled_until:
            if self._cached_features is not None:
                return self._cached_features
            return self._features(
                reason="audio capture paused after repeated failures",
                backend_status="NO_BACKEND",
            )
        if self._cached_features is not None and (now - self._last_capture_at) < 0.75:
            return self._cached_features

        try:
            import sounddevice as sd  # type: ignore
        except Exception as exc:
            self.backend_status = "NO_BACKEND"
            self._backend_error = str(exc)
            features = self._features(reason="sounddevice not installed", backend_status="NO_BACKEND")
            self._cached_features = features
            return features

        try:
            candidates = self._capture_candidates(sd)
            last_error = None
            best_silent: AudioFeatures | None = None
            for candidate in dict.fromkeys(candidates):
                try:
                    features = self._capture_device(sd, candidate)
                    self._capture_failures = 0
                    self._last_capture_at = now
                    self._cached_features = features
                    if (
                        features.has_speech_like
                        or features.ringback_cadence_confidence >= 0.45
                        or features.busy_tone_cadence_confidence >= 0.45
                        or features.beep_detected
                        or features.rms >= 0.012
                    ):
                        return features
                    if best_silent is None or features.rms > best_silent.rms:
                        best_silent = features
                except Exception as exc:
                    last_error = exc
            if best_silent is not None:
                self._last_capture_at = now
                self._cached_features = best_silent
                return best_silent
            raise last_error or RuntimeError("no audio capture device worked")
        except Exception as exc:
            self._capture_failures += 1
            if self._capture_failures >= 3:
                self._disabled_until = now + 45.0
            self.backend_status = "NO_BACKEND"
            self._backend_error = str(exc)
            features = self._features(
                reason=f"audio capture unavailable: {exc}",
                backend_status="NO_BACKEND",
            )
            self._cached_features = features
            return features

    def _capture_candidates(self, sd) -> list[int | str | None]:
        """Prefer Windows loopback-friendly inputs before speaker WASAPI loopback."""
        resolved = self._resolve_device(sd)
        if resolved is not None:
            return [resolved]

        candidates: list[int | str | None] = []
        for idx, dev in enumerate(sd.query_devices()):
            name = str(dev.get("name", "")).lower()
            in_ch = int(dev.get("max_input_channels", 0) or 0)
            if in_ch <= 0:
                continue
            if "stereo mix" in name:
                candidates.append(idx)
            elif "cable output" in name and in_ch == 2:
                candidates.append(idx)

        try:
            default_output = sd.default.device[1]
            if default_output is not None and int(default_output) >= 0:
                candidates.append(int(default_output))
        except Exception:
            pass
        candidates.append(None)
        return list(dict.fromkeys(candidates))

    def _capture_device(self, sd, device: int | str | None) -> AudioFeatures:
            info = sd.query_devices(device)
            output_channels = int(info.get("max_output_channels", 0) or 0)
            input_channels = int(info.get("max_input_channels", 0) or 0)
            sample_rate = int(float(info.get("default_samplerate", 0) or self.sample_rate))
            use_loopback = output_channels > 0 and input_channels <= 0
            extra = None
            if use_loopback:
                try:
                    extra = sd.WasapiSettings(loopback=True)
                except Exception as exc:
                    raise RuntimeError(
                        "output loopback is not supported by installed sounddevice"
                    ) from exc
                channel_options = [
                    c for c in (output_channels, 2, 1) if c and c > 0
                ]
            else:
                channel_options = [
                    c for c in (1, 2, min(input_channels, 2)) if c and c > 0
                ]
            channel_options = list(dict.fromkeys(channel_options))

            poll_seconds = min(self.chunk_seconds, 0.12)
            last_error: Exception | None = None
            for channels in channel_options:
                try:
                    frames = max(256, int(sample_rate * poll_seconds))
                    data = sd.rec(
                        frames,
                        samplerate=sample_rate,
                        channels=channels,
                        dtype="float32",
                        device=device,
                        blocking=True,
                        extra_settings=extra,
                    )
                    mono = [
                        float(sum(row) / len(row)) if hasattr(row, "__len__") else float(row)
                        for row in data
                    ]
                    self.backend_status = "ON"
                    self.backend_name = self._device_name(sd, device)
                    return self.analyze_from_pcm(mono, sample_rate=sample_rate)
                except Exception as exc:
                    last_error = exc
            raise last_error or RuntimeError("no supported channel layout for device")

    @staticmethod
    def recommend_capture_device() -> str:
        """Best-effort Windows capture device index for AMD loopback."""
        try:
            import sounddevice as sd  # type: ignore
        except Exception:
            return ""
        for idx, dev in enumerate(sd.query_devices()):
            name = str(dev.get("name", "")).lower()
            in_ch = int(dev.get("max_input_channels", 0) or 0)
            if in_ch <= 0:
                continue
            if "stereo mix" in name:
                return str(idx)
        for idx, dev in enumerate(sd.query_devices()):
            name = str(dev.get("name", "")).lower()
            in_ch = int(dev.get("max_input_channels", 0) or 0)
            if "cable output" in name and in_ch == 2:
                return str(idx)
        return ""

    @staticmethod
    def list_audio_devices() -> list[dict[str, Any]]:
        try:
            import sounddevice as sd  # type: ignore
            devices = sd.query_devices()
            return [
                {
                    "index": idx,
                    "name": str(dev.get("name", "")),
                    "max_input_channels": int(dev.get("max_input_channels", 0)),
                    "max_output_channels": int(dev.get("max_output_channels", 0)),
                    "default_samplerate": float(dev.get("default_samplerate", 0) or 0),
                }
                for idx, dev in enumerate(devices)
            ]
        except Exception:
            return []

    def _resolve_device(self, sd) -> int | str | None:
        if self.device not in (None, ""):
            if isinstance(self.device, str) and self.device.strip().isdigit():
                return int(self.device.strip())
            return self.device
        return None

    @staticmethod
    def _device_name(sd, device: int | str | None) -> str:
        try:
            if device is None:
                return "default"
            info = sd.query_devices(device)
            return str(info.get("name", device))
        except Exception:
            return str(device or "default")

    def _features(self, *, reason: str, backend_status: str | None = None) -> AudioFeatures:
        return AudioFeatures(
            reason=reason,
            backend_status=backend_status or self.backend_status,
            backend_name=self.backend_name,
        )

    def _cadence_confidence(self, *, target_voice: bool) -> float:
        if len(self._recent_rms) < 4:
            return 0.0
        loud = [v > 0.025 for v in self._recent_rms]
        transitions = sum(1 for a, b in zip(loud, loud[1:]) if a != b)
        if transitions < 2:
            return 0.0
        duty = sum(loud) / len(loud)
        if target_voice:
            return min(1.0, transitions / 6.0)
        return 0.75 if 0.25 <= duty <= 0.75 else 0.35

    def _busy_confidence(self) -> float:
        if len(self._recent_rms) < 6:
            return 0.0
        loud = [v > 0.03 for v in self._recent_rms[-8:]]
        transitions = sum(1 for a, b in zip(loud, loud[1:]) if a != b)
        duty = sum(loud) / len(loud)
        return 0.85 if transitions >= 4 and 0.35 <= duty <= 0.65 else 0.0

    @staticmethod
    def _tone_confidence(samples: list[float], sample_rate: int, target_hz: float) -> float:
        if not samples or sample_rate <= 0:
            return 0.0
        # Goertzel detector around the target tone, dependency-free.
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

    @staticmethod
    def _has_human_greeting(text: str) -> bool:
        return bool(re.search(r"\b(hello|hi|hey|yes|yeah|speaking)\b", text or "", re.I))

    @staticmethod
    def _voicemail_keyword_count(text: str) -> int:
        phrases = (
            "leave a message",
            "after the beep",
            "after the tone",
            "voicemail",
            "not available",
            "cannot take your call",
        )
        lower = (text or "").lower()
        return sum(1 for phrase in phrases if phrase in lower)
