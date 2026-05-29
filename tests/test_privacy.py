"""Privacy guarantees, enforced by tests so a future change cannot weaken them."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from warden.supervisor.brain import ScriptedBrain, build_brain
from warden.supervisor.privacy import audit, safe_for_llm


class TestSafeForLlm(unittest.TestCase):
    def test_drops_unknown_top_level_keys(self):
        raw = {
            "dynatrace_problem": {"title": "x"},
            "suspect_agent": "refund-agent",
            "raw_customer_pii": {"order_id": "ord_12345", "ssn": "123-45-6789"},  # must be dropped
        }
        clean, dropped = safe_for_llm(raw)
        self.assertNotIn("raw_customer_pii", clean)
        self.assertIn("raw_customer_pii", dropped)

    def test_drops_unknown_nested_problem_keys(self):
        raw = {
            "dynatrace_problem": {
                "title": "ok",
                "severityLevel": "CRITICAL",
                "customerEmail": "user@example.com",  # must be dropped
                "_internalTrace": "x" * 1000,         # must be dropped
            },
        }
        clean, dropped = safe_for_llm(raw)
        self.assertEqual(clean["dynatrace_problem"], {"title": "ok", "severityLevel": "CRITICAL"})
        self.assertIn("dynatrace_problem.customerEmail", dropped)
        self.assertIn("dynatrace_problem._internalTrace", dropped)

    def test_drops_unknown_nested_rollup_keys(self):
        raw = {"fleet_rollup": [
            {"agent": "a1", "actions": 5, "value_usd": 100.0, "order_ids": ["ord_1"]},  # order_ids dropped
        ]}
        clean, dropped = safe_for_llm(raw)
        self.assertEqual(clean["fleet_rollup"][0],
                         {"agent": "a1", "actions": 5, "value_usd": 100.0})
        self.assertIn("fleet_rollup[].order_ids", dropped)

    def test_keeps_full_legitimate_payload(self):
        raw = {
            "dynatrace_problem": {"problemId": "P-1", "title": "t", "severityLevel": "ERROR",
                                  "affectedEntity": "refund-agent", "signal": "anomalous_value",
                                  "metricValue": 750.0},
            "davis_root_cause": "Davis: refund-agent looks bad.",
            "fleet_rollup": [{"agent": "refund-agent", "actions": 4, "errors": 0,
                              "cost_usd": 0.01, "value_usd": 1500.0, "max_value_usd": 600.0}],
            "suspect_agent": "refund-agent",
            "value_at_risk_usd": 1500.0,
            "has_irreversible_actions": True,
        }
        clean, dropped = safe_for_llm(raw)
        self.assertEqual(clean, raw)
        self.assertEqual(dropped, [])


class TestAuditLog(unittest.TestCase):
    def test_writes_hashes_not_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.log")
            secret = "super-secret-prompt-with-pii"
            audit(model="gemini-flash-latest", vertex=False, prompt=secret,
                  response="reply", dropped=["raw_customer_pii"], log_path=path)
            with open(path, encoding="utf-8") as fh:
                line = fh.readline().strip()
            entry = json.loads(line)
            # Hashes and sizes are recorded.
            self.assertEqual(entry["input_bytes"], len(secret.encode("utf-8")))
            self.assertEqual(len(entry["input_sha256"]), 64)
            self.assertEqual(entry["dropped_fields"], ["raw_customer_pii"])
            # Raw content is NOT recorded.
            self.assertNotIn(secret, line)
            self.assertNotIn("reply", line)

    def test_empty_log_path_is_a_silent_noop(self):
        # Must not raise even with no path configured.
        audit(model="m", vertex=False, prompt="p", response="r", dropped=[], log_path="")


class TestKillSwitch(unittest.TestCase):
    def test_disable_generative_forces_scripted_brain_even_in_live_mode(self):
        with mock.patch.dict(os.environ,
                             {"WARDEN_MODE": "live", "WARDEN_DISABLE_GENERATIVE": "true"}):
            # Re-import config so the env override is picked up.
            import importlib

            from warden import config as cfg_module
            importlib.reload(cfg_module)
            from warden.supervisor import brain as brain_module
            importlib.reload(brain_module)
            b = brain_module.build_brain()
            self.assertIsInstance(b, brain_module.ScriptedBrain)
        # Reset modules to their .env-loaded state for the rest of the suite.
        import importlib

        from warden import config as cfg_module
        importlib.reload(cfg_module)
        from warden.supervisor import brain as brain_module
        importlib.reload(brain_module)


if __name__ == "__main__":
    unittest.main()
