"""Unit tests for the config-driven fleet loader.

Covers:
- WORKER_REGISTRY contains the three built-in worker types at import time.
- load_fleet_from_config reads JSON and instantiates the right classes.
- Missing config file falls back to the hardcoded seed (3 demo agents).
- Malformed JSON also falls back, with a printed warning, never crashing.
- Custom worker types registered via @register_worker compose with the loader.
- Unknown worker types in the config are skipped, not fatal.

Run:
    python -m unittest tests.test_fleet_config -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from warden.agents import (
    WORKER_REGISTRY,
    InventoryAgent,
    PricingAgent,
    RefundAgent,
    WorkerAgent,
    load_fleet_from_config,
    register_worker,
)
from warden.telemetry.store import TelemetryStore


class FleetConfigTests(unittest.TestCase):
    def test_registry_has_three_builtins(self):
        for name, cls in [
            ("RefundAgent", RefundAgent),
            ("PricingAgent", PricingAgent),
            ("InventoryAgent", InventoryAgent),
        ]:
            self.assertIn(name, WORKER_REGISTRY)
            self.assertIs(WORKER_REGISTRY[name], cls)

    def test_default_config_loads_three_agents(self):
        store = TelemetryStore()
        fleet = load_fleet_from_config(store, seed=7)
        self.assertEqual(set(fleet.agents.keys()),
                         {"refund-agent", "pricing-agent", "inventory-agent"})
        self.assertIsInstance(fleet.agents["refund-agent"], RefundAgent)
        self.assertIsInstance(fleet.agents["pricing-agent"], PricingAgent)
        self.assertIsInstance(fleet.agents["inventory-agent"], InventoryAgent)

    def test_missing_file_falls_back_to_seed(self):
        store = TelemetryStore()
        fleet = load_fleet_from_config(store, config_path="/no/such/file.json", seed=7)
        self.assertEqual(len(fleet.agents), 3)
        self.assertIn("refund-agent", fleet.agents)

    def test_malformed_json_falls_back_to_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "fleet.json"
            bad.write_text("this is not valid json {{", encoding="utf-8")
            store = TelemetryStore()
            fleet = load_fleet_from_config(store, config_path=bad, seed=7)
            self.assertEqual(len(fleet.agents), 3)

    def test_unknown_type_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "fleet.json"
            cfg.write_text(json.dumps({
                "fleet": [
                    {"id": "refund-agent",  "type": "RefundAgent"},
                    {"id": "ghost-agent",   "type": "NoSuchAgent"},
                    {"id": "pricing-agent", "type": "PricingAgent"},
                ]
            }), encoding="utf-8")
            store = TelemetryStore()
            fleet = load_fleet_from_config(store, config_path=cfg, seed=7)
            self.assertEqual(set(fleet.agents.keys()),
                             {"refund-agent", "pricing-agent"})

    def test_custom_worker_type_composes(self):
        @register_worker
        class PaymentsAgent(WorkerAgent):
            domain = "payments"

            def _tick_normal(self) -> None:
                self._emit("heartbeat", attributes={"state": "idle"})

            def _tick_rogue(self) -> None:
                self._emit("heartbeat", attributes={"state": "idle"})

        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Path(tmp) / "fleet.json"
                cfg.write_text(json.dumps({
                    "fleet": [
                        {"id": "refund-agent",   "type": "RefundAgent"},
                        {"id": "payments-agent", "type": "PaymentsAgent"},
                    ]
                }), encoding="utf-8")
                store = TelemetryStore()
                fleet = load_fleet_from_config(store, config_path=cfg, seed=7)
                self.assertEqual(set(fleet.agents.keys()),
                                 {"refund-agent", "payments-agent"})
                self.assertIsInstance(fleet.agents["payments-agent"], PaymentsAgent)
        finally:
            WORKER_REGISTRY.pop("PaymentsAgent", None)

    def test_seed_is_deterministic(self):
        store_a = TelemetryStore()
        fleet_a = load_fleet_from_config(store_a, seed=42)
        store_b = TelemetryStore()
        fleet_b = load_fleet_from_config(store_b, seed=42)
        for aid in fleet_a.agents:
            ra = fleet_a.agents[aid].rng.random()
            rb = fleet_b.agents[aid].rng.random()
            self.assertAlmostEqual(ra, rb, places=10,
                                   msg=f"seed=42 should be deterministic for {aid}")


if __name__ == "__main__":
    unittest.main()
