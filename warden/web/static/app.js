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
    b.innerHTML = `${s.label}<small><b>${s.agent_id}</b>: ${s.description}</small>`;
    b.onclick = () => fetch("/api/inject", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: key }),
    });
    el.appendChild(b);
  });
}

let LATEST_INCIDENTS = [];

function renderMetrics(summary) {
  $("m-incidents").textContent = summary.incidents;
  $("m-mttd").textContent = summary.avg_mttd_ticks == null ? "n/a" : summary.avg_mttd_ticks + " ticks";
  $("m-recovered").textContent = money(summary.dollars_recovered);
  $("m-loss").textContent = money(summary.irreversible_loss);
  $("m-prevented").textContent = money(summary.projected_loss_prevented);
}

function renderIncidents(incidents) {
  LATEST_INCIDENTS = incidents || [];
  const el = $("incidents");
  el.innerHTML = "";
  if (!incidents.length) { el.innerHTML = `<p class="dim">No incidents yet. Inject a scenario to watch Warden respond.</p>`; return; }
  incidents.slice().reverse().forEach((i) => {
    const approved = i.human_approval_required
      ? (i.human_approved ? `<span class="ok">approved</span>` : `<span class="no">denied/pending</span>`)
      : "n/a (autonomous)";
    const mttd = i.mttd_ticks == null ? "n/a" : i.mttd_ticks + " ticks";
    const card = document.createElement("div");
    card.className = "incident clickable";
    card.title = "Click for full diagnosis, plan, and actions";
    card.innerHTML = `
      <div class="ihead"><span>${i.incident_id} · ${i.suspect_agent}</span><span>sev ${i.diagnosis.severity}</span></div>
      <div class="imeta">
        ${i.diagnosis.failure_class}<br/>
        MTTD: ${mttd}, reasoned by ${i.diagnosis.reasoned_by}<br/>
        human approval: ${approved}<br/>
        <span class="ok">recovered ${money(i.dollars_recovered)}</span> ·
        <span class="no">lost ${money(i.irreversible_loss_at_detection)}</span><br/>
        prevented (est.) ${money(i.projected_loss_prevented)}
      </div>`;
    card.onclick = () => openIncident(i.incident_id);
    el.appendChild(card);
  });
}

function openIncident(id) {
  const i = LATEST_INCIDENTS.find(x => x.incident_id === id);
  if (!i) return;
  const d = i.diagnosis;
  const planRows = (i.plan && i.plan.actions || []).map(a =>
    `<tr><td>${a.kind}${a.needs_approval ? ' <span class="no">(needs approval)</span>' : ''}</td><td>${escapeHtml(a.detail || '')}</td></tr>`
  ).join('');
  const actionRows = (i.actions_taken || []).map(a =>
    `<tr><td>${a.action}</td><td>${a.agent || ''}</td><td>${a.ok === false ? '<span class="no">withheld</span>' : '<span class="ok">ok</span>'}</td><td>${escapeHtml(a.detail || '')}</td></tr>`
  ).join('');
  $("modal-body").innerHTML = `
    <h2>${i.incident_id} on ${i.suspect_agent}</h2>
    <p class="dim">Detected at tick ${i.detect_tick}, onset tick ${i.onset_tick == null ? 'n/a' : i.onset_tick}, MTTD ${i.mttd_ticks == null ? 'n/a' : i.mttd_ticks + ' ticks'}, reasoned by ${d.reasoned_by}.</p>
    <h3>Diagnosis</h3>
    <table class="kv">
      <tr><th>failure class</th><td>${d.failure_class}</td></tr>
      <tr><th>severity</th><td>${d.severity}</td></tr>
      <tr><th>blast radius</th><td>${money(d.blast_radius_usd)}</td></tr>
      <tr><th>reversible</th><td>${d.reversible}</td></tr>
      <tr><th>recommended</th><td>${d.recommended_action}</td></tr>
      <tr><th>confidence</th><td>${d.confidence}</td></tr>
    </table>
    <p>${escapeHtml(d.summary || '')}</p>
    <h3>Plan: ${escapeHtml(i.plan && i.plan.rationale || '')}</h3>
    <table class="plan"><thead><tr><th>step</th><th>detail</th></tr></thead><tbody>${planRows}</tbody></table>
    <h3>Actions taken</h3>
    <table class="plan"><thead><tr><th>kind</th><th>agent</th><th>result</th><th>detail</th></tr></thead><tbody>${actionRows}</tbody></table>
    <h3>Measured outcome</h3>
    <table class="kv">
      <tr><th>$ recovered (hard)</th><td class="ok">${money(i.dollars_recovered)}</td></tr>
      <tr><th>$ irreversible loss</th><td class="no">${money(i.irreversible_loss_at_detection)}</td></tr>
      <tr><th>$ projected loss prevented</th><td>${money(i.projected_loss_prevented)} <span class="dim">(estimate)</span></td></tr>
    </table>`;
  $("modal").classList.remove("hidden");
}

function closeIncident() { $("modal").classList.add("hidden"); }
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

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
      feedLine("chaos", `&#9888; <b>${payload.agent}</b> went ROGUE: ${payload.label}`);
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
      feedLine("action", `${payload.action} on ${payload.agent}${payload.dollars_recovered ? ", recovered " + money(payload.dollars_recovered) : ""}`);
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
$("reset-btn").onclick = async () => {
  const btn = $("reset-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = "Resetting...";
  closeIncident();
  hideApproval();
  const grid = document.querySelector("main.grid");
  grid.classList.add("resetting");
  try {
    await fetch("/api/reset", { method: "POST" });
    await new Promise(r => setTimeout(r, 450));
  } catch (_) { /* network blip is fine, button still re-enables below */ }
  grid.classList.remove("resetting");
  btn.disabled = false;
  btn.textContent = original;
};
$("modal-close").onclick = closeIncident;
$("modal").onclick = (e) => { if (e.target.id === "modal") closeIncident(); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeIncident(); });

(async function init() {
  const s = await (await fetch("/api/state")).json();
  $("mode-badge").textContent = "mode: " + (s.mode || "sim");
  renderScenarios(s.scenarios);
  await refreshState();
  connect();
})();
