"""Chaos injection: turn a healthy worker agent into a rogue one on demand.

This is what makes the demo dramatic and the impact measurable — we know exactly
when the rogue behavior started, so we can prove how fast Warden caught it.
"""

from .injector import SCENARIOS, ChaosInjector

__all__ = ["ChaosInjector", "SCENARIOS"]
