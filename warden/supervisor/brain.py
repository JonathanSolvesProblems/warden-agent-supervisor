"""Warden's reasoning. Two interchangeable brains behind one interface:

* `ScriptedBrain`: deterministic heuristics; runs offline with no model. Lets
  the whole supervisory loop be tested and demoed without credentials.
* `GeminiBrain`: Gemini via the `gemini-flash-latest` / `gemini-pro-latest` aliases turns the same
  evidence into a structured diagnosis. Wired in `gemini_brain.py`.

Both return the identical `Diagnosis` shape, so the policy/intervention layers
never know or care which one ran.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable

from ..config import THRESHOLDS

_SIGNAL_MAP = {
    "action_rate": ("runaway_action_loop", 5),
    "anomalous_value": ("anomalous_high_value_action", 5),
    "cost_spike": ("cost_overrun", 4),
    "error_rate": ("elevated_failure_rate", 3),
}


@dataclass
class Diagnosis:
    suspect_agent: str
    failure_class: str
    severity: int  # 1 (info) … 5 (critical)
    blast_radius_usd: float  # business value currently at risk from this agent
    reversible: bool  # is the at-risk value recoverable (vs. already gone)?
    confidence: float  # 0..1
    summary: str
    recommended_action: str  # "pause" | "rollback" | "alert" | "monitor"
    reasoned_by: str = "scripted"

    def to_dict(self) -> dict:
        return asdict(self)


@runtime_checkable
class Brain(Protocol):
    name: str

    def diagnose(self, problem: dict, evidence: dict) -> Diagnosis: ...


class ScriptedBrain:
    """Heuristic diagnosis derived from the telemetry evidence."""

    name = "scripted"

    def diagnose(self, problem: dict, evidence: dict) -> Diagnosis:
        agent = problem.get("affectedEntity", "unknown")
        signal = problem.get("signal", "error_rate")
        failure_class, base_sev = _SIGNAL_MAP.get(signal, ("anomaly", 3))

        rows = evidence.get("agent_actions", [])
        live = [r for r in rows if not r.get("rolled.back")]
        value_at_risk = round(sum(float(r.get("value.usd", 0)) for r in live), 2)
        irreversible_value = round(
            sum(float(r.get("value.usd", 0)) for r in live if not r.get("reversible", True)), 2
        )
        reversible = irreversible_value <= 0.0

        # Severity escalates with how badly the metric breached threshold.
        severity = base_sev
        if value_at_risk >= THRESHOLDS.human_approval_blast_usd:
            severity = 5

        if severity >= 4:
            recommended = "rollback" if reversible and value_at_risk > 0 else "pause"
        elif severity == 3:
            recommended = "alert"
        else:
            recommended = "monitor"

        confidence = 0.7 + 0.05 * (severity - 1)  # 0.7..0.9
        summary = (
            f"{agent} exhibits '{failure_class}' (signal={signal}, "
            f"value_at_risk=${value_at_risk:,.2f}, "
            f"{'recoverable' if reversible else 'PARTLY IRREVERSIBLE'}). "
            f"{evidence.get('davis', '')}"
        ).strip()

        return Diagnosis(
            suspect_agent=agent,
            failure_class=failure_class,
            severity=severity,
            blast_radius_usd=value_at_risk,
            reversible=reversible,
            confidence=round(min(confidence, 0.95), 2),
            summary=summary,
            recommended_action=recommended,
            reasoned_by="scripted",
        )


def build_brain() -> Brain:
    """Return the Gemini brain in LIVE mode, else the scripted brain.

    Honors the WARDEN_DISABLE_GENERATIVE kill switch: when set, ScriptedBrain
    is used unconditionally. This is the "no aggregates leave the perimeter"
    deployment posture for highly sensitive tenants.
    """
    from .. import config

    if config.PRIVACY.disable_generative:
        print("[warden] WARDEN_DISABLE_GENERATIVE=true; using ScriptedBrain only.")
        return ScriptedBrain()
    if config.is_live():
        try:
            from .gemini_brain import GeminiBrain

            return GeminiBrain()
        except Exception as exc:  # pragma: no cover - depends on optional deps/creds
            print(f"[warden] Gemini brain unavailable ({exc}); falling back to scripted brain.")
    return ScriptedBrain()
