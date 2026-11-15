// Every line the call can speak: AI replies from running all scenarios in 3 languages, every fixed
// rider-reply template with the default rules, and the rider's scripted lines.
const fs = require("fs"), W = process.argv[2];
const DATA = JSON.parse(fs.readFileSync(W + "/engine_data.json", "utf8"));
const SCEN = JSON.parse(fs.readFileSync("/home/claude/deliverysaathi/frontend/scenarios.json", "utf8"));
const make = require(W + "/engine.js");
const out = new Map();
const add = (role, lang, text) => { if (text) out.set(role + "|" + lang + "|" + text, { role, lang, text }); };
for (const sc of SCEN.scenarios) for (const lang of ["hi", "kn", "en"]) {
  let t = 1e6; const E = make(DATA, { clock: () => t });
  Object.assign(E.customer, sc.rules || {}); E.provider.mode = sc.provider_mode || "accept";
  const info = E.startCall(sc.order, lang); add("ai", lang, info.greeting[lang]);
  for (const st of sc.steps) {
    let r;
    if (st.say) { add("rider", lang, st.say[lang]); r = E.handleTranscript(info.call_id, st.say[lang], lang); }
    else if (st.customer === "no_answer") { t += 31; r = E.expireDue()[0]; }
    else if (st.customer) { const a = [...E.approvals.values()].find((x) => x.status === "pending"); r = E.decideApproval(a.id, st.customer, a.token); }
    else r = E.endCall(info.call_id, "rider_hung_up");
    add("ai", r.language || lang, r.reply_text);
  }
}
// every template with the default rules (covers typed lines that hit any intent)
const E = make(DATA);
for (const key of Object.keys(DATA.RIDER)) for (const lang of ["hi", "kn", "en"]) {
  const w = { window: E.fmtWindow("18:00", "20:00"), area: E.customer.area, landmark: E.customer.landmark };
  for (const who of ["guard", "neighbor"]) for (const time of ["18:00", "18:30", "19:00", "19:30", "20:00", "21:00", "17:00", "10:00"])
    add("ai", lang, E.riderReply(key, lang, Object.assign({}, w, { who, time })));
}
// a test line for the sound check
add("ai", "en", "Sound check. If you can hear this, the call audio works.");
add("ai", "hi", "साउंड चेक। अगर आपको यह सुनाई दे रहा है, तो कॉल की आवाज़ ठीक है।");
add("ai", "kn", "ಧ್ವನಿ ಪರೀಕ್ಷೆ. ಇದು ಕೇಳಿಸುತ್ತಿದ್ದರೆ, ಕರೆಯ ಧ್ವನಿ ಸರಿಯಾಗಿದೆ.");
fs.writeFileSync(process.argv[3], JSON.stringify([...out.values()], null, 0));
const c = {}; for (const v of out.values()) c[v.role + "-" + v.lang] = (c[v.role + "-" + v.lang] || 0) + 1;
console.log(out.size, "lines", JSON.stringify(c));
