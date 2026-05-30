"""Chaos injection: turn a healthy worker agent into a rogue one on demand.

This is what makes the demo dramatic and the impact measurable. The chaos
injector logs the exact tick rogue behavior started, so the harness can prove
how fast Warden caught it.
"""

from .injector import SCENARIOS, ChaosInjector

__all__ = ["ChaosInjector", "SCENARIOS"]
