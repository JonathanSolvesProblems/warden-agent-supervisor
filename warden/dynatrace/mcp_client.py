"""McpDynatrace — the LIVE adapter to the real Dynatrace MCP server.

Launches `@dynatrace-oss/dynatrace-mcp-server` (Node) over stdio and speaks the
Model Context Protocol to it, so Warden's senses are real production telemetry
(problems, DQL, Davis Copilot) and its alerts are real Dynatrace notifications
and workflows. The class satisfies the exact same `DynatraceTools` contract as
the mock, so Warden's loop is byte-for-byte identical across modes.

Requires: the `mcp` Python package (pip install mcp) and Node v22.10+ on PATH.
Auth comes from the environment (DT_ENVIRONMENT + DT_PLATFORM_TOKEN, or OAuth);
see .env.example. Confirm exact tool argument names against the server's own
schema via `list_tools()` — Warden introspects on connect and logs them.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading

from ..config import DYNATRACE

_MCP_COMMAND = "npx"
_MCP_ARGS = ["-y", "@dynatrace-oss/dynatrace-mcp-server@latest"]


def _parse_result(result) -> object:
    """Flatten an MCP tool result into JSON (if possible) or text."""
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
    blob = "\n".join(parts).strip()
    if not blob:
        return {}
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return blob


class _McpBridge:
    """Runs a persistent MCP stdio session on a dedicated asyncio loop thread."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._session = None
        self._exit_stack = None
        asyncio.run_coroutine_threadsafe(self._connect(), self._loop).result(timeout=90)

    async def _connect(self) -> None:
        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = dict(os.environ)
        env.setdefault("DT_ENVIRONMENT", DYNATRACE.environment)
        if DYNATRACE.platform_token:
            env.setdefault("DT_PLATFORM_TOKEN", DYNATRACE.platform_token)
        env.setdefault("DT_GRAIL_QUERY_BUDGET_GB", str(DYNATRACE.grail_budget_gb))

        self._exit_stack = AsyncExitStack()
        params = StdioServerParameters(command=_MCP_COMMAND, args=_MCP_ARGS, env=env)
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    def call(self, name: str, arguments: dict | None = None) -> object:
        coro = self._session.call_tool(name, arguments or {})
        result = asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=120)
        return _parse_result(result)

    def list_tools(self) -> list[str]:
        coro = self._session.list_tools()
        res = asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=60)
        return [t.name for t in res.tools]


class McpDynatrace:
    def __init__(self) -> None:
        self._bridge = _McpBridge()
        try:
            tools = self._bridge.list_tools()
            print(f"[warden] connected to Dynatrace MCP server; {len(tools)} tools: {', '.join(tools)}")
        except Exception as exc:  # pragma: no cover
            print(f"[warden] connected to Dynatrace MCP server (tool introspection failed: {exc})")

    @staticmethod
    def _as_list(obj) -> list[dict]:
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for key in ("problems", "results", "records", "items"):
                if isinstance(obj.get(key), list):
                    return obj[key]
            return [obj]
        return [{"text": obj}]

    # --- DynatraceTools contract ---------------------------------------------
    def list_problems(self) -> list[dict]:
        return self._as_list(self._bridge.call("list_problems"))

    def execute_dql(self, query: str) -> list[dict]:
        return self._as_list(self._bridge.call("execute_dql", {"dqlStatement": query}))

    def generate_dql_from_natural_language(self, prompt: str) -> str:
        out = self._bridge.call("generate_dql_from_natural_language", {"text": prompt})
        return out if isinstance(out, str) else json.dumps(out)

    def chat_with_davis_copilot(self, question: str) -> str:
        out = self._bridge.call("chat_with_davis_copilot", {"text": question})
        return out if isinstance(out, str) else json.dumps(out)

    def find_entity_by_name(self, name: str) -> dict:
        out = self._bridge.call("find_entity_by_name", {"entityName": name})
        return out if isinstance(out, dict) else {"result": out}

    def send_slack_message(self, channel: str, message: str) -> dict:
        out = self._bridge.call("send_slack_message", {"channel": channel, "message": message})
        return {"ok": True, "result": out}

    def send_event(self, title: str, properties: dict) -> dict:
        out = self._bridge.call("send_event", {"title": title, "properties": properties})
        return {"ok": True, "result": out}

    def create_workflow_for_notification(self, name: str, trigger: str, message: str) -> dict:
        out = self._bridge.call(
            "create_workflow_for_notification",
            {"name": name, "trigger": trigger, "message": message},
        )
        return {"ok": True, "result": out}
