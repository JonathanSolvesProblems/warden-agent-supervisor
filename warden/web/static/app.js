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
  const recEl = $("m-recovered");
  const recovered = Number(summary.dollars_recovered || 0);
  recEl.textContent = money(recovered);
  recEl.classList.toggle("has-value", recovered > 0); // warm gold when > 0
  $("m-loss").textContent = money(summary.irreversible_loss);
  $("m-prevented").textContent = money(summary.projected_loss_prevented);
}

function renderIncidents(incidents) {
  LATEST_INCIDENTS = incidents || [];
  const el = $("incidents");
  el.innerHTML = "";
  if (!incidents.length) {
    el.innerHTML = `
      <div class="incidents-empty">
        <p><span class="arrow">&larr;</span> Inject a scenario to watch Warden catch a rogue agent in real time.</p>
      </div>`;
    return;
  }
  incidents.slice().reverse().forEach((i) => {
    const isGated = i.human_approval_required;
    const pill = isGated
      ? `<span class="pill gated">HUMAN-GATED</span>`
      : `<span class="pill autonomous">AUTONOMOUS</span>`;
    const approved = isGated
      ? (i.human_approved ? `<span class="ok">approved</span>` : `<span class="no">denied/pending</span>`)
      : "n/a (autonomous)";
    const mttd = i.mttd_ticks == null ? "n/a" : i.mttd_ticks + " ticks";
    const card = document.createElement("div");
    card.className = "incident clickable";
    card.title = "Click for full diagnosis, plan, and actions";
    card.innerHTML = `
      <div class="ihead">
        <span>${i.incident_id} &middot; ${i.suspect_agent}${pill}</span>
        <span>sev ${i.diagnosis.severity}</span>
      </div>
      <div class="imeta">
        ${i.diagnosis.failure_class}<br/>
        MTTD: ${mttd}, reasoned by ${i.diagnosis.reasoned_by}<br/>
        human approval: ${approved}<br/>
        <span class="ok">recovered ${money(i.dollars_recovered)}</span> &middot;
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
  const card = document.querySelector(".modal-card");
  if (card) {
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-labelledby", "modal-title");
  }
  const d = i.diagnosis;
  const planRows = (i.plan && i.plan.actions || []).map(a =>
    `<tr><td>${a.kind}${a.needs_approval ? ' <span class="no">(needs approval)</span>' : ''}</td><td>${escapeHtml(a.detail || '')}</td></tr>`
  ).join('');
  const actionRows = (i.actions_taken || []).map(a =>
    `<tr><td>${a.action}</td><td>${a.agent || ''}</td><td>${a.ok === false ? '<span class="no">withheld</span>' : '<span class="ok">ok</span>'}</td><td>${escapeHtml(a.detail || '')}</td></tr>`
  ).join('');
  $("modal-body").innerHTML = `
    <h2 id="modal-title">${i.incident_id} on ${i.suspect_agent}</h2>
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

function pulseBrand() {
  const mark = document.querySelector(".brandmark");
  if (!mark) return;
  mark.classList.remove("pulse");
  void mark.offsetWidth;            // restart the animation if it's already running
  mark.classList.add("pulse");
}

function showApproval(detail) {
  $("approval-detail").textContent = detail || "";
  $("approval-banner").classList.remove("hidden");
}
function hideApproval() { $("approval-banner").classList.add("hidden"); }

function applyState(s) {
  $("mode-badge").textContent = "mode: " + (s.mode || "sim");
  $("mode-badge").classList.remove("loading");
  $("tick-badge").textContent = "tick " + s.tick;
  $("tick-badge").classList.remove("loading");
  renderFleet(s.states);
  renderMetrics(s.summary);
  renderIncidents(s.incidents);
  const placeholder = document.querySelector(".feed-placeholder");
  if (placeholder) placeholder.remove();
  if (s.pending_approval) {
    const g = (s.pending_approval.gated || [])[0];
    showApproval(g ? g.detail : "Operator approval required.");
  } else { hideApproval(); }
}

async function refreshState() {
  const s = await (await fetch("/api/state")).json();
  applyState(s);
}

function handleEvent(msg) {
  const { type, payload } = msg;
  switch (type) {
    case "tick":
      $("tick-badge").textContent = "tick " + payload.tick;
      $("tick-badge").classList.remove("loading");
      $("mode-badge").classList.remove("loading");
      renderFleet(payload.states);
      break;
    case "chaos":
      feedLine("chaos", `&#9888; <b>${payload.agent}</b> went ROGUE: ${payload.label}`);
      break;
    case "sense": {
      const n = (payload.problems || []).filter(p => !(payload.handled || []).includes(p.affectedEntity));
      if (n.length) {
        feedLine("sense", `Dynatrace flags: ${n.map(p => p.title).join("; ")}`);
        pulseBrand();
      }
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

const EVIDENCE_TAGS = {
  "spans-list":       ["DQL: fetch spans | summarize count()", "Distributed Tracing UI", "service.name = warden"],
  "span-detail":      ["span attribute inspector", "agent.id, service.namespace, span.name"],
  "metrics-by-agent": ["Dynatrace Notebooks", "warden.agent.actions by agent.id"],
};

function renderEvidence(items) {
  const grid = $("evidence-grid");
  grid.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "evidence-card";
    const tags = (EVIDENCE_TAGS[item.id] || []).map(t => `<span>${escapeHtml(t)}</span>`).join("");
    const frame = item.available
      ? `<img src="/preview/${item.file}" alt="${escapeHtml(item.title)}" loading="lazy" />`
      : `<div class="placeholder">
           <strong>${escapeHtml(item.title)}</strong>
           live tenant capture pending<br/>
           the loop ran end-to-end, the canonical screenshot lives outside the public repo
         </div>`;
    card.innerHTML = `
      <h3>${escapeHtml(item.title)}</h3>
      <div class="frame">${frame}</div>
      <p class="caption">${escapeHtml(item.caption)}</p>
      <div class="tags">${tags}</div>`;
    grid.appendChild(card);
  });
}

async function loadEvidence() {
  try {
    const r = await fetch("/api/evidence");
    const data = await r.json();
    renderEvidence(data.items || []);
  } catch (_) {
    $("evidence-grid").innerHTML = `<div class="dim" style="padding:0 22px">evidence manifest unavailable</div>`;
  }
}

function selectTab(which) {
  const isConsole = which === "console";
  $("tab-console").classList.toggle("active", isConsole);
  $("tab-evidence").classList.toggle("active", !isConsole);
  $("tab-console").setAttribute("aria-selected", String(isConsole));
  $("tab-evidence").setAttribute("aria-selected", String(!isConsole));
  $("view-console").hidden = !isConsole;
  $("view-evidence").hidden = isConsole;
  if (!isConsole) loadEvidence();
}

$("tab-console").onclick = () => selectTab("console");
$("tab-evidence").onclick = () => selectTab("evidence");

(async function init() {
  // window.__WARDEN_INITIAL__ is server-rendered into index.html so the
  // operator console paints with live data on the very first frame.
  // Only fall back to a network fetch when the inline snapshot is missing
  // (e.g. when the static file is loaded directly without the server).
  let s = window.__WARDEN_INITIAL__;
  if (!s) s = await (await fetch("/api/state")).json();
  renderScenarios(s.scenarios);
  applyState(s);
  connect();
})();
