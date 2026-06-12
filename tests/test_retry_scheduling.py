"""Retry queue must not starve when multiple lines are idle."""
from __future__ import annotations

from src.retry_queue import DialRetryQueue


def test_pop_ready_requeue_preserves_attempt_count():
    q = DialRetryQueue(max_retries=3, backoff_sec=(0.05, 2, 3))
    q.defer("+15551234567", "A", 0)
    import time
    time.sleep(0.06)
    ready = q.pop_ready()
    assert len(ready) == 1
    phone, name, attempt = ready[0]
    assert attempt == 1
    q.requeue(phone, name, attempt, 0.01)
    time.sleep(0.02)
    again = q.pop_ready()
    assert again == [("+15551234567", "A", 1)]


def test_defer_respects_max_retries():
    q = DialRetryQueue(max_retries=2, backoff_sec=(1,))
    assert q.defer("+15551234567", "A", 0) is True
    assert q.defer("+15551234567", "A", 2) is False
