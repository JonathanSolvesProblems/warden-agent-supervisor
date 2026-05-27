"""The Warden supervisory loop: sense → reason → decide → act → prove.

Designed to be driven one step at a time (after each fleet tick) so a CLI or a
web dashboard can stream the agent's thinking live. Warden only perceives the
fleet through the Dynatrace tool surface, never the raw store.
"""

from __future__ import annotations

import itertools
from typing import Callable, Protocol, runtime_checkable

from ..agents.fleet import Fleet
from ..chaos.injector import ChaosInjector
from ..dynatrace.interface import DynatraceTools
from ..telemetry.store import TelemetryStore
from .brain import Brain, build_brain
from .incidents import Incident, IncidentLog
from .interventions import Interventions
from .policies import Plan, PlannedAction, Policy

# How long (ticks) a rogue agent is assumed to keep bleeding if left unattended,
# used purely to estimate (and clearly label) projected loss prevented.
UNATTENDED_HORIZON_TICKS = 30


@runtime_checkable
class ApprovalGate(Protocol):
    def request(self, incident_preview: dict, gated_actions: list[PlannedAction]) -> bool: ...


class AutoApproveGate:
    """Stands in for an operator clicking 'Approve'. Configurable for tests/demo."""

    def __init__(self, approve: bool = True, on_request: Callable | None = None) -> None:
        self.approve = approve
        self.on_request = on_request

    def request(self, incident_preview: dict, gated_actions: list[PlannedAction]) -> bool:
        if self.on_request:
            self.on_request(incident_preview, gated_actions)
        return self.approve


Observer = Callable[[str, dict], None]


class Warden:
    def __init__(
        self,
        fleet: Fleet,
        dt: DynatraceTools,
        store: TelemetryStore,
        *,
        brain: Brain | None = None,
        policy: Policy | None = None,
        gate: ApprovalGate | None = None,
        injector: ChaosInjector | None = None,
        observer: Observer | None = None,
    ) -> None:
        self.fleet = fleet
        self.dt = dt
        self.store = store
        self.brain = brain or build_brain()
        self.policy = policy or Policy()
        self.gate = gate or AutoApproveGate()
        self.injector = injector
        self.observer = observer
        self.iv = Interventions(fleet, dt, store)
        self.log = IncidentLog()
        self._handled: set[str] = set()
        self._ids = itertools.count(1)

    # --- public API ----------------------------------------------------------
    def step(self) -> list[Incident]:
        """Run one supervision cycle. Returns incidents opened this cycle."""
        problems = self.dt.list_problems()
        self._notify("sense", {"problems": problems, "tick": self.store.tick,
                              "handled": sorted(self._handled)})
        opened: list[Incident] = []
        for problem in problems:
            agent = problem.get("affectedEntity", "unknown")
            if agent in self._handled:
                continue
            opened.append(self._handle(problem, agent))
            self._handled.add(agent)
        return opened

    # --- internals -----------------------------------------------------------
    def _handle(self, problem: dict, agent: str) -> Incident:
        evidence = self._gather(problem, agent)
        diagnosis = self.brain.diagnose(problem, evidence)
        self._notify("diagnose", {"agent": agent, "diagnosis": diagnosis.to_dict()})

        plan = self.policy.evaluate(diagnosis)
        self._notify("plan", {"agent": agent, "rationale": plan.rationale,
                              "actions": [a.__dict__ for a in plan.actions]})

        onset = self.injector.onset_tick(agent) if self.injector else None
        incident = Incident(
            incident_id=f"INC-{next(self._ids):03d}",
            detect_tick=self.store.tick,
            onset_tick=onset,
            suspect_agent=agent,
            diagnosis=diagnosis,
            plan=plan,
            human_approval_required=plan.needs_approval,
        )

        # 1) Autonomous containment: execute immediately.
        for action in plan.auto_actions:
            incident.actions_taken.append(self._execute_action(action, agent, onset))

        # 2) Human-gated actions: request approval, then proceed if granted.
        if plan.gated_actions:
            preview = {"incident_id": incident.incident_id, "agent": agent,
                       "diagnosis": diagnosis.to_dict()}
            self._notify("approval_request", {**preview,
                          "gated": [a.__dict__ for a in plan.gated_actions]})
            approved = self.gate.request(preview, plan.gated_actions)
            incident.human_approved = approved
            self._notify("approval_result", {"incident_id": incident.incident_id, "approved": approved})
            if approved:
                for action in plan.gated_actions:
                    incident.actions_taken.append(self._execute_action(action, agent, onset))
            else:
                incident.actions_taken.append(
                    {"action": "awaiting_human", "agent": agent, "ok": False}
                )

        self._score(incident, agent, onset)
        self.log.add(incident)
        self._notify("incident", incident.to_dict())
        return incident

    def _gather(self, problem: dict, agent: str) -> dict:
        """Forensics via the Dynatrace tools, exactly the MCP calls used in LIVE mode."""
        dql = self.dt.generate_dql_from_natural_language(f"list actions for {agent} to scope rollback")
        rollup = self.dt.execute_dql("summarize actions by agent")
        agent_actions = self.dt.execute_dql(f"fetch action records for {agent}")
        davis = self.dt.chat_with_davis_copilot(f"What is going wrong with {agent}?")
        return {
            "problem": problem,
            "dql": dql,
            "rollup": rollup,
            "agent_actions": agent_actions,
            "davis": davis,
        }

    def _execute_action(self, action: PlannedAction, agent: str, onset: int | None) -> dict:
        if action.kind == "pause":
            result = self.iv.pause(agent)
        elif action.kind == "rollback":
            result = self.iv.rollback(agent, since_tick=onset or 0)
        elif action.kind == "alert":
            result = self.iv.alert(agent, action.detail)
        else:  # monitor
            result = {"action": "monitor", "agent": agent, "ok": True}
        result["detail"] = action.detail
        self._notify("action", result)
        return result

    def _score(self, incident: Incident, agent: str, onset: int | None) -> None:
        # Hard numbers from the ledger.
        recovered = sum(
            a.get("dollars_recovered", 0.0) for a in incident.actions_taken if a.get("action") == "rollback"
        )
        since = onset or 0
        actions = self.store.actions(agent, since_tick=since)
        irreversible_loss = sum(a.value_usd for a in actions if not a.reversible)
        value_since_onset = sum(a.value_usd for a in actions)

        incident.dollars_recovered = recovered
        incident.irreversible_loss_at_detection = irreversible_loss

        # Estimate (labeled): bleed prevented by pausing early vs. running unattended.
        ticks_active = max(incident.mttd_ticks or 1, 1)
        rate = value_since_onset / ticks_active
        incident.projected_loss_prevented = max(rate * UNATTENDED_HORIZON_TICKS - value_since_onset, 0.0)

    def _notify(self, event_type: str, payload: dict) -> None:
        if self.observer:
            self.observer(event_type, payload)
