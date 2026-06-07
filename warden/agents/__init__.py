"""The subjects of supervision: a small fleet of autonomous worker agents.

These stand in for real production agents (Gemini/ADK agents in LIVE mode). Each
emits OpenTelemetry-style signals every tick. Warden never trusts them; it only
observes them through Dynatrace.
"""

from .base import WorkerAgent
from .fleet import Fleet
from .workers import (
    WORKER_REGISTRY,
    InventoryAgent,
    PricingAgent,
    RefundAgent,
    default_fleet,
    load_fleet_from_config,
    register_worker,
)

__all__ = [
    "WorkerAgent",
    "Fleet",
    "RefundAgent",
    "PricingAgent",
    "InventoryAgent",
    "WORKER_REGISTRY",
    "register_worker",
    "load_fleet_from_config",
    "default_fleet",
]
