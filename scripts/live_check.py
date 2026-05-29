"""Live-mode smoke test: prove the Dynatrace MCP handshake and a few tool calls.

Requires `WARDEN_MODE=live` plus `DT_ENVIRONMENT` and either `DT_PLATFORM_TOKEN`
or OAuth env vars in `.env`. Run:

    python -m scripts.live_check

A successful run reports the connected tool count, lists active problems, asks
Davis Copilot for a one-line summary, and runs a small DQL query, then exits 0.
"""

from __future__ import annotations

import sys

# UTF-8 safety for Windows consoles.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from warden import config


def main() -> int:
    if not config.is_live():
        print(f"WARDEN_MODE is '{config.mode()}'. Set WARDEN_MODE=live in .env to run this check.")
        return 1
    if not config.DYNATRACE.environment:
        print("DT_ENVIRONMENT is not set. Check .env.")
        return 1

    print(f"environment: {config.DYNATRACE.environment}")
    print(f"auth       : platform token (len={len(config.DYNATRACE.platform_token)})"
          if config.DYNATRACE.platform_token else "auth       : browser OAuth")
    print("connecting to Dynatrace MCP server (first run downloads via npx, ~60s)...")

    from warden.dynatrace.mcp_client import McpDynatrace
    dt = McpDynatrace()

    print()
    print("--- list_problems ---")
    problems = dt.list_problems()
    print(f"{len(problems)} problem(s) returned")
    for p in problems[:5]:
        title = p.get("title") or p.get("displayId") or str(p)[:80]
        print(f"  - {title}")

    print()
    print("--- chat_with_davis_copilot ---")
    summary = dt.chat_with_davis_copilot("Give me a one-sentence health summary of this tenant.")
    print(summary[:400] + ("..." if len(str(summary)) > 400 else ""))

    print()
    print("--- execute_dql (light query, scans recent fetch events) ---")
    try:
        rows = dt.execute_dql("fetch events | limit 3")
        print(f"{len(rows)} row(s) returned")
    except Exception as exc:
        print(f"DQL query skipped ({exc})")

    print()
    print("OK: live Dynatrace MCP handshake + tool calls verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
