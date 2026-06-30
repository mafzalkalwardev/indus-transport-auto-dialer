"""Route live human answers to a single agent audio line.

Power-dial campaigns may have many slots ringing at once. Only one picked-up
call should be audible to the agent; additional live answers wait in queue
until the agent releases the active line.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PickupRole = Literal["live", "queued"]


@dataclass
class AgentCallRouter:
    """Track which slot owns agent speakers/mic and which answers are waiting."""

    live_slot: int | None = None
    waiting: list[int] = field(default_factory=list)

    def on_pickup(self, slot_id: int) -> PickupRole:
        """Register a human/live answer on *slot_id*."""
        if self.live_slot == slot_id:
            return "live"
        if slot_id in self.waiting:
            return "queued"
        if self.live_slot is None:
            self.live_slot = slot_id
            return "live"
        self.waiting.append(slot_id)
        return "queued"

    def release_agent(self, slot_id: int) -> int | None:
        """Agent finished on *slot_id*; promote the next waiting answer if any."""
        if self.live_slot == slot_id:
            self.live_slot = None
        else:
            self._drop_waiting(slot_id)
            return None
        return self._promote_next()

    def remove_slot(self, slot_id: int) -> int | None:
        """Call ended on *slot_id* (hangup, voicemail, no-answer, etc.)."""
        if self.live_slot == slot_id:
            self.live_slot = None
        self._drop_waiting(slot_id)
        return self._promote_next()

    def reset(self) -> None:
        self.live_slot = None
        self.waiting.clear()

    def agent_ears_slot(self) -> int | None:
        return self.live_slot

    def is_live(self, slot_id: int) -> bool:
        return self.live_slot == slot_id

    def is_queued(self, slot_id: int) -> bool:
        return slot_id in self.waiting

    def waiting_count(self) -> int:
        return len(self.waiting)

    def queued_slots(self) -> list[int]:
        return list(self.waiting)

    def _drop_waiting(self, slot_id: int) -> None:
        self.waiting = [s for s in self.waiting if s != slot_id]

    def _promote_next(self) -> int | None:
        while self.waiting:
            slot_id = self.waiting.pop(0)
            if self.live_slot is None:
                self.live_slot = slot_id
                return slot_id
        return None
