"""Inject rogue-agent scenarios into the fleet."""

from __future__ import annotations

from dataclasses import dataclass

from ..agents.fleet import Fleet


@dataclass(frozen=True)
class Scenario:
    key: str
    agent_id: str
    label: str
    description: str


# Catalog of realistic failure modes a rogue production agent can exhibit.
SCENARIOS: dict[str, Scenario] = {
    "refund_fraud_loop": Scenario(
        "refund_fraud_loop",
        "refund-agent",
        "Fraudulent refund loop",
        "RefundAgent begins approving large, high-fraud-score, irreversible refunds in bursts.",
    ),
    "price_collapse": Scenario(
        "price_collapse",
        "pricing-agent",
        "Catastrophic mispricing",
        "PricingAgent slashes prices ~99%, risking massive revenue loss.",
    ),
    "inventory_overorder": Scenario(
        "inventory_overorder",
        "inventory-agent",
        "Runaway over-ordering",
        "InventoryAgent places enormous purchase orders, spiking spend.",
    ),
}


class ChaosInjector:
    def __init__(self, fleet: Fleet) -> None:
        self.fleet = fleet
        self.injected: list[dict] = []

    def inject(self, scenario_key: str, at_tick: int) -> Scenario:
        if scenario_key not in SCENARIOS:
            raise KeyError(f"unknown scenario {scenario_key!r}; choose from {list(SCENARIOS)}")
        scenario = SCENARIOS[scenario_key]
        agent = self.fleet.get(scenario.agent_id)
        if agent is None:
            raise KeyError(f"fleet has no agent {scenario.agent_id!r}")
        agent.go_rogue(scenario.key)
        record = {"scenario": scenario.key, "agent_id": scenario.agent_id, "tick": at_tick}
        self.injected.append(record)
        return scenario

    def onset_tick(self, agent_id: str) -> int | None:
        """Tick at which the given agent first went rogue (for MTTD math)."""
        for rec in self.injected:
            if rec["agent_id"] == agent_id:
                return rec["tick"]
        return None
