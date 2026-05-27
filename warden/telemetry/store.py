"""In-memory telemetry store + the action ledger Warden can roll back."""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

_action_seq = itertools.count(1)


@dataclass
class AgentEvent:
    """One telemetry signal emitted by a worker agent on a tick."""

    tick: int
    agent_id: str
    kind: str  # "action" | "error" | "heartbeat"
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    value_usd: float = 0.0  # business value moved (e.g. refund amount)
    error: bool = False
    reversible: bool = True
    action_type: str | None = None
    action_id: int | None = None
    rolled_back: bool = False
    attributes: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        """Flat dict shaped like a Dynatrace record (what execute_dql returns)."""
        return {
            "timestamp": self.tick,
            "dt.entity.agent": self.agent_id,
            "event.kind": self.kind,
            "action.type": self.action_type,
            "action.id": self.action_id,
            "duration.ms": round(self.latency_ms, 1),
            "cost.usd": round(self.cost_usd, 2),
            "value.usd": round(self.value_usd, 2),
            "is.error": self.error,
            "reversible": self.reversible,
            "rolled.back": self.rolled_back,
            **{f"attr.{k}": v for k, v in self.attributes.items()},
        }


class TelemetryStore:
    """Rolling window of agent events. Doubles as the reversible action ledger."""

    def __init__(self, maxlen: int = 5000) -> None:
        self._events: deque[AgentEvent] = deque(maxlen=maxlen)
        self.tick: int = 0

    # --- ingestion -----------------------------------------------------------
    def advance(self) -> int:
        self.tick += 1
        return self.tick

    def emit(self, event: AgentEvent) -> AgentEvent:
        if event.kind == "action" and event.action_id is None:
            event.action_id = next(_action_seq)
        self._events.append(event)
        return event

    # --- queries (used by the mock Dynatrace tools) --------------------------
    def recent(self, window: int | None = None) -> list[AgentEvent]:
        if window is None:
            return list(self._events)
        lo = self.tick - window
        return [e for e in self._events if e.tick > lo]

    def by_agent(self, agent_id: str, window: int | None = None) -> list[AgentEvent]:
        return [e for e in self.recent(window) if e.agent_id == agent_id]

    def agents(self) -> list[str]:
        return sorted({e.agent_id for e in self._events})

    def actions(self, agent_id: str, since_tick: int = 0) -> list[AgentEvent]:
        return [
            e
            for e in self._events
            if e.agent_id == agent_id and e.kind == "action" and e.tick >= since_tick
        ]

    def mark_rolled_back(self, action_ids: Iterable[int]) -> float:
        """Reverse the named actions; return the total business value recovered."""
        wanted = set(action_ids)
        recovered = 0.0
        for e in self._events:
            if e.action_id in wanted and not e.rolled_back:
                e.rolled_back = True
                recovered += e.value_usd
        return recovered
