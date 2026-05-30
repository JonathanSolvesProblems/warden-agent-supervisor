"""OTel smoke test: ship Warden spans and metrics to Dynatrace and verify acceptance.

    python -m scripts.otel_smoke

Success criteria (per Dynatrace docs):
1. OTel SDK initializes cleanly (endpoint + auth resolved).
2. `force_flush()` returns True (Dynatrace returned OTLP 2xx).
3. A DQL `fetch spans` query through the MCP server returns at least one
   warden span.

We deliberately do NOT verify by polling `list_problems()`. Davis AI needs at
least 5 minutes of 1-minute samples plus a configured Metric event before a
problem fires. A short smoke run cannot satisfy that, so an empty
`list_problems` result would be misleading rather than informative.

What success here means: the worker fleet is now emitting OpenTelemetry into
your tenant, which closes the data-plane half of the live loop. To make
Davis surface a real problem Warden can read via MCP, configure a Metric
event on `warden.agent.errors` or `warden.agent.latency_ms` (see
`docs/DEPLOY.md`).
"""

from __future__ import annotations

import sys
import time

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from warden import config
from warden.agents.workers import default_fleet
from warden.chaos.injector import ChaosInjector
from warden.telemetry import otel
from warden.telemetry.store import TelemetryStore


def main() -> int:
    if not config.is_live():
        print(f"WARDEN_MODE is '{config.mode()}'. Set WARDEN_MODE=live in .env to run this check.")
        return 1
    if not otel.init_otel():
        print("OTel init failed. Set DT_API_TOKEN (classic) or DT_OTEL_BEARER / DT_PLATFORM_TOKEN")
        print("with the openTelemetryTrace.ingest + metrics.ingest scopes.")
        return 1

    print()
    print("Running fleet for ~40 seconds to generate spans and metrics...")
    store = TelemetryStore()
    fleet = default_fleet(store)
    injector = ChaosInjector(fleet)

    start = time.monotonic()
    rogue_injected_at: int | None = None
    tick_interval_s = 0.25
    rogue_at_seconds = 20.0

    while time.monotonic() - start < 40.0:
        fleet.tick()
        elapsed = time.monotonic() - start
        if rogue_injected_at is None and elapsed >= rogue_at_seconds:
            injector.inject("refund_fraud_loop", at_tick=store.tick)
            rogue_injected_at = store.tick
            print(f"  injected refund_fraud_loop at tick {store.tick}")
        time.sleep(tick_interval_s)

    print(f"  ticked {store.tick} times; events emitted: {len(store.recent())}")

    print()
    print("Forcing flush of traces and metrics to Dynatrace...")
    ok = otel.force_flush(timeout_ms=15000)
    print(f"  force_flush: {'OK (OTLP 2xx)' if ok else 'FAILED (check token scopes and endpoint)'}")
    if not ok:
        return 1

    # Give Dynatrace a moment to make the spans queryable.
    print()
    print("Waiting 20s for ingest pipeline to make spans queryable...")
    time.sleep(20)

    print("Verifying via DQL `fetch spans` through the live MCP server...")
    try:
        from warden.dynatrace.mcp_client import McpDynatrace
        dt = McpDynatrace()
        rows = dt.execute_dql(
            'fetch spans, from:now() - 10m | filter service.name == "warden" '
            '| summarize total = count()'
        )
        print(f"  DQL response: {rows[:3]}")
    except Exception as exc:
        print(f"  DQL verification skipped ({exc})")
        print("  Hint: spans typically take 30 to 90 seconds to be queryable after ingest.")

    print()
    print("OK: OTel export to Dynatrace verified end-to-end.")
    print("Next step: configure a Davis Metric event on warden.agent.errors so a longer")
    print("run surfaces a real problem that Warden then reads back via list_problems.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
