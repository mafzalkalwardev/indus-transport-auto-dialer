"""Adapter for Prototype B (Google Voice Call Detection Prototype).

Prototype B is treated as an offline/local fallback/testing evidence provider.
It can replay fixture payloads for deterministic tests, or optionally poll
a configurable backend endpoint when running in live mode.

Defaults to offline / empty until fixtures or backend are provided.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ..external_evidence import ExternalEvidence, ExternalLabel, ProviderHealth, ProviderName
from ..external_evidence_mapper import ExternalEvidenceMapper

logger = logging.getLogger(__name__)


class PrototypeBAdapter:
    def __init__(
        self,
        backend_url: str = "http://127.0.0.1:3100",
        timeout_ms: int = 1500,
        debug: bool = False,
        fixtures: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.timeout_ms = int(timeout_ms)
        self.debug = debug
        self._fixtures = fixtures or []
        self._fixture_index = 0
        self._latest: Optional[ExternalEvidence] = None
        self._health: ProviderHealth = ProviderHealth.UNKNOWN
        self._lock = threading.Lock()
        self._fixture_mode = bool(self._fixtures)

    def start(self) -> None:
        if self._fixture_mode:
            self._load_fixture()
        else:
            self._probe_backend()

    def stop(self) -> None:
        pass

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

    def load_fixture(self, fixture: Dict[str, Any]) -> None:
        """Manually inject a simulated payload (used by tests and offline replay)."""
        evidence = ExternalEvidenceMapper.map_prototype_b(
            raw_label=str(fixture.get("classification", fixture.get("label", "unknown"))),
            confidence=float(fixture.get("confidence", 0.0)),
            transcript=str(fixture.get("transcript", "")),
            timestamp=float(fixture.get("timestamp", time.time())),
            latency_ms=float(fixture.get("latency_ms", 0.0)),
            provider_health="connected",
            diagnostic_reason=str(fixture.get("reason", "")),
            raw_payload=fixture,
        )
        with self._lock:
            if fixture not in self._fixtures:
                self._fixtures.append(fixture)
            self._latest = evidence
            self._health = ProviderHealth.CONNECTED

    def advance_fixture(self) -> None:
        if not self._fixtures:
            return
        with self._lock:
            self._fixture_index = (self._fixture_index + 1) % len(self._fixtures)
        self._load_fixture()

    def _load_fixture(self) -> None:
        if not self._fixtures:
            self._set_health(ProviderHealth.DISCONNECTED)
            return
        idx = self._fixture_index % len(self._fixtures)
        self.load_fixture(self._fixtures[idx])
        with self._lock:
            self._fixture_index = idx + 1

    def _probe_backend(self) -> None:
        try:
            import urllib.request
            import urllib.error
        except Exception as exc:
            if self.debug:
                logger.debug("PrototypeB adapter: urllib unavailable: %s", exc)
            self._set_health(ProviderHealth.ERROR)
            return

        url = f"{self.backend_url}/health"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout_ms / 1000.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                connected = bool(body.get("ok") or body.get("status") == "ok")
                self._set_health(ProviderHealth.CONNECTED if connected else ProviderHealth.ERROR)
        except Exception as exc:
            self._set_health(ProviderHealth.DISCONNECTED)
            if self.debug:
                logger.info("PrototypeB adapter backend probe failed: %s", exc)

    def _set_health(self, health: ProviderHealth) -> None:
        with self._lock:
            self._health = health
