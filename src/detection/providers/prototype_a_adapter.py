"""Adapter for Prototype A (GV AMD Detector).

Connects to Prototype A's FastAPI backend and consumes real-time
backend_amd_update messages over its WebSocket endpoint.

Prototype A backend is expected at:
  ws://127.0.0.1:8787/ws/amd-audio

If the backend is unreachable, returns None (fail-open).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from ..external_evidence_mapper import ExternalEvidenceMapper
from ..external_evidence import ExternalEvidence, ExternalLabel, ProviderHealth, ProviderName

logger = logging.getLogger(__name__)


class PrototypeAAdapter:
    def __init__(
        self,
        backend_url: str = "127.0.0.1",
        backend_port: int = 8787,
        timeout_ms: int = 1500,
        debug: bool = False,
    ) -> None:
        self.backend_url = backend_url
        self.backend_port = int(backend_port)
        self.timeout_ms = int(timeout_ms)
        self.debug = debug
        self._latest: Optional[ExternalEvidence] = None
        self._health: ProviderHealth = ProviderHealth.UNKNOWN
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_connect_attempt = 0.0
        self._reconnect_interval = 5.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def get_latest(self, call_id: Optional[str] = None, line_id: Optional[str] = None) -> Optional[ExternalEvidence]:
        with self._lock:
            if self._latest is None:
                return None
            ev = self._latest
            data = {
                "provider": ev.provider,
                "call_id": call_id or ev.call_id,
                "line_id": line_id or ev.line_id,
                "raw_label": ev.raw_label,
                "confidence": ev.confidence,
                "transcript": ev.transcript,
                "timestamp": ev.timestamp,
                "latency_ms": ev.latency_ms,
                "provider_health": ev.provider_health,
                "diagnostic_reason": ev.diagnostic_reason,
                "pre_answer": ev.pre_answer,
                "post_answer": ev.post_answer,
                "raw_payload": ev.raw_payload,
            }
            return ExternalEvidence(**data)

    def get_health(self) -> ProviderHealth:
        with self._lock:
            return self._health

    def _run(self) -> None:
        while not self._stop.is_set():
            self._connect_once()
            time.sleep(self._reconnect_interval)

    def _connect_once(self) -> None:
        try:
            import websockets  # type: ignore
        except Exception as exc:
            if self.debug:
                logger.debug("PrototypeA adapter: websockets library unavailable: %s", exc)
            self._set_health(ProviderHealth.ERROR)
            time.sleep(self._reconnect_interval)
            return

        ws_url = f"ws://{self.backend_url}:{self.backend_port}/ws/amd-audio"
        try:
            with websockets.connect(
                ws_url,
                close_timeout=2.0,
                ping_interval=10.0,
                ping_timeout=10.0,
            ) as ws:
                self._set_health(ProviderHealth.CONNECTED)
                if self.debug:
                    logger.info("PrototypeA adapter connected to %s", ws_url)
                while not self._stop.is_set():
                    try:
                        message = ws.recv()
                    except Exception:
                        break
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
                logger.info("PrototypeA adapter disconnected: %s", exc)

    def _handle_message(self, payload: Dict[str, Any]) -> None:
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
