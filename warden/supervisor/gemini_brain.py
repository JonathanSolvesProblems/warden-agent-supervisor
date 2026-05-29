"""GeminiBrain: Warden's reasoning powered by Gemini 3 (the required model).

Design choice that matters: Gemini supplies *judgment* (failure class, severity,
recommended action, plain-language summary) while the **dollar figures and
reversibility are computed deterministically in Python from the telemetry**.
The model never invents money math. This keeps the impact numbers honest (the
quality the Dynatrace judges explicitly said they look for) and prevents prompt
injection in agent telemetry from inflating a blast radius.

Requires `google-genai` and either Vertex AI creds (GOOGLE_CLOUD_PROJECT) or a
GOOGLE_API_KEY. Falls back to ScriptedBrain automatically if unavailable
(see build_brain in brain.py).
"""

from __future__ import annotations

import json

from .. import config
from .brain import Diagnosis
from .privacy import audit, safe_for_llm

_SYSTEM = (
    "You are Warden, a reliability supervisor for a fleet of autonomous AI agents "
    "operating on live production systems (payments, pricing, inventory). You are "
    "given a Dynatrace problem and forensic evidence about one suspect agent. "
    "Classify the failure and recommend a containment action. Be conservative: "
    "treat agents as untrusted actors and prefer stopping harm over preserving "
    "throughput. Respond ONLY with the requested JSON."
)

# Structured-output schema: the model fills judgment fields; Warden fills the math.
_SCHEMA = {
    "type": "object",
    "properties": {
        "failure_class": {
            "type": "string",
            "enum": [
                "runaway_action_loop",
                "anomalous_high_value_action",
                "cost_overrun",
                "elevated_failure_rate",
                "anomaly",
            ],
        },
        "severity": {"type": "integer", "minimum": 1, "maximum": 5},
        "recommended_action": {
            "type": "string",
            "enum": ["pause", "rollback", "alert", "monitor"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},
    },
    "required": ["failure_class", "severity", "recommended_action", "confidence", "summary"],
}


class GeminiBrain:
    name = "gemini"

    def __init__(self) -> None:
        from google import genai  # lazy import; only needed in LIVE mode

        cfg = config.GEMINI
        if cfg.use_vertex:
            self.client = genai.Client(vertexai=True, project=cfg.project, location=cfg.location)
        else:
            self.client = genai.Client()  # picks up GOOGLE_API_KEY
        self.model = cfg.reasoning_model

    def diagnose(self, problem: dict, evidence: dict) -> Diagnosis:
        agent = problem.get("affectedEntity", "unknown")

        # --- deterministic money math (never delegated to the model) ---------
        rows = evidence.get("agent_actions", [])
        live = [r for r in rows if not r.get("rolled.back")]
        value_at_risk = round(sum(float(r.get("value.usd", 0)) for r in live), 2)
        irreversible_value = sum(
            float(r.get("value.usd", 0)) for r in live if not r.get("reversible", True)
        )
        reversible = irreversible_value <= 0.0

        # --- ask Gemini for judgment -----------------------------------------
        # Privacy: allowlist what crosses the trust boundary to the model.
        raw_payload = {
            "dynatrace_problem": problem,
            "davis_root_cause": evidence.get("davis", ""),
            "fleet_rollup": evidence.get("rollup", []),
            "suspect_agent": agent,
            "value_at_risk_usd": value_at_risk,
            "has_irreversible_actions": not reversible,
        }
        safe_payload, dropped = safe_for_llm(raw_payload)
        prompt = json.dumps(safe_payload, default=str)
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "system_instruction": _SYSTEM,
                "response_mime_type": "application/json",
                "response_schema": _SCHEMA,
                "temperature": 0,
            },
        )
        # Append-only audit: hashes + sizes + dropped fields, never raw content.
        audit(
            model=self.model,
            vertex=config.GEMINI.use_vertex,
            prompt=prompt,
            response=resp.text or "",
            dropped=dropped,
            log_path=config.PRIVACY.audit_log_path,
        )
        data = json.loads(resp.text)

        # Severity floor: large blast radius is always critical regardless of model.
        severity = int(data["severity"])
        if value_at_risk >= config.THRESHOLDS.human_approval_blast_usd:
            severity = max(severity, 5)

        return Diagnosis(
            suspect_agent=agent,
            failure_class=data["failure_class"],
            severity=severity,
            blast_radius_usd=value_at_risk,
            reversible=reversible,
            confidence=round(float(data["confidence"]), 2),
            summary=data["summary"],
            recommended_action=data["recommended_action"],
            reasoned_by="gemini",
        )
