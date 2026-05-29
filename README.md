# Warden: the agent that governs your agents

Warden is an autonomous agent-reliability supervisor. It uses Gemini (via the
`gemini-flash-latest` and `gemini-pro-latest` aliases on Google Cloud Agent Builder
/ Vertex) and watches a fleet of production AI agents through the Dynatrace MCP
server. When one agent goes rogue, Warden catches it, diagnoses it, and contains it
under human oversight before it does more damage.

Submission for the Google Cloud Rapid Agent Hackathon (Dynatrace track).

## The problem

This hackathon is about agents that take real actions in production. That raises a
question almost no one is answering: once you have a fleet of autonomous agents
acting on real systems (approving refunds, changing prices, moving inventory), who
watches them?

Today the answer is "a human, eventually, after the damage shows up on a
dashboard." That does not scale to a fleet of agents running 24/7. Warden is the
missing supervisory layer. It treats every worker agent as an untrusted actor,
grounds its judgment in live production telemetry from Dynatrace, and acts the
moment an agent's behavior goes out of policy.

## The loop

```
        Worker agent fleet:  RefundAgent   PricingAgent   InventoryAgent ...
              |  each emits OpenTelemetry (traces, metrics, logs, actions)
              v
        Dynatrace  <----  list_problems / execute_dql / chat_with_davis_copilot
              ^ (MCP server)                                            |
              |                                                         |
        WARDEN  (Gemini reasoning via google-genai SDK)                 |
          1. SENSE    pull problems + telemetry from Dynatrace via MCP  |
          2. REASON   classify: which agent, what failure, blast radius |
          3. DECIDE   apply policy: act autonomously, or ask a human  --+
          4. ACT      pause / roll back / alert / open a workflow
          5. PROVE    measured incident report: MTTD, $ recovered, $ lost
```

Warden is agentic, not a dashboard. It plans, calls tools, and takes action, while
keeping a human in control for anything irreversible.

## Design choice that matters: deterministic vs. generative

Gemini supplies judgment (failure class, severity, recommended action, plain
language summary). The dollar figures and reversibility are computed
deterministically in Python from the telemetry. The model never invents money
math. This keeps the impact numbers honest and prevents prompt injection inside an
agent's telemetry from inflating a blast radius.

## Why this fits the Dynatrace track

1. The partner MCP is load-bearing, not bolted on. Remove Dynatrace and Warden is
   blind, because telemetry is its only sense organ.
2. It extends Dynatrace's own direction. Dynatrace already monitors AI agents;
   Warden adds the next step, which is governing and remediating them.
3. It proves impact instead of claiming it. Every run produces hard numbers (time
   to detect, dollars recovered, dollars lost), not adjectives.

## Run it in simulation mode (no cloud, no credentials)

The simulation engine is pure Python standard library, so it runs on Python 3.11
through 3.14 with nothing to install.

```bash
python -m warden.web.app        # live dashboard at http://127.0.0.1:8080
python -m scripts.demo          # CLI: watch Warden catch a rogue agent
python -m scripts.demo --inject price_collapse        # reversible: shows $ recovered
python -m scripts.demo --inject refund_fraud_loop --deny-approval   # deny the human gate
python -m scripts.bench         # quantified detection rate + false-positive rate
python -m unittest discover -s tests -v               # tests
```

### Measured performance (`python -m scripts.bench --episodes 30`)

| Metric | Result |
|---|---|
| False-positive rate (30 healthy episodes, no injection) | **0.00%** |
| Detection rate, refund fraud | **100%** |
| Detection rate, price collapse | **100%** |
| Detection rate, inventory over-order | **100%** |
| Cross-fleet noise (innocent agents flagged) | 0 |
| Median time-to-detect | **1 tick** (p95: 1 to 3) |
| Median $ recovered, reversible scenarios | $336 to $409 |
| Median $ lost at detect, irreversible refund fraud | $2,156 |

In the dashboard: click an "Inject a rogue scenario" button, watch the live
reasoning feed, and click Approve or Deny when the human-in-the-loop bar appears.

The mock Dynatrace mirrors the real MCP tool surface (`list_problems`,
`execute_dql`, `chat_with_davis_copilot`, and the rest), so the exact same Warden
logic runs locally and against a real tenant.

## Run it in live mode (real Gemini + real Dynatrace MCP)

Google ADK targets Python 3.10 to 3.13, so use a 3.12 or 3.13 virtual env for the
ADK deploy path.

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
copy .env.example .env                             # set GCP + Dynatrace values
set WARDEN_MODE=live
python -m scripts.live_check                       # smoke test: MCP handshake + tool calls
python -m scripts.demo                             # full loop against real Dynatrace
```

See [docs/DEPLOY.md](docs/DEPLOY.md) for the canonical ADK + MCP toolset pattern and
Cloud Run / Agent Runtime deployment.

## Architecture

| Layer | Component | Tech |
|---|---|---|
| Brain | `warden/supervisor` | Gemini via the `google-genai` SDK (Flash on the loop, Pro on Vertex paid quota), with a scripted fallback for offline dev |
| Senses | `warden/dynatrace` | Dynatrace MCP server (mock mirror for offline dev) |
| Hands | `warden/supervisor/interventions.py` | pause / rollback / alert behind a human-approval gate |
| Subjects | `warden/agents` | simulated worker-agent fleet, OpenTelemetry-instrumented |
| Stress | `warden/chaos` | injects realistic rogue-agent scenarios |
| Surface | `warden/web` | stdlib HTTP server, server-sent-events live console |
| Deploy | docs/DEPLOY.md | Agent Runtime or Cloud Run, with Secret Manager |

## Status

Core is complete and runs offline. The CLI demo, the web dashboard, and the test
suite are all verified. The **live Dynatrace MCP handshake is now verified**
against a real tenant: 20 tools enumerated, `list_problems`, `execute_dql`, and
`chat_with_davis_copilot` all return live data (`python -m scripts.live_check`).
Still pending: wiring the worker-agent fleet's OpenTelemetry exporter to push
real telemetry into Dynatrace, plus Cloud Run deploy. See
[docs/ROADMAP.md](docs/ROADMAP.md).

## License

[Apache 2.0](LICENSE).
