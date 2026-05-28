"""Warden benchmark harness.

Quantifies detection rate, false-positive rate, and time-to-detect across many
seeded simulated episodes. These are the numbers the writeup quotes (rubric
dimension: measure performance, especially false positives, with a negative
control).

Run:
    python -m scripts.bench
    python -m scripts.bench --episodes 50 --horizon 30
"""

from __future__ import annotations

import argparse
import statistics
import sys

# Ensure stdout is UTF-8 safe on Windows.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from warden.agents.workers import default_fleet
from warden.chaos.injector import SCENARIOS, ChaosInjector
from warden.dynatrace.mock import MockDynatrace
from warden.supervisor.loop import AutoApproveGate, Warden
from warden.telemetry.store import TelemetryStore

BAR = "=" * 88


def run_episode(seed: int, inject_key: str | None = None,
                inject_at: int = 8, horizon: int = 25):
    store = TelemetryStore()
    fleet = default_fleet(store, seed=seed)
    dt = MockDynatrace(store)
    injector = ChaosInjector(fleet)
    warden = Warden(fleet, dt, store, gate=AutoApproveGate(True), injector=injector)
    for _ in range(horizon):
        fleet.tick()
        if inject_key and store.tick == inject_at:
            injector.inject(inject_key, at_tick=store.tick)
        warden.step()
    return warden, fleet


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(pct * (len(s) - 1)))))
    return s[idx]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=20, help="seeds per cell")
    ap.add_argument("--horizon", type=int, default=25, help="ticks per episode")
    ap.add_argument("--inject-at", type=int, default=8, help="tick at which to go rogue")
    args = ap.parse_args()
    N = args.episodes

    # --- Negative control: healthy fleet, no injection ---------------------
    healthy_episodes = 0
    healthy_incidents = 0
    healthy_per_agent: dict[str, int] = {}
    for seed in range(N):
        w, _ = run_episode(seed=seed, horizon=args.horizon)
        healthy_episodes += 1
        for inc in w.log.incidents:
            healthy_incidents += 1
            healthy_per_agent[inc.suspect_agent] = healthy_per_agent.get(inc.suspect_agent, 0) + 1
    fp_rate = healthy_incidents / healthy_episodes if healthy_episodes else 0.0

    # --- Detection per scenario --------------------------------------------
    rows = []
    for sc_key, sc in SCENARIOS.items():
        detected = 0
        wrong_agent = 0
        mttds, rec, irr = [], [], []
        for seed in range(N):
            w, _ = run_episode(seed=seed, inject_key=sc_key,
                               inject_at=args.inject_at, horizon=args.horizon)
            target = sc.agent_id
            hits = [i for i in w.log.incidents if i.suspect_agent == target]
            others = [i for i in w.log.incidents if i.suspect_agent != target]
            wrong_agent += len(others)
            if hits:
                detected += 1
                mttds.append(hits[0].mttd_ticks)
                rec.append(hits[0].dollars_recovered)
                irr.append(hits[0].irreversible_loss_at_detection)
        rows.append({
            "scenario": sc_key,
            "agent": sc.agent_id,
            "detect_rate": detected / N if N else 0.0,
            "wrong_agent_flags": wrong_agent,
            "median_mttd": statistics.median(mttds) if mttds else None,
            "p95_mttd": percentile(mttds, 0.95),
            "median_recovered": statistics.median(rec) if rec else 0.0,
            "median_irreversible": statistics.median(irr) if irr else 0.0,
        })

    # --- Print summary ------------------------------------------------------
    print(BAR)
    print(f" WARDEN BENCHMARK   episodes per cell: {N}   horizon: {args.horizon} ticks")
    print(BAR)
    print(" Negative control (healthy fleet, no injection):")
    print(f"   episodes                   : {healthy_episodes}")
    print(f"   incidents raised in total  : {healthy_incidents}")
    print(f"   false-positive rate        : {fp_rate * 100:.2f}%")
    if healthy_per_agent:
        per = ", ".join(f"{a}={n}" for a, n in healthy_per_agent.items())
        print(f"   incidents by agent         : {per}")
    print()
    print(" Detection (rogue injected at tick", args.inject_at, "):")
    print(f"   {'scenario':<22} {'agent':<16} {'detect':>7} {'mis-flag':>9}"
          f" {'med MTTD':>9} {'p95 MTTD':>9} {'med $rec':>11} {'med $lost':>11}")
    for r in rows:
        med = "-" if r["median_mttd"] is None else f"{r['median_mttd']:.1f}"
        p95 = "-" if r["p95_mttd"] is None else f"{r['p95_mttd']:.1f}"
        print(f"   {r['scenario']:<22} {r['agent']:<16}"
              f" {r['detect_rate'] * 100:6.1f}%"
              f" {r['wrong_agent_flags']:>9}"
              f" {med:>9} {p95:>9}"
              f" ${r['median_recovered']:>9,.2f}"
              f" ${r['median_irreversible']:>9,.2f}")
    print(BAR)
    print(" Reading the table:")
    print("   detect   = fraction of seeds where Warden correctly flagged the rogue agent")
    print("   mis-flag = total incidents opened against an INNOCENT agent (cross-fleet noise)")
    print("   MTTD     = time-to-detect in ticks, measured from rogue onset to incident open")
    print(BAR)


if __name__ == "__main__":
    main()
