/* SETU AI — shared vanilla JS for rider.html and customer.html. No build step. */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const wsUrl = (path) => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers = { "Content-Type": "application/json" };
    if (!init.method) init.method = "POST";
  }
  const r = await fetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
}

function orderLabel(o) {
  const tag = o.status !== "out_for_delivery" ? "not out for delivery" : o.requires_otp ? "verified handover" : "handover can be approved";
  return `${o.id} · ${o.store} · ${tag}`;
}

const ACTION_STYLE = {
  instant_action: ["ok", "Instant action"],
  record_rider_agreed: ["info", "Logged as rider's word"],
  request_approval: ["wait", "Ask customer (silent card)"],
  refuse: ["bad", "Refused"],
  escalate: ["bad", "Escalated"],
};
const EVIDENCE_STYLE = {
  info: "ev-info", rejected_or_unresolved: "ev-bad", requested: "ev-wait", rider_agreed: "ev-rider",
  pre_approved: "ev-ok", customer_approved: "ev-ok", provider_accepted: "ev-prov",
};

/* =================================================================== RIDER */
function riderPage() {
  let callId = null, ws = null, health = null, recorder = null, chunks = [], recStart = 0;
  const player = $("player");

  function log(text, cls = "") {
    const li = document.createElement("li");
    li.className = cls;
    li.innerHTML = `<time>${new Date().toLocaleTimeString()}</time> ${text}`;
    $("log").prepend(li);
  }

  function setStatus(title, sub, live = false) {
    $("csTitle").textContent = title;
    $("csSub").innerHTML = sub;
    $("callStatus").classList.toggle("live", live);
  }

  function play(url) {
    if (!url) return;
    player.src = url;
    player.play().catch(() => {});
  }

  function render(out) {
    const stt = out.stt || {};
    $("transcript").textContent = out.transcript || (stt.ok === false ? `(STT failed: ${stt.error || "unknown"})` : "—");
    $("lang").textContent = `lang ${out.language || "—"}${stt.raw_language_code ? " · " + stt.raw_language_code : ""}`;
    $("sttEngine").textContent = `engine ${stt.engine || "—"}`;
    $("intent").textContent = out.intent ? JSON.stringify({ intent: out.intent.intent, time: out.intent.time, source: out.intent.source }, null, 1) : "—";
    if (out.decision) {
      const [cls, label] = ACTION_STYLE[out.decision.action] || ["info", out.decision.action];
      $("decision").innerHTML = `<span class="act ${cls}">${label}</span><code>${esc(out.decision.action)}</code><div class="reason">${esc(out.decision.reason)}${out.decision.provider_request ? " · provider request permitted" : ""}</div>`;
    } else {
      $("decision").innerHTML = `<span class="act info">No policy step</span><div class="reason">${esc(out.reply_key || "")}</div>`;
    }
    const fb = out.tts_fallback_from ? ` · voice fell back ${out.tts_fallback_from}→${out.spoken_lang}` : "";
    $("reply").innerHTML = `<span class="lang-tag">${esc(out.spoken_lang || out.language || "")}</span> ${esc(out.spoken_text || out.reply_text || "—")}`;
    $("replyMeta").innerHTML = `<span class="pill ghost">template: ${esc(out.reply_key)}</span>` +
      `<span class="pill ghost">${out.cached ? "from phrase cache" : out.audio_url ? "rendered live" : "no audio"}${fb}</span>` +
      (out.provider ? `<span class="pill sim">simulated provider: ${esc(out.provider.status)}</span>` : "");
    play(out.audio_url);
    const t = out.timings_ms || {};
    const keys = ["stt", "intent", "policy", "tts", "total"];
    const max = Math.max(1, ...keys.map((k) => t[k] || 0));
    $("latency").innerHTML = keys.map((k) => `<div class="bar"><span>${k}</span><i style="width:${Math.max(2, ((t[k] || 0) / max) * 100)}%"></i><b>${t[k] == null ? "—" : t[k] + " ms"}</b></div>`).join("");
    if (out.decision && out.decision.action === "request_approval") {
      setStatus("Waiting for the customer", `<span class="spinner"></span> Rider hears the holding line. Customer got a silent one-tap card.`, true);
    } else if (callId) {
      setStatus("On call · listening", "The agent replied. Hold to talk again.", true);
    }
    log(`<b>${esc(out.reply_key)}</b> ← ${esc(out.intent ? out.intent.intent : "—")} ${out.decision ? "· " + esc(out.decision.action) : ""}`,
        out.decision && ["refuse", "escalate"].includes(out.decision.action) ? "bad" : "");
  }

  async function loadOrders() {
    const orders = await api("/orders");
    $("order").innerHTML = orders.map((o) => `<option value="${o.id}">${esc(orderLabel(o))}</option>`).join("");
  }

  async function startCall() {
    if (ws) ws.close();
    const info = await api("/calls/start", { json: { order_id: $("order").value } });
    callId = info.call_id;
    ws = new WebSocket(wsUrl(`/ws/rider/${callId}`));
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "rider_reply" && m.data.approval_id && !m.data.stt) {
        log("customer answered → policy re-checked", "ok");
        render(m.data);
      }
    };
    $("talkBtn").disabled = false;
    $("sendTyped").disabled = false;
    setStatus(`On call · ${info.order_id}`, `AI disclosure played in Hindi, Kannada and English. <code>${callId}</code>`, true);
    $("reply").textContent = info.greeting.en;
    play(info.audio_url);
    log(`call started on <b>${esc(info.order_id)}</b>`);
  }

  async function sendText(text) {
    if (!callId) await startCall();
    const out = await api(`/calls/${callId}/text`, { json: { text } });
    render(out);
  }

  async function sendAudio(blob) {
    const fd = new FormData();
    fd.append("audio", blob, "clip.webm");
    fd.append("mock_transcript", $("typed").value || "");
    fd.append("telephony", $("telephony").checked ? "true" : "false");
    const r = await fetch(`/calls/${callId}/audio`, { method: "POST", body: fd });
    const out = await r.json();
    if (!r.ok) throw new Error(out.detail || "upload failed");
    render(out);
  }

  async function beginRec(e) {
    e.preventDefault();
    if (!callId || recorder) return;
    if (health && health.mock_voice && !$("typed").value.trim()) {
      $("talkHint").textContent = "Mock voice: type what you say first (it becomes the fake transcript), then hold.";
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, noiseSuppression: false } });
      recorder = new MediaRecorder(stream);
      chunks = [];
      recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        recorder = null;
        $("talkBtn").classList.remove("rec");
        try { await sendAudio(blob); } catch (err) { log(esc(err.message), "bad"); }
      };
      recStart = Date.now();
      recorder.start();
      $("talkBtn").classList.add("rec");
      $("talkBtn").querySelector(".talk-label").textContent = "Listening…";
    } catch (err) {
      $("talkHint").textContent = "Microphone not available — type the line and press Send.";
    }
  }

  function endRec(e) {
    e.preventDefault();
    $("talkBtn").querySelector(".talk-label").textContent = "Hold to talk";
    if (recorder && recorder.state === "recording") {
      setTimeout(() => recorder && recorder.stop(), Math.max(0, 300 - (Date.now() - recStart)));
    }
  }

  $("startBtn").onclick = () => startCall().catch((e) => log(esc(e.message), "bad"));
  $("sendTyped").onclick = () => $("typed").value.trim() && sendText($("typed").value.trim()).catch((e) => log(esc(e.message), "bad"));
  $("typed").addEventListener("keydown", (e) => e.key === "Enter" && $("sendTyped").click());
  const tb = $("talkBtn");
  tb.addEventListener("pointerdown", beginRec);
  tb.addEventListener("pointerup", endRec);
  tb.addEventListener("pointerleave", endRec);
  document.querySelectorAll(".chip").forEach((c) => (c.onclick = async () => {
    try {
      if (c.dataset.order && (c.dataset.order !== $("order").value || !callId)) {
        $("order").value = c.dataset.order;
        await startCall();
      }
      $("typed").value = c.dataset.text;
      await sendText(c.dataset.text);
    } catch (e) { log(esc(e.message), "bad"); }
  }));
  $("order").onchange = () => { callId = null; $("talkBtn").disabled = true; setStatus("No call", "Order changed. Start a new call."); };

  (async () => {
    health = await api("/health");
    $("modeBadge").textContent = health.mock_voice ? "MOCK VOICE (no keys)" : `LIVE · ${health.models.stt} + ${health.models.tts}`;
    $("modeBadge").className = "badge " + (health.mock_voice ? "ghost" : "live");
    $("typedLabel").textContent = health.mock_voice
      ? "What the rider says (mock voice uses this as the transcript)"
      : "Or type instead of speaking (skips STT)";
    await loadOrders();
  })().catch((e) => log(esc(e.message), "bad"));
}

