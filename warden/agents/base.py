"""Base class for supervised worker agents."""

from __future__ import annotations

import random

from ..telemetry.store import AgentEvent, TelemetryStore


class WorkerAgent:
    """A worker that does a unit of business work each tick and emits telemetry.

    State machine: normal → (chaos) → rogue → (Warden) → paused → (resume) → normal.
    """

    domain = "generic"

    def __init__(self, agent_id: str, store: TelemetryStore, rng: random.Random | None = None) -> None:
        self.agent_id = agent_id
        self.store = store
        self.rng = rng or random.Random()
        self.paused = False
        self.rogue = False
        self.scenario: str | None = None
        self.actions_taken = 0

    # --- lifecycle controlled by Warden's interventions ----------------------
    def go_rogue(self, scenario: str | None = None) -> None:
        self.rogue = True
        self.scenario = scenario

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        self.rogue = False
        self.scenario = None

    @property
    def state(self) -> str:
        if self.paused:
            return "paused"
        return "rogue" if self.rogue else "healthy"

    # --- per-tick behavior ---------------------------------------------------
    def tick(self) -> None:
        if self.paused:
            self._emit(kind="heartbeat", attributes={"state": "paused"})
            return
        if self.rogue:
            self._tick_rogue()
        else:
            self._tick_normal()

    def _tick_normal(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _tick_rogue(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    # --- telemetry helpers ---------------------------------------------------
    def _emit(
        self,
        kind: str,
        *,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        value_usd: float = 0.0,
        error: bool = False,
        reversible: bool = True,
        action_type: str | None = None,
        attributes: dict | None = None,
    ) -> AgentEvent:
        if kind == "action":
            self.actions_taken += 1
        return self.store.emit(
            AgentEvent(
                tick=self.store.tick,
                agent_id=self.agent_id,
                kind=kind,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                value_usd=value_usd,
                error=error,
                reversible=reversible,
                action_type=action_type,
                attributes=attributes or {},
            )
        )
