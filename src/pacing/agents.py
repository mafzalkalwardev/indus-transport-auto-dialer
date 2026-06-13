"""Agent availability helpers for predictive pacing."""
from __future__ import annotations

import json
import os

from src.paths import DATA_DIR

AGENTS_FILE = os.path.join(DATA_DIR, "agents.json")


def load_agents() -> list[dict]:
    if not os.path.exists(AGENTS_FILE):
        return [{"id": "default", "name": "Agent", "available_for_calls": True}]
    try:
        with open(AGENTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return [{"id": "default", "name": "Agent", "available_for_calls": True}]


def available_agent_count() -> int:
    return sum(1 for agent in load_agents() if agent.get("available_for_calls", True))
