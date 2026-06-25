"""Stream WASAPI PCM to Prototype A FastAPI and collect AMD updates."""
from __future__ import annotations

import json
import logging
import struct
import threading
import time
from typing import Any, Optional

from ..external_evidence import ExternalEvidence, ProviderHealth, ProviderName
from ..external_evidence_mapper import ExternalEvidenceMapper

logger = logging.getLogger(__name__)


class LocalAmdPublisher:
    """Bidirectional websocket client for /ws/amd-audio."""

    def __init__(
        self,
        *,
        backend_url: str = "127.0.0.1",
        backend_port: int = 8787,
        debug: bool = False,
    ) -> None:
        self.backend_url = backend_url
        self.backend_port = int(backend_port)
        self.debug = debug
        self._lock = threading.Lock()
        self._latest: Optional[ExternalEvidence] = None
        self._health = ProviderHealth.UNKNOWN
        self._thread: Optional[threading.Thread] = None
        self._send_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pcm_queue: list[bytes] = []
        self._active = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._active = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._active = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._send_thread = None
        with self._lock:
            self._pcm_queue.clear()

    def push_pcm(self, pcm_mono: list[float], *, sample_rate: int = 16000) -> None:
        if not self._active or not pcm_mono:
            return
        ints = []
        for sample in pcm_mono:
            value = max(-1.0, min(1.0, float(sample)))
            ints.append(int(value * 32767.0))
        payload = struct.pack(f"<{len(ints)}h", *ints)
        with self._lock:
            self._pcm_queue.append(payload)
            if len(self._pcm_queue) > 8:
                self._pcm_queue = self._pcm_queue[-8:]

    def get_latest(self) -> Optional[ExternalEvidence]:
        with self._lock:
            return self._latest

    def get_health(self) -> ProviderHealth:
        with self._lock:
            return self._health

    def _run(self) -> None:
        try:
            import websockets  # type: ignore
        except Exception as exc:
            if self.debug:
                logger.debug("LocalAmdPublisher: websockets unavailable: %s", exc)
            self._set_health(ProviderHealth.ERROR)
            return

        ws_url = f"ws://{self.backend_url}:{self.backend_port}/ws/amd-audio"
        while not self._stop.is_set():
            try:
                with websockets.connect(
                    ws_url,
                    close_timeout=2.0,
                    ping_interval=10.0,
                    ping_timeout=10.0,
                ) as ws:
                    self._set_health(ProviderHealth.CONNECTED)
                    if self.debug:
                        logger.info("LocalAmdPublisher connected to %s", ws_url)
                    self._send_thread = threading.Thread(
                        target=self._send_loop,
                        args=(ws,),
                        daemon=True,
                    )
                    self._send_thread.start()
                    while not self._stop.is_set():
                        try:
                            message = ws.recv(timeout=1.0)
                        except Exception:
                            continue
                        if isinstance(message, bytes):
                            continue
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        self._handle_message(payload)
            except Exception as exc:
                self._set_health(ProviderHealth.DISCONNECTED)
                if self.debug:
                    logger.info("LocalAmdPublisher disconnected: %s", exc)
                time.sleep(2.0)

    def _send_loop(self, ws: Any) -> None:
        while not self._stop.is_set():
            chunk = None
            with self._lock:
                if self._pcm_queue:
                    chunk = self._pcm_queue.pop(0)
            if chunk is None:
                time.sleep(0.05)
                continue
            try:
                ws.send(chunk)
            except Exception:
                break

    def _handle_message(self, payload: dict[str, Any]) -> None:
        msg_type = str(payload.get("type") or "").lower()
        if msg_type not in {"backend_amd_update", "gv_backend_amd_update"}:
            return
        raw_label = str(payload.get("finalAmdState") or payload.get("final_state") or "unknown")
        confidence = float(payload.get("confidence") or 0.0)
        transcript = str(payload.get("transcript") or payload.get("partial") or "")
        latency = float(payload.get("latency_ms") or 0.0)
        reason = str(payload.get("reason") or payload.get("backendLastError") or "")
        connected = bool(payload.get("backendConnected") or payload.get("deepgramConnected"))
        health = ProviderHealth.CONNECTED if connected else ProviderHealth.DISCONNECTED
        evidence = ExternalEvidenceMapper.map_prototype_a(
            raw_label=raw_label,
            confidence=confidence,
            transcript=transcript,
            timestamp=time.time(),
            latency_ms=latency,
            provider_health=health.value,
            diagnostic_reason=reason,
            raw_payload=payload,
        )
        with self._lock:
            self._latest = evidence
            self._health = health

    def _set_health(self, health: ProviderHealth) -> None:
        with self._lock:
            self._health = health


def classify_transcript_remote(
    transcript: str,
    *,
    backend_url: str = "127.0.0.1",
    backend_port: int = 8787,
    timeout_sec: float = 2.0,
) -> dict[str, Any] | None:
    """Optional LLM/rules fallback via Prototype A HTTP endpoint."""
    if not transcript.strip():
        return None
    try:
        import urllib.error
        import urllib.request

        url = f"http://{backend_url}:{backend_port}/classify-transcript"
        body = json.dumps({"transcript": transcript[:2000]}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
