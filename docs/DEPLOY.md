# Deploying Warden (LIVE mode)

Warden runs the identical supervisory loop in two modes. `sim` needs nothing.
`live` swaps in **Gemini 3** (the required model) as the brain and the **real
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

## 3. The canonical Agent Builder / ADK pattern (for judges)

Warden uses an explicit governance loop (deterministic safety + human-in-the-loop)
with Gemini for judgment. The same Dynatrace MCP server is what an ADK `LlmAgent`
consumes natively. Include this in the submission to show the blessed path:

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

warden_agent = LlmAgent(
    model="gemini-flash-latest",            # Gemini 3 Flash for the monitoring loop
    name="warden",
    instruction="Supervise the agent fleet; contain rogue agents under human oversight.",
    tools=[McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@dynatrace-oss/dynatrace-mcp-server@latest"],
                env={"DT_ENVIRONMENT": "...", "DT_PLATFORM_TOKEN": "..."},
            )),
        tool_filter=["list_problems", "execute_dql",
                     "chat_with_davis_copilot", "create_workflow_for_notification"],
    )],
)
```

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
