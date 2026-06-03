"""Per-number retry with exponential backoff during power dial campaigns."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RetryEntry:
    phone: str
    name: str
    attempt: int
    ready_at: float


class DialRetryQueue:
    """Holds numbers waiting for retry; does not block the dialer timer."""

    def __init__(self, max_retries: int = 3,
                 backoff_sec: tuple[float, ...] = (5.0, 15.0, 45.0)):
        self.max_retries = max(1, max_retries)
        self.backoff_sec = backoff_sec
        self._queue: list[RetryEntry] = []

    def clear(self) -> None:
        self._queue.clear()

    def defer(self, phone: str, name: str, attempt: int) -> bool:
        """
        Schedule a retry. attempt is how many dials have already failed (0-based).
        Returns False if max retries exhausted.
        """
        if attempt >= self.max_retries:
            return False
        idx = min(attempt, len(self.backoff_sec) - 1)
        wait = self.backoff_sec[idx]
        self._queue.append(RetryEntry(
            phone=phone,
            name=name,
            attempt=attempt + 1,
            ready_at=time.time() + wait,
        ))
        return True

    def pop_ready(self) -> list[tuple[str, str, int]]:
        """Return (phone, name, attempt) for entries ready to dial now."""
        now = time.time()
        ready: list[tuple[str, str, int]] = []
        remaining: list[RetryEntry] = []
        for entry in self._queue:
            if entry.ready_at <= now:
                ready.append((entry.phone, entry.name, entry.attempt))
            else:
                remaining.append(entry)
        self._queue = remaining
        return ready

    def requeue(self, phone: str, name: str, attempt: int,
                delay_sec: float = 2.0) -> None:
        """Put a number back when no line was ready to dial it yet."""
        self._queue.append(RetryEntry(
            phone=phone,
            name=name,
            attempt=attempt,
            ready_at=time.time() + delay_sec,
        ))

    def pending_count(self) -> int:
        return len(self._queue)