/* =================================================================== CUSTOMER */
function customerPage() {
  const cards = new Map();
  let timer = null;

  async function loadOrders() {
    const orders = await api("/orders");
    $("order").innerHTML = orders.map((o) => `<option value="${o.id}">${esc(o.id)}</option>`).join("");
  }

  async function loadPrefs() {
    const c = await api("/customers/CUST_001");
    $("ws").value = c.window_start; $("we").value = c.window_end;
    $("allowGuard").checked = !!c.allow_guard; $("allowNeighbor").checked = !!c.allow_neighbor;
  }

  function summarize(e) {
    const d = e.detail || {};
    if (e.event_type === "rider_utterance") return `“${esc(d.transcript)}” → <b>${esc(d.intent)}</b>${d.time ? " @ " + esc(d.time) : ""}`;
    if (e.event_type === "policy_decision") return `${esc(d.action)} · ${esc(d.reason)}`;
    if (e.event_type === "provider_response") return `simulated provider: <b>${esc(d.status)}</b>`;
    if (e.event_type === "customer_decision") return `you chose <b>${esc(d.choice)}</b>`;
    if (e.event_type === "rider_commitment") return `rider said ${esc(d.time)} · platform confirmed: no`;
    if (e.event_type === "approval_requested") {
      const s = d.slots || {};
      return `asked you: ${esc(String(s.request_intent || d.action).replaceAll("_", " "))}${s.time ? " @ " + esc(s.time) : ""}`;
    }
    if (d.customer_message) return `message: ${esc(d.customer_message)}`;
    return esc(Object.entries(d).filter(([k]) => !["slots"].includes(k)).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")).slice(0, 140);
  }

  async function loadLedger() {
    const L = await api(`/orders/${$("order").value}/ledger`);
    $("chainBadge").textContent = L.chain.ok ? `hash chain verified · ${L.chain.checked}` : `CHAIN BROKEN at #${L.chain.broken_at}`;
    $("chainBadge").className = "badge " + (L.chain.ok ? "ok" : "bad");
    $("ledgerMeta").textContent = `${L.events.length} events · highest evidence: ${L.highest_evidence}`;
    $("ledger").innerHTML = L.events.slice().reverse().map((e) => `
      <li class="${EVIDENCE_STYLE[e.evidence_level] || ""}">
        <div class="tl-top"><span class="ev">${esc(e.evidence_level.replaceAll("_", " "))}</span>
          <span class="tl-type">${esc(e.event_type)}</span><span class="tl-src">${esc(e.source)}</span>
          ${e.simulated ? '<span class="tl-sim">sim</span>' : ""}</div>
        <div class="tl-body">${summarize(e)}</div>
        <div class="tl-hash">#${e.seq} · ${new Date(e.ts * 1000).toLocaleTimeString()} · ${e.hash.slice(0, 12)}…</div>
      </li>`).join("") || `<li class="ev-info"><div class="tl-body">No events for this order yet.</div></li>`;
    if (L.customer_message) showMessage(L.customer_message);
  }

  function showMessage(m) {
    $("msgKn").textContent = m.kn;
    $("msgEn").textContent = m.en;
    $("msgFoot").textContent = m.downgraded
      ? "A stronger claim was blocked because the ledger has no evidence for it."
      : "Fixed template · chosen from ledger evidence · Kannada pending native review.";
  }

  function renderCards() {
    const list = [...cards.values()].filter((a) => a.status === "pending");
    if (!list.length) {
      $("approvalSlot").innerHTML = `<div class="empty">No request waiting. When a rider needs something you haven't pre-approved, it appears here as a silent card.</div>`;
      return;
    }
    $("approvalSlot").innerHTML = list.map((a) => {
      const handover = ["guard_drop_request", "neighbor_drop_request"].includes(a.action);
      const canApprove = !(handover && a.requires_otp); // never offered for verified orders
      return `<div class="approval" data-id="${a.id}">
        <div class="ap-head"><span class="badge sim">silent</span> <span class="muted small">${esc(a.order_id)}</span>
          <span class="countdown" data-exp="${a.expires_at}"></span></div>
        <div class="ap-q">The rider asks to <b>${esc(a.label)}</b>.</div>
        <div class="ap-actions">
          ${canApprove ? `<button class="btn approve" data-d="approve">Approve</button>` : ""}
          <button class="btn deny" data-d="reject">Do not allow</button>
          <button class="btn later" data-d="contact_later">Contact me later</button>
        </div>
        <div class="muted small">If you don't answer in time, the rider only hears your preferred window.</div>
      </div>`;
    }).join("");
    $("approvalSlot").querySelectorAll(".approval button").forEach((b) => (b.onclick = async () => {
      const id = b.closest(".approval").dataset.id;
      const a = cards.get(id);
      b.disabled = true;
      try {
        await api(`/approvals/${id}/decide`, { json: { decision: b.dataset.d, token: a.token } });
        a.status = b.dataset.d;
      } catch (e) {
        a.status = "error";
        alert(e.message);
      }
      renderCards();
      loadLedger();
    }));
    tick();
  }

  function tick() {
    const now = Date.now() / 1000;
    document.querySelectorAll(".countdown").forEach((el) => {
      const left = Math.max(0, Math.round(parseFloat(el.dataset.exp) - now));
      el.textContent = left ? `${left}s` : "expired";
      el.classList.toggle("urgent", left <= 10);
    });
  }

  function connect() {
    const ws = new WebSocket(wsUrl("/ws/customer"));
    ws.onmessage = (ev) => {
      const { type, data } = JSON.parse(ev.data);
      if (type === "hello") {
        data.pending.forEach((a) => cards.set(a.id, a));
        setMode(data.provider_mode);
        renderCards();
      } else if (type === "approval") {
        cards.set(data.id, data);
        if (data.order_id !== $("order").value) { $("order").value = data.order_id; loadLedger(); }
        renderCards();
      } else if (type === "ledger") {
        if (data.event_type === "approval_expired" && cards.has(data.detail.approval_id)) {
          cards.get(data.detail.approval_id).status = "expired";
          renderCards();
        }
        if (data.order_id === $("order").value) loadLedger();
      } else if (type === "status") {
        if (data.order_id !== $("order").value) { $("order").value = data.order_id; loadLedger(); }
        if (data.customer_message) showMessage(data.customer_message);
      } else if (type === "provider_mode") setMode(data.mode);
    };
    ws.onclose = () => setTimeout(connect, 1500);
  }

  function setMode(mode) {
    document.querySelectorAll("#providerMode button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  }

  document.querySelectorAll("#providerMode button").forEach((b) => (b.onclick = () =>
    api("/mock-provider/mode", { json: { mode: b.dataset.mode } }).then((r) => setMode(r.mode))));
  $("order").onchange = loadLedger;
  $("savePrefs").onclick = async () => {
    try {
      await api("/customers/CUST_001/preferences", { method: "PUT", json: {
        window_start: $("ws").value, window_end: $("we").value,
        allow_guard: $("allowGuard").checked, allow_neighbor: $("allowNeighbor").checked } });
      $("prefsNote").textContent = "Saved. Logged in the ledger. Verified-OTP orders still never go to a guard or neighbour.";
      loadLedger();
    } catch (e) { $("prefsNote").textContent = e.message; }
  };

  (async () => {
    await loadOrders();
    await loadPrefs();
    await loadLedger();
    connect();
    timer = setInterval(tick, 1000);
  })();
}

if (document.body.dataset.page === "rider") riderPage();
if (document.body.dataset.page === "customer") customerPage();
