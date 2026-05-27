"""Incident records + the measured-outcome ledger.

The numbers here are the whole point: they let Warden *prove* impact (time to
detect, dollars recovered, irreversible loss at detection) instead of claiming
it. Hard, observed figures are separated from clearly-labeled projections.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .brain import Diagnosis
from .policies import Plan


@dataclass
class Incident:
    incident_id: str
    detect_tick: int
    onset_tick: int | None
    suspect_agent: str
    diagnosis: Diagnosis
    plan: Plan
    actions_taken: list[dict] = field(default_factory=list)
    human_approval_required: bool = False
    human_approved: bool | None = None
    # Measured outcomes
    dollars_recovered: float = 0.0  # hard: reversible value clawed back
    irreversible_loss_at_detection: float = 0.0  # hard: value already gone when caught
    projected_loss_prevented: float = 0.0  # estimate: bleed avoided by early pause

    @property
    def mttd_ticks(self) -> int | None:
        if self.onset_tick is None:
            return None
        return max(self.detect_tick - self.onset_tick, 0)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "detect_tick": self.detect_tick,
            "onset_tick": self.onset_tick,
            "mttd_ticks": self.mttd_ticks,
            "suspect_agent": self.suspect_agent,
            "diagnosis": self.diagnosis.to_dict(),
            "plan": {
                "rationale": self.plan.rationale,
                "actions": [
                    {"kind": a.kind, "needs_approval": a.needs_approval, "detail": a.detail}
                    for a in self.plan.actions
                ],
            },
            "actions_taken": self.actions_taken,
            "human_approval_required": self.human_approval_required,
            "human_approved": self.human_approved,
            "dollars_recovered": round(self.dollars_recovered, 2),
            "irreversible_loss_at_detection": round(self.irreversible_loss_at_detection, 2),
            "projected_loss_prevented": round(self.projected_loss_prevented, 2),
        }


class IncidentLog:
    def __init__(self) -> None:
        self.incidents: list[Incident] = []

    def add(self, incident: Incident) -> Incident:
        self.incidents.append(incident)
        return incident

    def summary(self) -> dict:
        if not self.incidents:
            return {
                "incidents": 0,
                "dollars_recovered": 0.0,
                "irreversible_loss": 0.0,
                "projected_loss_prevented": 0.0,
                "avg_mttd_ticks": None,
            }
        mttds = [i.mttd_ticks for i in self.incidents if i.mttd_ticks is not None]
        return {
            "incidents": len(self.incidents),
            "dollars_recovered": round(sum(i.dollars_recovered for i in self.incidents), 2),
            "irreversible_loss": round(
                sum(i.irreversible_loss_at_detection for i in self.incidents), 2
            ),
            "projected_loss_prevented": round(
                sum(i.projected_loss_prevented for i in self.incidents), 2
            ),
            "avg_mttd_ticks": round(sum(mttds) / len(mttds), 2) if mttds else None,
        }
