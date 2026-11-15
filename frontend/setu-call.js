/* SETU AI — live translated call, rider's side. Loaded after call.js and builds on it.

   Call Asha  ->  her phone rings (INTERPRET_RING_S)
     she answers               -> SETU translates live: you speak your language, she hears hers, and back
     she's busy / no answer    -> SETU's AI agent answers (call.js, the existing flow)
   Scenario playback ("What to say" -> Play) always goes straight to the AI agent. */
"use strict";

const SETU = {
  sid: null, state: null, ringS: 20, customerLang: "kn", queue: [], lines: [],
  QUICK_RIDER: {
    hi: ["मैं गेट पर हूँ, गार्ड को दे दूँ?", "आपका घर कहाँ है?", "मैं पाँच मिनट इंतज़ार कर रहा हूँ", "ओटीपी बताइए", "ठीक है, धन्यवाद"],
    kn: ["ನಾನು ಗೇಟ್ ಹತ್ತಿರ ಇದ್ದೇನೆ, ಗಾರ್ಡ್‌ಗೆ ಕೊಡಲಾ?", "ನಿಮ್ಮ ಮನೆ ಎಲ್ಲಿದೆ?", "OTP ಹೇಳಿ", "ಸರಿ, ಧನ್ಯವಾದ"],
    en: ["I'm at the gate, can I leave it with the guard?", "Where exactly is your house?", "Tell me the OTP", "Okay, thank you"],
  },
  QUICK_CUSTOMER: {
    kn: ["ಹತ್ತು ನಿಮಿಷ ಕಾಯಿರಿ, ನಾನು ಬರುತ್ತಿದ್ದೇನೆ", "ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡಿ", "ಸಂಜೆ 7 ಗಂಟೆಗೆ ಬನ್ನಿ", "ಧನ್ಯವಾದ"],
    hi: ["दस मिनट रुकिए, मैं आ रही हूँ", "सिक्योरिटी गार्ड को दे दीजिए", "शाम 7 बजे आइए", "धन्यवाद"],
    en: ["Please wait 10 minutes, I'm coming down", "Leave it with the security guard", "Please come at 7 pm", "Thank you"],
  },
};
const LNAME = { hi: "हिंदी", kn: "ಕನ್ನಡ", en: "English" };
const agentStart = startCall, agentFinish = finish, agentTurn = turn;
const riderLang = () => (S.lang === "auto" ? "hi" : S.lang);

/* ------------------------------------------------------------------ ringing Asha */
startCall = async function (opts = {}) {
  if (opts.keep || S.autopilot || !$("ringFirst").checked) return agentStart(opts);
  unlockAudio();
  S.mode = "ringing"; S.ended = false; SETU.queue = []; SETU.lines = [];
  $("captions").innerHTML = ""; clearWait();
  $("dial").hidden = true; $("ended").hidden = true; $("incall").hidden = false;
  $("whoSub").textContent = "Ringing Asha's phone…"; $("timer").textContent = "00:00";
  $("voiceTag").textContent = "SETU AI";
  setState("Ringing Asha…", "idle");
  const info = await api("/interpret/start", { json: { order_id: S.orderId, rider_lang: riderLang() } });
  SETU.sid = info.sid; SETU.state = "ringing"; SETU.ringS = info.ring_s; SETU.customerLang = info.customer_lang;
  openSetuSocket();
  sys(`Ringing Asha. If she answers, SETU translates ${LNAME[riderLang()]} ⇄ ${LNAME[SETU.customerLang]}. If she's busy, SETU's AI agent answers.`);
  $("waitSlot").innerHTML = `<div class="waitcard">
    <div class="small"><b>Ringing Asha's phone.</b> <span class="countdown" data-exp="${Date.now() / 1000 + SETU.ringS}"></span></div>
    <div class="row"><span class="small muted">Solo demo, answer as Asha:</span></div>
    <div class="row"><button class="yes" data-a="answer">Asha answers</button><button data-a="decline">Asha is busy</button></div></div>`;
  $("waitSlot").querySelectorAll("button").forEach((b) => (b.onclick = () => {
    b.disabled = true;
    api(`/interpret/${SETU.sid}/${b.dataset.a}`, { json: {} }).catch(() => {});
  }));
  const deadline = Date.now() + SETU.ringS * 1000;
  while (SETU.state === "ringing" && Date.now() < deadline && !S.ended) await Sound.ring();
  if (S.ended) return;
  if (SETU.state === "ringing") {
    try { await api(`/interpret/${SETU.sid}/timeout`, { method: "POST" }); SETU.state = "ai_agent"; } catch (_) {}
  }
  clearWait();
  if (SETU.state === "connected") return startTranslated();
  sys(SETU.reason === "customer_busy" ? "Asha is busy and handed the call to SETU's AI agent."
                                      : "Asha didn't answer. SETU's AI agent is taking the call.");
  S.mode = "agent";
  return agentStart({ keep: true });
};

