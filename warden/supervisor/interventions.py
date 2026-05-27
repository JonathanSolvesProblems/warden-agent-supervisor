"""Warden's hands: the actions it can take on the fleet, plus Dynatrace alerts.

Pausing and rollback operate on the simulated fleet/ledger; alerting goes
through the Dynatrace tool surface (send_slack_message / send_event /
create_workflow_for_notification), so in LIVE mode these become real Dynatrace
notifications and workflows.
"""

from __future__ import annotations

from ..agents.fleet import Fleet
from ..dynatrace.interface import DynatraceTools
from ..telemetry.store import TelemetryStore


class Interventions:
    def __init__(self, fleet: Fleet, dt: DynatraceTools, store: TelemetryStore) -> None:
        self.fleet = fleet
        self.dt = dt
        self.store = store

    def pause(self, agent_id: str) -> dict:
        agent = self.fleet.get(agent_id)
        if agent is None:
            return {"action": "pause", "agent": agent_id, "ok": False, "reason": "unknown agent"}
        agent.pause()
        return {"action": "pause", "agent": agent_id, "ok": True}

    def rollback(self, agent_id: str, since_tick: int = 0) -> dict:
        """Reverse the recoverable actions this agent took; return $ recovered."""
        actions = self.store.actions(agent_id, since_tick=since_tick)
        reversible_ids = [
            a.action_id for a in actions if a.reversible and not a.rolled_back and a.action_id
        ]
        recovered = self.store.mark_rolled_back(reversible_ids)
        return {
            "action": "rollback",
            "agent": agent_id,
            "ok": True,
            "reversed_actions": len(reversible_ids),
            "dollars_recovered": round(recovered, 2),
        }

    def alert(self, agent_id: str, message: str, channel: str = "#agent-incidents") -> dict:
        slack = self.dt.send_slack_message(channel, message)
        self.dt.send_event(
            title=f"Warden intervention: {agent_id}",
            properties={"agent": agent_id, "message": message},
        )
        return {"action": "alert", "agent": agent_id, "ok": bool(slack.get("ok", True)), "channel": channel}

    def open_workflow(self, agent_id: str, message: str) -> dict:
        wf = self.dt.create_workflow_for_notification(
            name=f"warden-remediation-{agent_id}",
            trigger=f"problem.affectedEntity == {agent_id}",
            message=message,
        )
        return {"action": "open_workflow", "agent": agent_id, "ok": bool(wf.get("ok", True)),
                "workflow_id": wf.get("workflowId")}
