"""Unit + integration tests for Warden's supervisory loop.

Pure stdlib (unittest) so it runs anywhere with no dependencies:
    python -m unittest discover -s tests -v
    # or, if installed:  pytest -q
"""

from __future__ import annotations

import unittest

from warden.agents.workers import default_fleet
from warden.chaos.injector import ChaosInjector
from warden.dynatrace.mock import MockDynatrace
from warden.supervisor.brain import Diagnosis, ScriptedBrain
from warden.supervisor.interventions import Interventions
from warden.supervisor.loop import AutoApproveGate, Warden
from warden.supervisor.policies import Policy
from warden.telemetry.store import TelemetryStore


def build_world(seed: int = 7):
    store = TelemetryStore()
    fleet = default_fleet(store, seed=seed)
    dt = MockDynatrace(store)
    injector = ChaosInjector(fleet)
    return store, fleet, dt, injector


def run(warden, fleet, injector, *, ticks=30, inject=None, inject_at=8):
    for _ in range(ticks):
        fleet.tick()
        if inject and fleet.store.tick == inject_at:
            injector.inject(inject, at_tick=fleet.store.tick)
        warden.step()


class TestDetection(unittest.TestCase):
    def test_no_false_positives_when_healthy(self):
        store, fleet, dt, _ = build_world()
        for _ in range(25):
            fleet.tick()
        self.assertEqual(dt.list_problems(), [], "healthy fleet should raise no problems")

    def test_rogue_refund_is_detected(self):
        store, fleet, dt, injector = build_world()
        for _ in range(8):
            fleet.tick()
        injector.inject("refund_fraud_loop", at_tick=store.tick)
        for _ in range(3):
            fleet.tick()
        problems = dt.list_problems()
        self.assertTrue(problems, "rogue agent should surface a problem")
        self.assertTrue(any(p["affectedEntity"] == "refund-agent" for p in problems))


class TestScriptedBrain(unittest.TestCase):
    def test_irreversible_high_value_is_critical(self):
        brain = ScriptedBrain()
        problem = {"affectedEntity": "refund-agent", "signal": "anomalous_value"}
        evidence = {"agent_actions": [
            {"value.usd": 600, "reversible": False, "rolled.back": False},
            {"value.usd": 500, "reversible": False, "rolled.back": False},
        ], "davis": ""}
        d = brain.diagnose(problem, evidence)
        self.assertEqual(d.severity, 5)
        self.assertFalse(d.reversible)
        self.assertGreaterEqual(d.blast_radius_usd, 1000)

    def test_reversible_actions_flagged_recoverable(self):
        brain = ScriptedBrain()
        problem = {"affectedEntity": "pricing-agent", "signal": "anomalous_value"}
        evidence = {"agent_actions": [
            {"value.usd": 300, "reversible": True, "rolled.back": False},
        ], "davis": ""}
        d = brain.diagnose(problem, evidence)
        self.assertTrue(d.reversible)


class TestPolicy(unittest.TestCase):
    def test_irreversible_requires_human_approval(self):
        d = Diagnosis("a", "anomalous_high_value_action", 5, 1500, False, 0.9, "", "pause")
        plan = Policy().evaluate(d)
        self.assertTrue(plan.needs_approval)
        self.assertIn("pause", [a.kind for a in plan.auto_actions])

    def test_low_severity_is_monitor_only(self):
        d = Diagnosis("a", "elevated_failure_rate", 2, 0, True, 0.7, "", "monitor")
        plan = Policy().evaluate(d)
        self.assertFalse(plan.needs_approval)
        self.assertEqual([a.kind for a in plan.actions], ["monitor"])


class TestInterventions(unittest.TestCase):
    def test_pause_and_rollback_recovers_reversible_value(self):
        store, fleet, dt, injector = build_world()
        for _ in range(6):
            fleet.tick()
        injector.inject("price_collapse", at_tick=store.tick)
        onset = store.tick
        for _ in range(4):
            fleet.tick()
        iv = Interventions(fleet, dt, store)
        self.assertTrue(iv.pause("pricing-agent")["ok"])
        self.assertTrue(fleet.get("pricing-agent").paused)
        result = iv.rollback("pricing-agent", since_tick=onset)
        self.assertGreater(result["dollars_recovered"], 0)


class TestFullLoop(unittest.TestCase):
    def test_loop_contains_rogue_and_opens_incident(self):
        store, fleet, dt, injector = build_world()
        warden = Warden(fleet, dt, store, brain=ScriptedBrain(),
                        gate=AutoApproveGate(True), injector=injector)
        run(warden, fleet, injector, ticks=30, inject="refund_fraud_loop", inject_at=8)
        self.assertEqual(len(warden.log.incidents), 1)
        inc = warden.log.incidents[0]
        self.assertEqual(inc.suspect_agent, "refund-agent")
        self.assertTrue(fleet.get("refund-agent").paused)
        self.assertIsNotNone(inc.mttd_ticks)
        self.assertLessEqual(inc.mttd_ticks, 5)

    def test_denied_approval_withholds_gated_action_but_still_pauses(self):
        store, fleet, dt, injector = build_world()
        warden = Warden(fleet, dt, store, brain=ScriptedBrain(),
                        gate=AutoApproveGate(False), injector=injector)
        run(warden, fleet, injector, ticks=20, inject="refund_fraud_loop", inject_at=8)
        inc = warden.log.incidents[0]
        self.assertTrue(inc.human_approval_required)
        self.assertFalse(inc.human_approved)
        # Autonomous containment still happened: the agent is paused.
        self.assertTrue(fleet.get("refund-agent").paused)
        # The human-gated action was recorded as awaiting/withheld.
        self.assertTrue(any(a.get("action") == "awaiting_human" for a in inc.actions_taken))


if __name__ == "__main__":
    unittest.main()
