"""Background simulation runner + event bus + interactive approval gate.

Drives the fleet/Warden loop on a timer in a daemon thread, fans Warden's
reasoning out to connected dashboards over an event bus, and blocks on real
human approval when policy demands it.
"""

from __future__ import annotations

import json
import queue
import threading
import time

from .. import config
from ..agents.workers import default_fleet
from ..chaos.injector import SCENARIOS, ChaosInjector
from ..dynatrace import build_dynatrace
from ..supervisor.loop import Warden
from ..telemetry.store import TelemetryStore

MAX_HISTORY = 300


class WebApprovalGate:
    """Blocks Warden until an operator clicks Approve/Deny in the dashboard."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._decision = False
        self.pending: dict | None = None

    def request(self, incident_preview: dict, gated_actions) -> bool:
        self.pending = {
            "incident": incident_preview,
            "gated": [a.__dict__ for a in gated_actions],
        }
        self._decision = False
        self._event.clear()
        self._event.wait()  # park here until decide() is called from an HTTP handler
        self.pending = None
        return self._decision

    def decide(self, approved: bool) -> None:
        self._decision = approved
        self._event.set()


class SimRunner:
    def __init__(self, tick_interval: float = 0.9) -> None:
        self.tick_interval = tick_interval
        self._subscribers: list[queue.Queue] = []
        self._history: list[dict] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self.gate = WebApprovalGate()
        self._build()

    # --- lifecycle -----------------------------------------------------------
    def _build(self) -> None:
        self.store = TelemetryStore()
        self.fleet = default_fleet(self.store)
        self.dt = build_dynatrace(self.store)
        self.injector = ChaosInjector(self.fleet)
        self.warden = Warden(
            self.fleet, self.dt, self.store,
            gate=self.gate, injector=self.injector, observer=self._publish,
        )

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def reset(self) -> None:
        self._running = False
        time.sleep(self.tick_interval + 0.1)
        with self._lock:
            self._history.clear()
        self.gate = WebApprovalGate()
        self._build()
        self._publish("reset", {"message": "fleet reset"})
        self.start()

    def _loop(self) -> None:
        while self._running:
            self.fleet.tick()
            self._publish("tick", {"tick": self.store.tick, "states": self.fleet.states()})
            self.warden.step()
            time.sleep(self.tick_interval)

    # --- controls ------------------------------------------------------------
    def inject(self, scenario_key: str) -> dict:
        if scenario_key not in SCENARIOS:
            return {"ok": False, "error": f"unknown scenario {scenario_key}"}
        sc = self.injector.inject(scenario_key, at_tick=self.store.tick)
        self._publish("chaos", {"scenario": sc.key, "agent": sc.agent_id,
                               "label": sc.label, "tick": self.store.tick})
        return {"ok": True, "scenario": sc.key, "agent": sc.agent_id}

    def decide(self, approved: bool) -> dict:
        self.gate.decide(approved)
        return {"ok": True, "approved": approved}

    # --- event bus -----------------------------------------------------------
    def _publish(self, event_type: str, payload: dict) -> None:
        msg = {"type": event_type, "payload": payload, "ts": time.time()}
        with self._lock:
            self._history.append(msg)
            if len(self._history) > MAX_HISTORY:
                self._history = self._history[-MAX_HISTORY:]
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            # Backfill recent history so a fresh dashboard isn't blank.
            for msg in self._history[-80:]:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    break
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    # --- snapshot for late joiners / polling ---------------------------------
    def snapshot(self) -> dict:
        return {
            "mode": config.mode(),
            "tick": self.store.tick,
            "states": self.fleet.states(),
            "summary": self.warden.log.summary(),
            "incidents": [i.to_dict() for i in self.warden.log.incidents],
            "pending_approval": self.gate.pending,
            "scenarios": {k: {"label": v.label, "agent_id": v.agent_id,
                              "description": v.description} for k, v in SCENARIOS.items()},
        }

    @staticmethod
    def sse(msg: dict) -> bytes:
        return f"data: {json.dumps(msg)}\n\n".encode("utf-8")
