"""Governance policy: turn a Diagnosis into a concrete, accountable Plan.

This is where "keep a human in control" lives. Reversible, low-blast actions
(pause, small rollback) execute autonomously to stop the bleeding fast; anything
irreversible or above the blast-radius ceiling is gated on explicit human
approval before Warden proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import THRESHOLDS
from .brain import Diagnosis


@dataclass
class PlannedAction:
    kind: str  # "pause" | "rollback" | "alert" | "monitor"
    needs_approval: bool
    detail: str


@dataclass
class Plan:
    actions: list[PlannedAction] = field(default_factory=list)
    rationale: str = ""

    @property
    def needs_approval(self) -> bool:
        return any(a.needs_approval for a in self.actions)

    @property
    def auto_actions(self) -> list[PlannedAction]:
        return [a for a in self.actions if not a.needs_approval]

    @property
    def gated_actions(self) -> list[PlannedAction]:
        return [a for a in self.actions if a.needs_approval]


class Policy:
    def __init__(self, thresholds=THRESHOLDS) -> None:
        self.t = thresholds

    def evaluate(self, d: Diagnosis) -> Plan:
        actions: list[PlannedAction] = []

        high_blast = d.blast_radius_usd >= self.t.human_approval_blast_usd
        # Irreversible damage or a large blast radius means a human signs off.
        escalate = (not d.reversible) or high_blast

        if d.severity >= 4:
            # Pausing is always safe and reversible → do it immediately to stop the bleed.
            actions.append(
                PlannedAction("pause", needs_approval=False,
                              detail=f"Quarantine {d.suspect_agent} to halt further actions.")
            )
            if d.reversible and d.blast_radius_usd > 0:
                actions.append(
                    PlannedAction(
                        "rollback",
                        needs_approval=high_blast,
                        detail=(f"Reverse recoverable actions worth "
                                f"${d.blast_radius_usd:,.2f}."),
                    )
                )
            actions.append(
                PlannedAction("alert", needs_approval=False,
                              detail="Notify on-call + finance via Dynatrace workflow.")
            )
        elif d.severity == 3:
            actions.append(
                PlannedAction("alert", needs_approval=False,
                              detail=f"Warn on-call about degraded {d.suspect_agent}.")
            )
        else:
            actions.append(
                PlannedAction("monitor", needs_approval=False,
                              detail="Keep watching; no action warranted yet.")
            )

        # If any irreversible exposure exists, force a human review even when
        # the automatic containment (pause) has already fired.
        if escalate and d.severity >= 4:
            actions.append(
                PlannedAction(
                    "alert",
                    needs_approval=True,
                    detail=("HUMAN REVIEW: irreversible exposure or blast radius "
                            f">= ${self.t.human_approval_blast_usd:,.0f}. Approve clawback / "
                            "credential revocation before Warden proceeds."),
                )
            )

        rationale = (
            f"severity={d.severity}, blast=${d.blast_radius_usd:,.2f}, "
            f"reversible={d.reversible} -> "
            f"{'human-gated' if any(a.needs_approval for a in actions) else 'autonomous'} containment"
        )
        return Plan(actions=actions, rationale=rationale)
