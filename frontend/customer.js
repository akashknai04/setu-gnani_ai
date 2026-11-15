/* SETU AI — Asha's phone (customer). Vanilla JS. */
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers = { "Content-Type": "application/json" }; init.method = init.method || "POST"; }
  const r = await fetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
}

const cards = new Map();
let ac = null, liveCall = null, liveTimer = null;

/* ---------- alerts (sound + vibration need one tap first) */
$("alertsBar").onclick = () => {
  try { ac = new (window.AudioContext || window.webkitAudioContext)(); ac.resume(); } catch (_) {}
  $("alertsBar").hidden = true;
  chime();
};
function chime() {
  if (navigator.vibrate) navigator.vibrate([180, 90, 180]);
  if (!ac) return;
  const g = ac.createGain(); g.connect(ac.destination);
  [880, 1175].forEach((f, i) => {
    const o = ac.createOscillator(); o.frequency.value = f; o.connect(g);
    const t = ac.currentTime + i * 0.16;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.12, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.15);
    o.start(t); o.stop(t + 0.16);
  });
}

/* ---------- tabs */
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.pane)));
function showTab(id) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.pane === id)));
  document.querySelectorAll(".tabpane").forEach((p) => (p.hidden = p.id !== id));
  if (id === "pane-act") loadLedger();
}

/* ---------- live call banner */
function setLive(on) {
  clearInterval(liveTimer);
  if (!on) { $("liveCall").hidden = true; return; }
  liveCall = { t0: Date.now() };
  const draw = () => {
    const s = Math.floor((Date.now() - liveCall.t0) / 1000);
    $("liveCall").innerHTML = `<div class="live-call"><span class="dot"></span>Your assistant is talking to the rider · ${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}</div>`;
  };
  $("liveCall").hidden = false; draw(); liveTimer = setInterval(draw, 1000);
}

/* ---------- approval cards */
function renderCards() {
  const list = [...cards.values()].filter((a) => a.status === "pending");
  $("badge").hidden = !list.length; $("badge").textContent = list.length;
  if (!list.length) {
    $("cards").innerHTML = `<div class="empty">No request waiting. When the rider asks for something you haven't pre-approved, a silent card appears here.</div>`;
    return;
  }
  $("cards").innerHTML = list.map((a) => {
    const handover = ["guard_drop_request", "neighbor_drop_request"].includes(a.action);
    return `<div class="approval" data-id="${a.id}">
      <div class="ap-head"><span class="silent">SILENT</span>${esc(a.order_id)}<span class="countdown" data-exp="${a.expires_at}"></span></div>
      <div class="ap-q">The rider asks to <b>${esc(a.label)}</b>.</div>
      <div class="ap-actions">
        ${handover && a.requires_otp ? "" : `<button class="yes" data-d="approve">Approve</button>`}
        <button class="no" data-d="reject">Do not allow</button>
        <button class="later" data-d="contact_later">Contact me later</button>
      </div>
      <div class="ap-foot">No answer in time: the rider only hears your free window.</div></div>`;
  }).join("");
  $("cards").querySelectorAll(".ap-actions button").forEach((b) => (b.onclick = async () => {
    const a = cards.get(b.closest(".approval").dataset.id);
    b.closest(".ap-actions").querySelectorAll("button").forEach((x) => (x.disabled = true));
    try { await api(`/approvals/${a.id}/decide`, { json: { decision: b.dataset.d, token: a.token } }); a.status = b.dataset.d; }
    catch (e) { a.status = "closed"; $("msgFoot").textContent = e.message; }
    renderCards(); loadLedger();
  }));
  tick();
}
function tick() {
  const now = Date.now() / 1000;
  document.querySelectorAll(".countdown").forEach((el) => (el.textContent = Math.max(0, Math.ceil(parseFloat(el.dataset.exp) - now)) + "s"));
}
setInterval(tick, 500);

function showMessage(m) {
  if (!m) return;
  $("msgKn").textContent = m.kn; $("msgEn").textContent = m.en;
  $("msgFoot").textContent = m.downgraded ? "A stronger claim was blocked: the ledger has no evidence for it."
    : "Fixed template, chosen only from ledger evidence. Kannada pending native review.";
}

