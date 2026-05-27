"""The Dynatrace tool contract + the Problem type Warden reasons over."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Problem:
    """A Dynatrace 'problem': an anomaly Davis (or the mock detectors) surfaced."""

    problem_id: str
    title: str
    severity: str  # "INFO" | "WARNING" | "ERROR" | "CRITICAL"
    affected_agent: str
    signal: str  # "error_rate" | "cost_spike" | "action_rate" | "anomalous_value"
    metric_value: float
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "problemId": self.problem_id,
            "title": self.title,
            "severityLevel": self.severity,
            "affectedEntity": self.affected_agent,
            "signal": self.signal,
            "metricValue": self.metric_value,
            "evidence": self.evidence,
        }


@runtime_checkable
class DynatraceTools(Protocol):
    """Mirror of the Dynatrace MCP server tools Warden uses."""

    def list_problems(self) -> list[dict]: ...

    def execute_dql(self, query: str) -> list[dict]: ...

    def generate_dql_from_natural_language(self, prompt: str) -> str: ...

    def chat_with_davis_copilot(self, question: str) -> str: ...

    def find_entity_by_name(self, name: str) -> dict: ...

    def send_slack_message(self, channel: str, message: str) -> dict: ...

    def send_event(self, title: str, properties: dict) -> dict: ...

    def create_workflow_for_notification(self, name: str, trigger: str, message: str) -> dict: ...
