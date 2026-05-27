"""MockDynatrace: implements the Dynatrace tool surface from the TelemetryStore.

The detectors below stand in for Davis AI: they scan the rolling telemetry
window and raise Problems for error spikes, cost spikes, runaway action rates,
and anomalous business values. The DQL engine answers the handful of queries
Warden actually issues. All of this is replaced by the real MCP server in LIVE
mode without touching Warden's logic.
"""

from __future__ import annotations

from ..config import THRESHOLDS
from ..telemetry.store import TelemetryStore
from .interface import Problem


class MockDynatrace:
    def __init__(self, store: TelemetryStore) -> None:
        self.store = store
        self.sent_notifications: list[dict] = []
        self.workflows: list[dict] = []

    # --- detection (the "Davis AI" stand-in) ---------------------------------
    def _detect(self) -> list[Problem]:
        w = THRESHOLDS.window_ticks
        problems: list[Problem] = []
        for agent_id in self.store.agents():
            events = self.store.by_agent(agent_id, window=w)
            if not events:
                continue
            actions = [e for e in events if e.kind == "action"]
            errors = [e for e in events if e.error]
            spend = sum(e.cost_usd for e in events)
            n_actions = len(actions)
            err_rate = (len(errors) / n_actions) if n_actions else 0.0
            max_value = max((e.value_usd for e in actions), default=0.0)

            if err_rate >= THRESHOLDS.error_rate_alarm and len(errors) >= 3:
                problems.append(
                    Problem(
                        problem_id=f"P-{agent_id}-ERR",
                        title=f"Elevated failure rate on {agent_id}",
                        severity="ERROR",
                        affected_agent=agent_id,
                        signal="error_rate",
                        metric_value=round(err_rate, 2),
                        evidence={"errors": len(errors), "actions": n_actions},
                    )
                )
            if n_actions >= THRESHOLDS.action_rate_alarm:
                problems.append(
                    Problem(
                        problem_id=f"P-{agent_id}-RATE",
                        title=f"Runaway action rate on {agent_id}",
                        severity="CRITICAL",
                        affected_agent=agent_id,
                        signal="action_rate",
                        metric_value=float(n_actions),
                        evidence={"actions_in_window": n_actions, "window": w},
                    )
                )
            if spend >= THRESHOLDS.cost_alarm_usd:
                problems.append(
                    Problem(
                        problem_id=f"P-{agent_id}-COST",
                        title=f"Cost spike on {agent_id}",
                        severity="WARNING",
                        affected_agent=agent_id,
                        signal="cost_spike",
                        metric_value=round(spend, 2),
                        evidence={"window_spend_usd": round(spend, 2)},
                    )
                )
            if max_value >= THRESHOLDS.high_value_usd:
                problems.append(
                    Problem(
                        problem_id=f"P-{agent_id}-VALUE",
                        title=f"Anomalous high-value action on {agent_id}",
                        severity="CRITICAL",
                        affected_agent=agent_id,
                        signal="anomalous_value",
                        metric_value=round(max_value, 2),
                        evidence={"max_value_usd": round(max_value, 2)},
                    )
                )
        return problems

    # --- Dynatrace MCP tool surface ------------------------------------------
    def list_problems(self) -> list[dict]:
        # De-dupe by (agent, signal); keep the most severe per agent first.
        order = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}
        problems = sorted(self._detect(), key=lambda p: order.get(p.severity, 9))
        return [p.to_dict() for p in problems]

    def execute_dql(self, query: str) -> list[dict]:
        """Tiny DQL interpreter covering the queries Warden issues."""
        q = query.lower()
        w = THRESHOLDS.window_ticks

        # Per-agent rollup of recent actions (Warden's main forensic query).
        if "summarize" in q or "by agent" in q or "groupby" in q or "group by" in q:
            rollup: dict[str, dict] = {}
            for e in self.store.recent(window=w):
                r = rollup.setdefault(
                    e.agent_id,
                    {"agent": e.agent_id, "actions": 0, "errors": 0,
                     "cost_usd": 0.0, "value_usd": 0.0, "max_value_usd": 0.0},
                )
                if e.kind == "action":
                    r["actions"] += 1
                    r["value_usd"] += e.value_usd
                    r["max_value_usd"] = max(r["max_value_usd"], e.value_usd)
                if e.error:
                    r["errors"] += 1
                r["cost_usd"] += e.cost_usd
            for r in rollup.values():
                r["cost_usd"] = round(r["cost_usd"], 2)
                r["value_usd"] = round(r["value_usd"], 2)
                r["max_value_usd"] = round(r["max_value_usd"], 2)
            return list(rollup.values())

        # Raw recent action records for one agent (forensics / rollback scoping).
        for agent_id in self.store.agents():
            if agent_id.lower() in q:
                rows = [e.as_row() for e in self.store.actions(agent_id, since_tick=self.store.tick - w)]
                return rows

        # Default: latest records in the window.
        return [e.as_row() for e in self.store.recent(window=w)]

    def generate_dql_from_natural_language(self, prompt: str) -> str:
        p = prompt.lower()
        if "rollback" in p or "which actions" in p or "list actions" in p:
            agent = next((a for a in self.store.agents() if a.lower() in p), "<agent>")
            return (
                f"fetch logs | filter dt.entity.agent == \"{agent}\" "
                f"and event.kind == \"action\" | sort timestamp desc"
            )
        return (
            "fetch logs | filter event.kind == \"action\" "
            "| summarize count(), sum(value.usd), max(value.usd) by dt.entity.agent"
        )

    def chat_with_davis_copilot(self, question: str) -> str:
        """Plain-language root cause, the way Davis Copilot would summarize it."""
        problems = self._detect()
        if not problems:
            return "Davis: no active problems detected across the agent fleet."
        top = problems[0]
        ev = ", ".join(f"{k}={v}" for k, v in top.evidence.items())
        return (
            f"Davis: {top.affected_agent} is the likely root cause. Signal "
            f"'{top.signal}' breached threshold (value={top.metric_value}; {ev}). "
            f"Recommend isolating {top.affected_agent} and reviewing its recent actions."
        )

    def find_entity_by_name(self, name: str) -> dict:
        return {"entityId": f"AGENT-{name}", "displayName": name, "type": "ai_agent"}

    # --- outbound actions (recorded so the demo/UI can show them) ------------
    def send_slack_message(self, channel: str, message: str) -> dict:
        rec = {"tool": "send_slack_message", "channel": channel, "message": message}
        self.sent_notifications.append(rec)
        return {"ok": True, **rec}

    def send_email(self, to: str, subject: str, body: str) -> dict:
        rec = {"tool": "send_email", "to": to, "subject": subject, "body": body}
        self.sent_notifications.append(rec)
        return {"ok": True, **rec}

    def send_event(self, title: str, properties: dict) -> dict:
        rec = {"tool": "send_event", "title": title, "properties": properties}
        self.sent_notifications.append(rec)
        return {"ok": True, **rec}

    def create_workflow_for_notification(self, name: str, trigger: str, message: str) -> dict:
        wf = {"tool": "create_workflow", "name": name, "trigger": trigger, "message": message}
        self.workflows.append(wf)
        return {"ok": True, "workflowId": f"WF-{len(self.workflows)}", **wf}