/* ---------- ledger */
function summarize(e) {
  const d = e.detail || {};
  switch (e.event_type) {
    case "rider_utterance": return `“${esc(d.transcript)}” → <b>${esc(d.intent)}</b>${d.time ? " at " + esc(d.time) : ""}`;
    case "policy_decision": return `${esc(d.action)} · ${esc(d.reason)}`;
    case "provider_response": return `simulated provider: <b>${esc(d.status)}</b>`;
    case "customer_decision": return `you chose <b>${esc(d.choice)}</b>`;
    case "rider_commitment": return `rider said ${esc(d.time)} · platform confirmed: no`;
    case "approval_requested": return `asked you: ${esc(String(d.action).replaceAll("_", " "))}`;
    case "approval_cancelled": return "rider ended the call before you answered";
    case "call_started": return `AI disclosure played · order valid: ${d.order_valid ? "yes" : "no"}`;
    case "call_ended": return `call ended (${esc(String(d.by).replaceAll("_", " "))})`;
    case "preferences_updated": return `rules changed`;
    default: return d.customer_message ? `message: ${esc(d.customer_message)}` : esc(JSON.stringify(d)).slice(0, 120);
  }
}
async function loadLedger() {
  const L = await api(`/orders/${$("order").value}/ledger`);
  $("chain").className = "chain " + (L.chain.ok ? "ok" : "bad");
  $("chain").textContent = L.chain.ok ? `Hash chain verified · ${L.chain.checked} events` : `Chain broken at event #${L.chain.broken_at}`;
  $("ledgerMeta").textContent = `${L.events.length} events on ${$("order").value} · highest evidence: ${L.highest_evidence.replaceAll("_", " ")}`;
  $("ledger").innerHTML = L.events.slice().reverse().filter((e) => e.event_type !== "preferences_updated").slice(0, 80).map((e) => `
    <li class="lv-${e.evidence_level}">
      <div class="tl-top"><span class="ev">${esc(e.evidence_level.replaceAll("_", " "))}</span><span class="tl-type">${esc(e.event_type.replaceAll("_", " "))}</span></div>
      <div class="tl-body">${summarize(e)}</div>
      <div class="tl-hash">#${e.seq} · ${new Date(e.ts * 1000).toLocaleTimeString()} · ${e.hash.slice(0, 14)}… · simulated</div>
    </li>`).join("") || `<li><div class="tl-body">No events for this order yet.</div></li>`;
  if (L.customer_message) showMessage(L.customer_message);
}

/* ---------- rules + provider */
async function loadRules() {
  const c = await api("/customers/CUST_001");
  $("ws").value = c.window_start; $("we").value = c.window_end; $("ag").checked = !!c.allow_guard; $("an").checked = !!c.allow_neighbor;
}
$("rules").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/customers/CUST_001/preferences", { method: "PUT", json: { window_start: $("ws").value, window_end: $("we").value, allow_guard: $("ag").checked, allow_neighbor: $("an").checked } });
    $("rulesNote").textContent = "Saved. The change is in your activity log.";
  } catch (err) { $("rulesNote").textContent = err.message; }
});
function setMode(m) { document.querySelectorAll("#seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === m))); }
document.querySelectorAll("#seg button").forEach((b) => (b.onclick = () => api("/mock-provider/mode", { json: { mode: b.dataset.mode } }).then((r) => setMode(r.mode))));

/* ---------- live updates */
function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/customer`);
  ws.onmessage = (ev) => {
    const { type, data } = JSON.parse(ev.data);
    if (type === "hello") { data.pending.forEach((a) => cards.set(a.id, a)); setMode(data.provider_mode); renderCards(); }
    else if (type === "approval") {
      cards.set(data.id, data);
      if ($("order").value !== data.order_id) { $("order").value = data.order_id; }
      showTab("pane-req"); renderCards(); chime();
    } else if (type === "approval_closed") { const a = cards.get(data.id); if (a) { a.status = data.status; renderCards(); } }
    else if (type === "ledger") {
      if (data.event_type === "approval_expired" && cards.has(data.detail.approval_id)) { cards.get(data.detail.approval_id).status = "expired"; renderCards(); }
      if (data.order_id === $("order").value && !$("pane-act").hidden) loadLedger();
    } else if (type === "status") {
      if (data.started) setLive(true);
      if (data.ended) setLive(false);
      if (data.order_id && $("order").value !== data.order_id) $("order").value = data.order_id;
      showMessage(data.customer_message);
    } else if (type === "provider_mode") setMode(data.mode);
    else if (type.startsWith("interpret") && window.SetuCustomer) window.SetuCustomer.on(type, data);
  };
  ws.onclose = () => setTimeout(connect, 1500);
}

$("order").onchange = loadLedger;
(async () => {
  const orders = await api("/orders");
  $("order").innerHTML = orders.map((o) => `<option value="${o.id}">${esc(o.id)}</option>`).join("");
  await loadRules(); await loadLedger(); connect();
})();
