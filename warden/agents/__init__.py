"""The subjects of supervision: a small fleet of autonomous worker agents.

These stand in for real production agents (Gemini/ADK agents in LIVE mode). Each
emits OpenTelemetry-style signals every tick. Warden never trusts them; it only
observes them through Dynatrace.
"""

from .base import WorkerAgent
from .fleet import Fleet
from .workers import InventoryAgent, PricingAgent, RefundAgent, default_fleet

__all__ = [
    "WorkerAgent",
    "Fleet",
    "RefundAgent",
    "PricingAgent",
    "InventoryAgent",
    "default_fleet",
]
