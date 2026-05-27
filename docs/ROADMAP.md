# Build roadmap (16 days to June 11)

Status of the Warden build for the Google Cloud Rapid Agent Hackathon.

## Done: runnable today (simulation mode, zero credentials)

- [x] Telemetry store + reversible action ledger (`warden/telemetry`)
- [x] Dynatrace tool contract + mock that mirrors the real MCP tool surface (`warden/dynatrace`)
- [x] Worker-agent fleet (Refund / Pricing / Inventory), OTel-style signals (`warden/agents`)
- [x] Chaos injector with three realistic rogue scenarios (`warden/chaos`)
- [x] Warden loop: sense → reason → decide → act → prove (`warden/supervisor`)
  - [x] Scripted brain (offline) **and** Gemini brain (`gemini_brain.py`)
  - [x] Governance policy with autonomous vs. human-gated actions
  - [x] Interventions: pause / rollback / alert / workflow
  - [x] Incident ledger with **measured** outcomes (MTTD, $ recovered, $ lost, est. prevented)
- [x] CLI demo across all scenarios + the deny-approval path (`scripts/demo.py`)
- [x] Web dashboard: live SSE reasoning feed + interactive Approve/Deny gate (`warden/web`)
- [x] Live adapters: Gemini brain + Dynatrace MCP client (`mcp_client.py`)
- [x] Tests (`tests/`)

## Next: to harden for submission

- [ ] Validate LIVE mode against a real Dynatrace tenant; confirm MCP tool arg schemas.
- [ ] Deploy the canonical ADK `LlmAgent` + `McpToolset` (docs/DEPLOY.md §3) to Agent Runtime.
- [ ] Instrument Warden itself with OpenTelemetry → Dynatrace (self-observability).
- [ ] Ship to Cloud Run with Secret Manager; wire `$PORT`.
- [ ] Record the ≤3-min demo video: healthy fleet → inject rogue → catch in 1 tick →
      human approves clawback → measured-impact ledger.
- [ ] Optional second domain skin (2026 World Cup fan-services agents) for the "wow".

## Submission checklist (from the rules)

- [ ] Public repo, OSI license visible in About, Apache-2.0 present (`LICENSE`).
- [ ] Hosted/testable URL (Cloud Run).
- [ ] ≤3-min demo video (English / subtitled).
- [ ] Writeup: features, tech, data sources, learnings.
- [ ] Track selected: **Dynatrace**.
- [ ] Built with Gemini + Google Cloud Agent Builder + a partner MCP server. ✓ by design.
