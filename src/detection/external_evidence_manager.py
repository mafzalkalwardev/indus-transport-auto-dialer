"""Manager for external evidence providers.

Coordinates Prototype A and Prototype B adapters, exposes the latest
evidence to the detector, and emits diagnostics for the UI/logs.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from .external_evidence import ExternalEvidence, ProviderHealth, ProviderName
from .providers.prototype_a_adapter import PrototypeAAdapter
from .providers.prototype_b_adapter import PrototypeBAdapter

logger = logging.getLogger(__name__)


class ExternalEvidenceManager:
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._enabled = bool(self.config.get("external_detector_enabled", False))
        self._mode = str(self.config.get("external_detector_mode", "prototype_a")).lower()
        self._merge_mode = str(self.config.get("external_detector_merge_mode", "evidence_only")).lower()
        self._timeout_ms = int(self.config.get("external_detector_timeout_ms", 1500))
        self._fail_open = bool(self.config.get("external_detector_fail_open", True))
        self._debug = bool(self.config.get("external_detector_debug", True))

        self._lock = threading.Lock()
        self._latest: Optional[ExternalEvidence] = None
        self._provider: Optional[PrototypeAAdapter | PrototypeBAdapter] = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def initialize(self) -> None:
        if self._initialized:
            return
        if not self._enabled:
            return
        try:
            if self._mode == "prototype_b":
                self._provider = PrototypeBAdapter(
                    timeout_ms=self._timeout_ms,
                    debug=self._debug,
                )
            else:
                backend_url = str(self.config.get("external_detector_backend_url", "127.0.0.1"))
                backend_port = int(self.config.get("external_detector_backend_port", 8787))
                self._provider = PrototypeAAdapter(
                    backend_url=backend_url,
                    backend_port=backend_port,
                    timeout_ms=self._timeout_ms,
                    debug=self._debug,
                )
            self._provider.start()
            self._initialized = True
            if self._debug:
                logger.info("ExternalEvidenceManager initialized in mode=%s", self._mode)
        except Exception as exc:
            logger.warning("ExternalEvidenceManager init failed: %s", exc)
            self._provider = None

    def shutdown(self) -> None:
        if self._provider:
            try:
                self._provider.stop()
            except Exception:
                pass
            self._provider = None
        self._initialized = False

    def get_latest(
        self,
        call_id: Optional[str] = None,
        line_id: Optional[str] = None,
    ) -> Optional[ExternalEvidence]:
        if not self._enabled or self._provider is None:
            return None
        try:
            return self._provider.get_latest(call_id=call_id, line_id=line_id)
        except Exception as exc:
            if self._debug:
                logger.debug("get_latest failed: %s", exc)
            return None

    def get_health(self) -> ProviderHealth:
        if not self._enabled or self._provider is None:
            return ProviderHealth.UNKNOWN
        try:
            return self._provider.get_health()
        except Exception:
            return ProviderHealth.UNKNOWN

    def get_diagnostics(self) -> Dict[str, Any]:
        health = self.get_health()
        latest = self.get_latest()
        return {
            "external_detector_enabled": self._enabled,
            "external_detector_mode": self._mode,
            "external_detector_merge_mode": self._merge_mode,
            "external_detector_fail_open": self._fail_open,
            "external_provider_health": health.value,
            "external_last_label": (latest.raw_label if latest else "none"),
            "external_confidence": round(latest.confidence, 3) if latest else 0.0,
            "external_transcript": (latest.transcript[:120] if latest else ""),
            "external_latency_ms": latest.latency_ms if latest else 0.0,
            "external_diagnostic_reason": (latest.diagnostic_reason if latest else ""),
        }

    def update(self, call_id: Optional[str] = None, line_id: Optional[str] = None) -> Optional[ExternalEvidence]:
        """Refresh latest evidence and store for this call."""
        if not self._enabled:
            return None
        try:
            latest = self.get_latest(call_id=call_id, line_id=line_id)
            with self._lock:
                self._latest = latest
            return latest
        except Exception as exc:
            if self._debug:
                logger.debug("update failed: %s", exc)
            return None

    def load_fixture(self, fixture: Dict[str, Any]) -> None:
        """Inject a simulated payload (testing only)."""
        if self._provider and hasattr(self._provider, "load_fixture"):
            try:
                self._provider.load_fixture(fixture)
            except Exception as exc:
                if self._debug:
                    logger.debug("load_fixture failed: %s", exc)

    def advance_fixture(self) -> None:
        if self._provider and hasattr(self._provider, "advance_fixture"):
            try:
                self._provider.advance_fixture()
            except Exception as exc:
                if self._debug:
                    logger.debug("advance_fixture failed: %s", exc)
