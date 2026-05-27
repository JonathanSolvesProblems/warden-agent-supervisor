"""Telemetry domain model + in-memory store.

In LIVE mode the worker agents export the same signals over OpenTelemetry to
Dynatrace; in SIMULATION mode they land in this store and the mock Dynatrace
reads from it. Either way Warden only ever sees data through the Dynatrace
tool interface — never the store directly.
"""

from .store import AgentEvent, TelemetryStore

__all__ = ["AgentEvent", "TelemetryStore"]
