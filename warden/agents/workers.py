"""Concrete worker agents for the payments / e-commerce ops demo domain.

Each has a benign "normal" behavior and a realistic failure mode the chaos
injector can flip on. The dollar amounts are what make a rogue agent legible:
when RefundAgent starts approving $600 refunds in a loop, that is money leaving
the building until something stops it.
"""

from __future__ import annotations

import random

from ..telemetry.store import TelemetryStore
from .base import WorkerAgent
from .fleet import Fleet


class RefundAgent(WorkerAgent):
    """Approves customer refund requests. Rogue mode = fraudulent refund loop."""

    domain = "payments"

    def _tick_normal(self) -> None:
        if self.rng.random() < 0.6:
            amount = round(self.rng.uniform(10, 80), 2)
            self._emit(
                "action",
                action_type="approve_refund",
                latency_ms=self.rng.uniform(120, 300),
                cost_usd=0.002,
                value_usd=amount,
                reversible=True,
                attributes={"order_id": f"ord_{self.rng.randint(10000, 99999)}", "fraud_score": round(self.rng.uniform(0, 0.2), 2)},
            )
        else:
            self._emit("heartbeat", attributes={"state": "idle"})

    def _tick_rogue(self) -> None:
        # Approves a burst of large, high-fraud-score, irreversible refunds.
        for _ in range(self.rng.randint(2, 4)):
            amount = round(self.rng.uniform(300, 900), 2)
            self._emit(
                "action",
                action_type="approve_refund",
                latency_ms=self.rng.uniform(40, 90),  # suspiciously fast
                cost_usd=0.002,
                value_usd=amount,
                reversible=False,  # money wired out
                attributes={"order_id": f"ord_{self.rng.randint(10000, 99999)}", "fraud_score": round(self.rng.uniform(0.7, 0.99), 2)},
            )


class PricingAgent(WorkerAgent):
    """Adjusts product prices within guardrails. Rogue mode = catastrophic mispricing."""

    domain = "merchandising"

    def _tick_normal(self) -> None:
        if self.rng.random() < 0.4:
            self._emit(
                "action",
                action_type="adjust_price",
                latency_ms=self.rng.uniform(80, 200),
                cost_usd=0.001,
                value_usd=round(self.rng.uniform(5, 40), 2),
                reversible=True,
                attributes={"sku": f"sku_{self.rng.randint(100, 999)}", "delta_pct": round(self.rng.uniform(-3, 3), 1)},
            )
        else:
            self._emit("heartbeat", attributes={"state": "idle"})

    def _tick_rogue(self) -> None:
        # Sets near-zero prices — each is a large potential revenue loss.
        self._emit(
            "action",
            action_type="adjust_price",
            latency_ms=self.rng.uniform(60, 120),
            cost_usd=0.001,
            value_usd=round(self.rng.uniform(200, 500), 2),
            reversible=True,
            error=self.rng.random() < 0.3,
            attributes={"sku": f"sku_{self.rng.randint(100, 999)}", "delta_pct": -99.0},
        )


class InventoryAgent(WorkerAgent):
    """Reorders stock from suppliers. Rogue mode = runaway over-ordering (cost spike)."""

    domain = "supply_chain"

    def _tick_normal(self) -> None:
        if self.rng.random() < 0.3:
            self._emit(
                "action",
                action_type="reorder_stock",
                latency_ms=self.rng.uniform(150, 400),
                cost_usd=round(self.rng.uniform(0.5, 3), 2),
                value_usd=round(self.rng.uniform(20, 120), 2),
                reversible=True,
                attributes={"sku": f"sku_{self.rng.randint(100, 999)}", "qty": self.rng.randint(5, 50)},
            )
        else:
            self._emit("heartbeat", attributes={"state": "idle"})

    def _tick_rogue(self) -> None:
        self._emit(
            "action",
            action_type="reorder_stock",
            latency_ms=self.rng.uniform(150, 400),
            cost_usd=round(self.rng.uniform(15, 40), 2),  # huge purchase-order cost
            value_usd=round(self.rng.uniform(80, 200), 2),
            reversible=True,
            attributes={"sku": f"sku_{self.rng.randint(100, 999)}", "qty": self.rng.randint(5000, 20000)},
        )


def default_fleet(store: TelemetryStore, seed: int = 7) -> Fleet:
    """The standard three-agent demo fleet with a reproducible RNG."""
    rng = random.Random(seed)
    fleet = Fleet(store)
    fleet.add(RefundAgent("refund-agent", store, random.Random(rng.random())))
    fleet.add(PricingAgent("pricing-agent", store, random.Random(rng.random())))
    fleet.add(InventoryAgent("inventory-agent", store, random.Random(rng.random())))
    return fleet
