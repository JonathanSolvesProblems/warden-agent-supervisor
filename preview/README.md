# Preview screenshots

Screenshots captured from the real `xwy37883.apps.dynatrace.com` tenant, used in the demo video and Devpost gallery as proof that Warden's worker fleet is shipping live OpenTelemetry into Dynatrace.

Save each image into this folder with the canonical filename so the demo-video script and the Devpost gallery captions stay consistent.

| Suggested filename | What it shows | Demo-video beat |
|---|---|---|
| `warden-spans-list-808.png` | Distributed Tracing app, Spans view, `service.name = "warden"` filter, 400+ spans per `otel_smoke.py` run, timeseries chart with one or more activity bursts | Around 1:20, when narrating "every action emits a span" |
| `warden-span-detail.png` | Single `agent.action` span opened in the side pane, Core section showing span kind / name / duration / start / end | Around 1:30, when zooming in on a single agent action |
| `warden-metrics-by-agent.png` | Notebooks DQL chart: `timeseries actions = sum(warden.agent.actions), by: { agent.id }`, three colored series (inventory-agent / pricing-agent / refund-agent) | Around 1:40, when claiming "measured per agent, not just totals" |

Also reasonable additions if captured later:
- `warden-dashboard-incident.png`: Warden's own operator console with an open INCIDENT modal.
- `warden-davis-copilot.png`: Davis Copilot's response in `live_check` (terminal capture is fine).
- `warden-gemini-diagnosis.png`: the Gemini brain's structured Diagnosis output from `live_check`.

These screenshots are kept in the public repo so judges browsing GitHub can verify the integration immediately without running anything.

The same screenshots also power the dashboard's **Live Evidence** tab. Drop any of the canonical filenames above into this folder and they activate automatically on the hosted URL at `/preview/<filename>`; the rest stay rendered as styled placeholder cards.

The Devpost gallery cover is also generated into this folder as `cover.png`. Regenerate it from the JetBrains Mono fonts in `preview/.fonts/` with:

```bash
python -m scripts.generate_cover
```
