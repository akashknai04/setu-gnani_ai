/* SETU AI sound: one place that makes the call audible on every phone and laptop.

   Why this exists (each line below fixed a real "I can't hear anything" case):
   - Browsers block sound until the person taps. unlock() must run inside that tap. It starts one
     shared <audio> element with a silent clip; after that the page may play it at any time
     (iOS needs it to be the same element).
   - An <audio> element plays even when an iPhone's silent switch is on; Web Audio does not.
     So every voice clip and the ringback go through the <audio> element.
   - While a microphone is open, phones route sound to the quiet earpiece. The call screen releases
     the microphone while the assistant speaks (see call.js) and tells iOS which mode it is in.
   - Device voices are the last resort only: many phones have no Kannada (or Hindi) voice.
*/
(function (root) {
  "use strict";
  // 0.3 s of silence, MP3 (plays everywhere, used to unlock the element inside the first tap)
  const SILENT = "data:audio/mpeg;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMAAAAAAAAAAAAAAA//NwwAAAAAAAAAAAAEluZm8AAAAPAAAADgAABm0ALCwsLCwsLDw8PDw8PDxNTU1NTU1NXV1dXV1dXW1tbW1tbW19fX19fX19jo6Ojo6Ojp6enp6enp6erq6urq6urr6+vr6+vr7Pz8/Pz8/P39/f39/f3+/v7+/v7+//////////AAAAAExhdmM2MC4zMQAAAAAAAAAAAAAAACQDaQAAAAAAAAZtL+ircQAAAAAAAAAAAAAAAAD/80DEAAAAA0gAAAAATEFNRTMuMTAwVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zQsRbAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zQMSkAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NCxKMAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NAxKQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/80LEowAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/80DEpAAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zQsSjAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zQMSkAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NCxKMAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NAxKQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/80LEowAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVMQU1FMy4xMDBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/80DEpAAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zQsSjAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVQ==";
  let player = null, ac = null, unlocked = false, onBlocked = null, current = null;
  const log = [];   // what actually played: used by the automated browser test and for troubleshooting

  function el() {
    if (!player) {
      player = new Audio();
      player.preload = "auto";
      player.setAttribute("playsinline", "");
      player.setAttribute("webkit-playsinline", "");
    }
    return player;
  }

  function session(type) {           // iOS 17+: "playback" = loudspeaker, "play-and-record" = call mode
    try { if (navigator.audioSession) navigator.audioSession.type = type; } catch (_) {}
  }

  /* Call this synchronously inside a tap or click handler. */
  function unlock() {
    const p = el();
    session("playback");
    if (!unlocked) {
      try { p.src = SILENT; p.volume = 1; const pr = p.play(); if (pr) pr.then(() => (unlocked = true)).catch(() => {}); } catch (_) {}
    }
    try {
      if (!ac) ac = new (root.AudioContext || root.webkitAudioContext)();
      if (ac.state !== "running") ac.resume();
    } catch (_) {}
    try {
      if ("speechSynthesis" in root) { const u = new SpeechSynthesisUtterance(" "); u.volume = 0; speechSynthesis.speak(u); }
    } catch (_) {}
  }

  /* Play a URL or data: URI to the end. Resolves {ok, reason}. Never hangs. */
  function play(src, opts) {
    opts = opts || {};
    const p = el();
    stop();
    return new Promise((resolve) => {
      let done = false, guard = null, t0 = performance.now(), started = false;
      const fin = (ok, reason) => {
        if (done) return; done = true; clearTimeout(guard);
        log.push({ src: String(src).slice(0, 30), ok, reason: reason || "", started, played_s: +(p.currentTime || 0).toFixed(2),
                   duration_s: isFinite(p.duration) ? +p.duration.toFixed(2) : null, ms: Math.round(performance.now() - t0) });
        p.onended = p.onerror = p.onloadedmetadata = null; current = null;
        resolve({ ok, reason });
      };
      current = fin;
      p.onplaying = () => (started = true);
      p.onended = () => fin(true);
      p.onerror = () => fin(false, "decode");
      p.onloadedmetadata = () => {   // safety net: some browsers drop "ended"
        const d = isFinite(p.duration) ? p.duration : 12;
        clearTimeout(guard); guard = setTimeout(() => fin(true, "timeout"), (d + 2.5) * 1000);
      };
      guard = setTimeout(() => fin(false, "timeout"), opts.maxMs || 20000);
      session("playback");
      p.src = src; p.volume = 1; p.currentTime = 0;
      const pr = p.play();
      if (pr && pr.catch) pr.then(() => (unlocked = true)).catch((e) => {
        const blocked = e && e.name === "NotAllowedError";
        if (blocked && onBlocked) onBlocked();
        fin(false, blocked ? "blocked" : "play");
      });
    });
  }

  function stop() {
    try { if (player) player.pause(); } catch (_) {}
    if (current) current(false, "stopped");
    try { if ("speechSynthesis" in root && speechSynthesis.speaking) speechSynthesis.cancel(); } catch (_) {}
  }

  /* ----- device voice: last resort, for typed lines that have no recording ----- */
  let voices = [];
  function loadVoices() { try { voices = speechSynthesis.getVoices() || []; } catch (_) { voices = []; } }
  if ("speechSynthesis" in root) { loadVoices(); try { speechSynthesis.addEventListener("voiceschanged", loadVoices); } catch (_) { speechSynthesis.onvoiceschanged = loadVoices; } }
  const voicesFor = (lang) => voices.filter((v) => (v.lang || "").replace("_", "-").toLowerCase().startsWith(lang));

  function speakDevice(text, lang, who) {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in root)) return resolve({ ok: false, reason: "no_speech" });
      if (!voices.length) loadVoices();
      const vs = voicesFor(lang);
      if (!vs.length) return resolve({ ok: false, reason: "no_voice" });
      const u = new SpeechSynthesisUtterance(text);
      u.voice = who === "rider" && vs.length > 1 ? vs[vs.length - 1] : vs[0];
      u.lang = u.voice.lang; u.volume = 1; u.rate = who === "rider" ? 1.02 : 0.97; u.pitch = who === "rider" ? 0.85 : 1.05;
      let done = false, keep = null;
      const fin = (ok) => { if (done) return; done = true; clearInterval(keep); resolve({ ok, reason: ok ? "" : "speech_error" }); };
      u.onend = () => fin(true); u.onerror = () => fin(false);
      const go = () => {
        speechSynthesis.speak(u);
        keep = setInterval(() => { try { speechSynthesis.resume(); } catch (_) {} }, 5000);   // Chrome pauses long speech
        setTimeout(() => fin(true), 2500 + text.length * 120);
      };
      if (speechSynthesis.speaking || speechSynthesis.pending) { speechSynthesis.cancel(); setTimeout(go, 80); } else go();
    });
  }

  function hasDeviceVoice(lang) { if (!voices.length) loadVoices(); return voicesFor(lang).length > 0; }

  /* Ringback tone (Indian 400+450 Hz, 0.4 s on, 0.2 s off, 0.4 s on). Built once as a WAV in memory. */
  let ringUrl = null;
  function ringbackUrl() {
    if (ringUrl) return ringUrl;
    const rate = 16000, secs = 2.2, n = Math.floor(rate * secs), data = new Int16Array(n);
    for (let i = 0; i < n; i++) {
      const t = i / rate, on = (t < 0.4) || (t >= 0.6 && t < 1.0);
      data[i] = on ? Math.round(5200 * (Math.sin(2 * Math.PI * 400 * t) + Math.sin(2 * Math.PI * 450 * t))) : 0;
    }
    const buf = new ArrayBuffer(44 + n * 2), dv = new DataView(buf);
    const w = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
    w(0, "RIFF"); dv.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt "); dv.setUint32(16, 16, true);
    dv.setUint16(20, 1, true); dv.setUint16(22, 1, true); dv.setUint32(24, rate, true); dv.setUint32(28, rate * 2, true);
    dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); w(36, "data"); dv.setUint32(40, n * 2, true);
    new Int16Array(buf, 44).set(data);
    ringUrl = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
    return ringUrl;
  }
  function ring() { return play(ringbackUrl(), { maxMs: 4000 }); }

  /* Short two-note chime for Asha's phone (Web Audio is fine here: it's a notification). */
  function chime() {
    try { if (navigator.vibrate) navigator.vibrate([160, 80, 160]); } catch (_) {}
    try {
      if (!ac) return; if (ac.state !== "running") ac.resume();
      const g = ac.createGain(); g.connect(ac.destination);
      [880, 1175].forEach((f, i) => { const o = ac.createOscillator(); o.frequency.value = f; o.connect(g); const t = ac.currentTime + i * 0.15;
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.1, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.14); o.start(t); o.stop(t + 0.15); });
    } catch (_) {}
  }

  root.Sound = { unlock, play, stop, speakDevice, hasDeviceVoice, ring, chime, session, log,
    set onBlocked(f) { onBlocked = f; }, get unlocked() { return unlocked; } };
})(typeof window !== "undefined" ? window : globalThis);