function openSetuSocket() {
  if (SETU.ws) try { SETU.ws.close(); } catch (_) {}
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/rider/interp-${SETU.sid}`);
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "interpret_state") {
      SETU.state = m.data.state; SETU.reason = m.data.reason;
      if (m.data.customer_lang) SETU.customerLang = m.data.customer_lang;
      if (m.data.state !== "ringing") Sound.stop();
      if (m.data.state === "ended" && m.data.by === "customer" && S.mode === "setu") { sys("Asha ended the call."); finish("customer"); }
    } else if (m.type === "interpret_line") {
      SETU.queue.push(m.data);
      if (S.listenCtrl) S.listenCtrl.abort();
    }
  };
  SETU.ws = ws;
}

/* ------------------------------------------------------------------ the translated call */
async function startTranslated() {
  S.mode = "setu"; S.active = true; S.t0 = Date.now();
  clearInterval(S.timer);
  S.timer = setInterval(() => { const s = Math.floor((Date.now() - S.t0) / 1000); $("timer").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }, 500);
  $("whoSub").textContent = `Asha answered · SETU translating ${LNAME[riderLang()]} ⇄ ${LNAME[SETU.customerLang]}`;
  if (S.listen === "server") {
    try { await getMic(); await calibrate(); S.calibrated = true; releaseMic(); } catch (_) { S.listen = "none"; }
  }
  renderSolo();
  setuLoop();
}

function renderSolo() {
  const r = SETU.QUICK_RIDER[riderLang()] || SETU.QUICK_RIDER.en;
  const c = SETU.QUICK_CUSTOMER[SETU.customerLang] || SETU.QUICK_CUSTOMER.en;
  $("waitSlot").innerHTML = `<details class="waitcard setu-solo"><summary class="small">Solo demo: say a line for you or for Asha</summary>
    <div class="row"><span class="small muted">You say:</span></div>
    <div class="row">${r.map((t, i) => `<button data-r="${i}" class="${scriptClass(riderLang())}">${esc(t)}</button>`).join("")}</div>
    <div class="row"><span class="small muted">Asha says (in ${LNAME[SETU.customerLang]}):</span></div>
    <div class="row">${c.map((t, i) => `<button data-c="${i}" class="${scriptClass(SETU.customerLang)}">${esc(t)}</button>`).join("")}</div></details>`;
  $("waitSlot").querySelectorAll("[data-r]").forEach((b) => (b.onclick = async () => {
    S.autopilot = true; if (S.listenCtrl) S.listenCtrl.abort();
    const text = r[+b.dataset.r]; $("waitSlot").querySelector("details").open = false;
    try { await riderSays(text, riderLang()); await setuSay(text, true); } finally { S.autopilot = false; }
  }));
  $("waitSlot").querySelectorAll("[data-c]").forEach((b) => (b.onclick = () => ($("waitSlot").querySelector("details").open = false,
    api(`/interpret/${SETU.sid}/say`, { json: { who: "customer", text: c[+b.dataset.c], lang: SETU.customerLang } }).catch((e) => sys(e.message)))));
}

async function setuLoop() {
  while (S.active && S.mode === "setu") {
    if (SETU.queue.length) { await playLine(SETU.queue.shift()); continue; }
    if (S.autopilot || S.muted) { await sleep(150); continue; }
    setState(S.handsFree ? "Talk to Asha · SETU translates" : "Hold the button to talk", "you");
    S.listenCtrl = new AbortController();
    let heard = null;
    try { heard = await listenOnce(S.listenCtrl.signal); } catch (_) { heard = null; }
    S.listenCtrl = null;
    if (!S.active || heard == null || S.autopilot) continue;
    await setuSay(heard, false);
  }
}

async function setuSay(heard, played) {
  setState("Translating…", "think");
  let line;
  try {
    if (heard instanceof Blob) {
      const fd = new FormData();
      fd.append("who", "rider");
      fd.append("audio", heard, heard.type.includes("mp4") ? "clip.m4a" : heard.type.includes("ogg") ? "clip.ogg" : "clip.webm");
      if (Array.isArray(window.__mockSay) && window.__mockSay.length) fd.append("mock_transcript", window.__mockSay.shift());
      line = await api(`/interpret/${SETU.sid}/audio`, { method: "POST", body: fd });
    } else {
      line = await api(`/interpret/${SETU.sid}/say`, { json: { who: "rider", text: heard, lang: S.lang === "auto" ? null : S.lang } });
    }
  } catch (e) { if (e.status === 409) return finish("ended"); sys(e.message); return; }
  if (line.heard_nothing) return;
  SETU.lines.push(line);
  const tags = [`<span class="tag">${esc(LNAME[line.src_lang] || line.src_lang)}</span>`, methodTag(line)];
  if (played) tags.push(`<span class="tag">played by demo</span>`);
  if (line.masked_number) tags.push(`<span class="tag bad">number hidden</span>`);
  const heardBy = line.text ? `<div class="setu-sub">Asha hears (${esc(LNAME[line.tgt_lang])}): <span class="${scriptClass(line.tgt_lang)}">${esc(line.text)}</span></div>` : "";
  bubble("me", `<div class="${scriptClass(line.src_lang)}">${esc(line.original)}</div>${heardBy}<div class="meta">${tags.join("")}</div>`);
  if (/thank|धन्यवाद|ಧನ್ಯವಾದ|bye/i.test(line.original) && !line.text.includes("?")) setState("Say goodbye, or end the call", "you");
}

function methodTag(line) {
  const m = { phrases: "SETU doorstep phrases", model: "IndicTrans2 translation", untranslated: "not translated", same_language: "same language" }[line.method] || line.method;
  return `<span class="tag ${line.method === "untranslated" ? "bad" : "ok"} why">${esc(m)}</span>`;
}

async function playLine(line) {
  if (line.from === "setu") {
    bubble("sys", esc(line.text));
  } else {
    SETU.lines.push(line);
    const body = line.text
      ? `<div class="${scriptClass(line.tgt_lang)}">${esc(line.text)}</div><div class="setu-sub">Asha said (${esc(LNAME[line.src_lang])}): <span class="${scriptClass(line.src_lang)}">${esc(line.original)}</span></div>`
      : `<div class="${scriptClass(line.src_lang)}">${esc(line.original)}</div>`;
    bubble("ai setu", `<div class="setu-who">Asha · translated by SETU</div>${body}<div class="meta">${methodTag(line)}</div>`);
    (line.notes || []).forEach((n) => bubble("sys", esc(n)));
  }
  setState(line.from === "setu" ? "SETU speaking…" : "Asha (translated)…", "ai");
  for (const c of [...(line.clips || []), ...(line.note_audio || [])]) await speakClip(c, line.tgt_lang);
}

async function speakClip(c, lang) {
  if (c.audio_url) { try { await playUrl(c.audio_url); return; } catch (_) {} }
  if (!(await speakBrowser(c.text, lang, "ai"))) await readingPause(c.text);
}

/* ------------------------------------------------------------------ ending */
finish = async function (reason) {
  if (S.mode !== "setu" && S.mode !== "ringing") return agentFinish(reason);
  if (S.ended) return;
  S.ended = true; S.active = false;
  if (S.listenCtrl) S.listenCtrl.abort();
  Sound.stop(); releaseMic(); clearInterval(S.timer);
  let se = null;
  try { se = await api(`/interpret/${SETU.sid}/end`, { json: { who: reason === "customer" ? "customer" : "rider" } }); } catch (_) {}
  if (SETU.ws) try { SETU.ws.close(); } catch (_) {}
  showEndedSetu(se);
};

function showEndedSetu(se) {
  $("incall").hidden = true; $("ended").hidden = false; clearWait();
  $("endTime").textContent = `Call lasted ${$("timer").textContent}`;
  $("outKn").textContent = "";
  $("outEn").textContent = se && se.state === "ended" && se.answered_at
    ? `Asha answered and SETU translated ${LNAME[se.rider_lang]} ⇄ ${LNAME[se.customer_lang]}.`
    : "The call ended before Asha answered.";
  const lines = (se && se.lines) || [];
  $("did").innerHTML = lines.map((l) => `<li><b>${l.from === "rider" ? "You" : "Asha"}:</b> ${esc(l.original)}${l.text ? ` <span class="muted">→ ${esc(l.text)}</span>` : ""}</li>`).join("") || "<li>Nothing was said.</li>";
  $("chainLine").textContent = `${lines.length} translated lines · OTP-like numbers are hidden before translating`;
  S.mode = null;
}

/* Typed text ("What to say" → Type instead) goes to Asha when she is on the line. */
turn = async function (heard, played) {
  if (S.mode === "setu") return setuSay(heard, played);
  return agentTurn(heard, played);
};
window.__setu.SETU = SETU;
