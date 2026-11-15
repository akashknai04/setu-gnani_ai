"""Meaning-based translation for doorstep conversations (rider <-> customer), Hindi / Kannada / English.

Not word-for-word. Each sentence is matched against the things people actually say at a delivery
("I'm at the gate", "leave it with the guard", "wait 5 minutes", "come at 7"), and the same meaning is
said in the listener's language from a fixed, reviewed sentence. Works offline, can't invent content,
and an OTP or any long number is masked before anything is translated.

Anything it doesn't recognise is left to the optional free-translation model (backend/interpreter/model.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.engine.messages import fmt_time
from backend.intent.fast_path import _normalize, extract_time

LANGS = ("en", "hi", "kn")

# ---------------------------------------------------------------- what people say, as patterns
_P = {
    "otp": r"\botp\b|o\.\s?t\.\s?p|\bo t p\b|ओटीपी|ಒಟಿಪಿ|ಓಟಿಪಿ|one.?time.?pass|verification code|delivery code|\[redacted\]",
    "arrived": r"(at|outside|near|in front of) (the |your )?(gate|door|building|house|location)|i'?m (here|outside|downstairs)|"
               r"i (have )?(arrived|reached)|\b(reached|arrived)\b|gate (pe|par)|bahar khada|pahunch (gaya|gayi|gaye)|"
               r"aa gaya (hoon|hu)|पहुँच (गया|गई)|पहुंच (गया|गई)|गेट (पे|पर)|बाहर खड़ा|"
               r"ಗೇಟ್ (ಹತ್ತಿರ|ಬಳಿ|ಹತ್ರ)|ಬಂದಿದ್ದೀನಿ|ಬಂದಿದ್ದೇನೆ|ಬಂದಿದೀನಿ|bandidini|bandiddini|bandidini|gate hathra|gate hatra",
    "location": r"address|location|landmark|where (is|exactly|do|are)|which (building|floor|gate|block|tower|flat)|"
                r"\bkahan\b|\bkahaan\b|\bkaha\b|\bkidhar\b|किधर|कहाँ|कहां|ಎಲ್ಲಿ|\belli\b|ವಿಳಾಸ|lokeshan|लोकेशन|ಲೊಕೇಶನ್",
    "come_down": r"come (down|to the gate|outside|out|and (take|collect))|can you come|"
                 r"(neeche|niche|bahar|gate (pe|par)) (aao|aaiye|aaye|aa jao|aa jaiye|aa sakte)|नीचे (आइए|आओ|आ जाइए|आ सकते)|"
                 r"बाहर (आइए|आओ|आ सकते)|ಕೆಳಗೆ ಬನ್ನಿ|kelage banni|horage banni|ಹೊರಗೆ ಬನ್ನಿ|gate hathra banni",
    "guard": r"guard|security|watchman|chowkidar|chaukidar|darwan|reception|चौकीदार|गार्ड|सिक्योरिटी|सेक्युरिटी|"
             r"वॉचमैन|वाचमैन|ವಾಚ್ ?ಮನ್|ಗಾರ್ಡ್|ಸೆಕ್ಯುರಿಟಿ|ಸೆಕ್ಯೂರಿಟಿ",
    "neighbor": r"neighbou?r|next door|padosi|padosan|पड़ोस|पडोस|ಪಕ್ಕದ ?ಮನೆ|pakkad?a ?mane|nerehore|ನೆರೆಹೊರೆ",
    "door": r"(at|near|outside|in front of) (the |my )?door|doorstep|darwaze (pe|par|ke paas)|दरवाज़े|दरवाजे|"
            r"bagil|ಬಾಗಿಲ",
    "wait": r"\bwait\b|ruko|rukiye|rukna|ruk jao|ruk jaiye|रुको|रुकिए|रुकिये|रुक जाइए|kaayi|\bkayi\b|ಕಾಯಿರಿ|ಕಾಯಿ|"
            r"\bwaiting\b|intezaar|intezar|इंतज़ार|इंतजार|ಕಾಯ್ತಾ|kaaytha",
    "coming": r"\bcoming\b|on (my|the) way|aa (raha|rahi|rha|rhi)|aata (hoon|hu)|aati (hoon|hu)|आ (रहा|रही)|"
              r"आता हूँ|आती हूँ|ಬರ್ತೀನಿ|ಬರುತ್ತೇನೆ|ಬರ್ತಾ ಇದ್ದೀನಿ|ಬರುತ್ತಿದ್ದೇನೆ|bartini|barthini|barta iddini|bartha iddini",
    "late": r"traffic|\blate\b|\bder\b|देर|लेट|ट्रैफिक|ट्रैफ़िक|ಟ್ರಾಫಿಕ್|ತಡ|\btada\b",
    "not_home": r"not (at )?home|ghar (pe|par) (koi )?(nahi|nahin)|घर (पे|पर) (कोई )?नहीं|ಮನೆಯಲ್ಲಿ (ಯಾರೂ )?ಇಲ್ಲ|"
                r"maneli (yaaru )?illa|nobody (is )?(home|there|answering)|not (picking|answering)|"
                r"(phone|call) (nahi|nahin) utha|फ़ोन नहीं|फोन नहीं|ಫೋನ್ (ಎತ್ತುತ್ತಿಲ್ಲ|ತೆಗೆಯುತ್ತಿಲ್ಲ)|phone ettilla",
    "call_later": r"call (you )?back|call (you )?later|(baad|bad) (me|mein) (call|phone)|बाद में (कॉल|फ़ोन|फोन)|"
                  r"ಆಮೇಲೆ (ಕಾಲ್|ಫೋನ್)|amele (call|phone)",
    "have_order": r"(your|aapka|aapki|nimma|ನಿಮ್ಮ|आपका|आपकी) (order|parcel|delivery|package|ऑर्डर|पार्सल|ಆರ್ಡರ್|ಪಾರ್ಸೆಲ್)|"
                  r"delivery (hai|ide|aayi|aaya)",
    "greeting": r"\b(hello|hallo|helo|hi|hey|namaste|namaskar|namaskara)\b|ಹಲೋ|हेलो|हैलो|नमस्ते|ನಮಸ್ಕಾರ",
    "thanks": r"\b(thank ?you|thanks|thank u|dhanyavaad|dhanyavad|dhanyawad|shukriya|thanku|bye|goodbye)\b|"
              r"धन्यवाद|शुक्रिया|थैंक|ಧನ್ಯವಾದ|ಥ್ಯಾಂಕ್|ಬೈ|बाय",
}
_WHOLE = {  # only when that is the whole sentence
    "yes": r"(yes|yeah|yep|ok|okay|sure|haan|haan ji|ha|han|ji|ji haan|theek hai|thik hai|achha|accha|houdu|haudu|"
           r"sari|aytu|ಹೌದು|ಸರಿ|ಆಯ್ತು|ಹಾ|हाँ|हां|जी|जी हाँ|ठीक है|ओके|अच्छा)( ji| sir| madam)?",
    "no": r"(no|nahi|nahin|na|nako|illa|beda|ಇಲ್ಲ|ಬೇಡ|नहीं|ना)( ji| sir| madam)?",
}
_RX = {k: re.compile(v) for k, v in _P.items()}
_RX_WHOLE = {k: re.compile(rf"^{v}$") for k, v in _WHOLE.items()}

_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30,
         "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "das": 10, "dus": 10,
         "pandrah": 15, "bees": 20, "tees": 30, "ondu": 1, "eradu": 2, "mooru": 3, "nalku": 4, "aidu": 5,
         "hattu": 10, "hadinaidu": 15, "ippattu": 20, "moovattu": 30,
         "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "दस": 10, "पंद्रह": 15, "बीस": 20, "तीस": 30,
         "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಹತ್ತು": 10, "ಹದಿನೈದು": 15, "ಇಪ್ಪತ್ತು": 20, "ಮೂವತ್ತು": 30}
_MIN = re.compile(r"(\d{1,2}|" + "|".join(sorted(map(re.escape, _NUMW), key=len, reverse=True)) +
                  r")\s*-?\s*(?:min|mins|minute|minutes|minat|minit|मिनट|ನಿಮಿಷ|nimisha|nimsha|nimisa)")


def extract_minutes(t: str) -> int | None:
    m = _MIN.search(t)
    if not m:
        return None
    tok = m.group(1)
    n = int(tok) if tok.isdigit() else _NUMW.get(tok)
    return n if n and 0 < n <= 90 else None


# ---------------------------------------------------------------- what the listener hears
# {m|f} picks the speaker's grammatical gender (Hindi first person). Keys: meaning, or meaning@speaker.
T: dict[str, dict[str, str]] = {
    "arrived": {"en": "I have reached your location. I'm at the gate.",
                "hi": "मैं आपकी लोकेशन पर पहुँच ग{या|ई} हूँ। मैं गेट पर हूँ।",
                "kn": "ನಾನು ನಿಮ್ಮ ವಿಳಾಸಕ್ಕೆ ಬಂದಿದ್ದೇನೆ. ಗೇಟ್ ಹತ್ತಿರ ಇದ್ದೇನೆ."},
    "location": {"en": "Where exactly is your house? Which building or floor?",
                 "hi": "आपका घर ठीक कहाँ है? कौन-सी बिल्डिंग या फ्लोर?",
                 "kn": "ನಿಮ್ಮ ಮನೆ ಸರಿಯಾಗಿ ಎಲ್ಲಿದೆ? ಯಾವ ಬಿಲ್ಡಿಂಗ್ ಅಥವಾ ಫ್ಲೋರ್?"},
    "come_down@rider": {"en": "Can you come to the gate and collect it?",
                        "hi": "क्या आप गेट पर आकर ले सकते हैं?",
                        "kn": "ನೀವು ಗೇಟ್ ಹತ್ತಿರ ಬಂದು ತೆಗೆದುಕೊಳ್ಳಬಹುದೇ?"},
    "come_down@customer": {"en": "Please come up to the door.",
                           "hi": "कृपया दरवाज़े तक ऊपर आ जाइए।",
                           "kn": "ದಯವಿಟ್ಟು ಬಾಗಿಲವರೆಗೆ ಮೇಲೆ ಬನ್ನಿ."},
    "guard@rider": {"en": "Can I leave it with the security guard?",
                    "hi": "क्या मैं इसे सिक्योरिटी गार्ड को दे दूँ?",
                    "kn": "ಇದನ್ನು ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡಲಾ?"},
    "guard@customer": {"en": "Please leave it with the security guard.",
                       "hi": "कृपया इसे सिक्योरिटी गार्ड को दे दीजिए।",
                       "kn": "ದಯವಿಟ್ಟು ಇದನ್ನು ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್‌ಗೆ ಕೊಡಿ."},
    "neighbor@rider": {"en": "Can I leave it with your neighbour?",
                       "hi": "क्या मैं इसे आपके पड़ोसी को दे दूँ?",
                       "kn": "ಇದನ್ನು ನಿಮ್ಮ ಪಕ್ಕದ ಮನೆಯವರಿಗೆ ಕೊಡಲಾ?"},
    "neighbor@customer": {"en": "Please leave it with my neighbour.",
                          "hi": "कृपया इसे मेरे पड़ोसी को दे दीजिए।",
                          "kn": "ದಯವಿಟ್ಟು ಇದನ್ನು ನಮ್ಮ ಪಕ್ಕದ ಮನೆಯವರಿಗೆ ಕೊಡಿ."},
    "door@rider": {"en": "Shall I leave it at your door?",
                   "hi": "क्या मैं इसे आपके दरवाज़े पर रख दूँ?",
                   "kn": "ಇದನ್ನು ನಿಮ್ಮ ಬಾಗಿಲ ಹತ್ತಿರ ಇಡಲಾ?"},
    "door@customer": {"en": "Please leave it at my door.",
                      "hi": "कृपया इसे मेरे दरवाज़े पर रख दीजिए।",
                      "kn": "ದಯವಿಟ್ಟು ಇದನ್ನು ನನ್ನ ಬಾಗಿಲ ಹತ್ತಿರ ಇಡಿ."},
    "wait@rider": {"en": "I'm waiting here.", "hi": "मैं यहाँ इंतज़ार कर रह{ा|ी} हूँ।",
                   "kn": "ನಾನು ಇಲ್ಲೇ ಕಾಯುತ್ತಿದ್ದೇನೆ."},
    "wait@customer": {"en": "Please wait{min: {minutes} minutes}.",
                      "hi": "कृपया{min: {minutes} मिनट} रुकिए।",
                      "kn": "ದಯವಿಟ್ಟು{min: {minutes} ನಿಮಿಷ} ಕಾಯಿರಿ."},
    "coming@rider": {"en": "I'm on my way{min:, I'll reach in {minutes} minutes}.",
                     "hi": "मैं रास्ते में हूँ{min:, {minutes} मिनट में पहुँच जाऊँग{ा|ी}}।",
                     "kn": "ನಾನು ದಾರಿಯಲ್ಲಿದ್ದೇನೆ{min:, {minutes} ನಿಮಿಷದಲ್ಲಿ ಬರುತ್ತೇನೆ}."},
    "coming@customer": {"en": "I'm coming now{min:, in {minutes} minutes}.",
                        "hi": "मैं अभी आ रह{ा|ी} हूँ{min:, {minutes} मिनट में}।",
                        "kn": "ನಾನು ಈಗ ಬರುತ್ತಿದ್ದೇನೆ{min:, {minutes} ನಿಮಿಷದಲ್ಲಿ}."},
    "late@rider": {"en": "I'm stuck in traffic, I'll be a little late{min:, about {minutes} minutes}.",
                   "hi": "मैं ट्रैफिक में फँस{ा|ी} हूँ, थोड़ी देर होगी{min:, लगभग {minutes} मिनट}।",
                   "kn": "ನಾನು ಟ್ರಾಫಿಕ್‌ನಲ್ಲಿ ಸಿಲುಕಿದ್ದೇನೆ, ಸ್ವಲ್ಪ ತಡವಾಗುತ್ತದೆ{min:, ಸುಮಾರು {minutes} ನಿಮಿಷ}."},
    "late@customer": {"en": "I'll be a little late{min:, about {minutes} minutes}.",
                      "hi": "मुझे थोड़ी देर होगी{min:, लगभग {minutes} मिनट}।",
                      "kn": "ನನಗೆ ಸ್ವಲ್ಪ ತಡವಾಗುತ್ತದೆ{min:, ಸುಮಾರು {minutes} ನಿಮಿಷ}."},
    "time@rider": {"en": "Can I come at {time}?", "hi": "क्या मैं {time} बजे आ सकत{ा|ी} हूँ?",
                   "kn": "ನಾನು {time}ಕ್ಕೆ ಬರಲಾ?"},
    "time@customer": {"en": "Please come at {time}.", "hi": "कृपया {time} बजे आइए।",
                      "kn": "ದಯವಿಟ್ಟು {time}ಕ್ಕೆ ಬನ್ನಿ."},
    "minutes@rider": {"en": "I'll reach in {minutes} minutes.", "hi": "मैं {minutes} मिनट में पहुँच जाऊँग{ा|ी}।",
                      "kn": "ನಾನು {minutes} ನಿಮಿಷದಲ್ಲಿ ಬರುತ್ತೇನೆ."},
    "minutes@customer": {"en": "Give me {minutes} minutes.", "hi": "मुझे {minutes} मिनट दीजिए।",
                         "kn": "ನನಗೆ {minutes} ನಿಮಿಷ ಕೊಡಿ."},
    "not_home@rider": {"en": "Nobody is answering at the house.", "hi": "घर पर कोई जवाब नहीं दे रहा है।",
                       "kn": "ಮನೆಯಲ್ಲಿ ಯಾರೂ ಉತ್ತರಿಸುತ್ತಿಲ್ಲ."},
    "not_home@customer": {"en": "I'm not at home right now.", "hi": "मैं अभी घर पर नहीं हूँ।",
                          "kn": "ನಾನು ಈಗ ಮನೆಯಲ್ಲಿ ಇಲ್ಲ."},
    "call_later": {"en": "I'll call you back in a few minutes.", "hi": "मैं कुछ मिनट में आपको वापस कॉल करूँग{ा|ी}।",
                   "kn": "ನಾನು ಕೆಲವು ನಿಮಿಷಗಳಲ್ಲಿ ಮತ್ತೆ ಕರೆ ಮಾಡುತ್ತೇನೆ."},
    "have_order": {"en": "I have your order with me.", "hi": "आपका ऑर्डर मेरे पास है।",
                   "kn": "ನಿಮ್ಮ ಆರ್ಡರ್ ನನ್ನ ಬಳಿ ಇದೆ."},
    "otp@rider": {"en": "I need the OTP to hand over the order.",
                  "hi": "ऑर्डर देने के लिए मुझे OTP चाहिए।",
                  "kn": "ಆರ್ಡರ್ ಕೊಡಲು ನನಗೆ OTP ಬೇಕು."},
    "otp@customer": {"en": "About the OTP: I will share it in person.",
                     "hi": "OTP मैं खुद मिलकर बताऊँग{ा|ी}।",
                     "kn": "OTP ಅನ್ನು ನಾನು ಖುದ್ದಾಗಿ ಹೇಳುತ್ತೇನೆ."},
    "yes": {"en": "Yes, okay.", "hi": "हाँ, ठीक है।", "kn": "ಹೌದು, ಸರಿ."},
    "no": {"en": "No.", "hi": "नहीं।", "kn": "ಇಲ್ಲ."},
    "greeting": {"en": "Hello!", "hi": "नमस्ते!", "kn": "ನಮಸ್ಕಾರ!"},
    "thanks": {"en": "Thank you!", "hi": "धन्यवाद!", "kn": "ಧನ್ಯವಾದಗಳು!"},
}

# Safety notes shown (and spoken) by SETU itself, never as the other person's words.
NOTES = {
    "otp_to_customer": {"en": "SETU: share the OTP only in person, when you get the parcel. Never on a call.",
                        "hi": "SETU: OTP सिर्फ़ पार्सल मिलते समय आमने-सामने बताइए। कॉल पर कभी नहीं।",
                        "kn": "SETU: OTP ಅನ್ನು ಪಾರ್ಸೆಲ್ ಸಿಗುವಾಗ ಮಾತ್ರ ಮುಖಾಮುಖಿ ಹೇಳಿ. ಕರೆಯಲ್ಲಿ ಎಂದಿಗೂ ಬೇಡ."},
    "number_hidden": {"en": "SETU hid a number that looked like an OTP.",
                      "hi": "SETU ने OTP जैसा दिखने वाला नंबर छिपा दिया।",
                      "kn": "SETU OTP ತರಹ ಕಾಣುವ ಸಂಖ್ಯೆಯನ್ನು ಮರೆಮಾಡಿದೆ."},
}

ORDER = ["greeting", "arrived", "have_order", "not_home", "late", "coming", "wait", "location", "come_down",
         "guard", "neighbor", "door", "time", "minutes", "call_later", "otp", "thanks"]


@dataclass
class PhraseResult:
    meanings: list[str] = field(default_factory=list)
    text: str = ""
    parts: list[str] = field(default_factory=list)   # one fixed sentence per meaning (each has a recording)
    time: str | None = None
    minutes: int | None = None

    @property
    def ok(self) -> bool:
        return bool(self.meanings)


def _gender(s: str, g: str) -> str:
    return re.sub(r"\{([^{}|]*)\|([^{}|]*)\}", lambda m: m.group(1) if g != "f" else m.group(2), s)


def _slots(s: str, minutes: int | None, time: str | None) -> str:
    s = re.sub(r"\{min:([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", lambda m: m.group(1) if minutes else "", s)
    return s.replace("{minutes}", str(minutes or "")).replace("{time}", time or "")


def render(meaning: str, speaker: str, lang: str, gender: str = "m", minutes=None, time=None) -> str:
    tpl = T.get(f"{meaning}@{speaker}") or T.get(meaning)
    if not tpl:
        return ""
    return _slots(_gender(tpl[lang], gender), minutes, time)


def understand(text: str) -> PhraseResult:
    """Which doorstep meanings does this sentence carry, in order of appearance."""
    t = _normalize(text)
    if not t:
        return PhraseResult()
    bare = re.sub(r"[.।!]+$", "", t).strip()
    for k, rx in _RX_WHOLE.items():
        if rx.match(bare):
            return PhraseResult([k])
    found: list[tuple[int, str]] = []
    for k, rx in _RX.items():
        m = rx.search(t)
        if m:
            found.append((m.start(), k))
    minutes = extract_minutes(t)
    time = None if minutes else extract_time(t)
    if time:
        found.append((len(t), "time"))
    if minutes and not any(k in ("wait", "coming", "late") for _, k in found):
        found.append((len(t), "minutes"))
    keys = [k for _, k in sorted(found)]
    if "otp" in keys:  # an OTP sentence is only about the OTP
        keys = ["otp"]
    if keys and set(keys) - {"have_order", "greeting"}:
        keys = [k for k in keys if k != "have_order"]
    if "door" in keys and ("guard" in keys or "neighbor" in keys or "arrived" in keys):
        keys.remove("door")   # "guard at the door", "I'm at the door": not a request to leave it at the door
    if "arrived" in keys and "come_down" in keys:
        pass
    if "location" in keys and "arrived" in keys and "where" not in t and "कहाँ" not in t and "ಎಲ್ಲಿ" not in t:
        keys.remove("location")  # "I'm at your location"
    if "time" in keys and "late" in keys:
        keys.remove("late")
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return PhraseResult(out[:3], time=time, minutes=minutes)


_PART = {"hi": ("सुबह", "दोपहर", "शाम", "रात"), "kn": ("ಬೆಳಿಗ್ಗೆ", "ಮಧ್ಯಾಹ್ನ", "ಸಂಜೆ", "ರಾತ್ರಿ")}


def say_time(hhmm: str, lang: str) -> str:
    """'18:30' -> '6:30 PM' / 'शाम 6:30' / 'ಸಂಜೆ 6:30'."""
    if lang == "en":
        return fmt_time(hhmm)
    h, m = (int(x) for x in hhmm.split(":"))
    part = _PART[lang][0 if h < 12 else 1 if h < 16 else 2 if h < 20 else 3]
    h12 = h % 12 or 12
    return f"{part} {h12}" + (f":{m:02d}" if m else "")


MINUTE_STEPS = (2, 5, 10, 15, 20, 30)


def all_fixed_sentences() -> list[dict]:
    """Every fixed interpreter sentence that can be recorded ahead of time (no clock times).
    role 'rider' = the rider's words in the rider's (male) voice; 'ai' = customer's words and SETU's notes."""
    out = []
    for key, tpl in T.items():
        meaning, _, who = key.partition("@")
        speakers = [who] if who else ["rider", "customer"]
        for sp in speakers:
            role, g = ("rider", "m") if sp == "rider" else ("ai", "f")
            for lang in LANGS:
                s = tpl[lang]
                if "{time}" in s:
                    continue
                variants = [None] + list(MINUTE_STEPS) if ("{min:" in s or "{minutes}" in s) else [None]
                for mins in variants:
                    if "{minutes}" in s.replace("{min:", "") and mins is None and "{min:" not in s:
                        continue
                    out.append({"role": role, "lang": lang, "text": render(meaning, sp, lang, g, mins)})
    from backend.interpreter.routes import SYSTEM
    from backend.interpreter.service import UNTRANSLATED
    for group in list(NOTES.values()) + list(SYSTEM.values()) + [UNTRANSLATED]:
        for lang, s in group.items():
            out.append({"role": "ai", "lang": lang, "text": s})
    seen, uniq = set(), []
    for l in out:
        k = (l["role"], l["lang"], l["text"])
        if l["text"] and k not in seen:
            seen.add(k)
            uniq.append(l)
    return uniq


def translate(text: str, speaker: str, tgt: str, gender: str = "m") -> PhraseResult:
    r = understand(text)
    if not r.ok:
        return r
    t = say_time(r.time, tgt) if r.time else None
    parts, used = [], False
    for k in r.meanings:
        takes = k in ("wait", "coming", "late", "minutes")
        parts.append(render(k, speaker, tgt, gender, r.minutes if takes and not used else None, t))
        used = used or takes
    r.parts = [p for p in parts if p]
    r.text = " ".join(r.parts)
    return r
