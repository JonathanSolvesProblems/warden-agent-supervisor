"""The fleet: advances the simulation clock and ticks every worker agent."""

from __future__ import annotations

from ..telemetry.store import TelemetryStore
from .base import WorkerAgent


class Fleet:
    def __init__(self, store: TelemetryStore) -> None:
        self.store = store
        self.agents: dict[str, WorkerAgent] = {}

    def add(self, agent: WorkerAgent) -> WorkerAgent:
        self.agents[agent.agent_id] = agent
        return agent

    def get(self, agent_id: str) -> WorkerAgent | None:
        return self.agents.get(agent_id)

    def tick(self) -> int:
        """Advance one simulated tick: bump the clock, then run every agent."""
        self.store.advance()
        for agent in self.agents.values():
            agent.tick()
        return self.store.tick

    def states(self) -> dict[str, str]:
        return {aid: a.state for aid, a in self.agents.items()}
