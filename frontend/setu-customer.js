/* SETU AI — Asha's side of a live translated call. Loaded after customer.js.
   Incoming call -> "Answer with SETU translation" or "Let SETU's agent handle it".
   On the call: the rider's words arrive translated into her language (and spoken); she replies by
   voice (tap the mic), a quick reply, or typing, and SETU translates it for the rider. */
"use strict";
(function () {
  const LNAME = { hi: "हिंदी", kn: "ಕನ್ನಡ", en: "English" };
  const BCP = { hi: "hi-IN", kn: "kn-IN", en: "en-IN" };
  const QUICK = {
    kn: ["ಹತ್ತು ನಿಮಿಷ ಕಾಯಿರಿ, ನಾನು ಬರುತ್ತಿದ್ದೇನೆ", "ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡಿ", "ನನ್ನ ಬಾಗಿಲ ಹತ್ತಿರ ಇಡಿ", "ಸಂಜೆ 7 ಗಂಟೆಗೆ ಬನ್ನಿ", "ಹೌದು", "ಇಲ್ಲ", "ಧನ್ಯವಾದ"],
    hi: ["दस मिनट रुकिए, मैं आ रही हूँ", "सिक्योरिटी गार्ड को दे दीजिए", "दरवाज़े पर रख दीजिए", "शाम 7 बजे आइए", "हाँ", "नहीं", "धन्यवाद"],
    en: ["Please wait 10 minutes, I'm coming down", "Leave it with the security guard", "Leave it at my door", "Please come at 7 pm", "Yes", "No", "Thank you"],
  };
  const T = {   // her screen's own words, in her language
    en: { calling: "Delivery partner calling", speaks: "speaks", translate: "SETU translates into", answer: "Answer with SETU translation", agent: "Let SETU's agent handle it",
          on: "On call with the rider", translating: "SETU translating", talk: "Tap to talk", listening: "Listening… tap to send", type: "Type a reply", send: "Send", end: "End call",
          ended: "Call ended", close: "Close", rider: "Rider", you: "You", riderHears: "Rider hears", saidIn: "said in", noMic: "This browser can't listen. Use the quick replies or type.",
          handed: "SETU's AI agent is handling the call with your rules.", missed: "You missed the call. SETU's AI agent answered with your rules." },
    hi: { calling: "डिलीवरी पार्टनर का कॉल", speaks: "भाषा", translate: "SETU अनुवाद करेगा", answer: "SETU अनुवाद के साथ उठाएँ", agent: "SETU एजेंट को संभालने दें",
          on: "डिलीवरी पार्टनर से बात", translating: "SETU अनुवाद कर रहा है", talk: "बोलने के लिए दबाएँ", listening: "सुन रहा है… भेजने के लिए दबाएँ", type: "जवाब लिखें", send: "भेजें", end: "कॉल खत्म करें",
          ended: "कॉल खत्म", close: "बंद करें", rider: "डिलीवरी पार्टनर", you: "आप", riderHears: "पार्टनर सुनेगा", saidIn: "मूल", noMic: "यह ब्राउज़र सुन नहीं सकता। झटपट जवाब चुनें या लिखें।",
          handed: "SETU का AI एजेंट आपके नियमों से कॉल संभाल रहा है।", missed: "आपका कॉल छूट गया। SETU के AI एजेंट ने आपके नियमों से जवाब दिया।" },
    kn: { calling: "ಡೆಲಿವರಿ ಪಾರ್ಟ್ನರ್ ಕರೆ", speaks: "ಭಾಷೆ", translate: "SETU ಅನುವಾದಿಸುತ್ತದೆ", answer: "SETU ಅನುವಾದದೊಂದಿಗೆ ಸ್ವೀಕರಿಸಿ", agent: "SETU ಏಜೆಂಟ್ ನೋಡಿಕೊಳ್ಳಲಿ",
          on: "ಡೆಲಿವರಿ ಪಾರ್ಟ್ನರ್ ಜೊತೆ ಕರೆ", translating: "SETU ಅನುವಾದಿಸುತ್ತಿದೆ", talk: "ಮಾತನಾಡಲು ಒತ್ತಿ", listening: "ಕೇಳುತ್ತಿದೆ… ಕಳುಹಿಸಲು ಒತ್ತಿ", type: "ಉತ್ತರ ಬರೆಯಿರಿ", send: "ಕಳುಹಿಸಿ", end: "ಕರೆ ಮುಗಿಸಿ",
          ended: "ಕರೆ ಮುಗಿಯಿತು", close: "ಮುಚ್ಚಿ", rider: "ಡೆಲಿವರಿ ಪಾರ್ಟ್ನರ್", you: "ನೀವು", riderHears: "ಪಾರ್ಟ್ನರ್ ಕೇಳುವುದು", saidIn: "ಮೂಲ", noMic: "ಈ ಬ್ರೌಸರ್ ಕೇಳಲು ಸಾಧ್ಯವಿಲ್ಲ. ತ್ವರಿತ ಉತ್ತರಗಳನ್ನು ಬಳಸಿ ಅಥವಾ ಬರೆಯಿರಿ.",
          handed: "SETU AI ಏಜೆಂಟ್ ನಿಮ್ಮ ನಿಯಮಗಳಂತೆ ಕರೆ ನೋಡಿಕೊಳ್ಳುತ್ತಿದೆ.", missed: "ನಿಮ್ಮ ಕರೆ ತಪ್ಪಿತು. SETU AI ಏಜೆಂಟ್ ನಿಮ್ಮ ನಿಯಮಗಳಂತೆ ಉತ್ತರಿಸಿತು." },
  };
  const C = { sid: null, lang: "kn", riderLang: "hi", state: null, queue: [], busy: false, t0: 0, timer: null, rec: null, voice: "browser" };
  const box = () => document.getElementById("setuCall");
  const sc = (l) => (l === "kn" ? "kn" : l === "hi" ? "hi" : "");
  const t = (k) => (T[C.lang] || T.en)[k];
  fetch("/health").then((r) => r.json()).then((h) => { C.voice = h.voice; }).catch(() => {});

  function ring() {
    clearInterval(C.ringIv);
    let n = 0;
    const once = () => { if (C.state !== "ringing" || n++ > 12) return clearInterval(C.ringIv); try { chime(); } catch (_) {} };
    once(); C.ringIv = setInterval(once, 1800);
  }

  function showRinging(d) {
    C.sid = d.sid; C.riderLang = d.rider_lang; C.lang = d.customer_lang || "kn"; C.state = "ringing"; C.queue = [];
    const exp = Date.now() / 1000 + (d.ring_s || 20);
    const draw = () => {
      box().innerHTML = `<div class="setu-ring">
        <div class="eyebrow">SETU AI · ${esc(d.order_id)} · simulated</div>
        <div class="setu-avatar">R</div>
        <h2 class="${sc(C.lang)}">${esc(t("calling"))}</h2>
        <div class="small muted">${esc(t("speaks"))}: <b class="${sc(C.riderLang)}">${esc(LNAME[C.riderLang])}</b> · <span class="countdown" data-exp="${exp}"></span></div>
        <div class="setu-pick"><span class="small muted ${sc(C.lang)}">${esc(t("translate"))}</span>
          <div class="seg" role="group">${["kn", "en", "hi"].map((l) => `<button type="button" data-l="${l}" class="${sc(l)}" aria-pressed="${l === C.lang}">${LNAME[l]}</button>`).join("")}</div></div>
        <button class="btn primary block setu-answer ${sc(C.lang)}" id="setuAnswer">${esc(t("answer"))}</button>
        <button class="btn block ${sc(C.lang)}" id="setuDecline">${esc(t("agent"))}</button>
      </div>`;
      box().querySelectorAll("[data-l]").forEach((b) => (b.onclick = () => { C.lang = b.dataset.l; draw(); }));
      document.getElementById("setuAnswer").onclick = answer;
      document.getElementById("setuDecline").onclick = () => api(`/interpret/${C.sid}/decline`, { method: "POST" }).catch(() => {});
    };
    draw(); box().hidden = false; ring();
    clearInterval(C.cd);
    C.cd = setInterval(() => {
      const el = box().querySelector(".countdown"); if (!el) return clearInterval(C.cd);
      el.textContent = `${Math.max(0, Math.ceil(exp - Date.now() / 1000))}s`;
    }, 400);
  }

  async function answer() {
    try { Sound.unlock(); } catch (_) {}
    try { await api(`/interpret/${C.sid}/answer`, { json: { customer_lang: C.lang } }); }
    catch (e) { box().querySelector(".setu-ring").insertAdjacentHTML("beforeend", `<div class="small muted">${esc(e.message)}</div>`); }
  }

  function showCall() {
    C.state = "connected"; C.t0 = Date.now();
    const canListen = C.voice === "gnani" ? !!(navigator.mediaDevices && window.MediaRecorder) : !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    box().innerHTML = `<div class="setu-live">
      <div class="setu-head"><div><b class="${sc(C.lang)}">${esc(t("on"))}</b>
        <div class="small muted"><span class="${sc(C.lang)}">${esc(t("translating"))}</span> ${LNAME[C.riderLang]} ⇄ ${LNAME[C.lang]} · <span id="setuTimer">00:00</span></div></div>
        <button class="btn setu-end ${sc(C.lang)}" id="setuEnd">${esc(t("end"))}</button></div>
      <div class="setu-lines" id="setuLines" aria-live="polite"></div>
      <div class="setu-quick">${(QUICK[C.lang] || QUICK.en).map((q, i) => `<button type="button" data-q="${i}" class="${sc(C.lang)}">${esc(q)}</button>`).join("")}</div>
      <form class="setu-type" id="setuType"><input id="setuIn" class="${sc(C.lang)}" placeholder="${esc(t("type"))}" autocomplete="off">
        <button class="btn ${sc(C.lang)}" type="submit">${esc(t("send"))}</button></form>
      ${canListen ? `<button class="btn primary block setu-mic ${sc(C.lang)}" id="setuMic">${esc(t("talk"))}</button>` : `<div class="small muted ${sc(C.lang)}">${esc(t("noMic"))}</div>`}
    </div>`;
    clearInterval(C.timer);
    C.timer = setInterval(() => { const s = Math.floor((Date.now() - C.t0) / 1000); const el = document.getElementById("setuTimer"); if (el) el.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }, 500);
    box().querySelectorAll("[data-q]").forEach((b) => (b.onclick = () => say((QUICK[C.lang] || QUICK.en)[+b.dataset.q])));
    document.getElementById("setuType").onsubmit = (e) => { e.preventDefault(); const v = document.getElementById("setuIn").value.trim(); if (v) { document.getElementById("setuIn").value = ""; say(v); } };
    document.getElementById("setuEnd").onclick = () => api(`/interpret/${C.sid}/end`, { json: { who: "customer" } }).catch(() => {});
    const mic = document.getElementById("setuMic"); if (mic) mic.onclick = toggleMic;
    drain();
  }

  function addLine(cls, html) {
    const el = document.getElementById("setuLines"); if (!el) return;
    const d = document.createElement("div"); d.className = "setu-line " + cls; d.innerHTML = html;
    el.appendChild(d); el.scrollTop = el.scrollHeight;
  }

  async function say(text, blob) {
    let line;
    try {
      if (blob) {
        const fd = new FormData(); fd.append("who", "customer"); fd.append("lang", C.lang);
        fd.append("audio", blob, blob.type.includes("mp4") ? "clip.m4a" : "clip.webm");
        line = await api(`/interpret/${C.sid}/audio`, { method: "POST", body: fd });
      } else {
        line = await api(`/interpret/${C.sid}/say`, { json: { who: "customer", text, lang: C.lang } });
      }
    } catch (e) { addLine("sys", esc(e.message)); return; }
    if (line.heard_nothing) return;
    shown.add(line.id);
    addLine("me", `<div class="${sc(line.src_lang)}">${esc(line.original)}</div>` +
      (line.text ? `<div class="setu-sub"><span class="${sc(C.lang)}">${esc(t("riderHears"))}</span> (${LNAME[line.tgt_lang]}): <span class="${sc(line.tgt_lang)}">${esc(line.text)}</span></div>` : "") +
      (line.notes || []).map((n) => `<div class="setu-note">${esc(n)}</div>`).join(""));
  }
  const shown = new Set();

  async function drain() {
    if (C.busy) return;
    C.busy = true;
    while (C.queue.length && document.getElementById("setuLines")) {
      const line = C.queue.shift();
      if (line.from === "setu") addLine("sys", esc(line.text));
      else addLine("them", `<div class="setu-who ${sc(C.lang)}">${esc(t("rider"))} · SETU</div>` +
        (line.text ? `<div class="${sc(line.tgt_lang)}">${esc(line.text)}</div><div class="setu-sub">${esc(t("saidIn"))} (${LNAME[line.src_lang]}): <span class="${sc(line.src_lang)}">${esc(line.original)}</span></div>`
                   : `<div class="${sc(line.src_lang)}">${esc(line.original)}</div>`) +
        (line.notes || []).map((n) => `<div class="setu-note">${esc(n)}</div>`).join(""));
      for (const c of [...(line.clips || []), ...(line.note_audio || [])]) {
        let ok = false;
        if (c.audio_url) ok = (await Sound.play(c.audio_url)).ok;
        if (!ok) ok = (await Sound.speakDevice(c.text, line.tgt_lang, "rider")).ok;
        if (!ok) await new Promise((r) => setTimeout(r, Math.min(6000, 700 + c.text.length * 45)));
      }
    }
    C.busy = false;
  }

  /* her microphone: Gnani Prisma when live (record, then send), else the browser's recogniser */
  async function toggleMic() {
    const btn = document.getElementById("setuMic");
    if (C.rec) { C.rec.stop(); return; }
    try { Sound.unlock(); } catch (_) {}
    if (C.voice === "gnani") {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const chunks = []; const rec = new MediaRecorder(stream); C.rec = rec;
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => { stream.getTracks().forEach((x) => x.stop()); C.rec = null; btn.textContent = t("talk"); btn.classList.remove("rec");
        say(null, new Blob(chunks, { type: rec.mimeType || "audio/webm" })); };
      rec.start(100); btn.textContent = t("listening"); btn.classList.add("rec");
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = new SR(); r.lang = BCP[C.lang]; r.interimResults = false; C.rec = { stop: () => r.stop() };
    r.onresult = (e) => { const txt = Array.from(e.results).map((x) => x[0].transcript).join(" ").trim(); if (txt) say(txt); };
    r.onend = () => { C.rec = null; btn.textContent = t("talk"); btn.classList.remove("rec"); };
    btn.textContent = t("listening"); btn.classList.add("rec");
    try { r.start(); } catch (_) { r.onend(); }
  }

  function showEnded(msgKey) {
    clearInterval(C.timer); clearInterval(C.ringIv); C.state = "ended";
    try { Sound.stop(); } catch (_) {}
    const extra = msgKey ? `<div class="small ${sc(C.lang)}">${esc(t(msgKey))}</div>` : "";
    const lines = document.getElementById("setuLines");
    box().innerHTML = `<div class="setu-ring"><h2 class="${sc(C.lang)}">${esc(t("ended"))}</h2>${extra}
      ${lines ? `<div class="setu-lines done">${lines.innerHTML}</div>` : ""}
      <button class="btn block ${sc(C.lang)}" id="setuClose">${esc(t("close"))}</button></div>`;
    const close = () => { box().hidden = true; box().innerHTML = ""; };
    document.getElementById("setuClose").onclick = close;
    if (msgKey) setTimeout(() => { if (C.state === "ended") close(); }, 4000);   // handed to the agent: her approval cards must be visible
  }

  window.SetuCustomer = {
    on(type, d) {
      if (type === "interpret_ring") { showTab("pane-req"); return showRinging(d); }
      if (!C.sid || d.sid !== C.sid) return;
      if (type === "interpret_state") {
        if (d.state === "connected") { if (d.customer_lang) C.lang = d.customer_lang; showCall(); }
        else if (d.state === "ai_agent") showEnded(d.reason === "customer_busy" ? "handed" : "missed");
        else if (d.state === "ended") showEnded(null);
      } else if (type === "interpret_line") {
        if (shown.has(d.id)) return;
        C.queue.push(d); drain();
      }
    },
    state: C,
  };
})();
