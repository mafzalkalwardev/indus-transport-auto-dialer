"""Monitor QWebEngine slots; detect stuck or high-memory states and request restart."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.dialer_logging import log_info, log_warning


def webengine_total_memory_mb() -> int:
    """Sum RSS of QtWebEngine / Chromium helper processes (Windows)."""
    try:
        import psutil
    except ImportError:
        return 0
    total = 0
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "qtwebengine" in name or (
                "chrome" in name and "qt" in name
            ):
                mi = proc.info.get("memory_info")
                if mi:
                    total += int(mi.rss / (1024 * 1024))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


@dataclass
class _SlotHealth:
    slot_id: int
    last_heartbeat: float = field(default_factory=time.time)
    last_state_change: float = field(default_factory=time.time)
    current_state: str = "IDLE"
    calls_completed: int = 0


class SlotWatchdog(QObject):
    """Qt-thread watchdog; emits when a slot should be restarted."""

    slot_restart_requested = pyqtSignal(int, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._slots: dict[int, _SlotHealth] = {}
        self.heartbeat_timeout_sec = 45.0
        self.stuck_state_sec = 90.0
        self.memory_limit_mb = 700
        self.recycle_after_calls = 75
        self.check_interval_ms = 5000
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_all)
        self._memory_getter: Optional[Callable[[], int]] = None
        self._running = False

    def configure(
        self,
        *,
        heartbeat_timeout_sec: float = 45.0,
        stuck_state_sec: float = 90.0,
        memory_limit_mb: int = 700,
        recycle_after_calls: int = 75,
        check_interval_ms: int = 5000,
    ) -> None:
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self.stuck_state_sec = stuck_state_sec
        self.memory_limit_mb = memory_limit_mb
        self.recycle_after_calls = recycle_after_calls
        self.check_interval_ms = check_interval_ms
        if self._running:
            self._timer.setInterval(check_interval_ms)

    def set_memory_getter(self, getter: Callable[[], int]) -> None:
        self._memory_getter = getter

    def register_slot(self, slot_id: int) -> None:
        self._slots[slot_id] = _SlotHealth(slot_id=slot_id)

    def unregister_slot(self, slot_id: int) -> None:
        self._slots.pop(slot_id, None)

    def heartbeat(self, slot_id: int) -> None:
        if slot_id in self._slots:
            self._slots[slot_id].last_heartbeat = time.time()

    def record_state(self, slot_id: int, state: str) -> None:
        h = self._slots.get(slot_id)
        if not h:
            return
        if state != h.current_state:
            h.current_state = state
            h.last_state_change = time.time()
        self.heartbeat(slot_id)

    def record_call_completed(self, slot_id: int) -> None:
        h = self._slots.get(slot_id)
        if h:
            h.calls_completed += 1

    def reset_call_counter(self, slot_id: int) -> None:
        h = self._slots.get(slot_id)
        if h:
            h.calls_completed = 0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._timer.setInterval(self.check_interval_ms)
        self._timer.start()

    def stop(self) -> None:
        self._running = False
        self._timer.stop()

    def _check_all(self) -> None:
        now = time.time()
        mem_mb = self._memory_getter() if self._memory_getter else webengine_total_memory_mb()
        mem_high = mem_mb > self.memory_limit_mb if mem_mb > 0 else False

        for slot_id, h in list(self._slots.items()):
            if h.current_state in ("IDLE", "ENDED", "VOICEMAIL", "NO_ANSWER", "FAILED"):
                if mem_high and h.calls_completed > 10:
                    self._request_restart(
                        slot_id,
                        f"WebEngine memory high ({mem_mb} MB)",
                    )
                elif h.calls_completed >= self.recycle_after_calls:
                    self._request_restart(
                        slot_id,
                        f"recycle after {h.calls_completed} calls",
                    )
                continue

            elapsed_hb = now - h.last_heartbeat
            if elapsed_hb > self.heartbeat_timeout_sec:
                self._request_restart(
                    slot_id,
                    f"no heartbeat for {elapsed_hb:.0f}s (state={h.current_state})",
                )
                continue

            if h.current_state in ("DIALING", "RINGING", "CONNECTED"):
                elapsed_st = now - h.last_state_change
                if elapsed_st > self.stuck_state_sec:
                    self._request_restart(
                        slot_id,
                        f"stuck in {h.current_state} for {elapsed_st:.0f}s",
                    )

    def _request_restart(self, slot_id: int, reason: str) -> None:
        log_warning(f"Watchdog slot {slot_id}: {reason}")
        self.reset_call_counter(slot_id)
        h = self._slots.get(slot_id)
        if h:
            h.last_heartbeat = time.time()
            h.last_state_change = time.time()
        self.slot_restart_requested.emit(slot_id, reason)
