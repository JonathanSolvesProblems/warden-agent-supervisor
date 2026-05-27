"use strict";

const $ = (id) => document.getElementById(id);
const money = (n) => "$" + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });

const AGENT_DOMAINS = {
  "refund-agent": "payments",
  "pricing-agent": "merchandising",
  "inventory-agent": "supply chain",
};

function feedLine(type, html) {
  const feed = $("feed");
  const div = document.createElement("div");
  div.className = "line " + type;
  div.innerHTML = `<span class="tag ${type}">${type.toUpperCase()}</span>${html}`;
  feed.prepend(div);
  while (feed.children.length > 120) feed.removeChild(feed.lastChild);
}

function renderFleet(states) {
  const el = $("fleet");
  el.innerHTML = "";
  Object.entries(states).forEach(([id, state]) => {
    const card = document.createElement("div");
    card.className = "agent" + (state === "rogue" ? " rogue" : "");
    card.innerHTML = `
      <div>
        <div class="name">${id}</div>
        <div class="domain">${AGENT_DOMAINS[id] || ""}</div>
      </div>
      <span class="state ${state}">${state}</span>`;
    el.appendChild(card);
  });
}

function renderScenarios(scenarios) {
  const el = $("scenarios");
  el.innerHTML = "";
  Object.entries(scenarios).forEach(([key, s]) => {
    const b = document.createElement("button");
    b.className = "btn scenario-btn";
    b.innerHTML = `${s.label}<small>${s.agent_id} — ${s.description}</small>`;
    b.onclick = () => fetch("/api/inject", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: key }),
    });
    el.appendChild(b);
  });
}

function renderMetrics(summary) {
  $("m-incidents").textContent = summary.incidents;
  $("m-mttd").textContent = summary.avg_mttd_ticks == null ? "—" : summary.avg_mttd_ticks + " ticks";
  $("m-recovered").textContent = money(summary.dollars_recovered);
  $("m-loss").textContent = money(summary.irreversible_loss);
  $("m-prevented").textContent = money(summary.projected_loss_prevented);
}

function renderIncidents(incidents) {
  const el = $("incidents");
  el.innerHTML = "";
  if (!incidents.length) { el.innerHTML = `<p class="dim">No incidents yet. Inject a scenario to watch Warden respond.</p>`; return; }
  incidents.slice().reverse().forEach((i) => {
    const approved = i.human_approval_required
      ? (i.human_approved ? `<span class="ok">approved</span>` : `<span class="no">denied/pending</span>`)
      : "n/a (autonomous)";
    const card = document.createElement("div");
    card.className = "incident";
    card.innerHTML = `
      <div class="ihead"><span>${i.incident_id} · ${i.suspect_agent}</span><span>sev ${i.diagnosis.severity}</span></div>
      <div class="imeta">
        ${i.diagnosis.failure_class}<br/>
        MTTD: ${i.mttd_ticks} ticks · reasoned by ${i.diagnosis.reasoned_by}<br/>
        human approval: ${approved}<br/>
        <span class="ok">recovered ${money(i.dollars_recovered)}</span> ·
        <span class="no">lost ${money(i.irreversible_loss_at_detection)}</span><br/>
        prevented (est.) ${money(i.projected_loss_prevented)}
      </div>`;
    el.appendChild(card);
  });
}

function showApproval(detail) {
  $("approval-detail").textContent = detail || "";
  $("approval-banner").classList.remove("hidden");
}
function hideApproval() { $("approval-banner").classList.add("hidden"); }

async function refreshState() {
  const s = await (await fetch("/api/state")).json();
  $("tick-badge").textContent = "tick " + s.tick;
  renderFleet(s.states);
  renderMetrics(s.summary);
  renderIncidents(s.incidents);
  if (s.pending_approval) {
    const g = (s.pending_approval.gated || [])[0];
    showApproval(g ? g.detail : "Operator approval required.");
  } else { hideApproval(); }
}

function handleEvent(msg) {
  const { type, payload } = msg;
  switch (type) {
    case "tick":
      $("tick-badge").textContent = "tick " + payload.tick;
      renderFleet(payload.states);
      break;
    case "chaos":
      feedLine("chaos", `&#9888; ${payload.agent} went ROGUE — ${payload.label}`);
      break;
    case "sense": {
      const n = (payload.problems || []).filter(p => !(payload.handled || []).includes(p.affectedEntity));
      if (n.length) feedLine("sense", `Dynatrace flags: ${n.map(p => p.title).join("; ")}`);
      break;
    }
    case "diagnose": {
      const d = payload.diagnosis;
      feedLine("diagnose", `${d.suspect_agent}: <b>${d.failure_class}</b> (sev ${d.severity}, ${money(d.blast_radius_usd)} at risk, ${d.reversible ? "reversible" : "IRREVERSIBLE"}, by ${d.reasoned_by})`);
      break;
    }
    case "plan":
      feedLine("plan", `${payload.rationale}`);
      break;
    case "approval_request": {
      const g = (payload.gated || [])[0];
      feedLine("approval", `&#9995; awaiting human approval: ${g ? g.detail : ""}`);
      showApproval(g ? g.detail : "");
      break;
    }
    case "approval_result":
      feedLine("approval", `operator ${payload.approved ? "APPROVED" : "DENIED"}`);
      hideApproval();
      break;
    case "action":
      feedLine("action", `${payload.action} on ${payload.agent}${payload.dollars_recovered ? " — recovered " + money(payload.dollars_recovered) : ""}`);
      break;
    case "incident":
      feedLine("incident", `${payload.incident_id} opened for ${payload.suspect_agent} (MTTD ${payload.mttd_ticks} ticks)`);
      refreshState();
      break;
    case "reset":
      $("feed").innerHTML = "";
      refreshState();
      break;
  }
}

function connect() {
  const es = new EventSource("/events");
  es.onmessage = (e) => { try { handleEvent(JSON.parse(e.data)); } catch (_) {} };
  es.onerror = () => { /* browser auto-reconnects */ };
}

$("approve-btn").onclick = () => { fetch("/api/decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved: true }) }); hideApproval(); };
$("deny-btn").onclick = () => { fetch("/api/decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved: false }) }); hideApproval(); };
$("reset-btn").onclick = () => fetch("/api/reset", { method: "POST" });

(async function init() {
  const s = await (await fetch("/api/state")).json();
  $("mode-badge").textContent = "mode: " + (s.mode || "sim");
  renderScenarios(s.scenarios);
  await refreshState();
  connect();
})();
