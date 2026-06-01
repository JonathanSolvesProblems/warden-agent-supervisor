# Deploying Warden (LIVE mode)

Warden runs the identical supervisory loop in two modes. `sim` needs nothing.
`live` swaps in **Gemini** (via the `gemini-flash-latest` / `gemini-pro-latest` aliases) as the brain and the **real
Dynatrace MCP server** as the senses. This doc covers going live + deploying to
Google Cloud.

## 1. Prerequisites

- Google Cloud project with **Vertex AI / Gemini Enterprise Agent Platform** enabled.
- A **Dynatrace** tenant (free trial: https://www.dynatrace.com/signup/) with a
  platform token, scopes per the MCP server README
  (`storage:*:read`, `automation:workflows:read`, `davis-copilot:conversations:execute`,
  `email:emails:send`, …).
- **Node v22.10+** (the Dynatrace MCP server runs via `npx`).
- Python 3.12 or 3.13 (Google ADK targets 3.10–3.13; use a venv if your host is 3.14).

## 2. Configure

```bash
cp .env.example .env
# set WARDEN_MODE=live, GOOGLE_CLOUD_PROJECT, DT_ENVIRONMENT, DT_PLATFORM_TOKEN
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Smoke-test the brain + senses wiring:

```bash
WARDEN_MODE=live python -m scripts.demo --ticks 20
# on connect you should see: "[warden] connected to Dynatrace MCP server; N tools: ..."
```

> Tool argument names differ slightly across MCP server versions. `McpDynatrace`
> introspects and logs the available tools on connect; confirm names with
> `list_tools()` and adjust `warden/dynatrace/mcp_client.py` if your server
> version differs.

## 3. The canonical Agent Builder / ADK pattern

Warden ships this as a real code artifact, not a docs snippet: see
[`warden/adk_agent.py`](../warden/adk_agent.py). That file defines an ADK
`LlmAgent` powered by Gemini 3 (via `gemini-flash-latest`), wired to the
Dynatrace MCP server via `McpToolset` with a `tool_filter` enforcing least
privilege on the four tools Warden actually invokes. It is the deployment
target for Agent Runtime / Agent Engine. To build the agent:

```python
from warden.adk_agent import build_warden_agent

agent = build_warden_agent()
```

The supervisory loop in `warden/supervisor/loop.py` is the deterministic
governance harness that runs in the demo today; both entry points use the
same Gemini 3 family models and the same Dynatrace MCP server.

## 4. Deploy to Google Cloud

**Option A: Cloud Run (the web dashboard + API):**

```bash
gcloud run deploy warden \
  --source . \
  --set-env-vars WARDEN_MODE=live,GOOGLE_CLOUD_PROJECT=$PROJECT,DT_ENVIRONMENT=$DT \
  --set-secrets DT_PLATFORM_TOKEN=dt-token:latest \
  --region us-central1 --allow-unauthenticated
```

Put `DT_PLATFORM_TOKEN` and any keys in **Secret Manager**; never commit them.
The web server reads `WARDEN_WEB_PORT` (Cloud Run sets `$PORT`, map it).

**Option B: Agent Runtime / Agent Engine:** deploy the ADK agent from §3 to the
managed runtime for long-running, stateful supervision; front it with the Cloud
Run dashboard for the operator console.

## 5. Self-observability (closing the loop)

Instrument Warden itself with OpenTelemetry and export to Dynatrace, so the
supervisor is observable too. See Dynatrace's AI-agent instrumentation examples:
https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples
