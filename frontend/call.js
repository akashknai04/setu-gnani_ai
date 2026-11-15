/* SETU AI — rider's phone call screen. Vanilla JS, no build step.

   Voice paths
   - gnani   : hands-free mic capture with silence detection -> POST /calls/{id}/audio
               (Prisma STT on the server) -> reply audio from Timbre, played here.
   - browser : no Gnani key (MOCK_VOICE=1). The browser's speech recognition and voices
               stand in, so the demo still talks. Labelled on screen; not Gnani.
   - none    : no speech recognition in this browser: use "What to say" (Play / Say it for me).

   The agent is half-duplex like a walkie-talkie: it never listens while it is speaking.
*/
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LANG_NAME = { hi: "Hindi", kn: "Kannada", en: "English" };
const BCP = { hi: "hi-IN", kn: "kn-IN", en: "en-IN" };
const ACT = {
  instant_action: ["ok", "answered"], record_rider_agreed: ["info", "logged as rider's word"],
  request_approval: ["wait", "asked Asha"], refuse: ["bad", "refused"], escalate: ["bad", "escalated"],
};

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers = { "Content-Type": "application/json" };
    init.method = init.method || "POST";
  }
  const r = await fetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(body.detail || `HTTP ${r.status}`); e.status = r.status; throw e; }
  return body;
}

/* ------------------------------------------------------------------ state */
const S = {
  health: null, scen: null, lang: "hi", voice: "browser", listen: "browser", calibrated: false,
  callId: null, orderId: "ORD_1024", active: false, ended: false, muted: false, handsFree: true,
  autopilot: false, waiting: null, queue: [], handled: new Set(), listenCtrl: null, ws: null, playingAll: false,
  t0: 0, timer: null, ac: null, mic: null, analyser: null, floor: 0.01,
};

/* ------------------------------------------------------------------ audio (see sound.js) */
function unlockAudio() {
  Sound.unlock();
  try { if (!S.ac) S.ac = new (window.AudioContext || window.webkitAudioContext)(); if (S.ac.state !== "running") S.ac.resume(); } catch (_) {}
}

function rms(an) {
  const buf = new Float32Array(an.fftSize);
  an.getFloatTimeDomainData(buf);
  let s = 0; for (const v of buf) s += v * v;
  return Math.sqrt(s / buf.length);
}

let orbRAF = 0;
function orb(mode) {
  const el = $("orb");
  el.dataset.mode = mode;
  cancelAnimationFrame(orbRAF);
  const tick = () => {
    let lvl = 1;
    if (mode === "you" && S.analyser) lvl = 1 + Math.min(0.45, rms(S.analyser) * 8);
    else if (mode === "ai") lvl = 1.15 + 0.15 * Math.sin(performance.now() / 160);
    else if (mode === "wait" || mode === "think") lvl = 1.05 + 0.08 * Math.sin(performance.now() / 300);
    el.style.setProperty("--lvl", lvl.toFixed(3));
    orbRAF = requestAnimationFrame(tick);
  };
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) tick();
}

function setState(text, mode) { $("state").textContent = text; orb(mode || "idle"); }

/* Phones send sound to the quiet earpiece while a microphone is open, so the microphone is
   released before the assistant speaks and reopened when it is the rider's turn. */
function releaseMic() {
  if (S.mic) { S.mic.getTracks().forEach((t) => t.stop()); S.mic = null; S.analyser = null; }
  Sound.session("playback");
}

async function playUrl(url) {
  releaseMic();
  const r = await Sound.play(url);
  if (!r.ok && r.reason !== "stopped") throw new Error(r.reason);
}

async function speakBrowser(text, lang, who = "ai") {
  releaseMic();
  const r = await Sound.speakDevice(text, lang, who);
  return r.ok;
}
const readingPause = (text) => sleep(Math.min(9000, 900 + text.length * 55));

/* ------------------------------------------------------------------ captions */
function bubble(cls, html) {
  const d = document.createElement("div");
  d.className = "bub " + cls; d.innerHTML = html;
  $("captions").appendChild(d);
  $("captions").scrollTop = $("captions").scrollHeight;
  return d;
}
const scriptClass = (lang) => (lang === "kn" ? "kn" : lang === "hi" ? "hi" : "");
function riderBubble(out, played) {
  const st = out.stt || {};
  const tags = [`<span class="tag">${esc(LANG_NAME[out.language] || out.language || "")}</span>`];
  if (st.engine && st.engine !== "typed") tags.push(`<span class="tag">${esc(st.engine)}</span>`);
  if (played) tags.push(`<span class="tag">played by demo</span>`);
  if ((out.transcript || "").includes("[REDACTED]")) tags.push(`<span class="tag bad why">digits hidden before logging</span>`);
  bubble("me", `<div class="${scriptClass(out.language)}">${esc(out.transcript)}</div><div class="meta">${tags.join("")}</div>`);
}
function aiBubble(out) {
  const lang = out.spoken_lang || out.language;
  const tags = [];
  if (out.decision) {
    const [cls, label] = ACT[out.decision.action] || ["", out.decision.action];
    tags.push(`<span class="tag ${cls} why">${label}</span><span class="tag why">${esc(out.decision.reason)}</span>`);
  }
  if (out.intent && out.intent.intent) tags.push(`<span class="tag why">heard: ${esc(out.intent.intent)}${out.intent.time ? " " + esc(out.intent.time) : ""}</span>`);
  if (out.provider) tags.push(`<span class="tag why">simulated provider: ${esc(out.provider.status)}</span>`);
  if (out.tts_fallback_from) tags.push(`<span class="tag">voice fell back ${esc(out.tts_fallback_from)}→${esc(out.spoken_lang)}</span>`);
  bubble("ai", `<div class="${scriptClass(lang)}">${esc(out.spoken_text || out.reply_text)}</div><div class="meta">${tags.join("")}</div>`);
}
const sys = (t) => bubble("sys", esc(t));

/* ------------------------------------------------------------------ listening */
async function getMic() {
  if (S.mic && S.mic.getTracks().some((t) => t.readyState === "live")) return S.mic;
  Sound.session("play-and-record");
  S.mic = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  const src = S.ac.createMediaStreamSource(S.mic);
  S.analyser = S.ac.createAnalyser(); S.analyser.fftSize = 1024; src.connect(S.analyser);
  return S.mic;
}
async function calibrate(ms = 600) {
  if (!S.analyser) return;
  const vals = []; const end = performance.now() + ms;
  while (performance.now() < end) { vals.push(rms(S.analyser)); await sleep(40); }
  vals.sort((a, b) => a - b);
  S.floor = vals[Math.floor(vals.length * 0.4)] || 0.01;   // the quieter part of the sample is the room's floor
}
function recMime() {
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"]) if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m;
  return "";
}

/* Hands-free: record until the rider stops talking. Returns a Blob, or null (nothing said / aborted). */
function captureUtterance(signal) {
  return new Promise((resolve) => {
    const mime = recMime();
    let rec = new MediaRecorder(S.mic, mime ? { mimeType: mime } : undefined);
    let chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const thr = Math.max(0.012, S.floor * 2.6);
    let speechMs = 0, silenceMs = 0, started = false, idleMs = 0, totalSpeech = 0, done = false;
    const finish = (keep) => {
      if (done) return; done = true; clearInterval(iv);
      rec.onstop = () => resolve(keep && totalSpeech >= 350 ? new Blob(chunks, { type: rec.mimeType || "audio/webm" }) : null);
      try { rec.stop(); } catch (_) { resolve(null); }
    };
    rec.start(100);
    const iv = setInterval(() => {
      if (signal.aborted) return finish(false);
      if (S.muted) { idleMs = 0; return; }
      const level = rms(S.analyser);
      if (level > thr) {
        speechMs += 50; silenceMs = 0;
        if (started) totalSpeech += 50;
        if (!started && speechMs >= 150) { started = true; totalSpeech = speechMs; setState("Hearing you…", "you"); }
      } else {
        speechMs = Math.max(0, speechMs - 25);
        if (started) { silenceMs += 50; if (silenceMs >= 850) return finish(true); }
        else {
          idleMs += 50;
          if (idleMs >= 4000) {   // keep the clip short: restart quietly while nobody talks
            idleMs = 0; chunks = [];
            try { rec.stop(); } catch (_) {}
            rec = new MediaRecorder(S.mic, mime ? { mimeType: mime } : undefined);
            rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
            rec.start(100);
          }
        }
      }
      if (started && totalSpeech >= 15000) finish(true);
    }, 50);
  });
}

/* Push-to-talk capture (hands-free off). */
function capturePTT(signal) {
  return new Promise((resolve) => {
    const btn = $("ptt"); let rec = null, chunks = [], t0 = 0;
    const down = (e) => { e.preventDefault(); if (rec) return;
      const mime = recMime(); rec = new MediaRecorder(S.mic, mime ? { mimeType: mime } : undefined);
      chunks = []; rec.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data); rec.start(100); t0 = Date.now();
      btn.classList.add("rec"); btn.textContent = "Listening… release to send"; setState("Hearing you…", "you"); };
    const up = (e) => { e.preventDefault(); if (!rec) return;
      btn.classList.remove("rec"); btn.textContent = "Hold to talk";
      const r = rec; rec = null; r.onstop = () => { cleanup(); resolve(Date.now() - t0 > 350 ? new Blob(chunks, { type: r.mimeType }) : null); }; r.stop(); };
    const cleanup = () => { btn.removeEventListener("pointerdown", down); btn.removeEventListener("pointerup", up); btn.removeEventListener("pointerleave", up); };
    btn.addEventListener("pointerdown", down); btn.addEventListener("pointerup", up); btn.addEventListener("pointerleave", up);
    signal.addEventListener("abort", () => { cleanup(); if (rec) { try { rec.stop(); } catch (_) {} } resolve(null); });
  });
}

/* Browser speech recognition (no Gnani key). Resolves recognised text or null. */
function recogniseBrowser(signal) {
  return new Promise((resolve) => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = new SR(); r.lang = BCP[S.lang] || "hi-IN"; r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
    let live = null, final = "", settled = false;
    const end = (v) => { if (settled) return; settled = true; if (live) live.remove(); resolve(v); };
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) final += e.results[i][0].transcript; else interim += e.results[i][0].transcript;
      }
      if (interim) { setState("Hearing you…", "you"); if (!live) live = bubble("me live", ""); live.textContent = interim; }
    };
    r.onerror = () => {};
    r.onend = () => end(final.trim() || null);
    signal.addEventListener("abort", () => { try { r.abort(); } catch (_) {} end(null); });
    try { r.start(); } catch (_) { end(null); }
  });
}

async function listenOnce(signal) {
  if (S.listen === "server") { await getMic(); if (!S.calibrated) { await calibrate(); S.calibrated = true; } }
  if (S.listen === "server") return S.handsFree ? captureUtterance(signal) : capturePTT(signal);
  if (S.listen === "browser") {
    Sound.session("play-and-record");
    if (S.handsFree) return recogniseBrowser(signal);
    await new Promise((res) => { const b = $("ptt"); const h = (e) => { e.preventDefault(); b.removeEventListener("pointerdown", h); res(); };
      b.addEventListener("pointerdown", h); signal.addEventListener("abort", res); });
    if (signal.aborted) return null;
    return recogniseBrowser(signal);
  }
  if (S.listen === "none") { await new Promise((res) => signal.addEventListener("abort", res)); return null; }
  await new Promise((res) => signal.addEventListener("abort", res));   // nothing to listen with: wait for demo input
  return null;
}

/* ------------------------------------------------------------------ talking to the server */
async function sendHeard(heard) {
  if (heard instanceof Blob) {
    const fd = new FormData();
    fd.append("audio", heard, heard.type.includes("mp4") ? "clip.m4a" : heard.type.includes("ogg") ? "clip.ogg" : "clip.webm");
    // Automated browser test hook: with MOCK_VOICE=1 the server reads this as the transcript. Ignored with real Prisma.
    if (Array.isArray(window.__mockSay) && window.__mockSay.length) fd.append("mock_transcript", window.__mockSay.shift());
    return api(`/calls/${S.callId}/audio`, { method: "POST", body: fd });
  }
  return api(`/calls/${S.callId}/text`, { json: { text: heard, language: S.lang === "auto" ? null : S.lang } });
}

async function speakReply(out) {
  const text = out.spoken_text || out.reply_text || "";
  const lang = out.spoken_lang || out.language || "en";
  setState("Assistant speaking…", "ai");
  if (out.audio_url) { try { await playUrl(out.audio_url); return; } catch (_) {} }
  if (out.tts_error) sys("Timbre could not speak this line; trying this device's voice.");
  const ok = await speakBrowser(text, lang, "ai");
  if (!ok) { sys(`This device has no ${LANG_NAME[lang]} voice for this line: read the caption.`); await readingPause(text); }
}

async function riderSays(text, lang) {      // demo: the rider's line, spoken aloud
  setState("Rider speaking (demo)…", "you");
  try { const r = await api("/tts/rider", { json: { text, language: lang } }); if (r.audio_url) { await playUrl(r.audio_url); return; } } catch (_) {}
  if (!(await speakBrowser(text, lang, "rider"))) await readingPause(text);
}

async function handleReply(out) {
  if (out.approval_id && out.decision && !out.stt && out.decision.action !== "request_approval") {
    if (S.handled.has(out.approval_id)) return;
    S.handled.add(out.approval_id);
    clearWait();
    sys("Asha answered. Policy checked again.");
  }
  aiBubble(out);
  await speakReply(out);
  if (out.ended) return finish("goodbye");
  if (out.decision && out.decision.action === "request_approval" && out.approval_id) showWait(out.approval_id);
}

/* ------------------------------------------------------------------ waiting for Asha */
async function showWait(aprId) {
  S.waiting = aprId;
  const pend = await api("/approvals/pending").catch(() => []);
  const a = pend.find((x) => x.id === aprId);
  const handover = a && ["guard_drop_request", "neighbor_drop_request"].includes(a.action);
  $("waitSlot").innerHTML = `<div class="waitcard">
    <div class="small"><b>Waiting for Asha.</b> Her phone shows a silent card. <span class="countdown" data-exp="${a ? a.expires_at : 0}"></span></div>
    <div class="row"><span class="small muted">Solo demo, answer as Asha:</span></div>
    <div class="row">
      ${handover && a.requires_otp ? "" : '<button class="yes" data-d="approve">Approve</button>'}
      <button data-d="reject">Do not allow</button><button data-d="contact_later">Contact me later</button>
    </div></div>`;
  $("waitSlot").querySelectorAll("button").forEach((b) => (b.onclick = () => answerAsAsha(b.dataset.d)));
  setState("Waiting for Asha's answer…", "wait");
}
function clearWait() { S.waiting = null; $("waitSlot").innerHTML = ""; }
async function answerAsAsha(choice) {
  const pend = await api("/approvals/pending").catch(() => []);
  const a = pend.find((x) => x.id === S.waiting);
  if (!a) return;
  $("waitSlot").querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    const out = await api(`/approvals/${a.id}/decide`, { json: { decision: choice, token: a.token } });
    setTimeout(() => { if (!S.handled.has(out.approval_id)) enqueue(out); }, 1200);   // in case the live channel is down
  } catch (e) { sys(e.message); }
}
setInterval(() => {
  const now = Date.now() / 1000;
  document.querySelectorAll(".countdown").forEach((el) => {
    const left = Math.max(0, Math.ceil(parseFloat(el.dataset.exp) - now));
    el.textContent = parseFloat(el.dataset.exp) ? `${left}s left` : "";
  });
}, 500);

function enqueue(out) { S.queue.push(out); if (S.listenCtrl) S.listenCtrl.abort(); }

/* ------------------------------------------------------------------ the call */
async function startCall(opts = {}) {     // opts.keep: continue on the same screen (after ringing Asha)
  unlockAudio();
  S.ended = false; S.queue = []; S.handled = new Set();
  if (!opts.keep) $("captions").innerHTML = "";
  clearWait();
  $("dial").hidden = true; $("ended").hidden = true; $("incall").hidden = false;
  $("whoSub").textContent = "Calling…"; $("timer").textContent = "00:00";
  if (S.listen === "server") {
    try { await getMic(); await calibrate(); S.calibrated = true; releaseMic(); }
    catch (_) { S.listen = "none"; sys("Microphone blocked. Allow it in the browser, or use What to say."); }
  }
  if (!opts.keep) { setState("Ringing…", "idle"); await Sound.ring(); }
  const lang = S.lang === "auto" ? null : S.lang;
  const info = await api("/calls/start", { json: { order_id: S.orderId, language: lang } });
  S.callId = info.call_id; S.active = true; S.t0 = Date.now();
  clearInterval(S.timer);
  S.timer = setInterval(() => { const s = Math.floor((Date.now() - S.t0) / 1000); $("timer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }, 500);
  $("whoSub").textContent = "Asha is in a meeting · SETU's AI agent answered";
  openSocket();
  const glang = info.greeting_langs.length === 1 ? info.greeting_langs[0] : "hi";
  const gtext = info.greeting_langs.map((l) => info.greeting[l]).join(" ");
  bubble("ai", `<div class="${scriptClass(glang)}">${esc(gtext)}</div><div class="meta"><span class="tag why">AI disclosure</span></div>`);
  setState("Assistant speaking…", "ai");
  let spoke = false;
  if (info.audio_url) { try { await playUrl(info.audio_url); spoke = true; } catch (_) {} }
  if (!spoke) for (const l of info.greeting_langs) { if (!(await speakBrowser(info.greeting[l], l))) await readingPause(info.greeting[l]); }
  loop();
}

async function loop() {
  while (S.active) {
    if (S.autopilot) { await sleep(150); continue; }          // the scenario player drives the call
    if (S.queue.length) { await handleReply(S.queue.shift()); continue; }
    if (S.muted) { await sleep(150); continue; }
    setState(S.waiting ? "Waiting for Asha · you can keep talking" : S.handsFree ? "Listening… just talk" : "Hold the button to talk", S.waiting ? "wait" : "you");
    S.listenCtrl = new AbortController();
    let heard = null;
    try { heard = await listenOnce(S.listenCtrl.signal); } catch (_) { heard = null; }
    S.listenCtrl = null;
    if (!S.active || heard == null || S.autopilot) continue;
    await turn(heard, false);
  }
}

async function turn(heard, played) {
  setState("Understanding…", "think");
  let out;
  try { out = await sendHeard(heard); }
  catch (e) { if (e.status === 409) return finish("ended"); sys(e.message); return; }
  if (out.heard_nothing) return;
  riderBubble(out, played);
  await handleReply(out);
  return out;
}

function openSocket() {
  if (S.ws) try { S.ws.close(); } catch (_) {}
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/rider/${S.callId}`);
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "rider_reply" && m.data.approval_id && m.data.decision && !m.data.stt && !S.handled.has(m.data.approval_id)) enqueue(m.data);
  };
  S.ws = ws;
}

async function finish(reason) {
  if (S.ended) return;
  S.ended = true; S.active = false;
  if (S.listenCtrl) S.listenCtrl.abort();
  Sound.stop(); releaseMic();
  clearInterval(S.timer);
  let summary = null;
  try {
    const r = reason === "goodbye" ? null : await api(`/calls/${S.callId}/end`, { method: "POST" });
    summary = r ? r.summary : await api(`/calls/${S.callId}`);
  } catch (_) {}
  if (S.ws) try { S.ws.close(); } catch (_) {}
  showEnded(summary);
}

function showEnded(sm) {
  $("incall").hidden = true; $("ended").hidden = false; clearWait();
  $("endTime").textContent = `Call lasted ${$("timer").textContent}`;
  if (sm) {
    $("outKn").textContent = sm.customer_message.kn; $("outEn").textContent = sm.customer_message.en;
    const labels = { greeting: "Rider said hello", customer_unavailable: "Rider said the customer isn't answering", ask_availability: "Asked when Asha is free",
      propose_time: "Offered a delivery time", guard_drop_request: "Asked to leave it with the guard", neighbor_drop_request: "Asked to leave it with a neighbour",
      request_otp: "Asked for the OTP (refused)", change_address: "Asked about a different address", ask_address: "Asked for directions", end_call: "Said goodbye", unclear: "Said something unclear" };
    $("did").innerHTML = sm.intents.map((i) => `<li>${esc(labels[i] || i)}</li>`).join("") || "<li>Nothing was said.</li>";
    $("chainLine").textContent = `${sm.events} ledger events · hash chain ${sm.chain_ok ? "verified" : "BROKEN"} · highest evidence: ${sm.highest_evidence.replaceAll("_", " ")}`;
  }
}

/* ------------------------------------------------------------------ scenarios */
async function setup(sc) {
  await api("/customers/CUST_001/preferences", { method: "PUT", json: { allow_guard: false, allow_neighbor: false, ...(sc.rules || {}) } });
  await api("/mock-provider/mode", { json: { mode: sc.provider_mode || "accept" } });
  S.orderId = sc.order; $("order").value = sc.order; updateOrder();
}

async function nextQueued(timeoutMs) {        // scenario player: wait for Asha's answer to come back
  const end = Date.now() + timeoutMs;
  while (!S.queue.length && S.active && Date.now() < end) await sleep(100);
  while (S.queue.length) await handleReply(S.queue.shift());
}

async function play(sc) {
  unlockAudio();
  closeSheet();
  const lang = S.lang === "auto" ? "hi" : S.lang;
  await setup(sc);
  if (S.active) await finish("restart");
  S.autopilot = true;
  try {
    await startCall();
    sys(`Playing: ${sc.title}`);
    for (const step of sc.steps) {
      if (!S.active) break;
      if (step.say) {
        const text = step.say[lang];
        await riderSays(text, lang);
        await turn(text, true);
      } else if (step.customer === "no_answer") {
        sys(`Asha does not answer. The card expires in ${S.health.approval_ttl_s} s.`);
        await nextQueued((S.health.approval_ttl_s + 8) * 1000);
      } else if (step.customer) {
        const label = { approve: "Approve", reject: "Do not allow", contact_later: "Contact me later" }[step.customer];
        await sleep(1600);
        sys(`Asha taps “${label}” on her phone.`);
        await answerAsAsha(step.customer);
        await nextQueued(8000);
      } else if (step.hangup) {
        await sleep(1200);
        sys("Rider hangs up.");
        await finish("hangup");
      }
      await sleep(500);
    }
  } finally {
    S.autopilot = false;
  }
}

async function playAll() {
  S.playingAll = true;
  for (const sc of S.scen.scenarios) {
    if (!S.playingAll) break;
    await play(sc);
    await sleep(2500);
  }
  S.playingAll = false;
}

function renderSheet() {
  const lang = S.lang === "auto" ? "hi" : S.lang;
  const by = {};
  S.scen.scenarios.forEach((s) => (by[s.group] = by[s.group] || []).push(s));
  const custText = { approve: "Asha taps Approve", reject: "Asha taps Do not allow", contact_later: "Asha taps Contact me later", no_answer: "Asha doesn't answer in time" };
  $("sheetBody").innerHTML =
    `<div class="scn-acts" style="margin:8px 0 4px"><button class="go" id="playAll">Play all ${S.scen.scenarios.length} scenarios</button></div>` +
    S.scen.groups.map((g) => `<div class="grp">${esc(g)}</div>` + by[g].map((s) => `
    <div class="scn" data-id="${s.id}">
      <div class="scn-top"><span class="scn-title">${esc(s.title)}</span><span class="pill">${esc(s.order)}</span></div>
      ${s.steps.map((st, i) => st.say ? `<div class="scn-line ${scriptClass(lang)}"><span class="q">Say</span>“${esc(st.say[lang])}”
          ${S.active ? `<button class="linkish" data-say="${i}">say it for me</button>` : ""}</div>`
        : `<div class="scn-cust">${esc(st.hangup ? "Rider hangs up" : custText[st.customer])}</div>`).join("")}
      ${s.rules || s.provider_mode ? `<div class="scn-cust">Setup: ${esc([s.rules ? "neighbour pre-approved" : "", s.provider_mode ? "provider " + s.provider_mode : ""].filter(Boolean).join(", "))}</div>` : ""}
      <div class="scn-acts"><button class="go" data-play>Play</button><button data-setup>Set up and call</button></div>
    </div>`).join("")).join("") +
    `<div class="grp">Type instead</div><form id="typeForm" style="display:flex;gap:8px"><input type="text" id="typeIn" placeholder="What the rider says" autocomplete="off"><button class="btn" type="submit">Send</button></form>`;
  $("playAll").onclick = () => playAll();
  $("sheetBody").querySelectorAll(".scn").forEach((el) => {
    const sc = S.scen.scenarios.find((s) => s.id === el.dataset.id);
    el.querySelector("[data-play]").onclick = () => play(sc);
    el.querySelector("[data-setup]").onclick = async () => { closeSheet(); await setup(sc); if (!S.active) startCall(); else sys(`Set up: ${sc.title}. Start a new call if the order changed.`); };
    el.querySelectorAll("[data-say]").forEach((b) => (b.onclick = async () => {
      closeSheet(); S.autopilot = true; if (S.listenCtrl) S.listenCtrl.abort();
      const text = sc.steps[+b.dataset.say].say[lang];
      await riderSays(text, lang); await turn(text, true); S.autopilot = false;
    }));
  });
  $("typeForm").onsubmit = async (e) => {
    e.preventDefault(); const t = $("typeIn").value.trim(); if (!t || !S.active) return;
    closeSheet(); S.autopilot = true; if (S.listenCtrl) S.listenCtrl.abort();
    await turn(t, false); S.autopilot = false; $("typeIn").value = "";
  };
}
function openSheet() { renderSheet(); $("sheet").hidden = false; $("sheetBack").hidden = false; }
function closeSheet() { $("sheet").hidden = true; $("sheetBack").hidden = true; }

/* ------------------------------------------------------------------ dial screen */
function updateOrder() {
  S.orderId = $("order").value;
  $("orderPill").textContent = S.orderId;
  $("otpPill").textContent = S.orderId === "ORD_2048" ? "needs verification" : S.orderId === "ORD_9999" ? "already delivered" : "no OTP at handover";
}
function setLang(l) {
  S.lang = l;
  $("langs").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === l)));
}

async function init() {
  S.health = await api("/health");
  S.scen = await (await fetch("/static/scenarios.json")).json();
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  S.voice = S.health.voice;                        // gnani | recorded | browser (how the assistant speaks)
  S.listen = S.voice === "gnani" ? "server" : SR ? "browser" : "none";   // how the rider is heard
  if (location.hash === "#browser-voice" && SR) S.listen = "browser";
  if (location.hash === "#server-voice") S.listen = "server";   // test / troubleshooting: force Prisma's audio path
  const speaks = { gnani: "Gnani Timbre speaks every reply", recorded: "the assistant speaks with built-in recordings (no key)", browser: "the assistant uses this device's voice" }[S.voice];
  const hears = { server: "Gnani Prisma hears you", browser: "this browser's speech recognition hears you", none: "this browser can't hear you, so use What can I say?" }[S.listen];
  $("voiceNote").textContent = `${hears[0].toUpperCase() + hears.slice(1)}; ${speaks}. Tap Test sound first.`;
  $("voiceTag").textContent = { gnani: "Gnani voice", recorded: "Recorded voice (no key)", browser: "Device voice" }[S.voice];
  $("autoLang").hidden = S.listen !== "server";
  $("langs").style.gridTemplateColumns = S.listen === "server" ? "repeat(4, minmax(0,1fr))" : "repeat(3, minmax(0,1fr))";
  $("langLabel").textContent = S.listen === "server" ? "Greeting language (the assistant follows whatever you speak)" : "I will speak in";
}

$("langs").querySelectorAll("button").forEach((b) => (b.onclick = () => setLang(b.dataset.lang)));
$("order").onchange = updateOrder;
$("callBtn").onclick = () => { unlockAudio(); startCall().catch((e) => { sys(e.message); }); };
$("testBtn").onclick = async () => {
  unlockAudio();
  const lang = S.lang === "auto" ? "hi" : S.lang, b = $("testBtn");
  b.disabled = true; b.textContent = "Playing…";
  let ok = false;
  try { const r = await api("/tts/check", { json: { language: lang } }); if (r.audio_url) ok = (await Sound.play(r.audio_url)).ok; } catch (_) {}
  if (!ok) ok = (await Sound.speakDevice({ hi: "साउंड चेक", kn: "ಧ್ವನಿ ಪರೀಕ್ಷೆ", en: "Sound check" }[lang], lang)).ok;
  b.disabled = false; b.textContent = "Test sound";
  $("testNote").textContent = ok ? "Did you hear it? If not, turn up the volume and check the phone isn't on silent or connected to Bluetooth."
                                 : "The browser didn't play anything. Tap Test sound again; on iPhone, turn off Low Power Mode.";
};
Sound.onBlocked = () => { $("soundGate").hidden = false; };
$("soundGate").onclick = () => { unlockAudio(); $("soundGate").hidden = true; };
$("endBtn").onclick = () => { S.playingAll = false; finish("hangup"); };
$("againBtn").onclick = () => { $("ended").hidden = true; $("dial").hidden = false; };
$("muteBtn").onclick = () => { S.muted = !S.muted; $("muteBtn").setAttribute("aria-pressed", String(S.muted)); if (S.listenCtrl && S.listen === "browser") S.listenCtrl.abort(); setState(S.muted ? "Muted" : "Listening…", S.muted ? "idle" : "you"); };
$("handsBtn").onclick = () => { S.handsFree = !S.handsFree; $("handsBtn").setAttribute("aria-pressed", String(S.handsFree)); $("ptt").hidden = S.handsFree; if (S.listenCtrl) S.listenCtrl.abort(); };
$("whyBtn").onclick = () => { const on = $("whyBtn").getAttribute("aria-pressed") !== "true"; $("whyBtn").setAttribute("aria-pressed", String(on)); $("captions").classList.toggle("reasons-off", !on); };
$("openSheet1").onclick = openSheet; $("openSheet2").onclick = openSheet;
$("closeSheet").onclick = closeSheet; $("sheetBack").onclick = closeSheet;
window.__setu = window.__deliverysaathi = { S, turn, play, finish };   // used by the automated browser test
init().catch((e) => { $("voiceNote").textContent = "Server not reachable: " + e.message; });
