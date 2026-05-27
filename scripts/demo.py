"""Warden end-to-end demo.

Spins up a worker-agent fleet, runs it healthy for a while, injects a rogue
scenario, and lets Warden detect, diagnose, and contain it live in the terminal.

    python -m scripts.demo
    python -m scripts.demo --inject price_collapse --deny-approval
    python -m scripts.demo --ticks 40 --inject-at 10 --seed 7

Runs in SIMULATION mode by default (no cloud). Set WARDEN_MODE=live (+ .env) to
run the identical loop against real Gemini + a real Dynatrace tenant.
"""

from __future__ import annotations

import argparse
import sys

# Be robust on Windows consoles (cp1252) so output never crashes on a stray glyph.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from warden import config
from warden.agents.workers import default_fleet
from warden.chaos.injector import SCENARIOS, ChaosInjector
from warden.dynatrace import build_dynatrace
from warden.supervisor.loop import AutoApproveGate, Warden
from warden.telemetry.store import TelemetryStore

BAR = "=" * 78


def make_observer():
    icons = {
        "sense": "SENSE   ",
        "diagnose": "DIAGNOSE",
        "plan": "PLAN    ",
        "approval_request": "APPROVAL",
        "approval_result": "APPROVAL",
        "action": "ACT     ",
        "incident": "INCIDENT",
    }

    def observer(event_type: str, payload: dict) -> None:
        tag = icons.get(event_type, event_type.upper())
        if event_type == "sense":
            handled = set(payload.get("handled", []))
            new = [p for p in payload["problems"] if p["affectedEntity"] not in handled]
            if new:  # stay quiet once an agent is contained, even if it lingers in the window
                titles = ", ".join(p["title"] for p in new[:3])
                print(f"  [{tag}] tick {payload['tick']}: Dynatrace flags {len(new)} new problem(s): {titles}")
        elif event_type == "diagnose":
            d = payload["diagnosis"]
            print(f"  [{tag}] {d['suspect_agent']}: {d['failure_class']} "
                  f"(sev {d['severity']}, ${d['blast_radius_usd']:,.2f} at risk, "
                  f"{'reversible' if d['reversible'] else 'IRREVERSIBLE'}, "
                  f"conf {d['confidence']}, by {d['reasoned_by']})")
        elif event_type == "plan":
            kinds = " -> ".join(a["kind"] + ("*" if a["needs_approval"] else "") for a in payload["actions"])
            print(f"  [{tag}] {payload['rationale']}")
            print(f"           steps: {kinds}   (* = needs human approval)")
        elif event_type == "approval_request":
            for a in payload["gated"]:
                print(f"  [{tag}] >>> HUMAN-IN-THE-LOOP requested: {a['detail']}")
        elif event_type == "approval_result":
            verdict = "APPROVED" if payload["approved"] else "DENIED"
            print(f"  [{tag}] <<< Operator {verdict}")
        elif event_type == "action":
            extra = ""
            if payload.get("action") == "rollback":
                extra = f" ({payload['reversed_actions']} actions, ${payload['dollars_recovered']:,.2f} recovered)"
            print(f"  [{tag}] {payload.get('action')} on {payload.get('agent')}"
                  f"{' OK' if payload.get('ok') else ' PENDING'}{extra}")
        elif event_type == "incident":
            print(f"  [{tag}] {payload['incident_id']} opened for {payload['suspect_agent']} "
                  f"(MTTD {payload['mttd_ticks']} ticks)")

    return observer


def main() -> None:
    parser = argparse.ArgumentParser(description="Warden demo")
    parser.add_argument("--ticks", type=int, default=30, help="total simulation ticks")
    parser.add_argument("--inject", default="refund_fraud_loop", choices=list(SCENARIOS),
                        help="rogue scenario to inject")
    parser.add_argument("--inject-at", type=int, default=9, help="tick at which to go rogue")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed for reproducibility")
    parser.add_argument("--deny-approval", action="store_true",
                        help="operator DENIES the human-gated step (shows the gate holding)")
    args = parser.parse_args()

    print(BAR)
    print(f" WARDEN - agent-reliability supervisor   [mode: {config.mode()}]")
    print(BAR)
    print(f" Scenario   : {SCENARIOS[args.inject].label} on {SCENARIOS[args.inject].agent_id}")
    print(f"              {SCENARIOS[args.inject].description}")
    print(f" Injecting  : tick {args.inject_at}   |   horizon: {args.ticks} ticks")
    print(BAR)

    store = TelemetryStore()
    fleet = default_fleet(store, seed=args.seed)
    dt = build_dynatrace(store)
    injector = ChaosInjector(fleet)
    gate = AutoApproveGate(approve=not args.deny_approval)
    warden = Warden(fleet, dt, store, gate=gate, injector=injector, observer=make_observer())

    for _ in range(args.ticks):
        fleet.tick()
        if store.tick == args.inject_at:
            sc = injector.inject(args.inject, at_tick=store.tick)
            print(f"\n  !! CHAOS @ tick {store.tick}: {sc.agent_id} has gone rogue ({sc.label}) !!\n")
        warden.step()

    print("\n" + BAR)
    print(" INCIDENT REPORT")
    print(BAR)
    for inc in warden.log.incidents:
        d = inc.to_dict()
        print(f" {d['incident_id']}  agent={d['suspect_agent']}  "
              f"class={d['diagnosis']['failure_class']}  sev={d['diagnosis']['severity']}")
        print(f"   detected tick {d['detect_tick']} (onset {d['onset_tick']}, MTTD {d['mttd_ticks']} ticks)")
        print(f"   human approval: required={d['human_approval_required']} approved={d['human_approved']}")
        print(f"   $ recovered (hard)            : ${d['dollars_recovered']:,.2f}")
        print(f"   $ irreversible loss at detect : ${d['irreversible_loss_at_detection']:,.2f}")
        print(f"   $ projected loss prevented*   : ${d['projected_loss_prevented']:,.2f}  (*estimate)")
        print(f"   final state of {d['suspect_agent']}: {fleet.states().get(d['suspect_agent'])}")

    s = warden.log.summary()
    print("\n" + BAR)
    print(" FLEET OUTCOME")
    print(BAR)
    print(f" incidents handled         : {s['incidents']}")
    print(f" avg time-to-detect        : {s['avg_mttd_ticks']} ticks")
    print(f" $ recovered (hard)        : ${s['dollars_recovered']:,.2f}")
    print(f" $ irreversible loss       : ${s['irreversible_loss']:,.2f}")
    print(f" $ projected loss prevented: ${s['projected_loss_prevented']:,.2f}  (estimate)")
    notes = getattr(dt, "sent_notifications", [])
    print(f" Dynatrace notifications    : {len(notes)} sent")
    print(f" final fleet states         : {fleet.states()}")
    print(BAR)


if __name__ == "__main__":
    main()
