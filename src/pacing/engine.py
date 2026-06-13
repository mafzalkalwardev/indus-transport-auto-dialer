"""Predictive pacing engine for call-center dial assignment."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import median
from typing import Deque


@dataclass
class PacingMetrics:
    agents_available: int
    connect_rate: float
    abandon_rate: float
    calls_in_progress: int = 0


@dataclass
class PacingConfig:
    target_abandon_rate: float = 0.03
    min_connect_rate: float = 0.05
    max_dials_per_interval: int = 5
    pacing_interval_sec: float = 2.5
    abandon_backoff_factor: float = 0.5


@dataclass
class PredictivePacingEngine:
    config: PacingConfig = field(default_factory=PacingConfig)
    _connect_history: Deque[float] = field(default_factory=lambda: deque(maxlen=120))
    _abandon_history: Deque[float] = field(default_factory=lambda: deque(maxlen=120))

    def record_outcome(self, *, connected: bool, abandoned: bool = False) -> None:
        self._connect_history.append(1.0 if connected else 0.0)
        if connected:
            self._abandon_history.append(1.0 if abandoned else 0.0)

    def rolling_connect_rate(self) -> float:
        if not self._connect_history:
            return self.config.min_connect_rate
        return max(self.config.min_connect_rate, sum(self._connect_history) / len(self._connect_history))

    def rolling_abandon_rate(self) -> float:
        if not self._abandon_history:
            return 0.0
        return sum(self._abandon_history) / len(self._abandon_history)

    def calculate_dials_needed(self, metrics: PacingMetrics) -> int:
        agents = max(0, int(metrics.agents_available))
        in_progress = max(0, int(metrics.calls_in_progress))
        if agents <= 0:
            return 0

        connect_rate = max(
            self.config.min_connect_rate,
            metrics.connect_rate or self.rolling_connect_rate(),
        )
        abandon_rate = metrics.abandon_rate if metrics.abandon_rate > 0 else self.rolling_abandon_rate()

        target_dials = max(0, int(round(agents / connect_rate)) - in_progress)
        if abandon_rate > self.config.target_abandon_rate:
            target_dials = int(target_dials * self.config.abandon_backoff_factor)

        return max(0, min(target_dials, self.config.max_dials_per_interval, agents * 2))

    def smoothed_dials_needed(self, metrics: PacingMetrics, *, samples: list[int] | None = None) -> int:
        raw = self.calculate_dials_needed(metrics)
        history = list(samples or [])
        history.append(raw)
        if len(history) < 2:
            return raw
        return max(0, int(median(history[-5:])))
