"""Local FastAPI AMD service — faster-whisper STT + rule classifier + optional Ollama.

Compatible with LocalAmdPublisher websocket protocol used by the dialer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import time
from collections import deque
from typing import Any

import numpy as np

from src.detection.unified_transcript_classifier import (
    classification_to_external_label,
    classify_transcript,
)

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - optional at import time
    FastAPI = None  # type: ignore
    WebSocket = object  # type: ignore
    WebSocketDisconnect = Exception  # type: ignore
    JSONResponse = object  # type: ignore
    BaseModel = object  # type: ignore
    Field = lambda *a, **k: None  # type: ignore


class ClassifyRequest(BaseModel):
    transcript: str = ""
    duration_seconds: float = 0.0
    near_silence: bool = False


class AmdFastApiService:
    """Stateful helper used by the FastAPI app factory."""

    def __init__(self) -> None:
        self._whisper = None
        self._whisper_error = ""
        self._ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self._ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        self._whisper_model = os.environ.get("AMD_WHISPER_MODEL", "tiny.en")

    def _get_whisper(self):
        if self._whisper is not None:
            return self._whisper
        try:
            from faster_whisper import WhisperModel  # type: ignore

            device = os.environ.get("AMD_WHISPER_DEVICE", "cpu")
            compute = os.environ.get("AMD_WHISPER_COMPUTE", "int8")
            self._whisper = WhisperModel(self._whisper_model, device=device, compute_type=compute)
        except Exception as exc:
            self._whisper_error = str(exc)
            self._whisper = None
        return self._whisper

    def transcribe_pcm16(self, pcm_bytes: bytes, *, sample_rate: int = 16000) -> tuple[str, bool, str]:
        if not pcm_bytes:
            return "", False, "empty audio"
        model = self._get_whisper()
        if model is None:
            return "", False, self._whisper_error or "faster-whisper unavailable"
        count = len(pcm_bytes) // 2
        if count <= 0:
            return "", False, "empty audio"
        ints = struct.unpack(f"<{count}h", pcm_bytes[: count * 2])
        audio = np.asarray(ints, dtype=np.float32) / 32768.0
        try:
            segments, _info = model.transcribe(audio, language="en", vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text, True, ""
        except Exception as exc:
            return "", False, str(exc)

    def classify_text(
        self,
        transcript: str,
        *,
        duration_seconds: float = 0.0,
        near_silence: bool = False,
        use_ollama: bool = True,
    ) -> dict[str, Any]:
        result = classify_transcript(
            transcript,
            duration_seconds=duration_seconds,
            near_silence=near_silence,
        )
        label = classification_to_external_label(result.classification)
        confidence = float(result.confidence or 0.0)
        reason = result.reason or result.classification

        if use_ollama and result.classification in {"unknown", "unknown_or_silence"} and transcript.strip():
            ollama = self._classify_with_ollama(transcript)
            if ollama:
                label = ollama.get("finalAmdState") or label
                confidence = float(ollama.get("confidence") or confidence)
                reason = str(ollama.get("reason") or reason)

        return {
            "classification": result.classification,
            "finalAmdState": label,
            "confidence": round(confidence, 3),
            "transcript": transcript,
            "reason": reason,
            "matched_rules": result.matched_rules,
            "human_score": result.human_score,
            "voicemail_score": result.voicemail_score,
        }

    def _classify_with_ollama(self, transcript: str) -> dict[str, Any] | None:
        try:
            import urllib.request

            prompt = (
                "Classify this phone call opening as exactly one label: "
                "human_picked, voicemail_detected, busy_or_failed, call_screening_prompt, unknown_or_silence.\n"
                f"Transcript: {transcript[:1500]}\n"
                "Reply JSON only: {\"label\":\"...\",\"confidence\":0.0,\"reason\":\"...\"}"
            )
            body = json.dumps({
                "model": self._ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self._ollama_url}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            raw = str(payload.get("response") or "").strip()
            if not raw:
                return None
            parsed = json.loads(raw)
            label = str(parsed.get("label") or "unknown_or_silence")
            return {
                "finalAmdState": label,
                "confidence": float(parsed.get("confidence") or 0.55),
                "reason": f"ollama:{parsed.get('reason') or label}",
            }
        except Exception as exc:
            logger.debug("Ollama classify skipped: %s", exc)
            return None


def create_app(service: AmdFastApiService | None = None):
    if FastAPI is None:
        raise RuntimeError("fastapi is not installed — pip install fastapi uvicorn")

    svc = service or AmdFastApiService()
    app = FastAPI(title="Indus Transports AMD API", version="1.0.0")

    @app.get("/health")
    async def health() -> JSONResponse:
        whisper_ok = svc._get_whisper() is not None
        return JSONResponse({
            "status": "ok",
            "whisper": whisper_ok,
            "whisper_model": svc._whisper_model,
            "whisper_error": svc._whisper_error,
            "ollama_url": svc._ollama_url,
            "ollama_model": svc._ollama_model,
        })

    @app.post("/classify-transcript")
    async def classify_transcript_http(req: ClassifyRequest) -> dict[str, Any]:
        return svc.classify_text(
            req.transcript,
            duration_seconds=req.duration_seconds,
            near_silence=req.near_silence,
        )

    @app.websocket("/ws/amd-audio")
    async def amd_audio_ws(ws: WebSocket) -> None:
        await ws.accept()
        buffer = bytearray()
        last_emit = 0.0
        sample_rate = 16000
        try:
            while True:
                try:
                    message = await asyncio.wait_for(ws.receive(), timeout=0.25)
                except asyncio.TimeoutError:
                    message = None
                if message is not None:
                    if message.get("type") == "websocket.disconnect":
                        break
                    data = message.get("bytes")
                    if data:
                        buffer.extend(data)
                        if len(buffer) > sample_rate * 2 * 30:
                            buffer = buffer[-sample_rate * 2 * 30 :]

                now = time.monotonic()
                min_bytes = sample_rate * 2  # ~1 second PCM16 mono
                if len(buffer) >= min_bytes and (now - last_emit) >= 1.2:
                    pcm = bytes(buffer)
                    started = time.monotonic()
                    transcript, ok, err = svc.transcribe_pcm16(pcm, sample_rate=sample_rate)
                    classified = svc.classify_text(transcript) if ok else {
                        "finalAmdState": "unknown_or_silence",
                        "confidence": 0.0,
                        "transcript": "",
                        "reason": err or "transcription failed",
                    }
                    latency_ms = int((time.monotonic() - started) * 1000)
                    await ws.send_json({
                        "type": "backend_amd_update",
                        "finalAmdState": classified.get("finalAmdState"),
                        "confidence": classified.get("confidence"),
                        "transcript": classified.get("transcript") or transcript,
                        "partial": transcript,
                        "reason": classified.get("reason"),
                        "latency_ms": latency_ms,
                        "backendConnected": True,
                        "whisper_ok": ok,
                    })
                    last_emit = now
                    buffer.clear()
        except WebSocketDisconnect:
            return

    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("AMD_API_HOST", "127.0.0.1")
    port = int(os.environ.get("AMD_API_PORT", os.environ.get("EXTERNAL_DETECTOR_PORT", "8787")))
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    logger.info("Starting AMD FastAPI on http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
