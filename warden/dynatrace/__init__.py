"""Warden's senses: the Dynatrace tool surface.

`DynatraceTools` is the contract Warden depends on. It mirrors the real
Dynatrace MCP server's tools (list_problems, execute_dql,
generate_dql_from_natural_language, chat_with_davis_copilot, send_slack_message,
create_workflow_for_notification, …). Two implementations satisfy it:

* `MockDynatrace`: derives problems/DQL answers from the local TelemetryStore
                     (SIMULATION mode, zero credentials).
* `McpDynatrace`: proxies to the live Dynatrace MCP server via Google ADK
                     (LIVE mode). See `mcp_client.py`.

Swapping modes never changes a line of Warden's reasoning code.
"""

from .interface import DynatraceTools, Problem
from .mock import MockDynatrace

__all__ = ["DynatraceTools", "Problem", "MockDynatrace", "build_dynatrace"]


def build_dynatrace(store=None):
    """Factory: return the live MCP-backed tools, or the mock, per WARDEN_MODE."""
    from .. import config

    if config.is_live():
        from .mcp_client import McpDynatrace  # lazy: avoids importing ADK in sim mode

        return McpDynatrace()
    if store is None:
        raise ValueError("MockDynatrace requires a TelemetryStore")
    return MockDynatrace(store)
