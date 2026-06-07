"""Concrete worker agents for the payments / e-commerce ops demo domain.

Each has a benign "normal" behavior and a realistic failure mode the chaos
injector can flip on. The dollar amounts are what make a rogue agent legible:
when RefundAgent starts approving $600 refunds in a loop, that is money leaving
the building until something stops it.

Scaling to N agents
-------------------
The fleet is built from a config file (`warden/agents/fleet_config.json` by
default), not from a hardcoded list. Adding a new worker is:

    1. Write a class that subclasses `WorkerAgent` and decorate it with
       `@register_worker` (or with an explicit type name:
       `@register_worker("MyAgent")`).
    2. Add a row to `fleet_config.json`:
       `{"id": "my-agent", "type": "MyAgent"}`.

No supervisor changes. The loop, Dynatrace MCP sensing, Gemini diagnosis, the
policy gate, and the intervention layer are all parameterized by `agent.id`,
not by worker type. The three demo agents below are seeds for a focused demo,
not a wall in the architecture. In production the JSON file is swapped for a
service registry, a config store, or a Secret Manager URL.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Callable

from ..telemetry.store import TelemetryStore
from .base import WorkerAgent
from .fleet import Fleet

# WORKER_REGISTRY is the source of truth for "what worker types can the fleet
# spin up". Each WorkerAgent subclass registers its type name here at import
# time via the @register_worker decorator. The fleet loader reads JSON config,
# looks up the type name in this registry, and instantiates.
WORKER_REGISTRY: dict[str, type[WorkerAgent]] = {}


def register_worker(arg=None) -> Callable[[type[WorkerAgent]], type[WorkerAgent]] | type[WorkerAgent]:
    """Decorator that adds a `WorkerAgent` subclass to `WORKER_REGISTRY`.

    Usage::

        @register_worker
        class RefundAgent(WorkerAgent): ...

        @register_worker("SomeOtherName")
        class PaymentsAgent(WorkerAgent): ...

    Re-registration is allowed (last writer wins) so reloads in a notebook do
    not blow up. Type collisions across modules are the caller's responsibility.
    """
    if isinstance(arg, type) and issubclass(arg, WorkerAgent):
        WORKER_REGISTRY[arg.__name__] = arg
        return arg

    type_name = arg

    def _wrap(cls: type[WorkerAgent]) -> type[WorkerAgent]:
        WORKER_REGISTRY[type_name or cls.__name__] = cls
        return cls

    return _wrap


@register_worker
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


@register_worker
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
        # Sets near-zero prices: each is a large potential revenue loss.
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


@register_worker
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


_DEFAULT_FLEET_CONFIG = Path(__file__).with_name("fleet_config.json")


def _fallback_seed() -> list[dict]:
    """The seed used when no fleet_config.json is available.

    This is the same three demo agents the project shipped with before config
    loading existed. It is the safety net that guarantees the dashboard never
    boots with an empty fleet even if the config file is renamed or missing.
    """
    return [
        {"id": "refund-agent",    "type": "RefundAgent"},
        {"id": "pricing-agent",   "type": "PricingAgent"},
        {"id": "inventory-agent", "type": "InventoryAgent"},
    ]


def load_fleet_from_config(
    store: TelemetryStore,
    config_path: str | os.PathLike[str] | None = None,
    seed: int = 7,
) -> Fleet:
    """Build a `Fleet` from a JSON config file (with a hardcoded fallback).

    The config file format::

        {"fleet": [{"id": "<agent_id>", "type": "<class_name>"}, ...]}

    `type` is looked up in `WORKER_REGISTRY`. Unknown types are skipped with a
    printed warning rather than crashing, so a typo cannot take the dashboard
    down. The RNG seed is split across workers deterministically so that the
    same `seed` produces the same per-agent behavior regardless of fleet size.
    """
    path = Path(config_path) if config_path else _DEFAULT_FLEET_CONFIG
    entries: list[dict]
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("fleet", []) or _fallback_seed()
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warden] fleet config {path} unreadable ({exc}); falling back to default seed")
            entries = _fallback_seed()
    else:
        entries = _fallback_seed()

    rng = random.Random(seed)
    fleet = Fleet(store)
    for entry in entries:
        agent_id = entry.get("id")
        type_name = entry.get("type")
        if not agent_id or not type_name:
            continue
        cls = WORKER_REGISTRY.get(type_name)
        if cls is None:
            print(f"[warden] unknown worker type {type_name!r} for agent {agent_id!r}; skipping")
            continue
        fleet.add(cls(agent_id, store, random.Random(rng.random())))
    return fleet


def default_fleet(store: TelemetryStore, seed: int = 7) -> Fleet:
    """Backward-compatible alias kept for scripts/bench.py, scripts/demo.py,
    scripts/otel_smoke.py, and the existing tests. New callers should use
    `load_fleet_from_config` directly so the config-driven nature of the
    fleet is obvious at the call site.
    """
    return load_fleet_from_config(store, seed=seed)
